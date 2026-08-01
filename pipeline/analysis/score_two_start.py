"""Score the two-start descent against its pre-registered gate.

The gate is in `inverse_gate.md` and was written before the run:

  1. median resynthesis cosine >= baseline + 0.02
  2. **no species worse than baseline at all** — not -0.05. With the baseline start always
     one of the two candidates, any regression is a bug in the selection, not a trade.

Reads the per-type `FIT` lines the fit already logs, so it scores exactly the syllables
that shipped rather than a re-derivation. Types are matched on (species, type id) and only
types present in both arms are compared — the type inventory is fitted per arm and a type
that exists in one and not the other is not a comparison.

Usage: score_two_start.py BASELINE.log CANDIDATE.log [--label NAME]
"""

from __future__ import annotations

import argparse
import re
import statistics as st
import sys
from pathlib import Path

FIT = re.compile(
    r"^FIT (?P<species>\S+) (?P<type>\S+) .*?\bcos=(?P<cos>-?[\d.]+)", re.MULTILINE
)

#: Pre-registered in inverse_gate.md, before the run.
GATE_MEDIAN_GAIN = 0.02
GATE_WORST_SPECIES = 0.0


def load(path: Path) -> dict[tuple[str, str], float]:
    """(species, type) -> resynthesis cosine, from the fit's own log."""
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[tuple[str, str], float] = {}
    for m in FIT.finditer(text):
        out[(m["species"], m["type"])] = float(m["cos"])
    if not out:
        raise SystemExit(f"{path}: no FIT lines — is this a learn log?")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("baseline", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--label", default="candidate")
    args = ap.parse_args()

    base = load(args.baseline)
    cand = load(args.candidate)
    shared = sorted(set(base) & set(cand))
    if not shared:
        raise SystemExit("no types in common — the arms do not share an inventory")

    b = [base[k] for k in shared]
    c = [cand[k] for k in shared]
    med_b, med_c = st.median(b), st.median(c)
    gain = med_c - med_b
    improved = sum(1 for k in shared if cand[k] > base[k])
    worse = sum(1 for k in shared if cand[k] < base[k])

    print(f"types compared         {len(shared)} "
          f"(baseline held {len(base)}, {args.label} {len(cand)})")
    print(f"median cosine          {med_b:.4f} -> {med_c:.4f}  ({gain:+.4f})")
    print(f"types improved         {improved}/{len(shared)} = "
          f"{100 * improved / len(shared):.1f} %")
    print(f"types worse            {worse}/{len(shared)} = "
          f"{100 * worse / len(shared):.1f} %")

    # Per species, on the species' own median — the shape the gate is written in.
    per: dict[str, list[tuple[float, float]]] = {}
    for sp, ty in shared:
        per.setdefault(sp, []).append((base[(sp, ty)], cand[(sp, ty)]))
    deltas = {
        sp: st.median([x[1] for x in rows]) - st.median([x[0] for x in rows])
        for sp, rows in per.items()
    }
    ranked = sorted(deltas.items(), key=lambda kv: kv[1])
    worst_sp, worst_delta = ranked[0]
    down = [(s, d) for s, d in ranked if d < 0]
    print(f"species                {len(deltas)}; "
          f"{sum(1 for d in deltas.values() if d > 0)} up, {len(down)} down, "
          f"{sum(1 for d in deltas.values() if d == 0)} unmoved")
    print(f"worst species          {worst_sp} {worst_delta:+.4f}")
    if down:
        print("  species down:")
        for s, d in down[:12]:
            print(f"    {s:34} {d:+.4f}")
        if len(down) > 12:
            print(f"    ... and {len(down) - 12} more")

    g1 = gain >= GATE_MEDIAN_GAIN
    g2 = worst_delta >= GATE_WORST_SPECIES
    print()
    print(f"GATE 1  median gain >= {GATE_MEDIAN_GAIN:+.2f}      "
          f"{gain:+.4f}  {'PASS' if g1 else 'FAIL'}")
    print(f"GATE 2  no species worse at all      "
          f"worst {worst_delta:+.4f}  {'PASS' if g2 else 'FAIL'}")
    print()
    print("VERDICT:", "PASS — adopt" if (g1 and g2) else "FAIL — do not adopt")
    return 0 if (g1 and g2) else 1


if __name__ == "__main__":
    sys.exit(main())
