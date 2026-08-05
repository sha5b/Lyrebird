"""How does phylogenetic signal in an acoustic trait recover as per-species sampling deepens?

`g2_pgls.py` measured three points and read them as a story about noise: fitted Pagel's
lambda on species-level f0 residuals is **0.000** at `n_syllables >= 100` and **0.291** at
`>= 400`, and a lambda of zero cannot be true of birdsong. Measurement error pushes lambda
toward zero and attenuates a standardised slope by the same mechanism, and both recovered
together at depth. `recordist_bias_comparative.py` has since named one component of that
noise: two recordists on the same species disagree on its median pitch by 0.638 of the
variance that separates species.

This turns three points into a curve, which is the form the claim is actually about: **how
much per-species audio does a large opportunistic archive need before a species-level
acoustic trait carries measurable phylogenetic signal?** Nobody has published that, and it
is a question every comparative study drawing on these archives implicitly answers by
choosing a sampling floor.

**The confound, and the control that removes it.** Raising the floor also shrinks the sample:
lambda could climb because the trait got cleaner, or because a small ML fit on few species is
unstable and biased. So every depth arm is paired with a **matched-n control** — a random
subsample of the *unfiltered* species set at the same size, same trees, same estimator. If
lambda climbs with depth and stays flat in the matched-n controls, the recovery is about
depth. If both climb together, it is about n and the depth reading is withdrawn.

**PRE-REGISTERED, before the run.**

1. Fitted lambda increases with the per-species syllable floor, and the deepest arm exceeds
   the shallowest by at least 0.15.
2. The matched-n controls do **not** reproduce that climb: their lambda spread across floors
   stays below half the depth arms' spread.
3. The standardised slope's magnitude increases with the floor, i.e. attenuation falls as
   the trait gets cleaner.

Clause 2 is the one that decides whether this is a result or an artefact. Any of them failing
is reportable as it stands and no threshold moves afterwards.

Usage:
    .venv/bin/python analysis/lambda_recovery_curve.py [--trees 10]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dendropy  # noqa: E402

from g2_pgls import masses, pgls_lambda, standardised  # noqa: E402
from w2_learners import tree_path, vcv  # noqa: E402

F0_CACHE = ROOT / "out/external/species-f0.json"
OUT = Path(__file__).resolve().parent / "lambda_recovery_curve.json"

FLOORS = (0, 50, 100, 200, 300, 400, 600)
SEED = 0
#: Pre-registered thresholds.
MIN_LAMBDA_CLIMB = 0.15
CONTROL_SPREAD_SHARE = 0.5


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def tip_of(species_id: str) -> str:
    """`sclateria_naevia` -> `Sclateria_naevia`, BirdTree's tip label form."""
    head, _, tail = species_id.partition("_")
    return f"{head.capitalize()}_{tail}" if tail else head.capitalize()


def arm(rows, trees, label) -> dict:
    tips = [r["tip"] for r in rows]
    y = np.log(np.array([r["f0"] for r in rows]))
    x = np.log(np.array([r["mass"] for r in rows]))
    mats = [vcv(t, tips) for t in trees]
    per = [pgls_lambda(y, x, m) for m in mats]
    ols = standardised(y, x, None)
    return {
        "label": label,
        "n": len(rows),
        "median_syllables": float(np.median([r["n"] for r in rows])),
        "lambda": float(np.mean([p["lambda"] for p in per])),
        "lambda_min": float(np.min([p["lambda"] for p in per])),
        "lambda_max": float(np.max([p["lambda"] for p in per])),
        "beta_pgls": float(np.mean([p["beta"] for p in per])),
        "p_pgls": float(np.median([p["p"] for p in per])),
        "beta_ols": ols["beta"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trees", type=int, default=10)
    args = ap.parse_args()

    f0 = json.loads(F0_CACHE.read_text())
    mass = masses()
    rows = []
    for sid, rec in f0.items():
        tip = tip_of(sid)
        # AVONET's `Species2` is space-separated ("Sclateria naevia"); BirdTree tips are
        # underscored. Try both rather than assume one.
        m = mass.get(tip.replace("_", " ")) or mass.get(tip)
        if m is None or not rec.get("f0_median"):
            continue
        rows.append({
            "tip": tip, "f0": float(rec["f0_median"]),
            "mass": float(m), "n": int(rec.get("n_syllables") or 0),
        })
    log(f"species with f0 and mass: {len(rows)}")

    log(f"reading {args.trees} posterior trees ...")
    wanted = {r["tip"] for r in rows}
    trees = []
    with tree_path().open() as fh:
        for i, line in enumerate(fh):
            if i >= args.trees:
                break
            t = dendropy.Tree.get(data=line, schema="newick", preserve_underscores=True)
            t.retain_taxa_with_labels(wanted)
            trees.append(t)
    present = {t.label for t in trees[0].taxon_namespace}
    rows = [r for r in rows if r["tip"] in present]
    log(f"species on the tree: {len(rows)}")

    rng = np.random.default_rng(SEED)
    depth, control = [], []
    for floor in FLOORS:
        use = [r for r in rows if r["n"] >= floor]
        if len(use) < 60:
            log(f"floor {floor}: only {len(use)} species, skipped")
            continue
        log(f"floor {floor}: {len(use)} species ...")
        depth.append(arm(use, trees, f"n_syllables >= {floor}"))

        # matched-n control: same size, drawn from the UNFILTERED set
        idx = rng.permutation(len(rows))[: len(use)]
        control.append(arm([rows[i] for i in idx], trees,
                           f"random n={len(use)}"))

    lam_d = [a["lambda"] for a in depth]
    lam_c = [a["lambda"] for a in control]
    climb = lam_d[-1] - lam_d[0] if len(lam_d) > 1 else float("nan")
    spread_d = max(lam_d) - min(lam_d) if lam_d else float("nan")
    spread_c = max(lam_c) - min(lam_c) if lam_c else float("nan")
    beta_d = [abs(a["beta_pgls"]) for a in depth]

    result = {
        "trees": args.trees,
        "floors": list(FLOORS),
        "depth_arms": depth,
        "matched_n_controls": control,
        "clause1": {
            "lambda_climb": climb,
            "threshold": MIN_LAMBDA_CLIMB,
            "held": bool(climb >= MIN_LAMBDA_CLIMB),
        },
        "clause2": {
            "depth_spread": spread_d,
            "control_spread": spread_c,
            "threshold_share": CONTROL_SPREAD_SHARE,
            "held": bool(spread_c < CONTROL_SPREAD_SHARE * spread_d) if spread_d else None,
        },
        "clause3": {
            "beta_first": beta_d[0] if beta_d else None,
            "beta_last": beta_d[-1] if beta_d else None,
            "held": bool(len(beta_d) > 1 and beta_d[-1] > beta_d[0]),
        },
    }

    print("=" * 82)
    print("Phylogenetic signal in species-level f0, as per-species sampling deepens")
    print("=" * 82)
    print("  DEPTH ARMS")
    print("  arm                      n   med syl   lambda  [min,max]      beta   p")
    for a in depth:
        print(f"  {a['label']:20s} {a['n']:6d} {a['median_syllables']:9.0f}"
              f"   {a['lambda']:6.3f}  [{a['lambda_min']:.2f},{a['lambda_max']:.2f}]"
              f"  {a['beta_pgls']:+8.3f}  {a['p_pgls']:.2g}")
    print()
    print("  MATCHED-n CONTROLS  (same size, drawn from the unfiltered set)")
    print("  arm                      n   med syl   lambda  [min,max]      beta")
    for a in control:
        print(f"  {a['label']:20s} {a['n']:6d} {a['median_syllables']:9.0f}"
              f"   {a['lambda']:6.3f}  [{a['lambda_min']:.2f},{a['lambda_max']:.2f}]"
              f"  {a['beta_pgls']:+8.3f}")
    print()
    for k in ("clause1", "clause2", "clause3"):
        print(f"  {k}: {json.dumps(result[k])}")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
