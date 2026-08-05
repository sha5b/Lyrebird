"""What does the band fix actually remove? Compare the two segmentations row by row.

`v10_resegment_yield.py` projects that in-band re-segmentation costs about 710 fitted
species. Before paying 710 species for a bug fix, the question is what those rows *are*.

**The first version of this script was invalid and the record is kept here on purpose.**
It classified every stored row by whether its measured pitch contour fell inside
`SEGMENT_BAND_HZ` and reported **100.0 % inside, 0 below, 0 above** over all 378 224 rows.
That is tautological: `extract_syllables` tracks f0 only within `[F0_MIN_HZ, F0_MAX_HZ]`,
so a stored contour cannot lie outside the band by construction. `segment_band` changes
where syllable *boundaries* are detected — the full-band path locks onto the broadband
envelope, so it lands on rumble amplitude peaks and then reports a perfectly in-band f0
for a span that was never a syllable. No field on a stored row can reveal that. The
instrument constrained the answer, and the number looked like a clean result.

**The valid form compares the two segmentations against each other on the same audio.**
For each sampled recording both paths run, their syllables are matched by time overlap,
and every row lands in one of three buckets:

    agreed      found by both paths            — the corpus the fix keeps
    full_only   found only full-band           — what the fix REMOVES
    band_only   found only in-band             — what the fix ADDS

Then the quality fields the segmenter already measures are compared across buckets.

**PRE-REGISTERED, before the run.** If the fix is removing noise, `full_only` rows are
less harmonic, flatter, noisier and lower-SNR than `agreed` rows. The stated prediction is
that `full_only` has a lower median `harmonic` and a higher median `flatness` than
`agreed`. If instead `full_only` looks like `agreed` on these fields, the fix is discarding
ordinary syllables and the 710-species cost is a real loss of repertoire, not a correction.
Either outcome is reportable and neither moves the bar afterwards.

Usage:
    .venv/bin/python analysis/v10_outofband_census.py [--n 120] [--seed 0]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
from pathlib import Path

from birdy_pipeline import learn
from birdy_pipeline.harvest import decode

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "out/audio-cache"
STORE = ROOT / "out/harvest-gan"
OUT = Path(__file__).resolve().parent / "v10_outofband_census.json"

MAX_SECONDS = 90.0
#: Two spans are the same syllable when they overlap by more than this share of the
#: shorter one. Generous on purpose: the question is which rows exist, not whether the
#: boundaries moved slightly.
OVERLAP_SHARE = 0.5

FIELDS = ("harmonic", "flatness", "noise_frac", "snr", "level", "dur", "am_depth")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def overlap(a, b) -> float:
    """Share of the shorter span that the two spans share."""
    lo = max(a.start, b.start)
    hi = min(a.start + a.dur, b.start + b.dur)
    if hi <= lo:
        return 0.0
    return (hi - lo) / max(min(a.dur, b.dur), 1e-9)


def match(full: list, band: list) -> tuple[list, list, list]:
    """Greedy one-to-one match by best overlap. Returns (agreed_full, full_only, band_only)."""
    used = set()
    agreed, full_only = [], []
    for o in full:
        best, best_share = None, 0.0
        for j, c in enumerate(band):
            if j in used:
                continue
            share = overlap(o, c)
            if share > best_share:
                best, best_share = j, share
        if best is not None and best_share >= OVERLAP_SHARE:
            used.add(best)
            agreed.append(o)
        else:
            full_only.append(o)
    band_only = [c for j, c in enumerate(band) if j not in used]
    return agreed, full_only, band_only


def summarise(rows: list) -> dict:
    out: dict = {"n": len(rows)}
    for f in FIELDS:
        vals = [
            float(getattr(r, f))
            for r in rows
            if getattr(r, f, None) is not None
        ]
        out[f] = round(st.median(vals), 4) if vals else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    state = json.loads((STORE / "state.json").read_text())
    species_of = {k: v.get("speciesId", "?") for k, v in state["recordings"].items()}

    files = sorted(CACHE.glob("INAT*.wav"))
    sample = random.Random(args.seed).sample(files, min(args.n, len(files)))
    log(f"comparing both segmentations on {len(sample)} recordings")

    buckets: dict[str, list] = {"agreed": [], "full_only": [], "band_only": []}
    per_rec = []
    for i, path in enumerate(sample, 1):
        rid = path.stem
        sid = species_of.get(rid, "unlabelled")
        try:
            mono, rate = decode(path)
        except Exception as exc:  # noqa: BLE001
            log(f"  skip {rid}: {exc}")
            continue
        full = learn.extract_syllables(
            mono, rate, sid, rid, max_seconds=MAX_SECONDS, segment_band=None
        )
        band = learn.extract_syllables(mono, rate, sid, rid, max_seconds=MAX_SECONDS)
        agreed, full_only, band_only = match(full, band)
        buckets["agreed"] += agreed
        buckets["full_only"] += full_only
        buckets["band_only"] += band_only
        per_rec.append({
            "recording": rid, "full": len(full), "band": len(band),
            "agreed": len(agreed), "full_only": len(full_only),
            "band_only": len(band_only),
        })
        if i % 20 == 0:
            log(f"  {i}/{len(sample)} ...")

    stats = {k: summarise(v) for k, v in buckets.items()}
    a, f = stats["agreed"], stats["full_only"]
    held = (
        a["harmonic"] is not None and f["harmonic"] is not None
        and f["harmonic"] < a["harmonic"] and f["flatness"] > a["flatness"]
    )

    result = {
        "recordings": len(per_rec),
        "overlap_share": OVERLAP_SHARE,
        "max_seconds": MAX_SECONDS,
        "buckets": stats,
        "totals": {k: len(v) for k, v in buckets.items()},
        "prediction": "full_only has lower median harmonic and higher median flatness "
                      "than agreed",
        "prediction_held": bool(held),
        "per_recording": per_rec,
    }

    print("=" * 78)
    print("What the band fix removes and adds, matched span by span on the same audio")
    print("=" * 78)
    print(f"  recordings compared   {len(per_rec)}")
    print(f"  agreed / full_only / band_only   "
          f"{len(buckets['agreed'])} / {len(buckets['full_only'])} / "
          f"{len(buckets['band_only'])}")
    print()
    hdr = "  bucket        " + "".join(f"{f:>12s}" for f in FIELDS)
    print(hdr)
    for k in ("agreed", "full_only", "band_only"):
        row = stats[k]
        print(f"  {k:12s}  " + "".join(
            f"{(row[f] if row[f] is not None else float('nan')):>12.4f}" for f in FIELDS
        ) + f"   n={row['n']}")
    print()
    print(f"  PRE-REGISTERED: {result['prediction']}")
    print(f"  held: {result['prediction_held']}")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
