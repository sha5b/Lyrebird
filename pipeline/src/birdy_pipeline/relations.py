"""Cross-species relations: shared syllable types and acoustic similarity, label-free.

Everything the learning side produced before this module was conditioned on xeno-canto's
species label: typing ran per species, grammar ran per species, and no artifact ever said
anything *between* species. This is the between-species artifact, and it lives entirely
in the critic's 32-d embedding, because that space is the one trained without being told
what it would hear — "do these two birds share a sound" is a distance question there in
a way it never was in seven hand-weighted numbers.

Two questions, both answered with counts and distances and neither glossed as meaning:

- **Shared or convergent types.** Two species' types whose centroids are nearer than two
  types of *one* bird usually are. That is the whole criterion, and it is deliberately
  derived rather than chosen: the threshold is the median within-species nearest-type
  distance (× 1.0), so "shared" means nearer than the within-bird type spacing of this
  corpus, whatever that spacing happens to be. Whether such a pair is a borrowed call, a
  convergent trill, or a relative's inheritance is not a question the distance answers,
  and the output does not pretend to.
- **Species similarity.** A symmetric matrix over species combining two terms: the
  cosine distance between centroids-of-centroids, and a distributional term — the
  symmetrised mean distance from each species' syllables to the nearest syllable of the
  other. The second term was chosen over a KL divergence between type histograms for a
  concrete reason: type ids are species-local, so two species' histograms have disjoint
  support by construction and every pairwise KL would come out at its maximum. Mean 1-NN
  asks the same question — how much do these two repertoires overlap — in a way that is
  defined.

Shipped as `relations.json` beside the built assets: data only. What the app draws on
top of it is the app's business.

The unlabelled pool is excluded throughout: its typing rows point at *other* species'
types by design (that is what the inheritance verdict is), so averaging over them would
measure the assignment rule rather than any acoustics.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

#: The asset filename `build` writes and the `relations` command defaults to.
RELATIONS_NAME = "relations.json"

#: Syllables sampled per species for the 1-NN term. The statistic stabilises long before
#: this, and a full cross-product over 47k embeddings would buy precision the question
#: does not need at the cost of minutes per build.
NN_SAMPLE = 400


def _unit_rows(z: np.ndarray) -> np.ndarray:
    return z / np.maximum(np.linalg.norm(z, axis=1, keepdims=True), 1.0e-12)


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pairwise cosine distance between the rows of two unit-normed matrices."""
    return 1.0 - _unit_rows(a) @ _unit_rows(b).T


def type_centroids(
    observations: Sequence[Any],
    typing: dict[str, Any],
    embeddings: np.ndarray,
) -> dict[tuple[str, str], np.ndarray]:
    """One unit centroid per (species, typeId), from the store's typing and embeddings.

    `embeddings` is aligned with `observations` by row — the contract `embeddings.f32`
    already keeps with `store.syllables` — and rows with no embedding (NaN, the
    patch-less) are dropped rather than averaged into a centroid they would drag to the
    origin. Unlabelled rows and inheritance verdicts are excluded; see the module
    docstring for why.
    """
    from .learn import UNLABELLED_SPECIES

    row_of = {
        (o.species_id, o.recording_id, o.order): i for i, o in enumerate(observations)
    }
    z = np.asarray(embeddings, dtype=np.float64)
    members: dict[tuple[str, str], list[int]] = {}
    for e in typing.get("entries", []):
        if e["speciesId"] == UNLABELLED_SPECIES:
            continue
        i = row_of.get((e["speciesId"], e["recordingId"], int(e["order"])))
        if i is None or i >= z.shape[0] or not np.all(np.isfinite(z[i])):
            continue
        members.setdefault((e["speciesId"], str(e["typeId"])), []).append(i)
    return {
        key: _unit_rows(z[rows]).mean(axis=0)
        for key, rows in members.items()
        if rows
    }


def compute_relations(
    store: Any,
    embeddings: np.ndarray,
    typing: dict[str, Any],
    inventory: dict[str, Any] | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    """The relations document for one store: shared types and species similarity.

    `store` supplies the syllable observations (row-aligned with `embeddings`),
    `typing` is the store's typing.json, and `inventory` is only consulted for common
    names — the document stands without it.
    """
    centroids = type_centroids(store.syllables, typing, embeddings)
    by_species: dict[str, list[str]] = {}
    for species_id, type_id in centroids:
        by_species.setdefault(species_id, []).append(type_id)
    species = sorted(by_species)
    names = {
        sp.get("id", ""): sp.get("common", "")
        for sp in (inventory or {}).get("species", [])
    }

    # The shared-type threshold, derived: how far apart two types of *one* bird usually
    # are, as the median over species of each bird's own nearest-type distance. A
    # cross-species pair nearer than that is "nearer than two types of one bird usually
    # are" — the × 1.0 multiplier means exactly the median spacing, no margin, because
    # the point of the number is to be a statement about this corpus rather than a
    # knob, and every pair reported carries its own distance for anyone who wants a
    # stricter reading.
    within: list[float] = []
    for sid in species:
        tids = by_species[sid]
        if len(tids) < 2:
            continue
        c = np.stack([centroids[(sid, t)] for t in tids])
        d = _cosine_distance(c, c)
        np.fill_diagonal(d, np.inf)
        within.append(float(d.min()))
    threshold = float(np.median(within)) if within else 0.0

    shared: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for ai, a in enumerate(species):
        ca = np.stack([centroids[(a, t)] for t in by_species[a]])
        for b in species[ai + 1 :]:
            cb = np.stack([centroids[(b, t)] for t in by_species[b]])
            d = _cosine_distance(ca, cb)
            pairs = []
            for ia, ta in enumerate(by_species[a]):
                for ib, tb in enumerate(by_species[b]):
                    dist = float(d[ia, ib])
                    if dist < threshold:
                        pairs.append(
                            {
                                "a": {"species": a, "typeId": ta},
                                "b": {"species": b, "typeId": tb},
                                "distance": round(dist, 4),
                            }
                        )
            if pairs:
                pairs.sort(key=lambda p: p["distance"])
                shared[(a, b)] = pairs

    # Species similarity: centroid-of-centroids cosine distance plus the distributional
    # term (symmetrised mean 1-NN between the species' syllable embeddings), averaged.
    # Both components are reported per pair, so the combination can be second-guessed.
    rng = np.random.default_rng(seed)
    z = np.asarray(embeddings, dtype=np.float64)
    per_species_rows: dict[str, np.ndarray] = {}
    row_of = {
        (o.species_id, o.recording_id, o.order): i for i, o in enumerate(store.syllables)
    }
    species_rows: dict[str, list[int]] = {sid: [] for sid in species}
    for e in typing.get("entries", []):
        sid = e["speciesId"]
        if sid not in species_rows:
            continue
        i = row_of.get((sid, e["recordingId"], int(e["order"])))
        if i is not None and i < z.shape[0] and np.all(np.isfinite(z[i])):
            species_rows[sid].append(i)
    for sid, rows in species_rows.items():
        if not rows:
            continue
        rows = np.asarray(rows)
        if len(rows) > NN_SAMPLE:
            rows = rows[rng.choice(len(rows), size=NN_SAMPLE, replace=False)]
        per_species_rows[sid] = _unit_rows(z[rows])

    species_centroid = {
        sid: _unit_rows(
            np.stack([centroids[(sid, t)] for t in by_species[sid]])
        ).mean(axis=0)
        for sid in species
    }

    pairs_out: list[dict[str, Any]] = []
    for ai, a in enumerate(species):
        for b in species[ai + 1 :]:
            centroid_dist = float(
                1.0
                - np.dot(
                    _unit_rows(species_centroid[a][None])[0],
                    _unit_rows(species_centroid[b][None])[0],
                )
            )
            nn_dist = None
            if a in per_species_rows and b in per_species_rows:
                d_ab = 1.0 - per_species_rows[a] @ per_species_rows[b].T
                nn_dist = float(
                    0.5 * (d_ab.min(axis=1).mean() + d_ab.min(axis=0).mean())
                )
            distance = (
                centroid_dist if nn_dist is None else 0.5 * centroid_dist + 0.5 * nn_dist
            )
            pairs_out.append(
                {
                    "a": a,
                    "b": b,
                    "aCommon": names.get(a, ""),
                    "bCommon": names.get(b, ""),
                    "distance": round(distance, 4),
                    "centroidDistance": round(centroid_dist, 4),
                    "nearestNeighbourDistance": (
                        round(nn_dist, 4) if nn_dist is not None else None
                    ),
                    "sharedTypes": shared.get((a, b), []),
                }
            )
    pairs_out.sort(key=lambda p: p["distance"])

    return {
        "version": 1,
        "space": "critic-embedding-32d",
        "sharedTypeThreshold": round(threshold, 4),
        "sharedTypeDefinition": (
            "cross-species type pairs nearer than the median within-species "
            "nearest-type distance of this corpus — nearer than two types of one bird "
            "usually are. A distance, not a claim of borrowing or kinship."
        ),
        "speciesPairs": pairs_out,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def write_relations(path: Path, document: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(document, indent=1), encoding="utf-8")


def self_test(verbose: bool = True) -> None:
    """A planted shared type must be found, and its distance must beat the threshold."""

    class Store:
        syllables: list[Any] = []

    from .learn import SyllableObservation

    def obs(species: str, order: int) -> SyllableObservation:
        return SyllableObservation(
            species_id=species, recording_id="r", order=order, start=0.0, dur=0.05,
            level=0.9, attack=0.006, hold=True, contour=[[0.0, 3000.0]], am=0.0,
            am_depth=0.0, vib_rate=0.0, vib_depth=0.0, harmonic=0.2, timbre="pure",
            flatness=0.05, gap_before=0.05,
        )

    rng = np.random.default_rng(0)
    store = Store()
    entries = []
    embeddings = []
    # Species A: three well-separated types. Species B: two types of its own, plus one
    # sitting almost on top of A's second type — the planted shared pair.
    basis = rng.normal(size=(8, 32))
    planted_a = rng.normal(size=32)
    planted_b = planted_a + 0.02 * rng.normal(size=32)  # nearly the same direction
    prototypes = {
        ("a", "L00"): basis[0], ("a", "L01"): planted_a, ("a", "L02"): basis[2],
        ("b", "L00"): basis[4], ("b", "L01"): planted_b,
    }
    for (sid, tid), proto in prototypes.items():
        for k in range(6):
            store.syllables.append(obs(sid, k))
            entries.append(
                {"speciesId": sid, "recordingId": "r", "order": k, "typeId": tid}
            )
            embeddings.append(proto + 0.01 * rng.normal(size=32))
    doc = compute_relations(
        store, np.stack(embeddings), {"version": 1, "entries": entries}
    )
    pair = doc["speciesPairs"][0]
    assert {pair["a"], pair["b"]} == {"a", "b"}
    shared = pair["sharedTypes"]
    assert len(shared) == 1, f"expected exactly the planted pair, got {shared}"
    assert shared[0]["a"]["typeId"] == "L01" and shared[0]["b"]["typeId"] == "L01"
    assert shared[0]["distance"] < doc["sharedTypeThreshold"]
    if verbose:
        print(
            f"relations self-test ok: planted shared type found at "
            f"{shared[0]['distance']:.4f} (threshold {doc['sharedTypeThreshold']:.4f})"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
