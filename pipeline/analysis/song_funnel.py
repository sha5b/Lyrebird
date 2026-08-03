"""Score a re-learned inventory on the song funnel, not only on the syllable fit.

**The gate HANDOFF said was missing.** The v6 re-learn improved every syllable-level number
it was gated on — median resynthesis cosine +0.0313, never worse per type — and cost the
syntax layer badly: species with a song 98 -> 68, repeat classes 260 -> 82 (-68 %), grammar
chunks 5 593 -> 1 272 (-77 %). That is not drift and not a bug. It is a measured property of
the project: a finer typing splits the same physical repeat across different ids, so a bout
that collapsed to one token six times now collapses to two tokens four and two times, and
neither clears `SONG_MIN_CLUSTER = 6`. The two-start's gate reads resynthesis cosine and
cannot see the song funnel narrowing behind it.

So every re-learn gets scored on both from now on. This does not decide anything — it prints
the trade, loudly when the syntax layer drops more than a fifth, so an install is a decision
made with the number rather than a surprise found later.

    uv run python pipeline/analysis/song_funnel.py <installed.json> <candidate.json>
"""

import json
import sys
from collections import Counter
from typing import Any

#: A drop past this on any syntax count is called out rather than left in the table.
ALARM = 0.2

#: The counts that make up the funnel, narrowest last: types -> species that have a song at
#: all -> song types -> the classes those split into -> the chunks mined under them.
FIELDS = (
    "species",
    "types",
    "species with a song",
    "song types",
    "repeat classes",
    "motifs",
    "grammar chunks",
)

#: The three the alarm watches. `motifs` is deliberately not among them: it moved least
#: across v5->v6 (96 -> 82) and is the least load-bearing of the four.
WATCHED = ("song types", "repeat classes", "grammar chunks")


def funnel(path: str) -> dict[str, int]:
    doc = json.load(open(path, encoding="utf-8"))
    species: list[dict[str, Any]] = doc.get("species", [])
    kinds: Counter[str] = Counter()
    for sp in species:
        for t in (sp.get("grammar") or {}).get("songTypes") or []:
            kinds[t.get("kind", "?")] += 1
    return {
        "species": len(species),
        "types": sum(len(sp.get("syllables", [])) for sp in species),
        "species with a song": sum(
            1 for sp in species if (sp.get("grammar") or {}).get("songTypes")
        ),
        "song types": sum(
            len((sp.get("grammar") or {}).get("songTypes") or []) for sp in species
        ),
        "repeat classes": kinds.get("repeat", 0),
        "motifs": kinds.get("motif", 0),
        "grammar chunks": sum(
            len((sp.get("grammar") or {}).get("chunks") or []) for sp in species
        ),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    old, new = funnel(argv[1]), funnel(argv[2])

    print(f"  {'':22} {'installed':>10} {'candidate':>10} {'change':>9}")
    for key in FIELDS:
        o, n = old[key], new[key]
        change = "     —" if not o else f"{(n - o) / o * 100:+.0f} %"
        print(f"  {key:22} {o:>10} {n:>10} {change:>9}")

    lost = [k for k in WATCHED if old[k] and new[k] < old[k] * (1.0 - ALARM)]
    if lost:
        print(f"\n  ** THE SYNTAX LAYER LOST MORE THAN {ALARM * 100:.0f} % ON: " + ", ".join(lost))
        print("  ** Expected, measured and documented (docs/22 §22.2): a better syllable fit")
        print("  ** is a worse typing for finding repeats, because finer distinctions fracture")
        print("  ** the runs repeat detection depends on. Not a bug, and not a reason to abort")
        print("  ** the chain — a reason not to install without deciding to accept it.")
    else:
        print(f"\n  the syntax layer held: nothing watched fell more than {ALARM * 100:.0f} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
