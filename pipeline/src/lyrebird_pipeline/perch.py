"""Perch 2.0 as the second-opinion pseudo-labeller of docs/13 §A1.

**What this is.** The novelty scorer (critic.py, docs/09 §9.2b) can say a syllable is
unlike every known type; it cannot say what the syllable *is*. Perch 2.0 (Google,
Apache 2.0, ~14.8k species classes trained on xeno-canto + iNaturalist +
Tierstimmenarchiv + FSD50K) is the external second opinion: run it over the cached
audio of each flagged syllable and record its top guesses.

**What it is not — the discipline that makes this file safe.** Every label written
here is *metadata*: `{HONESTY_LABEL}`. Nothing in learn.py reads `perch-labels.jsonl`,
and nothing may — the moment a Perch inference becomes a type's identity, model error
has been laundered into the canonical inventory and the pre-registered-metric
discipline dies (docs/13 §A1, §c "Pseudo-labels as ground truth"). A flagged syllable
stays `unlabelled` (§8.5); Perch only narrows which documented species it resembles.

**Why ONNX and not the official SavedModel.** The official artifact is a TF SavedModel
on Kaggle Models, which needs full TensorFlow (~600 MB of wheel) to run. The
`justinchuby/Perch-onnx` community port on Hugging Face is the same network converted
to ONNX (verified against Perch-Hoplite's `perch_v2_onnx` preset: same 32 kHz / 5 s
frontend, same 0.25 peak normalisation, same 0.97/-10.0 logit calibration), and runs
under `onnxruntime` alone — ~50 ms per 5 s window on a CPU. One new dependency instead
of a TensorFlow installation, and inference stays offline and far from the browser, as
docs/13 §c requires ("BirdNET/Perch in the browser ... server-side or nothing").

**Where the audio comes from.** The store keeps no audio by design. The only audio on
disk is the owner-sanctioned iNat cache (`pipeline/out/audio-cache/`, INAT* recording
ids, deleted when the training phase ends — AGENTS.md). Syllables from any other
source (xeno-canto harvests above all) were deleted after description and cannot be
labelled here; the command counts and reports them as skipped, never silently.

`onnxruntime` is imported at the top of this module and nowhere else in the pipeline;
`kagglehub`/`huggingface_hub` are imported lazily inside `ensure_model`, so a cached
model needs no hub package. Callers import `perch` inside a function and degrade with
a clear message, exactly like the critic's torch (pyproject's `perch` extra).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import onnxruntime as ort

from . import harvest

# --- the model, and the one honest sentence every label carries --------------------

#: The exact text of docs/13 §A1's UI honesty label. It ships in the JSONL `_meta`
#: record so no consumer can claim the provenance was unclear.
HONESTY_LABEL = "closest documented species (Perch 2.0 inference, unverified)"

PERCH_SAMPLE_RATE = 32000
PERCH_WINDOW_SECONDS = 5.0
#: Perch 2.0's embedding width. (Perch 1.0's was 1280; the 1536 figure is measured off
#: the loaded ONNX graph and matches the Perch 2.0 paper's table.)
EMBED_DIM = 1536
#: Per-window peak normalisation and logit calibration of Perch-Hoplite's
#: `perch_v2_onnx` preset — the reference inference recipe for this exact model file.
TARGET_PEAK = 0.25
LOGIT_SLOPE = 0.97
LOGIT_INTERCEPT = -10.0

#: Where the weights and class list come from. The ONNX file is a community port (see
#: the module docstring); the class list is Google's own, from the Kaggle model
#: package. Both download anonymously — the Kaggle model is public, not gated.
HF_REPO = "justinchuby/Perch-onnx"
HF_FILE = "perch_v2.onnx"
KAGGLE_LABELS_SLUG = "google/bird-vocalization-classifier/tensorFlow2/perch_v2/2"
KAGGLE_LABELS_PATH = "assets/labels.csv"


@dataclass
class PerchModel:
    """A loaded Perch 2.0 ONNX session plus its 14 795-class species list."""

    session: Any  # ort.InferenceSession
    labels: list[str]

    def label(self, windows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """5-s float32 windows at 32 kHz -> (scores, embeddings).

        Scores are `sigmoid(0.97 * logit - 10.0)`, the calibration Perch-Hoplite ships
        for this model; they rank classes within a window and are not probabilities of
        presence in any calibrated sense — another reason the output is metadata.
        """
        x = np.asarray(windows, dtype=np.float32)
        peak = np.maximum(np.abs(x).max(axis=1, keepdims=True), 1e-8)
        x = x / peak * TARGET_PEAK
        logits, emb = self.session.run(["label", "embedding"], {"inputs": x})
        logits = logits.reshape(x.shape[0], -1) * LOGIT_SLOPE + LOGIT_INTERCEPT
        scores = 1.0 / (1.0 + np.exp(-np.clip(logits, -60.0, 60.0)))
        return scores.astype(np.float32), emb.reshape(x.shape[0], -1).astype(np.float32)


def ensure_model(model_dir: Path) -> PerchModel:
    """Load Perch 2.0, downloading the weights and class list on first use.

    Both hub caches are pointed inside `model_dir` (unless the environment already
    redirects them) so the 409 MB download lands under the gitignored `pipeline/out/`
    with the rest of the local-only training artifacts, not in a home-directory cache.
    """
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("KAGGLEHUB_CACHE", str(model_dir / "kagglehub"))
    os.environ.setdefault("HF_HOME", str(model_dir / "hf"))

    try:
        import kagglehub
    except ImportError:
        raise ImportError(
            "kagglehub is needed to fetch Perch's class list once. "
            "`uv sync --extra perch` and try again."
        ) from None
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise ImportError(
            "huggingface_hub is needed to fetch the Perch ONNX weights once. "
            "`uv sync --extra perch` and try again."
        ) from None

    onnx_path = hf_hub_download(HF_REPO, HF_FILE)
    csv_path = kagglehub.model_download(KAGGLE_LABELS_SLUG, path=KAGGLE_LABELS_PATH)
    lines = Path(csv_path).read_text(encoding="utf-8").splitlines()
    # First line is the class-list namespace ("inat2024_fsd50k"), not a species.
    labels = [line.strip() for line in lines[1:] if line.strip()]
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    n_classes = next(o.shape[-1] for o in session.get_outputs() if o.name == "label")
    if len(labels) != n_classes:
        raise RuntimeError(
            f"class list has {len(labels)} entries but the model emits {n_classes} "
            "logits — refusing to attach the wrong names to the right numbers"
        )
    return PerchModel(session=session, labels=labels)


# --- target selection: which syllables get a second opinion -------------------------


def load_novelty_centroids(novelty_path: Path) -> tuple[np.ndarray, float]:
    """`(centroids, threshold)` from `<critic>-novelty.json`, without importing torch.

    This is `critic.Novelty`'s file read directly — importing `critic` here would make
    a labelling run need torch for no reason (the embeddings it would compute are
    already in `<store>/embeddings.f32`).
    """
    blob = json.loads(Path(novelty_path).read_text(encoding="utf-8"))
    centroids = np.asarray(blob["centroids"], dtype=np.float64)
    return centroids, float(blob["threshold"])


def novelty_mask(
    store: harvest.HarvestStore,
    embeddings_path: Path,
    centroids: np.ndarray,
    threshold: float,
    chunk: int = 20000,
) -> np.ndarray:
    """Per-syllable novelty verdict: the stored flag where it exists, the scorer's
    verdict recomputed from `<store>/embeddings.f32` everywhere else.

    Why recompute: the `novel` flag is set only by the control surface at ingest time
    (server.py), so bulk-harvested stores — every current one — carry `False` meaning
    *never measured*, not *measured, not novel*. The recomputation is bit-for-bit the
    measurement the ingest path makes (`Novelty.is_novel` on the same embeddings with
    the same centroids and threshold), so it invents no new discipline; it just runs
    the existing one over rows that were harvested before the scorer existed.
    """
    n = len(store.syllables)
    emb = np.fromfile(embeddings_path, dtype="<f4")
    if emb.size != n * 32:
        raise RuntimeError(
            f"{embeddings_path} holds {emb.size // 32} rows but the store holds {n} "
            "syllables — re-run `critic embed` against this store"
        )
    emb = emb.reshape(n, 32).astype(np.float64)
    z = centroids / np.linalg.norm(centroids, axis=1, keepdims=True)
    mask = np.zeros(n, dtype=bool)
    for s in range(0, n, chunk):
        e = emb[s : s + chunk]
        norms = np.linalg.norm(e, axis=1, keepdims=True)
        ok = norms[:, 0] > 0
        e = e / np.maximum(norms, 1e-12)
        # Zero-norm (unembedded) rows get distance -inf: unmeasured is not novel.
        d = np.full(e.shape[0], -np.inf)
        d[ok] = 1.0 - (e[ok] @ z.T).max(axis=1)
        mask[s : s + chunk] = d > threshold
    return mask


def window_at(x: np.ndarray, start: float, dur: float, rate: int) -> np.ndarray:
    """The 5-s Perch window centred on a syllable, clamped to the recording, zero-padded."""
    win = int(PERCH_WINDOW_SECONDS * rate)
    if x.size <= win:
        return np.pad(x, (0, win - x.size))
    centre = int((start + dur / 2.0) * rate)
    w0 = int(min(max(centre - win // 2, 0), x.size - win))
    return x[w0 : w0 + win]


# --- the labelling pass --------------------------------------------------------------


def label_novel(
    store: harvest.HarvestStore,
    audio_cache: Path,
    out_path: Path,
    model: PerchModel,
    targets: np.ndarray,
    limit: int | None = None,
    batch: int = 32,
    keep_embeddings: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, int]:
    """Run Perch over every target syllable whose audio still exists; write JSONL.

    The store is only ever read. Output rows are
    `{recordingId, order, top3: [{species, score}], embedding?}`, preceded by one
    `_meta` record carrying the provenance and the honesty label. Returns counts for
    the caller's log line.
    """
    audio_cache = Path(audio_cache)
    observations = store.syllables
    by_recording: dict[str, list[int]] = {}
    skipped_no_audio = 0
    skipped_missing_wav = 0
    for i, o in enumerate(observations):
        if not targets[i]:
            continue
        if not o.recording_id.startswith("INAT"):
            # xeno-canto (and every other source) is decode -> describe -> delete;
            # the audio is gone by design, and no Perch run can bring it back.
            skipped_no_audio += 1
            continue
        if not (audio_cache / f"{o.recording_id}.wav").exists():
            skipped_missing_wav += 1
            continue
        by_recording.setdefault(o.recording_id, []).append(i)

    wanted = sum(len(v) for v in by_recording.values())
    if limit is not None:
        wanted = min(wanted, limit)
    log(f"label-novel: {int(targets.sum())} target syllables; "
        f"{skipped_no_audio} unlabelable (non-iNat source, audio deleted by design), "
        f"{skipped_missing_wav} unlabelable (iNat recording not in {audio_cache}), "
        f"labelling {wanted}")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "_meta": {
            "model": f"{HF_REPO}/{HF_FILE} (community ONNX port of Kaggle "
                     f"{KAGGLE_LABELS_SLUG})",
            "classes": len(model.labels),
            "embeddingDim": EMBED_DIM,
            "windowSeconds": PERCH_WINDOW_SECONDS,
            "sampleRate": PERCH_SAMPLE_RATE,
            "score": f"sigmoid({LOGIT_SLOPE} * logit + {LOGIT_INTERCEPT})",
            "honesty": HONESTY_LABEL,
            "discipline": "metadata only — never typing ground truth; learn.py does "
                          "not read this file (docs/13 section A1)",
            "targets": int(targets.sum()),
            "skippedNoAudio": skipped_no_audio,
            "skippedMissingWav": skipped_missing_wav,
        }
    }
    counts = {"labelled": 0, "recordings": 0}
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta) + "\n")
        for recording_id, idxs in sorted(by_recording.items()):
            if limit is not None and counts["labelled"] >= limit:
                break
            try:
                x, rate = harvest.decode(audio_cache / f"{recording_id}.wav",
                                         PERCH_SAMPLE_RATE)
            except Exception as exc:
                log(f"  skip {recording_id}: {exc}")
                continue
            counts["recordings"] += 1
            if limit is not None:
                idxs = idxs[: max(0, limit - counts["labelled"])]
            windows = np.stack([
                window_at(x, observations[i].start, observations[i].dur, rate)
                for i in idxs
            ])
            for s in range(0, len(idxs), batch):
                scores, emb = model.label(windows[s : s + batch])
                for j, i in enumerate(idxs[s : s + batch]):
                    top = scores[j].argsort()[::-1][:3]
                    row: dict[str, Any] = {
                        "recordingId": recording_id,
                        "order": observations[i].order,
                        "top3": [
                            {"species": model.labels[k],
                             "score": round(float(scores[j][k]), 4)}
                            for k in top
                        ],
                    }
                    if keep_embeddings:
                        row["embedding"] = [round(float(v), 4) for v in emb[j]]
                    fh.write(json.dumps(row) + "\n")
                    counts["labelled"] += 1
            if counts["recordings"] % 200 == 0:
                log(f"  {counts['labelled']}/{wanted} labelled "
                    f"({counts['recordings']} recordings)")
    log(f"wrote {out_path}: {counts['labelled']} labels over "
        f"{counts['recordings']} recordings — every one is \"{HONESTY_LABEL}\"")
    return counts
