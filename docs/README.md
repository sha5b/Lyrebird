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
