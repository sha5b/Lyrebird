"""Descriptors -> 3D projection -> KMeans -> the generated asset set of contract 8.3.

Three projections are available (`--projection`). KMeans and the activation lookup work
on the standardised 28-d descriptors and never touch the 3D positions, so the choice of
projection is free as far as the client's cluster maths is concerned; what it changes is
whether *distance on screen* means anything. `faithfulness` measures exactly that.
"""

from __future__ import annotations

import json
import math
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors
from umap import UMAP

from . import features
from .corpus import Cancelled, Clip

UMAP_N_NEIGHBORS = 15
# 0.25 rather than 0.12: at 0.12 each syllable type packs into a knot a few pixels
# wide and the galaxy reads as empty space (docs/05-embedding-galaxy.md wants a dense
# continuous cloud). Between-cluster separation, which the activation lookup depends
# on, is preserved - see the cluster purity number the CLI prints.
UMAP_MIN_DIST = 0.25
UMAP_METRIC = "cosine"
TEMPERATURE = 0.12
# One cluster per syllable type is the point — a cluster the app can name and cite. The
# cap only exists to stop a pathological corpus from asking for thousands, and it was 64
# when the inventory had 44 types. A learned inventory has an order more (12 fitted types
# per species on top of the authored ones), and capping there is not a cheaper galaxy but
# a wrong one: types get merged, and the documented calls lose the clusters that carry
# their function and citation. On the merged inventory the cap cost 13 % purity against
# 176 requested types. Nothing downstream is quadratic in it — the shader holds one float
# per cluster and the labels cull by collision.
#
# **Raised from 256 after it bound a second time, silently, and cost the cuckoo both of
# its calls.** A 264-type learned inventory asks for 308 clusters plus room for the field
# points; at 256 the shipped build named 180 types and dropped 128, and `cuculus_canorus`
# was the species that lost *every* authored syllable. Nothing in the app can report that:
# `clusterIndexFor` correctly returns -1 rather than guessing, so the bird simply sang
# with no node to light, no trajectory to draw and no label to show. The cap is now high
# enough that the corpus decides the number, and `cluster_plan` says out loud when it is
# the cap talking instead.
K_CAP = 1024

PROJECTIONS = ("umap", "pca", "cmds")
DEFAULT_PROJECTION = "cmds"  # most distance-faithful; see README "Galaxy shape"
FAITHFULNESS_PAIRS = 200_000
KNN_AGREEMENT_K = 10
# above this many points the full n x n cMDS matrix gets expensive in memory
# (n^2 * 8 bytes twice over), so fall back to landmark MDS
CMDS_FULL_MAX = 6000
CMDS_LANDMARKS = 800

# Per-point features shipped to the browser so a point can react on its own rather than
# inheriting its cluster's activation. The full 28-d matrix would be 4*28*n bytes; the
# top-8 principal components keep most of the between-type structure at 2/7 the size,
# and the number that says how much is kept goes into the manifest.
POINT_FEATURE_DIMS = 8


@dataclass
class PointSet:
    """Descriptors plus the parallel metadata that lands in points.json.

    The galaxy is built from this rather than from `Clip`s so that a source which has
    already thrown its audio away — the harvester, which never holds more than one
    recording in memory — can be embedded on equal terms with a rendered corpus.
    """

    x: np.ndarray  # (n, features.DIM) raw descriptors
    species_id: list[str]
    syllable_id: list[str]
    song_id: list[str]
    duration: list[float]
    source: list[str]

    def __len__(self) -> int:
        return int(self.x.shape[0])

    def types(self) -> list[tuple[str, str]]:
        """(speciesId, syllableId|song:<id>) per point — the label purity is measured on."""
        return [
            (sp, syl or f"song:{song}")
            for sp, syl, song in zip(self.species_id, self.syllable_id, self.song_id)
        ]

    @staticmethod
    def concat(parts: Sequence["PointSet"]) -> "PointSet":
        kept = [p for p in parts if len(p)]
        if not kept:
            raise RuntimeError("nothing to embed: every source was empty")
        return PointSet(
            x=np.concatenate([p.x for p in kept], axis=0),
            species_id=[v for p in kept for v in p.species_id],
            syllable_id=[v for p in kept for v in p.syllable_id],
            song_id=[v for p in kept for v in p.song_id],
            duration=[v for p in kept for v in p.duration],
            source=[v for p in kept for v in p.source],
        )


@dataclass
class GalaxyStats:
    n_points: int
    n_dropped: int
    k: int
    cluster_counts: list[int]
    duration_range: tuple[float, float]
    position_extent: float
    labels: list[str]
    purity: float  # share of points that carry their cluster's majority type
    spread: float  # mean distance from the galaxy centre, in units of max|coord|
    projection: str
    faithfulness: dict[str, Any]  # 28-d cosine vs 3D euclidean correlation
    knn_agreement: float  # share of 3D k-NN sharing a point's type
    point_feature_variance: float  # share of variance the shipped per-point features keep


def descriptors(
    clips: Sequence[Clip],
    verbose: bool = True,
    should_stop: Callable[[], bool] | None = None,
) -> PointSet:
    """28-d descriptor per clip; clips with no voiced frame are dropped (8.2)."""
    rows: list[np.ndarray] = []
    kept: list[Clip] = []
    for i, clip in enumerate(clips):
        if should_stop and i % 64 == 0 and should_stop():
            raise Cancelled("stopped while extracting descriptors")
        d = features.descriptor(clip.audio, clip.sample_rate)
        if d is None or not np.all(np.isfinite(d)):
            continue
        rows.append(d)
        kept.append(clip)
        if verbose and (i + 1) % 200 == 0:
            print(f"  descriptors {i + 1}/{len(clips)}", file=sys.stderr)
    if not rows:
        raise RuntimeError("no clip produced a descriptor")
    return PointSet(
        x=np.stack(rows),
        species_id=[c.species_id for c in kept],
        syllable_id=[c.syllable_id for c in kept],
        song_id=[c.song_id for c in kept],
        duration=[c.duration for c in kept],
        source=[c.source for c in kept],
    )


# --- projections ------------------------------------------------------------------


def canonical_signs(pos: np.ndarray) -> np.ndarray:
    """Fix the arbitrary sign of each axis so a rebuild cannot mirror the galaxy.

    Eigenvectors (cMDS, PCA) are only defined up to sign, and which one LAPACK returns
    can differ between BLAS builds. Flipping each axis so its largest-magnitude
    coordinate is positive makes the output reproducible across environments.
    """
    out = pos.copy()
    for c in range(out.shape[1]):
        col = out[:, c]
        if col[np.argmax(np.abs(col))] < 0:
            out[:, c] = -col
    return out


def _unit_rows(z: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(z, axis=1, keepdims=True)
    return z / np.maximum(norm, 1.0e-12)


def cosine_distance_matrix(z: np.ndarray) -> np.ndarray:
    """1 - cosine similarity, the metric UMAP/KMeans/the client all use."""
    u = _unit_rows(z)
    d = 1.0 - u @ u.T
    np.fill_diagonal(d, 0.0)
    return np.maximum(d, 0.0)


def _classical_mds(d2: np.ndarray, k: int = 3) -> tuple[np.ndarray, dict[str, Any]]:
    """Torgerson/PCoA on a squared-distance matrix: double-centre, top-k eigenpairs.

    Cosine distance is not Euclidean, so the double-centred matrix has negative
    eigenvalues; `negativeEigenvalueMass` says how much of the spectrum they hold,
    which is the honest measure of how much the 3D picture has to invent.
    """
    row = d2.mean(axis=0)
    b = -0.5 * (d2 - row[None, :] - row[:, None] + d2.mean())
    w, v = np.linalg.eigh(b)  # ascending
    order = np.argsort(w)[::-1]
    w = w[order]
    v = v[:, order]
    top = np.maximum(w[:k], 0.0)
    pos = canonical_signs(v[:, :k] * np.sqrt(top))
    positive = float(w[w > 0].sum())
    info = {
        "eigenvalues": [float(x) for x in w[:k]],
        "varianceRatio": [float(x / positive) if positive > 0 else 0.0 for x in top],
        "negativeEigenvalueMass": float(abs(w[w < 0].sum()) / (positive + 1e-12)),
    }
    return pos, info


def _landmark_mds(
    z: np.ndarray, k: int = 3, n_landmarks: int = CMDS_LANDMARKS, seed: int = 0
) -> tuple[np.ndarray, dict[str, Any]]:
    """Silva-Tenenbaum landmark MDS, for corpora too big for the full matrix."""
    rng = np.random.default_rng(seed)
    n = z.shape[0]
    m = min(n_landmarks, n)
    idx = rng.choice(n, size=m, replace=False)
    u = _unit_rows(z)
    d_lm = np.maximum(1.0 - u[idx] @ u[idx].T, 0.0)
    np.fill_diagonal(d_lm, 0.0)
    pos_lm, info = _classical_mds(d_lm**2, k)

    # embed the rest: x = -0.5 * L_pinv @ (d_x^2 - mean_landmark_sq)
    lam = np.maximum(np.asarray(info["eigenvalues"][:k], dtype=np.float64), 1.0e-12)
    l_pinv = (pos_lm / lam).T  # (k, m)
    d_all = np.maximum(1.0 - u @ u[idx].T, 0.0) ** 2  # (n, m)
    mean_sq = d_all.mean(axis=0)
    pos = -0.5 * (d_all - mean_sq[None, :]) @ l_pinv.T
    pos[idx] = pos_lm
    # The three arrays a later extension needs to place a point in this same frame
    # without disturbing anything already in it. See grow.py.
    info = {
        **info,
        "landmarks": m,
        "basis": {
            "landmarks": u[idx],
            "lPinv": l_pinv,
            "meanSq": mean_sq,
        },
    }
    return pos, info


def project(
    z: np.ndarray,
    method: str,
    seed: int = 0,
    min_dist: float | None = None,
    verbose: bool = True,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Standardised 28-d descriptors -> raw (unnormalised) 3D positions + info."""
    n = z.shape[0]
    if method == "umap":
        n_neighbors = min(UMAP_N_NEIGHBORS, max(2, n - 1))
        umap_min_dist = UMAP_MIN_DIST if min_dist is None else float(min_dist)
        if verbose:
            print(
                f"projection umap: n_neighbors={n_neighbors}, min_dist={umap_min_dist}, "
                f"metric={UMAP_METRIC}, seed={seed}",
                file=sys.stderr,
            )
        reducer = UMAP(
            n_components=3,
            n_neighbors=n_neighbors,
            min_dist=umap_min_dist,
            metric=UMAP_METRIC,
            random_state=seed,
        )
        pos = np.asarray(reducer.fit_transform(z), dtype=np.float64)
        return pos, {
            "nNeighbors": n_neighbors,
            "minDist": umap_min_dist,
            "metric": UMAP_METRIC,
        }

    if method == "pca":
        if verbose:
            print("projection pca: first 3 principal components", file=sys.stderr)
        pca = PCA(n_components=3, random_state=seed)
        pos = canonical_signs(np.asarray(pca.fit_transform(z), dtype=np.float64))
        return pos, {
            "varianceRatio": [float(v) for v in pca.explained_variance_ratio_],
            "varianceRatioTotal": float(pca.explained_variance_ratio_.sum()),
        }

    if method == "cmds":
        if n <= CMDS_FULL_MAX:
            if verbose:
                print(
                    f"projection cmds: classical MDS on the {n}x{n} cosine distance "
                    "matrix (full eigendecomposition)",
                    file=sys.stderr,
                )
            d2_full = cosine_distance_matrix(z) ** 2
            pos, info = _classical_mds(d2_full)
            info["mode"] = "full"
            # The same out-of-sample frame the landmark path emits, with every point
            # acting as a landmark. Without it a corpus under the full-matrix limit
            # could be built but never grown, which is the wrong way round — a small
            # corpus is exactly the one you expect to add to.
            lam_full = np.maximum(
                np.asarray(info["eigenvalues"][:3], dtype=np.float64), 1.0e-12
            )
            info["basis"] = {
                "landmarks": _unit_rows(z),
                "lPinv": (pos / lam_full).T,
                "meanSq": d2_full.mean(axis=0),
            }
        else:
            if verbose:
                print(
                    f"projection cmds: landmark MDS, {CMDS_LANDMARKS} landmarks "
                    f"(n={n} exceeds the {CMDS_FULL_MAX}-point full-matrix limit)",
                    file=sys.stderr,
                )
            pos, info = _landmark_mds(z, seed=seed)
            info["mode"] = "landmark"
        info["metric"] = "cosine"
        return pos, info

    raise ValueError(f"unknown projection {method!r}, expected one of {PROJECTIONS}")


#: Coordinate quantile the scaling is fitted to, before the tail is clamped in.
POSITION_QUANTILE = 99.5
#: How far cluster centres are pushed apart, relative to the knots' own size.
DEFAULT_SEPARATION = 1.6
#: Where the tail compressor starts. Named because an extension has to reuse it.
SOFT_LIMIT_KNEE = 0.86


def separate_clusters(
    pos: np.ndarray, cluster_id: np.ndarray, k: int, factor: float
) -> tuple[np.ndarray, np.ndarray]:
    """Push the knots apart without changing their shape, so the cloud has gaps in it.

    Every point moves by the same vector as the rest of its cluster — its centre times
    `factor - 1` — so within a knot nothing changes at all, and between knots the gaps
    grow. After renormalisation the visible effect is that each knot is smaller relative
    to the space it sits in, which is the difference between a cloud you can see the
    structure of and one soft ball.

    It is a stated distortion, not a hidden one: between-cluster distances are scaled up
    against within-cluster distances, so the ratio of the two no longer matches the 28-d
    space. The projection comparison in the log is measured *after* this runs, so the
    faithfulness figure the manifest reports is the one that ships.
    """
    if factor <= 1.0:
        return pos, np.zeros((k, pos.shape[1]))
    centres = np.zeros((k, pos.shape[1]))
    counts = np.zeros(k)
    for i, c in enumerate(cluster_id):
        if 0 <= c < k:
            centres[c] += pos[i]
            counts[c] += 1
    centres /= np.maximum(counts, 1)[:, None]
    per_cluster = centres * (factor - 1.0)
    # A point in no cluster is not pushed anywhere. `np.clip` alone would hand every
    # unassigned point cluster 0's shift and drag the whole of the noise into one knot.
    shift = np.where(
        (cluster_id >= 0)[:, None],
        per_cluster[np.clip(cluster_id, 0, k - 1)],
        0.0,
    )
    return pos + shift, per_cluster




def _soft_limit(out: np.ndarray, knee: float = SOFT_LIMIT_KNEE) -> np.ndarray:
    """Compress the tail into the box instead of clipping it against the wall.

    Clipping is what the contract's ``max|coord| == 1`` used to be enforced with, and it
    destroys the position of everything it touches. Measured on the shipped build: 471
    points sat exactly on a face, and they were not scattered — cluster 19 had *all 64*
    of its points pinned to one plane and cluster 16 had 55 of 64, so two whole knots were
    drawn as flat smears against the boundary, at coordinates the projection never
    produced. A point that has been clipped is not merely imprecise, it is somewhere else.

    Below the knee nothing moves at all, so the 99 % of the corpus that was already inside
    the box is untouched and the faithfulness figure is unaffected. Above it the axis is
    squashed through a tanh scaled so the furthest point lands exactly on 1: monotonic, so
    the ordering of the tail survives, and injective, so no two points are merged onto the
    same face. The outliers are still the least trustworthy positions in the picture —
    they are just no longer lies about which side of each other they are on.
    """
    out = out.copy()
    for axis in range(out.shape[1]):
        v = out[:, axis]
        mag = np.abs(v)
        far = mag > knee
        if not far.any():
            continue
        peak = float(mag.max())
        if peak <= knee:
            continue
        span = 1.0 - knee
        # tanh maps [0, inf) -> [0, 1); dividing by its value at the furthest point makes
        # that point land on exactly 1 rather than merely approaching it
        top = np.tanh((peak - knee) / span)
        excess = np.tanh((mag[far] - knee) / span) / max(top, 1.0e-9)
        v[far] = np.sign(v[far]) * (knee + span * excess)
    return out


def normalise_positions(
    pos: np.ndarray, per_axis: bool = True
) -> tuple[np.ndarray, float, dict[str, np.ndarray | float]]:
    """Centre, scale the *bulk* to fill the box, clamp the tail to it (8.3).

    `per_axis` scales each of the three axes by its own quantile rather than by one
    global number. A projection does not spread its variance evenly — cMDS puts 31 % on
    the first axis and 7 % on the third — so one global scale fills the box along the
    widest axis and leaves the other two occupying a fraction of it. The cloud then reads
    as a flat lens whichever way you orbit it, and the third axis, which is real
    structure, is invisible.

    It is an anisotropic scaling, so it stretches distances by up to the ratio of the
    axes' spreads. Like the separation above, it is applied before the faithfulness
    measurement, so the correlation the manifest reports is the one that ships.

    Scaling by the single furthest point is what made the cloud read as one soft ball:
    a handful of strays set the radius, everything else was divided by their distance,
    and 99 % of the corpus ended up inside a fraction of the box with its structure
    squeezed out of visibility. Fitting to the 99.5th percentile instead expands the
    bulk to fill the space, and the few points beyond it are clamped to the surface —
    they are outliers in the projection, and their exact radius is the least
    trustworthy number in it.

    The contract's invariant (`max|coord| == 1`) still holds, which is what `verify`
    checks and what the camera framing assumes.
    """
    centre = 0.5 * (pos.max(axis=0) + pos.min(axis=0))
    out = pos - centre
    extent = float(np.max(np.abs(out)))
    if per_axis:
        scale = np.percentile(np.abs(out), POSITION_QUANTILE, axis=0)
    else:
        scale = np.full(out.shape[1], np.percentile(np.abs(out), POSITION_QUANTILE))
    scale = np.where(scale > 0.0, scale, max(extent, 1.0e-9))
    scaled = out / scale
    # The three numbers a later extension has to reuse rather than re-fit: without them
    # every point already drawn would move the moment anything was added. See grow.py.
    frame = {
        "centre": centre,
        "scale": scale,
        "knee": SOFT_LIMIT_KNEE,
        "peak": np.abs(scaled).max(axis=0),
    }
    return _soft_limit(scaled), extent, frame


# --- how meaningful are the distances? --------------------------------------------


def _ranks(x: np.ndarray) -> np.ndarray:
    """Ordinal ranks. Distances are continuous floats, so ties are negligible."""
    order = np.argsort(x, kind="stable")
    r = np.empty(x.shape[0], dtype=np.float64)
    r[order] = np.arange(x.shape[0], dtype=np.float64)
    return r


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / denom) if denom > 0 else 0.0


def faithfulness(
    z: np.ndarray, pos: np.ndarray, seed: int = 0, n_pairs: int = FAITHFULNESS_PAIRS
) -> dict[str, Any]:
    """Correlate 28-d cosine distance with 3D Euclidean distance over random pairs.

    This is the number that answers "do distances in the galaxy mean anything": 1.0
    would be a perfectly distance-faithful picture, ~0 a picture where only local
    neighbourhoods survive.
    """
    n = z.shape[0]
    rng = np.random.default_rng([seed, 0xFA1F])
    i = rng.integers(0, n, size=n_pairs)
    j = rng.integers(0, n, size=n_pairs)
    keep = i != j
    i, j = i[keep], j[keep]

    u = _unit_rows(z)
    d_hi = np.maximum(1.0 - np.einsum("ij,ij->i", u[i], u[j]), 0.0)
    d_lo = np.linalg.norm(pos[i] - pos[j], axis=1)
    return {
        "pearson": round(_pearson(d_hi, d_lo), 4),
        "spearman": round(_pearson(_ranks(d_hi), _ranks(d_lo)), 4),
        "pairs": int(i.size),
    }


def torn_clusters(pos: np.ndarray, cluster_id: np.ndarray, k: int) -> dict[str, Any]:
    """How many clusters the projection draws in two places at once.

    **The failure this catches is worse than an unfaithful distance and it is invisible in
    every other metric on the page.** A projection is free to rearrange the space, but the
    app draws one node per cluster: a label at the centroid, a trajectory between
    centroids, a wave from the centroid. All of that assumes a cluster is *somewhere*. If
    the embedding puts half of a cluster's points on one side of the galaxy and half on
    the other, the centroid lands in the empty space between them, the tag sits on
    nothing, and one sound lights two knots a box-width apart.

    Measured by splitting each cluster's own points in two in 3D and comparing the gap
    between the halves against their own spread. Splitting a single blob always yields a
    ratio near 2, so 2 is the null and only larger values mean anything. Measured on the
    same corpus: UMAP tore 95 of 166 clusters past 5 and 65 past 8, with gaps up to 1.2 of
    the box; cMDS tore 3 and 2, worst gap 0.49, median ratio 2.06.

    Purity does not see this — it is computed on cluster membership, which the projection
    never touches. Faithfulness does not see it either: it correlates *random pairs*, and
    a handful of torn clusters barely move a 200k-pair correlation.
    """
    ratios: list[float] = []
    worst_gap = 0.0
    for c in range(k):
        members = pos[cluster_id == c]
        if len(members) < 12:
            continue
        km = KMeans(n_clusters=2, n_init=4, random_state=0).fit(members)
        a = members[km.labels_ == 0]
        b = members[km.labels_ == 1]
        if len(a) < 3 or len(b) < 3:
            continue
        gap = float(np.linalg.norm(a.mean(axis=0) - b.mean(axis=0)))
        spread = 0.5 * (
            float(np.linalg.norm(a - a.mean(axis=0), axis=1).mean())
            + float(np.linalg.norm(b - b.mean(axis=0), axis=1).mean())
        )
        ratios.append(gap / max(spread, 1.0e-9))
        worst_gap = max(worst_gap, gap)
    if not ratios:
        return {"measured": 0, "torn": 0, "severe": 0, "median": 0.0, "worstGap": 0.0}
    r = np.asarray(ratios)
    return {
        "measured": int(r.size),
        "torn": int((r > 5).sum()),
        "severe": int((r > 8).sum()),
        "median": round(float(np.median(r)), 3),
        "worstGap": round(worst_gap, 3),
    }


def knn_label_agreement(
    pos: np.ndarray, labels: Sequence[Any], k: int = KNN_AGREEMENT_K
) -> float:
    """Share of each point's k nearest 3D neighbours that share its type.

    How *tidy* the picture looks, as opposed to how faithful its distances are - the
    two pull in opposite directions, which is the trade-off worth knowing about.
    """
    n = pos.shape[0]
    k_eff = min(k, n - 1)
    if k_eff < 1:
        return 1.0
    nn = NearestNeighbors(n_neighbors=k_eff + 1).fit(pos)
    _, idx = nn.kneighbors(pos)
    lab = np.asarray([hash(x) for x in labels])
    same = lab[idx[:, 1:]] == lab[:, None]
    return float(same.mean())


def _purity(cluster_id: np.ndarray, types: Sequence[Any], k: int) -> float:
    # Measured over assigned points. A density clustering leaves some of the corpus in no
    # cluster at all, and counting those as impure would score honesty as failure.
    """Share of points carrying their cluster's majority type."""
    majority = 0
    for c in range(k):
        members = [types[i] for i in np.nonzero(cluster_id == c)[0]]
        if members:
            majority += Counter(members).most_common(1)[0][1]
    return majority / len(types) if len(types) else 0.0


def _print_projection_table(results: dict[str, dict[str, Any]], chosen: str) -> None:
    print("", file=sys.stderr)
    print(
        "  projection   pearson  spearman   purity  knn10   meanR    torn   notes",
        file=sys.stderr,
    )
    for method, r in results.items():
        note = ""
        info = r["info"]
        if "varianceRatio" in info:
            vr = info["varianceRatio"]
            note = "variance " + "/".join(f"{v * 100:.0f}%" for v in vr[:3])
            if info.get("negativeEigenvalueMass") is not None:
                note += f", neg mass {info['negativeEigenvalueMass'] * 100:.0f}%"
        elif "minDist" in info:
            note = f"min_dist {info['minDist']}"
        mark = " <- shipped" if method == chosen else ""
        f = r["faithfulness"]
        t = r["tearing"]
        print(
            f"  {method:11} {f['pearson']:8.3f} {f['spearman']:9.3f} "
            f"{r['purity'] * 100:7.1f}% {r['knnAgreement'] * 100:5.1f}% "
            f"{r['meanRadius']:7.3f} {t['torn']:4d}/{t['measured']:<4d} {note}{mark}",
            file=sys.stderr,
        )
    print(
        "  pearson/spearman = 28-d cosine distance vs 3D euclidean distance over "
        f"{next(iter(results.values()))['faithfulness']['pairs']} random pairs",
        file=sys.stderr,
    )
    print("", file=sys.stderr)


def default_k(points: PointSet) -> int:
    """
    How many clusters to fit: one per known syllable type, or — for a corpus that has no
    syllable labels at all — a count scaled to the size of the corpus.

    **The fallback used to be one cluster per species, and that is never a defensible
    number of acoustic clusters.** Harvested field points carry no ``syllable_id``, so a
    build from the harvest alone found no types and fell back to counting birds: twenty
    thousand points into eleven clusters, each one about eighteen hundred points holding
    every species in the corpus. Measured on that build, cluster purity was 0.056 and
    k-NN agreement 0.19 — the clusters carried essentially no information, every one of
    them lit for every sound, and because none of them mapped to a documented syllable
    the galaxy drew no connections at all. It looked like the app had broken; what had
    happened is that the corpus was asked how many kinds of sound it contained and
    answered "twelve, one per bird".

    sqrt(n / 2) is the standard rule of thumb for an unknown cluster count and it is
    honest here in a way the species count is not: it makes no claim about what the
    groups *are*, only that a corpus of twenty thousand syllables holds more than eleven
    kinds of sound. For that corpus it gives 100, in the same range as the 176 the mixed
    build fits from real labels.
    """
    return cluster_plan(points)["k"]


def cluster_plan(points: PointSet) -> dict[str, Any]:
    """`default_k` with its reasoning attached, so a build can report what it asked for.

    **One per type was only ever half the count.** Harvested points carry no
    ``syllable_id``, and they are 40 % of the shipped corpus — they need clusters as much
    as the rendered types do, and they take them first, because a field recording is
    further from every synthetic render than the renders are from each other. Asking for
    exactly ``len(types)`` therefore hands a large share of the clusters to field audio and
    leaves the named types to share what is left: the 256-cluster build gave 76 clusters to
    field-only knots, so 180 remained for 308 types and 128 types ended up with no cluster
    carrying their name. That is invisible in purity, which only scores the points that
    *do* have a cluster, and invisible in the app, which cannot distinguish "this call has
    no node" from "this call is quiet".

    So the count is the types plus an allowance for the points that have no type, using the
    same sqrt(n/2) rule this function already trusted for a corpus with no labels at all.
    """
    types = {
        (sp, syl) for sp, syl in zip(points.species_id, points.syllable_id) if syl
    }
    unlabelled = sum(1 for syl in points.syllable_id if not syl)
    allowance = int(math.sqrt(unlabelled / 2)) if unlabelled else 0
    wanted = len(types) + allowance if types else int(
        math.sqrt(max(1, len(points.species_id)) / 2)
    )
    k = max(2, min(K_CAP, wanted))
    return {
        "k": k,
        "types": len(types),
        "unlabelledPoints": unlabelled,
        "allowance": allowance,
        "wanted": wanted,
        "capped": wanted > K_CAP,
        "cap": K_CAP,
    }


def type_seeds(
    z: np.ndarray, points: PointSet, k: int, seed: int = 0
) -> tuple[np.ndarray, int] | None:
    """Initial centroids: one at the centre of every named type, the rest found freely.

    **KMeans++ picks its seeds by distance, and distance in this space is dominated by
    "was this recorded or synthesised".** So it spends its seeds spreading across that gap
    and two acoustically similar types of the same bird — a rendered `oo` and a fitted
    `L02`, both low held cuckoo tones — start life sharing one seed and finish sharing one
    cluster. Whichever loses the majority vote loses its name, its function and its
    citation, and in the app it loses the ability to light, label or draw a trajectory at
    all. Raising `k` alone does not fix that: it hands the extra clusters to whatever is
    furthest away, which is more field audio, not the type that was crowded out.

    Seeding each type at its own centre states the thing the design already claims — that a
    type is what a cluster is *for*. Lloyd's algorithm still moves every centroid and still
    decides membership, so nothing is forced: a type whose renders genuinely sit inside
    another type's cloud will still be absorbed, and `typeCoverage` will still say so. What
    changes is that a type is no longer denied a cluster by an accident of initialisation.

    Returns the seed matrix and how many of its rows are type means, or None when the
    corpus has no types or has more of them than `k` can hold.
    """
    labelled: dict[tuple[str, str], list[int]] = {}
    unlabelled: list[int] = []
    for i, (sp, syl) in enumerate(zip(points.species_id, points.syllable_id)):
        if syl:
            labelled.setdefault((sp, syl), []).append(i)
        else:
            unlabelled.append(i)
    if not labelled or len(labelled) > k:
        return None

    means = np.stack(
        [z[idx].mean(axis=0) for _, idx in sorted(labelled.items())]
    )
    extra = k - len(means)
    if extra <= 0:
        return means[:k], len(means[:k])
    # The remaining seeds belong to the points that have no type — overwhelmingly field
    # audio — and KMeans++ over just those is the right way to place them, because there
    # the "recorded or synthesised" axis it keys on is no longer a distraction.
    pool = z[unlabelled] if len(unlabelled) >= extra else z
    rest = KMeans(n_clusters=extra, n_init=3, random_state=seed).fit(pool).cluster_centers_
    return np.concatenate([means, rest]), len(means)


def point_features(
    z: np.ndarray, centroid_vectors: np.ndarray, dims: int = POINT_FEATURE_DIMS
) -> tuple[np.ndarray, np.ndarray, float]:
    """Compress the standardised descriptors to `dims` unit vectors, for the renderer.

    The browser matches live audio against the 28-d centroid vectors, as the contract
    requires; that match is what the readout reports. This is a second, cheaper space
    used only to decide *how brightly each individual point* responds, so that a cluster
    lights up from the inside out instead of as one flat blob. Cosine is preserved
    approximately, which is all a brightness needs — the returned variance share says
    how approximately.
    """
    mean = z.mean(axis=0)
    k = min(dims, z.shape[1], max(1, z.shape[0] - 1))
    pca = PCA(n_components=k, random_state=0).fit(z - mean)
    kept = float(pca.explained_variance_ratio_.sum())

    # The sign of a principal axis is arbitrary. It is resolved once, on the points, and
    # the same flip is then applied to the centroids — resolving it per matrix would put
    # the two sets in mirrored spaces and every similarity would be wrong.
    lo = pca.transform(z - mean)
    signs = np.array(
        [-1.0 if lo[np.argmax(np.abs(lo[:, c])), c] < 0 else 1.0 for c in range(k)]
    )

    def project(rows: np.ndarray) -> np.ndarray:
        out = np.zeros((rows.shape[0], dims), dtype=np.float64)
        out[:, :k] = pca.transform(rows - mean) * signs
        norm = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.maximum(norm, 1.0e-12)

    return project(z), project(centroid_vectors), kept


# What a call *does*, which is the only kind of meaning this project claims. The classes
# are matched against the documented function text in `data/inventory.json`, in this
# order, because several functions mention more than one ("mate attraction /
# countersinging" is courtship before it is territorial). The table ships in the manifest
# so the grouping can be audited rather than taken on trust, and `structural` is a real
# answer: a song element with no referential meaning is not an unclassified call.
FUNCTION_CLASSES: list[tuple[str, tuple[str, ...]]] = [
    ("alarm", ("hawk", "predator", "alarm", "mobbing", "escape", "flee", "vigilance",
               "attack", "danger", "scan", "agitation", "threat", "cover", "snake")),
    ("recruitment", ("recruitment", "approach the caller", "receivers approach")),
    ("courtship", ("courtship", "mate attraction", "pair contact")),
    ("territorial", ("territor", "advertis", "countersinging")),
    ("contact", ("contact", "cohesion", "flock")),
    ("structural", ("song element", "song onset", "song-type", "song introduction",
                    "transition", "phrase ending", "flourish", "trill element",
                    "percussive", "opening note", "terminal note", "song syntax",
                    "song bout", "motif", "note 1", "note 2")),
]
UNCLASSIFIED = "unclassified"


def function_class(text: str) -> str:
    """Behavioural class of a documented function, or `unclassified` when it says nothing."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return UNCLASSIFIED
    for name, keywords in FUNCTION_CLASSES:
        if any(word in lowered for word in keywords):
            return name
    return UNCLASSIFIED


def _inventory_index(inventory: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    """(speciesId, syllableId, songId) -> label/function/confidence/refs."""
    idx: dict[tuple[str, str, str], dict[str, Any]] = {}
    for sp in inventory.get("species", []):
        common = sp.get("common", sp["id"])
        for syl in sp.get("syllables", []):
            idx[(sp["id"], syl["id"], "")] = {
                "label": f"{common} - {syl.get('label', syl['id'])}",
                "function": syl.get("function", ""),
                "confidence": syl.get("confidence", ""),
                "refs": list(syl.get("refs", [])),
            }
        for song in sp.get("songs", []):
            idx[(sp["id"], "", song["id"])] = {
                "label": f"{common} - {song.get('label', song['id'])}"
                + (f" ({song['gloss']})" if song.get("gloss") else ""),
                "function": song.get("function", ""),
                "confidence": song.get("confidence", ""),
                "refs": list(song.get("refs", [])),
            }
    return idx


def label_cluster(
    members: Sequence[tuple[str, str, str]],
    index: dict[tuple[str, str, str], dict[str, Any]],
    common_names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Majority syllable wins; fall back to majority song, then to the raw label.

    `members` are (speciesId, syllableId, songId) triples.
    """
    keys = Counter(
        (sp, syl, song if not syl else "") for sp, syl, song in members
    )
    syllable_keys = Counter({k: v for k, v in keys.items() if k[1]})
    key, _ = (syllable_keys or keys).most_common(1)[0]
    meta = index.get(key)
    if meta is None:
        # No inventory entry means no citation and no documented function: a cluster of
        # field recordings we can name the species of and nothing more. Saying so with
        # `unlabelled` keeps contract 8.5 honest instead of letting the interface's
        # default ("invented") imply we made the function up.
        common = (common_names or {}).get(key[0], key[0])
        meta = {
            "label": f"{common} - unlabelled field cluster",
            "function": "",
            "confidence": "unlabelled",
            "refs": [],
        }
    return {
        "label": meta["label"],
        "speciesId": key[0],
        "syllableId": key[1],
        "function": meta["function"],
        "confidence": meta["confidence"],
        "refs": meta["refs"],
    }


def build_galaxy(
    source: Sequence[Clip] | PointSet,
    inventory: dict[str, Any],
    out_dir: Path,
    inventory_path: Path,
    seed: int = 0,
    k: int | None = None,
    clustering: str = "kmeans",
    min_cluster_size: int = 25,
    min_dist: float | None = None,
    projection: str = DEFAULT_PROJECTION,
    compare_projections: bool = True,
    separation: float = DEFAULT_SEPARATION,
    build_info: dict[str, Any] | None = None,
    verbose: bool = True,
) -> GalaxyStats:
    # The projection (and `min_dist` within UMAP) is purely about the picture: KMeans
    # and the activation vectors live in the standardised 28-d feature space, never in
    # these 3D positions.
    if projection not in PROJECTIONS:
        raise ValueError(f"unknown projection {projection!r}, expected {PROJECTIONS}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(source, PointSet):
        kept = source
        n_dropped = 0
    else:
        if verbose:
            print(f"extracting descriptors for {len(source)} clips", file=sys.stderr)
        kept = descriptors(source, verbose=verbose)
        n_dropped = len(source) - len(kept)

    x = kept.x
    mean = x.mean(axis=0)
    std = x.std(axis=0)  # population std, floored at lookup time
    z = features.standardise(x, mean, std)
    if not np.all(np.isfinite(z)):
        raise RuntimeError("standardised descriptors contain NaN/inf")

    # The clustering is what the client's activation lookup uses, and it runs on the
    # standardised descriptors, so it is identical for every projection.
    density_summary: dict[str, Any] | None = None
    anchors: list[dict[str, Any]] | None = None
    plan_report: dict[str, Any] | None = None
    if clustering == "hdbscan":
        from . import density as density_mod

        if verbose:
            print(
                f"hdbscan: min_cluster_size={min_cluster_size} on standardised descriptors",
                file=sys.stderr,
            )
        found = density_mod.cluster(z, min_cluster_size=min_cluster_size)
        if found.k < 2:
            raise RuntimeError(
                f"hdbscan found {found.k} clusters at min_cluster_size={min_cluster_size}; "
                "lower it, or harvest more audio"
            )
        cluster_id = found.labels
        centre_vectors = found.centres
        k_final = found.k
        anchors = density_mod.anchor(
            cluster_id, kept.species_id, kept.syllable_id, kept.source, k_final
        )
        density_summary = density_mod.summarise(found, anchors)
        if verbose:
            print(
                f"  {k_final} clusters, {found.noise} points in none of them "
                f"({found.noise_share * 100:.1f} %); anchored {density_summary['anchored']}, "
                f"unknown {density_summary['unknown']}",
                file=sys.stderr,
            )
    else:
        plan = cluster_plan(kept)
        plan_report = plan
        k_final = int(k or plan["k"])
        k_final = max(2, min(k_final, len(kept)))
        if verbose:
            print(f"kmeans: k={k_final} on standardised descriptors", file=sys.stderr)
            print(
                f"  {plan['types']} named types + {plan['allowance']} for "
                f"{plan['unlabelledPoints']} points with no type = {plan['wanted']} wanted",
                file=sys.stderr,
            )
            if plan["capped"]:
                # The failure mode this replaces was silent, and silence is what made it
                # expensive: a bird lost every cluster carrying its name and the only
                # symptom was that it sang and nothing lit up.
                print(
                    f"  WARNING: clamped to the cap of {plan['cap']}; "
                    f"{plan['wanted'] - plan['cap']} types will share clusters and lose "
                    "the name, function and citation that go with having one",
                    file=sys.stderr,
                )
        seeded = type_seeds(z, kept, k_final, seed=seed)
        if seeded is not None:
            init, n_type_seeds = seeded
            if verbose:
                print(
                    f"  seeded {n_type_seeds} centroids at their own type's centre, "
                    f"{k_final - n_type_seeds} by kmeans++ over the untyped points",
                    file=sys.stderr,
                )
            # n_init must be 1 with an explicit init: the seeds are the whole point, and a
            # restart would throw them away for a random draw.
            km = KMeans(n_clusters=k_final, init=init, n_init=1, random_state=seed).fit(z)
        else:
            km = KMeans(n_clusters=k_final, n_init=10, random_state=seed).fit(z)
        cluster_id = km.labels_.astype(int)
        centre_vectors = km.cluster_centers_
        plan_report = {**plan, "seededTypes": seeded[1] if seeded else 0}

    assigned = cluster_id >= 0
    n_noise = int((~assigned).sum())

    type_of = kept.types()
    purity = _purity(cluster_id, type_of, k_final)

    # The renderer's per-point response space. Built from the same standardised
    # descriptors, after KMeans, so nothing about the clustering depends on it.
    lo_points, lo_centroids, lo_variance = point_features(z, centre_vectors)
    if verbose:
        print(
            f"per-point features: {POINT_FEATURE_DIMS}-d, "
            f"{lo_variance * 100:.1f} % of the 28-d variance retained",
            file=sys.stderr,
        )

    # Evaluate the projections. Distance faithfulness decides which one is honest;
    # kNN agreement says how tidy it looks. Purity cannot move (it never sees pos).
    wanted = list(PROJECTIONS) if compare_projections else [projection]
    if projection not in wanted:
        wanted.insert(0, projection)
    results: dict[str, dict[str, Any]] = {}
    for method in wanted:
        raw, info = project(z, method, seed=seed, min_dist=min_dist, verbose=verbose)
        # Held aside rather than left in `info`, which is serialised into the manifest as
        # projectionParams — these are megabytes of float arrays, not metadata.
        basis_parts = info.pop("basis", None)
        if not np.all(np.isfinite(raw)):
            raise RuntimeError(f"projection {method} produced non-finite positions")
        spaced, cluster_shift = separate_clusters(raw, cluster_id, k_final, separation)
        candidate, candidate_extent, frame = normalise_positions(spaced)
        results[method] = {
            "positions": candidate,
            "extent": candidate_extent,
            "info": info,
            "faithfulness": faithfulness(z, candidate, seed=seed),
            "knnAgreement": round(knn_label_agreement(candidate, type_of), 4),
            "purity": round(_purity(cluster_id, type_of, k_final), 4),
            "meanRadius": round(float(np.mean(np.linalg.norm(candidate, axis=1))), 4),
            "tearing": torn_clusters(candidate, cluster_id, k_final),
            "clusterShift": cluster_shift,
            "frame": frame,
            "basisParts": basis_parts,
        }

    if verbose:
        _print_projection_table(results, projection)

    chosen = results[projection]
    pos = chosen["positions"]
    extent = chosen["extent"]

    index = _inventory_index(inventory)
    common_names = {sp["id"]: sp.get("common", sp["id"]) for sp in inventory.get("species", [])}
    items: list[dict[str, Any]] = []
    counts: list[int] = []
    for c in range(k_final):
        sel = np.nonzero(cluster_id == c)[0]
        members = [
            (kept.species_id[i], kept.syllable_id[i], kept.song_id[i]) for i in sel
        ]
        info = label_cluster(members, index, common_names) if members else {
            "label": "", "speciesId": "", "syllableId": "",
            "function": "", "confidence": "", "refs": [],
        }
        position = pos[sel].mean(axis=0) if sel.size else np.zeros(3)
        member_durations = [kept.duration[i] for i in sel]
        member_sources = Counter(kept.source[i] for i in sel)
        # What this dense region can be said to be, and on what evidence. Only density
        # clustering produces it — KMeans has no notion of a region that anchors nothing.
        verdict = anchors[c] if anchors and c < len(anchors) else None
        items.append(
            {
                "id": c,
                **info,
                "position": [round(float(v), 6) for v in position],
                "functionClass": function_class(info["function"]),
                "vector": [round(float(v), 6) for v in centre_vectors[c]],
                "featuresLo": [round(float(v), 6) for v in lo_centroids[c]],
                "count": int(sel.size),
                # Small per-cluster summary the interface can put on screen next to the
                # node without fetching anything else.
                "meanDuration": round(float(np.mean(member_durations)), 4)
                if member_durations
                else 0.0,
                "radius": round(
                    float(np.mean(np.linalg.norm(pos[sel] - position, axis=1)))
                    if sel.size
                    else 0.0,
                    4,
                ),
                "cohesion": round(
                    float(np.mean(_unit_rows(z[sel]) @ _unit_rows(centre_vectors[c][None, :])[0]))
                    if sel.size
                    else 0.0,
                    4,
                ),
                "speciesMix": [
                    {"speciesId": sp, "count": int(n)}
                    for sp, n in Counter(kept.species_id[i] for i in sel).most_common(3)
                ],
                "sources": {s: int(n) for s, n in member_sources.most_common()},
                **({"anchor": verdict} if verdict else {}),
            }
        )
        counts.append(int(sel.size))

    # How many types actually ended up with a cluster carrying their name.
    #
    # **This is the number whose absence cost the cuckoo both of its calls.** A type only
    # gets a `syllableId` on a cluster when it wins that cluster's majority vote, so a type
    # can be present in the corpus, rendered 96 times, and still have no node anywhere in
    # the galaxy — at which point the app cannot draw its trajectory, cannot light it and
    # cannot label it, and the bird sings into an empty picture. Purity does not see it
    # (it scores the points that have a cluster), the projection metrics do not see it, and
    # neither did anyone until a cuckoo went quiet. So it is measured, printed, and written
    # into the manifest with the offenders named.
    named_types = {
        (sp, syl) for sp, syl in zip(kept.species_id, kept.syllable_id) if syl
    }
    homed = {(it["speciesId"], it["syllableId"]) for it in items if it["syllableId"]}
    orphans = sorted(f"{sp}/{syl}" for sp, syl in (named_types - homed))
    coverage = {
        "types": len(named_types),
        "withCluster": len(named_types) - len(orphans),
        "orphans": orphans,
        "share": round((len(named_types) - len(orphans)) / max(1, len(named_types)), 4),
    }
    if verbose:
        print(
            f"type coverage: {coverage['withCluster']}/{coverage['types']} types have a "
            f"cluster carrying their name ({coverage['share'] * 100:.1f} %)",
            file=sys.stderr,
        )
        if orphans:
            print(
                f"  {len(orphans)} with no cluster — they cannot light, label or draw a "
                f"trajectory: {', '.join(orphans[:12])}"
                + (f", +{len(orphans) - 12} more" if len(orphans) > 12 else ""),
                file=sys.stderr,
            )

    # --- write the asset set (8.3) ---
    # The frozen frame, so later audio can be added to this galaxy rather than replacing
    # it. Only cMDS carries one: UMAP and PCA have no out-of-sample extension that keeps
    # the existing points still, so a build with either of those can only ever be rebuilt.
    basis_parts = chosen.get("basisParts")
    if basis_parts is not None:
        from .grow import ProjectionBasis

        ProjectionBasis(
            landmarks=basis_parts["landmarks"],
            l_pinv=basis_parts["lPinv"],
            mean_sq=basis_parts["meanSq"],
            cluster_shift=chosen["clusterShift"],
            centre=np.asarray(chosen["frame"]["centre"]),
            scale=np.asarray(chosen["frame"]["scale"]),
            knee=float(chosen["frame"]["knee"]),
            peak=np.asarray(chosen["frame"]["peak"]),
            mean=mean,
            std=std,
        ).save(out_dir)
        if verbose:
            print(f"wrote {out_dir / 'projection-basis.json'}", file=sys.stderr)

    (out_dir / "positions.f32").write_bytes(
        pos.astype("<f4", copy=False).ravel(order="C").tobytes()
    )
    (out_dir / "point-features.f32").write_bytes(
        lo_points.astype("<f4", copy=False).ravel(order="C").tobytes()
    )
    _write_json(
        out_dir / "points.json",
        {
            "n": len(kept),
            "speciesId": kept.species_id,
            "syllableId": kept.syllable_id,
            "songId": kept.song_id,
            "clusterId": [int(v) for v in cluster_id],
            "durations": [round(v, 6) for v in kept.duration],
            "source": kept.source,
        },
    )
    _write_json(out_dir / "centroids.json", {"k": k_final, "dims": features.DIM, "items": items})
    _write_json(
        out_dir / "feature-space.json",
        {
            # flat keys = the client interface of 8.3; the nested `extractor` block
            # below is the same information plus the exact formulas.
            "sampleRate": features.SAMPLE_RATE,
            "frameSize": features.FRAME,
            "hopSize": features.HOP,
            "window": features.WINDOW_SPEC,
            "melBands": features.N_MEL,
            "mfccCoeffs": features.N_MFCC,
            "dims": features.DIM,
            "dimNames": features.DIM_NAMES,
            "mean": [float(v) for v in mean],
            "std": [float(v) for v in std],
            "temperature": TEMPERATURE,
            "standardisation": "z = (x - mean) / max(std, 1e-6)",
            "extractor": {
                "sampleRate": features.SAMPLE_RATE,
                "frame": features.FRAME,
                "hop": features.HOP,
                "bins": features.N_BINS,
                "window": features.WINDOW_SPEC,
                "peakNormalise": features.PEAK_NORM,
                "voiced": {
                    "rmsFloor": features.RMS_FLOOR,
                    "rmsRelativeToClipMax": features.RMS_REL,
                    "note": "rms is computed on the unwindowed frame",
                },
                "mel": {
                    "bands": features.N_MEL,
                    "hzToMel": "1125*ln(1 + hz/700)",
                    "spanHz": [0, features.SAMPLE_RATE // 2],
                    "binPt": "melToHz(i/(M+1)*melMax) * N/sampleRate, i in [0, M+2)",
                    "appliedTo": "power spectrum mag^2",
                    "bandFloor": features.BAND_FLOOR,
                },
                "mfcc": {
                    "count": features.N_MFCC,
                    "dct": "unnormalised DCT-II: c[i] = sum_j ln(E[j])*cos(pi*i*(j+0.5)/M)",
                },
                "centroid": "log2(max(sum(f*mag)/sum(mag), 20))",
                "flatness": "exp(mean(ln(mag+1e-10))) / (mean(mag)+1e-10)",
            },
            "activation": {
                "similarity": "cosine(z_live, z_centroid)",
                "softmaxTemperature": TEMPERATURE,
                "ema": [0.82, 0.18],
            },
        },
    )
    shutil.copyfile(inventory_path, out_dir / "inventory.json")

    spread = float(np.mean(np.linalg.norm(pos, axis=1)))
    durations = list(kept.duration)
    stats = GalaxyStats(
        n_points=len(kept),
        n_dropped=n_dropped,
        k=k_final,
        cluster_counts=counts,
        duration_range=(min(durations), max(durations)),
        position_extent=extent,
        labels=[it["label"] for it in items],
        purity=purity,
        spread=spread,
        projection=projection,
        faithfulness=dict(chosen["faithfulness"]),
        knn_agreement=float(chosen["knnAgreement"]),
        point_feature_variance=lo_variance,
    )

    manifest = {
        "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "birdy-pipeline",
        "contract": "docs/08-implementation.md v1",
        "inventoryVersion": inventory.get("version"),
        # Which inventory this galaxy was built from, and when that file was last written.
        # A build is only as current as its input, and the input is a file another command
        # rewrites: `learn` had refit the inventory to 80 types while the shipped assets
        # still held the 264-type fit, and nothing on either side said so. With this the
        # app can compare what it loaded against what is on disk now.
        "inventorySource": {
            "path": str(inventory_path),
            "name": Path(inventory_path).name,
            "writtenAt": datetime.fromtimestamp(
                Path(inventory_path).stat().st_mtime, timezone.utc
            ).isoformat(timespec="seconds"),
            "species": len(inventory.get("species", [])),
            "syllables": sum(
                len(sp.get("syllables", [])) for sp in inventory.get("species", [])
            ),
        },
        # Types that got a cluster carrying their name, and the ones that did not. See the
        # comment where this is computed: an orphaned type is silently unplayable.
        "typeCoverage": coverage,
        "clusterPlan": plan_report,
        "points": stats.n_points,
        "pointsDropped": stats.n_dropped,
        "clusters": stats.k,
        "dims": features.DIM,
        "seed": seed,
        "projection": projection,
        "projectionParams": {
            k2: v for k2, v in chosen["info"].items() if k2 != "positions"
        },
        "faithfulness": {
            **chosen["faithfulness"],
            "definition": (
                "correlation between 28-d cosine distance and 3D euclidean distance "
                "over random point pairs; 1.0 = distances fully meaningful"
            ),
        },
        "knnAgreement": {
            "k": KNN_AGREEMENT_K,
            "value": round(float(chosen["knnAgreement"]), 4),
            "definition": "share of a point's 3D k nearest neighbours sharing its type",
        },
        "tearing": {
            **chosen["tearing"],
            "definition": (
                "clusters this projection draws in two places at once, so their centroid "
                "— where the label, the trajectory and the wave all go — lands between "
                "two blobs instead of on the points; splitting a single blob scores ~2, "
                "so 2 is the null and 'torn' counts above 5"
            ),
        },
        "projectionComparison": {
            method: {
                "faithfulness": r["faithfulness"],
                "knnAgreement": r["knnAgreement"],
                "purity": r["purity"],
                "meanRadius": r["meanRadius"],
                "params": {k2: v for k2, v in r["info"].items() if k2 != "positions"},
            }
            for method, r in results.items()
        },
        "clustering": clustering,
        "kmeans": {"k": stats.k, "nInit": 10, "randomState": seed,
                   "inputSpace": "standardised 28-d descriptors"},
        "positions": {
            "format": "little-endian float32, 3*n, xyz",
            "bytes": stats.n_points * 3 * 4,
            "normalisation": "centred on the bbox midpoint, scaled so max|coord| = 1",
        },
        "pointFeatures": {
            "format": f"little-endian float32, {POINT_FEATURE_DIMS}*n, row-major",
            "bytes": stats.n_points * POINT_FEATURE_DIMS * 4,
            "dims": POINT_FEATURE_DIMS,
            "space": "PCA of the standardised 28-d descriptors, rows unit-normalised",
            "varianceRatioTotal": round(lo_variance, 4),
            "purpose": (
                "per-point render response only; the reported match still uses the "
                "28-d centroid vectors"
            ),
        },
        "functionClasses": {
            "definition": (
                "behavioural class of each cluster's documented function, matched "
                "against the keyword table below in order; the first hit wins"
            ),
            "rules": {name: list(words) for name, words in FUNCTION_CLASSES},
            "counts": {
                c: int(n) for c, n in Counter(it["functionClass"] for it in items).most_common()
            },
        },
        "sourceMix": {s: int(n) for s, n in Counter(kept.source).most_common()},
        "speciesMix": {s: int(n) for s, n in Counter(kept.species_id).most_common()},
        "durationSeconds": [round(stats.duration_range[0], 4), round(stats.duration_range[1], 4)],
        "clusterPurity": round(stats.purity, 4),
        **({"density": density_summary} if density_summary else {}),
        "unassigned": n_noise,
        "meanRadius": round(stats.spread, 4),
        "files": [
            "manifest.json",
            "inventory.json",
            "syrinx-calibration.json",
            "feature-space.json",
            "positions.f32",
            "point-features.f32",
            "points.json",
            "centroids.json",
        ],
        **(build_info or {}),
    }
    _write_json(out_dir / "manifest.json", manifest)
    return stats


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
