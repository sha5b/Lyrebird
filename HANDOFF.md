# Birdy — Session Handoff (2026-07-31)

**Landed today (uncommitted at this writing — user commits):**

- **AVEX arm-C bigger re-test: NO ADOPTION (docs/17 §17.6).** Pre-registered,
  63 both-domain species from the gan store (subset in /tmp, production store
  read-only), 16-species holdout vs §17.4's 3. **C's contrastive boost does not
  replicate** (+1.7 pts over B vs the +10 gate — small-sample structure, same
  lesson as the mel-weight probe); its §17.4 AUC drop reverses (+0.007). The
  honest corollary recorded in place: **B's merge win also shrank** (+3.6, not
  +14.4) and B's AUC reads *below* A's here — every §17.4 number was 12-species
  small-sample, in both directions. What survives is the ordering: data >
  mechanism at every scale tested. Machinery stays default-off.
- **Session quality gate ships as an honesty gate (docs/20 §20.3, second
  session).** Pre-registered three gates; measured on a real embed-space debug
  build of `out/harvest-b100` (= docs/20's store: 45 held-out recordings, 3 731
  eval rows) with the production inventory (331 k points, verified green).
  §20.1's structure reproduced exactly (8 bad sessions, all XC, 22.9 % of the
  flip loss). **G1 passes** (off-manifold 5-NN AUC 0.953; 256 anchors ≥ 0.92);
  **G2 fails raw** (+3.5 pts vs +5 bar; tie-adjusted +8.7–13.7) so the
  pre-registered fallback fires: `sessionGate` (anchors + k + threshold +
  calibration text) ships in feature-space.json's embedding block — **app-side
  hookup DONE same day**: `SessionGate` in features.ts (brute-force 5-NN,
  exact vs reference at 1e-9), fed from the mic path only (the chorus crosses
  the same bus; corpus audio would never flag), published through `onMeters`,
  and first branch in the Reading panel — "off the map: this session is off
  everything the galaxy knows; positions are guesses" with the score-vs-line
  numbers and the shipped calibration text, outranking inferred call names but
  never scheduled (known) songs. Absent-gate assets are a byte-identical no-op;
  verify-features.mjs asserts renders-don't-flag/noise-flags once a gated build
  is linked. npm check 4/4 baseline, verify:features pass, parity 18/18. Not
  browser-click-tested. **G3 fails** (fit-side
  pruning costs −0.006/−0.015 cosine: weird sessions are manifold coverage).
  `mapQuality` gains `centroidAgreementTieAdjusted` + `speciesAgreement`
  (§20.2's margin-aware fields). New instrument: `build --dump-spacemap-eval`.
  Calibration trap recorded: fit-side thresholds don't transfer to unseen
  sessions (29 % flag rate) — the shipped line is calibrated cross-half.
  **Verified end-to-end**: rebuilt assets green (`verify` all checks), shipped
  operating point on held-out recordings: 8/45 flag, 5/8 bad caught incl. the
  three worst loss-carriers, 3 clean false-flags all within 0.02 of the bad
  line. Two build-time bugs of this change were caught and fixed en route
  (np.unique return-order swap; a `counts` local clobbering build_galaxy's
  cluster sizes — both mine, both fixed before the green build).
- **Build cost structure mapped (low-end-machine question, explore report in
  session log).** The 33-min build was UMAP single-threaded (`random_state`
  kills numba parallelism) + ~22 brute-force kNN passes in the relations
  battery — at 331 k points, not 56 k (the production inventory was used).
  Lean debug path now in AGENTS.md: `--no-relations --no-compare-projections`.
  Ranked proposals (mechanism mostly exists): sequence battery after build via
  `critic groupings`; hoist the geometry kNN graph per space; parallelise
  render/descriptor loops with learn's proven fork-pool (renders independently
  seeded, order-preserving → bit-identical); add a learn resume reader
  (checkpoints written, never read); free clip audio during descriptor
  extraction (several GB RSS); `--epochs 30` critic for CPU boxes. **Shipped
  from that list:** the silhouette (n,n,d) diff is now the Gram form
  (geometry.py `_silhouette` euclidean branch — the 212 GB OOM shape is gone,
  value-equivalent at 5e-7, groupings battery bit-identical). Deliberately not
  done: gating relations.json on `--no-relations` — the flag skips analysis,
  relations.json is a cheap shipped asset the app consumes.
- **Dangling dev symlinks removed** (app/static/birdy/{known,unknown} → the
  wiped /tmp/birdy-debug) — they were the app's ENOENT on startup; absent
  subdirs restore the old single-map behavior. Re-link to fresh debug assets
  when wanted.
- **OWNER RULE (restated twice today, now in AGENTS.md): debug-100 only, always.**
  No production builds, no full harvests, no bulk network sweeps. All work is proven
  on the 100-species debug subset (`subset --species 100 --out /tmp/...`). A
  production build on the full corpus OOM'd the machine this afternoon (500k+ points
  after rendering the 2 423-species inventory — the debug builds at 45-56k were
  fine); the Stage-0 chain was killed before the build step. Steps 1-3 of that chain
  (learn/respfit/docrefit) had already written their data/ artifacts and are left
  in place, unbuilt.

- **Spectral bench — the uncomfortable finding (docs/19, `specbench.py` +
  `birdy-pipeline specbench`):** the 28-d resynthesis cosine, the pipeline's
  universal fit objective, does NOT correlate with audible spectral distortion
  (Pearson/Spearman ≈ 0.1 vs both MCD and multi-res STFT, n=200 on debug-100 vs the
  iNat cache; robustness: recomputed cosine matches stored at 0.921, MCD↔STFT agree
  at 0.925). The cosine keeps its proven role as the *clustering* statistic;
  respfit/docrefit/fricative adoption gates now carry the caveat; the **mel-patch
  fit target is promoted to the priority** (objective = audible metric at last), and
  future fit gates read the bench. Stage-1's invariance verdict is unaffected
  (judged on kNN lift, not cosine).
- **P2 song-level kernel baseline: DOES NOT HOLD (docs/18 P2 result).** The
  token×gap edit-distance kernel loses to bag-of-types on species lift (+0.877 vs
  +0.924 on harvest-test; +0.050 vs +0.081 on debug-100) and fails the recordist
  gate (+0.264/+0.087 vs < 0.05). The useful findings: within-species song
  structure EXISTS (18/18 deep species separate recordings) but lives entirely in
  token marginals — order and rhythm add nothing at current depth; the rhythm term
  *costs* lift; the bar for any learned song encoder is bag-of-types, after P0.
  OOM receipt: `geometry._silhouette` builds an (n,n,d) diff (212 GB at 4 000 ×
  1 658) — that is what took the host down; rank ≤ 128 is safe.
- **Serial execution rule (owner): one heavy agent/job at a time** — the OOMs
  killed VS Code twice with two agents running. Queue: mel-patch fit target
  (running), then Stage-1 follow-up sweep, then serve store fix.
- **Stage-1 follow-up sweep: NO ADOPTION, road exhausted (docs/17 §17.5).** The
  recording-within-species adversarial target shipped default-off
  (`CriticConfig.record_within_species`, `critic train --record-within-species`):
  classes are recordings of species holding ≥ 2 of them, softmax masked to the
  patch's own species. Pre-registered 5-arm sweep on the §17.3 store with a
  fresh baseline (fake side drifted with the Stage-0 inventory): **the
  factorization works** (species lift never drops — flat to +10 %, unlike the
  recordist head's 1:1 trade) **but the target doesn't reach the confound**
  (recordist lift −6 % at w 0.1 vs the −30 % gate, and that arm already fails
  the AUC gate). Reading: the recordist signal is *between*-species, so a
  species-factored head is forbidden from touching it. With §17.3 (buy it 1:1
  with species) and §17.4 (buy real invariance with data, +14.4 pts) the
  loss-engineering road is closed at both ends — invariance is a data action.
  That clears all three queue items (mel-patch, this sweep, serve fix).
- **Spacemap 0.66 decomposed: metric problem, not a map problem** (docs/20).
  76 % of the loss is boundary near-ties (tie-adjusted agreement 0.91; 41 % of
  flips land on the runner-up knot); genuine big-margin map failure is ~2 % of
  rows; 8 bad xeno-canto sessions carry 24 % of the loss. Direction: margin-aware
  + species-level agreement in mapQuality, live claims at species level (0.78),
  knot-level claims labelled "nearest of several close knots"; NO ONNX/bridge
  work; the double-digit lever is per-session quality gating on bad XC sessions.
- **Fidelity verdict: the premise holds, with a blend (docs/19 §19.4).**
  `learn --mel-weight W` (wired end-to-end, default 0 = bit-identical, serial ==
  parallel verified): the mel-path objective tracks audible distortion at Spearman
  −0.42 vs the cosine's +0.10 (n=200). Pre-registered w=1 wins 7/10 on MCD (+5.6
  dB) but the cosine guardrail collapses — **w=1 must not ship; w=0.5 is the
  measured candidate** (MCD win survives, guardrail holds; exploratory, n=10).
  Default learn behaviour unchanged; adoption is the owner's call after a bigger
  probe.
- **Adoption-gate probe (n=80): NOT adoptable (docs/19 §19.5).** The 10-type probe
  was small-sample luck: w=0.5 wins only 31 % of types on MCD (gate 60 %), median
  ΔMCD exactly 0.0 (mostly converged already), one type loses 0.12 cosine. The
  honest state: **measure spectrally (bench/MCD for gates), optimise on the cosine
  (bounded failure, cluster-safe)** — an objective that is both remains unfound.
- **Serve store-trap fixed + server bug sweep** (server.py +119, cli.py serve
  parser): no-flag `serve` now announces its store (path, syllables, species) and
  warns per newer sibling store ("harvest-d100 was modified more recently — did you
  mean --store ...?"); explicit `--store` unchanged. Fixed two real crashes:
  `status()` dying on a half-written learned inventory/manifest.json during the
  1.5 s poll. Sweep found nothing else worth surgery; 7 cosmetic/perf items
  REPORTED-ONLY in the session log. AGENTS.md serve note updated.
- **AVEX verdict: data wins, mechanism doesn't** (docs/17 §17.4):
  naive merge of both domains (**12** shared species — horornis_diphone has zero
  xeno observations, not 13) buys +14.4 pts cross-domain species retrieval with
  AUC/accuracy held (gate PASSED); the cross-domain contrastive pairing reaches
  +27.8 but drops realism AUC 0.012 (gate FAILED, re-testable bigger). Domain
  grouping lift ≈ 0 in all arms — the confound lives in the retrieval gap, not
  local geometry. **Invariance is a data action**: more domains per species, not
  more losses. Machinery in critic.py, default-off.
- **`build --clustering both`**: one render writes `<out>/known` (kmeans, every type
  named) + `<out>/unknown` (hdbscan, discovery view), each a complete verified asset
  set. **This is the debug cycle's default now** — the known and unknown views of a
  corpus are always comparable side by side. Verified on the debug store (56 284
  points: known 1 024 clusters/purity 35.9 %, unknown 136/purity 8.6 %).
- **UI gains piped in** (app-side, npm check 4/4 baseline, parity 18/18):
  known/unknown map switcher (auto-detected when `<assets>/{known,unknown}` both
  exist — segmented "Name everything"/"Find the unknown" toggle in the galaxy
  corner stack, active state derived from the loaded manifest's `clustering` field,
  full reload via the exercised reloadGalaxy path, reload-loop edge handled, absent
  subdirs = byte-identical old behavior); Reading-panel honesty line per map
  ("this view cannot report an unidentified sound" vs "N of M sounds sit in no
  region — unidentified: real acoustics, no documented function"); fit-quality
  copy now says the cosine is a clustering match with audible fidelity measured
  separately on the bench (docs/19). Dev symlinks at app/static/birdy/{known,
  unknown} → /tmp/birdy-debug/assets-100 (gitignored). Not browser-click-tested.
- **Stage 1 verdict: NO ADOPTION (documented, docs/17).** The machinery is in
  critic.py (channel-EQ, MixStyle, recordist-adversarial head — all default-off),
  plus `critic groupings` (the battery without a build) and a recordist probe in the
  report. The sweep: augmentation alone is species-safe but moves recordist lift
  −0.7 % (nothing); the adversarial head trades ~1:1 (−33 % recordist at w 0.05 with
  species accuracy −14.7 pts; w 0.3 destroys the embedding). Next attempt's leads:
  recording-within-species as the adversarial target, and the channel cue is not
  band-response-shaped.
- **`docs/18-syntax-roadmap.md`**: the pattern/syntax line made explicit — P0 depth
  harvest → P1 grammar bake-off (first-order vs Jin–Kozhevnikov vs POMM; can start
  now, no new data) → P2 song-level embedding (gated on P0 + source invariance) →
  P3 CETI-style factorization → P4 dialect maps. Structure first; meaning only from
  playback.
- **P1 done, first-order stays** (`syntax.py` + `birdy-pipeline syntax`, docs/18 P1
  result): M2 repeat-count loses decisively (−0.348 nats/token, 0/30 species); M3
  HMM wins the pre-registered rule (+0.422, 29/30) **but the decomposition reverses
  adoption** — on the 90 % seen transitions first-order is best, and M3's whole edge
  is the 10 % unseen tail (M1 −9.25 vs M3 −4.16): smoothing shape, not hidden
  structure. Recorded follow-up: repair M1's unseen backoff as a *smoothing* fix,
  re-run the bake-off after the depth harvest.
- **Backoff repair shipped** (same day): `FirstOrder backoff="continuation"`
  (Kneser–Ney continuation counts) passes its gate on BOTH debug stores (+1.90 /
  +2.32 nats/token on unseen-context transitions, seen side bit-identical).
  Full-tail gain is +0.37/+0.65 (80 % of the tail is seen-context, out of scope) —
  and it narrows the HMM's tail advantage, confirming M3's win was smoothing shape.
- **Debug-100 cycle run end-to-end** (/tmp/birdy-debug/harvest-100): subset → learn
  (100/100 species fitted) → bake-off re-run (M3 wins the rule again at +0.240, but
  only 12/100 species have ≥ 20 bouts — the depth ceiling in one number) →
  `--clustering both` build. The user's full-harvest stop stands: depth work uses
  debug stores, no bulk network harvests. **Embed-space note:** the descriptor-space
  unknown map degenerated on this corpus (3 clusters, one holding 95 % — iNat
  soundscape is one density blob in 28-d); the embed space has real structure (98
  clusters, 53 % unassigned, both verifies green) and the known map improved with it
  (purity 29.1 % → 41.6 %). Debug builds should pass `--space embed` once
  embeddings.f32 exists (auto does, now that the store holds it).

**Earlier same day (committed e242f88):**

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
