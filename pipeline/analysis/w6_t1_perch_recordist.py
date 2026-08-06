"""W6 T1 — an external, archive-scale embedding against the recordist confound.

§23.6 names BirdNET. This runs T1 with **Perch 2.0**, which is already ported here
(`perch.py`, ONNX, 1536-d, 5 s at 32 kHz) and carries the two properties T1 turns on: it
was trained on the same archives at roughly the same scale, and it has **no realism term
anywhere in it** — it was never asked to tell our resynthesis from a bird. If Perch shows
the recordist structure our critic shows, the confound is in the archives rather than in
our loss, which §23.6 calls the valuable negative, and it arrives without a new model
port. BirdNET stays worth doing for the occurrence prior and as a third opinion.

PRE-REGISTERED, before the run:

  T1  recordist kNN lift in the Perch space must sit **at least 30 % below** the critic
      space's, measured on the SAME recordings with the SAME estimator, while species
      lift does not fall. -30 % is §17.3's own bar, so the training road and the external
      road are judged by one rule.
  T3  species lift, Perch against critic, on the same rows.
  Source lift is NOT asked here and the reason is stated rather than skipped: every
      cached recording is real field audio, so this population has no synthetic side.

POPULATION. The 6 453 cached iNat recordings, every one of which carries a recordist
(1 836 distinct). Selection, fixed before the run: recordists with >= 8 cached
recordings, at most 20 recordings each (seeded sample), to a cap of 2 000 recordings —
so one prolific recordist cannot carry the result.

REPRESENTATION. One point per recording, which is what §23.6 says W1 wants as its batch
representation, and which has a property the syllable-level test had to block for: two
points from the same recording cannot exist, so same-recording leakage is impossible by
construction rather than by exclusion.
  - Perch: mean of the 5 s window embeddings over the first WINDOW_BUDGET windows.
  - critic: mean of that recording's syllable embeddings from `embeddings.f32`.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/sha5b/Documents/GitHub/Lyrebird/pipeline/src")

from lyrebird_pipeline import geometry, perch  # noqa: E402
from lyrebird_pipeline.harvest import HarvestStore  # noqa: E402

STORE = Path("/home/sha5b/Documents/GitHub/Lyrebird/pipeline/out/harvest-gan")
CACHE = Path("/home/sha5b/Documents/GitHub/Lyrebird/pipeline/out/audio-cache")
MODEL_DIR = Path("/home/sha5b/Documents/GitHub/Lyrebird/pipeline/out/perch")
OUT = Path(__file__).resolve().parent / "w6_t1_perch_recordist.json"
MIN_PER_RECORDIST = 8
MAX_PER_RECORDIST = 20
RECORDING_CAP = 2000
WINDOW_BUDGET = 6  # 30 s per recording
SEED = 0


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def select(store: HarvestStore) -> list[str]:
    cached = {p.stem for p in CACHE.glob("*.wav")}
    by_recordist: dict[str, list[str]] = defaultdict(list)
    for rid, meta in sorted(store.recordings.items()):
        if rid in cached and meta.get("recordist"):
            by_recordist[meta["recordist"]].append(rid)
    rng = np.random.default_rng(SEED)
    chosen: list[str] = []
    for who in sorted(by_recordist, key=lambda w: (-len(by_recordist[w]), w)):
        recs = by_recordist[who]
        if len(recs) < MIN_PER_RECORDIST:
            continue
        take = recs if len(recs) <= MAX_PER_RECORDIST else [
            recs[i] for i in rng.permutation(len(recs))[:MAX_PER_RECORDIST]
        ]
        chosen.extend(sorted(take))
        if len(chosen) >= RECORDING_CAP:
            break
    return sorted(chosen[:RECORDING_CAP])


def load_model() -> perch.PerchModel:
    """The shipped Perch session without the class list.

    `perch.ensure_model` also fetches the 14 795-name class list from Kaggle, which needs
    Kaggle credentials. T1 reads the embedding and never a label, so the names are not
    just unused here — attaching them would be the one thing §23.6 says not to do. The
    weights, the peak normalisation and the ONNX call are the shipped ones
    (`PerchModel.label`); only the label list is absent.
    """
    import os

    import onnxruntime as ort
    from huggingface_hub import hf_hub_download

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(MODEL_DIR / "hf"))
    onnx_path = hf_hub_download(perch.HF_REPO, perch.HF_FILE)
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    return perch.PerchModel(session=session, labels=[])


def perch_embed(model: perch.PerchModel, path: Path) -> np.ndarray | None:
    import soundfile as sf

    audio, rate = sf.read(str(path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != perch.PERCH_SAMPLE_RATE:
        # Linear resample: the model wants 32 kHz and the cache is whatever the source
        # was. This is the same job `window_at` does downstream of the harvester.
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


def critic_embed(store: HarvestStore, wanted: set[str]) -> dict[str, np.ndarray]:
    raw = np.fromfile(STORE / "embeddings.f32", dtype="<f4")
    n = len(store.syllables)
    if raw.size % n:
        raise RuntimeError(f"embeddings.f32 holds {raw.size} floats for {n} syllables")
    emb = raw.reshape(n, -1).astype(np.float64)
    sums: dict[str, np.ndarray] = {}
    counts: Counter[str] = Counter()
    for row, o in zip(emb, store.syllables):
        rid = o.recording_id
        if rid not in wanted or not np.all(np.isfinite(row)) or not row.any():
            continue
        sums[rid] = sums.get(rid, 0.0) + row
        counts[rid] += 1
    return {rid: v / counts[rid] for rid, v in sums.items()}


def main() -> None:
    t0 = time.time()
    store = HarvestStore(STORE)
    store.load()
    chosen = select(store)
    log(f"selected {len(chosen)} recordings from "
        f"{len({store.recordings[r]['recordist'] for r in chosen})} recordists, "
        f"{len({store.recordings[r]['speciesId'] for r in chosen})} species")

    critic = critic_embed(store, set(chosen))
    log(f"critic: per-recording means for {len(critic)} of them")

    model = load_model()
    rows: list[str] = []
    p_vecs: list[np.ndarray] = []
    for i, rid in enumerate(chosen):
        if rid not in critic:
            continue
        try:
            v = perch_embed(model, CACHE / f"{rid}.wav")
        except Exception as exc:  # a bad wav is a skip with a count, never a crash
            log(f"  {rid}: {exc}")
            continue
        if v is None:
            continue
        rows.append(rid)
        p_vecs.append(v)
        if (i + 1) % 200 == 0:
            log(f"  embedded {len(rows)}/{i + 1} in {time.time() - t0:.0f}s")

    perch_x = np.stack(p_vecs)
    critic_x = np.stack([critic[r] for r in rows])
    species = [store.recordings[r]["speciesId"] for r in rows]
    recordist = [store.recordings[r]["recordist"] for r in rows]
    log(f"{len(rows)} recordings embedded both ways in {time.time() - t0:.0f}s")

    report: dict[str, object] = {
        "recordings": len(rows),
        "species": len(set(species)),
        "recordists": len(set(recordist)),
        "windowBudget": WINDOW_BUDGET,
        "arms": [],
    }
    for tag, matrix in (("critic 32-d", critic_x), ("perch 1536-d", perch_x)):
        row: dict[str, object] = {"space": tag, "dims": int(matrix.shape[1])}
        for name, labels in (("species", species), ("recordist", recordist)):
            # No blocks: one point per recording, so a same-recording pair cannot exist.
            found = geometry.measure(matrix, list(labels), name, tag, "cosine", seed=SEED)
            row[name] = None if found is None else round(found.knn - found.knn_null, 4)
            row[f"{name}Coverage"] = None if found is None else round(found.coverage, 4)
        report["arms"].append(row)
        log(f"  {tag:14} species {row['species']}  recordist {row['recordist']}")

    critic_row, perch_row = report["arms"]
    passes = None
    if None not in (critic_row["recordist"], perch_row["recordist"],
                    critic_row["species"], perch_row["species"]):
        passes = bool(
            perch_row["recordist"] <= critic_row["recordist"] * 0.7
            and perch_row["species"] >= critic_row["species"]
        )
    report["gate"] = (
        "T1: recordist lift at least 30 % below the critic's on the same recordings, "
        "species lift not lower (docs/23 §23.6, stated before the run)"
    )
    report["passes"] = passes
    report["seconds"] = round(time.time() - t0, 1)
    OUT.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
