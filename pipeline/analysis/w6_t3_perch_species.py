"""W6 T3 — species retrieval in the Perch space against the critic's, same estimator.

T1's population was chosen for recordist replication (135 recordists, ~14 recordings
each), which leaves 1 611 species over 1 934 recordings — almost no species reaches
`geometry.MIN_GROUP` = 8, so a species lift cannot be estimated there at all. This pass
selects for the other axis and reports both groupings on it, so T3 has a population that
can carry it and T1's recordist number gets a second, differently-drawn sample.

PRE-REGISTERED, before the run:

  T3  species kNN lift in the Perch space must be **at or above** the critic's on the
      same recordings. The comparator is the critic measured per recording on these same
      rows, because that is the only apples-to-apples form.

      **The form of the test is forced by the data.** The audio cache holds at most TWO
      recordings per species (2 616 species with exactly two, 1 221 with one, no species
      with three) — the iNat ingest took no more, and the xeno-canto audio was deleted at
      harvest. So a species group of `geometry.MIN_GROUP` = 8 does not exist and cannot be
      made without re-fetching audio, which is an owner-called network step. What the data
      does support is the pair test: with `min_group=2`, does a recording's nearest
      neighbour come from its own species? `geometry.measure` allows exactly this — its
      docstring keeps `min_group` for callers testing a small population on purpose, where
      the permutation null rather than the group size is what keeps the test honest.
  T1' recordist lift, reported again on this population. The T1 gate is unchanged:
      at least 30 % below the critic's, species lift not lower.

Selection, fixed before the run: species with exactly 2 cached recordings, both taken, to
a cap of 2 000 recordings — 1 000 species, each a pair.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/sha5b/Documents/GitHub/Birdy/pipeline/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from birdy_pipeline import geometry  # noqa: E402
from birdy_pipeline.harvest import HarvestStore  # noqa: E402
from w6_t1_perch_recordist import CACHE, SEED, STORE, critic_embed, load_model, log, perch_embed  # noqa: E402

MIN_PER_SPECIES = 2
MAX_PER_SPECIES = 2
RECORDING_CAP = 2000
OUT = Path(__file__).resolve().parent / "w6_t3.json"


def select(store: HarvestStore) -> list[str]:
    cached = {p.stem for p in CACHE.glob("*.wav")}
    by_species: dict[str, list[str]] = defaultdict(list)
    for rid, meta in sorted(store.recordings.items()):
        if rid in cached and meta.get("recordist") and meta.get("speciesId"):
            by_species[meta["speciesId"]].append(rid)
    rng = np.random.default_rng(SEED)
    chosen: list[str] = []
    for sp in sorted(by_species, key=lambda s: (-len(by_species[s]), s)):
        recs = by_species[sp]
        if len(recs) < MIN_PER_SPECIES:
            continue
        take = recs if len(recs) <= MAX_PER_SPECIES else [
            recs[i] for i in rng.permutation(len(recs))[:MAX_PER_SPECIES]
        ]
        chosen.extend(sorted(take))
        if len(chosen) >= RECORDING_CAP:
            break
    return sorted(chosen[:RECORDING_CAP])


def main() -> None:
    t0 = time.time()
    store = HarvestStore(STORE)
    store.load()
    chosen = select(store)
    log(f"selected {len(chosen)} recordings from "
        f"{len({store.recordings[r]['speciesId'] for r in chosen})} species, "
        f"{len({store.recordings[r]['recordist'] for r in chosen})} recordists")
    critic = critic_embed(store, set(chosen))
    log(f"critic: per-recording means for {len(critic)} of them")

    model = load_model()
    rows: list[str] = []
    vecs: list[np.ndarray] = []
    for i, rid in enumerate(chosen):
        if rid not in critic:
            continue
        try:
            v = perch_embed(model, CACHE / f"{rid}.wav")
        except Exception as exc:
            log(f"  {rid}: {exc}")
            continue
        if v is None:
            continue
        rows.append(rid)
        vecs.append(v)
        if (i + 1) % 400 == 0:
            log(f"  embedded {len(rows)}/{i + 1} in {time.time() - t0:.0f}s")

    perch_x = np.stack(vecs)
    critic_x = np.stack([critic[r] for r in rows])
    species = [store.recordings[r]["speciesId"] for r in rows]
    recordist = [store.recordings[r]["recordist"] for r in rows]
    log(f"{len(rows)} recordings embedded both ways in {time.time() - t0:.0f}s")

    report: dict[str, object] = {
        "recordings": len(rows),
        "species": len(set(species)),
        "recordists": len(set(recordist)),
        "arms": [],
    }
    for tag, matrix in (("critic 32-d", critic_x), ("perch 1536-d", perch_x)):
        row: dict[str, object] = {"space": tag, "dims": int(matrix.shape[1])}
        for name, labels in (("species", species), ("recordist", recordist)):
            # species groups are pairs here, for the reason in the module docstring;
            # recordist keeps the corpus-level gate of 8.
            found = geometry.measure(
                matrix, list(labels), name, tag, "cosine", seed=SEED,
                min_group=2 if name == "species" else geometry.MIN_GROUP,
            )
            row[name] = None if found is None else round(found.knn - found.knn_null, 4)
            row[f"{name}Coverage"] = None if found is None else round(found.coverage, 4)
        report["arms"].append(row)
        log(f"  {tag:14} species {row['species']} (cov {row['speciesCoverage']})  "
            f"recordist {row['recordist']} (cov {row['recordistCoverage']})")

    c, p = report["arms"]
    report["gate"] = (
        "T3: perch species lift >= critic's on the same rows. T1: perch recordist lift "
        "<= 70 % of the critic's with species lift not lower (docs/23 §23.6)"
    )
    if None not in (c["species"], p["species"]):
        report["t3Passes"] = bool(p["species"] >= c["species"])
    if None not in (c["recordist"], p["recordist"], c["species"], p["species"]):
        report["t1Passes"] = bool(
            p["recordist"] <= c["recordist"] * 0.7 and p["species"] >= c["species"]
        )
    report["seconds"] = round(time.time() - t0, 1)
    OUT.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
