# 18 — Syntax & pattern roadmap: from syllables to what they're saying

The translator roadmap's pattern half, made explicit. The rule throughout: **structure
first, meaning only from playback** (CETI's lesson, and our §8.5 honesty rule). Every
stage names its blocker, its pre-registered metric, and its debug loop. Nothing here
ships from a full run until it has won on the debug store.

## Where we stand

- Rhythm is measured, not invented: 26 897 per-transition gaps; >1 s = bout boundary.
- Syntax is first-order only: transitions, mined chunks, HMM song types (docs/12).
  The literature is unambiguous that birdsong is not first-order (Jin & Kozhevnikov
  2011 — repeat-count adaptation; Lu et al. 2025 — POMMs beat HMMs on Bengalese
  finch). This is a known, documented under-model, not a surprise.
- The galaxy is syllable-level. A song-level space does not exist yet.
- Two gating constraints from elsewhere: **depth** (~10 recordings/species is too
  thin for song structure) and the **recorder confound** (docs/14 §14.4; Stage 1's
  retrain is the fix being swept — a pattern space built on a recorder-organised
  embedding would cluster microphones, not songs).

## P0 — Depth harvest (the unblocker)

20–50 recordings each for ~100 chosen species, audio retained in the cache (owner
exception). Species chosen for: documented syntax cases (chickadee chick-a-dee,
Japanese tit ABC-D congeners, starling mimicry, sparrow dialects), repertoire depth,
and playback anchors already in the inventory. **This one action unblocks P2, P4,
and the spectral bench simultaneously — nothing else on this page does that.**
Debug: `subset --diverse` already exists for choosing the bench species honestly.

## P1 — Grammar model comparison (can start now, on debug data)

Pre-registered bake-off on the deepest species we already have: current first-order
transitions vs **Jin–Kozhevnikov** (repeat-count-dependent transitions, the minimal
sufficient model for finch syntax) vs **POMM** (partially observable Markov). Metric:
held-out bout likelihood + transition entropy, same bouts, same splits. Ships only
the winner; a wash keeps first-order and is documented. No new data needed — this is
a model question, and mechanics are debug-testable today.

## P2 — Song-level embedding (lens #5)

Whole bouts as points: syllable-type tokens + measured gaps + tempo. Start with a
parameter-free sequence kernel (edit distance over token×gap sequences) before any
learned encoder — the critic's own discipline says the hand-written baseline comes
first, so the learned one has something to beat. Pre-registered: kNN lift by
species vs by individual vs by recordist (the last must stay ~0 or Stage 1 failed
upstream). **Blocked on P0 (bouts per bird) and Stage 1 (invariance).**

## P3 — CETI-style factorization

Decompose each deep species' songs into independent axes — rhythm, tempo, rubato,
ornamentation — the way sperm-whale codas factorized into a 156-unit alphabet
(Sharma et al. 2024). The raw material already exists: typed tokens, measured gaps,
contour shapes. Deliverable: per-species combinatorial alphabets and their usage
statistics — the strongest honest claim available without playback.

## P4 — Dialect & individual maps

With P0 depth: same-species song variants placed geographically (the white-crowned
sparrow dialect literature, and Otter 2026's continent-wide song takeover, are the
template), individuals separated where 10–16 bouts each exist (literature-proven
sufficient). The galaxy gains a song-level view beside the syllable one — and the
two-map discipline (`--clustering both`) applies to it from day one.

## P5 — Function propagation through syntax

The playback anchors stay the only proof. What patterns add is *channels*: a motif
appearing in the same sequence position across individuals is a stronger function
candidate than a bare acoustic match, and is propagated as exactly that — a
candidate, with shares and a confidence label.

## P6 — Unknown-bird syntax

The arrival pipeline extends upward: U* syllable candidates → sequence statistics
over time → candidate song types for birds nobody has documented. Everything above
the syllable stays `unlabelled: real acoustics, no documented function`.

## Order and gates

**Now:** P1 (no new data needed). **After Stage 1's verdict:** P0 (deliberate
harvest). **After P0:** P2 → P3 → P4. **Continuous:** P5, P6 as each layer lands.
Each stage is judged on the debug store with both maps built, and a negative result
is written down, not deleted.
