# Birdy — Session Handoff (2026-07-31)

**Landed today (uncommitted at this writing — user commits):**

- **Stale-embeddings crash fixed.** The Learn-tab `ValueError: cannot reshape …
  (39999,newaxis)` was a stale `embeddings.f32` against a changed store, hit at five
  `reshape(len(store.syllables), -1)` sites in cli.py. New `read_store_embeddings`
  checks row counts and says to re-run `critic embed`; build falls back to embedding
  on the spot, placement/spacemap/relations exit 2 with a clear message.
- **1024-cluster cap no longer unseeds the build.** The `WARNING: clamped to the cap`
  build was worse than the warning said: over the cap, `type_seeds` returned None and
  the build fell back to *unseeded* k-means — every type's seed lost at once. Now
  `type_seeds` triages: source-split second knots shed first, then thinnest learned
  types, a documented call's knot last. Debug build (1 287 wanted / 1 024 cap): all
  648 types kept their knot, 254 lost only their second. Full 12 724-type corpus
  still exceeds any sane cap — that's the spacemap question, not a cap tweak.
- **`docrefit` — the one-tone documented re-fit shipped** (docs/16 §16.4 status note
  has the numbers). Debug store: 14/15 one-tone calls gained measured noise/rough
  (owl `hooLong` → noise 0.05, rough 0.65, +0.052; gate held at +0.013 on the one
  holdout). Production run waits on the production learn.
- **Galaxy legend**: a "?" button under the Display toggle opens "Reading the galaxy"
  (points / knots / distance / hue / wave / thread / violet), app-side, `npm run
  check` clean.
- **Learn-tab review**: nothing obsolete; the "Fit syllables and syntax" button earns
  its place (refit without re-harvesting, e.g. after a critic retrain) and already
  sits inside the collapsed "run one step by hand" section.
- Other agent (same day): `subset --diverse` (k-medoid pick; beats top-N and
  farthest-point on mean-distance-to-nearest, 3.125 vs 3.813).

**Research sweep landed** (birdsong syntax/meaning, recorder-invariant embeddings,
known→unknown transfer): the actionable stack is training-time invariance (DIR
impulse-response augmentation + domain-invariant contrastive losses, AVEX: corpus
diversity > architecture) and CETI-style structure-first semantics. Report is in the
session log; candidates for docs/17.

# Birdy — Session Handoff (2026-07-30, end of day)

**The day in one paragraph:** the corpus grew 36 → 3 811 species (iNatSounds, 6 453
recordings, 6.3 GB audio cache), the critic retrained to 2 686 species (novelty ROC
0.846 / TPR 32.2 %), the learn went parallel+streaming (2 423 named species, 12 724
types, bit-identical, ~12× faster), the synth gained respiration + two-voice +
shaped fricative noise (parity 18/18, all default-off pending per-species fits),
Perch 2.0 label-novel works offline, and the app went through a full UI cycle:
Compose tab, wave activations with real data provenance, color language (points =
provenance, labels = species hue), camera snap, listen modes, and a debug-100 build
discipline that caught and fixed a dozen real issues. Evidence: docs/16 (+12–15).

## Shipped, with the headline numbers

| What | Key measurement |
|---|---|
| iNatSounds ingest | 6 453 rec, 226 264 syllables, 3 811 species, drift 0.048 sd; **audio cache** (owner exception, AGENTS.md) |
| Critic retrain | 2 686 species / 895 held out; realism 1.000; **novelty ROC 0.846, TPR 32.2 %** (14.8 → 22.3 → 32.2 % across three epochs) |
| Parallel + streaming learn | **bit-identical to serial**; ~3 h → ~15 min; 2 423 species, 12 724 types, **all real common names**; progress + checkpoints |
| `grammar.gaps` | 26 897 measured per-transition gaps — no invented rhythm left |
| B1 respiration / B2 two-voice | parity 16/16; both **default-off** (hand-set defaults don't win; per-species fit is the pre-registered answer) |
| **Fricative path** (shaped noise) | noise through the syllable's own formants, one pressure gesture; bench **0.584 → 0.656**, end-to-end **13 wins / 0 losses**, ships per-type where it wins; parity **18/18** |
| Perch label-novel | ONNX offline, ~48 ms/window; 23 697 novel syllables identified; metadata only ("closest documented species, unverified") |
| Debug-100 build | 45 592 pts, 1 024 clusters, **0 % unassigned**, verify green, shards live (55 MB → 312 KB) |
| UI | Compose tab (3 modes), distance-ordered wavefront + signed ripples + dense-knot bloom, provenance points + species-hue labels + trajectory gradients, unmatched grey-breath state, camera snap, mic/system input + device picker, tempo-lag fix, solo-chorus/click-away/button fixes |

## The honest findings (the ones that hurt)

- **Fricative syllables were the biggest acoustic gap**: real chip notes are filtered
  noise bursts; our renders were tonal (or the fit parked at `noise=0.85` and still
  failed: nuthatch cos 0.16). §16.7's shaped noise fixes the *shape*; most sub-0.3
  types are a different, unfixed gap.
- **The tracker inferred positions for notes it knew were unplaced** ("ripple from
  the center") — fixed: known-unplaced beats inferred.
- **B1/B2 hand-set defaults don't beat the envelope** — the physics is right, the
  per-species fit is what's missing (fit pass mechanics proven: gate holds, only
  winners ship).
- **Coverage**: 71 % of types have knots on the debug build; 33 authored calls own
  no points. Data depth, not machinery.
- **Embedding's strongest structure is still recorder, not bird** (+0.488 vs
  +0.196, docs/14 §14.4) — the source-invariance question rides on the next retrain.

## The roadmap to a real translator (baked in, honestly ordered)

An embedding is its objective made visible; we own four lenses (28-d descriptor,
critic 32-d, Perch 1536-d, song-sequence space). The path to *syntax discovery and
a translator for unknown birds*:

1. **Perch-vs-critic RSA/CKA** — external second opinion: novelty agreement, and
   whether recorder-clumping is our critic's artifact or acoustics.
2. **Dialect/individual discovery** — corpus finally supports it (10–16 individuals
   per species is literature-proven separable).
3. **Song-level embedding for structure** — dialect variants, shared motifs,
   "sing it as \<bird\>" (relations.json ready: 6 441 pairs).
4. **Function stays at syllable level** — a dozen playback anchors, propagated only
   as candidates with shares; playback is the only proof, always.
5. The unknown-bird pipeline is live end-to-end: arrive → type by similarity →
   cluster into U* candidates → Perch labels as metadata → syntax measured over
   time. Anything more confident than that is numerology (§8.5).

## Open items for next session

1. **Full 2 423-species production build** (deliberate; debug cycle first proved it).
2. **Per-species fit pass completion** (respiration/two-voice full-store run) →
   **one-tone documented re-fit** (owl's `hooLong` et al. get measured noise/rough).
3. **Quality-weighted fit** (agent running at this writing: SNR + clipping at
   ingest, weighted exemplars, "fitted from N, M clean").
4. **Full label-novel run** (23 697 novel syllables).
5. **App-side**: relations overlay + "sing it as \<bird\>"; unlabelled-arrivals live
   view; legend/copy check against the final color language.
6. **Serve default-store fix** (caught on the wrong store twice).

**Operational reminders:** `learn --jobs N`; debug cycle =
`subset --species 100 --out /tmp/…` → learn → build; restart `serve` after pipeline
code changes, always `--store out/harvest-gan`; verification runs to `/tmp`;
audio cache is local-only and dies with the training phase.
