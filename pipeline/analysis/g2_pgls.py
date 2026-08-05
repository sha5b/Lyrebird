"""G2 under PGLS — the half of the gate that was owed. (docs/24 Phase 0)

G2's pre-registration asks for "a negative slope significant under a phylogenetic
generalised least squares fit, with an effect size inside the range the comparative
literature already reports". The 2026-08-04 run answered the first half with OLS and said
so. This is the second half, and it is cheap because W2 already put BirdTree on disk and
already has a working VCV and GLS.

**Why it is not a formality.** Body mass and song frequency are both strongly conserved
within clades, so an OLS over 1 578 species is counting each family many times over. PGLS
is the correction, and the honest possibility is that our r = -0.247 is mostly one big
signal repeated — in which case the effect survives but shrinks, and the gate's "inside
the range the literature reports" becomes the question rather than the sign.

**The comparison target.** Mikula et al. 2021 (Ecology Letters, doi:10.1111/ele.13662),
PGLS over 5 085 passerines, peak frequency on body mass, **standardised slope -0.51**. A
standardised slope is what a correlation looks like after both sides are z-scored, so this
script reports the standardised PGLS slope and holds *that* against -0.51, rather than
holding a raw log-log slope against it.

Two populations are reported rather than one, because G2's own OLS result showed the
effect sharpening with per-species sample depth and that has to be visible here too.

Usage:  .venv/bin/python analysis/g2_pgls.py
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from w2_learners import gls, tree_path, vcv  # noqa: E402

F0_CACHE = ROOT / "out/external/species-f0.json"
TAXON = ROOT / "out/external/BLIOCPhyloMasterTax.csv"
AVONET = ROOT / "out/external/AVONET.xlsx"
INVENTORY = ROOT.parent / "data/learned-inventory.json"
OUT = Path(__file__).resolve().parent / "g2_pgls.json"

TREE_SAMPLE = 10
MIKULA_STANDARDISED = -0.51


def masses() -> dict[str, float]:
    import openpyxl

    wb = openpyxl.load_workbook(AVONET, read_only=True)
    ws = wb["AVONET2_eBird"]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    i_n, i_m = hdr.index("Species2"), hdr.index("Mass")
    return {r[i_n]: float(r[i_m]) for r in it if r[i_n] and r[i_m] is not None}


def _z(v: np.ndarray) -> np.ndarray:
    return (v - v.mean()) / v.std(ddof=0)


def pgls_lambda(y: np.ndarray, x: np.ndarray, c: np.ndarray) -> dict[str, float]:
    """PGLS with Pagel's lambda fitted by maximum likelihood, on z-scored variables.

    **Forcing Brownian motion was the first attempt and it had to be abandoned.** With
    lambda pinned at 1 the ten posterior trees returned standardised slopes spanning
    -1.962 to +0.001 — a range that crosses zero and is wider than any real disagreement
    between two samples of the same posterior. The VCV was not the problem: every tree
    came back exactly ultrametric and positive-definite, with condition numbers around
    1e6 to 1e7, which float64 Cholesky handles. The problem is that Brownian is a *model
    assumption*, and forcing it on a trait with less signal than that over-corrects, so
    the estimate is driven by a handful of deep splits whose arrangement differs between
    trees.

    Fitting lambda is the standard practice this should have used from the start, and it
    is what Mikula et al. did. It also reports something worth knowing in itself: lambda
    is how much phylogenetic signal the residuals actually carry.

        C(lambda) = lambda * C + (1 - lambda) * diag(C)

    which leaves the variances alone and scales only the shared history.
    """
    from scipy import optimize, stats

    n = len(y)
    design = np.column_stack([np.ones(n), _z(x)])
    target = _z(y)
    diag = np.diag(np.diag(c))

    def fit(lam: float):
        cl = lam * c + (1.0 - lam) * diag
        lo = np.linalg.cholesky(cl)
        yt = np.linalg.solve(lo, target)
        xt = np.linalg.solve(lo, design)
        beta, *_ = np.linalg.lstsq(xt, yt, rcond=None)
        resid = yt - xt @ beta
        rss = float(resid @ resid)
        logdet = 2.0 * float(np.sum(np.log(np.diag(lo))))
        # Profile likelihood: sigma^2 at its MLE, so only lambda is being searched.
        nll = 0.5 * (n * math.log(2 * math.pi * rss / n) + logdet + n)
        return nll, beta, xt, rss

    best = optimize.minimize_scalar(
        lambda lam: fit(lam)[0], bounds=(0.0, 1.0), method="bounded",
        options={"xatol": 1e-4},
    )
    lam = float(best.x)
    _nll, beta, xt, rss = fit(lam)
    dof = n - design.shape[1]
    cov = (rss / dof) * np.linalg.inv(xt.T @ xt)
    se = math.sqrt(cov[1, 1])
    t = beta[1] / se
    return {
        "beta": float(beta[1]), "se": se, "t": float(t),
        "p": float(2 * stats.t.sf(abs(t), dof)), "lambda": lam, "n": n,
    }


def standardised(y: np.ndarray, x: np.ndarray, c: np.ndarray | None) -> dict[str, float]:
    """OLS on z-scored y and x — the lambda = 0 corner, kept as the comparison."""
    design = np.column_stack([np.ones(len(y)), _z(x)])
    return gls(_z(y), design, c)


def main() -> int:
    import dendropy

    f0 = json.loads(F0_CACHE.read_text())
    mass = masses()
    tax = {r["Scientific"]: r["TipLabel"] for r in csv.DictReader(TAXON.open())}
    inv = json.loads(INVENTORY.read_text())
    sci = {sp["id"]: sp["scientific"] for sp in inv["species"]}

    rows = []
    seen: set[str] = set()
    for species_id, rec in f0.items():
        name = sci.get(species_id)
        if not name:
            continue
        tip, m = tax.get(name), mass.get(name)
        if not tip or m is None or tip in seen:
            continue
        seen.add(tip)
        rows.append({
            "tip": tip, "name": name,
            "f0": rec["f0_median"], "mass": m, "n": rec["n_syllables"],
        })

    print("=" * 74)
    print("G2 under PGLS — larger birds sing lower, with phylogeny accounted for")
    print("=" * 74)
    print(f"  fitted species with f0                          {len(f0):5d}")
    print(f"  ...joined to AVONET mass and a BirdTree tip      {len(rows):5d}")

    print(f"  reading {TREE_SAMPLE} posterior trees...")
    wanted = {r["tip"] for r in rows}
    trees = []
    with tree_path().open() as fh:
        for i, line in enumerate(fh):
            if i >= TREE_SAMPLE:
                break
            t = dendropy.Tree.get(data=line, schema="newick", preserve_underscores=True)
            t.retain_taxa_with_labels(wanted)
            trees.append(t)
    present = {t.label for t in trees[0].taxon_namespace}
    rows = [r for r in rows if r["tip"] in present]
    print(f"  species on the tree                             {len(rows):5d}")

    results: dict[str, object] = {}
    # The deep arm is the test of the attenuation reading: if our slope falls short of the
    # published one because per-species f0 is noisy, it should lengthen where the sample
    # per species is largest, and lambda should stop sitting on zero.
    for label, floor in (("all species", 0), ("n_syllables >= 100", 100),
                         ("n_syllables >= 400", 400)):
        use = [r for r in rows if r["n"] >= floor]
        if len(use) < 50:
            continue
        tips = [r["tip"] for r in use]
        y = np.log(np.array([r["f0"] for r in use]))
        x = np.log(np.array([r["mass"] for r in use]))

        ols = standardised(y, x, None)
        mats = [vcv(t, tips) for t in trees]
        brownian = [standardised(y, x, m) for m in mats]
        per = [pgls_lambda(y, x, m) for m in mats]

        b = float(np.mean([p["beta"] for p in per]))
        lo = float(np.min([p["beta"] for p in per]))
        hi = float(np.max([p["beta"] for p in per]))
        pv = float(np.median([p["p"] for p in per]))
        lam = float(np.mean([p["lambda"] for p in per]))
        bb = float(np.mean([p["beta"] for p in brownian]))
        blo = float(np.min([p["beta"] for p in brownian]))
        bhi = float(np.max([p["beta"] for p in brownian]))

        print()
        print(f"  {label}  (n = {len(use)})")
        print(f"    standardised slope, OLS (lambda = 0)  {ols['beta']:+.3f}  p {ols['p']:.2g}")
        print(f"    ...forced Brownian (lambda = 1)       {bb:+.3f}  [{blo:+.3f}, {bhi:+.3f}]"
              "   <- unstable, see the docstring")
        print(f"    ...lambda fitted by ML                {b:+.3f}  "
              f"[{lo:+.3f}, {hi:+.3f}]  median p {pv:.2g}")
        print(f"    fitted lambda                         {lam:.3f}")
        print(f"    Mikula et al. 2021 (5 085 passerines) {MIKULA_STANDARDISED:+.3f}")
        neg = b < 0
        sig = pv < 0.05
        print(f"    negative {'yes' if neg else 'NO'}   significant {'yes' if sig else 'NO'}")
        results[label] = {
            "n": len(use), "ols_beta": ols["beta"], "ols_p": ols["p"],
            "brownian_beta_mean": bb, "brownian_beta_range": [blo, bhi],
            "pgls_beta_mean": b, "pgls_beta_range": [lo, hi], "pgls_p_median": pv,
            "lambda_mean": lam, "negative": bool(neg), "significant": bool(sig),
        }

    main_arm = results.get("all species", {})
    passed = bool(main_arm.get("negative")) and bool(main_arm.get("significant"))
    print()
    print(f"  G2 VERDICT under PGLS: {'PASS' if passed else 'FAIL'}")
    print("  The sign and the significance are the pre-registered half. Whether the")
    print("  magnitude sits 'inside the range the literature reports' is a judgement")
    print("  against -0.51, and the numbers above are what that judgement is made on.")

    OUT.write_text(json.dumps(results, indent=1, default=float))
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
