"""W0 full run, stage 2 — what a recordist-blocked split costs, at scale, on two models.

This is the pilot's experiment with the two things the pilot said it lacked:

  * **Scale.** 886 species over ~13 600 post-cutoff recordings, against 62 species over
    2 158. Selection is by species (`w0_full_fetch.py`), because W0's unit is the species.
  * **A second model.** Perch 2.0 and BirdNET V2.4 — different architectures, trained by
    different groups. Agreement between them is evidence about **the archives**; a result on
    one model alone cannot separate that from a property of that model.

Everything else is deliberately the pilot's, so the two are comparable: frozen features and
a linear probe only, audio uploaded after Perch 2.0's snapshot, and the same three arms with
the same warning attached to each. The probe moved to the GPU because 886 classes in 1 536
dimensions is not a tractable CPU fit; `w0_probe.py --verify` is the check that it is the
same estimator, and it agrees with the pilot's scikit-learn probe to within 1 point.

**The gate, pre-registered in docs/24 and restated so it cannot drift:** more than 10 points
of top-1 drop, on a public corpus, **on both models**. The pilot measured 9.68 on one model
and recorded that as not met. This run can meet it, fail it, or split between the models, and
a split is a reportable outcome rather than a tie to be broken.

**The pilot also asked for the bar to be restated as an error ratio, and that is reported
beside the gate rather than instead of it.** 9.68 points at 93 % accuracy is 2.44x the
errors; the same 9.68 points at 60 % would be 1.24x. A bar written in accuracy points is far
harsher near the ceiling, which is a flaw in how the gate was written. The registered gate is
still scored as written.

Usage:  .venv/bin/python analysis/w0_full.py
        .venv/bin/python analysis/w0_full.py --repeats 5    # quick look while fetching
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

from w0_probe import device_of, probe_accuracy  # noqa: E402

EMB = ROOT / "out/external/w0-full-embeddings.npz"
META = ROOT / "out/external/w0-full-meta.json"
OUT = Path(__file__).resolve().parent / "w0_full.json"

MIN_PER_SPECIES = 6
MIN_RECORDISTS_PER_SPECIES = 2
HELD_FRACTION = 0.3
SEED = 0
REPEATS = 20

#: Pre-registered in docs/24. Points of top-1 drop, and it applies to BOTH models.
GATE_POINTS = 10.0

MODELS = ("perch", "birdnet")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def load() -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, dict]:
    z = np.load(EMB, allow_pickle=True)
    ids = [str(r) for r in z["ids"]]
    info = json.loads(META.read_text())
    meta = info.get("meta", info)
    keep = [i for i, r in enumerate(ids) if r in meta]
    spaces = {m: z[m][keep] for m in MODELS}
    rows = [ids[i] for i in keep]
    species = np.array([meta[r]["species"] for r in rows])
    who = np.array([meta[r]["recordist"] for r in rows])
    return spaces, species, who, info.get("census", {})


def apply_floor(spaces, species, who):
    """W0's floor: a species needs enough recordings AND at least two recordists.

    A species whose recordings all come from one recordist lands wholly on one side of a
    blocked split and cannot be classified at all. That is an empty test class, not
    leakage, and counting it as an error would manufacture the result W0 is looking for.
    """
    counts = Counter(species)
    by_sp = defaultdict(set)
    for s, w in zip(species, who):
        by_sp[s].add(w)
    keep_sp = {
        s for s in counts
        if counts[s] >= MIN_PER_SPECIES and len(by_sp[s]) >= MIN_RECORDISTS_PER_SPECIES
    }
    single = sum(
        1 for s in counts
        if counts[s] >= MIN_PER_SPECIES and len(by_sp[s]) < MIN_RECORDISTS_PER_SPECIES
    )
    mask = np.array([s in keep_sp for s in species])
    return {m: x[mask] for m, x in spaces.items()}, species[mask], who[mask], keep_sp, single


def _fold(x, y, test, device):
    """One scored fold, restricted to classes present on both sides.

    **That restriction has to be applied to both arms or the comparison is rigged.** A
    blocked split strands whole species on one side; dropping those from the blocked arm
    alone would leave it a smaller and easier label set than the random arm, which inflates
    blocked accuracy and understates the very drop being measured.
    """
    if not test.any() or test.all():
        return None
    shared = set(y[~test]) & set(y[test])
    if len(shared) < 3:
        return None
    keep = np.array([s in shared for s in y])
    t2, x2, y2 = test[keep], x[keep], y[keep]
    if not t2.any() or t2.all():
        return None
    return probe_accuracy(x2[~t2], y2[~t2], x2[t2], y2[t2], device), len(shared), int(t2.sum())


def run_space(name, x, species, who, keep_sp, repeats, device) -> dict:
    recordists = sorted(set(who))
    out: dict = {"space": name, "dims": int(x.shape[1])}

    # ---- ARM A: random split, stratified by species.
    rand = []
    for rep in range(repeats):
        r = np.random.default_rng(SEED + rep)
        test = np.zeros(len(species), bool)
        for s in keep_sp:
            idx = np.flatnonzero(species == s)
            test[r.permutation(idx)[: max(1, int(round(HELD_FRACTION * len(idx))))]] = True
        got = _fold(x, species, test, device)
        if got:
            rand.append(got)

    # ---- ARM B: recordist-blocked. Every recording by one recordist on one side.
    block = []
    for rep in range(repeats):
        r = np.random.default_rng(SEED + 1000 + rep)
        held = set(r.permutation(recordists)[
            : max(1, int(round(HELD_FRACTION * len(recordists))))
        ])
        got = _fold(x, species, np.array([w in held for w in who]), device)
        if got:
            block.append(got)

    # ---- ARM C: paired folds on identical class sets. This is the number to quote: each
    # blocked fold's surviving class set is reused for a random fold, so the pair differ in
    # one thing only — whether a recordist may appear on both sides.
    p_rand, p_block, p_classes = [], [], []
    for rep in range(repeats):
        r = np.random.default_rng(SEED + 1000 + rep)
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

        rr = np.random.default_rng(SEED + 2000 + rep)
        rtest = np.zeros(len(yk), bool)
        for s in shared:  # same held-out fraction, stratified, same classes
            idx = np.flatnonzero(yk == s)
            rtest[rr.permutation(idx)[: max(1, int(round(bk.mean() * len(idx))))]] = True
        if not rtest.any() or rtest.all():
            continue
        p_block.append(probe_accuracy(xk[~bk], yk[~bk], xk[bk], yk[bk], device))
        p_rand.append(probe_accuracy(xk[~rtest], yk[~rtest], xk[rtest], yk[rtest], device))
        p_classes.append(len(shared))

    if not rand or not block:
        out["status"] = "no usable folds"
        return out

    a = float(np.mean([v[0] for v in rand])) * 100
    b = float(np.mean([v[0] for v in block])) * 100
    out["unpaired"] = {
        "random_top1": a, "blocked_top1": b, "drop_points": a - b,
        "random_folds": len(rand), "blocked_folds": len(block),
        "random_classes": float(np.mean([v[1] for v in rand])),
        "blocked_classes": float(np.mean([v[1] for v in block])),
    }
    if p_rand:
        pa = float(np.mean(p_rand)) * 100
        pb = float(np.mean(p_block)) * 100
        diffs = (np.array(p_rand) - np.array(p_block)) * 100
        err_r, err_b = 100 - pa, 100 - pb
        out["paired"] = {
            "random_top1": pa, "blocked_top1": pb, "drop_points": pa - pb,
            "folds": len(p_rand), "classes": float(np.mean(p_classes)),
            "per_fold_mean": float(diffs.mean()), "per_fold_sd": float(diffs.std()),
            "folds_blocked_worse": int((diffs > 0).sum()),
            "error_rate_random": err_r, "error_rate_blocked": err_b,
            "error_ratio": err_b / err_r if err_r else None,
            "gate_met": bool((pa - pb) > GATE_POINTS),
        }
    return out


def sweep_classes(name, x, species, who, repeats, device) -> list[dict]:
    """The paired drop as a function of how many species are in the label set.

    **This exists because the gate's unit makes the pilot and the full run incomparable, and
    someone will notice.** The pilot scored 62 classes and reached 93.29 % top-1, where 9.68
    points of drop was 2.44x the errors. The full run scores 886 classes, where top-1 is far
    lower and the same *ratio* of errors would show up as a much larger number of points. A
    gate written in accuracy points is therefore partly a gate on how many species happened
    to clear the floor, which is not a fact about recordists at all.

    So the drop is reported across nested label sets drawn from the same recordings and the
    same folds. If the points-drop climbs with class count while the error ratio stays flat,
    the ratio is the invariant and the points bar was measuring our corpus depth.
    """
    all_sp = sorted(set(species))
    targets = [n for n in (62, 150, 300, 500, len(all_sp)) if n <= len(all_sp)]
    if targets and targets[-1] != len(all_sp):
        targets.append(len(all_sp))
    recordists = sorted(set(who))
    rows = []
    for target in targets:
        pick = set(np.random.default_rng(SEED + 7).permutation(all_sp)[:target])
        m = np.array([s in pick for s in species])
        xs, ys, ws = x[m], species[m], who[m]
        p_rand, p_block = [], []
        for rep in range(repeats):
            r = np.random.default_rng(SEED + 1000 + rep)
            held = set(r.permutation(recordists)[
                : max(1, int(round(HELD_FRACTION * len(recordists))))
            ])
            btest = np.array([w in held for w in ws])
            if not btest.any() or btest.all():
                continue
            shared = set(ys[~btest]) & set(ys[btest])
            if len(shared) < 3:
                continue
            keep = np.array([s in shared for s in ys])
            xk, yk, bk = xs[keep], ys[keep], btest[keep]
            rr = np.random.default_rng(SEED + 2000 + rep)
            rtest = np.zeros(len(yk), bool)
            for s in shared:
                idx = np.flatnonzero(yk == s)
                rtest[rr.permutation(idx)[: max(1, int(round(bk.mean() * len(idx))))]] = True
            if not rtest.any() or rtest.all():
                continue
            p_block.append(probe_accuracy(xk[~bk], yk[~bk], xk[bk], yk[bk], device))
            p_rand.append(probe_accuracy(xk[~rtest], yk[~rtest], xk[rtest], yk[rtest], device))
        if not p_rand:
            continue
        pa, pb = float(np.mean(p_rand)) * 100, float(np.mean(p_block)) * 100
        err_r, err_b = 100 - pa, 100 - pb
        rows.append({
            "species_target": target, "folds": len(p_rand),
            "random_top1": pa, "blocked_top1": pb, "drop_points": pa - pb,
            "error_ratio": err_b / err_r if err_r else None,
            "gate_met": bool((pa - pb) > GATE_POINTS),
        })
        log(f"    {name} sweep {target:4d} classes -> drop {pa - pb:5.2f} pts, "
            f"{err_b / err_r if err_r else float('nan'):.2f}x errors")
    return rows


def report(res: dict) -> None:
    p = res.get("paired")
    u = res.get("unpaired")
    print(f"\n  --- {res['space'].upper()}  ({res['dims']}-d frozen features)")
    if not u:
        print(f"      {res.get('status', 'no result')}")
        return
    print(f"      unpaired   random {u['random_top1']:6.2f} %   "
          f"blocked {u['blocked_top1']:6.2f} %   drop {u['drop_points']:6.2f}")
    print(f"        classes scored   random {u['random_classes']:.1f}   "
          f"blocked {u['blocked_classes']:.1f}")
    if not p:
        print("      paired arm produced no usable folds")
        return
    print(f"      PAIRED     random {p['random_top1']:6.2f} %   "
          f"blocked {p['blocked_top1']:6.2f} %   DROP {p['drop_points']:6.2f} points")
    print(f"        {p['folds']} paired folds, {p['classes']:.0f} classes each; "
          f"blocked worse in {p['folds_blocked_worse']}/{p['folds']}")
    print(f"        per fold  mean {p['per_fold_mean']:+.2f}  sd {p['per_fold_sd']:.2f}")
    print(f"        as errors {p['error_rate_random']:.2f} % -> "
          f"{p['error_rate_blocked']:.2f} %   ({p['error_ratio']:.2f}x)")
    print(f"        gate > {GATE_POINTS} points: "
          f"{'MET' if p['gate_met'] else 'NOT met'}")


def main() -> int:
    repeats = REPEATS
    if "--repeats" in sys.argv:
        repeats = int(sys.argv[sys.argv.index("--repeats") + 1])
    if not EMB.exists() or not META.exists():
        log("embeddings are missing — run analysis/w0_full_fetch.py first.")
        return 2

    spaces, species, who, census = load()
    spaces, species, who, keep_sp, single = apply_floor(spaces, species, who)
    device = device_of()

    print("=" * 74)
    print("W0 FULL RUN — what a recordist-blocked split costs, two models, post-cutoff audio")
    print("=" * 74)
    for k, v in census.items():
        print(f"  {k:24s} {v:7d}")
    print(f"  embedded and scorable    {len(species):7d}")
    print(f"  species scored           {len(keep_sp):7d}")
    print(f"  recordists               {len(set(who)):7d}")
    print(f"  single-recordist species dropped {single:5d}"
          "   <- unclassifiable under blocking, not leakage")
    print(f"  probe device             {str(device):>7s}   folds per arm {repeats}")
    print("  (pilot, for comparison:       62 species over 2 158 recordings, one model)")

    if len(keep_sp) < 20 or len(species) < 1000:
        print("\n  still too thin — let the fetch finish before reading this.")

    t0 = time.time()
    results = {}
    for m in MODELS:
        results[m] = run_space(m, spaces[m], species, who, keep_sp, repeats, device)
        report(results[m])
        if results[m].get("paired"):
            results[m]["class_sweep"] = sweep_classes(
                m, spaces[m], species, who, repeats, device
            )
            print(f"      class-count sweep  {'classes':>8}{'drop pts':>10}{'errors':>9}")
            for row in results[m]["class_sweep"]:
                print(f"        {'':16}{row['species_target']:8d}"
                      f"{row['drop_points']:10.2f}"
                      f"{row['error_ratio']:8.2f}x")
        log(f"  {m} done in {time.time() - t0:.0f}s")

    # The two models are the point: one model cannot separate a property of the archives
    # from a property of that model.
    print()
    print("=" * 74)
    drops = {m: (results[m].get("paired") or {}).get("drop_points") for m in MODELS}
    met = {m: (results[m].get("paired") or {}).get("gate_met") for m in MODELS}
    for m in MODELS:
        d = drops[m]
        print(f"  {m:8s} paired drop "
              f"{'n/a' if d is None else f'{d:6.2f} points'}   "
              f"gate {'MET' if met[m] else 'NOT met'}")
    both = all(met[m] for m in MODELS)
    any_ = any(met[m] for m in MODELS)
    # A missing arm is not a failed gate. Falling through to "not met" here would have
    # printed "the drop is real and consistent but under 10 points" over a run that scored
    # no folds at all, which is the one sentence this script must never emit unearned.
    incomplete = [m for m in MODELS if drops[m] is None]
    if incomplete:
        verdict = (f"INCOMPLETE — no scorable folds for {', '.join(incomplete)}. "
                   "Nothing is measured here; let the fetch finish and re-run.")
        both = any_ = False
    elif both:
        verdict = ("GATE MET on both models — a recordist-blocked split costs more than "
                   f"{GATE_POINTS} points of top-1 in two independent embedding spaces.")
    elif any_:
        verdict = ("SPLIT — the gate is met on one model and not the other. That is "
                   "reportable as it stands and must not be resolved by picking one.")
    else:
        verdict = (f"GATE NOT MET on either model. The drop is real and consistent but "
                   f"under {GATE_POINTS} points, as the pilot found.")
    print()
    print(f"  VERDICT: {verdict}")
    print("  Both models are frozen in both arms, and the audio was uploaded after Perch")
    print("  2.0's snapshot, so this is not a memorisation artefact.")

    OUT.write_text(json.dumps({
        "census": census,
        "recordings_scored": int(len(species)),
        "species_scored": len(keep_sp),
        "recordists": len(set(who)),
        "single_recordist_species_dropped": single,
        "folds_per_arm": repeats,
        "gate_points": GATE_POINTS,
        "gate_met_both_models": bool(both),
        "incomplete_models": incomplete,
        "results": results,
        "audio": "xeno-canto uploads after Perch 2.0 (since 2025-09-01), q:A, grp:birds",
        "models": {"perch": "perch-2.0-frozen", "birdnet": "birdnet-v2.4-backbone-frozen"},
        "probe": "multinomial logistic, L2 C=1.0, GPU; verified against sklearn in w0_probe.py",
    }, indent=1, default=float))
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
