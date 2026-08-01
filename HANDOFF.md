# Birdy — Session Handoff (2026-08-01, label assignment)

**In one paragraph:** the production knot problem now has its instrument.
`build --clustering label` (docs/22 §22.8) stops clustering the 96 % of points that
already carry a type and gives each type its own knot, fitting kmeans only over the
points with no label. It builds, it verifies, and **type coverage is 100 %** where the
shipped kmeans build reaches 92.6 % on the same corpus. It also **failed its own headline
gate against the uncapped build** (+2.5 points of type retrieval against a +10 bar), and
it costs 5.9 points of species agreement in the live path. Both are in the doc, and both
are why it ships as a flag rather than as the default.

- **`--clustering label`: ADOPTED as a flag, not a default** (docs/22 §22.8,
  `galaxy.label_assign` + `galaxy.self_test`). Every labelled point goes to its own type's
  source blob — `_type_blobs`, now the *one* partition the seeding and the assignment both
  read, pinned by a self-test the build runs at start — and kmeans fits only the untyped
  remainder. Cost is O(n) plus that remainder: **0.2 s against 65 s** on the debug matrix.
- **Measured on §22.6's fixed matrix, through the shipped functions.** The harness is
  validated twice before any arm is read: the k = 1 024 row reproduces §22.6's base row
  exactly (purity 0.4232, coverage 0.4260) and the k = 4 298 row reproduces the shipped
  debug manifest (0.5797 / 0.9258).

  | arm | k | purity | type coverage | **type retrieval** |
  |---|---|---|---|---|
  | kmeans, uncapped (as shipped) | 4 298 | 0.5797 | 0.9258 | 0.5775 |
  | kmeans at production's shed ratio | 1 264 | 0.4601 | 0.5114 | 0.4599 |
  | kmeans, k = 1 024 (§22.6 base) | 1 024 | 0.4232 | 0.4260 | 0.4227 |
  | **label assignment** | 4 298 | 0.9988 | 1.0000 | **0.6020** |

  **Type retrieval** is the new statistic and the only one of these that still measures
  anything under label assignment: for each point, is the nearest centroid by cosine — the
  lookup `SpectralMatcher` performs on live audio — a cluster whose name is that point's
  own type. Purity and coverage are identities here (a type *is* a cluster); the manifest
  now says so in a `clusterPurityNote`, because 1.0 read as a good map is reading the
  definition back.
- **The pre-registered gate FAILED where the cap does not bind.** +2.5 points against the
  uncapped kmeans build, gate +10. The mechanism it was predicted from is types shedding
  their only knot, and at `K_CAP` 8 192 the debug corpus wants 4 298 and gets all of them.
  **On a corpus that fits under the cap, seeded kmeans is nearly as good as knowing the
  answer** — a real result about the seeding, and the argument against a default. It
  passes at production's shedding ratio (k = 1 264, **+14.2**) and at k = 1 024 (**+17.9**),
  which is the condition production is actually in: 27 862 wanted against 8 192.
- **A ceiling the cap was hiding.** Even with every type owning a knot, type retrieval is
  **0.602** — for 40 % of points the nearest centroid belongs to another type. That is the
  embedding's own confusion, not the clustering's, and the kmeans arm could not show it
  because a type with no knot cannot be retrieved at all. It is the honest bound on "sing
  and the right knot lights", it is now measurable at every k, and raising it is docs/23
  W1/W6 work, not clustering work.
- **The live-path cost, measured on the built assets.** Against the kmeans build of the
  same corpus: centroid agreement **0.6572 → 0.6316**, species agreement **0.7421 →
  0.6831**, tie-adjusted **0.8032 → 0.8136**. More near-ties, not worse decisions —
  centroids at label means are less separated than centroids Lloyd's pushed apart. Anyone
  switching a build whose headline is the species claim should read that row first.
- **Built and verified end to end**: `/tmp/birdy-debug/assets-label`, 214 154 points,
  k = 4 298 (2 143 types all source-split + 12 for the 300 song-level points), 375 s after
  the render, `verify` all checks passed, **type coverage 2 143/2 143**. The app says what
  it is: the manifest carries `clustering: label`, its `kmeans` block states that kmeans
  fitted the unlabelled points only, and the Reading panel's map line reads "the knots are
  the labels, not a second finding". `npm run check` at the 4 known baseline errors.
- **What still blocks the production build, and it is no longer the clustering** (this
  supersedes decision 2 of the entry below — the instrument it asked for now exists). k would
  be 27 862 (27 762 type blobs + 100), which the renderer's cluster-state texture takes
  without complaint (1 024 wide, 28 rows). `centroids.json` is the wall: **1 596 bytes per
  cluster measured**, so about **44 MB**, written whole and loaded whole by the browser.
  The fix is the one `inventory.json` already had — shard it, or move the two float
  vectors to an `.f32` sidecar beside `point-features.f32`. The build prints the projected
  size whenever k passes `K_CAP` rather than shipping the surprise.
- **Correction to the entry below:** the shipped debug-100 assets are purity **0.5797**,
  not 0.423 — 0.423 is the k = 1 024 figure from §22.6's table, carried into the paragraph
  about the 4 298-cluster build by mistake. The manifest has said 0.5797 since it was built.

# Birdy — Session Handoff (2026-08-01, data audit)

**The day's second half in one paragraph:** the data was audited against the code that
produces it, and four of the six proposals died on their own pre-registered gates. Songs:
repeat classes ship and take the corpus from 48 species with a real song to 98, with the
shuffle control unmoved. Knots: neither cheap fix works, and the arm that does work is
the one that was flagged as the owner's call. The Learn tab was found running a
configuration the command line abandoned, and was fixed. Evidence: docs/22.

- **Repeat classes: ADOPTED, default on** (docs/22 §22.2, `learn.SONG_MIN_REPEATS`).
  `_collapse_runs` reads a trill as one token, which then falls under `SONG_MIN_MOTIF` —
  so a bird whose song IS a trill could never have a song type. 19 738 of 34 696 bouts
  (57 %) collapse to one token and **6 940 of those are 3+ syllables**. A repeat class is
  one collapsed string heard 6+ times in bouts of 3+ syllables, matched by equality
  (equality cannot chain, which is the noise mode the motif gate exists for), carrying
  `kind: motif | repeat` so nothing downstream has to infer the claim. Measured on the
  production store: **species with a song 48 -> 98, song types 96 -> 356, placed bouts
  1 052 -> 3 741, shuffle control unchanged at 0.170 %** (bar 0.2 %). The control finds
  no repeat classes at all — shuffling destroys runs — which is the sharpest evidence
  available that the ones found are real. **Needs a `learn` run to reach the inventory.**
- **Per-species recurrence bar: REFUTED** (docs/22 §22.3, `floor=`, off). Letting each
  species set its own bar on its own shuffled tokens let 2 398 of 2 421 species take the
  loosest one — a species with 8 candidate bouts has a control too small to ever place a
  bout, so "the control found nothing" meant "the control had nothing to work with"
  (control 0.170 % -> 0.442 %). Adding a power requirement fixes the mechanism but not
  the verdict: **no candidate requirement in {10, 15, 20, 30, 50} returns the control to
  0.2 %** (0.399 / 0.378 / 0.378 / 0.356 / 0.266 %), and the rows that come closest gain
  nothing over the 98 species repeat classes already reach. Machinery kept, refutation
  recorded in the constant.
- **Per-species bout rule: REFUTED** (docs/22 §22.4, removed with its flag). 5x the
  species' own median gap reaches 105 species against 98, at **0.628 % control yield**.
  Splitting a fast singer's bouts finer makes more short strings, and short strings are
  what chance chains. **The three refuted flags of this day were then removed** —
  `--adaptive-bouts`, `--song-floor`, `--deflate-source`, plus the dead `--source
  harvest` shim and the code behind each. The measurements survive as docs/22's tables;
  a refuted policy nobody can reach is surface, not machinery. **What did ship: the bout rule was
  three separate literal `1.0`s** (`learn_grammar`, `bout_sequences`, `syntax`) for one
  rule the grammar, the chunk miner, the P1 bake-off and the song types must share. Now
  `learn.GAP_BOUT_SECONDS` plus one argument every caller takes, pinned by a self-test.
- **Knots — both cheap fixes FAIL, and the measurement says why** (docs/22 §22.6, one
  debug-100 `--dump-points` matrix, 214 154 points, every arm scored through the shipped
  `cluster_plan`/`type_seeds`/`_purity`/`label_cluster`). Pre-registered: seeds per type
  toward 1.0, purity and coverage no worse.
  - `--member-variants 0` (anchor only): seeds/type **2.000 -> 1.993**, i.e. no effect.
    **The source split is binary** — `_type_seed_means` splits whenever a type holds
    points on both sides, so 24 renders and 1 render split it equally. It does buy
    purity 0.423 -> 0.568 on 24 % fewer points, which is real but is not the mechanism
    that was predicted.
  - source-axis deflation: removes 42.0 % of the space's energy and drives the source mean
    gap **7.233 -> 0.0**, and **still every type splits** (1.999), with purity down 1.1
    points. So recorded-vs-synthesised is **not one direction**: the global offset is,
    the per-type geometry the seeding gates on is not. Ships off.
  - **What works** (`--member-variants 0 --no-member-anchor`, kept): render nothing for a type
    that has member observations — it already exists in the map as the real syllables
    `typing.json` assigned to it. Seeds/type **exactly 1.000**, wanted 4 298 -> 2 155,
    purity **0.577** (best), coverage 0.432 (best), 25 % fewer points. **Owner's call,
    not a default**: it gives up the rendered voice's own place on the map. And it does
    not undo the cap — 2 155 still exceeds k=1 024, so 1 119 types lose their only knot
    in every arm. The documented-knot column reads 0 in all arms because debug-100 is
    the deepest 100 species and holds no authored calls.
- **`K_CAP = 1024` is an app constraint, not a pipeline one.** The renderer declares
  three `uniform float[clusterCount]` arrays in its VERTEX shader — 3 072 vertex uniform
  floats, already past the WebGL2 guaranteed minimum. Raising the cap needs those three
  channels moved to a data texture first; `centroids.json` at 1.7 kB/cluster (23 MB at
  13 903) is the next constraint, and sharding already solved that for `inventory.json`.
- **Learn tab was not running the cycle — fixed** (docs/22 §22.7, server.py). It fitted
  **serially** (`_fit` never passed `jobs`; the pool is bit-identical and ~12x faster),
  left **stale embeddings** so the next tab build silently used the 28-d descriptor space
  instead of the 32-d one, ran the **relations battery every build** (the 33-minute
  phase; `--no-relations` skips the battery, not the shipped `relations.json`), and
  **shipped assets unverified**. Now: `default_jobs()` (cores-2, capped 8),
  `_refresh_embeddings` through the CLI's own `write_store_embeddings`, `--no-relations`
  by default with a `relations` opt-in, and `verify` as part of the job. Restart `serve`.
- **Still not on the tab:** `subset` (so the tab structurally cannot obey the debug-100
  rule — every tab build is a production build), `respfit`/`docrefit`, and the new build
  flags. Flagged, not done.

- **The cap was an app constraint, and it is gone — the silence with it.** The renderer
  declared the three per-cluster channels as `uniform float[clusterCount]` arrays in its
  **vertex** shader, so 1 024 knots cost 3 072 vertex uniform floats and `K_CAP` was
  really a WebGL limit wearing a pipeline constant's name. They now live in a
  `DataTexture` (`uClusterState`, RGB = activation/sung/learning, nearest-filtered,
  width capped at 1 024). `K_CAP` 1 024 -> 8 192. Rebuilt debug-100 at k=**4 298** with
  nothing shed: **type coverage 42.6 % -> 92.6 %**, and the symptom the owner reported —
  "sound plays, nothing reacts" — went from **26 songs that could light nothing to 1**
  (songs lighting every note 28 -> 85; song types referencing no knot 54 -> 6). Those
  assets are what `app/static/birdy` now holds (214 154 points, purity 0.423). 4 298
  clusters is itself the proof the texture works: the old uniform arrays could not hold
  it. **Production is NOT rebuilt at the new cap** — `/tmp/birdy-prod/assets-v4` is
  green but was built under 1 024 (7.0 % coverage), and production wants 27 862 seeds so
  8 192 still binds there; at that scale the answer is docs/22 §22.5's label assignment,
  not a bigger k-means.
- **Point-cloud performance: measured first, then fixed.** The per-frame CPU work is
  1.9 ms of a 16.7 ms budget at 214 154 points, so the frame is **not** CPU-bound and
  gating the attribute uploads would have bought nothing — the cost is GPU fill rate,
  two full-geometry passes of blended sprites. Fixed as: (1) the responding pass draws
  only points that can respond, via a shared-attribute geometry with a per-frame index,
  and is **skipped entirely** when nothing is sounding; (2) **knot-level LOD** — at
  galaxy distance the cloud draws **one representative per knot (1 024 points, 0.5 %)**,
  the member nearest its own centroid and never an average; 25 % at mid distance; all of
  it inside a bird, with a focused species always drawn whole. Points in no cluster draw
  at every level, because they are what the discovery map exists to show. Three levels
  built once at load, hysteresis band on the swap. npm check at the 4 known baseline
  errors, parity 18/18. **Not browser-tested — there are no renderer tests, and the
  fill-rate diagnosis is inferred from sprite count, so the first look is the real test.**

- **W1 RUN: NO ADOPTION, and it closes the road at a third end** (docs/23 §23.1.1,
  `batcheffect.py` + self-test, `analysis` extra). 20 000 syllables of the production
  embedding, 885 species / 1 001 recordists / 3 265 recordings, every arm scored by
  `geometry.measure` against its own null. **No arm passes the gate.** Three findings.
  (1) **The confound is not a location shift**: subtracting each recordist's mean leaves
  the recordist lift *higher* (0.1665 -> 0.1687) and costs a third of the species
  structure — which explains mechanically why §17.3 and §17.5 failed, since both
  attacked it during training where nothing can be inspected. (2) **Harmony reaches it
  and pays §17.3's exact price**: recordist lift -71 %, species lift -70 %, the same
  one-for-one trade as the adversarial head, by a completely unrelated post-hoc method.
  (3) **Correcting by recording removes both** (-74 % / -75 %) because a recording holds
  one bird of one species, so the labels are nearly nested. Together with §17.3 and
  §17.5 the road is now closed during training twice and post-hoc once, and the reason
  is visible: species and recordist are **confounded in the sample**, not in the model.
  §17.4's "invariance is a data action" is now a boundary, and the action is named —
  more recordists per species. Raises the value of W6's T1.
- **Two dependency repairs while doing it.** `harmonypy` and `pandas` are declared as the
  new `analysis` extra. And `docs/whitepaper/build_whitepaper.py` had **undeclared**
  dependencies (python-docx, matplotlib, pillow) installed by hand, so the first
  `uv sync` that did not name them removed them and the builder stopped importing; they
  are now the `whitepaper` extra. Sync line for a full working tree:
  `uv sync --extra critic --extra analysis --extra whitepaper`.

- **W2 RUN, and it is three results and one retracted test** (docs/23 §23.2.1,
  `seqstats.py` + self-test). On the production corpus, 34 696 bouts against docs/12's
  control: **the tokens are not arbitrary** — H(next | previous 1) is 0.941 bits against
  the shuffle's 3.343, which is the "are these units" question answered in the
  affirmative and the premise of P2/P3 surviving. **Menzerath does not hold** (median
  exponent +0.019; 45.7 % of species negative against the control's 8.5 %, so a weak
  effect in the law's direction but not the law). **NCD is refuted** — the control
  separates species *better* (0.038 vs 0.018), so compression distance reads alphabet
  and marginals rather than order, and no song encoder should be measured against it.
  **The second-order arm was a badly designed test and is recorded as one**: comparing
  the k=1→2 drop between real and control is invalid when the curves start 2.4 bits
  apart, and past k=3 the control's curve falls *below* the real one because a plug-in
  estimator reports near-unique contexts as determined. `_verdict` now refuses that
  comparison instead of returning the answer it would have returned. The honest
  instrument is docs/18's held-out cross-entropy, which is unbiased — so P1 stands and
  this arm needs re-running with it.

- **New plan written from the failures: docs/23.** Five workstreams, each naming the
  measured failure it attacks, the method, the gate stated before the run, and what a
  negative result would mean — with the methods taken from fields that solved the same
  problem on other data. W1 the recorder confound as a **batch effect** (Harmony/PLDA
  post-hoc on `embeddings.f32`, hours, no retraining — the genomics toolkit the project
  has never tried, against a failure it has recorded twice). W2 **model-free sequence
  statistics** (Menzerath–Altmann, predictive-information scaling, NCD) — an afternoon
  on the existing 34 696 bouts, and the first test of whether the type inventory is a
  real unit system rather than a convenient clustering. W3 the syrinx fit by
  **simulation-based inference / differentiable DSP** instead of coordinate search, the
  direct answer to docs/21's "the model is right, the fit is what fails". W4 **function
  without playback** — weak labels from the store's own xeno-canto behavioural
  annotations, and the cross-species convergence test `relations.json` already has the
  data for. W5 stop contaminating the analysis space with our own renderer (docs/22
  §22.6's measured arm). Order: W2, W1, W5, W4, W3 — cheapest and most refutative first.


## Open, for the next session

**Decisions waiting on the owner**
1. **W5 — the measurement is done, the call is not** (docs/22 §22.6). Giving a type with
   member observations no synthetic point at all gives seeds/type exactly 1.000, purity
   0.423 -> 0.577, coverage 0.432, on 25 % fewer points. It ships today as
   `--member-variants 0 --no-member-anchor`, off. It changes what the map contains — the
   rendered voice loses its own place — so it is a claim, not a default.
2. **Production build at the new cap.** `/tmp/birdy-prod/assets-v4` is green but capped
   at 1 024. A production rebuild wants 27 862 seeds against `K_CAP` 8 192, so it still
   sheds, and k-means at that k on 694 936 points is the wrong instrument. docs/22 §22.5:
   assign labelled points to their own type, cluster only what has no label.
3. **Whitepaper structure.** Both STE passes landed and the PDF is at
   `docs/whitepaper/birdy-whitepaper.pdf` (25 pages, verified). The agent flagged one
   thing prose cannot fix: the document's spine is a 28-row pre-registered gate ledger,
   so it reads like a test report *structurally*. Making it narrative is a restructure
   (results section, ledger to an appendix) and was deliberately not done.

**Work queued, in docs/23's order**
4. **W6 — BirdNET second opinion** (§23.6). T1 is the whole bet and W1 just raised its
   value: does a model trained on the same archives at ~100x the scale escape the same
   trap? Practical check first — BirdNET ships TFLite and this repo carries no
   TensorFlow, so `tflite-runtime` or an ONNX export.
5. **W7 — mimicry as ground truth** (§23.7). Pilot run: the test is well-formed, the
   corpus holds 31 lyrebird syllables. It is a targeted harvest, and xeno-canto's
   lyrebird records often name the mimicked species, so the harvest returns labelled
   mimic-to-model pairs.
6. **W2's second-order arm, re-run properly** (§23.2.1). The plug-in estimator cannot
   answer it; docs/18's held-out cross-entropy can, and is unbiased by construction.
7. **W4** (function without playback) and **W3** (SBI / differentiable DSP) — untouched.

**Known-broken and known-untested**
8. `verify-features.mjs` **fails on the shipped assets** — it checks that documented
   syllables match their own cluster, and debug-100 is the deepest hundred species and
   contains none of the 44 authored syllables. It is the corpus, not the code. A build
   from a subset chosen to *contain* authored species is what would exercise it.
9. **The renderer changes have never been seen running.** No renderer tests exist.
10. **Restart `serve`** to pick up the Learn-tab fixes (it holds the pipeline in memory).
11. The Learn tab still has no `subset`, `verify` or `respfit`/`docrefit` verbs, so it
    structurally cannot obey the debug-100 rule — every tab build is a production build.

**Environment**
12. `uv sync --extra critic --extra analysis --extra whitepaper` is the full working
    tree. The `whitepaper` extra exists because those dependencies were installed by
    hand and undeclared, and a plain `uv sync` removed them.


# Birdy — Session Handoff (2026-07-31)

**Landed today (uncommitted at this writing — user commits):**

- **Production learn on the deepened store: DONE.** `critic embed` refreshed
  (340 079 rows), then learn: **2 421 species, 13 859 learned types** (was
  12 724), median resynthesis cosine 0.648 (was 0.662 — expected dip with the
  harder XC-depth species in), worst −0.445, 23 min. typing.json +
  data/learned-inventory.json rewritten. Unlabelled pool: 28 arrivals → 12
  inherited, 2 candidates. **Next: P1 bake-off re-run (pre-registered,
  docs/18), then the production build decision.**
- **Detected song types are now playable songs (owner report).** The dropdown
  only ever offered "learned bout" (a generated sample) because the pipeline
  writes detected songs under `grammar.songTypes`, never under `songs`. The
  detection itself was always in (docs/12: run-collapsed medoid sequences
  with counts — 48/2 423 species carry them today, growing with P0 depth).
  `assets.ts` now surfaces each song type heard ≥ 2× as a Song
  (`S01 · heard 6×`, confidence `inferred`, gloss says repeats are sampled
  from the bird's measured self-transition rates), runs re-expanded
  deterministically (seeded on species+song id), gaps from the measured
  transition table (`grammar.gaps`, now also typed in types.ts — it shipped
  untyped since 2026-07-30). Works in shard and whole-file modes; the chorus
  treats them as the synthesized class. Shard contract test passes.
- **Ink-mode accent bug found + fixed (owner report).** `easeAccent` in
  PointCloud retinted the accent to the subject's species hue whenever
  `plain` was true — and with the three-way mode split, `plain` covers BOTH
  ink and bird modes, so ink mode's activations and selections flared the
  bird's own (newly saturated) hue instead of violet. Now: provenance mode →
  class colour, bird mode → species hue, **ink mode → violet, never retinted**.
  Companion coherence: labels/dot accents follow the same three-way rule
  (NodeProjector hot→violet in ink, neutral at rest; NodeLabels dot reads
  --accent; Trajectory gained an ink-neutral palette so idle threads go quiet
  with the points). Mode matrix verified per element; legend hue row
  rewritten to state the three languages. npm check 4/4 baseline.
- **Wavefront reach doubled (owner, same day).** `uWaveLocal` 2 → 4 knot
  spacings (the front read as a knot-local flash; a wave should be seen to
  travel) and launch amp ×1.5 capped at 1. Shader/launch comments updated;
  visual-only, npm check 4/4 baseline.
- **Palette + colour-language coherence (owner, same day).** Bird hues boosted
  58 %/38 % → 82 %/45 % ("heatmap, not pastel"); provenance classes saturated
  (rose #da9a76 → magenta #db2777, others boosted; grey stays grey — the class
  that claims nothing); app.css confidence vars kept in step. The colour
  language now moves as one across dots, threads and tags: ContextPaths got
  vertex colours per mode (neutral slate in ink, species hue in bird, class
  colour in provenance — it was flat slate in all modes), and NodeProjector's
  label accent follows `prov` (it stayed species hue in provenance mode —
  two languages on one tag). npm check 4/4 baseline; palette changes are
  visual-only, no parity impact.
- **UI text pass (ste-writing, same day).** The ASD-STE100 writing skill the
  owner pointed at is saved user-scope
  (`~/.agents/skills/ste-writing/SKILL.md`) and was applied to the visible UI
  strings: chorus class toggles moved below the Chorus button and only show
  while the chorus runs; long tooltips and panel notes rewritten short-active
  (tempo/song-gap/chorus/mic/critic titles, gate branch, "cannot respond"
  block, reading caveat); semicolons split; the mandated §8.5 honesty phrases
  ("unlabelled: real acoustics, no documented function") kept verbatim on
  purpose. British spelling kept for repo consistency.
- **Syrinx fidelity research (docs/21).** Verdict: **the model is correct;
  the fit is what fails.** The ODE is the published UBA normal form
  term-for-term (Laje & Mindlin), validated by RK4, the §8.6 table and 18/18
  parity; every recorded deviation sits in parameterisation, periphery or the
  objective, not the oscillator. Noise/machine-sounding renders are a
  taxonomy of measured causes (fit parked at the noise ceiling, sinusoidal
  source where real labia are skewed pulses, no jitter/tremor, static tract,
  envelope-instead-of-respiration). Top-2 ranked extensions with
  pre-registered sketches in §21.3: (1) the per-species respiratory pressure
  fit (machinery shipped, respfit won 445/12 680 types; gate read on the
  docs/19 bench), (2) measured physiological jitter/tremor per type (two
  scalars; Tumer & Brainard 2007 ~1 % FF CV; KS-distribution match + MCD
  non-inferiority on the P0 corpus). ~25 external citations, web-verified.
- **Point-colour modes + unified categories + sweep fixes (app-side, same day).**
  Points now have three colour languages in Display (**Ink / Bird / Provenance**):
  bird mode colours each point by the same species-hue hash as the labels
  (`aBird` attribute, `uBird` swaps the class tint — every other rule
  unchanged); tags stay in the labels' own language so the stage never speaks
  two hue languages at once. The chorus filter was re-keyed to the same
  vocabulary as the points (**documented / synthesized / recorded**, mapped to
  song-confidence values in one place, `CHORUS_CLASS_CONFIDENCE`) — the
  parallel confidence taxonomy is gone from the UI. Independent renderer sweep
  (read-only agent): today's changes verified clean; three PRE-EXISTING bugs
  found and fixed — `uHighlight = -1` collided with unassigned `aCluster = -1`
  (the hdbscan haze "breathed" 15 % in silence), the grey breath was never
  cleared in the singing branch (a weak self-match during a scheduled note
  could claim "nothing claimed" over a known note), and three `pow(x, 2.0)`
  calls with negative bases (spec-undefined, NaN-vanish hazard on exp2/log2
  drivers) now square explicitly. npm check 4/4 baseline, parity 18/18,
  verify:features pass.
- **Authored-call corpus crack found + fixed (2026-08-01).** The first
  production build's known map verified green (694 144 points, 1 024 clusters)
  but had **zero documented knots**: every authored call of a harvest-covered
  species (wrenChip, hooLong, chickA, cuck, oo — 33 syllables over 10 species)
  fell between the two render paths — `measured_corpus` renders only types
  with member observations, and the typed/authored species split sent those
  species down the measured path entirely, so the authored syllables of typed
  species never rendered. Symptom: confidence mix `unlabelled=1024`, no
  hoo*/wren* points. Fix (cli.py): the observed-type fallback — syllables of
  typed species with no members render jittered through `synthetic_corpus`,
  exactly the pre-split behaviour; verified on the real inventory (33 fallen
  syllables, all the documented calls, zero learned types). Rebuild running.
  **Fallback v2 (same day):** the v1 fallback crashed the rebuild —
  `KeyError: song 'learned_bout' references unknown syllable 'L31'`: the
  kept-only syllable table was paired with the species' full song list, and
  learned songs sequence learned types. But `measured_corpus` already renders
  EVERY song of a typed species against the full table, so the fallback now
  sends `songs: []` — songs would have been duplicate points as well as the
  crash. Verified: 66 clips render, no learned ids, ruff clean. Also note the
  trap that cost a diagnosis cycle: the first rebuild piped its log through
  `tail -30`, so mid-run checks read the PREVIOUS build's stale output files
  and looked like "the fix did not fire" — rebuilds now log to a file.
  **Outcome (rebuild v3, same day): the rendering crack is fixed, but
  documented knots are still zero — and that is now a design finding, not a
  bug.** The 33 documented calls render (24 points each, seeded as knots),
  yet all 1 024 clusters are named learned types. Two mechanisms stack: the
  k-cap (1 024 clusters vs 13 903 types — the build itself reports "the cap
  cost 12 879 types their only one", type coverage 968/13 903 = 7.0 %), and
  `label_cluster`'s pure point-count majority: a documented call's seeded
  cluster is flooded by hundreds-to-thousands of field points of OTHER
  species' learned types (wrenChip's 24 points sit in a 2 017-point
  mega-cluster named poecile_palustris/L05; hooLong's in an 11 653-point one
  named cuculus_canorus/L08), so the documented name, function and citation
  lose every vote. Forcing the documented name onto such a cluster would
  mislabel thousands of unrelated field points — the honesty rule forbids the
  cheap fix. The real options (raise K_CAP, weight the vote, pin documented
  knots outside the cap) are owner-level calls; until one is taken, the
  galaxy's knots are learned-type-only and the documented calls exist as
  points without knots. Recorded here so the next session does not re-hunt
  this as a rendering bug.
- **P0 depth harvest COMPLETE (owner call, batched — docs/18 P0).** 100 species
  (the debug-100 working corpus, deepest-first) × up to 30 recordings each,
  four 25-species batches run singularly with per-species logs in
  /tmp/birdy-p0/, every species exit 0. **+139 440 syllables** (200 k → 340 k
  observations), 7 992 → 10 184 recordings. Depth on the target 100: **median
  29 recordings/species, 71/100 at 20+** (the syntax threshold; p10 = 5 —
  xeno-canto simply has no more for those). Caps raised for the phase
  (--syllable-cap 400000 --cap 600000, recorded as a decision). Two catches en
  route: harvest `--species` needs `--inventory data/learned-inventory.json`
  for learned species (first attempt failed fast); the store was already at
  its 200 k syllable cap. XC audio still deleted immediately; the store grew
  28.65 MB per species of measurements only. **Next is the owner's call:
  production `learn` on the deepened store, then the pre-registered P1
  bake-off re-run (docs/18).** NOTE for the app session: the running `serve`
  (vite autostart) still holds the OLD `out/harvest` store — its Learn-tab
  jobs fit against that, not harvest-gan; the store path is now visible in
  the tab.
- **Point-cloud optics fixed (app-side, audits + fixes same day).** Diagnosis by
  two audits: (1) with `depthWrite:false` + normal blending, paint order is the
  only occlusion, so resting points later in the buffer overpainted lit ones —
  fixed as a **two-pass draw** (resting pass + ACTIVE_PASS at renderOrder 1,
  shared uniforms, lit-on-lit compositing unchanged), plus an activation-scaled
  size floor (3px + vAct·2 — the size channel was clamped away at galaxy zoom)
  and resting-ink dimming while sounding (`uLevel`); (2) the label "drag" was
  **task order**: `Framing` re-aimed the camera every frame *after*
  `NodeProjector` projected — Framing now mounts first, and its double
  `controls.update()` per frame (half the configured damping time) only fires
  when the aim actually moved; the labels' fixed-per-frame EMA is delta-scaled
  (was 2× fast at 120 Hz). **Member floor raised** (PointTracker 0.2 → 0.45):
  an activated knot's members all light now — "the inactive ones get active" —
  affinity still ranks members inside the knot. uPixelRatio updates per frame
  (was captured at construction). No renderer tests exist; verified by npm
  check and the diagnosis chain, not by eye — worth a browser look.
- **Wiring audit (app-side):** Learn tab shows the **store path** (the
  serve-store trap is now visible); unassigned-count caveat gated on the map
  kind, not on both maps existing (was unreachable on single-map builds);
  map-honesty line carries the new `centroidAgreement{TieAdjusted}` /
  `speciesAgreement` when a build ships them; dead `buildSource` removed;
  harvest cap/maxSeconds got the inputs their comment claimed existed.
- **Relations wired (old HANDOFF item):** relations.json loads optionally
  (`assets.relations`, absent = null); the Reading panel shows "shares call
  shapes with … — candidates, not documented relationships" for the matched
  species. The 3D overlay is deliberately NOT drawn as song-path threads (a
  relation link is a different claim than a bout thread; needs its own visual
  language, left open).
- **Unlabelled-arrivals live view:** per-class visibility filter in Display
  (documented/learned/field/unlabelled/candidate, shader discard via
  uProvHide/uProvHideCand) with an "only the unidentified" isolate — "what
  don't we know" as a picture.
- **Chorus category checkboxes:** songs filtered by confidence
  (documented/playback-verified/inferred/invented/field recording) —
  `startAmbient` takes an optional confidence whitelist, species with no
  eligible songs drop out of the pool; all-on = old behaviour.
- **Legend check:** all 7 rows verified against the color language; added the
  missing grey-breath row ("heard, but nothing claimed"). npm check 4/4
  baseline, parity 18/18, verify:features pass.
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
