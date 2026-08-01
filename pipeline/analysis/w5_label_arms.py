"""docs/22 §22.5 — label assignment against the shipped kmeans path, one fixed matrix.

The matrix is the debug-100 `build --dump-points` set (214 154 points, 2 143 types) that
§22.6's four arms already ran on, so this row is comparable to that table. Every arm goes
through the shipped functions — `cluster_plan`, `type_seeds`, `label_assign`, `_purity`,
`label_cluster` — so no arm is a re-implementation of the build.

PRE-REGISTERED, before the run:

  G1  type retrieval — for each labelled point, is the nearest centroid (cosine in the
      standardised 32-d space, the lookup `SpectralMatcher` performs on live audio) a
      cluster whose majority name is that point's own type?  Gate: label >= kmeans + 10
      points.  This is the honest headline: purity and type coverage are 1.0 under label
      assignment by construction and measure nothing.
  G2  type coverage — share of types that are some cluster's majority name.
      Gate: label = 1.000, kmeans reported alongside.
  G3  clustering wall clock on this matrix.  Gate: label faster than kmeans.
  G4  documented knots — clusters named from an authored syllable.  REPORTED, NOT GATED:
      debug-100 is the deepest hundred species and holds no authored calls, so this reads
      0 in both arms and the question needs a subset chosen to contain them.

Purity is reported for continuity with §22.6's table and is explicitly not a gate here.
"""

from __future__ import annotations

import sys
import time
from collections import Counter

import numpy as np
from sklearn.cluster import KMeans

sys.path.insert(0, "/home/sha5b/Documents/GitHub/Birdy/pipeline/src")

from birdy_pipeline.galaxy import (  # noqa: E402
    PointSet,
    _purity,
    _type_seed_means,
    cluster_plan,
    label_assign,
    label_cluster,
    type_seeds,
)

#: The debug-100 `build --dump-points` matrix of docs/22 §22.6. Rewrite this for a
#: fresh dump; every arm in this file is only comparable to the table while it is fixed.
NPZ = "/tmp/birdy-debug/points-debug100.npz"


def load() -> tuple[np.ndarray, PointSet]:
    d = np.load(NPZ, allow_pickle=True)
    z = d["z"].astype(np.float64)
    pts = PointSet(
        x=d["z28"].astype(np.float64),
        species_id=[str(v) for v in d["species_id"]],
        syllable_id=[str(v) for v in d["syllable_id"]],
        song_id=[str(v) for v in d["song_id"]],
        duration=[float(v) for v in d["duration"]],
        source=[str(v) for v in d["source"]],
    )
    return z, pts


def cluster_names(
    cluster_id: np.ndarray, pts: PointSet, k: int
) -> list[tuple[str, str]]:
    """Each cluster's (speciesId, syllableId) through the shipped vote."""
    out: list[tuple[str, str]] = []
    order = np.argsort(cluster_id, kind="stable")
    bounds = np.searchsorted(cluster_id[order], np.arange(k + 1))
    for c in range(k):
        sel = order[bounds[c] : bounds[c + 1]]
        if sel.size == 0:
            out.append(("", ""))
            continue
        members = [(pts.species_id[i], pts.syllable_id[i], pts.song_id[i]) for i in sel]
        info = label_cluster(members, {}, {})
        out.append((info["speciesId"], info["syllableId"]))
    return out


def unit(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.maximum(n, 1.0e-12)


def type_retrieval(
    z: np.ndarray, centres: np.ndarray, names: list[tuple[str, str]], pts: PointSet
) -> float:
    """Share of labelled points whose nearest centroid carries their own type's name."""
    uz, uc = unit(z), unit(np.asarray(centres, dtype=np.float64))
    own = np.asarray(
        [
            (sp, syl) if syl else None
            for sp, syl in zip(pts.species_id, pts.syllable_id)
        ],
        dtype=object,
    )
    named = np.asarray(names, dtype=object)
    hit = 0
    total = 0
    for lo in range(0, uz.shape[0], 4096):
        hi = min(lo + 4096, uz.shape[0])
        near = (uz[lo:hi] @ uc.T).argmax(axis=1)
        for row, c in zip(range(lo, hi), near):
            if own[row] is None:
                continue
            total += 1
            if tuple(named[c]) == own[row]:
                hit += 1
    return hit / total if total else 0.0


def coverage(names: list[tuple[str, str]], pts: PointSet) -> tuple[float, int, int]:
    types = {(sp, syl) for sp, syl in zip(pts.species_id, pts.syllable_id) if syl}
    named = {n for n in names if n[1]}
    got = len(types & named)
    return got / len(types) if types else 0.0, got, len(types)


def main() -> None:
    z, pts = load()
    type_of = pts.types()
    print(f"matrix: {z.shape[0]} points x {z.shape[1]}-d", flush=True)

    rows = []

    # --- arm A: kmeans exactly as the build runs it -------------------------------
    plan = cluster_plan(pts, z)
    k = plan["k"]
    print(f"kmeans arm: plan {plan}", flush=True)
    t0 = time.time()
    seeded = type_seeds(z, pts, k, seed=0)
    init, n_type_seeds, shed = seeded
    km = KMeans(n_clusters=k, init=init, n_init=1, random_state=0).fit(z)
    t_km = time.time() - t0
    cid_a, cen_a = km.labels_.astype(int), km.cluster_centers_
    print(f"  fitted in {t_km:.1f}s, shed {shed}", flush=True)
    names_a = cluster_names(cid_a, pts, k)
    rows.append(
        (
            "kmeans, as built",
            z.shape[0],
            k,
            round(_purity(cid_a, type_of, k), 4),
            round(coverage(names_a, pts)[0], 4),
            round(type_retrieval(z, cen_a, names_a, pts), 4),
            round(t_km, 1),
        )
    )
    print(rows[-1], flush=True)

    # --- arm B: label assignment ---------------------------------------------------
    t0 = time.time()
    cid_b, cen_b, k_b, report = label_assign(z, pts, seed=0)
    t_lb = time.time() - t0
    print(f"label arm: {report}, fitted in {t_lb:.1f}s", flush=True)
    names_b = cluster_names(cid_b, pts, k_b)
    rows.append(
        (
            "label assignment",
            z.shape[0],
            k_b,
            round(_purity(cid_b, type_of, k_b), 4),
            round(coverage(names_b, pts)[0], 4),
            round(type_retrieval(z, cen_b, names_b, pts), 4),
            round(t_lb, 1),
        )
    )
    print(rows[-1], flush=True)

    print("\n| arm | points | k | purity | type coverage | type retrieval | clustering s |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r[0]} | {r[1]} | {r[2]} | {r[3]:.4f} | {r[4]:.4f} | {r[5]:.4f} | {r[6]} |"
        )

    # seeds/type, for continuity with §22.6's column
    seeds, n_split, owners = _type_seed_means(z, pts)
    n_types = len({o[0] for o in owners})
    print(f"\nseeds/type {len(seeds) / n_types:.3f} ({n_split} of {n_types} split)")

    # G4: documented knots — a syllable id that is not learned (L*) or unlabelled (U*)
    for label, names in (("kmeans", names_a), ("label", names_b)):
        doc = sum(1 for _, syl in names if syl and not syl.startswith(("L", "U")))
        print(f"{label}: {doc} clusters named from an authored syllable")


if __name__ == "__main__":
    main()
