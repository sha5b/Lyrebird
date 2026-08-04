---
license: cc-by-nc-sa-4.0
task_categories:
  - audio-classification
language:
  - en
tags:
  - bioacoustics
  - birdsong
  - recordist-leakage
  - dataset-splitting
  - evaluation
  - perch
  - birdnet
  - xeno-canto
pretty_name: Recordist-blocked evaluation for bioacoustic foundation models
size_categories:
  - 1K<n<10K
---

# Recordist-blocked evaluation for bioacoustic foundation models

Frozen embeddings and recordist metadata for a fixed population of xeno-canto recordings,
built to measure one thing: **what does blocking an evaluation split by recordist cost a
current foundation model?**

## There is no audio here, on purpose

The recordings belong to the xeno-canto contributors under per-recording licences that cannot
be sublicensed. This dataset holds **non-invertible derived features** and the metadata needed
to reconstruct the population from the source. `_catalogue_full.json` records exactly which
recordings were used, so a replication re-fetches them from xeno-canto under the contributors'
own terms.

If you use this, cite the recordists. They are named per recording in the catalogue.

## What is in it

| field | description |
|---|---|
| `recording_id` | xeno-canto id |
| `species` | scientific name, genus + species |
| `recordist` | the contributor's name as xeno-canto records it |
| `perch` | 1536-d Perch 2.0 embedding, mean-pooled over six 5 s windows at 32 kHz |
| `birdnet` | 1024-d BirdNET V2.4 backbone embedding, mean-pooled over ten 3 s windows at 48 kHz |

Both models are **frozen**. Neither was fine-tuned at any point.

## Why the population is what it is

- **Query:** `grp:birds since:2025-09-01 q:A`. The group tag is not optional — without it the
  same query returns 6,000 recordings of which *none* are birds (bats, frogs, grasshoppers and
  land mammals, in that order of frequency).
- **Uploaded after both models' training snapshots.** Perch 2.0 was published August 2025;
  BirdNET V2.4 was released June 2023. Xeno-canto's `since:` filters on *upload* date, which
  is a one-directional guarantee rather than an estimate. This is what makes a comparison on
  an xeno-canto corpus valid for both models at once — normally BirdNET is excluded from
  xeno-canto-derived benchmarks for training-set leakage.
- **Species floor:** at least 6 recordings from at least **2 distinct recordists**. Under a
  recordist-blocked split, a species whose recordings all come from one person lands wholly on
  one side and cannot be classified at all. That is an empty test class, not leakage, and
  scoring it as an error would manufacture the result.
- **Cap of 12 recordings per species,** allocated round-robin across that species' recordists.
  The raw pool is skewed 6 / median 9 / max 338, so an uncapped set lets a few species dominate
  the class prior. The cap is recordist-aware because a plain random sample of 12 would strip a
  19-to-1 species down to a single recordist and silently make it unscorable.

## How to use it

The intended use is a **split-comparison**, not a leaderboard:

1. Train a linear probe on the frozen features under a random split, stratified by species.
2. Train the same probe under a recordist-blocked split, where every recording by a held-out
   recordist is on the test side.
3. Restrict **both** arms to the classes present on both sides before scoring. A blocked split
   strands whole species on one side, and dropping those from the blocked arm alone leaves it a
   smaller and easier label set — which inflates blocked accuracy and understates the drop.
4. Report the gap in error-rate ratio as well as accuracy points. Points are a much harsher
   unit near the ceiling: the same 9.7-point drop is 2.44x the errors at 93% accuracy and
   1.24x at 60%.

## Known limitations

- One archive, one quality tier (`q:A`). Quality A keeps the audio comparable but selects for
  recordings a human judged clean, and cleanliness may correlate with recordist skill — the
  variable under test.
- Upload date is not recording date. The guarantee is one-directional and that is all it needs
  to be, but a corpus of recent uploads may over-represent currently active recordists.
- A linear probe is not a fine-tuned model. The frozen-feature design is what makes the
  difference attributable to the split, at the cost of not being the number a practitioner
  would report from fine-tuning.
- Recordist identity is self-reported. One person with two accounts reads as two recordists and
  weakens blocking; two people sharing an account reads as one and strengthens it.

## Citation

See `CITATION.cff` in the code repository, and the Zenodo DOI for the archived release.

## Licence

CC BY-NC-SA 4.0 for the derived features and the metadata compilation. The underlying
recordings are **not** covered by this and remain under their contributors' own licences.
