"""The browser's bridge into the learned embedding space: a ridge map from 28-d to 32-d.

**Why this module exists.** Phase 2 of docs/09 moves the galaxy's projection, clustering
and centroids into the critic's 32-d embedding, because it is the measurably better
similarity space (§9.7/§9.8). But the browser cannot run the critic — no weights ship,
the assets are plain JSON/f32, and that is a hard constraint (§9.4) rather than a
packaging detail. What the browser *can* compute is the same 28-d window descriptor it
has always computed. So the live path needs a map from the space it lives in to the
space the galaxy now lives in, fitted offline and shipped as numbers.

A linear ridge is the honest choice of map, not an impoverished one. The two spaces are
two views of the same syllables, and the question is how much of the embedding is
*recoverable* from the descriptor; a nonlinear map would fit the recording conditions of
the training pairs (the very thing the descriptor and the embedding disagree least
about) and report a flattering number that does not survive a new microphone. Ridge has
one knob, and the knob is chosen on held-out *recordings*.

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
    log(
        "spacemap: lambda "
        + ", ".join(f"{l:g} -> median cos {s:.3f}" for s, l in sorted(scores, key=lambda t: t[1]))
        + f"; chose {lam:g}"
    )

    w, b = _ridge_fit(xf, yf, lam)
    eval_mapped = x[eval_mask] @ w + b
    eval_true = y[eval_mask]
    cos = _cosines(eval_mapped, eval_true)
    median = float(np.median(cos))
    deciles = [round(float(np.percentile(cos, q)), 4) for q in range(10, 100, 10)]
    quality: dict[str, Any] = {
        "pairs": int(x.shape[0]),
        "trainPairs": int(fit_mask.sum()),
        "evalPairs": int(eval_mask.sum()),
        "evalRecordings": len({r for r, m in zip(recordings, eval_mask) if m}),
        "split": "by recording, 80/20; the penalty was chosen on a further 80/20 split "
        "of the fit side, never on these rows",
        "lambda": lam,
        "medianCosine": round(median, 4),
        "meanCosine": round(float(cos.mean()), 4),
        "deciles": deciles,
        "target": ACCEPT_MEDIAN_COSINE,
        "accepted": bool(median >= ACCEPT_MEDIAN_COSINE),
        "definition": (
            "cosine between the mapped 28-d descriptor and the true critic embedding, "
            "on syllables of recordings the map was not fitted on"
        ),
    }

    # The shipped weights see everything; the numbers above do not. Both facts matter.
    w_all, b_all = _ridge_fit(x, y, lam)
    return SpaceMap(
        w=w_all, b=b_all, lam=lam, quality=quality,
        eval_mapped=eval_mapped, eval_true=eval_true,
    )
