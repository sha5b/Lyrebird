"""Two questions about the recordist confound that the literature has not asked.

Limit 2 of the system paper says the confound is real, that four independent removal attempts
failed, and that "the named action is more recordists per species, in the data". That last
sentence is a slogan. It has no number attached, so nobody can act on it. And the claim that
the confound belongs to *the archives* rather than to a model rests on an aggregate: two
models both carry it. Aggregates are weak evidence for a mechanism.

This asks both properly, and both are new. Neither Stowell & Plumbley 2014, the 2026
foundation-model review, nor the Perch and BirdNET reports contain either measurement.

**A. The dose-response curve: how many recordists per species does it take?**

The blocked-against-random cost is measured separately for species carried by 2, 3, 4, 5 and
6+ recordists. If the cost falls as recordists rise, the slogan becomes a target: *this many
recordists per species and the leakage is gone.* If it does not fall, the action named in the
paper is wrong and should be withdrawn.

Two confounds are controlled, and both matter:

  * **Recordings per species.** More recordists usually means more recordings, and more
    training rows is easier regardless of who made them. `w0_full_fetch.py` caps every species
    at 12, so recordings per species is bounded to 6-12 across every stratum and cannot carry
    the trend on its own. The realized mean per stratum is reported so a reader can check.
  * **Label-set size.** A drop in accuracy points is not comparable across label sets of
    different size, which is the whole point of the class-count sweep in `w0_full.py`. Every
    stratum is therefore subsampled to the same number of species, and the error ratio is
    reported beside the points.

**B. Is it the same recordists in two independent models?**

For every recordist, how identifiable are their recordings from the embedding alone? Then
correlate that per-recordist score between Perch 2.0 and BirdNET V2.4 — different
architectures, different training groups, one shared archive.

This is the sharper form of the archives claim. Two models can both show an aggregate
recordist lift for unrelated reasons. But if the *same individual recordists* are the easy
ones in both spaces, the structure is a property of those recordists — their microphone,
their sites, their habits — and not of either model's inductive bias. A correlation near zero
would mean each model has its own idiosyncratic notion of recordist and the aggregate
agreement is a coincidence.

Usage:  .venv/bin/python analysis/w0_confound_anatomy.py
        .venv/bin/python analysis/w0_confound_anatomy.py --repeats 5
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from w0_full import HELD_FRACTION, MODELS, SEED, apply_floor, load  # noqa: E402
from w0_probe import device_of, probe_accuracy  # noqa: E402

OUT = Path(__file__).resolve().parent / "w0_confound_anatomy.json"

#: Strata for part A. The last is open-ended.
RECORDIST_BINS = ((2, 2), (3, 3), (4, 4), (5, 5), (6, 10**6))
#: A recordist needs this many recordings before "are your recordings findable" is a question.
MIN_PER_RECORDIST = 6
REPEATS = 20


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- part A


def paired_drop(x, species, who, repeats, device, rng_offset=0):
    """The paired blocked-against-random drop, as in `w0_full.py` ARM C."""
    recordists = sorted(set(who))
    if len(recordists) < 4:
        return None
    p_rand, p_block, classes = [], [], []
    for rep in range(repeats):
        r = np.random.default_rng(SEED + 1000 + rng_offset + rep)
        held = set(r.permutation(recordists)[
            : max(1, int(round(HELD_FRACTION * len(recordists))))
        ])
        btest = np.array([w in held for w in who])
        if not btest.any() or btest.all():
            continue
        shared = set(species[~btest]) & set(species[btest])
        if len(shared) < 3:
            continue
        keep = np.array([s in shared for s in species])
        xk, yk, bk = x[keep], species[keep], btest[keep]
        rr = np.random.default_rng(SEED + 2000 + rng_offset + rep)
        rtest = np.zeros(len(yk), bool)
        for s in shared:
            idx = np.flatnonzero(yk == s)
            rtest[rr.permutation(idx)[: max(1, int(round(bk.mean() * len(idx))))]] = True
        if not rtest.any() or rtest.all():
            continue
        p_block.append(probe_accuracy(xk[~bk], yk[~bk], xk[bk], yk[bk], device))
        p_rand.append(probe_accuracy(xk[~rtest], yk[~rtest], xk[rtest], yk[rtest], device))
        classes.append(len(shared))
    if not p_rand:
        return None
    pa, pb = float(np.mean(p_rand)) * 100, float(np.mean(p_block)) * 100
    err_r, err_b = 100 - pa, 100 - pb
    return {
        "random_top1": pa, "blocked_top1": pb, "drop_points": pa - pb,
        "error_ratio": err_b / err_r if err_r > 0 else None,
        "folds": len(p_rand), "classes": float(np.mean(classes)),
    }


def dose_response(spaces, species, who, repeats, device) -> dict:
    per_species_recordists = defaultdict(set)
    per_species_n = Counter()
    for s, w in zip(species, who):
        per_species_recordists[s].add(w)
        per_species_n[s] += 1

    strata: dict[str, list[str]] = {}
    for lo, hi in RECORDIST_BINS:
        name = f"{lo}" if lo == hi else f"{lo}+"
        strata[name] = sorted(
            s for s, r in per_species_recordists.items() if lo <= len(r) <= hi
        )

    sizes = {k: len(v) for k, v in strata.items()}
    usable = {k: v for k, v in strata.items() if len(v) >= 20}
    if len(usable) < 2:
        return {"status": "too few strata", "stratum_sizes": sizes}
    # Equal label-set size across strata, so a drop in points is comparable between them.
    n_species = min(len(v) for v in usable.values())
    log(f"  dose-response: strata {sizes}, equalised to {n_species} species each")

    out: dict = {"stratum_sizes": sizes, "species_per_stratum": n_species, "strata": {}}
    for name, members in usable.items():
        pick = set(np.random.default_rng(SEED + 11).permutation(members)[:n_species])
        m = np.array([s in pick for s in species])
        row: dict = {
            "species": int(len(pick)),
            "recordings": int(m.sum()),
            "mean_recordings_per_species": float(
                np.mean([per_species_n[s] for s in pick])
            ),
            "mean_recordists_per_species": float(
                np.mean([len(per_species_recordists[s]) for s in pick])
            ),
        }
        for model in MODELS:
            row[model] = paired_drop(spaces[model][m], species[m], who[m],
                                     repeats, device)
        out["strata"][name] = row
        got = row.get(MODELS[0]) or {}
        log(f"    {name:>3} recordists -> drop {got.get('drop_points', float('nan')):6.2f} pts, "
            f"{got.get('error_ratio') or float('nan'):.2f}x errors "
            f"({row['mean_recordings_per_species']:.1f} rec/species)")
    return out


# --------------------------------------------------------------------------- part B


def recordist_findability(x, who, device=None) -> dict[str, float]:
    """Per recordist: how much more often is a recording's nearest neighbour also theirs?

    Cosine nearest neighbour, excluding the recording itself, minus the rate expected if
    labels were shuffled. Positive means this recordist's recordings cluster.
    """
    import torch

    n = len(who)
    xt = torch.tensor(np.asarray(x, dtype=np.float32),
                      device=device or device_of())
    xt = xt / xt.norm(dim=1, keepdim=True).clamp_min(1e-9)
    # Nearest neighbour by cosine, self excluded.
    nn = torch.empty(n, dtype=torch.long, device=xt.device)
    step = 2048
    for i in range(0, n, step):
        sim = xt[i : i + step] @ xt.T
        for r in range(sim.shape[0]):
            sim[r, i + r] = -2.0
        nn[i : i + step] = sim.argmax(dim=1)
    nn = nn.cpu().numpy()

    counts = Counter(who)
    hit: Counter[str] = Counter()
    for i, w in enumerate(who):
        if who[nn[i]] == w:
            hit[w] += 1
    out: dict[str, float] = {}
    for w, total in counts.items():
        if total < MIN_PER_RECORDIST:
            continue
        # Chance that a random other row is this recordist's.
        chance = (total - 1) / (n - 1)
        out[w] = hit[w] / total - chance
    return out


def cross_model_agreement(spaces, who, device) -> dict:
    scores = {m: recordist_findability(spaces[m], who, device) for m in MODELS}
    shared = sorted(set(scores[MODELS[0]]) & set(scores[MODELS[1]]))
    if len(shared) < 10:
        return {"status": "too few recordists", "recordists": len(shared)}
    a = np.array([scores[MODELS[0]][r] for r in shared])
    b = np.array([scores[MODELS[1]][r] for r in shared])

    def pearson(u, v):
        u, v = u - u.mean(), v - v.mean()
        d = float(np.sqrt((u * u).sum() * (v * v).sum()))
        return float((u * v).sum() / d) if d > 0 else float("nan")

    def spearman(u, v):
        ru = np.argsort(np.argsort(u)).astype(float)
        rv = np.argsort(np.argsort(v)).astype(float)
        return pearson(ru, rv)

    # A null: shuffle one model's per-recordist scores. If the real correlation is not far
    # above this, the agreement is an artefact of the score's own distribution.
    rng = np.random.default_rng(SEED)
    null = [pearson(a, rng.permutation(b)) for _ in range(200)]

    # **The nuisance variable, and without it this number is not evidence.** A recordist
    # holding 20 recordings is easier to find than one holding 6 in *either* space, simply
    # because more same-label neighbours exist to be found. That inflates both scores together
    # and would manufacture a correlation with no shared mechanism behind it. So the headline
    # is the correlation with `log(recordings)` partialled out of both sides. If the raw
    # correlation is high and the partial one collapses, the agreement was the nuisance.
    counts = Counter(who)
    z = np.log(np.array([counts[r] for r in shared], dtype=float))

    def residual(v):
        zz = z - z.mean()
        denom = float((zz * zz).sum())
        beta = float((zz * (v - v.mean())).sum() / denom) if denom > 0 else 0.0
        return v - v.mean() - beta * zz

    ra, rb = residual(a), residual(b)
    partial = pearson(ra, rb)
    null_partial = [pearson(ra, rng.permutation(rb)) for _ in range(200)]

    return {
        "recordists": len(shared),
        "min_recordings_per_recordist": MIN_PER_RECORDIST,
        f"mean_findability_{MODELS[0]}": float(a.mean()),
        f"mean_findability_{MODELS[1]}": float(b.mean()),
        "pearson_raw": pearson(a, b),
        "spearman_raw": spearman(a, b),
        "pearson_partial_log_recordings": partial,
        "null_pearson_mean": float(np.mean(null)),
        "null_pearson_p95": float(np.percentile(null, 95)),
        "null_partial_p95": float(np.percentile(null_partial, 95)),
        "findability_vs_log_recordings_perch": pearson(a, z),
        "findability_vs_log_recordings_birdnet": pearson(b, z),
        "share_positive_both": float(np.mean((a > 0) & (b > 0))),
    }


def main() -> int:
    repeats = REPEATS
    if "--repeats" in sys.argv:
        repeats = int(sys.argv[sys.argv.index("--repeats") + 1])

    spaces, species, who, census = load()
    spaces, species, who, keep_sp, _single = apply_floor(spaces, species, who)
    device = device_of()

    print("=" * 74)
    print("The anatomy of the recordist confound: a dose curve, and one mechanism test")
    print("=" * 74)
    print(f"  recordings {len(species)}   species {len(keep_sp)}   "
          f"recordists {len(set(who))}   device {device}")
    if len(species) < 2000:
        print("\n  TOO THIN — let the fetch finish. Nothing below is measured.")
        return 1

    t0 = time.time()
    print("\n  A. How many recordists per species does it take?")
    print("     (label-set size held equal across strata; the cap holds recordings flat)")
    dose = dose_response(spaces, species, who, repeats, device)

    print("\n  B. Are the same recordists findable in both models?")
    agree = cross_model_agreement(spaces, who, device)
    if "pearson_raw" in agree:
        print(f"     {agree['recordists']} recordists with >= {MIN_PER_RECORDIST} recordings")
        print(f"     Perch mean findability   {agree['mean_findability_perch']:+.4f}")
        print(f"     BirdNET mean findability {agree['mean_findability_birdnet']:+.4f}")
        print(f"     raw       pearson {agree['pearson_raw']:+.3f}  "
              f"spearman {agree['spearman_raw']:+.3f}")
        print(f"     PARTIAL   pearson {agree['pearson_partial_log_recordings']:+.3f}  "
              "<- log(recordings) removed from both sides; THIS is the number")
        print(f"     nuisance  findability vs log(recordings): "
              f"perch {agree['findability_vs_log_recordings_perch']:+.3f}, "
              f"birdnet {agree['findability_vs_log_recordings_birdnet']:+.3f}")
        print(f"     shuffled null  raw 95th pct {agree['null_pearson_p95']:+.3f}, "
              f"partial 95th pct {agree['null_partial_p95']:+.3f}")
        print(f"     positive in both spaces: {100 * agree['share_positive_both']:.1f} % "
              "of recordists")
    else:
        print(f"     {agree}")

    result = {
        "census": census,
        "recordings": int(len(species)),
        "species": len(keep_sp),
        "recordists": len(set(who)),
        "dose_response": dose,
        "cross_model_recordist_agreement": agree,
        "seconds": round(time.time() - t0, 1),
    }
    OUT.write_text(json.dumps(result, indent=1, default=float))
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
