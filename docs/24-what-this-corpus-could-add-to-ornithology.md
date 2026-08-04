# 24 — What this corpus could add to ornithology

docs/23 is a plan for fixing the tool. This is a plan for adding to the science. The
difference matters, because the honest answer today is that the project has contributed
**nothing to what anyone knows about birds**. It has contributed method warnings and a
resource. 16 291 of 16 380 regions are `unlabelled`, nine are `experimental`, and no claim
about function, meaning or behaviour survives anywhere in the build.

This document names the biological questions this corpus can actually answer, the gates each
must clear first, and the order to attempt them in.

## Results first — Phase 0 ran on 2026-08-04

Every gate below was written before it was run, and the thresholds were not moved
afterwards. Three of the four ran; the fourth was closed by the third's result. The plan
that follows is left standing as it was written, with each gate's outcome attached to it,
because a pre-registration edited after the fact is not one.

```
G1  fitted tract length vs body mass      FAIL      partial r +0.194, gate > 0.4
G2  the textbook mass/frequency result    PASS      r -0.542 on well-sampled species
G3  recordist confound after aggregation  PASS      species +0.229 vs recordist +0.196
W0  step-zero literature check            MOVED     the practice exists; the number does not
W1  phylogenetic signal in production      CLOSED    by G1, per this document's own rule
W2  learners vs non-learners              REFUSED   the measures cannot carry the question
```

**The one-sentence version: the comparative biology does not exist, and Phase 0 is what
establishes that rather than what was hoped to open it.** The three scripts are
`pipeline/analysis/g1_g2_avonet.py`, `g3_recordist_aggregation.py` and `w2_learners.py`.
Details sit with each gate below.

**G2 is what makes G1's failure worth reading.** A pipeline that failed both gates would
just be broken. This one recovers a textbook relationship at the published effect size and
still cannot find anatomy in its own fitted tract, which narrows the finding from "the
corpus is bad" to "this particular parameter is not a measurement".

## 24.0 What we hold that nobody else does

The plan follows from the asset, so the asset has to be stated precisely.

1. **16 283 fitted physical parameter vectors over 2 650 species.** Each one is an
   interpretable control set for a published oscillator: pressure and tension gestures, an
   effective tract length, a harmonic profile, a noise fraction. It is not an embedding. The
   physical-model literature fits individual birds, one at a time.
2. **378 224 measured syllables over 3 636 species**, with order preserved inside each
   recording, so syntax is available and not only spectra.
3. **A measured first-order grammar per species**, with repeat classes and song types.
4. **A generative model.** The same parameters that describe a syllable can render it, so a
   prediction here is playable rather than only printable.

Points 1 and 4 are the unusual ones. A comparative study of **song production mechanics**
across thousands of species has not been possible before, because nobody had the parameters.

## 24.1 The problem that decides whether any of this is science

**Every question below assumes the fitted parameters measure the bird.** That assumption is
currently unproven and there is direct evidence against parts of it.

- The fit's own objective, a 28-dimensional descriptor cosine, correlates with audible
  spectral distortion at about $r = 0.1$. The optimiser cannot hear.
- The median fitted type reaches a cosine of 0.699. That number ranks nothing perceptual.
- The effective tract length is quantized to 39 distinct values over 1 621 species. 388
  species (24 %) sit on the 1.4 cm floor and 11 sit on the 14.3 cm ceiling.
- The embedding organises by recordist at +0.488 against species at +0.196, and four
  independent removal attempts failed.

So **Phase 0 is not optional and it is not a formality.** If the parameters do not track
anatomy, Phase 1 is measuring our own fitting artefacts and dressing them as biology.

## Phase 0 — Earn the right to make a biological claim

Three gates. All three are cheap, use open data, need no new audio and no training run. All
three are pre-registered here, before the runs.

### G1 — Does the fitted tract length track body size?

**Why this one first.** Effective tracheal length is the only fitted parameter with a direct,
independently measurable anatomical counterpart. Tracheal length scales with body size in
birds, and a number of lineages (cranes, curassows, guans, some birds-of-paradise) carry
famously elongated tracheae that are documented in the anatomical literature. If our
`L_eff` is anatomy, it will find them.

**Method.** Join `L_eff` per species to body mass from **AVONET** (Tobias et al. 2022, open,
11 009 species). Drop species pinned at the floor or the ceiling, which are clamps rather
than measurements. Regress $\log L_{\text{eff}}$ on $\log$ mass. Report the partial
correlation controlling for the species' median $f_0$, because a resonance that merely
restates pitch is not a measurement of a windpipe.

**What is already known before the run.** `L_eff` is a deterministic function of the fitted
tract $f_1$ ($r = -1.000$ in log-log, by construction). Against the species' own median $f_0$
it correlates at only $r = -0.206$. That weak coupling is the encouraging part. It means the
tract estimate carries information the pitch does not.

**Gate.** Partial $r > 0.4$ between $\log L_{\text{eff}}$ and $\log$ mass, controlling for
$\log f_0$, over at least 800 unpinned species. Also required: the known long-trachea clades
must sit in the upper decile.

**If it fails.** The fitted tract is a fitting artefact. Phase 1 is then closed for any
question that leans on production mechanics, and the honest write-up is a negative result
about inferring anatomy from song at scale. That is publishable and it is worth knowing.

**RESULT, 2026-08-04: FAIL.** AVONET joined 1 578 of the 1 621 fitted species on eBird
taxonomy, leaving 1 187 unpinned, so the sample half of the gate cleared easily.

```
r          log L_eff ~ log mass                 +0.241
partial r  log L_eff ~ log mass | log f0        +0.194     gate > 0.4     p 1.5e-11
```

Real, in the right direction, significant past any reasonable doubt, and less than half
the gate. **The two excuses available for a weak correlation were both measured and both
closed before the verdict was written.**

```
quantization   a PERFECT predictor snapped to the same 39 levels reaches r +0.998
               so 39 values are ample; the grid is not what is limiting this
thin sampling  r by per-species syllable count: +0.241 / +0.263 / +0.226 / +0.299
               flat. More audio per species does not sharpen it.
```

The clade half is the one encouraging fragment: **cranes sit 2 of 2 in the upper decile at
a median 10.6 cm**, and Cracidae, Anatidae and Phasianidae all beat the 10 % base rate.
Every one of those families is a handful of species here, so it is a hint and not a
result. `L_eff` carries a little anatomical information and is dominated by fitting
artefact. It cannot support comparative biology.

### G2 — Can we reproduce a relationship the field already agrees on?

**Why.** A pipeline that cannot recover a textbook result has not earned the right to report
a novel one. Body mass against song frequency is the standard: larger birds sing lower.

**Method.** Species median $f_0$ against AVONET body mass, over all 2 650 fitted species.

**Gate.** A negative slope significant under a phylogenetic generalised least squares fit,
with an effect size inside the range the comparative literature already reports.

**If it fails.** Something upstream is broken, and no result from this corpus should be
believed until it is found.

**RESULT, 2026-08-04: PASS.** Negative, significant, and the effect size lands where the
literature puts it once the per-species sample is deep enough to measure.

```
                              slope    r
all 1 578 species            -0.130   -0.247
n_syllables >= 100            -0.109   -0.213
n_syllables >= 400 (53 spp)   -0.193   -0.542
```

The comparable published figure is a **standardised** slope, so it is our r that has to
be held against it and not our OLS slope: Mikula et al. 2021 (Ecology Letters, PGLS over
5 085 passerines) report beta = -0.51 for peak frequency on body mass. On the species we
have actually sampled deeply we get -0.542.

**The contrast with G1 is the point, and it is what turns a failure into a finding.** f0
is a direct measurement and it sharpens as the sample grows, exactly as a measurement
should. `L_eff` is a fitted parameter and it stayed flat. The dilution at low syllable
counts is sampling, not a broken pipeline.

Still owed: PGLS. This is OLS, and the BirdTree download that W2 later used is now on
disk, so the phylogenetic version is cheap and should be run before anything is published.

### G3 — Does the recordist confound survive species-level aggregation?

**Why.** This is the project's strongest measured finding and it is lethal to every
comparative claim below if it is not handled. Habitat, region and recordist are correlated in
archive audio, so an "acoustic adaptation" result could be a map of who owns which recorder.

**Method.** Recompute the confound on **species means** rather than on points, and on a
recordist-blocked resample where no species contributes two recordings from one recordist.
Report the species lift and the recordist lift under both.

**Gate.** Species lift must exceed recordist lift on species means. State the margin.

**If it fails.** Every comparative question below must be restricted to species with
recordings from three or more independent recordists, and the sample shrinks to whatever
that leaves. Report that number before running anything else.

**RESULT, 2026-08-04: PASS on all three arms, and it inverts the project's own headline
number.** At syllable level the confound is recordist +0.488 against species +0.196. One
point per recording reverses it.

```
ARM A  all 9 026 recordings                 species +0.221   recordist +0.155   +0.066
ARM B  recordist-blocked resample           species +0.156   recordist +0.138   +0.018
ARM C  matched rows, the fair margin        species +0.229   recordist +0.196   +0.033
```

**Arm C exists because Arms A and B do not compare like with like.** `geometry.measure`
drops any group under 8 members, and "species with >= 8 recordings" is a different
population from "recordist with >= 8 recordings" — 25.9 % against 57.7 % coverage in Arm
A. Subtracting two lifts computed on different rows is not the margin this gate asks
about. Arm C keeps only recordings whose species *and* recordist both clear 8, so both
lifts come off one identical row set at 100 % coverage. It is the number to quote.

**What it means, and it cuts against us.** Most of the recordist confound was
same-recording pseudo-replication: syllables from one recording are neighbours, and one
recording has one recordist. That is a weaker claim than the project has been making, and
it weakens W0's premise as well as this gate's threat.

Two deviations, both forced and both stated rather than absorbed. "Species means" taken
literally is one point per species, which makes species lift untestable by construction;
one point per *recording* is the aggregation that removes the pseudo-replication while
leaving both groupings measurable, and it is what `w6_t1_perch_recordist.py` already uses.
And the margins are thin. +0.033 is a pass, not a comfortable one.

The fallback population, reported either way as this gate requires:

```
species with >= 3 independent recordists     743 of 3 636
species with >= 2                          1 940
species with exactly 1                     1 696
```

## Phase 1a — The one result that would reach the whole field

Everything else in this document is a contribution to ornithology. **This one is a
contribution to every group that uses bird audio**, which is a much larger room, and it is
the thing this project is best positioned to deliver.

### W0 — Are bioacoustic benchmarks inflated by recordist leakage?

**The claim to test.** Standard evaluation in this field splits recordings at random. If a
species' recordings come disproportionately from one recordist, and a model can identify the
recordist, then a random split leaks the answer across the train and test sides. The reported
number is then partly a measure of recorder identity, not of the bird.

**Why we are positioned to ask it.** We already measured the mechanism on our own store:
nearest-neighbour lift is **+0.488 for recordist against +0.196 for species**, and four
independent attempts to remove it failed. Two of those attempts used **Perch 2.0 and
BirdNET**, which are the field's own archive-scale models, and they carry it too. We also
found they disagree with each other by more than either differs from ours.

**Why it matters beyond us.** BirdNET and Perch are deployed by ecologists for real
monitoring and for real conservation decisions. Their benchmark numbers set expectations. A
recordist is also, functionally, a *recorder and a site*, so leakage across a random split is
the same failure that appears when a model trained on archives is deployed on a new device in
a new place. The field already knows deployment performance disappoints. This names a
measurable cause and gives a cheap fix.

**Method, and it needs no new audio.**

1. Take a **public** corpus we did not build: BirdSet (`XCM`/`XCL`, Hugging Face) or the
   BirdCLEF splits. Using our own store would let anyone dismiss it as our pipeline being odd.
2. Take the field's own models off the shelf: **Perch 2.0** and **BirdNET**. Both already run
   here, and `perch.py` is wired and tested.
3. Evaluate species retrieval or classification twice, changing one thing only:
   - the standard **random split**;
   - a **recordist-blocked split**, where every recording by one recordist falls on one side.
4. Report the difference, per model, with the recordist coverage of each corpus stated.

**Gate, pre-registered.** A drop of more than 10 points of top-1 species accuracy between the
random and the recordist-blocked split, on at least one public corpus, reproduced on both
models.

**If it passes**, the deliverable is not our system. It is a short paper saying: *block your
splits by recordist, here is what it costs you, here is the code*. That changes what other
groups do, which is the definition of adding to a field.

**If it fails**, that is equally worth publishing, and it retires our own strongest complaint.
It would mean the confound we measured is a property of our store rather than of the archives,
and the four failed removals become a local curiosity rather than a warning.

**Step zero, before any of it: a literature check.** Domain shift and soundscape-to-focal
generalisation are known problems in this field. Recordist-blocked evaluation may already
exist somewhere under another name. The novelty claim has to be checked before the run, not
after, and if it is already known the correct action is to cite it and move to Phase 1.

**RESULT of step zero, 2026-08-04: the claim has to move, and the run is still worth
doing.** Half of W0 as written above is twelve years old.

- **The practice exists.** Stowell & Plumbley 2014 (PeerJ 488, `doi:10.7717/peerj.488`)
  held out one recordist at a time on the British Library dawn-chorus set, with our exact
  rationale in their words: it "tests whether the system can generalise to recordings from
  unknown recordists, rather than adapting to any specifics of the known recordists". The
  Cornell CBI dataset is likewise split so that no recordist spans two partitions.
- **The quantity does not.** Checked against the sources rather than against an abstract:
  Stowell & Plumbley report no random-against-blocked comparison; neither does the 2026
  foundation-model comparative review (arXiv 2508.01277) nor Earth Species' 2025 training
  recipe (arXiv 2508.11845). Nobody has published what a recordist-blocked split costs a
  current foundation model.

So W0's deliverable is no longer *block your splits*, which is known and ignored. It is
**here is the number, on Perch 2.0 and BirdNET, on public corpora** — a measurement whose
absence is what lets the practice keep being ignored.

**A design constraint found in the same pass, and it breaks the method as written.**
BirdNET is excluded from BirdSet evaluation for training-set leakage: it was trained on
xeno-canto, which is what BirdSet's XCM/XCL are drawn from. "Reproduced on both models"
therefore cannot use an XC-derived corpus for BirdNET. Either find a corpus BirdNET was
not trained on, report BirdNET separately with the contamination stated, or replace the
second model. This has to be settled before the run, not discovered during it.

**And G3 has since undercut the premise.** If most of the recordist structure we measured
was same-recording pseudo-replication, the leakage W0 predicts is smaller than we thought.
That does not retire the question — a random split still puts one recordist on both sides
— but the expected effect should be revised down before the gate of "more than 10 points"
is treated as likely.

## Phase 1 — The four questions worth asking

Ordered by how much new biology a positive result would add, against how exposed each is to
our known confounds.

### W1 — Phylogenetic signal in song *production*, not song *sound*

**The open question.** How much of song variation is inherited and how much is ecological is
a long-running comparative question. It has always been asked of acoustic summaries such as
peak frequency and bandwidth. It has never been asked of **production parameters**, because
those did not exist at scale.

**Why it is new.** Pressure and tension gestures, tract length and harmonic structure are
closer to the anatomy and the motor program than a spectral summary is. Signal in a spectral
summary may be signal in body size. Signal in a *gesture* is a different and more interesting
claim.

**Method.** Pagel's $\lambda$ and Blomberg's $K$ on species-mean production parameters,
against the **BirdTree** phylogeny (Jetz et al. 2012, open, all extant birds), over a
posterior sample of trees rather than one consensus tree. Body mass as a covariate
throughout, because size is the obvious confound and is exactly what G1 measures.

**Gate.** $\lambda$ significantly above 0 and distinguishable from a Brownian expectation of
1, on at least three production parameters, over at least 1 000 species with tree coverage.

**What a positive result says.** Song production mechanics carry phylogenetic signal
independent of body size. That is a genuinely new comparative finding.

**RESULT, 2026-08-04: CLOSED, not run.** G1 failed, and §24.1 of this document closes
Phase 1 for "any question that leans on production mechanics". W1 is that question in its
purest form. Running it anyway would produce a number, and the number would be the
phylogenetic structure of our own fitting artefacts — which is precisely the failure mode
this document was written to prevent. It stays closed until a tract estimate passes G1.

### W2 — Vocal learners against non-learners

**The open question.** Oscines learn their songs, suboscines mostly do not, and
non-passerines mostly do not. The theoretical expectation is that learning permits greater
syntactic complexity and larger repertoires. Testing it has been limited by sample size.
2 650 species spanning all three groups is the sample that test has been waiting for.

**Why we can ask it.** We hold a measured repertoire size, a measured first-order grammar and
a measured entropy rate for every fitted species. The group labels are free from open
taxonomy.

**Method.** Phylogenetic generalised least squares on repertoire size, first-order entropy
rate and repeat-class count, with learning status as the predictor and body mass as a
covariate.

**Gate.** Learners exceed non-learners on at least two of the three measures after
phylogenetic correction, at an effect size stated before the run.

**The honest limit, stated separately.** Our "repertoire size" is a count of machine-derived
clusters, so it is a repertoire *proxy*. It is applied identically to every species, which is
what a comparative contrast needs. It is not a count any field ornithologist would recognise
as a repertoire, and the write-up must say so in those words.

**RESULT, 2026-08-04: REFUSED. Not a null result about vocal learning — a statement that
our measures cannot carry the question.** W2 does not depend on G1 (its three measures come
from segmentation, typing and transition counting, none of which touch the fitted
oscillator), so it ran, and it ran at full scale: 2 059 species, learner status from
BirdTree's own `OscSubOsc` column rather than a hand-typed family list, PGLS over 10
posterior Ericson trees, body mass **and sampling effort** as covariates.

All three measures came back flat under both codings. But the diagnostic that runs *before*
the model is what decides how to report it:

```
repertoire vs sampling effort        r = +0.852
repeat_types is zero on              97.7 % of species
repertoire  median 5,  p90 10,  max 64   (field oscine repertoires reach dozens)

median repertoire by how much audio we hold for the species:
    0-30 syllables    median 2.0
   30-100             median 4.0
  100-300             median 8.0
  300+                median 8.0
```

One of the three measures is degenerate. Another is 85 % a count of our own audio. A
2-of-3 gate cannot be cleared by the one that is left, so the flat coefficients are
evidence about this corpus's depth — median 69 syllables per species — and not about
birds. **Reporting them as a null about vocal learning would be the most attractive
available mistake**, because the null is publishable-sounding and the sample is large.

**One covariate this section did not ask for and should have.** Repertoire and entropy both
rise with how much audio a species has, and learners are not sampled at the same rate as
non-learners in citizen-science archives. Without `log(n_syllables)` in the model, W2
measures collection effort. It is in every fit; the r = +0.852 above is why.

**What would make W2 answerable.** Depth, not breadth. The measure saturates around 8
types by 100-300 syllables, so the binding constraint is syllables per species and not
species count. That is the same decision named in the handoff as "988 species under the
fitting floor", seen from the other end.

### W3 — How independent are the source and the filter?

**The open question.** Birds were long treated as lacking a strong source-filter separation.
Recent work shows tracheal resonance and beak gape do filter the syringeal source. How that
separation varies across taxa is open.

**Why we can ask it.** The fit estimates a source (oscillator) and a filter (tract) as
separate parameter sets, for 1 621 species. That is exactly the decomposition the question
needs.

**Method.** Per species, the correlation between source $f_0$ and fitted tract $f_1$ across
its own syllable types. A bird that moves its filter with its source scores high. A bird
whose tract sits still scores near zero. Compare the distribution across clades.

**Gate.** Conditional on G1. Without an anatomically valid tract estimate this measures
nothing.

**RESULT, 2026-08-04: CLOSED by G1, and this one was already written as conditional.** The
gate above is doing its job. Nothing to run.

### W4 — Acoustic adaptation, at a scale it has never been tested

**The open question.** Whether habitat shapes song structure is contested, and the tests are
usually small-sample. AVONET carries habitat and foraging niche for every species.

**Why it is last.** It is the most exposed to G3. Habitat correlates with geography, which
correlates with who was holding the recorder. A positive result here is the easiest of the
four to be wrong about, and the most attractive to publish, which is a dangerous combination.

**Gate.** Runs only if G3 passes cleanly, and only on species with three or more independent
recordists.

**RESULT, 2026-08-04: still open, and the gate is not satisfied.** G3 passed, but "cleanly"
is the operative word and a +0.033 margin is not clean. The population this gate confines
W4 to is now measured: **743 species of 3 636** carry three or more independent recordists.
W4 is the most attractive result in this document and the easiest to be wrong about, so it
stays last and it stays behind a margin that is currently thin.

## Phase 2 — The only route to function

Everything above is morphology, phylogeny and syntax. None of it says what a sound *means*.
The project's own evidence ladder already names the one thing that would: `experimental`,
meaning a bird was played this sound and responded.

**The asset that makes this unusual.** We can *synthesise* a species' fitted types, and we can
synthesise controlled variants of them, changing one physical parameter at a time. A playback
experiment with a real bird, using stimuli that differ in one fitted parameter, would test
whether the parameters the model fits are parameters the bird attends to. That is a real
experiment and it is the only item in this document that produces biology rather than
comparative statistics.

It needs a field collaborator, a permit and a season. It is out of scope for a solo
engineering effort, and naming it is not the same as planning it.

## 24.1b The decision on the table, and it is taken

Owner, 2026-08-04, asked which of these would genuinely add to the field and then answered
**both**. So W0 and G1 are both live, and the ordering below is about what to run first rather
than about what to drop.

They are independent on purpose. **W0 needs no part of our pipeline to be correct**, because it
runs public models over public corpora. **G1 decides whether any comparative biology exists.**
Each costs about a day. Neither blocks the other.

**Settled, 2026-08-04.** G1 ran and failed, so the question it decided is answered: no
comparative biology. W0 is still live, at about half the cost, because its step-zero
literature check retired the half of it that was already published in 2014. The
independence held — G1's failure cost W0 nothing, which is why they were run this way.

## 24.2 Order, and why

**The order below was the plan. It has been run down to step 4, and what remains is short
enough to state before restating the original reasoning.**

```
still to run    W0        the run itself, with the corpus/model pairing fixed first
                G2-PGLS   cheap now; BirdTree is on disk
                W4        only behind a G3 margin better than +0.033
closed          W1, W3    by G1
refused         W2        by its own measures, until the corpus is deeper per species
```

0. **W0**, because it is the widest-reaching result available and it depends on none of the
   gates below. It uses public corpora and public models, so it stands even if every
   parameter we fitted turns out to be an artefact.
1. **G1**, because it decides whether Phase 1 exists. One open dataset, an afternoon.
2. **G2**, same afternoon, same join. If a textbook relationship does not reproduce, stop.
3. **G3**, because it decides how much of Phase 1 survives, and it sharpens the project's
   strongest existing finding at the same time.
4. **W1**, then **W2**. Both need one phylogeny download and standard comparative methods.
5. **W3**, conditional on G1 being strong rather than merely passing.
6. **W4** last, and only behind G3.
7. **Phase 2** whenever a collaborator exists.

## 24.3 What to publish, and when

There are two papers here and they should not be the same paper.

**Paper one, the one with the widest reach.** W0: benchmark inflation under recordist
leakage, on public corpora with public models. It needs no part of our pipeline to be correct
and it is the result other groups would act on.

**Paper two, ready now.** The system, the resource and the refusals. 58 pre-registered gates
with 36 written refusals, the recordist confound closed at four ends including two
archive-scale foundation models, and the five noise gates measured dead. This is a methods
and resource contribution and it is honest about being one.

**Paper three, conditional on Phase 0.** The comparative biology. It does not exist yet and it
may never. Whether it does is decided by G1, and G1 costs an afternoon.

The failure mode to avoid is putting a thin comparative result into the system paper to make
it look like biology. The refusals are the contribution there. Diluting them would cost the
thing that makes it worth reading.

### 24.3b What Phase 0 did to that plan, 2026-08-04

**Paper three is decided, and the answer is no.** G1 cost an afternoon, as predicted, and
it failed. The comparative biology does not exist. It is not deferred, it is closed until
some future tract estimate passes G1.

**Paper two got better, not worse, and this is the substantive change.** Phase 0 was
supposed to be a licence to write paper three. What it actually produced is three results
that belong in paper two:

- a **negative result with both excuses closed** — the fitted tract does not measure the
  windpipe, and it is neither the 39-value quantization nor thin sampling;
- a **positive control that makes the negative one credible** — the same pipeline recovers
  the mass/frequency relationship at the published effect size, so "our corpus is broken"
  is not available as an explanation;
- a **correction to our own loudest claim** — the recordist confound largely does not
  survive aggregation past same-recording pseudo-replication.

The third is uncomfortable and is the reason to trust the other two. A methods-and-refusals
paper that also retracts its own headline number is doing the thing it claims to be for.

**Paper one is unchanged in value and changed in framing.** W0 stops being "recordist-blocked
splits are a good idea", which Stowell & Plumbley published in 2014, and becomes "here is
what one costs a current foundation model", which nobody has measured. Smaller claim,
still nobody else's, and now with a corpus/model contamination problem to solve first.

**The failure mode named above is now the live risk rather than a hypothetical one.** There
is a large, tidy, phylogenetically corrected null sitting in `w2_learners.json` that would
look like biology in a table. It is not. Whatever else paper two says about W2, it says
r = +0.852 in the same paragraph.
