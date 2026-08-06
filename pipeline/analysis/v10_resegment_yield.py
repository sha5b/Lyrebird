"""Pre-flight for the v10 sweep: what does in-band re-segmentation do to corpus size?

The sweep re-segments every recording with `learn.SEGMENT_BAND_HZ` (400-12 000 Hz) instead
of full-band. `quality.self_test` already proves the two paths find *different* syllables at
different times, so the yield can move in either direction, and two decisions depend on
which way and by how much:

- **The caps.** `harvest-gan` holds 378 224 syllable observations against a `syllableCap` of
  400 000, i.e. 5.8 % of headroom. If in-band segmentation yields materially more per
  recording, the sweep hits the cap and `add_syllables` starts trimming per species
  mid-run — silently changing the corpus while it is being built.
- **The under-floor species.** 988 species already sit below the fitting floor. If the yield
  falls, that number rises, and the sweep costs repertoire breadth.

Measured on the iNaturalist cache, because that is the audio already on disk. Both arms run
on the same files in the same process, so the only difference is `segment_band`.

This measures *yield*, not quality. It says how big the new corpus will be, not whether its
rows are better — the band fix's justification is docs/23's noise work, not this script.

Usage:
    .venv/bin/python analysis/v10_resegment_yield.py [--n 80] [--seed 0]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
from pathlib import Path

from lyrebird_pipeline import learn
from lyrebird_pipeline.harvest import decode

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "out/audio-cache"
OLD_STORE = ROOT / "out/harvest-gan"
OUT = Path(__file__).resolve().parent / "v10_resegment_yield.json"

#: `harvest.DEFAULT_MAX_SECONDS`, so the measurement analyses exactly as much of each
#: recording as the sweep will. An earlier run used 60 s; both arms were affected equally,
#: but the ratio is what is being projected, so it is read at the real value.
MAX_SECONDS = 90.0

#: The fitting floor, as `analysis/topup_underfloor.py` defines it: a species needs this
#: many syllables before `learn` will fit it.
FIT_FLOOR = 24

#: Monte Carlo draws for the species-level projection below.
DRAWS = 200


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=80, help="recordings to sample")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    state = json.loads((OLD_STORE / "state.json").read_text())
    species_of = {k: v.get("speciesId", "?") for k, v in state["recordings"].items()}

    files = sorted(CACHE.glob("INAT*.wav"))
    rng = random.Random(args.seed)
    sample = rng.sample(files, min(args.n, len(files)))
    log(f"{len(files)} cached iNat recordings; sampling {len(sample)} at seed {args.seed}")

    rows = []
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
        band = learn.extract_syllables(
            mono, rate, sid, rid, max_seconds=MAX_SECONDS
        )
        rows.append({
            "recording": rid,
            "seconds": round(mono.size / rate, 1),
            "full_band": len(full),
            "in_band": len(band),
            "full_dur_s": round(sum(o.dur for o in full), 3),
            "in_dur_s": round(sum(o.dur for o in band), 3),
        })
        if i % 10 == 0:
            log(f"  {i}/{len(sample)} ...")

    if not rows:
        log("nothing decoded")
        return 1

    tf = sum(r["full_band"] for r in rows)
    tb = sum(r["in_band"] for r in rows)
    ratio = tb / tf if tf else float("nan")
    per = [r["in_band"] / r["full_band"] for r in rows if r["full_band"]]
    grew = sum(1 for r in rows if r["in_band"] > r["full_band"])
    shrank = sum(1 for r in rows if r["in_band"] < r["full_band"])
    zero = sum(1 for r in rows if r["in_band"] == 0)

    projected = int(round(state["syllableObservations"] * ratio))
    cap = state.get("syllableCap")

    # --- the species-level consequence, by Monte Carlo rather than a point estimate.
    #
    # A single ratio would hide the shape that matters: 16 % of sampled recordings yield
    # *nothing* in band, so a species carried by two recordings can lose everything while
    # the corpus-wide ratio still reads 0.72. So each recording draws its own ratio from
    # the measured empirical distribution and the species is re-totalled.
    per_rec_now: dict[str, int] = {}
    rec_species: dict[str, str] = {}
    for line in (OLD_STORE / "syllables.jsonl").open():
        row = json.loads(line)
        rid = row.get("recording_id") or "?"
        per_rec_now[rid] = per_rec_now.get(rid, 0) + 1
        rec_species[rid] = row.get("species_id") or "?"

    by_species: dict[str, list[int]] = {}
    for rid, n in per_rec_now.items():
        by_species.setdefault(rec_species[rid], []).append(n)

    empirical = [r["in_band"] / r["full_band"] for r in rows if r["full_band"]]
    empirical += [0.0] * sum(1 for r in rows if r["full_band"] == 0)
    rng2 = random.Random(args.seed + 1)

    fitted_now = sum(1 for c in by_species.values() if sum(c) >= FIT_FLOOR)
    fitted_draws = []
    lost_draws = []
    for _ in range(DRAWS):
        fitted = 0
        for counts in by_species.values():
            total = sum(int(round(n * rng2.choice(empirical))) for n in counts)
            if total >= FIT_FLOOR:
                fitted += 1
        fitted_draws.append(fitted)
        lost_draws.append(fitted_now - fitted)
    fitted_draws.sort()
    lo, mid, hi = (fitted_draws[int(DRAWS * q)] for q in (0.05, 0.5, 0.94))

    result = {
        "recordings_measured": len(rows),
        "max_seconds": MAX_SECONDS,
        "full_band_syllables": tf,
        "in_band_syllables": tb,
        "corpus_ratio": ratio,
        "per_recording_ratio_median": st.median(per) if per else None,
        "recordings_yield_up": grew,
        "recordings_yield_down": shrank,
        "recordings_in_band_empty": zero,
        "full_band_seconds_kept": round(sum(r["full_dur_s"] for r in rows), 1),
        "in_band_seconds_kept": round(sum(r["in_dur_s"] for r in rows), 1),
        "store_syllables_now": state["syllableObservations"],
        "store_syllable_cap": cap,
        "projected_store_syllables": projected,
        "projected_exceeds_cap": bool(cap and projected > cap),
        "fit_floor": FIT_FLOOR,
        "species_in_store": len(by_species),
        "species_over_floor_now": fitted_now,
        "species_over_floor_projected_median": mid,
        "species_over_floor_projected_p05": lo,
        "species_over_floor_projected_p94": hi,
        "species_lost_median": fitted_now - mid,
        "monte_carlo_draws": DRAWS,
        "rows": rows,
    }

    print("=" * 74)
    print("In-band re-segmentation yield, against the same files full-band")
    print("=" * 74)
    print(f"  recordings measured          {len(rows):6d}")
    print(f"  syllables full-band          {tf:6d}")
    print(f"  syllables in-band            {tb:6d}")
    print(f"  corpus ratio                 {ratio:6.3f}   (in-band / full-band)")
    print(f"  per-recording ratio, median  {result['per_recording_ratio_median']}")
    print(f"  yield up / down / empty      {grew} / {shrank} / {zero}")
    print()
    print(f"  store now                    {state['syllableObservations']:6d} syllables")
    print(f"  projected after the sweep    {projected:6d}")
    print(f"  syllableCap                  {cap}")
    print(f"  would exceed the cap:        {result['projected_exceeds_cap']}")
    print()
    print(f"  species over the floor of {FIT_FLOOR} now      {fitted_now:5d}")
    print(f"  projected after the sweep (median)  {mid:5d}   [p05 {lo}, p94 {hi}]")
    print(f"  species that would drop below it    {fitted_now - mid:5d}")
    print("  (Monte Carlo: each recording draws its own measured ratio, so the "
          "16 %-yield-nothing tail is carried rather than averaged away)")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
