# 18 — Syntax & pattern roadmap: from syllables to what they're saying

The translator roadmap's pattern half, made explicit. The rule throughout: **structure
first, meaning only from playback** (CETI's lesson, and our §8.5 honesty rule). Every
stage names its blocker, its pre-registered metric, and its debug loop. Nothing here
ships from a full run until it has won on the debug store.

## Where we stand

- Rhythm is measured, not invented: 26 897 per-transition gaps. A gap of >1 s marks a
  bout boundary.
- Syntax is first-order only: transitions, mined chunks, HMM song types (docs/12).
  The literature is unambiguous: birdsong is not first-order. Jin & Kozhevnikov
  2011 show repeat-count adaptation. Lu et al. 2025 show POMMs beat HMMs on Bengalese
  finch. This is a known, documented under-model, not a surprise.
- The galaxy is syllable-level. A song-level space does not exist yet.
- Two gating constraints come from elsewhere. The first is **depth**: ~10
  recordings/species is too thin for song structure. The second is the **recorder
  confound** (docs/14 §14.4). Stage 1's retrain is the fix under test. A pattern space
  built on a recorder-organized embedding would cluster microphones, not songs.

## P0 — Depth harvest (the unblocker)

This stage gets 20–50 recordings each for ~100 chosen species. The cache retains the
audio (owner exception). The selection favors species with documented syntax cases:
chickadee chick-a-dee, Japanese tit ABC-D congeners, starling mimicry, sparrow
dialects. It also weighs repertoire depth and playback anchors already in the
inventory.

**This one action unblocks P2, P4, and the spectral bench at the same time. Nothing
else on this page does that.** Debug: `subset --diverse` already exists for choosing
the bench species honestly.

## P1 — Grammar model comparison (can start now, on debug data)

Pre-registered bake-off on the deepest species we already have. The contenders: current
first-order transitions vs **Jin–Kozhevnikov** (repeat-count-dependent transitions, the
minimal sufficient model for finch syntax) vs **POMM** (partially observable Markov).
Metric: held-out bout likelihood + transition entropy, same bouts, same splits.

Ship only the winner. A wash keeps first-order, and this doc records it. This needs no
new data. It is a model question, and the mechanics are debug-testable today.

## P2 — Song-level embedding (lens #5)

Whole bouts as points: syllable-type tokens + measured gaps + tempo. Start with a
parameter-free sequence kernel (edit distance over token×gap sequences) before any
learned encoder. The critic's own discipline says the hand-written baseline comes
first, so the learned one has something to beat. Pre-registered: kNN lift by
species vs by individual vs by recordist (the last must stay ~0 or Stage 1 failed
upstream). **Blocked on P0 (bouts per bird) and Stage 1 (invariance).**

## P3 — CETI-style factorization

Decompose each deep species' songs into independent axes: rhythm, tempo, rubato,
ornamentation. Sperm-whale codas factorized into a 156-unit alphabet the same way
(Sharma et al. 2024). The raw material already exists: typed tokens, measured gaps,
contour shapes. Deliverable: per-species combinatorial alphabets and their usage
statistics. This is the strongest honest claim available without playback.

## P4 — Dialect & individual maps

With P0 depth, place same-species song variants geographically. The white-crowned
sparrow dialect literature and Otter 2026's continent-wide song takeover are the
template. Separate individuals where 10–16 bouts each exist (literature-proven
sufficient). The galaxy gains a song-level view beside the syllable one. The two-map
discipline (`--clustering both`) applies to it from day one.

## P5 — Function propagation through syntax

The playback anchors stay the only proof. What patterns add is *channels*. A motif that
appears in the same sequence position across individuals is a stronger function
candidate than a bare acoustic match. The pipeline propagates it as exactly that: a
candidate, with shares and a confidence label.

## P6 — Unknown-bird syntax

The arrival pipeline extends upward: U* syllable candidates → sequence statistics
over time → candidate song types for birds nobody has documented. Everything above
the syllable stays `unlabelled: real acoustics, no documented function`.

## Order and gates

**Now:** P1 (no new data needed). **After Stage 1's verdict:** P0 (deliberate
harvest). **After P0:** P2 → P3 → P4. **Continuous:** P5, P6 as each layer lands.
The debug store judges each stage with both maps built, and the project writes a
negative result down instead of deleting it.

## P1 result (2026-07-31): the grammar bake-off — first-order stays

`syntax.py` + `birdy-pipeline syntax`, run on the debug store (30 qualifying
species, 3 750 bouts ≥ 3 tokens, seeded 80/20 bout splits, add-α 0.1 backoff,
deterministic — two runs bit-identical). The pre-registered table:

| model | mean ΔLL/token vs first-order | species won |
|---|---|---|
| M2 repeat-count (Jin–Kozhevnikov) | **−0.348** | 0 / 30 |
| M3 hidden-state HMM (K ∈ {4,8,16}) | **+0.422** | 29 / 30 |

By the letter of the rule M3 wins. **The decomposition is the honest reading, and
it reverses the adoption.** Split the held-out tokens into transitions seen vs unseen
in train. On the 90 % seen, first-order is the best model (−1.525 vs M3's −1.624
nats/token, better in 15/30 species, M2 worse in 25/30).

M3's whole advantage comes from the 10 % unseen tail, where M1 pays −9.25 and M3
only −4.16 nats/token. That is a property of smoothing *shape* (a mixture predictive
is heavy-tailed), not of recovered hidden structure. So:

- **First-order stays the shipped model.** M2's mechanism fragments counts on this
  corpus and adds nothing. M3's win is real as scored and meaningless as structure.
  Adopting a heavier model for a smoothing artifact is the wrong lesson.
- **The one real weakness the bake-off exposed is M1's unseen-transition backoff**
  (−9.25 nats/token on a tenth of held-out transitions). A repair, such as softer
  unigram backoff or Kneser–Ney-style continuation counts, is a *smoothing* fix.
  Judge it on its own pre-registered terms, not smuggled in as a model upgrade.
- **Re-run after the depth harvest (P0).** At current depth ~10 % of held-out
  transitions are unseen. Depth shrinks that tail and may change the picture. Thin
  data is exactly where higher-order models starve (M2's 0/30 says so).

### The backoff repair (same day, pre-registered separately) — shipped

`FirstOrder` in syntax.py gains `backoff="continuation"` (Kneser–Ney lower order:
P(next) ∝ distinct contexts `next` followed, add-α to uniform, seen contexts
bit-identical to the old row). Gate: ≥ +1 nat/token on unseen-*context* transitions
with seen-side loss ≤ 0.01. **Passes on both debug corpora**: +1.90 (37-species
store) and +2.32 (debug-100) nats/token, seen loss exactly 0.0000.

Two honest caveats. First, 80 % of the unseen tail is *seen context, unseen
continuation*, outside the repair's scope, so the full-tail gain is +0.37/+0.65, not
the +1.9 headline. Second, the repair narrows the HMM's unseen-tail advantage, which
confirms that M3's "win" was smoothing shape. The shipped grammar artifact is
untouched either way. The repair improves the *measurement baseline* future bake-offs
are judged against.

## P2 result (2026-07-31): the song-level kernel baseline does not hold

`songspace.py` + `birdy-pipeline songspace`: bouts as (type, gap) sequences, with a
weighted edit-distance kernel. Substitution/indel costs 1, and the match
cost |Δlog gap| is priced inside the DP, so the edit path *is* the rhythm alignment.
The pre-registered rule judges it: species kNN lift must beat bag-of-types over the
same bouts AND recordist lift must stay < 0.05. **It fails both gates on both debug
stores:**

| store | species lift, kernel | species lift, bag-of-types | recordist lift |
|---|---|---|---|
| harvest-test (37 spp, 3 750 bouts) | +0.877 | **+0.924** | **+0.264** |
| harvest-100 (100 spp, 889 bouts) | +0.050 | +0.081 | **+0.087** |

Post-hoc exact-kNN (no MDS) reproduces the lifts, so the loss is not an
embedding-truncation artifact. The measured details, each worth keeping:

- **Within-species song structure exists**: 18/18 deep species separate recordings
  clearly (parus_major +0.68, cuculus_solitarius +0.43, strix_aluco +0.27). But
  bag-of-types matches it almost everywhere. The structure is already entirely in
  the token marginals. **Order and rhythm add nothing measurable at current
  depth.** This is the P0-depth caveat, confirmed from a second direction.
- **The rhythm term costs** species lift (ablation w=1: +0.877 vs w=0: +0.896).
  It prices variation the corpus does not organize by.
- The recordist gate failure is corpus composition: recordist ↔ species/geography
  correlate, and bag shows the same lift. The gate keeps its failure status per the
  pre-registration. The mechanism is visible in the baseline's identical number.
- **The bar for any learned song encoder is bag-of-types (+0.924), not the edit
  kernel.** Depth is the real unblocker. A learned encoder is unpromising
  until then. This slot in the roadmap is now "beat bag-of-types, after P0".
- OOM receipt: `geometry._silhouette` builds an (n,n,d) diff — 212 GB at
  4 000 × 1 658 dims. That is what took the host down twice today. The statistic
  survives at rank ≤ 128. Flagged for the next high-rank use of `geometry.measure`.

## P1 re-run after P0 (2026-08-01): M3 wins again — and now against the repaired M1

Same bake-off, same pre-registered rule, on the deepened store (P0: median 29
recordings/species for the target 100). **Qualifying species went 30 → 104**
(the depth harvest's whole point; the debug-100 store had 12). Results:

| model | mean ΔLL/token vs M1 | beats M1 on | verdict |
|---|---|---|---|
| M2 (repeat-count) | −0.1736 | 17/104 | does not win |
| **M3 (hidden-state)** | **+0.4976** | **78/104** | **WINS the rule** |

The adoption question this time is whether the edge is still smoothing shape,
because the M1 in the bake-off is the *unrepaired* one (unigram backoff —
`FirstOrder`'s default). The repair's own re-measurement on this store
(`syntax --compare-backoff`, same splits): the continuation backoff gains
**+0.1253 nats/token pooled** (seen rows untouched by construction; the
unseen-context bucket gains +2.60 and passes its adoption gate at full scale).
Subtracting on the shared protocol: **M3 beats the *repaired* M1 by ≈ +0.37
nats/token** — still well over the +0.1 gate, on 104 species with real depth.
The debug-era explanation (the whole edge is the unseen tail, M1 −9.25 vs M3
−4.16) cannot account for a residual that size: something closer to genuine
hidden structure is scoring better now that the data can support it.

What this does NOT yet do: ship M3. The inventory grammar is `learn_grammar`'s
raw first-order counts — there is no HMM-state grammar writer, and adopting
one changes what `learn` emits, what the app improvises from, and what
`song-typing` aligns against. That adoption needs its own pre-registered task:
per-species HMM decode → states as inventory grammar, judged against the
first-order inventory on the build's own numbers. Recorded here as the next
syntax task, with the number to beat: **+0.37 nats/token over the repaired
first-order, 104 qualifying species.** Also recorded: the inventory grammar
still ships raw counts — neither the add-α backoff nor the continuation repair
is in `learn_grammar`'s output table, a known gap the app currently papers
over with its own alpha at improv time.
