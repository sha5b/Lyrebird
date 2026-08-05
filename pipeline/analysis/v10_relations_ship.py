"""
Write the *shipped* relations.json for the v10 build, which no run has produced yet.

The v10 chain skipped it (`--no-relations`, and `out/harvest-inband` had no
`embeddings.f32` until now), so `app/static/birdy/relations.json` has never existed and
`RelationThreads` has been drawing nothing for the whole life of this build. The asset is
optional by design — the loader treats absent and over-budget identically — which is why
the omission was silent.

The standalone `birdy-pipeline relations --out` verb is not the thing to use here: it
writes the *complete* document on purpose, because that verb's output is the analysis. On
this corpus that is 2 929 410 species pairs, and the 2026-08-01 build wrote 760 MB of it
into the assets and hung the tab. `build` ships a trimmed copy instead
(`relations.shipped_relations`, 8 nearest partners per species), and the app enforces the
same decision from the other side with a 32 MB budget on any optional asset. This script is
the trimmed write on its own, so the asset that lands is the one the browser is built for.

Run: `uv run python analysis/v10_relations_ship.py` from `pipeline/`.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from birdy_pipeline import harvest, learn, relations as relations_mod
from birdy_pipeline.cli import EMBEDDINGS_NAME, load_inventory, log, read_store_embeddings

REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "pipeline" / "out" / "harvest-inband"
INVENTORY = REPO / "pipeline" / "out" / "v10" / "learned-v10.json"
OUT = REPO / "pipeline" / "out" / "v10" / "assets" / "relations.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", type=Path, default=STORE)
    ap.add_argument("--inventory", type=Path, default=INVENTORY)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument(
        "--per-species",
        type=int,
        default=relations_mod.SHIPPED_PAIRS_PER_SPECIES,
        help="partners kept per species (the browser reads three at a time)",
    )
    args = ap.parse_args()

    store = harvest.HarvestStore(args.store)
    typing_path = args.store / learn.TYPING_NAME
    emb_path = args.store / EMBEDDINGS_NAME
    for path in (typing_path, emb_path):
        if not path.exists():
            raise SystemExit(f"missing {path}")

    relations_mod.self_test(verbose=False)
    t0 = time.time()
    typing = json.loads(typing_path.read_text(encoding="utf-8"))
    emb = read_store_embeddings(emb_path, len(store.syllables), log=log)
    if emb is None:
        raise SystemExit("could not read the store embeddings")
    inventory = load_inventory(args.inventory)
    document = relations_mod.compute_relations(store, emb, typing, inventory)

    pairs = document["speciesPairs"]
    shared = sum(len(p["sharedTypes"]) for p in pairs)
    log(
        f"{len(pairs)} species pairs, {shared} shared-type candidates under threshold "
        f"{document['sharedTypeThreshold']} ({time.time() - t0:.1f}s)"
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    relations_mod.write_relations(args.out, document, per_species=args.per_species)
    size = args.out.stat().st_size
    log(
        f"wrote {args.out} — {size / 1e6:.1f} MB, trimmed to {args.per_species} partners "
        f"per species (the loader's optional-asset budget is 32 MB)"
    )
    if size > 32 * 1024 * 1024:
        log("OVER BUDGET: the app will treat this exactly like an absent file")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
