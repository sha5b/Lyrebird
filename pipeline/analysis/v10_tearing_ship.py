"""
Write the per-knot `tearing` field onto the *shipped* v10 centroids, without a rebuild.

`torn_clusters` has always measured tearing per knot and then thrown the per-knot numbers
away, keeping only the aggregate the manifest carries: 2 035 of 6 316 measured knots drawn
in two places at once, median ratio 3.704. That aggregate is a fact about the picture, and
it is the wrong shape for the question anyone actually asks — a viewer reading a distance
off *one* knot cannot tell from it whether that knot is one of the third that are torn.
The pipeline now writes the ratio onto each centroids item, but the v10 galaxy is a full
build (444 213 points, k = 15 341) and rebuilding it to add one float per knot is not
affordable. So this script does the write on its own.

It recomputes the ratios with the pipeline's own `torn_clusters` — imported, not copied —
over the positions that actually shipped, then refuses to write unless its aggregate
reproduces the manifest's. Separation is a rigid per-cluster translation and normalisation
is a global affine, and the ratio is scale-free, so the aggregate is invariant under both:
if the two disagree, the shipped positions are not the ones that were measured, and that is
a finding rather than something to round away.

Run: `uv run python analysis/v10_tearing_ship.py` from `pipeline/`.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from birdy_pipeline.cli import log
from birdy_pipeline.galaxy import torn_clusters

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "app" / "static" / "birdy"

#: The aggregate keys the manifest carries. `definition` is prose and `worstGap` is a
#: distance rather than a ratio, so the four counted/ordered numbers are the check.
CHECKED = ("measured", "torn", "severe", "median")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", type=Path, default=ASSETS)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print the distribution, write nothing",
    )
    args = ap.parse_args()

    points_path = args.assets / "points.json"
    centroids_path = args.assets / "centroids.json"
    manifest_path = args.assets / "manifest.json"
    positions_path = args.assets / "positions.f32"
    for path in (points_path, centroids_path, manifest_path, positions_path):
        if not path.exists():
            raise SystemExit(f"missing {path}")

    t0 = time.time()
    points = json.loads(points_path.read_text(encoding="utf-8"))
    centroids = json.loads(centroids_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cluster_id = np.asarray(points["clusterId"], dtype=np.int32)
    n = int(points.get("n", cluster_id.size))
    if cluster_id.size != n:
        raise SystemExit(f"points.json says n={n} but clusterId has {cluster_id.size}")
    pos = np.fromfile(positions_path, dtype="<f4")
    if pos.size != n * 3:
        raise SystemExit(f"{positions_path} holds {pos.size} floats, expected {n * 3}")
    pos = pos.reshape(n, 3).astype(np.float64)

    items = centroids["items"]
    k = int(centroids["k"])
    if len(items) != k:
        raise SystemExit(f"centroids.json says k={k} but carries {len(items)} items")
    log(
        f"{n} points, {k} knots, positions {pos.shape} "
        f"({time.time() - t0:.1f}s to read)"
    )

    t1 = time.time()
    aggregate, per_cluster = torn_clusters(pos, cluster_id, k)
    log(f"measured {len(per_cluster)} knots in {time.time() - t1:.1f}s")

    shipped = manifest.get("tearing") or {}
    ok = all(aggregate.get(key) == shipped.get(key) for key in CHECKED)
    log("aggregate: manifest vs recomputed")
    for key in (*CHECKED, "worstGap"):
        mark = "" if aggregate.get(key) == shipped.get(key) else "   <- MISMATCH"
        log(f"  {key:9} {shipped.get(key)!r:>10} {aggregate.get(key)!r:>10}{mark}")
    if not ok:
        log(
            "the shipped positions are not the ones the manifest's tearing was measured "
            "on — nothing written"
        )
        return 1

    measured = 0
    for item in items:
        cid = int(item["id"])
        ratio = per_cluster.get(cid)
        if ratio is None:
            # Absent means unmeasured, so a stale value has to go rather than stand in.
            item.pop("tearing", None)
            continue
        measured += 1
        value = round(float(ratio), 3)
        if "tearing" in item:
            item["tearing"] = value
            continue
        # Same slot the pipeline writes it into, so a rebuilt asset and a patched one
        # order their keys the same way.
        rebuilt = {}
        for key, existing in list(item.items()):
            if key == "speciesMix":
                rebuilt["tearing"] = value
            rebuilt[key] = existing
        if "tearing" not in rebuilt:
            rebuilt["tearing"] = value
        item.clear()
        item.update(rebuilt)

    ratios = np.asarray([per_cluster[c] for c in sorted(per_cluster)])
    torn = int((ratios > 5).sum())
    severe = int((ratios > 8).sum())
    log(
        f"wrote tearing onto {measured} of {k} knots — {k - measured} absent (fewer than "
        "12 members, or a degenerate 2-means split)"
    )
    log(
        f"  torn (>5): {torn} ({torn / ratios.size * 100:.1f} % of measured)   "
        f"severe (>8): {severe} ({severe / ratios.size * 100:.1f} %)   "
        f"median: {np.median(ratios):.3f} (null for one blob is ~2)"
    )
    label_of = {int(it["id"]): it.get("label", "") for it in items}
    worst = sorted(per_cluster.items(), key=lambda kv: -kv[1])[:5]
    log("  worst 5 knots:")
    for cid, ratio in worst:
        log(f"    #{cid:<6} {ratio:8.3f}  {label_of.get(cid, '')}")

    if args.dry_run:
        log("dry run — centroids.json untouched")
        return 0

    # `indent=1`, the same as galaxy.py's `_write_json`: any other formatting turns a
    # one-line-per-knot diff into a rewrite of all 15 341 items.
    centroids_path.write_text(json.dumps(centroids, indent=1), encoding="utf-8")
    log(f"wrote {centroids_path} — {centroids_path.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
