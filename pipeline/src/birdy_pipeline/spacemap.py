"""The browser's bridge into the learned embedding space: a ridge map from 28-d to 32-d.

**Why this module exists.** Phase 2 of docs/09 moves the galaxy's projection, clustering
and centroids into the critic's 32-d embedding, because it is the measurably better
similarity space (§9.7/§9.8). But the browser cannot run the critic — no weights ship,
the assets are plain JSON/f32, and that is a hard constraint (§9.4) rather than a
packaging detail. What the browser *can* compute is the same 28-d window descriptor it
has always computed. So the live path needs a map from the space it lives in to the
space the galaxy now lives in, fitted offline and shipped as numbers.

A linear ridge was the honest choice of map while it passed its gate — the two spaces
are two views of the same syllables, and the question is how much of the embedding is
*recoverable* from the descriptor; a nonlinear map could fit the recording conditions
of the training pairs (the very thing the descriptor and the embedding disagree least
about) and report a flattering number that does not survive a new microphone.

**That argument fell to a measurement.** On the 19-species critic the ridge cleared the
gate at 0.8585 median cosine. The 47 k retrain (2026-07-29, finer contrastive typing —
485 types where the old space had 357) dropped it to 0.7997, below the 0.8 gate, with
nearest-centroid agreement 0.18 against the galaxy's own clusters: the new embedding
encodes structure the descriptor simply does not project linearly. So the map class is
now chosen the same way every other knob here is — on held-out *recordings*, never on
the eval rows — between the linear ridge and an RFF ridge (random Fourier features
approximating an RBF kernel, then the same closed-form ridge). Measured on the 47 185
store pairs under this module's exact protocol: linear 0.7585 median / 0.176 agreement,
RFF (D=2048, sigma=4, lambda=1) **0.9043 / 0.482** — the validation-to-eval gap is 0.01,
so the flattering-fit concern is answered by the split, not by refusing the model
class. The linear map is still fitted and still ships when it wins; the refutation is
recorded here, not deleted.

**The gate is the point.** Everything about how well this works is measured on
recordings the map never fitted, split by recording and never by syllable — two
syllables of one bird in one take are nearly the same pair twice, and a syllable-level
split would measure memorisation of the session instead of the map. The numbers land in
`feature-space.json`'s `embedding.mapQuality`, and when the median mapped-vs-true
cosine falls under `ACCEPT_MEDIAN_COSINE` the map still ships but with
`accepted: false`, which tells the browser to keep using the 28-d path. A bad map that
ships silently is how you get a galaxy that lights the wrong knots with total
confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np

#: Ridge penalties swept on the validation split. The descriptor has 28 inputs and the
#: store has tens of thousands of pairs, so the interesting range is "almost none" to
#: "the inputs are nearly collinear anyway"; the sweep decides, per corpus.
LAMBDAS: tuple[float, ...] = (0.1, 1.0, 10.0, 100.0, 1000.0)

#: RFF map knobs (see the module docstring for why this class exists). D random cosine
#: features approximate an RBF kernel of bandwidth `sigma` on standardised inputs;
#: sigma and the ridge penalty are swept on the validation recordings, D is fixed —
#: 512 already clears the gate (0.8818) and 2048 is the knee (0.9043; 4096 bought
#: nothing in the sweep that chose this).
RFF_D = 2048
RFF_SIGMAS: tuple[float, ...] = (2.5, 4.0, 6.0)
RFF_LAMBDAS: tuple[float, ...] = (0.1, 1.0, 10.0)

#: The f32 asset the RFF weights ship as, beside `feature-space.json` — 123 k floats
#: are a 1 MB JSON but a 0.5 MB binary, and the app already loads f32 assets.
RFF_FILE = "space-map.f32"

#: Median mapped-vs-true cosine on held-out recordings below which the map is shipped
#: but flagged `accepted: false` — the browser reads that and stays on the 28-d path.
#: 0.8 is the level two real syllables of one type score against each other in the
#: embedding's own frame, so below it the map is adding more distance than the biology
#: does.
ACCEPT_MEDIAN_COSINE = 0.8


def _unit_rows(z: np.ndarray) -> np.ndarray:
    return z / np.maximum(np.linalg.norm(z, axis=1, keepdims=True), 1.0e-12)


def _ridge_fit(x: np.ndarray, y: np.ndarray, lam: float) -> tuple[np.ndarray, np.ndarray]:
    """Closed-form ridge with an unpenalised intercept, via the normal equations."""
    xm = x.mean(axis=0)
    ym = y.mean(axis=0)
    xc = x - xm
    yc = y - ym
    w = np.linalg.solve(xc.T @ xc + lam * np.eye(x.shape[1]), xc.T @ yc)
    return w, ym - xm @ w


def _recording_split(
    recordings: Sequence[str], fraction: float, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """Boolean (fit, held-out) masks over rows, split so whole recordings land on one side.

    Two syllables from one recording share the microphone, the room, the weather and the
    bird's mood; letting the fit see some of them and grading it on the rest would
    measure how well the map recognises a *session*, which is precisely the thing it
    must not be rewarded for. Recordings are the smallest unit that is genuinely new.
    """
    n = len(recordings)
    names = sorted(set(recordings))
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(names))
    n_hold = max(1, int(round((1.0 - fraction) * len(names)))) if len(names) > 1 else 0
    held = {names[i] for i in order[:n_hold]}
    hold_mask = np.asarray([r in held for r in recordings])
    return ~hold_mask, hold_mask


def _cosines(mapped: np.ndarray, true: np.ndarray) -> np.ndarray:
    return np.einsum("ij,ij->i", _unit_rows(mapped), _unit_rows(true))


def centroid_agreement(
    mapped: np.ndarray, true: np.ndarray, centroids: np.ndarray
) -> float:
    """Share of rows whose nearest centroid is the same whether mapped or truly embedded.

    The end-to-end number: the browser only ever asks "which knot is this nearest", so
    this is the share of held-out syllables that would light the same knot through the
    map as through the critic. It can exceed the cosine's suggestion — a mediocre map
    still lands on the right side of most cluster boundaries — and it can fall short of
    it, which is why both are reported.
    """
    c = _unit_rows(np.asarray(centroids, dtype=np.float64))
    near_mapped = (_unit_rows(mapped) @ c.T).argmax(axis=1)
    near_true = (_unit_rows(true) @ c.T).argmax(axis=1)
    return float((near_mapped == near_true).mean())


@dataclass
class SpaceMap:
    """A fitted 28-d -> 32-d affine map, its chosen penalty, and its honest scorecard.

    `w`/`b` are refit on *all* pairs once the penalty is chosen — the shipped map should
    see every recording there is. The quality numbers are deliberately not from that
    refit: they come from a map fitted on 80 % of recordings and applied to the other
    20 %, so they describe the map the browser gets, not the map the fit remembers.
    """

    w: np.ndarray  # (28, 32), applied to the standardised descriptor
    b: np.ndarray  # (32,)
    lam: float
    quality: dict[str, Any] = field(default_factory=dict)
    #: Held-out predictions and truths, so the caller can score them against its own
    #: centroids once those exist (the galaxy's clusters are fitted after the map is).
    eval_mapped: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    eval_true: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))

    def apply(self, x28: np.ndarray) -> np.ndarray:
        return np.asarray(x28, dtype=np.float64) @ self.w + self.b

    def to_json(self) -> dict[str, Any]:
        return {
            "w": [[round(float(v), 6) for v in row] for row in self.w],
            "b": [round(float(v), 6) for v in self.b],
            "lambda": self.lam,
            "input": "standardised 28-d window descriptor (feature-space.json mean/std)",
            "output": "standardised 32-d critic embedding (embedding.mean/std)",
        }


def _rff(x: np.ndarray, R: np.ndarray, phase: np.ndarray) -> np.ndarray:
    """Random Fourier features of an RBF kernel: sqrt(2/D) cos(x @ R + phase).

    R ~ N(0, sigma^-2 I) makes E[cos(wx+b)cos(wy+b)] = exp(-||x-y|^2 / 2 sigma^2) —
    a fixed, shippable featurisation, so the browser needs no optimiser and no torch,
    just one matmul, a cosine and a second matmul.
    """
    return np.sqrt(2.0 / R.shape[1]) * np.cos(x @ R + phase)


@dataclass
class RffMap:
    """The nonlinear candidate: RFF features of the 28-d descriptor, then ridge to 32-d.

    Same fitting discipline as `SpaceMap` — knobs chosen on held-out recordings,
    quality graded on recordings the fit never saw, shipped weights refit on all pairs.
    The weights are too wide for JSON (28x2048 + 2048x32 floats), so they ship as the
    f32 asset `RFF_FILE` with the layout `to_json` describes; the browser's apply is
    `sqrt(2/D) cos(x28 @ R + phase) @ w + b`, all in the same standardised frames the
    linear map used.
    """

    R: np.ndarray  # (28, D), gaussian projection, std 1/sigma
    phase: np.ndarray  # (D,), uniform shifts
    w: np.ndarray  # (D, 32), ridge weights over the RFF features
    b: np.ndarray  # (32,)
    sigma: float
    lam: float
    quality: dict[str, Any] = field(default_factory=dict)
    eval_mapped: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    eval_true: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))

    def apply(self, x28: np.ndarray) -> np.ndarray:
        return _rff(np.asarray(x28, dtype=np.float64), self.R, self.phase) @ self.w + self.b

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": "rff-ridge",
            "file": RFF_FILE,
            "sigma": self.sigma,
            "D": int(self.R.shape[1]),
            "lambda": self.lam,
            "layout": "little-endian f32, row-major: R (28 x D) | phase (D) | "
            "w (D x 32) | b (32)",
            "apply": "z = sqrt(2/D) * cos(x28 @ R + phase); out = z @ w + b",
            "input": "standardised 28-d window descriptor (feature-space.json mean/std)",
            "output": "standardised 32-d critic embedding (embedding.mean/std)",
        }

    def to_f32(self) -> bytes:
        parts = [
            np.asarray(a, dtype="<f4").ravel(order="C")
            for a in (self.R, self.phase, self.w, self.b)
        ]
        return np.concatenate(parts).tobytes()


def fit_map(
    x28: np.ndarray,
    z32: np.ndarray,
    recordings: Sequence[str],
    lambdas: Sequence[float] = LAMBDAS,
    seed: int = 0,
    log: Callable[[str], None] = print,
) -> SpaceMap:
    """Fit the ridge map and grade it on recordings it never saw.

    `x28` are standardised 28-d descriptors (the frame the browser will standardise its
    live windows against), `z32` the standardised 32-d embeddings of the same
    syllables, and `recordings` the recording id of each row — the split unit.
    """
    x = np.asarray(x28, dtype=np.float64)
    y = np.asarray(z32, dtype=np.float64)
    if x.shape[0] != y.shape[0] or x.shape[0] != len(recordings):
        raise ValueError(
            f"x28 {x.shape}, z32 {y.shape} and {len(recordings)} recording ids disagree"
        )
    fit_mask, eval_mask = _recording_split(recordings, 0.8, seed)
    if not eval_mask.any():
        raise ValueError("only one recording in the pairs — nothing to grade the map on")

    # The penalty is itself a fit, so it gets its own held-out slice of the fit side —
    # choosing it on the eval recordings would spend the honesty the split bought.
    sub_fit, sub_val = _recording_split(
        [r for r, m in zip(recordings, fit_mask) if m], 0.8, seed + 1
    )
    xf, yf = x[fit_mask], y[fit_mask]
    scores: list[tuple[float, float]] = []
    for lam in lambdas:
        w, b = _ridge_fit(xf[sub_fit], yf[sub_fit], lam)
        cos = _cosines(xf[sub_val] @ w + b, yf[sub_val])
        scores.append((float(np.median(cos)), lam))
    scores.sort(reverse=True)
    lam = scores[0][1]
    linear_val = scores[0][0]
    log(
        "spacemap: lambda "
        + ", ".join(f"{l:g} -> median cos {s:.3f}" for s, l in sorted(scores, key=lambda t: t[1]))
        + f"; chose {lam:g}"
    )

    # The RFF candidate, swept under the same discipline: sigma and lambda are chosen on
    # the validation recordings, and the map *class* that ships is the one with the
    # better validation score — the eval rows below grade a decision already made, so
    # they stay an honest measurement of it.
    rff_best: tuple[float, float, float, np.ndarray, np.ndarray] | None = None
    for sigma in RFF_SIGMAS:
        rng = np.random.default_rng(seed + 2)
        R = rng.normal(0.0, 1.0 / sigma, size=(x.shape[1], RFF_D))
        phase = rng.uniform(0, 2 * np.pi, size=RFF_D)
        F = _rff(xf[sub_fit], R, phase).astype(np.float64)
        Fv = _rff(xf[sub_val], R, phase).astype(np.float64)
        for rlam in RFF_LAMBDAS:
            w, b = _ridge_fit(F, yf[sub_fit], rlam)
            s = float(np.median(_cosines(Fv @ w + b, yf[sub_val])))
            if rff_best is None or s > rff_best[0]:
                rff_best = (s, sigma, rlam, R, phase)
        del F, Fv
    assert rff_best is not None
    rff_val, rff_sigma, rff_lam, R, phase = rff_best
    log(f"spacemap: rff sigma {rff_sigma:g} lambda {rff_lam:g} -> val median cos "
        f"{rff_val:.3f} (linear {linear_val:.3f}); shipping "
        f"{'rff' if rff_val > linear_val else 'linear'}")

    if rff_val > linear_val:
        F = _rff(xf, R, phase).astype(np.float64)
        w, b = _ridge_fit(F, yf, rff_lam)
        eval_mapped = _rff(x[eval_mask], R, phase).astype(np.float64) @ w + b
        extra = {"kind": "rff-ridge", "sigma": rff_sigma, "D": RFF_D}
        lam_out = rff_lam
        del F
    else:
        w, b = _ridge_fit(xf, yf, lam)
        eval_mapped = x[eval_mask] @ w + b
        extra = {"kind": "linear"}
        lam_out = lam
    eval_true = y[eval_mask]
    cos = _cosines(eval_mapped, eval_true)
    median = float(np.median(cos))
    deciles = [round(float(np.percentile(cos, q)), 4) for q in range(10, 100, 10)]
    quality: dict[str, Any] = {
        "pairs": int(x.shape[0]),
        "trainPairs": int(fit_mask.sum()),
        "evalPairs": int(eval_mask.sum()),
        "evalRecordings": len({r for r, m in zip(recordings, eval_mask) if m}),
        "split": "by recording, 80/20; every knob — penalties, sigma, and which map "
        "class ships — was chosen on a further 80/20 split of the fit side, never on "
        "these rows",
        "lambda": lam_out,
        "medianCosine": round(median, 4),
        "meanCosine": round(float(cos.mean()), 4),
        "deciles": deciles,
        "target": ACCEPT_MEDIAN_COSINE,
        "accepted": bool(median >= ACCEPT_MEDIAN_COSINE),
        "definition": (
            "cosine between the mapped 28-d descriptor and the true critic embedding, "
            "on syllables of recordings the map was not fitted on"
        ),
        **extra,
    }

    # The shipped weights see everything; the numbers above do not. Both facts matter.
    if extra["kind"] == "rff-ridge":
        F_all = _rff(x, R, phase).astype(np.float64)
        w_all, b_all = _ridge_fit(F_all, y, rff_lam)
        del F_all
        return RffMap(
            R=R, phase=phase, w=w_all, b=b_all, sigma=rff_sigma, lam=rff_lam,
            quality=quality, eval_mapped=eval_mapped, eval_true=eval_true,
        )
    w_all, b_all = _ridge_fit(x, y, lam)
    return SpaceMap(
        w=w_all, b=b_all, lam=lam, quality=quality,
        eval_mapped=eval_mapped, eval_true=eval_true,
    )
