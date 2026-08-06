# 10 — The galaxy becomes a measurement

**Status: built and measured.** This document is the evidence record for the change that
moved the galaxy off hand-set jitter and off the hand-designed descriptor. It follows the
style of doc 09: every claim below has a number behind it, and the failures are written
down next to the successes. Read `08-implementation.md` §8.1a–c and doc 09 first. This
document assumes both.

The complaint that started it, verbatim: *"the cloud at a node means two different things
depending on the node. For a synthetic knot, its extent is the jitter you dialled in — a
sampling distribution of your own render parameters, not a measurement of a bird."* The
complaint was literally true: the code applied `syrinx.Jitter` (pitch 3 %, duration 8 %,
level 10 %, warp 4 %) to one median render. It did this 96 times per syllable, for every
species alike. `geometry.py` already said it: ninety-six jitters of one parameter set are
one observation, not ninety-six.

Four structural changes follow, each with its measurements. A fifth change — the learned
inverse of doc 09 Part 2 — was built, measured, and **failed its ship rule**. §10.5
documents it, and it stays experimental.

## 10.1 Every cloud is a measurement now

Three moves, all in the pipeline:

1. **`learn` exports `typing.json`** into the store: one `{speciesId, recordingId, order,
   typeId}` row per observation. On the 47 k store: **47 185 of 47 185** observations
   carry a learned type id.
2. **Galaxy field points are syllables, not windows.** `HarvestStore.syllable_point_set`
   emits one point per stored observation. The point's own 28-d descriptor (or its 32-d
   embedding — §10.2) sets its position, and the point carries its type id. This is what
   doc 01 §1.2 always said a point means. The window reservoir still feeds
   `feature-space.json`'s standardisation frame. The browser's live path analyses windows,
   so its frame must stay window-based (`--field-source {auto,syllables,windows}`, default
   auto).
3. **Synthetic points are renders of measured realisations.** For a learned type,
   `corpus.measured_corpus` renders the unjittered median once. This is the anchor, the
   sound that Lyrebird sings. It also makes up to `--variants` (now default 24, was 96)
   renders of *actual member observations'* measured parameter sets. Hand-authored species
   keep the jitter path. This is honest, because no measurements exist for them.

Measured on the five-species store, knot `radius` (n≥10): field-syllable knots
**0.049–0.296** (median 0.145), measured-render knots 0.032–0.235 (0.113), jitter-path
knots 0.023–0.150 (0.084). Under fixed jitter these were near-constant. Now the extent
varies per type, and measured knots are systematically wider than the old dial said: real
variance exceeds ±3–10 %. In the UI the `n/ρ/r` figures carry a "measured" / "invented"
qualifier from the knot's source mix.

## 10.2 The galaxy lives in the learned embedding

Doc 09 §9.7 left "use the embedding for the galaxy's clustering, not only for typing" as
the open item. Closed. The command `build --space embed` runs the entire build on the
critic's 32-d embedding of each observation's mel patch. Its default `auto` selects embed
when the store has `embeddings.f32`, typing, and a loadable critic. The entire build means
landmark cMDS, separation, seeded KMeans, PCA point-features, and the projection basis.

**The subset comparison** (625 field syllables of three species, identical points, same
seed, only the space changed): purity **70.9 % → 90.9 %**, type coverage **12/14 →
14/14**, 3-D knn10 agreement **64.5 % → 83.2 %**, distance faithfulness (pearson)
**0.874 → 0.940**.

**The production build of the time** (2026-07; *"the production build" now means the
2026-08-01 one — 348 461 points, k = 14 003, `--clustering label`*) has 47 185 field
syllables + measured renders, 56 500 points, 375 clusters, 32-d. The embedding's own structure analysis puts species kNN at **0.426**
(chance 0.072) and syllable-type kNN at **0.310** (chance 0.006). The same groupings
measured in the 3-D projection give 0.269 / 0.147 for comparison. The map's geometry is now the geometry
that measurably decides "same syllable".

**The browser cannot run torch** (docs/09 §9.4). So the pipeline fits a ridge map
R^28 → R^32 on (store descriptor, store embedding) pairs. It ships the map as numbers in
`feature-space.json`'s `embedding` block. This has the same status as the shipped
mean/std: no weights.

**The gate, measured on 117 held-out recordings (10 218 syllables): median cosine 0.8585
between mapped and true embeddings** (deciles 0.644 / 0.728 / 0.777 / 0.812 / 0.839 /
0.862 / 0.884 / 0.905 / 0.933) → accepted (target 0.8). Nearest-centroid agreement of the
map against the true embedding is 0.37 — the map is good enough for activation weighting,
not for exact argmax identity. The shipped `mapQuality` says both. If the gate ever fails,
the assets carry `accepted: false` and the browser stays on the 28-d path.

Two honest caveats:

- **Type coverage fell**: 258/368 types have a cluster carrying their name (70 %). The
  old 28-d build shipped 555 clusters for 433 types. Typing nearly all field points shrank
  the unlabelled allowance in `cluster_plan`. Now k (375) sits close to the type count,
  and KMeans merges some seeds. Not yet re-tuned.
- A render-free placement check scores the 32-d space slightly below the 28-d (38.5 % vs
  41.3 %). The check compares stored observations against per-species *mean* references. A
  single mean per species discards the within-species type structure the embedding
  encodes. Every type-respecting metric above favours it. Reported with its definition,
  not blended.

## 10.3 Novelty is live — and its threshold was lying

The novelty detector (doc 09 §9.2b use 2) now runs at ingest. `/api/ingest` embeds new
observations and sets `novel=True` where the calibrated distance fires. `/api/status`
exposes `novelCount`/`recentNovel`.

During `grow`, novel points are no longer force-assigned to the nearest knot. Below quorum
they stay unassigned (clusterId −1). At quorum (≥ 8 coherent pending points, greedy seed,
0.70 cosine radius, 0.75 cohesion floor) they found a **new knot**, idempotently. Its
label is "unheard syllable", confidence `unlabelled`. The UI shows the count with the
§9.2b honesty text: detecting that a sound is new is not knowing what it means.

**The calibration did not transfer between harvest epochs.** The shipped threshold
(0.1048, calibrated on the 9 k store) flagged **29.8 %** of the current 47 k store. That
includes 29 % of *training* species' syllables, against a chosen 5 % false-positive rate.

The cause is recording-level distribution shift within known species. This is exactly the
failure that a chosen-FPR threshold is supposed to make visible. Recalibration on the
current store (`fit_novelty`, no retrain) gives threshold 0.1558, with a store-wide flag
rate of **5.6 %**.

The honest ROC on this store holds six species out of training: **AUC 0.596**, TPR 7.4 %
at the 5 % operating point. This is much weaker than doc 09 §9.7's 0.825 on the 9 k store.
Per species it is the same story that §9.7 told, but louder:

| held-out species | flagged | nearest trained relative |
|---|---|---|
| `perisoreus_infaustus` | 26.3 % | none |
| `horornis_diphone` | 20.0 % | `horornis_canturians` (not in store) |
| `zosterops_simplex` | 12.3 % | two congeners |
| `parus_minor` | 5.6 % | `parus_major` |
| `troglodytes_troglodytes` | 2.7 % | none |
| `cuculus_solitarius` | 1.5 % | two congeners |

Denser per-type centroid coverage (19 species × up to 8 types) leaves less "far" to be.
The detector also prices acoustic neighbourhood over relatedness. A held-out congener is
genuinely hard. The wren is once again the counterexample that proves the detector does
not measure taxonomy.

"Flag a never-heard *species*" is a harder test than "flag a genuinely new *sound*". The
detector is honest about both. Trained-species flag rates sit at 0–7.8 % around the 5 %
design point.

## 10.4 Structure from the unorganized data

**Typing the unlabelled.** `learn_unlabelled` types observations with no species label
(what `/api/ingest` produces) against known type centroids inside the novelty threshold.
The remainder clusters (HDBSCAN) into candidate `U*` types under a pseudo-species
`unlabelled`, with `assign_ids` inheritance across refits. **Relabel-recovery test**
(three species × 300 syllables relabelled `unlabelled`): 97.4 % inherited a known type,
and 65.2 % overall inherited the *correct species'* type. Misassignments go to
similar-sounding types of other species: acoustic neighbourhood again, not taxonomy.

**Chunks.** `mine_chunks` extracts repeated contiguous type sequences with count ≥ 3 and
PMI above a per-species bigram baseline. An evidence gate (pmi·√count ≥ 6) and a mono-run
exclusion guard the result. Each guard exists because its absence produced measured
garbage. Frequency-profile aliasing faked PMI up to 1.2 under the null. The winner's-curse
tail reached pmi·√count ≈ 4.6 without the gate.

The 47 k store holds parus_major's two-note alternation (`L07↔L19`, up to length 6,
counts ~100), chickadee ABA patterns (`L00 L02 L00`, pmi 1.87), and cuckoo alternation.
The shuffled-sequence control finds **0 chunks**. The build reports chunks as discovered
structure with counts, never glossed as meaning.

**Relations.** `relations.json` (shipped with the build) holds cross-species shared-type
candidates: pairs nearer than the median within-species nearest-type distance. It also
holds a species similarity matrix (centroid-of-centroids cosine + symmetrised 1-NN).
Symmetric KL is degenerate here, because type ids are species-local, and the code says so.

**The shipped copy is a trim, and it says so in the file.** Every unordered species pair is
quadratic — 2 929 410 pairs and 760 MB at production's 2 423 species — so
`relations.shipped_relations` keeps each species' eight nearest partners, deduplicated:
**14 425 pairs, 5.6 MB**, lossless for the three-nearest question the app asks. The file's
`retention` block carries the rule and both totals. Analysis wants the whole document and
the standalone `relations` verb still writes it. See docs/08 §8.3.

The build finds 117 shared-type candidates. Congeners rank high
(`cuculus_clamosus/cuculus_solitarius` #1, `zosterops` pair #2, `parus` pair #11), with
honest misses (`cuculus_canorus` sits far from its congeners). This is the same
acoustic-neighbourhood geometry, now a product feature.

**Expand.** `lyrebird-pipeline expand` ranks discovered-but-uncovered species (congeners of
high-novelty genera first). It runs the existing harvest → embed → learn → grow chain per
target, with rate-limit pauses intact. `--dry-run` prints targets with no network. The
server wires it as `/api/expand` next to `/api/loop`.

## 10.5 The learned inverse: built, measured, did not ship

Doc 09 Part 2 describes an encoder (mel patch → syrinx parameters). Its training data is
free, because we own the forward model. The session implemented it (`inverse.py`), trained
it on 150 k rendered pairs, and put it to a **pre-registered bake-off**. The bake-off used
24 real fitted types across 10 species: current coordinate descent vs encoder-init +
identical polish.

| | baseline | encoder + polish |
|---|---|---|
| median resynthesis cosine | 0.734 | 0.737 |
| median wall time per type | 0.2 s | 0.2 s |

Ship rule: cosine ≥ baseline − 0.01 **and** time ≤ 0.5 × baseline. The cosine arm passes.
The time arm fails outright: render+score is ~2 ms, so a full descent costs ~0.2 s no
matter where it starts. The 2× speedup that the rule asked for never existed on this
hardware. The encoder-only start scores *below* the median it replaces (0.342 vs 0.442),
because on measured fields its regression estimate overwrites a measurement.

So it does not ship. The module stays experimental, with the full table in its docstring.
The loss mechanism points at a follow-up: an init restricted to the four *unmeasured*
§8.1a axes (gammaScale, tractQ, noise, rough), where the encoder's wins clustered. That
arm was not pre-registered, and the session deliberately did not run it.

On the GAN question that this session keeps coming back to: nothing here changes doc 09's
verdicts. The realism objective is refuted twice. A generative audio model remains the
wrong tool. It has no accepted quality metric and no bird validation. It would also
destroy the interpretability that the galaxy, grammar, and honesty labels rest on.

The critic earns its place exactly where the measurements put it: embedding, typing,
novelty, and now the galaxy itself.

## 10.6 What is still open

- ~~**Type coverage 70 %** (§10.2)~~ — fixed in docs/11 §11.4: the ceiling was one seed
  per type sitting between the field and synthetic blobs. Source-split seeds measure
  94.6 %.
- **Novelty transfer across harvest epochs** — the threshold is per-embedding-space and
  per-store. A big harvest should trigger recalibration (`fit_novelty` is cheap, and
  `critic train` now does it on every run). Detecting *species*-level novelty at 5 % FPR
  sits at 14.8 % TPR pooled after the 47 k retrain (docs/11 §11.2). Better is a research
  problem, not a tuning one.
- ~~**Critic retrain on the 47 k store with a proper species holdout**~~ — done, docs/11
  §11.2 (all four metrics up, full re-derivation shipped). Doc 09's alternation remains
  moot while the realism term stays refuted (§10.5).
- **`expand` has only been dry-run** so far. A real run spends xeno-canto rate-limit
  budget (or a Kaggle key, docs/11 §11.5), so it should be a deliberate choice.
