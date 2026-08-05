"""W0 asked what a *recordist*-blocked split costs. This asks the same of the other blocks.

W0 measured one number: blocking an evaluation split by recordist costs a linear probe over
frozen Perch features 18.51 points of top-1 and BirdNET 21.59. The obvious next questions
are the ones a benchmark maintainer actually faces, and nobody has published either:

- **Geography.** Train here, deploy there is the real deployment scenario, and a
  location-blocked split is what an ecologist needs. Every recording in this population
  carries lat/lon and a country.
- **Time.** Equipment, codecs and archive conventions drift, so a temporally-blocked split
  is the other standard honesty move.

**Everything is held identical to the published run except the blocking variable.** Same
frozen embeddings (`w0-full-embeddings.npz`, no re-embedding), same population after W0's
own floor, same probe, same `HELD_FRACTION`, same seeds, same paired class-set correction.
So the drops here are directly comparable to 18.51 / 21.59, and the recordist arm doubles
as a replication check on this harness: if it does not reproduce, nothing else here counts.

**The confound is the point, not a nuisance.** A recordist records near home, so a
location-blocked split is partly a recordist-blocked split, and a recordist-blocked split
is partly geographic. Reporting the drops without the association between the blocks would
invite exactly the wrong reading, so the association is measured and printed alongside.

**PRE-REGISTERED, before the run.**

1. The recordist arm reproduces the published Perch drop to within 1.5 points. If it does
   not, the harness is wrong and no other arm is reportable.
2. Location-blocked costs more than the 10-point gate W0 used, i.e. geography leaks too.
3. Location-blocked is **no larger** than recordist-blocked, because a recordist block
   removes the channel and microphone signature exactly, while a location block removes it
   only to the extent that recordists are geographically confined.
4. Year-blocked is the smallest of the three, because recordists span years and equipment
   eras drift slowly.

Any of 2-4 failing is reportable as it stands and no threshold moves afterwards. 3 failing
would be the most interesting outcome: it would mean place carries something above and
beyond who held the microphone.

Usage:
    .venv/bin/python analysis/w0_blocking_variables.py [--repeats 20] [--models perch,birdnet]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from w0_probe import device_of, probe_accuracy  # noqa: E402

EMB = ROOT / "out/external/w0-full-embeddings.npz"
META = ROOT / "out/external/w0-full-meta.json"
CATALOGUE = ROOT / "out/audio-postcutoff/_catalogue_full.json"
OUT = Path(__file__).resolve().parent / "w0_blocking_variables.json"

# --- every one of these matches analysis/w0_full.py exactly. Do not tune them here.
MIN_PER_SPECIES = 6
MIN_RECORDISTS_PER_SPECIES = 2
HELD_FRACTION = 0.3
SEED = 0
GATE_POINTS = 10.0

#: The published Perch drop, and the tolerance clause 1 of the pre-registration uses.
PUBLISHED_PERCH_DROP = 18.51
REPLICATION_TOLERANCE = 1.5

#: 1 degree of latitude is about 111 km, which is a defensible spatial block: far enough
#: apart that a held-out cell is a different place, coarse enough to leave usable cells.
GRID_DEGREES = 1.0


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load():
    z = np.load(EMB, allow_pickle=True)
    ids = [str(r) for r in z["ids"]]
    info = json.loads(META.read_text())
    meta = info.get("meta", info)
    cat = json.loads(CATALOGUE.read_text())

    keep = [i for i, r in enumerate(ids) if r in meta]
    rows = [ids[i] for i in keep]
    spaces = {m: z[m][keep] for m in ("perch", "birdnet")}
    species = np.array([meta[r]["species"] for r in rows])
    who = np.array([meta[r]["recordist"] for r in rows])

    def cell(r: str) -> str:
        c = cat.get(r) or {}
        try:
            lat, lon = float(c["lat"]), float(c["lon"])
        except (KeyError, TypeError, ValueError):
            return ""
        return f"{math.floor(lat / GRID_DEGREES)}_{math.floor(lon / GRID_DEGREES)}"

    def country(r: str) -> str:
        return str((cat.get(r) or {}).get("cnt") or "")

    def year(r: str) -> str:
        d = str((cat.get(r) or {}).get("date") or "")
        return d[:4] if len(d) >= 4 else ""

    blocks = {
        "recordist": who,
        "location_1deg": np.array([cell(r) for r in rows]),
        "country": np.array([country(r) for r in rows]),
        "year": np.array([year(r) for r in rows]),
    }
    return spaces, species, who, blocks, rows


def apply_floor(spaces, species, who, blocks):
    """W0's own floor, unchanged, so the population is the published one."""
    counts = Counter(species)
    by_sp = defaultdict(set)
    for s, w in zip(species, who):
        by_sp[s].add(w)
    keep_sp = {
        s for s in counts
        if counts[s] >= MIN_PER_SPECIES and len(by_sp[s]) >= MIN_RECORDISTS_PER_SPECIES
    }
    mask = np.array([s in keep_sp for s in species])
    return (
        {m: x[mask] for m, x in spaces.items()},
        species[mask],
        {k: v[mask] for k, v in blocks.items()},
        keep_sp,
    )


def _held_levels(levels, group, rng, target_held: float | None):
    """Which levels to hold out.

    Two rules, and the difference matters more than it looks. Holding out a fixed share of
    *levels* is what `w0_full.py` does, and it is right when comparing one blocking variable
    against a random split. It is **wrong for comparing blocking variables against each
    other**, because the variables have wildly different level counts: 30 % of 116 countries
    strands 43 % of the recordings while 30 % of 646 recordists strands 34 %, and the arm
    with less training data loses accuracy for a reason that has nothing to do with leakage.

    `target_held` instead adds shuffled levels until the held *recordings* reach the target,
    which equalises training-set size across variables. Same spirit as W0's class-set
    correction: remove the bias that would otherwise be read as the effect.
    """
    order = list(rng.permutation(levels))
    if target_held is None:
        return set(order[: max(1, int(round(HELD_FRACTION * len(levels))))])

    n = len(group)
    per_level = Counter(group)
    held: set = set()
    got = 0
    for lv in order:
        # Stop before overshooting further than stopping short would.
        nxt = got + per_level[lv]
        if held and abs(nxt / n - target_held) > abs(got / n - target_held):
            break
        held.add(lv)
        got = nxt
        if got / n >= target_held:
            break
    return held


def paired_arm(x, species, group, repeats, device, target_held=None) -> dict:
    """`w0_full.py`'s ARM C, with the blocking variable passed in.

    Each blocked fold's surviving class set is reused for a random fold, so the pair differ
    in one thing only: whether a member of the held-out group may appear on both sides.
    """
    levels = sorted({g for g in group if g})
    if len(levels) < 3:
        return {"status": f"only {len(levels)} usable levels"}

    p_rand, p_block, p_classes, p_held = [], [], [], []
    for rep in range(repeats):
        r = np.random.default_rng(SEED + 1000 + rep)
        held = _held_levels(levels, group, r, target_held)
        btest = np.array([g in held for g in group])
        if not btest.any() or btest.all():
            continue
        shared = set(species[~btest]) & set(species[btest])
        if len(shared) < 3:
            continue
        keep = np.array([s in shared for s in species])
        xk, yk, bk = x[keep], species[keep], btest[keep]

        rr = np.random.default_rng(SEED + 2000 + rep)
        rtest = np.zeros(len(yk), bool)
        for s in shared:
            idx = np.flatnonzero(yk == s)
            rtest[rr.permutation(idx)[: max(1, int(round(bk.mean() * len(idx))))]] = True
        if not rtest.any() or rtest.all():
            continue
        p_block.append(probe_accuracy(xk[~bk], yk[~bk], xk[bk], yk[bk], device))
        p_rand.append(probe_accuracy(xk[~rtest], yk[~rtest], xk[rtest], yk[rtest], device))
        p_classes.append(len(shared))
        p_held.append(float(bk.mean()))

    if not p_rand:
        return {"status": "no usable folds"}
    pa, pb = float(np.mean(p_rand)) * 100, float(np.mean(p_block)) * 100
    diffs = (np.array(p_rand) - np.array(p_block)) * 100
    err_r, err_b = 100 - pa, 100 - pb
    return {
        "levels": len(levels),
        "random_top1": pa,
        "blocked_top1": pb,
        "drop_points": pa - pb,
        "folds": len(p_rand),
        "classes": float(np.mean(p_classes)),
        "held_share": float(np.mean(p_held)),
        "per_fold_sd": float(diffs.std()),
        "folds_blocked_worse": int((diffs > 0).sum()),
        "error_ratio": err_b / err_r if err_r else None,
        "exceeds_gate": bool((pa - pb) > GATE_POINTS),
    }


def association(a: np.ndarray, b: np.ndarray) -> float:
    """Normalised mutual information between two groupings, 0 = independent, 1 = identical.

    This is what says how much a location-blocked split is *also* a recordist-blocked one.
    """
    n = len(a)
    ca, cb = Counter(a), Counter(b)
    joint = Counter(zip(a, b))

    def ent(c):
        return -sum((v / n) * math.log(v / n) for v in c.values() if v)

    ha, hb = ent(ca), ent(cb)
    hj = ent(joint)
    mi = ha + hb - hj
    denom = math.sqrt(ha * hb)
    return mi / denom if denom else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--models", default="perch,birdnet")
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    device = device_of()
    log(f"device: {device}")
    spaces, species, who, blocks, rows = load()
    spaces, species, blocks, keep_sp = apply_floor(spaces, species, who, blocks)
    log(f"population after W0's floor: {len(species)} recordings, {len(keep_sp)} species")
    for k, v in blocks.items():
        miss = sum(1 for g in v if not g)
        log(f"  {k:14s} {len(set(g for g in v if g)):5d} levels, {miss} rows without one")

    results: dict = {
        "population": {"recordings": int(len(species)), "species": len(keep_sp)},
        "grid_degrees": GRID_DEGREES,
        "repeats": args.repeats,
        "published_perch_drop": PUBLISHED_PERCH_DROP,
        "arms": {},
        "association_nmi": {},
    }

    names = list(blocks)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            results["association_nmi"][f"{a}|{b}"] = association(blocks[a], blocks[b])

    # The recordist arm at W0's own rule sets the held-recording share that every other
    # variable is then matched to, so the comparison is not a training-set-size contest.
    for model in models:
        x = spaces[model]
        results["arms"][model] = {}
        for name, group in blocks.items():
            log(f"{model} / blocked by {name} (W0's level rule) ...")
            results["arms"][model][name] = paired_arm(
                x, species, group, args.repeats, device
            )

    target = (
        results["arms"].get(models[0], {}).get("recordist", {}).get("held_share")
    )
    results["matched_held_share_target"] = target
    if target:
        for model in models:
            x = spaces[model]
            results.setdefault("arms_matched", {})[model] = {}
            for name, group in blocks.items():
                log(f"{model} / blocked by {name} (held share matched to {target:.3f}) ...")
                results["arms_matched"][model][name] = paired_arm(
                    x, species, group, args.repeats, device, target_held=target
                )

    # --- clause 1: the harness has to reproduce the published number first.
    rep = results["arms"].get("perch", {}).get("recordist", {})
    got = rep.get("drop_points")
    results["replication"] = {
        "published": PUBLISHED_PERCH_DROP,
        "reproduced": got,
        "tolerance": REPLICATION_TOLERANCE,
        "ok": bool(got is not None
                   and abs(got - PUBLISHED_PERCH_DROP) <= REPLICATION_TOLERANCE),
    }

    print("=" * 78)
    print("What each blocking variable costs, same rows and same probe as W0")
    print("=" * 78)
    print(f"  population  {len(species)} recordings, {len(keep_sp)} species, "
          f"{args.repeats} paired folds")
    print()
    for model in models:
        print(f"  --- {model}")
        print("  blocked by        levels   random   blocked     drop   err ratio   worse")
        for name in blocks:
            r = results["arms"][model][name]
            if "drop_points" not in r:
                print(f"  {name:16s} {r.get('status')}")
                continue
            print(f"  {name:16s} {r['levels']:6d}  {r['random_top1']:7.2f}  "
                  f"{r['blocked_top1']:8.2f} {r['drop_points']:8.2f}   "
                  f"{r['error_ratio']:9.2f}   {r['folds_blocked_worse']}/{r['folds']}")
        print()
    if results.get("arms_matched"):
        print(f"  === held recording share matched to {target:.3f} "
              "(the comparison to read) ===")
        for model in models:
            print(f"  --- {model}")
            print("  blocked by        levels   held   classes     drop   err ratio   worse")
            for name in blocks:
                r = results["arms_matched"][model][name]
                if "drop_points" not in r:
                    print(f"  {name:16s} {r.get('status')}")
                    continue
                print(f"  {name:16s} {r['levels']:6d}  {r['held_share']:5.3f}  "
                      f"{r['classes']:7.1f} {r['drop_points']:8.2f}   "
                      f"{r['error_ratio']:9.2f}   {r['folds_blocked_worse']}/{r['folds']}")
            print()
    print("  association between blocks (normalised mutual information):")
    for k, v in results["association_nmi"].items():
        print(f"    {k:34s} {v:5.3f}")
    print()
    r = results["replication"]
    print(f"  CLAUSE 1 replication: published {r['published']}, reproduced "
          f"{r['reproduced']}, ok={r['ok']}")

    OUT.write_text(json.dumps(results, indent=1))
    print(f"\n  written to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
