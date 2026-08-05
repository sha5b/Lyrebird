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
| `country` | country as xeno-canto records it, 116 distinct |
| `lat`, `lon` | decimal degrees where xeno-canto publishes them (21 156 of 21 928 catalogue rows) |
| `date` | recording date, for temporal blocking |
| `perch` | 1536-d Perch 2.0 embedding, mean-pooled over six 5 s windows at 32 kHz |
| `birdnet` | 1024-d BirdNET V2.4 backbone embedding, mean-pooled over ten 3 s windows at 48 kHz |

Both models are **frozen**. Neither was fine-tuned at any point.

The geographic and temporal fields are here because recordist is not the only axis that
leaks, and on this population it is not even the most expensive one. Blocking by **country**
costs more than blocking by recordist, and blocking by **year** costs about the same — so the
fields needed to reproduce or contest that are shipped rather than described.

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

### Comparing blocking variables against each other

If you extend this to `country`, a lat/lon grid or `date`, hold out a fixed share of
**recordings**, not of levels. The variables have very different level counts, and 30% of 116
countries strands 43% of the recordings while 30% of 646 recordists strands 34% — the arm with
less training data then loses accuracy for a reason that has nothing to do with leakage. Match
the held recording share, and report the surviving class count per arm, because the drop also
grows with the size of the label set.

Two numbers to expect on this population, both with the held share matched, 20 paired folds:

| blocked by | levels | classes | Perch drop | BirdNET drop |
|---|---|---|---|---|
| recordist | 646 | 716 | 19.02 | 22.07 |
| location, 1° cell | 1128 | 726 | 18.26 | 20.68 |
| country | 116 | 502 | **23.87** | **26.97** |
| year | 36 | 706 | 19.11 | 21.50 |

These axes are **not independent** — normalised mutual information is 0.817 between recordist
and 1° cell, 0.733 between recordist and country — because a recordist records near home. The
transferable claim is that blocking costs 17–27 points on whichever of these axes you pick,
not that there are four separate leaks to fix.

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
- The country arm above is suggestive rather than settled, and two biases oppose each other in
  it. Even matched, country holds 0.436 of recordings against recordist's 0.402, because 116
  coarse levels cannot be matched finely, and that residual favours a larger country drop.
  Against it, country's folds survive with far fewer classes (502 vs 716), and a smaller label
  set makes the drop smaller. Sub-sampling within countries to match the held share exactly, or
  re-running at matched class counts, would settle the ordering.
- Where xeno-canto redacts a location for a species it considers at risk from disturbance, the
  lat/lon fields are absent rather than approximate. 222 rows in the scored population carry no
  grid cell for this reason and fall out of the location arm only.

## Citation

See `CITATION.cff` in the code repository, and the Zenodo DOI for the archived release.

## Licence

CC BY-NC-SA 4.0 for the derived features and the metadata compilation. The underlying
recordings are **not** covered by this and remain under their contributors' own licences.
