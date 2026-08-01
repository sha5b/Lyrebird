"""Score the amortised inverse against its pre-registered gate (`inverse_gate.md`).

Reads two learned inventories produced by identical `learn` runs that differ only in
`--inverse`, and applies the three conditions written before either was run:

  1. median resynthesis cosine over fitted types rises by >= 0.02
  2. at least 60 % of types improve
  3. no species' median falls by more than 0.05

Usage: python inverse_compare.py <baseline.json> <encoder.json>
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def types_of(path: Path) -> dict[tuple[str, str], float]:
    """(species, syllable) -> resynthesis cosine, for every fitted type that has one."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], float] = {}
    for sp in doc.get("species", []):
        for syl in sp.get("syllables", []):
            learned = syl.get("learned") or {}
            cos = learned.get("resynthesisCosine")
            if cos is not None:
                out[(sp["id"], syl["id"])] = float(cos)
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a_path, b_path = Path(sys.argv[1]), Path(sys.argv[2])
    a, b = types_of(a_path), types_of(b_path)
    shared = sorted(set(a) & set(b))
    if not shared:
        print("the two inventories share no fitted type — different stores or seeds?")
        return 2
    print(f"baseline {a_path.name}: {len(a)} fitted types")
    print(f"encoder  {b_path.name}: {len(b)} fitted types")
    print(f"compared on the {len(shared)} they share "
          f"({len(set(a) ^ set(b))} in only one, excluded)\n")

    av = [a[k] for k in shared]
    bv = [b[k] for k in shared]
    med_a, med_b = statistics.median(av), statistics.median(bv)
    improved = sum(1 for k in shared if b[k] > a[k])
    share = 100.0 * improved / len(shared)

    per_species: dict[str, list[tuple[float, float]]] = {}
    for sp, _syl in shared:
        per_species.setdefault(sp, [])
    for (sp, syl) in shared:
        per_species[sp].append((a[(sp, syl)], b[(sp, syl)]))
    deltas = {
        sp: statistics.median(y for _x, y in rows) - statistics.median(x for x, _y in rows)
        for sp, rows in per_species.items()
    }
    worst_sp = min(deltas, key=lambda s: deltas[s])

    print(f"median resynthesis cosine  {med_a:.4f} -> {med_b:.4f}   ({med_b - med_a:+.4f})")
    print(f"mean                       {sum(av)/len(av):.4f} -> {sum(bv)/len(bv):.4f}")
    print(f"types improved             {improved}/{len(shared)} = {share:.1f} %")
    print(f"worst species              {worst_sp} {deltas[worst_sp]:+.4f} "
          f"(of {len(deltas)} species)")

    g1 = (med_b - med_a) >= 0.02
    g2 = share >= 60.0
    g3 = deltas[worst_sp] >= -0.05
    for name, ok, detail in (
        ("G1 median rises >= 0.02", g1, f"{med_b - med_a:+.4f}"),
        ("G2 >= 60 % of types improve", g2, f"{share:.1f} %"),
        ("G3 no species falls > 0.05", g3, f"{deltas[worst_sp]:+.4f}"),
    ):
        print(f"  {'PASS' if ok else 'FAIL'}  {name:32} {detail}")
    verdict = g1 and g2 and g3
    print(f"\nGATE: {'PASSES' if verdict else 'FAILS'} — "
          f"{'adoptable' if verdict else 'not a default'}")
    print("Note either way: the cosine is a clustering statistic. docs/19 measured its "
          "correlation with audible distortion at ~0.1, so a pass here is a reason to run "
          "the MCD bench, not a claim that it sounds better.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
