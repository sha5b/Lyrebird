"""
Density clustering, and the one thing it can say that KMeans cannot: *nothing*.

KMeans answers "which of these k groups is this sound in", and it answers it for every
sound, always. Asked about a call the corpus has never heard, it returns the nearest of
the k regardless of how far that is, with no way to signal the difference. For a picture
of a known repertoire that is fine. For a tool whose whole subject is unidentified audio
it is the wrong question, because the interesting answer — "this belongs to none of them"
— is not in its output space.

HDBSCAN answers a different question: where are the dense regions, how many are there,
and which points are in none of them. Three consequences that matter here:

- **k is discovered, not declared.** The number of syllable types in a corpus of field
  recordings is exactly the thing we do not know, and `default_k` was guessing it from
  the inventory — which is why a harvest with no labels collapsed to one cluster per bird.
- **Noise is a category.** A point HDBSCAN refuses to assign is a sound with no dense
  neighbourhood: either genuinely novel, or too rare to call yet. Both are worth seeing,
  and neither had any representation before.
- **Clusters can be anchored.** A dense region containing both documented renders and
  unlabelled field audio is the translation primitive this project has been missing: the
  field audio in it sounds like the documented call, measured, with a share attached.

## Metric

Everything else in the pipeline measures cosine distance. HDBSCAN wants a metric space,
and on unit-normalised vectors Euclidean distance is a monotonic function of cosine
distance — ‖u−v‖² = 2 − 2·cos(u,v) — so ranking by one ranks by the other, and the tree
structure HDBSCAN builds from mutual-reachability distances is identical. Normalising and
using Euclidean therefore changes no cluster boundary and gets the spatial index.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from sklearn.cluster import HDBSCAN

#: Fewest points that can be called a syllable type. Below this a "cluster" is a handful
#: of renders of one clip and naming it would be overfitting the harvest.
DEFAULT_MIN_CLUSTER_SIZE = 25
#: How conservative the density estimate is. Left at min_cluster_size by default, which is
#: HDBSCAN's own recommendation when you have no reason to prefer otherwise.
DEFAULT_MIN_SAMPLES: int | None = None
#: A cluster is called anchored when this much of its labelled membership agrees.
ANCHOR_MAJORITY = 0.6


def _fit(u: np.ndarray, min_cluster_size: int, min_samples: int | None) -> Any:
    """
    Fit HDBSCAN*, on whichever implementation can finish at this corpus's size.

    **This is one algorithm and two minimum-spanning-tree implementations, not a choice
    between two clusterings.** Both build the exact MST of the same mutual-reachability
    graph and both select clusters by excess of mass, so the labels agree up to ties. What
    differs is cost, and at production scale the difference decides whether the map exists.

    `sklearn.cluster.HDBSCAN` runs Prim's algorithm over a dense mutual-reachability graph.
    That is O(n^2) with no parallel path — `_hdbscan_prims` calls `kneighbors` through
    joblib's *sequential* output, which is what a live py-spy dump of a production run
    showed it sitting in. Measured on this corpus's own embedding (32-d unit rows,
    `min_cluster_size=25`): 13.0 s at n=20 000, 62.5 s at 40 000, 422.2 s at 80 000 — about
    n^2.5 in this regime, which extrapolates to roughly **8.4 hours at the shipped 444 213
    points**. A production run was killed at 1 h 40 m having reached about a fifth of it.
    `n_jobs=-1` halves the wall clock (12.6 / 39.8 / 208.9 s) and does not change the
    exponent, because the sequential MST is what dominates.

    The standalone `hdbscan` package has a Boruvka MST, which sklearn does not: tree-
    accelerated and parallel over the core-distance step. Same measurement, same data:
    44.8 s at 80 000 and 265.2 s at 200 000 — about n^2.0, extrapolating to roughly
    **22 minutes** at 444 213. So the fast path is preferred when it is installed, and
    sklearn remains the fallback so a `uv sync` without the optional extra still works on
    the debug store, where either finishes in seconds.

    `core_dist_n_jobs=-1` on the fast path and `n_jobs=-1` on the fallback: the core
    distances are an embarrassingly parallel kNN and leaving them on one core was free
    waste.
    """
    try:
        import hdbscan as hdbscan_pkg
    except ImportError:
        return HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=None if min_samples is None else int(min_samples),
            metric="euclidean",  # on unit rows this ranks identically to cosine; see above
            cluster_selection_method="eom",
            copy=True,
            n_jobs=-1,
        ).fit(u)
    return hdbscan_pkg.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=None if min_samples is None else int(min_samples),
        metric="euclidean",
        cluster_selection_method="eom",
        core_dist_n_jobs=-1,
    ).fit(u)


def _unit_rows(z: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(z, axis=1, keepdims=True)
    return z / np.maximum(norm, 1.0e-12)


@dataclass
class DensityResult:
    """Labels, centroid vectors, and what could not be placed."""

    #: Per point: cluster index, or -1 for a sound in no dense region.
    labels: np.ndarray
    #: (k, dims) — the mean standardised descriptor of each cluster's members.
    centres: np.ndarray
    #: Per point, HDBSCAN's confidence that it belongs where it was put.
    strengths: np.ndarray
    k: int
    noise: int

    @property
    def noise_share(self) -> float:
        return float(self.noise / max(1, len(self.labels)))


def cluster(
    z: np.ndarray,
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
    min_samples: int | None = DEFAULT_MIN_SAMPLES,
) -> DensityResult:
    """Find the dense regions of the standardised descriptor space."""
    u = _unit_rows(np.asarray(z, dtype=np.float64))
    model = _fit(u, int(max(2, min_cluster_size)), min_samples)

    labels = model.labels_.astype(int)
    k = int(labels.max()) + 1 if labels.size and labels.max() >= 0 else 0
    centres = np.zeros((k, z.shape[1]), dtype=np.float64)
    for c in range(k):
        members = z[labels == c]
        if len(members):
            centres[c] = members.mean(axis=0)
    return DensityResult(
        labels=labels,
        centres=centres,
        strengths=np.asarray(model.probabilities_, dtype=np.float64),
        k=k,
        noise=int((labels < 0).sum()),
    )


def anchor(
    labels: np.ndarray,
    species_id: Sequence[str],
    syllable_id: Sequence[str],
    source: Sequence[str],
    k: int,
) -> list[dict[str, Any]]:
    """
    What each dense region can be said to be, and on what evidence.

    This is the step the project did not have. A cluster's *labelled* members are renders
    of documented or fitted syllables and carry an identity; its *unlabelled* members are
    harvested field audio and carry none. Where both land in the same dense region, the
    field audio is acoustically consistent with that syllable — which is a real, measured
    claim, and a much weaker one than "this bird said that", so it is reported with the
    share of the cluster that supports it rather than as a fact.

    Four shapes come out of this, and telling them apart is the whole point:

    - **anchored** — has a documented majority, and unlabelled members that inherit a
      candidate identity from it;
    - **confirmed** — labelled majority with no unlabelled members: nothing new, but it
      says the fitting and the harvest agree;
    - **unknown** — real audio, dense enough to be a type, and nothing documented in it.
      These are the candidates for a new syllable;
    - **mixed** — labelled members that do not agree with each other, so it anchors
      nothing and is a sign k is too coarse here.
    """
    out: list[dict[str, Any]] = []
    for c in range(k):
        members = np.nonzero(labels == c)[0]
        if not len(members):
            out.append({"kind": "empty", "size": 0})
            continue
        named = Counter(
            (species_id[i], syllable_id[i]) for i in members if syllable_id[i]
        )
        unlabelled = sum(1 for i in members if not syllable_id[i])
        field = sum(1 for i in members if source[i] == "field")
        entry: dict[str, Any] = {
            "size": int(len(members)),
            "labelled": int(sum(named.values())),
            "unlabelled": int(unlabelled),
            "field": int(field),
        }
        if not named:
            entry["kind"] = "unknown"
            out.append(entry)
            continue
        (sp, syl), top = named.most_common(1)[0]
        agreement = top / max(1, sum(named.values()))
        entry["candidate"] = {"speciesId": sp, "syllableId": syl}
        entry["agreement"] = round(float(agreement), 4)
        # The share of the *whole* cluster backing the claim, not just of its labelled
        # part — a cluster that is 5 documented renders and 500 unknown syllables agrees
        # with itself perfectly and still supports almost nothing.
        entry["support"] = round(float(top / len(members)), 4)
        if agreement < ANCHOR_MAJORITY:
            entry["kind"] = "mixed"
        elif unlabelled:
            entry["kind"] = "anchored"
        else:
            entry["kind"] = "confirmed"
        out.append(entry)
    return out


def summarise(result: DensityResult, anchors: list[dict[str, Any]]) -> dict[str, Any]:
    """One line per shape, for the build log and the manifest."""
    kinds = Counter(a.get("kind", "empty") for a in anchors)
    inherited = sum(
        a.get("unlabelled", 0) for a in anchors if a.get("kind") == "anchored"
    )
    return {
        "algorithm": "hdbscan",
        "clusters": result.k,
        "noise": result.noise,
        "noiseShare": round(result.noise_share, 4),
        "anchored": kinds.get("anchored", 0),
        "confirmed": kinds.get("confirmed", 0),
        "unknown": kinds.get("unknown", 0),
        "mixed": kinds.get("mixed", 0),
        "pointsGivenACandidate": int(inherited),
        "definition": (
            "anchored: a dense region holding both documented renders and unlabelled "
            "field audio, so the field audio inherits a candidate identity. unknown: "
            "dense, real, and nothing documented in it — a candidate new syllable. "
            "noise: in no dense region at all."
        ),
    }
