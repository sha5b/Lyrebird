"""Clause 2 failed. What does the lambda estimator do at these sample sizes when nothing is there?

`lambda_recovery_curve.py` pre-registered three clauses and clause 2 — the one that decides
whether the depth reading is a result or an artefact — did not hold: the matched-n controls'
lambda spread (0.230) is not below half the depth arms' (0.319). Per the pre-registration the
depth reading is withdrawn, and no threshold moves afterwards.

This script asks the follow-up question, which the failed clause cannot answer on its own:
**why** did the controls spread that far? The curve draws exactly *one* control subsample per
size, so a control arm's lambda is a single realisation of the estimator at that n. Three of
the seven landed at 6.6e-5 — that is `minimize_scalar`'s converged lower boundary on (0, 1),
so the maximum-likelihood estimate is at zero — and their reported interval had **zero width**,
because `lambda_min`/`lambda_max` in that script range over the ten posterior trees and not
over the sampling of species. An interval that reads zero-width while its neighbouring arms
differ by 0.1 is measuring the wrong source of variation.

So: B independent control draws per size instead of one, giving the estimator's own null
distribution at each n. Each depth arm can then be read against the null band at its own
sample size rather than against a single draw, and the share of control draws that collapse to
the boundary says directly how stable the estimator is there.

This measures the instrument, not the birds. It cannot revive the withdrawn depth reading —
that clause is settled — and it is not a new test of it. It says what a future design would
have to do to ask the depth question properly.

Sizes are the depth arms' own n, minus the full set (2 812 species is every row, so there is
no subsample to draw) and it stops at 1 379 because the cost is a Cholesky per likelihood
step at n x n.

Usage:
    .venv/bin/python analysis/lambda_null_band.py [--reps 20] [--trees 3]
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dendropy  # noqa: E402

from g2_pgls import masses, pgls_lambda  # noqa: E402
from lambda_recovery_curve import F0_CACHE, tip_of  # noqa: E402
from w2_learners import tree_path, vcv  # noqa: E402

OUT = Path(__file__).resolve().parent / "lambda_null_band.json"
CURVE = Path(__file__).resolve().parent / "lambda_recovery_curve.json"

#: The depth arms' sample sizes, from the curve. 2 812 is the whole set — no null exists.
SIZES = (70, 76, 82, 123, 651, 1379)
#: `minimize_scalar(bounds=(0, 1), xatol=1e-4)` converges here when the MLE is at zero.
BOUNDARY = 1e-3
SEED = 1  # not the curve's seed, so these draws are independent of its single controls


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--trees", type=int, default=3)
    args = ap.parse_args()

    f0 = json.loads(F0_CACHE.read_text())
    mass = masses()
    rows = []
    for sid, rec in f0.items():
        tip = tip_of(sid)
        m = mass.get(tip.replace("_", " ")) or mass.get(tip)
        if m is None or not rec.get("f0_median"):
            continue
        rows.append({"tip": tip, "f0": float(rec["f0_median"]), "mass": float(m)})

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
    bands = []
    for n in SIZES:
        if n > len(rows):
            log(f"n={n} exceeds {len(rows)} species, skipped")
            continue
        lams = []
        for b in range(args.reps):
            idx = rng.permutation(len(rows))[:n]
            sub = [rows[i] for i in idx]
            tips = [r["tip"] for r in sub]
            y = np.log(np.array([r["f0"] for r in sub]))
            x = np.log(np.array([r["mass"] for r in sub]))
            per = [pgls_lambda(y, x, vcv(t, tips))["lambda"] for t in trees]
            lams.append(float(np.mean(per)))
            log(f"  n={n} rep {b + 1}/{args.reps}: lambda {lams[-1]:.4f}")
        q = np.quantile(lams, [0.05, 0.5, 0.95])
        bands.append({
            "n": n,
            "reps": len(lams),
            "lambda_p05": float(q[0]),
            "lambda_median": float(q[1]),
            "lambda_p95": float(q[2]),
            "lambda_min": float(np.min(lams)),
            "lambda_max": float(np.max(lams)),
            "lambda_iqr": float(np.subtract(*np.quantile(lams, [0.75, 0.25]))),
            "share_at_boundary": round(sum(1 for v in lams if v < BOUNDARY) / len(lams), 3),
            "lambdas": [round(v, 5) for v in lams],
        })
        log(f"n={n}: null band [{q[0]:.3f}, {q[2]:.3f}], median {q[1]:.3f}, "
            f"{bands[-1]['share_at_boundary']:.0%} at the boundary")

    # Each depth arm read against the null band at its own n, which is what the curve's
    # single control draw could not do. Recorded as context for the withdrawal, not as a
    # replacement test: clause 2 is settled and this design was written after seeing it.
    depth = {}
    if CURVE.exists():
        curve = json.loads(CURVE.read_text())
        by_n = {b["n"]: b for b in bands}
        for a in curve["depth_arms"]:
            band = by_n.get(a["n"])
            if not band:
                continue
            depth[a["label"]] = {
                "n": a["n"],
                "lambda": round(a["lambda"], 4),
                "null_p05": round(band["lambda_p05"], 4),
                "null_p95": round(band["lambda_p95"], 4),
                "above_null_p95": bool(a["lambda"] > band["lambda_p95"]),
            }

    result = {
        "reps": args.reps,
        "trees": args.trees,
        "seed": SEED,
        "species": len(rows),
        "boundary": BOUNDARY,
        "bands": bands,
        "depth_arms_vs_null": depth,
        "reading": "The null band is the estimator's spread at a given n when species are "
                   "drawn without regard to sampling depth. Wide bands and a nonzero "
                   "share_at_boundary say the estimator is unstable at that n, which is "
                   "what clause 2 detected with a single draw per size.",
    }

    print("=" * 78)
    print("Pagel's lambda: the estimator's null distribution at each sample size")
    print("=" * 78)
    print(f"  {args.reps} draws per size, {args.trees} trees each, {len(rows)} species")
    print()
    print("     n   reps   p05     median   p95     min     max    at boundary")
    for b in bands:
        print(f"  {b['n']:5d} {b['reps']:6d}  {b['lambda_p05']:.3f}   "
              f"{b['lambda_median']:.3f}    {b['lambda_p95']:.3f}   "
              f"{b['lambda_min']:.3f}   {b['lambda_max']:.3f}   "
              f"{b['share_at_boundary']:>6.0%}")
    if depth:
        print()
        print("  depth arm vs the null band at its own n")
        for label, d in depth.items():
            verdict = "above p95" if d["above_null_p95"] else "inside the null band"
            print(f"    {label:22s} lambda {d['lambda']:.3f}  "
                  f"null [{d['null_p05']:.3f}, {d['null_p95']:.3f}]  -> {verdict}")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
