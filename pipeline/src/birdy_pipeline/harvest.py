"""Stream real recordings through the extractor and keep only what fits in a budget.

The point of this module is what it *throws away*. A field corpus is far larger than
anything Lyrebird can hold, ship or embed: xeno-canto alone carries hundreds of thousands
of recordings, and one 4-minute mp3 becomes ~800 descriptors. So nothing is
accumulated in the store. Each recording is fetched, decoded, sliced, reduced to the 28-d
descriptors of contract 8.2, folded into the store, and then deleted — audio, temporary
file and all — before the next one starts. Peak memory is one recording, not one
corpus.

**Deleting the audio is the default, and since 2026-08-01 it is only the default**
(owner decision). `--keep-audio DIR` copies each analysed recording into `DIR` before the
temporary directory is torn down, but only where the recording's licence permits it —
`audio_may_be_cached` below, which **refuses NoDerivatives** and **refuses an unrecorded
licence**, because absence of a licence is not permission. Peak memory is unchanged
either way; what changes is whether the file survives the loop. Nothing audio ever
reaches the browser or an asset set: retention is not redistribution, and that is the
line that keeps it so. See the repository's `NOTICE.md` §3.4.

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
from .learn import SEGMENT_BAND_HZ, SyllableObservation, extract_syllables
from .syrinx import SAMPLE_RATE, peak_normalise

XC_API = "https://xeno-canto.org/api/3/recordings"
XC_PAGE_PAUSE = 1.0
# The repo URL is the live one. The product is now called Lyrebird, but the GitHub repo is
# still `Birdy` — the owner renames it separately, and until then this URL must resolve,
# because xeno-canto's terms ask a bulk client to be identifiable.
USER_AGENT = "birdy-pipeline/0.1 (research; https://github.com/sha5b/Birdy)"
DOWNLOAD_TIMEOUT = 60
# Searching is slower than downloading, and by a lot.
#
# A download is a static file off a CDN; a search makes xeno-canto count and page a result
# set, and `q:">B"` over a common European bird matches thousands of recordings. Measured
# from here: a `Cuculus canorus` search takes about 15 s, and the common species are far
# worse — which is why harvests kept dying on `Parus minor` with a read timeout while the
# audio itself was never the problem. Sharing the download timeout meant the slowest step in
# the pipeline had the tightest budget.
SEARCH_TIMEOUT = 180
# Decline a recording this long before downloading it. Ten minutes is well past any single
# bout and comfortably past `DEFAULT_MAX_SECONDS` of analysis; what sits above it on
# xeno-canto is dawn-chorus soundscapes, which are mostly other species anyway.
DEFAULT_MAX_LENGTH_SECONDS = 600.0


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _length_seconds(text: str) -> float | None:
    """`"3:07"` or `"1:02:11"` to seconds; None when xeno-canto gives us nothing usable."""
    parts = str(text or "").strip().split(":")
    if not parts or not all(p.strip().isdigit() for p in parts):
        return None
    total = 0.0
    for part in parts:
        total = total * 60 + int(part)
    return total
# Raised from 20_000 once discovery started adding species.
#
# The reservoir is stratified, so the cap divides by however many species are being collected:
# at 20_000 the original twelve held about 1_670 descriptors each, and adding fourteen
# discovered birds would have cut every one of them to ~770 to make room. It also had a second
# cost nobody would guess from the number — a *full* store cannot grow, only replace, because
# Algorithm R swaps random slots and the changed descriptors are no longer a suffix any append
# can express. So every pass ended in a full rebuild, and the arrival animation the renderer
# already implements (`aBorn`/`uArrival`) never had a generation to play.
DEFAULT_CAP = 60_000
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


#: A window must hold at least this much segmented syllable to count as a bird.
MIN_SYLLABLE_OVERLAP_S = 0.08


def slice_descriptors(
    mono: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    clip_seconds: float = LOCAL_CLIP_SECONDS,
    hop_seconds: float = LOCAL_HOP_SECONDS,
    max_seconds: float | None = None,
    voiced: Sequence[tuple[float, float]] | None = None,
) -> Iterator[np.ndarray]:
    """Yield one 28-d descriptor per window that holds a bird. Audio is never copied out.

    `voiced` is the segmenter's syllable spans, and passing it is what keeps the galaxy a
    picture of birdsong rather than of the places birds were recorded. Without it every
    0.6 s of a field recording becomes a point, gaps included, and a recording is mostly
    gaps: wind, traffic, a river, the two seconds before the bird answers. Those windows
    cluster together perfectly happily, and then the corpus contains a cluster whose
    honest description is "background", which white noise matches at 0.99 — measured, on
    the build before this: the live match meter read 0.987 for noise against a floor of
    0.78, so the galaxy lit up on room tone.

    The descriptor's own voicing test cannot catch this, because it is relative to each
    window's own peak: a window of pure wind has a loudest 5 % too.
    """
    if max_seconds is not None:
        mono = mono[: int(max_seconds * sample_rate)]
    win = int(round(clip_seconds * sample_rate))
    hop = max(1, int(round(hop_seconds * sample_rate)))
    spans = sorted(voiced) if voiced else None
    for start in range(0, max(1, mono.size - win + 1), hop):
        seg = mono[start : start + win]
        if seg.size < win // 2:
            continue
        if spans is not None:
            t0 = start / sample_rate
            t1 = (start + seg.size) / sample_rate
            overlap = sum(max(0.0, min(t1, b) - max(t0, a)) for a, b in spans)
            if overlap < MIN_SYLLABLE_OVERLAP_S:
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
        cap: int | None = None,
        seed: int = 0,
        syllable_cap: int | None = None,
        load_syllables: bool = True,
    ):
        """`load_syllables=False` skips `syllables.jsonl` and `patches.f16`.

        **For callers that only want to report how big the store is.** Those two files are
        the whole weight of a store — 26 MB of JSONL and 13 MB of patches at 9 k syllables,
        and about three times that at 40 k — while everything else here is under 2 MB. The
        server's status endpoint was rebuilding a `HarvestStore` on *every poll*, which put a
        1.3-second JSON parse behind a request the interface makes every 1.5 seconds; it only
        ever read `len(self.syllables)`, and `state.json` records that count already.

        `syllable_count` is the accessor that works either way. Anything that touches
        `self.syllables` itself must load them.

        `cap=None` (the default) means "the store's own caps": whatever the last writer
        saved into `state.json`, falling back to the module defaults for a fresh store.
        Passing a number is an explicit override and is persisted on save. This ordering
        exists because the alternative — every caller defaulting to the module constants —
        is a silent trap: fetch with raised caps once, and the next default-cap ingest
        trims the enlarged store back down without a word.
        """
        self.root = Path(root)
        self._cap_override = None if cap is None else int(cap)
        self._syllable_cap_override = None if syllable_cap is None else int(syllable_cap)
        self.cap = self._cap_override or DEFAULT_CAP
        self.syllable_cap = self._syllable_cap_override or DEFAULT_SYLLABLE_CAP
        self.load_syllables = bool(load_syllables)
        self.rng = np.random.default_rng([seed, 0x8A2E])
        self.strata: dict[str, Stratum] = {}
        self.recordings: dict[str, dict[str, Any]] = {}
        # Kept in recording order. `learn` reads these; the galaxy does not.
        self.syllables: list[SyllableObservation] = []
        #: Count from `state.json`, so it is available when the rows were not loaded.
        self._recorded_syllable_count = 0
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

    @property
    def _patches_path(self) -> Path:
        """The critic's log-mel patches, one row per syllable, in `syllables.jsonl` order.

        A binary sidecar rather than a field in the JSONL because it is a matrix: 736
        float16s per syllable is 1.4 KB here and about 7 KB as rounded JSON, and the JSONL
        is parsed in full on every load. Row order is the only thing tying the two files
        together, so `load` refuses a pair whose counts disagree rather than silently
        misattributing every patch to the wrong syllable.

        This is still a measurement and not a recording — log magnitudes, no phase, mean
        centred (see `features.mel_patch`) — so the licensing property of §9.4 holds.
        """
        return self.root / "patches.f16"

    @property
    def syllable_count(self) -> int:
        """How many syllable observations the store holds, loaded or not."""
        return len(self.syllables) if self.load_syllables else self._recorded_syllable_count

    def load(self) -> None:
        if self.load_syllables and self._syllables_path.exists():
            self.syllables = [
                SyllableObservation.from_dict(json.loads(line))
                for line in self._syllables_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self._load_patches()
        # Recordings that can never be fetched, and species where none of them can.
        #
        # `has()` only remembers *successes*, so a recording that 404s or is redacted was
        # re-attempted on every pass forever — and the zebra finch, whose audio xeno-canto
        # withholds as a restricted species, burned a search plus seventeen skips per pass to
        # arrive at the same answer. Neither is an error worth retrying: a redaction is policy
        # and a 404 is a deleted file.
        #
        # Initialised before the early return, because a store with no `state.json` is a
        # *new* store, and a new store still has to answer `restricted` and `dead` — the
        # harvest asks both before it has written anything. Setting them only on the load
        # path meant the very first harvest into a fresh directory raised AttributeError.
        self.dead: dict[str, Any] = {}
        self.restricted: set[str] = set()
        if not self._state_path.exists():
            return
        state = json.loads(self._state_path.read_text(encoding="utf-8"))
        if self._cap_override is not None:
            self.cap = self._cap_override
        else:
            self.cap = int(state.get("cap", DEFAULT_CAP))
        if self._syllable_cap_override is not None:
            self.syllable_cap = self._syllable_cap_override
        else:
            self.syllable_cap = int(state.get("syllableCap", DEFAULT_SYLLABLE_CAP))
        shape = state.get("patchShape")
        if shape is not None and tuple(shape) != features.PATCH_SHAPE:
            raise RuntimeError(
                f"{self.root} holds {tuple(shape)} patches but this build measures "
                f"{features.PATCH_SHAPE}. A patch is only comparable with another taken by "
                f"the same code, so mixing the two would train the critic on two different "
                f"representations. Re-harvest into a fresh store, or check out the commit "
                f"whose `features.PATCH_*` constants match."
            )
        self.recordings = state.get("recordings", {})
        self.dead = dict(state.get("dead", {}))
        self.restricted = set(state.get("restricted", []))
        self.recording_descriptors = state.get("recordingDescriptors", {})
        self._recorded_syllable_count = int(state.get("syllableObservations", 0))
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

    #: Rows whose first value is NaN mean "this syllable has no patch". float16 NaN is
    #: representable and `features.mel_patch` can never produce one — it is the log of a
    #: value floored at `BAND_FLOOR` — so this marks absence without a second file and
    #: without confusing a missing patch for a silent one. It matters because a store
    #: harvested before patches existed can still have new observations appended to it.
    _PATCH_ABSENT = np.float16("nan")

    def _load_patches(self) -> None:
        if not self._patches_path.exists():
            return
        blob = self._patches_path.read_bytes()
        # Byte length before element count: a file truncated mid-value is not a multiple of
        # 2 either, and `np.frombuffer` would raise "buffer size must be a multiple of element
        # size" — true, but it names neither the file nor the fix.
        if len(blob) % (features.PATCH_DIM * 2) != 0:
            raise RuntimeError(
                f"{self._patches_path} is {len(blob)} bytes, which is not a whole number of "
                f"{features.PATCH_SHAPE} float16 patches ({features.PATCH_DIM * 2} bytes "
                f"each). It is truncated or was written by a build with different patch "
                f"constants; delete it and re-harvest."
            )
        raw = np.frombuffer(blob, dtype="<f2")
        if raw.size % features.PATCH_DIM != 0:
            raise RuntimeError(
                f"{self._patches_path} holds {raw.size} float16s, which is not a whole "
                f"number of {features.PATCH_SHAPE} patches. It was written by a build with "
                f"different patch constants; delete it and re-harvest."
            )
        rows = raw.reshape(-1, *features.PATCH_SHAPE)
        if rows.shape[0] != len(self.syllables):
            raise RuntimeError(
                f"{self.root} is inconsistent: {rows.shape[0]} patches but "
                f"{len(self.syllables)} syllable observations. Row order is the only thing "
                f"pairing them, so this cannot be reconciled — delete "
                f"{self._patches_path.name} and re-harvest to restore it."
            )
        for o, row in zip(self.syllables, rows):
            o.mel_patch = None if np.isnan(row[0, 0]) else row

    def _save_patches(self) -> None:
        """Write the sidecar, or remove it when no observation carries a patch."""
        if not any(o.mel_patch is not None for o in self.syllables):
            self._patches_path.unlink(missing_ok=True)
            return
        absent = np.full(features.PATCH_SHAPE, self._PATCH_ABSENT, dtype="<f2")
        stacked = np.stack([
            absent if o.mel_patch is None else np.asarray(o.mel_patch, dtype="<f2")
            for o in self.syllables
        ])
        self._patches_path.write_bytes(stacked.ravel(order="C").tobytes())

    def save(self) -> None:
        # **A store opened without its syllables must never be written back.** `save` rewrites
        # `syllables.jsonl` and `patches.f16` from the in-memory lists, which are empty here,
        # so this would silently replace the most expensive thing in the repository with
        # nothing — 40 000 observations gathered under xeno-canto's rate limits, of which
        # there is one copy (docs/09 §9.4). Refuse loudly instead.
        if not self.load_syllables:
            raise RuntimeError(
                f"refusing to save {self.root}: it was opened with load_syllables=False, so "
                f"its {self._recorded_syllable_count} syllable observations are not in memory "
                f"and saving would erase them. Re-open it with load_syllables=True to write."
            )
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
        self._save_patches()
        self._state_path.write_text(
            json.dumps(
                {
                    "cap": self.cap,
                    "syllableCap": self.syllable_cap,
                    "retained": len(meta),
                    "syllableObservations": len(self.syllables),
                    # Recorded so a store carries its own patch geometry: changing
                    # `features.PATCH_*` invalidates every patch ever written, and this is
                    # what lets `critic.py` say so instead of training on a reshaped mess.
                    "patchShape": list(features.PATCH_SHAPE),
                    # The segmentation band of the build that wrote this state, so a store
                    # says which regime it was last ingested under instead of leaving it to
                    # be inferred (`learn.SEGMENT_BAND_HZ`; `null` is the full-band
                    # behaviour every store harvested before it existed used).
                    #
                    # **It describes the latest ingest, not every row.** A store that
                    # accumulated across the change is mixed and this cannot say so —
                    # `out/harvest-gan` is exactly such a store, 340 122 rows segmented
                    # full-band with anything added afterwards segmented in-band. Recorded
                    # rather than omitted because "unknown" and "full-band" were previously
                    # the same silence, and `quality.remeasure_store` has to tell them apart.
                    "segmentBand": (
                        None if SEGMENT_BAND_HZ is None else list(SEGMENT_BAND_HZ)
                    ),
                    "patchesWithData": sum(
                        1 for o in self.syllables if o.mel_patch is not None
                    ),
                    "recordingDescriptors": self.recording_descriptors,
                    "streamCount": self.stream_n,
                    "streamMean": [float(v) for v in self.stream_mean],
                    "streamM2": [float(v) for v in self.stream_m2],
                    "seenPerSpecies": {s: self.strata[s].seen for s in sorted(self.strata)},
                    "recordings": self.recordings,
                    "dead": self.dead,
                    "restricted": sorted(self.restricted),
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        self.write_credits()

    def mark_dead(self, recording_id: str, reason: str) -> None:
        self.dead[recording_id] = reason[:120]

    def mark_restricted(self, species_id: str) -> None:
        self.restricted.add(species_id)

    def write_credits(self) -> None:
        """Per-recording attribution and licence. Required by every CC licence xeno-canto uses."""
        lines = [
            "# Harvested recordings",
            "",
            "Every recording below contributed descriptors to this store. The audio itself",
            "was discarded after analysis unless `harvest --keep-audio` kept a",
            "licence-permitting copy on this machine; either way none of it is shipped.",
            "These are the sources whose acoustics are in the galaxy. Their per-recording",
            "licences are not ours to change, and both the licence and the recordist below",
            "must travel with the recording and with anything derived from it.",
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
        """Keep each recording's syllables whole, and trim **per species** when over cap.

        Unlike the descriptors, these cannot be sampled independently: `learn` counts
        transitions between consecutive syllables, and a reservoir would silently delete
        the middle of every phrase and invent transitions that were never sung. So whatever
        goes has to go a whole recording at a time.

        **Which recording, though, is the part that was wrong.** This used to drop the oldest
        ones until the store fitted — and a harvest works through its species one at a time,
        so "oldest" means "the species collected first". Growing `out/harvest-gan` from 9 k to
        40 k syllables that way deleted **twelve of twenty-five species outright**, including
        the two with the largest fitted repertoires, while `strata` still listed all
        twenty-five because the descriptor reservoir trims per stratum and never had this
        problem. The galaxy showed a bird the learning set no longer contained, and the
        measurement taken on that store silently became a 13-species one.

        So this mirrors `_rebalance`: repeatedly retire the oldest recording of whichever
        species currently has the most syllables. That converges on an even split rather than
        a chronological one, and because the victim is always the current largest, a species
        cannot be emptied while another still has more than it.
        """
        self.syllables.extend(observations)
        if len(self.syllables) <= self.syllable_cap:
            return len(observations)

        # recordings per species, in arrival order, with their syllable counts
        recordings: dict[str, list[str]] = {}
        per_recording: dict[tuple[str, str], int] = {}
        per_species: dict[str, int] = {}
        for o in self.syllables:
            key = (o.species_id, o.recording_id)
            if key not in per_recording:
                per_recording[key] = 0
                recordings.setdefault(o.species_id, []).append(o.recording_id)
            per_recording[key] += 1
            per_species[o.species_id] = per_species.get(o.species_id, 0) + 1

        total = len(self.syllables)
        dropped: set[tuple[str, str]] = set()
        while total > self.syllable_cap:
            available = [s for s, rids in recordings.items() if rids]
            if not available:
                break
            victim = max(available, key=lambda s: per_species[s])
            rid = recordings[victim].pop(0)
            dropped.add((victim, rid))
            total -= per_recording[(victim, rid)]
            per_species[victim] -= per_recording[(victim, rid)]

        if dropped:
            self.syllables = [
                o for o in self.syllables
                if (o.species_id, o.recording_id) not in dropped
            ]
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

    def syllable_point_set(self, typing: dict[str, Any]) -> PointSet:
        """One point per stored syllable observation, each carrying its learned type id.

        **Why this exists next to `to_point_set`.** The reservoir points are 0.6 s
        windows — the unit the browser's live path analyses, which is why they still
        define the standardisation frame in `feature-space.json`. But a window is not a
        measurement of a syllable: it averages the syllable with whatever silence and
        hedgerow shared the window, and it cannot say which learned type it contains.
        The observations can. Each was measured from its own segmented audio while that
        audio still existed, and `learn` has already assigned it a type, so one row per
        observation is both the sharper point and the honest one: a knot built from
        these has the extent of what real birds sang, not of how we sliced the
        recordings.

        `typing` is the parsed `typing.json` `learn` writes into this store. An
        observation with no entry — its species was too sparse to fit — keeps an empty
        `syllable_id`. An observation with no descriptor is skipped: stores harvested
        before that field existed do not have it, and a point without a vector is not a
        point. If *no* observation carries one there is nothing to build, which is a
        hard error rather than an empty galaxy.
        """
        type_of = {
            (e["speciesId"], e["recordingId"], int(e["order"])): str(e["typeId"])
            for e in typing.get("entries", [])
        }
        kept = [o for o in self.syllables if o.descriptor]
        if not kept:
            raise RuntimeError(
                f"{self.root} holds {len(self.syllables)} syllable observations but none "
                "carries a descriptor — the store predates that field, so syllable-level "
                "field points cannot be built from it. Re-harvest, or build with "
                "--field-source windows."
            )
        return PointSet(
            x=np.stack([np.asarray(o.descriptor, dtype=np.float64) for o in kept]),
            species_id=[o.species_id for o in kept],
            syllable_id=[
                type_of.get((o.species_id, o.recording_id, o.order), "") for o in kept
            ],
            song_id=[o.recording_id for o in kept],
            duration=[float(o.dur) for o in kept],
            source=[SOURCE] * len(kept),
            # Carried through to `points.json` as a data channel, so the browser can show
            # the corpus's quality axis instead of only its shape. `None` where the row
            # was never measured, which the pipeline treats as neutral and not as bad.
            snr=[None if o.snr is None else float(o.snr) for o in kept],
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
        with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT) as res:
            return json.loads(res.read().decode("utf-8"))

    # A search that times out is a slow server, not a broken pipeline.
    #
    # **This is what killed the loop.** `_get` has a timeout, `search` caught `HTTPError`
    # and nothing else, so a single slow response raised `TimeoutError` out of the generator,
    # out of `harvest_xeno_canto`, and out of the job — sixty seconds into a run that was
    # meant to continue until stopped. One unlucky request should cost one species' page, not
    # the session, and a bad key should still fail loudly on the first try, which is why the
    # HTTP errors below are not retried.
    SEARCH_ATTEMPTS = 3
    SEARCH_BACKOFF_S = 2.0

    def _search_page(self, url: str, query: str) -> dict[str, Any] | None:
        for attempt in range(1, self.SEARCH_ATTEMPTS + 1):
            try:
                return self._get(url)
            except urllib.error.HTTPError as exc:
                raise RuntimeError(
                    f"xeno-canto returned {exc.code} for {query!r}"
                    + (" — check the API key" if exc.code in (401, 403) else "")
                ) from None
            except (TimeoutError, OSError, ValueError) as exc:
                # OSError covers URLError and socket errors; ValueError covers a truncated
                # body that will not parse as JSON.
                if attempt == self.SEARCH_ATTEMPTS:
                    log(f"skip {query}: {type(exc).__name__}: {exc} after {attempt} tries")
                    return None
                log(f"retrying {query}: {type(exc).__name__}: {exc}")
                time.sleep(self.SEARCH_BACKOFF_S * attempt)
        return None

    def search(self, query: str, max_pages: int = 3) -> Iterator[dict[str, Any]]:
        page = 1
        while page <= max_pages:
            url = f"{XC_API}?{urllib.parse.urlencode({'query': query, 'key': self.key, 'page': page})}"
            data = self._search_page(url, query)
            if data is None:
                return
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
            # xeno-canto redacts the audio (and the location) for species it considers at
            # risk from trapping or disturbance, and says so only in `_meta`. Reporting it
            # as a missing url made the zebra finch look like a transient fetch failure
            # worth retrying; it is a policy decision, and no query will get round it.
            redacted = (recording.get("_meta") or {}).get("redacted_fields") or {}
            why = redacted.get("file")
            if why:
                raise RuntimeError(
                    f"recording {recording.get('id')} has no audio: xeno-canto redacts it ({why})"
                )
            raise RuntimeError(f"recording {recording.get('id')} has no file url")
        self._wait()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as res:
            suffix = Path(urllib.parse.urlparse(res.geturl()).path).suffix or ".mp3"
            out = dest / f"xc{recording['id']}{suffix}"
            with out.open("wb") as fh:
                shutil.copyfileobj(res, fh, length=1 << 16)
        return out


def quality_term(quality: str) -> str:
    """xeno-canto's quality term for a filter like ``A`` or ``>B``.

    A comparison has to be quoted: ``q:">B"``. Bare ``q:>B`` and the older website syntax
    ``q>:B`` are both rejected by API v3 with a 400 and the message that it "only accepts
    queries using tags", which does not obviously point at the operator. Measured against
    the live API: ``q:">B"`` returns 17 zebra finch recordings, ``q:B`` 23, unfiltered 49.
    """
    quality = quality.strip()
    if not quality:
        return ""
    if quality[0] in "<>":
        return f'q:"{quality}"'
    return f"q:{quality}"


DISCOVERED_NAME = "discovered-species.json"


def species_id_for(scientific: str) -> str:
    """`Cuculus canorus` -> `cuculus_canorus`, matching the ids the inventory already uses."""
    parts = [p for p in str(scientific or "").strip().split() if p]
    if len(parts) < 2:
        return ""
    return f"{parts[0].lower()}_{parts[1].lower()}"


def canonical_species_id(value: str) -> str:
    """`Cuculus canorus` **or** `cuculus_canorus` -> `cuculus_canorus`.

    For species asks that come from a human or from a generated file, where both spellings
    are legitimate. `species_id_for` stays strict on purpose — it is fed scientific names by
    the fetchers, and a one-word name there is bad metadata that should read as empty rather
    than be waved through — so widening it would hide real errors at the ingest boundary.

    **This function exists because its absence silently ran a 73-minute sweep on the wrong
    thing.** `sources fetch --species-file` documents "ids or \"Genus species\"", and
    `analysis/topup_underfloor.py` writes ids; every one of them went through
    `species_id_for`, came back `""`, was dropped by a `discard("")`, and left the wanted set
    **empty** — which the filter reads as "no filter". The result was an unfiltered
    taxonomic-order pass: of 1 287 recordings ingested against a 1 160-species target list,
    302 landed on a target. A filter that silently becomes a no-op when its input is the
    documented format is worse than one that raises.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    parts = [p for p in text.split() if p]
    if len(parts) >= 2:
        return f"{parts[0].lower()}_{parts[1].lower()}"
    # One word: an id already, if it is shaped like one. A bare genus is not a species and
    # must not become `genus_` or match anything. A trinomial is cut to its binomial, which is
    # what the spaced branch above already does to "Acanthis hornemanni exilipes".
    chunks = [c for c in parts[0].lower().split("_") if c]
    if len(chunks) >= 2:
        return f"{chunks[0]}_{chunks[1]}"
    return ""


def load_discovered(path: Path) -> list[dict[str, Any]]:
    """Species found by `--discover`, kept out of the authored inventory on purpose.

    `data/inventory.json` is the file that carries functions and citations, and a species
    nobody has written anything about does not belong in it. This registry sits beside it and
    is unioned in wherever the pipeline asks "which birds are we collecting?", so a discovered
    bird is harvested, fitted, rendered and analysed exactly like the twelve, while the
    provenance of the authored file stays intact.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data.get("species", []) if e.get("scientific")]


def save_discovered(path: Path, entries: Sequence[dict[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps({"note": "species found by harvest --discover", "species": list(entries)}, indent=1),
        encoding="utf-8",
    )


def discover_species(
    client: XenoCanto,
    known: set[str],
    limit: int = 4,
    query: str | None = None,
    genera: Sequence[str] = (),
    max_pages: int = 1,
) -> list[dict[str, Any]]:
    """Find species xeno-canto has and the inventory does not.

    The default search is **congeners**: for each genus already in the inventory, ask what else
    xeno-canto holds in that genus. That is a more defensible expansion than a global
    best-quality sweep, which returns whatever happens to be popular — a bird in the same genus
    as one we already model is close enough that the existing syrinx parameter ranges are
    likely to reach it, and close enough that a confusion between the two is interesting rather
    than noise.

    Nothing is downloaded here. Only the metadata is read, and the result is a candidate list
    ranked by how much audio exists, because a species with four recordings cannot clear
    `MIN_OBSERVATIONS` and would sit in the inventory as a permanent empty knot.
    """
    counts: dict[str, dict[str, Any]] = {}
    queries = [query] if query else [f'gen:"{g}"' for g in genera]
    for q in queries:
        if not q:
            continue
        log(f"discovering: {q}")
        for rec in client.search(q, max_pages=max_pages):
            scientific = f"{rec.get('gen', '')} {rec.get('sp', '')}".strip()
            sid = species_id_for(scientific)
            if not sid or sid in known:
                continue
            entry = counts.setdefault(
                sid,
                {
                    "id": sid,
                    "scientific": scientific,
                    "common": rec.get("en", "") or scientific,
                    "bank": "learned",
                    "summary": "Discovered on xeno-canto; nothing documented.",
                    "recordings": 0,
                    "syllables": [],
                    "songs": [],
                },
            )
            entry["recordings"] += 1
    ranked = sorted(counts.values(), key=lambda e: -e["recordings"])[: max(0, limit)]
    for e in ranked:
        log(f"  + {e['id']:28} {e['common'][:34]:34} {e['recordings']} recordings seen")
    return ranked


def species_queries(
    inventory: dict[str, Any],
    quality: str = "",
    extra: Sequence[dict[str, Any]] = (),
) -> list[tuple[str, str]]:
    """(speciesId, xeno-canto query) for every species the inventory already knows.

    Harvesting these and only these is what makes the result usable: the points land
    under species ids the app can already name, so the galaxy grows around the
    documented clusters instead of beside them.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for sp in [*inventory.get("species", []), *extra]:
        if sp.get("id") in seen:
            continue
        seen.add(sp.get("id", ""))
        scientific = sp.get("scientific", "").strip()
        if not scientific or " " not in scientific:
            continue
        genus, epithet = scientific.split(" ", 1)
        query = f'gen:"{genus}" sp:"{epithet.split()[0]}"'
        term = quality_term(quality)
        if term:
            query += f" {term}"
        out.append((sp["id"], query))
    return out


# --- the harvest loop -------------------------------------------------------------


#: Licence prefixes whose audio may be **kept on this machine** (owner decision,
#: 2026-08-01). The project is non-commercial and open source, so the NC and SA clauses
#: impose nothing it does not already satisfy, and retention is not redistribution — the
#: audio still never reaches the browser or an asset set. Two exclusions, and both are
#: refusals rather than oversights:
#:
#: - **NoDerivatives.** Retention alone is arguably fine, but everything this pipeline does
#:   next produces derived measurements, and ND is the one clause where that is not clearly
#:   covered. 9.7 % of the corpus, declined.
#: - **An unrecorded licence.** Absence of a licence is not permission.
#:
#: Measured over the production store when this shipped: 90.3 % of 10 184 recordings pass,
#: and all 10 184 carry a recordist, so attribution is available for every kept file.
CACHEABLE_LICENCES = ("by", "by-nc", "by-nc-sa", "by-sa", "zero", "publicdomain", "cc0")


def audio_may_be_cached(licence: str) -> bool:
    """Whether this recording's licence permits keeping the audio locally.

    Conservative by construction: an unknown or unparseable licence returns False, so a new
    source that reports something this has never seen withholds rather than assumes.
    """
    text = (licence or "").strip().lower().rstrip("/")
    if not text:
        return False
    if "publicdomain" in text or "/zero" in text or text.endswith("cc0"):
        return True
    if "/licenses/" not in text:
        return False
    code = text.split("/licenses/")[1].split("/")[0]
    if "nd" in code.split("-"):
        return False
    return code in CACHEABLE_LICENCES


@dataclass
class HarvestReport:
    recordings: int = 0
    skipped: int = 0
    failed: int = 0
    descriptors: int = 0
    retained: int = 0
    syllables: int = 0
    seconds: float = 0.0
    #: Audio files kept under `CACHEABLE_LICENCES`, and those withheld because the licence
    #: did not permit it — counted separately so a harvest says which it was.
    audio_cached: int = 0
    audio_withheld: int = 0


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

    # Segment first: the syllable spans decide which descriptor windows are worth keeping.
    observations = (
        extract_syllables(mono, rate, species_id, recording_id, max_seconds=max_seconds)
        if segment
        else []
    )
    spans = [(o.start, o.start + o.dur) for o in observations] or None

    rows: list[np.ndarray] = []
    for descriptor in slice_descriptors(mono, rate, max_seconds=max_seconds, voiced=spans):
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

    if observations:
        report.syllables += store.add_syllables(observations)
    del mono, rows, observations


def harvest_xeno_canto(
    store: HarvestStore,
    client: XenoCanto,
    targets: Iterable[tuple[str, str]],
    per_species: int = 20,
    max_seconds: float | None = DEFAULT_MAX_SECONDS,
    max_pages: int = 3,
    dry_run: bool = False,
    should_stop: Callable[[], bool] | None = None,
    max_length_seconds: float | None = DEFAULT_MAX_LENGTH_SECONDS,
    clean_only: bool = False,
    keep_audio: Path | None = None,
) -> HarvestReport:
    """`should_stop` is polled between recordings, so a run can be asked to end.

    `keep_audio` copies each analysed recording into that directory when its licence
    permits (`audio_may_be_cached`), before the temporary directory it was fetched into
    disappears. Without it the loop is unchanged: fetch, describe, delete. The reason to
    keep it is measured rather than convenient — an external model (Perch, BirdNET) and
    any per-syllable re-measurement need the waveform, and docs/23 §23.6.1 could only run
    on the 6 453 of 10 184 recordings whose audio still existed.

    Between, not during: one recording is one indivisible unit of work — it is fetched,
    analysed and deleted — and everything already ingested is kept, because a stopped
    harvest is a shorter harvest rather than a wasted one.
    """
    report = HarvestReport()

    # **Least-collected species first, so a pass works the backlog instead of the front.**
    #
    # The target list arrives in inventory order — the twelve documented birds, then whatever
    # discovery added — and a pass harvests a couple of recordings per species down that list.
    # With the store at its cap the documented birds already hold about 1970 descriptors each
    # and mostly return recordings `has()` already knows, so the budget went on re-searching
    # birds that could not gain anything while the newly discovered ones, holding zero, sat at
    # the far end of a queue every pass ran out of time before reaching. Fourteen species stayed
    # at "0 of ~100" indefinitely, which reads as discovery being broken when it is starvation.
    #
    # Ordering by what each species already has fixes it without a quota or a special case: a
    # bird with nothing is always served before a bird with two thousand, and once the new ones
    # have caught up the order flattens back out on its own.
    ordered = sorted(
        targets,
        key=lambda t: (
            len(store.strata[t[0]].rows) if t[0] in store.strata else 0,
            t[0],
        ),
    )
    if len(ordered) > 1:
        first = ", ".join(
            f"{sid}({len(store.strata[sid].rows) if sid in store.strata else 0})"
            for sid, _ in ordered[:4]
        )
        log(f"harvest order — least collected first: {first}, …")
    for species_id, query in ordered:
        if should_stop and should_stop():
            log("\nstopping: asked to")
            return report
        if species_id in store.restricted:
            log(f"\n{species_id}: skipped — xeno-canto withholds this species' audio "
                "(restricted_species); use --from-dir or an open dataset instead")
            continue
        log(f"\n{species_id}: {query}")
        taken = 0
        redacted = 0
        for rec in client.search(query, max_pages=max_pages):
            if taken >= per_species:
                break
            if should_stop and should_stop():
                log("  stopping: asked to")
                return report
            rid = f"XC{rec.get('id')}"
            if store.has(rid) or rid in store.dead:
                report.skipped += 1
                continue
            # What the API gives us and we were throwing away.
            #
            # xeno-canto returns 39 fields per recording; this kept nine. Four of the rest are
            # not trivia, they are the answers to questions this project already asks out loud:
            #
            # - **`type`** ("song", "alarm call", "flight call", "begging call") is a real,
            #   recordist-supplied call type for every recording. It was already stored, and it
            #   is still the cheapest available route to labelling a field cluster with what the
            #   call *does* rather than "unlabelled field cluster" — see the root README on how
            #   little meaning the four claim buckets can carry when 226 clusters have none.
            # - **`also`** lists the other species audible in the recording. The pipeline README
            #   says the dominant axis of the descriptor space is recording conditions rather
            #   than call identity; a recording with three other birds in it is precisely that
            #   contamination, arriving labelled, and it was being discarded unread.
            # - **`length`** is the duration as `m:ss`, known *before* the download. A pass
            #   currently pushes a few hundred megabytes through memory to keep a few hundred
            #   descriptors; the long soundscapes are most of that weight and can be declined.
            # - **`smp`** is the sample rate. The contract fixes analysis at 48 kHz, so a
            #   recording already at 48 kHz needs no resampling and one at 22 kHz has nothing
            #   above 11 kHz — which a wren trill very much does.
            #
            # `playback-used` is kept because it bears on the honesty rule: a call elicited by
            # playback is a response to a loudspeaker, not spontaneous behaviour.
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
                "also": [a for a in (rec.get("also") or []) if a],
                "length": rec.get("length", ""),
                "sampleRate": _int_or_none(rec.get("smp")),
                "sex": rec.get("sex", ""),
                "stage": rec.get("stage", ""),
                "playbackUsed": rec.get("playback-used", ""),
                "automatic": rec.get("auto", ""),
                "date": rec.get("date", ""),
            }
            seconds = _length_seconds(info["length"])
            if max_length_seconds and seconds and seconds > max_length_seconds:
                # Declined before the download rather than truncated after it: `max_seconds`
                # already caps how much of a recording is analysed, so fetching forty minutes
                # to read ninety seconds of it is pure transfer.
                report.skipped += 1
                log(f"  skip {rid}: {info['length']} is longer than the "
                    f"{max_length_seconds:.0f}s limit")
                continue
            if clean_only and info["also"]:
                report.skipped += 1
                log(f"  skip {rid}: {len(info['also'])} other species audible "
                    f"({', '.join(info['also'][:2])})")
                continue
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
                    text = str(exc)
                    # Permanent by nature: policy, or a file that is gone. Remembered so the
                    # next pass spends its budget on audio that exists.
                    if "restricted_species" in text or "404" in text:
                        store.mark_dead(rid, text)
                        if "restricted_species" in text:
                            redacted += 1
                    log(f"  skip {rid}: {exc}")
                    continue
                # Still inside the `with`: after it, the file is gone.
                if keep_audio is not None:
                    if audio_may_be_cached(info["licence"]):
                        keep_audio.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(audio_path, keep_audio / f"{rid}{audio_path.suffix}")
                        report.audio_cached += 1
                    else:
                        report.audio_withheld += 1
            # the TemporaryDirectory is gone here unless keep_audio took a copy
            store.note_recording(rid, info)
            taken += 1
            report.recordings += 1
            log(
                f"  {rid:10} q={info['quality']:1} {info['type'][:34]:34} "
                f"+{report.retained - before:4d} kept  store={len(store)}"
            )
        # Every candidate withheld and nothing ingested: this species has no audio here.
        if taken == 0 and redacted >= 5:
            store.mark_restricted(species_id)
            log(f"  {species_id}: all {redacted} candidates withheld — not querying it again")
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


def self_test(verbose: bool = True) -> None:
    """Check the two things about this store that fail *silently* when they break.

    Both are cheap to assert and expensive to discover: a store that quietly drops species,
    and a store that quietly writes back an empty syllable list. Neither raises on its own —
    the first shows up as a fitted repertoire missing birds the galaxy still displays, and the
    second as an erased corpus.
    """
    import tempfile

    def obs(species: str, recording: str, order: int) -> SyllableObservation:
        return SyllableObservation(
            species_id=species, recording_id=recording, order=order, start=0.0, dur=0.05,
            level=0.9, attack=0.006, hold=True, contour=[[0.0, 3000.0], [1.0, 3200.0]],
            am=0.0, am_depth=0.0, vib_rate=0.0, vib_depth=0.0, harmonic=0.2,
            timbre="pure", flatness=0.05, gap_before=0.0,
        )

    with tempfile.TemporaryDirectory() as tmp:
        # --- the cap must trim per species, not chronologically ---
        #
        # A harvest works through its species one at a time, so a chronological trim drops
        # whichever species came first. That is how a 25-species store became a 13-species one
        # without saying anything; see `add_syllables`.
        store = HarvestStore(Path(tmp) / "trim", syllable_cap=1000)
        plan = [("sp_a", 12, 200), ("sp_b", 6, 100), ("sp_c", 3, 60), ("sp_d", 2, 30),
                ("sp_e", 10, 150)]
        for species, n_recordings, per in plan:
            for r in range(n_recordings):
                store.add_syllables(
                    [obs(species, f"{species}-r{r}", i) for i in range(per)]
                )

        kept = {o.species_id for o in store.syllables}
        assert kept == {p[0] for p in plan}, f"the cap deleted whole species: {kept}"
        assert len(store.syllables) <= 1000, f"over cap: {len(store.syllables)}"

        # Whole recordings only: `learn_grammar` counts transitions between consecutive
        # syllables, so half a recording invents transitions that were never sung.
        sizes: dict[str, int] = {}
        for o in store.syllables:
            sizes[o.recording_id] = sizes.get(o.recording_id, 0) + 1
        expected = {f"{s}-r{r}": per for s, n, per in plan for r in range(n)}
        for rid, n in sizes.items():
            assert n == expected[rid], f"{rid} was split: kept {n} of {expected[rid]}"

        # --- a store opened without its syllables must refuse to save ---
        full = HarvestStore(Path(tmp) / "guard")
        full.add_syllables([obs("sp_a", "sp_a-r0", i) for i in range(5)])
        full.save()
        light = HarvestStore(Path(tmp) / "guard", load_syllables=False)
        assert light.syllable_count == 5, f"count not read from state.json: {light.syllable_count}"
        assert not light.syllables, "load_syllables=False still loaded the rows"
        try:
            light.save()
        except RuntimeError:
            pass
        else:  # pragma: no cover
            raise AssertionError("a lightweight store saved, which would erase the corpus")
        assert HarvestStore(Path(tmp) / "guard").syllable_count == 5, "the store was damaged"

        # --- the novelty flag must survive a store save/load ---
        #
        # Ingest flags an unheard syllable and saves; the next grow reads the flag back
        # to decide the point may not be force-assigned to an existing knot (docs/09
        # §9.2b). A flag that silently loaded as False would reintroduce exactly the
        # misassignment it exists to end.
        flagged_store = HarvestStore(Path(tmp) / "novel")
        heard = [obs("sp_a", "sp_a-r0", i) for i in range(3)]
        unheard = obs("sp_a", "sp_a-r0", 3)
        unheard.novel = True
        flagged_store.add_syllables([*heard, unheard])
        flagged_store.save()
        loaded = HarvestStore(Path(tmp) / "novel")
        assert [o.novel for o in loaded.syllables] == [False, False, False, True], (
            f"the novel flag did not survive save/load: {[o.novel for o in loaded.syllables]}"
        )

    # The licence gate decides whether audio may stay on this machine, so a wrong answer
    # is a licence violation rather than a bug. Both directions are pinned, and the two
    # refusals — NoDerivatives and an unrecorded licence — are pinned *as* refusals.
    cc = "https://creativecommons.org/licenses/"
    for url, want in (
        (f"{cc}by-nc/4.0/", True),
        (f"{cc}by-nc-sa/4.0/", True),
        (f"{cc}by-sa/4.0/", True),
        (f"{cc}by/4.0/", True),
        ("https://creativecommons.org/publicdomain/zero/1.0/", True),
        (f"{cc}by-nc-nd/4.0/", False),
        (f"{cc}by-nd/4.0/", False),
        ("", False),
        ("local file", False),
        ("http://example.com/unknown-terms", False),
    ):
        assert audio_may_be_cached(url) is want, f"licence gate wrong for {url!r}"

    # A species ask must parse from either spelling, and must NOT parse from a genus.
    # This is the guard on a 73-minute sweep that ran unfiltered because every id in a
    # generated species file came back empty — see `canonical_species_id`.
    for text, want_id in (
        ("Acanthis hornemanni", "acanthis_hornemanni"),
        ("acanthis_hornemanni", "acanthis_hornemanni"),
        ("ACANTHIS_HORNEMANNI", "acanthis_hornemanni"),
        ("Acanthis hornemanni exilipes", "acanthis_hornemanni"),
        ("acanthis_hornemanni_exilipes", "acanthis_hornemanni"),
        ("Acanthis", ""),
        ("", ""),
    ):
        got = canonical_species_id(text)
        assert got == want_id, f"canonical_species_id({text!r}) = {got!r}, want {want_id!r}"
    # ...and the strict parser stays strict, because it reads fetcher metadata where a
    # one-word scientific name is bad data rather than a shorthand.
    assert species_id_for("cuculus_canorus") == "", "species_id_for must not accept a bare id"
    assert species_id_for("Cuculus canorus") == "cuculus_canorus"

    if verbose:
        print(
            f"harvest self-test ok: cap trims per species ({len(plan)} survived), "
            f"recordings stay whole, a lightweight store refuses to save, "
            f"the novel flag survives save/load, the licence gate keeps NC/SA and "
            f"refuses ND and unrecorded"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
