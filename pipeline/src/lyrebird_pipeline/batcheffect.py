"""W1 of docs/23 — the recorder confound treated as a batch effect.

**The failure this attacks.** The strongest relation in the critic's embedding is not the
bird. Recordist kNN lift is +0.488 against species' +0.196 (docs/14 §14.4). Two attempts
to remove it during training failed and are recorded: the recordist-adversarial head
trades roughly one point of species accuracy for one of recordist invariance (docs/17
§17.3), and a species-factored adversarial target cannot reach a confound that lives
*between* species (§17.5). docs/17 closed the loss-engineering road at both ends and
concluded that invariance is a data action.

**Why this module exists anyway.** The problem has a name in another field. Genomics
calls it a batch effect — technical variation from the instrument, the run and the
operator, sitting on top of the biological signal — and has spent fifteen years on it.
None of that toolkit has ever been run here, and its strongest members share the one
property that makes them testable in an afternoon: they are **post-hoc**. They correct
an embedding that already exists. No retraining, no new data, no new loss.

Three corrections, cheapest first, so the answer is attributable:

- **`centre`** — subtract each batch's mean. ComBat's location term without its scale
  term, and the simplest thing that could possibly work. numpy only.
- **`whiten`** — centre and scale each batch to unit variance per dimension. ComBat's
  location-and-scale form, still linear, still numpy only.
- **`harmony`** — iterative soft clustering that removes batch structure while
  preserving cluster structure (harmonypy, the `analysis` extra). Imported lazily; a
  machine without it still gets the first two arms and a logged reason.

**The gate, stated in docs/23 before any of this ran.** Recordist lift must fall by at
least half **and** species lift must not fall at all. A correction that buys invariance
by spending species structure is §17.3's trade under a new name, and fails. Both numbers
come from `geometry.measure` against its own permutation null, blocked by recording, so
they are directly comparable with every other lift this project has published.

**The batch label is a choice, and it is measured rather than assumed.** `recordist` is
the confound docs/14 named. `recording` is finer, and it is the unit `geometry.py`
already blocks on — correcting at that level is close to conceding that every recording
is its own instrument. Both are run, because the difference between them says whether
the confound is the person or the session.

Nothing here ships to the app. This is a measurement of the embedding, and its result is
a decision about whether the docs/17 road is closed or merely was not tried with the
right tool.
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from typing import Any, Sequence

import numpy as np


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


#: Fewest rows a batch needs before it is corrected at all. A batch of one has no
#: within-batch variation to estimate, and subtracting its own mean would move it to the
#: origin — which is not a correction, it is a deletion.
MIN_BATCH = 3


def _groups(labels: Sequence[str]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for i, label in enumerate(labels):
        out[label].append(i)
    return out


def centre(z: np.ndarray, batches: Sequence[str]) -> np.ndarray:
    """Subtract each batch's mean: the location term alone.

    The grand mean is added back, so the corrected cloud sits where the original did.
    Without that every batch lands on the origin and the space's scale changes under the
    correction, which would move the cosine distances the battery is about to measure.
    """
    out = z.astype(np.float64, copy=True)
    grand = out.mean(axis=0)
    for _, rows in _groups(batches).items():
        if len(rows) >= MIN_BATCH:
            out[rows] += grand - out[rows].mean(axis=0)
    return out


def whiten(z: np.ndarray, batches: Sequence[str]) -> np.ndarray:
    """Centre each batch and scale it to the grand standard deviation per dimension.

    ComBat's location-and-scale form, without its empirical-Bayes shrinkage. The floor on
    the divisor keeps a batch that is constant in one dimension from exploding it.
    """
    out = z.astype(np.float64, copy=True)
    grand_mean = out.mean(axis=0)
    grand_std = out.std(axis=0)
    for _, rows in _groups(batches).items():
        if len(rows) < MIN_BATCH:
            continue
        block = out[rows]
        std = np.maximum(block.std(axis=0), 1.0e-6)
        out[rows] = (block - block.mean(axis=0)) / std * grand_std + grand_mean
    return out


def harmony(
    z: np.ndarray, batches: Sequence[str], seed: int = 0, max_iter: int = 10
) -> np.ndarray | None:
    """harmonypy's correction, or None with a logged reason when it is unavailable.

    Lazy import, in the pattern of every optional component here: a machine without the
    `analysis` extra still gets `centre` and `whiten`, and the report says which arms
    it managed to run.
    """
    try:
        import harmonypy
        import pandas as pd
    except ImportError as exc:
        log(f"harmony skipped: {exc}. `uv sync --extra analysis` to run this arm.")
        return None
    meta = pd.DataFrame({"batch": list(batches)})
    result = harmonypy.run_harmony(
        z.astype(np.float64), meta, ["batch"], max_iter_harmony=max_iter, random_state=seed
    )
    # harmonypy has returned the corrected matrix under two names across versions, and
    # transposed. Take whichever exists and orient it by the row count, so a version bump
    # cannot silently hand back a matrix of the wrong shape.
    corrected = getattr(result, "Z_corr", None)
    if corrected is None:
        corrected = getattr(result, "result", lambda: None)()
    corrected = np.asarray(corrected, dtype=np.float64)
    if corrected.shape[0] != z.shape[0]:
        corrected = corrected.T
    if corrected.shape != z.shape:
        log(f"harmony returned {corrected.shape} for a {z.shape} input — skipping")
        return None
    return corrected


def evaluate(
    z: np.ndarray,
    species: Sequence[str],
    recordist: Sequence[str],
    recording: Sequence[str],
    seed: int = 0,
) -> dict[str, Any]:
    """Every correction against every batch definition, scored by the shipped battery."""
    from . import geometry

    def score(matrix: np.ndarray, tag: str) -> dict[str, Any]:
        row: dict[str, Any] = {"arm": tag}
        for name, labels in (("species", species), ("recordist", recordist)):
            found = geometry.measure(
                matrix, list(labels), name, tag, "cosine", seed=seed,
                blocks=list(recording),
            )
            row[name] = None if found is None else round(found.knn - found.knn_null, 4)
        log(f"  {tag:34} species {row['species']}  recordist {row['recordist']}")
        return row

    t0 = time.time()
    arms = [score(z, "baseline")]
    base = arms[0]
    for batch_name, batches in (("recordist", recordist), ("recording", recording)):
        arms.append(score(centre(z, batches), f"centre by {batch_name}"))
        arms.append(score(whiten(z, batches), f"whiten by {batch_name}"))
        corrected = harmony(z, batches, seed=seed)
        if corrected is not None:
            arms.append(score(corrected, f"harmony by {batch_name}"))

    def verdict(row: dict[str, Any]) -> dict[str, Any]:
        if row["recordist"] is None or base["recordist"] is None:
            return {"passes": None}
        halved = row["recordist"] <= base["recordist"] * 0.5
        kept = (
            row["species"] is not None
            and base["species"] is not None
            and row["species"] >= base["species"]
        )
        return {"recordistHalved": halved, "speciesHeld": kept, "passes": halved and kept}

    return {
        "rows": len(z),
        "dims": int(z.shape[1]),
        "species": len(set(species)),
        "recordists": len(set(recordist)),
        "recordings": len(set(recording)),
        "arms": [{**row, **verdict(row)} for row in arms],
        "gate": (
            "recordist lift falls by at least half AND species lift does not fall "
            "(docs/23 §23.1, stated before the run)"
        ),
        "seconds": round(time.time() - t0, 1),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "W1 the recorder confound as a batch effect (docs/23 §23.1)",
        f"{report['rows']} rows x {report['dims']}-d over {report['species']} species, "
        f"{report['recordists']} recordists, {report['recordings']} recordings",
        "",
        f"  {'arm':34} {'species':>8} {'recordist':>10}  verdict",
    ]
    for row in report["arms"]:
        mark = (
            "" if row["arm"] == "baseline"
            else "  PASSES" if row.get("passes")
            else "  fails"
        )
        lines.append(
            f"  {row['arm']:34} {str(row['species']):>8} {str(row['recordist']):>10}{mark}"
        )
    lines += ["", f"gate: {report['gate']}"]
    return "\n".join(lines)


def self_test(verbose: bool = True) -> None:
    """A planted batch effect must be removable, and a planted signal must survive.

    Two classes in 8-d, three batches, each batch given its own offset far larger than
    the class separation — the shape of the docs/14 finding, where the confound is
    stronger than the signal. Centring must collapse the batch means and leave the class
    means apart. A correction that also collapses the classes is the failure this test
    exists to catch.
    """
    rng = np.random.default_rng(0)
    n, d = 600, 8
    cls = rng.integers(0, 2, size=n)
    batch = rng.integers(0, 3, size=n)
    signal = np.zeros((n, d))
    signal[cls == 1, 0] = 1.0
    offsets = rng.normal(size=(3, d)) * 5.0
    z = signal + offsets[batch] + rng.normal(scale=0.1, size=(n, d))
    labels = [f"b{b}" for b in batch]

    def spread(matrix: np.ndarray, keys: np.ndarray) -> float:
        means = np.stack([matrix[keys == k].mean(axis=0) for k in np.unique(keys)])
        return float(np.linalg.norm(means - means.mean(axis=0), axis=1).mean())

    before_batch, before_class = spread(z, batch), spread(z, cls)
    fixed = centre(z, labels)
    after_batch, after_class = spread(fixed, batch), spread(fixed, cls)
    assert after_batch < before_batch * 0.05, (
        f"batch offsets survived centring: {before_batch:.3f} -> {after_batch:.3f}"
    )
    assert after_class > before_class * 0.5, (
        f"centring destroyed the class signal: {before_class:.3f} -> {after_class:.3f}"
    )
    # Whitening must not be worse on either count, or the scale term is doing harm.
    w = whiten(z, labels)
    assert spread(w, batch) < before_batch * 0.05
    assert spread(w, cls) > before_class * 0.3
    # A batch too small to estimate is left alone rather than moved to the origin.
    tiny = np.ones((2, d))
    kept = centre(np.vstack([z, tiny]), labels + ["solo", "solo"])
    assert np.allclose(kept[-2:], tiny), "a 2-row batch must not be 'corrected'"

    if verbose:
        print(
            f"batcheffect self-test ok: batch spread {before_batch:.2f} -> "
            f"{after_batch:.3f}, class spread {before_class:.2f} -> {after_class:.2f}"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
