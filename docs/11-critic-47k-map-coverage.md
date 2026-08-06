# 11 — The 47 k critic, the map that broke, and the 70 % ceiling

Session evidence record (2026-07-29), in the pattern of docs/09 §9.7 and docs/10 §10.5:
pre-registered comparisons, fixed corpora, negative results kept. It covers the critic
retrain that docs/10 §10.6 asked for. It covers the browser-map regression that the
retrain caused, and its measured fix. It covers the type-coverage ceiling and its measured
fix, and the multi-source harvest layer. One operational lesson first, because it cost a
galaxy.

## 11.1 Operational: `serve` holds code in memory — restart it after pulling

The previous session's final learn+build ran through a `serve` process started at 11:47,
*before* that day's embedding work landed. Its Learn-tab builds used the stale in-memory
code. They wrote a descriptor-space galaxy from the old `out/harvest` store over the
embed-space assets. They also wrote a typing/inventory with no grammar chunks and no embed
typing. The tell was a manifest with no `space` key built hours after the key existed.

The session re-derived the assets with live code (`learn --embed-typing` → `build --space
embed`). The rule is now: **a pipeline code change is not live until `serve` is
restarted.** The Learn tab is a control surface over whatever code the process started
with, not over the checkout.

## 11.2 The critic retrain (docs/10 §10.6 open item — done)

`critic train --store out/harvest-gan`: 47 185 real patches / 21 species, 11 424 rendered
patches from the then-current fit, 60 epochs, 346 s on the RTX 3500. The run trained 16
species and **held out 5 entirely** (cuculus_solitarius, luscinia_megarhynchos,
poecile_cinctus, turdus_merula, zosterops_erythropleurus). The run preserved the
pre-retrain critic as `out/critic-20260729-pre47k.*`.

| metric | old critic (19 sp, 6.1 k real) | new critic (16 sp, 30.8 k real) |
|---|---|---|
| realism AUC, held-out species | 0.9897 | **0.997** |
| species accuracy (chance 0.062) | 0.9175 | **0.939** |
| contrastive top-1 (chance 0.004) | 0.6953 | **0.820** |
| novelty ROC AUC, held-out species | 0.596 | **0.672** |
| novelty TPR at 5 % FPR | 7.4 % | **14.8 %** |

Honesty notes: the novelty rows compare *different held-out species sets*. The split is
seeded over the store's species, and the species changed. The novelty rows are therefore
indicative, not paired. The novelty threshold recalibrated automatically 0.1558 → 0.1912
— §10.3's rule that thresholds do not transfer across embedding spaces held again.

Re-derivation (`critic embed` → `learn --embed-typing` → `build --space embed`) typed
finer: **485 types where the old space had 357**. The build's species kNN lift rose to
+0.444, the strongest structure measured.

## 11.3 The 28→32 map broke, and "linear is the honest choice" fell with it

The new embedding types finer because it encodes structure that the 28-d descriptor does
not project linearly. The browser's ridge map paid for it: **median mapped-vs-true cosine
0.7997, below the 0.8 gate**, nearest-centroid agreement 0.2263. It would have shipped
`accepted: false`: an embed galaxy the browser can only address in the old space.

`spacemap.py`'s docstring argued that a linear ridge is the honest map class. Its reason:
a nonlinear one "would fit the recording conditions of the training pairs and report a
flattering number". The session tested that argument instead of believing it. The session
fitted and graded the candidates under the module's exact protocol on the 47 185 store
pairs. The protocol: recording-level 80/20, with knobs chosen on a further split of the
fit side.

| candidate | val median | **eval median** | eval centroid agreement |
|---|---|---|---|
| linear ridge (status quo) | 0.773 | 0.759 | 0.176 |
| RFF ridge D=512, σ=6 | 0.891 | 0.882 | — |
| **RFF ridge D=2048, σ=4, λ=1** | 0.915 | **0.905** | **0.482** |
| degree-2 polynomial ridge | 0.900 | 0.889 | — |

The val→eval gap is ~0.01: the recording split, not the refusal of the model class,
answers the flattering-fit concern. The build ships the RFF ridge. The build chooses the
**map class itself on the validation split** (never on eval rows). It still fits the
linear map and ships it when it wins.

The weights ship as `space-map.f32` (123 k floats). The layout and the one-line apply are
in `feature-space.json`. `verify` checks the sidecar, and the app (`features.ts`
`ActivationTracker`) applies it. On any sidecar mismatch the app drops to the honest 28-d
path. This is the same "treat inconsistency as absent" rule as point-features.

In-build gate numbers (identical inputs, linear vs RFF): **0.7997 → 0.9268** median
cosine, **0.2263 → 0.5688** nearest-centroid agreement. The new map beats the old critic's
*accepted* linear map (0.8585 / 0.3739) on both.

## 11.4 Type coverage: the 70 % ceiling was a seed in empty space

Three consecutive builds measured type coverage at 70-71 % (110, then 148, then 144
orphaned types) regardless of k, because the cause was not k. In the critic's space the
strongest relation is `source` — recorded vs synthesised (kNN 0.990 vs 0.513 for species). A
typed field syllable and the renders of its own type sit in **different blobs**. One seed
per type at the mean of both sits in the empty space between them. The bigger blob
captures the seed, and a neighbour names the other blob.

The session measured this on a fixed corpus from the new `build --dump-points` flag. The
dump holds 59 700 points with labels, so clustering ideas cost seconds, not a 9-minute
re-render each:

| seeding | k | coverage | purity |
|---|---|---|---|
| one seed per type (status quo) | 503 | 71.0 % | 48.1 % |
| +144 free seeds | 647 | 78.8 % | 51.5 % |
| 2× types, free seeds | 999 | 86.9 % | 54.4 % |
| **source-split seeds (gate 0.9)** | 981 | **93.1 %** | **56.6 %** |

The gate sweep gives 0.9/0.8/0.7/0.6 → 93.5/92.7/90.9/88.1 %. It says 483 of 496 types
have their two source means more than cos 0.9 apart. The gap touches nearly every type.
Shipped: `_type_seed_means` in galaxy.py. A type with both sources gets a seed per blob
when their two means are more than cos 0.9 apart. `cluster_plan` counts the same seeds (k = 986).

**Production build of the time: 94.6 % coverage (27 orphans), 56.7 % purity**, map and
relations as above, verify green. *(Superseded 2026-08-01: the shipped production build is
`--clustering label` at **100 % type coverage, 0 orphans**, and its 94.5 % purity is an
identity rather than a measurement — a type is a cluster there. docs/22 §22.8.)* Both blobs of a split type may win a cluster name: two knots, one
type. That is the honest picture of a space where recorded and synthesised do not
coincide.

## 11.5 Multi-source harvesting: what is actually out there

`sources.py` adds `lyrebird-pipeline sources list/fetch` (subagent-built, live-probed
2026-07-29). Every adapter stages audio and ingests it through the *same* decode →
describe → delete-by-default machinery as xeno-canto. When its key or package is missing, an adapter
skips with a reason, never an error. `pipeline/.env.example` documents `XC_API_KEY`,
`KAGGLE_USERNAME`, `KAGGLE_KEY`, `HF_TOKEN`, and `ZENODO_TOKEN`. Verified probes into
`/tmp` stores:

| source | key | probe result | honest scope |
|---|---|---|---|
| zenodo XCDC (15420487) | none | 1 soundscape streamed from the 23.6 GB tar → 57 descriptors | dawn-chorus soundscapes, species-rich but not focal — novelty/soundscape work, not typing |
| internet-archive `xccoverbl_2014` | none | 2 flacs → 146 descriptors, 203 syllables | real XC mirror, 88 UK species, per-file CC licences |
| internet-archive `warblrb10k` / `ff1010bird` | none | range-requested wavs from 4.9/5.7 GB zips | **control sets only** — their public labels are binary hasbird, not species (recorded in place; the task list was wrong) |
| kaggle BirdCLEF 2021-2025 | yes | slugs live; per-species file filtering implemented | skip path proven; fetch untested (no creds here) |
| huggingface BirdSet | optional (not gated) | shard streaming proven (parus_major oggs from byte 0) | per-species partial download **not practical** (no tar directory) — honest subsets only |

Staged audio after every probe: none (`find /tmp` — clean). The probes left
`pipeline/out/harvest*` untouched. What this changes: `expand`'s rate-budget problem has a
keyless route for UK-covered species (xccoverbl) and soundscape controls. BirdCLEF waits
on the user's Kaggle key.

**Why the variety matters, and what it may not be mistaken for.** The store's name
(`harvest-gan`) is a fossil. The GAN/realism objective was refuted twice (docs/09 §9.7,
docs/10 §10.5), and nothing generative is being trained. The synthesiser stays physical.

What *does* learn from data is the critic, and its measured weaknesses in this project are
all *coverage* weaknesses. Species-level novelty detection sits at 14.8 % TPR. To a space
trained on 21 species from one archive, "a never-heard species" and "a new microphone in a
new country" look alike (§10.3). The map gate is graded on recording conditions
precisely because that is what shifts. Widening the sources is the direct attack on that:

- **more species and taxa** (BirdCLEF's hundreds of per-species recordings, BirdSet's
  ~520 k) → denser acoustic neighbourhood, fewer false "novel" flags on merely-unseen
  birds, and better type inheritance for rare species.
- **more recording conditions** (different continents, devices, eras of the xccoverbl 2014
  mirror) → the embedding stops pricing microphone and geography into "species".
- **other sound forms** (XCDC dawn-chorus soundscapes, warblr/ff1010 hasbird controls) →
  an honest answer to "what does *not our kind of sound* look like". The novelty threshold
  is calibrated against exactly that.

The discipline does not change. Decode → describe → delete is the default in every adapter,
and no audio is ever shipped. *(2026-08-01: `--keep-audio` may keep a licence-permitting
copy on the machine — NoDerivatives and unrecorded licences refused. See `NOTICE.md` §3.4.)* Every claim gets a confidence label. Any large ingest must face the same
pre-registered numbers on the fixed store: critic report, map gate, novelty ROC, type
coverage. The judgement happens after a full re-derivation, with novelty recalibrated per
§10.3.

## 11.6 What is still open

- **Docs 09's alternation** was again not run. It is moot while the realism term stays
  refuted (§10.5). This note records it so it stops accruing "never run" notes.
- **Novelty at species level** sits at 14.8 % TPR @ 5 % FPR. §10.3's verdict stands:
  better is a research problem, not a tuning one. Perch-2.0 labelling of flagged arrivals
  is the HANDOFF's researched route.
- **App-side overlays**: relations from `relations.json`, "what comes next" from
  `grammar.chunks`, the translator's novelty branch — with the app-side session.
- **A real `expand`** is now a deliberate choice with two budgets: xeno-canto rate limits,
  or a Kaggle key for BirdCLEF.
