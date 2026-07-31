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

## P1 result (2026-07-31): the grammar bake-off — first-order stays

`syntax.py` + `birdy-pipeline syntax`, run on the debug store (30 qualifying
species, 3 750 bouts ≥ 3 tokens, seeded 80/20 bout splits, add-α 0.1 backoff,
deterministic — two runs bit-identical). The pre-registered table:

| model | mean ΔLL/token vs first-order | species won |
|---|---|---|
| M2 repeat-count (Jin–Kozhevnikov) | **−0.348** | 0 / 30 |
| M3 hidden-state HMM (K ∈ {4,8,16}) | **+0.422** | 29 / 30 |

By the letter of the rule M3 wins. **The decomposition is the honest reading, and
it reverses the adoption**: split held-out tokens into transitions seen vs unseen
in train — on the 90 % seen, first-order is the best model (−1.525 vs M3's −1.624
nats/token, better in 15/30 species; M2 worse in 25/30); M3's whole advantage comes
from the 10 % unseen tail, where M1 pays −9.25 and M3 only −4.16 nats/token. That
is a property of smoothing *shape* (a mixture predictive is heavy-tailed), not of
recovered hidden structure. So:

- **First-order stays the shipped model.** M2's mechanism fragments counts on this
  corpus and adds nothing; M3's win is real as scored and meaningless as structure.
  Adopting a heavier model for a smoothing artifact is the wrong lesson.
- **The one real weakness the bake-off exposed is M1's unseen-transition backoff**
  (−9.25 nats/token on a tenth of held-out transitions). A repair — softer unigram
  backoff or Kneser–Ney-style continuation counts — is a *smoothing* fix, to be
  judged on its own pre-registered terms, not smuggled in as a model upgrade.
- **Re-run after the depth harvest (P0).** At current depth ~10 % of held-out
  transitions are unseen; depth shrinks that tail and may change the picture — thin
  data is exactly where higher-order models starve (M2's 0/30 says so).

### The backoff repair (same day, pre-registered separately) — shipped

`FirstOrder` in syntax.py gains `backoff="continuation"` (Kneser–Ney lower order:
P(next) ∝ distinct contexts `next` followed, add-α to uniform; seen contexts
bit-identical to the old row). Gate: ≥ +1 nat/token on unseen-*context* transitions
with seen-side loss ≤ 0.01. **Passes on both debug corpora**: +1.90 (37-species
store) and +2.32 (debug-100) nats/token, seen loss exactly 0.0000. Two honest
caveats: 80 % of the unseen tail is *seen context, unseen continuation* — outside
the repair's scope, so the full-tail gain is +0.37/+0.65, not the headline +1.9; and
the repair narrows the HMM's unseen-tail advantage, confirming that M3's "win" was
smoothing shape. The shipped grammar artifact is untouched either way — the repair
improves the *measurement baseline* future bake-offs are judged against.
