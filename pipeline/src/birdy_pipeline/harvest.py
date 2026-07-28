"""Stream real recordings through the extractor and keep only what fits in a budget.

The point of this module is what it *throws away*. A field corpus is far larger than
anything Birdy can hold, ship or embed: xeno-canto alone carries hundreds of thousands
of recordings, and one 4-minute mp3 becomes ~800 descriptors. So nothing is
accumulated. Each recording is fetched, decoded, sliced, reduced to the 28-d
descriptors of contract 8.2, folded into the store, and then deleted — audio, temporary
file and all — before the next one starts. Peak memory is one recording, not one
corpus.

What survives is a **bounded, species-stratified reservoir** of descriptors:

  - every descriptor the stream produces gets a fair chance of being retained
    (Algorithm R, resumable across runs via a persisted counter);
  - each species gets its own stratum, so a species with 900 recordings on
    xeno-canto cannot bury one with 12;
  - the store never exceeds `--cap` points, however much audio is fed through it.

Running statistics (Welford, elementwise over 28 dims) are kept over *every* descriptor
ever seen, including the discarded ones. They cost 3 floats per dimension and they are
what tells you whether the retained sample is representative: `birdy-pipeline harvest
--stats` prints the drift between the reservoir's own mean/std and the full stream's.
If that drift is large, the cap is too small for the diversity being fed in.

Harvested points are never given a documented function. They are real audio of a known
species and nothing more, so they carry `confidence: "unlabelled"` — the honesty rule of
contract 8.5 applied to data that has no citation behind it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

import numpy as np
import soundfile as sf

from . import features
from .corpus import AUDIO_SUFFIXES, LOCAL_CLIP_SECONDS, LOCAL_HOP_SECONDS, resample
from .galaxy import PointSet
from .learn import SyllableObservation, extract_syllables
from .syrinx import SAMPLE_RATE, peak_normalise

XC_API = "https://xeno-canto.org/api/3/recordings"
XC_PAGE_PAUSE = 1.0
USER_AGENT = "birdy-pipeline/0.1 (research; https://github.com/sha5b/Birdy)"
DOWNLOAD_TIMEOUT = 60
DEFAULT_CAP = 20_000
# Syllable observations are ~30 floats each and are the input to `learn`, which needs
# order within a recording — so they are kept whole per recording rather than sampled,
# and bounded by dropping the oldest recordings' worth once the cap is passed.
DEFAULT_SYLLABLE_CAP = 40_000
DEFAULT_MAX_SECONDS = 90.0
MIN_STRATUM = 64
SOURCE = "field"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- decoding ---------------------------------------------------------------------


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def decode(path: Path, sample_rate: int = SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """Any audio file -> mono float64 at `sample_rate`.

    `soundfile` first; ffmpeg only as a fallback, and then only to transcode to a
    wav at the file's *own* rate. The mono mix (channel mean) and the resampler stay
    the ones `--source local` uses, so a harvested descriptor and a locally-read one
    are computed by the same code from the same samples.
    """
    try:
        data, rate = sf.read(str(path), dtype="float64", always_2d=True)
    except Exception:
        if not have_ffmpeg():
            raise RuntimeError(
                f"{path.name}: soundfile cannot read it and ffmpeg is not installed "
                "(most xeno-canto downloads are mp3)"
            ) from None
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "decoded.wav"
            proc = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(path),
                 "-c:a", "pcm_f32le", "-f", "wav", str(wav)],
                capture_output=True,
            )
            if proc.returncode != 0 or not wav.exists():
                raise RuntimeError(
                    f"{path.name}: ffmpeg failed: {proc.stderr.decode()[:200]}"
                ) from None
            data, rate = sf.read(str(wav), dtype="float64", always_2d=True)
    mono = data.mean(axis=1)
    return resample(mono, int(rate), sample_rate), sample_rate


def slice_descriptors(
    mono: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    clip_seconds: float = LOCAL_CLIP_SECONDS,
    hop_seconds: float = LOCAL_HOP_SECONDS,
    max_seconds: float | None = None,
) -> Iterator[np.ndarray]:
    """Yield one 28-d descriptor per voiced window. The audio is never copied out."""
    if max_seconds is not None:
        mono = mono[: int(max_seconds * sample_rate)]
    win = int(round(clip_seconds * sample_rate))
    hop = max(1, int(round(hop_seconds * sample_rate)))
    for start in range(0, max(1, mono.size - win + 1), hop):
        seg = mono[start : start + win]
        if seg.size < win // 2:
            continue
        d = features.descriptor(peak_normalise(seg), sample_rate)
        if d is not None and np.all(np.isfinite(d)):
            yield d


# --- the bounded store ------------------------------------------------------------


@dataclass
class Stratum:
    """One species' reservoir. `seen` counts everything, retained or not."""

    rows: list[np.ndarray] = field(default_factory=list)
    meta: list[dict[str, Any]] = field(default_factory=list)
    seen: int = 0


class HarvestStore:
    """Species-stratified reservoir of descriptors, persisted between runs.

    Descriptors are tiny (28 floats); it is the audio that is unaffordable, and the
    audio is gone by the time anything reaches this class. A 20 000-point store is
    2.2 MB, so the whole thing is held in memory while harvesting and written once.
    """

    def __init__(
        self,
        root: Path,
        cap: int = DEFAULT_CAP,
        seed: int = 0,
        syllable_cap: int = DEFAULT_SYLLABLE_CAP,
    ):
        self.root = Path(root)
        self.cap = int(cap)
        self.syllable_cap = int(syllable_cap)
        self.rng = np.random.default_rng([seed, 0x8A2E])
        self.strata: dict[str, Stratum] = {}
        self.recordings: dict[str, dict[str, Any]] = {}
        # Kept in recording order. `learn` reads these; the galaxy does not.
        self.syllables: list[SyllableObservation] = []
        # Mean descriptor per recording, so a learned syllable can be checked against
        # the acoustics it was fitted to without keeping any audio.
        self.recording_descriptors: dict[str, list[float]] = {}
        # Welford accumulators over every descriptor the stream has ever produced.
        self.stream_n = 0
        self.stream_mean = np.zeros(features.DIM)
        self.stream_m2 = np.zeros(features.DIM)
        self.load()

    # -- persistence --

    @property
    def _descriptors_path(self) -> Path:
        return self.root / "descriptors.f32"

    @property
    def _points_path(self) -> Path:
        return self.root / "points.jsonl"

    @property
    def _state_path(self) -> Path:
        return self.root / "state.json"

    @property
    def _syllables_path(self) -> Path:
        return self.root / "syllables.jsonl"

    def load(self) -> None:
        if self._syllables_path.exists():
            self.syllables = [
                SyllableObservation.from_dict(json.loads(line))
                for line in self._syllables_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        if not self._state_path.exists():
            return
        state = json.loads(self._state_path.read_text(encoding="utf-8"))
        self.recordings = state.get("recordings", {})
        self.recording_descriptors = state.get("recordingDescriptors", {})
        self.stream_n = int(state.get("streamCount", 0))
        self.stream_mean = np.asarray(state.get("streamMean", self.stream_mean), dtype=np.float64)
        self.stream_m2 = np.asarray(state.get("streamM2", self.stream_m2), dtype=np.float64)

        raw = self._descriptors_path.read_bytes() if self._descriptors_path.exists() else b""
        matrix = np.frombuffer(raw, dtype="<f4").reshape(-1, features.DIM).astype(np.float64)
        meta = [
            json.loads(line)
            for line in self._points_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ] if self._points_path.exists() else []
        if matrix.shape[0] != len(meta):
            raise RuntimeError(
                f"{self.root} is inconsistent: {matrix.shape[0]} descriptors but "
                f"{len(meta)} metadata rows. Delete it and re-harvest."
            )
        seen_counts = state.get("seenPerSpecies", {})
        for row, m in zip(matrix, meta):
            st = self.strata.setdefault(m["speciesId"], Stratum())
            st.rows.append(row)
            st.meta.append(m)
        for sid, n in seen_counts.items():
            self.strata.setdefault(sid, Stratum()).seen = int(n)

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        rows: list[np.ndarray] = []
        meta: list[dict[str, Any]] = []
        for sid in sorted(self.strata):
            st = self.strata[sid]
            rows.extend(st.rows)
            meta.extend(st.meta)
        matrix = (
            np.stack(rows).astype("<f4", copy=False)
            if rows
            else np.zeros((0, features.DIM), dtype="<f4")
        )
        self._descriptors_path.write_bytes(matrix.ravel(order="C").tobytes())
        self._points_path.write_text(
            "\n".join(json.dumps(m, sort_keys=True) for m in meta) + ("\n" if meta else ""),
            encoding="utf-8",
        )
        self._syllables_path.write_text(
            "\n".join(json.dumps(o.to_dict(), sort_keys=True) for o in self.syllables)
            + ("\n" if self.syllables else ""),
            encoding="utf-8",
        )
        self._state_path.write_text(
            json.dumps(
                {
                    "cap": self.cap,
                    "retained": len(meta),
                    "syllableObservations": len(self.syllables),
                    "recordingDescriptors": self.recording_descriptors,
                    "streamCount": self.stream_n,
                    "streamMean": [float(v) for v in self.stream_mean],
                    "streamM2": [float(v) for v in self.stream_m2],
                    "seenPerSpecies": {s: self.strata[s].seen for s in sorted(self.strata)},
                    "recordings": self.recordings,
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        self.write_credits()

    def write_credits(self) -> None:
        """Per-recording attribution and licence. Required by every CC licence xeno-canto uses."""
        lines = [
            "# Harvested recordings",
            "",
            "Every recording below contributed descriptors to this store. The audio itself",
            "was discarded after analysis; these are the sources whose acoustics are in the",
            "galaxy, and their licences travel with them.",
            "",
            "| id | species | recordist | licence | source |",
            "|---|---|---|---|---|",
        ]
        for rid in sorted(self.recordings):
            r = self.recordings[rid]
            lines.append(
                f"| {rid} | {r.get('scientific', '')} | {r.get('recordist', '')} | "
                f"{r.get('licence', '')} | {r.get('url', '')} |"
            )
        (self.root / "CREDITS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # -- accumulation --

    def has(self, recording_id: str) -> bool:
        return recording_id in self.recordings

    def _stratum_cap(self) -> int:
        return max(MIN_STRATUM, self.cap // max(1, len(self.strata)))

    def _rebalance(self) -> None:
        """Trim the largest strata until the store fits the cap.

        Dropping uniformly at random from an oversized stratum leaves the survivors a
        uniform sample of it, so the reservoir property holds after trimming too.
        """
        total = sum(len(s.rows) for s in self.strata.values())
        if total <= self.cap:
            return
        limit = self._stratum_cap()
        for st in sorted(self.strata.values(), key=lambda s: -len(s.rows)):
            while len(st.rows) > limit and total > self.cap:
                victim = int(self.rng.integers(0, len(st.rows)))
                st.rows.pop(victim)
                st.meta.pop(victim)
                total -= 1

    def offer(self, descriptor: np.ndarray, meta: dict[str, Any]) -> bool:
        """Fold one descriptor into the store. Returns whether it was retained.

        Algorithm R against the stratum's own `seen` counter, which is persisted, so
        a store built over ten sessions is the same uniform sample as one built in a
        single pass.
        """
        # running statistics first: the discarded ones count here
        self.stream_n += 1
        delta = descriptor - self.stream_mean
        self.stream_mean += delta / self.stream_n
        self.stream_m2 += delta * (descriptor - self.stream_mean)

        st = self.strata.setdefault(meta["speciesId"], Stratum())
        st.seen += 1
        limit = self._stratum_cap()
        if len(st.rows) < limit:
            st.rows.append(descriptor)
            st.meta.append(meta)
            self._rebalance()
            return True
        j = int(self.rng.integers(0, st.seen))
        if j < limit:
            st.rows[j] = descriptor
            st.meta[j] = meta
            return True
        return False

    def note_recording(self, recording_id: str, info: dict[str, Any]) -> None:
        self.recordings[recording_id] = info

    def add_syllables(self, observations: Sequence[SyllableObservation]) -> int:
        """Keep a recording's syllables whole, then trim the oldest recordings if over cap.

        Unlike the descriptors, these cannot be sampled independently: `learn` counts
        transitions between consecutive syllables, and a reservoir would silently delete
        the middle of every phrase and invent transitions that were never sung.
        """
        self.syllables.extend(observations)
        if len(self.syllables) <= self.syllable_cap:
            return len(observations)
        keep_from = len(self.syllables) - self.syllable_cap
        boundary = self.syllables[keep_from].recording_id
        while keep_from < len(self.syllables) and self.syllables[keep_from].recording_id == boundary:
            keep_from += 1
        self.syllables = self.syllables[keep_from:]
        return len(observations)

    def descriptor_for(self, recording_id: str) -> np.ndarray | None:
        row = self.recording_descriptors.get(recording_id)
        return np.asarray(row, dtype=np.float64) if row else None

    def note_descriptor(self, recording_id: str, mean: np.ndarray) -> None:
        self.recording_descriptors[recording_id] = [round(float(v), 5) for v in mean]

    # -- reading back --

    def __len__(self) -> int:
        return sum(len(s.rows) for s in self.strata.values())

    def stream_std(self) -> np.ndarray:
        if self.stream_n < 2:
            return np.zeros(features.DIM)
        return np.sqrt(self.stream_m2 / self.stream_n)

    def representativeness(self) -> dict[str, float]:
        """How far the retained sample has drifted from the full stream it came from.

        Both numbers are in units of the stream's own standard deviation, averaged over
        the 28 dimensions. Near zero means the reservoir is a faithful miniature of
        everything that was fed through it; large means the cap is too small.
        """
        if len(self) < 2 or self.stream_n < 2:
            return {"meanDrift": 0.0, "stdRatio": 1.0}
        kept = np.stack([r for s in self.strata.values() for r in s.rows])
        s = np.maximum(self.stream_std(), 1e-9)
        return {
            "meanDrift": float(np.mean(np.abs(kept.mean(axis=0) - self.stream_mean) / s)),
            "stdRatio": float(np.mean(kept.std(axis=0) / s)),
        }

    def to_point_set(self) -> PointSet:
        rows: list[np.ndarray] = []
        meta: list[dict[str, Any]] = []
        for sid in sorted(self.strata):
            rows.extend(self.strata[sid].rows)
            meta.extend(self.strata[sid].meta)
        if not rows:
            raise RuntimeError(f"{self.root} holds no descriptors yet — run `harvest` first")
        return PointSet(
            x=np.stack(rows),
            species_id=[m["speciesId"] for m in meta],
            syllable_id=["" for _ in meta],
            song_id=[m.get("recordingId", "") for m in meta],
            duration=[float(m.get("duration", LOCAL_CLIP_SECONDS)) for m in meta],
            source=[m.get("source", SOURCE) for m in meta],
        )

    def summary(self) -> str:
        rep = self.representativeness()
        per = ", ".join(
            f"{sid} {len(self.strata[sid].rows)}/{self.strata[sid].seen}"
            for sid in sorted(self.strata, key=lambda s: -len(self.strata[s].rows))[:8]
        )
        return (
            f"{len(self)} descriptors retained of {self.stream_n} seen "
            f"({len(self.recordings)} recordings, cap {self.cap}, "
            f"{len(self.strata)} species)\n"
            f"  retained/seen per species: {per}\n"
            f"  sample drift from the full stream: mean {rep['meanDrift']:.3f} sd, "
            f"spread ratio {rep['stdRatio']:.3f} (1.0 = identical spread)"
        )


# --- xeno-canto -------------------------------------------------------------------


class XenoCanto:
    """Minimal v3 client. The key is the caller's; nothing is cached beyond the store.

    v2 is retired and v3 requires a personal API key, so this cannot be run without
    the user supplying one. Requests are spaced by `pause` seconds because the service
    rate-limits and a research corpus is not worth being blocked over.
    """

    def __init__(self, key: str, pause: float = XC_PAGE_PAUSE):
        if not key:
            raise RuntimeError(
                "xeno-canto v3 needs an API key. Create one at "
                "https://xeno-canto.org/account and pass --xc-key, or set XC_API_KEY."
            )
        self.key = key
        self.pause = pause
        self._last = 0.0

    def _wait(self) -> None:
        gap = self.pause - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()

    def _get(self, url: str) -> Any:
        self._wait()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as res:
            return json.loads(res.read().decode("utf-8"))

    def search(self, query: str, max_pages: int = 3) -> Iterator[dict[str, Any]]:
        page = 1
        while page <= max_pages:
            url = f"{XC_API}?{urllib.parse.urlencode({'query': query, 'key': self.key, 'page': page})}"
            try:
                data = self._get(url)
            except urllib.error.HTTPError as exc:
                raise RuntimeError(
                    f"xeno-canto returned {exc.code} for {query!r}"
                    + (" — check the API key" if exc.code in (401, 403) else "")
                ) from None
            recordings = data.get("recordings", [])
            if not recordings:
                return
            yield from recordings
            if page >= int(data.get("numPages", 1)):
                return
            page += 1

    def download(self, recording: dict[str, Any], dest: Path) -> Path:
        url = recording.get("file") or ""
        if not url:
            raise RuntimeError(f"recording {recording.get('id')} has no file url")
        self._wait()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as res:
            suffix = Path(urllib.parse.urlparse(res.geturl()).path).suffix or ".mp3"
            out = dest / f"xc{recording['id']}{suffix}"
            with out.open("wb") as fh:
                shutil.copyfileobj(res, fh, length=1 << 16)
        return out


def species_queries(inventory: dict[str, Any], quality: str = "") -> list[tuple[str, str]]:
    """(speciesId, xeno-canto query) for every species the inventory already knows.

    Harvesting these and only these is what makes the result usable: the points land
    under species ids the app can already name, so the galaxy grows around the
    documented clusters instead of beside them.
    """
    out: list[tuple[str, str]] = []
    for sp in inventory.get("species", []):
        scientific = sp.get("scientific", "").strip()
        if not scientific or " " not in scientific:
            continue
        genus, epithet = scientific.split(" ", 1)
        query = f'gen:"{genus}" sp:"{epithet.split()[0]}"'
        if quality:
            query += f" q:{quality}"
        out.append((sp["id"], query))
    return out


# --- the harvest loop -------------------------------------------------------------


@dataclass
class HarvestReport:
    recordings: int = 0
    skipped: int = 0
    failed: int = 0
    descriptors: int = 0
    retained: int = 0
    syllables: int = 0
    seconds: float = 0.0


def ingest_file(
    store: HarvestStore,
    path: Path,
    species_id: str,
    recording_id: str,
    max_seconds: float | None,
    report: HarvestReport,
    segment: bool = True,
) -> None:
    """Decode, analyse twice, and let the audio go out of scope. Nothing is kept.

    Both passes happen here, in the one window where the samples exist: the sliding
    descriptors that become galaxy points, and the segmented syllables that become the
    learned repertoire. Doing them separately would mean fetching and decoding every
    recording twice.
    """
    mono, rate = decode(path)
    report.seconds += mono.size / rate

    rows: list[np.ndarray] = []
    for descriptor in slice_descriptors(mono, rate, max_seconds=max_seconds):
        report.descriptors += 1
        rows.append(descriptor)
        if store.offer(
            descriptor,
            {
                "speciesId": species_id,
                "recordingId": recording_id,
                "duration": LOCAL_CLIP_SECONDS,
                "source": SOURCE,
            },
        ):
            report.retained += 1
    if rows:
        store.note_descriptor(recording_id, np.mean(np.stack(rows), axis=0))

    if segment:
        report.syllables += store.add_syllables(
            extract_syllables(mono, rate, species_id, recording_id, max_seconds=max_seconds)
        )
    del mono, rows


def harvest_xeno_canto(
    store: HarvestStore,
    client: XenoCanto,
    targets: Iterable[tuple[str, str]],
    per_species: int = 20,
    max_seconds: float | None = DEFAULT_MAX_SECONDS,
    max_pages: int = 3,
    dry_run: bool = False,
    should_stop: Callable[[], bool] | None = None,
) -> HarvestReport:
    """`should_stop` is polled between recordings, so a run can be asked to end.

    Between, not during: one recording is one indivisible unit of work — it is fetched,
    analysed and deleted — and everything already ingested is kept, because a stopped
    harvest is a shorter harvest rather than a wasted one.
    """
    report = HarvestReport()
    for species_id, query in targets:
        if should_stop and should_stop():
            log("\nstopping: asked to")
            return report
        log(f"\n{species_id}: {query}")
        taken = 0
        for rec in client.search(query, max_pages=max_pages):
            if taken >= per_species:
                break
            if should_stop and should_stop():
                log("  stopping: asked to")
                return report
            rid = f"XC{rec.get('id')}"
            if store.has(rid):
                report.skipped += 1
                continue
            info = {
                "speciesId": species_id,
                "scientific": f"{rec.get('gen', '')} {rec.get('sp', '')}".strip(),
                "english": rec.get("en", ""),
                "recordist": rec.get("rec", ""),
                "licence": rec.get("lic", ""),
                "quality": rec.get("q", ""),
                "type": rec.get("type", ""),
                "country": rec.get("cnt", ""),
                "url": rec.get("url", ""),
            }
            if dry_run:
                log(f"  would fetch {rid}  q={info['quality']:1}  {info['type'][:40]:40}  {info['licence']}")
                taken += 1
                report.recordings += 1
                continue
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    audio_path = client.download(rec, Path(tmp))
                    before = report.retained
                    ingest_file(store, audio_path, species_id, rid, max_seconds, report)
                except Exception as exc:
                    report.failed += 1
                    log(f"  skip {rid}: {exc}")
                    continue
            # the TemporaryDirectory is gone here: the audio existed for one iteration
            store.note_recording(rid, info)
            taken += 1
            report.recordings += 1
            log(
                f"  {rid:10} q={info['quality']:1} {info['type'][:34]:34} "
                f"+{report.retained - before:4d} kept  store={len(store)}"
            )
    return report


def harvest_directory(
    store: HarvestStore,
    audio_dir: Path,
    max_seconds: float | None = None,
    species_id: str | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> HarvestReport:
    """The same streaming path over files already on disk — no network, no key.

    Labels come from the parent directory name, matching `--source local`.
    """
    audio_dir = Path(audio_dir)
    report = HarvestReport()
    paths = [
        p
        for p in sorted(audio_dir.rglob("*"))
        if p.is_file() and (p.suffix.lower() in AUDIO_SUFFIXES or p.suffix.lower() == ".mp3")
    ]
    if not paths:
        raise FileNotFoundError(f"no audio under {audio_dir}")
    for path in paths:
        if should_stop and should_stop():
            log("stopping: asked to")
            return report
        rid = path.stem
        if store.has(rid):
            report.skipped += 1
            continue
        label = species_id or (path.parent.name if path.parent != audio_dir else "unlabelled")
        before = report.retained
        try:
            ingest_file(store, path, label, rid, max_seconds, report)
        except Exception as exc:
            report.failed += 1
            log(f"  skip {path.name}: {exc}")
            continue
        store.note_recording(
            rid,
            {"speciesId": label, "recordist": "", "licence": "local file", "url": str(path)},
        )
        report.recordings += 1
        log(f"  {path.name[:40]:40} +{report.retained - before:4d} kept  store={len(store)}")
    return report


def format_report(report: HarvestReport, store: HarvestStore) -> str:
    rate = 100.0 * report.retained / report.descriptors if report.descriptors else 0.0
    audio_mb_avoided = report.seconds * SAMPLE_RATE * 4 / 1e6
    return (
        f"\n{report.recordings} recordings ingested, {report.skipped} already known, "
        f"{report.failed} failed\n"
        f"{report.descriptors} descriptors produced from {report.seconds / 60:.1f} min of "
        f"audio; {report.retained} retained ({rate:.1f} %)\n"
        f"{report.syllables} syllables segmented, {len(store.syllables)} held for learning\n"
        f"{audio_mb_avoided:.0f} MB of decoded audio passed through and was discarded; "
        f"the store is {len(store) * features.DIM * 4 / 1e6:.2f} MB\n"
        f"{store.summary()}"
    )
