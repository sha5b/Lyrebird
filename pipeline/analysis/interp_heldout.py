"""Does the 32-d geometry predict a held-out fitted type, or only that the species is a blob?

HANDOFF's "one experiment to run first", because it decides whether the synthetic space is
warranted: hold out a real fitted type, interpolate between that species' remaining types,
and ask whether the interpolant lands nearer the held-out type than chance. If it does,
filling gaps is warranted and `inverse.py` can render the fill. If it does not, the
synthetic space generates plausible noise.

PRE-REGISTERED, before the run.

The trap this design exists to avoid: "the held-out type is near its own species' types" is
trivially true — a species is a cluster, so any query built from its types retrieves its
other types. That measures species cohesion, not gap-filling. So the interpolant is scored
against three controls on the identical query population, and **only arm A beating arm B
is evidence for interpolation**:

  A  interpolant   midpoints of every pair of the species' remaining types. The test.
  B  sibling       the remaining types themselves, unmodified. The species-blob baseline.
                   A must beat B, or a midpoint carries nothing a real type did not already.
  C  centroid      the mean of the remaining types. One point, no pair structure.
  D  shuffled      arm A run on a *different* species' types, matched for count. The null,
                   in geometry.py's spirit: a geometry that cannot beat its own shuffle is
                   reported as no relation.

Retrieval, following w5_field_retrieval.py: for one held-out type h of species s, the
candidate pool is h plus every knot of every *other* species. The species' remaining types
are excluded from the pool because they are what the query is built from, and a midpoint of
two vectors is trivially nearest to those two vectors. Cosine, the lookup `SpectralMatcher`
performs on live audio.

  rank percentile   share of the pool h beats. Chance 0.5.
  top-1 / top-10    share of trials where h is the nearest / in the nearest ten.
                    Chance 1/N and 10/N, and N is about 13 800, so chance top-1 is ~0.007 %.

GATES, so the answer cannot be argued after the fact:

  G1  arm A rank percentile > arm D by at least 0.05  -> the geometry beats its own shuffle.
  G2  arm A top-1 > arm B top-1                       -> interpolation beats the siblings.
  G3  reported, not gated: A against C, which says whether pair structure beats the mean.

If G1 fails the synthetic space is not warranted and that is the finding. If G1 passes and
G2 fails, the geometry is real but interpolation adds nothing over nearest-sibling
retrieval — which is a different and cheaper thing to ship.

Runs against the installed assets, so it measures the build the app is drawing. Nothing is
written; the numbers are the deliverable.
"""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import numpy as np

#: One row per knot: vector32 (the critic embedding), vector (28-d descriptor), featuresLo.
#: Only the first block is read here — the 32-d space is the one the galaxy clusters in.
ROW_FLOATS = 68
VECTOR32 = 32


def load(assets: Path) -> tuple[np.ndarray, list[str], list[str]]:
    """The shipped knots as (vectors32, speciesId, syllableId)."""
    meta = json.loads((assets / "centroids.json").read_text())
    items = meta["items"]
    raw = np.fromfile(assets / "centroid-vectors.f32", dtype="<f4")
    rows = raw.reshape(-1, ROW_FLOATS)
    if rows.shape[0] != len(items):
        raise SystemExit(f"{rows.shape[0]} vector rows against {len(items)} centroids")
    z = rows[:, :VECTOR32].astype(np.float64)
    return z, [it["speciesId"] for it in items], [it["syllableId"] for it in items]


def unit(m: np.ndarray) -> np.ndarray:
    """Row-normalised, so a dot product is a cosine — the matcher's own comparison."""
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.maximum(n, 1.0e-12)


def midpoints(v: np.ndarray) -> np.ndarray:
    """Every pair's midpoint. One type gives nothing; the caller checks."""
    pairs = list(combinations(range(v.shape[0]), 2))
    if not pairs:
        return np.empty((0, v.shape[1]))
    a = np.array([p[0] for p in pairs])
    b = np.array([p[1] for p in pairs])
    return (v[a] + v[b]) / 2.0


def score(
    queries: np.ndarray, uz: np.ndarray, target: int, excluded: np.ndarray
) -> tuple[float, bool, bool]:
    """Rank `target` against every knot except `excluded`, by best cosine to any query.

    Best-over-queries, because the question is whether *some* interpolant lands on the
    held-out type, not whether the average one does.

    Scored against the whole matrix and corrected for the exclusions rather than copying a
    pool per trial: the pool is 13 848 x 32 and there are 13 704 trials x 4 arms, so the
    copy alone would move tens of gigabytes to answer a question about one row.
    """
    if queries.shape[0] == 0:
        return float("nan"), False, False
    sim = (unit(queries) @ uz.T).max(axis=0)
    hit = sim[target]
    better = int((sim > hit).sum()) - int((sim[excluded] > hit).sum())
    n = uz.shape[0] - excluded.shape[0]
    return 1.0 - better / (n - 1), better == 0, better < 10


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", default="app/static/lyrebird", type=Path)
    ap.add_argument("--min-types", type=int, default=3,
                    help="a species needs this many fitted types to hold one out")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    z, species, syllable = load(args.assets)
    uz = unit(z)
    rng = np.random.default_rng(args.seed)

    # Fitted types only. A documented syllable is not what the synthetic space would fill,
    # and counting it here would mix the two epistemic categories the project keeps apart.
    learned = np.array([s.startswith("L") for s in syllable])
    by_species: dict[str, list[int]] = {}
    for i in np.flatnonzero(learned):
        by_species.setdefault(species[i], []).append(int(i))

    eligible = {s: idx for s, idx in by_species.items() if len(idx) >= args.min_types}
    print(f"{z.shape[0]} knots, {int(learned.sum())} fitted, "
          f"{len(by_species)} species with a fitted type, "
          f"{len(eligible)} with >= {args.min_types}", flush=True)

    donors = sorted(eligible)
    arms = {k: {"pct": [], "t1": [], "t10": [], "n": []} for k in ("A", "B", "C", "D")}
    trials = 0

    for s, own in sorted(eligible.items()):
        for held in own:
            # The pool is every knot except this species' *remaining* fitted types: those
            # are what the query is built from, and a midpoint of two vectors is trivially
            # nearest to those two vectors. The held-out type stays in, as the target.
            rest = [i for i in own if i != held]

            # D: a different species, matched for how many types the query is built from.
            # Drawn from the eligible set so the donor always has enough types to match.
            other = s
            while other == s and len(donors) > 1:
                other = donors[int(rng.integers(len(donors)))]
            shuffled = by_species[other][: len(rest)]

            # Each arm excludes its own query source, so no arm can retrieve the vectors it
            # was built from and every arm ranks against the same size of pool.
            for arm, q, src in (
                ("A", midpoints(z[rest]), rest),
                ("B", z[rest], rest),
                ("C", z[rest].mean(axis=0, keepdims=True), rest),
                ("D", midpoints(z[shuffled]), shuffled),
            ):
                pct, t1, t10 = score(q, uz, held, np.array(src))
                if np.isnan(pct):
                    continue
                arms[arm]["pct"].append(pct)
                arms[arm]["t1"].append(t1)
                arms[arm]["t10"].append(t10)
                arms[arm]["n"].append(len(rest))
            trials += 1
        if trials and trials % 2000 == 0:
            print(f"  {trials} held-out trials", flush=True)

    n_pool = z.shape[0] - int(np.median([len(v) for v in eligible.values()])) + 1
    print(f"\n{trials} held-out trials, pool about {n_pool} knots")
    print(f"chance: rank percentile 0.5, top-1 {1 / n_pool:.6f}, top-10 {10 / n_pool:.6f}\n")

    label = {"A": "interpolant (midpoints)", "B": "sibling (the types)",
             "C": "centroid (the mean)", "D": "shuffled (another species)"}
    print("| arm | rank percentile | top-1 | top-10 | trials |")
    print("|---|---|---|---|---|")
    out = {}
    for k in ("A", "B", "C", "D"):
        a = arms[k]
        r = float(np.mean(a["pct"]))
        t1 = float(np.mean(a["t1"]))
        t10 = float(np.mean(a["t10"]))
        out[k] = (r, t1, t10)
        print(f"| {label[k]} | {r:.4f} | {t1:.4f} | {t10:.4f} | {len(a['pct'])} |")

    # How many anchors does interpolation need before it beats them?
    #
    # A midpoint of two types is a guess about the space between them, so with two anchors
    # there is one guess and it is the mean; with ten there are 45 and they sketch a hull.
    # If the A - B margin grows with the anchor count then interpolation is warranted for
    # well-sampled birds and not for thin ones, which is a sharper answer than one average.
    print("\nby anchor count (types the query is built from), A - B top-1:")
    print("| anchors | trials | A top-1 | B top-1 | A - B | A pct | D pct |")
    print("|---|---|---|---|---|---|---|")
    na = np.array(arms["A"]["n"])
    for lo, hi, name in ((2, 2, "2"), (3, 3, "3"), (4, 5, "4-5"),
                         (6, 8, "6-8"), (9, 1_000, "9+")):
        m = (na >= lo) & (na <= hi)
        if not m.any():
            continue
        a1 = float(np.array(arms["A"]["t1"])[m].mean())
        b1 = float(np.array(arms["B"]["t1"])[m].mean())
        ap = float(np.array(arms["A"]["pct"])[m].mean())
        dp = float(np.array(arms["D"]["pct"])[m].mean())
        print(f"| {name} | {int(m.sum())} | {a1:.4f} | {b1:.4f} | "
              f"{a1 - b1:+.4f} | {ap:.4f} | {dp:.4f} |")

    print()
    g1 = out["A"][0] - out["D"][0]
    g2 = out["A"][1] - out["B"][1]
    print(f"G1 A - D rank percentile = {g1:+.4f}  "
          f"({'PASS' if g1 > 0.05 else 'FAIL'}, gate > 0.05)")
    print(f"G2 A - B top-1           = {g2:+.4f}  "
          f"({'PASS' if g2 > 0 else 'FAIL'}, gate > 0)")
    print(f"G3 A - C top-1           = {out['A'][1] - out['C'][1]:+.4f}  (reported)")
    # G2 is a gate on top-1 only, so say plainly when the percentile disagrees with it —
    # a gate that passes on one statistic while another moves the other way is a thin pass
    # and reporting it as a clean one would be the false positive this project warns about.
    pct_margin = out["A"][0] - out["B"][0]
    print(f"   A - B rank percentile = {pct_margin:+.4f}  "
          f"({'agrees with G2' if pct_margin > 0 else 'DISAGREES with G2'})")
    print()
    if g1 <= 0.05:
        print("VERDICT: the geometry does not beat its own shuffle. Filling gaps by "
              "interpolation is not warranted — it would generate plausible noise.")
    elif g2 <= 0:
        print("VERDICT: the geometry is real but a midpoint carries nothing a real "
              "sibling type did not. Nearest-sibling retrieval is the cheaper thing to "
              "ship; interpolation is not justified by this measurement.")
    elif pct_margin <= 0:
        print("VERDICT: the geometry is emphatically real — the shuffle sits at chance and "
              "a species' own types find the held-out one far above it. But interpolation "
              "beats the sibling types on top-1 only, and by a margin the rank percentile "
              "contradicts, so a midpoint is close to redundant *on average*. Read the "
              "anchor-count table before deciding: if the margin grows with the anchor "
              "count, filling gaps is warranted for well-sampled birds and not for thin "
              "ones.")
    else:
        print("VERDICT: interpolants land nearer the held-out type than both the shuffle "
              "and the sibling types, on both statistics. Filling gaps is warranted and "
              "inverse.py can render the fill.")


if __name__ == "__main__":
    main()
