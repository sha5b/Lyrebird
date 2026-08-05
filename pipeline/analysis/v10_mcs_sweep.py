"""
How many dense regions the corpus holds, and how much of it is in none of them, as a
function of the one number that decides both.

`build --clustering hdbscan` reports a single pair — k clusters, and a noise share — at a
single `min_cluster_size` (25, `density.DEFAULT_MIN_CLUSTER_SIZE`). One pair cannot be read
as a measurement of the corpus, because nobody looking at it can tell whether it sits on a
plateau or on a cliff: `min_cluster_size` is simultaneously the smallest thing allowed to be
a syllable type and the threshold that decides what "in no dense region" means, and both k
and the noise share move with it. This script sweeps it and prints the curve, so the choice
is made against the trade-off rather than tuned until the picture agrees with the answer
that was wanted.

**The noise share is expected to be large, and that is the finding, not a fault.** The
scaling test behind `density._fit`'s timings ran at `min_cluster_size=25` on subsamples of
this corpus's own embedding, and left 93 % of the points in no dense region at n = 80 000 and
86 % at n = 200 000 (the timings are recorded in `density._fit`; those two shares are not,
which is part of why this script exists). If the 444 213-point corpus lands near them, then
"belongs to none of them" is
most of the corpus, and the honest report is the number — a density map that refuses nine
points in ten is telling you the corpus is mostly thin, singleton field audio, which is a
statement about the harvest rather than about HDBSCAN.

## Which matrix this clusters, and whether it is the one the build clustered

For `--space embed` (what the v10 runs use), `build_galaxy` hands `density.cluster` exactly
one array, `z`, built at galaxy.py:1703:

    z = (e - embedding["mean"]) / np.maximum(embedding["std"], 1e-6)

where `e` is each point's 32-d critic embedding and the moments are measured over all
embedded points of that build. That is the array behind the `hdbscan: min_cluster_size=25 on
standardised descriptors` log line — 444 213 x 32, rows in build order: 8 583 rendered
inventory points first, then the 435 630 field syllables. `density.cluster` then unit-
normalises its rows internally, so the matrix to hand it is `z` itself, unnormalised.

**`z` is not written to disk by a build, so it is reconstructed here, and only in part.**
The two modes differ in what they cost, and they are not interchangeable:

- `--matrix embed32` (default) rebuilds `z` from `out/harvest-inband/embeddings.f32` and the
  `embedding.mean` / `embedding.std` in the build's own `feature-space.json`, applying the
  same expression. The sidecar is 435 630 x 32 in `store.syllables` row order, written by
  `critic embed` from the same `critic.pt` the build used — the script refuses to run if the
  sidecar's critic mtime and the manifest's disagree. For those rows the values are the
  build's values, to the bit, and the space, the dimensionality and the standardisation are
  the build's. What is missing is the 8 583 rendered rows (1.93 % of the corpus): their
  embeddings exist only inside the build, which rendered the audio and pushed it through the
  critic, and no asset carries them. So this mode clusters **435 630 of 444 213 rows in the
  exact clustering space** — a corpus 1.93 % smaller than the build's, which is a real
  difference in a density estimate and is stated in the report rather than rounded away.
- `--matrix features-lo` clusters `point-features.f32` — all 444 213 rows, but 8-d, PCA of
  the same standardised space, rows unit-normalised, holding 64.77 % of its variance
  (manifest `pointFeatures`). Row-complete and space-wrong: a density estimate in 8 dims at
  65 % of the variance is a different question, and its k and noise share should not be
  compared with the build's. It exists so that "how much of this curve is the missing 1.9 %
  of rows, and how much is the space" can be answered instead of argued.

Either way the mode's own `min_cluster_size=25` row is printed beside the build manifest's
`density` block, which was measured on the whole of `z`. That comparison is the measurement
of the reconstruction: if the default mode's row lands near the manifest's, dropping the
rendered anchor cost little; if it does not, the curve describes the field corpus and has to
be read as such.

## Agreement with the map that ships

The shipped galaxy is a `--clustering label` build: every point gets a knot by construction,
15 341 of them, so it cannot say "none of these". Each sweep point is scored against that
partition with Adjusted Rand and Adjusted Mutual Information, **twice**:

- *assigned* — over the non-noise points only. This asks whether the two maps agree about
  the points HDBSCAN was willing to place.
- *all* — over every row, with noise as one label of its own. This asks whether the two maps
  describe the same corpus, and a partition that refuses ~90 % of it does not.

One number would be the second one, dominated by the noise block, and would be read as the
first. `v10_unknown_join.py` reports the *all* form at the build's own single
`min_cluster_size`; the pair reported per sweep point here is what shows how much of the
agreement is structure and how much is the refusal.

## What this does not measure

The curve does not identify a correct `min_cluster_size`; there is no held-out quantity here
that a maximum could be chosen against. ARI and AMI against the label map are agreement, not
accuracy — the label partition is bookkeeping over the type inventory and has no claim to be
right, so a low ARI is equally readable as the density map disagreeing with it. Nothing here
re-projects, re-separates or re-writes an asset: a sweep point is a clustering, not a build,
and the k it reports would only become a galaxy through a full run.

Run: `uv run python analysis/v10_mcs_sweep.py` from `pipeline/` (add `--dry-run` first).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "app" / "static" / "birdy"
UNKNOWN = REPO / "pipeline" / "out" / "v10" / "assets-unknown"
STORE = REPO / "pipeline" / "out" / "harvest-inband"
REPORT = Path(__file__).with_suffix(".json")

DEFAULT_SWEEP = "25,50,100,200"

#: What the v10 corpus is, so a wrong asset set is caught by its shape rather than by a
#: plausible report. 8 583 rendered rows + 435 630 field syllables; `sourceMix` in the
#: manifest is the same three counts.
EXPECTED_POINTS = 444_213
EXPECTED_FIELD = 435_630
EXPECTED_DIMS = 32
#: `point-features.f32` is 8 floats per point (galaxy.POINT_FEATURE_DIMS).
LO_DIMS = 8
#: `harvest.SOURCE`, the tag every field row carries in points.json.
FIELD = "field"

#: The fast path's measured cost on this corpus's embedding at `min_cluster_size=25`
#: (density._fit): 44.8 s at n = 80 000, 265.2 s at 200 000, about n^2.0 in this regime.
#: Used only to print what a sweep will cost before it is started.
FAST_SECONDS_AT_200K = 265.2


def projected_seconds(n: int) -> float:
    """Rough wall clock per sweep point on the Boruvka path, from density.py's own numbers."""
    return FAST_SECONDS_AT_200K * (n / 200_000.0) ** 2


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _field_start(source: list[str]) -> int:
    """First field row, asserting the field rows are a contiguous suffix.

    `cmd_build` concatenates rendered points, then any local corpus, then the harvest
    store's field points, and nothing between there and the write re-sorts — so the field
    rows are the tail of the matrix and `embeddings.f32` lines up with that tail positionally.
    That is an argument about the code; this is the check on the data.
    """
    is_field = np.asarray(source) == FIELD
    if not is_field.any():
        raise SystemExit("no row is tagged `field`: this asset set holds no harvest points")
    start = int(np.argmax(is_field))
    if not bool(is_field[start:].all()):
        raise SystemExit(
            "the field rows are not a contiguous suffix, so the store's embeddings cannot "
            "be joined to them positionally — rebuild, or use --matrix features-lo"
        )
    return start


def load_embed32(
    store_dir: Path, feature_space: Path, manifest: dict[str, Any], n_field: int
) -> tuple[np.ndarray, dict[str, Any]]:
    """The build's own `z`, for its field rows: the reconstruction the docstring describes."""
    sidecar = _read_json(store_dir / "embeddings.json")
    raw = np.fromfile(store_dir / "embeddings.f32", dtype="<f4")
    dim = int(sidecar.get("dim", EXPECTED_DIMS))
    rows = int(sidecar.get("n", 0))
    if raw.size != rows * dim:
        raise SystemExit(
            f"embeddings.f32 holds {raw.size} floats, embeddings.json says {rows} x {dim} — "
            "re-run `birdy-pipeline critic embed` against this store"
        )
    if rows != n_field:
        raise SystemExit(
            f"embeddings.f32 has {rows} rows and the build has {n_field} field rows: the "
            "store changed since the build read it, and row i is no longer the same syllable"
        )
    if int(sidecar.get("countNaN", 0)):
        raise SystemExit(
            f"embeddings.f32 holds {sidecar['countNaN']} non-finite rows; the build drops "
            "such points, so this reconstruction would not be the same point set"
        )

    # The same critic or nothing. A different critic.pt defines a different 32-d space, and
    # the resulting matrix would answer a question about a space no build ever clustered.
    build_critic = ((manifest.get("embedding") or {}).get("critic")) or {}
    file_critic = sidecar.get("critic") or {}
    if build_critic.get("mtime") and file_critic.get("mtime"):
        if build_critic["mtime"] != file_critic["mtime"]:
            raise SystemExit(
                f"the build embedded with critic mtime {build_critic['mtime']} and "
                f"embeddings.f32 was written by {file_critic['mtime']} — different spaces"
            )

    fs = _read_json(feature_space)
    block = fs.get("embedding") or {}
    mean = np.asarray(block.get("mean", []), dtype=np.float64)
    std = np.asarray(block.get("std", []), dtype=np.float64)
    if mean.size != dim or std.size != dim:
        raise SystemExit(
            f"{feature_space} carries {mean.size}/{std.size} standardisation moments for a "
            f"{dim}-d space — this build did not run in the embedding space"
        )
    e = raw.reshape(rows, dim).astype(np.float64)
    # galaxy.py:1703, character for character. The floor is 1e-6, not features.py's floor.
    z = (e - mean) / np.maximum(std, 1.0e-6)
    if not np.all(np.isfinite(z)):
        raise SystemExit("the reconstructed matrix holds NaN/inf, which the build would not")
    return z, {
        "kind": "embed32",
        "what": (
            "the build's own clustering matrix z = (e - mean)/max(std, 1e-6) over the "
            "32-d critic embeddings, restricted to the field rows"
        ),
        "rows": int(rows),
        "dims": int(dim),
        "rowsOfBuild": int(EXPECTED_POINTS),
        "rowsMissing": int(EXPECTED_POINTS - rows),
        "rowsMissingShare": round((EXPECTED_POINTS - rows) / EXPECTED_POINTS, 4),
        "missing": (
            "the rendered inventory points, whose embeddings exist only inside a build "
            "(rendered audio through the critic) and are in no asset"
        ),
        "embeddings": str(store_dir / "embeddings.f32"),
        "moments": str(feature_space),
        "critic": file_critic.get("path"),
        "exact": True,
    }


def load_features_lo(assets: Path, n: int) -> tuple[np.ndarray, dict[str, Any]]:
    """`point-features.f32`: row-complete, and a different space. See the docstring."""
    path = assets / "point-features.f32"
    raw = np.fromfile(path, dtype="<f4")
    if raw.size != n * LO_DIMS:
        raise SystemExit(
            f"{path} holds {raw.size} floats, expected {n} x {LO_DIMS} = {n * LO_DIMS}"
        )
    lo = raw.reshape(n, LO_DIMS).astype(np.float64)
    return lo, {
        "kind": "features-lo",
        "what": (
            "point-features.f32 — an 8-d PCA of the standardised 32-d space, rows already "
            "unit-normalised, holding about 65 % of its variance"
        ),
        "rows": int(n),
        "dims": LO_DIMS,
        "rowsOfBuild": int(n),
        "rowsMissing": 0,
        "rowsMissingShare": 0.0,
        "file": str(path),
        "exact": False,
        "warning": (
            "NOT the matrix the build clustered: 8 of 32 dimensions, 65 % of the variance. "
            "Its k and noise share answer a different question and must not be quoted "
            "against the build's"
        ),
    }


def sweep_point(
    z: np.ndarray, shipped: np.ndarray, min_cluster_size: int
) -> dict[str, Any]:
    """One clustering, and everything measured about it."""
    from birdy_pipeline import density

    t0 = time.time()
    found = density.cluster(z, min_cluster_size=min_cluster_size)
    seconds = time.time() - t0
    labels = np.asarray(found.labels, dtype=np.int64)
    sizes = (
        np.bincount(labels[labels >= 0], minlength=found.k).astype(np.float64)
        if found.k
        else np.zeros(0)
    )

    row: dict[str, Any] = {
        "minClusterSize": int(min_cluster_size),
        "clusters": int(found.k),
        "noise": int(found.noise),
        "noiseShare": round(float(found.noise_share), 4),
        "medianClusterSize": float(np.median(sizes)) if sizes.size else 0.0,
        "meanClusterSize": round(float(sizes.mean()), 1) if sizes.size else 0.0,
        "largestCluster": int(sizes.max()) if sizes.size else 0,
        "seconds": round(seconds, 1),
    }

    # Both forms, because they say different things and the corpus makes the difference
    # enormous. `assigned` drops the noise rows: agreement over the points this clustering
    # was willing to place. `all` keeps them as one label: agreement about the corpus, which
    # a partition refusing ~90 % of it does not have. With noise this large the `all` figure
    # is mostly a measurement of one giant block against 15 341 knots, so reporting it alone
    # would answer the second question while being read as the first.
    from sklearn.metrics import adjusted_mutual_info_score, adjusted_rand_score

    t1 = time.time()
    assigned = labels >= 0
    if int(assigned.sum()) > 1:
        row["ariAssigned"] = round(
            float(adjusted_rand_score(shipped[assigned], labels[assigned])), 4
        )
        row["amiAssigned"] = round(
            float(adjusted_mutual_info_score(shipped[assigned], labels[assigned])), 4
        )
    else:
        row["ariAssigned"] = None
        row["amiAssigned"] = None
    row["ariAll"] = round(float(adjusted_rand_score(shipped, labels)), 4)
    row["amiAll"] = round(float(adjusted_mutual_info_score(shipped, labels)), 4)
    row["agreementSeconds"] = round(time.time() - t1, 1)
    row["pointsScoredAssigned"] = int(assigned.sum())
    row["pointsScoredAll"] = int(labels.size)
    return row


HEADER = (
    f"{'mcs':>5} {'k':>7} {'noise':>9} {'noise%':>7} {'median':>7} {'mean':>7} "
    f"{'largest':>8} {'ARI(asg)':>9} {'AMI(asg)':>9} {'ARI(all)':>9} {'AMI(all)':>9} "
    f"{'s':>8}"
)


def format_row(row: dict[str, Any]) -> str:
    def num(value: Any, spec: str) -> str:
        # None means "not measurable at this sweep point" (every row was noise), which is a
        # different statement from 0.0 and is printed as a different thing.
        return "        -" if value is None else format(value, spec)

    return (
        f"{row['minClusterSize']:>5} {row['clusters']:>7} {row['noise']:>9} "
        f"{row['noiseShare'] * 100:>7.1f} {row['medianClusterSize']:>7.1f} "
        f"{row['meanClusterSize']:>7.1f} {row['largestCluster']:>8} "
        f"{num(row['ariAssigned'], '>9.4f')} {num(row['amiAssigned'], '>9.4f')} "
        f"{row['ariAll']:>9.4f} {row['amiAll']:>9.4f} {row['seconds']:>8.1f}"
    )


def check_inputs(args: argparse.Namespace) -> tuple[list[str], list[str], dict[str, Any]]:
    """Every input, its shape, and what is missing — without clustering anything.

    Returns `(lines, missing, facts)`. `missing` empty means the sweep can run.
    """
    lines: list[str] = []
    missing: list[str] = []
    facts: dict[str, Any] = {}

    def want(path: Path, why: str, size_note: str | None = None) -> bool:
        if path.exists():
            size = path.stat().st_size
            lines.append(f"  ok      {path}  {size / 1e6:.2f} MB{size_note or ''}")
            return True
        missing.append(f"{path} ({why})")
        lines.append(f"  ABSENT  {path}  <- {why}")
        return False

    lines.append("shipped label assets (the partition every sweep point is scored against):")
    shipped_points = args.assets / "points.json"
    if want(shipped_points, "the shipped clusterId, one per syllable"):
        points = _read_json(shipped_points)
        cluster_id = np.asarray(points["clusterId"], dtype=np.int64)
        n = int(points.get("n", cluster_id.size))
        distinct = int(np.unique(cluster_id).size)
        facts["shippedPoints"] = n
        facts["shippedDistinctClusters"] = distinct
        facts["shippedFieldStart"] = _field_start(points["source"])
        facts["shippedFieldRows"] = n - facts["shippedFieldStart"]
        lines.append(
            f"          {n} rows, {distinct} distinct clusterId, field rows "
            f"{facts['shippedFieldStart']}..{n - 1} ({facts['shippedFieldRows']})"
        )
        if cluster_id.size != n:
            missing.append(f"{shipped_points}: clusterId has {cluster_id.size} of {n} rows")
        if n != EXPECTED_POINTS:
            lines.append(
                f"          NOTE: {n} rows, not the v10 corpus's {EXPECTED_POINTS}"
            )
        if facts["shippedFieldRows"] != EXPECTED_FIELD:
            lines.append(
                f"          NOTE: {facts['shippedFieldRows']} field rows, not "
                f"{EXPECTED_FIELD}"
            )

    lines.append(
        "hdbscan build assets (its standardisation moments, its manifest to check against):"
    )
    manifest_path = args.unknown_assets / "manifest.json"
    fs_path = args.unknown_assets / "feature-space.json"
    unknown_points = args.unknown_assets / "points.json"
    if want(manifest_path, "the build's own density block and critic provenance"):
        manifest = _read_json(manifest_path)
        density_block = manifest.get("density") or {}
        facts["buildManifest"] = {
            "points": manifest.get("points"),
            "clustering": manifest.get("clustering"),
            "space": manifest.get("space"),
            "density": density_block or None,
        }
        lines.append(
            f"          clustering={manifest.get('clustering')} "
            f"space={manifest.get('space')} points={manifest.get('points')}"
        )
        if density_block:
            lines.append(
                f"          density: {density_block.get('clusters')} clusters, "
                f"{density_block.get('noise')} noise "
                f"({float(density_block.get('noiseShare', 0)) * 100:.1f} %)"
            )
        else:
            lines.append("          NOTE: no `density` block — this is not an hdbscan build")
    want(fs_path, "embedding.mean / embedding.std, the build's standardisation")
    if want(unknown_points, "the build's own row order and field-row count"):
        upoints = _read_json(unknown_points)
        start = _field_start(upoints["source"])
        facts["buildFieldRows"] = int(upoints["n"]) - start
        lines.append(
            f"          {upoints['n']} rows, field rows {start}..{int(upoints['n']) - 1} "
            f"({facts['buildFieldRows']})"
        )
    if args.matrix == "features-lo":
        want(
            args.unknown_assets / "point-features.f32",
            f"the 8-d matrix, {LO_DIMS} floats per point",
        )

    if args.matrix == "embed32":
        lines.append("harvest store (the 32-d embeddings the build read):")
        if want(STORE / "embeddings.json", "the sidecar's row count, dim and critic"):
            sidecar = _read_json(STORE / "embeddings.json")
            facts["embeddings"] = {
                "n": sidecar.get("n"),
                "dim": sidecar.get("dim"),
                "countNaN": sidecar.get("countNaN"),
                "writtenAt": sidecar.get("writtenAt"),
                "critic": (sidecar.get("critic") or {}).get("mtime"),
            }
            lines.append(
                f"          {sidecar.get('n')} x {sidecar.get('dim')}, "
                f"{sidecar.get('countNaN')} NaN rows, critic mtime "
                f"{(sidecar.get('critic') or {}).get('mtime')}, written "
                f"{sidecar.get('writtenAt')}"
            )
        if want(STORE / "embeddings.f32", "the embeddings themselves, in store row order"):
            floats = (STORE / "embeddings.f32").stat().st_size // 4
            lines.append(
                f"          {floats // EXPECTED_DIMS} rows at {EXPECTED_DIMS}-d "
                f"({floats} float32)"
            )

    lines.append("clustering implementation:")
    try:  # noqa: SIM105 - the branch is the report
        import hdbscan  # noqa: F401

        lines.append(
            "  ok      hdbscan package present — Boruvka MST, the only path that finishes "
            "at this scale"
        )
        facts["implementation"] = "hdbscan (boruvka)"
    except ImportError:
        lines.append(
            "  NOTE    hdbscan package absent: density.cluster falls back to "
            "sklearn.cluster.HDBSCAN, whose sequential MST is about n^2.5 — hours per "
            "sweep point at this n"
        )
        facts["implementation"] = "sklearn.cluster.HDBSCAN (prims)"
    try:
        import sklearn

        lines.append(f"  ok      scikit-learn {sklearn.__version__} for ARI/AMI")
    except ImportError:  # pragma: no cover - the venv always has it
        missing.append("scikit-learn (adjusted_rand_score / adjusted_mutual_info_score)")
        lines.append("  ABSENT  scikit-learn <- ARI/AMI cannot be computed")

    return lines, missing, facts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--assets",
        type=Path,
        default=ASSETS,
        help="the shipped label build, whose clusterId every sweep point is scored against",
    )
    ap.add_argument(
        "--unknown-assets",
        type=Path,
        default=UNKNOWN,
        help="the hdbscan build: its feature-space.json moments and its manifest",
    )
    ap.add_argument(
        "--matrix",
        choices=("embed32", "features-lo"),
        default="embed32",
        help=(
            "embed32: the build's own 32-d clustering matrix, field rows only (98.07 %% of "
            "them, exact values). features-lo: all rows, 8-d PCA, a different space"
        ),
    )
    ap.add_argument(
        "--min-cluster-size",
        default=DEFAULT_SWEEP,
        help=f"comma-separated sweep points (default {DEFAULT_SWEEP})",
    )
    ap.add_argument("--report", type=Path, default=REPORT)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "check every input's presence and shape, print the plan and the projected cost, "
            "cluster nothing. Exits 0 either way: the verdict is the READY/NOT READY line"
        ),
    )
    args = ap.parse_args()

    try:
        sweep = [int(v) for v in str(args.min_cluster_size).split(",") if v.strip()]
    except ValueError:
        raise SystemExit(f"--min-cluster-size {args.min_cluster_size!r} is not a list of ints")
    if not sweep:
        raise SystemExit("--min-cluster-size is empty; nothing to sweep")

    lines, missing, facts = check_inputs(args)
    for line in lines:
        print(line)

    if args.matrix == "embed32":
        rows_to_cluster = (
            facts.get("buildFieldRows")
            or facts.get("shippedFieldRows")
            or EXPECTED_FIELD
        )
    else:
        rows_to_cluster = facts.get("shippedPoints") or EXPECTED_POINTS
    print("")
    print(f"plan: {args.matrix} matrix, {rows_to_cluster} rows")
    print(f"  sweep min_cluster_size = {', '.join(str(v) for v in sweep)}")
    each = projected_seconds(int(rows_to_cluster))
    print(
        f"  projected {each / 60:.0f} min per point on the Boruvka path, "
        f"{each * len(sweep) / 60:.0f} min for {len(sweep)} points "
        "(from density.py's measured 265.2 s at n = 200 000, ~n^2.0)"
    )
    print(f"  ARI/AMI against {facts.get('shippedDistinctClusters', '?')} shipped clusters, "
          "twice per point: non-noise rows only, and all rows with noise as one label")
    print(f"  writes {args.report}; no asset is touched")

    if missing:
        print("")
        print(f"NOT READY — {len(missing)} input(s) the sweep needs do not exist yet:")
        for item in missing:
            print(f"  {item}")
        print(
            "  the hdbscan build writes its whole asset set at the end of the run, so an "
            "empty or partial assets-unknown/ is what an unfinished build looks like"
        )
        if args.dry_run:
            return 0
        return 2

    print("")
    print("READY — every input present and the expected shape")
    if args.dry_run:
        return 0

    # --- load the shipped partition and the matrix, and prove they are row-aligned -------
    shipped = _read_json(args.assets / "points.json")
    cluster_id = np.asarray(shipped["clusterId"], dtype=np.int64)
    n_shipped = int(shipped.get("n", cluster_id.size))
    if cluster_id.size != n_shipped:
        raise SystemExit(
            f"points.json says n={n_shipped} but clusterId holds {cluster_id.size}"
        )
    field_start = _field_start(shipped["source"])
    manifest = _read_json(args.unknown_assets / "manifest.json")

    t0 = time.time()
    if args.matrix == "embed32":
        z, provenance = load_embed32(
            STORE,
            args.unknown_assets / "feature-space.json",
            manifest,
            n_shipped - field_start,
        )
        # Row-index safety. The whole join rests on row i being the same syllable in both
        # asset sets, and this mode clusters a suffix of the shipped rows: the matrix must
        # be exactly as long as that suffix, and the suffix plus the head it drops must be
        # the whole shipped corpus. Anything else and the ARI below would be fiction.
        if z.shape[0] != n_shipped - field_start:
            raise SystemExit(
                f"the matrix has {z.shape[0]} rows and the shipped field suffix is "
                f"{n_shipped - field_start} — the join would be off by "
                f"{abs(z.shape[0] - (n_shipped - field_start))} syllables"
            )
        if field_start + z.shape[0] != n_shipped:
            raise SystemExit(
                f"{field_start} head rows + {z.shape[0]} matrix rows != {n_shipped} "
                "shipped rows"
            )
        joined = cluster_id[field_start:]
        print(
            f"matrix: {z.shape[0]} x {z.shape[1]} — the build's z, field rows only "
            f"({provenance['rowsMissing']} rendered rows "
            f"({provenance['rowsMissingShare'] * 100:.2f} %) are in no asset and are "
            f"absent from this sweep)"
        )
    else:
        z, provenance = load_features_lo(args.unknown_assets, n_shipped)
        if z.shape[0] != cluster_id.size:
            raise SystemExit(
                f"the matrix has {z.shape[0]} rows and the shipped clusterId has "
                f"{cluster_id.size} — row i is not the same syllable in both"
            )
        joined = cluster_id
        print(f"matrix: {z.shape[0]} x {z.shape[1]} — {provenance['what']}")
        print(f"WARNING: {provenance['warning']}")
    print(f"  loaded in {time.time() - t0:.1f}s; row-alignment checks passed")

    # --- the sweep -----------------------------------------------------------------------
    # One matrix, loaded once, reused by every point: the clustering is the cost, and a
    # reload per point would be pure waste.
    results: list[dict[str, Any]] = []
    print("")
    print(HEADER)
    for mcs in sweep:
        row = sweep_point(z, joined, mcs)
        results.append(row)
        print(format_row(row), flush=True)

    print("")
    print(
        "noise% is the share of the clustered rows in no dense region at all. "
        "median/mean/largest are cluster sizes in points."
    )

    # --- what the build itself measured, on all 444 213 rows ------------------------------
    density_block = manifest.get("density") or {}
    build_mcs = 25
    same = next((r for r in results if r["minClusterSize"] == build_mcs), None)
    if density_block and same:
        print("")
        print(f"the build's own clustering, for comparison at min_cluster_size={build_mcs}:")
        print(
            f"  build   {manifest.get('points')} rows   k={density_block.get('clusters')}   "
            f"noise={density_block.get('noise')} "
            f"({float(density_block.get('noiseShare', 0)) * 100:.1f} %)"
        )
        print(
            f"  sweep   {z.shape[0]} rows   k={same['clusters']}   "
            f"noise={same['noise']} ({same['noiseShare'] * 100:.1f} %)"
        )
        print(
            "  the gap is what this reconstruction costs: same algorithm and settings, a "
            f"{provenance['rowsMissingShare'] * 100:.2f} %-smaller corpus"
            + ("" if provenance["exact"] else " in a different space")
        )

    report = {
        "question": (
            "how k and the noise share move with min_cluster_size, and how much each "
            "clustering agrees with the shipped label map"
        ),
        "matrix": provenance,
        "rowsClustered": int(z.shape[0]),
        "shipped": {
            "assets": str(args.assets),
            "points": n_shipped,
            "distinctClusters": int(np.unique(cluster_id).size),
            "fieldStart": int(field_start),
            "joinedRows": int(joined.size),
        },
        "build": facts.get("buildManifest"),
        "embeddings": facts.get("embeddings"),
        "implementation": facts.get("implementation"),
        "sweep": results,
        "definitions": {
            "noiseShare": "share of the clustered rows HDBSCAN put in no dense region",
            "ariAssigned": (
                "adjusted Rand against the shipped label clustering over the non-noise "
                "rows only — agreement about the points this clustering placed"
            ),
            "ariAll": (
                "adjusted Rand over every clustered row with noise as one label of its "
                "own — agreement about the corpus, which a partition refusing most of it "
                "does not have"
            ),
            "notMeasured": (
                "neither figure is accuracy: the label partition is bookkeeping over the "
                "type inventory and has no claim to be correct. The curve identifies no "
                "best min_cluster_size; it makes the trade-off visible"
            ),
        },
    }
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("")
    print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
