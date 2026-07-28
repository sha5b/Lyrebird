"""Descriptors -> UMAP(3D) -> KMeans -> the generated asset set of contract 8.3."""

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
    build_info: dict[str, Any] | None = None,
    verbose: bool = True,
) -> GalaxyStats:
    # min_dist is purely visual: KMeans and the activation vectors live in the
    # standardised 28-d feature space, never in these 3D positions, so loosening the
    # packing costs nothing in cluster fidelity (measured: purity identical at 0.25,
    # 0.5 and 0.8).
    umap_min_dist = UMAP_MIN_DIST if min_dist is None else float(min_dist)
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

    # 8.3 fixes n_neighbors = 15; it is only clamped for corpora too small for that,
    # which cannot happen for the synthetic source (1000+ points).
    n_neighbors = min(UMAP_N_NEIGHBORS, max(2, len(kept) - 1))
    if verbose:
        print(
            f"umap: {z.shape} -> 3d (n_neighbors={n_neighbors}, "
            f"min_dist={umap_min_dist}, metric={UMAP_METRIC}, seed={seed})",
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

    # centre on the bounding-box midpoint, then scale so max|coord| == 1 (8.3)
    mid = 0.5 * (pos.max(axis=0) + pos.min(axis=0))
    pos = pos - mid
    extent = float(np.max(np.abs(pos)))
    if extent > 0.0:
        pos = pos / extent
    if not np.all(np.isfinite(pos)):
        raise RuntimeError("UMAP produced non-finite positions")

    if verbose:
        print(f"kmeans: k={k_final} on standardised descriptors", file=sys.stderr)
    km = KMeans(n_clusters=k_final, n_init=10, random_state=seed).fit(z)
    cluster_id = km.labels_.astype(int)

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

    # cluster purity: how well the clusters correspond to syllable types
    type_of = [c.syllable_id or f"song:{c.song_id}" for c in kept]
    keyed = [(c.species_id, t) for c, t in zip(kept, type_of)]
    majority = 0
    for c in range(k_final):
        members = [keyed[i] for i in np.nonzero(cluster_id == c)[0]]
        if members:
            majority += Counter(members).most_common(1)[0][1]
    purity = majority / len(kept)
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
        "umap": {
            "nComponents": 3,
            "nNeighbors": n_neighbors,
            "minDist": umap_min_dist,
            "metric": UMAP_METRIC,
            "randomState": seed,
            "inputSpace": "standardised 28-d descriptors",
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
