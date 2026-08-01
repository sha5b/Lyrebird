# Birdy — Session Handoff (2026-08-01, night: the production build landed, and the 1 fps was the labels)

**The production build is done and green.** `/tmp/birdy-prod/assets-v5`, `--space embed
--clustering label`, **348 461 points, k = 14 003** (13 903 type blobs with 0 source
splits + 100 kmeans clusters for the 20 241 points with no label), **type coverage
13 903/13 903 = 100 %**, 1 136.8 s, **all checks passed**. The size predictions held to
within a rounding error: **centroids.json 7.69 MB + centroid-vectors.f32 3.81 MB**
against the 44 MB that blocked the build. Projection: distance pearson 0.691 /
spearman 0.689 over 200 000 pairs, purity 94.5 %. Confidence mix documented=27,
experimental=10, inferred=16, invented=31, unlabelled=13 919.

**The owner's report — "the whole browser slows to 1 fps" — was diagnosed, and it was
not the point cloud.** The cloud has a level of detail. **The label layer had none.**
`NodeLabels` rendered one full specimen tag per knot: at the shipped 4 298-knot build
that is **~77 000 DOM elements**, every one of them carrying `will-change: transform,
opacity` — so the compositor is asked for 4 298 layers — and `NodeProjector` then
projected every centroid, sorted every centroid, and wrote **seven style properties to
every one of those elements every frame**, i.e. **~30 000 style mutations a frame to draw
at most 26 tags**. `MAX_LABELS` was already 26; the budget capped what was *visible* and
nothing capped what was *touched*. At the new build's 14 003 knots it would have been
~250 000 elements and ~98 000 writes a frame. The layer's own comment said it was
"written for 44 clusters".

**Fixed as a fixed-size pool** (`app/src/lib/galaxy/labels.ts`, `LABEL_SLOTS = 28`).
`slots[s]` is the knot bound into tag element `s`; the `{#each}` is keyed by slot so the
element is built once and only the text inside a rebound slot re-renders. The projector
now does a **cheap scalar pass** over the activations first — a knot at rest with nothing
lingering costs one comparison — and only that handful is projected, sorted, culled and
written. **DOM cost and per-frame cost are now the pool's, and neither moves when the
corpus grows.** Nothing about the picture changes: same ordering, same collision culling,
same linger envelope, same three colour languages.

- **A second load-time wall, found while there and fixed with a test.** The wavefront's
  reach is quoted in knot-spacings, and the median nearest-neighbour distance was a plain
  `k²` double loop: 18 M distance tests at 4 298 knots, **196 M at 14 003 — measured at
  5 670 ms of frozen tab**. Replaced with a uniform grid sized to one cell per knot plus a
  ring search that stops as soon as the best distance is inside the radius the searched
  rings have cleared: **9 ms, a 600x cut, and exact**. Memberless knots are now excluded,
  because their centroid is (0,0,0) — a position `layouts.ts` already documents as a lie —
  and including them dragged the median toward zero. Same fix caught a latent
  off-by-population bug: the median was indexed `clusterCount >> 1` into an array that
  only holds the knots with members.
- **The repo now has its first renderer test**: `npm run verify:layout`
  (`app/scripts/verify-layout.mjs`) checks the grid against the brute-force loop it
  replaced, on six shapes at six knot counts — uniform cube, flat sheet, one line, tight
  clumps with far outliers, half the knots memberless, every knot coincident — and
  **agrees exactly on all 36 cases** (max difference 1.4e-14). Known-broken item 9 was
  "no renderer tests exist"; this is one.
- **`relations.json` on this build is 760 MB, and the app fetched it unconditionally
  before the first frame.** 2 929 410 species pairs written whole, where the UI reads
  three at a time; `--no-relations` skips the battery, not the file. It sat inside a
  `try/catch` written for a *missing* file, so the failure mode was a tab that does not
  come back rather than an error. **App side is guarded now**: an optional JSON asset over
  **32 MB** (debug-100 ships 1.5 MB) is refused on its `Content-Length`, the body is
  cancelled unread, and it is treated exactly like an absent asset — with a console
  warning, because a silently dropped asset and a corpus with no relations look identical
  in the UI. **The pipeline side is untouched and is the real bug**: writing 2.9 M pairs
  when 26 859 cleared the threshold is the owner's call to change.
- **The browser is running WebGL on the Intel iGPU, not the RTX 3500 Ada.** `glxinfo -B`
  reports `Mesa Intel(R) Graphics (RPL-S)` as the default renderer and `nvidia-smi` shows
  the discrete GPU at 218 MiB, i.e. idle. Verified that offload works:
  `__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia glxinfo -B` reports the
  RTX. So a share of the fill-rate problem is the machine's, not the code's, and the same
  two variables in front of the browser move it. **This is now visible in the app** rather
  than being something only a terminal can answer.
- **The UI thing: a "What this costs" readout** in the Display panel, off by default.
  Frame rate and frame time, points drawn against the corpus total (plus the responding
  count when audio is playing), which LOD level is in force, tags drawn against the knot
  count, and **the GPU string the browser actually gave us**, via
  `WEBGL_debug_renderer_info`. The renderer writes a plain non-reactive object every frame
  (`app/src/lib/galaxy/stats.ts`) and the page copies it four times a second, so reading
  the instrument cannot become the thing being measured. It exists because both of this
  project's renderer regressions were invisible from inside the app and both are one
  number.
- **`npm run check` at the 4 known baseline errors** (all four in
  `syrinx-processor.js`), **`verify:synth` 44/44 syllables ok** at 0.3 % median pitch
  error, **`verify:layout` green**. `verify:features` still reports its two failures —
  confirmed pre-existing by re-running with the app changes stashed, byte-identical
  output; that is the known corpus mismatch, not this work.

**The LOD's own bug, found on the owner's first look ("still a bit buggy") and fixed:
the three levels were not nested.** Level 0 draws one representative per knot — the member
nearest its own centroid — and level 1 drew a plain `i % 4` stride. A representative has no
reason to be a multiple of four, so **flying in from galaxy distance made 57 % of the
points you were looking at vanish** and unrelated members of the same knots appear in
their place (measured on a synthetic corpus of the shipped shape: 10 796 of 19 003). The
point count went *up* while the picture flickered, which reads as a fault rather than as
detail arriving. Level 1 is now level 0 ∪ the stride, so **level 0 ⊂ level 1 ⊂ level 2** and
coming in can only ever *add* marks. Both index arrays are ascending by construction now,
so the sort is gone and the index buffer is in vertex order.

Two cheaper things in the same function: the no-focus case is now **a single typed-array
copy** instead of a full-corpus scan, and the focused-bird branch reuses its membership
scratch instead of allocating **348 kB of garbage per swap — produced exactly while the
camera is moving**, which is the worst possible moment for a GC pause.

**Two LOD levers left deliberately untouched, both now visible in the readout**

- **`LOD_NEAR = 1.6` cloud radii is where "every point" engages**, which at 348 461 points
  is the whole corpus drawn for most of the range anyone actually looks from. Raising the
  bar is a one-line tuning call, and the "detail" line in the cost readout is what should
  decide it — with a number, not by feel.
- **The responding pass is not LOD-bounded.** At galaxy distance a sung knot lights all of
  its members even though only its representative was drawn at rest, so a chorus there
  costs far more than the resting picture suggests. That is arguably right — the response
  is the content — but it is the reason a quiet galaxy and a singing one can be different
  frame rates at the same camera distance. The readout's "responding" count says so.

**Open, for whoever is next**

1. **The production assets are built but not installed.** `app/static/birdy` still holds
   the debug-100 build (214 154 points, k = 4 298, `clustering: kmeans`). Copying v5 in is
   the real test of everything above, and the cost readout is the thing to watch while
   doing it — **do not copy `relations.json`**.
2. **The point cloud itself is still unmeasured at 348 461 points.** The LOD's galaxy
   level draws one representative per knot, which is now 14 003 sprites rather than
   1 024 — 14x the level that existed to make the galaxy view cheap. Inside a bird it
   draws all 348 461. On the iGPU that is the remaining fill-rate question and the readout
   will answer it in a second.
3. **The pipeline's `relations.json` size** (above) — an app guard is not a fix.

# Birdy — Session Handoff (2026-08-01, evening: knots, W2/W5/W6, licences, the inverse)

**Read this first if you are here for the point cloud.** The corpus the renderer draws
changed shape today and the numbers below are the ones that matter to it: **points roughly
halved** (production 694 936 -> 348 461) because a type with real members no longer renders
a synthetic copy of itself, **clusters roughly halved** (27 862 wanted -> about 14 000, and
every one of them now *has* a knot), and the per-cluster float arrays moved out of
`centroids.json` into a binary sidecar the loader already reads. One number moved the wrong
way and it is a picture number: on debug-100, 3D distance faithfulness fell 0.903 -> 0.747
while kNN agreement rose 20.7 % -> 28.0 %. Removing the rendered copies removed structure
the projection found easy, so **distance on screen now means less than it did** — worth
knowing before tuning anything visual. Nothing about knots or matching depends on those 3D
positions.

**PRODUCTION BUILT AND VERIFIED, and it fixes the thing §22.5 was written about.**
`/tmp/birdy-prod/assets-v5`, 19 minutes, `--space embed --clustering label` with today's
defaults. **Not copied into `app/static/birdy`** — that placement is one command and it is
the owner's.

| | old (v4, kmeans k=1024) | **new (v5, label + W5)** |
|---|---|---|
| points | 694 936 | **348 461** |
| clusters | 1 024 | **14 003** (13 903 types + 100, zero source splits) |
| type coverage | 968/13 903 = 7.0 % | **13 903/13 903 = 100 %** |
| **authored calls with a knot** | **0 / 44** | **44 / 44** |
| centroids | 44 MB projected | **7.69 MB JSON + 3.81 MB sidecar** |
| verify | green | green |

The zero-documented-knots finding is closed: every authored call now owns the knot that
carries its function and citation, and the confidence mix reads `documented=27,
experimental=10, inferred=16, invented=31` where v4 read `unlabelled=1024` and nothing else.

Two numbers to be honest about. **3D distance faithfulness is 0.691** (pearson) with kNN
agreement 12.0 %, down from v4's; the projection has 348 461 points and 14 003 knots to
place and the rendered copies that used to make it tidy are gone. And **cluster purity
reads 94.5 %, which is not a measurement** — it is 1.0 by construction on the labelled
clusters, and the manifest says so in `clusterPurityNote`.

**The new blocker is `relations.json`, and it is 66x worse than the one that was just
fixed.** 2 929 410 species pairs = **760 MB** at production scale, against 1.49 MB on the
shipped debug asset. It is **pre-existing** — v4 has the identical 760 MB — and it is
quadratic in species count, so it grows with every discovery. Measured: only **12 762 pairs
(0.44 %) carry a shared type at all**, and filtering to those would be **6.57 MB**. The app
loads the file optionally and uses it for one line ("shares call shapes with …"), so the
fix is to write only the pairs that say something, or shard per species the way
`inventory.json` already is. It changes an asset contract, so it is the owner's call, and it
is the one thing standing between v5 and a shippable production asset set.

**Restart `serve`** (it is holding pre-today pipeline code; it was already running when this
session started).

**Open, for the next session — the point cloud**

The renderer work from the previous session (knot-level LOD, the two-pass draw, the
cluster-state `DataTexture`) has **still never been seen running**, and there are no
renderer tests. That is the first thing to do, and it is now more interesting because the
corpus it draws is half the size and every type owns a knot. Specifics worth knowing:

- **Per-frame cost scales with cluster count.** `SpectralMatcher.update` walks every
  centroid every frame (cosine over 32 dims). At debug's 2 155 that is nothing; at
  production's ~14 000 it is ~450 k multiply-adds per frame. Measured CPU headroom before
  today was 1.9 ms of a 16.7 ms budget at 214 154 points, so this is probably fine —
  probably is not measured.
- **`layouts.ts` allocates per cluster** too (`centroidsOf`, the counts array).
- **The LOD's galaxy level draws one representative per knot.** With ~14 000 knots instead
  of 1 024 that is 14x the galaxy-level sprite count — the level that existed to make the
  galaxy view cheap.
- **The provenance colouring loses a class.** With W5 on, a typed species has no synthetic
  points at all, so "synthesized" only appears for types with no members. The legend and
  the three colour languages should be re-read against that.
- **`verify-features.mjs` reports two failures on the shipped assets** and both are the
  known corpus mismatch (debug-100 holds none of the 44 authored syllables the script
  renders). It used to *crash* on the first one — a TDZ bug, fixed today — so this is newly
  visible rather than newly broken.

**The five things that shipped**

1. **`build --clustering label`** (docs/22 §22.8) — typed points go to their own type's
   knot, k-means runs only over the unlabelled remainder. Type coverage 100 % by
   construction, 0.2 s of clustering against 65 s. Its pre-registered gate *failed* against
   an uncapped kmeans build (+2.5 points of type retrieval against +10) and passes by +14.2
   where the cap binds, which is production's condition — so it is a flag, not a default,
   and it is now the third choice on the Learn tab ("Use the labels").
2. **W5 adopted as the default** — `measured_corpus(anchor=False)`; `--member-anchor` buys
   the rendered voice back, `--no-member-anchor` is gone. Scored on a query population that
   does not move with the arm it buys **+0.02 points of retrieval, i.e. nothing**; the case
   is size, and the owner took it on that basis.
3. **The per-cluster vectors are a sidecar**, `centroid-vectors.f32` — they were **64 % of
   centroids.json's bytes**. Debug: 6.86 MB -> 1.18 MB + 0.59 MB. Contract in docs/08 §8.3;
   readers `galaxy.centroid_vectors` and `app/src/lib/data/centroid-vectors.ts`, both of
   which still read the pre-2026-08-01 inline layout.
4. **Audio may now be kept where the licence permits** (owner decision) — `harvest
   --keep-audio`, ND and unrecorded licences refused, 90.3 % of 10 184 recordings pass, all
   10 184 carry a recordist. **Nothing ships to the browser**; that half was declined.
5. **The Learn tab gained the label build** and says what it costs in honesty terms.

**Four honest negatives, which are the part worth carrying**

- **W2's second-order arm, re-run with the unbiased estimator: no structure** (docs/23
  §23.2.2). Median species *loses* 0.091 bits/token at order 2, at three seeds. The
  by-product is stronger than the arm: order 1 buys **0.98 bits/token** held out while on
  the shuffle it *costs* 0.75 — the cleanest evidence yet that the tokens are units.
- **W6 closed with two external models, and they disagree** (§23.6.1-3). Perch cuts the
  recordist lift 16.5 %, **BirdNET raises it 24 % — worse than our own critic**. If
  archive-scale training conferred recorder invariance both would have it and they would
  agree. It is in the archives, not in anyone's loss. §17.4's data action is all that is
  left.
- **The amortised inverse fails its gate on all three conditions** (docs/09 §9.3 status
  note). +0.0135 median cosine against +0.02, 52.8 % of types improved against 60 %, one
  species down 0.0816 against 0.05. **The starting point was not the binding constraint** —
  the descent already finds a comparable basin about half the time. `--inverse` exists,
  default off, deliberately *not* in the UI.
- **BirdNET's occurrence prior is blocked on metadata, not machinery.** It wants
  `[lat, lon, week]`; the store keeps `date` and `country` and **no coordinates**. Both
  archives return them; the harvester never recorded them.

# Birdy — Session Handoff (2026-08-01, label assignment + W2 + W5 + W6)

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
- **The documented-knot question, finally asked on a corpus that has them.** §22.6 could
  not ask it. The fast-loop store built against the authored inventory can, and **both
  arms reach 44/44 authored syllables with a knot** — at k = 130 for 125 types nothing is
  shed, so kmeans needs no help. Coverage still moves 84.0 % → 100 % on the learned types.
  One behaviour found there: kmeans named a cluster after a documented *song*, and label
  assignment does not — a song-level point carries no type, so it goes to the kmeans
  remainder (300 points, 12 clusters on debug-100). Whether a song should own a knot is a
  separate claim and was not made.
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
- **BOTH OWNER DECISIONS TAKEN, 2026-08-01, and both are built and verified.**
  1. **W5 is now the default.** `measured_corpus(anchor=)` defaults to False; the flag
     inverted — `--member-anchor` buys the rendered voice back, `--no-member-anchor` is
     gone. Debug-100 with label assignment: **160 579 points (−25 %), k = 2 155, zero
     source splits**, type coverage 2 143/2 143, verify green, 246 s against 375 s. One
     number moved the wrong way and it is a picture number: 3D distance faithfulness
     0.903 → 0.747 (kNN agreement 20.7 → 28.0 %). Removing 53 575 rendered points removes
     structure the projection found easy, so *distance on screen means less than it did*;
     knots and matching never used the 3D positions.
  2. **The per-cluster vectors moved to `centroid-vectors.f32`** — they were **64 % of
     centroids.json's bytes**. Little-endian float32, row-major, layout declared in
     centroids.json's own `vectors` block, values rounded exactly as before so no match
     moves. Contract in docs/08 §8.3. Readers: `galaxy.centroid_vectors` and
     `app/src/lib/data/centroid-vectors.ts`, **both of which still read the old inline
     layout**, so `app/static/birdy` keeps verifying untouched.

  Measured together: **centroids.json 6.86 MB → 1.18 MB** + 0.59 MB binary on debug-100
  (548 B of JSON and 272 B of float per cluster). At production's 14 003 clusters that is
  about **7.7 MB + 3.8 MB, against the 44 MB that blocked the build**. Production is now
  unblocked; the build itself is still your call to run.
- **Two app-side repairs found while wiring it.** `verify-features.mjs` had a
  **TDZ bug**: the session-gate block assigned `failed` before its `let`, so the script
  crashed with `ReferenceError` at the first failure instead of reporting it — every run
  since the gate shipped ended at that crash, hiding the check below it. Now it reports
  both failures on the shipped assets, and both are the known corpus mismatch (debug-100
  holds none of the 44 authored syllables the script renders), not new breakage; confirmed
  pre-existing by re-running with today's app changes stashed. And `features.ts` had two
  places that assumed the vectors were plain arrays — `Float32Array.map` returns a
  `Float32Array`, which `flatMap` does not flatten, so the raw-vector median would have
  been taken over typed arrays.
- **W5 measured against a query population that does not move — and it buys nothing in
  accuracy** (docs/22 §22.8's square; this is the evidence decision 1 below was waiting
  for, and it is not the evidence that was expected). Retrieval over *all* points is not
  comparable between arms holding different points: W5 deletes the synthetic copies, which
  are the *hard* queries, so it flatters itself by 18 points. Scored on the 160 279 field
  points every arm holds:

  | arm | points | k | field-point retrieval |
  |---|---|---|---|
  | kmeans, as shipped | 214 154 | 4 298 | 0.7176 |
  | label assignment | 214 154 | 4 298 | **0.7604** |
  | label + W5 | 160 579 | 2 155 | **0.7606** |
  | kmeans + W5 | 160 579 | 2 155 | 0.7156 |

  Label assignment is worth **+4.3 points**, the same in both W5 conditions, so the effect
  is the clustering's. **W5 is worth +0.02.** What W5 *is* worth is the map: identical field
  retrieval on **half the knots** (2 155 against 4 298) and a quarter fewer points, because
  with no synthetic copy there is nothing for the source split to split. Together with
  label assignment that takes production from 27 862 clusters to about **14 003**, and
  centroids.json from ≈ 44 MB to ≈ 22 MB — which is the difference between "needs a new
  asset format" and "ships". **Recommendation: adopt W5 with label assignment, on size.**
  It remains the owner's call and the default is unchanged, because the reason it was
  flagged has not moved: the rendered voice loses its own place on the map.
- **W2's second-order arm, re-run properly: NO STRUCTURE FOUND** (closes item 6 of the
  entry below; docs/23 §23.2.2,
  `seqstats.held_out_scaling` + `syntax.MarkovOrder` + self-test). The retracted plug-in
  arm is replaced by the docs/18 bake-off's own instrument: per species, its 80/20 **bout**
  split, a k-order backoff model fitted on the train half for k = 0…3, every held-out token
  scored, bits per token. Same corpus as §23.2.1 to the token — the new `seqstats.load_bouts`
  is pinned against `learn.bout_sequences` and refuses to run if the bout rule has drifted
  (34 696 bouts, 327 164 tokens, 2 421 species; 217 clear the 20-bout bar).
  **Pre-registered:** median gain ≥ 0.05 bits/token at order 1 → 2, ≥ 0.05 more than its own
  shuffle, and share of species gaining ≥ control + 20 points — all three.

  | | real | control |
  |---|---|---|
  | held-out CE k = 0 / 1 / 2 / 3 (bits/token) | 3.284 / **2.301** / 2.546 / 2.866 | 2.879 / 3.634 / 4.868 / 5.313 |
  | median gain, order 1 → 2 | **−0.091** | −0.912 |
  | species gaining at 1 → 2 | **25.3 %** | 4.1 % |

  **The gate fails at three seeds** (real gain −0.091 / −0.116 / −0.142). For the median
  species a second-order model is *worse on bouts it has not seen*. The share criterion
  passes at all three (25.3 / 24.9 / 24.4 % against 4.1 / 3.7 / 3.7 %), so a quarter of
  species hint at a second order at six times the shuffle's rate — a hint, not the gate.
  **And the first-order result is far stronger than §23.2.1 could state**: order 1 buys
  **0.98 bits/token** held out, while on the shuffle it *costs* 0.75. A model that can only
  win when the transitions are real, winning by a bit per token, is the clean form of
  "these tokens are units". P1 stands, P2/P3's premise is confirmed, and the depth question
  is now measured as **data-limited, not method-limited** — 217 of 2 421 species can be
  asked at all.
- **The amortised inverse: BUILT, WIRED, MEASURED, NOT ADOPTED** (docs/09 §9.3 Part 2 status
  note; gate and result in `pipeline/analysis/inverse_gate.md`). `inverse.py` had been
  complete and **imported by nothing** for weeks — 984 lines, self-test green, unreachable.
  It is now reachable: `birdy-pipeline inverse` trains it (150 k free, perfectly-labelled
  pairs from our own forward model; early stop epoch 26, best val 1.333, on the GPU) and
  `learn --inverse PT` re-initialises each type's gesture axes from its own mean mel patch
  before the same coordinate descent runs. The seam keeps the measured contour and duration.

  **The gate was written before the run and fails on all three conditions**, over two
  serial debug-100 fits sharing all 1 661 types:

  | | baseline | encoder | gate |
  |---|---|---|---|
  | median resynthesis cosine | 0.7411 | 0.7546 (**+0.0135**) | +0.02 |
  | types improved | | 877/1 661 = **52.8 %** | 60 % |
  | worst species | | **−0.0816** (`gampsonyx_swainsonii`) | −0.05 |

  **Default unchanged, `--inverse` opt-in and off.** The median and mean both rise, so it
  does something real, but it improves barely more types than a coin and costs one species a
  tenth of its fit. **The finding that matters: the starting point is not the binding
  constraint** — the descent from the cluster median already reaches a comparable basin about
  half the time, which is more than §9.3 assumed. What is left of docs/21's "the fit is what
  fails" is the objective (docs/19: cosine correlates ~0.1 with audible distortion) and the
  physics beyond the oscillator, not where the search starts. Both predicted weak spots were
  recorded *before* the run and survive: `tractQ` val MSE 1.125, timbre accuracy 0.442.
  **UI wiring was deliberately not done** — it was conditional on the gate.
  One follow-up is pre-registered in the same file: a **two-start descent** (median start
  and encoder start, keep the better), which cannot regress by construction; its bar is
  +0.02 median with *no* species worse at all.
- **W6 T1 RUN with Perch instead of BirdNET: THE CONFOUND SURVIVES, and this is the fourth
  end of the road** (docs/23 §23.6.1). T1 turns on two properties — same archives, ~100×
  the scale, and **no realism term** — and Perch 2.0 has both and is *already ported*
  (`perch.py`, ONNX, 1536-d), so T1 could be asked today instead of after a BirdNET port.
  One point per recording (§23.6's own ask for W1's batch representation, and a form where
  same-recording leakage is impossible rather than excluded): Perch = mean of the first six
  5 s windows, critic = mean of that recording's syllable embeddings, both through
  `geometry.measure` against its own null, same 1 567 rows, coverage 0.907 either way.

  | space | dims | recordist lift |
  |---|---|---|
  | critic 32-d | 32 | **0.0891** |
  | Perch 1536-d | 1 536 | **0.0744** |

  **−16.5 % against a −30 % gate: T1 fails.** A model that has never been asked to tell our
  resynthesis from a bird still carries five sixths of the recordist structure ours does.
  §17.3 closed this road during training, §17.5 with a factored target, §23.1.1 post-hoc,
  and this closes it **from outside our own loss entirely** — the first end that cannot be
  blamed on anything we built. §17.4's "invariance is a data action" is now the only action
  left: more recordists per species.
- **W6 T3 RUN: Perch retrieves species 8x better than our critic does** (docs/23 §23.6.2).
  The pair test the cache forces — 958 species with two recordings each, 1 644 recordings,
  760 recordists, `min_group=2` for species:

  | space | species lift (cov 0.834) | recordist lift (cov 0.329) |
  |---|---|---|
  | critic 32-d | 0.0074 | 0.1684 |
  | Perch 1536-d | **0.0588** | **0.1155** |

  **T3 passes decisively.** Caveat that belongs with the number: the critic's is a
  *syllable* space averaged over a recording, which is not its job, so this says Perch is
  the better **per-recording** space — exactly what W1 wants as its batch descriptor — and
  says nothing about syllable-for-syllable, which was not run. **T1 passes here at −31.4 %
  and failed at −16.5 % in §23.6.1, and the tie-break is coverage**: the recordist estimate
  covers 0.907 of rows there and 0.329 here, so the population built for the question wins
  and **T1's verdict stays fail**. What holds in both draws is the sentence worth carrying:
  in the Perch space the recordist lift is still **twice the species lift**. A 100×-scale
  model that has never seen a resynthesis still encodes who recorded it more strongly than
  which bird it is. **T2 (novelty AUC) is unrun**, and §23.6's offer to retire the critic's
  species head does not trigger — it needed T1 *and* T3.
- **A hard constraint on the rest of W6, found by running it.** The audio cache holds **at
  most two recordings per species** (2 616 species with exactly two, 1 221 with one, none
  with three) — iNat took no more, xeno-canto audio is deleted at harvest. So the species
  half of T1, and T3 as §23.6 states it, cannot be estimated on any audio this machine
  holds; a species-stratified draw returns zero recordings. Anything in W6 needing several
  recordings of one species **needs audio re-fetched first**, which is your call. What the
  cache does support is the pair test (`min_group=2`: is a recording's nearest neighbour its
  own species?), which `geometry.measure` explicitly allows — running as §23.6.2.
- **Practical notes for whoever does the BirdNET port.** No TensorFlow and no
  `tflite-runtime` are needed for the Perch route; `uv sync --extra critic --extra analysis
  --extra whitepaper --extra perch` is now the full tree. The 391 MB ONNX landed in
  `~/.cache/huggingface`, not `pipeline/out/perch`, because `HF_HOME` is already set in this
  environment — which `perch.ensure_model` documents as allowed. T1 read only the embedding,
  so it loaded the session directly and skipped `ensure_model`'s Kaggle class-list fetch:
  the labels are the one thing §23.6 says must never become ground truth, and they were
  never fetched.
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
