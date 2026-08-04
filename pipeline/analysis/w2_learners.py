"""W2 — do vocal learners have more complex song than non-learners? (docs/24 Phase 1)

Pre-registered in `docs/24-what-this-corpus-could-add-to-ornithology.md`:

    Phylogenetic generalised least squares on repertoire size, first-order entropy rate
    and repeat-class count, with learning status as the predictor and body mass as a
    covariate.

    gate: learners exceed non-learners on at least two of the three measures after
          phylogenetic correction.

**Why W2 runs when W1 does not.** G1 failed, and docs/24 §24.1 closes Phase 1 for "any
question that leans on production mechanics". W1 leans on exactly that. W2 does not: its
three measures come from segmentation, typing and transition counting, none of which
touch the fitted oscillator. Its exposure is to the recordist confound (G3, passed) and
to sampling effort, which is handled below.

**One covariate docs/24 did not ask for, and it is not optional.** Repertoire size and
entropy rate both rise with how much audio a species has — find more recordings, find
more types. Learners are not sampled at the same rate as non-learners in citizen-science
archives, so without `log(n_syllables)` in the model this measures collection effort and
calls it biology. It is added to every fit here and reported alongside the predictor.

**The honest limit, restated from docs/24 because it belongs next to the number.** Our
"repertoire size" is a count of machine-derived clusters. It is applied identically to
every species, which is what a comparative contrast needs; it is not a count any field
ornithologist would recognise as a repertoire.

DATA
  learning status   BirdTree's own `OscSubOsc` column (BLIOCPhyloMasterTax.csv), so the
                    oscine/suboscine split is the phylogeny authors' and not hand-typed
                    from a family list. Two codings are reported:
                      strict  Passeri = learner; Tyranni and non-passerines = not.
                      wide    ...plus parrots and hummingbirds as learners, which is what
                              the vocal-learning literature actually holds.
  phylogeny         BirdTree Ericson Stage-2 posterior, first TREE_SAMPLE trees, not a
                    consensus. The trees are ultrametric, so VCV_ij = h - D_ij/2.
  mass              AVONET (eBird taxonomy).

**CAVEAT added 2026-08-04, after `g2_pgls.py`.** The fits below force Brownian motion
(lambda = 1) rather than fitting Pagel's lambda, and G2 later showed that assumption is
unstable on this corpus — its forced-Brownian slopes spanned -1.962 to +0.001 across ten
trees from one posterior, and fitting lambda collapsed the range to [-0.214, -0.207]. The
same instability is visible here in the entropy row's [-0.067, +0.680].

**The verdict below is unaffected**, because it rests on the pre-model diagnostic — one
measure degenerate, another 85 % sampling effort — and not on any coefficient. But the
coefficients themselves should not be quoted as they stand, and a re-run on a deeper corpus
must fit lambda. `g2_pgls.pgls_lambda` is the implementation to reuse.

Usage:  .venv/bin/python analysis/w2_learners.py
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

INVENTORY = ROOT.parent / "data/learned-inventory.json"
TAXON = ROOT / "out/external/BLIOCPhyloMasterTax.csv"
AVONET = ROOT / "out/external/AVONET.xlsx"
F0_CACHE = ROOT / "out/external/species-f0.json"
TREES = Path(
    "/tmp/claude-1000/-home-sha5b-Documents-GitHub-Birdy/"
    "c1c0b9d0-6d5e-4390-9f42-087508a40cb8/scratchpad/AllBirdsEricson1.tre"
)
OUT = Path(__file__).resolve().parent / "w2_learners.json"

TREE_SAMPLE = 10

#: Non-passerine vocal learners, for the `wide` coding. Parrots and hummingbirds are the
#: two uncontested non-passerine learning clades.
WIDE_LEARNER_ORDERS = {"PSITTACIFORMES"}
WIDE_LEARNER_FAMILIES = {"Trochilidae"}


def entropy_rate(transitions: dict[str, dict[str, float]]) -> float:
    """First-order entropy rate, in bits per syllable.

    `sum_i pi_i * H(next | i)`, with `end` kept as an *outcome* (stopping is a choice the
    grammar makes) but not as a state. `pi` is the stationary distribution of the
    within-song part, by power iteration; a grammar whose recurrent part is degenerate
    falls back to a uniform weighting rather than being dropped, and that is rare enough
    to state but not rare enough to ignore.
    """
    states = sorted(transitions)
    if len(states) < 2:
        return float("nan")
    idx = {s: i for i, s in enumerate(states)}
    n = len(states)

    h = np.zeros(n)
    m = np.zeros((n, n))
    for s, nxt in transitions.items():
        i = idx[s]
        tot = sum(nxt.values())
        if tot <= 0:
            continue
        for t, p in nxt.items():
            q = p / tot
            if q > 0:
                h[i] -= q * math.log2(q)
            if t in idx:
                m[i, idx[t]] = q

    rs = m.sum(axis=1, keepdims=True)
    walk = np.divide(m, rs, out=np.full_like(m, 1.0 / n), where=rs > 0)
    pi = np.full(n, 1.0 / n)
    for _ in range(200):
        nxt = pi @ walk
        s = nxt.sum()
        if s <= 0:
            pi = np.full(n, 1.0 / n)
            break
        nxt /= s
        if np.abs(nxt - pi).sum() < 1e-10:
            pi = nxt
            break
        pi = nxt
    return float(pi @ h)


def measures() -> dict[str, dict[str, float]]:
    """scientific name -> the three W2 measures plus sampling effort.

    Effort comes from the store's own per-species syllable count, not from the
    inventory's `learnedFrom` sentence — only 10 of 2 650 species carry that sentence,
    so parsing it would have silently reduced W2 to a seven-species test.
    """
    inv = json.loads(INVENTORY.read_text())
    effort = json.loads(F0_CACHE.read_text()) if F0_CACHE.exists() else {}
    out: dict[str, dict[str, float]] = {}
    for sp in inv["species"]:
        g = sp.get("grammar") or {}
        tr = g.get("transitions") or {}
        st = g.get("songTyping") or {}
        eff = effort.get(sp["id"])
        if not eff:
            continue
        n_syl = int(eff["n_syllables"])
        out[sp["scientific"]] = {
            "repertoire": float(len(sp.get("syllables") or [])),
            "entropy": entropy_rate(tr),
            "repeat_types": float(st.get("repeatTypes", 0)),
            "bouts": float(st.get("bouts", 0)),
            "n_syllables": float(n_syl),
        }
    return out


def taxonomy() -> dict[str, dict[str, str]]:
    rows = list(csv.DictReader(TAXON.open()))
    return {r["Scientific"]: r for r in rows}


def masses() -> dict[str, dict[str, object]]:
    import openpyxl

    wb = openpyxl.load_workbook(AVONET, read_only=True)
    ws = wb["AVONET2_eBird"]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    i_n, i_m = hdr.index("Species2"), hdr.index("Mass")
    i_f, i_o = hdr.index("Family2"), hdr.index("Order2")
    return {
        r[i_n]: {"mass": float(r[i_m]), "family": r[i_f], "order": r[i_o]}
        for r in it
        if r[i_n] and r[i_m] is not None
    }


def vcv(tree, tips: list[str]) -> np.ndarray:
    """Shared root-to-MRCA path length for every pair, in one post-order pass.

    The obvious route — dendropy's pairwise distance matrix — is a Python call per pair,
    which at ~2 000 tips is four million calls per tree and does not finish. Here each
    internal node instead fills the block between its children *once*, with its own
    root-depth, and a binary tree has only about n such nodes. The numpy block assignment
    does the O(n^2) work in C.
    """
    index = {t: i for i, t in enumerate(tips)}
    for node in tree.preorder_node_iter():
        parent = node.parent_node
        node.depth = 0.0 if parent is None else parent.depth + (node.edge_length or 0.0)

    n = len(tips)
    c = np.zeros((n, n))
    for node in tree.postorder_node_iter():
        if node.is_leaf():
            # A leaf outside `tips` contributes to no pair among `tips`, and dropping it
            # changes no internal depth — so it is skipped rather than being an error.
            # Callers that prune once and then analyse a subset (g2_pgls.py's second arm)
            # rely on this; without it the tree and the index silently disagree.
            i = index.get(node.taxon.label if node.taxon else None)
            node.tips = np.empty(0, dtype=np.intp) if i is None else np.array([i], dtype=np.intp)
            continue
        groups = [ch.tips for ch in node.child_node_iter()]
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                c[np.ix_(groups[a], groups[b])] = node.depth
                c[np.ix_(groups[b], groups[a])] = node.depth
        node.tips = np.concatenate(groups) if groups else np.empty(0, dtype=np.intp)

    for node in tree.leaf_node_iter():
        i = index.get(node.taxon.label if node.taxon else None)
        if i is not None:
            c[i, i] = node.depth
    return c


def gls(y: np.ndarray, x: np.ndarray, c: np.ndarray | None) -> dict[str, float]:
    """Return the coefficient on column 1 of x (the learner dummy), with its t and p."""
    from scipy import stats

    if c is None:
        lo = np.eye(len(y))
    else:
        lo = np.linalg.cholesky(c)
    yt = np.linalg.solve(lo, y)
    xt = np.linalg.solve(lo, x)
    beta, *_ = np.linalg.lstsq(xt, yt, rcond=None)
    resid = yt - xt @ beta
    dof = len(y) - x.shape[1]
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.inv(xt.T @ xt)
    se = math.sqrt(cov[1, 1])
    t = beta[1] / se
    return {
        "beta": float(beta[1]),
        "se": float(se),
        "t": float(t),
        "p": float(2 * stats.t.sf(abs(t), dof)),
        "n": len(y),
    }


def main() -> int:
    import dendropy

    meas = measures()
    tax = taxonomy()
    mass = masses()

    rows = []
    for name, m in meas.items():
        t = tax.get(name)
        a = mass.get(name)
        if not t or not a or not math.isfinite(m["entropy"]):
            continue
        osc = t["OscSubOsc"]
        strict = osc == "Passeri"
        wide = strict or a["order"] in WIDE_LEARNER_ORDERS or a["family"] in WIDE_LEARNER_FAMILIES
        rows.append({
            "name": name, "tip": t["TipLabel"], "osc": osc,
            "strict": strict, "wide": wide, "mass": a["mass"],
            "family": a["family"], "order": a["order"], **m,
        })

    print("=" * 74)
    print("W2 — vocal learners against non-learners")
    print("=" * 74)
    print(f"  species in the inventory with a grammar          {len(meas):5d}")
    print(f"  ...joined to BirdTree taxonomy and AVONET mass   {len(rows):5d}")
    n_strict = sum(r["strict"] for r in rows)
    n_wide = sum(r["wide"] for r in rows)
    print(f"  learners, strict (Passeri only)                  {n_strict:5d}"
          f"   non-learners {len(rows) - n_strict:5d}")
    print(f"  learners, wide (+ parrots, hummingbirds)         {n_wide:5d}"
          f"   non-learners {len(rows) - n_wide:5d}")

    print()
    print("  raw group medians, before any correction:")
    print(f"    {'measure':14s} {'learner':>10s} {'non-learner':>12s}")
    for key in ("repertoire", "entropy", "repeat_types"):
        a = np.median([r[key] for r in rows if r["wide"]])
        b = np.median([r[key] for r in rows if not r["wide"]])
        print(f"    {key:14s} {a:10.2f} {b:12.2f}")
    a = np.median([r["n_syllables"] for r in rows if r["wide"]])
    b = np.median([r["n_syllables"] for r in rows if not r["wide"]])
    print(f"    {'n_syllables':14s} {a:10.2f} {b:12.2f}   <- the effort covariate,"
          " and note the gap")

    # ------------------------------------------------- can the measures answer at all?
    # Run BEFORE the model, because if the measures cannot carry the question then the
    # model's p-values are a null about our sampling and not a null about birds.
    print()
    print("  -- are the three measures able to answer this question? --")
    rep = np.array([r["repertoire"] for r in rows])
    rt = np.array([r["repeat_types"] for r in rows])
    ns = np.array([r["n_syllables"] for r in rows])
    r_eff = float(np.corrcoef(np.log(rep + 1), np.log(ns + 1))[0, 1])
    print(f"    repertoire vs sampling effort   r = {r_eff:+.3f}"
          "   <- the repertoire proxy is mostly a count of our own audio")
    print(f"    repeat_types is zero on         {100 * (rt == 0).mean():.1f}% of species"
          "   <- degenerate, like `harmonic` clipping at 1.0")
    print(f"    repertoire median {np.median(rep):.0f}, p90 {np.percentile(rep, 90):.0f},"
          f" max {rep.max():.0f}   (field oscine repertoires reach dozens)")
    print("    median repertoire by how much audio the species has:")
    for lo, hi in ((0, 30), (30, 100), (100, 300), (300, 10**9)):
        m = (ns >= lo) & (ns < hi)
        if m.sum() > 30:
            print(f"      {lo:5d}-{hi if hi < 10**9 else 'inf':<6} syllables   "
                  f"n {int(m.sum()):5d}   median repertoire {np.median(rep[m]):.1f}")
    print("    -> one of the three measures is degenerate and another is dominated by")
    print("       collection effort. A 2-of-3 gate cannot be cleared by the one that is")
    print("       left, so what follows is reported as a REFUSAL, not as a null result")
    print("       about vocal learning.")

    # -------------------------------------------------------------- trees
    print()
    print(f"  reading {TREE_SAMPLE} posterior trees...")
    tips_wanted = {r["tip"] for r in rows}
    trees = []
    with TREES.open() as fh:
        for i, line in enumerate(fh):
            if i >= TREE_SAMPLE:
                break
            t = dendropy.Tree.get(data=line, schema="newick", preserve_underscores=True)
            t.retain_taxa_with_labels(tips_wanted)
            trees.append(t)
    present = {t.label for t in trees[0].taxon_namespace}
    use = [r for r in rows if r["tip"] in present]
    # A tip label can repeat in our rows only if two of our species map to one BirdTree
    # tip; keep the first so the VCV stays positive-definite.
    seen: set[str] = set()
    use = [r for r in use if not (r["tip"] in seen or seen.add(r["tip"]))]
    print(f"  species on the tree and in the model              {len(use):5d}")

    tips = [r["tip"] for r in use]
    results: dict[str, object] = {}

    for coding in ("strict", "wide"):
        print()
        print(f"  === coding: {coding} ===")
        learner = np.array([1.0 if r[coding] else 0.0 for r in use])
        lmass = np.log(np.array([r["mass"] for r in use]))
        leff = np.log(np.array([max(r["n_syllables"], 1.0) for r in use]))
        x = np.column_stack([np.ones(len(use)), learner, lmass, leff])

        for key in ("repertoire", "entropy", "repeat_types"):
            y = np.array([r[key] for r in use])
            if key != "entropy":
                y = np.log1p(y)
            ols = gls(y, x, None)
            per = [gls(y, x, vcv(t, tips)) for t in trees]
            b = float(np.mean([p["beta"] for p in per]))
            pv = float(np.median([p["p"] for p in per]))
            lo = float(np.min([p["beta"] for p in per]))
            hi = float(np.max([p["beta"] for p in per]))
            sign = "learners HIGHER" if b > 0 else "learners lower"
            ok = b > 0 and pv < 0.05
            print(f"    {key:13s} OLS beta {ols['beta']:+.3f} (p {ols['p']:.2g})"
                  f"   PGLS beta {b:+.3f} [{lo:+.3f},{hi:+.3f}]"
                  f"  median p {pv:.2g}   {sign} {'*' if ok else ''}")
            results[f"{coding}:{key}"] = {
                "ols": ols, "pgls_beta_mean": b, "pgls_beta_range": [lo, hi],
                "pgls_p_median": pv, "supports_gate": bool(ok),
            }

        wins = sum(
            1 for key in ("repertoire", "entropy", "repeat_types")
            if results[f"{coding}:{key}"]["supports_gate"]
        )
        print(f"    -> {wins} of 3 measures support the hypothesis after phylogenetic"
              f" correction. Gate needs 2. {'PASS' if wins >= 2 else 'FAIL'}")
        results[f"{coding}:verdict"] = "PASS" if wins >= 2 else "FAIL"

    OUT.write_text(json.dumps(results, indent=1, default=float))
    print()
    print(f"  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
