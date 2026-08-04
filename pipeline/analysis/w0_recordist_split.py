"""W0 pilot — what does a recordist-blocked split cost? (docs/24 Phase 1a)

**The pre-registered method could not be run, and this is the redesign.** docs/24 asked for
top-1 species accuracy from Perch 2.0 and BirdNET on a public corpus, once under a random
split and once under a recordist-blocked split. Both models trained on Xeno-canto (Perch
also on iNaturalist), so on any XC-derived corpus their accuracy measures memorisation as
much as generalisation, and the gap between the two splits partly measures *which*
recordings were memorised rather than what blocking costs.

Two changes fix that, and both make the experiment cheaper rather than more expensive.

  1. **The model is frozen and only a linear probe is trained.** The foundation model is a
     fixed feature extractor in both arms, so whatever it memorised is identical on both
     sides and cancels out of the difference. What differs between arms is only the probe's
     training set, which is the thing the claim is about.
  2. **The audio was uploaded after the model's training snapshot.** `SINCE` in
     `w6_t1b_perch_postcutoff.py` is a month past Perch 2.0's publication, and Xeno-canto's
     `since:` tag filters on upload date, so these recordings provably could not have been
     in the snapshot. This is belt and braces on top of (1) and it is what makes the result
     quotable without a contamination paragraph attached.

**Read this as a pilot, not as the paper.** The population is whatever
`w6_t1b_perch_postcutoff.py` fetched — hundreds of recordings, not the tens of thousands a
published version needs — and one model, because BirdNET is not wired here. What it can
establish is the sign and the rough size of the effect on uncontaminated audio, which is
what decides whether the full run is worth building.

**SUPERSEDED for the headline number: see `w0_full.py`.** The full run was built and it
carries both of the things this file says it lacks — 886 species over ~8 300 recordings
against 62 over 2 158, and BirdNET beside Perch. Two things this pilot got wrong about its
own population are worth keeping visible, because both were invisible from inside it:

  * Its catalogue held exactly 6 000 recordings, which was `SEARCH_PAGES = 60` in
    `w6_t1b_perch_postcutoff.py` and not the archive. The same query has **21 928**.
  * It selected by *recordist*, inheriting T1b's rule, while W0's unit is the *species*.
    That is what left 62 scorable classes out of 827 species fetched.

This file is kept runnable and unchanged: it is the measurement the whitepaper's pilot row
was computed from, and it should stay reproducible against the catalogue it actually used.

**The species filter is not a convenience, it is the experiment.** Under a recordist-blocked
split, a species whose recordings all come from one recordist lands entirely on one side and
cannot be classified at all — that is not "leakage", it is an empty test class, and counting
it as an error would manufacture the result W0 is looking for. Only species with recordings
from at least two recordists are used, and the number excluded is reported.

Depends on the audio cache `w6_t1b_perch_postcutoff.py` populates. Run that first.

Usage:  .venv/bin/python analysis/w0_recordist_split.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from birdy_pipeline import perch  # noqa: E402

CACHE = ROOT / "out/audio-postcutoff"
META = ROOT / "out/audio-postcutoff/_meta.json"
EMB = ROOT / "out/external/postcutoff-perch.npz"
MODEL_DIR = ROOT / "out/perch"
OUT = Path(__file__).resolve().parent / "w0_recordist_split.json"

WINDOW_BUDGET = 6
MIN_PER_SPECIES = 6
MIN_RECORDISTS_PER_SPECIES = 2
SEED = 0
REPEATS = 20  # random-split arm is averaged; the blocked arm is enumerated per fold

#: Pre-registered in docs/24, restated here so it cannot drift.
GATE_POINTS = 10.0


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def audio_for(rid: str) -> Path | None:
    """The cached file for a recording, whatever extension the server redirected to."""
    for path in CACHE.glob(f"xc{rid}.*"):
        if path.suffix.lower() != ".json":
            return path
    return None


def load_model() -> perch.PerchModel:
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(MODEL_DIR / "hf"))
    onnx_path = hf_hub_download(perch.HF_REPO, perch.HF_FILE)
    return perch.PerchModel(
        session=ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"]),
        labels=[],
    )


def embed_one(model: perch.PerchModel, path: Path) -> np.ndarray | None:
    import soundfile as sf

    audio, rate = sf.read(str(path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != perch.PERCH_SAMPLE_RATE:
        n = int(round(len(audio) * perch.PERCH_SAMPLE_RATE / rate))
        if n < 2:
            return None
        audio = np.interp(
            np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio
        ).astype(np.float32)
    win = int(perch.PERCH_WINDOW_SECONDS * perch.PERCH_SAMPLE_RATE)
    if len(audio) < win:
        audio = np.pad(audio, (0, win - len(audio)))
    starts = list(range(0, max(1, len(audio) - win + 1), win))[:WINDOW_BUDGET]
    batch = np.stack([audio[s : s + win] for s in starts]).astype(np.float32)
    _scores, emb = model.label(batch)
    return np.asarray(emb, dtype=np.float64).mean(axis=0)


def embeddings(meta: dict[str, dict]) -> tuple[np.ndarray, list[str]]:
    """Frozen Perch features, cached — the probe is the only thing that ever trains."""
    if EMB.exists():
        z = np.load(EMB, allow_pickle=True)
        return z["x"], list(z["ids"])
    model = load_model()
    ids, vecs = [], []
    t0 = time.time()
    for i, rid in enumerate(sorted(meta)):
        # The cache is named by `XenoCanto.download`, which lowercases the prefix and takes
        # the suffix from the redirected URL — so these are `xc123.wav` as often as
        # `xc123.mp3`. Guessing `XC{id}.mp3` here matched nothing at all and would have
        # reported an empty population rather than failing.
        path = audio_for(rid)
        if path is None:
            continue
        try:
            v = embed_one(model, path)
        except Exception as exc:
            log(f"  embed {rid}: {exc}")
            continue
        if v is None:
            continue
        ids.append(rid)
        vecs.append(v)
        if (i + 1) % 100 == 0:
            log(f"  embedded {len(ids)}/{i + 1} in {time.time() - t0:.0f}s")
    x = np.stack(vecs)
    EMB.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(EMB, x=x, ids=np.array(ids, dtype=object))
    return x, ids


def probe(xtr, ytr, xte, yte) -> float:
    """Top-1 accuracy of a multinomial logistic probe on frozen features."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(xtr)
    # No `n_jobs`: it has had no effect since scikit-learn 1.8 and only emits a warning
    # per fold, which at 40 folds buries the result it is printed above.
    clf = LogisticRegression(max_iter=2000, C=1.0)
    clf.fit(scaler.transform(xtr), ytr)
    return float(clf.score(scaler.transform(xte), yte))


def self_test() -> int:
    """Two synthetic cases with known answers, because a drop is not self-validating.

    A number out of this script is only worth reading if the two arms can tell apart a
    world where recordist identity predicts species from one where it does not. Run with
    `--self-test`; it needs no audio and no model.

      A  recordist assigned at random    -> blocking should cost nothing
      B  recordist confounded with species -> blocking should be devastating

    Measured when this was written: A dropped +0.0 points, B dropped +77.4.
    """
    rng = np.random.default_rng(0)
    nsp, nrec, per = 12, 20, 12

    def arms(x, species, who, seed=0, reps=10):
        ra, ba = [], []
        for rep in range(reps):
            r = np.random.default_rng(seed + rep)
            test = np.zeros(len(species), bool)
            for s in sorted(set(species)):
                idx = np.flatnonzero(species == s)
                test[r.permutation(idx)[: max(1, int(round(0.3 * len(idx))))]] = True
            got = _score(x, species, test)
            if got:
                ra.append(got[0])
        recs = sorted(set(who))
        for rep in range(reps):
            r = np.random.default_rng(seed + 1000 + rep)
            held = set(r.permutation(recs)[: max(1, int(round(0.3 * len(recs))))])
            got = _score(x, species, np.array([w in held for w in who]))
            if got:
                ba.append(got[0])
        return float(np.mean(ra)) * 100, float(np.mean(ba)) * 100

    species, who, feats = [], [], []
    for i in range(nsp):
        centre = rng.normal(size=16) * 3
        for _ in range(per):
            species.append(f"sp{i}")
            who.append(f"rec{rng.integers(nrec)}")
            feats.append(centre + rng.normal(size=16) * 0.6)
    a_rand, a_block = arms(np.array(feats), np.array(species), np.array(who))

    species, who, feats = [], [], []
    for i in range(nsp):
        centre = rng.normal(size=16) * 3
        for k in range(2):
            sig = rng.normal(size=16) * 4
            for _ in range(per // 2):
                species.append(f"sp{i}")
                who.append(f"rec{i}_{k}")
                feats.append(centre * 0.15 + sig + rng.normal(size=16) * 0.5)
    b_rand, b_block = arms(np.array(feats), np.array(species), np.array(who))

    print(f"  A recordist independent   random {a_rand:6.1f}%  blocked {a_block:6.1f}%"
          f"  drop {a_rand - a_block:+6.1f}")
    print(f"  B recordist confounded    random {b_rand:6.1f}%  blocked {b_block:6.1f}%"
          f"  drop {b_rand - b_block:+6.1f}")
    ok = (a_rand - a_block) < 5.0 and (b_rand - b_block) > 30.0
    print(f"  self-test: {'PASS' if ok else 'FAIL'}"
          " — A must be flat and B must collapse")
    return 0 if ok else 1


def _score(x, species, test):
    """Shared by `main` and `self_test`; see the comment in `main` for why both arms use it."""
    if not test.any() or test.all():
        return None
    shared = set(species[~test]) & set(species[test])
    if len(shared) < 3:
        return None
    keep = np.array([s in shared for s in species])
    t2, x2, y2 = test[keep], x[keep], species[keep]
    if not t2.any() or t2.all():
        return None
    return probe(x2[~t2], y2[~t2], x2[t2], y2[t2]), len(shared), int(t2.sum())


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if not META.exists():
        log(f"{META} is missing — run analysis/w6_t1b_perch_postcutoff.py first.")
        return 2
    meta = json.loads(META.read_text())

    x, ids = embeddings(meta)
    species = np.array([meta[r]["species"] for r in ids])
    who = np.array([meta[r]["recordist"] for r in ids])

    # The species filter, and the count it excludes is part of the result.
    by_sp_recordists = defaultdict(set)
    counts = Counter(species)
    for s, w in zip(species, who):
        by_sp_recordists[s].add(w)
    keep_sp = {
        s for s in counts
        if counts[s] >= MIN_PER_SPECIES
        and len(by_sp_recordists[s]) >= MIN_RECORDISTS_PER_SPECIES
    }
    mask = np.array([s in keep_sp for s in species])

    print("=" * 74)
    print("W0 pilot — what a recordist-blocked split costs a probe on frozen Perch")
    print("=" * 74)
    print(f"  recordings embedded (post-cutoff audio)   {len(ids):5d}")
    print(f"  species before filtering                  {len(counts):5d}")
    print(f"  species with >= {MIN_PER_SPECIES} recordings AND")
    print(f"    >= {MIN_RECORDISTS_PER_SPECIES} recordists                      {len(keep_sp):5d}")
    print(f"  recordings used                           {int(mask.sum()):5d}")
    print(f"  single-recordist species dropped          "
          f"{sum(1 for s in counts if counts[s] >= MIN_PER_SPECIES and len(by_sp_recordists[s]) < MIN_RECORDISTS_PER_SPECIES):5d}"
          "   <- unclassifiable under blocking, not leakage")

    if mask.sum() < 100 or len(keep_sp) < 5:
        print()
        print("  TOO SMALL to measure. The pilot needs a wider fetch —")
        print("  raise SEARCH_PAGES / RECORDING_CAP in w6_t1b_perch_postcutoff.py.")
        OUT.write_text(json.dumps({"status": "too_small",
                                   "recordings": int(mask.sum()),
                                   "species": len(keep_sp)}, indent=1))
        return 1

    x, species, who = x[mask], species[mask], who[mask]
    rng = np.random.default_rng(SEED)

    # `_score` restricts each fold to species present on BOTH sides before scoring.
    # **That restriction has to be applied to both arms or the comparison is rigged.** A
    # blocked split strands whole species on one side, and dropping those from the blocked
    # arm alone leaves it a smaller, easier label set than the random arm — which inflates
    # blocked accuracy and understates the very drop this is measuring. Both arms call the
    # same helper, and each fold reports how many classes it scored so the two can be
    # checked against each other in the output.
    def score(test: np.ndarray):
        return _score(x, species, test)

    # ---- ARM A: random split, stratified by species.
    rand_acc, rand_classes, rand_test = [], [], []
    for rep in range(REPEATS):
        r = np.random.default_rng(SEED + rep)
        test = np.zeros(len(species), dtype=bool)
        for s in keep_sp:
            idx = np.flatnonzero(species == s)
            pick = r.permutation(idx)[: max(1, int(round(0.3 * len(idx))))]
            test[pick] = True
        got = score(test)
        if got:
            rand_acc.append(got[0])
            rand_classes.append(got[1])
            rand_test.append(got[2])

    # ---- ARM B: recordist-blocked. Every recording by one recordist on one side.
    block_acc, block_classes, block_test = [], [], []
    recordists = sorted(set(who))
    for rep in range(REPEATS):
        r = np.random.default_rng(SEED + 1000 + rep)
        held = set(r.permutation(recordists)[: max(1, int(round(0.3 * len(recordists))))])
        got = score(np.array([w in held for w in who]))
        if got:
            block_acc.append(got[0])
            block_classes.append(got[1])
            block_test.append(got[2])

    # ---- ARM C: paired folds on identical class sets.
    # The two arms above are not scored on the same task. A blocked split strands whole
    # species on one side, so its folds end up with fewer classes than the random folds —
    # and fewer classes is an easier problem, which *understates* the drop. Here each
    # blocked fold's surviving class set is reused for a random fold, so the pair differ in
    # one thing only: whether a recordist may appear on both sides.
    paired_rand, paired_block, paired_classes = [], [], []
    for rep in range(REPEATS):
        r = np.random.default_rng(SEED + 1000 + rep)
        held = set(r.permutation(recordists)[: max(1, int(round(0.3 * len(recordists))))])
        btest = np.array([w in held for w in who])
        if not btest.any() or btest.all():
            continue
        shared = set(species[~btest]) & set(species[btest])
        if len(shared) < 3:
            continue
        keep = np.array([s in shared for s in species])
        xk, yk, bk = x[keep], species[keep], btest[keep]

        rr = np.random.default_rng(SEED + 2000 + rep)
        rtest = np.zeros(len(yk), dtype=bool)
        for s in shared:  # same held-out fraction, stratified, same classes
            idx = np.flatnonzero(yk == s)
            rtest[rr.permutation(idx)[: max(1, int(round(bk.mean() * len(idx))))]] = True
        if not rtest.any() or rtest.all():
            continue
        b_acc = probe(xk[~bk], yk[~bk], xk[bk], yk[bk])
        r_acc = probe(xk[~rtest], yk[~rtest], xk[rtest], yk[rtest])
        paired_block.append(b_acc)
        paired_rand.append(r_acc)
        paired_classes.append(len(shared))

    if not rand_acc or not block_acc:
        print("\n  no usable folds; the sample is too thin for a blocked split.")
        return 1

    a, b = float(np.mean(rand_acc)) * 100, float(np.mean(block_acc)) * 100
    drop = a - b
    print()
    print(f"  random split          top-1 {a:6.2f} %   (n folds {len(rand_acc)}, "
          f"sd {np.std(rand_acc) * 100:.2f})")
    print(f"  recordist-blocked     top-1 {b:6.2f} %   (n folds {len(block_acc)}, "
          f"sd {np.std(block_acc) * 100:.2f})")
    # If these two rows disagree badly the arms were not scored on comparable tasks, and
    # the drop above is measuring the label set rather than the split.
    print(f"    classes scored        random {np.mean(rand_classes):.1f}   "
          f"blocked {np.mean(block_classes):.1f}")
    print(f"    test recordings       random {np.mean(rand_test):.0f}   "
          f"blocked {np.mean(block_test):.0f}")
    print(f"  DROP                        {drop:6.2f} points   gate > {GATE_POINTS}")
    verdict_drop = drop
    if paired_rand:
        pa, pb = float(np.mean(paired_rand)) * 100, float(np.mean(paired_block)) * 100
        verdict_drop = pa - pb
        print()
        print("  PAIRED — each fold scored on ONE class set, so the arms differ only in")
        print("  whether a recordist may appear on both sides. This is the number to quote:")
        print(f"    random split        top-1 {pa:6.2f} %")
        print(f"    recordist-blocked   top-1 {pb:6.2f} %")
        print(f"    DROP                      {pa - pb:6.2f} points   over "
              f"{len(paired_rand)} paired folds, {np.mean(paired_classes):.1f} classes each")

        # A mean without its spread is not quotable, and the folds are paired, so the
        # per-fold difference is the statistic with the least noise in it.
        diffs = (np.array(paired_rand) - np.array(paired_block)) * 100
        wins = int((diffs > 0).sum())
        # Points are a poor unit near the ceiling: the same 9 points is a much bigger
        # change in what the model gets WRONG, which is what a deployment feels.
        err_r, err_b = 100 - pa, 100 - pb
        print(f"    per fold            mean {diffs.mean():+6.2f}  sd {diffs.std():5.2f}  "
              f"blocked worse in {wins}/{len(diffs)} folds")
        print(f"    as error rate       {err_r:.2f} % -> {err_b:.2f} %   "
              f"({err_b / err_r:.2f}x the errors)")
        results_paired = {
            "random_top1": pa, "blocked_top1": pb, "drop_points": pa - pb,
            "folds": len(paired_rand), "classes": float(np.mean(paired_classes)),
            "per_fold_mean": float(diffs.mean()), "per_fold_sd": float(diffs.std()),
            "folds_blocked_worse": wins,
            "error_rate_random": err_r, "error_rate_blocked": err_b,
            "error_ratio": err_b / err_r,
        }
    else:
        results_paired = None
        print("\n  PAIRED arm produced no usable folds.")

    print()
    print(f"  W0 pilot VERDICT: {'gate met' if verdict_drop > GATE_POINTS else 'gate NOT met'}"
          " — on one model, on post-cutoff audio, at pilot scale.")
    print("  Perch is frozen in both arms, so this is not a memorisation artefact.")

    OUT.write_text(json.dumps({
        "recordings": int(len(species)), "species": len(keep_sp),
        "random_top1": a, "blocked_top1": b, "drop_points": drop,
        "random_folds": len(rand_acc), "blocked_folds": len(block_acc),
        "gate_points": GATE_POINTS, "gate_met": bool(verdict_drop > GATE_POINTS),
        "paired": results_paired,
        "model": "perch-2.0-frozen", "audio": "xeno-canto uploads after Perch 2.0",
    }, indent=1))
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
