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

# --- the duplicate-recording guard -------------------------------------------------
#
# **Two species can be the same audio under two labels, and the pair then reads as the
# closest relation in the corpus.** `bleda_notatus` and `eurillas_latirostris` are
# `INAT165079.wav` and `INAT165088.wav`: byte-identical, 965 770 bytes, same sha256, same
# iNaturalist rights holder. Each has one recording and 146 syllables, every row identical
# once the ids are stripped, all 8 of 8 type centroids bit-identical — so "8 shared types"
# is one repertoire counted twice, and the pair came out at distance -0.0, the float
# overshoot of a unit vector against itself.
#
# It is a class of row, not one row: 17 cross-species duplicate groups over 35 recordings
# and 40 species in the harvest store, of which 11 pairs survived the trim into the shipped
# asset. **Four of the five nearest pairs in that asset were duplicate artefacts**, which
# means the head of "Sounds like" — the part a reader trusts most, because it is the part
# the interface shows first — was mostly not a finding about birds.
#
# The durable fix is upstream: `sources.py`'s `_ingest_staged` dedupes on the recording id
# alone and no content hash exists anywhere in harvest/sources, so the same bytes under two
# iNaturalist observation ids pass straight through. This guard is the downstream half, and
# it is nearly free here because `d_ab` is already computed for the distance.
#
# Costed before it was applied: 11 pairs and 140 of 526 shared-type candidates (27 %).

#: Cosine distance under which two sampled syllables are the same sound. Identical unit
#: vectors score exactly 0.0 or -0.0, so this is "bit-identical" and not "very similar" —
#: deliberately far below the 0.014 of the nearest *genuine* pair in the corpus. The
#: distribution has a hole between -0.0 and 0.014, so the constant is not delicate.
DUPLICATE_TWIN_DISTANCE = 1.0e-9

#: Share of one species' sampled syllables that must have an identical twin in the other
#: before the pair is refused. Half, because a duplicate *recording* shared between two
#: species duplicates most of both repertoires, while two birds genuinely singing one call
#: share a handful of types out of dozens.
DUPLICATE_TWIN_SHARE = 0.5


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
    #: Pairs refused as the same audio under two labels. Kept and reported rather than
    #: silently dropped: an exclusion nobody can see reads as a corpus that simply has no
    #: duplicates in it, and this one costs 27 % of the shared-type candidates.
    duplicate_pairs: list[dict[str, Any]] = []
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
                # The duplicate-recording guard. Symmetric — `max` of the two shares, not
                # A's alone — because which species is `a` is decided by the sort and
                # nothing else, and a recording that duplicates all of a small repertoire
                # into a large one shows up in only one direction. Taking the larger share
                # makes the verdict independent of the ordering.
                twin_a = float((d_ab.min(axis=1) <= DUPLICATE_TWIN_DISTANCE).mean())
                twin_b = float((d_ab.min(axis=0) <= DUPLICATE_TWIN_DISTANCE).mean())
                if max(twin_a, twin_b) > DUPLICATE_TWIN_SHARE:
                    duplicate_pairs.append(
                        {
                            "a": a,
                            "b": b,
                            "aCommon": names.get(a, ""),
                            "bCommon": names.get(b, ""),
                            "identicalShare": round(max(twin_a, twin_b), 4),
                            "sharedTypesRefused": len(shared.get((a, b), [])),
                        }
                    )
                    continue
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
        "duplicateSourcePairs": duplicate_pairs,
        "duplicateSourceDefinition": (
            "pairs refused because more than half of one species' sampled syllables have "
            "a bit-identical twin in the other — the same recording ingested under two "
            "labels, which scores as the closest relation in the corpus and is not a "
            "relation at all. The upstream fix is a content hash in the harvester; until "
            "that exists these are excluded here, and counted so the exclusion is visible."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# How many nearest partners each species keeps in the SHIPPED asset.
#
# The reader (`relationsOf` in app/src/routes/+page.svelte) asks for a species' three
# nearest partners. Eight leaves headroom, so the shipped file answers any request up to
# eight *exactly* — the same partners, in the same order, as the whole document would.
SHIPPED_PAIRS_PER_SPECIES = 8


def shipped_relations(
    document: dict[str, Any], per_species: int = SHIPPED_PAIRS_PER_SPECIES
) -> dict[str, Any]:
    """The part of `document` a browser needs, with the cut declared inside it.

    **Why this exists.** `compute_relations` returns every unordered pair of species,
    which is what the analysis wants and is quadratic in the corpus: at the 2 423 species
    of the 2026-08-01 production build that is **2 929 410 pairs and a 760 MB JSON file**,
    written beside a galaxy whose whole point-cloud is 4 MB. The app fetched it before the
    first frame, and `JSON.parse` at that size is not slow, it is a tab that does not come
    back. The app-side loader now refuses an optional asset over 32 MB, which stops the
    hang; it does not make the feature work. This does.

    **Measured on that production document**: 2 929 410 pairs -> **14 425 (5.6 MB, 135x
    smaller)**, carrying 9 513 of the 26 859 shared-type candidates, and checked lossless
    across all 2 421 species at the app's limit of 3 with zero mismatches. That trim is
    what `app/static/birdy/relations.json` holds — so read the 760 MB above as the motive,
    not as the current size of anything shipped.

    **What is kept is what is read.** Each species keeps its `per_species` nearest
    partners, so every question the UI asks is answered identically to the full document.
    The union is deduplicated — a pair near the top of both its species' lists is one pair.

    **What is dropped is stated, in the file.** The `retention` block records the totals,
    so the shipped asset can never be mistaken for the whole finding: in particular the
    shared-type count it carries is the count *among kept pairs*, and reading it as the
    corpus's would understate it. The complete document is still what `compute_relations`
    returns and what the build logs its statistics from, so nothing about the measurement
    moves — only the size of the copy the browser is handed.
    """
    pairs = document["speciesPairs"]
    if per_species <= 0:
        return document

    # Nearest-first per species. `pairs` arrives sorted by distance, so the first
    # `per_species` hits for a species are its nearest — no re-sorting needed.
    seen_for: dict[str, int] = {}
    keep: list[dict[str, Any]] = []
    kept_ids: set[int] = set()
    for pair in pairs:
        a, b = pair["a"], pair["b"]
        wanted = (
            seen_for.get(a, 0) < per_species or seen_for.get(b, 0) < per_species
        )
        if not wanted:
            continue
        seen_for[a] = seen_for.get(a, 0) + 1
        seen_for[b] = seen_for.get(b, 0) + 1
        if id(pair) not in kept_ids:
            kept_ids.add(id(pair))
            keep.append(pair)

    shared_kept = sum(len(p["sharedTypes"]) for p in keep)
    shared_total = sum(len(p["sharedTypes"]) for p in pairs)
    out = dict(document)
    out["speciesPairs"] = keep
    out["retention"] = {
        "rule": (
            f"each species keeps its {per_species} nearest partners; the union, "
            "deduplicated. Every query the app makes (a species' three nearest) is "
            "answered exactly as the complete document would answer it."
        ),
        "pairsKept": len(keep),
        "pairsComputed": len(pairs),
        "sharedTypesKept": shared_kept,
        "sharedTypesComputed": shared_total,
        "note": (
            "sharedTypesKept counts only the kept pairs and is NOT this corpus's "
            "shared-type total — sharedTypesComputed is. The complete document is what "
            "compute_relations returns and what the build reports its statistics from; "
            "this file is the browser's copy of the part it reads."
        ),
    }
    return out


def write_relations(
    path: Path,
    document: dict[str, Any],
    per_species: int | None = SHIPPED_PAIRS_PER_SPECIES,
) -> None:
    """Write `document`, trimmed to what a browser reads unless `per_species` is None.

    `None` writes the complete document — for the standalone `relations` verb, where the
    file is the analysis output rather than a shipped asset.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = document if per_species is None else shipped_relations(document, per_species)
    Path(path).write_text(json.dumps(payload, indent=1), encoding="utf-8")


def self_test(verbose: bool = True) -> None:
    """A planted shared type must be found, and its distance must beat the threshold."""

    class Store:
        syllables: list[Any] = []

    from .learn import SyllableObservation

    def obs(species: str, recording: str, order: int) -> SyllableObservation:
        return SyllableObservation(
            species_id=species, recording_id=recording, order=order, start=0.0, dur=0.05,
            level=0.9, attack=0.006, hold=True, contour=[[0.0, 3000.0]], am=0.0,
            am_depth=0.0, vib_rate=0.0, vib_depth=0.0, harmonic=0.2, timbre="pure",
            flatness=0.05, gap_before=0.05,
        )

    rng = np.random.default_rng(0)
    store = Store()
    entries = []
    embeddings = []
    # Axis directions for the ordinary types: mutually at distance 1, so the only pair
    # under any sane threshold is the planted one. Species A has three well-separated
    # types; species B has one of its own plus one sitting almost on top of A's second
    # type — the planted shared pair.
    basis = np.eye(32)
    planted_a = basis[1] + 0.01 * rng.normal(size=32)
    planted_b = planted_a + 0.02 * rng.normal(size=32)  # nearly the same direction
    prototypes = {
        ("a", "L00"): basis[0], ("a", "L01"): planted_a, ("a", "L02"): basis[2],
        ("b", "L00"): basis[4], ("b", "L01"): planted_b,
    }
    for (sid, tid), proto in prototypes.items():
        for k in range(6):
            store.syllables.append(obs(sid, f"{sid}-{tid}", k))
            entries.append(
                {"speciesId": sid, "recordingId": f"{sid}-{tid}", "order": k, "typeId": tid}
            )
            embeddings.append(proto + 0.01 * rng.normal(size=32))
    doc = compute_relations(
        store, np.stack(embeddings), {"version": 1, "entries": entries}
    )
    pair = doc["speciesPairs"][0]
    assert {pair["a"], pair["b"]} == {"a", "b"}
    shared = pair["sharedTypes"]
    assert shared, "the planted shared pair was not found"
    top = shared[0]
    assert top["a"]["typeId"] == "L01" and top["b"]["typeId"] == "L01"
    assert top["distance"] < 0.01, f"planted pair too far: {top['distance']}"
    # ...and uniquely close: everything else is ordinary cross-species spacing.
    assert all(p["distance"] > 0.9 for p in shared[1:]), shared
    # The genuine pair must survive the duplicate guard: a planted *shared type* is one
    # type of several, not a duplicated repertoire, and refusing it would throw away the
    # finding this module exists to make.
    assert not doc["duplicateSourcePairs"], doc["duplicateSourcePairs"]

    # --- and the duplicate guard, on a repertoire that really is a copy ----------------
    #
    # Byte-identical rows under two labels, which is what `INAT165079.wav` and
    # `INAT165088.wav` are. Checked here rather than trusted, because the failure mode is
    # silent in both directions: too tight a threshold ships the artefact at the head of
    # "Sounds like", and too loose a one refuses two birds that genuinely share a call.
    copy_store = Store()
    copy_store.syllables = []
    copy_entries: list[dict[str, Any]] = []
    copy_rows: list[np.ndarray] = []
    block = rng.normal(size=(6, 32))
    for sid in ("orig", "dupe", "other"):
        rows = block if sid != "other" else rng.normal(size=(6, 32))
        for k, row in enumerate(rows):
            copy_store.syllables.append(obs(sid, f"{sid}-rec", k))
            copy_entries.append(
                {"speciesId": sid, "recordingId": f"{sid}-rec", "order": k, "typeId": f"T{k}"}
            )
            copy_rows.append(row)
    dup_doc = compute_relations(
        copy_store, np.stack(copy_rows), {"version": 1, "entries": copy_entries}
    )
    refused = dup_doc["duplicateSourcePairs"]
    assert len(refused) == 1, f"the duplicated repertoire was not refused: {refused}"
    assert {refused[0]["a"], refused[0]["b"]} == {"orig", "dupe"}, refused
    assert refused[0]["identicalShare"] == 1.0, refused
    # Both genuine pairings survive — the guard must cost exactly the duplicate.
    assert len(dup_doc["speciesPairs"]) == 2, dup_doc["speciesPairs"]
    assert all(
        "dupe" not in (p["a"], p["b"]) or "orig" not in (p["a"], p["b"])
        for p in dup_doc["speciesPairs"]
    )
    if verbose:
        print(
            f"relations self-test ok: planted shared type found at "
            f"{top['distance']:.4f} (threshold {doc['sharedTypeThreshold']:.4f})"
        )

    _shipped_self_test(verbose=verbose)


def _shipped_self_test(verbose: bool = True) -> None:
    """The trim must answer every question the app asks exactly as the whole document does.

    That is the whole claim `shipped_relations` makes, and it is the one worth pinning: a
    trim that quietly drops a species' nearest partner would show the wrong bird in the
    Reading panel and nothing would ever say so. Built on a synthetic ring of species so
    the expected answer is known without running a corpus.
    """
    n = 40
    per_species = 8
    names = [f"s{i:02d}" for i in range(n)]
    # Distance from the index gap: species i's nearest partners are its neighbours in the
    # ring, so who *should* survive the trim is known by construction.
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            gap = min(j - i, n - (j - i))
            pairs.append(
                {
                    "a": names[i],
                    "b": names[j],
                    "aCommon": "",
                    "bCommon": "",
                    "distance": float(gap),
                    "centroidDistance": float(gap),
                    "nearestNeighbourDistance": None,
                    # Give a couple of pairs shared types, so the retention counts are
                    # exercised rather than asserted against zero.
                    "sharedTypes": [{"a": {}, "b": {}, "distance": 0.0}] if gap == 1 else [],
                }
            )
    pairs.sort(key=lambda p: p["distance"])
    whole = {"version": 1, "speciesPairs": pairs, "sharedTypeThreshold": 0.5}
    trimmed = shipped_relations(whole, per_species=per_species)

    def nearest(doc: dict[str, Any], sid: str, limit: int) -> list[tuple[str, float]]:
        """Exactly what `relationsOf` does in the app, in Python."""
        mine = [p for p in doc["speciesPairs"] if p["a"] == sid or p["b"] == sid]
        mine.sort(key=lambda p: p["distance"])
        return [
            (p["b"] if p["a"] == sid else p["a"], p["distance"]) for p in mine[:limit]
        ]

    # The app asks for three. Assert across every species, and at the full headroom too.
    for limit in (3, per_species):
        for sid in names:
            want = nearest(whole, sid, limit)
            got = nearest(trimmed, sid, limit)
            # Compare distances, not partner identity: ties at equal gap are ordered by
            # whatever the sort was stable on, and the claim is about what is *shown*.
            assert [d for _, d in want] == [d for _, d in got], (
                f"{sid} at limit {limit}: {want} != {got}"
            )
            assert len(got) == limit, f"{sid} lost partners at limit {limit}: {got}"

    r = trimmed["retention"]
    assert r["pairsComputed"] == len(pairs)
    assert r["pairsKept"] < r["pairsComputed"], "the trim kept everything"
    assert r["sharedTypesComputed"] == n, r["sharedTypesComputed"]
    # No duplicates, and nothing invented.
    keys = [(p["a"], p["b"]) for p in trimmed["speciesPairs"]]
    assert len(keys) == len(set(keys)), "the trim duplicated a pair"
    assert set(keys) <= {(p["a"], p["b"]) for p in pairs}
    # per_species=0 is the escape hatch: the whole document, untouched.
    assert shipped_relations(whole, per_species=0) is whole

    if verbose:
        print(
            f"shipped-relations self-test ok: {r['pairsKept']} of {r['pairsComputed']} "
            f"pairs kept, every species' nearest {per_species} answered identically"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
