#!/usr/bin/env python3
"""Recount the pre-registered gate ledger from the manuscript itself.

The tally sentence appears twice in `docs/whitepaper/arxiv/main.tex` (abstract-adjacent
contributions list, and the appendix preamble) and once as a comment in the W0 paper.
Every other number in this project has a command that reproduces it; this one did not,
and it was wrong -- the appendix said two gates were "unrun or pending" when exactly one
row in the table carries an unrun verdict.

Classification rule, stated before the count and applied to the verdict column only:

  UNRUN    the verdict says "unrun" or "not run"
  PASS     the verdict names an adoption (ships / adopted / passes / wins) and does NOT
           also say fails / failed / refuted
  REFUSAL  everything else

A verdict that says both -- "fails; ships as an honesty gate" -- counts as a refusal.
That is the project's own reading: the appendix's next sentence calls the map-flip lever,
the mel target, label assignment and the source-axis deflation "four refusals [that]
still produced an asset".

Rows beginning `\\quad` are continuations of the gate above them (a first attempt that
found a bug) and are not counted as separate gates. That is what makes the total 58
rather than 59.

The two totals are robust to the two genuinely arguable rows: "wins the rule; not
adopted" and "superseded by the above". Swapping either verdict's bucket leaves
20 / 37 / 1 unchanged, because they sit on opposite sides of the rule.

Usage:
    python analysis/ledger_tally.py [path/to/main.tex]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DEFAULT_TEX = Path(__file__).resolve().parents[2] / "docs/whitepaper/arxiv/main.tex"

PASS_WORDS = ("ships", "adopted", "passes", "wins")
FAIL_WORDS = ("fails", "failed", "refuted", "retracted")
UNRUN_WORDS = ("unrun", "not run")


def ledger_rows(tex: str) -> list[tuple[str, str]]:
    """Return (what was tried, verdict) for every counted row of tab:ledger."""
    body = tex.split(r"\label{tab:ledger}", 1)[1]
    body = body.split(r"\endlastfoot", 1)[1].split(r"\end{longtable}", 1)[0]

    rows: list[tuple[str, str]] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.endswith(r"\\") or line.startswith("%"):
            continue
        if line.startswith(r"\quad"):  # continuation of the gate above
            continue
        cells = line[:-2].split("&")
        if len(cells) != 4:
            raise SystemExit(f"row is not four columns: {line[:60]}")
        rows.append((cells[0].strip(), cells[-1].strip()))
    return rows


def classify(verdict: str) -> str:
    v = re.sub(r"\\(textbf|emph|,|;)|[{}]", " ", verdict).lower()
    if any(w in v for w in UNRUN_WORDS):
        return "unrun"
    if any(w in v for w in PASS_WORDS) and not any(w in v for w in FAIL_WORDS):
        return "pass"
    return "refusal"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TEX
    rows = ledger_rows(path.read_text(encoding="utf-8"))

    counts = {"pass": 0, "refusal": 0, "unrun": 0}
    per_row = []
    for what, verdict in rows:
        bucket = classify(verdict)
        counts[bucket] += 1
        per_row.append({"gate": what, "verdict": verdict, "bucket": bucket})

    for r in per_row:
        print(f"{r['bucket']:8s}  {r['gate'][:52]:52s}  {r['verdict'][:44]}")

    print()
    print(f"gates counted   {len(rows)}")
    print(f"passed          {counts['pass']}")
    print(f"written refusal {counts['refusal']}")
    print(f"unrun           {counts['unrun']}")

    claimed = re.search(
        r"Of (\d+) gates, (\d+) passed, (\d+) ended in a written refusal, and (\d+)",
        path.read_text(encoding="utf-8"),
    )
    if claimed:
        stated = tuple(int(g) for g in claimed.groups())
        found = (len(rows), counts["pass"], counts["refusal"], counts["unrun"])
        print(f"\nthe manuscript states {stated}")
        print(f"the table contains    {found}")
        print("AGREES" if stated == found else "DISAGREES -- the manuscript is stale")

    out = Path(__file__).with_suffix(".json")
    out.write_text(
        json.dumps({"counts": counts, "gates": len(rows), "rows": per_row}, indent=1),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
