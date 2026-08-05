"""Does *who recorded a species* bias the species-level pitch that comparative papers use?

Every cross-species acoustic comparison built on an opportunistic archive reduces a species
to one number — usually a median or mean frequency over whatever recordings exist. This
project has already shown that the archives carry a strong recordist signature: nearest
neighbour lift +0.488 by recordist against +0.196 by species, an outside foundation model
reading the same signature off audio it never trained on (+0.441), and blocking an
evaluation split by recordist costing 18-27 points of top-1. None of that asks the question
a comparative ornithologist would ask, which is whether the signature reaches the
*estimate*.

**Why this question survives where the others died.** It is a direct measurement — f0 off the
measured contour — not a fitted parameter, so it does not share G1's failure mode. And it is
**paired within species**: the comparison is recordist A against recordist B on the same
bird, so the between-species selection that blocked G3 and W4 barely applies. The population
is an order of magnitude larger than G3's 77 of 3 636 — 797 species have two or more
recordists contributing at least 20 syllables each, and 1 439 do at 8.

**PRE-REGISTERED, before the run.**

H1 — *the signature reaches the per-recordist estimate.* The observed within-species,
between-recordist variance in median log f0 exceeds the 95th percentile of a null built by
shuffling recordist labels **within** each species. Shuffling within species is what makes
the null test the recordist rather than the bird.

H2 — *and it does not bias the comparative slope.* The mass/f0 slope estimated the standard
way (one median over all of a species' syllables) agrees with a recordist-balanced estimate
(each recordist one vote, then the median across recordists) to within **15 %** of the
standard slope's magnitude.

The honest expectation is that both hold: a recordist signature is real, and f0 is a strong
enough species trait that recordist noise should average out rather than tilt a slope. **H2
failing is the consequential outcome** — it would mean the species-mean estimator inherits
the archive's recordist composition, and published comparative slopes drawn from these
archives inherit it too. Either way the result is reportable and neither threshold moves.

Reported alongside, because it is what makes H2 interpretable: the correlation between a
species' recordist count and its estimate, and how far the two estimators disagree per
species.

Usage:
    .venv/bin/python analysis/recordist_bias_comparative.py [--min-syllables 20]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from g1_g2_avonet import avonet, f0_reference, scientific  # noqa: E402

STORE = ROOT / "out/harvest-gan"
OUT = Path(__file__).resolve().parent / "recordist_bias_comparative.json"

#: A recordist needs this many syllables of a species before their median is used.
MIN_SYLLABLES = 20
#: And a species needs this many qualifying recordists.
MIN_RECORDISTS = 2

SHUFFLES = 500
SEED = 0

#: H2's threshold, as a share of the standard slope's magnitude.
SLOPE_TOLERANCE = 0.15


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def collect(min_syllables: int):
    """(species, recordist) -> list of log10 f0, streamed once over the store."""
    state = json.loads((STORE / "state.json").read_text())
    who_of = {k: (v.get("recordist") or "") for k, v in state["recordings"].items()}

    per: dict[tuple[str, str], list[float]] = defaultdict(list)
    n = 0
    for line in (STORE / "syllables.jsonl").open():
        row = json.loads(line)
        contour = row.get("contour")
        if not contour:
            continue
        who = who_of.get(row.get("recording_id") or "", "")
        if not who:
            continue
        f0 = f0_reference(contour)
        if not (f0 and f0 > 0):
            continue
        per[(row["species_id"], who)].append(math.log10(f0))
        n += 1
        if n % 100_000 == 0:
            log(f"  {n} rows ...")
    log(f"{n} rows with a contour and a named recordist")

    kept = {k: v for k, v in per.items() if len(v) >= min_syllables}
    by_species: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for (sid, who), vals in kept.items():
        by_species[sid][who] = vals
    return {s: d for s, d in by_species.items() if len(d) >= MIN_RECORDISTS}


def within_between(by_species) -> tuple[float, float]:
    """(within-species between-recordist variance, between-species variance) of median log f0."""
    sp_means, within = [], []
    for d in by_species.values():
        meds = [float(np.median(v)) for v in d.values()]
        m = float(np.mean(meds))
        sp_means.append(m)
        within += [x - m for x in meds]
    return float(np.var(within, ddof=1)), float(np.var(sp_means, ddof=1))


def shuffled_within(by_species, rng) -> float:
    """The same within-species variance with recordist labels shuffled inside each species.

    Pooling a species' syllables and re-dealing them into groups of the same sizes keeps the
    bird and destroys the recordist, which is exactly the null H1 needs.
    """
    within = []
    for d in by_species.values():
        sizes = [len(v) for v in d.values()]
        pool = np.concatenate([np.asarray(v) for v in d.values()])
        rng.shuffle(pool)
        meds, at = [], 0
        for k in sizes:
            meds.append(float(np.median(pool[at:at + k])))
            at += k
        m = float(np.mean(meds))
        within += [x - m for x in meds]
    return float(np.var(within, ddof=1))


def ols(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """(slope, standardised slope) of y on x."""
    b = float(np.polyfit(x, y, 1)[0])
    sx, sy = float(np.std(x, ddof=1)), float(np.std(y, ddof=1))
    return b, b * sx / sy if sy else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-syllables", type=int, default=MIN_SYLLABLES)
    args = ap.parse_args()

    by_species = collect(args.min_syllables)
    log(f"population: {len(by_species)} species with >= {MIN_RECORDISTS} recordists "
        f"at >= {args.min_syllables} syllables each")
    if len(by_species) < 50:
        log("too small to report")
        return 1

    # --- H1
    w_obs, b_obs = within_between(by_species)
    rng = np.random.default_rng(SEED)
    null = np.array([shuffled_within(by_species, rng) for _ in range(SHUFFLES)])
    p95 = float(np.percentile(null, 95))
    h1 = bool(w_obs > p95)
    log(f"H1: within {w_obs:.6f} vs shuffled p95 {p95:.6f} -> {h1}")

    # --- H2: the comparative slope, two estimators on the same species.
    mass = avonet()
    rows = []
    for sid, d in by_species.items():
        info = mass.get(scientific(sid))
        if not info:
            continue
        allvals = np.concatenate([np.asarray(v) for v in d.values()])
        naive = float(np.median(allvals))
        balanced = float(np.median([float(np.median(v)) for v in d.values()]))
        rows.append({
            "species": sid,
            "log_mass": math.log10(float(info["mass"])),
            "naive": naive,
            "balanced": balanced,
            "recordists": len(d),
            "syllables": int(allvals.size),
        })
    log(f"joined to AVONET mass: {len(rows)} species")

    lm = np.array([r["log_mass"] for r in rows])
    yn = np.array([r["naive"] for r in rows])
    yb = np.array([r["balanced"] for r in rows])
    bn, sn = ols(lm, yn)
    bb, sb = ols(lm, yb)
    rel = abs(bb - bn) / abs(bn) if bn else float("nan")
    h2 = bool(rel <= SLOPE_TOLERANCE)

    disagree = np.abs(yn - yb)
    nrec = np.array([r["recordists"] for r in rows], float)
    r_disagree_rec = float(np.corrcoef(np.log10(nrec), disagree)[0, 1])
    r_naive_rec = float(np.corrcoef(np.log10(nrec), yn)[0, 1])

    result = {
        "min_syllables_per_recordist": args.min_syllables,
        "min_recordists_per_species": MIN_RECORDISTS,
        "species_in_population": len(by_species),
        "species_with_mass": len(rows),
        "h1": {
            "within_species_between_recordist_var": w_obs,
            "between_species_var": b_obs,
            "variance_ratio_within_over_between": w_obs / b_obs if b_obs else None,
            "shuffled_null_p95": p95,
            "shuffled_null_median": float(np.median(null)),
            "shuffles": SHUFFLES,
            "held": h1,
        },
        "h2": {
            "slope_naive": bn,
            "slope_recordist_balanced": bb,
            "standardised_naive": sn,
            "standardised_balanced": sb,
            "relative_change": rel,
            "tolerance": SLOPE_TOLERANCE,
            "held": h2,
        },
        "context": {
            "median_abs_disagreement_dex": float(np.median(disagree)),
            "r_log_recordists_vs_disagreement": r_disagree_rec,
            "r_log_recordists_vs_naive_f0": r_naive_rec,
        },
    }

    print("=" * 78)
    print("Does recordist identity bias the species-level pitch estimate?")
    print("=" * 78)
    print(f"  population   {len(by_species)} species, >= {MIN_RECORDISTS} recordists at "
          f">= {args.min_syllables} syllables each")
    print(f"  with mass    {len(rows)} species")
    print()
    print("  H1  the signature reaches the per-recordist estimate")
    print(f"      within-species between-recordist var   {w_obs:.6f}")
    print(f"      shuffled-within null, median / p95     "
          f"{np.median(null):.6f} / {p95:.6f}")
    print(f"      between-species var                    {b_obs:.6f}")
    print(f"      within / between                       "
          f"{result['h1']['variance_ratio_within_over_between']:.4f}")
    print(f"      HELD: {h1}")
    print()
    print("  H2  and it does not bias the comparative slope")
    print(f"      slope, standard estimator              {bn:+.4f}  "
          f"(standardised {sn:+.3f})")
    print(f"      slope, recordist-balanced              {bb:+.4f}  "
          f"(standardised {sb:+.3f})")
    print(f"      relative change                        {rel:6.3f}  "
          f"(tolerance {SLOPE_TOLERANCE})")
    print(f"      HELD: {h2}")
    print()
    print(f"  median |naive - balanced|                  "
          f"{result['context']['median_abs_disagreement_dex']:.4f} dex")
    print(f"  r(log recordists, disagreement)            {r_disagree_rec:+.3f}")
    print(f"  r(log recordists, naive f0)                {r_naive_rec:+.3f}")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
