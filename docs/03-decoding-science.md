# 3 — Translating birds: what is actually possible

## 3.1 The honest framing

The field's own position (Rutz et al., *Science* 2023, DOI 10.1126/science.adg7314):
ML today can

1. **characterize** repertoires (find the units and their structure),
2. **functionally decode** (link signals to context/behavior),
3. but **not** translate into propositional human language — that needs playback
   experiments, which exist for only a handful of systems.

A central ethological asymmetry (Patel-Grosz et al., "Super Linguistics"): bird *song*
has rich syntax but weak/no referential meaning. Bird *calls* carry meaning but little
syntax. So the scientifically defensible product is **functional translation**: call
type → documented behavioral function, species, individual identity, urgency — with
confidence labels. "Word-for-word translation" is marketing, not science. The app
should say so.

## 3.2 Studied vocabularies — the basis of Lyrebird's language set

| Species | What's documented | Key refs |
|---|---|---|
| Japanese great tit | >10 note types with referential meaning; **ABC-D compositionality** (ABC = "scan for danger", D = "approach", ABC-D = compound; reversed order elicits nothing) — strongest evidence for word-order rules in birds | Suzuki, Wheatcroft & Griesser, Nature Comms 2016 |
| Siberian jay | Alarm calls encode *predator behavior* (perched/searching/attacking hawk), situation-specific escapes | Griesser 2008, Current Biology |
| Black-capped chickadee | chick-a-dee call: 4 note types, strict A→B→C→D ordering, D-count scales with threat; notes carry flock/individual identity | Freeberg et al. 2003 |
| Nightingale | ~180–200 song types per male; package organization, context rules, countersinging duel rules (matching/overlapping) | Hultsch & Todt; Jäckel et al. 2022 |
| Bengalese finch | **Finite-state song syntax** (transition grammar with chunks/loops); females prefer syntactic complexity | Okanoya 2004; Katahira et al. |
| Zebra finch | Linear stereotyped motif, strong individual signatures; individual recognition is the main "semantic" layer | Elie & Theunissen 2018 |
| Budgerigar | Warble syntax encodes group identity; two phonological systems | Tu et al. 2011 |

This table *is* the language set: a curated vocabulary of call/syllable types per
species, each annotated with its documented function — not invented meanings.

## 3.3 Decoding stack — models that exist today

- **Google Perch / Perch 2.0** (Apache 2.0, commercial OK): EfficientNet-B1, 5 s @
  32 kHz → 1280-d embedding, 14,597 species (v2, 2025). Embeddings are linearly
  separable → compute once, reuse for few-shot classifiers.
  https://github.com/google-research/perch · arXiv:2508.04665
- **BirdNET** (Cornell): EfficientNet CNN, 3 s @ 48 kHz → 6,522 species + 1024-d
  embedding. Runs on CPU/RPi. **License: CC BY-NC-SA — non-commercial only.**
  https://github.com/birdnet-team/BirdNET-Analyzer
- **Self-supervised encoders (MIT)**: AVES/BirdAVES (Earth Species Project,
  HuBERT-style), BirdMAE (SOTA on BirdSet). One API over all of them: ESP's `avex`
  or the `bacpipe` pip package. https://github.com/earthspecies/avex
- **Text-promptable zero-shot**: NatureLM-audio (audio-language model, ICLR 2025,
  arXiv:2411.07186) and BioLingual (CLAP-style text↔bioacoustic embedding).
- **"Teach a new call from 5 examples"**: DCASE Task 5 few-shot bioacoustic detection
  is exactly this paradigm. Linear probes on Perch/BirdNET embeddings work with ~5
  labels.
- **Individual recognition**: a fine-tuned BirdAVES identified 173 wild zebra finches
  from 1–3 s clips (macro-F1 0.73). Per-user few-shot "enroll my bird" is feasible.

## 3.4 Multiple birds

- **Cocktail-party separation** is immature in bioacoustics. The reference system is
  BioCPPNet from ESP, a U-Net that separates overlapping conspecific calls
  (github.com/earthspecies/cocktail-party-problem). No production species-general
  bird "speaker separation" exists.
- **Practical pipeline**: detection windows → embeddings → **clustering**
  (Perch/BirdNET embeddings cluster by individual in many species) → user-confirmed
  enrollment.
- **Mic arrays** (TDOA/beamforming localization) are the mature route to attributing
  calls to individuals spatially (Rhinehart et al. 2020) — power-user feature.
- If "multiple birds" means *multiple users streaming mics*, extract features
  client-side. Then broadcast tiny feature vectors over WebSocket instead of audio.
  This gives near-zero bandwidth with no SFU (see `06-architecture.md`).

## 3.5 Datasets

- **xeno-canto** has ~1M recordings and >10k species behind a REST API. Licenses are
  per-recording CC: check NC/ND flags before shipping audio.
- **Macaulay Library** (Cornell, more restrictive licensing).
- **BirdSet** (curated XC, Hugging Face, the current standard benchmark).
- **BirdCLEF** (Kaggle, CC BY-NC-SA), **BEANS** benchmark, **DCASE Task 5** few-shot
  sets.
- Isolated-syllable corpora for synthesis training: Bengalese Finch Song Repository
  (vocalpy.org/bfsongrepo), 887 isolated zebra finch syllables (Zenodo 5545872).
