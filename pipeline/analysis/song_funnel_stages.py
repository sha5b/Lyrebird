"""The whole song funnel, stage by stage, on whatever store is current.

`song_funnel.py` scores a re-learned *inventory* and answers "did the syntax layer narrow".
It cannot draw `fig_song_funnel`, because that figure needs the three counts that live in the
**store** rather than in the inventory: syllable observations, bouts, and what the bouts do
when their runs collapse. Those numbers were computed once for docs/22 on the
340 079-observation store and never again, which is why the figure carried a note saying it was
pinned to a store that is no longer current.

**This exists so the figure moves as a unit.** The figure's own note refused to patch the
syllable panel alone, correctly: three panels on two different stores is worse than three
panels on one old store. So every count it draws is recomputed here, from one store, in one
pass.

**The bout rule is imported, not reimplemented.** `learn.bout_sequences` and
`learn._collapse_runs` are the functions the production build itself uses, with
`GAP_BOUT_SECONDS` and `SONG_MIN_MOTIF` as the build sets them. A second implementation of the
bout rule here would be a second definition of what a bout is, and the two would drift.

Memory: `syllables.jsonl` is 601 MB on the v9 store and a full parse of it exhausted this
machine once already. Only the four fields the bout rule reads are kept, so the pass runs in
a few hundred megabytes.

Usage:
    .venv/bin/python analysis/song_funnel_stages.py out/harvest-gan out/v9/learned-v9.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from birdy_pipeline import learn  # noqa: E402

OUT = Path(__file__).resolve().parent / "song_funnel_stages.json"


@dataclass(slots=True)
class Row:
    """The four fields `bout_sequences` reads. Nothing else is retained."""

    species_id: str
    recording_id: str
    order: int
    gap_before: float


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def stream_rows(store: Path) -> list[Row]:
    rows: list[Row] = []
    path = store / "syllables.jsonl"
    with path.open() as fh:
        for i, line in enumerate(fh):
            d = json.loads(line)
            rows.append(Row(d["species_id"], d["recording_id"], int(d["order"]),
                            float(d.get("gap_before") or 0.0)))
            if (i + 1) % 100_000 == 0:
                log(f"  read {i + 1} rows")
    return rows


def main() -> int:
    if len(sys.argv) < 3:
        log(__doc__.strip().splitlines()[-1])
        return 2
    store = Path(sys.argv[1])
    inventory = Path(sys.argv[2])
    if not store.is_absolute():
        store = ROOT / store
    if not inventory.is_absolute():
        inventory = ROOT / inventory

    log(f"reading {store.name}/syllables.jsonl ...")
    rows = stream_rows(store)
    typing = json.loads((store / "typing.json").read_text())["entries"]
    log(f"  {len(rows)} observations, {len(typing)} typed")

    bouts = learn.bout_sequences(rows, typing)
    collapsed = [learn._collapse_runs(seq) for _, _, seq in bouts]

    # The funnel's own definitions, matching the figure's labels.
    one_token = sum(1 for c in collapsed if len(c) == 1)
    # The figure's footnote makes a specific point with this: a bout that collapses to one
    # token but held three or more syllables is a bird repeating one sound. That is a
    # repertoire fact, not a measurement error, and it is most of the collapse.
    mono_runs_3plus = sum(1 for (_, _, seq), c in zip(bouts, collapsed)
                          if len(c) == 1 and len(seq) >= 3)
    # Bouts the song layer actually placed in a type.
    song_typing = store / "song-typing.json"
    placed_bouts = (len(json.loads(song_typing.read_text()).get("entries") or [])
                    if song_typing.exists() else None)
    candidates = [(sp, c) for (sp, _, _), c in zip(bouts, collapsed)
                  if len(c) >= learn.SONG_MIN_MOTIF]
    # "Can be asked at all": a species needs enough candidate bouts for song-level
    # clustering to run, which is `SONG_MIN_CLUSTER`. Fewer than that and the question is
    # not refused, it is unaskable.
    per_species = Counter(sp for sp, _ in candidates)
    askable = {sp for sp, n in per_species.items() if n >= learn.SONG_MIN_CLUSTER}

    # Species that end up with a song, split by what gave it to them.
    #
    # **The path is `sp["grammar"]["songTypes"]` and guessing it cost a wrong answer once.**
    # An earlier version of this looked for `sp["songTypes"]` and fell back to `sp["songs"]`,
    # which exists on every species and is a different thing entirely, so it reported all
    # 2 650 fitted species as having a song. `song_funnel.py` already had the correct path,
    # so its own counts are imported below rather than restated here.
    doc = json.loads(inventory.read_text())
    species_entries = doc.get("species") or []
    motif_species: set[str] = set()
    repeat_species: set[str] = set()
    for sp in species_entries:
        sid = sp.get("id") or sp.get("speciesId") or ""
        for song in ((sp.get("grammar") or {}).get("songTypes") or []):
            if str(song.get("kind") or "") == "repeat":
                repeat_species.add(sid)
            else:
                motif_species.add(sid)

    # Cross-check against the existing scorer. If these disagree, one of the two is reading
    # the inventory wrongly and neither number should be drawn.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from song_funnel import funnel as inventory_funnel  # noqa: E402

    scored = inventory_funnel(str(inventory))
    assert scored["species with a song"] == len(motif_species | repeat_species), (
        f"song_funnel.py says {scored['species with a song']} species have a song, "
        f"this says {len(motif_species | repeat_species)} — the inventory is being read "
        "two different ways"
    )

    result = {
        "store": store.name,
        "inventory": inventory.name,
        "gap_bout_seconds": learn.GAP_BOUT_SECONDS,
        "song_min_motif": learn.SONG_MIN_MOTIF,
        "song_min_cluster": learn.SONG_MIN_CLUSTER,
        "syllable_observations": len(rows),
        "typed": len(typing),
        "typed_share": len(typing) / max(1, len(rows)),
        "bouts": len(bouts),
        "collapse_to_one_token": one_token,
        "collapse_share": one_token / max(1, len(bouts)),
        "collapse_but_3plus_syllables": mono_runs_3plus,
        "placed_bouts": placed_bouts,
        "candidates": len(candidates),
        "candidate_share": len(candidates) / max(1, len(bouts)),
        "species_total": len({r.species_id for r in rows}),
        "species_askable": len(askable),
        "species_with_motif_song": len(motif_species),
        "species_with_any_song": len(motif_species | repeat_species),
        "song_types": scored["song types"],
        "motifs": scored["motifs"],
        "repeat_classes": scored["repeat classes"],
        "grammar_chunks": scored["grammar chunks"],
    }

    print("=" * 74)
    print(f"Song funnel, all stages, on {store.name} + {inventory.name}")
    print("=" * 74)
    w = max(len(k) for k in result)
    for k, v in result.items():
        if isinstance(v, float):
            print(f"  {k:<{w}}  {v:.4f}")
        else:
            print(f"  {k:<{w}}  {v}")
    print()
    print("  For comparison, the pre-v9 numbers the figure was drawn from:")
    print("    observations 340 079, typed 327 164, bouts 34 696,")
    print("    collapse 19 738, candidates 10 550,")
    print("    askable 366, motif-song species 48, any-song species 98")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
