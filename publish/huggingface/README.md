# Hugging Face: where the audience actually is

BirdSet, Perch and BirdNET all live on Hugging Face. The people who would act on the W0 result
read dataset cards there. They do not read ecology preprint servers.

This is the highest-leverage venue on the list and it costs nothing.

## Steps

1. Account at [huggingface.co](https://huggingface.co). Free.
2. `pip install huggingface_hub` and `huggingface-cli login`.
3. Create a **dataset** repo (not a model repo): `lyrebird-recordist-blocked` or similar.
4. Paste [`dataset-card.md`](dataset-card.md) as the repo's `README.md`. The YAML block at the
   top is what makes it findable — the `tags` are the search surface.
5. Upload:

```
pipeline/out/external/w0-full-embeddings.npz      # perch + birdnet, float32
pipeline/out/external/w0-full-meta.json           # species, recordist, census
pipeline/out/audio-postcutoff/_catalogue_full.json  # so the population is reconstructible
```

6. **Do not upload audio.** Nothing matching `pipeline/out/audio-postcutoff/xc*` or
   `pipeline/out/audio-cache/*`. `NOTICE.md` is the reason.

## Make it loadable, or it will not get used

An `.npz` is a barrier. Convert to Parquet so `load_dataset` just works — a dataset nobody can
open in one line does not get opened:

```python
import json, numpy as np, pyarrow as pa, pyarrow.parquet as pq
z = np.load("w0-full-embeddings.npz", allow_pickle=True)
meta = json.load(open("w0-full-meta.json"))["meta"]
ids = [str(r) for r in z["ids"] if str(r) in meta]
keep = [i for i, r in enumerate(z["ids"]) if str(r) in meta]
pq.write_table(pa.table({
    "recording_id": ids,
    "species":   [meta[r]["species"] for r in ids],
    "recordist": [meta[r]["recordist"] for r in ids],
    "perch":     [v.tolist() for v in z["perch"][keep]],
    "birdnet":   [v.tolist() for v in z["birdnet"][keep]],
}), "w0.parquet")
```

Then the card can promise `load_dataset("<you>/lyrebird-recordist-blocked")` and be telling the
truth.

## After it is up

Post in the **Community** tab of the two model repos that this measures — `google/perch` and
the BirdNET ONNX exports — and of `DBD-research-group/BirdSet`. One short message each, linking
the dataset and the number. BirdSet is the most direct: it already excludes BirdNET from its
xeno-canto splits for leakage, and the post-cutoff design is a way around exactly that problem.

Draft messages are in [`../community/benchmark-maintainers.md`](../community/benchmark-maintainers.md).
