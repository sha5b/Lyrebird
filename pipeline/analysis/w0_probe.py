"""The linear probe, on the GPU, and the proof that it is the same estimator as the pilot's.

**Why this is not just `LogisticRegression` again.** The pilot fitted 62 classes over 2 158
recordings and scikit-learn's lbfgs was the obvious choice. The full run is 886 classes over
13 646 recordings in 1 536 dimensions, and multinomial lbfgs there costs roughly
`n x d x k = 1.9e10` multiply-adds *per iteration*, which is minutes an iteration on this
CPU and hundreds of iterations a fold, times 20 folds, times two arms, times two models.
That is not a tractable job; it is the same job on the wrong device.

**Why the swap is safe, and how that is established rather than asserted.** Swapping the
estimator silently would make the full run incomparable with the published pilot, so this
module implements the *same objective* scikit-learn minimises and `--verify` checks the two
against each other on real data:

    scikit-learn (multinomial, L2, no intercept scaling) minimises
        0.5 * ||W||^2  +  C * sum_i crossentropy_i
    dividing through by C*n gives the mean-loss form used here
        mean_i crossentropy_i  +  (0.5 / (C * n)) * ||W||^2

so `C=1.0` is weight decay `1/n` against the mean loss. Full-batch L-BFGS is the same
optimiser family, so agreement should be tight rather than approximate, and `--verify`
fails loudly if it is not.

Usage:  .venv/bin/python analysis/w0_probe.py --verify
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

#: Matches the pilot's `LogisticRegression(max_iter=2000, C=1.0)`.
C_INVERSE_REG = 1.0
MAX_ITER = 2000
#: L-BFGS is a full-batch method, so this is iterations rather than epochs.
TOLERANCE = 1e-7


def device_of(prefer_gpu: bool = True):
    import torch

    if prefer_gpu and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def probe_accuracy(
    xtr: np.ndarray,
    ytr: np.ndarray,
    xte: np.ndarray,
    yte: np.ndarray,
    device=None,
) -> float:
    """Top-1 accuracy of a multinomial logistic probe, standardised features, L2 penalty.

    Standardisation is fitted on the training side only — fitting it on both would leak the
    test set's mean and variance across the split, which is exactly the kind of leak W0 is
    about.
    """
    import torch

    if device is None:
        device = device_of()

    classes, ytr_i = np.unique(ytr, return_inverse=True)
    index = {c: i for i, c in enumerate(classes)}
    yte_i = np.array([index[c] for c in yte], dtype=np.int64)

    mean = xtr.mean(axis=0, keepdims=True)
    sd = xtr.std(axis=0, keepdims=True)
    sd[sd == 0] = 1.0

    xt = torch.tensor((xtr - mean) / sd, dtype=torch.float32, device=device)
    xv = torch.tensor((xte - mean) / sd, dtype=torch.float32, device=device)
    yt = torch.tensor(ytr_i, dtype=torch.long, device=device)
    yv = torch.tensor(yte_i, dtype=torch.long, device=device)

    n, d = xt.shape
    k = len(classes)
    weight = torch.zeros((d, k), dtype=torch.float32, device=device, requires_grad=True)
    bias = torch.zeros(k, dtype=torch.float32, device=device, requires_grad=True)
    decay = 1.0 / (C_INVERSE_REG * n)

    opt = torch.optim.LBFGS(
        [weight, bias],
        max_iter=MAX_ITER,
        tolerance_grad=TOLERANCE,
        tolerance_change=TOLERANCE,
        history_size=10,
        line_search_fn="strong_wolfe",
    )
    loss_fn = torch.nn.functional.cross_entropy

    def closure():
        opt.zero_grad()
        loss = loss_fn(xt @ weight + bias, yt)
        # The bias is unpenalised, as in scikit-learn.
        loss = loss + 0.5 * decay * (weight * weight).sum()
        loss.backward()
        return loss

    opt.step(closure)

    with torch.no_grad():
        pred = (xv @ weight + bias).argmax(dim=1)
        return float((pred == yv).double().mean().item())


def sklearn_accuracy(xtr, ytr, xte, yte) -> float:
    """The pilot's estimator, verbatim, for the comparison in `--verify`."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(xtr)
    clf = LogisticRegression(max_iter=MAX_ITER, C=C_INVERSE_REG)
    clf.fit(scaler.transform(xtr), ytr)
    return float(clf.score(scaler.transform(xte), yte))


def verify() -> int:
    """Agreement on synthetic data and on the pilot's real Perch features."""
    print("=" * 74)
    print("probe equivalence — torch/GPU against the pilot's scikit-learn estimator")
    print("=" * 74)
    dev = device_of()
    print(f"  device: {dev}")
    rows = []

    # --- synthetic, where the answer is knowable and the classes are balanced.
    rng = np.random.default_rng(0)
    for nsp, per, dim in ((12, 30, 64), (40, 20, 256)):
        centres = rng.normal(size=(nsp, dim)) * 2.0
        x, y = [], []
        for i in range(nsp):
            for _ in range(per):
                x.append(centres[i] + rng.normal(size=dim))
                y.append(f"c{i}")
        x = np.asarray(x)
        y = np.asarray(y)
        test = rng.permutation(len(y))[: len(y) // 3]
        m = np.zeros(len(y), bool)
        m[test] = True
        rows.append((f"synthetic {nsp}c/{dim}d",
                     sklearn_accuracy(x[~m], y[~m], x[m], y[m]),
                     probe_accuracy(x[~m], y[~m], x[m], y[m], dev)))

    # --- the pilot's own features and population, which is the comparison that matters.
    emb = ROOT / "out/external/postcutoff-perch.npz"
    meta = ROOT / "out/audio-postcutoff/_meta.json"
    if emb.exists() and meta.exists():
        import json
        from collections import Counter, defaultdict

        z = np.load(emb, allow_pickle=True)
        info = json.loads(meta.read_text())
        ids = [r for r in list(z["ids"]) if r in info]
        keep_idx = [i for i, r in enumerate(list(z["ids"])) if r in info]
        x = z["x"][keep_idx]
        species = np.array([info[r]["species"] for r in ids])
        who = np.array([info[r]["recordist"] for r in ids])
        counts = Counter(species)
        by_sp = defaultdict(set)
        for s, w in zip(species, who):
            by_sp[s].add(w)
        keep = {s for s in counts if counts[s] >= 6 and len(by_sp[s]) >= 2}
        m0 = np.array([s in keep for s in species])
        x, species, who = x[m0], species[m0], who[m0]

        r = np.random.default_rng(0)
        test = np.zeros(len(species), bool)
        for s in keep:
            idx = np.flatnonzero(species == s)
            test[r.permutation(idx)[: max(1, int(round(0.3 * len(idx))))]] = True
        shared = set(species[~test]) & set(species[test])
        kk = np.array([s in shared for s in species])
        xs, ys, ts = x[kk], species[kk], test[kk]
        rows.append((f"pilot Perch {len(shared)}c/{x.shape[1]}d",
                     sklearn_accuracy(xs[~ts], ys[~ts], xs[ts], ys[ts]),
                     probe_accuracy(xs[~ts], ys[~ts], xs[ts], ys[ts], dev)))
    else:
        print("  (pilot embeddings absent — synthetic cases only)")

    print()
    print(f"  {'case':26}{'sklearn':>10}{'torch':>10}{'delta':>9}  verdict")
    ok = True
    for name, a, b in rows:
        d = (b - a) * 100
        good = abs(d) <= 1.0
        ok &= good
        print(f"  {name:26}{a * 100:9.2f}%{b * 100:9.2f}%{d:+8.2f}  "
              f"{'OK' if good else 'FAIL'}")
    print()
    print(f"  equivalence: {'PASS' if ok else 'FAIL'} — "
          "the two estimators must agree within 1 accuracy point")
    return 0 if ok else 1


def benchmark() -> int:
    """How long one fold costs at full-run scale, on each device."""
    import torch

    rng = np.random.default_rng(0)
    nsp, per, dim = 886, 15, 1536
    centres = rng.normal(size=(nsp, dim)).astype(np.float32)
    x = np.repeat(centres, per, axis=0) + rng.normal(size=(nsp * per, dim)).astype(np.float32)
    y = np.repeat([f"c{i}" for i in range(nsp)], per)
    m = np.zeros(len(y), bool)
    m[rng.permutation(len(y))[: len(y) // 3]] = True
    print(f"  scale: {len(y)} rows, {dim} dims, {nsp} classes")
    for name, dev in (("cuda", torch.device("cuda")) if torch.cuda.is_available()
                      else ("cpu", torch.device("cpu")),):
        t0 = time.time()
        acc = probe_accuracy(x[~m], y[~m], x[m], y[m], dev)
        print(f"  {name}: {time.time() - t0:.1f}s  (acc {acc * 100:.1f}%)")
    return 0


if __name__ == "__main__":
    if "--benchmark" in sys.argv:
        raise SystemExit(benchmark())
    raise SystemExit(verify())
