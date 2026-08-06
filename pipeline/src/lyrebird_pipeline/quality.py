"""Re-measure ingest-time quality on the observations that were harvested without it.

**Why this exists.** `learn.extract_syllables` measures `snr` and `clipped` in the one
window where the audio exists, and both are keyword fields with a `None` default because
rows harvested before they existed carry no such key. `learn.quality_weight` treats that
`None` as neutral — *"Unmeasured is neutral, not bad"* — which was the right call for a
field nothing could fill in. It is measured on 41 % of `out/harvest-gan`, and the other
59 % is not a sampling accident: 188 986 of the 199 993 unmeasured rows are the iNat
sweep, whose audio the owner sanctioned caching (AGENTS.md), and **5 366 of its 5 368
recordings are still in `pipeline/out/audio-cache`**. The samples that measurement needs
are on this disk. Nothing had to be re-downloaded and nothing had to be guessed.

**Why it is exact rather than approximate.** This does not re-segment. It reproduces the
segmentation the store already holds — same `peak_normalise`, same `envelope`, same
`_segments`, same `_noise_floor` — and then measures the two quality fields on the
segment the stored row already names, matching by `(recording_id, order)` and
**verifying `start` and `dur` agree to a millisecond before it writes anything**. On the
first five recordings tried (358 syllables, one of them a 194-syllable dawn chorus) the
worst disagreement was 0.0000 s.

That verification is also this module's expiry date, and deliberately so. Change
anything in the segmentation path and every row stops matching, so a run against a store
harvested by different code writes **nothing** and reports every row as drifted, rather
than quietly attributing one recording's SNR to another recording's syllable. A gate that
fails closed is the only kind worth having here: `syllables.jsonl` is the most expensive
file in the repository and there is one copy of it (docs/09 §9.4).

**What it does not touch.** Row order is the only thing pairing `syllables.jsonl` with
`patches.f16`, `descriptors.f32`, `points.jsonl` and `typing.json`, so this rewrites the
JSONL **line for line, in place**: same count, same order, two keys changed on the rows
it could measure and no key changed on the rows it could not. It never calls
`HarvestStore.save`, which would rebuild all five files from memory to change two floats.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import harvest, learn

#: How far a re-derived segment may sit from the stored one and still be called the same
#: syllable. A millisecond is four samples at 44.1 kHz and two envelope hops is 5.8 ms, so
#: this is tight enough that a real segmentation change cannot slip through it and loose
#: enough to absorb the rounding `to_dict` applies (`round(start, 4)`).
MATCH_TOLERANCE_S = 1.0e-3

#: Recording ids this can reach at all. The store keeps no audio by design; the only audio
#: on disk is the iNat cache, and xeno-canto's was deleted after description and cannot be
#: brought back (`perch.py` makes the same point for the same reason).
CACHEABLE_PREFIX = "INAT"


@dataclass
class RemeasureReport:
    """Counts, and every one of them is a row that did or did not get measured."""

    rows: int = 0
    #: Rows that already carried an `snr`. Left alone: the ingest measurement is the
    #: primary one, and a re-measurement that silently replaced it would make the two
    #: indistinguishable.
    already_measured: int = 0
    #: Non-iNat rows. Their audio is gone by design, not by accident.
    no_audio_by_design: int = 0
    #: iNat rows whose wav is not in the cache (2 of 5 368 recordings).
    missing_wav: int = 0
    #: Measured and written.
    measured: int = 0
    #: The stored row names an `order` the re-derived segmentation does not have.
    absent_segment: int = 0
    #: The segment exists but sits somewhere else — the segmentation path has changed.
    drifted: int = 0
    #: Recordings that could not be decoded, by id.
    undecodable: dict[str, str] = field(default_factory=dict)
    recordings: int = 0

    @property
    def unreachable(self) -> int:
        return self.no_audio_by_design + self.missing_wav

    def format(self, store_root: Path) -> str:
        lines = [
            f"{store_root}: {self.rows} syllable observations",
            f"  already measured   {self.already_measured:>7}   left untouched",
            f"  measured now       {self.measured:>7}   snr + clipped written",
            f"  no audio by design {self.no_audio_by_design:>7}   non-iNat source",
            f"  wav not cached     {self.missing_wav:>7}",
        ]
        if self.drifted or self.absent_segment:
            lines.append(
                f"  DRIFTED            {self.drifted:>7}   segment moved past "
                f"{MATCH_TOLERANCE_S * 1000:.0f} ms — nothing written for these"
            )
            lines.append(f"  absent segment     {self.absent_segment:>7}")
        if self.undecodable:
            lines.append(f"  undecodable        {len(self.undecodable):>7} recordings")
        lines.append(f"  read {self.recordings} recordings from the cache")
        return "\n".join(lines)


def measure_recording(
    audio: np.ndarray,
    sample_rate: int,
    max_seconds: float | None = harvest.DEFAULT_MAX_SECONDS,
) -> dict[int, tuple[float, float, float, bool]]:
    """`{order: (start, dur, snr, clipped)}` for one recording, no re-description.

    The segmentation half of `learn.extract_syllables`, and nothing else: no f0 track, no
    harmonic profile, no mel patch, no 28-d descriptor. Those are what make ingest cost
    hundreds of milliseconds a recording, and none of them feed `snr` or `clipped`. The
    parts that do are copied here by *calling the same functions* rather than by being
    reimplemented — `peak_normalise`, `envelope`, `_segments`, `_noise_floor` — so the two
    paths cannot drift apart without this module's tolerance check noticing.

    `order` is the index into the segment list, which is what `extract_syllables` writes
    and is therefore stable even though that function skips segments it cannot track a
    pitch through (`f0.size < 2`). A skipped segment simply has no stored row.
    """
    if max_seconds is not None:
        audio = audio[: int(max_seconds * sample_rate)]
    if audio.size < learn.F0_FRAME:
        return {}
    unscaled = audio
    mono = learn.peak_normalise(audio)
    env = learn.envelope(mono)
    if not env.size:
        return {}
    segments = learn._segments(env, sample_rate)
    noise_floor = learn._noise_floor(env, segments)

    out: dict[int, tuple[float, float, float, bool]] = {}
    for order, (s0, s1) in enumerate(segments):
        if order >= learn.MAX_PER_RECORDING:
            break
        seg = mono[s0:s1]
        if not seg.size:
            continue
        seg_rms = float(np.sqrt(np.mean(seg * seg)))
        snr = 20.0 * math.log10(max(seg_rms, 1.0e-9) / max(noise_floor, 1.0e-9))
        raw = unscaled[s0:s1]
        clipped = bool(
            np.mean(np.abs(raw) >= learn.CLIP_FULL_SCALE) > learn.CLIP_SHARE_MIN
        )
        out[order] = (s0 / sample_rate, seg.size / sample_rate, snr, clipped)
    return out


def self_test(verbose: bool = True) -> None:
    """`measure_recording` must be `extract_syllables(segment_band=None)`, exactly.

    This is the one property the whole pass rests on and the one the tolerance check cannot
    see: `MATCH_TOLERANCE_S` compares *timing*, so a re-measurement that segmented
    identically but computed `snr` by a different formula would match every row and write
    188 986 wrong numbers into the corpus. `learn.self_test` §12d guards the same seam from
    the other side.
    """
    rate = 44100
    t = np.arange(int(2.5 * rate)) / rate
    rng = np.random.default_rng(7)
    # Rumble and hiss modulated together, with four chirps over them: the shape that made
    # `learn.SEGMENT_BAND_HZ` necessary. Both paths describe four syllables here and they are
    # not the same four — the legacy path lands on the rumble's amplitude peaks (0.000, 0.508,
    # 1.138, 1.759 s) and the band-limited one lands on the chirps (0.305, 0.903, 1.504,
    # 2.104 s). A fixture where only one path finds anything would not test the seam.
    modulation = 1.0 + 0.8 * np.sin(2 * np.pi * 1.6 * t)
    audio = 0.35 * np.sin(2 * np.pi * 70.0 * t) * modulation
    audio += 0.02 * rng.normal(0.0, 1.0, t.size) * modulation
    for onset in (0.3, 0.9, 1.5, 2.1):
        span = (t >= onset) & (t < onset + 0.08)
        audio[span] += 0.5 * np.sin(2 * np.pi * 4100.0 * t[span]) * np.hanning(
            int(span.sum())
        )

    full = learn.extract_syllables(audio, rate, "test", "r0", max_seconds=None,
                                   segment_band=None)
    cheap = measure_recording(audio, rate, max_seconds=None)
    assert full, "the fixture described nothing on the legacy path"
    for o in full:
        got = cheap.get(o.order)
        assert got is not None, f"order {o.order} is missing from measure_recording"
        start, dur, snr, clipped = got
        assert abs(start - o.start) <= MATCH_TOLERANCE_S, f"start {start} vs {o.start}"
        assert abs(dur - o.dur) <= MATCH_TOLERANCE_S, f"dur {dur} vs {o.dur}"
        assert o.snr is not None, "extract_syllables stopped measuring snr"
        assert abs(round(snr, 2) - float(o.snr)) < 0.005, f"snr {snr:.4f} vs {o.snr}"
        assert clipped == o.clipped, f"clipped {clipped} vs {o.clipped}"

    # ...and it must NOT match the band-limited path, or the tolerance check has nothing to
    # protect and a store harvested after `SEGMENT_BAND_HZ` would be silently overwritten.
    banded = learn.extract_syllables(audio, rate, "test", "r0", max_seconds=None)
    drifted = sum(
        1
        for o in banded
        if o.order not in cheap
        or abs(cheap[o.order][0] - o.start) > MATCH_TOLERANCE_S
    )
    assert drifted, (
        "the band-limited path is indistinguishable from the legacy one on this fixture, "
        "so `remeasure_store` could write legacy numbers onto band-limited rows"
    )
    if verbose:
        print(
            f"quality self-test ok: {len(full)} rows reproduce "
            f"extract_syllables(segment_band=None) exactly; {drifted} of {len(banded)} "
            f"band-limited rows correctly read as drifted"
        )


def _scan_targets(syllables_path: Path) -> tuple[int, dict[str, list[dict]], RemeasureReport]:
    """First pass: which rows want measuring, grouped by recording.

    Streamed rather than loaded through `HarvestStore`, which would also pull
    `patches.f16` — 500 MB of float16 that this pass has no use for.
    """
    report = RemeasureReport()
    targets: dict[str, list[dict]] = {}
    with syllables_path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            report.rows += 1
            d = json.loads(line)
            if d.get("snr") is not None:
                report.already_measured += 1
                continue
            rid = d.get("recording_id", "")
            if not rid.startswith(CACHEABLE_PREFIX):
                report.no_audio_by_design += 1
                continue
            targets.setdefault(rid, []).append(
                {"order": d.get("order"), "start": d.get("start"), "dur": d.get("dur")}
            )
    return report.rows, targets, report


def remeasure_store(
    store_root: Path,
    audio_cache: Path,
    max_seconds: float | None = harvest.DEFAULT_MAX_SECONDS,
    dry_run: bool = False,
    log: Callable[[str], None] = print,
) -> RemeasureReport:
    """Fill `snr`/`clipped` on every row whose recording is still in `audio_cache`.

    Two passes over `syllables.jsonl` and one decode per recording. The write is a
    temporary file in the store directory followed by `os.replace`, so an interrupted run
    leaves the original intact — the alternative is a half-rewritten copy of the corpus.
    """
    store_root = Path(store_root)
    audio_cache = Path(audio_cache)
    syllables_path = store_root / "syllables.jsonl"
    if not syllables_path.exists():
        raise FileNotFoundError(f"{syllables_path} does not exist")

    _, targets, report = _scan_targets(syllables_path)
    log(
        f"{report.rows} rows: {report.already_measured} already measured, "
        f"{report.no_audio_by_design} unreachable by design, "
        f"{sum(len(v) for v in targets.values())} to try across {len(targets)} recordings"
    )

    #: `(recording_id, order) -> (snr, clipped)`, only for rows that matched.
    measured: dict[tuple[str, int], tuple[float, bool]] = {}
    for n, (rid, rows) in enumerate(sorted(targets.items()), start=1):
        wav = audio_cache / f"{rid}.wav"
        if not wav.exists():
            report.missing_wav += len(rows)
            continue
        try:
            audio, rate = harvest.decode(wav)
        except Exception as exc:  # a truncated cache entry is not a reason to stop
            report.undecodable[rid] = str(exc)
            report.missing_wav += len(rows)
            continue
        report.recordings += 1
        fresh = measure_recording(audio, rate, max_seconds=max_seconds)
        for row in rows:
            got = fresh.get(row["order"])
            if got is None:
                report.absent_segment += 1
                continue
            start, dur, snr, clipped = got
            if (
                abs(start - float(row["start"])) > MATCH_TOLERANCE_S
                or abs(dur - float(row["dur"])) > MATCH_TOLERANCE_S
            ):
                report.drifted += 1
                continue
            measured[(rid, int(row["order"]))] = (round(snr, 2), clipped)
            report.measured += 1
        del audio
        if n % 500 == 0:
            log(f"  {n}/{len(targets)} recordings, {report.measured} measured")

    if report.drifted:
        log(
            f"WARNING: {report.drifted} rows name a segment that has moved more than "
            f"{MATCH_TOLERANCE_S * 1000:.0f} ms. The segmentation path is not the one "
            f"that harvested this store, so those rows were left alone."
        )
    if dry_run:
        log("dry run: nothing written")
        return report

    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=store_root, prefix=".syllables-", suffix=".jsonl",
        delete=False,
    )
    try:
        with tmp, syllables_path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                d = json.loads(line)
                key = (d.get("recording_id", ""), d.get("order"))
                if d.get("snr") is None and key in measured:
                    d["snr"], d["clipped"] = measured[key]
                tmp.write(json.dumps(d, sort_keys=True) + "\n")
        os.replace(tmp.name, syllables_path)
    except BaseException:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    return report
