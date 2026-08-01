"""W6 T1/T3 with BirdNET — the second external opinion, independent of Perch.

§23.6 named BirdNET and §23.6.1 answered T1 with Perch instead, because Perch was already
ported. This runs the same two tests with BirdNET, which matters for one reason: Perch and
BirdNET are different architectures trained by different groups, so agreement between them
is evidence about **the archives**, and disagreement would be evidence about *a model*. A
single external opinion could not tell those apart.

Three things §23.6 assumed that turned out to be wrong, all in our favour:

  - "BirdNET ships TFLite and this repo carries no TensorFlow, so it is tflite-runtime or
    an ONNX export." There is an ONNX export, by the same author as the Perch port this
    repo already trusts (`justinchuby/BirdNET-onnx`), so BirdNET needs **no new runtime at
    all** — the `perch` extra's `onnxruntime` runs it.
  - "a 320-d embedding taken from the second-to-last layer". The backbone export
    (`biodiversica/BirdNET-onnx-backbone`, derived from the same base) outputs **1024-d**.
  - Size: 52 MB classifier + 25 MB backbone against Perch's 391 MB.

PRE-REGISTERED, before the run, and deliberately the same gates §23.6.1/§23.6.2 were read
against so the three spaces are comparable:

  T1  recordist kNN lift in the BirdNET space, against the critic's on the same rows.
      Gate: at least 30 % below, with species lift not lower.
  T3  species kNN lift (the pair population), BirdNET against the critic.
  Reported beside both: whether recordist lift still outranks species lift, which is the
  statement that held in every draw of §23.6.1-2 and is the one this run can refute.

The two populations, the per-recording representation, the estimator and the splits are
`w6_t1_perch_recordist.py` and `w6_t3_perch_species.py` unchanged — only the embedder
differs, which is the point.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/sha5b/Documents/GitHub/Birdy/pipeline/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from birdy_pipeline import geometry  # noqa: E402
from birdy_pipeline.harvest import HarvestStore  # noqa: E402
from w6_t1_perch_recordist import CACHE, SEED, STORE, critic_embed, log  # noqa: E402
from w6_t1_perch_recordist import select as select_recordist  # noqa: E402
from w6_t3_perch_species import select as select_species  # noqa: E402

#: BirdNET V2.4 is 3 s at 48 kHz, against Perch's 5 s at 32 kHz.
BIRDNET_RATE = 48000
BIRDNET_WINDOW = 144000
#: The same 30 s of audio per recording the Perch runs used, so the two are comparable —
#: ten 3 s windows rather than six 5 s ones.
WINDOW_BUDGET = 10
HF_BACKBONE = ("biodiversica/BirdNET-onnx-backbone", "model_backbone.onnx")
OUT = Path(__file__).resolve().parent / "w6_birdnet_arms.json"


def load_backbone():
    """The BirdNET feature extractor: the classifier with its head removed.

    The labels are not fetched and not used. docs/23 §23.6 is explicit that an external
    model's species names are metadata and never typing ground truth, and this test reads
    geometry only.
    """
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(*HF_BACKBONE)
    return ort.InferenceSession(path, providers=["CPUExecutionProvider"])


def birdnet_embed(session, path: Path) -> np.ndarray | None:
    import soundfile as sf

    audio, rate = sf.read(str(path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != BIRDNET_RATE:
        n = int(round(len(audio) * BIRDNET_RATE / rate))
        if n < 2:
            return None
        audio = np.interp(
            np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio
        ).astype(np.float32)
    if len(audio) < BIRDNET_WINDOW:
        audio = np.pad(audio, (0, BIRDNET_WINDOW - len(audio)))
    starts = list(range(0, max(1, len(audio) - BIRDNET_WINDOW + 1), BIRDNET_WINDOW))
    batch = np.stack(
        [audio[s : s + BIRDNET_WINDOW] for s in starts[:WINDOW_BUDGET]]
    ).astype(np.float32)
    emb = session.run(None, {session.get_inputs()[0].name: batch})[0]
    return np.asarray(emb, dtype=np.float64).mean(axis=0)


def run(store: HarvestStore, chosen: list[str], name: str, species_min_group: int) -> dict:
    t0 = time.time()
    critic = critic_embed(store, set(chosen))
    session = load_backbone()
    rows: list[str] = []
    vecs: list[np.ndarray] = []
    for i, rid in enumerate(chosen):
        if rid not in critic:
            continue
        try:
            v = birdnet_embed(session, CACHE / f"{rid}.wav")
        except Exception as exc:
            log(f"  {rid}: {exc}")
            continue
        if v is None:
            continue
        rows.append(rid)
        vecs.append(v)
        if (i + 1) % 400 == 0:
            log(f"  {name}: embedded {len(rows)}/{i + 1} in {time.time() - t0:.0f}s")

    birdnet_x = np.stack(vecs)
    critic_x = np.stack([critic[r] for r in rows])
    species = [store.recordings[r]["speciesId"] for r in rows]
    recordist = [store.recordings[r]["recordist"] for r in rows]
    log(f"{name}: {len(rows)} recordings embedded both ways in {time.time() - t0:.0f}s")

    arms = []
    for tag, matrix in (("critic 32-d", critic_x), ("birdnet 1024-d", birdnet_x)):
        row: dict = {"space": tag, "dims": int(matrix.shape[1])}
        for label_name, labels in (("species", species), ("recordist", recordist)):
            found = geometry.measure(
                matrix, list(labels), label_name, tag, "cosine", seed=SEED,
                min_group=species_min_group if label_name == "species" else geometry.MIN_GROUP,
            )
            row[label_name] = None if found is None else round(found.knn - found.knn_null, 4)
            row[f"{label_name}Coverage"] = None if found is None else round(found.coverage, 4)
        arms.append(row)
        log(f"  {tag:16} species {row['species']} (cov {row['speciesCoverage']})  "
            f"recordist {row['recordist']} (cov {row['recordistCoverage']})")
    return {
        "population": name,
        "recordings": len(rows),
        "species": len(set(species)),
        "recordists": len(set(recordist)),
        "arms": arms,
        "seconds": round(time.time() - t0, 1),
    }


def main() -> None:
    store = HarvestStore(STORE)
    store.load()
    report = {"windowBudget": WINDOW_BUDGET, "runs": []}

    chosen = select_recordist(store)
    log(f"T1 population: {len(chosen)} recordings, "
        f"{len({store.recordings[r]['recordist'] for r in chosen})} recordists")
    report["runs"].append(run(store, chosen, "T1 (recordist-stratified)", geometry.MIN_GROUP))

    chosen = select_species(store)
    log(f"T3 population: {len(chosen)} recordings, "
        f"{len({store.recordings[r]['speciesId'] for r in chosen})} species")
    report["runs"].append(run(store, chosen, "T3 (species pairs)", 2))

    print("\n| population | space | species lift | recordist lift |")
    print("|---|---|---|---|")
    for r in report["runs"]:
        for a in r["arms"]:
            print(f"| {r['population']} | {a['space']} | {a['species']} | {a['recordist']} |")
    OUT.write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
