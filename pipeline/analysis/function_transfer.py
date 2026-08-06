"""Can a documented function be predicted on a species the model never saw?

This is the measurement that decides the second of the app's three refusals — *"it does not
say what a fitted type is for"*. HANDOFF §9 named the blocker and this takes the number:
the entire anchor set is **53 documented functions over 12 species**, and function is
species-specific, so the honest prior is that cross-species transfer is weak. It is cheap to
measure and **the measurement is the deliverable** — a null result closes the question
honestly and is worth as much as a positive one.

PRE-REGISTERED, before the run.

Leave-one-species-out in the shipped 32-d critic embedding: hold out one species, and for
each of its documented knots predict the `functionClass` of its nearest documented knot
among the *other* eleven. Cosine, the comparison the matcher performs. Nothing is trained —
a 53-point set cannot support a fitted model, and nearest-neighbour transfer is the most
generous thing the data allows, so a failure here is a failure of the premise rather than of
the method.

  arm   LOSO k=1        nearest documented knot of another species
  arm   LOSO k=3        majority of the three nearest, ties to the nearer
  base  majority class  always answer `structural`, which is 24 of the 53. THE NUMBER TO
                        BEAT — the classes are badly unbalanced and an accuracy under this
                        is worse than a constant answer.
  base  within-species  nearest neighbour *including* the held-out species' own knots. The
                        ceiling: if this fails too, the embedding carries nothing about
                        function at all and the cross-species question does not arise.
  null  permutation     `functionClass` shuffled across all 53 knots, LOSO re-run 2 000
                        times. geometry.py's discipline — a grouping that cannot beat its
                        own shuffle is reported as no relation.

GATES:

  G1  LOSO k=1 accuracy > the majority-class baseline.
  G2  permutation p < 0.05, one-sided.
  G3  reported, not gated: within-species accuracy, as the ceiling.
  G4  reported, not gated: G1 restricted to the 28 knots whose `confidence` is
      `documented`. 15 of the 53 labels are `inferred` and 10 `experimental`, so the headline
      set is partly inference — if the result only holds on the soft labels it is not a
      result about documented function.

If G1 or G2 fails, the refusal stands as written and the honest form of any future claim is
the one §9 already stated: never "L33 is an alarm call", only "L33 sits where N % of
documented neighbours are alarm calls, and this predictor scores X on species it never saw"
— and X is what this file measures. A predictor that ships its own error rate is allowed; an
identity is not.

Runs against the installed assets. Nothing is written.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

#: One row per knot: vector32, vector (28-d), featuresLo. Only the first block is read.
ROW_FLOATS = 68
VECTOR32 = 32


def load(assets: Path):
    """The documented knots: 32-d vectors, species, function class, confidence."""
    items = json.loads((assets / "centroids.json").read_text())["items"]
    rows = np.fromfile(assets / "centroid-vectors.f32", dtype="<f4").reshape(-1, ROW_FLOATS)
    if rows.shape[0] != len(items):
        raise SystemExit(f"{rows.shape[0]} vector rows against {len(items)} centroids")
    keep = [i for i, it in enumerate(items) if it.get("function")]
    z = rows[keep, :VECTOR32].astype(np.float64)
    n = np.linalg.norm(z, axis=1, keepdims=True)
    return (
        z / np.maximum(n, 1.0e-12),
        np.array([items[i]["speciesId"] for i in keep]),
        np.array([items[i].get("functionClass", "") for i in keep]),
        np.array([items[i].get("confidence", "") for i in keep]),
    )


def loso(uz: np.ndarray, species: np.ndarray, label: np.ndarray, k: int = 1,
         within: bool = False) -> tuple[int, int]:
    """Hits and trials for leave-one-species-out nearest-neighbour transfer.

    `within=True` keeps the held-out species' own knots in the pool, which is the ceiling
    arm — it answers "does the space know about function at all" rather than "does function
    cross a species boundary".
    """
    sim = uz @ uz.T
    np.fill_diagonal(sim, -np.inf)  # a knot is not its own neighbour in any arm
    hits = 0
    trials = 0
    for i in range(uz.shape[0]):
        s = sim[i].copy()
        if not within:
            s[species == species[i]] = -np.inf
        order = np.argsort(-s)
        pool = [j for j in order[:k] if np.isfinite(s[j])]
        if not pool:
            continue  # a species holding the only member of the pool has nobody to ask
        trials += 1
        vote = Counter(label[j] for j in pool)
        top = max(vote.values())
        # Ties fall to the nearest, and `pool` is already in distance order.
        best = next(label[j] for j in pool if vote[label[j]] == top)
        hits += best == label[i]
    return hits, trials


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", default="app/static/lyrebird", type=Path)
    ap.add_argument("--permutations", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    uz, species, label, confidence = load(args.assets)
    rng = np.random.default_rng(args.seed)

    print(f"{uz.shape[0]} documented knots over {len(set(species))} species, "
          f"{len(set(label))} function classes")
    print(f"classes: {dict(Counter(label).most_common())}")
    print(f"confidence: {dict(Counter(confidence).most_common())}")
    print(f"per species: {dict(Counter(species).most_common())}\n")

    majority = Counter(label).most_common(1)[0]
    base = majority[1] / len(label)

    h1, t1 = loso(uz, species, label, k=1)
    h3, t3 = loso(uz, species, label, k=3)
    hw, tw = loso(uz, species, label, k=1, within=True)

    print("| arm | accuracy | hits/trials |")
    print("|---|---|---|")
    print(f"| LOSO k=1 | {h1 / t1:.4f} | {h1}/{t1} |")
    print(f"| LOSO k=3 | {h3 / t3:.4f} | {h3}/{t3} |")
    print(f"| majority class (`{majority[0]}`) | {base:.4f} | {majority[1]}/{len(label)} |")
    print(f"| within-species k=1 (ceiling) | {hw / tw:.4f} | {hw}/{tw} |")

    # The null: shuffle the labels, keep the geometry and the species blocks exactly as they
    # are. What survives is only what the *arrangement* of labels in the space explains.
    obs = h1 / t1
    null = np.empty(args.permutations)
    for p in range(args.permutations):
        shuffled = rng.permutation(label)
        hp, tp = loso(uz, species, shuffled, k=1)
        null[p] = hp / tp if tp else 0.0
    pval = (1 + int((null >= obs).sum())) / (1 + args.permutations)
    print(f"\npermutation null over {args.permutations} shuffles: "
          f"mean {null.mean():.4f}, 95th {np.quantile(null, 0.95):.4f}")

    # G4: the hard-label subset. `inferred` and `experimental` labels are themselves
    # claims, and a result that only holds on them is not a result about documented function.
    hard = confidence == "documented"
    if hard.sum() >= 4 and len(set(species[hard])) >= 2:
        hh, th = loso(uz[hard], species[hard], label[hard], k=1)
        hard_base = Counter(label[hard]).most_common(1)[0][1] / int(hard.sum())
        hard_acc = hh / th if th else float("nan")
    else:
        hh = th = 0
        hard_base, hard_acc = float("nan"), float("nan")

    print()
    print(f"G1 LOSO k=1 {obs:.4f} against majority {base:.4f}   "
          f"({'PASS' if obs > base else 'FAIL'})")
    print(f"G2 permutation p = {pval:.4f}                       "
          f"({'PASS' if pval < 0.05 else 'FAIL'}, gate < 0.05)")
    print(f"G3 within-species ceiling {hw / tw:.4f}             (reported)")
    print(f"G4 documented-confidence only {hard_acc:.4f} against majority {hard_base:.4f} "
          f"({hh}/{th}) (reported)")
    print()

    if obs <= base:
        print("VERDICT: cross-species function transfer does not beat a constant answer. "
              f"The refusal stands: with {uz.shape[0]} functions over {len(set(species))} "
              "species there is no anchor set to propagate from, and the honest fix is more "
              "documented function, not a better model.")
    elif pval >= 0.05:
        print("VERDICT: the margin over the majority class does not survive its own "
              "shuffle, so it is not evidence. The refusal stands.")
    elif hard_acc == hard_acc and hard_acc <= hard_base:
        print("VERDICT: the transfer beats chance on the full set but not on the 28 knots "
              "whose labels are actually documented, so what it learned is the inference "
              "and not the documentation. Not usable as a claim about function.")
    else:
        print("VERDICT: function transfers across species above chance and above its own "
              "shuffle. A prediction that ships this error rate is allowed — an identity "
              "is still not.")
    if uz.shape[0] < 200:
        print(f"\nSTANDING LIMIT: n = {uz.shape[0]}. Every number here is computed on a set "
              "small enough that one species' repertoire moves it. Read the gates, not the "
              "third decimal.")


if __name__ == "__main__":
    main()
