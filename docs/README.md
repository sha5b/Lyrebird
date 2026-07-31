# Birdy — Deep Research Index

Goal: recreate the viral "AI is decoding what birds have been saying all along"
concept as a SvelteKit webapp — record real birds, "translate" them functionally,
generate scientifically-grounded synthetic bird voices with a choosable vocabulary,
support multiple birds, and visualize everything as an audio-reactive 3D embedding
galaxy that jumps with tone and melody.

Status: built. The research below is the basis; `08-implementation.md` is the contract the
code actually implements, and it is normative — the Python pipeline and the browser engine
both follow it. Date: 2026-07-28.

## Documents

1. [`01-reference-artifact.md`](01-reference-artifact.md) — what the viral
   image/video actually depicts, its origins, and what the point cloud means
   technically.
2. [`02-procedural-voice-engine.md`](02-procedural-voice-engine.md) — analysis of an
   existing procedural bird-voice synthesizer we can reuse as the rendering layer.
3. [`03-decoding-science.md`](03-decoding-science.md) — the scientific state of AI
   bird-vocalization decoding: what's honestly possible, vocabularies, models,
   multiple birds, datasets.
4. [`04-synthetic-bird-voices.md`](04-synthetic-bird-voices.md) — scientifically
   grounded synthesis: syrinx biology, the Mindlin–Laje model, neural alternatives,
   and word-conditioned generation.
5. [`05-embedding-galaxy.md`](05-embedding-galaxy.md) — the 3D point-cloud
   visualization: prior art, building the map, live audio-reactive animation.
6. [`06-architecture.md`](06-architecture.md) — proposed SvelteKit architecture,
   risk register, build order.
7. [`07-references.md`](07-references.md) — key papers, repos, datasets, tools.
8. [`08-implementation.md`](08-implementation.md) — **the contract**: the syrinx model and
   its measured parameter space, the shared 28-d feature extractor, the generated asset
   formats, and the honesty rule. Both halves of the codebase implement this document.
9. [`09-learned-objective-plan.md`](09-learned-objective-plan.md) — the critic: a learned
   syllable embedding (works, shipped for typing), a realism objective (refuted twice),
   and novelty detection, with the full ablations.
10. [`10-real-data-galaxy.md`](10-real-data-galaxy.md) — the galaxy becomes a measurement:
    syllable-level real clouds, the embedding-space build and browser space map, live
    novelty with an honest ROC, label-free typing/chunks/relations, and the learned
    inverse's failed bake-off.
11. [`11-critic-47k-map-coverage.md`](11-critic-47k-map-coverage.md) — the 47 k critic
    retrain (all metrics up), the linear space map's refutation and the RFF ridge that
    replaced it (0.9268/0.5688), the 70 % type-coverage ceiling explained and fixed by
    source-split seeds (94.6 %), and the multi-source harvest layer.
12. [`12-song-level-types.md`](12-song-level-types.md) — song-level type discovery:
    clustering bouts of type ids into song types (50 types, 13 species, 92 % own-medoid
    separation), the two measured failure modes and their gates, and the permutation
    control that sets the recurrence floor (0.2 % at the shipped setting).
13. [`13-sources-and-complexification.md`](13-sources-and-complexification.md) — research
    report: new audio sources ranked by variety × integration cost (iNatSounds, GBIF
    sound archives, NBM flight calls, lab-bird ground truth), complexification routes
    (Perch 2.0 pseudo-labelling, per-taxon renderers, song-level generation), and the
    evidenced don'ts.
14. [`14-xccoverbl-ingest.md`](14-xccoverbl-ingest.md) — the first `sources fetch`:
    xccoverbl takes the store 36 → 121 species; species placement 8.8× → 12.8× over
    chance, novelty ROC 0.786 on a harder test, coverage 54 % (harvest-depth problem,
    not clustering), and the source-invariance warning that sets up the next retrain.
15. [`15-synth-extensions-math.md`](15-synth-extensions-math.md) — the implementable
    mathematics for the naturalness program: respiratory oscillator (Fainstein 2025,
    eqs + Table S2 parameters), dove membrane model (Elemans 2009), tracheophone
    three-source (Garcia 2017 + released code), parrot lingual formants, two-voice
    tracheal coupling (Laje & Mindlin 2005), and a ranked "what else" (plantcutter,
    echolocation, non-syringeal sonations).
16. [`16-inat-critic-naturalness.md`](16-inat-critic-naturalness.md) — the iNatSounds
    ingest (3 811 species, audio cache), the 2 686-species critic (novelty ROC 0.846 /
    TPR 32 %), the streaming+parallel learn (bit-identical, ~12× faster, common names),
    B1 respiration + B2 two-voice (parity 16/16, default-off pending the per-species
    fit), and Perch 2.0 label-novel as metadata.
17. [`17-source-invariance.md`](17-source-invariance.md) — the recorder-invariant
    critic retrain: channel-EQ simulation + Freq-MixStyle on log-mel patches, a
    recordist-adversarial head, and the pre-registered verdict table (docs/14 §14.4's
    source-confound attacked at training time, the only place the literature says it
    can be). **Four verdicts inside:** the loss-engineering sweep fails (adversarial
    trades 1:1 with species), the AVEX experiment succeeds — naive domain merge
    buys +14.4 pts cross-domain retrieval with everything held — the §17.5
    follow-up closes the loss road (a recording-within-species adversarial head is
    species-safe by construction but reaches only −6 % of the recordist lift,
    because the confound lives *between* species), and the §17.6 bigger re-test
    shrinks the small-sample numbers: arm C's contrastive boost does not replicate
    (+1.7 pts vs the +10 gate; its §17.4 AUC drop reverses), and the merge's own
    win reads +3.6, not +14.4. The ordering survives: invariance is a data action.
18. [`18-syntax-roadmap.md`](18-syntax-roadmap.md) — the pattern/syntax roadmap:
    depth harvest first, then a pre-registered grammar bake-off (first-order vs
    Jin–Kozhevnikov vs POMM), a song-level embedding, CETI-style factorization,
    dialect maps. Structure first; meaning only from playback. **P1 result inside:**
    the bake-off is run — first-order stays (the HMM's win is a smoothing artifact;
    the real find is the unseen-transition backoff weakness).
19. [`19-spectral-bench.md`](19-spectral-bench.md) — the uncomfortable one: the 28-d
    resynthesis cosine, the pipeline's universal fit objective, does **not**
    correlate with audible spectral distortion (r ≈ 0.1 against both MCD and
    multi-res STFT, n=200, two agreeing metrics). The cosine keeps its proven role
    as the clustering guardrail; the mel-patch fit target becomes the priority, and
    every future fit gate reads the bench.
20. [`20-spacemap-agreement.md`](20-spacemap-agreement.md) — the 0.66 centroid
    agreement decomposed: 76 % is boundary near-ties (tie-adjusted agreement is
    0.91), genuine map failure is ~2 % of rows, and 8 bad xeno-canto sessions carry
    24 % of the loss. Metric problem, not a map problem; no ONNX, no new bridge —
    species-level live matching is the honest claim. §20.3 attacks the bad
    sessions: fit-side pruning fails its gate (weird sessions are manifold
    coverage), the live-path off-manifold signal and the margin-aware mapQuality
    fields are the surviving direction.
