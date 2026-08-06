"""Does fitting cMDS to the honest metric make a better picture, or only honest arithmetic?

`projectionParams.negativeEigenvalueMass` on the shipped build is **0.408**: 41 % of the
eigenvalue mass is negative, because classical MDS is defined for a Euclidean distance and
was being fitted to the cosine distance, which is not one. The rows are unit vectors, so
the Euclidean distance between two of them is the chord `sqrt(2 - 2 cos)` — same ordering,
same neighbours, and the double-centred matrix is then positive semi-definite by
construction (`galaxy.mds_squared_distances`).

That argument is about arithmetic. Whether the *picture* improves is a measurement, and
this is it: both metrics over the same rows, scored on the build's own instruments.

Run against the shipped **knot** vectors (`centroid-vectors.f32`, 32-d, one row per knot),
which is the production corpus's own space and needs no rebuild. It answers the knot-level
claim — "distance between knots is acoustic distance" — and cannot answer tearing, which
is a within-knot statistic and needs the per-point matrix (`build --dump-points`).

    uv run python pipeline/analysis/mds_metric.py [asset-root]
"""

import json
import sys
from pathlib import Path

import numpy as np

from lyrebird_pipeline import galaxy

root = Path(sys.argv[1] if len(sys.argv) > 1 else "app/static/lyrebird")
centroids = json.loads((root / "centroids.json").read_text())
blocks = galaxy.centroid_vectors(root, centroids)
z = blocks.get("vector32")
if z is None or not z.size:
    raise SystemExit(f"{root} ships no 32-d knot vectors")

print(f"{root}: {z.shape[0]} knots x {z.shape[1]}-d")
print(f"(the build's cMDS path here is {'landmark' if z.shape[0] > galaxy.CMDS_FULL_MAX else 'full'} MDS)\n")

def chord_faithfulness(z: np.ndarray, pos: np.ndarray, seed: int = 0) -> dict:
    """The build's faithfulness, scored against the chord distance instead of the cosine.

    The chord projector aims at `sqrt(2 - 2 cos)`, so grading it on agreement with
    `1 - cos` penalises it for a monotone reparametrisation rather than for arranging
    anything badly — a *Pearson* objection only, since Spearman sees ranks and the two
    dissimilarities are monotone in each other. Reported so the objection is closed
    rather than argued about.
    """
    rng = np.random.default_rng(seed)
    n = z.shape[0]
    pairs = min(galaxy.FAITHFULNESS_PAIRS, n * (n - 1) // 2)
    i = rng.integers(0, n, pairs)
    j = rng.integers(0, n, pairs)
    keep = i != j
    i, j = i[keep], j[keep]
    u = galaxy._unit_rows(z)
    d_hi = np.sqrt(np.maximum(2.0 - 2.0 * np.sum(u[i] * u[j], axis=1), 0.0))
    d_lo = np.linalg.norm(pos[i] - pos[j], axis=1)
    return {
        "pearson": round(galaxy._pearson(d_hi, d_lo), 4),
        "spearman": round(galaxy._pearson(galaxy._ranks(d_hi), galaxy._ranks(d_lo)), 4),
    }


def run(z: np.ndarray, label: str) -> None:
    print(f"\n--- {label} ---")
    print(f"{'projector':12} {'metric':7} {'neg mass':>9} {'3 axes':>8} "
          f"{'r(cos)':>8} {'rho(cos)':>9} {'r(chord)':>9}")
    # `cmds-chord` was a projector until 2026-08-03 and was removed once this measurement
    # said it was worse on both yardsticks. The metric survives in
    # `galaxy.mds_squared_distances`, so the comparison is still runnable — it just goes
    # through `_classical_mds` directly rather than through a projector nobody should pick.
    for method, metric in (("cmds", "cosine"), ("chord (removed)", "chord")):
        # Mirror `project`'s own full-vs-landmark decision. Calling `_classical_mds` on the
        # whole matrix regardless was the first version of this and it is not a small
        # mistake: 13 848 knots is a 1.5 GB matrix and an O(n^3) eigendecomposition, where
        # the build itself would have used 800 landmarks.
        if z.shape[0] <= galaxy.CMDS_FULL_MAX:
            u = galaxy._unit_rows(z)
            d2 = galaxy.mds_squared_distances(u, u, metric)
            np.fill_diagonal(d2, 0.0)
            pos, info = galaxy._classical_mds(d2)
            info = {**info, "mode": "full"}
        else:
            pos, info = galaxy._landmark_mds(z, seed=0, metric=metric)
            info = {**info, "mode": "landmark"}
        info = {**info, "metric": metric}
        f = galaxy.faithfulness(z, pos, seed=0)
        fc = chord_faithfulness(z, pos, seed=0)
        print(f"{method:12} {info['metric']:7} {info['negativeEigenvalueMass'] * 100:8.1f} % "
              f"{sum(info['varianceRatio']) * 100:7.1f} % {f['pearson']:8.4f} "
              f"{f['spearman']:9.4f} {fc['pearson']:9.4f}")


run(z, f"the build's own path ({'landmark' if z.shape[0] > galaxy.CMDS_FULL_MAX else 'full'} MDS)")

# The landmark approximation is the obvious confound — 800 of 13 848 rows carry the fit,
# and a metric could plausibly interact with that sampling. Repeat on a subsample small
# enough for the full eigendecomposition, where there is no approximation left to blame.
sub = np.random.default_rng(0).choice(z.shape[0], min(galaxy.CMDS_FULL_MAX, z.shape[0]),
                                      replace=False)
run(z[sub], f"full eigendecomposition, {len(sub)} knots subsampled")

print(
    "\nneg mass is the share of the eigenvalue spectrum that is negative — the part of the\n"
    "fitted space that cannot exist. `3 axes` is of the *positive* mass, so under cosine\n"
    "it is a share of a quantity that is itself partly imaginary.\n"
    "r/rho are the build's faithfulness against 32-d cosine distance, which is the claim\n"
    "the app makes; r(chord) grades the chord fit on its own target. **rho settles it**:\n"
    "the two dissimilarities are monotone in each other, so a rank correlation cannot\n"
    "favour either yardstick."
)

# --- why the impossible space wins, and what negativeEigenvalueMass is actually measuring
#
# The chord fit losing on cosine distance is unsurprising. The chord fit losing on *chord*
# distance is not, and it needs an explanation before the result can be used.
#
# The explanation is reweighting. Every one of these metrics is a monotone function of the
# same cosine distance, so they order every pair identically and differ only in how much
# weight they put on far pairs against near ones. `(1-cos)^p` for larger p stretches the
# far pairs, and cMDS's top-3 truncation then spends its three axes on the coarse
# separations — which is what a random-pair distance correlation rewards. The chord is
# p = 0.5, the flattest of the family and the one that spends the most on local detail
# the three axes cannot hold anyway.
#
# The sweep is the test: if reweighting is the mechanism, faithfulness rises with p and
# then falls, and it does — peaking near p = 1.5, with the shipped p = 1 just below it and
# the Euclidean-honest p = 0.5 worst of all.
sub_u = galaxy._unit_rows(z[sub])
cosd = np.maximum(1.0 - sub_u @ sub_u.T, 0.0)
np.fill_diagonal(cosd, 0.0)
print(f"\n--- the family `d = (1-cos)^p`, {len(sub)} knots, full eigendecomposition ---")
print(f"{'p':>6} {'neg mass':>9} {'r(cos)':>8} {'rho(cos)':>9}")
for p in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0):
    d2 = cosd ** (2 * p)
    np.fill_diagonal(d2, 0.0)
    pos, info = galaxy._classical_mds(d2)
    f = galaxy.faithfulness(z[sub], pos, seed=0)
    tag = {0.5: "  <- chord, the honest Euclidean one", 1.0: "  <- shipped"}.get(p, "")
    print(f"{p:6.1f} {info['negativeEigenvalueMass'] * 100:8.1f} % "
          f"{f['pearson']:8.4f} {f['spearman']:9.4f}{tag}")

print(
    "\n**negativeEigenvalueMass does not measure how much the picture has to invent**, and\n"
    "galaxy.py said for a year that it did. Faithfulness across this family peaks at 62 %\n"
    "negative mass and is at its worst at 0 %: the two are decoupled, and if anything the\n"
    "indefiniteness runs the right way. It measures one true thing — that classical MDS is\n"
    "being fitted to a dissimilarity no Euclidean space can hold — and nothing at all about\n"
    "the quality of the answer.\n"
    "\nSo the chord metric was measured and **removed** rather than shipped, and `pacmap`\n"
    "is the default for reasons the local metrics settled separately. p = 1.5\n"
    "measures best by 0.008 and is NOT adopted: it is a fitted exponent with no argument\n"
    "behind it, on one seed, and a knob tuned to a faithfulness number is how the match ramp\n"
    "got into trouble."
)
