# Lyrebird — the research record

Lyrebird is an instrument in three parts: a physical model of the bird syrinx that
sings, a corpus of 340 079 measured syllables that contains no audio, and a 3-D
map with one point per measured syllable. The app records real birds and
translates them functionally — call type to documented behavioural function,
with a confidence label on every phrase. It generates synthetic bird voices from
fitted physiological parameters rather than from recordings, because the harvest
decodes each file, describes it as numbers, and — by default — deletes it.

*Since 2026-08-01, deleting is the default rather than the whole policy:
`harvest --keep-audio` may keep a recording on the machine where its licence
permits (NoDerivatives refused, an unrecorded licence refused). The **store**
still contains no audio and **nothing audio ships to the browser**, so the
sentence above holds for everything anybody receives. See `NOTICE.md` §3.4.*

These 23 notes are the evidence behind that. They are written as a record rather
than as a pitch: every claim names the fixed corpus it was measured on, and
every refuted idea stays in place with its numbers, so nobody tries it twice.

**`08-implementation.md` is normative.** It is the contract between the Python
pipeline and the browser engine, and both halves implement it. Everything else
is evidence, plan, or literature.

**Status: built and running.** Last updated 2026-08-01. The whitepaper in
`whitepaper/` is the readable synthesis of everything below.

## Reading paths

- **What this is, and why it is built this way** — 3, then 8, then the whitepaper.
- **The voice, and why it still sounds like a machine** — 4, 15, then 21.
- **How the map is made** — 9, 10, 11, then 20.
- **What the project has refused to adopt** — 17, 18, 19, and the ledger table
  in the whitepaper.
- **Where to add data** — 13, then 14 and 16 for how the last two ingests went.

## The notes

**Foundations (1–7)** — what the concept is, and what the field says is possible.

1. `01-reference-artifact.md` — what the viral image actually depicts, where it
   came from, and what its point cloud means technically.
2. `02-procedural-voice-engine.md` — the existing procedural voice synthesiser
   reused as the rendering layer.
3. `03-decoding-science.md` — the honest state of machine decoding: what can be
   characterised, what can be functionally decoded, what cannot be translated.
4. `04-synthetic-bird-voices.md` — syrinx biology, the Mindlin–Laje model, the
   neural alternatives, and why they were declined.
5. `05-embedding-galaxy.md` — the 3-D point cloud: prior art, building the map,
   live audio-reactive animation.
6. `06-architecture.md` — the two halves, the risk register, the build order.
7. `07-references.md` — papers, repositories, datasets, tools.

**The contract and the machine (8–12)** — what was built, and what it measured.

8. `08-implementation.md` — **the contract.** The syrinx model and its measured
   parameter space, the shared 28-d feature extractor, the asset formats, and
   the honesty rule that governs every claim the app makes.
9. `09-learned-objective-plan.md` — the critic. The learned syllable embedding
   works and shipped. The realism objective was refuted twice. Full ablations.
10. `10-real-data-galaxy.md` — the galaxy becomes a measurement: syllable-level
    real clouds, the browser space map, live novelty with an honest ROC. The
    learned inverse failed its bake-off.
11. `11-critic-47k-map-coverage.md` — the 47 k retrain (all metrics up), the
    linear space map's refutation and the RFF ridge that replaced it, and the
    source-split seeds that fixed the 70 % type-coverage ceiling.
12. `12-song-level-types.md` — song types from bouts of type ids: 50 types over
    13 species, with a permutation control setting the recurrence floor at
    0.2 %. Two measured failure modes and their gates.

**Growing the corpus (13–16)** — more birds, and what each ingest cost.

13. `13-sources-and-complexification.md` — new audio sources ranked by variety
    against integration cost, plus complexification routes and the evidenced
    don'ts.
14. `14-xccoverbl-ingest.md` — the first `sources fetch`: 36 → 121 species, and
    the source-confound warning that set up note 17.
15. `15-synth-extensions-math.md` — the implementable mathematics for the
    naturalness program: the respiratory oscillator, the dove membrane model,
    the tracheophone three-source, parrot formants, two-voice coupling.
16. `16-inat-critic-naturalness.md` — the iNatSounds ingest (3 811 species) and
    the 2 686-species critic (novelty ROC 0.846). The streaming parallel learn
    is bit-identical and about twelve times faster.

**The uncomfortable ones (17–21)** — where the measurements contradicted the plan.

17. `17-source-invariance.md` — the embedding organises by recorder before bird.
    **Four verdicts:** loss engineering trades recordist against species one for
    one; a species-safe adversarial head cannot reach the confound, because it
    lives *between* species; the naive domain merge wins; and the bigger re-test
    shrinks every number from the first one. Invariance is a data action.
18. `18-syntax-roadmap.md` — structure first, meaning only from playback. The
    pre-registered grammar bake-off runs and first-order stays: the HMM's win is
    a smoothing artifact in the unseen tail, not recovered hidden structure.
19. `19-spectral-bench.md` — the one that hurts. The 28-d cosine is the
    pipeline's universal fit objective and it does **not** correlate with
    audible spectral distortion (r ≈ 0.1 against two agreeing metrics). It keeps
    its proven role as the clustering guardrail. Every future fit gate reads the
    bench.
20. `20-spacemap-agreement.md` — the map's 0.66 decomposed: 76 % is boundary
    near-ties, genuine failure is about 2 % of rows, and 8 bad sessions carry
    24 % of the loss. A metric problem, not a map problem.
21. `21-syrinx-fidelity.md` — the synthesiser audited against the canonical
    literature. **The model equations are correct, term for term. Every measured
    failure is fit or parameterisation.** A taxonomy pins six "it sounds like a
    machine" symptoms to their causes, and the extension roadmap is ranked by
    realism per unit of interpretability.
22. `22-song-funnel-and-knots.md` — the data audited against the code that
    produces it. Repeat classes ship (species with a song 48 → 98). Both cheap
    knot fixes fail and the measurement says why. **§22.8 is `--clustering label`
    and W5** — the two flags the shipped production build is made of, each with
    the gate it passed or failed.
23. `23-what-we-have-not-tried.md` — five workstreams written from the failures,
    each with the gate stated before the run. W1 (batch effect) **no adoption**,
    W2 order-2 **no structure** though order 1 buys 0.98 bits/token held out, W5
    **adopted**, W6 T1 **fails** with Perch and T3 **passes**. The negatives are
    the point.
24. `24-what-this-corpus-could-add-to-ornithology.md` — the plan for adding to the
    science rather than to the tool. **W0** asks whether bioacoustic benchmarks are
    inflated by recordist leakage, on public corpora with public models, and is the
    one result here that would reach the whole field. **G1** asks whether the fitted
    tracheal length tracks body mass, which decides whether any comparative biology
    is possible at all. Owner's call, 2026-08-04: **run both.** They are independent,
    and W0 stands even if every parameter we fitted is an artefact.

