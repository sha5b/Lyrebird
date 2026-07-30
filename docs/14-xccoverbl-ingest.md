# 14 — First sources ingest: xccoverbl, 36 → 121 species, and what variety costs

Evidence record for the first real `sources fetch` (open item 2 of the 2026-07-29
handoff). Source: `internet-archive / xccoverbl_2014` — 264 xeno-canto mirror flacs
balanced over 88 UK species, keyless, deduplicating against the XC harvest by
recording id for free. Chosen over spending the XC rate budget (`expand` had two
obscure white-eyes) and over waiting on the user's Kaggle key, because the critic's
measured weaknesses are coverage weaknesses (docs/11 §11.5) and this was the largest
keyless variety gain.

## 14.1 The ingest (2026-07-30)

- 259 recordings ingested, 5 failed (download errors), 0 already known.
- 291.9 min of audio decoded → 21 325 syllables segmented → 3.4 GB discarded,
  nothing retained but patches and descriptors, as always.
- Store: 1 280 → 1 539 recordings, **36 → 121 species**, syllables 39 999 → 39 874
  (the 40 000 syllable cap binds: the stratified reservoir traded volume in
  over-represented species for 85 new ones — the intended behaviour; stream drift
  0.054 sd, spread ratio 0.980, so the retained sample still looks like the stream).

## 14.2 The chain

`critic embed` (39 874×32, no NaN) → `learn --critic --embed-typing` → novelty
recalibration (`fit_novelty`, target 5 % FPR) → `build --space embed` → `verify`
(all checks passed). The critic itself was **not** retrained: 85 of the new species
carry ~3 recordings each, far below the training bar, and a retrain is its own
pre-registered decision. Embeddings for new species are the 16-species critic's, read
off-distribution — everything below should be read with that in mind.

Also fixed in passing: `embeddings.f32` had gone stale (47 185 rows vs the trimmed
39 999-row store) — the pre-ingest `placement` crashed on it; the re-embed realigned
them.

## 14.3 Pre-registered numbers, before → after

docs/09's four (`placement`), with the caveat that the problem got harder (36 → 117
species references; chance drops 2.8 % → 0.9 %):

| metric | before | after | target | reading |
|---|---|---|---|---|
| nearest own species | 24.6 % | 11.5 % | > 35 % | down in absolute, **up over chance**: 8.8× → 12.8× |
| nearest own type | 60.2 % | 62.6 % | ≥ 56 % | held |
| median resynthesis cosine | 0.768 | 0.742 | ≥ 0.74 | held, barely — 3-recording species fit thin types |
| median \|F0 error\| | 2.9 % | 3.1 % | ≤ 5 % | held |

The rest of the battery:

- **Novelty, recalibrated**: threshold 0.1912 → **0.1737**. ROC AUC 0.672 → **0.786**,
  TPR@5 %FPR 14.8 % → **22.3 %** — but the test changed with the store: the novel side
  is now 25 892 syllables of 105 genuinely non-training species instead of 5 chosen
  holdouts, a harder and more honest ROC. The improvement is real but the two numbers
  are not the same measurement; both are recorded.
- **Galaxy**: 986 clusters / 59 700 points → **1 024 clusters / 75 743 points**;
  space map 0.9268/0.5688 → **0.9531 / 0.5921** (better); relations 210 pairs / 129
  shared → 6 441 pairs / 915 shared.
- **Type coverage: 94.6 % → 54.1 %** (768 of 1 419 types have a cluster). Not a
  regression in the machinery: 651 orphan types belong mostly to the 85 three-recording
  species, which cannot meet the galaxy's minimum cluster size. The ceiling moved from
  "the clustering can't place types" (docs/11, fixed by split seeds) to "the harvest
  depth per species can't support clusters" — a data problem with a known remedy
  (deeper harvest per new species; iNatSounds/GBIF per docs/13).
- **Cluster purity 56.7 % → 30.3 %** — same cause at the other end: 117 species over
  1 024 clusters means clusters now routinely mix species, which purity counts against
  them.
- **Song types on the new store: 42 over 18 species, 477 bouts typed** (was 50 over
  13 species on the 36-species store). Fewer despite more birds: cap-trimming thinned
  the big species' bout counts, and 3-recording species rarely produce six bouts of
  one motif (`SONG_MIN_CLUSTER`). Consistent with the docs/12 calibration.

## 14.4 The warning the geometry section printed

> source — a recording condition, not a bird — is the strongest relation in this
> space; every other result is suspect until the representation is invariant to it.

In the 32-d embedding, `source` kNN lift is **+0.488**, species +0.196 (species was
+0.444 on the 36-species store). The variety ingest did what it was supposed to —
more species, more recording conditions — and the critic, never retrained, organises
the new space by recorder before bird. This is now the pipeline's most honest open
measurement: variety without a retrain buys coverage and costs invariance. It
directly motivates the docs/13 order: a bigger, more varied ingest (iNatSounds,
GBIF archives) followed by a deliberate critic **retrain** with the source-invariance
question pre-registered, not another incremental chain.

## 14.5 State after this round

- Production assets rebuilt and verified: 75 743 points, 1 024 clusters, RFF map
  accepted (0.9531/0.5921), `relations.json` with 915 shared-type candidates.
- `serve` restarted on current code with `--store out/harvest-gan` (the pre-existing
  process ran the morning's code against the old `out/harvest` store — again; the
  Learn-tab hand-harvest `NameError` regression from `287d49c` is fixed in the same
  restart, with the dropdown union in `+page.svelte`).
- Next deliberate steps, in the docs/13 order: iNatSounds + GBIF adapter build,
  critic retrain with source-invariance pre-registered, Perch 2.0 `label-novel`.
