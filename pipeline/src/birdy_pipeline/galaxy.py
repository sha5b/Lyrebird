"""Descriptors -> 3D projection -> KMeans -> the generated asset set of contract 8.3.

Three projections are available (`--projection`). KMeans and the activation lookup work
on the standardised 28-d descriptors and never touch the 3D positions, so the choice of
projection is free as far as the client's cluster maths is concerned; what it changes is
whether *distance on screen* means anything. `faithfulness` measures exactly that.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors
from umap import UMAP

from . import features
from .corpus import Clip

UMAP_N_NEIGHBORS = 15
# 0.25 rather than 0.12: at 0.12 each syllable type packs into a knot a few pixels
# wide and the galaxy reads as empty space (docs/05-embedding-galaxy.md wants a dense
# continuous cloud). Between-cluster separation, which the activation lookup depends
# on, is preserved - see the cluster purity number the CLI prints.
UMAP_MIN_DIST = 0.25
UMAP_METRIC = "cosine"
TEMPERATURE = 0.12
K_CAP = 64

PROJECTIONS = ("umap", "pca", "cmds")
DEFAULT_PROJECTION = "cmds"  # most distance-faithful; see README "Galaxy shape"
FAITHFULNESS_PAIRS = 200_000
KNN_AGREEMENT_K = 10
# above this many points the full n x n cMDS matrix gets expensive in memory
# (n^2 * 8 bytes twice over), so fall back to landmark MDS
CMDS_FULL_MAX = 6000
CMDS_LANDMARKS = 800


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


def descriptors(clips: Sequence[Clip], verbose: bool = True) -> tuple[np.ndarray, list[Clip]]:
    """28-d descriptor per clip; clips with no voiced frame are dropped (8.2)."""
    rows: list[np.ndarray] = []
    kept: list[Clip] = []
    for i, clip in enumerate(clips):
        d = features.descriptor(clip.audio, clip.sample_rate)
        if d is None or not np.all(np.isfinite(d)):
            continue
        rows.append(d)
        kept.append(clip)
        if verbose and (i + 1) % 200 == 0:
            print(f"  descriptors {i + 1}/{len(clips)}", file=sys.stderr)
    if not rows:
        raise RuntimeError("no clip produced a descriptor")
    return np.stack(rows), kept


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
    info = {**info, "landmarks": m}
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
            pos, info = _classical_mds(cosine_distance_matrix(z) ** 2)
            info["mode"] = "full"
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


def normalise_positions(pos: np.ndarray) -> tuple[np.ndarray, float]:
    """Centre on the bounding-box midpoint, scale so max|coord| == 1 (8.3)."""
    out = pos - 0.5 * (pos.max(axis=0) + pos.min(axis=0))
    extent = float(np.max(np.abs(out)))
    if extent > 0.0:
        out = out / extent
    return out, extent


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
        "  projection   pearson  spearman   purity  knn10   meanR   notes",
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
        print(
            f"  {method:11} {f['pearson']:8.3f} {f['spearman']:9.3f} "
            f"{r['purity'] * 100:7.1f}% {r['knnAgreement'] * 100:5.1f}% "
            f"{r['meanRadius']:7.3f}   {note}{mark}",
            file=sys.stderr,
        )
    print(
        "  pearson/spearman = 28-d cosine distance vs 3D euclidean distance over "
        f"{next(iter(results.values()))['faithfulness']['pairs']} random pairs",
        file=sys.stderr,
    )
    print("", file=sys.stderr)


def default_k(clips: Sequence[Clip]) -> int:
    """Number of distinct syllable types (or labels, for a local corpus), cap 64."""
    types = {(c.species_id, c.syllable_id) for c in clips if c.syllable_id}
    if not types:
        types = {(c.species_id, "") for c in clips}
    return max(2, min(K_CAP, len(types)))


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
    members: Sequence[Clip], index: dict[tuple[str, str, str], dict[str, Any]]
) -> dict[str, Any]:
    """Majority syllable wins; fall back to majority song, then to the raw label."""
    keys = Counter(
        (c.species_id, c.syllable_id, c.song_id if not c.syllable_id else "")
        for c in members
    )
    syllable_keys = Counter({k: v for k, v in keys.items() if k[1]})
    key, _ = (syllable_keys or keys).most_common(1)[0]
    meta = index.get(key)
    if meta is None:
        meta = {
            "label": key[0] + (f" - {key[2]}" if key[2] else ""),
            "function": "",
            "confidence": "",
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
    clips: Sequence[Clip],
    inventory: dict[str, Any],
    out_dir: Path,
    inventory_path: Path,
    seed: int = 0,
    k: int | None = None,
    min_dist: float | None = None,
    projection: str = DEFAULT_PROJECTION,
    compare_projections: bool = True,
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

    if verbose:
        print(f"extracting descriptors for {len(clips)} clips", file=sys.stderr)
    x, kept = descriptors(clips, verbose=verbose)
    n_dropped = len(clips) - len(kept)

    mean = x.mean(axis=0)
    std = x.std(axis=0)  # population std, floored at lookup time
    z = features.standardise(x, mean, std)
    if not np.all(np.isfinite(z)):
        raise RuntimeError("standardised descriptors contain NaN/inf")

    k_final = int(k or default_k(kept))
    k_final = max(2, min(k_final, len(kept)))

    # KMeans first: the clustering is what the client's activation lookup uses, and it
    # runs on the standardised descriptors, so it is identical for every projection.
    if verbose:
        print(f"kmeans: k={k_final} on standardised descriptors", file=sys.stderr)
    km = KMeans(n_clusters=k_final, n_init=10, random_state=seed).fit(z)
    cluster_id = km.labels_.astype(int)

    type_of = [(c.species_id, c.syllable_id or f"song:{c.song_id}") for c in kept]
    purity = _purity(cluster_id, type_of, k_final)

    # Evaluate the projections. Distance faithfulness decides which one is honest;
    # kNN agreement says how tidy it looks. Purity cannot move (it never sees pos).
    wanted = list(PROJECTIONS) if compare_projections else [projection]
    if projection not in wanted:
        wanted.insert(0, projection)
    results: dict[str, dict[str, Any]] = {}
    for method in wanted:
        raw, info = project(z, method, seed=seed, min_dist=min_dist, verbose=verbose)
        if not np.all(np.isfinite(raw)):
            raise RuntimeError(f"projection {method} produced non-finite positions")
        candidate, candidate_extent = normalise_positions(raw)
        results[method] = {
            "positions": candidate,
            "extent": candidate_extent,
            "info": info,
            "faithfulness": faithfulness(z, candidate, seed=seed),
            "knnAgreement": round(knn_label_agreement(candidate, type_of), 4),
            "purity": round(_purity(cluster_id, type_of, k_final), 4),
            "meanRadius": round(float(np.mean(np.linalg.norm(candidate, axis=1))), 4),
        }

    if verbose:
        _print_projection_table(results, projection)

    chosen = results[projection]
    pos = chosen["positions"]
    extent = chosen["extent"]

    index = _inventory_index(inventory)
    items: list[dict[str, Any]] = []
    counts: list[int] = []
    for c in range(k_final):
        sel = np.nonzero(cluster_id == c)[0]
        members = [kept[i] for i in sel]
        info = label_cluster(members, index) if members else {
            "label": "", "speciesId": "", "syllableId": "",
            "function": "", "confidence": "", "refs": [],
        }
        position = pos[sel].mean(axis=0) if sel.size else np.zeros(3)
        items.append(
            {
                "id": c,
                **info,
                "position": [round(float(v), 6) for v in position],
                "vector": [round(float(v), 6) for v in km.cluster_centers_[c]],
                "count": int(sel.size),
            }
        )
        counts.append(int(sel.size))

    # --- write the asset set (8.3) ---
    (out_dir / "positions.f32").write_bytes(
        pos.astype("<f4", copy=False).ravel(order="C").tobytes()
    )
    _write_json(
        out_dir / "points.json",
        {
            "n": len(kept),
            "speciesId": [c.species_id for c in kept],
            "syllableId": [c.syllable_id for c in kept],
            "songId": [c.song_id for c in kept],
            "clusterId": [int(v) for v in cluster_id],
            "durations": [round(c.duration, 6) for c in kept],
            "source": [c.source for c in kept],
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
    durations = [c.duration for c in kept]
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
    )

    manifest = {
        "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": "birdy-pipeline",
        "contract": "docs/08-implementation.md v1",
        "inventoryVersion": inventory.get("version"),
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
        "kmeans": {"k": stats.k, "nInit": 10, "randomState": seed,
                   "inputSpace": "standardised 28-d descriptors"},
        "positions": {
            "format": "little-endian float32, 3*n, xyz",
            "bytes": stats.n_points * 3 * 4,
            "normalisation": "centred on the bbox midpoint, scaled so max|coord| = 1",
        },
        "durationSeconds": [round(stats.duration_range[0], 4), round(stats.duration_range[1], 4)],
        "clusterPurity": round(stats.purity, 4),
        "meanRadius": round(stats.spread, 4),
        "files": [
            "manifest.json",
            "inventory.json",
            "syrinx-calibration.json",
            "feature-space.json",
            "positions.f32",
            "points.json",
            "centroids.json",
        ],
        **(build_info or {}),
    }
    _write_json(out_dir / "manifest.json", manifest)
    return stats


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
