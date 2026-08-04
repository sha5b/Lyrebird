# Lyrebird — READ THIS FIRST (2026-08-04, later): Phase 0 ran, the comparative biology is closed, and the whitepaper now carries the findings and a replication table

Phase 0 of `docs/24` was run end to end. **The headline: paper three does not exist. Paper
two is stronger than it was this morning.** Every gate was pre-registered before the run and
no threshold was moved afterwards. Full detail sits with each gate in `docs/24`, which now
carries a RESULT block under every one.

```
G1  fitted tract length vs body mass      FAIL      partial r +0.194, gate > 0.4
G2  the textbook mass/frequency result    PASS      r -0.542 on well-sampled species
G3  recordist confound after aggregation  PASS*     species +0.229 vs recordist +0.196,
                                                    but on 77 of 3 636 species -- see ARM D
W0  step-zero literature check            MOVED     the practice exists; the number does not
W0  method as pre-registered              BROKEN    both models trained on the eval corpus;
                                                    redesigned as a frozen-embedding probe
W0  pilot, frozen Perch, post-cutoff      NOT MET   9.68 points, gate > 10 -- but 2.44x the
                                                    errors, worse in 20 of 20 folds
T1b Perch recordist lift, unseen audio    CONFIRMED +0.441 on matched rows; the earlier
                                                    contamination alarm was overcautious
W1  phylogenetic signal in production      CLOSED    by G1, per docs/24's own rule
W3  source-filter independence            CLOSED    by G1, and it was written conditional
W2  learners vs non-learners              REFUSED   the measures cannot carry the question
W4  acoustic adaptation                   HELD      743 of 3 636 species qualify; margin thin
```

New, and none of it writes to the store:

```
pipeline/analysis/g1_g2_avonet.py            G1 and G2, with both excuses measured
pipeline/analysis/g3_recordist_aggregation.py  three arms, incl. the matched-row one
pipeline/analysis/w2_learners.py             PGLS over 10 BirdTree posterior trees
pipeline/out/external/AVONET.xlsx            11 009 species, Tobias et al. 2022
pipeline/out/external/BLIOCPhyloMasterTax.csv  BirdTree taxonomy + OscSubOsc
pipeline/out/external/EricsonStage2.zip      1 000 posterior trees, 194 MB
pipeline/out/external/species-f0.json        per-species median f0 and syllable count
```

## The four things worth knowing before anything else

**1. G1 failed, and it failed past both available excuses.** `L_eff` correlates with body
mass at partial r = +0.194 controlling f0 — right direction, p = 1.5e-11, less than half
the gate. A *perfect* predictor snapped to the same 39 discrete levels reaches r = +0.998,
so the quantization is not the ceiling; and r stays flat (+0.241 → +0.299) as per-species
syllable counts rise, so it is not thin sampling. Cranes do land 2 of 2 in the upper decile
at median 10.6 cm, which is a hint at n = 2 and nothing more.

**2. G2 passing is what makes G1's failure publishable.** The same pipeline recovers the
textbook mass/frequency relationship at the published effect size (our r = -0.542 on the 53
best-sampled species against Mikula et al. 2021's standardised -0.51). So "the corpus is
broken" is not available as an explanation for G1. A direct measurement sharpened with more
data; the fitted parameter did not. That contrast is the finding.

**3. G3 passed, and it qualifies our loudest number — but less than I first wrote.** At
syllable level the confound is recordist +0.488 against species +0.196. One point per
*recording* reverses it: species +0.229 against recordist +0.196 on matched rows. Arms A
and B were comparing lifts computed on different populations (25.9 % against 57.7 %
coverage, because `geometry.measure` drops groups under 8), so Arm C restricts to rows
where species *and* recordist both clear 8 and measures both at 100 % coverage. That
+0.033 is the number to quote, and it is thin.

**CORRECTED TWICE, same day. Read this before quoting G3.**

I first wrote that the confound was "mostly same-recording pseudo-replication". Wrong:
`geometry.blocks_for` already blocks by recording, so the +0.488 had same-recording
neighbours excluded. I then wrote that averaging strips the recordist's signature while
leaving the species' centre. Also wrong. **ARM D was added to measure it** — one population
of recordings, scored at both representations, nothing else changed:

```
                                       species   recordist
syllable-level, blocked by recording    +0.343     +0.295
the same recordings, averaged           +0.223     +0.198
```

Both fall by about a third, together — aggregation is not selective. And look at the top
row: **species already outranks recordist at syllable level on this population.** There is
no inversion for aggregation to have caused.

**The driver is the population**, and this time it is measured rather than argued:

```
r(log recordings, log recordists) over 3 853 species      +0.923
species with >= 8 recordings   median distinct recordists  17.0
species with  < 8 recordings   median distinct recordists   2.0
```

`measure` drops groups under 8, and at recording level that means "species with >= 8
recordings" — **77 of 3 636**. A species is well sampled in this corpus almost exactly
because several recordists contributed to it.

**That last fact is not new and the write-up must not claim it is** — the whitepaper's
Wall 2 already says "most species in this corpus are carried by a handful of recordists"
and names the action as "more recordists per species, in the data". The +0.923 is a number
for something already in print. **What is new is what it does to this gate:** the floor
that makes the recording-level test possible is the floor that selects away the confound
the test is looking for. So
**G3 passes on the sub-population where it can be measured, and that sub-population is
selected in a way that favours passing.** The gate's letter is met; its spirit is not.
Treat W4 as blocked rather than thin, and do not quote "+0.229 vs +0.196" without the
77-of-3 636 next to it.

**4. W2 is a refusal, not a null, and the difference matters commercially.** It ran at full
scale — 2 059 species, 10 posterior trees, learner status from BirdTree's own `OscSubOsc`,
mass and sampling effort as covariates — and every coefficient came back flat. Do not report
that as a null about vocal learning:

```
repertoire vs sampling effort     r = +0.852
repeat_types is zero on           97.7 % of species
repertoire median 5, p90 10       field oscine repertoires reach dozens
```

One measure is degenerate, another is 85 % a count of our own audio. **There is a large,
tidy, phylogenetically corrected null sitting in `w2_learners.json` that would look like
biology in a table.** It is a statement about a corpus with a median of 69 syllables per
species. Whatever gets written about W2 says r = +0.852 in the same paragraph.

## Two things found on the way that are not about the science

**`embeddings.f32` was stale and silently so.** It held 340 079 rows against the store's
378 224 syllables, written 2026-07-31, before the topup ingest. The v9 build *did* detect
this, refuse the file and re-embed in memory — and then never wrote it back, so the on-disk
sidecar stayed stale and every analysis script that reads it, `w6_t1_perch_recordist.py`
included, was quietly working on 90 % of the store. Regenerated with
`birdy-pipeline critic embed --store out/harvest-gan`: 378 224 x 32, 0 NaN, 5.3 s. **Any
recordist or species number produced by those scripts before 2026-08-04 was computed on a
partial store and should be re-run rather than trusted.**

**`descriptors.f32` is aligned to `points.jsonl`, not to `syllables.jsonl`.** 293 757 rows
of 28, which matches `points.jsonl` exactly. This is correct and not a bug, but it looks
like a third count that disagrees with the other two, and it cost time to rule out.

## What is next, and W0 changed shape

**W0's claim has to move, and the run is still worth doing.** Half of it is twelve years
old: Stowell & Plumbley 2014 (PeerJ 488) held out one recordist at a time with our exact
rationale in their words, and the Cornell CBI dataset is split the same way. What nobody
has published — checked against the sources, not the abstracts — is **what a
recordist-blocked split costs a current foundation model.** So W0 stops being "block your
splits" and becomes "here is the number".

Two constraints on that run, both discovered in the literature pass:

- **BirdNET cannot be evaluated on an XC-derived corpus.** It is excluded from BirdSet for
  training-set leakage, having been trained on xeno-canto. "Reproduced on both models" needs
  a different corpus, a separate BirdNET report with the contamination stated, or a
  different second model. Settle this before the run.
- **G3 revised the expected effect down.** A benchmark split is a *recording*-level
  operation, so the leakage W0 predicts should be read off the recording-level lift
  (+0.196), not the syllable-level one (+0.488). The gate of "more than 10 points" should
  not be treated as likely on the strength of the larger number.

Cheap and still owed: **G2 under PGLS.** It is OLS today; BirdTree is now on disk and
`w2_learners.py` already has a working VCV and GLS, so this is an hour.

## Later the same day: G2's PGLS landed, and W0's method turned out to be broken

**G2 now passes both halves of its gate** (`analysis/g2_pgls.py`). Pagel's lambda is
fitted by maximum likelihood rather than assumed, over 10 BirdTree posterior trees:

```
                        n     standardised slope   fitted lambda
all species          2 059          -0.211             0.130
n_syllables >= 100     651          -0.248             0.000
n_syllables >= 400      76          -0.560             0.291
Mikula et al. 2021   5 085          -0.510
```

Negative and significant everywhere. The magnitude only meets the published figure on the
deep arm — and **lambda tells you why**. A fitted lambda of 0.000 says our species-level f0
residuals carry no phylogenetic signal, which cannot be true of birdsong. Measurement error
pushes lambda to zero and attenuates a standardised slope by the same mechanism, and both
recover together at depth. **The shortfall is our noise, not the birds.**

**A method trap worth remembering.** The first attempt forced Brownian motion, which is
what "PGLS" is usually taken to mean. It returned slopes spanning **-1.962 to +0.001 across
ten trees from one posterior** — crossing zero. Not a numerical fault: every pruned tree was
exactly ultrametric and positive-definite, condition number ~1e6-1e7. Forcing a model the
trait does not follow puts the estimate on a few deep splits that differ between trees.
Fitting lambda collapsed the range to [-0.214, -0.207]. **Do not trust a PGLS number from
this corpus with lambda assumed.**

**W0 cannot be run as written, and the reason is in docs/24 §W0.** BirdNET is excluded from
BirdSet for training-set leakage — that was known. Checking the other model made it worse:
**Perch 2.0 trained on Xeno-canto *and* iNaturalist** (arXiv 2508.04665). Both candidate
models have trained on the corpus W0 proposed to evaluate them on, so a top-1 comparison
between a random and a recordist-blocked split cannot separate leakage from memorisation.

The redesign is cheaper than the original: freeze the model as a feature extractor, embed
once, and put the split on a **linear probe** trained twice on those fixed embeddings. The
contamination is then identical in both arms and cancels. The claim narrows to "a
recordist-blocked split costs a linear probe over frozen Perch/BirdNET features N points",
which is still a number nobody has published.

**And this lands on a claim we have already published — but more gently than first written
here.** Perch trained on iNaturalist research-grade audio; **5 368 of our store's recordings
are iNaturalist**, and `w6_t1_perch_recordist.py` ran Perch over exactly that cache.

**"Contaminated" was applied to two different tests and only fits one of them.** For W0,
which measures accuracy, memorisation is fatal — hence the redesign. For the recordist-lift
arm it is speculative, because Perch was **never given recordist labels**, because
same-recording pairs are **already blocked out**, and because an overfitting species
classifier gets *better* at ignoring channel and microphone — the very things carrying a
recordist's signature — which would lower recordist lift rather than create it.

So T1b is worth running because the whitepaper leans on Perch as an *independent*
replication and training overlap is what independence costs. **The honest expectation is
that it confirms the original arm.**

**T1b RAN, and it confirms it. The alarm was overcautious.** 2 158 quality-A bird
recordings uploaded to xeno-canto *after* Perch 2.0 — audio it provably never trained on —
137 recordists, 827 species:

```
ARM A  every recording       species +0.742 (28.2 % cov)   recordist +0.159 (99.8 % cov)
ARM B  matched rows, n=293   species +0.750 (100 %)        recordist +0.441 (100 %)
```

Arm B is the number to quote: both groupings on identical rows, recordist lift **+0.441,
"strong", p at the permutation floor**. **Perch was not recognising its own training data.**
The recordist confound is a property of the archives that an outside model reads off
recordings it has never seen — which is the claim the whitepaper actually makes, now on
firmer ground than before. Arm A shows the same coverage trap G3 hit (28.2 % vs 99.8 %),
which is why Arm B existed from the first run this time.

## And the W0 pilot ran: 9.68 points, just under its own gate

`analysis/w0_recordist_split.py`. 62 species with >= 6 recordings and >= 2 recordists, 730
recordings, frozen Perch features, post-cutoff audio, 20 paired folds:

```
                     random split   recordist-blocked
top-1                   93.29 %          83.61 %
DROP                     9.68 points                  gate > 10.0   NOT MET
per fold            mean +9.68  sd 5.08  blocked worse in 20 of 20 folds
as error rate         6.71 %  ->  16.39 %             2.44x the errors
```

**The gate is not met and the threshold is not being moved.** But points are the wrong unit
at 93 % accuracy, and that belongs next to the verdict: the same 9.68 points is **2.44x the
errors**, and blocking was worse in **every one of 20 folds**. A re-registration should
state the bar as an error-rate ratio.

**The class-set correction is why the number is trustworthy.** Scored as the folds fall it
is 9.14 points, because a blocked split strands whole species and leaves that arm a smaller,
easier label set (49.9 classes against 62). Pairing each blocked fold with a random fold on
its *own* class set gives 9.68 — the bias ran exactly as predicted, and removing it made the
effect bigger.

**The BirdNET arm is probably clean, and it is the stronger of the two — so the whitepaper
sentence survives.** BirdNET v2.4 trains on Xeno-canto, Macaulay, BirdSet soundscapes and
internal data; **iNaturalist is not among them**, and `w6_birdnet_arms.py` runs on the same
iNat cache. The whitepaper's BirdNET result is that it *raises* the recordist lift by 24 %.
**A model with no documented reason to have seen this audio finding more recordist
structure in it than our own critic does is evidence the structure is in the recordings,
not in memorisation.** Caveat that must travel with it: BirdNET's training set is not
publicly documented, so "probably clean" is the strongest available claim.

## The whitepaper now carries Phase 0, and there is a replication table

`docs/whitepaper/arxiv/main.tex`, three edits:

- **`\subsection{Both questions were then asked, and this is what they answered}`**, new,
  inside `sec:next` and labelled `sec:phase0`. Six paragraphs, most consequential first:
  anatomy is closed; the textbook control passes and localises the failure; W0's 9.68
  points; T1b confirming the confound on unseen audio; G3's selection effect; W2's refusal.
  **The two prediction paragraphs above it are left exactly as written** so the forecast and
  the outcome read together — the sentence "Neither question is answered here" is replaced
  by a pointer rather than deleted.
- **`Table~\ref{tab:phase0}`**, a longtable in the same design as the gate ledger
  (`what was tried / the gate set in advance / what it measured / how to reproduce`), with
  the runnable command in every row. That is the "so everybody can replicate our steps"
  artefact. It closes with the `grp:birds` warning, because that failure produced 6 000
  recordings and no error.
- **Wall 2 gains two sharpening sentences** — Perch's $+0.441$ on post-cutoff audio, and
  `r = +0.923` for recordings-per-species against recordists-per-species, which is the
  number for a sentence Wall 2 already had in words.

Statically validated as before: braces balanced, environments nested, 0 dangling refs, both
longtables matched. The two `\todo`s (Zenodo DOI, acknowledgements) are untouched and still
need the owner.

**It also compiles — see "Paper" under *What is still open* below for the real account.**
I wrote here that `main.tex` had never been compiled and that the new longtable would
merely produce overfull boxes. **Both halves were wrong**: `tectonic` is on this machine,
`build/main.pdf` was already tracked, and the new table was a *hard error*
(`longtable not in 1-column mode`) until it was wrapped in `\onecolumn`. The build is clean
now at 39 pages. Do not trust the "never compiled" line if it reappears anywhere in this
file — it is stale in two older entries below.

## The W0 full run is BUILT AND RUNNING, and paper one exists

Read this before the "still open" list below, which it partly supersedes.

**The pilot's two limits were ours, not the archive's.** Its catalogue held exactly 6 000
recordings, which was `SEARCH_PAGES = 60` times 100 a page. The same query reports **21 928**.
And it selected by *recordist*, a rule inherited from `w6_t1b_perch_postcutoff.py` whose unit
was the recordist. W0's unit is the species, and that is what left 62 scorable classes out of
827 species fetched.

```
886 species clear W0's floor (>=6 recordings from >=2 recordists), over 13 646 recordings.
MAX_PER_SPECIES = 12 trims that to 8 321 without losing a single species: the pool is
skewed 6 / median 9 / max 338, so uncapped a handful of species would supply a fifth of
the probe's training rows. The cap is recordist-aware by round-robin -- a plain sample of
12 would strip a 19/1 species down to one recordist and make it unscorable AFTER it had
been counted as scorable. An assertion checks the scorable set is unchanged.
```

**BirdNET is no longer blocked, and this is the methodological point.** docs/24 recorded that
"reproduced on both models" could not use an XC-derived corpus, because BirdSet excludes
BirdNET for training on xeno-canto. BirdNET **V2.4 was released June 2023** (EfficientNetB0,
1024-d, which matches the backbone `w6_birdnet_arms.py` already runs). Uploads after
2025-09-01 postdate it by two years and Perch 2.0 by a month, so the discriminator is *upload
date* and not archive provenance, and the constraint dissolves rather than being worked around.

**Measured before optimising, twice.** CPU embedding is 0.43 s per recording for *both* models
against a 2.3 s download pace, so `onnxruntime-gpu` would buy nothing and was not installed.
The probe is the opposite: 886 classes in 1 536 dimensions is ~$10^{10}$ multiply-adds per
lbfgs iteration, so it moved to torch on the GPU at **1.0 s a fold**. `w0_probe.py --verify`
is the check that it is the same estimator as the pilot's scikit-learn one -- they agree to
**0.91 points** on the pilot's real features, and it fails loudly if they do not.

```
analysis/w0_full_catalogue.py   pages the complete catalogue and reports what it supports
analysis/w0_full_fetch.py       selects, downloads, embeds through both models, resumable
analysis/w0_probe.py            the GPU probe + --verify against sklearn
analysis/w0_full.py             three arms, the gate, and a class-count sweep
docs/whitepaper/w0-arxiv/       PAPER ONE. 6 pages, builds clean. Results are \todo.
```

**Do not read `analysis/w0_full.json` yet.** It currently holds an INCOMPLETE placeholder.
An early run is not merely underpowered, it is **biased low**: at 20 % embedded only 32
species cleared the floor, and the ones that clear first are those with the most recordings,
which correlate with recordists per species at r = +0.923. That is G3's trap exactly -- the
floor that makes the test possible removes what it is testing for.

**Also fixed while there:** the pilot scored **730** recordings, not 2 158. The larger figure
was the embedded population before the two-recordist floor, and the whitepaper said "On 2 158
recordings ... reaches 93.29 %". Corrected in both papers.

## The song funnel was re-measured on v9, and it narrowed

`fig_song_funnel` carried a note saying it was pinned to the 340 079-observation store and
that the figure "moves as a unit or not at all". `analysis/song_funnel_stages.py` now
recomputes every count it draws, from one store in one pass, **importing**
`learn.bout_sequences` and `learn._collapse_runs` so there is only one definition of a bout.

```
                       pre-v9      v9
observations          340 079   378 224
bouts                  34 696    40 526
candidates             10 550    17 140
species with a song        98        80   <- NARROWED
placed bouts            3 741     2 299   <- NARROWED
```

Wider early, narrower late: a finer typing splits one physical repeat across several type ids,
so fewer bouts clear `SONG_MIN_CLUSTER = 6`. This is the trade `song_funnel.py` was written to
catch. Repeat classes still roughly double the songs (46 species to 80, 96 song types to 187),
so the adoption stands, but **"double" is a pre-v9 number and the v9 factor is 1.7** -- the
subsection title now says "roughly".

The sequence-statistics and grammar-order numbers, the song-detector arms table and the gate
ledger were **left at their pre-v9 values on purpose**. Those are different studies and a
historical record. Updating them would claim re-runs that never happened, so the findings
section carries an explicit reconciliation paragraph instead.

`fig_corpus`'s clay annotation is also fixed: it ran off the panel ("...twelve sp") and its
leader started where the "13" label sits, so it struck the number through.

## What is still open, in the order I would take it

**Science**

```
W0 full run   RUNNING as of 2026-08-04 12:10, ~2.5 h of downloads left. See the section
              above. Stage 1 is `w0_full_fetch.py`, stage 2 `w0_full.py`, and paper one is
              drafted with the results section marked \todo. Nothing to decide.
W4            BLOCKED, not thin. G3 only passes on the 77-of-3 636 well-sampled species,
              which is the population selected against the confound. Do not run it behind
              a "+0.033 margin" reading; that reading is retracted.
W2            refused until the corpus is deeper per species (median 69 syllables).
W1, W3        closed by G1. Reopen only if a tract estimate ever passes it.
G2 re-check   the deep arm rests on 76 species. Worth re-running as depth grows.
```

**Corpus** — both are owner decisions, not tasks:

```
988 species under the fitting floor: ~24 700 obs needed against 21 776 headroom, so it
crosses syllableCap and _trim starts evicting the largest species' oldest recordings.
The store's rows are still segmented full-band; the band fix is in the code and has not
touched the corpus. Re-deriving means new patches, descriptors, embeddings and typing.
```

**Paper** — it compiles, and the new longtable was a hard error, not overfull boxes:

```
tectonic IS on this machine (~/.local/bin/tectonic), and build/main.pdf was already
tracked from a 1 Aug build -- so "never compiled" was wrong. What had never been
compiled was main.tex WITH the new four-column longtable, and that did not build:

  ! Package longtable Error: longtable not in 1-column mode.

`longtable` refuses to run inside a twocolumn body, and the table is 14.4 cm of rules
against an 8.6 cm column, so it was authored for full width anyway. It is now wrapped
in \onecolumn ... \twocolumn, the same treatment tab:ledger already gets in the
appendix, and its last column widened 4.4 -> 5.6 cm to swallow the unbreakable
\texttt paths (15.6 cm of rules + 1.13 cm tabcolsep against 17.2 cm of textwidth).
```

**The build is now clean**: 39 pages, **0 undefined references, 0 undefined citations, 0
overfull vboxes**, and 2 overfull hboxes of 1.7 pt and 1.5 pt — both far below the ~20 pt
where a rule shows in the margin. Table 10 lands on page 29 with all six rows on one page.
`build/main.pdf`, `main.log` and `main.blg` are refreshed to this build.

```
Rebuild:  cd docs/whitepaper/arxiv && tectonic -X compile main.tex --outdir build
```

**One cosmetic consequence for the owner to accept or reject.** `\onecolumn` ejects the
page, so Table 10 sits alone on page 29 with about two thirds of it white. The alternative
is a `table*` float, which would let text fill the page — but a `table*` cannot break
across pages, and this table gains a row every time a gate is run (the W0 full run is next),
so it would fail silently the first time it outgrows a page. The breakable version is the
one that is safe to leave unattended, which is why it is what is committed.

Still open, and still the owner's:

```
Two \todo items: the Zenodo release DOI, and acknowledgements (an explicit none is fine).
Both render as loud red [TODO: ...] in the PDF, so neither can ship unnoticed.
fig_corpus's clay annotation overruns its panel (pre-existing, inside the figure asset).
fig_song_funnel is pinned to the pre-v9 store; its three panels move as one unit.
```

`\S`sec:next no longer needs the fix the last handoff asked for — it already reads *"Both
were subsequently run \dots{} neither opened the door it was aimed at"* and points at
`\S`sec:phase0. That item is done; this note is what was stale.

**App** — the monitor capture is now verified, and the check found a bug:

```
Listen defaults to computer audio and reaches it through the output's monitor device
(getUserMedia), so no screen picker. VERIFIED at the sound-server layer, no speakers
and no browser needed: a sink's monitor carries the mix whether or not anything is
plugged in, so the test is to play a known probe and read the capture's spectrogram.
```

A 4 s probe — 1 s each at 1 kHz, 3 kHz, 6 kHz, then a 500 Hz→10 kHz sweep — was played to
the default sink while `parecord` took its monitor. Aligned by cross-correlation, the
capture returns **1000.0, 2999.9 and 6000.0 Hz** (error ≤ 0.1 Hz) at 18–23 dB over the
other audio on that sink, and the sweep rises linearly to 10 kHz. On an otherwise idle
sink the capture was bit-exact: peak 0.06000 against a probe amplitude of 0.06, noise
floor at −140 dBFS. **The monitor route delivers the real, unprocessed, full-band mix of
every application on the sink** — which is exactly what "computer audio" has to mean.

**The bug: `monitorDevice()` picked the wrong monitor.** It was `find`-ing the first
`audioinput` whose label matches `/monitor/`, but a sound server publishes one monitor per
sink and every sink that is not being played to is silence. This machine has **ten**
monitor sources; measured over a 2 s capture with audio playing, nine sat at the noise
floor (−280 dBFS, digital zero) and only the default sink's monitor carried anything
(−13.5 dBFS). Note the old note above was misleading on this point: `HiFi__Speaker__sink.monitor`
does exist, and it is one of the silent nine, because output goes to a Bluetooth sink.

`engine.ts` now pairs the monitor to the default output by `groupId` (Chrome gives a sink
and its monitor the same group), falling back to the old first-label-match when `groupId`
is empty — so it is no worse than before in the worst case. **What still needs a browser:**
that Chrome really does populate `groupId` on PulseAudio monitors. If it does not, the
fallback puts us back on today's behaviour, silent monitor and all.

One measured quirk worth knowing: a sink waking from `SUSPENDED` **drops its first ~0.9 s**
to silence and is sample-accurate after that. An empty first second of Listen is the sound
server starting, not a missing signal. Both facts are now in the `engine.ts` comments.

**Disk**: `pipeline/out/audio-postcutoff` is 13 GB of fetched xeno-canto audio. Outside the
repo, re-fetchable from its own cached `_catalogue.json`, safe to delete.

## The Words tab was reworked, and it now refuses on purpose

Owner's ask: typing should be read for *meaning*, and the bird's notes should say what the
utterance could be. **What the tab did before was less than it looked like** — the primary
"Sing the words" button ran a path where the text contributes exactly two numbers, a
syllable count and which indexes start a word. Semantics existed only as a hand-written
table of 68 keywords across 5 species.

It now classifies into one of **five functional categories** and reports what *this*
species' authored calls in that category are documented to do, with their own evidence
badges and citations. The design rule, and `docs/03` §3.6 is the long form:

```
link 1   typed English -> category      OURS.  always `invented`, said on its own line
link 2   category -> this species' call  THE CORPUS'S. keeps its own badge and refs
```

The claim is *"the functional category is real to the bird; the assignment of your words to
it is ours"*. The first half is defensible on Elie et al. 2025 (Science 389:1210-1215):
zebra finches' own confusion errors between call types cluster by behavioural context
rather than acoustic similarity. The second half has no literature behind it and there is a
structural reason it cannot — call form is non-arbitrary, so there is no arbitrary
signifier to attach an English word to.

**The refusal is the majority path and is designed as one.** 12 species of 2 650 carry any
authored function, so a randomly picked bird refuses 99.55 % of the time. The picker keeps
all 2 650 and marks the 12 with a dot; narrowing it would have made the feature work nearly
always while presenting the best 0.45 % of the corpus as if it were the corpus.

```
app/src/lib/lang/functions.ts        categories, lexicon, classifier, refusal text
app/scripts/verify-functions.mjs     46 checks, `npm run verify:functions`
app/src/lib/lang/grammar.ts          songPhrase() exported; the keyword table is now dead
app/src/routes/+page.svelte          the reading, the one-click category override
docs/03-decoding-science.md §3.6     what the tab may and may not claim, with sources
```

`functions.ts` deliberately imports **no** framework path. `data/assets.ts` pulls in
`$app/paths`, which only resolves inside SvelteKit, so depending on it would have put the
module out of reach of the bare-node verify harnesses; `speciesById` is a one-line find and
is local. That is what lets all 46 checks run against the real shipped inventory.

Three things refused in writing, each because someone will ask: the 16 239 `unlabelled`
fitted types may not be recruited to widen coverage (no sender state, no receiver, no
context — Rutz et al. 2023's own caution about archives); `d_abc`, the reversed great tit
control, is not offered as a message because in playback it elicits neither response; and
embedding typed text against the fitted types is refused outright, because with no parallel
data a fluent hallucination scores identically to a correct answer.

**Still open on this, and it is the owner's call.** The lexicon is a few hundred hand-written
terms. It will miscategorise — "I miss you" reads as contact and produces a plausible-sounding
wrong answer with a real citation attached, which is the failure mode that matters here. The
one-click category override is the mitigation and it is also free instrumentation: every
correction is a labelled datum. Nothing currently records those corrections.

## Carried over from the entry below, still true

- `fig_corpus`'s clay annotation overruns its panel.
- 988 species under the fitting floor. **W2 gives this a second reason to matter**: the
  repertoire measure saturates near 8 types by 100-300 syllables, so depth per species, not
  species count, is what would make W2 answerable.
- `fig_song_funnel` is pinned to the pre-v9 store.
- Two `\todo` items in `main.tex`, both needing the owner. (The "never been compiled" that
  used to follow this line was wrong: tectonic is installed and the build is clean at 39 pages.)

# Lyrebird — (2026-08-04): v9 is installed, five noise gates are measured dead, and the whitepaper leads with its findings

## START HERE NEXT CHAT

Two research runs are agreed, and everything else in this list is small. Owner asked which of
the two would genuinely add to the field and answered **both**. They are independent, each is
about a day, and neither blocks the other. The full specification with pre-registered gates is
`docs/24-what-this-corpus-could-add-to-ornithology.md`.

### 1. W0 — is benchmark accuracy in this field inflated by recordist leakage?

The widest-reaching result available, and **it does not depend on any part of our pipeline
being correct**, because it runs public models over public corpora.

```
corpus   BirdSet XCM or XCL (Hugging Face), or the BirdCLEF splits  -- NOT our store
models   Perch 2.0 (already wired: perch.py, weights cached) and BirdNET
measure  species retrieval / top-1, twice, changing ONE thing:
           a) the standard random split
           b) a recordist-blocked split (all of one recordist's recordings on one side)
gate     > 10 points of top-1 drop, on >= 1 public corpus, reproduced on both models
```

**Step zero is a literature check, before the run.** Domain shift and focal-to-soundscape
generalisation are known problems here, and recordist-blocked evaluation may already exist
under another name. If it does, cite it and move to G1.

Why us: we measured the mechanism at +0.488 recordist against +0.196 species, four removal
attempts failed, and both external models carry it. A negative result is also publishable and
retires our loudest complaint.

### 2. G1 — does the fitted tracheal length track body mass?

This decides whether **any** comparative biology is possible with this corpus.

```
data     L_eff per species, 1 621 species, parsed from out/v9/learn.log
         AVONET (Tobias et al. 2022, open, 11 009 species) for body mass
method   log L_eff on log mass, partial on log f0, EXCLUDING clamped species
gate     partial r > 0.4 over >= 800 unpinned species,
         AND the known long-trachea clades in the upper decile
```

Known before the run, and three of the four facts are discouraging: `L_eff` is a deterministic
restatement of the fitted tract f1 (r = -1.000 log-log), it takes only **39 distinct values**,
and **388 species (24 %) sit on the 1.4 cm floor** with 11 on the 14.3 cm ceiling. The one
encouraging fact is that it correlates with the species' own median f0 at only **-0.206**, so
it is not pitch in centimetres.

If G1 passes, W1 to W4 in docs/24 open up (phylogenetic signal in production parameters,
learners against non-learners, source-filter independence, acoustic adaptation). If it fails,
write the negative result and close the biology.

### 3. Carried over, small, and named so they are not lost

- **`fig_corpus`'s clay annotation overruns its panel.** Pre-existing: byte-identical at
  `git show HEAD`, so the sixth row did not cause it. Either shorten the text or move the
  `xytext` left.
- **988 species are still under the fitting floor** (median 11, max 23). A correctly filtered
  pass needs ~24 700 observations against **21 776 of headroom**, so it crosses `syllableCap`
  and `_trim` starts evicting the oldest recordings of the *largest* species. Raising the cap,
  accepting eviction, or stopping at 2 650 species is a decision, not a task. `--species-file`
  now works, so the pass itself is one command.
- **`fig_song_funnel` is pinned to the pre-v9 store** in its docstring and caption. Its three
  panels are one study, so it moves as a unit or not at all. Re-running the full funnel on v9
  is what it needs.
- **Two `\todo` items left in `main.tex`**: the Zenodo release DOI, and the acknowledgements,
  which can legitimately be an explicit statement of none. Both need the owner.
- **`main.tex` has never been compiled.** There is no TeX toolchain on this machine. It is
  validated statically only: braces balanced, environments nested, 0 dangling refs, 19 figures
  with PDFs. Expect overfull boxes on the first real build.
  <br>**FALSE, corrected 2026-08-04 later — left in place because this is a dated entry.**
  `tectonic` is at `~/.local/bin/tectonic` and `build/main.pdf` was already tracked. See the
  top entry for the real state: the build is clean at 39 pages.

### 4. State, so nothing has to be re-derived

```
store        pipeline/out/harvest-gan   378 224 observations, 3 636 species with syllables
             snr on 97.1 % of rows, segmentBand [400, 12000] recorded in state.json
             headroom 21 776 of syllableCap 400 000
installed    app/static/birdy = v9: 387 287 points, 16 380 knots, verify passes
             data/learned-inventory.json = 2 650 species, 16 283 types
             committed as 569ddef; ROLLBACK IS 94c4ad8 (348 461 points, 2 423 species)
             — named explicitly because HEAD has since moved and "HEAD~1" no longer
             points at the pre-v9 build
audio cache  pipeline/out/audio-cache, 6 453 wavs, 6.3 GB, iNat only
perch        runs; weights in the HF cache; analysis/perch_presence.py works
whitepaper   findings section now BEFORE the walls; 0 em dashes in prose; author set;
             new section "What this corpus could be asked next"
```


The section below asked what filtering would keep a noise-only recording out and offered an
SNR floor or a tonality test as the answer. **Both are measured dead, a third candidate is
measured dead, and the reason all three failed is the finding: the syllables had already
been chosen by the noise before any per-syllable gate could see them.**

```
INAT227259, energy below 400 Hz                          98.7 %
   ...and F0_MIN_HZ, the floor of every description       400 Hz
```

`_segments` thresholds at `ONSET_REL` = 14 % of the recording's **full-band** envelope peak,
while `track_f0` and `measure_harmonics` throw away everything outside 400 Hz – 12 kHz. On a
file carrying wind, handling noise or traffic under it, those two facts disagree and the
segmenter wins: it slices the rumble, and the description then reads whatever tonal haze
happens to sit inside those spans. **A per-syllable filter cannot help, because the spans
are wrong.** That is why each candidate gate failed on the owner's own example:

```
                          INAT227259        the corpus              verdict
absolute SNR floor        med 11.5 dB       med 17.1 dB             would need ~19 dB
                          min  8.2 dB                               -> over half the corpus
spectral flatness         0.044             med 0.106               21st percentile
                                                                    -> reads MORE tonal
Perch 2.0 taxon_max       0.899             med 0.541, p90 0.919    88th percentile
                          Passer domesticus                         -> rejecting it costs 89 %
```

Perch was the owner's chosen route and it is the sharpest of the three refusals: **Perch
reads that recording as a bird with high confidence**, `Trogon curucui` (the store's own
label) in its early windows and *Passer domesticus* up to 0.899 later. Ranked against a
200-recording sample of the cache it sits at the 88th percentile, so a threshold low enough
to reject it takes 89 % of the corpus with it. `analysis/perch_presence.py` is that
measurement, runnable, with the distribution and the cost of every threshold; nothing is
wired into ingest, and the module docstring says why in the first paragraph.

The spectrogram is what settled it. INAT227259 is not empty — under a loud sub-400 Hz
rumble there is a very regular ~1.5 kHz pulse train, broadband ticks, and a banded
vocalisation at 4–6 kHz around 22–26 s. The owner heard the rumble, Perch heard the bird,
and both were right about a file whose 95 stored "syllables" have an f0 median of 992 Hz
against the corpus's 2 762 — the segmenter had described neither.

## 1. The fix: the segmentation now hears the band the description uses

`learn.SEGMENT_BAND_HZ = (F0_MIN_HZ, F0_MAX_HZ)`, the band every measurement below it was
already restricted to. `band_limit` is a 4th-order Butterworth under `sosfiltfilt` —
zero-phase, because the whole point of this pass is *when* a syllable starts and a causal
filter would move every onset by its group delay.

Not a rare shape, and that is the argument for changing the default. Over a 200-recording
sample of `out/audio-cache`, the share of energy under 400 Hz runs **median 35.5 %, p75
86.8 %, p90 97.5 %: 23 % of recordings put over nine tenths of their energy outside the
band that describes them.**

Measured over 120 cached recordings, both paths run on the same audio:

```
                       full-band        band-limited     per recording
syllables (total)         3,882            3,009          -22.5 %
f0 median                2,622 Hz         3,179 Hz        up on 67 %
snr median                12.73 dB         15.85 dB       +3.10 dB, up on 81 %
described by neither 13,  full only 3,  band only 6
```

Fewer syllables, higher, and better separated from their own floor — which is what "stop
segmenting on rumble" should do. **A spectral mask was tried first and is in the code's
history for a reason:** at `ENV_FRAME` = 512, 44.1 kHz gives 86 Hz bins, so `F0_MIN_HZ` is
bin 4.6 and a Hann main lobe is four bins wide — the band edge is as wide as the band's own
lower reach. On the self-test fixture the mask found **11 segments where there are four**,
peak-to-median 15 against the filter's 234 060. A window's sidelobes are not a stopband.

**What this does not do, stated plainly: it does not make INAT227259 clean.** Band-limited,
that file yields 105 syllables at f0 median 1 455 Hz — the segmenter has stopped chasing the
rumble and started chasing the 1.5 kHz pulse train, which is the next loudest thing in the
band and is probably an insect. The fix makes the segmenter *coherent with the description*
and improves the corpus measurably. It is not an "is this a bird" gate and no gate here is.

Also: `snr`'s numerator is now read in the same band as its floor. Dividing a full-band
segment level by an in-band floor is how a file that is 98.7 % rumble reports a healthy SNR —
the numerator counts the rumble and the denominator does not, so the worse the rumble the
better the number. **The legacy full-band path is left arithmetically untouched**
(`segment_band=None`), because §2 writes 188 986 rows through it and "exactly" is the only
property that makes such a pass safe.

## 2. The 59 % that was unmeasured is now 3.2 %, and the audio never had to be re-fetched

The section below says an SNR floor "cannot touch the 199 993 rows with no `snr` without
re-measuring them". **Re-measuring them was available on this disk the whole time**, and
that was the most useful correction of the round:

```
rows with no snr                    199,993
  ...that are iNat                  188,986      94.5 %
iNat recordings in the store          5,368
  ...still in out/audio-cache         5,366      6.3 GB
```

`birdy-pipeline quality remeasure` (new, `quality.py`) fills them. **It is exact, not
approximate:** it does not re-segment, it reproduces the segmentation the store already
holds and measures the two quality fields on the segment the stored row names, matching by
`(recording_id, order)` and verifying `start`/`dur` agree to a millisecond before writing
anything. On the whole store that verification passed on **188 986 of 188 986 rows — zero
drifted, zero absent, zero missing wav.**

Ran, verified against a backup line by line:

```
rows                340,122 -> 340,122      order preserved
keys that differ    ['clipped', 'snr']      and nothing else
snr coverage        41.2 % -> 96.8 %        329,115 of 340,122
clipped = True                        840
```

Row order is the only thing pairing `syllables.jsonl` with `patches.f16`,
`descriptors.f32`, `points.jsonl` and `typing.json`, so the write is a line-for-line stream
rewrite plus `os.replace`, and it never calls `HarvestStore.save` — which would rebuild all
five files from memory to change two floats.

**The corpus is quieter than the measured 41 % suggested, so the floor costs in the section
below were computed on a biased sample.** The real distribution, now that 96.8 % of it is
measured:

```
                 was (41 % subset)      now (96.8 %)
median snr             17.13 dB             11.94 dB
below  3 dB            (6.2 %)              10.9 %      35,889 rows
below  6 dB           (13.9 %)              23.7 %      78,036 rows
below 10 dB           (26.6 %)              42.5 %     139,717 rows
min / max             -9.7 / 81.0        -12.04 / 169.38
```

That 169 dB maximum is a recording whose frames outside its syllables are near-digital
silence, so the floor estimate collapses. It is not a bug in the measurement but it is a
reminder that `snr` is a ratio inside one recording and nothing more.

## 3. Consequences worth knowing before the next run

- **`out/harvest-gan` is now a mixed store**: 340 122 rows segmented full-band, anything
  added from here segmented in-band. `state.json` records `segmentBand` so a store says
  which regime it was last ingested under — and the field's comment says outright that it
  describes the latest ingest, not every row.
- **A re-learn will no longer reproduce the installed inventory.** `quality_weight` changed
  for 188 986 rows, so the byte-for-byte reproduction that the v8 chain used as an integrity
  check is spent. That was the cost the owner accepted when choosing to write the
  re-measurement into the store rather than to a sidecar.
- **The existing rows cannot be re-segmented cheaply.** The iNat half *is* re-derivable from
  the cache, but new spans mean new patches, descriptors, embeddings and typing — a rebuild
  of five files, not a field edit. Not attempted.
- **`--dry-run` first, always.** The pass is naturally idempotent (a row with an `snr` is
  left alone), so a second run now finds only the 11 007 xeno-canto rows and reports them
  unreachable by design.

## 4. Tests

- `learn.self_test` §12: five properties of the band. Rejection over 40 dB on a 60 Hz rumble
  at 0.9 under 5.2 kHz chirps at 0.05; onsets do not move (zero phase); the band envelope
  peaks inside a chirp; the segmenter returns **4 of 4 chirps that the full-band path misses
  entirely**; and `segment_band=None` still computes the old SNR formula, checked against
  the arithmetic spelled out by hand.
- `quality.self_test`: `measure_recording` reproduces
  `extract_syllables(segment_band=None)` exactly — timing, SNR to 0.005 dB, and the clipping
  flag. This is the one property the tolerance check *cannot* see, since it compares timing
  only: a pass that segmented identically but computed `snr` differently would match every
  row and write 188 986 wrong numbers. It also asserts the band-limited path reads as
  drifted, or the guard has nothing to protect. Wired into the CLI command, which runs it
  before touching the corpus.
- Every module self-test still passes: `features`, `galaxy`, `harvest`, `learn`, `quality`,
  `inverse`, `respiration`, `twovoice`.
- `scipy` is now an explicit dependency. It was already present transitively through
  scikit-learn and umap-learn, which is exactly why it needed writing down: a core module
  now imports `scipy.signal` at module scope on every ingest.

## 5. The iNat sweep is RUNNING

Held until the gate landed, then started, so the top-up is ingested under the new
segmentation rather than needing the same audit again afterwards:

```
setsid nohup uv run birdy-pipeline sources fetch --source inat-sounds \
  --species-file out/underfloor-species.txt --per-species 1 --limit 1500 \
  --keep-audio out/audio-cache --store out/harvest-gan > out/inat-topup.log 2>&1 &
```

`setsid` for the reason the section below records: `( cmd & )` does not survive the shell
exiting. Progress is in `out/inat-topup.log`; it reports `110 498 acceptable Aves recordings
for 1160 named species` and streams the 81 GB archive until 1 500 are ingested.

**`--keep-audio out/audio-cache` was added and is not in the earlier plan.** AGENTS.md
sanctions it for the current training phase, and everything in §2 and §4 depends on cached
audio existing: without it the new rows would be the only ones in the corpus that can never
be re-measured or re-examined. Cost is ~1 MB a recording, so ~1.5 GB on top of the 6.3 GB
already there.

Two hazards while it runs:

- **Do not start a harvest from the Learn page.** The control server builds a fresh
  `HarvestStore` per request (checked: server.py lines 421, 476, 638, 673, 902), so it cannot
  clobber §2's re-measurement with stale memory — but two processes holding the store and
  saving would make the last writer win, and the sweep is the one with hours of work in it.
- `store=NNNNNN` in the log is the **descriptor** count against `cap` 600 000, not the
  syllable count. It reads like the corpus shrinking from 340 122 and it is not; it started
  from `retained` 258 400 and is climbing.

Then `learn`. Two things to expect that were not true before: new rows will be segmented
in-band (so about a fifth fewer syllables per recording, at higher SNR), and the `--limit`
arithmetic in the section below assumed ~33 observations per recording — at −22.5 % that is
closer to 26, so 1 500 recordings is a *smaller* bite of the 59 921 headroom than it was.

## 6. The periodicity gate was built, and it is the fifth candidate measured dead

`analysis/periodicity.py`. The idea was the best one left: every earlier gate asks "is this
*syllable* a bird", and one insect pulse is not distinguishable from one short call, so ask
about the **sequence** instead — an insect stridulates at a fixed rate for a whole recording
and its pulses are spectrally identical. Per recording, from stored fields only (no audio, so
it covers all 340 122 rows): the longest run of consecutive inter-onset intervals holding
within 12 % of the run's own median, the share of the recording that run covers, its CV, and
the mean cosine between successive descriptors inside it.

**It ranks real birds at the top.** All fifteen most metronomic recordings in the corpus are
genuine:

```
XC273582    scytalopus_vicinior      run 192/391  share 0.49  cv 0.047  sim 0.989
XC354217    scytalopus_vicinior      run 120/213  share 0.56  cv 0.028  sim 0.986
INAT167833  scytalopus_speluncae     run  75/ 75  share 1.00  cv 0.011  sim 0.993
XC1152455   gallinago_gallinago      run  60/ 83  share 0.72  cv 0.019  sim 0.995
XC1005194   jynx_torquilla           run  51/144  share 0.35  cv 0.058  sim 0.995
```

Tapaculos, a snipe, a wryneck, antpittas — and of the 45 recordings a `run >= 12, share >=
0.5` cut selects, **40 belong to a species that is in the inventory.**

**And it does not flag the recording it was designed for.** INAT227259 ranks 959th of 7 103
(run 5 of 95). On the band-limited spans it will actually get, its run rises to 22 of 105 —
so the pulse train is real and detectable — but `INAT167833`, a *modelled* *Scytalopus
speluncae*, is **75 of 75 at CV 0.011**: more metronomic than the insect on every axis. Its
spectrogram was checked by eye — 75 identical notes at 5/s across the whole file. Any
threshold catching the insect deletes the tapaculo.

Pairing periodicity with loudness looked like the way out (the metronomic birds sit at
23–30 dB in-band, INAT227259 at 9). Over the corpus it is not: the cut selects 43 recordings
that are again mostly real birds which are simply quiet and repetitive — *Chamaeza*
antthrushes, a *Glaucidium* pygmy-owl, a sedge warbler, a tawny frogmouth — and INAT227259 is
not among them. It is a "quiet repetitive bird" detector that happened to contain one insect.

**The generalisable lesson, and the reason the file stays in the tree:** loudness, tonality,
harmonicity, model presence and rhythm each name a property that some real bird has in the
extreme. **n = 1 labelled noise recording cannot separate anything.** The next attempt should
start by getting more labels — a dozen recordings the owner has listened to and called noise
— and not by proposing a sixth feature. Everything needed to make that cheap is now in place:
`out/audio-cache` holds 5 366 recordings, `out/periodicity.jsonl` and
`out/perch-presence.jsonl` rank them, and `quality remeasure` proves audio-derived
measurements can be written back exactly.

## 6b. Docs, whitepaper and figures

Done, and none of it waits on the sweep:

- **`docs/23-what-we-have-not-tried.md` §23.9 — W8, a new workstream.** The five gates, the
  root cause, and a **pre-registered gate for the next attempt**: at least 12 owner-labelled
  noise recordings, then ≥ 0.8 recall on them at ≤ 2 % loss of recordings belonging to
  inventory species. §23.8's order list and the "three of the six" count are updated.
- **`docs/whitepaper/arxiv/figures.py` — `fig_noise_gates`, new figure `noise-gates.pdf`.**
  Two panels: the percentile the flagged recording occupies on each of the five statistics
  against the tail a gate would have to reject, and what a threshold at its own value costs.
  Every number re-derived per-recording against the current store rather than reused from
  prose, so `p43` for SNR is the **post-remeasure** figure and not §2's old 41 % sample.
- **`main.tex` — a new subsection** under "The system", §"What the segmenter listens to, and
  five gates that do not work", plus the figure. Validated the way the README requires
  (no TeX toolchain here): braces balanced, environments nested, all `\ref`s resolve, all 19
  figures have PDFs. README's stale "11 tables and 10 figures" corrected to 10 and 19.
- **Only `noise-gates.pdf` is new in `figures/`.** Every other PDF regenerated byte-identically
  — the file pins its own creation date and uses no RNG — which is the check that adding a
  figure perturbed nothing.

**A pre-existing breakage found while doing it, and NOT fixed:** `figures.py` aborts before
`write_manifest()`.

```
pinned types absent from the inventory: [('arundinax_aedon', 'L06')]
```

`_load_examples` raises `SystemExit` when a pinned example type is missing, and
`arundinax_aedon` now types as L01–L11 with **no L06** — `data/learned-inventory.json` has
been that way since 2026-08-02 and is committed, so this predates today. Consequences:
`figures/MANIFEST.md` is stale (it has neither `noise-gates.pdf` nor anything else added since
the type vanished), and `spectral-examples.pdf` / `gestures.pdf` on disk are from an older run.
Deliberately left for after `learn`: that step rewrites the inventory and the type ids with
it, so re-deriving the three pinned examples now would be work thrown away. The criteria to
re-derive them under are written above `EXAMPLES` — top/middle/bottom of the
resynthesis-cosine ordering, cached recording, 0.10–0.45 s, energy above 1 kHz — so it is a
lookup, not a judgement call.

## 6d. The sweep finished, and `--species-file` was silently matching nothing

```
1500 recordings ingested, 4710 already known, 0 failed
38102 syllables segmented, 378224 held for learning      (was 340,122)
293757 descriptors retained, 11687 recordings, 3812 species
6353 MB of member data streamed, 73 minutes
```

Cap held: 378 224 of 400 000, so nothing was evicted. `state.json` now carries
`segmentBand: [400.0, 12000.0]`, and the new rows arrived at **25.4 observations per
recording** against the old ~33 — the −22.5 % the segmentation fix predicted, confirmed on
1 500 recordings this time instead of 120.

`snr` coverage is now **97.1 %**: every row except the 11 007 xeno-canto ones whose audio was
deleted by design.

**But it was not a targeted sweep, and the reason is a bug I have fixed.**

```
species clearing learn.MIN_OBSERVATIONS = 24      2,423 -> 2,648   (+227)
of the 1,160 target species, now clearing          202
their observations, median                          11 -> 13
of 1,287 ingested recordings still holding rows, on a target species     302
```

`sources fetch --species-file` documents its input as *"ids or \"Genus species\""*, and
`analysis/topup_underfloor.py` writes ids. Every one of them went through
`harvest.species_id_for`, which **splits on whitespace and requires two parts** — so
`acanthis_hornemanni` returned `""`, a `discard("")` emptied the wanted set, and
`if wanted_ids and sid not in wanted_ids` then read an empty set as *no filter*. The run was
an unfiltered taxonomic-order pass over all 3 846 Aves species: exactly the "One broad pass"
option this file warned would cover alphabetically-early species. The log said so at the time
and nobody read it — `110498 acceptable Aves recordings for 1160 named species` is the
**unfiltered** total.

Fixed, and the fix is two changes because one of them is the real lesson:

- `harvest.canonical_species_id` accepts either spelling (and cuts a trinomial to its
  binomial), while `species_id_for` **stays strict** — it reads fetcher metadata, where a
  one-word scientific name is bad data rather than shorthand, and widening it would hide real
  errors at the ingest boundary.
- `InatSoundsSource._wanted` now **raises** when a species ask parses to nothing, instead of
  falling through to an 81 GB sweep. A filter that silently becomes a no-op on its own
  documented input format is worse than one that refuses.

`harvest.self_test` covers seven spellings plus the two strictness assertions.

**The consequence, and it is a decision not a task.** 988 species are still under the floor
(median 11, max 23). A correctly-filtered pass over them needs ~988 recordings at ~25
observations each ≈ **24 700 observations against 21 776 of headroom**, so it would cross
`syllableCap` and `_trim` would start evicting — and `_trim` retires the oldest recording of
whichever species holds the most, which is the opposite of what a top-up wants. Raising the
cap, accepting eviction, or stopping at 2 648 species is the owner's call, with those numbers.

## 6c. Still to do, and it is a chain that has to run in order

`analysis/run_production_v9.sh` is **running** (started 19:46). Its executable body is
byte-identical to v8's apart from the two staging paths — checked with `diff` — because that
script is the record of what produced the shipped build and the recipe is not what changed
this round. It seeds the staging inventory with the current one so type ids stay stable, then
learn → docrefit → respfit → build → verify → song funnel.

```
learn      RUNNING, ~2 h at v8's 2 423 species, expect longer at 2 648
docrefit   texture for the 44 authored documented calls
respfit    respiration + two-voice where they win their gate
build      --space embed --clustering label --projection pacmap
verify     then analysis/song_funnel.py against the installed inventory
```

**It installs nothing, by design.** Everything lands in `out/v9/` and the install is a
separate deliberate step once `verify` has passed — so the app's `manifest.json`, and every
prose number that follows from it, does not move until someone decides it should.

Then, and only with v9's numbers in hand:

```
figures.py     fig_corpus needs a sixth row; EXAMPLES needs re-deriving (see 6b)
prose numbers  2 423 species / 340 079 syllables / 13 748 rows / 1 043 genera
song funnel    stage 6 prints the syntax trade; v6's re-learn cost repeat classes 68 %
```

That last one is the gate worth watching rather than the cosine: a finer typing fractures the
runs repeat detection depends on, and this corpus change is a typing change.

The app itself needs no figure work: `app/static/figures/` is four **screenshots of the
running app**, and the interface has not changed. What it does need is the number sweep —
`InfoPage.svelte` reads §5 from the loaded `manifest.json` (so that updates itself), but
`2 423` and `340 079` are also written into prose and comments in `+page.svelte`,
`InventoryTable.svelte`, `inventory-rows.ts`, `palette.ts`, `shaders.ts`, `Galaxy.svelte`
and `types.ts`.

## 6e. v9 is INSTALLED, and the whitepaper was rewritten

The chain finished at 23:18, 3 h 31 m. Every gate passed and the song funnel, which is the
one that matters for a typing change, **widened** where the v6 re-learn had cost it 68 %:

```
                    installed(v8)  candidate(v9)   change
species                     2423           2650      +9 %
types                      13748          16283     +18 %
species with a song           68             80     +18 %
repeat classes                82             91     +11 %
motifs                        82             96     +17 %
grammar chunks              1272           2389     +88 %
  -> the syntax layer held: nothing watched fell more than 20 %
```

`learn` took 10 683 s for 2 648 species / 16 239 types. `verify` on the installed assets:
387 287 points, 16 380 clusters, PaCMAP purity 95.3 %, all checks passed.

**Installed** (owner's call, on those numbers): `out/v9/assets` -> `app/static/birdy/`,
`learned-v9.json` -> `data/learned-inventory.json`, re-verified in place. The install is
**committed** as `569ddef`, whose `manifest.json` is byte-identical to the built one
(sha256 `c83c2ee5...`), so `git status` is clean for those paths and git is no longer the
rollback point. **`HEAD~1` is**: it carries 348 461 points / 13 848 clusters / 2 423
species, so `git checkout HEAD~1 -- app/static/birdy data/learned-inventory.json` puts v8
back. One reason install was the right way and not merely the nicer
one: `learn` writes `typing.json` **into the store**, so after the chain the store described
v9 while the installed inventory was v8, and only 91.4 % of v8's types still had typed
members. Leaving it would have kept an inventory and a typing that disagree.

App prose numbers swept across 17 files (2 423 -> 2 650, 13 748 -> 16 283, 1 043 -> 1 089
genera, 340 079 -> 378 224, 348 461 -> 387 287, 13 848/14 003 -> 16 380). `npm run check`
reports the same 4 pre-existing errors as a clean tree, all in `syrinx-processor.js`.

### The whitepaper, on the owner's three complaints

Owner: *"i still see alot of dashes and false positiv formulations i tells us all the time
what it cant in the same sentences in what i can. this is very bad ... and one big part is
missing, what did we genuinaly find in the data."*

1. **Dashes: 192 -> 0 in prose.** 123 lines fixed by pattern, then **17 by hand**, because a
   line-by-line pass broke every appositive pair that spanned a line break: the first dash
   became a period and left a fragment (`Two scalar control curves. Air-sac pressure and
   labial tension ---`). Each of those 17 is a judgement, not a substitution.
2. **The bundled claim-and-limit sentence: the dash WAS the joiner.** Splitting the dashes
   fixed most of it mechanically. A scan for a claim and a negation inside one sentence now
   returns 6, and most of those are a result paired with its control, which is the honest
   form. The convention is now stated in the findings preamble: the result first, the ceiling
   in a following sentence, never the same claim.
3. **"What did we genuinely find" was not missing. It was buried and hedged.** The section
   `What the data supports` already existed at line 1645 of 2100, so a reader met every wall
   and every refutation before reaching a single positive result. **It now sits directly after
   `The system` and before the walls**, and opens with six numbered findings stated plainly.

Also: the abstract was rewritten around the same order (what holds, then what runs against
the design), and the stale totals were updated **only where a sentence describes the corpus
now**. Historical measurements keep their own store's numbers, and one disclosure sentence in
the findings preamble says so, instead of twenty hedges. Restating a 340 079-store result
under 378 224 would be a claim nobody made.

`main.tex` validates the way the README requires (no TeX toolchain here): braces balanced,
environments nested, 0 dangling refs, 19 figures with PDFs, 22 800 words.

### `figures.py` runs to completion again

The pre-existing abort is fixed. `EXAMPLES` was re-derived under its own documented rule
against the installed inventory, and the comment now records that **any re-learn invalidates
those three ids** and how to regenerate them:

```
top     diuca_diuca                 L34  cos  0.9711
middle  caryothraustes_poliogaster  L07  cos  0.7245     (corpus median 0.6985)
bottom  zimmerius_bolivianus        L13  cos -0.3282
```

So `write_manifest()` runs and **MANIFEST.md tracks all 19 figures** for the first time since
the pinned type vanished. `fig_corpus` gained a sixth row, `fig_claim_ladder` now carries v9's
region mix, and `fig_song_funnel` is **pinned to the pre-v9 store in its own docstring and
caption** rather than half-updated: its three panels are one study and only mean anything
together.

**Not fixed, and pre-existing:** `fig_corpus`'s clay annotation ("a store-trim bug deleted
twelve species") overruns its panel. Checked against `git show HEAD` and it is byte-identical
there, so the sixth row did not cause it.

## 7. Also not done

- **`harmonic` clips at 1.0 on over a quarter of the corpus** (p75 = 1.000), which makes it
  useless as a discriminator over that quarter. Noticed while testing gates; not chased.
- **`harmonics` and `noise_frac` are on every row and unused as gates.** The reason not to
  reach for them is §1: they are per-syllable, and the spans they would judge are still
  chosen by whatever is loudest in band.
- **The store's existing rows are still segmented full-band.** The iNat half is re-derivable
  from the cache, but new spans mean new patches, descriptors, embeddings and typing — a
  rebuild of five files, not a field edit.
- `out/harvest-gan/syllables.jsonl.bak` has been **deleted** (owner's call, after the numbers
  in §2 were reviewed). The re-measurement is no longer reversible from a copy; it is
  reproducible from the cache, which is the better property anyway.

# Lyrebird — (2026-08-03, ~17:45): noise gets into the corpus, and the gate that should stop it is unmeasured on 59 % of it

**Superseded by the section above.** Its diagnosis ("a tonality or harmonicity test is the thing that would actually separate a bird from a river") is measured wrong, and its claim that the unmeasured rows cannot be re-measured is measured wrong. The measurements it *does* record are still good; the conclusions are not.

Owner, on an ingested recording: *"I'm looking at INAT227259, it's just noise, no bird call — do
we have sufficient filtering that errors like that never come in?"*

**No. Measured, and the specific recording is in the store:**

```
INAT227259                     95 observations retained, every one with snr: None
observations with an snr      140,129
observations with none        199,993     <- 59 % of the corpus
snr distribution (measured)   min -9.7 dB  p1 -1.2  p5 2.4  p10 4.6  median 17.1  max 81.0
```

## Why it gets in

Three gates exist and none of them is an absolute test for "is this a bird".

1. **`slice_descriptors` requires a window to overlap a segmented syllable by ≥ 0.08 s**
   (`MIN_SYLLABLE_OVERLAP_S`). This one is real and it was added for exactly this class of
   problem — its docstring records the measurement: without it *"the corpus contains a cluster
   whose honest description is 'background', which white noise matches at 0.99 — the live match
   meter read 0.987 for noise against a floor of 0.78, so the galaxy lit up on room tone."*
2. **But the segmenter's threshold is relative to the recording's own peak.**
   `_segments` uses `ONSET_REL = 0.14` of `env.max()`, floored at 1e-4. On a file that is nothing
   but hiss, the loudest hiss is 100 % of the peak, so segments are found and the overlap gate
   passes. **The gate tests "is this the loud part of this file", not "is this a bird".**
3. **`snr` is a weight, not a gate.** It is computed as segment RMS against the median frame RMS
   *outside* the segments, then used as `clip(snr / SNR_FULL_WEIGHT_DB, 0, 1)` when fitting.
   Nothing rejects on it — and `learn`'s own comment is *"Unmeasured is neutral, not bad"*, so the
   95 observations from a noise-only file are weighted as though they were fine.

The only real backstops are downstream and coarse: `MIN_OBSERVATIONS = 24` per species, and the
resynthesis cosine gates in the fit.

## What closing it would cost, measured

An **absolute** SNR floor at ingest, applied to the observations that have one:

```
floor  3 dB   drops   8,715 of 140,129   6.2 %
floor  6 dB   drops  19,457 of 140,129  13.9 %
floor 10 dB   drops  37,285 of 140,129  26.6 %
```

Two honest limits on that. It cannot touch the **199 993 rows with no `snr`** without
re-measuring them, and `snr` is itself relative — a noise-only file has no quiet frames outside
its "syllables", so its floor estimate is high and its SNR comes out *flattering*. A tonality or
harmonicity test (`harmonic`, `flatness`, `noise_frac` are all already on every row and all
already unused as gates) is the thing that would actually separate a bird from a river.

**Nothing here has been changed.** This is a measurement and a diagnosis; the fix is a decision
about what to reject and what to re-measure.

# Lyrebird — the targeted iNat sweep works now (2026-08-03, ~17:40)

The top-up plan of the section below needed one patch, and with it a bounded run **succeeded**:

```
sources fetch --source inat-sounds --species-file out/underfloor-species.txt \
              --per-species 1 --limit 3 --store out/harvest-gan

3 recordings ingested, 43 syllables segmented, 340,079 -> 340,122 held
73 seconds wall clock, ~13 MB of member data
```

**The patch: `--species-file`, so one sweep serves many species.** `InatSoundsSource._wanted` took
a single name and `fetch` streams one 81 GB tar sequentially, so asking for one bird cost a whole
sweep to reach its first file — measured at fifteen minutes for `Acanthis hornemanni`, ingesting
nothing. `_wanted` now filters on a *set*, and `--species-file` reads ids or `"Genus species"` one
per line. With 1 160 species matching instead of 1, the first hits arrive in seconds.

`out/underfloor-species.txt` holds the 1 160 ids, emptiest first, regenerated by
`analysis/topup_underfloor.py` (which computes them from the retained data — see the trap below).

**To run the full pass:** the same command with `--limit` set to what the cap allows. At ~33
observations per recording and 59 921 of headroom, **1 500 recordings is the ceiling** and ~1 160
is what the target list wants. Expect it to stream a large part of the 81 GB archive once.

Then `learn`, which is the step that turns observations into fitted types and could take the
inventory from **2 423 toward ~3 583 species**.

# Lyrebird — the corpus is not short of audio, it is short of a little audio for 1 160 birds (2026-08-03)

**The single most useful measurement of the day, and it contradicts what this file said two
sections down.** Parsing `out/harvest-gan/syllables.jsonl` — the retained observations, which is
what `learn` actually reads:

```
retained syllable observations   340,079
species with retained syllables    3,581
  ... not in the inventory         1,160
  ... of those, >= 24 retained         0      <- learn.MIN_OBSERVATIONS
  largest unmodelled                  23      one short of the floor
  median unmodelled                   11
```

**Every unmodelled species sits at or below 23.** `learn` already considered all 1 160 and
skipped every one. That is the mechanism behind the v8 chain reproducing the installed inventory
byte-for-byte: the inventory contains *exactly* the species that cleared 24, so a re-learn on an
unchanged store cannot do anything else. **A re-learn today would produce the same file a third
time. Do not run one.**

What the corpus needs is not a harvest in general. It needs **a median of 13 more observations
for 1 160 specific birds**, each of which is then modellable.

## The trap that produced a wrong answer first, so nobody repeats it

`state.json`'s `seenPerSpecies` counts **windows analysed**. Read as "observations we hold" it
says 545 of the unmodelled species already clear the floor. The true answer from the retained
data is **zero**. The two differ by a factor that is not constant, so `seenPerSpecies` is an
upper bound and nothing else. `analysis/topup_underfloor.py` reads `syllables.jsonl` and its
docstring says why.

## The audio came from iNaturalist, not xeno-canto

`out/harvest-gan/CREDITS.md` is full of `INAT…` ids against `visipedia/inat_sounds`, and
`birdy-pipeline sources list` reports **iNatSounds 2024 (AWS Open Data): 111k Aves recordings,
3 846 species, keyless** — which is the 3 581 in the store. So the top-up belongs to
`sources fetch --source inat-sounds`, not to the xeno-canto harvest: same archive, no API key,
no quota, and `--per-species` makes a balanced take instead of the archive's first species in
taxonomic order.

Owner's call: **iNat first, then add the same species to the xeno-canto registry** so a second
archive can deepen them afterwards.

## The cap is not the blocker, and the arithmetic says so

```
syllableCap             400,000
held                    340,079   -> 59,921 headroom
observations/recording      ~33   (340,079 / 10,184)
1,160 birds x 1 recording ~38,000 -> fits, with room left
```

Past the cap `HarvestStore._trim` **does not refuse — it evicts**, retiring the oldest recording
of whichever species currently holds the most, converging on an even split. Defensible on its
own terms and the opposite of what a top-up wants, so `topup_underfloor.py` stops with 5 000
observations of headroom still unspent and says so.

## Three misconfigurations in the control server, all fixed

Any one of these would have corrupted the corpus if a harvest had been started first. The
`serve --store` help even warns that it "warns when a sibling store in out/ has moved more
recently", which is the pipeline predicting this exact situation.

```
                  was                              now
store   out/harvest        40 species     out/harvest-gan   3,581 species / 340,079 syllables
inventory data/inventory.json  12 documented   learned-inventory.json   2,423
queue   12 + 32 discovered = 44 species    2,423 + 32 = 2,455
```

`serve` defaults `--inventory` to `data/inventory.json` (cli.py, the twelve documented birds),
which is why the Learn page's harvest queue was 44 species. Restarted with the learned inventory
and the production store, `pipeline/.env` sourced so `hasKey` survived.

**Launch them with `setsid`.** Two earlier restarts printed their banner and died: `( cmd & )`
does not survive the shell exiting, and the port was silently free afterwards. The v8 chain used
`setsid` for the same reason.

## Written, run, and the run proved the shape wrong — read this before trying again

`pipeline/analysis/topup_underfloor.py` computes the target list correctly and its dry pass is
worth keeping:

```
syllables 340,079 of cap 400,000 — headroom 59,921
under the floor of 24: 1,160 species not in the inventory
store holds 10,184 recordings, averaging 33 observations each
[1/8] would fetch 1 for Acanthis hornemanni (has 1)   ...
```

**But its per-species loop cannot work, and the reason is in `sources.py`.** `InatSoundsSource`
does two expensive things *per invocation*:

1. `_wanted()` downloads and parses the whole `train.json.tar.gz` index (14 MB gzipped, 111k
   records) — once per call, then filters to the one species asked for.
2. `fetch()` then opens **`train.tar.gz` — 81 GB — as a single sequential stream** (`r|gz`) and
   picks matching members out as they pass, in taxonomic order.

So fetching one species streams the archive until that species' first file appears. Measured: a
single `--species "Acanthis hornemanni" --limit 1` ran **fifteen minutes and ingested nothing**,
with the index downloaded at 17:17 and the archive still streaming at 17:32. Multiply by 1 160
and it is weeks. **The loop was stopped and the store is untouched at 340 079.**

The archive is designed to be swept **once**. `--per-species N` exists exactly for that, and the
code says so: *"a per-species cap turns the same stream into a balanced take: every species
passes its first `per_species` members, and the archive order stops mattering to what is kept."*

So the two real options, both with a cost worth stating:

- **One broad pass, no code change.** `--per-species 1 --limit N`, no `--species`. Streams until
  N are ingested, so it stops early — but members arrive in taxonomic order, so a bounded pass
  covers alphabetically-early species and only about a third of them are under-floor.
- **One targeted pass, small patch.** Teach `_wanted` to filter on a *set* of species instead of
  one, so a single sweep ingests only the 1 160 that need it. Correct coverage, and the cost is
  streaming most of the 81 GB once.

`--limit` is also the cap guard: 1 recording × 33 observations means ~1 800 recordings would
exhaust the 59 921 headroom, so no pass should ask for more than about 1 500.

Then, and only then, `learn` — which is what turns observations into fitted types, and could
take the inventory from **2 423 toward ~3 583 species**.

# Lyrebird — the browser finally looked at it, and it caught a fix that was fixing nothing (2026-08-03)

`playwright` is a devDependency now and `npm run probe:stage` is the instrument. It asserts on
console errors, computed styles and element counts — never screenshots, because pixel diffing was
tried on this app and could not localise anything against the live cloud and font rasterisation.

## 1. What only the browser could answer

**The bird-colour shader compiles and links.** `shader errors: 0`, including after toggling the
mode on. That was the real risk: three.js logs `THREE.WebGLProgram: Shader Error` and then draws
*nothing*, and TypeScript never sees GLSL.

```
grid tile            87.1191 px, offset 43.5596 px  (exactly half)
ruler caption        "1 tick = 20 knot-spacings"    (20 x 4.356 px/knot = 87.12)
grid layers          3 — vignette + 2 lines, one lattice
figure vs container  743 / 743
downloads row        two 29 px bordered buttons
learn order          PIPELINE · KEEP LEARNING · REFINE THE DATASET · REBUILD THE GALAXY · drawer
"Local knot shape"   gone;  "Bird colours" present;  exclusion works both ways
404s                 birdy/known|unknown/manifest.json — detectGalaxyMaps probing, benign
```

## 2. The fix that was fixing nothing

The provenance key was reported as leading with an empty class. The morning's fix sorted
`provLegend` by measured share — and **`provLegend` was rendered nowhere**. The list the app draws
is an inline literal in the markup, so the sort was dead code and the visible order never moved.
Caught only because the probe read the DOM:

```
before   documented 2% · synthesized none · recorded 94% · unlabelled none · unidentified 4%
after    recorded 94% · unidentified 4% · documented 2% · synthesized none · unlabelled none
```

`provLegend` is gone and `provFilterOrder` feeds the markup. **A "fix" verified only by reading
the diff is not verified**, and this is the round's evidence for it.

## 3. What the probe cannot reach — and the owner closed it

**The ring on a knot is verified, by eye.** Owner, on looking at the running app: *"heads knots
good."* That is the check the probe could not make and the last open item from this round's
interface work.

The probe cannot reach it and the reason is worth keeping, because it will apply to the next mark
on the cloud too: a tag exists only for a knot that is **sounding, selected or pinned**, and
headless chromium has no audio device, so nothing ever activates and no tag is created. Choosing a
bird from the picker does create tags — but it races the shard fetch, and it worked on one run and
not the next, so it is not something to assert on.

The one opportunistic sample taken while something happened to be singing agrees with the
owner's verdict: `5px`, fill `rgba(0,0,0,0)`, border alpha **0.780** — which is exactly
`0.38 + 0.645 x 0.62`, so `--ring-on` was resolving against `--act ≈ 0.645`. The ring was tracking
the activation, hollow, and at particle size.

**So the whole of this round's interface work is now looked at**: the grid and its alignment, the
three thread inks, the weighted grammar alpha, the reordered provenance key, the bird-colour
shader, the Learn page's actions, the info page's downloads and figure widths, and the rings.

# Lyrebird — a third colour language, the ring on a knot, and two zeros explained (2026-08-03)

## 1. Bird colours, and it costs no vertex attribute

Owner wanted the points colourable by bird as a toggle. That mode **existed and was removed**, for
two reasons in the source: at 2 423 species on a dense scatter the hues cannot be told apart, and
its per-point hue attribute took the program to fifteen vertex attributes, which **failed to link
on Mesa's Intel driver in Firefox**.

The second reason no longer applies, and that is why this could come back: the knot's species hue
already rides `uClusterState`'s **A channel**, because the accent reads it to light a singing knot
in its own bird's colour. So `uBird` reads a value the shader already has — 10 attributes, no new
slot. The legibility finding stands unchanged, which is why it is **off by default** and mutually
exclusive with the provenance tint ("colour says one thing at a time" is the legend's own rule).

Verified in a browser: 0 shader errors with it on, and the exclusion clears the other switch both
ways. Written as two `onchange` handlers, not an effect on both flags — an effect that cleared
`birdColours` whenever `provColours` was set makes the bird mode **unreachable**, because turning
it on immediately satisfies the condition that turns it off.

## 2. The ring on a knot: hollow, zoom-scaled, and centred at last

It was a 7 px filled disc driven by a binary. Now:

- **Hollow.** Owner: *"I thought it's a border colour and infill 0."* A filled mark is a bigger
  claim than the data it annotates. Tried at 1.8em (~21 px) on a literal reading of "three times
  the size" and that was wrong twice over — too large, and filled.
- **Sized from the zoom**, `clamp(5, pxPerKnot, 22)` px, because a knot's drawn extent is about one
  knot spacing (0.0417 against 0.0419) so `pxPerKnot` *is* roughly the knot's diameter on screen.
- **Centred on the knot, and this was a real off-by-half that predates today.** `margin-top: 0.26em`
  (~3 px) was pushing the ring *below* the projected position, so the point sat at its lower edge —
  invisible at 7 px, and outside the ring entirely at particle size. `.tag` is transformed onto the
  knot and `translate(-50%,-50%)` does the rest; the card now carries the offset instead, because
  **the card is what moves to meet the mark, never the other way round**.
- **On `--act`, not `--hot`.** NodeProjector writes both — a binary "card is open" and the eased
  0..1 activation — and the ring was on the binary, so the one mark sitting on the data snapped
  while everything around it ramped. `max(--act, --hot * 0.4)` keeps a pinned knot findable.
- **No CSS transition, deliberately.** `--act` is rewritten per frame and already eased upstream; a
  transition would smooth a smoothed value and add 120 ms of lag, so the ring would trail the
  points it sits among. The match meter beside it sets `width` from `--act` the same way.

Audited the other anchored marks while there: the ruler's `.tick` is edge-anchored (a 1 px line at
`left: at`, so its centre is 0.5 px past the value) while `.num` *is* centred. Sub-pixel, reported,
not changed.

## 3. The two zeros in the two vocabularies

Owner: why so few recorded, why so few synthesized? Both are zeros, in two different filters that
share three words — and the answer is one sentence read from opposite ends.

```
                recorded            our own
sounds (points) 327,164  94 %       0  synthesized
songs                 0             2,426  99.3 %  invented
```

- **`recorded` is 0 in the chorus filter** because it maps to song confidence `unlabelled`, and the
  pipeline writes `unlabelled` onto **syllables and knots, never onto a song**. Real audio enters as
  points, not as arranged sequences — the class names a kind of song no code path produces.
- **`synthesized` is 0 in the provenance key** because of `corpus.py`'s `if not anchor: continue`.
  With `--member-anchor` off a fitted type that has field members renders nothing, since putting our
  own synthesiser on the map would be *"a claim about our synthesiser rather than about a bird"*.
  Only the 44 documented syllables render, and those are classed `documented`.
- Those 2 421 `invented` songs are one `learned_bout` per species from `learn.py`, commented *"the
  sequence is ours even though the syllables are measured."*

**The bird made the sounds; we chose the orders.** The chorus panel now prints each class's *share*,
because a working toggle with 0.7 % of the pool to act on is indistinguishable from a broken one.

**And a real bug behind that:** the class counts were computed over *loaded shards*, and a zero
**disabled** the checkbox. Load one bird whose only song is `invented` and "documented" went
unclickable although sixteen exist. It now disables only on a complete count and shows `…` while
shards arrive.

## 4. Smaller

- **Grid bursts merge when they land together.** Repeat strikes on the same knot were already
  folded; two *different* knots a few pixels apart drew two crosses whose rules lay on top of each
  other. Within 8 % of the rule's half-length the live cross is refreshed instead — measured
  against `reachNow()` rather than in cloud units, because "near" here is a judgement about the
  picture and the rule's length already tracks the zoom.
- **Clicking a label selects the song and the bird.** `pickKnot` already took the bird; the song is
  a second dispatch rather than a widened transition, because `chooseSong` owns everything that
  must follow a song change (pin released, epoch bumped, running solo re-pooled) and duplicating
  any of it would be the second copy this machine exists to avoid. Clicking a pinned knot still
  releases rather than re-selecting.
- **"Local knot shape" is gone.** Always on: the comparison it existed for is settled (torn knots
  379 → 245, severe 77 → 37, median extent unchanged). It was also the one Display switch that
  rebuilt the cloud, so flipping it read as the points turning off and on.

# Lyrebird — the fade was measured in frames, not seconds (2026-08-03)

Owner asked whether the activation fades were right. They were not, and the defect never threw.

`ActivationTracker`'s attack and release were EMA coefficients applied once per
`requestAnimationFrame`, so the glow's duration was a function of the monitor. `RELEASE = 0.97`
has a half-life of 22.8 **frames**:

```
        per frame (was)    per second (now)
 24 fps     0.958 s            0.417 s
 60 fps     0.383 s  <- tuned  0.383 s
144 fps     0.160 s            0.382 s
240 fps     0.096 s            0.383 s
```

A **10x spread**, and the comment claiming "~0.4 s" was right about exactly one refresh rate. It
also disagreed with its neighbours, which is what makes it correctness and not taste: the
scheduled pulse in `listener.ts` is two gaussians in *seconds* off the audio clock, and
NodeProjector's ease is already `1 - 0.8 ** (delta * 60)` with a comment saying "as fast at
120 Hz as at 60 Hz". **`features.ts` was the outlier, not the convention.**

Fixed by raising each coefficient to `dt * 60`, which reproduces the tuned 60 Hz behaviour
exactly — the numbers that were chosen do not move — and makes every other rate match it.

**`verify:fade`, 12 checks over 10 frame rates.** Reverting to per-frame fails 4, including
"144 fps is not faster than 60". Self-contained on a synthetic two-knot corpus, so it does not
depend on which build is installed.

**And it caught a mistake inside the fix.** The first version clamped `dt` at 0.25 s "to keep the
exponent sane", which left a knot **63 % lit after thirty seconds in a background tab**. Nothing
needed the clamp: `0.97 ** 1800` underflows to zero, which is the right answer for "nothing has
sounded for half a minute". Only the lower bound and a NaN guard remain.

# Lyrebird — one scale on the stage, and Learn's three main actions (2026-08-03)

## 1. The stage had two scales and only one of them meant anything

Owner: *"i want the grid background to align with the ruler and also be reactive to the zoom…
make the grid get a bit smaller when we zoom in like the ruler, it aligns with it."*

**First, a correction worth carrying forward: there is no 3-D grid.** `.stage`'s comment says
*"the measured field the cloud is read against is now the 3D cage inside the scene, which turns
with it"* — **that cage does not exist.** Nothing in the scene draws it; the comment outlived
whatever component did. The only persistent lattice is the flat CSS background on `.stage`, and
`GridBurst` is the transient per-note crosses, which is a different thing (and still the
suspect for the "diagonal red and blue streaks" report).

What was wrong: `background-size: 120px 120px`. **Fixed pixels, agreeing with nothing**, while
the ruler's divisions re-scale with the zoom. So the picture carried two scales at once, and the
squares were not a unit of anything — at one zoom a square was three knot spacings, at another a
fifth of one. **A reader reads a grid as a measure whether or not it is one**, so the lattice was
quietly answering "how big is that gap" with a number that had no referent.

Now a coarse square is **one labelled tick** and a fine square a fifth of it, both from
`galaxy/ticks.ts`, which the ruler now reads too. A grid line and a tick at the same place is one
claim made twice, and it re-scales with the zoom because the step does.

Two details that are the whole difficulty:

- **The half-tile offset.** The ruler counts outward from the centre of the view, because the
  projection has no meaningful origin, so its zero sits at `extent / 2`. A CSS background at
  `background-position: 50%` puts its tile origin at `(extent − tile) / 2` — **half a tile short**
  — so every line would land exactly *between* two ticks. That reads as alignment failing rather
  than as a different grid. Adding half a tile back is the correction, and `verify:ticks` proves
  the naive version would miss.
- **`--grid-fine` was a declared, unused token.** It has a job now: the fifth divisions, under the
  coarse lines at 0.035 of ink against 0.03. Five and not ten, because every step is 1, 2 or 5
  times a power of ten and five divides all three into something countable.

### `verify:ticks`: 18 checks, and the failing one taught me about the ruler

The claim — every grid line falls on a ruler tick — fails by *half a tile*, which on screen reads
as "the alignment is a bit off" and never as anything broken. So it is computed at 167 zooms
across six viewport widths (13 324 ticks) rather than looked at once.

**One check failed on the first run and the check was wrong, not the code.** I asserted the drawn
spacing brackets `TARGET_PX = 78`. It does not: the 1-2-5 choice rounds the step *up*, so **78 px
is a floor**, and the spacing runs 78 to 190 px — up to 2.4x the "target" just before each step
change. That is now written down where the constant is defined, because it is what bounds the
grid: a coarse square is 78–190 px and a fine one 16–38 px, which is exactly why five divisions
stay countable instead of becoming texture.

Proven by mutation:

```
drop the half-tile offset          2 checks fail, incl. "a line falls on the ruler zero"
put the grid back on fixed 120 px  1 check fails ("every step is 1, 2 or 5 x a power of ten")
ten fine divisions instead of five 1 check fails
```

## 2. Learn's main actions are main actions now

Owner: *"start learning is one… harvesting is in the drawer, that's correct, but build should be
outside of it, it's a main action. Same goes for refining the dataset — button is missing."*

Both right, and the second was the more useful observation.

**Rebuild is out of the drawer.** It was inside "run one step by hand", which was wrong twice
over: it is not a step of the loop — the loop rebuilds on its own when drift says the frame has
stopped describing its contents — and it is the action that decides what the galaxy on screen
*is*. Harvest and Learn genuinely are hand versions of loop steps, so they stay in. It keeps its
stated cost, because being a main action does not make it cheap.

**"Refine the dataset" is a new main action and it is not a new capability.** The
least-collected-first ordering has always been in `harvest.py` — a bird with nothing served before
a bird with two thousand — but the only way to ask for it was the drawer's Harvest form, behind a
species picker defaulted to "every species" and four sliders. **So the single most useful thing
you can do to the corpus looked like a configuration exercise.** The button is the same call with
no species chosen, and it says what it will do: how many known birds hold nothing, and that they
go first. The count moved here from the drawer's note, which now explains only what the form adds
— choosing one bird, and how deeply.

The page reads: **Start learning · Refine the dataset · Rebuild the galaxy**, then a rule, then
the drawer with Harvest and Learn. The divider's meaning changed with it and its comment says so.

## 3. Tests

`npm run check` clean apart from the four pre-existing `syrinx-processor.js` errors, zero
warnings. `build`, `verify:ticks`, `verify:zip`, `verify:context-threads`, `verify:performance`,
`verify:layout`, `verify:inventory-table`, `verify:biplot`, `verify:trajectory` and
`verify:split-knots` all pass.

**SETTLED — all of it has since been looked at**, by the browser probe and by the owner; see "the
browser finally looked at it" above. Left as written because the reasoning stands: `verify:ticks`
can prove the grid's arithmetic but not that the CSS layers compose the way the rule says, and it
took the probe to find that the provenance sort in this very round was fixing an array nothing
rendered.

# Lyrebird — the build can be taken away, and two things on the info page were badly wrong (2026-08-03)

Owner, on the info page: *"i want the json to be there to download as a link, you click and load
all in a zip"*, *"the download whitepaper button is nearly not visible thats bad"*, *"the images on
the right corner are not going to the width of the container"*. All three real, and the second and
third were one-line causes.

## 1. The whole build leaves as one zip, and it is the end of §1's argument

Every figure on the info page is read from the loaded manifest, which is the property that makes
that page trustworthy. This is the other half of it: **the reader can take the build away and
check any of them.** Not an export format and not a summary — the same bytes the browser loaded.

**The file list is `manifest.files`, which is the pipeline's own record of what it wrote.** A list
kept in the app instead would drift the first time the pipeline wrote a twelfth file, and the
download would then quietly be a subset of the build while still calling itself the build. Found
while wiring it: the `Manifest` type declared `files?: Record<string, string>` and the pipeline
writes an **array** of eleven paths. Nothing had ever read the field, so nothing had disagreed
with it.

`relations.json` is deliberately absent because it is absent from `manifest.files` — a sidecar the
app reads three pairs of at a time, not part of the build's contract. One production build wrote
760 MB of it.

Measured on the installed build: **76.7 MB of assets to a 22.9 MB archive, 30 %, in 1.0 s.**

`data/zip.ts` is hand-rolled and that is a deliberate trade: a zip with no encryption, no zip64
and known sizes is about sixty lines of header writing, `CompressionStream` has done the only hard
part since Safari 16.4, and a library would be more bytes shipped to every visitor than the format
costs to write. Sizes are known before anything is written because each entry is compressed in
full first, which is what lets it emit ordinary local headers instead of the streaming variant
with data descriptors — a plain zip is the one every tool opens. Guards throw rather than write a
broken file past 4 GB or 65 535 entries.

Two details that are decisions rather than defaults. The archive is stamped with the **build's**
`builtAt` and not the download time, so two downloads of one build are byte-identical and cannot
be mistaken for two builds. And every fetch carries `builtAt` as its cache-buster, the same rule
the loader follows and for the same reason: an archive must not be assembled from two builds.

### `verify:zip`: 15 checks, and `unzip` is the judge

A zip is the archetype of the failure this project keeps naming: **an off-by-one in a
central-directory offset produces a file of the right size, with every payload byte present, that
no tool will open.** Nothing throws. So a self-consistency test is close to worthless — the same
wrong arithmetic would be used to read it back.

`verify-zip.mjs` writes real archives and hands them to the system `unzip`, which knows the format
and did not learn it from us: `-t` for integrity, `-p` for byte-exact round-trip, `-l` for the
listing. CRC-32 is checked against the format's documented values (`"a"` → `0xe8b7be43`,
`"123456789"` → `0xcbf43926`). Covered: a nested path, a zero-length member, incompressible
binary, and a pre-1980 stamp.

Then it mutates and requires rejection, because a test that only ever sees valid input cannot tell
you it would notice invalid input:

```
central-directory offset off by one   unzip exits non-zero
wrong CRC in a local header           unzip exits non-zero
truncated payload                     unzip exits non-zero
```

The real 11-file build was also packed and checked end to end — `unzip -t` clean, and
`points.json`, `inventory.json`, `inventory/index.json` and `positions.f32` byte-exact out the
other side.

**No size is printed on the button.** It is not known until the archive is packed, and a number
there would be a figure this page invented, which is the one thing this page may not do. The file
count comes from the manifest; the prose says "roughly a third", which is a ratio rather than a
fabricated absolute.

## 2. The two download affordances were the least visible thing on the page

The whitepaper was a `.paperlink` inside a `.note` — 0.74 rem, `--ink-dim`, **the same weight as
the paragraph above it**. So the one thing on the info page a reader might want to *take away* was
harder to see than the body copy. A thing you can leave with is a control, and both are controls
now, in `controls.css`'s existing button vocabulary rather than a new one.

The look is repeated rather than shared, because `button {}` is an element rule and an
`<a download>` cannot inherit it. Repeating the vocabulary keeps a download reading as the same
kind of object as every other control; inventing a look would have said it was a different kind of
thing.

## 3. `.figure` was wearing the prose measure

One line: `max-width: 44rem`, which is `.measure` — the cap that keeps a *line of prose* short
enough to read. **An image has no line length to protect**, so on the wide figure column every
screenshot stopped short of the container and read as misaligned against the text beside it.
Removed from the image; the caption is prose and keeps it.

## 4. One property amended honestly

`InfoPage`'s docstring said it holds no state, and the download keeps a progress line while it
packs — because compressing 77 MB behind a silent button reads as a broken button. That is
transient state about the component's own control and nothing else; the fetching and packing live
in `data/asset-download.ts`. The property that matters is intact and is restated in the docstring:
every *figure* on the page is still a prop, so the page cannot invent one.

`mapDir` is now a prop, so a `--clustering both` root packs the galaxy on screen rather than the
root's. Passed in rather than guessed.

## 5. Tests

`npm run check` clean apart from the four pre-existing `syrinx-processor.js` errors, zero warnings.
`build`, `verify:zip`, `verify:context-threads`, `verify:performance`, `verify:layout`,
`verify:inventory-table`, `verify:biplot`, `verify:trajectory` and `verify:split-knots` all pass.

**SETTLED — since looked at**, by `npm run probe:stage` and by the owner. The downloads row
measured two 29 px bordered buttons and the figure exactly filled its container at 743 / 743.
The principle stands and earned its keep the same day: a rendering change is not verified until
somebody has seen it, and the probe found that this round's provenance-order "fix" was sorting an
array the markup never rendered.

# Lyrebird — the grammar gets its weight back, and the synthetic space gets an answer (2026-08-03)

The v8 chain ran underneath all of this and **landed at 15:12 having reproduced the installed
build byte-for-byte** — see the section headed "the v8 chain LANDED" below. Nothing in this round
touches the pipeline or the installed assets.

(A note on extrapolating from a partial file, since it was done here and it was wrong: at 14:39
`learned-v8.json.partial` was 16.5 MB against the 21.1 MB stage 0 had seeded, which read as four
fifths through and put the finish near 16:00. Learn ended four minutes later, at 14:43. The
partial is not written at a rate proportional to species remaining, so its size is not a clock.)

## 1. The one experiment the last round said to run first, and it has a sharper answer than expected

`pipeline/analysis/interp_heldout.py`. Hold out a real fitted type, interpolate between that
species' remaining types in the shipped 32-d critic embedding, and ask whether the interpolant
lands nearer the held-out type than chance. Pre-registered in the docstring, four arms on one
query population, over the **installed** assets — so it measures the build the app is drawing.

12 736 held-out trials over the 1 937 species with at least three fitted types. The candidate
pool is the held-out knot plus every knot of every other species — the species' *remaining*
types are excluded from the pool, because a midpoint of two vectors is trivially nearest to
those two vectors and scoring against them would measure the construction rather than the space.

```
arm                            rank pct    top-1   top-10
interpolant (midpoints)          0.9771   0.5525   0.6975
sibling (the types)              0.9776   0.5403   0.6996
centroid (the mean)              0.9586   0.3894   0.5438
shuffled (another species)       0.5049   0.0002   0.0005
chance                           0.5      0.00007  0.0007
```

**The geometry is emphatically real.** The shuffle sits at chance on all three statistics, and a
species' own types find the held-out one at top-1 **0.55 against a chance of 0.00007** — about
7 700x. So the 32-d space is not a plausible-looking smear, and that half of the question is
settled.

**Interpolation itself is another matter, and the average hides the answer.** A midpoint beats
the sibling types by +0.0122 on top-1 and *loses* by 0.0004 on rank percentile — a gate passing
on one statistic while the other moves the other way, which is a thin pass and is reported as
one. Broken out by how many anchors the query is built from, the margin is monotone and
**crosses zero at about six**:

```
anchors  trials   A top-1   B top-1     A - B
      2    1131    0.3033    0.3307   -0.0274
      3    1164    0.4149    0.4459   -0.0309
    4-5    2344    0.5307    0.5320   -0.0013
    6-8    4963    0.6053    0.5932   +0.0121
     9+    3134    0.6264    0.5734   +0.0530
```

So the honest finding is not "interpolation works" or "it does not". **Below about six anchors a
midpoint is worse than simply using the bird's real types** — with two anchors there is one guess
and it is the mean, and the mean is the weakest arm in the table. Above six the guesses start to
sketch a hull and it pays, reaching +0.053 at nine or more. 8 097 of the 12 736 trials, about two
thirds, are in the paying region.

**What that licenses, and what it does not.** Filling gaps by interpolation is warranted for
well-sampled birds and is not warranted for thin ones, and the anchor count is known before any
fill is attempted — so the gate is cheap and it is per species, not global. It does **not**
license the synthetic space in general: this measures whether the geometry can find a type it
already holds, which is a weaker claim than whether `inverse.py` renders something a bird would
sing. That still needs `specbench`, which is still unrun.

## 2. Three claims, three inks, and the grammar's probability reaches the draw

The previous round's §4 asked what the faint lines between the knots are and answered: three
different claims drawn in one identical grey, with the grammar's measured probability **thrown
away at draw time**. Both halves are fixed.

`ContextPath` (`shaders.ts`) replaces `number[][]` on the signal — `nodes`, `kind`, `weight` —
so `setContext` carries what each thread claims and how strongly. A song's weight is 1 and that
is not a probability standing in for one: an authored sequence is in the corpus or it is not, so
there is no measured uncertainty to draw and only the grammar varies.

```
song     slate, even weight            the established backdrop ink, unchanged
grammar  PROV_LEARNED amber, weighted  alpha 0.12 at the floor to 0.5 at p = 1
relation partner's hue at the far end  already distinct, untouched
```

Two things worth keeping in view. The amber is **not a new colour**: the app already says amber
for a fitted thing wherever provenance is the language, so a grammar thread borrowing it makes
the stage agree with the legend instead of inventing a fourth vocabulary. And songs deliberately
**keep the slate** rather than taking `PROV_DOCUMENTED` blue — colouring every thread was tried
on the tags and the verdict was "too dominant", which was right. One ink added is what the
reading needs.

The band is 0.12–0.5 rather than the bare probability because `GRAMMAR_FLOOR` is 0.08: alpha = p
would draw most surviving transitions under 0.2 and the weighting would read as *the grammar
faded out*. Weight is carried as **per-vertex alpha**, not line width — `linewidth` is ignored by
every WebGL renderer, so width is not a channel this project has. Checked against the installed
three 0.185 rather than assumed: `vertexAlphas` is exactly `vertexColors && color.itemSize === 4`,
which is what sets `USE_COLOR_ALPHA`.

**The legend now says which is which**, in three rows whose swatches are the inks they name —
because an ink nobody can look up is still mute, which was the actual complaint.

### `verify:context-threads`: 33 checks, and all four mutations are named

`context-threads.ts` holds the pass split and the weight mapping, out of the component for the
reason `inventory-rows.ts` is out of the page: **a wrong alpha shows up as a thread that looks
slightly faint, never as an error** — the most expensive kind of wrong, because it is legible.

Proven by mutation:

```
throw the probability away again (alpha = 0.28)   10 checks fail
draw both kinds in one pass                      10 checks fail
alpha = p, no readable band                       7 checks fail
drop the clamp                                    2 checks fail
```

The second mutation originally *crashed* the script instead of failing it, which is a detection
that tells whoever runs it nothing. The checks read through `?.` and NaN now, so an empty pass
reports which claim stopped being made.

## 3. Asked: we have `synthesized` as a provenance class and we never synthesize anything

Owner, and **right, measured**: the class holds **0 of 348 461 points and 0 of 13 848 knots**. So
does `unlabelled arrival`. Two of the five classes are empty in the shipped build.

Synthesis does happen — 8 382 points are renders — but every one of them is of an *authored*
sound, so every one is classed `documented`:

```
synthetic        1 056   44 documented syllables x 24 variants   -> documented
synthetic-song   7 326   2 442 authored songs x 3 variants       -> documented
field          340 079   real recordings                         -> field / candidate
```

1 056 = 44 x 24 exactly, and 44 is 13 748 - 13 704: the documented syllables. The amber class
needs a point that is **both** a fitted `L*` type **and** our render, and those never co-occur,
because of one line in `corpus.py`:

```python
if not anchor:
    continue
```

`--member-anchor` is off by default (`memberAnchor: false`), and the comment above it gives the
reason: rendering a fitted type would put *"the rendered voice's own place on the map — a claim
about our synthesiser rather than about a bird"*. A fitted type that has field members therefore
renders nothing. Only a type with no members renders, "because renders are all the evidence it
has" — and those are exactly the 44 authored calls.

**So the class is empty by design, and the bug is elsewhere: the key introduced it first.** The
Display list was a hardcoded order under a comment claiming "strongest-carrying class first so
the eye starts where the mass is", and it led with the class holding none of the corpus while
`field`, which holds 94 %, came second. **Fixed by sorting on the measured share**, so the order
is true of whatever is loaded rather than of one build. The class stays in the vocabulary: a
build *can* emit it, and a key that cannot name what the pipeline can produce is worse than one
with an empty row.

## 4. The Learn page: two things said out loud, one thing separated

- **Harvest already serves the emptiest bird first**, and had since `harvest.py` grew the
  ordering — *"a bird with nothing is always served before a bird with two thousand, and once the
  new ones have caught up the order flattens back out on its own"*. It was logged on the server
  where nobody on this page could see it, so pressing Harvest looked like it might spend the run
  deepening the twelve birds already deepest. **The policy was never missing, only invisible**:
  the panel now states it and counts how many known birds hold nothing yet.
- **Rebuild is separated from Harvest and Learn**, because it is the one action on the page that
  is not incremental: the other two accrete and move nothing already drawn, while Rebuild
  re-clusters and re-projects the whole corpus so every point takes a new position. Four
  undifferentiated sections made the cheapest control and the most expensive one read alike. A
  rule and a stated cost, not a warning tint — a rebuild is the normal end of a learning run.

**Not done, and it is the sharper finding of the three:** the Keep-learning loop's third step is
`grow`, `grow` needs `projection-basis.json`, and **a PaCMAP build does not write one** — the
installed v7 has no such file. So on the installed galaxy the loop can harvest and fit but the
galaxy cannot accrete. The loop's UI does not know this. Owner has seen it and did not pick it.

## 5. The function-transfer measurement: a clean null, and it closes a question

`pipeline/analysis/function_transfer.py`, pre-registered, against the installed assets. The
second refusal — *"it does not say what a fitted type is for"* — was argued in §9 of an earlier
round from the size of the anchor set. It is now **measured** rather than argued.

Leave-one-species-out nearest-neighbour transfer of `functionClass` in the shipped 32-d
embedding. The whole anchor set is 53 documented functions over 12 species, six classes,
badly unbalanced (`structural` 24, `alarm` 11, `territorial` 10, `contact` 4, `recruitment` 2,
`courtship` 2).

```
arm                                accuracy   hits
LOSO k=1                             0.4151   22/53
LOSO k=3                             0.3774   20/53
majority class (`structural`)        0.4528   24/53   <- the number to beat
within-species k=1 (the ceiling)     0.4717   25/53
permutation null, 2 000 shuffles     0.2784 mean, 0.3962 at the 95th
```

**Cross-species function transfer does not beat a constant answer.** 0.4151 against 0.4528 —
always saying "structural" is better than asking the geometry. It does beat its own shuffle
(p = 0.0375), so the embedding carries *some* function signal; there is just not enough of it to
beat a majority vote. And the ceiling says why that is not a projection problem: even
*within*-species transfer reaches only 0.4717, barely over the constant.

**The decisive arm is G4.** 15 of the 53 labels are `inferred` and 10 `experimental`; only 28 are
`documented`. On those 28 the accuracy is **0.3571 against a majority baseline of 0.5714** — far
worse than a constant. So whatever the full set was picking up, it was the inference and not the
documentation.

So **the refusal stands, and now with a number behind it.** The honest fix is more documented
function, not a better model: 53 anchors over 12 species is not an anchor set to propagate from.
Standing limit stated in the output: at n = 53 one species' repertoire moves every figure, so the
gates are the finding and the third decimal is not.

## 6. The literature, August 2026

- **Function and behavioural context is the field's own stated frontier**, not something already
  solved elsewhere — the comparative review of bioacoustic foundation models puts it as the next
  step, with explainability work only beginning to say which spectral cues models use. So §5's
  null is where the field is, not behind it.
- **What does transfer across species is valence, not function.** XGBoost separates positive from
  negative contact calls across seven ungulate species at ~89 %, and species-independent emotional
  analysis reports the same with the caveat we measured: *"notable variability at the species level
  in how emotional states are conveyed"*. The transferable axis is low-dimensional arousal, not a
  six-class function taxonomy. **If this project ever wants a cross-species claim, that is the
  shape of one that could hold** — and it is a different claim from the one the refusal declines.
- **Generative bird audio is established, and the field uses it as augmentation rather than as a
  finding.** BirdDiff conditions a diffusion generator on MFCCs, species label and text over 12
  wild species; DDPM spectrogram augmentation improves classification; a 2026 hybrid strategy does
  the same for killer-whale detection. That is exactly the epistemic category `perch.py`'s
  quarantine already implies — **a generated sound is training data, never evidence that a type
  exists.** Worth keeping if a fill-the-gaps button is ever built on §1's result.
- Perch 2.0 still tops BirdSet in the 2026 review, which leaves the earlier round's "test whether
  Perch or our critic is better, per recording" exactly where it was.

## 7. Tests

`npm run check` clean apart from the four pre-existing `syrinx-processor.js` errors, zero
warnings. `build`, `verify:layout`, `verify:split-knots`, `verify:trajectory`,
`verify:inventory-table`, `verify:biplot`, `verify:performance` and `verify:context-threads` all
pass. **Since looked at in a browser** — see "the browser finally looked at it" above: the
bird-colour shader links, the grid aligns with the ruler to the half-pixel, and the rings are
owner-approved. One of this round's changes turned out to be fixing nothing, which is why the
rule is worth keeping.

# Lyrebird — the performance is one value now (2026-08-03)

The chain is still in stage 1 (`learn`). This round is the refactor the previous one said should
come before the tab panels, and for the reason it gave: **both of that round's bugs came out of
this machine being four effects and two flags in one scope.**

## What it was

Thirteen pieces of state, eleven functions and seven effects in a 4 200-line scope, with no
statement anywhere of who owned what. The single largest was a 38-line effect that read four of
those variables and decided between four outcomes.

## What it is

`src/lib/state/performance.ts` — 319 lines, no imports, nothing that touches the engine, the
listener, the camera or the DOM. `reduce(state, event)` returns the next state **and the
commands that make it so, as data**. The page has one `dispatch` and one `perform`.

```
events    chooseBird · releaseSelection · pickKnot · chooseSong · selectSung
          pressChorus · setChorus · setSoloMode · stop
commands  panic · stopAmbient · clearPaths · startGlobal · startSolo
          showContext · refreshSelection
```

The six values the rest of the page reads — `chorus`, `speciesId`, `songId`, `selectedSung`,
`pinnedCluster`, `soloMode` — are `$derived` **projections** of `perf`. So about two hundred
readers are unchanged and **nothing but `dispatch` can write them**. That is the property the old
code could not have: any of those places could assign, and several did. Making them `const` is
what produced the fix list — the compiler named all nineteen writers.

Three rules that previously existed only as the shape of an if-chain are now written down:

- **Precedence.** `subjectOf` — knot, then history phrase, then call, then bird, then corpus.
  It lived inside `frameNodes` and three other places re-derived it.
- **Resume.** One flag, set on the way in, read on the way back, cleared by every explicit stop.
- **Epoch.** Two commands are asynchronous. The old code guarded them by re-reading `chorus`
  after the await, which is right until the state has moved *and moved back* — what a fast
  double click does. A command carries the epoch it was emitted at.

## `verify:performance`: 42 checks, and it catches both original bugs

Proven by mutation, not asserted:

```
reintroduce the toggle in setChorus   5 checks fail, incl. "89 of 512
                                     programmatic sequences silence the chorus"
stop consulting the resume flag       3 checks fail, incl. "the aviary comes back"
```

That second number is the whole argument for the refactor. The bug was not one wrong line; it
was a shape in which **one sequence in six silences the app**, and no amount of care at the call
sites would have found that.

Also swept: no event sequence throws or loses a field (1 000 three-event runs), every async
command carries its epoch, and any transition that starts or stops a chorus moves the epoch.

## One regression I introduced, measured and fixed

Routing the re-pool effect (tempo, confidence filter, chosen call) through `setChorus` moved the
epoch — which invalidated the start command the *original* transition had just emitted, because
that one was still awaiting a species shard. The solo chorus voiced **1 sample in 56 where it
had managed 18**. Re-pooling is not a state change, so it re-issues the command directly with
the current epoch. Restored to 13/56.

That is exactly the failure the epoch exists to prevent, caused by misusing the epoch. Worth
keeping in view: a token that discards superseded work is only correct if the thing reissuing
work is not itself a new transition.

## Deleted

`setChorus`, `toggleChorus`'s body, `startSoloChorus`, `noteChorusBeforeSelecting`,
`chorusToResume`, `resumeGlobal`, `lastSpeciesChoice`, `songSpecies`, the 38-line species
effect, and the inline re-implementation of both chorus starts inside the restart effect — which
had **already drifted**: it passed the confidence filter to the aviary and `setChorus` did not.
Two copies of "how a chorus begins", one of them wrong, is what a state machine with no owner
produces.

`+page.svelte` is **4 129 lines**, from 6 286 at the start of the day.

## Tests

`npm run check` clean apart from the four pre-existing `syrinx-processor.js` errors, zero
warnings. `build`, `verify:layout`, `verify:split-knots`, `verify:trajectory`,
`verify:inventory-table`, `verify:biplot`, `verify:performance` and `check-provenance-buffers`
all pass. The browser probe was re-run and every behaviour it measures is intact: the history
strip stays stable under the pointer and selects the bird aimed at, clicking away resumes the
aviary, solo songs and solo improvise both sound, and pressing the running mode stops it.

**Next:** the three tab panels. They were blocked on this and are not blocked now — Sing needs
`dispatch`, the projections and `frameNodes`, which is a prop list rather than a tangle.

# Lyrebird — two selection bugs, two choruses, and the stylesheet comes out of the page (2026-08-03)

The v8 chain is still in stage 1 (`learn`, started 11:41, still going at 13:32). Nothing here
touches the pipeline.

## 1. Two selection bugs, both measured in a browser before and after

Owner: *"the selection is a bit broken when we select with the tags on the bottom — the cam
sometimes doesn't focus, and when we click away it is still selected and nothing plays."* Both
real, and neither was what it looked like.

**"The cam doesn't focus" — it focused correctly, on the wrong bird.** The newest phrase is
*prepended* to the history strip, so every chip shifts one place right each time the chorus
sings, about once every two seconds during a whole-aviary chorus. Reaching for a chip selected
whichever phrase had slid under the cursor by the time the click landed. Proven: hovering a
chip, waiting six seconds and clicking it used to select a different species. The strip now
**freezes its rendered list while a pointer is inside it** and releases on the way out —
`history` keeps filling, only the display is held, so nothing is dropped. After: the chip under
the cursor was unchanged after six seconds and the bird selected was the bird aimed at.

**"Nothing plays" — the chorus was left stuck silent, and the cause was a toggle called
programmatically.** `setChorus` read `chorus = chorus === mode ? 'off' : mode`, which is button
behaviour, and four effects called it with a mode they merely wanted to be *in*. Two resume
paths raced — `chorusToResume` in `clearSelection` and `resumeGlobal` in the `speciesId`
effect — and whichever arrived second asked for the mode already running, which the toggle read
as *stop*.

Measured, phrases scheduled in 14 s:

```
                       before   after
whole-aviary chorus        8       (baseline)
after clicking away        0        3
```

and it stayed at 0 afterwards — every later selection was silent too. Fixes: `setChorus` is a
**setter**, `toggleChorus` is the button and the only caller allowed to stop a chorus by asking
for it again, and there is **one** resume flag instead of two.

## 2. Two choruses for a selected bird, and no Stop

Owner: *"in the bird selected we want 2 modes of chorus, one with the songs one improvised, and
delete the stop button — it stops anyway when we deselect."*

`Songs` is the chorus this app has always had: three voices drawing from the repertoire.
`Improvise` walks the bird's **measured grammar** instead — the transitions counted from its own
field recordings, sampled fresh each phrase, so none of them is a phrase anybody recorded. Two
modes rather than a checkbox because they are two different claims: one plays back a repertoire,
the other generates from a statistic.

The improvised chorus is an `$effect` rather than a hand-started timer, because it has to end on
the chorus stopping, the mode changing, the bird changing, the tempo changing and a galaxy
reload. An effect's teardown covers all five; four scattered `clearInterval` calls is how §1
happened. Floored at 1.5 s between phrases — an improvised bout runs about a second, and asking
faster stacks voices instead of making a chorus.

Stop is gone, and the owner is right that it was redundant: clicking the stage clears the bird
and the `speciesId` effect hands the air back to whatever had it. Measured: improvise voices
17/56 samples, and clicking the same button again gives 0/56.

**Known gap, not a regression:** improvised phrases go through `singPhrase`, which calls
`addLive` but not `recordSung`, so they draw a thread and never appear in the history strip. The
same has always been true of `Sing it` and `Improvise`.

## 3. The stylesheet comes out of the page

Owner: *"we have to refactor, get rid of the monoliths, make global css variables with reset and
typo and layout and make modules."*

`app.css` was one 183-line block holding four different kinds of thing. It is an index now:

```
src/styles/tokens.css       57   every colour, both typefaces, the one radius. No selectors.
src/styles/reset.css        35   the ground: paper, type, quiet scrollbars.
src/styles/typography.css   15   .mono and code.
src/styles/controls.css    102   buttons, selects, inputs, ranges, checkboxes, .primary, .on.
src/styles/layout.css      699   the vocabulary the whole app shares.
src/app.css                 22   five @imports and the reasoning.
```

**`layout.css` is the one that mattered, and it fixed a real bug rather than tidying.** 91 rules
moved out of `+page.svelte` (5 637 lines now, from 6 286). Svelte scopes a component's CSS to
that component, so `.note`, `.block`, `.field`, `.segmented` and the rest — defined in the page —
reached nothing inside a component extracted *from* the page. The first extraction hit it
immediately: `InventoryTable.svelte` had to redefine a paragraph style that already existed a
thousand lines away in the file it came out of. **A vocabulary only one file can speak is what
made the page a monolith** — every new surface had to be built inside it to look like the rest of
the app.

What stayed scoped: everything about the *stage* — the bench grid, the hud, the floating panels,
the history strip, the legend, the ruler captions. Those are one screen's arrangement, not a
vocabulary, and globalising them would move the monolith into the stylesheet.

**One regression, found and fixed: `:global(...)` is Svelte-only syntax.** Two moved rules used
it (`.pagesection :global(p)`, `.pagecol > :global(section.block)`) and it is not a selector in a
plain stylesheet, so the info page lost every paragraph gap. Unwrapped.

**How it was verified, because screenshot diffing could not do it.** Diffing before/after showed
5–21 % of pixels differing on every surface — all of it the live cloud, the churning inventory
table and font rasterisation, none of it localisable. So the check is a **computed-style probe**
instead: open each surface, read the one property each moved rule uniquely sets, assert it is
still set. 24 properties across the stage, the sing panel, the learn page and the info page, all
correct — `.pagesection p` back to 11.7 px (0.9 rem), `.measure` 44 rem, `.deflist`/`.claims`/
`.pagebody` all two columns, `.segmented button` radius 3 px, `.blocktitle` uppercase. That probe
is worth keeping the next time CSS moves.

## 4. Asked: what are the faint lines between the knots?

Owner: *"what are the connections besides the knots connected? what do they say? I don't get it,
they never animate or do shit."* Answered here rather than changed, because the answer is that
**three different claims are drawn in one identical grey**.

`showContext` builds `listener.setContext([...songPathsOf(id), ...grammarPathsOf(id)])` — so the
web around a selected bird is:

1. its **documented songs**, as sequences a person authored or recorded;
2. its **measured grammar**, the transitions counted from its own field audio above
   `GRAMMAR_FLOOR = 0.08`;

and beside them `RelationThreads` draws a third thing entirely — hairlines out to **other
species that share call shapes** (`relations.json`, capped at 64 pairs).

Three answers to three different questions, at one weight, all static, with nothing on the stage
saying which is which. The grammar segments even **carry a probability that is thrown away at
draw time**. That is why it reads as decoration: it is not that the lines mean nothing, it is
that the picture refuses to say which meaning each line has.

The bounded fix, not done: **weight each grammar segment by its measured transition
probability** and give the three kinds three distinguishable inks. That turns the web into a
reading — *this bird's syntax, heavier where the transition is more likely* — from data already
in the assets. It needs a weight channel through `listener.setContext` and `ContextPaths`, which
is a real change rather than a styling tweak. It is also the natural surface for the predictive
work in the previous round's §9: a predicted continuation is an edge with a probability, and this
is the channel that would draw it.

## 6. The refactor, continued: two pages out of the monolith

`+page.svelte` is **4 211 lines, from 6 286** — a third gone, and none of it deleted.

```
src/lib/pages/InfoPage.svelte    699   §1-§6, the legend, and its swatch CSS
src/lib/pages/LearnPage.svelte   909   the pipeline surface, its form state, its layout
src/lib/lang/glossary.ts          22   BOUT_GLOSS
```

**`InfoPage` was the easy one and it is pure.** Nothing in it starts a sound, moves the camera
or holds state; every number it prints is a prop read from the loaded manifest by the page
above. That is the property worth having on the one surface whose whole job is to state what
the app does and does not claim — it cannot invent a figure.

**`LearnPage` is worth more than its line count.** Sixteen `$state` declarations went with it:
`harvestQuality`, `buildMinCluster`, `loopPerPass` and thirteen more were form fields for one
surface sitting in the same scope as the camera, the chorus and the matcher. `harvestOptions`,
`learnedTotals` and `learnedTypeCount` moved too — pure functions of `pipelineStatus`, and a
derived value belongs beside its only reader. What stayed in the page is everything the *poll*
owns: a learning run outlives the page you started it from, so `pipelineStatus` and `job` are
props.

`BOUT_GLOSS` became a module for the reason its own docstring gave: it was held as one string
so the gloss could not drift between the five places that carry it, and the moment a surface
leaves the page a page-local constant stops being reachable.

### Two regressions, both found by instruments rather than by looking

1. **`:global(...)` is Svelte-only syntax.** Two rules moved into `layout.css` still used it, so
   the info page silently lost every paragraph gap. A plain stylesheet needs the bare selector.
2. **`.stagepage` stayed behind when its element left, and it broke the table.** Both
   `.stagepage` rules were in the page's scoped CSS while the `<div>` moved into a component.
   `.stagepage.tall` is the whole height chain the inventory table's windowing depends on:
   without it `.tbody` grew to fit its content, its measured `clientHeight` became the height of
   all 13 748 rows, and the window arithmetic faithfully drew **every one of them into the DOM**.
   A missing `overflow: hidden` rendered the exact thing the windowing exists to prevent. Caught
   by counting `.trow` elements in the browser: **13 748 drawn, then 48 after the fix.**

Neither would have been caught by reading the diff, and the first would not have been caught by
a screenshot either. The two instruments that found them are worth keeping: a **computed-style
probe** (open each surface, read the one property each moved rule uniquely sets, assert it is
still set — 24 of them) and a **DOM-count probe** on anything virtualised.

Screenshot diffing was tried first and could not do the job: 5-21 % of pixels differed on every
surface, all of it the live cloud, the churning inventory table and font rasterisation, none of
it localisable.

### Still monolithic, and the next cuts

The page is still 4 211 lines and the three tab panels are most of it — Sing (~230), Compose
(~490), Listen (~240). Those are harder than the two pages because they read and write the
chorus, the camera and the selection, so extracting them means deciding what the chorus state
machine's API is. **That is worth doing next and for the reason §1 exists:** two bugs this round
came out of that machine being four effects and two flags in one scope.

## 5. Tests

`npm run check` clean apart from the four pre-existing `syrinx-processor.js` errors, zero
warnings. `build`, `verify:layout`, `verify:split-knots`, `verify:trajectory`,
`verify:inventory-table` and `verify:biplot` all pass. Both §1 fixes were measured in a real
browser before and after, and the numbers are in §1.

# Lyrebird — the learn page, and a name for a sound nobody named (2026-08-03)

**The v8 chain is still running** — see the section below this one, which is still the first
thing to read. It went into stage 1 (`learn`) at 11:41 and was still there at 12:45. Nothing
in this round touches the pipeline or the installed assets, so the two do not interact.

## 1. Learn is a page off the header, not a tab in a 20 rem column

Owner: *"we have a learn tab, I want to move it into the top."* The left strip reads
**Sing / Compose / Listen** now, and all three are ways of making or hearing a sound. Learn
never was: it drives the pipeline, it reports a run that outlives any selection, and it wanted
twice the width it had. It opens from a `learn` cell in the header's readings row beside
`info`, and that cell shows a pulsing dot and the job's age while a run is going — the only
place the app could admit to a running loop while the galaxy is what you are looking at.

Consequences worth knowing: the pipeline poll is fast (1.5 s) while the page is **open** and
slow (6 s) otherwise, where it used to key off the tab; the right-hand readout panel is
unconditionally the *reading* again, because the learning run used to displace it.

## 2. The inventory table, and it follows playback

Owner: *"a data table on that page which follows playback — while it plays it jumps around in
the list."* 13 748 rows over 2 423 species, over a canvas already drawing 348 461 points, so
it is **windowed**: only the visible slice exists, held by two spacers. The arithmetic is in
`inventory-rows.ts` because an off-by-one in it shows as *a row that never highlights* rather
than as an error.

The cursor is new and is the part that could have been quietly wrong. `onScheduled` hands over
a whole phrase at once and then the audio clock runs alone, so nothing knew which note was
sounding at any instant. `SoundingLog` (`audio/sounding.ts`) is that reading. **The
latest-starting window wins, not the first found** — during a chorus the first-match version
marks whichever bird started earliest, which reads as the table lagging a phrase behind rather
than as a bug. Proven to fail: mutating the scan to first-match makes
`verify:inventory-table` report it.

The list is pulled to the sounding row only when that row has **left the middle half** of the
viewport, then centres it. Centring on every note makes a table a blur at chorus rates, which
would defeat having one.

## 3. A fitted type gets a name, and it is a description of a noise

Owner: *"we call all learned L whatever — wouldn't it make more sense to give them the real
infos, real type names, real call names?"*

**Half of that is available and half of it is not, and the difference is the project.** A
documented call's name comes out of a paper with a citation and names a *function*: `jar` and
`tsupi` are Suzuki 2014 on the Japanese great tit, `feebee` is the chickadee, `hawkPerched`
the Siberian jay. Nobody has ever documented what `L33` is for, so giving it a call name would
be a claim with no source — the exact false positive the owner warned against in the same
breath.

What *is* available is the form. The pipeline measured this syllable's timbre class, its
modulation depth and rate, its vibrato and its pitch track. So a fitted type is named after
what it sounds like and never after what it might mean:

```
L33  ->  buzzy rattling flat          554 Hz   29 ms
L32  ->  buzzy rattling fall, dipping  5.2 kHz  251 ms
```

`syllable-name.ts` holds it. Two things were tuned against the corpus rather than by taste:
**at most one modulation word** (the first version produced *"reedy trilled warbling
two-voiced steep fall, dipping"* — accurate and past the length at which a name is a name),
and `MOD_DEPTH = 0.4`, because `amDepth` clusters at 0.15/0.3/0.45/0.6/0.8 over the 13 704
fitted types and a lower gate called four types in five *trilled* — a word every row carries
describes nothing. Median name is 37 characters.

The test has a **forbidden-word scan** over described names — `alarm`, `contact`, `warning`
and five more. It is blunt on purpose: if one of those ever enters the vocabulary, that fails
rather than shipping a claim with nothing behind it.

Where it shows: the inventory table's `sound` column, and the tags in the cloud, which used to
spend their one line on `L01`.

## 4. What the table says out loud that the ids were saying alone

`doc` / `fit` is a column now. A reader meeting `jar` beside `L33` had no way to know the first
was a name and the second a serial number, and the app was signalling it with font weight.
Also fixed: the id column was 3.2 rem and `hawkSearching` ran straight over the column beside
it. Counted off the syllable's `learned` field, never off the shape of the id — the shape
happens to be right and is one rename from being wrong.

## 5. The two pages were badly designed, and were redesigned

Owner, in order: *"the design and placement of the buttons is ugly"*, *"the page design for
both is horrific"*, *"make a 2 column design and the entire width"*, *"get rid of the grid"*.
All four were fair.

- **The header openers had no padding and no divider**, so `info close` ran into `learn open`
  as one word. The cause is one selector: `.readings > div` does not match a `<button>`. A
  cell of that row is a cell of that row whichever element it is.
- **The pages laid prose directly on the stage's grid ruling**, so every line of body copy had
  a rule through it. The graph was reaching for "turning the same instrument over" and it cost
  legibility, which is not a trade. The stage keeps its grid; a document is paper.
- **Full width, two columns**, 2.6 rem padding. A single centred 38 rem column left two thirds
  of a 1600 px screen empty; full-bleed paragraphs are one long line. Two columns are both
  fixes at once.
- **The left column of the Learn page was clipping** — the store path and the critic line ran
  out from under themselves. `min-width: 0`: a grid item's default minimum is its content's,
  and one unbreakable 52-character path was widening the track past itself.

## 6. The info page was reworked, with figures

Owner: *"we need explanations of what types are, fits, froms, knots… what the project is
(please no false negatives no false positives)… nice design with explanations and a screenshot
of different things that are mentioned, nice to scroll, nice to look at but still scientific."*

Six numbered sections. **§1 is a table of what the app will and will not say**, claims and
refusals in the same list, because a limit stated beside a claim is harder to skip than a
caveat at the end. **§2 is the vocabulary** — point, type, knot, id, doc, fit, Hz·ms, fit,
from, bout, match — which is what §4 above needed a reader to already know. §3 carries four
**figures, which are screenshots of this app** (`app/static/figures/`, 576 KB for four,
quantised and downscaled from 1.7 MB). §5 quotes the loaded manifest and nothing else. §6 is
the old legend, verbatim and diffed against git to prove it.

Also on §1: "no samples" and "340 079 measurements of real recordings" are both true and sound
contradictory, so the page says what is kept is the measurement and never the audio.

## 7. The node label: filled, then put back

The tags were reworked to be filled with the knot's colour with black-or-white ink chosen from
that colour's **measured luminance** — lightness is not brightness, and yellow at 45 % L is
about three times as luminous as blue at the same L. It worked, it was tested, and the owner's
verdict on seeing it was *"too dominant"*, which is right: a tag is an annotation and the cloud
is the data. **Reverted**, and `readableInk` was deleted with it rather than left lying about.

Two things kept from the attempt. The **bird's name is first now** and the sound second —
owner's call, and the right way round for the question a lit knot raises. And `.figures`
wraps: it was `nowrap` on a 15 rem card holding five figures, so it had *always* been
overflowing and being clipped mid-word (`measured fiel`). Only a filled card made it visible.

## 8. Tests and state

`npm run verify:inventory-table` is new: 60 checks over the row building, the window
arithmetic, the follow rule, the sounding cursor, and the naming. Two of them were proven to
fail by mutation (first-match cursor; `padTop` off by one row).

`npm run check` clean apart from the four pre-existing `syrinx-processor.js` errors, and
**zero warnings** — the table's `aria-rowcount`/`aria-rowindex` needed the grid row pattern,
which costs one wrapper per *drawn* row (about forty), not per row in the corpus. `build`,
`verify:layout`, `verify:split-knots`, `verify:trajectory`, `verify:biplot`,
`verify:inventory-table` and `check-provenance-buffers` all pass. Every surface was looked at
in a real browser.

§1 and §2 have been through `/ste-writing` (STE-flavored): no semicolons, no contractions, no
sentence over 25 words, active voice, and every measured figure left exact. One semicolon in §5
went with them. The figures were re-rendered after the label revert, so what they show is what
ships.

**Not done:** the three ideas from the earlier interface round (radial decompression of the
core, the depth exponent, a drawable knot hull) are untouched and still the best-argued things
on the list.

## 9. Asked and answered: can AI close the three "it does not" rows?

Owner asked how the three refusals in §1 could be solved, and *"where is the synthetic space
where we try to find the missing parts based on the geometrical structures of already known and
learned?"* Not built — this is the survey, because the pieces all exist and the blocking number
is small.

**Every component is already in the repo.** `critic.py` gives the 32-d embedding the galaxy
clusters in and a novelty scorer (AUC 0.825 on held-out species, calibrated to 5 % FPR).
`spacemap.py` bridges the browser's 28-d descriptor into it (RFF ridge, 0.9043 median cosine).
`density.py`'s docstring already names the primitive: *"a dense region containing both
documented renders and unlabelled field audio is the translation primitive this project has
been missing."* `inverse.py` decodes a mel patch to syrinx parameters, so a **point that does
not exist yet can be rendered** — trained on unlimited synthetic data because we own the
forward model. `geometry.py` is the arbiter: kNN lift against a label-permutation null, and *a
grouping that cannot beat its own shuffle is reported as no relation.* `perch.py` sets the
discipline for how a model's guess may appear at all — quarantined metadata with an honesty
label, and **nothing in learn.py reads it**.

**The blocking measurement, taken here: there are 53 documented functions over 12 species.**
`territorial` 10, `structural` 24, `alarm` 11, `contact` 4, `recruitment` 2, `courtship` 2.
That is the entire anchor set for any propagation onto 13 704 fitted types, and function is
species-specific — one clade's alarm need not be acoustically like another's. So the honest
prior is that cross-species function transfer is weak. It is cheap to measure and the
measurement is the deliverable.

Row by row:

1. **"It does not translate birdsong" — keep it.** Not an AI problem. Translation needs paired
   call-to-behaviour ground truth, which is field biology. Perch returns species, not meaning.
2. **"It does not say what a fitted type is for" — this is the one that can move**, and only by
   changing the epistemic category: not *"L33 is an alarm call"* but *"L33 sits where 78 % of
   documented neighbours are alarm calls, and this predictor scores X on species it never
   saw."* A prediction that ships its own error rate is allowed; an identity is not.
3. **"It does not claim the picture is a faithful map" — partly, and not with a better
   projection.** 3-d is the ceiling. The measured split already says it: coarse is trustworthy
   (0.9247), local is not (0.4685). The fix is to stop asking the picture to carry the local
   question.

**The one experiment to run first**, because it is cheap and it decides everything: hold out a
real fitted type, interpolate in the 32-d embedding between that species' remaining types, and
ask whether the interpolant lands nearer the held-out type than chance. If the geometry
predicts held-out types, filling the gaps is warranted and `inverse.py` can render them. If it
does not, the synthetic space generates plausible noise. `w5_field_retrieval.py` is the
retrieval template and `geometry.py` supplies the null.

# Lyrebird — the v8 chain LANDED and it reproduced v7 bit-for-bit (2026-08-03, 15:12)

**Finished 15:12:55, 3 h 31 m. Nothing was installed, because there is nothing to install:
v8 is byte-identical to what `app/static/birdy` already holds.** Every asset file md5-matches
the installed one and the inventory matches too (`de98ec12…` both). Every manifest number is
the same figure rather than a near one — knnAgreement 0.4685, faithfulness 0.4745 / 0.4829,
torn 1864 / 5320, severe 1009, trustworthiness 0.9247, continuity 0.9036, purity 0.9452,
meanRadius 0.5303. (The chain's own narration prints "3D kNN agreement 46.9 %", which is that
same 0.4685 rounded — not a difference.)

Both gates passed on the way: `verify.log` says `all checks passed`, and **stage 6 did not
shout** — every watched count came out +0 %:

```
                        installed  candidate  change
species                      2423       2423     +0 %
types                       13748      13748     +0 %
species with a song            68         68     +0 %
song types                    164        164     +0 %
repeat classes                 82         82     +0 %
motifs                         82         82     +0 %
grammar chunks               1272       1272     +0 %
```

**Why identical is the correct result and not a failed run.** Two things were checked before
concluding it, because "the output equals the input" is also what a chain that silently
discarded its own work looks like:

- **The store has not grown.** `harvest-gan/state.json` reads `syllableObservations: 340079`
  and `streamCount: 425061`, which is exactly what the installed manifest recorded. No new
  audio has arrived since that inventory was written on 2026-08-02.
- **No fitting code changed.** Every commit since then touches the *projector and build*
  layer — PaCMAP, poincare, the split gate, cmds-chord, the match ramp — and none of them
  touches learn, docrefit or respfit.

Same store, same fitting code, fixed seeds: deterministic reproduction, down to PaCMAP's
seeded layout. The stages did do their work and said so — docrefit shipped 11 of 17 one-tone
re-fits, respfit ran its gate over 1 277 species — and the result of doing it again on
unchanged inputs is the same file.

**So what the 3 h 31 m actually bought is a reproducibility proof**, end to end: the galaxy
on screen is exactly what this pipeline produces today, so every figure quoted anywhere in
this handoff is re-derivable rather than historical. That is worth more than a new build would
have been, and it is not an install.

**What would make a next chain produce something different:** new audio in the store (harvest
first — the queue serves the emptiest bird first), or a change inside learn/docrefit/respfit.
Rebuilding alone cannot, and re-rolling the projection on identical input reproduces the same
positions.

**Two things this chain did not settle**, so they are not surprises: the production
cMDS-versus-PaCMAP bake-off (skipped for time — `--compare-projections` would add UMAP over
348 461 points), and `grow` stays unavailable on any PaCMAP build.

**One instrument note, for whoever writes the next watcher.** The monitor armed on this run
polled `pgrep -f run_production_v8.sh` to detect the chain exiting, and its own shell command
line contains that string — so it matched itself and could never have fired. The stage lines
carried the information instead, and no time was lost, but a `pgrep -f` on a pattern that
appears in the watcher's own command is a check that always says yes.

# Lyrebird — the interface round (2026-08-03): a page instead of a popover, and a ruler that says one thing

## Done

**The ruler caption.** Owner: *"delete this line, it means nothing — we just need to know
what the unit on the ruler means when we zoom in, and place it correctly. It is not on the
left side, the panel with Sing is before that."* Both halves were real. The caption sat at
`left: --ruler + 20rem + 2.6rem`, a hard-coded guess at the width of the controls column,
and the column outgrew the guess, so the text ran back under the Sing panel. It is anchored
to the **right** edge now, which cannot be wrong about a left-hand panel's width. It carries
the tick unit and nothing else. 53 lines of caption machinery went with the rest — the stats
sampler that fed only the removed spans, and the `widthKnots` and `reading` props.

**The legend button is gone, and the legend is a page.** The `?` icon on the right edge and
its 16 rem popover are deleted. Its 205 lines of legend moved into a **full-stage page**
opened from an `info` item in the header readings row, beside `points` and `clusters` —
because that row is already where a viewer looks for what the build is, so what the build
*means* belongs at the end of it rather than behind an icon in a corner. The page is ruled
with the same faint graph the stage draws behind the points, at the same weight, so opening
it reads as turning the instrument over rather than leaving it for a document. Two columns
once there is room: the paper and the summary as prose, the legend as reference.

It also carries the **whitepaper** (`app/static/lyrebird-whitepaper.pdf`, 0.7 MB, copied
from `docs/whitepaper/arxiv/`) and the **fitted axis directions** as a table of shares. Those
were in the ruler caption and read as clutter there — a share of 19 % beside a name is an
explanation, not a label.

## Not done — the owner asked for these and they are next

1. **Move the Learn tab out of the left column and into the header**, as a second full-stage
   page in the same shape as `info`. Owner: *"we have a learn tab, I want to move it into the
   top and make that what you proposed, instead of the learning in the tab left."* The left
   tab strip then reads Sing / Compose / Listen.
2. **A data table on that page, which follows playback** — *"while it plays it jumps around
   in the list."* The learned inventory as rows, and the sounding row scrolled to and marked
   as each note fires. `onScheduled` already fires per note and is where the cursor comes
   from.
3. **The tone pass.** The new page copy was written STE-flavored; the 205 lines of legend
   moved into it verbatim and have not been through `/ste-writing`.

## Ideas for the cloud, from the owner asking what would make it look better

Recorded because they follow from measurements rather than taste:

- **The core is still one mass.** `KNOT_GAP` 3.0 moved every knot apart by one factor, which
  fixed the median and not the core, and packing the core is PaCMAP's signature. A **radial
  decompression** — push each knot outward as a function of its distance from the centre —
  would open the middle and leave the rim alone. It is monotone in radius, so it preserves
  every neighbour relation and stays the same kind of honest display transform `KNOT_GAP` is.
- **Depth is barely reading.** The perspective exponent (0.82) and the aerial gradient (0.62)
  were tuned when the cloud was 30 % tighter and knots overlapped. With real gaps they have
  more room to work.
- **A knot's shape is now drawable.** Earlier rounds rejected a hull or a ring at the measured
  `radius` because knots interpenetrated 3.3x. At 0.99x they are separate objects, so the
  thing that could not land before now can.
- **The diagonal red and blue streaks look wrong** in a resting frame. Worth checking whether
  `GridBurst` fires continuously rather than on response.
- **Argued against, for the record:** tinting knots by genus at rest would make the map read
  as regions immediately, and it spends the rule that nothing is coloured until it sounds.
  That rule has earned its place.

# Lyrebird — room to breathe (2026-08-03): KNOT_GAP 2.0 -> 3.0 on the PaCMAP build

Owner, on the installed v7: *"it tends to dense up a lot and we nearly can't see the
connection between them — so we need to visually give all nodes much more space in between
so they can breathe."*

**The crowding is absolute, not relative, and the obvious ratio would have hidden that.**
The number this project usually quotes — how many times wider a knot is than the gap to its
nearest neighbour — actually *improved* when PaCMAP replaced cMDS:

```
                            v6 cmds    v7 pacmap
median knot spacing          0.0395       0.0280
median knot extent           0.0829       0.0417
width / gap                    2.1x        1.49x
```

PaCMAP packs neighbourhoods tighter, so the whole cloud shrank by about 30 % and every knot
shrank with it. The ratio looked better while the picture got denser, and a thread between
two knots then runs through occupied space rather than clear air — which is the half of the
report about connections.

**KNOT_GAP 3.0** is where both readings agree: spacing back to **0.0419**, just past what v6
had, and the ratio at **0.99x** — the crossover where a knot is no wider than the gap to its
neighbour, so knots stop interpenetrating and read as separate places. One constant if it
wants dialling: 3.7 gives 0.8x, 2.5 gives 1.2x. Each knot's own extent is untouched, which is
the whole point of moving the gap rather than shrinking the knots (`CLUSTER_SPACING` has the
argument). Everything downstream recomputes from the drawn layout: the wave's reach, the
framing, the LOD grid, the ruler's unit.

**Found while measuring, and it is good news nobody had looked for:** `localShapes` repairs
far more tearing than the pipeline's own count suggests. The manifest reports **1 864 of
5 320** knots torn, and `drawnLobes` on the raw shipped positions agrees at 1 750 — but on
the positions the app actually *draws*, after the local pass reshapes each knot from its own
features, only **244 of 6 389** are still two-lobed. So the two-level layout is doing most of
the work, and the per-lobe tags are the backstop for the 244 it cannot honestly repair.

# Lyrebird — the clear-out (2026-08-03): what PaCMAP superseded is gone

PaCMAP is the approach, so the things it replaced are removed rather than left lying about.
Every finding survives — in the section below, in the docstrings, and in git — but no code
that nothing will ever run again.

**Removed from the pipeline (163 + 30 lines):**

- **`poincare`** — the hyperbolic projector. Won on a planted tree (0.602 against cMDS's
  0.580) and lost on the real corpus (0.684 against 0.724), because what gets embedded is
  the acoustic space and that carries taxonomy only weakly. §4 below has the numbers.
- **`cmds-chord`** — the exact Euclidean metric for cMDS. Correct arithmetic (negative
  eigenvalue mass exactly zero) and measurably worse: 0.722/0.699 against 0.767/0.742.
  `mds_squared_distances` **keeps** the chord metric, because a `projection-basis.json`
  written while that projector existed records `metric: "chord"` and a reader that cannot
  handle a value it once wrote is a bug. `pipeline/analysis/mds_metric.py` still runs the
  whole comparison, through `_landmark_mds` instead of a projector nobody should pick.

`PROJECTIONS` is now `umap, pca, cmds, pacmap` — the set worth running, not everything ever
tried.

**Removed from the app (89 lines):**

- **`trajectoryVertexShader` / `trajectoryFragmentShader`** — the one-pixel `LineSegments`
  shaders, orphaned by the ribbon pass earlier the same day. Nothing referenced them.
- **The `CLAIM_*` taxonomy** — eight exports mapping call functions to four "claim" classes,
  with labels and hints. Entirely self-referential: `CLAIM_OF_FUNCTION` fed `CLAIM_LABELS`
  fed nothing, and no file outside `shaders.ts` had ever read any of it. Its own docstring
  said the view that used it "has been taken out" and that the taxonomy was kept anyway;
  `functionClass` still ships on every centroid, so if that view comes back the reasoning
  is one `git show` away.

Checked and **kept**: `FRONT_SPEED`/`FRONT_WIDTH`/`frontEnvelope` (used inside `shaders.ts`),
`speciesGenus`/`genusHue`/`speciesSaturation` (used inside `palette.ts`),
`AssetsMissingError` (thrown). Over-exported, not orphaned.

## The cost of the new default, and it is not small

**A PaCMAP build writes no `projection-basis.json`, so `grow` cannot extend it.** `grow`
adds new audio to an existing galaxy without moving the points already in it, and it does
that through the frozen frame only cMDS emits. PaCMAP does expose a `transform`, and its own
documentation rules it out for this purpose — *"the same point could be mapped into a
different place"* is exactly what `grow` may not do.

So a galaxy on the current default can be rebuilt and never extended. The build now says so
on stderr instead of leaving it to be discovered. If growth matters more than the 3.2x local
structure, `--projection cmds` is one flag; that is a real trade and it is the owner's.

# Lyrebird — what the 3-d picture says, and four attempts to make it say more (2026-08-03)

Owner: *"does the 3d representation make any sense, does it tell us anything important? Is
there a better way to display it so visually we can read things out?"* Then: research first.

## 0. What it says today, measured

Share of a point's ten nearest neighbours **in the drawn picture** that share its label,
against the chance of two random points sharing it (40 000 of 348 461 points):

```
                in the picture    chance     lift
syllable type            6.0 %     0.05 %    120x
species                  9.8 %     0.31 %     31x
genus                   10.1 %     0.49 %     21x
```

So it is emphatically not noise. It is also not a local map: **nine of every ten
neighbours are a different bird.** Global distance faithfulness is r = 0.667. The picture
is a trustworthy coarse map and an untrustworthy local one.

**And the projection was the bottleneck, not the corpus.** The same test in the shipped
8-d features: type **12.9 %**, species **25.5 %** — 2.1x and 2.6x what the drawing shows,
and 8-d is only a linear PCA of the 32-d space, so the real space holds at least that.

## 1. The research (August 2026)

- **The critique is real and we reproduced it from the other side.** Chari & Pachter's
  Picasso forces data into any 2-d shape; an embedding shaped like an **elephant** scores
  as well as UMAP and t-SNE on distance metrics. The shape of a scatter is not evidence.
  (Contested — a 2024 rebuttal shows UMAP/t-SNE do preserve neighbourhoods — but the
  contested part is "how bad", not "lossy".)
- **cMDS is a global-only method**, which is exactly our measured failure: classical MDS
  fits pairwise distances and has no local-neighbourhood term at all. PaCMAP was built for
  the split (near / **mid-near** / far pairs) and benches first among the modern methods.
  DREAMS (Aug 2025) beats it but is 2-d only.
- **Hyperbolic space suits a taxonomy** — Poincaré embeddings match high-dimensional
  Euclidean baselines at 2–4 dimensions, and we have 1 043 genera over 2 423 species.
- **Interpretable axes have a literature**: generalized biplots for stress-based
  projections, DimReader, FeatMAP. *Annotate* the projection rather than replace it.
- **3-d on a flat monitor buys less than assumed** — depth cues reduce to occlusion,
  parallax and shading, and one study found parallax did not help size judgement. 3-d pays
  off with stereo, or **combined with cues like point size**.
- **Supervised UMAP would be a trap.** We have labels for 96 % of points; it would make the
  picture look far better and destroy its evidential value, because it shows you the labels
  you fed it. Argued against, not adopted.
- **The field's practice** (bacpipe, EcoScape) is 2-d UMAP + click-a-point-for-spectrogram:
  the *interaction* carries the local question, the map only carries the coarse one.

## 2. PaCMAP is now the projector, and the bake-off is why

Scoring gained **trustworthiness and continuity** (Venna & Kaski), because faithfulness is
a correlation over random pairs and therefore blind to the thing a viewer reads when two
marks sit together. Verified against known answers: 1.0 for an identity embedding, ~0.50
for a random one. All six candidates, same corpus:

```
projector    pearson  spearman   trust    cont   knn10      torn
umap           0.341     0.328   0.931   0.947   65.7%   156/447
pca            0.589     0.568   0.845   0.941   22.2%    15/502
cmds           0.767     0.742   0.850   0.956   21.4%    18/493
cmds-chord     0.722     0.699   0.861   0.961   23.2%    19/493
pacmap         0.324     0.284   0.936   0.933   68.5%   217/438
```

cMDS held the default only because faithfulness was the only thing scored. **PaCMAP puts
68.5 % of a point's drawn neighbours on its own type against cMDS's 21.4 %.**

**It pays in tearing, and that could not be papered over.** Of its 217 torn knots only 14
are flung outliers; **120 are genuine second lobes holding a median 21.7 % of the knot at a
median 0.464 box units.** Anchoring a label at the nearest member stops it floating in the
void but leaves those lobes lit and anonymous — the report this whole line of work began
from.

So `layouts.ts::drawnLobes` splits a two-lobed knot **in the layout pass, from the drawn
positions** — the one dimensionality where the gap/spread threshold of 5 is calibrated,
which is why the equivalent gate in `_type_blobs` stays off. Each lobe gets its own anchor
on its own most central member, and `NodeProjector` emits a tag site per lobe, so both lit
patches carry the name. The larger lobe keeps the knot's single identity for the thread and
the fly-to. Measured: **197 second anchors over 396 measurable knots, 2 928 members that
would otherwise have lit unnamed, 27 ms.** The deterministic axis-cut agrees with the
pipeline's k-means test (197/396 against 217/438; median lobe 20.7 % against 21.7 %).

## 3. The picture now says what its directions mean

"I cannot read anything off this" was true: correlating each drawn axis against every
nameable quantity, the strongest was knot member count at **+0.26**, duration at **+0.05**.

**The meaning is there and it is not axis-aligned**, which is why it needed a biplot.
Fitting each attribute's gradient obliquely against the drawn coordinates:

```
              shipped cMDS   PaCMAP
brightness           0.402    0.796
noisiness            0.375    0.571
loudness             0.639    0.507
movement             0.240    0.425
duration             0.015    0.035
```

The ruler caption names each screen direction with the share it explains, rewritten as the
camera settles. r² travels with every name, because an arrow without it is a confident
claim about an unknown amount — and duration, which this picture genuinely does not carry,
falls below the threshold and never appears. Only quantities a person can hear are offered:
26 of the 28 descriptor dimensions are MFCC coefficients, and "mfcc7_mean" is a label, not
an explanation. **PaCMAP is also markedly more readable** (brightness 0.80 against 0.40),
which nobody had measured.

## 4. The hyperbolic branch: a clean no

`poincare` is a sixth projector — Riemannian SGD on sampled-pair stress in the 3-d Poincaré
ball, rather than h-MDS, whose `cosh` of the full matrix overflows and whose recovery step
eigendecomposes an indefinite matrix. Against the shipped 13 848 knot vectors:

```
poincare     0.6836   (hyperbolic distance, the one it fits)
cmds         0.7239
cmds-chord   0.6827
pca          0.5870
pacmap       0.4041
```

On a **planted** three-level tree it wins as the literature predicts (0.602 against cMDS's
0.580). On the real corpus it loses. The premise breaks: the corpus is a taxonomy, but the
thing being embedded is the **acoustic** space, and that space carries taxonomy only
weakly — 9.8 % species agreement against 0.31 % chance is 31x chance and still nine
neighbours in ten from another bird. The fit says so itself: it settles at a maximum radius
of 0.68, never reaching for the room near the boundary that is the whole point.

Two limits on that: it is a hand-rolled sampled-pair optimiser, so "did not win" is weaker
than "cannot win"; and a hyperbolic embedding of the **taxonomy** rather than the acoustics
was never tried — a clade map instead of an acoustic one, a different question.

## 5. One thing dropped, and the reason

"Knot weight: size by log(count), edge by cohesion" was chosen and then **not built**, after
checking. It came off a miss-list that predates two later rounds: the knot pins were deleted
on the owner's call ("marks that are not sounds"), so there is no per-knot mark to size;
member count is already visible as the number of points drawn; and `localShapes` already
scales each knot by its own feature spread, which is what `radius`/`cohesion` measure. What
is genuinely still undrawn — `meanDuration`, `speciesMix`, the per-knot source mix — has no
channel left, since hue is spent on genus and size on LOD and events.

## 6. Verified on screen — v7 is installed

**v7 is built, installed and looked at.** Owner, on seeing it: *"much better yes."* That is
the verification the tests could not reach, and it covers the three renderer changes that
had no automated check between them: the **ribbon threads** (a dead ShaderMaterial draws
nothing, so "the threads are visible" is also "the shader compiled"), the **per-lobe tags**,
and the **axis caption**.

Production figures, 348 461 points and 13 848 knots, against the cMDS build it replaced:

```
                          v6 cmds    v7 pacmap
knnAgreement               0.0849       0.4685   5.5x
trustworthiness                 -       0.9247
continuity                      -       0.9036
faithfulness r             0.6672       0.4745
torn / measured          386/6733    1864/5320
brightness as a direction   0.402        0.618
```

`drawnLobes` at production scale: **1 750 second anchors, 18 188 members that would
otherwise light unnamed, 63 ms** — against `localShapes`' 197 ms, and agreeing with the
pipeline's independent k-means count of 1 864.

**Still not measured at production scale:** the split-gate A/B and the cMDS-versus-PaCMAP
bake-off were both run on the 40-species descriptor-space corpus. The *ranking* transfers;
the absolute figures do not.

New instruments: `npm run verify:biplot`, `verify:trajectory`, `verify:split-knots`;
`neighbourhood_quality` in the pipeline; `pipeline/analysis/mds_metric.py`.

`npm run check` clean apart from the four pre-existing `syrinx-processor.js` errors;
`build`, `verify:layout`, `verify:biplot`, `verify:trajectory`, `verify:split-knots`,
`check-provenance-buffers` and `galaxy.self_test` all pass.

# Lyrebird — the song lines (2026-08-03): the thread was one pixel wide, and it is not a styling choice

Owner asks 4b and 6 from the WORK QUEUE: *"make the song lines legible — they are currently
hard to see at all"* and *"a song playing should animate its line, and that wants refining"*.
Both have one cause.

## 1. `lineWidth` does not work, and the code already knew

`THREE.LineSegments` rasterises `gl.LINES`, and WebGL's `lineWidth` is ignored by every
desktop driver worth naming: **a thread is exactly one pixel however close the camera gets**.
One pixel at 0.55 alpha over a 348 461-point cloud is not a faint line, it is no line. The bead
run beside it exists only to compensate — its own comment says so: *"a GL line is capped at one
pixel wide, which disappears against the cloud, so the path is also drawn as a run of small
sprites"*. So there was no styling change available; the geometry had to change.

**The thread is now a ribbon**: two triangles per node-to-node segment, corners offset
perpendicular to the segment **in screen space** in the vertex shader, so the width is in
pixels and does not change with depth. Resting width 2.2 px against the cloud's 2–3 px marks —
legible over a dense scatter without becoming the loudest thing on the stage, which keeps the
project's ordering that the points are the data and the thread is a relation drawn between
them.

No subdivisions any more. The old geometry sampled each segment 14 times because the travelling
highlight had to move smoothly along it; on a ribbon the along-path coordinate is a varying and
the swell is computed per *fragment*, so a straight segment needs exactly two ends and comes out
smoother than the 14-sample version. The bead geometry keeps its subdivisions — those are the
marks running along the thread and there has to be a run of them.

## 2. The line animates by changing shape, not only brightness

That is ask 6, and it is the reason the width is computed in the vertex shader rather than
faked in the fragment. Three things widen the ribbon:

- the **travelling peak** — the same gaussian the bead rides — takes it to about 5.7 px, so the
  note passing along the phrase is a swell running through the line;
- the part **already sung** is held about a third fuller than the part still to come, so the
  phrase visibly fills in as it is performed;
- **nothing at all while idle**: a selected-but-unplayed call stays the thin thread it was, so
  the animation still means "this is sounding now".

## 3. What is verified, and what is not — say it plainly

**The shader is not verified. Nothing in this repo can compile GLSL.** A dead `ShaderMaterial`
draws nothing and reports only to the console, which is how this project lost its entire grid
to a variable named `out`. So the work was split so that most of it *could* be checked, and
`npm run verify:trajectory` (new) checks it:

- the buffer construction is a pure function in `ribbon.ts` — vertex counts, both sides present,
  every vertex paired with its own far end, the along-path index spanning `n..n+1` (an
  off-by-one there puts the swell on the wrong syllable and reads as lag, not as a bug);
- the three cases that would draw nothing or NaN: a zero-length segment is skipped rather than
  normalised into NaN, which would take the whole draw call and not just its quad; a one-node
  path emits nothing; the segment cap binds before the buffer ends, since writing past a
  Float32Array is a silent no-op in JS and would show as a thread that stops halfway;
- **the vertex shader's pixel arithmetic, restated in JS and checked against it** — half-width
  is 2.000000 px for a 4 px thread at w = 1, 5 and 40, so the perspective divide is right, and
  the same for vertical and diagonal segments, so the per-axis resolution divide is right. This
  is the half that goes wrong quietly: an offset that forgets the divide looks correct at one
  depth and wrong at every other;
- a **reserved-word scan** over every exported shader string, and a check that every varying a
  fragment shader reads is both declared and assigned by its vertex shader. Proven to fail:
  injecting `vec2 out = ...` into the ribbon shader makes it report
  *"declares a variable named 'out', which is reserved in GLSL"* and exit 1. It is a text scan,
  not a compiler, and it says so.

What is left unverified is everything a screen would tell you: whether 2.2 px is right, whether
the swell reads, whether the ribbon fights the bead. **Someone has to look at it.**

`npm run check` clean apart from the four pre-existing `syrinx-processor.js` errors;
`build`, `verify:layout`, `verify:split-knots`, `verify:trajectory` and
`check-provenance-buffers` all pass.

# Lyrebird — the pipeline pair (2026-08-03): both of last round's open items, and both premises were wrong

HANDOFF §5 left two things "not done, both need a rebuild". Both are now built and measured.
Neither turned out to be the thing it was described as, and in both cases the measurement is
the deliverable.

**Neither is installed, and neither is the default.** `learn` has since been run on
`pipeline/out/harvest` (25 min — it is a 40-species store, not the one v6 came from) and two
builds done from it, so both changes are now exercised end to end. `cmds` stays the default
projector and `--type-split` is opt-in; §1 and §2 say why, and in both cases the reason is a
measurement rather than caution. `pipeline/out/harvest-gan` is the only store carrying
typing.json *and* embeddings.f32, so it is the route to a production-scale `--space embed`
check when someone wants one.

## 1. cMDS and the "honest" metric: it trades worse, and the number behind the ask means
   something else

The ask was: `negativeEigenvalueMass` is **0.408**, cMDS is fitting a space that cannot exist,
the rows are unit vectors so the chord `√(2 − 2·cos)` *is* their Euclidean distance and drives
the negative mass to zero. All of that is true. `cmds-chord` implements it, one
`mds_squared_distances` serves the full path, the landmark path and `grow.embed`, and the
projection basis now records which metric it was fitted with so a grown point cannot be placed
through the other one. Asserted in the self-test: the chord distance is the Euclidean one to
1e-16, and its double-centred matrix is PSD to 1e-9.

**And it measures worse**, on the shipped 13 848 knot vectors, landmark and full paths alike:

```
projector    metric   neg mass   3 axes   r(cos)  rho(cos)  r(chord)
cmds         cosine      40.4 %    33.4 %   0.7436    0.7362    0.7239
cmds-chord   chord        0.0 %    32.2 %   0.6956    0.6854    0.6827
```

Note the last column: the cosine fit is a **better fit to chord distance than the chord fit
is**. That needed explaining before it could be used, and the explanation is reweighting —
every metric in the family `(1 − cos)^p` orders every pair identically and differs only in how
far pairs are weighted against near ones. The sweep:

```
   p    neg mass   pearson   spearman
 0.5       0.0 %    0.6925     0.6811   <- the chord, a true Euclidean distance
 1.0      41.4 %    0.7414     0.7332   <- shipped
 1.5      62.1 %    0.7498     0.7462
 2.0      73.7 %    0.7360     0.7364
 4.0      91.1 %    0.6125     0.6133
```

**Faithfulness peaks at 62 % negative mass and is at its worst at 0 %.** So
`negativeEigenvalueMass` does not measure "how much the 3D picture has to invent", which is
what galaxy.py's docstring said it measured for a year. It measures one true thing — that
classical MDS is fitted to a dissimilarity no Euclidean space can hold — and nothing about the
quality of the answer. Docstring corrected. `cmds` stays the default. p = 1.5 measures best by
0.008 and is **not** adopted: a knob fitted to a faithfulness number on one seed is how the
match ramp got into trouble in the first place.

`pipeline/analysis/mds_metric.py` is the whole thing, re-runnable.

## 2. The bimodality split: the statistic behind "166 genuinely torn" does not survive 8-d

The plan was to gate `_type_blobs` on a type's own bimodality using the same test
`torn_clusters` uses — gap over spread, torn above 5. **That threshold is unreachable above
three dimensions and the reason is arithmetic.** A blob's mean radius grows like √d while the
gap between its two halves does not, so the ratio collapses as dimension rises. Measured on
unit rows, two blobs a full **180° apart** — the most separated two groups on a sphere can be:

```
             null (one blob)   90° apart   180° apart
3-d                1.5 .. 2.0        5.48         7.45
8-d                0.7 .. 1.1        2.70         3.61
32-d               0.4 .. 0.7        1.25         1.82
```

A gate of 5 is sensible in 3-d and sits **above the maximum achievable** in 8-d. So last
round's `tear_dims.py` figure — *"166 of the 385 are also torn in 8-d, therefore genuinely two
groups"* — is not measuring what it says: at >5 in 8-d it selects configurations with unequal
spread or outliers, not separated groups. **The 3-d half of that script stands; the 8-d half
and the 166 need re-deriving.** Not done here.

**The gate that shipped is an effect size instead**: project both halves onto the line joining
their centres, divide the gap by the pooled standard deviation *on that line*. The √d inflation
cancels and the number means the same thing in every dimension — 3.1..4.9 on one blob whatever
`d`, 8..10 on two blobs 90° apart. Calibrated on a heavy-tailed null: at the 40-member floor a
gate of 6.0 falsely splits about **1 %** of single blobs, and 0 % by 80 members; below 40
members it is 12 %, which is what the floor is for.

`TYPE_SPLIT_SEPARATION = 6.0`, `TYPE_SPLIT_MIN_MEMBERS = 40`, `TYPE_SPLIT_MIN_SIDE = 8` (the
same floor `grow.MIN_NOVEL_CLUSTER` uses). Measured against the shipped **8-d** per-point
features — a lower bound, since 8-d folds some splits shut — it would split **317 knots**, 2.3 %
of all knots but **13.6 % of all points**, since these are the big ones.

The blob tuple now carries *why* it split, and the manifest separates `sourceSplitTypes` from
`bimodalSplitTypes`. Each centroid carries `blobRank` / `blobCount`.

### …and then the A/B said it does not do its job, so it is off by default

`learn` on `pipeline/out/harvest` finished in 25 minutes, not 3 hours — that store is **40
species / 675 types**, not the 2 423-species one v6 came from (that is almost certainly
`harvest-gan`, which is the only store carrying typing.json *and* embeddings.f32). It has no
`embeddings.f32`, so this is a descriptor-space build. But it exercises every line of the
change, and it made the control cheap. Two builds of one corpus:

```
split ON    k=742   58 types split   533 measured   18 torn   4 severe   median 2.289
split OFF   k=684    0 types split   493 measured   18 torn   4 severe   median 2.283
```

**The torn count did not move.** The diagnostic says why: of the 58 types the gate split, only
**4 were torn in the drawn 3-d positions at all**, and their median 3-d ratio was 2.38 against a
null of 2. It is firing almost entirely on types that are bimodal in the 28-d feature space and
**already drawn as one place** — adding 58 knots, and a claim of a distinction the picture
cannot show. That is the opposite of the thing it was built for.

The statistic is right and the calibration holds. The **targeting** is wrong: a type wants
splitting when it is bimodal in the features *and* torn in the projection, and on this corpus
those two sets are close to disjoint. Doing it properly means measuring per-type 3-d tearing
*before* choosing the partition, which inverts the build's clustering-then-projection order —
a real change, not a tweak.

So `--type-split` is **opt-in**, the default behaviour is byte-for-byte what it was, and the
measurement is in the constant's docstring where the next person will find it. The 317-knot
estimate from the 8-d shipped features still stands as an estimate of how often the gate
*fires*; this says nothing it fires on is worth drawing differently.

**This is the honest outcome of the ask rather than a failure to deliver it:** the gate is
built, calibrated, switchable and measured, and what it measured is that it should not be on.

## 3. The app could not have addressed a split knot, and that was a live landmine

`buildClusterLookup` kept the **first** cluster it saw per `(species, syllable)` and dropped the
rest. Harmless today — 0 of 13 748 types own two knots on this build — and it would have turned
the split into the previous round's bug with the sign flipped: the second blob drawn, never lit,
never labelled. Splitting without fixing this would have been strictly worse than not splitting.

Owner's call on what a second knot gets: **it lights and is tagged with the first; the thread
still runs through the primary.** A song is a sequence in time and a forked line would say the
bird sang one syllable in two places at once, while a lit-but-unnamed blob is the exact
complaint that started all of this. So:

- `allBySyllable` carries every knot, primary first, sorted on the build's own `blobRank`
  rather than on file order — a rebuild that reorders centroids cannot silently move which knot
  a thread runs through.
- `LivePath.companions` is per node, and both `applyScheduledPulses` and `pulseScheduledPoints`
  light them. They are written to `sung`, not merely `activations`: a split type's other knot is
  ground truth by exactly the same warrant, and the merely-resembling channel is drawn in a
  different colour.
- Tags come free — `NodeProjector` picks its candidates by scanning activations.
- `clusterIndexFor` is unchanged and still returns one place.

The lookup moved to `src/lib/data/cluster-lookup.ts` so a test could import it: `assets.ts` uses
a TypeScript parameter property, which node's strip-only mode refuses, and that is why the other
harnesses re-derive what they check. Re-deriving is fine for a rule with one reading and wrong
here — the bug is *in the lookup*, so a test that reimplements it would reproduce it.
`assets.ts` re-exports, so no importer changed.

## 4. Tests

- `npm run verify:split-knots` (new): both knots reachable, primary is rank 0 even when the
  array is out of order, a legacy build with no ranks still resolves, an unranked two-knot build
  falls back to the larger blob, companions stay attached to their own syllable when an unplaced
  one is dropped between them, and the shipped assets are self-consistent about rank/count.
- `galaxy.self_test` gains: a real two-lobed type splits, a *wide single* blob does not, a
  two-lobed type of 20 members does not, rank 0 is the larger side, `split_separation=inf`
  restores the old behaviour exactly; plus the chord metric's two exactness claims and a
  round-trip of both metrics through `grow.embed` — with the negative case, that the wrong
  metric really does move the points, so the round-trip is not vacuous.
- `verify --out` reports the match ramp and fails on an inverted one.

Found on the way and fixed: **`birdy-pipeline build --help` has been crashing**, on a single
unescaped `%` in one help string (`type coverage 100 %)`) among a dozen correctly doubled ones.
argparse only formats help when it prints it, so nobody had ever run it.

`npm run check` clean apart from the four pre-existing `syrinx-processor.js` errors;
`npm run build`, `verify:layout`, `verify:split-knots` (against the 58-split build as well as
the shipped one), `verify:trajectory`, `check-provenance-buffers`, `verify-inventory-shards`,
`galaxy.self_test`, `build --help` and pipeline `verify` all pass. The build's own `match ramp`
line and `verify`'s ramp check both fired on the new assets, which is the ramp round proven
end to end.

## 5. What I would do next

1. **Re-target the split gate, or drop it.** Bimodal-in-features and torn-in-3-d are close to
   disjoint; the gate wants the intersection, which means measuring per-type tearing before the
   partition is chosen. Until then it is off, and the A/B above is the reason.
2. **Re-derive the "genuinely torn" count** with the effect-size statistic, in the 32-d
   clustering space rather than the 8-d shadow. `tear_dims.py` needs the new statistic and a
   `--dump-points` matrix.
3. **Look at the ribbon threads in a browser** — the one thing in this session no test reaches.

# Lyrebird — the match ramp round (2026-08-03): the ramp ships with the assets it measures

The test round of 2026-08-02 ran `thresholds` for the first time and found that the browser's
match ramp had gone stale in silence. This closes it, and not by editing the two numbers.

**What was wrong.** `MATCH_FLOOR` 0.62 and `MATCH_CEILING` 0.86 were hand-tuned against a
2026-07 corpus whose real field syllables ran p5 0.605 · p50 0.801. By v6 the whole distribution
had moved up 0.07–0.14 — re-measured on the installed build, p5 **0.732** · p50 **0.873** — and
the constants had not. The floor sat below the **first** percentile, so it excluded nothing at
all, and the ceiling sat below the **median** real syllable, so more than half of all genuine
birdsong pegged the ramp at full strength. "A partial match should look partial, not certain"
had quietly stopped being true, and nothing caught it for a month, because a constant cannot
notice that its corpus was rebuilt.

## 1. The ramp is a property of the assets, so it now travels with them

`manifest.matchRamp`, written by every build and by `thresholds --write`, read by the app.
The rule rather than the numbers is what is fixed: **floor = p5, ceiling = p90** of how real
harvested field syllables score against *these* centroids. p5 keeps the floor's stated promise
(it lets in nineteen field syllables in twenty) and is where the hand-tuned floor sat in the
corpus it was tuned against; p90 is where a match is unambiguous by the corpus's own account.
On the installed build that is **0.732 .. 0.948**, and the median field syllable now reads
**72 %** strength instead of 100 %.

`MATCH_FLOOR`/`MATCH_CEILING` survive as the fallback for an asset set that ships no ramp, and
carry v6's measurement. `matchRamp()` refuses an inverted or degenerate pair — the app divides by
`ceiling − floor`, so an inverted one would invert the whole matcher and light the galaxy hardest
on the sounds least like a bird, silently. `verify` fails on the same condition and reports
absence without failing, since a build with no harvest store has nothing to measure.

## 2. Every downstream gate held, and that is the point of using percentiles

`strength` gates four other things, all tuned against the old ramp, and the obvious worry was
that retuning the ramp silently retunes all of them. Measured across the v5→v6 shift:

```
gate                 old cosine  old pct     new cosine  new pct
name a call (0.25)        0.698      19 %         0.802      21 %
wave claim (0.15)         0.679      15 %         0.784      16 %
tag claim (0.02)          0.640       9 %         0.750       8 %
panel shows (0.01)        0.634       8 %         0.744       7 %
```

Every one lands within two points of the **corpus share** it used to gate, because a threshold
on a percentile-anchored ramp is really a threshold on "what fraction of genuine birdsong clears
this". So `REPORT_STRENGTH` and the three shader gates are unchanged, deliberately, and the
table is in `translate.ts` where the next person will go to ask. With the ramp left as constants
it was the opposite: the same 0.25 went from naming 81 % of real syllables to naming all of them.

## 3. Not a regression, and it never was the cosine's job

White noise and room tone still score **0.967**, above the median real syllable, and still read
100 % on the ramp alone. The tonality gate is what rejects them and it is untouched:
`verify:features` measures both at flatness 0.848 and **strength 0.000**. The instrument now
prints the ramp's verdict on the probes next to the birds' so nobody re-hunts this.

## 4. Tools

- `thresholds` prints p1…p99 (it printed to p50, which cannot site a ceiling), marks which two
  the ramp uses, says what the median syllable reads, and takes `--write`.
- The measurement is one function, `measure_match_ramp`, run against the **finished asset
  directory** — so the build's pass and a by-hand run months later cannot disagree.
- `galaxy.write_manifest` is now the only manifest writer. Amending one with a plain
  `json.dumps` reflowed all 3 858 lines; one writer, one format, a 22-line diff.
- `verify:features` reads the shipped ramp instead of the constants, and says which it got.

`npm run check` is clean apart from the four pre-existing `syrinx-processor.js` errors;
`npm run build`, `verify:features` (30/44, exit 0) and pipeline `verify` all pass. **Not
re-run: the ramp at build time** — that path is exercised only by a full rebuild, which is the
next round's business.

# Lyrebird — the torn-knot round (2026-08-03): a knot is drawn in one place now

The report was *"very few times we see the red points somewhere where no activation was or
sound or anything"*, then, sharper: *"one note shines and we see it and then the second but no
label and no activation and no connection."*

It was not the renderer inventing points. It was **projection tearing**, which this build has
been measuring all along and nobody had read: `manifest.tearing` says **386 of 6 733 measurable
knots are drawn in two places at once**, 77 of them severely, worst gap **1.269 box units** on a
box whose half-width is 1. When such a knot is sung, `PointTracker.pulseCluster` lights every
member by cluster id with no reference to position, so **both** blobs go to the sung accent —
the red points — while the tag, the thread, the grid strike and the wave all read
`view.centroids[c]`, the arithmetic mean, which lands in the gap between the halves. One blob
gets the label, the other is lit with no label, no thread and no wave. 5.7 % of knots is "very
few times".

Two things it was **not**, both checked rather than assumed: orphan syllables (a scheduled note
whose type owns no knot would look identical, but `typeCoverage.share` is **1** and
`orphans` is empty — every scheduled syllable resolves), and a bad choice of projector (the
pipeline already bakes off umap/pca/cmds, and UMAP tore 95 of 166 against cMDS's 3 on the corpus
`torn_clusters`' docstring was written against).

## 1. Is a torn knot torn in the data, or only in its shadow?

Nobody had asked, because the tearing test only ever ran on the 3-d output.
`pipeline/analysis/tear_dims.py` (new) runs the same test on the shipped 8-d point features —
a PCA of the standardised 32-d critic space, rows unit-normalised — and on the 3-d positions,
over the same knots:

```
3-d   torn(>5): 385   severe(>8): 77   median 2.357
8-d   torn(>5): 210   severe(>8): 31   median 1.887

of the 385 torn in 3-d:  166 also torn in 8-d    219 whole in 8-d
plus 44 knots torn in 8-d but whole in 3-d — a real split the projection folds shut
```

The implication runs one way and that is enough: a separation surviving a *linear* projection to
8-d exists in 32-d too, so **166 (43 %) are genuinely two groups of sounds** and no arrangement
can honestly draw them as one place. **219 (57 %) are one group, torn by the squeeze into three
dimensions.** The field/synthetic seam explains none of it — only 2 of the 385 torn knots hold
both sources, and `clusterPlan.sourceSplitTypes` is 0.

## 2. The two-level layout (`localShapes` in layouts.ts)

**Where a knot is** stays the global projection's answer, but not its members' mean — that is
exactly the position that can fall in the void. It is the position of the knot's **feature
medoid**, the member closest to the knot's centre in feature space: the knot is drawn where the
projection put its most typical sound, which is always a real place.

**What a knot looks like** is now a 3-d principal-component projection of *that knot's own
members* in the 8-d space, laid out around that centre. The global fit never places a member,
so it cannot tear one.

The five dimensions the frame cannot show come back as **isotropic residue** — total scatter
minus what the three axes hold, as a step of that RMS length in a direction hashed from the
point's index, radius drawn uniformly through the ball. This is not decoration: without it the
top-3 frame keeps the largest separation and throws away most of the within-lobe spread, and the
tearing test scored **390** (worse than the projection's 379) purely because the denominator had
shrunk. A fixed-length step was the first attempt and drew every knot as a hollow shell.

Local coordinates are scaled by **one global constant** (median 3-d spread ÷ median feature
spread, 0.4258 on this build) so the corpus's median knot keeps exactly the extent it had. Inside
that, a knot's drawn size is proportional to its true feature spread — which is what extent was
always supposed to mean, and what a tear was inflating.

Measured on the shipped build, `npm run measure:layout` (new):

```
                    torn  severe  median ratio      widest split in one knot
projected            379      77         2.320      max 1.269   1590 knots > 0.5
two-level            245      37         2.003      max 0.802    913 knots > 0.5

knot extent   median 0.134 -> 0.1336    p10 0.0715 -> 0.0699    p90 0.2764 -> 0.2502
local pass    197 ms at load, 13 414 knots reshaped, 434 single-member skipped
```

Median ratio **2.003** against a null of 2.0 — the median knot is now one blob by the test's own
definition. The 245 that remain are the ones torn in the measurements; the honest repair for
those is upstream, in the clustering, not here.

**What this changes about the picture's claims**, and it is a change, so it is on screen. The
single global claim ("distance is acoustic distance everywhere") becomes two true ones: *knot
centres are the coarse acoustic arrangement; spread inside a knot is that knot's own variation.*
It loses less than it sounds — `knnAgreement` on this build is **0.0849**, so 8.5 % of a point's
ten nearest neighbours in 3-d shared its type, and what the global fit was saying inside a knot
was mostly residue. **Direction inside a knot carries no meaning between knots**; distance from
its centre does. Signs are pinned to the member reaching furthest along each axis, so a reload
draws the same knot.

`Display -> Local knot shape`, default on. It is read once when the cloud is built, so flipping
it remounts the canvas (`{#key `${galaxyVersion}:${localKnots}`}`) — the same path a map switch
takes. The switch exists so the two arrangements can be compared side by side rather than argued
about. The key's own note now says which of the three display transforms are running, and the
torn-knot note says what the layout does about it.

## 3. The hue floor was written and never taken off

Found on the way. `PointCloud` writes each knot's species hue into the cluster-state texture's A
channel as `HUE_FLOOR + (1 - HUE_FLOOR) * turns`, with the floor there so **0 can keep meaning
"this knot has no bird"**. The fragment read the value straight back as turns, so every knot's
accent sat up to **7.2°** around the circle from the hue the same bird's tag and thread are drawn
in — near-matching, which is the kind that reads as "the colours do not line up". `HUE_FLOOR` now
lives in `shaders.ts` and the fragment subtracts it before decoding, so the two sides cannot
drift.

## 4. Tests and tools

- `npm run verify:layout` gains a section on `localShapes`: a knot torn by the projection is
  repaired; a knot genuinely split in the features **stays** split (the layout may not hide a
  real finding, only stop the flattening inventing one); an untorn knot survives; extent follows
  the feature spread; the pass is deterministic; a build with no per-point features falls
  through. All pass.
- `npm run measure:layout` (`app/scripts/measure-layout.mjs`) is the before/after on a real
  asset root — re-run it after every rebuild, because the numbers above are this build's.
- `pipeline/analysis/tear_dims.py` is the 3-d-versus-8-d question, the one that decides whether a
  tear is the layout's problem or the clustering's.
- `stats.localKnots` carries what the pass did (reshaped / skipped / scale / ms).

## 5. Still open, pipeline side — not done

Both need a rebuild to land, so neither is in this round:

1. **Split the 166 genuinely-torn knots.** `_type_blobs` already splits a type in two when its
   blobs point further apart than cosine 0.9, but it only ever tests the field/synthetic seam,
   which explains none of these. The same gate on a type's own bimodality in 32-d would catch
   them, and then a knot is one place because it is one thing.
2. **Feed cMDS the metric the space actually has.** `projectionParams.negativeEigenvalueMass` is
   **0.408** — 41 % of the eigenvalue mass is negative, meaning the dissimilarity being fitted is
   not Euclidean-embeddable and classical MDS is fitting a space that cannot exist. The vectors
   are unit rows, so the chord distance `√(2 − 2·cos)` *is* the Euclidean distance between them
   and drives the negative mass to zero. The three kept axes currently hold 32.9 % of the
   variance; `--compare-projections` would say in one run whether the honest metric trades
   better.

`npm run check` is clean apart from the four pre-existing `syrinx-processor.js` errors;
`npm run build`, `npm run verify:layout` and `npm run measure:layout` all pass.

# Lyrebird — removal round (2026-08-02): the knot pins and the region place-names are gone

Both were added the same day, one round earlier (§3 and §2 below), and both are now removed on
the owner's call: *"we have knot pins as points in the pointcloud, that is wrong… the labels in
the pointcloud about the species, the small grey ones, also broke — get rid of them."*

**Knot pins** (`KnotMarkers.svelte`, deleted): one marker per membered knot, 13 848 of them,
drawn as a `T.Points` pass in the same group as the cloud. The switch added last round answered
"how do I remove them" but not the actual objection — a second point pass *inside the point
cloud* means the stage draws marks that are not sounds, and a reader cannot tell one kind from
the other at a glance. Threads and tags still terminate at the centroid; they now do it without
a mark under them. `PointCloud`'s `texture` bindable existed only to feed this pass and is gone
with it (the internal `clusterTexture` is unchanged — it still drives the points).

**Region place-names** (`buildPlaceNames`, `PlaceName`, `PLACE_NAME_MAX` in assets.ts;
NodeProjector's pass six; NodeLabels' `.place` pool): the small grey genus names over the
whole-galaxy view. The genus rewrite last round took them from one name to five, which was the
fix for "one tag called Marsh Tit", but they are out entirely rather than tuned again.
`NodeProjector` is back to five passes and no longer keeps a place clock.

The "Knot pins" checkbox is gone from Display; the key's knot entry no longer promises a pin.
`npm run check` is clean apart from the four pre-existing `syrinx-processor.js` errors, and
`npm run build` passes.

The two sections below are kept as written — they are the record of why these existed.

# Lyrebird — reading round (2026-08-02, night 5): room between the knots, regions named by clade, and what the unlabelled marks were

## 1. Twice the space between knots

`KNOT_GAP` 1.3 → **2.0** (owner: *"give the point cloud more space between the points —
sometimes knots and tones are so near each other that it looks like there is no animation
between them"*). The measurement behind it: on v6 the median knot's mean member distance is
0.129 against a median knot spacing of 0.0395, so **the average knot was 3.3× wider than the
gap to its neighbour** — the knots interpenetrated everywhere and there was no gap for a
response to happen *in*. At 2.0 the ratio is 2.1.

**The gap went up rather than the knots coming in**, though the two are arithmetically
identical for that ratio: this way each knot's extent — how tightly its members agree, which
is measured — is left exactly as the projection reported it (`CLUSTER_SPACING` in layouts.ts
has the long argument for why shrinking a knot is not available). Everything downstream
recomputes from the drawn layout: the wave's reach, the framing, the LOD grid, the ruler's
unit. It is one constant if the owner wants it dialled back toward 1.6.

It cannot make knots into beads and nothing short of a lie about the corpus could: the overlap
is a property of `label` clustering, where a knot is every sound carrying one type's name and
those sounds are under no obligation to land together in three dimensions.

## 2. "There is one tag called Marsh Tit — is that a bug?"

Not a bug, and not right either. Region place-names take a 6³ grid over the knots and name a
cell when one **species** holds 40 % of it. Measured on the shipped build: of the **35 cells**
that clear the 1 %-of-corpus gate, exactly **one** had such a species — `poecile_palustris` at
44 % — so the map printed a single name and read as broken. On a 2 423-species corpus a
species-level plurality is close to unobtainable by construction.

**Regions are now named by genus at a 30 % plurality**, which is the level this map can
actually speak at *and* the level the colours now speak at, so a region's name and the hue of
the birds in it say the same thing. Five regions qualify on this build (Poecile 48 %,
Sclateria, Hirundo, Larvivora, Colibri at 30–33 %); three were on screen in the check run.
The label is the genus capitalised — a clade takes the Latin the way a map takes a region's
name — and the share is carried on the record so a weak plurality can be said out loud.

**And no, they do not react to activation, by design.** A place-name is printed cartography:
it reprojects four times a second and holds one opacity. The instruments that answer are the
points, the pins and the tags; a map label flickering with the audio would be a fourth thing to
watch, saying nothing the knot under it is not already saying.

## 3. "I disabled all labels and there are still a lot of points — what are these?"

The **knot pins**: one small mark at each knot's drawn centre, 13 848 of them, drawn by
`KnotMarkers` — which was never gated on the Labels switch. They are where a tag and a thread
attach and they brighten when their knot answers, so they are not labels and should not ride
the labels toggle; but with the labels off they were the only thing on screen a viewer could
neither name nor remove.

**They now have their own switch** in Display ("Knot pins", default on) with the explanation on
hover.

## 4. The ruler's rules are gone

The band's border — a full-width line across the top of the stage and a matching one down the
left — read as a frame around the picture rather than as part of the scale. Removed; the ticks
are the scale.

# Lyrebird — the response round (2026-08-02, night 4): the wave, depth, taxonomy colour, and a shader that had silently died

Four owner asks in one pass, all checked in a browser.

## 1. The wave propagates, at last — the limiter was a rule that aged badly

`uWaveLocal` bounded every front at `4 × medianKnotSpacing`. That rule reads well and it
rotted: the spacing fell from 0.135 on the 149- and 1024-knot builds to **0.0395** on v6's
13 848, so the same line of code silently shrank the wave **3.4×** and a front died inside
0.16 box units — about **5 % of the cloud's radius**, and ~2 % of the opening view once the
framing fix brought the whole corpus into frame. Everything else about the wave (speed
0.55–1.45 box/s, 3.2 s life, 0.35 shell) was already scaled to cross the cloud; this one
envelope was strangling it.

**The reach now belongs to the space, not to the knot count: 30 % of the corpus's own
radius**, with the old knot-spacing rule kept as a floor so a small or tightly packed corpus
cannot get a front that swallows it. Displacement cap 0.06 → 0.10 box units in the same
breath ("stronger"). Owner's verdict on seeing it: *"wave works great."*

## 2. Depth

Two changes, both in the fragment/vertex stage, both cheap:

- **Perspective exponent 0.7 → 0.82.** At 0.7 the size range was compressed so hard that size
  had almost stopped being a depth cue, and after occlusion and parallax it is the strongest
  one this picture has. The floor and the 24 px ceiling still catch both extremes.
- **The aerial gradient now works from both ends.** It faded the far marks toward the paper
  (0.45, now 0.62) and did nothing to the near ones, so the contrast range the eye reads as
  depth was the back half only. The near marks now take a tenth of a step toward ink. Kept
  small deliberately: past that they start reading as *responding*, which is a claim this
  view has to keep for sound.

## 3. A bird's colour is now its genus

`speciesHue` hashed the whole species id, which spent the colour circle on 2 423 unrelated
numbers: two thrushes were as far apart as a thrush and an owl, so the one thing a colour
could have told you — **what kind of bird just answered** — was the one thing it did not.

The id is `genus_species`, so the clade is free, and on this corpus it is worth having:
**1 043 genera over 2 423 species, 75.5 % of species in a genus with at least one sibling**
(largest: *Turdus* at 34). Now: **hue is the genus, shade is the bird** — one hue per genus,
each species jittered up to ±14° inside that band with its own saturation between 74 % and
90 %. Everything downstream moved with it in one edit: tags, threads, knot pins, chips, the
per-knot response accent.

**The honest limit, and it is in the key on screen:** genus is the deepest taxonomy this
corpus holds. Family and order are not collected anywhere in the store or the inventory, so
"broader than a genus" cannot be coloured today — that is a harvest-side field, the same class
of one-field change as lat/lng (WORK QUEUE §11). And a genus hue is *arbitrary*: only the same
hue means anything, neighbouring hues are not neighbouring clades.

## 4. GridBurst: the colour kept, the styling reverted, and a shader that had silently died

- **Kept:** a strike is now struck in **the knot's own bird hue** in ink mode (the class colour
  in provenance, as before). It was a flat grey, which made the cross the one part of a
  response that said nothing about who sang while the wave, the points and the tag all did.
  Since the hue is now the genus, a cross also says roughly what kind of bird struck it.
- **Reverted on the owner's look:** the longer reach (2.4 half-heights), the finer dashes (120
  steps) and the slower taper. At that size the rule stopped reading as a struck line and
  started reading as graph paper. Back to 1.2 / 20 steps / the original fade, exactly as
  before.
- **A bug worth remembering:** the intermediate version named a GLSL variable `out`, which is a
  reserved word. The vertex shader then failed to compile and **the entire grid vanished with
  no visible error** — a dead `ShaderMaterial` draws nothing and reports only to the console,
  which is why it took the owner's console paste to find. `npm run check` cannot see inside a
  shader string; nothing in this repo can. That is one more argument for the browser smoke
  test in the test round above.

# Lyrebird — test round (2026-08-02, night 3): the suite is green, and `thresholds` says the match ramp is stale

**Everything that exists was run after the UI/renderer round, all green:**

| check | result |
|---|---|
| `npm run check` | 4 baseline errors (all `syrinx-processor.js`), 0 warnings |
| `npm run build` | green |
| `verify:layout` | all checks passed — grid 12 ms against the k² loop's 6 513 ms at k = 14 003 |
| `verify:synth` | **44/44**, median pitch error 0.3 % |
| `verify:features` | **exit 0** |
| `verify-parity` | **18/18**, worst difference 2.78e-08 |
| `verify-inventory-shards` | all assertions pass (index rows, stale-shard cleanup, app contract) |
| `check-provenance-buffers` | OK — 0 orphan syllables, 0 knots owning no points |

**One number in `verify:features` moved with v6 and is worth carrying:** exact syllable match is
**30/44 = 68.2 %** against the 50 % floor, where v5 measured 37/44 = 84.1 %. It passes, and the
drop is the corpus, not this work — nothing in this round touches the renderer's feature path.

## `thresholds` — one of the WORK QUEUE's four unrun tests, now run, and it found something

`uv run birdy-pipeline thresholds --out app/static/birdy --store out/harvest`, measured on the
**installed v6 assets** (2 000 of 39 930 field syllables):

| | v6 (now) | the constants were tuned against |
|---|---|---|
| p1 | 0.648 | 0.509 |
| p5 | 0.732 | 0.605 |
| p10 | 0.764 | 0.654 |
| p25 | 0.819 | 0.728 |
| p50 | **0.873** | 0.801 |

**The whole distribution moved up about 0.07–0.14, and `MATCH_CEILING` did not.** It is 0.86,
which used to sit above the median real syllable and now sits **below** it: on this build more
than half of all genuine birdsong pegs the ramp at full strength. The "a partial match should
look partial, not certain" behaviour the ramp was written for is largely gone — the Reading
panel's match percentage is now saturated for the median case. `MATCH_FLOOR` 0.62 is likewise
below the new p1, so it excludes nothing at all.

Suggested retune, **not applied** (these are tuned constants and the owner's call, and the app's
live matching changes the moment they move): floor ≈ 0.73 (the new p5, where 0.62 was the old
p5), ceiling ≈ 0.93. Better still, the ramp could be written into the build and read from the
manifest, since it is a property of the assets and drifts every time they are rebuilt — which
is exactly what happened here and what nothing caught.

**Not a bug, and the code already says so:** the same run scores white noise at 0.967 and room
tone at 0.967, above the median real syllable. `features.ts` documents this in full — the
cosine cannot separate noise on this corpus and the **tonality gate** is what does the work
(white noise 0.845 flatness against real syllables' 0.345 at p99). The session gate agrees:
`verify:features` flags white noise at 5.50 against a 3.95 threshold.

## What none of these tests can see

Every bug fixed in the two rounds above — the framing race that cropped the corpus to 40 %, the
ink-mode pins wearing species hue, the single global accent, the duplicated roster — was
invisible to all eight checks and was found by driving a headless browser. **The repo has one
renderer test (`verify:layout`) and no browser test at all.** A boot-and-assert smoke test would
have caught three of the four: no page errors, the opening view frames the whole corpus, the
resting ink-mode stage has no saturated pixels, the song dropdown solos and frames. It needs
Playwright as a devDependency and a Chromium download, which is a dependency decision rather
than a code one.

# Lyrebird — colour audit (2026-08-02, night 2): two real bugs behind "the colours are not aligning"

Owner: *"the points are coloured in ink mode — the not-active ones. Double-check the animation
colours, sometimes it seems it's not aligning correctly, maybe a bug?"* Both halves were real,
and they are different bugs.

## 1. Ink mode was drawing 13 848 species-coloured marks at rest — the knot pins

`KnotMarkers` colours each pin `mix(slate, identityHue, 0.25 + 0.75 × response)`, and in ink
mode the identity hue is the **species** hue. That rule was copied from the tags, which is a
pool of **28**; the pins are one per membered knot, **13 848 of them**. The same argument that
removed species hue from the *points* on 2026-08-01 ("a hundred hues on a dense scatter cannot
be told apart") applies here and was missed.

Measured on a headless capture of the resting ink-mode stage, silenced and with labels off:
**1.6 % of the stage's pixels came back saturated**, in the mode whose whole promise is that
nothing is coloured until it sounds — greens, blues and violets scattered through a grey cloud.

**Fixed:** a `uRestTint` uniform, 0 in ink and 0.25 in provenance. Ink-mode pins now rest in the
neutral slate and walk to their bird's hue only as the knot answers; provenance mode is
unchanged, because five class colours at rest is exactly what that mode is for. Re-measured
after the change: saturation > 20 fell 1.64 % → 1.00 % with the chorus running (the rest is
tags and live threads, which are meant to be coloured), and > 30 fell to **0.014 %** at rest —
the remaining chroma is the pins' own neutral slate.

## 2. The accent was one colour for the whole stage, so a chorus of five birds sang in one hue

`uAccent` is a single uniform, eased on the CPU toward the species hue of whichever knot won
`signal.best` that frame. One bird singing: correct. **A whole-aviary chorus sounds four or
five species at once, and every one of their knots lit in one bird's hue** — and during the
~0.25 s ease, in a blend belonging to neither. That is the "sometimes it does not line up"
report, and it was not a timing bug: the picture only had one accent colour to give.

**Fixed, and it cost no new attribute.** The cluster-state texture is RGBA and only RGB was in
use. **A now carries each knot's own species hue in turns**, written once at init (it is static
per knot) and preserved by the quiet gate, which zeroes only the three live channels. The
fragment converts it with the exact sRGB transfer function so a knot matches its own tag, and
falls back to the uniform when the hue is 0 (an unassigned point, or an older build). Provenance
mode keeps the uniform on purpose: there the accent is a *class* colour, and the class belongs
to the subject rather than to the knot.

Verified during a live global chorus: 4–6 distinct hue buckets present in the same frame
(210°, 330°, 240°, 300°, 270°, 180°), each matching its own tag — a crimson tanager, a cyan
robin and a blue dove lit at once, which was impossible before.

## 3. The panels now clear the ruler

One `--ruler` custom property on `.stage-wrap` (1.15 rem). The controls column, the display
buttons, the history strip, the panel max-heights and the ruler caption all inset by it plus
their own margin, and `Ruler` reads the same variable for its band size — so the frame moves
together and the panel can no longer sit on the scale.

## Not a bug, checked and recorded so nobody re-hunts it

- **The pin and the points genuinely do not coincide.** Both anchor on the drawn centroid, and
  on this build the centroid sits **1.1 knot-spacings from its own nearest member** (median).
  Tags, threads and waves all anchor there too, so they agree with each other and disagree with
  the cloud — by the corpus's geometry, not by a transform bug.
- **The two cluster-state texture grids match.** `PointCloud` and `KnotMarkers` size the
  texture by the same `min(1024, count)` / `ceil` rule, so a pin cannot be reading another
  knot's channels. This was the obvious candidate for "not aligning" and it is clean.

# Lyrebird — the galaxy audit (2026-08-02, night): what the animation says, what it does not say, and the framing bug that was hiding the corpus

Owner, on the screenshot of a selected bird: *"that's how the activation says — what is it? I
don't see the structure of the node, I don't know why the points move, why they move. All the
data animation should tell us something about the data."*

He is right on every count, and one of the three causes turned out to be a bug rather than a
design choice. Everything below is measured on the **installed v6 build** (348 461 points,
13 848 knots, `clustering: label`) — the geometry from `positions.f32` + `centroids.json`, the
projection figures from the manifest the build already writes.

## 0. The corpus's own unit, so the rest of this is readable

**One knot spacing = 0.0395 projection units** — the median nearest-neighbour distance between
drawn knot centres (`KNOT_GAP` 1.3 included). Everything below is quoted in it, and the new
stage ruler ticks in it. The corpus is roughly **80 knot-spacings across**.

## 1. THE BUG: the opening "whole galaxy" view was showing about 40 % of the corpus, and had been

`Spinner` eases its scale from **1** up to the opening **6.2** over about a second. `Framing`
fits the camera **on the first frame it sees a frame set**, reads the group's scale to turn the
reach into world units, then sets `snapped` and never refits — and its task is registered
*before* Spinner's. So the fit read scale 1 against a cloud about to become six times bigger,
the camera landed ~6× too close, and autoload — which *is* the whole-galaxy case — opened
**inside** the cloud.

Measured with the new ruler: **33 knot-spacings across, against a corpus about 80 wide.** No
margin anywhere, points to all four edges, so nothing on screen suggested anything was missing;
it read as "the galaxy is an even fog". `stats.viewRadii` said the same thing all along — 0.4,
i.e. inside the bounding sphere — and nothing was reading it.

**Fixed** in `Spinner.svelte`: `current` starts at the requested scale (`untrack`) and is
applied in an effect before any task runs; the ease still belongs to the distance slider. The
opening view is now **206 spacings across** and the galaxy has a shape — a dense core, an arm,
outliers — that was simply off-screen before. This is the single largest change to what the app
looks like in this whole round, and it was three lines.

**Consequences to know about.** Every LOD and blossom gate is quoted against `viewRadii`
(frontier 3.2 → 1.6, blossom 1.9 → 1.0, size floor 3.5 → 1.8), and that number just went from
0.4 to about 2.4 at rest. The opening view therefore now draws *fewer* points and *unblossomed*
knots — which is what those gates were written to do and what the framing bug had been
defeating. Worth an owner look: the thresholds have never been seen at their intended distances.

## 2. Why there is no visible knot structure — and it is not the renderer

| measured on v6 | value | in knot-spacings |
|---|---|---|
| median knot's mean member distance | 0.1286 | **3.3** |
| p90 knot | 0.2704 | **6.8** |
| centroid → its own nearest member (median) | 0.0436 | **1.1** |
| … p90 | 0.117 | 3.0 |
| members per knot | median 13, mean 25.2, max 1828 | 14.8 % have fewer than 5 |

**The average knot is over three times wider than the distance to the next knot.** They
interpenetrate everywhere. There are no beads to see, and no amount of point styling will
produce any: what the owner is looking at in that screenshot is the true arrangement.

Two reasons, both structural:

- **`label` clustering means a knot is a name, not a place.** Every sound goes to the knot of
  the type it already carries; the clustering never runs on it (docs/22 §22.8). A type's sounds
  are under no obligation to land together in three dimensions, and they do not.
- **The projection is weak locally.** The manifest's own numbers, written by every build and
  **never read by the app until this round**: distance faithfulness **r = 0.667**, and
  `knnAgreement` **0.085** — only 8.5 % of a point's ten on-screen neighbours share its type.
  Far above chance among 13 848 knots, and still nine neighbours in ten belong to something
  else.
- **386 of 6 733 measured knots are drawn in two places at once** (77 severely). Their centroid
  lands between the two blobs, which is exactly the "lines go to air" report — and it is a
  property of the flattening, not of the pin.

The centroid figure deserves its own line: **the pin sits farther from its own nearest member
than the next knot's centre is** (1.1 spacings against 1.0). `KnotMarkers` is drawing an honest
mark in genuinely empty space.

**None of this was anywhere in the interface.** The key said "a knot is a cluster of similar
sounds" and "distance is acoustic similarity" flatly. Both are now corrected and quoted from
the loaded build (see §5).

## 3. Every animated channel, and what it actually encodes

| channel | driven by | encodes | verdict |
|---|---|---|---|
| **idle drift** (`shaders.ts:497`) | `uTime` + per-point hash phase, 0.004 units | **nothing** | Always on. 0.1 spacings — under a pixel at galaxy distance, **~5 px of meaningless wobble zoomed in**. This is "why do the points move". |
| **rotation** (`Spinner`) | the Rotate toggle | nothing (a depth cue) | Fine, and now stated in the key as such. |
| **per-point pulse** (`shaders.ts:416`) | knot activation × mic level; **direction and phase are hash noise** | "this knot is active", weakly | The one bit it carries is already carried by size and colour. The direction says nothing. |
| **wavefront inside the knot** (`aFront`) | each member's **true distance** from where the sound landed | **real** — the knot's internal geometry, in arrival order | The best channel in the app. Also the least visible, because the knot is 3.3 spacings wide and the displacement is capped at ~1.1. |
| **travelling waves** (≤ 3, signed, interfering) | distance from the sounding knot; crossing fronts add and cancel | **real** | Reach is `4 × knot spacing` = 0.158 units. That was 12 % of the old (broken) opening view and is now **2 %** of the correct one. Effectively invisible at galaxy distance — the owner's "propagate further and stronger" is now *more* wanted, not less. |
| **blossom** (`aSpread`) | knot radius, as a display transform | radius-ish | Capped at 0.6 × spacing = **18 % of the knot's own spread**, so it is not what makes a selected bird look scattered. Measured before blaming it. |
| **size** (`shaders.ts:516-551`) | activation, level, front, ripple, learning, selection | **events only** | At rest, size carries exactly one bit of data: a sound in no knot is 35 % smaller. On this build there are **zero** such points, so at rest the size channel carries **nothing at all**. |
| **colour** | ink / provenance / accent | class, or who is sounding | Fine. |

So: of the motion on screen at rest, **all of it is decoration**; of the motion during a
response, the two channels that carry real structure are the two that are hardest to see.

## 4. The misses — data this project has measured and no channel shows

Ranked by how much they would repay, cheapest first within a tier.

1. **Members per knot.** Median 13, max 1828, and the two marks are identical. `count` is
   already in `centroids.json`. A knot pin scaled by log(count) would make the corpus's weight
   visible in one line of shader.
2. **Knot spread / cohesion.** `radius` and `cohesion` (0.85 median) ship per knot and are
   unused. A tight type and a type smeared across the projection look the same.
3. **`speciesMix` per knot.** Ships per knot, unused. A knot holding two species *is* the
   "sounds like" claim, at the level where it was measured, and it is invisible.
4. **`sources` per knot** (field vs synthesized mix) — ships, unused. The provenance colouring
   answers this per point and then a plurality per knot; the mix itself is thrown away.
5. **Tearing.** 386 knots drawn twice. Now stated in the key as a number; the *specific* knots
   are known to the build and could be marked, which would stop them being read as faults.
6. **`meanDuration` per knot** — ships, unused. Duration is the one acoustic property a viewer
   can hear and check against the picture.
7. **Novelty.** `novel` exists per point and only ever becomes a class colour. The novelty
   score itself (docs/13) never reaches the screen.
8. **Nothing shows time.** Recording date is in the store and unread (WORK QUEUE §10); there is
   no way to see the corpus grow, and `grow` was built to make it grow.

And one non-data miss worth its own line: **the activation has no legend and no scale.** A knot
lights, and nothing says whether that was a 40 % match or a 95 % one. The Reading panel has the
number; the galaxy does not.

## 5. What changed this round, besides the framing fix

- **Provenance colours is a checkbox**, sitting with Rotate and Labels, instead of a two-row
  radio group folded inside a `<details>` rollup — three clicks and a paragraph to flip a
  boolean.
- **The class list stops lying in ink mode.** It is both the visibility filter and the legend
  for the colouring; with the colouring off it was printing five class colours beside a cloud
  drawn entirely in neutral grey. The swatches now go hollow when the points are not wearing
  them, and the line under the heading says which of the two things the list currently is.
- **The key was audited against the code and the build, and three lines were wrong or absent.**
  "A knot is a cluster of similar sounds" is false on a `label` build and now reads from
  `manifest.clustering`; "distance is acoustic similarity" now quotes r = 0.67 and the 8 %
  neighbour agreement from the loaded manifest; **size** and **movement** had no entries at all
  and now have one each, including the plain statement that the resting drift means nothing.
  New lines: the knot-overlap ratio (3.3× on this build, computed live from `radius` and the
  measured knot spacing) and the tearing count.
- **A ruler along the top and left of the stage**, in knot spacings, with a caption that reacts
  to the zoom (`1 tick = 20 knot-spacings · 206 across · N % of points drawn`). `Scale.svelte`
  computes pixels-per-knot from the frustum at the view centre's depth and reports only when it
  moves by 0.5 %; `Ruler.svelte` draws DOM ticks under the floating panels. The projection has
  no meaningful origin, so the numbers count outward from the centre of the view, and the
  tooltip says so along with the "exact at the centre depth" caveat any perspective scale bar
  needs.

## 6. What I would do next, in order

1. **Make the wave's reach a share of the view, not a fixed 4 knot-spacings.** At the corrected
   opening distance it crosses 2 % of the screen. This is the owner's own ask from the previous
   round and the framing fix made it worse.
2. **Put weight on the knot pins** (log member count) and let them survive the LOD. That is the
   cheapest thing on this page that turns the cloud from a fog into a map.
3. **Kill the idle drift, or earn it.** If the cloud must move at rest, drive it with something
   — recording age, novelty, anything measured — or let it be still and leave the motion channel
   to mean "something is happening".
4. **Decide what a knot looks like.** A hull, a ring at `radius`, or a per-knot beeswarm as an
   opt-in display transform. Any of the three would make the structure the owner is looking for
   *visible*; none of them can make it *exist*, and the key now says so.
5. **Re-look at every `viewRadii` threshold** now that the number means what it was written to
   mean.

# Lyrebird — UI round (2026-08-02, later still): the owner's four open UI asks, all four done and all four checked in a browser

`npm run check` at the 4 baseline errors, 0 warnings; `npm run build` green; `verify:layout`
green; `verify:synth` 44/44 at 0.3 %. **Everything below was driven in a real browser**
(headless Chromium against `vite dev`, the shipped v6 assets) rather than reasoned about — the
last two rounds both shipped things that only a run could have caught, so each claim here has a
screenshot or a printed value behind it.

1. **The top "Now singing" roster is gone.** Markup, the `.roster` CSS, the `heardAt` map, its
   2 s prune `setInterval` and the Map rebuilt on every scheduled note all deleted. The history
   strip along the bottom is the same chip in the same shape and says *what* was sung as well as
   *who*, which the roster never did.
2. **`bout` is defined where it is first used.** One `BOUT_GLOSS` constant, so the wording
   cannot drift: the key now reads *"A thread links the knots of one **bout** — one burst of
   singing, syllables less than a second apart — in the order they were sung"*, with the full
   definition (including that transitions, motifs and song types are all counted *within* one)
   on hover, and the Compose census carries the same gloss inline. Where the word was
   incidental rather than technical it is simply gone — "the burst of singing ends here" in the
   grammar's end-probability tooltip, "mined from the recorded bursts of singing" for chunks,
   "our ordering" in the Guided tooltip. New `.term` style: marked, not emphasised.
3. **Knot counts are on the song labels.** Verified live on Lark Bunting:
   `learned bout · 3 knots`, `S01 · heard 32× · 2 knots`, `S03 · heard 9× · 1 knot`. **Distinct**
   knots, not sequence length — a song that returns to a syllable draws a thread back to the
   same knot, and counting it twice would promise two places to look. Unplaced syllables are
   absent, the same omission the trajectory makes; the tally beside the label still says how
   many were dropped.
4. **Choosing a call now claims the camera and, optionally, the chorus.**
   - *Focus.* `frameNodes` gained a branch between the pin and the bird: pick a call and the
     camera flies to its knots. Driven by a separate `songFocus`, **not** by `songId`, because
     the effect that repairs an invalid selection when the bird changes writes `songId` without
     meaning any of it — and `learned_bout` is a universal id, so a selection often stays
     *valid* across a change of bird. A `Frame this call` toggle does the same by hand and is
     the way back out. Verified: choosing the one-knot `S03` flies into a single knot; turning
     the toggle off flies back out to the whole repertoire.
   - *Solo.* `startAmbient` takes a `songIds` filter; `Only this call` pins the pool to it and
     starts the chorus if nothing is singing. It **overrides the confidence checkboxes** —
     naming a call is the more specific instruction, and having a class filter veto it would be
     a control silently overruling a stricter one. Verified by reading the history strip: 7 of
     7 songs scheduled after the toggle were `S02`, against `S03 / S02 / learned bout` before.
   - Both are released when the bird changes or the selection is cleared.
   - Found and fixed on the way: the class filter was passed at **one of three** solo-chorus
     start sites, so a checkbox only took effect at the next tempo change. All three now go
     through one `startSoloChorus`.
5. **"List every song" was already true, and the guard that could have made it false is gone.**
   `withDetectedSongs` folds `grammar.songTypes` into the dropdown and dropped any type heard
   fewer than twice. Measured over all 2 423 shards: 164 song types, **minimum count 6** — the
   pipeline mines nothing below `SONG_MIN_CLUSTER = 6`, so the guard was excluding nothing, and
   every type's syllables resolve (164 all-present, 0 partial). The guard is removed anyway and
   a once-heard type would now list itself as `S0n · heard once`: a weaker claim is not an
   absent one, and a chooser must not hide that an entry exists.

**Taste calls the owner may want to reverse, each one line:** the fly-to fires on *any* hand
change of the dropdown (not only on the toggle); choosing a call clears a pinned knot and a
history selection, because both outrank it in `frameNodes` and leaving them would make the
click do visibly nothing; `Only this call` starts a chorus rather than waiting for one.

# Lyrebird — UI round (2026-08-02, later): five fixes, two non-bugs, and what is still open

`npm run check` at the 4 baseline errors, 0 warnings, throughout.

**Fixed**

1. **The trajectory gradient was never broken — it was fed identical colours.** `rebuild()`
   already interpolates per vertex (`mixRgb(colA, colB, t)`, start knot at t=0, end knot at
   t=1). The fault was upstream in `knotPalettes`: ink mode handed **every** knot the same
   `#8595ae`, so the gradient blended slate into slate. Ink mode now uses each knot's own
   species hue with the same per-knot `knotHeat` shift the tags use, so two knots of one bird
   still differ along the thread. **The bead came free**: it is
   `mix(uColdColor, vColour, 0.35 + peak)` reading the same per-vertex colour.
   **Provenance mode still has the same flatness for a different reason** — 94 % of knots are
   the `recorded` class, so nearly every segment is green into green. Unfixed, and it needs a
   decision rather than a patch: either the class hue gets a per-knot shift, or threads keep
   speaking bird in both modes.
2. **The Display panel rendered the class list twice** — a read-only legend and the
   visibility filter, same five classes, same shares, stacked. Self-inflicted: the shares were
   added to the filter earlier in the session, which turned it into a second legend. The
   read-only copy is gone; the filter *is* the legend. Took `.legend b` and `.legend li.absent`
   dead with it (caught by `npm run check`, removed).
3. **The reading panel could show a stale name.** `heldReading` keeps a match readable for
   6 s after its sound stops, and it was **only ever cleared on reload** — so during a chorus
   the panel could keep showing the *previous* song's match while a new one was already
   sounding. Now `onScheduled` calls `releaseHeldReading()`: the moment something else is
   scheduled, the last thing we heard is no longer the last thing we heard. The live reading is
   untouched; if the matcher cannot place the new song the panel goes quiet, which is the
   honest answer rather than another bird's name.
4. **Knot markers were below the visual threshold** — 1.5 px / 0.30 alpha, so threads landed
   on an anchor nobody could see. Now 2.4 px / 0.50, still under the cloud's 2–3 px so the
   "waypoint, not data" ordering holds.
5. **The activation dim is local.** It rode `uAnswer` globally, so one syllable restyled the
   whole galaxy. It now rides `vWave` and follows the front outward from the knot that
   sounded, with a 0.25 floor so a response is still felt corpus-wide.

**Two things that turned out NOT to be bugs — do not re-hunt**

- **"Songs always land on the same node."** They do, and correctly. For
  `horornis_diphone` the three dropdown entries are `ho → ho2 → kyo` (**3 knots**),
  `learned_bout = ['L02','L02']` (**1 knot**), and `S01 = ['L02']` (**1 knot**, `kind=repeat`,
  `count=6`). A **repeat class is by definition one collapsed token**, and `_sample_bout` drew
  L02 twice because uguisu's transition table has a strong self-loop. All 17 uguisu types own
  a knot (5771–5787), authored ones included, so resolution is clean. Common corpus-wide —
  the v6 learn log is full of `example bout L01 L01`.
- **The `sung` channel is correctly wired.** `applyScheduledPulses` runs every frame
  (`listener.ts:422`) and writes both `activations[node]` and `sung[node]` for every node of
  every live path with a time-windowed pulse. Nodes along a song *do* light. The owner saw one
  node because both songs tested touch one knot.

**Why the cloud is slow, measured (owner asked "what do we do inherently wrong")**

**Fill, not point count.** 14 floats/vertex × 348 461 points = **~20 MB of vertex fetch per
pass**; against roughly **45 M blended fragments a frame** (~22× overdraw at 1080p) across two
passes. `transparent` + `depthWrite:false` + NormalBlending means **no early-Z and every
fragment is a framebuffer read-modify-write**. That blending is *not* a mistake — additive on
white dissolves the cloud, and normal blending is what makes density read as darkness — so the
honest summary is: **the most expensive rasterisation mode, chosen for good reasons, run on the
weakest available GPU.**

- **Done:** an early `discard` for fragments whose alpha falls below 1/255 after the
  seven-multiply chain. Below that the blend is a **no-op**, so this is not an approximation,
  and a dimmed corpus is the state the galaxy spends most of its time in.
- **Rejected, with reasons.** *Attribute packing*: `aMisc` is **already** four packed channels
  behind `#define`s (an early grep of mine called it dead — it is not, and it was checked
  before anything was deleted). The remaining win is ~2 floats against a cost that fill
  outweighs 2:1 — wrong trade for a refactor touching every writer with no browser to test in.
  *Dropping the 24 px size ceiling*: quadratic in fill and tempting, but it only binds close to
  the camera, which is exactly "inside a bird" where the owner asked for **more** presence. It
  would fight the stated goal. *WebGPU*: owner ruled it out as experimental; it is also a
  rewrite.
- **Still the biggest single win and not a code change: run the browser on the RTX.**

**STILL OPEN — the owner asked for these and they are not done**

- **The four UI asks that were listed here are done** — see the section above this one
  (2026-08-02, later still). What is left of the list is below.
- Everything in the WORK QUEUE below (spaces, map-agreement regression, the four unrun pipeline
  tests, the UI sweep whose agents all died on a provider quota error).

# Lyrebird — WORK QUEUE (owner round, 2026-08-02) — read this before touching the galaxy

**v6 IS NOW INSTALLED** (this supersedes the "parked" entry below, which is kept for its
measurements). `app/static/birdy` = 348 461 points, **13 848 clusters**, built
2026-08-02T09:27; `data/learned-inventory.json` = 13 748 syllables. Owner accepted the
song-layer trade with the measurement in hand. v5 is in git, which is where a revert comes
from. Whole suite green: parity **18/18** at 2.78e-08, synth **44/44** at
0.3 %, `verify:features` exit 0, shards + provenance buffers OK, pipeline `verify` clean,
`npm run check` at the 4 baseline errors. One thing improved: field-knot in-manifold
agreement **3.17 → 2.95** median, 74.7 % → **84.8 %** under threshold.

## THREE OF THE OWNER'S ASKS ALREADY EXIST — tune, do not rebuild

Checked in the source before writing this. Whoever picks this up should **look at the running
app first**, because the gap may be visibility rather than absence.

1. **"Centroids mostly don't have a point in the middle, lines go to air."**
   `KnotMarkers.svelte` **already does exactly this** — one marker per membered knot at the
   drawn centre, and its own docstring says *"it reacts to everything its knot reacts to"*
   via the shared `clusterState` texture (R activation / G sung / B learn), no second state
   channel. **So this is a visibility problem, not a missing feature**: rest is a 1.5 px
   floor at 0.35 alpha against the cloud's 2–3 px at ~0.5, deliberately "a waypoint, not
   data". The owner cannot see it. **Action: raise its resting presence until a thread
   visibly lands on something**, and check the thread endpoints actually terminate on the
   marker rather than near it.
2. **"Inside a single bird, show its full point cloud."** Partly there: `vChosen` exists,
   the chosen species is exempt from the frontier and the governor, and its knots are force-
   blossomed (`aSpread * max(uBlossom, vChosen)`). **Action: verify the LOD too** — a focused
   species must draw *every* one of its points at *every* camera distance, not just be
   blossomed. Check `updateLod`'s focus branch actually unions the whole species in.
3. **"Localised activation instead of the whole cloud densifying."** The reveal mechanism
   exists (`REVEAL_FRONT = 0.015` in `shaders.ts`, third inclusion channel in
   `updateActiveIndex`, `stats.pointsRevealed`). What is still global is the **resting dim**:
   `uAnswer` dims the entire cloud whenever anything answers. **Action: make the reveal the
   only densification and drop or localise the global `uAnswer` dim**, then widen the front —
   owner wants it to *propagate further and stronger*, and to reveal the full local cloud
   where it passes. Treat it as a 3-D travelling front like `GridBurst`, which is the model
   the owner named.

## THE REST OF THE OWNER'S LIST — not built

4. **The cloud is hard to read.** Owner: *"we can't read much out of it."* Two named
   sub-asks: **place the knots more distinctly** (they read as one mass), and make the
   **song lines legible** — they are currently hard to see at all.
5. **The travelling dot on a song line has a colour-gradient bug**: *"sometimes it doesn't
   have the same colour gradient between the 2 points it wants to connect."* Look at the
   bead's vertex colours in `Trajectory.svelte` against the two endpoint knots' hues — most
   likely the bead interpolates in a different space, or against a stale endpoint, than the
   line it rides.
6. **A song playing should animate its line, and that wants refining.** Currently the
   animation is (at most) the bead; owner wants the line itself to respond.

## SPACES THAT EXIST AND ARE IDLE — the research opportunity, owner-confirmed

7. **Perch 2.0's 1536-d embedding as a *second opinion on novelty*.** The extraction is
   already shipped (`perch.label_novel(keep_embeddings=True)`) and **docs/13 §A1
   pre-registered the exact question** — "does Perch's space agree this is novel?" — and it
   was never implemented as a signal. W6 is why it is interesting: Perch retrieves species
   **8×** better than our critic, and the two external models **disagree with each other more
   than either differs from ours**. So **cross-space disagreement is itself the new
   information**: "critic says novel, Perch says familiar" flags one kind of interesting, the
   reverse flags another. Owner also asks directly: **test whether Perch or our approach is
   better** — note W6's honest limit, the critic is a *syllable* space averaged over a
   recording, so any comparison must be per-recording or it is unfair.
8. **The song-level novelty pool nobody consumes**: docs/12 clusters bouts into song types and
   **1 726 bouts were heard exactly once** and sit unused. `grow`'s novelty answer is
   syllable-level only.
9. **The 28-d vs 32-d disagreement is unexploited** — measured at ~0.49 centroid agreement
   (docs/20). Same syllable, two opinions, and the disagreement is thrown away.
10. **Metadata already in the store and never read.** The recordist's own call-type label
    ("song" / "alarm call") is discarded unread — `harvest.py:1170` even calls it *"the
    cheapest available route to labelling what a call does"*. Also unused: co-singing
    species, country, date, sex, stage, playbackUsed.
11. **lat/lng is not collected at all** — a one-field harvest change opens the
    dialect/geography axis (docs/18 P4, sketched and unbuilt; the whitepaper notes the corpus
    now has the depth for it).
12. **Standing caveat on every new space**: the recorder confound (W1/W6, docs/23). Even
    Perch's archive-scale space carries five sixths of our recordist structure.

## OPEN MEASUREMENTS

13. **Map agreement fell again on v6 and I have no mechanism for it.** Region agreement
    **0.4909 → 0.3977**, species **0.5619 → 0.5094**, tie-adjusted 0.7056 → 0.6785. The v5
    explanation (more knots, harder nearest-centroid lookup) **is contradicted** — v6 has
    *fewer* knots (13 848 vs 14 003), so the lookup should be marginally easier. Something in
    the re-typing moved the descriptor→embedding relationship. Needs measuring, not guessing.
14. **Four pipeline tests exist and none has been run.** `specbench` is the valuable one —
    it renders fitted types against cached audio on MCD / multi-res STFT and is **the only
    instrument in the project that speaks to audible fidelity**, which every cosine number in
    this session explicitly does not. Then `placement` (docs/09's four numbers, direct v5-v6
    comparison), `syntax` (would quantify the song-layer cost properly instead of counting
    repeat classes), and `thresholds` (re-measures the browser's match ramp — the assets just
    changed underneath it).

# Lyrebird — Session Handoff (2026-08-02: v6 built, and a UI sweep is owed)

**v6 is built, verified green by the build's own checks, and DELIBERATELY NOT INSTALLED.**
It lives at `/tmp/birdy-prod/v6/` (assets + `learned-v6.json`). `app/static/birdy` and
`data/learned-inventory.json` are untouched and still the **v5** build. The reason for
parking is one number, below.

**What v6 is.** `pipeline/analysis/run_production_v6.sh` — learn (two-start) -> docrefit ->
respfit -> build -> verify, run unattended. Learn 08:02-11:01 (**2 h 59 m**), docrefit 23 s,
respfit 7 m 45 s, build 21 min. 348 461 points, **13 848 clusters**, type coverage
13 748/13 748 = 100 %, all the build's own checks passed.

**What it gains, all measured:**

| | v5 (installed) | v6 (parked) |
|---|---|---|
| median resynthesis cosine | 0.6477 | **0.6790 (+0.0313)** |
| documented calls with measured texture | **0 of 44** | **9 of 44** |
| types carrying respiration | **0** | **186** |
| types carrying two-voice | 3 471 | 3 749 |
| relations.json | 5.6 MB (hand-trimmed) | **3.7 MB (pipeline-trimmed)** |

The +0.0313 essentially reproduces the debug gate's +0.0330 over 13 704 types, so **the
two-start's gain holds at production scale**. The encoder basin won a steady **51 %** of
types across the whole run, identical to debug.

**WHY IT IS PARKED — the song layer lost half its content.**

| | v5 | v6 |
|---|---|---|
| species with song types | **98** | **68** |
| repeat classes | **260** | **82** |
| motifs | 96 | 82 |
| grammar chunks | **5 593** | **1 272** |

Repeat classes fell **68 %** and chunks **77 %**. That is not drift: repeat classes are an
*adopted* result (docs/22 §22.2) recorded as taking species-with-a-song **48 -> 98** with the
shuffle control unmoved at 0.170 %. v6 lands at 68, most of the way back to the pre-adoption
baseline. **Installing v6 would trade a syntax headline for a synthesis one**, and this
project does not get to do that quietly.

**MEASURED, and it is not a bug: the fit objective trades against the syntax layer.**

Run through the pipeline's own `bout_sequences` / `_collapse_runs` against v6's typing, over
all 44 species that lost every repeat class. **Every one is genuinely under the bar** —
`SONG_MIN_CLUSTER = 6`, and their best collapsed string is seen:

| times seen | species | |
|---|---|---|
| 5 | 7 | **one short of the bar** |
| 4 | 11 | |
| 3 | 12 | |
| 2 | 9 | |
| 0–1 | 5 | structure genuinely gone |

**41 % (18 of 44) are within two of the threshold.** The detector is behaving exactly as
specified; nothing is misfiring.

**The mechanism is confirmed by the type counts.** Those 44 species gained types — **mean
+2.1** — against **−0.06 across all 2 423**. More types split the same physical repeat across
different ids: a bout that collapsed to `('L17',)` six times now collapses to `('L17',)` four
times and `('L23',)` twice, neither clears 6, and the class vanishes.

**So the finding is a real property of the project, not an accident of this run: the
syllable-level objective and the sequence-level structure are not aligned.** The two-start
made the fits measurably better (+0.0313 median cosine, gate-passing, never worse per type)
and that better typing is a *worse* typing for finding repeats, because finer distinctions
fracture the runs repeat detection depends on. **Nothing in the pipeline measures this
trade** — the two-start's gate reads resynthesis cosine and cannot see the song funnel
narrowing behind it. Any future change to typing should be scored on the song funnel as well
as on the cosine, and there is currently no gate that does it.

The cheap follow-up, *not* taken: re-run song detection alone against v6's typing at
`SONG_MIN_CLUSTER = 5` to see whether the structure is fractured or gone. It is minutes and
needs no refit — but it is exactly the threshold-lowering docs/12 warns against, since the
constant is pinned at 6 by a permutation control (at 4 the control chains 103 spurious bouts
into 17 spurious types; at 6 it finds one type over 0.2 % of bouts). Read the control before
touching the number.

The re-typing itself was clean: the sweep re-chose for **301 of 2 423 species** (87 up to
+50 types, 214 down to −56, net −155 = 1.1 %), **no species dropped or added, zero duplicate
ids**.

**Two script bugs found by running it, both mine, both fixed in the script:**

1. **`learn --inventory` doubled the inventory.** `cmd_learn` ends with
   `write_learned_inventory(out, merge_learned_inventory(inventory, document))` — the flag is
   **merged back into the fit** to preserve the hand-authored calls, and it wants the
   *authored* `data/inventory.json` (12 species, 44 syllables). The first v6 attempt passed
   `data/learned-inventory.json` (2 423 species, **13 859 fitted types**), so every fitted
   type was folded in as though a person had written it: 13 903 -> **27 607** syllables,
   `hirundo_rustica` at 16 with five ids twice over. The help text ("used for species names
   and citations, never overwritten") is true and incomplete. **Omit the flag** — the default
   is the authored file and it is what arms A-D used.
2. **The build's 9-hour stage was the permutation battery.** The first attempt omitted
   `--no-relations`, which skips "the permutation tests that say which groupings the geometry
   corresponds to". It ran 9 h at 268 % CPU and was not hung. `relations.json` is still
   written either way.
3. **`verify --assets` is not a flag** — it is `verify --out`. The chain's stage 5 reported
   `FAILED at verify` for that reason alone. Fixed in the script, and **verify has since been
   run by hand on the v6 assets: all checks passed** — 348 461 points, 13 848 clusters,
   point-features mean cosine 0.838 to own centroid against 0.068 to all, calibration
   monotonic over 100 % of measured beta steps, contract 8.6 worst error 0.03 % F0. So v6 is
   a complete and verified artefact that is parked on the song number, not a broken one.
   One projection figure moved and is worth carrying: distance faithfulness pearson
   **0.667 against v5's 0.691**.

**A UI BUG SWEEP IS OWED, and the agent swarm that was doing it died mid-flight.**

Eight audit agents were dispatched across the app and **all eight failed on a provider quota
error** (`403 usage limit for this billing cycle`) before returning anything. Nothing was
audited. The territories they were given are the right ones and are worth re-running when
quota allows:

- `+page.svelte` **1-1400** (script): state written-but-never-read, effects with stale
  closures or re-running more than intended, async races where `loadSpecies`/`setChorus`/
  `sing*` resolve after the state moved, diverged duplicate logic, dead handlers.
- `+page.svelte` **1400-4469** (markup + styles): dead markup, CSS classes defined-but-unused
  and used-but-undefined, unreachable branches, and **orphaned copy describing features that
  no longer exist — bird mode was removed from the points, so hunt its leftovers**.
- `PointCloud.svelte` + `shaders.ts` + `palette.ts`: leftovers from the day's many reworks
  (`uMorph`, `aTarget`, `aBird`, `uBird`, `vBird`, `lodLevels`, hysteresis), uniforms declared
  but never written or read, unused varyings, GLSL dead branches, stats fields written but
  never displayed, double work across `updateLod`/`updateActiveIndex`/`updateFronts`, and
  **who disposes the shared cluster texture `KnotMarkers` borrows**.
- The rest of `galaxy/`: props declared but never passed (and passed but never used),
  per-frame allocations inside `useTask`, effects missing cleanup, **label-pool `bound`/`slots`
  desync**, unused exports in `layouts.ts`/`stats.ts`.
- `data/`: fetch/cache races, endianness and typed-array view bugs on the `.f32` readers,
  shard-vs-whole-file divergence, error paths that leave assets half-initialised.
- `audio/`: timer leaks, worklet message races, scheduler edge cases (tempo 0, empty species),
  `startAmbient` while already running, `stopAmbient` leaving state in flight.
- `lang/` + `PipelineClient`: dead exports, token/gap off-by-ones, polling leaks.

Known already from this session and worth folding into that sweep: the memberless-knot
`(0,0,0)` invariant is still unguarded in `ContextPaths`, `Trajectory` and `NodeProjector`;
and `centroids.json` ships a prose `note` carrying a stale "44 MB" figure.

# Birdy — Session Handoff (2026-08-01, late 5: knot pins, focus cloud, wave reveal)

**Owner round on the pointcloud's readability, all app-side, checks green** (4
baseline / 0 warnings, parity 18/18, layout, build). Owner confirmed the
pipeline-side research queue (Perch cross-check, song-bout pool, recordist
call-types, lat/lng) — unpicked, debug-subset discipline when it starts.

- **Knot centre pins** (`KnotMarkers.svelte`, new): one small marker per membered
  knot at the drawn centroid, driven by the *same* cluster-state texture as the
  cloud (R/G/B, same weights), so pins brighten with response, sung and learning
  and go quiet with the gate. Rest: 1.5 px floor, alpha 0.30, slate with 25 % of
  the knot's identity hue. Relation threads and labels no longer land on empty
  space. Own tiny program (3 attributes; the cloud stays at 10).
- **Selected bird = full cloud, verified and made decisive.** No coverage bug:
  `reorderCells`' species test already covers unclustered points, and the focused
  span is exempt from frontier AND governor (now documented). New: the selected
  bird's knots are always fully blossomed (`aSpread * max(uBlossom, vChosen)`),
  its marks get a light fog exemption (×(1−0.4·vChosen)) and skip the uAnswer
  resting dim. Unclustered points keep their shrink — a structure claim, not a
  selection one.
- **Wave reveal.** The travelling front now reveals the full local membership:
  `REVEAL_FRONT = 0.015` (exported from shaders.ts so CPU scan and GLSL share it)
  adds a third inclusion channel to `updateActiveIndex`; the reveal band
  (vWave ∈ [0.015, 0.05), vAct < 0.25) renders at 0.38 alpha, resting tone, no
  accent — density appearing, not answers. `FRONT_WIDTH` 0.16 → 0.22, front amp
  floor 0.3 → 0.45 (scales with how much of the knot answered). New
  `stats.pointsRevealed`, shown in the cost readout as "· N revealed". Watch it on
  the iGPU during chorus: the active pass is deliberately not LOD-bounded.

# Birdy — Session Handoff (2026-08-01, late 4: relations, roster, place-names; spaces research)

**Four sense-making features shipped, plus the owner's "how do we find new songs"
research answered.** Checks green throughout (4 baseline errors, 0 warnings, parity
18/18, layout, build). Owner visual pass owed.

- **Provenance verdict, measured on the shipped corpus:** points 93.9 % field / 3.7 %
  candidate / 2.4 % documented / 0 % learned / 0 % unlabelled; knots 99.0 % field
  plurality; NN same-class 91.5 % vs 88.2 % from base rates — the spatial colouring
  carries ~3 points of information. The ink/provenance switch is now demoted into a
  "provenance colours" rollup with that honesty line; the discovery isolate keeps the
  classes top-level.
- **Relation threads + "Sounds like" chips.** `assets.relationPartners()` resolves
  relations.json's 9 513 shared-type pairs to knot↔knot pairs (1:1 on the label
  build). `RelationThreads.svelte` draws up to 64 hairlines from the selected bird's
  knots to partner knots (neutral → partner hue), rebuilt on selection only; partner
  knots join the label pool at low priority via a new `related` prop on NodeProjector.
  Sing tab shows ≤ 6 partner chips in species hues with the honest definition
  ("nearer than two types of one bird usually are — a distance, not kinship").
- **"Now singing" roster.** Chips of the species heard in the last 10 s
  (`engine.onScheduled` → `heardAt` map, 2 s prune tick), newest first, click to fly
  to the bird. Above the history lane.
- **Region place-names.** 6×6×6 grid over the knots; a cell ≥ 1 % of points with a
  ≥ 40 % plurality species gets its bird's name as a quiet map-style label
  (`buildPlaceNames`, cap 12), projected at ≤ 0.25 s cadence only when nothing is
  selected and viewRadii ≥ 2.2 (new `stats.viewRadii`). Separate pool from the tags.
- **Research answer (for the next round, nothing built):** novelty today is geometry
  in ONE space — cosine distance in the critic's 32-d embedding to per-type centroids
  (5 % FPR threshold; species-level AUC only 0.596, "a research problem, not a tuning
  one"). Idle spaces/information: Perch's 1536-d (extraction already in
  `perch.label_novel(keep_embeddings=True)`; docs/13 §A1 pre-registered "does Perch
  agree this is novel?"; W6: external models disagree with each other more than
  either differs from ours → cross-space disagreement is itself signal), the 1 726
  singleton bouts (song-level novelty pool, docs/12 §12.4, unconsumed), the 28-d vs
  32-d disagreement (~0.49 centroid agreement, docs/20), and never-used store
  metadata: recordist call-`type` labels (harvest.py:1170 calls them the cheapest
  route to functional labels), `also`, country, date, sex, stage. **lat/lng is not
  collected** — a one-field harvest change opens the dialect axis (docs/18 P4).
  Caveat for any new space: recorder confound (docs/23 W1/W6). Songs are already
  connected three ways (measured grammar, song types, shared types across species);
  a visible "what comes next" ghost-thread from the sounding knot along the measured
  transitions is the natural next build.

# Birdy — Session Handoff (2026-08-01, late 3: adaptive density, knot spacing, bird mode out)

**Owner round 3 on the galaxy: mid-zoom fps still tanked, knots too tight, bird
colouring "useless".** All three addressed app-side; checks green (4 baseline errors,
0 warnings, parity 18/18, layout, build). Owner visual pass owed on all of it.

- **Adaptive density governor.** The frontier's ceiling is now driven by measured
  frame time: >20 ms sinks the cap fast (delta×0.8), <13 ms recovers slowly
  (delta×0.15), clamp [0.10, 1]; effective fraction = min(shownFraction, cap), so
  throttling *dissolves* through the aRank fade instead of popping. Seeds at 0.55 when
  the renderer string says Intel-non-Arc. `stats.densityCap` feeds a cost-readout row
  ("held at NN% for framerate", shown only when < 0.99) and a Display-panel
  "adaptive detail" toggle (default on; off pins cap 1). This cannot tank by
  construction — density thins toward the priority order, i.e. toward structure.
- **Spacing.** `KNOT_GAP = 1.3` in layouts.ts (`separateKnots`: p → c·1.3 + (p−c),
  unclustered points untouched, centroids recompute so everything downstream —
  waves, framing, uWaveLocal, LOD grid — reads the expanded geometry; required a
  bounding-sphere recompute in PointCloud's layout-seed block). Blossom widened:
  target 1.35× knot radius, cap 0.6× median knot spacing. The key note discloses both
  display transforms.
- **Bird mode removed from the points.** The cloud now speaks ink or provenance only;
  `aBird` is gone — **the program is down to 10 attributes** (15 before the Mesa fix).
  The ink-mode accent is now the **responding bird's species hue** (FNV hash, same as
  the tags) instead of the universal violet — violet only when nothing names a who.
  Tags carry the species hue whenever provenance is off (NodeLabels, NodeProjector
  `--accent`), so tag and cloud accent agree. Threads (ContextPaths, Trajectory) lost
  their species palettes with the mode. Taste knobs for the owner: the 20/13 ms
  governor band, KNOT_GAP 1.3, blossom 1.35/0.6.

# Birdy — Session Handoff (2026-08-01, late 2: cloud visuals — blossom, ring-down, haze)

**Owner asked for visual enhancement of the point cloud: spacing, lab-style finish,
better animations/activations.** All implemented app-side; `npm run check` at the 4
baseline errors, `verify-parity` 18/18, `verify:layout` green (last two run before the
tracker/gate edits; the shader work was checked after each step). **Owner visual pass
still owed** — every piece reverts independently if the taste read disagrees.

- **Knot blossom (the spacing fix).** New static attribute `aSpread`: each point gets a
  deterministic target radius inside its knot (`sqrt(hash) × knotRadius × 1.1`, uniform
  over the disc, capped at 0.5 × median knot spacing, rim points barely move).
  `p += aRadDir * (aFront*aBloom + aSpread*uBlossom)` — one shared multiply in the
  vertex shader. `uBlossom` opens 1.9 → 1.0 cloud radii: knots are compact structure at
  galaxy distance and blossom into separated individuals on approach (beeswarm/Gaia-sky
  reference). Corpus positions untouched; the "Reading the galaxy" key discloses the
  display jitter.
- **Ring-down afterglow (the animation fix).** The trackers' release was 32–58 ms — marks
  snapped off. Now: `PointTracker.update` runs an asymmetric EMA (attack 0.7, release
  0.97 ≈ 0.4 s half-life) and `ActivationTracker.decay` releases activations at 0.97
  while `strength` keeps the pace-aware fast fall (it gates `best()`/HUD). The 9 Hz
  response buzz is a 0.4 Hz swell (`sin(uTime*9.0)` → `2.6`, displacement 0.007 →
  0.004) — the wavefront owns the attack, a held note breathes. **The quiet gate got a
  settle window** (`QUIET_SETTLE_FRAMES = 90`): uploads continue ~1.5 s into silence so
  the ring-down reaches ~0.02 before the freeze zero-fills; idle silence still uploads
  nothing, and chorus gaps under ~2 s no longer blink.
- **Lab finish.** Distance-dependent size floor: `mix(2.0, 3.0, uNearFloor)` (3.5 → 1.8
  radii) — distant knots render as finer haze, which is also less iGPU fill; the crisp
  3 px disc returns on approach, responders keep their `+vAct*2.0` rise. Subtle CSS
  vignette on `.stage` (radial-gradient layer in the existing background stack, 4 %
  ink at the corners, hairline grid untouched).
- **Mesa attribute overflow, found by the owner's first run and fixed same day.**
  `aSpread` was the 15th vertex attribute and Firefox/Mesa refused to link the program
  ("Number of attributes exceeds Mesa's reported max attribute count") — the cloud did
  not render at all. Two moves took it to **11**: `aTarget` + `uMorph` deleted (dead
  code, pinned 0 since it shipped; in git history if the morph ever returns) and
  `aSeed/aBloom/aSpread/aRank` packed into one `vec4 aMisc` (DynamicDrawUsage;
  `reorderCells` writes the w channel at stride 4). Side cost recorded: a focus change
  now uploads the 5.6 MB packed buffer instead of the 1.4 MB rank buffer — still
  focus-change-only, never per frame. `Stats.svelte` also falls back to plain
  `gl.RENDERER` when `WEBGL_debug_renderer_info` is absent (deprecated in Firefox).
  The label pool's dev-mode warnings are gone too: `slots` and `elements` are now
  passed with `bind:` (`$bindable` in NodeProjector/NodeLabels), the tag ref is a
  function binding, and `labelElements` is `$state` — free, since the array is only
  written at mount (the per-frame positioning goes straight to `node.style`).

# Birdy — Session Handoff (2026-08-01, late: smooth LOD, chorus stops on Compose, text-first Compose tab)

**Three owner-reported UI issues fixed, all in the app.** Checks green: `npm run check`
at the 4 baseline errors, `verify-parity` 18/18, `verify:layout` green. **Not yet
verified visually** — fps before/after and the zoom feel need a run on the owner's
machine with the Display panel's cost readout open.

- **The LOD pop and the fps tank.** `PointCloud.svelte`'s discrete 3-level LOD is gone.
  The index is now **one fixed priority order** (knot representatives + unclustered
  points first, then stride tiers), uploaded once at load and re-uploaded only when the
  focused bird changes. A **continuous frontier** replaces the thresholds: a **cubed**
  smoothstep from one-point-per-knot at 3.2 cloud radii to everything at 1.6, applied
  per frame as integer `setDrawRange` calls — no buffer traffic, no hysteresis, no pop.
  (The cube was the first tuning correction, same day, on the owner's report: a plain
  smoothstep drew ~55 % of the corpus at the window's midpoint, where the whole cloud
  is still in the frustum and no cell is culled yet — the frame-rate floor just moved
  to mid-zoom. The cube holds the midpoint to ~21 % and pays density out late, when
  culling has teeth. `shownFraction` in `PointCloud.svelte` carries the full comment.) A new `aRank`
  attribute + `uLod` uniform fade the ~2 % of points at the frontier in, same idiom as
  the arrival ramp. **The resting pass is now 64 chunked geometries** (4×4×4 grid over
  the bbox, shared attributes, per-cell exact bounding spheres padded 0.12 box units,
  `frustumCulled: true`) — zoomed into one bird, off-screen cells cost nothing.
  **Silent frames no longer upload anything**: activation/orphan/front/cluster-texture
  uploads and the O(n) active-index scan are all skipped when nothing sounds (one zero
  upload on the transition into quiet). Point-size ceiling 42 → 24 px (overdraw on the
  iGPU). `stats.lod` is now the live 0..1 fraction and the cost readout prints it as a
  percentage. The active (responding) pass is untouched.
- **Chorus stops on the Compose tab.** A new `$effect` on `tab` calls `silence()` when
  entering Compose with a chorus running; returning to Sing does not resume (explicit
  stop semantics). The selection → solo-chorus effect is now gated on `tab === 'sing'`,
  so the Compose tab's species picker no longer hijacks or starts a chorus. Galaxy
  clicks still work: `pickCluster` sets `tab = 'sing'` in the same handler and effects
  run after state settles.
- **Compose tab is text-first now.** Order: Species → words textarea ("Words for the
  bird to sing") → interpretation callout → strip → Sing it / Clear. One new primary
  button, **"Sing the words"**, fills the strip to the text's rhythm and plays it in
  one click (replaces "Set the rhythm from the words"). The callout shows the honest
  case both ways: documented match unchanged (real call, citation, its own button), and
  a new invented branch ("No documented call matches these words…") with the existing
  badge machinery. All the manual machinery (Free/Guided/Song types, suggestions,
  motifs, keyboard) lives in a collapsed `<details>` "build the strip by hand" — same
  code, relocated. `grammar.ts`'s DOCUMENTED keyword rows gained obvious synonyms only
  (raptor/falcon, mate/attract/desire, beware/warning, hi/hey/anyone, evening/midnight);
  every row still maps to the same playback-verified call.
- **Answer recorded for the owner's question "is there a words→meaning-space
  mechanism": no.** The DOCUMENTED table is the only semantic path; everything else is
  rhythm + measured grammar. The centroid vectors are audio embeddings with no text
  alignment — a true cross-modal bridge is pipeline-side research, not a UI change.

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

**Two more owner-reported bugs, both found and both real**

- **"A one-tone bird makes the cloud flash / dim while it is active."** The resting wash
  gave up 40 % of its alpha in proportion to `uLevel`, the **raw live input level** —
  loudness, not match. A pure tone matches almost no bird syllable, so it dimmed the entire
  corpus by 40 % and lit nothing: the galaxy flinching at a sound it could not place. And
  `uLevel` is per-frame and unsmoothed, so the whole picture flickered at audio rate. Now
  driven by a new `uAnswer` = **loudness × `signal.strength`, eased** — the wash only steps
  back when there is something behind it to see, and it comes back slower than it left
  (~80 ms rise, ~250 ms fall, both delta-scaled so the half-life is the same at 60 and
  144 Hz). `uLevel` still drives the pulse and the growth in the vertex stage, unchanged.
- **"The camera does not centre on the centre of the point cloud, especially on autoload."**
  Two causes, both in `Framing.svelte`. First, **it aimed at the per-axis median of the
  knots, which is not the middle of the cloud.** The median is right for a bird — it is why
  one stray call cannot drag the view off the repertoire — and wrong for "everything",
  because knot density is skewed. Measured on the built assets: the projection is centred on
  the origin to within 0.001, and the median lands **0.269 box units off on the shipped
  build (14 % of the cloud's span) and 0.537 off on the production build (27 %)**. The
  camera was aiming a quarter of the way out from the cloud, worst on autoload because
  autoload *is* the whole-galaxy case. `reachQuantile` already excluded framing-everything
  by name for the *reach*; the exception was simply never applied to the *centre*. It now
  centres on the extent when framing ≥ 90 % of the knots and keeps the median otherwise.
  Second, **it read centroids without checking `counts`** — `layouts.ts` documents a
  memberless knot's (0,0,0) as a lie that every positional effect must check, and this one
  did not, so on a build with memberless knots the aim was an average of the corpus and the
  origin. Latent on both current builds (both have zero memberless knots) and now guarded.
- **Same invariant still unguarded in `ContextPaths` and `Trajectory`** (thread endpoints)
  and in `NodeProjector` (tag position). Latent for the same reason — zero memberless knots
  on both builds — and worth closing before a build that has them.

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

**The production assets are INSTALLED, and `verify:features` went green for the first time**

`app/static/birdy` now holds the v5 build (176 MB, `clustering: label`, 348 461 points,
k = 14 003, coverage 100 %), committed in `409b4d3`. **`relations.json` is deliberately
absent** — see the 760 MB note above; the app treats it as an absent optional asset and
the "shares call shapes with" line simply does not appear. Regenerating a small one is a
pipeline fix, and hand-trimming the 760 MB file would have faked the pipeline's
provenance, so it was not done.

- `verify-inventory-shards`: **all assertions passed**, 2 423 shards + index.
- `check-provenance-buffers`: **OK**, and the number worth reading — **0 orphan syllables,
  0 that own no points at all**. The debug build's "sound plays, nothing reacts" class is
  gone by construction, which is what 100 % type coverage buys.
- **`verify:features` PASSES.** Exact syllable match **37/44 = 84.1 %** against a 50 %
  floor, where the shipped debug build failed it — **known-broken item 8 was the corpus,
  exactly as predicted**: debug-100 is the deepest hundred species and holds none of the 44
  authored syllables, and production holds them.
- **The session-gate failure was a false assertion in the test, and it is now the right
  assertion.** The check demanded that *this script's own synth renders* not flag, on the
  grounds that "the corpus's own renders are in-manifold by construction". They are not:
  the gate's anchors come from the fit *sessions*, which are field recordings, and our
  renders are the synthesized class — docs/22 §22.6 measures that class at a source mean
  gap of 7.233 along an axis holding 42 % of the space's energy. Scored against the shipped
  anchors:

  | rows | n | median 5-NN | under the 3.92 threshold |
  |---|---|---|---|
  | field-evidence knots | 13 928 | **3.17** | **74.7 %** |
  | synthesized-only knots | 75 | 11.02 | 0 % |
  | the script's 44 renders | 44 | 13.09 | fails |

  So the gate is calibrated correctly and holds on field audio; the old check was asking
  synth output to land on the field manifold. It now asserts the claim that is true and
  worth pinning — **real field audio is in-manifold**, over all 13 928 field knots' own 28-d
  means from the sidecar — keeps broadband noise as the negative control (5.48, flags), and
  **reports the 13.09 render score without asserting it**, because its distance from the
  field cloud is a real property of the corpus and a change in it is worth seeing.
- **One thing checked and found NOT to be a bug, recorded so nobody re-hunts it.** The
  obvious suspicion was a space mismatch — anchors in raw descriptor units, rows pushed
  standardised, which would inflate every distance about 4x and look exactly like a
  miscalibrated threshold. It is not that: **both the anchors and `centroids.json`'s 28-d
  `vector` are already standardised** (per-dim |mean| ≈ 0.4, std ≈ 0.97 for both, against a
  feature-space mean of [24.9, 25.7, …] and std of [57.3, 27.8, …]), so `listener.ts`'s
  `standardise()` push matches the anchors. `SessionGate` strides the flat anchor array by
  a *passed-in* `dims`, which is a real desync hazard, but both call sites pass the
  top-level 28 and the anchors are 28 wide.
- **`listener.ts`'s mic-only guard on the gate is load-bearing, and its comment now says
  so.** It used to claim corpus audio "would never — and should never — flag"; the first
  half is false at 11.02 against 3.92. Without the `if (micActive)`, playing Birdy's own
  voice near an open mic would light the Reading panel's *first* branch — "off the map,
  positions are guesses" — about our own corpus.

**A PRODUCTION LEARN WITH `--inverse` RUNS SERIALLY ON 28 CORES, AND THAT IS THE REAL COST
OF THE TWO-START — not the two descents**

Measured on the v6 run: **7.5 species/min, so ~5.4 h for 2 421 species** against the ~23 min
a plain production learn takes. Two causes, and the second is the structural one:

1. **`learn --jobs` defaults to 1.** The v6 command was copied from the debug arm-C/D
   invocation, where serial is fine at 100 species and is not fine at 2 421.
2. **Passing `--jobs` would not have helped.** `learn.py` forces serial whenever `realism`
   or `inverse` is not None — a torch model cannot be pickled into a fork worker, so the
   pool is skipped with a logged reason. `--jobs 8` is *ignored* under `--inverse`.

Observed while running: **28 cores, load average 2.04, GPU 0 % / 216 MiB.** The GPU holds the
encoder and does nothing, because the encoder runs **once per type** (`init_syllable`) while
the actual work — render, descriptor, cosine, twice per type — is CPU numpy.

**The fix, for whoever runs the next one.** Batch every encoder proposal up front on the GPU
(one forward pass over all types, which is what the GPU is for and it is idle), cache the
proposed starting syllables, then fit in parallel with **no torch in the workers**. That
removes the reason for the serial gate entirely and should recover most of the 8-14x the
machine is offering. The two descents per type are a 2x cost and were predicted; the 14x is
the fork gate, and it was not.

Left running rather than fixed mid-flight: the run was 1.6 h in, healthy, and with the
encoder basin winning a steady 51 %. Restarting would have cost the elapsed time plus an
untested change.

**THE PRODUCTION BUILD'S MAP AGREEMENT IS 12-14 POINTS WORSE THAN THE DEBUG BUILD, AND THIS
IS THE RE-MEASUREMENT docs/20 ASKED FOR BEFORE ANY PRODUCTION DECISION** (it shipped without
it; the figures were in the build all along, in `feature-space.json`'s
`embedding.mapQuality`, and nobody read them)

| build | k | region agreement | tie-adjusted | species agreement |
|---|---|---|---|---|
| debug, label | 4 298 | 0.6316 | 0.8136 | 0.6831 |
| debug, label + W5 | 2 155 | 0.6439 | 0.7847 | 0.6982 |
| production v4, kmeans | 1 024 | 0.6081 | 0.8410 | 0.6300 |
| **production v5, label (SHIPPED)** | **14 003** | **0.4909** | **0.7056** | **0.5619** |

- **What it means for the central gesture.** Agreement is the nearest-centroid lookup the live
  path performs: sing, map the 28-d descriptor into the 32-d space, take the nearest knot. On
  the build now in `app/static/birdy`, that lookup lands on the same region the embedding
  itself would choose **less than half the time** (0.4909), and the same species just over
  half (0.5619). The tie-adjusted 0.7056 says most of the disagreement is a near-miss between
  *adjacent* knots rather than an unrelated region — a blurred answer rather than a wrong one —
  but it does not make the raw number bigger.
- **The direction is explicable, not mysterious.** 14 003 knots against the debug build's
  4 298 means roughly three times as many near neighbours available to be confused with the
  right one. Nothing regressed; the task got harder because the map got finer. **This is the
  cost side of the 100 % type coverage that label assignment bought**, and the two numbers
  belong in the same sentence from now on.
- Taken with §22.8's type-retrieval ceiling of **0.602**, the honest bound on "sing and the
  right knot lights" at production scale is **lower than any debug figure in the record**.
- Now stated in the whitepaper's Limitations section rather than left as a gap.

**THE TWO-START DESCENT PASSES ITS PRE-REGISTERED GATE — the first gate the amortised
inverse has ever cleared** (`pipeline/analysis/inverse_gate.md`, full run record there;
`learn --inverse PT --inverse-two-start`)

Per type, `invert_gestures` runs from the cluster median **and** from the encoder's
proposal, and the better candidate wins. Against arm A on debug-100, 1 661 shared types:

| | baseline | single-start (arm B) | **two-start (arm D)** | gate |
|---|---|---|---|---|
| median resynthesis cosine | 0.7410 | 0.7550 (+0.0140) | **0.7740 (+0.0330)** | +0.02 |
| types improved | | 51.7 % | **51.7 %** | — |
| **types worse** | | 45.0 % | **0.0 %** | — |
| **worst species** | | **−0.0815** | **+0.0000** | none worse |
| | | FAIL both | **PASS both — adopt** | |

- **The gate caught a real bug, which is what it was written for.** The first two-start run
  (arm C) cleared gate 1 at +0.0320 and **failed gate 2 with 48 of 1 661 types worse, by up
  to 0.049**. The pre-registration says a regression here "is a bug in the selection rather
  than a trade", so it was hunted rather than excused. Three hypotheses died on measurements
  — the objective and the reported metric are the same computation; `fricative_seed` is
  monotone; the arms fitted **identical** inventories (members/dur/f0 equal on all 1 661) —
  and a fourth died on a direct test: **the render is bit-identical for fixed parameters**
  (cosine 1.000000 over 5 renders at `noise=0.6 rough=0.65`), so it is not stochastic.
  **The cause: 19.3 % of types ship `fricative: true`, but 100 % of the 48 regressions did**
  (p ≈ 10⁻³⁵). The selection read the **pre-fricative** score while the shipped and gated
  number is **post-fricative**, and `fricative_seed`'s benefit depends on the basin — so the
  better proxy could land on the worse product. Fixed by making a candidate *the descent
  plus the fricative seed, scored as it ships*; regressions went 48 -> **0**.
- **What it licenses.** A fit option that is *never worse* — the gate as written is met. It
  does **not** say the renders sound better: docs/19 put the cosine's correlation with
  audible distortion at ≈ 0.1, and this gate reads the cosine, so the MCD/STFT bench is
  still what an audible claim needs. **Cost is 5.5x**: ~61 min against arm A's ~11, more
  than the predicted doubling. Default unchanged; the flag exists and passes.
- **Correction carried into the record:** arm B's published "worst species −0.0816" was
  scored through the same proxy, so part of it is this artefact rather than the encoder's
  fault. Arm B still fails, on gate 1's median alone.
- `analysis/score_two_start.py` reads the fit's own `FIT` log lines and was **validated
  against a known answer before use** — on arm A vs arm B it reproduces the published
  failure (+0.0140, worst `gampsonyx_swainsonii` −0.0815 against the recorded −0.0816).

**`relations.json` fixed in the pipeline, and the feature is back: 760 MB -> 5.6 MB**

`compute_relations` returns every unordered pair of species, which is what the analysis
wants and is quadratic in the corpus: **2 929 410 pairs**, which is C(2 421, 2) exactly —
**2 421 species, not the inventory's 2 423**. The two knots that differ are real: relations
is computed over species that have type centroids in the critic space, and the unlabelled
pool is excluded by design. Quoting the inventory's 2 423 against this pair count, as an
earlier draft of this entry did, is off by two species and does not reproduce the
arithmetic. The new
`relations.shipped_relations` writes the browser's copy — **each species' eight nearest
partners, deduplicated** — and `write_relations` applies it by default. The standalone
`relations` verb passes `per_species=None` and still writes the complete document, because
there the file *is* the analysis rather than a shipped asset.

- **Lossless for every question the app asks.** `relationsOf` wants a species' three
  nearest; eight leaves headroom. Checked against the real 760 MB document across **all
  2 421 species at the app's limit of 3: zero mismatches**, and a self-test pins the same
  property on a synthetic ring at limits 3 and 8.
- **Measured on the production document**: 2 929 410 pairs -> **14 425** (5.6 MB, **135x
  smaller**), carrying 9 513 of the 26 859 shared-type candidates.
- **The cut is declared in the file, not silent.** A `retention` block carries the rule and
  both totals, and says in as many words that `sharedTypesKept` is **not** the corpus's
  shared-type count — `sharedTypesComputed` is. The build logs the trim too, and its
  headline statistics are still taken from the *complete* document, so the finding is
  reported whole even though the asset is not. `RelationsDoc.retention` is declared in
  `types.ts` so a reader of the schema knows the field exists.
- Installed at `app/static/birdy/relations.json`, produced by running the pipeline's own
  `shipped_relations` over the build's own output — not hand-edited, which was the reason
  it was left absent in the first place.

**Open, for whoever is next**

1. ~~The production assets are built but not installed.~~ **Done**, `409b4d3`.
   ~~The pipeline-side `relations.json` fix.~~ **Done**, above.
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
