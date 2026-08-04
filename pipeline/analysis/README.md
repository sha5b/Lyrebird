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
| `w0_full.py` | stage 2: the same experiment at 886 species on Perch **and** BirdNET | **PENDING — the fetch was still running when this row was written.** `w0_full.json` currently holds an INCOMPLETE placeholder and must not be read as a result | docs/24 W0 |
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
