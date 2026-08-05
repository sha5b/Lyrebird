"""If the band was the wrong lever on corpus quality, what does an SNR floor cost and buy?

`v10_outofband_census.py` measured what the in-band re-segmentation actually changes, and
the answer was not what the sweep assumed. Matched span by span on the same audio:

    found by both paths   median SNR 13.61 dB   15 % under 6 dB
    removed by the fix    median SNR  4.68 dB   66 % under 6 dB
    added by the fix      median SNR  2.64 dB   80 % under 6 dB

The two segmentations agree on the strong material and disagree almost entirely on
marginal rows near the noise floor, and the rows the fix *adds* are weaker than the ones
it removes. Paired with `v10_resegment_yield.py`'s projection — the corpus shrinks 22 % and
about 710 species fall below the fitting floor — the band fix is a change in which marginal
calls get made, not a purification.

So the lever that the measurement points at is **SNR**, which every stored row already
carries. This script prices it: for a range of floors, how many rows survive, how many
species stay above the fitting floor, and what the surviving corpus's SNR looks like.

No audio, no re-segmentation, no sampling — an exact census over all 378 224 rows, so the
answer is a table rather than an estimate. Nothing is written to the store: this prices a
decision, it does not take it.

Read it as a trade, not a recommendation. A floor buys median quality and costs species,
and the project's own resource claim is breadth (2 650 fitted species), so the right floor
is the owner's call and depends on which of the two the corpus is for.

Usage:
    .venv/bin/python analysis/v10_snr_floor.py
"""

from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "out/harvest-gan"
OUT = Path(__file__).resolve().parent / "v10_snr_floor.json"

#: `analysis/topup_underfloor.py`'s floor: syllables a species needs before `learn` fits it.
FIT_FLOOR = 24

FLOORS = (0.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    rows: list[tuple[str, float | None]] = []
    missing = 0
    for line in (STORE / "syllables.jsonl").open():
        r = json.loads(line)
        snr = r.get("snr")
        if snr is None:
            missing += 1
        rows.append((r.get("species_id") or "?", None if snr is None else float(snr)))
        if len(rows) % 100_000 == 0:
            log(f"  {len(rows)} rows ...")

    n = len(rows)
    have = [s for _, s in rows if s is not None]
    log(f"{n} rows, {missing} without an snr measurement")

    by_species_all: dict[str, int] = defaultdict(int)
    for sid, _ in rows:
        by_species_all[sid] += 1
    species_now = sum(1 for c in by_species_all.values() if c >= FIT_FLOOR)

    table = []
    for floor in FLOORS:
        kept: dict[str, int] = defaultdict(int)
        kept_snr = []
        for sid, snr in rows:
            # A row with no measurement is kept: dropping it would price a missing
            # field as if it were a bad recording, and 0 rows lack one here anyway.
            if snr is None or snr >= floor:
                kept[sid] += 1
                if snr is not None:
                    kept_snr.append(snr)
        fitted = sum(1 for c in kept.values() if c >= FIT_FLOOR)
        total = sum(kept.values())
        table.append({
            "floor_db": floor,
            "rows_kept": total,
            "rows_kept_share": total / n,
            "species_over_fit_floor": fitted,
            "species_lost_vs_now": species_now - fitted,
            "median_snr_kept": round(st.median(kept_snr), 2) if kept_snr else None,
        })
        log(f"  floor {floor:4.1f} dB -> {total} rows, {fitted} species")

    result = {
        "rows": n,
        "rows_without_snr": missing,
        "corpus_median_snr": round(st.median(have), 2) if have else None,
        "corpus_snr_p10": round(st.quantiles(have, n=10)[0], 2) if have else None,
        "corpus_snr_p90": round(st.quantiles(have, n=10)[8], 2) if have else None,
        "fit_floor": FIT_FLOOR,
        "species_over_fit_floor_now": species_now,
        # **This block was wrong in the first version of this script and the correction
        # matters.** It asserted that the band fix "buys no SNR, because it is not selecting
        # on SNR". That was an inference, never measured, and it is false. Segmenting the
        # same 60 cached recordings both ways and taking the SNR of every resulting row:
        # full-band median 6.36 dB against in-band 7.13 dB at 0.711 retention. The band fix
        # does raise median SNR. It raises it by 0.77 dB while removing 29 % of the rows.
        #
        # So the honest comparison is an exchange rate rather than a dominance: per row
        # sacrificed the floor buys about four times the median-SNR gain, and keeps 224 more
        # species. The band fix is a poor trade, not a worthless one.
        #
        # Unresolved, and flagged rather than smoothed over: docs/23 reports the in-band arm
        # at an SNR median of 15.9 dB against 12.7 dB over 120 recordings, a +3.2 dB gain
        # where the measurement above finds +0.77. Different sample, and possibly a different
        # statistic (per-recording medians averaged, rather than the median over rows). The
        # two need reconciling before either is quoted as the band fix's SNR yield.
        "band_fix_for_comparison": {
            "rows_kept_share": 0.777,
            "species_over_fit_floor": 1938,
            "median_snr_full_band": 6.36,
            "median_snr_in_band": 7.13,
            "snr_gain_db": 0.77,
            "measured_on": "60 cached iNat recordings, both segmentations, all rows",
            "docs23_reports_instead": {"from": 12.7, "to": 15.9, "n_recordings": 120},
            "source": "analysis/v10_resegment_yield.json + this file's docstring",
        },
        "table": table,
    }

    print("=" * 78)
    print("What an SNR floor costs and buys, over every row in the store")
    print("=" * 78)
    print(f"  rows {n},  median SNR {result['corpus_median_snr']} dB "
          f"(p10 {result['corpus_snr_p10']}, p90 {result['corpus_snr_p90']})")
    print(f"  species over the fitting floor of {FIT_FLOOR} now: {species_now}")
    print()
    print("  floor    rows kept    share   species >= floor   lost   median SNR kept")
    for t in table:
        print(f"  {t['floor_db']:4.1f} dB  {t['rows_kept']:10d}  {t['rows_kept_share']:6.3f}"
              f"   {t['species_over_fit_floor']:14d} {t['species_lost_vs_now']:6d}"
              f"   {t['median_snr_kept']:>8}")
    print()
    b = result["band_fix_for_comparison"]
    print(f"  for comparison, the band-fix sweep: share {b['rows_kept_share']}, "
          f"species {b['species_over_fit_floor']}, median SNR "
          f"{b['median_snr_full_band']} -> {b['median_snr_in_band']} dB "
          f"(+{b['snr_gain_db']})")
    print("  So it is an exchange rate, not a dominance: per row sacrificed the floor buys")
    print("  about four times the median-SNR gain, and keeps 224 more species. See the note")
    print("  in this file about the docs/23 figure, which reports +3.2 dB and needs")
    print("  reconciling with the +0.77 measured here.")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
