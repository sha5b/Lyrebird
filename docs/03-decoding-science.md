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

## 3.6 Typing words at a bird — what the Words tab may and may not claim

Added 2026-08-04, when the Words tab was reworked from keyword matching to a functional
reading. `app/src/lib/lang/functions.ts` is the implementation and
`app/scripts/verify-functions.mjs` is the 46-check harness that holds it to this section.

**The claim the tab makes, in one sentence:**

> The functional category is real to the bird. The assignment of your words to it is ours.

**Why the first half is defensible, and it is newly so.** Elie et al. 2025 (*Science*
389:1210-1215, doi:10.1126/science.ads8482) found that zebra finches' own confusion errors
between call types cluster by **behavioural context rather than by acoustic similarity**.
The categories are organised in the bird's head, not only in our table. That is the best
evidence in the bird literature that a functional category is a psychologically real object
in a way a word is not.

**Why the second half has to be said out loud.** There is no literature supporting a
mapping from English text to an animal signal category, and there is a structural reason
there is none: bird call form is non-arbitrary (Marler 1955; Morton 1977), so a call means
what it means the way a growl does, not the way a word does — Wheeler & Fischer 2012
(*Evol. Anthropol.* 21:195-205) put it as the vervet leopard alarm not referring to leopards
"in the way the English word 'leopard' does". **There is no arbitrary signifier to attach an
English word to.** So the mapping is ours, it is `invented`, and the interface says so on
its own line rather than in a footnote.

The chain is therefore two links with different evidence classes, and they are never merged:

```
link 1   typed English -> functional category     OURS. always `invented`
link 2   category -> this species' authored call  THE CORPUS'S. keeps its own
                                                  confidence badge and citations
```

The phrase badge takes the weaker link; the note reports the stronger one.

**Five categories, and the count is a finding rather than a shortcut.** alarm,
recruitment, contact, territory, courtship. Begging, distress, flight call, food call,
roost assembly and duet have no authored call in any of the 12 species with functions, so
they are not offered. There is also no external vocabulary to borrow: xeno-canto's
controlled list has no "contact call", Macaulay/eBird collapses alarm and contact into one
"Call" bucket, and BirdNET's 6 522 classes are all taxon labels. Saying "we defined these
five from what our own corpus holds" is more defensible than implying a standard exists.

**Coverage, stated because it decides the design.** 12 species of 2 650 carry any authored
function — 0.45 %. Pick a bird at random and there is a **99.55 % chance the typed words
have nothing to map to**, so the refusal is the majority path and is written as a designed
answer rather than an error. The picker keeps all 2 650 and marks the 12; narrowing it
would make the feature work nearly always while quietly presenting the best 0.45 % of the
corpus as if it were the corpus.

**Three refusals worth naming, because each is a thing someone will ask for.**

- **The 16 239 `unlabelled` fitted types may not be recruited to widen coverage.** A
  cluster from an archive recording has no sender state, no receiver and no context, which
  is exactly the case Rutz et al. 2023 says archives alone cannot decode: "robust
  information on the identities and states of the senders and receivers, and the specific
  communication context, is usually lacking". It is not a weak label; it is no label.
- **`d_abc`, the reversed great tit control, is not offered as something to say.** In
  playback it elicits neither response, so it is a null result. Offering it as a message
  would invert its meaning.
- **Embedding typed text against the fitted types and returning the nearest is refused.**
  It is the worst case in Goldwasser et al.'s own theorem (arXiv:2211.11081) — minimum
  repertoire complexity, minimum common ground — and Paradise et al. 2025
  (arXiv:2510.15768) concede that without parallel data a fluent hallucination scores
  identically to a correct answer. There is nothing to validate against and no gate that
  could be pre-registered, so the answer is no.

**Valence is refused; arousal is not claimed here either.** Across species valence is
signalled categorically, by switching call type, rather than by graded modulation, and in
birds the evidence is worse than thin — Bessa Ferreira et al. 2022 (*PLOS ONE*
17:e0279553) found neither White Leghorns nor Red Junglefowl behaviourally distinguished
alarm from contentment calls. The one graded axis the corpus does support is **D-note count
in the black-capped chickadee** (Templeton, Greene & Davis 2005, *Science* 308:1934-1937),
and the interface says it is one species rather than implying a general intensity dial.

**ABC-D is presented as a playback result, not as settled compositional syntax.**
Schlenker et al. 2023 (*Biol. Rev.* 98:1142-1159) grant it as the one surviving case in the
animal literature; Beckers et al. 2024 (*Front. Psychol.* 15:1393895) grant none, arguing
concatenation and a bigram model suffice; the nearest independent replication (Dutour,
Suzuki & Wheatcroft 2020) was mixed. The build is on the right side of this and should not
overstate it.
