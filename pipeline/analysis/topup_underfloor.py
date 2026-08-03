"""Top up the species that sit just below learn's fitting floor, from the archive they came from.

The measurement this exists to act on, taken 2026-08-03 against `out/harvest-gan`:

    retained syllable observations   340,079
    species with retained syllables    3,581
      ... not in the inventory         1,160
      ... of those, >= 24 retained         0    <- learn.MIN_OBSERVATIONS
      largest unmodelled                  23    (one short of the floor)
      median unmodelled                   11

**Every unmodelled species is at or below 23.** `learn` already considered them and skipped
every one, which is why the v8 chain reproduced the installed inventory byte-for-byte: the
inventory contains exactly the species that cleared 24. So the corpus is not short of audio in
general — it is short of *a little* audio for 1 160 birds, and each of them needs a median of
13 more observations to become modellable.

Source is `inat-sounds`, not xeno-canto, because that is where this audio came from:
`out/harvest-gan/CREDITS.md` is full of `INAT…` ids against visipedia/inat_sounds, and
`sources list` reports iNatSounds 2024 as 111k Aves recordings over 3 846 species — which is
the 3 581 in the store. It is also keyless, so this costs no API quota.

**The cap is the thing to be careful about.** `syllableCap` is 400 000 and the store holds
340 079, so there are 59 921 observations of headroom. Past that `HarvestStore._trim` does not
stop — it retires the oldest recording of whichever species currently has the most syllables,
converging on an even split. That is defensible behaviour and it is not what this script is
for, so it stops while there is still headroom and says so.

One recording is usually enough: the store averages 340 079 / 10 184 ≈ 33 observations per
recording, so a bird at 11 clears 24 on its first new file. `--per-file` is therefore 1 by
default and the budget is spent on breadth rather than depth.

    uv run python analysis/topup_underfloor.py --dry-run          # what it would fetch
    uv run python analysis/topup_underfloor.py --max-species 50   # a bounded proof
    uv run python analysis/topup_underfloor.py                    # the lot, cap-guarded

Nothing here writes the inventory. `learn` is what turns new observations into fitted types,
and it is a separate, deliberate step.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PIPELINE = REPO / "pipeline"

#: learn.MIN_OBSERVATIONS — below this a repertoire is not worth fitting, so a species below
#: it is invisible to the model however much has been analysed for it.
FLOOR = 24

#: Leave this much of the syllable cap unspent. The trim rule evicts rather than refuses, and
#: a top-up that quietly retired somebody else's recordings would be the opposite of the point.
HEADROOM_MARGIN = 5_000

SPECIES_ID = re.compile(r'"species_id": "([^"]*)"')


def store_state(store: Path) -> dict:
    return json.loads((store / "state.json").read_text(encoding="utf-8"))


def retained_by_species(store: Path) -> dict[str, int]:
    """Counts from `syllables.jsonl`, which is what `learn` actually reads.

    Deliberately not `state.json`'s `seenPerSpecies`: that counts windows *analysed*, and
    reading it as "observations we hold" is the mistake that produced a confident "545 species
    could be fitted today" when the true answer was zero.
    """
    counts: dict[str, int] = {}
    with (store / "syllables.jsonl").open(encoding="utf-8") as f:
        for line in f:
            m = SPECIES_ID.search(line)
            if m:
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts


def scientific_of(species_id: str) -> str:
    """`parkesia_noveboracensis` -> `Parkesia noveboracensis`.

    The ids are built from the scientific name, so this inverts cleanly for a binomial. A
    three-part id (a subspecies) keeps its tail, which is what the archive indexes it under.
    """
    parts = species_id.split("_")
    if len(parts) < 2:
        return ""
    return " ".join([parts[0].capitalize(), *parts[1:]])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="out/harvest-gan", type=Path)
    ap.add_argument("--inventory", default=str(REPO / "data" / "learned-inventory.json"))
    ap.add_argument("--per-file", type=int, default=1,
                    help="recordings to fetch per species; one is usually enough to clear the floor")
    ap.add_argument("--max-species", type=int, default=0, help="0 = every under-floor species")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    store = (PIPELINE / args.store) if not args.store.is_absolute() else args.store
    state = store_state(store)
    cap = int(state.get("syllableCap", 400_000))
    held = int(state.get("syllableObservations", 0))
    print(f"store {store}")
    print(f"  syllables {held:,} of cap {cap:,} — headroom {cap - held:,}")

    inventory = {sp["id"] for sp in json.loads(Path(args.inventory).read_text())["species"]}
    counts = retained_by_species(store)
    under = {
        sid: n for sid, n in counts.items()
        if sid and sid not in inventory and n < FLOOR
    }
    # Emptiest first, the same discipline the xeno-canto harvest queue follows: a bird holding
    # nothing is served before a bird holding twenty-three.
    order = sorted(under, key=lambda s: (under[s], s))
    if args.max_species:
        order = order[: args.max_species]

    print(f"  under the floor of {FLOOR}: {len(under):,} species not in the inventory")
    print(f"  this run will attempt {len(order):,}, emptiest first")
    if not order:
        print("nothing to do")
        return

    # Per-recording yield, measured on this store rather than assumed: it is what decides
    # whether one file is enough and how much of the cap a pass will spend. `recordings` in
    # state.json is a *mapping* of recording id to its metadata, not a count.
    seen = state.get("recordings")
    recordings = max(1, len(seen) if hasattr(seen, "__len__") else int(seen or 1))
    print(f"  (store holds {recordings:,} recordings, averaging "
          f"{held / recordings:.0f} observations each)")

    fetched = 0
    added = 0
    started = time.time()
    for i, sid in enumerate(order, 1):
        name = scientific_of(sid)
        if not name:
            print(f"  skip {sid}: cannot form a binomial")
            continue

        held_now = int(store_state(store).get("syllableObservations", 0))
        if cap - held_now <= HEADROOM_MARGIN:
            print(f"\nSTOPPING at {held_now:,} of {cap:,}: only {cap - held_now:,} headroom left, "
                  f"and the trim rule evicts rather than refuses. "
                  f"Raise syllableCap to go further.")
            break

        cmd = [
            "uv", "run", "birdy-pipeline", "sources", "fetch",
            "--source", "inat-sounds",
            "--species", name,
            "--limit", str(args.per_file),
            "--store", str(args.store),
        ]
        if args.dry_run:
            print(f"  [{i}/{len(order)}] would fetch {args.per_file} for {name} (has {under[sid]})")
            continue

        before = held_now
        proc = subprocess.run(cmd, cwd=PIPELINE, capture_output=True, text=True, timeout=1800)
        after = int(store_state(store).get("syllableObservations", 0))
        gain = after - before
        added += gain
        fetched += 1
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()
        note = tail[-1][:80] if tail else ""
        print(f"  [{i}/{len(order)}] {name:38} {under[sid]:>3} -> +{gain:<5} obs   {note}")
        sys.stdout.flush()

    if not args.dry_run:
        final = int(store_state(store).get("syllableObservations", 0))
        print(f"\nfetched for {fetched} species, +{added:,} observations "
              f"in {(time.time() - started) / 60:.1f} min")
        print(f"store now {final:,} of {cap:,}")
        print("\nNext: `learn` is what turns these into fitted types. Until it runs, the "
              "inventory is unchanged and the galaxy is unchanged.")


if __name__ == "__main__":
    main()
