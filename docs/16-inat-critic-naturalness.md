# 16 — iNatSounds ingest, the 2 686-species critic, and the naturalness program

Evidence record for the 2026-07-30 session(s): the first large source ingest beyond
xeno-canto, a critic retrained on 2 686 species, the parallel/streaming learn, the
first two synth extensions (respiration, two-voice), and the Perch 2.0 pseudo-labeller.
Build/verify/placement numbers are filled in at the end (§16.6) — this file is written
while the production build runs.

## 16.1 The ingest

`inat-sounds` adapter (sources.py): iNatSounds 2024 via AWS Open Data, keyless, 81 GB
train archive streamed once, **Aves only, NoDerivatives licences excluded** (531 of
111 029 files), `--per-species` for balanced takes. One pass: **6 453 recordings,
2 513 min of audio, 226 264 syllables, 3 811 species**, zero failures, drift 0.048 sd.
Store caps were raised deliberately (300k descriptors / 200k syllables) and — the
load-bearing fix — **caps now persist in `state.json`** (harvest.py): before this, a
default-cap `serve` ingest would have silently trimmed the enlarged store back.

**Audio cache.** The owner overrode the delete loop for the training phase
(AGENTS.md records it, 2026-07-30): `--keep-audio` cached 6 453 WAVs (6.3 GB) to
`pipeline/out/audio-cache/`. Local only, gitignored, feeds `harvest_directory`,
deleted at phase end; xeno-canto harvests still delete immediately. The cache is
what makes Perch labelling and fit iteration possible without re-downloading.

## 16.2 The critic, retrained on variety

2 686 training species (895 held out entirely), 126 757 real + 44 608 synthetic
patches, 60 epochs:

| metric | 16-species critic (docs/11) | this critic | reading |
|---|---|---|---|
| realism AUC held-out | 0.997 | **1.000** | — |
| species accuracy | 0.939 (16 classes) | **0.730** (2 686 classes, chance 0.0004) | not comparable — a far harder problem; both recorded |
| contrastive top-1 | 0.820 | 0.672 | same caveat |
| novelty ROC AUC | 0.672 → 0.786 (recal) | **0.846** | the novel side is now 895 whole species — the hardest test yet |
| novelty TPR @ 5% FPR | 14.8 % → 22.3 % | **32.2 %** | threshold 0.1323 |

The docs/14 §14.4 question — does the embedding still organise by recorder before
bird — is re-measured after the production build (§16.6): source-lift vs species-lift
on the new geometry.

## 16.3 Learn, now streaming and parallel

- **Parallel per-species fitting** (`learn --jobs N`): the critic embeds all
  observations once in the parent (GPU, ~4 s), then a fork pool fits species
  independently (`_fit_species_parallel`). **Verified bit-identical** to the serial
  fit on the fast store. The 3 800-species learn went from a ~3 h serial pace to
  ~15 min on 16 workers.
- **Streaming writes**: `learn-progress.json` per fitted species (surfaced as
  `learnProgress` in `/api/status`), typing + partial document checkpointed every
  100 species. Before this, a crash at minute 50 cost the whole run — it happened
  twice on the way here.
- **Common names**: `learn.recording_names` recovers English names from the store's
  recording metadata (xccoverbl `en`, iNatSounds `common_name`); **2 423 of 2 423
  fitted species carry real names** instead of their ids.
- **Measured gaps** (`grammar.gaps`): median `gap_before` per transition — rhythm is
  no longer an invented constant anywhere the app plays sequences.

The 200k learn: **2 423 species, 12 724 types, 187 078 observations typed**, median
resynthesis cosine 0.650 (thin types from 2-recording species pull the median down —
expected, and the per-species fit pass below is aimed at exactly this), 9 song types
(52 syllables/species median is too thin for 6-bout motifs; honest, see docs/12).

## 16.4 The naturalness program, first two pieces

Both judged on a fixed store (`learn --no-invert`, /tmp copy of harvest-mp), both
shipped **off by default**, both waiting on the per-species fit:

- **B1 respiratory oscillator** (respiration.py; Fainstein/Goller/Mindlin 2025, docs/15
  §1): 2-state pressure dynamics + Heaviside inflow/outflow asymmetry replaces the
  designed envelope; √ps at the tract input (Laje & Mindlin 2005's low-frequency
  result — docs/09 §9.6's "every reference injects ẏ" corrected in place). Parity
  14/14. Hand-set default: median cosine 0.343 → 0.336 (wash), placement +3. Losses
  concentrate in sub-50 ms notes.
- **B2 two-voice renderer** (twovoice.py; Laje & Mindlin 2005 coupling): independent
  gesture streams + shared tracheal pressure (γ_refl 0.9, fractional-delay round
  trip). Parity 16/16. Hand-set default: 0.343 → 0.294 — but the two worst-fitting
  low-pitched species *improve* (coupling adds structure where the single voice was
  furthest from the audio). The per-species fit is the expected win, pre-registered.

**The fit pass** (running at this writing): per-species coordinate search over the
Table S2 ranges, shipping a fitted parameter set on a type only where it beats the
current cosine; then the pure-tone documented re-fit (the tawny owl's `hooLong` is
`noise=0, rough=0, timbre=pure` — a sine with an organ envelope, which is what
sounds "digital"; the learned types of the same bird carry noise 0.05–0.25 and rough
up to 0.65).

## 16.5 Perch 2.0 label-novel

`birdy-pipeline critic label-novel` (perch.py; ONNX port of Perch 2.0, no TF dep,
~48 ms/window CPU). Labels the critic's novel-flagged syllables from the audio cache
as **metadata** with the honesty line "closest documented species (Perch 2.0
inference, unverified)" — never as type identity. Spike findings: 23 697 novel
syllables in the store; 841 honestly unlabelable (xeno-canto audio deleted by
design). Smoke sanity: a flagged crossbill syllable → *Loxia curvirostra* 0.883.
Measured caveat: Perch labels the 5-s window, not the syllable — background birds
can dominate.

## 16.6 The build (filled when it lands)

_Production build of the 2 423-species galaxy — points, clusters, coverage, purity,
space map, source-vs-species lift (the §16.2 question), verify, placement
before/after. Pending at this writing._
