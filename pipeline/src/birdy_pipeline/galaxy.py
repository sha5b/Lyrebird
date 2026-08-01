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
#
# **Raised from 1024 on 2026-08-01, once the renderer stopped being the reason for it.**
# 1024 was not a pipeline number at all: the browser declared the three per-cluster
# channels as `uniform float[clusterCount]` arrays in its *vertex* shader, so 1 024
# knots cost 3 072 vertex uniform floats and stood only because the development GPU is
# generous. The cost of that ceiling was measured and is not small — on the 2 143-type
# debug corpus, **1 231 types (57 %) had no cluster**, and a type with no cluster lights
# nothing when it sounds: 26 of 100 songs could not light a single note. The channels
# now live in a data texture (`app/src/lib/galaxy/shaders.ts`, `uClusterState`), so the
# renderer's ceiling is texture size and no longer binds.
#
# What binds now is k-means: Lloyd's iteration is O(n k d), so k is a build-time cost
# rather than a browser one. 8192 covers the debug corpora outright and cuts what the
# production corpus has to shed by 8x. A corpus that wants more than this does not want
# a bigger k-means — 96 % of points already carry a type from `typing.json`, so the
# honest answer at that scale is to assign those points to their own type and cluster
# only what has no label (docs/22 §22.5, the vote the build currently re-derives).
K_CAP = 8192

#: `harvest.SOURCE`, duplicated rather than imported: harvest pulls in the audio decode
#: stack and galaxy must stay importable where only numpy/sklearn exist.
FIELD_SOURCE = "field"

#: Cosine between a type's field-blob mean and its synthetic-blob mean below which the
#: two are seeded separately (`_type_seed_means`). 0.9 splits 483 of 496 types on the
#: 47 k corpus — the source gap touches nearly everything — and still merges the blobs
#: that genuinely coincide, which is what keeps the second seed honest.
SOURCE_SEED_GATE = 0.9

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
    #: 32-d critic embedding per row, aligned with `x`; NaN where a point has none.
    #: None for a corpus that was never embedded — the descriptor-space build, which is
    #: still the default. Only a build with `space="embed"` reads this.
    embeddings: np.ndarray | None = None
    #: One flag per row: the observation this point came from was judged unlike every
    #: known type centroid at ingest (docs/09 §9.2b use 2). None on corpora that were
    #: never scored — every build path, where the flag changes nothing. Only `grow`
    #: reads it, to hold a new point back from force-assignment to the nearest knot.
    novel: list[bool] | None = None

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
        # All-or-nothing: a build in the embedding space cannot have some of its points
        # embedded and some not, so a part without rows drops the whole matrix and the
        # embed-mode build will say so rather than silently mixing spaces.
        embeddings = (
            np.concatenate([p.embeddings for p in kept], axis=0)
            if all(p.embeddings is not None for p in kept)
            else None
        )
        # Same all-or-nothing rule as the embeddings: a partially flagged corpus would
        # make "unflagged" ambiguous between "measured, known" and "never measured".
        novel = (
            [v for p in kept for v in (p.novel or [False] * len(p))]
            if all(p.novel is not None for p in kept)
            else None
        )
        return PointSet(
            x=np.concatenate([p.x for p in kept], axis=0),
            species_id=[v for p in kept for v in p.species_id],
            syllable_id=[v for p in kept for v in p.syllable_id],
            song_id=[v for p in kept for v in p.song_id],
            duration=[v for p in kept for v in p.duration],
            source=[v for p in kept for v in p.source],
            embeddings=embeddings,
            novel=novel,
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
    embedder: Callable[[Clip], np.ndarray | None] | None = None,
) -> PointSet:
    """28-d descriptor per clip; clips with no voiced frame are dropped (8.2).

    `embedder` additionally maps each *kept* clip to its 32-d critic embedding — for a
    build that clusters in the learned space (`build --space embed`). It is a per-clip
    callable rather than a batch so this loop stays the only place that decides which
    clips survive; returning None gives the point a NaN row, which the embed-mode build
    excludes and counts.
    """
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
    embeddings = None
    if embedder is not None:
        vectors = [embedder(clip) for clip in kept]
        found = next((v for v in vectors if v is not None), None)
        if found is not None:
            dim = int(np.asarray(found).shape[0])
            embeddings = np.stack([
                np.full(dim, np.nan, dtype=np.float32) if v is None
                else np.asarray(v, dtype=np.float32)
                for v in vectors
            ])
    return PointSet(
        x=np.stack(rows),
        species_id=[c.species_id for c in kept],
        syllable_id=[c.syllable_id for c in kept],
        song_id=[c.song_id for c in kept],
        duration=[c.duration for c in kept],
        source=[c.source for c in kept],
        embeddings=embeddings,
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
    """Correlate feature-space cosine distance with 3D Euclidean distance over random pairs.

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
        "  pearson/spearman = feature-space cosine distance vs 3D euclidean distance over "
        f"{next(iter(results.values()))['faithfulness']['pairs']} random pairs",
        file=sys.stderr,
    )
    print("", file=sys.stderr)


def _type_seed_means(
    z: np.ndarray, points: PointSet, gate: float = SOURCE_SEED_GATE
) -> tuple[list[np.ndarray], int, list[tuple[tuple[str, str], int]]]:
    """One seed per type per *source blob*: the field mean and the synthetic mean.

    The strongest relation in the critic's space is not species, it is `source` —
    recorded or synthesised (kNN 0.990 against species' 0.513 on the 47 k build). A
    type with members on both sides therefore lives in two blobs, and a single seed at
    the mean of both sits in empty space between them, gets captured by whichever blob
    is bigger, and leaves the other blob to be named by a neighbour. Measured on the
    fixed 59 700-point corpus (`build --dump-points`): one seed per type covers 71.0 %
    of types and scores 48.1 % purity; splitting at the 0.9 gate covers **93.1 %** at
    56.6 % purity. 483 of 496 types split at that gate — the gap touches nearly every
    type — and the gate still keeps the two seeds honest: blobs that genuinely coincide
    (cosine >= gate) share one, because there is nothing to separate.

    The third return value names every seed: `((species, syllable), rank)` with rank 0
    the type's primary (or only) blob and 1 the second blob of a source split — the
    information `type_seeds` needs to decide which seeds a capped build can afford to
    lose.
    """
    labelled: dict[tuple[str, str], list[int]] = {}
    for i, (sp, syl) in enumerate(zip(points.species_id, points.syllable_id)):
        if syl:
            labelled.setdefault((sp, syl), []).append(i)
    seeds: list[np.ndarray] = []
    owners: list[tuple[tuple[str, str], int]] = []
    n_split = 0
    for key, idx in sorted(labelled.items()):
        ix = np.asarray(idx)
        is_field = np.asarray([points.source[i] == FIELD_SOURCE for i in ix])
        f, s = ix[is_field], ix[~is_field]
        if f.size and s.size:
            fm, sm = z[f].mean(axis=0), z[s].mean(axis=0)
            cos = float(
                np.dot(fm, sm)
                / max(float(np.linalg.norm(fm) * np.linalg.norm(sm)), 1.0e-12)
            )
            if cos < gate:
                seeds.extend((fm, sm))
                owners.extend(((key, 0), (key, 1)))
                n_split += 1
                continue
        seeds.append(z[ix].mean(axis=0))
        owners.append((key, 0))
    return seeds, n_split, owners


def deflate_direction(
    z: np.ndarray, source: Sequence[str], verbose: bool = True
) -> dict[str, Any] | None:
    """Project the recorded-vs-synthesised axis out of the space, in place.

    **The measured problem.** The critic's leading loss term is realism — real against
    our own resynthesis, `w_real 1.0` — so the strongest relation in its embedding is
    `source` (kNN 0.990 against species' 0.513), which is the axis it was trained to
    encode. The galaxy is then built in that space out of both kinds of point, so every
    type lives in two blobs and needs two seeds: on the 2026-08-01 production build,
    `typeSeeds 27 762` for `types 13 903` — **13 859 of 13 859 learned types split**.
    The cap therefore binds at twice the type count, and the triage in `type_seeds`
    sheds 12 879 types' only knot. Half of that demand is one direction in a 32-d space.

    **What this removes, and what it does not.** The direction is the difference of the
    two source means in the standardised space — the axis the split is measured along,
    computed from the points themselves rather than from the critic's realism weights,
    so it works in the descriptor space too and stays honest if the critic is retrained.
    One unit vector is projected out of every row; the other 31 directions are
    untouched. What is lost is the galaxy's ability to place a point by how synthetic it
    sounds, which is not a claim about birds and is not what a knot is for; the fit's
    realism objective is unaffected, because that reads the critic's head, not this
    matrix. Returns the receipt (variance share removed, the gap before and after) for
    the manifest, or None when the corpus has only one source and there is nothing to
    remove.
    """
    src = np.asarray(source)
    field = src == FIELD_SOURCE
    if not field.any() or field.all():
        return None
    before = float(np.linalg.norm(z[field].mean(axis=0) - z[~field].mean(axis=0)))
    direction = z[field].mean(axis=0) - z[~field].mean(axis=0)
    norm = float(np.linalg.norm(direction))
    if norm < 1.0e-9:
        return None
    unit = direction / norm
    total = float((z**2).sum())
    projection = z @ unit
    removed = float((projection**2).sum())
    z -= np.outer(projection, unit)
    after = float(np.linalg.norm(z[field].mean(axis=0) - z[~field].mean(axis=0)))
    report = {
        "definition": "the recorded-minus-synthesised mean difference, projected out of "
                      "the standardised space before clustering",
        "varianceShareRemoved": round(removed / max(total, 1.0e-12), 4),
        "sourceMeanGap": [round(before, 4), round(after, 4)],
        "dims": int(z.shape[1]),
    }
    if verbose:
        print(
            f"deflated the source axis: {report['varianceShareRemoved']:.1%} of the "
            f"space's energy, source mean gap {before:.3f} -> {after:.3f}",
            file=sys.stderr,
        )
    return report


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


def cluster_plan(points: PointSet, z: np.ndarray | None = None) -> dict[str, Any]:
    """`default_k` with its reasoning attached, so a build can report what it asked for.

    **One seed per type was only ever half the count — twice.** First because harvested
    points carried no ``syllable_id`` and took clusters the named types then lacked (the
    256-cluster build: 76 field-only knots, 128 types orphaned). Then, once typing
    labelled every field point and the sqrt allowance shrank to nothing (126 untyped →
    7), because a type's field and synthetic members sit in *different blobs*: `source`
    is the strongest relation in the critic's space (kNN 0.990, species 0.513), and one
    midpoint seed per type is captured by the bigger blob. Coverage stuck at 70-71 %
    across three builds (110, then 148, then 144 orphaned types — cuculus_solitarius
    losing a dozen at a time).

    The count is therefore the number of *type seeds* — one per type per source blob,
    `_type_seed_means` with its measured gate — plus the sqrt allowance for the points
    that still have no type. Measured on the fixed 59 700-point corpus: 71.0 % → 93.1 %
    coverage, purity 48.1 % → 56.6 % (better on both: the seeds finally sit where the
    points are). `z` is the standardised space matrix; without it the plan cannot see
    the blobs and falls back to one seed per type, which is what `default_k` still does.
    """
    types = {
        (sp, syl) for sp, syl in zip(points.species_id, points.syllable_id) if syl
    }
    unlabelled = sum(1 for syl in points.syllable_id if not syl)
    allowance = int(math.sqrt(unlabelled / 2)) if unlabelled else 0
    n_seeds = len(_type_seed_means(z, points)[0]) if z is not None else len(types)
    wanted = n_seeds + allowance if types else int(
        math.sqrt(max(1, len(points.species_id)) / 2)
    )
    k = max(2, min(K_CAP, wanted))
    return {
        "k": k,
        "types": len(types),
        "typeSeeds": n_seeds,
        "sourceSplitTypes": n_seeds - len(types) if types else 0,
        "unlabelledPoints": unlabelled,
        "allowance": allowance,
        "wanted": wanted,
        "capped": wanted > K_CAP,
        "cap": K_CAP,
    }


def type_seeds(
    z: np.ndarray, points: PointSet, k: int, seed: int = 0
) -> tuple[np.ndarray, int, dict[str, int]] | None:
    """Initial centroids: one at the centre of every type's every source blob, the rest
    found freely.

    **KMeans++ picks its seeds by distance, and distance in this space is dominated by
    "was this recorded or synthesised".** So it spends its seeds spreading across that gap
    and two acoustically similar types of the same bird — a rendered `oo` and a fitted
    `L02`, both low held cuckoo tones — start life sharing one seed and finish sharing one
    cluster. Whichever loses the majority vote loses its name, its function and its
    citation, and in the app it loses the ability to light, label or draw a trajectory at
    all. Raising `k` alone does not fix that: it hands the extra clusters to whatever is
    furthest away, which is more field audio, not the type that was crowded out.

    Seeding each type at its own centre was the first fix; seeding each type's *source
    blobs* separately is the measured one (`_type_seed_means`: the source gap is the
    space's strongest axis, and a midpoint seed between two blobs is a seed in empty
    space). Lloyd's algorithm still moves every centroid and still decides membership,
    so nothing is forced: a blob whose points genuinely sit inside another type's cloud
    will still be absorbed, and `typeCoverage` will still say so. Both blobs of a split
    type may win their cluster's name — two knots, one type — which is the honest
    picture of a space where recorded and synthesised do not coincide.

    **More seeds than `k` is a triage, not a surrender.** The old answer was to return
    None and let the build fall back to unseeded k-means — the worst possible response,
    since it threw away *every* type's seed the moment the cap bound (a 1 420-type debug
    build at k=1024 lost all 2 840 seeds, and 1 816 types shared clusters). Now the
    seeds are shed in the order that costs the least:

    1. second knots of source-split types first (the type keeps its primary knot),
    2. then whole types, thinnest learned types first — a type fitted from six
       syllables gives up its cluster before one fitted from six hundred,
    3. a documented call's knot last of all: it is where the function and the
       citation live, and losing it is the failure the cap warning exists for.

    Returns the seed matrix, how many rows are type means, and what the triage cost
    (`typesLost` = types with no seed left at all, `splitKnotsLost` = second blobs
    shed), or None when the corpus has no types.
    """
    unlabelled: list[int] = []
    for i, syl in enumerate(points.syllable_id):
        if not syl:
            unlabelled.append(i)
    means_list, _, owners = _type_seed_means(z, points)
    if not means_list:
        return None
    shed = {"typesLost": 0, "splitKnotsLost": 0}
    if len(means_list) > k:
        members = Counter(
            (sp, syl) for sp, syl in zip(points.species_id, points.syllable_id) if syl
        )

        def priority(i: int) -> tuple[int, int, int, str, str]:
            (sp, syl), rank = owners[i]
            learned = syl.startswith(("L", "U"))
            return (rank, 1 if learned else 0, -members[(sp, syl)], sp, syl)

        keep = sorted(range(len(means_list)), key=priority)[:k]
        keep_set = set(keep)
        lost = {owners[i][0] for i in range(len(owners))} - {
            owners[i][0] for i in keep_set
        }
        shed = {
            "typesLost": len(lost),
            "splitKnotsLost": sum(
                1
                for i in range(len(owners))
                if i not in keep_set
                and owners[i][1] == 1
                and owners[i][0] not in lost
            ),
        }
        keep.sort()
        means_list = [means_list[i] for i in keep]
        owners = [owners[i] for i in keep]
    means = np.stack(means_list)
    extra = k - len(means)
    if extra <= 0:
        return means[:k], len(means[:k]), shed
    # The remaining seeds belong to the points that have no type — overwhelmingly field
    # audio — and KMeans++ over just those is the right way to place them, because there
    # the "recorded or synthesised" axis it keys on is no longer a distraction.
    pool = z[unlabelled] if len(unlabelled) >= extra else z
    rest = KMeans(n_clusters=extra, n_init=3, random_state=seed).fit(pool).cluster_centers_
    return np.concatenate([means, rest]), len(means), shed


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
    recordings: dict[str, Any] | None = None,
    test_relations: bool = True,
    frame: tuple[np.ndarray, np.ndarray] | None = None,
    space: str = "descriptor",
    embedding: dict[str, Any] | None = None,
    dump_points: Path | None = None,
    dump_spacemap_eval: Path | None = None,
    deflate_source: bool = False,
) -> GalaxyStats:
    # The projection (and `min_dist` within UMAP) is purely about the picture: KMeans
    # and the activation vectors live in the standardised feature space, never in
    # these 3D positions.
    #
    # `space` chooses which feature space that is. "descriptor" is the hand-designed
    # 28-d one of 8.2, as it always was. "embed" is the critic's learned 32-d embedding
    # (docs/09 §9.7: the measurably better similarity space), carried per point in
    # `PointSet.embeddings`. Everything downstream — projection, separation, KMeans with
    # its type seeds, the per-point PCA — runs on the chosen matrix unchanged, because
    # none of it ever knew what the dimensions meant. `embedding` carries the space's
    # standardisation moments, the browser's 28-d -> 32-d map and its gate numbers; see
    # spacemap.py.
    if projection not in PROJECTIONS:
        raise ValueError(f"unknown projection {projection!r}, expected {PROJECTIONS}")
    if space not in ("descriptor", "embed"):
        raise ValueError(f"unknown space {space!r}, expected 'descriptor' or 'embed'")
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
    # `frame` pins the standardisation instead of deriving it from these points. It ships
    # in feature-space.json and the browser standardises its live *windows* against it,
    # so when the galaxy's field points are syllable-level observations the frame must
    # still be measured over the window corpus — which is what cmd_build passes. With no
    # frame the points define it, as they always did.
    if frame is None:
        mean = x.mean(axis=0)
        std = x.std(axis=0)  # population std, floored at lookup time
    else:
        mean, std = frame
    # The 28-d standardisation is computed in every mode: it is what feature-space.json
    # ships for the browser's live descriptor, and in embed mode it is what each
    # cluster's fallback `vector` is averaged from.
    z28 = features.standardise(x, mean, std)
    if not np.all(np.isfinite(z28)):
        raise RuntimeError("standardised descriptors contain NaN/inf")

    z = z28
    space_dims = features.DIM
    emb_mean = emb_std = None
    if space == "embed":
        if embedding is None or kept.embeddings is None:
            raise RuntimeError(
                "space='embed' needs every point to carry a critic embedding "
                "(PointSet.embeddings) and the space's moments in `embedding` — the "
                "descriptor-space build is the one that needs neither"
            )
        e = np.asarray(kept.embeddings, dtype=np.float64)
        finite = np.all(np.isfinite(e), axis=1)
        n_nan = int((~finite).sum())
        if n_nan:
            # A point with no embedding cannot be placed in this space at all. Dropping
            # it with a count is the honest reading of "no evidence"; pretending it sits
            # at the space's centre would hand it to an arbitrary cluster.
            if verbose:
                print(
                    f"embed space: {n_nan} points have no embedding (no mel patch) and "
                    "are excluded from the build",
                    file=sys.stderr,
                )
            kept = PointSet(
                x=x[finite],
                species_id=[v for v, m in zip(kept.species_id, finite) if m],
                syllable_id=[v for v, m in zip(kept.syllable_id, finite) if m],
                song_id=[v for v, m in zip(kept.song_id, finite) if m],
                duration=[v for v, m in zip(kept.duration, finite) if m],
                source=[v for v, m in zip(kept.source, finite) if m],
                novel=(
                    [v for v, m in zip(kept.novel, finite) if m]
                    if kept.novel is not None
                    else None
                ),
            )
            x = kept.x
            z28 = z28[finite]
            e = e[finite]
            n_dropped += n_nan
        emb_mean = np.asarray(embedding["mean"], dtype=np.float64)
        emb_std = np.asarray(embedding["std"], dtype=np.float64)
        z = (e - emb_mean) / np.maximum(emb_std, 1.0e-6)
        if not np.all(np.isfinite(z)):
            raise RuntimeError("standardised embeddings contain NaN/inf")
        space_dims = int(z.shape[1])
        if verbose:
            print(
                f"feature space: critic embedding, {len(kept)} points x {space_dims}-d",
                file=sys.stderr,
            )

    deflation: dict[str, Any] | None = None
    if deflate_source:
        deflation = deflate_direction(z, kept.source, verbose=verbose)

    if dump_points is not None:
        # The clustering/placement iteration set: the exact matrix and labels KMeans
        # sees, so cluster_plan changes can be measured against a fixed corpus instead
        # of re-rendering ~400 s of audio per idea (evidence discipline, docs/09 §9.7).
        np.savez(
            dump_points,
            z=z.astype(np.float32),
            z28=z28.astype(np.float32),
            species_id=np.asarray(kept.species_id),
            syllable_id=np.asarray(kept.syllable_id),
            song_id=np.asarray(kept.song_id),
            source=np.asarray(kept.source),
            duration=np.asarray(kept.duration, dtype=np.float32),
        )
        if verbose:
            print(f"dumped {len(kept)} clustering points to {dump_points}", file=sys.stderr)

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
        plan = cluster_plan(kept, z)
        plan_report = plan
        k_final = int(k or plan["k"])
        k_final = max(2, min(k_final, len(kept)))
        if verbose:
            print(f"kmeans: k={k_final} on standardised descriptors", file=sys.stderr)
            print(
                f"  {plan['types']} named types ({plan['sourceSplitTypes']} with "
                f"source-split seeds) + {plan['allowance']} for "
                f"{plan['unlabelledPoints']} points with no type = {plan['wanted']} wanted",
                file=sys.stderr,
            )
            if plan["capped"]:
                # The failure mode this replaces was silent, and silence is what made it
                # expensive: a bird lost every cluster carrying its name and the only
                # symptom was that it sang and nothing lit up. The triage in `type_seeds`
                # now decides *which* seeds the cap costs — the line after it says how
                # many types lost their only knot.
                print(
                    f"  WARNING: {plan['wanted']} wanted seeds exceed the cap of "
                    f"{plan['cap']} — shedding second (field/synth) knots first, then "
                    "the thinnest learned types; a documented call's knot is shed last",
                    file=sys.stderr,
                )
        seeded = type_seeds(z, kept, k_final, seed=seed)
        if seeded is not None:
            init, n_type_seeds, shed = seeded
            if verbose:
                print(
                    f"  seeded {n_type_seeds} centroids at their own type's centre, "
                    f"{k_final - n_type_seeds} by kmeans++ over the untyped points",
                    file=sys.stderr,
                )
                if shed["typesLost"] or shed["splitKnotsLost"]:
                    parts = []
                    if shed["splitKnotsLost"]:
                        parts.append(
                            f"{shed['splitKnotsLost']} types their second knot "
                            "(they keep their name on the first)"
                        )
                    if shed["typesLost"]:
                        parts.append(
                            f"{shed['typesLost']} types their only one — those share a "
                            "neighbour's cluster and lose the name, function and "
                            "citation that go with having one"
                        )
                    print(f"  the cap cost {'; and '.join(parts)}", file=sys.stderr)
            # n_init must be 1 with an explicit init: the seeds are the whole point, and a
            # restart would throw them away for a random draw.
            km = KMeans(n_clusters=k_final, init=init, n_init=1, random_state=seed).fit(z)
        else:
            km = KMeans(n_clusters=k_final, n_init=10, random_state=seed).fit(z)
        cluster_id = km.labels_.astype(int)
        centre_vectors = km.cluster_centers_
        plan_report = {
            **plan,
            "seededTypes": seeded[1] if seeded else 0,
            **(seeded[2] if seeded else {}),
        }

    assigned = cluster_id >= 0
    n_noise = int((~assigned).sum())

    type_of = kept.types()
    purity = _purity(cluster_id, type_of, k_final)

    # The renderer's per-point response space. Built from the same standardised
    # matrix, after KMeans, so nothing about the clustering depends on it.
    lo_points, lo_centroids, lo_variance = point_features(z, centre_vectors)
    if verbose:
        print(
            f"per-point features: {POINT_FEATURE_DIMS}-d, "
            f"{lo_variance * 100:.1f} % of the {space_dims}-d variance retained",
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
        # The per-cluster vector the browser matches live audio against. In the embedding
        # space the primary is `vector32` — the 32-d standardised embedding centroid — and
        # `vector` is the 28-d centroid over the same members, so the browser's pre-embedding
        # fallback path (and any asset consumer that only knows 28-d) still has a vector in
        # the space it understands. In the descriptor space `vector` is the KMeans centroid,
        # as it always was.
        item_vectors: dict[str, Any] = {}
        if space == "embed":
            item_vectors["vector32"] = [round(float(v), 6) for v in centre_vectors[c]]
            if sel.size:
                item_vectors["vector"] = [
                    round(float(v), 6) for v in z28[sel].mean(axis=0)
                ]
        else:
            item_vectors["vector"] = [round(float(v), 6) for v in centre_vectors[c]]
        items.append(
            {
                "id": c,
                **info,
                "position": [round(float(v), 6) for v in position],
                "functionClass": function_class(info["function"]),
                **item_vectors,
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
        if not named_types:
            # **A galaxy with no named type cannot answer the app's own voice.** Every
            # response in the interface goes through a cluster that carries a
            # `(speciesId, syllableId)`: the trajectory a phrase draws, the tag that names
            # what lit, the match the reading panel reports. A corpus of field audio alone
            # has none, so the app sings, the picture drifts, and nothing else happens — which
            # is indistinguishable from the app being broken and was reported as exactly that.
            # `--source harvest` is a legitimate thing to build; it is not a legitimate thing
            # to build *silently*.
            print(
                "  WARNING: not one cluster carries a syllable name, so nothing this app "
                "sings can light a knot, draw a trajectory or be labelled. That is what a "
                "field-audio-only corpus gives you. Include the rendered inventory "
                "(--source synthetic --harvest-store ...) for a galaxy the app can respond in.",
                file=sys.stderr,
            )

    # Does any way of grouping these points correspond to where they sit?
    #
    # Run here rather than as a separate command because this is the only place the
    # standardised 28-d matrix, every candidate arrangement and every label exist at once —
    # recomputing them afterwards would mean either shipping a 5 MB descriptor matrix to the
    # browser or re-rendering the corpus. See `geometry.py` for why every figure carries a
    # permutation p-value and why `source` is on the table.
    relations: list[Any] = []
    relation_summary: dict[str, Any] | None = None
    if test_relations:
        from . import geometry as geo

        groupings = geo.label_sets(
            species_id=kept.species_id,
            syllable_id=kept.syllable_id,
            # The harvest store carries each field descriptor's recording id in `song_id`;
            # a rendered clip carries its song id there and matches no recording.
            recording_id=kept.song_id,
            source=kept.source,
            recordings=recordings or {},
        )
        spaces = {
            f"{space_dims}-d {'critic embedding' if space == 'embed' else 'descriptors'}": (
                z,
                "cosine",
            ),
            f"3-d {projection}": (pos, "euclidean"),
        }
        if verbose:
            print("testing which groupings have geometric structure", file=sys.stderr)
        # Blocked by recording (field) and by syllable type (rendered variants): see
        # `geometry._neighbours` for why the unblocked figures were all ~0.98 and meaningless.
        blocks = geo.blocks_for(
            kept.species_id, kept.syllable_id, kept.song_id, kept.source
        )
        relations = geo.analyse(spaces, groupings, seed=seed, blocks=blocks)
        relation_summary = geo.summarise(relations)
        if verbose:
            print(geo.format_table(relations), file=sys.stderr)
            print(f"  => {relation_summary['headline']}", file=sys.stderr)

    # --- write the asset set (8.3) ---
    # The frozen frame, so later audio can be added to this galaxy rather than replacing
    # it. Only cMDS carries one: UMAP and PCA have no out-of-sample extension that keeps
    # the existing points still, so a build with either of those can only ever be rebuilt.
    # The basis standardisation is the *clustering* space's — 32-d embedding moments in an
    # embed build — because the landmarks are rows of that space and `grow` has to place
    # new points through the same transform.
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
            mean=emb_mean if space == "embed" else mean,
            std=emb_std if space == "embed" else std,
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
    _write_json(out_dir / "centroids.json", {"k": k_final, "dims": space_dims, "items": items})

    # The embedding block, when the build ran in the learned space: the standardisation
    # moments of the 32-d space, the browser's 28-d -> 32-d ridge map, and the map's gate
    # numbers — completed here with the nearest-centroid agreement against *this* galaxy's
    # centroids, which cannot be measured before they exist.
    embedding_json: dict[str, Any] | None = None
    map_quality: dict[str, Any] | None = None
    map_file: str | None = None
    if space == "embed" and embedding is not None:
        from . import spacemap

        map_quality = dict(embedding.get("mapQuality") or {})
        eval_mapped = embedding.get("_evalMapped")
        eval_true = embedding.get("_evalTrue")
        if eval_mapped is not None and len(eval_mapped):
            agreement = spacemap.centroid_agreement(eval_mapped, eval_true, centre_vectors)
            map_quality["centroidAgreement"] = round(agreement, 4)
            map_quality["centroidAgreementDefinition"] = (
                "share of held-out syllables whose nearest cluster centroid of this "
                "galaxy is the same through the 28-d -> 32-d map as through the critic"
            )
            # docs/20's margin-aware and species-level companions: the raw figure
            # undersells the map by construction — 74 % of rows are boundary
            # near-ties, and the browser's honest single-label claim is the species,
            # not the knot.
            um = spacemap._unit_rows(np.asarray(eval_mapped, dtype=np.float64))
            ut = spacemap._unit_rows(np.asarray(eval_true, dtype=np.float64))
            cu = spacemap._unit_rows(np.asarray(centre_vectors, dtype=np.float64))
            sim_m, sim_t = um @ cu.T, ut @ cu.T
            near_m, near_t = sim_m.argmax(axis=1), sim_t.argmax(axis=1)
            srt = np.sort(sim_t, axis=1)
            margin = srt[:, -1] - srt[:, -2]
            decided = margin >= 0.05
            map_quality["centroidAgreementTieAdjusted"] = round(
                float((near_m[decided] == near_t[decided]).mean()), 4
            )
            map_quality["centroidAgreementTieAdjustedDefinition"] = (
                "the same agreement with boundary near-ties excluded (true-space "
                "top-2 margin under 0.05; the share of flips that are a near-miss "
                "between adjacent knots rather than a wrong bird, per docs/20)"
            )
            sp_uniques, sp_codes = np.unique(kept.species_id, return_inverse=True)
            assigned = cluster_id >= 0
            knot_sp = np.zeros((len(centre_vectors), len(sp_uniques)), dtype=np.int64)
            np.add.at(knot_sp, (cluster_id[assigned], sp_codes[assigned]), 1)
            knot_species = np.asarray([
                sp_uniques[c.argmax()] if c.sum() else "" for c in knot_sp
            ])
            same_species = (
                (knot_species[near_m] == knot_species[near_t])
                & (knot_species[near_t] != "")
            )
            map_quality["speciesAgreement"] = round(float(same_species.mean()), 4)
            map_quality["speciesAgreementDefinition"] = (
                "share of held-out syllables whose nearest knot carries the same "
                "majority species through the map as through the critic — the "
                "honest single-label claim; knot-level answers are 'nearest of "
                "several close knots' (docs/20 §20.2)"
            )
            if dump_spacemap_eval is not None:
                # docs/20's per-session debug payload: the held-out rows with their
                # recording ids, the fit-side cloud, and this galaxy's centroids —
                # everything the session-quality analysis needs, off one build.
                np.savez(
                    dump_spacemap_eval,
                    eval_mapped=np.asarray(eval_mapped, dtype=np.float32),
                    eval_true=np.asarray(eval_true, dtype=np.float32),
                    eval_recs=np.asarray(embedding.get("_evalRecs", [])),
                    fit_x=np.asarray(
                        embedding.get("_fitX", np.zeros((0, 0))), dtype=np.float32
                    ),
                    fit_recs=np.asarray(embedding.get("_fitRecs", [])),
                    centroids=np.asarray(centre_vectors, dtype=np.float32),
                )
        space_map = embedding["map"]
        map_json = space_map.to_json() if hasattr(space_map, "to_json") else space_map
        map_file = None
        if hasattr(space_map, "to_f32"):
            # The RFF map's 123 k floats ship as a binary beside feature-space.json —
            # the JSON block keeps the layout and the apply formula, the app already
            # loads f32 assets, and a 1 MB JSON is nobody's friend.
            (out_dir / spacemap.RFF_FILE).write_bytes(space_map.to_f32())
            map_file = spacemap.RFF_FILE
        embedding_json = {
            "dims": space_dims,
            "mean": [float(v) for v in emb_mean],
            "std": [float(v) for v in emb_std],
            "standardisation": "z = (e - mean) / max(std, 1e-6)",
            **({"critic": embedding["critic"]} if embedding.get("critic") else {}),
            "map": map_json,
            "mapQuality": map_quality,
            **(
                {"sessionGate": space_map.session_gate}
                if getattr(space_map, "session_gate", None)
                else {}
            ),
        }
        if verbose:
            print(
                f"space map: median cosine {map_quality.get('medianCosine')} on held-out "
                f"recordings, nearest-centroid agreement "
                f"{map_quality.get('centroidAgreement')}",
                file=sys.stderr,
            )
            if not map_quality.get("accepted", True):
                # The number the whole phase stands on. Below the gate the map still
                # ships — flagged — and the browser keeps using the 28-d path, which is
                # the difference between an honest fallback and a confidently wrong one.
                print(
                    f"  WARNING: the 28-d -> 32-d space map is below its gate (median "
                    f"cosine {map_quality.get('medianCosine')} < "
                    f"{map_quality.get('target')}); it ships with accepted: false and "
                    "the browser will stay on the 28-d descriptor path",
                    file=sys.stderr,
                )

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
            **({"embedding": embedding_json} if embedding_json else {}),
        },
    )
    shutil.copyfile(inventory_path, out_dir / "inventory.json")
    _write_inventory_shards(out_dir, inventory)

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
        # Which groupings actually correspond to the geometry, each against its own label
        # permutation. `headline` says whether the best of them beats the recording-condition
        # controls, which is the difference between structure about birds and structure about
        # microphones.
        "relations": relation_summary,
        "clusterPlan": plan_report,
        # Absent unless `--deflate-source` ran: what the space had removed from it before
        # anything was clustered in it (`deflate_direction`).
        **({"deflation": deflation} if deflation else {}),
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
                f"correlation between {space_dims}-d cosine distance and 3D euclidean "
                "distance over random point pairs; 1.0 = distances fully meaningful"
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
        "space": space,
        **(
            {
                "embedding": {
                    "dims": space_dims,
                    "critic": embedding.get("critic") if embedding else None,
                    "mapQuality": map_quality,
                    # The per-cluster vector decision, stated where an auditor will look:
                    # `vector32` is the primary centroid (32-d standardised embedding);
                    # `vector` is the 28-d centroid over the same members, shipped so the
                    # browser's fallback path keeps working. The assets carry both.
                    "centroidVectors": (
                        "vector32 = 32-d embedding centroid (primary); vector = 28-d "
                        "centroid over the same members, for the pre-embedding fallback"
                    ),
                }
            }
            if space == "embed"
            else {}
        ),
        "kmeans": {"k": stats.k, "nInit": 10, "randomState": seed,
                   "inputSpace": f"standardised {space_dims}-d "
                   f"{'critic embedding' if space == 'embed' else 'descriptors'}"},
        "positions": {
            "format": "little-endian float32, 3*n, xyz",
            "bytes": stats.n_points * 3 * 4,
            "normalisation": "centred on the bbox midpoint, scaled so max|coord| = 1",
        },
        "pointFeatures": {
            "format": f"little-endian float32, {POINT_FEATURE_DIMS}*n, row-major",
            "bytes": stats.n_points * POINT_FEATURE_DIMS * 4,
            "dims": POINT_FEATURE_DIMS,
            "space": f"PCA of the standardised {space_dims}-d feature space, rows unit-normalised",
            "varianceRatioTotal": round(lo_variance, 4),
            "purpose": (
                "per-point render response only; the reported match still uses the "
                "cluster centroid vectors"
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
            "inventory/index.json",
            "syrinx-calibration.json",
            "feature-space.json",
            "positions.f32",
            "point-features.f32",
            "points.json",
            "centroids.json",
            *([map_file] if map_file else []),
        ],
        **(build_info or {}),
    }
    _write_json(out_dir / "manifest.json", manifest)
    return stats


def _write_inventory_shards(out_dir: Path, inventory: dict[str, Any]) -> None:
    """Write `inventory/<speciesId>.json` per species plus a tiny `inventory/index.json`.

    The whole-file `inventory.json` stays exactly what it was: the canonical checkpoint
    `learn` rewrites atomically and everything else reads. The shards are the app's lazy
    view of the same document, not a second source of truth. At 2 423 species / 12 724
    types the whole file is a multi-megabyte JSON the app parsed up front to fill a
    dropdown, while a selection, a composed phrase or a sung call only ever needs one
    bird — so the index carries the header (`refs`/`banks` included: a citation must
    never require opening a shard) plus one row per species, and each shard is the
    species' entry exactly as it appears in the whole file, syllables, songs, grammar
    and all.

    Idempotent: shards of species the inventory no longer holds are deleted, so a refit
    that drops a bird cannot leave its ghost fetchable beside the new whole file.
    """
    shard_dir = out_dir / "inventory"
    shard_dir.mkdir(exist_ok=True)
    rows = []
    live: set[str] = set()
    for sp in inventory.get("species", []):
        sid = sp["id"]
        live.add(sid)
        _write_json(shard_dir / f"{sid}.json", sp)
        rows.append(
            {
                "id": sid,
                "common": sp.get("common", sid),
                "bank": sp.get("bank", ""),
                "types": len(sp.get("syllables", [])),
                "songs": len(sp.get("songs", [])),
            }
        )
    for stale in shard_dir.glob("*.json"):
        if stale.name != "index.json" and stale.stem not in live:
            stale.unlink()
    _write_json(
        shard_dir / "index.json",
        {
            "version": inventory.get("version"),
            "note": inventory.get("note", ""),
            "refs": inventory.get("refs", {}),
            "banks": inventory.get("banks", {}),
            "species": rows,
        },
    )


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
