# One-off measurement runners

Arms that were run once, against a fixed store or a fixed dumped matrix, to settle a
question recorded in `docs/`. They are here rather than in `src/birdy_pipeline/` because
nothing imports them and nothing ships them — but they are here rather than in `/tmp`
because **the pre-registered gate of each run is the docstring at the top of its file**,
and a result whose gate cannot be re-read is not evidence.

Each one states its gate before its code, names the population it drew, and prints a table.
Paths are absolute and point at this machine's stores; a different machine needs those three
constants changed and nothing else.

| file | question | verdict | evidence |
|---|---|---|---|
| `w2_heldout_orders.py` | is there structure beyond first order? | no — median species loses 0.09 bits/token at order 2 | docs/23 §23.2.2 |
| `w5_label_arms.py` | label assignment against the shipped kmeans path | +2.5 pts uncapped (gate wanted +10), +14.2 at production's shed ratio | docs/22 §22.8 |
| `w5_field_retrieval.py` | the same four arms on one query population | label assignment +4.3 pts; W5 itself +0.02 | docs/22 §22.8 |
| `w6_t1_perch_recordist.py` | does an external 100x-scale space escape the recordist confound? | no — recordist lift 0.0891 -> 0.0744, gate wanted -30 % | docs/23 §23.6.1 |
| `w6_t3_perch_species.py` | does it retrieve species better? | yes, 8x (0.0074 -> 0.0588), and recordist still outranks species | docs/23 §23.6.2 |
| `w6_birdnet_arms.py` (+ `.json`) | BirdNET as the second external opinion | it *raises* the recordist lift 24 % — worse than our own critic, and it disagrees with Perch | docs/23 §23.6.1-3 |
| `inverse_gate.md` | the amortised inverse's pre-registered gate, and its result | **fails all three conditions**: +0.0135 median cosine (wanted +0.02), 52.8 % of types improved (wanted 60 %), worst species -0.0816 (wanted -0.05). `--inverse` default off | docs/09 §9.3 Part 2 |
| `inverse_compare.py` | scores the baseline fit against the encoder-start fit | the table in `inverse_gate.md` | docs/09 §9.3 |
| `score_two_start.py` | the pre-registered follow-up: keep the better of median-start and encoder-start | unrun; bar is +0.02 median with **no** species worse at all | `inverse_gate.md` |
| `g1_g2_avonet.py` | G1: does the fitted tract length measure a windpipe? G2: does the textbook mass/frequency result reproduce? | **G1 fails** at partial r +0.194 (gate 0.4), and neither quantization nor thin sampling explains it. **G2 passes.** | docs/24 G1, G2 |
| `g2_pgls.py` | G2's owed half: the same question with phylogeny accounted for | passes, standardised slope -0.560 on the deep arm against a published -0.510. **Lambda is fitted, not assumed** — forcing Brownian spanned -1.962 to +0.001 across one posterior | docs/24 G2 |
| `g3_recordist_aggregation.py` | does the recordist confound survive aggregation to one point per recording? | **passes on 77 of 3 636 species, and that is the finding.** species +0.229 vs recordist +0.196, but ARM D shows aggregation is not what inverts it — the 8-member floor selects the well-sampled species, which are the ones with many recordists (r +0.923) | docs/24 G3 |
| `w2_learners.py` | do vocal learners have larger repertoires and more complex syntax? | **refused, not null.** repertoire correlates with sampling effort at r +0.852 and repeat-classes are zero on 97.7 % of species, so the measures cannot carry the question | docs/24 W2 |
| `w6_t1b_perch_postcutoff.py` | does Perch's recordist structure survive on audio it provably never trained on? | **yes** — recordist lift +0.441 ("strong") on matched rows over 2 158 post-cutoff recordings. The contamination alarm was overcautious | docs/24 W0 |
| `w0_recordist_split.py` | what does a recordist-blocked split cost a probe over frozen Perch features? | **9.68 points** (93.29 % -> 83.61 %), gate wanted > 10 so NOT met — but 2.44x the errors, worse in 20 of 20 folds. `--self-test` validates the split logic first | docs/24 W0 |
| `w0_full_catalogue.py` | how big is the post-cutoff population really? | **21 928** recordings, not the pilot's 6 000 — that was `SEARCH_PAGES = 60` x 100 a page. 4 305 species, 961 recordists, and 886 species clear W0's floor | docs/24 W0 |
| `w0_full_fetch.py` | stage 1 of the full run: select the scorable population and embed it through both models | 8 321 recordings over 886 species and 649 recordists, after a recordist-aware cap of 12 per species. Resumable; audio is kept because the download is the expensive half | docs/24 W0 |
| `w0_probe.py` | is the GPU probe the same estimator as the pilot's scikit-learn one? | **yes, to 0.91 accuracy points** on the pilot's own features. `--verify` fails loudly if not. It exists because 886 classes in 1 536 dims is not a tractable CPU fit | docs/24 W0 |
| `w0_full.py` | stage 2: the same experiment at 884 species on Perch **and** BirdNET | **GATE MET on both.** 18.51 points on Perch (81.68 -> 63.16) and 21.59 on BirdNET (79.08 -> 57.49), 20/20 folds each, 2.01x and 2.03x the errors, 8 287 recordings / 884 species / 646 recordists. A class-count sweep shows points climbing 12.75 -> 18.51 while the ratio *falls* 2.97x -> 2.01x, so **neither unit is invariant** | docs/24 W0 |
| `w0_confound_anatomy.py` (+ `.json`) | how many recordists per species does it take, and is it the same recordists in both models? | **30.82 points of drop at 2 recordists per species falling to 3.08 at >=6**, label-set size and recordings/species held flat — a factor of ten, and the first result that removes the confound instead of pricing it. Per-recordist findability correlates between Perch and BirdNET at a partial r of **+0.852** (null p95 +0.140) over 212 recordists | exploratory, not pre-registered |
| `specbench` (CLI, + `specbench_n1200.json`) | does a cosine gain track an audible gain, at 6x the published sample? | **worse than "no".** n = 1 200 on the production store: cosine vs MCD Spearman **+0.200** (p 3e-12) and vs STFT +0.186 (p 9e-11) — significant and the **wrong sign**, so higher cosine goes with more distortion. The mel target ranks it correctly at **-0.456** (p 1e-62). docs/19's n = 200 called the cosine "not distinguishable from zero"; it is now distinguishable, in the wrong direction | docs/19 §19.2 |
| `rejudge_respfit.py` (+ `.json`) | would a cosine-gated adoption survive re-judgment on the spectral bench? | **NO, and it is worse than a wash.** The respiration block gained +0.034 median cosine (its gate needed +0.02) and cost **-4.18 dB median MCD** and -2.34 dB STFT, winning on MCD for only **33.1 %** (58/175) of adopted types. Pre-registered prediction (win share < 50 %, median dMCD <= 0) held. Measures a *gate*, not the physics | docs/19 §19.2; Limitations |
| `rejudge_twovoice.py` (+ `.json`) | does the *next* cosine-gated adoption survive the same re-judgment? | **YES, and the pre-registered prediction failed.** The two-voice block gained +0.071 median cosine and **won +1.13 dB median MCD** on **55.6 %** (966/1 737) of adopted types — sign test p 3.2e-6, Wilcoxon p 6.4e-12, and +0.03 dB on STFT. Opposite sign to respiration on **twelve times** the population, so the n=1200 anti-correlation does not reach into every gate it produced. Corrects `rejudge_respfit.py`'s claim that this adoption could not be isolated: `two` is a descent axis, but **`voices`** is written only onto winners — checked 1:1 against `out/v9/respfit-report.json`, 2 144 = 2 144, zero mismatches | docs/19 §19.2; Limitations |
| `recordist_bias_comparative.py` (+ `.json`) | does the recordist signature reach the species-level pitch estimate comparative papers use? | **yes, and it is large — but the slope survives it.** 797 species with >=2 recordists at >=20 syllables each (against G3's 77 of 3 636), because this is a *direct* measurement paired *within* species. Within-species between-recordist variance of median log f0 is **0.0446** against a within-species-shuffled null of 0.0033 (p95 0.0037) — **12x** — and **0.638 of the between-species variance**, i.e. two recordists on the same bird disagree by two thirds of what separates species. Yet the mass/f0 slope moves **1.0 %** when recordist-balanced (−0.1655 → −0.1672, tolerance 15 %). A large mean-zero effect attenuates rather than tilts, which names a component of the noise behind G2's −0.211 vs Mikula's −0.510 and the fitted lambda of 0.000. Both clauses pre-registered, both held | new; G2 / Limit 2 |
| `w0_blocking_variables.py` (+ `.json`) | W0 priced a recordist-blocked split. What do geography and time cost? | **all of them leak, and country costs the most.** Same 8 287 recordings, 884 species, frozen embeddings, probe and seeds as `w0_full.py`, so the recordist arm is a replication check and it passes at **18.38 vs the published 18.51**. Held-recording-share matched across variables: recordist 19.02 / location 1° 18.26 / **country 23.87** / year 19.11 on Perch (22.07 / 20.68 / **26.97** / 21.50 on BirdNET). Two of four pre-registered clauses **failed** — country is *larger* than recordist, and year is not smallest once held share is matched. Carries the level-vs-recordings trap (30 % of 116 countries strands 43 % of rows against 34 % for 646 recordists) and the NMI between blocks (recordist\|location **0.817**), so the claim is "17-27 points on whichever axis", not four independent leaks | docs/24 W0, extension |
| `v10_resegment_yield.py` (+ `.json`) | how big would the corpus be if every row were re-segmented in band? | **smaller, and it costs species.** Ratio 0.777 over 250 recordings at harvest's own 90 s, so 378 224 -> ~293 700 syllables; 14.8 % of recordings yield *nothing* in band. Monte Carlo per recording (so the yield-nothing tail is carried, not averaged): species over the fitting floor of 24 fall **2 648 -> ~1 938**. No `syllableCap` collision | v10 sweep pre-flight |
| `v10_outofband_census.py` (+ `.json`) | what does the band fix remove and add? | **it trades marginal rows for weaker ones.** Both segmentations on the same audio, matched by time overlap: agreed rows median SNR **13.61 dB** (15 % under 6 dB), removed rows **4.68 dB** (66 %), added rows **2.64 dB** (80 %). The paths agree on strong material and disagree only near the noise floor. Carries two recorded method traps: a first version was tautological (f0 is tracked *inside* the band, so 100 % of rows read "inside"), and the pre-registered prediction used `harmonic`, which **saturates at exactly 1.0** on 64 % of disagreed rows — degenerate on short spans, not a quality signal | v10 sweep pre-flight |
| `v10_snr_floor.py` (+ `.json`) | if the band was the wrong lever, what does an SNR floor cost and buy? | **a much better exchange rate, though not a dominance.** Exact census over all 378 224 rows: at 6 dB it keeps 0.768 of rows, **2 162 species** and median SNR **15.28 dB** (from 11.96). The band fix at 0.777 of rows keeps **1 938 species** and raises median SNR **6.36 → 7.13 dB** — so ~4x the gain per row sacrificed, plus 224 more species. **Corrected mid-session**: the first version claimed the band fix "buys no SNR", which was an untested inference and is false. One tension left open: docs/23 reports the in-band arm at 12.7 → 15.9 dB over 120 recordings against the +0.77 measured here on 60 — reconcile before quoting either. A 0 dB floor costs 3.6 % of rows for +0.5 dB | v10 sweep pre-flight |
| `v10_fetch_xc_audio.py` | the store's own xeno-canto audio, which harvest streams and deletes | **DONE: 3 726 of 3 728, 18 GB** in `out/audio-xc` (2 permanent failures, one http 500 and one 404). Fetches the exact XC ids in `harvest-gan` — not a fresh query — so the cache matches the corpus. `specbench --extra-audio-cache out/audio-xc` now takes `noCachedAudio` to **0**. **Never average the two arms**: `band_hz` is the reference's own Nyquist and the caches sit an octave apart (22.05 vs 48 kHz), so wav-backed types read median MCD 78.96 dB against mp3-backed 111.70 — mostly band, not fit. A band cap is owed | owner request; NOTICE.md unaffected, local cache only |
| `ledger_tally.py` (+ `.json`) | does the manuscript's gate tally match its own table? | **it did not.** 58 gates and 20 passes are right; the split was **37 refusals and 1 unrun**, not 36 and 2 — only one row carries an unrun verdict, and the error predates every commit that touches the file, so it was never a W0 side-effect. States its classification rule before counting; the totals survive swapping either arguable row | app:ledger |
| `song_funnel.py` | did a re-learn quietly narrow the syntax layer? | prints the trade rather than deciding it, and alarms past a fifth. v9: species with a song 80, repeat classes 91, grammar chunks 2 389 | docs/22 §22.1-2 |
| `song_funnel_stages.py` (+ `.json`) | the whole funnel, stage by stage, on whatever store is current | **wider early, narrower late.** v9 against pre-v9: bouts 34 696 -> 40 526 and candidates 10 550 -> 17 140, but species with a song 98 -> **80** and placed bouts 3 741 -> **2 299**. Imports the build's own bout rule; cross-checks its species count against `song_funnel.py` | docs/22 §22.1-2 |

**Not in the table above, and their verdicts are not restated here because they were not
re-read when this note was written:** `function_transfer.py`, `interp_heldout.py`,
`mds_metric.py`, `perch_presence.py`, `periodicity.py`, `tear_dims.py`,
`topup_underfloor.py`. Each still carries its own gate in its own docstring, which is the
rule this directory runs on. Adding a row means reading the file, not guessing from the name.

`w5_field_retrieval.py` and `w6_t3_perch_species.py` import helpers from their siblings, so
run them from this directory (or with it on `sys.path`; the W6 pair does that itself).

The two W5 runners read one fixed matrix, `/tmp/birdy-debug/points-debug100.npz` — the
debug-100 `build --dump-points` set (214 154 points, 2 143 types, 96 MB) that docs/22 §22.6's
table was measured on. It is outside the repo on purpose and it is not backed up: regenerate
it with `build --dump-points` and expect the absolute numbers to move, since the arms are
only comparable to each other while the matrix is fixed.

The W6 runners need the `perch` extra and the 391 MB Perch ONNX, which downloads on first
use: `uv sync --extra perch`. They read the embedding only and never fetch Perch's class
list — the labels are the one thing docs/23 §23.6 says must never become ground truth.

The Phase-0 runners (`g1_g2_avonet.py`, `g2_pgls.py`, `g3_recordist_aggregation.py`,
`w2_learners.py`) need three open downloads, none of them in the repo and all of them
re-fetchable: AVONET (figshare 16586228) for body mass, and BirdTree's
`BLIOCPhyloMasterTax.csv` plus one Ericson Stage-2 tree set for the phylogeny. They land in
`out/external/`. `g2_pgls.py` imports `vcv` and `gls` from `w2_learners.py`, so run it from
this directory.

`w6_t1b_perch_postcutoff.py` and `w0_recordist_split.py` share one audio cache and one
embedding file, both under `out/`. **Their query carries `grp:birds` and that is not
cosmetic**: xeno-canto hosts bats, frogs, grasshoppers and land mammals, and without the
tag the first 6 000 results were 3 035 bats, 1 568 frogs, 926 grasshoppers and 471 land
mammals — zero birds, no error, and 256 kHz ultrasonic clips that decode perfectly well and
would have gone into a bird model as birdsong.
