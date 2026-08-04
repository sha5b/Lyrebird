# 24 — What this corpus could add to ornithology

docs/23 is a plan for fixing the tool. This is a plan for adding to the science. The
difference matters, because the honest answer today is that the project has contributed
**nothing to what anyone knows about birds**. It has contributed method warnings and a
resource. 16 291 of 16 380 regions are `unlabelled`, nine are `experimental`, and no claim
about function, meaning or behaviour survives anywhere in the build.

This document names the biological questions this corpus can actually answer, the gates each
must clear first, and the order to attempt them in.

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

### G2 — Can we reproduce a relationship the field already agrees on?

**Why.** A pipeline that cannot recover a textbook result has not earned the right to report
a novel one. Body mass against song frequency is the standard: larger birds sing lower.

**Method.** Species median $f_0$ against AVONET body mass, over all 2 650 fitted species.

**Gate.** A negative slope significant under a phylogenetic generalised least squares fit,
with an effect size inside the range the comparative literature already reports.

**If it fails.** Something upstream is broken, and no result from this corpus should be
believed until it is found.

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

### W4 — Acoustic adaptation, at a scale it has never been tested

**The open question.** Whether habitat shapes song structure is contested, and the tests are
usually small-sample. AVONET carries habitat and foraging niche for every species.

**Why it is last.** It is the most exposed to G3. Habitat correlates with geography, which
correlates with who was holding the recorder. A positive result here is the easiest of the
four to be wrong about, and the most attractive to publish, which is a dangerous combination.

**Gate.** Runs only if G3 passes cleanly, and only on species with three or more independent
recordists.

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

## 24.2 Order, and why

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
