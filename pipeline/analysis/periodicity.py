"""Find metronomic runs in the corpus: the one thing in INAT227259 with no birdsong analogue.

**Why this and not another threshold.** Four candidate noise gates have been measured dead
on the owner's example (HANDOFF, 19:10): an absolute SNR floor, spectral flatness, Perch 2.0
presence, and — the root cause, now fixed — full-band segmentation. What is left in that
recording after the segmentation fix is a very regular ~1.5 kHz pulse train, 105 syllables
of it, almost certainly an insect. Every gate tried so far asks "is this syllable a bird",
one syllable at a time, and a single insect pulse is not distinguishable from a short call.
**Periodicity is the first candidate that asks about the sequence instead**, and the
sequence is where the difference lives: an insect stridulates at a fixed rate for the whole
recording, and its pulses are spectrally identical to each other.

**The honest difficulty, up front: birds do this too.** A woodpecker drum is metronomic. A
rattle, a trill, a Sedge Warbler's churr — all are steady runs of near-identical elements.
So this file measures the statistic and ranks the corpus by it; it does *not* assume a
threshold exists. Whether one does is the thing to look at, and the top-ranked recordings
have to be inspected before anything is gated on this.

**The statistic**, per recording, from stored fields only — no audio, so it runs over all
340 122 rows including the 11 007 whose audio was deleted by design:

  1. inter-onset intervals between consecutive syllables, in order;
  2. the longest run of consecutive intervals holding within `IOI_TOLERANCE` of the run's
     own median (a relative tolerance, because a 40 ms pulse rate and a 400 ms one are both
     "steady" at different scales);
  3. within that run, the mean cosine between successive 28-d descriptors — how alike the
     repeated elements actually are;
  4. what share of the recording's syllables the run accounts for.

A bird trill scores high on 2 and 3 over a *short* run; the shape being looked for is a long
run that covers most of the recording. That is why `runShare` is reported next to `runLength`
rather than instead of it.

    uv run python analysis/periodicity.py --store out/harvest-gan --out out/periodicity.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

#: How far an interval may sit from the run's median and still continue the run, as a
#: fraction of that median. 12 % is loose enough for a real insect (whose rate drifts with
#: temperature over a minute) and tight enough that a bird's phrase, which changes element
#: length as it goes, breaks the run.
IOI_TOLERANCE = 0.12

#: Intervals outside this range are not a pulse train worth calling periodic: below it the
#: "interval" is inside one syllable's own envelope, above it the gaps are phrase-scale and
#: any recording of a bird calling steadily would qualify.
IOI_MIN_S = 0.02
IOI_MAX_S = 1.0

#: Runs shorter than this are not evidence of anything — a three-note phrase is periodic by
#: accident. Reported anyway; this is only the floor for the summary counts.
MIN_RUN = 12


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def longest_steady_run(intervals: np.ndarray) -> tuple[int, int, float]:
    """`(start_index, length, median_interval)` of the longest steady run of intervals.

    Greedy and left-to-right rather than optimal: a run is extended while the next interval
    stays within `IOI_TOLERANCE` of the median of the run *so far*, which is what makes it
    tolerant of slow drift but not of a step change. An optimal segmentation would be
    O(n^2) for a statistic whose whole purpose is to rank recordings coarsely.
    """
    best = (0, 0, 0.0)
    i = 0
    n = intervals.size
    while i < n:
        if not (IOI_MIN_S <= intervals[i] <= IOI_MAX_S):
            i += 1
            continue
        j = i + 1
        while j < n:
            median = float(np.median(intervals[i:j]))
            if median <= 0 or abs(intervals[j] - median) > IOI_TOLERANCE * median:
                break
            if not (IOI_MIN_S <= intervals[j] <= IOI_MAX_S):
                break
            j += 1
        if j - i > best[1]:
            best = (i, j - i, float(np.median(intervals[i:j])))
        i = max(j, i + 1)
    return best


def measure(rows: list[dict]) -> dict | None:
    """One recording's periodicity, from its syllable rows in `order`."""
    rows = sorted(rows, key=lambda r: r["order"])
    if len(rows) < 4:
        return None
    starts = np.array([float(r["start"]) for r in rows])
    intervals = np.diff(starts)
    if intervals.size < 3:
        return None
    at, length, period = longest_steady_run(intervals)
    if length < 2:
        return {
            "recordingId": rows[0]["recording_id"],
            "speciesId": rows[0]["species_id"],
            "syllables": len(rows),
            "runLength": 0,
            "runShare": 0.0,
            "periodS": 0.0,
            "ioiCv": 0.0,
            "selfSimilarity": 0.0,
        }
    # The run of *intervals* [at, at+length) spans the syllables [at, at+length].
    members = rows[at : at + length + 1]
    run_intervals = intervals[at : at + length]
    cv = float(np.std(run_intervals) / max(np.mean(run_intervals), 1e-12))

    descriptors = [r.get("descriptor") for r in members]
    usable = [np.asarray(d, dtype=np.float64) for d in descriptors if d]
    if len(usable) >= 2:
        z = _unit(np.stack(usable))
        similarity = float(np.mean(np.sum(z[:-1] * z[1:], axis=1)))
    else:
        similarity = float("nan")

    # The recording's own SNR, because periodicity alone does not separate an insect from a
    # tapaculo and loudness does: measured, the metronomic *birds* at the top of this ranking
    # sit at 23-30 dB while INAT227259 sits at 9. See `SHORTLIST` below for why that pairing
    # is offered as a shortlist and not wired up as a gate.
    snrs = [float(r["snr"]) for r in rows if r.get("snr") is not None]
    return {
        "recordingId": rows[0]["recording_id"],
        "speciesId": rows[0]["species_id"],
        "syllables": len(rows),
        "runLength": int(length + 1),
        "runShare": round((length + 1) / len(rows), 4),
        "periodS": round(period, 4),
        "ioiCv": round(cv, 4),
        "selfSimilarity": round(similarity, 4) if similarity == similarity else None,
        "snrMedian": round(float(np.median(snrs)), 2) if snrs else None,
    }


#: A diagnostic cut, kept because of what it *failed* to do. **Do not gate on it.**
#:
#: Periodicity alone is measured dead. The fifteen most metronomic recordings in the corpus
#: are all real birds — four *Scytalopus* tapaculos, a snipe, a wryneck, two antpittas — and
#: `INAT227259` ranks 959th of 7 103 on its stored spans. On the band-limited spans it will
#: actually get, its steady run rises from 5 to 22 syllables, so the pulse train is real and
#: detectable; but `INAT167833`, a modelled *Scytalopus speluncae*, scores **75 of 75
#: syllables at CV 0.011** — more metronomic than the insect on every axis, and its
#: spectrogram is 75 identical notes at 5/s across the whole file. Any threshold that catches
#: the one deletes the other, and the other is in the inventory.
#:
#: Pairing periodicity with loudness looked like the escape: the metronomic birds sit at
#: 23-30 dB in-band while INAT227259 sits at 9. **Measured over the corpus, it is not.** These
#: constants select 43 recordings and they are again dominated by real birds that are simply
#: quiet and repetitive — *Chamaeza* antthrushes, a *Glaucidium* pygmy-owl, a sedge warbler, a
#: tawny frogmouth. INAT227259 is not even among them. So the conjunction is not a noise
#: detector; it is a "quiet repetitive bird" detector that happened to contain one insect.
#:
#: The generalisable lesson, which is the reason this file stays in the tree: **every gate
#: tried so far fails the same way.** Loudness, tonality, harmonicity, model presence and now
#: rhythm each name a property that some real bird has in the extreme. n=1 labelled noise is
#: not enough to separate anything, and the next attempt should start by getting more labels
#: rather than by proposing a sixth feature.
SHORTLIST = {"minRun": 12, "minShare": 0.2, "maxSnr": 15.0}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--store", default="out/harvest-gan")
    p.add_argument("--out", default="out/periodicity.jsonl")
    p.add_argument("--inventory", default="../data/learned-inventory.json",
                   help="used only to say how many flagged recordings belong to a species "
                        "that is actually modelled — the cost side of any gate")
    args = p.parse_args(argv)

    path = Path(args.store) / "syllables.jsonl"
    if not path.exists():
        print(f"{path} does not exist", file=sys.stderr)
        return 2

    by_recording: dict[str, list[dict]] = {}
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            by_recording.setdefault(d["recording_id"], []).append(
                {k: d.get(k) for k in
                 ("recording_id", "species_id", "order", "start", "dur", "descriptor",
                  "snr")}
            )
            n += 1
            if n % 100000 == 0:
                print(f"  read {n}", file=sys.stderr, flush=True)
    print(f"{n} rows, {len(by_recording)} recordings", file=sys.stderr)

    rows = [m for m in (measure(v) for v in by_recording.values()) if m]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    run = np.array([r["runLength"] for r in rows])
    share = np.array([r["runShare"] for r in rows])
    print(f"\n{len(rows)} recordings measured -> {out}")
    print("longest steady run (syllables):")
    for q in (50, 75, 90, 95, 99, 100):
        print(f"  p{q:<3d} {np.percentile(run, q):6.1f}")
    print("share of the recording that run covers:")
    for q in (50, 75, 90, 95, 99, 100):
        print(f"  p{q:<3d} {np.percentile(share, q):6.3f}")

    modelled: set[str] = set()
    inv = Path(args.inventory)
    if inv.exists():
        blob = json.loads(inv.read_text(encoding="utf-8"))
        items = blob.get("species") or blob.get("items") or []
        modelled = {
            s.get("id") or s.get("speciesId") for s in items if isinstance(s, dict)
        } - {None}

    print(f"\nwhat a gate would cost (run >= {MIN_RUN} and share >= 0.5):")
    for min_run in (MIN_RUN, 20, 30, 50):
        for min_share in (0.5, 0.7):
            hit = [r for r in rows if r["runLength"] >= min_run and r["runShare"] >= min_share]
            in_inv = sum(1 for r in hit if r["speciesId"] in modelled)
            syl = sum(r["syllables"] for r in hit)
            print(f"  run >= {min_run:3d}, share >= {min_share:.1f}: "
                  f"{len(hit):5d} recordings ({100*len(hit)/len(rows):4.1f} %), "
                  f"{syl:7d} syllables, {in_inv:5d} of them a modelled species")

    print("\ntop 15 by run length:")
    for r in sorted(rows, key=lambda r: (-r["runLength"], -r["runShare"]))[:15]:
        print(f"  {r['recordingId']:12s} {r['speciesId']:32s} run {r['runLength']:4d}/"
              f"{r['syllables']:4d} share {r['runShare']:.2f} period {r['periodS']:.3f}s "
              f"cv {r['ioiCv']:.3f} sim {r['selfSimilarity']}")

    # Periodic AND quiet. This looked like the pairing that separates the one labelled noise
    # recording from the metronomic birds above it, and over the corpus it does not — see
    # `SHORTLIST`. Printed so the negative result is reproducible rather than asserted.
    short = sorted(
        (r for r in rows
         if r["runLength"] >= SHORTLIST["minRun"]
         and r["runShare"] >= SHORTLIST["minShare"]
         and r["snrMedian"] is not None
         and r["snrMedian"] < SHORTLIST["maxSnr"]),
        key=lambda r: (r["snrMedian"], -r["runLength"]),
    )
    cached = Path("out/audio-cache")
    print(f"\nDIAGNOSTIC CUT — not a gate (run >= {SHORTLIST['minRun']}, "
          f"share >= {SHORTLIST['minShare']}, snr < {SHORTLIST['maxSnr']:.0f} dB): "
          f"{len(short)} of {len(rows)} recordings ({100 * len(short) / len(rows):.1f} %), "
          f"{sum(r['syllables'] for r in short)} syllables")
    for r in short[:25]:
        audio = "audio" if (cached / f"{r['recordingId']}.wav").exists() else "  -  "
        print(f"  {audio} {r['recordingId']:12s} {r['speciesId']:30s} "
              f"run {r['runLength']:3d}/{r['syllables']:4d} share {r['runShare']:.2f} "
              f"period {r['periodS']:.3f}s snr {r['snrMedian']:6.2f}")
    if len(short) > 25:
        print(f"  ... and {len(short) - 25} more in {out}")

    target = [r for r in rows if r["recordingId"] == "INAT227259"]
    if target:
        r = target[0]
        rank = sum(1 for x in rows if x["runLength"] > r["runLength"])
        print(f"\nINAT227259: run {r['runLength']}/{r['syllables']} share {r['runShare']:.2f} "
              f"period {r['periodS']:.3f}s cv {r['ioiCv']:.3f} sim {r['selfSimilarity']} "
              f"-> rank {rank + 1} of {len(rows)} "
              f"({100 * (1 - rank / len(rows)):.1f}th percentile)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
