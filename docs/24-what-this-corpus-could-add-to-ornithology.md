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
G2  the textbook mass/frequency result    PASS      PGLS beta -0.560 on the deep arm,
                                                    against a published -0.510
G3  recordist confound after aggregation  PASS*     species +0.229 vs recordist +0.196,
                                                    but on 77 of 3 636 species -- see ARM D
W0  step-zero literature check            MOVED     the practice exists; the number does not
W0  method as pre-registered              BROKEN    both models trained on the eval corpus;
                                                    redesigned as a frozen-embedding probe
W0  pilot, frozen Perch, post-cutoff      NOT MET   9.68 points, gate > 10 -- but 2.44x the
                                                    errors, worse in 20 of 20 folds
T1b Perch recordist lift, unseen audio    CONFIRMED +0.441 on matched rows; the earlier
                                                    contamination alarm was overcautious
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

**PGLS, run 2026-08-04 later the same day (`analysis/g2_pgls.py`): G2 now passes both
halves of its gate, and the way it passes is a finding of its own.**

```
                        n     standardised slope   fitted lambda
all species          2 059          -0.211             0.130
n_syllables >= 100     651          -0.248             0.000
n_syllables >= 400      76          -0.560             0.291
Mikula et al. 2021   5 085          -0.510
```

Negative and significant everywhere (p 1e-9 or better), so the pre-registered sign half is
clear. **The magnitude half is only met on the deep arm** — at 2 059 species we are at
about 40 % of the published slope, and at 76 deeply-sampled species we are on top of it.

**Lambda is the tell, and it moves the same way.** Pagel's lambda is fitted by maximum
likelihood here rather than assumed. It comes out at **0.130 over all species and exactly
0.000 on the middle arm** — that is, our species-level f0 residuals carry no phylogenetic
signal at all, which cannot be true of birdsong. Measurement error biases lambda towards
zero and attenuates a standardised slope by exactly the same mechanism, and both recover
together on the deep arm (lambda 0.291, slope -0.560). **The shortfall is our noise, not
the birds' biology**, and the deep arm is the check that says so rather than an assertion.

**One method note worth keeping, because it nearly produced a wrong answer.** The first
attempt forced Brownian motion (lambda = 1), which is what "PGLS" is often taken to mean.
It returned standardised slopes spanning **-1.962 to +0.001 across ten posterior trees** —
a range crossing zero, from trees drawn out of one posterior. That was not a numerical
fault: every pruned tree came back exactly ultrametric and positive-definite with condition
numbers around 1e6-1e7. Forcing a model the trait does not follow put the whole estimate on
a handful of deep splits whose arrangement differs between trees. Fitting lambda collapsed
the range to [-0.214, -0.207]. **A "PGLS" number with lambda assumed rather than fitted
should not be trusted from this corpus, and that generalises past us.**

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

**What it means — and this took two wrong explanations before ARM D measured the right
one. All three are recorded, because the gate reads differently under each.**

*First explanation, wrong: same-recording pseudo-replication.* `geometry.blocks_for`
already gives every field observation the block `rec:{recording_id}` and `measure` drops
same-block pairs, so the +0.488 was measured with same-recording neighbours excluded — the
whitepaper says "blocked by recording" in the same sentence as the number. Nothing to
remove.

*Second explanation, also wrong: averaging strips the recordist's signature.* ARM D tests
it directly — one population of recordings, scored at both representations, nothing else
changed:

```
                                       species   recordist
syllable-level, blocked by recording    +0.343     +0.295
the same recordings, averaged           +0.223     +0.198
```

Both fall by about a third, together. Aggregation is not selective.

*What is actually going on: the population, not the representation.* Look at the top row
again — **species already outranks recordist at syllable level here**. There is no
inversion for aggregation to cause. `measure` drops any group under 8, and at recording
level that floor means "species with at least 8 recordings": **77 of 3 636**.

The last step of that argument is measured rather than assumed, because the two before it
were not:

```
r(log recordings, log recordists) over 3 853 species      +0.923
species with >= 8 recordings   median distinct recordists  17.0
species with  < 8 recordings   median distinct recordists   2.0
```

A species is well sampled in this corpus almost exactly because several recordists
contributed to it.

**That much is not new and must not be written up as if it were.** The whitepaper's Wall 2
already states it: "most species in this corpus are carried by a handful of recordists, so
no method that sees only the embedding can separate labels the data never separated", and
"the named action is more recordists per species, in the data". The +0.923 is a number for
a fact the project had already put in print.

**The new part is what it does to this gate.** The floor that makes the recording-level
test possible is the same floor that selects away the confound the test is looking for. G3
asks whether the confound survives aggregation, and it can only be asked on the slice of
the corpus where the sampling problem does not apply.

**So G3 passes on the sub-population where it is measurable, and that sub-population is
selected in a way that favours passing.** The gate's letter is met and its spirit is not
settled. The coverage figures in each arm are the honest part of the result, and W4 — which
this gate exists to license — should be read as still blocked rather than merely thin.

Two deviations, both forced and both stated rather than absorbed. "Species means" taken
literally is one point per species, which makes species lift untestable by construction;
one point per *recording* is the aggregation that answers the question while leaving both
groupings measurable, and it is what `w6_t1_perch_recordist.py` already uses.
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

**And G3 revises the expected effect down, though less than first written here.** An
earlier version of this paragraph said most of the recordist structure was same-recording
pseudo-replication; that was wrong and is corrected under G3 above — the original
measurement was already blocked by recording. What G3 does show is that the confound is
weaker at recording level than at syllable level (+0.196 against +0.488), and a benchmark
split is a *recording*-level operation. So the leakage W0 predicts should be read off the
recording-level figure rather than the syllable-level one, and the pre-registered gate of
"more than 10 points" should not be treated as likely on the strength of +0.488.

### W0's method as written is broken, and the fix is cheap. 2026-08-04.

The contamination note above named BirdNET. Checking the other model made it worse:
**Perch 2.0 was trained on Xeno-canto *and* iNaturalist** (Perch 2.0 tech report,
arXiv 2508.04665: ~1.5 M recordings over 14 500 classes from Xeno-canto, iNaturalist
research-grade audio via GBIF, Tierstimmenarchiv and FSD50K).

So both candidate models have trained on the corpus W0 proposed to evaluate them on, and
that breaks the pre-registered method rather than merely qualifying it:

> **Top-1 accuracy on a random split versus a recordist-blocked split cannot separate
> leakage from memorisation.** A model that has seen the individual test recordings scores
> high on the random split for a reason that has nothing to do with recordists, and the
> gap between the two splits then partly measures *which recordings it memorised*. The
> pre-registered gate of "more than 10 points of top-1 drop" would be met, or missed, for
> the wrong reason either way.

**The redesign, and it is cheaper than the original.** Use the foundation model as a
**frozen feature extractor** and put the split on a **linear probe trained on top of it**:

```
1  embed a public focal corpus with recordist metadata once, per model, frozen
2  train a linear probe TWICE on those fixed embeddings, changing one thing only:
     a) a random split
     b) a recordist-blocked split
3  report the top-1 difference, per model, with recordist coverage stated
```

The foundation model's contamination is then **identical in both arms** and cancels out of
the comparison. What differs between the arms is only the probe's training set, which is
the thing the claim is about. It is also an order of magnitude cheaper than the original:
embeddings are computed once, and a linear probe is seconds.

This does narrow the claim, and the narrowing should be stated in the paper rather than
buried: the result becomes *"a recordist-blocked split costs a linear probe over frozen
Perch/BirdNET features N points"*, not *"benchmark accuracy is inflated by N points"*. That
is still a number nobody has published and it is still directly actionable.

**RESULT of the pilot, 2026-08-04 (`analysis/w0_recordist_split.py`): the effect is real,
large, and lands just under the pre-registered gate.** 62 species with >= 6 recordings and
>= 2 recordists, 730 recordings, frozen Perch features, post-cutoff audio, 20 folds.

```
                     random split   recordist-blocked
top-1                   93.29 %          83.61 %
DROP                     9.68 points                  gate > 10.0     NOT MET
per fold            mean +9.68  sd 5.08  blocked worse in 20 of 20 folds
as error rate         6.71 %  ->  16.39 %             2.44x the errors
```

**Gate not met, and it is not close enough to argue about — 9.68 against 10.** The
threshold was pre-registered and it is not being moved.

**But points are the wrong unit near the ceiling, and that is worth saying next to the
verdict rather than instead of it.** The same 9.68 points is a **2.44x increase in what the
model gets wrong**, and blocked was worse in **20 of 20 folds**. A gate specified in
accuracy points at 93 % accuracy is a much harsher bar than the same gate at 60 %, which is
a flaw in how it was written rather than a property of the effect. Any re-registration
should state the threshold as an error-rate ratio.

**The class-set correction mattered and is the reason to trust the number.** Scoring the
arms as they fall gives 9.14 points, because a blocked split strands whole species and
leaves that arm a smaller, easier label set (49.9 classes against 62). Pairing each blocked
fold with a random fold on its *own* class set raises the drop to 9.68 — the bias ran in
the direction predicted, and correcting it made the effect larger, not smaller.

Limits, stated: one model, pilot scale, and only species carried by two or more recordists,
which is the population where blocking is possible at all.

**A consequence for a claim we have already made — and the first version of this note
overstated it by applying one word to two very different tests.** Perch 2.0 trained on
iNaturalist research-grade audio, and **5 368 of our store's recordings are iNaturalist**,
so Perch has very likely seen the files `w6_t1_perch_recordist.py` fed it. That is true.
What follows from it is not the same for both tests:

*For W0, contamination is fatal.* W0 measures accuracy. A memorised recording is scored
correctly for a reason unrelated to generalisation, and the random-against-blocked gap then
partly measures which recordings were memorised. That is why W0 is redesigned above.

*For the recordist-lift arm, it is a speculative worry rather than a demonstrated flaw*,
and three things weigh against it:

- **Perch was never given recordist labels.** It was trained on species. It cannot have
  memorised an identity nobody told it.
- **Same-recording pairs are already excluded** by the blocking, so memorising one file
  cannot produce the effect directly — it would have to make *different* recordings by one
  recordist more alike.
- **The plausible direction of overfitting runs the other way.** A species classifier that
  overfits gets better at ignoring channel, microphone and background, which are exactly
  what carries a recordist's signature. That would lower recordist lift, not manufacture it.

So `w6_t1b_perch_postcutoff.py` is worth running, but for a narrower reason than "the
result is suspect": the whitepaper leans on Perch as an **independent** replication, and
training overlap is precisely what independence costs. The honest expectation is that it
**confirms** the original arm. If it does, the correction on record is that this note was
overcautious, not that the arm was wrong.

**RESULT, 2026-08-04: it confirms it, and the note above was overcautious.** 2 158 quality-A
bird recordings uploaded to xeno-canto after Perch 2.0's publication — audio the model
provably could not have trained on — 137 recordists, 827 species.

```
ARM A  every recording       species +0.742 (28.2 % cov)   recordist +0.159 (99.8 % cov)
ARM B  matched rows, n=293   species +0.750 (100 %)        recordist +0.441 (100 %)
```

Arm B is the number: both groupings on identical rows at full coverage, recordist lift
**+0.441, verdict "strong", p at the permutation floor**. **Perch was not recognising its
own training data.** The recordist confound is a property of archive audio that a
foundation model reads off recordings it has never seen.

Two notes. Species lift is very high here (+0.750) because Perch is a well-trained species
classifier and these are quality-A focal recordings; both structures are strong at once,
which is the point rather than a contradiction. And Arm A shows the same coverage trap G3
hit — species scored on 28.2 % of rows against recordist's 99.8 % — which is why Arm B was
built in from the start this time.

**The BirdNET arm is probably clean, and that matters more than the Perch problem.**
Checked after raising the alarm above, because an alarm is only useful with its scope
attached. BirdNET v2.4's training sources are Xeno-canto, the Macaulay Library, BirdSet's
soundscape evaluation subsets and project-internal data — **iNaturalist is not among
them**. `w6_birdnet_arms.py` imports `CACHE` from the Perch runner, so it ran on the same
iNaturalist audio, which BirdNET has no documented reason to have seen.

That asymmetry is the useful part:

```
Perch 2.0   trained on XC + iNaturalist   -> our iNat cache is contaminated
BirdNET     trained on XC + Macaulay      -> our iNat cache is probably clean
```

And the whitepaper's BirdNET result is the stronger of the two: BirdNET *raises* the
recordist lift by 24 %, more recordist structure than our own critic shows. **A model that
never trained on this audio finding more recordist structure in it is evidence the
structure is in the recordings rather than in anyone's memorisation.** So the "closed at
four ends" sentence survives, resting on the BirdNET end rather than the Perch end.

Two caveats that must travel with this. BirdNET's training set is **not publicly
documented** — the 2026 comparative review says as much, and notes that correspondence with
the authors indicated some downstream datasets are used in training. "Probably clean" is
the strongest available claim, not "certainly clean". And BirdNET having trained on
BirdSet's soundscape subsets is exactly why it is excluded from BirdSet evaluation, which
is the constraint on W0 above.

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

**One caveat added after G2's PGLS, and it does not change the verdict.** W2's fits force
Brownian motion (lambda = 1) rather than fitting lambda, which G2 later showed is unstable
on this corpus — W2's own posterior ranges show it, with entropy spanning [-0.067, +0.680].
**The refusal stands regardless**, because it rests on the pre-model diagnostic (one measure
degenerate, another 85 % sampling effort) and not on any coefficient. But if W2 is ever
re-run on a deeper corpus, it must fit lambda rather than assume it, and the numbers in
`w2_learners.json` should not be quoted as they stand.

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
                W4        only behind a G3 margin better than +0.033
done            G2-PGLS   lambda fitted, not assumed; gate now met on both halves
closed          W1, W3    by G1
refused         W2        by its own measures, until the corpus is deeper per species
```

**A constraint that emerged from G2's PGLS and now applies to everything left.** Fitted
lambda is 0.000 on 651 species and 0.291 on the 76 deepest. Per-species measurement noise,
not phylogeny, is what is limiting the comparative arm of this corpus — and it limits W4
the same way it limited W2. **Depth per species is now the single binding constraint on
every remaining question**, which is the same conclusion W2 reached from the other side.

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
- a **qualification of our own loudest claim** — the recordist confound is weaker at
  recording level (+0.196) than at syllable level (+0.488), and species overtakes it there.

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
