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
        # **This block has been wrong twice and both corrections are kept, because the
        # second one reverses the first's conclusion.**
        #
        # v1 asserted the band fix "buys no SNR, because it is not selecting on SNR" — an
        # inference, never measured, and false.
        #
        # v2 measured 60 cached recordings both ways, took the median over every resulting
        # row, and found +0.77 dB at 0.711 retention. It flagged docs/23's +3.2 dB as an
        # unresolved tension and argued the floor buys "about four times the gain per row
        # sacrificed".
        #
        # v3, `analysis/v10_snr_reconcile.py`: **that +0.77 was an unstable statistic, not a
        # smaller truth.** It reproduces exactly at n=60 seed 0 and becomes +2.57 on 120
        # recordings from the same cache. A median over rows lets one recording with hundreds
        # of near-floor syllables outvote fifty clean recordings. The per-recording statistic
        # — which is docs/23's, and which its "81 % of recordings improving" already implied —
        # is stable across both samples at +2.46 and +2.90, so docs/23's +3.2 dB replicates
        # and the figure quoted below is its gain rather than its absolute pair (that pair
        # sits ~3 dB above this cache's current draw).
        #
        # The same script also refutes the obvious objection. Both arms measure SNR in the
        # band they segment in (`learn.py` ~573-587), so every cross-arm figure here compares
        # two meters. Scored through one common band, the gain does not shrink — it grows,
        # full-band spans falling to 2.91 dB against the in-band arm's 8.95, because full-band
        # spans sit on rumble peaks and are nearly floor in the band that describes them.
        #
        # **So the exchange rate below is close, not four to one, and the two gains are not
        # the same kind of number.** The floor selects rows on the very field it reports, so
        # its median rises by construction and no span improves; the band fix changes which
        # spans exist and does not select on SNR. The floor still keeps 224 more species.
        "band_fix_for_comparison": {
            "rows_kept_share": 0.777,
            "species_over_fit_floor": 1938,
            "snr_gain_db_per_recording": 2.9,
            "snr_gain_db_range": [2.46, 2.9],
            "share_recordings_improving": 0.775,
            "statistic": "median of per-recording medians — the pooled-row median is "
                         "unstable at this sample size and is not quoted",
            "measured_on": "120 cached iNat recordings, both segmentations "
                           "(analysis/v10_snr_reconcile.py)",
            "docs23_agrees": {"gain_db": 3.2, "share_improving": 0.81, "n_recordings": 120},
            "retired": {"snr_gain_db": 0.77, "why": "pooled-row median, n=60 seed 0; the "
                        "same statistic gives +2.57 at n=120"},
            "not_the_same_kind_of_number": "the floor selects on the field it reports, so "
                                           "its gain is partly definitional; the band fix "
                                           "does not select on SNR",
            "source": "analysis/v10_resegment_yield.json + v10_snr_reconcile.json",
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
          f"species {b['species_over_fit_floor']}, SNR "
          f"+{b['snr_gain_db_per_recording']} dB per recording "
          f"({b['share_recordings_improving']:.0%} of recordings improving)")
    print("  The rates are close: the fix buys +2.9 dB at 0.71 retention, a 6 dB floor buys")
    print("  +3.3 dB at 0.77 retention and keeps 224 more species. They are also not the same")
    print("  kind of number — the floor selects rows on the field it then reports, so its")
    print("  median rises by construction and no span is improved. See v10_snr_reconcile.py;")
    print("  the +0.77 dB figure this script used to quote is retired as unstable.")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
