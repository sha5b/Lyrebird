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

## 16.7 The fricative path (design, pre-registered)

**The evidence.** Two independent species parked their fits at the noise ceiling and
still failed: chestnut-headed oropendola (L02/L04 `noise=0.85`, cos 0.12–0.77) and
Algerian nuthatch (5 of 8 types at `noise=0.60–0.85`, cos 0.16–0.60). The debug
spectrogram comparison (real vs render on cached iNat audio) shows the class: real
chip notes are **broadband bursts with formant structure**; our renders of them are
tonal — or, when the fit gives up and maxes the axis, flat white noise.

**The diagnosis.** A fricative call is not "tone plus noise": it is a *noise burst
filtered by the vocal tract and driven by the pressure gesture* — whispered vowels,
not static. The current `noise` axis injects turbulence at the labia (broadband,
weakly shaped). The fit pushing it to the ceiling and still scoring 0.16 is the
model reporting that the *shape* is missing, not the amount.

**The work, one path:**

1. **Formant-filtered noise** — the fricative gets its own tract filtering: band
   shape from the fitted formant set, applied to the noise source, not only to the
   tonal one.
2. **Pressure-driven noise envelope** — the respiratory gesture (B1) drives the
   noise burst's envelope exactly as it drives the tonal source: a fricative burst
   *is* a pressure event.
3. **A noise-first fit strategy** — the inversion currently searches "tone, plus how
   much noise" from the median; this class starts at "noise, shaped how" and fits
   the filter. Same pre-registered judgment: resynthesis cosine + placement on a
   fixed store, ship only where it wins, starting with nuthatch L00/L02 and
   oropendola L02/L04 as the test bench.

**Verdict history:** this is the third measured gap in the same family (docs/11
coverage, docs/14 source-invariance, §16.7 shaped noise) — all three say the corpus
grew past the representation. The first two have their fixes in flight; this one is
the acoustic half.

## 16.6 The build (debug-100 cycle) and the discovery roadmap

The deliberate full-store build was paused for a debug cycle (the user's call): subset
(100 biggest species, 20 193 syllables, recordings whole) → parallel learn (~2 min) →
embed → build → verify — **all green**: 45 592 points, 1 024 clusters, **0 %
unassigned points**, 713/1 003 types placed, space map 0.9624/0.6634, shards live
(55 MB → 312 KB index). This is the build discipline going forward: debug-100 first,
full run when it passes.

The judgment pass on it found and fixed: trajectory tangle (a static context
backdrop with no lifecycle), rest-wash too faint (0.34 → 0.5, class separation
0.146 → 0.215), activation firing at *inferred* knots for orphan notes ("known-
unplaced beats inferred"), chorus solo leak, all-birds auto-chorus, and shipped the
full color language (points = provenance, labels = species hue, trajectory
gradients, dense-knot bloom, the grey-breath unmatched state, points plain/coloured
toggle). And it found the fricative gap — fixed in §16.7 with measured wins.

**The discovery roadmap** (from the embedding-space discussion): an embedding is its
objective made visible, and the project now owns four lenses — the 28-d descriptor,
the critic's 32-d, Perch 2.0's 1536-d (offline, Apache-2.0), and the song-type
sequence space. Next: (1) **Perch-vs-critic RSA/CKA comparison** — does Perch's
space agree on novelty, and is the recorder-clumping our critic's artifact or
acoustics; (2) **dialect/individual structure** — the corpus is finally big enough
(separating 10–16 individuals per species is literature-proven); (3) **song-level
embedding for structure** — dialect variants, shared motifs — while function
identification stays at syllable level with a dozen anchors, propagated only as
candidates with shares. The translator for unknown birds is a pipeline, not a
promise: arrive → type by similarity → cluster into candidates (U*) → Perch label
as metadata → measure its syntax over time → function claims only where playback
anchors exist. Anything less honest is numerology.
