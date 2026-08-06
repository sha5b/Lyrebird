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
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Callable

import numpy as np

#: Filename inside the built asset directory.
BASIS_FILE = "projection-basis.json"

#: The route mark carried by a point rendered from a newly fitted type and grown in without
#: a rebuild. A build-placed point carries `""`. **These are not the same measurement**: a
#: build re-fits the projection around every point it places, while this one is placed
#: through a basis frozen before its type existed, so purity and coverage computed over a
#: mixture of the two are an average of two different things. Recording the route is what
#: lets a reader hold it constant instead.
ROUTE_FIT = "fit"

#: Filename next to the grown assets holding the pending pool of unassigned novel
#: points — new sounds waiting for enough company to found a knot of their own.
NOVEL_POOL_FILE = "novel-pool.json"

#: How many unassigned novel points it takes to found a knot. Below this a new sound
#: is a point in no cluster (clusterId -1), not a forced member of the nearest existing
#: one — the silent misassignment docs/09 §9.2b exists to end. 8 mirrors the critic's
#: own typing floor: `fit_novelty` asks KMeans for one type per 8 syllables, so a group
#: smaller than that is not a "type" anywhere else in the pipeline either.
MIN_NOVEL_CLUSTER = 8

#: Membership radius for founding that knot: cosine to the group's (iterated) centre in
#: the standardised space. Measured on 219 genuinely-novel flagged syllables of
#: perisoreus_infaustus — a species the critic never trained on — grouped by their
#: learn-types: a real group's cohesion is 0.81..0.97, so 0.70 admits the core of every
#: one of them while staying well above what two different new sounds share. The
#: novelty boundary itself (0.895 cosine at the calibrated 5 % false-positive rate)
#: plays no part here — everything in the pool is already past it. This radius decides
#: what counts as *one* new sound, not whether the sound is new.
NOVEL_CLUSTER_MIN_COSINE = 0.70

#: A founded knot must also hold together at this mean cosine to its own centre, or it
#: is a bag of unrelated oddballs and stays in the pool. The loosest genuine group in
#: the measurement above held 0.81.
NOVEL_CLUSTER_MIN_COHESION = 0.75


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
    #: Which dissimilarity the build's cMDS was fitted to (`galaxy.MDS_METRICS`).
    #: **A basis written before 2026-08-03 carries none and is `cosine` by definition** —
    #: that was the only metric there was. Recorded rather than assumed because measuring
    #: a new point's distance with the other one lands it somewhere plausible and wrong,
    #: and nothing downstream could tell.
    metric: str = "cosine"

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
            "metric": self.metric,
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
            metric=str(raw.get("metric", "cosine")),
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
    in the build's feature space, the same comparison the live matcher makes.
    """
    x = np.atleast_2d(np.asarray(x, dtype=np.float64))
    z = (x - basis.mean) / np.maximum(basis.std, 1.0e-6)
    u = _unit_rows(z)

    # Out-of-sample landmark MDS, with the corpus's own centring term rather than one
    # re-measured over the new rows — that is what keeps the old points still. The
    # dissimilarity is the build's own (import is local: galaxy imports grow back).
    from .galaxy import mds_squared_distances

    d2 = mds_squared_distances(u, basis.landmarks, basis.metric)
    pos = -0.5 * (d2 - basis.mean_sq[None, :]) @ basis.l_pinv.T

    k = basis.cluster_shift.shape[0]
    # A point in no cluster — and a point in a knot founded *after* the basis was
    # frozen, which has no shift entry — is not pushed anywhere. `np.clip` alone would
    # hand every such point cluster 0's shift and drag them all into one knot; this is
    # the same guard `separate_clusters` applies at build time, and the new knots'
    # members were themselves placed with zero shift, so future members placed the same
    # way land consistently.
    cluster_id = np.asarray(cluster_id)
    valid = (cluster_id >= 0) & (cluster_id < k)
    pos = pos + np.where(valid[:, None], basis.cluster_shift[np.clip(cluster_id, 0, k - 1)], 0.0)

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
    """Nearest existing centroid by cosine, in the basis's standardised space.

    Space-agnostic by construction: `x` is standardised by the basis's own moments, so
    the caller hands over rows of whichever space the build clustered in — 28-d
    descriptors for a descriptor build, 32-d embeddings (the centroids' `vector32`) for
    an embed build — and the comparison is the same cosine the live matcher makes.
    """
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


# --- adding to a built galaxy -----------------------------------------------------------


def _read_f32(path: Path, cols: int) -> np.ndarray:
    return np.frombuffer(path.read_bytes(), dtype="<f4").reshape(-1, cols).astype(np.float64)


def _write_f32(path: Path, rows: np.ndarray) -> None:
    path.write_bytes(rows.astype("<f4", copy=False).ravel(order="C").tobytes())


# --- which fitted types the galaxy has no knot for ---------------------------------------


def unbuilt_types(
    inventory: dict[str, Any], centroids: dict[str, Any]
) -> list[tuple[str, str]]:
    """The `(speciesId, syllableId)` pairs the fitted inventory has and the galaxy does not.

    **Two callers must agree on this set or they disagree about what needs doing.** The
    learning loop uses it to decide a rebuild is owed (`server._unbuilt_types`), and
    `render_unbuilt` uses it as the render queue. Two copies of the rule would drift into
    two different answers to "is this galaxy current?", so there is one.

    Only a centroid that names a syllable counts as placing it. A knot founded from the
    novel pool carries an empty `syllableId` — it is a sound nobody has named — so it
    places nothing, which is what keeps a founded-but-unnamed knot from being mistaken for
    coverage of a fitted type.
    """
    placed = {
        (c.get("speciesId"), c.get("syllableId"))
        for c in centroids.get("items", [])
        if c.get("syllableId")
    }
    return [
        (sp["id"], y["id"])
        for sp in inventory.get("species", [])
        for y in sp.get("syllables", [])
        if (sp["id"], y["id"]) not in placed
    ]


def render_unbuilt(
    out_dir: Path,
    inventory_path: Path,
    *,
    calibration: Any = None,
    variants: int = 24,
    seed: int = 0,
    embedder: Callable[[Any], np.ndarray | None] | None = None,
    stamp: str | None = None,
    verbose: bool = True,
    should_stop: Callable[[], bool] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Render the fitted types this galaxy has no knot for, and grow them in.

    **This is synthesis at fit time rather than at build time.** Today a type that `learn`
    has just fitted has no position until the next full build, because the synthetic source
    renders the whole inventory and that runs inside `build`. Everything needed to place one
    sooner already existed: the projection basis is frozen precisely so a point can be
    placed out-of-sample, `unbuilt_types` already names which types are missing, and
    `extend_build` already appends points and founds knots. This joins them.

    **Rendering only the missing types is the whole economy of it.** A build renders every
    syllable in the inventory; this renders the handful that just appeared, and
    `synthetic_corpus(only=...)` keeps their audio byte-identical to what a full render
    would have produced.

    Three things this does not do, and they are the honest cost. The projection is *not*
    refitted, so a type arrives in a frame fitted before it existed — `drift` remains the
    measurement of how much that matters and the rebuild trigger stays. Knots founded here
    carry `route: "fit"` and their points carry the same mark, so nobody averages a
    fit-placed purity against a build-placed one without seeing that they differ. And a
    galaxy with no projection basis cannot be grown at all, which `extend_build` says.
    """
    from . import galaxy as galaxy_mod
    from .corpus import load_inventory, synthetic_corpus

    out_dir = Path(out_dir)
    inventory = load_inventory(Path(inventory_path))
    centroids = json.loads((out_dir / "centroids.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    pairs = unbuilt_types(inventory, centroids)
    deferred: list[tuple[str, str]] = []
    if limit is not None and len(pairs) > limit:
        # Say what was left behind. A cap that quietly truncates reads afterwards as "all
        # the new types are placed" when they are not, and the next reader has no way to
        # tell the difference from the assets.
        deferred = pairs[limit:]
        pairs = pairs[:limit]
        if verbose:
            print(
                f"rendering {len(pairs)} of {len(pairs) + len(deferred)} unbuilt types; "
                f"{len(deferred)} deferred to the next pass",
                file=sys.stderr,
            )
    if not pairs:
        return {"types": [], "rendered": 0, "added": 0, "deferred": []}

    clips = synthetic_corpus(
        inventory,
        calibration,
        variants=variants,
        seed=seed,
        verbose=verbose,
        should_stop=should_stop,
        only=set(pairs),
    )
    if not clips:
        return {"types": [], "rendered": 0, "added": 0, "deferred": _fmt(deferred)}

    new = galaxy_mod.descriptors(
        clips, verbose=verbose, should_stop=should_stop, embedder=embedder
    )
    space = manifest.get("space", "descriptor")
    descriptors28: np.ndarray | None = None
    if space == "embed":
        if new.embeddings is None:
            raise RuntimeError(
                "this galaxy was built in the embedding space, so rendering into it needs "
                "an embedder — pass one, or rebuild the galaxy in the descriptor space"
            )
        # A clip the critic could not embed is a NaN row, which the embed-space build
        # excludes and counts. Growing one in would place a point from nothing.
        keep = np.all(np.isfinite(new.embeddings), axis=1)
        if not keep.any():
            raise RuntimeError("no rendered clip could be embedded; nothing to grow in")
        descriptors28 = np.asarray(new.x, dtype=np.float64)[keep]
        new = galaxy_mod.PointSet(
            x=np.asarray(new.embeddings, dtype=np.float64)[keep],
            species_id=[v for v, k in zip(new.species_id, keep) if k],
            syllable_id=[v for v, k in zip(new.syllable_id, keep) if k],
            song_id=[v for v, k in zip(new.song_id, keep) if k],
            duration=[v for v, k in zip(new.duration, keep) if k],
            source=[v for v, k in zip(new.source, keep) if k],
        )
    new.route = [ROUTE_FIT] * len(new)

    result = extend_build(
        out_dir,
        new,
        stamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        verbose=verbose,
        inventory_path=Path(inventory_path),
        descriptors28=descriptors28,
    )
    result["types"] = _fmt(pairs)
    result["rendered"] = len(clips)
    result["deferred"] = _fmt(deferred)
    return result


def _fmt(pairs: Sequence[tuple[str, str]]) -> list[str]:
    return [f"{sp}/{sy}" for sp, sy in pairs]


# --- the novel pool: new sounds waiting for a quorum ------------------------------------


def _load_pool(out_dir: Path, points: dict[str, Any]) -> list[dict[str, Any]]:
    """The pending unassigned novel points, validated against the points on disk.

    Every entry names a row of `points.json` that is still unassigned. Anything else —
    an index past the end, or a row that has since gained a cluster — means the assets
    were *rebuilt* since the pool was written, and the entry is dropped: a rebuild
    re-clusters the whole corpus, novel points included, so a pool fitted to the old
    point order has nothing left to say.
    """
    path = Path(out_dir) / NOVEL_POOL_FILE
    if not path.exists():
        return []
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        entries = blob.get("entries", [])
    except (OSError, ValueError):
        return []
    cluster_id = points.get("clusterId", [])
    return [
        e for e in entries
        if 0 <= int(e.get("point", -1)) < len(cluster_id)
        and cluster_id[int(e["point"])] == -1
    ]


def _save_pool(out_dir: Path, entries: list[dict[str, Any]]) -> None:
    path = Path(out_dir) / NOVEL_POOL_FILE
    if not entries:
        path.unlink(missing_ok=True)
        return
    path.write_text(
        json.dumps({"version": 1, "entries": entries}, indent=1), encoding="utf-8"
    )


def _novel_groups(
    u: np.ndarray,
    min_cosine: float = NOVEL_CLUSTER_MIN_COSINE,
    quorum: int = MIN_NOVEL_CLUSTER,
    cohesion_floor: float = NOVEL_CLUSTER_MIN_COHESION,
) -> list[tuple[np.ndarray, np.ndarray, float]]:
    """Cohesive groups of at least `quorum` pending points: greedy seed + radius.

    Seeds are tried in pool order — deterministic, which is what makes repeated grows
    idempotent. A bare radius around the seed is unstable against an eccentric seed
    (measured: one genuine 108-member novel group averaged 0.85 cosine to its own mean
    but 0.34 to its first member), so the centre is re-fit to the members and the
    radius re-applied, a few times: one spherical-kmeans step per seed, which moves the
    centre off the seed and onto the group. What survives must also clear the cohesion
    floor, or eight unrelated oddballs would found a knot that means nothing.
    """
    consumed = np.zeros(len(u), dtype=bool)
    groups: list[tuple[np.ndarray, np.ndarray, float]] = []
    for i in range(len(u)):
        if consumed[i]:
            continue
        centre = u[i]
        members = np.zeros(0, dtype=int)
        for _ in range(4):
            sim = u @ centre
            members = np.nonzero((sim >= min_cosine) & ~consumed)[0]
            if not len(members):
                break
            new_centre = _unit_rows(u[members].mean(axis=0, keepdims=True))[0]
            if np.allclose(new_centre, centre, atol=1e-9):
                break
            centre = new_centre
        if len(members) < quorum:
            continue
        cohesion = float((u[members] @ centre).mean())
        if cohesion < cohesion_floor:
            continue
        groups.append((members, centre, cohesion))
        consumed[members] = True
    return groups


def extend_build(
    out_dir: Path,
    new: Any,
    stamp: str,
    verbose: bool = True,
    inventory_path: Path | None = None,
    descriptors28: np.ndarray | None = None,
) -> dict[str, Any]:
    """
    Append a `PointSet` to the galaxy already in `out_dir`, leaving it otherwise alone.

    Every existing point keeps the coordinates it had. New points are assigned to the
    nearest existing knot in the 28-d space — the same comparison the live matcher makes —
    and placed through the frozen frame. Nothing is re-clustered and nothing is re-fitted,
    which is what makes this cheap and what makes `drift` necessary.

    The exception is a point whose observation was flagged `novel` at ingest (docs/09
    §9.2b use 2). Force-assigning it to the nearest knot is exactly the silent
    misassignment the flag exists to end, so it joins the cloud unassigned
    (`clusterId -1`, which the renderer already tolerates from the density-clustering
    path) and waits in a persisted pool (`novel-pool.json`). Once the pool holds a
    quorum of mutually cohesive novel points — `MIN_NOVEL_CLUSTER` of them, one sound
    heard enough times to be a type and not an accident — they found a knot of their
    own: appended to `centroids.json` as "unheard syllable", species unknown,
    confidence `unlabelled`, because detecting that a sound is new is not knowing what
    it means (§8.5). The pool persists between runs and a founded knot leaves it, so
    repeated grows are deterministic and idempotent.

    `descriptors28` is the new rows' 28-d descriptors, only so a knot founded in an
    embed-space galaxy can also carry the fallback `vector` the browser's pre-embedding
    path reads — the knot's primary vector is computed from `new.x` itself.

    The generation counter is what lets the interface animate an arrival: every point
    carries the build it joined in, so the renderer can tell which marks are new without
    diffing two asset sets.
    """
    out_dir = Path(out_dir)
    basis = ProjectionBasis.load(out_dir)
    if basis is None:
        raise RuntimeError(
            "this galaxy has no projection basis, so it can only be rebuilt, not grown. "
            "Build it again — the basis is written by every cMDS build."
        )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    points = json.loads((out_dir / "points.json").read_text(encoding="utf-8"))
    centroids = json.loads((out_dir / "centroids.json").read_text(encoding="utf-8"))
    items = centroids["items"]
    # Which per-cluster vector the assignment compares against. An embed-space build
    # clustered in the critic's 32-d space and ships it as `vector32`; its `vector` is a
    # 28-d fallback for the browser and would place new points in the wrong space. The
    # basis's landmark width is the ground truth for what `new.x` must contain.
    space = manifest.get("space", "descriptor")
    dims = int(basis.landmarks.shape[1])
    # **Through the one reader that knows both layouts.** Since 2026-08-01 a build ships the
    # per-cluster arrays in `centroid-vectors.f32` and leaves no `vector` / `vector32` /
    # `featuresLo` key on the item at all. Reading them off the item therefore found nothing
    # on every asset set built since — an embed-space galaxy was reported as carrying no
    # `vector32` and the operator was told to rebuild it with `--space embed`, which would
    # have written the same sidecar again and failed the same way. `galaxy.centroid_vectors`
    # reads the sidecar and still reads an older inline build.
    from .galaxy import CENTROID_VECTORS_NAME, centroid_vectors

    blocks = {k: np.asarray(v, dtype=np.float64) for k, v in
              centroid_vectors(out_dir, centroids).items()}
    #: How many knots the galaxy had before this grow — the boundary between rows that come
    #: from the sidecar and rows founded below.
    n_knots_before = len(items)
    want = "vector32" if space == "embed" else "vector"
    if want not in blocks:
        raise RuntimeError(
            f"this galaxy's centroids carry no {want}, in centroids.json or in "
            f"{CENTROID_VECTORS_NAME} — it cannot be grown, only rebuilt"
        )
    cent = blocks[want]

    x = np.asarray(new.x, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != dims:
        raise RuntimeError(
            f"new descriptors are {x.shape}, expected (n, {dims})"
            + (
                " — this is an embed-space galaxy, so new rows must be critic "
                "embeddings, not 28-d descriptors (see cmd_grow)"
                if space == "embed"
                else ""
            )
        )

    report = drift(basis, x, cent)
    ids = assign_clusters(basis, x, cent)

    # Points backed by an observation flagged `novel` at ingest are *not* force-assigned:
    # that silent assignment to the nearest knot is exactly what the flag exists to end
    # (docs/09 §9.2b). They join the cloud unassigned and wait in the pool below. `None`
    # means the corpus was never scored — the window-level grow and every build path —
    # and an unmeasured point is not a novel one.
    novel_flags = (
        [bool(v) for v in new.novel] if new.novel is not None else [False] * len(x)
    )
    if any(novel_flags):
        ids = ids.copy()
        ids[np.asarray(novel_flags)] = -1

    # Rows rendered from a newly fitted type found a knot of their own rather than joining
    # the nearest existing one. **They are held back for the opposite reason to the novel
    # pool.** A pooled point is anonymous — the detector knows only that it is unlike
    # everything known — so it must wait for `MIN_NOVEL_CLUSTER` of its kind to prove it is
    # a type at all. A fitted type arrives already named and already grouped: `learn` gave
    # it an id and it cleared that module's own floor of `OBS_PER_TYPE` observations to
    # exist. Re-testing it here would ask it to prove by a looser rule what it proved
    # upstream by a stricter one, so the quorum does not apply and grouping is by label
    # rather than by discovered cohesion.
    route_flags = [str(v) for v in new.route] if new.route is not None else [""] * len(x)
    placed_types = {
        (c.get("speciesId"), c.get("syllableId"))
        for c in items
        if c.get("syllableId")
    }
    fit_flags = [
        r == ROUTE_FIT and (sp, sy) not in placed_types
        for r, sp, sy in zip(route_flags, new.species_id, new.syllable_id)
    ]
    if any(fit_flags):
        ids = ids.copy()
        ids[np.asarray(fit_flags)] = -1
    pos_new = embed(basis, x, ids)

    n_old = int(points["n"])
    pos_all = np.concatenate([_read_f32(out_dir / "positions.f32", 3), pos_new])

    z_new = (x - basis.mean) / np.maximum(basis.std, 1.0e-6)
    u_new = _unit_rows(z_new)

    # Per-point features come from the same frozen PCA the build shipped: the centroids
    # carry their own 8-d rows, so a new point's is the unit-normalised projection onto
    # the basis those rows span. Approximating it as its cluster's row would light every
    # member of a knot identically and undo the per-point response entirely.
    #
    # This read has the same sidecar dependency as the centroid vectors above, but it failed
    # *quietly*: `items[0].get("featuresLo")` is absent on every sidecar build, so `lo_dims`
    # came out 0 and the whole per-point feature update was skipped without a word. The
    # grown points then carried no 8-d row and lit identically, which is the exact outcome
    # the comment above says this block exists to prevent.
    lo_path = out_dir / "point-features.f32"
    lo_cent = blocks.get("featuresLo")
    lo_dims = 0 if lo_cent is None else int(lo_cent.shape[1])
    lo_new: np.ndarray | None = None
    if lo_dims and lo_path.exists():
        z_cent = (cent - basis.mean) / np.maximum(basis.std, 1.0e-6)
        # Least-squares map from the standardised space onto the shipped 8-d rows,
        # fitted on the centroids, which are the only paired examples the assets carry.
        proj, *_ = np.linalg.lstsq(z_cent, lo_cent, rcond=None)
        lo_new = z_new @ proj
        lo_new /= np.maximum(np.linalg.norm(lo_new, axis=1, keepdims=True), 1.0e-12)
        _write_f32(lo_path, np.concatenate([_read_f32(lo_path, lo_dims), lo_new]))

    _write_f32(out_dir / "positions.f32", pos_all)

    generation = int(manifest.get("generation", 0)) + 1
    grown = list(points.get("generation") or [0] * n_old) + [generation] * len(x)
    points.update(
        {
            "n": n_old + int(len(x)),
            "speciesId": list(points["speciesId"]) + list(new.species_id),
            "syllableId": list(points["syllableId"]) + list(new.syllable_id),
            "songId": list(points["songId"]) + list(new.song_id),
            "clusterId": list(points["clusterId"]) + [int(v) for v in ids],
            "durations": list(points["durations"]) + [float(v) for v in new.duration],
            "source": list(points["source"]) + list(new.source),
            "generation": grown,
            # Which route placed each point. Existing rows are build-placed and say so
            # with `""`, so the column is never ambiguous between "came by a build" and
            # "written before the column existed" — a galaxy grown by this path always
            # rewrites the whole column.
            "route": list(points.get("route") or [""] * n_old) + route_flags,
        }
    )

    # The novel pool: this batch's unassigned points join the ones earlier grows parked,
    # and a quorum of mutually cohesive ones founds a knot of its own. Entries carry the
    # point's unit-normalised standardised vector so grouping needs nothing but the pool,
    # and — when the caller handed over 28-d descriptors — the standardised 28-d row, so
    # a knot founded in an embed-space galaxy can still ship the fallback `vector` the
    # browser's pre-embedding path reads.
    z28_new: np.ndarray | None = None
    if descriptors28 is not None:
        d28 = np.atleast_2d(np.asarray(descriptors28, dtype=np.float64))
        if d28.shape[0] != len(x):
            raise RuntimeError(
                f"descriptors28 has {d28.shape[0]} rows for {len(x)} new points"
            )
        fs_path = out_dir / "feature-space.json"
        if fs_path.exists():
            fs = json.loads(fs_path.read_text(encoding="utf-8"))
            fmean = np.asarray(fs["mean"], dtype=np.float64)
            fstd = np.asarray(fs["std"], dtype=np.float64)
            if fmean.size == d28.shape[1]:
                z28_new = (d28 - fmean) / np.maximum(fstd, 1.0e-6)
    pool = _load_pool(out_dir, points)
    for i, flag in enumerate(novel_flags):
        if not flag:
            continue
        entry: dict[str, Any] = {
            "point": n_old + i,
            "vector": [round(float(v), 6) for v in u_new[i]],
        }
        if z28_new is not None:
            entry["vector28"] = [round(float(v), 6) for v in z28_new[i]]
        pool.append(entry)

    founded: list[int] = []

    # --- fitted types found their own, named knots ---------------------------------------
    #
    # Grouped by label rather than by cohesion, which is the whole difference from the pool
    # below: these points already know what they are. The knot is therefore *named* — it
    # takes the same label, function, confidence and refs a rebuild would give it, from the
    # same `_inventory_index` — where a pool-founded knot can only be called "unheard
    # syllable" because nobody knows what it is.
    fit_founded: list[str] = []
    if any(fit_flags):
        from .galaxy import _inventory_index, function_class

        inv_doc: dict[str, Any] = {}
        if inventory_path is not None and Path(inventory_path).exists():
            inv_doc = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
        index = _inventory_index(inv_doc)

        by_type: dict[tuple[str, str], list[int]] = {}
        for i, flag in enumerate(fit_flags):
            if flag:
                by_type.setdefault(
                    (new.species_id[i], new.syllable_id[i]), []
                ).append(i)

        for (sp_id, sy_id), local_idx in sorted(by_type.items()):
            point_idx = [n_old + i for i in local_idx]
            new_id = len(items)
            for idx in point_idx:
                points["clusterId"][idx] = new_id
            member_pos = pos_all[np.asarray(point_idx, dtype=int)]
            position = member_pos.mean(axis=0)
            rows = _unit_rows(u_new[np.asarray(local_idx, dtype=int)])
            centre = rows.mean(axis=0)
            centre_u = centre / max(float(np.linalg.norm(centre)), 1.0e-12)
            # The same statistic the pool's `cohesion_floor` is measured against, so the
            # field means one thing across both founding routes and a reader can compare
            # a fit-founded knot's tightness with a pool-founded one's.
            cohesion = float(np.mean(rows @ centre_u))
            meta = index.get((sp_id, sy_id, ""), {})
            item = {
                "id": new_id,
                "label": meta.get("label", f"{sp_id} - {sy_id}"),
                "speciesId": sp_id,
                "syllableId": sy_id,
                "function": meta.get("function", ""),
                "confidence": meta.get("confidence", "") or "unlabelled",
                "refs": list(meta.get("refs", [])),
                "position": [round(float(v), 6) for v in position],
                "functionClass": function_class(meta.get("function", "")),
                "count": len(point_idx),
                "meanDuration": round(
                    float(np.mean([points["durations"][i] for i in point_idx])), 4
                ),
                "radius": round(
                    float(np.mean(np.linalg.norm(member_pos - position, axis=1))), 4
                ),
                "cohesion": round(cohesion, 4),
                "speciesMix": [{"speciesId": sp_id, "count": len(point_idx)}],
                "sources": {
                    s: int(n)
                    for s, n in Counter(points["source"][i] for i in point_idx).most_common()
                },
                # Which route founded the knot, for the same reason each point carries it:
                # this centroid was placed in a frame fitted before its type existed, and a
                # reader comparing knot geometry across generations has to be able to see
                # that. A rebuild re-fits and drops the mark.
                "route": ROUTE_FIT,
            }
            if space == "embed":
                item["vector32"] = [round(float(v), 6) for v in centre_u]
                if z28_new is not None:
                    v28 = z28_new[np.asarray(local_idx, dtype=int)].mean(axis=0)
                    item["vector"] = [round(float(v), 6) for v in v28]
            else:
                item["vector"] = [round(float(v), 6) for v in centre_u]
            if lo_new is not None:
                item["featuresLo"] = [
                    round(float(v), 6)
                    for v in _unit_rows(
                        lo_new[np.asarray(local_idx, dtype=int)].mean(axis=0, keepdims=True)
                    )[0]
                ]
            items.append(item)
            founded.append(new_id)
            fit_founded.append(f"{sp_id}/{sy_id}")
        if fit_founded and verbose:
            print(
                f"{len(fit_founded)} knot(s) founded from newly fitted types: "
                + ", ".join(fit_founded[:6])
                + ("..." if len(fit_founded) > 6 else ""),
                file=sys.stderr,
            )

    from_pool: list[int] = []
    if pool:
        vectors = _unit_rows(np.asarray([e["vector"] for e in pool], dtype=np.float64))
        groups = _novel_groups(vectors)
        consumed: set[int] = set()
        for members, centre, cohesion in groups:
            point_idx = [int(pool[m]["point"]) for m in members]
            consumed.update(int(m) for m in members)
            # `len(items)`, not `len(items) + len(founded)`. A knot's id *is* its position
            # in `items` — `assign_clusters` argmaxes over the centroid array and the count
            # fixup below indexes it positionally — and `items` is appended once per knot
            # in this same loop, so adding `founded` counted every previous knot twice.
            # Founding three knots in one grow allocated ids 5, 7, 9 for the knots at
            # positions 5, 6, 7, after which every count landed on the wrong knot.
            new_id = len(items)
            for idx in point_idx:
                points["clusterId"][idx] = new_id
            member_pos = pos_all[np.asarray(point_idx, dtype=int)]
            position = member_pos.mean(axis=0)
            member_sources = Counter(points["source"][i] for i in point_idx)
            item: dict[str, Any] = {
                "id": new_id,
                # "Unheard", not a name: the detector measured that this sound is far
                # from every known type, which is all anyone knows about it (docs/09
                # §9.2b). It stays `unlabelled` — real acoustics, no documented
                # function (§8.5).
                "label": "unheard syllable",
                "speciesId": "",
                "syllableId": "",
                "function": "",
                "confidence": "unlabelled",
                "refs": [],
                "position": [round(float(v), 6) for v in position],
                "functionClass": "unclassified",
                "count": len(members),
                "meanDuration": round(
                    float(np.mean([points["durations"][i] for i in point_idx])), 4
                ),
                "radius": round(
                    float(np.mean(np.linalg.norm(member_pos - position, axis=1))), 4
                ),
                "cohesion": round(float(cohesion), 4),
                "speciesMix": [
                    {"speciesId": sp, "count": int(n)}
                    for sp, n in Counter(
                        points["speciesId"][i] for i in point_idx
                    ).most_common(3)
                    if sp
                ],
                "sources": {s: int(n) for s, n in member_sources.most_common()},
            }
            if space == "embed":
                item["vector32"] = [round(float(v), 6) for v in centre]
                v28 = [pool[m].get("vector28") for m in members]
                if all(v is not None for v in v28):
                    item["vector"] = [
                        round(float(v), 6)
                        for v in np.asarray(v28, dtype=np.float64).mean(axis=0)
                    ]
            else:
                item["vector"] = [round(float(v), 6) for v in centre]
            if lo_new is not None:
                # Members that arrived in this batch have their 8-d rows in `lo_new`;
                # older ones are already in the file that was just appended. Either
                # way the rows exist, so the knot lights its members individually
                # rather than not at all.
                lo_all = _read_f32(lo_path, lo_dims)
                item["featuresLo"] = [
                    round(float(v), 6)
                    for v in _unit_rows(lo_all[np.asarray(point_idx, dtype=int)].mean(axis=0, keepdims=True))[0]
                ]
            items.append(item)
            founded.append(new_id)
            from_pool.append(new_id)
        pool = [e for j, e in enumerate(pool) if j not in consumed]
        # `from_pool`, not `founded`: since fitted types found knots above, `founded` also
        # holds named ones, and reporting those as "unheard syllable" would say the
        # opposite of the truth about a knot that arrived with a name.
        if from_pool and verbose:
            print(
                f"{len(from_pool)} new knot(s) founded from the novel pool: "
                + ", ".join(f"#{i} unheard syllable" for i in from_pool),
                file=sys.stderr,
            )
    _save_pool(out_dir, pool)

    (out_dir / "points.json").write_text(json.dumps(points, indent=1), encoding="utf-8")

    # The knots keep their centroid vectors — nothing was re-fitted — but their membership
    # counts have changed and the app reads those. Unassigned points (-1) belong to no
    # knot and bump no count.
    added = np.bincount(ids[ids >= 0], minlength=len(items))
    for i, item in enumerate(items[: len(added)]):
        item["count"] = int(item.get("count", 0)) + int(added[i])

    # **A founded knot has to reach the sidecar, or the galaxy stops loading.** `k` below is
    # rewritten to `len(items)`, and `galaxy.centroid_vectors` checks the binary against it:
    # appending an item without appending its row left `centroid-vectors.f32` one row short
    # and every later reader — `verify`, `thresholds`, any analysis — raising "the sidecar
    # and centroids.json disagree". Founding a knot on a shipped asset set did not fail
    # loudly, it made the asset set unreadable.
    vec_block = centroids.get("vectors")
    if vec_block and len(items) > n_knots_before:
        order = list(vec_block["order"])
        widths = {n: int(w) for n, w in vec_block["dims"].items()}
        rows: list[list[float]] = []
        for i, item in enumerate(items):
            row: list[float] = []
            for name in order:
                w = widths[name]
                if i < n_knots_before and name in blocks:
                    row.extend(float(v) for v in blocks[name][i])
                else:
                    v = list(item.get(name) or [])
                    row.extend([float(t) for t in v[:w]] + [0.0] * max(0, w - len(v)))
            rows.append(row)
        (out_dir / vec_block["file"]).write_bytes(
            np.asarray(rows, dtype="<f4").ravel(order="C").tobytes()
        )
        vec_block = {**vec_block, "bytes": len(items) * sum(widths[n] for n in order) * 4}
        centroids = {**centroids, "vectors": vec_block}
        # The inline copies are dropped on the knots that carry them, so a sidecar galaxy
        # never holds the same array twice with two chances to disagree.
        for item in items[n_knots_before:]:
            for name in order:
                item.pop(name, None)
    (out_dir / "centroids.json").write_text(
        json.dumps({**centroids, "k": len(items), "items": items}, indent=1),
        encoding="utf-8",
    )

    # The inventory travels with the points, or the growth is invisible where it counts.
    #
    # A grow can add points for a syllable — or a whole species — that the shipped
    # `inventory.json` has never heard of, because `learn` writes the fitted repertoire to
    # `data/` and only a full build used to copy it across. The result was a galaxy that
    # drew the new marks and an app that could not sing them: no voice, no songs, no
    # grammar, and a species dropdown that never grew an entry. Copying the inventory
    # alongside costs one file write and is what makes "learn while it runs" mean anything.
    #
    # It only travels when the ids still line up. A grown galaxy keeps the clusters the build
    # fitted, and those clusters are labelled with syllable ids; shipping an inventory whose
    # ids have moved on would leave the app singing a syllable whose name belongs to a
    # cluster fitted to a different sound — audibly new, invisible in the cloud, which is the
    # exact failure this copy exists to prevent. `learn.assign_ids` now keeps ids stable, so
    # in the ordinary case this check passes; when it does not, the honest answer is that
    # only a rebuild can take the new repertoire in, and it says so.
    inventory_copied = False
    if inventory_path is not None and Path(inventory_path).exists():
        candidate = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
        offered = {
            (sp["id"], syl["id"])
            for sp in candidate.get("species", [])
            for syl in sp.get("syllables", [])
        }
        labelled = {
            (c["speciesId"], c["syllableId"]) for c in items if c.get("syllableId")
        }
        orphaned = labelled - offered
        if orphaned:
            print(
                f"not copying {Path(inventory_path).name}: {len(orphaned)} of the galaxy's "
                f"labelled clusters name syllables it no longer contains "
                f"({', '.join(f'{s}/{y}' for s, y in sorted(orphaned)[:4])}...). "
                "The points are grown; the repertoire needs a rebuild.",
                file=sys.stderr,
            )
        else:
            shutil.copyfile(Path(inventory_path), out_dir / "inventory.json")
            # The app's lazy view must track the whole file, or a grow silently
            # strands the shards of every changed species (see galaxy.py's writer).
            from .galaxy import _write_inventory_shards

            _write_inventory_shards(out_dir, json.loads(Path(inventory_path).read_text()))
            inventory_copied = True

    manifest.update(
        {
            "points": n_old + int(len(x)),
            "clusters": len(items),
            "builtAt": stamp,
            "generation": generation,
            "grownBy": [*manifest.get("grownBy", []), {"points": int(len(x)), "drift": report}],
        }
    )
    if inventory_copied:
        inv = json.loads((out_dir / "inventory.json").read_text(encoding="utf-8"))
        manifest["inventorySource"] = {
            "path": str(inventory_path),
            "name": Path(inventory_path).name,
            "writtenAt": datetime.fromtimestamp(
                Path(inventory_path).stat().st_mtime, timezone.utc
            ).isoformat(timespec="seconds"),
            "species": len(inv.get("species", [])),
            "syllables": sum(len(sp.get("syllables", [])) for sp in inv.get("species", [])),
        }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    if verbose:
        print(
            f"grew the galaxy by {len(x)} points to {n_old + len(x)} "
            f"(generation {generation}); "
            f"mean cosine to the nearest knot {report['meanCosine']}, "
            f"{report['unmatched'] * 100:.1f} % matched nothing, "
            f"{report['clipped'] * 100:.1f} % fell outside the frame",
            file=sys.stderr,
        )
    return {"added": int(len(x)), "points": n_old + int(len(x)),
            "generation": generation, "drift": report, "founded": founded,
            # Split by route, because the caller's message differs: a pool-founded knot is
            # an unnamed sound heard enough times, a fit-founded one is a named type that
            # just took its place.
            "foundedFromPool": from_pool, "foundedFromTypes": fit_founded}


def self_test(verbose: bool = True) -> None:
    """Grow a two-species galaxy, then place two types that were fitted after it was built.

    The scenario is the one the module exists for: build without two syllables, hand the
    full inventory back, and check that the types take their place without a rebuild. It
    also pins the three failures found while writing it, each of which was silent —
    knot ids that skipped, a sidecar the grow never appended to, and per-point features
    quietly not written.
    """
    import copy
    import shutil
    import tempfile

    from . import galaxy as galaxy_mod
    from .corpus import load_inventory, synthetic_corpus

    # --- unbuilt_types is the one definition the loop and the renderer share -------------
    inv_toy = {"species": [
        {"id": "sp1", "syllables": [{"id": "A"}, {"id": "B"}]},
        {"id": "sp2", "syllables": [{"id": "C"}]},
    ]}
    cen_toy = {"items": [
        {"speciesId": "sp1", "syllableId": "A"},
        # A pool-founded knot names no syllable, so it places none.
        {"speciesId": "", "syllableId": ""},
    ]}
    assert unbuilt_types(inv_toy, cen_toy) == [("sp1", "B"), ("sp2", "C")]

    root = Path(__file__).resolve().parents[3] / "data" / "inventory.json"
    if not root.exists():  # a checkout without the data directory: the toy case still ran
        if verbose:
            print("grow: inventory.json absent, skipped the end-to-end case", file=sys.stderr)
        return

    tmp = Path(tempfile.mkdtemp(prefix="grow-selftest-"))
    try:
        full = load_inventory(root)
        fitted = {"species": copy.deepcopy(full["species"][:2])}
        built_inv = copy.deepcopy(fitted)
        # Hold two syllables back, and with them any song that would reference a syllable
        # the build no longer has.
        held = [built_inv["species"][0]["syllables"].pop() for _ in range(2)]
        held_ids = {h["id"] for h in held}
        built_inv["species"][0]["songs"] = [
            s for s in built_inv["species"][0].get("songs", [])
            if not {str(e) for e in s.get("sequence", [])} & held_ids
        ]

        clips = synthetic_corpus(
            built_inv, None, variants=6, song_variants=1, seed=0, verbose=False
        )
        points = galaxy_mod.descriptors(clips, verbose=False)
        old_path = tmp / "built-inventory.json"
        old_path.write_text(json.dumps(built_inv), encoding="utf-8")
        galaxy_mod.build_galaxy(
            points, built_inv, out_dir=tmp, inventory_path=old_path,
            clustering="label", projection="cmds", compare_projections=False,
            test_relations=False, verbose=False,
        )

        fitted_path = tmp / "fitted-inventory.json"
        fitted_path.write_text(json.dumps(fitted), encoding="utf-8")
        before = json.loads((tmp / "centroids.json").read_text(encoding="utf-8"))
        assert len(unbuilt_types(fitted, before)) == 2

        result = render_unbuilt(tmp, fitted_path, variants=6, seed=0, verbose=False)
        assert len(result["foundedFromTypes"]) == 2, result["foundedFromTypes"]

        after = json.loads((tmp / "centroids.json").read_text(encoding="utf-8"))
        pts = json.loads((tmp / "points.json").read_text(encoding="utf-8"))

        # The galaxy now covers every fitted type, which is what stops the rebuild trigger.
        assert unbuilt_types(fitted, after) == []

        # A knot's id is its position. `len(items) + len(founded)` allocated 5, 7, 9 for the
        # knots at 5, 6, 7, after which the count fixup credited the wrong knots.
        assert [c["id"] for c in after["items"]] == list(range(len(after["items"])))

        # The sidecar has to grow with the knots or `centroid_vectors` refuses the galaxy.
        blocks = galaxy_mod.centroid_vectors(tmp, after)
        assert all(v.shape[0] == after["k"] == len(after["items"]) for v in blocks.values())
        for c in after["items"]:
            if c.get("route") == ROUTE_FIT:
                assert float(np.linalg.norm(blocks["vector"][c["id"]])) > 0.0

        # Per-point features are written for grown points, not skipped for want of a key.
        assert "featuresLo" in blocks
        lo = _read_f32(tmp / "point-features.f32", blocks["featuresLo"].shape[1])
        assert lo.shape[0] == pts["n"], (lo.shape, pts["n"])

        # Route is recorded on every point, or the two placements are not separable later.
        assert set(pts["route"]) == {"", ROUTE_FIT}
        fit_knots = {c["id"] for c in after["items"] if c.get("route") == ROUTE_FIT}
        assert len(fit_knots) == 2
        for i, r in enumerate(pts["route"]):
            if r == ROUTE_FIT:
                assert pts["clusterId"][i] in fit_knots

        # A named type founds a *named* knot; only the anonymous pool says "unheard".
        for c in after["items"]:
            if c.get("route") == ROUTE_FIT:
                assert c["speciesId"] and c["syllableId"] in held_ids
                assert c["label"] and c["label"] != "unheard syllable"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if verbose:
        print("grow: ok", file=sys.stderr)
