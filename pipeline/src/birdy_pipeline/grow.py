"""
Adding to a galaxy instead of replacing it.

A build re-places every point at once, which is correct and is also why the corpus can
only ever arrive as a discontinuity: harvest for ten minutes, rebuild, and the picture
you had been reading is gone and a different one is in its place. Nothing about the
science requires that. Classical MDS has an out-of-sample extension — a new point can be
placed from its distances to a fixed set of landmarks — so new audio can be *added* to
the arrangement that is already on screen, leaving every existing point exactly where it
was.

## What has to be frozen, and why all of it

The build applies three global transforms after the projection, and every one of them is
fitted to the corpus it saw:

1. **the landmark embedding** — landmark coordinates, their eigenvalues, and the mean
   squared distance from the corpus to each landmark, which is the centring term;
2. **`separate_clusters`** — each cluster is shifted by its own centre times
   `factor - 1`, so the shift depends on where the cluster's members were;
3. **`normalise_positions`** — a centring offset, a per-axis scale fitted to the 99.5th
   percentile, and a per-axis tanh knee fitted to the furthest point on that axis.

Re-deriving any of them from the grown corpus would move every point already drawn, which
is exactly the thing this module exists to avoid. So all three are captured at build time
and re-applied verbatim. The consequence is honest and worth stating: **an extension is
measured in the old corpus's frame.** New audio that falls outside the box the old build
was scaled to will be compressed by a tanh knee fitted before it existed, and clusters it
should have formed do not exist because the clustering is not re-run — it joins the
nearest existing knot instead.

That is the trade. Extension is cheap, continuous, and slightly wrong in a way that grows
with how much you add; a rebuild is expensive, discontinuous, and correct. `drift()` below
measures how wrong, so the interface can say when the arrangement has stopped describing
its own contents and a real build is due.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

#: Filename inside the built asset directory.
BASIS_FILE = "projection-basis.json"


def _unit_rows(z: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(z, axis=1, keepdims=True)
    return z / np.maximum(norms, 1.0e-12)


@dataclass
class ProjectionBasis:
    """Everything needed to place a new point in an existing galaxy's frame."""

    #: Unit-normalised landmark descriptors, (m, dims). Distances are measured to these.
    landmarks: np.ndarray
    #: (3, m) — the pseudo-inverse term of the landmark embedding.
    l_pinv: np.ndarray
    #: (m,) — mean squared distance from the build's corpus to each landmark.
    mean_sq: np.ndarray
    #: (k, 3) — the shift `separate_clusters` applied to each cluster.
    cluster_shift: np.ndarray
    #: (3,) — the centring offset `normalise_positions` removed.
    centre: np.ndarray
    #: (3,) — the per-axis scale it divided by.
    scale: np.ndarray
    #: Knee of the tail compressor, and the per-axis peak it was fitted to.
    knee: float
    peak: np.ndarray
    #: Feature-space standardisation, frozen so a new descriptor lands on the same axes.
    mean: np.ndarray
    std: np.ndarray

    def to_json(self) -> dict[str, Any]:
        return {
            "note": (
                "Frozen projection frame. Lets new points be added to this build without "
                "moving the ones already in it; see grow.py."
            ),
            "dims": int(self.landmarks.shape[1]),
            "landmarkCount": int(self.landmarks.shape[0]),
            "landmarks": self.landmarks.astype(float).tolist(),
            "lPinv": self.l_pinv.astype(float).tolist(),
            "meanSq": self.mean_sq.astype(float).tolist(),
            "clusterShift": self.cluster_shift.astype(float).tolist(),
            "centre": self.centre.astype(float).tolist(),
            "scale": self.scale.astype(float).tolist(),
            "knee": float(self.knee),
            "peak": self.peak.astype(float).tolist(),
            "mean": self.mean.astype(float).tolist(),
            "std": self.std.astype(float).tolist(),
        }

    @staticmethod
    def from_json(raw: dict[str, Any]) -> "ProjectionBasis":
        arr = lambda key: np.asarray(raw[key], dtype=np.float64)  # noqa: E731
        return ProjectionBasis(
            landmarks=arr("landmarks"),
            l_pinv=arr("lPinv"),
            mean_sq=arr("meanSq"),
            cluster_shift=arr("clusterShift"),
            centre=arr("centre"),
            scale=arr("scale"),
            knee=float(raw["knee"]),
            peak=arr("peak"),
            mean=arr("mean"),
            std=arr("std"),
        )

    def save(self, out_dir: Path) -> Path:
        path = Path(out_dir) / BASIS_FILE
        path.write_text(json.dumps(self.to_json()), encoding="utf-8")
        return path

    @staticmethod
    def load(out_dir: Path) -> "ProjectionBasis | None":
        path = Path(out_dir) / BASIS_FILE
        if not path.exists():
            return None
        return ProjectionBasis.from_json(json.loads(path.read_text(encoding="utf-8")))


def embed(basis: ProjectionBasis, x: np.ndarray, cluster_id: np.ndarray) -> np.ndarray:
    """
    Place raw descriptors into the basis's frame, in exactly the build's own order of
    operations: standardise, land against the landmarks, shift by the cluster's offset,
    centre, scale per axis, compress the tail.

    `cluster_id` is which existing knot each row has been assigned to — nearest centroid
    in the 28-d space, the same comparison the live matcher makes.
    """
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    z = (x - basis.mean) / np.maximum(basis.std, 1.0e-6)
    u = _unit_rows(z)

    # Out-of-sample landmark MDS, with the corpus's own centring term rather than one
    # re-measured over the new rows — that is what keeps the old points still.
    d2 = np.maximum(1.0 - u @ basis.landmarks.T, 0.0) ** 2
    pos = -0.5 * (d2 - basis.mean_sq[None, :]) @ basis.l_pinv.T

    k = basis.cluster_shift.shape[0]
    pos = pos + basis.cluster_shift[np.clip(cluster_id, 0, k - 1)]

    out = (pos - basis.centre) / np.maximum(basis.scale, 1.0e-9)
    return _soft_limit_frozen(out, basis.knee, basis.peak)


def _soft_limit_frozen(out: np.ndarray, knee: float, peak: np.ndarray) -> np.ndarray:
    """
    The build's tail compressor with its peak held fixed.

    The original fits `peak` to the furthest point it can see, which for an extension
    would be re-fitted per batch and would therefore place the same descriptor somewhere
    different depending on what arrived alongside it. Frozen, the curve is a function of
    the coordinate alone. A new point beyond the old peak lands past 1 and is clipped —
    rare, visible in `drift`, and the honest signal that the frame no longer fits.
    """
    out = out.copy()
    span = 1.0 - knee
    for axis in range(out.shape[1]):
        v = out[:, axis]
        mag = np.abs(v)
        far = mag > knee
        if not far.any():
            continue
        top = np.tanh((max(float(peak[axis]), knee + 1e-9) - knee) / span)
        excess = np.tanh((mag[far] - knee) / span) / max(top, 1.0e-9)
        v[far] = np.sign(v[far]) * (knee + span * np.minimum(excess, 1.0))
    return np.clip(out, -1.0, 1.0)


def assign_clusters(basis: ProjectionBasis, x: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """Nearest existing centroid by cosine, in the standardised 28-d space."""
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    z = (x - basis.mean) / np.maximum(basis.std, 1.0e-6)
    u = _unit_rows(z)
    c = _unit_rows(np.asarray(centroids, dtype=np.float64))
    return np.argmax(u @ c.T, axis=1).astype(int)


def drift(basis: ProjectionBasis, x: np.ndarray, centroids: np.ndarray) -> dict[str, Any]:
    """
    How badly the frozen frame fits the audio being added to it.

    Three symptoms, because they fail independently. `unmatched` is the share of new
    points whose nearest existing knot is further than any real member of a knot should
    be — sounds the corpus has no cluster for, which no amount of re-placing fixes and
    only a rebuild will. `clipped` is the share landing outside the box the old build was
    scaled to. `meanCosine` is how close the new material sits to what is already there.
    """
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    z = (x - basis.mean) / np.maximum(basis.std, 1.0e-6)
    u = _unit_rows(z)
    c = _unit_rows(np.asarray(centroids, dtype=np.float64))
    sim = u @ c.T
    best = sim.max(axis=1)
    ids = np.argmax(sim, axis=1).astype(int)
    pos = embed(basis, x, ids)
    return {
        "points": int(len(u)),
        "meanCosine": round(float(best.mean()), 4),
        "unmatched": round(float((best < 0.62).mean()), 4),
        "clipped": round(float((np.abs(pos) >= 0.999).any(axis=1).mean()), 4),
    }
