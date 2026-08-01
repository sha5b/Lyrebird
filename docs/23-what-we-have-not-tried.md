# 23 — What we have not tried

A plan written from the failures, not from the roadmap. Every workstream below names
the measured failure it attacks, the method, the gate stated before the run, and what a
negative result would mean. Methods are taken from fields that solved the same problem
on other data. Birdsong is the subject here, not the boundary of the reading list.

The order is by cost over payoff, not by ambition. Three of the six need no new data,
no network and no training run.

## 23.0 The pattern this plan answers

Almost every negative result in this repository has one shape. A mechanism is proposed,
pre-registered, and loses its gate. docs/17 §17.4 said the reason out loud — **data
beats mechanism at every scale tested** — and 2026-08-01 added three more losses in the
same shape (docs/22 §§22.3, 22.4, 22.6). Read together, the record says the binding
constraint is corpus structure and measurement method, not a shortage of ideas.

So the plan spends its first two workstreams on **measurements that can refute what the
pipeline already believes**, and only then on new machinery.

## 23.1 W1 — The recorder confound as a batch effect

**The failure.** Recordist kNN lift is +0.488 against species' +0.196 (docs/14 §14.4).
Two attempts to remove it by training failed: the adversarial head trades species
accuracy roughly 1:1 (§17.3), and a species-factored target cannot reach a
between-species confound (§17.5). docs/17 closed the loss-engineering road at both ends.

**What has not been tried.** The problem is a batch effect, and genomics has worked on
it for fifteen years. None of that toolkit has been run here. The important property is
that the strongest candidates are **post-hoc**: they correct an existing embedding and
need no retraining.

- **Harmony** — iterative soft clustering that removes batch structure while keeping
  cluster structure. Runs on `embeddings.f32` with the recordist as the batch label.
- **PLDA**, from speaker verification, which explicitly factorises between-class from
  within-class variability and is a linear model over the same embedding.
- ComBat, MNN and scVI as the second rank if the first two move nothing.

**Gate, stated before the run.** On the same fixed store, through `geometry.measure`
against its own permutation null: recordist lift falls by at least half **and** species
lift does not fall at all. Anything that buys invariance by spending species structure
is the §17.3 trade again under a new name, and fails.

**Cost.** Hours. No training, no network, no new data.

**A negative result would mean** the confound is not linear-and-post-hoc removable in
this space, which strengthens §17.4's "invariance is a data action" from a conclusion
into a boundary.

### 23.1.1 Result, 2026-08-01 — the road is closed at a third end

`batcheffect.py`, 20 000 syllables of the production embedding over 885 species, 1 001
recordists and 3 265 recordings, every arm scored by `geometry.measure` against its own
permutation null, blocked by recording.

| arm | species lift | recordist lift | ratio |
|---|---|---|---|
| baseline | 0.1643 | 0.1665 | 0.99 |
| centre by recordist | 0.1113 | 0.1687 | 0.66 |
| whiten by recordist | 0.0955 | 0.154 | 0.62 |
| harmony by recordist | 0.0501 | 0.0478 | 1.05 |
| centre by recording | 0.0432 | 0.0408 | 1.06 |
| whiten by recording | 0.0342 | 0.0331 | 1.03 |
| harmony by recording | 0.0463 | 0.0501 | 0.92 |

**No arm passes.** The gate wanted the recordist lift halved with species held, and every
arm that halves the one halves the other.

Three findings, in order of how much they change the picture.

**The confound is not a location shift.** Subtracting each recordist's mean leaves the
recordist lift *higher* than it started (0.1665 to 0.1687) while costing a third of the
species structure. Adding the scale term barely helps. Whatever marks a recordist in
this embedding, it is not an offset and not a per-dimension gain — which is a
mechanistic explanation for why §17.3 and §17.5 failed, and it was never available
before, because both of those attacked the confound during training where nothing can be
inspected.

**Harmony reaches it and pays §17.3's price exactly.** The one non-linear arm cuts the
recordist lift 71 % — the first half of the gate, which nothing else managed — and cuts
species 70 % with it. That is the same one-for-one trade docs/17 §17.3 measured for the
adversarial head, obtained post-hoc, with no training, by a completely different method.
Two unrelated mechanisms landing on the same exchange rate is evidence about the data
rather than about either mechanism.

**Correcting by recording removes both because they are nearly nested.** A recording
normally holds one bird of one species, so the recording label almost implies the species
label, and a correction that flattens recordings flattens species. This is a statement
about how the corpus was collected, not about the embedding.

**Read together with §17.3 and §17.5, the road is closed at three ends** — during
training with an adversarial head, during training with a factored target, and post-hoc
with the genomics toolkit including its strongest member. The reason is now visible:
species and recordist are **confounded in the sample**, not merely in the model. Most
species in this corpus are carried by a handful of recordists, so no method that only
sees the embedding can separate labels the data never separated.

That promotes §17.4's "invariance is a data action" from a conclusion to a boundary, and
it names the specific action: **more recordists per species**, which is the same
prescription AVEX reached from the other direction with more domains per species. It also
raises the value of W6's T1, which asks whether a model trained on the same archives at a
hundred times the scale escapes the same trap.

## 23.2 W2 — Model-free sequence statistics

**The failure.** Every syntax test so far fits a model and compares. P1 kept first
order. P2's kernel lost to bag-of-types. The rhythm term cost lift. Those results answer
"does this model beat that one". None of them answers "is there structure beyond first
order at all", and none of them tests whether the **type inventory** is a real unit
system rather than a convenient clustering.

**What has not been tried.** The model-free tests quantitative linguistics and animal
communication research use on exactly this question:

- **Menzerath–Altmann law** — longer constructs have shorter constituents. Tested in
  primates, whales, dolphins and birds. It is a falsification test of the inventory
  itself: arbitrary clusters have no reason to obey it, real units often do.
- **Predictive information / excess entropy scaling with block length** — how much the
  past tells about the future as the block grows. It separates random from Markov from
  hierarchical long-range structure **without fitting a model**, which is precisely the
  question the bake-off could not ask.
- **Normalised compression distance** — model-free sequence similarity from
  compressibility. The other classic baseline a learned song encoder must beat, and the
  one P2 left out.

**Gate.** These are descriptive, so the gate is a control, not a threshold: each
statistic must separate the real corpus from its own permutation null (tokens shuffled
within species, bout lengths and marginals kept — docs/12's control). A statistic that
the shuffled corpus reproduces says nothing about birds.

**Cost.** One afternoon on 34 696 bouts. No new data, no network, no GPU.

**Why it goes early.** If the inventory fails Menzerath, every song-level encoder built
on those tokens is built on sand, and P2/P3 should be re-aimed before anyone writes one.
If it passes, the roadmap gains its first evidence that the units are units.

### 23.2.1 Result, 2026-08-01 — run on the production corpus

`seqstats.py`, 34 696 bouts, 327 164 tokens, 2 421 species, against docs/12's control.

| statistic | real | control | reading |
|---|---|---|---|
| Menzerath exponent, median | **+0.019** | +0.051 | the law does not hold |
| species with a negative exponent | 45.7 % | 8.5 % | a weak effect in the right direction |
| NCD, across minus within | 0.018 | **0.038** | adds nothing |
| H(next given 1 previous) | **0.941 bits** | 3.343 | very strong first-order structure |
| H(next given 3 previous) | 0.435 | **0.293** | the control has fallen below the real |

**What holds.** The tokens are not arbitrary. 0.941 bits against a shuffle's 3.343 is
not a subtle effect, and it is the question behind "are these units" answered in the
affirmative. Whatever `learn_types` cut out, the sequences built from it are strongly
predictable at first order.

**Menzerath does not hold here.** The median exponent is positive. The share of species
with a negative one is 45.7 % against the control's 8.5 %, so there is something in the
law's direction, but this corpus does not look like the primate and cetacean results.
Note also that the *control* has a consistently positive exponent, which is a sampling
artefact and not a finding: a mean over more draws sits closer to the species mean, and
a log of it rises with the count. That artefact is exactly why the control is run.

**NCD is refuted.** The control separates species *better* than the real corpus does.
Compression distance here reads alphabet and marginals, which the shuffle preserves, and
not order. No learned song encoder should be measured against it.

**The second-order arm was a badly designed test, and it is being recorded as one.**
The pre-registration compared the k=1 to k=2 drop between real and control. That is not
a test: the curves start 2.4 bits apart, so the control drops further for the trivial
reason that it has more entropy to lose, and past k=3 its curve falls *below* the real
one because a plug-in estimator on shuffled tokens reports near-unique contexts as
determined. Both effects are bias. `_verdict` now refuses the comparison and says so
rather than returning the answer it would have returned. **The honest instrument for
this question is the held-out cross-entropy the docs/18 bake-off already used**, which
is unbiased by construction — so P1's verdict stands, and this arm needs re-running with
that estimator rather than with this one.

**Consequence for the roadmap.** The premise of P2 and P3 survives: the tokens carry
real sequence structure. What does not survive is the hope that a model-free statistic
would settle the depth question cheaply. The re-run with the unbiased estimator is
§23.2.2, and it answers the question in the negative.

### 23.2.2 The second-order arm, re-run with the unbiased estimator — NO STRUCTURE FOUND

§23.2.1 retracted its own second-order test and named the instrument that could answer
it. This is that re-run. `seqstats.held_out_scaling` + `syntax.MarkovOrder`: per species,
the docs/18 bake-off's own 80/20 **bout** split, a k-order backoff model fitted on the
train half for k = 0…3, every held-out token scored, cross-entropy in bits per token.
Same corpus as §23.2.1 to the token (34 696 bouts, 327 164 tokens, 2 421 species — the
loader is pinned against `learn.bout_sequences` and fails if the bout rule drifts), same
docs/12 control. 217 species clear the bake-off's 20-bout bar.

**Pre-registered before the run** (`HELD_OUT_GAIN_BITS`, `HELD_OUT_SHARE_POINTS`): the
median species must gain ≥ 0.05 bits/token from order 1 to order 2, gain ≥ 0.05 more than
its own shuffle, **and** the share of species gaining at all must beat the control's share
by ≥ 20 points. All three, or the arm returns false.

| | real | control |
|---|---|---|
| held-out CE, k = 0 (unigram) | 3.284 | 2.879 |
| k = 1 | **2.301** | 3.634 |
| k = 2 | 2.546 | 4.868 |
| k = 3 | 2.866 | 5.313 |
| median gain, order 1 → 2 | **−0.091** | −0.912 |
| species gaining at 1 → 2 | **25.3 %** | 4.1 % |
| median gain, order 2 → 3 | −0.108 | −0.187 |

**The gate fails, at three seeds.** The magnitude criterion fails and the share criterion
passes, at every split drawn (real gain −0.091 / −0.116 / −0.142, share 25.3 / 24.9 /
24.4 %; control share 4.1 / 3.7 / 3.7 %). For the median species a second-order model is
**worse on bouts it has not seen** — the corpus cannot estimate the contexts it asks for.
Read as one sentence: *there is no second-order structure this corpus can support, and a
quarter of species hint at one.* 25.3 % against a shuffle's 4.1 % is a six-fold rate and
clears the pre-registered 20-point margin, so the hint is not nothing; it is also not what
the gate asked for, and the gate was written first.

**The first-order result is now much stronger than §23.2.1 could state.** Order 1 buys
**0.98 bits/token** on held-out bouts (3.284 → 2.301) while on the shuffle it *costs*
0.75 (2.879 → 3.634). An unbiased estimator paying for parameters it cannot use is the
clean form of "these tokens are units": the model can only win if the transitions are
real, and it wins by a bit per token.

**Two properties of this estimator that the plug-in one lacked**, both visible in the
control column: the control's curve *rises* with k instead of collapsing below the real
one, because sparsity is now punished rather than rewarded; and the same behaviour is
pinned in `seqstats.self_test`, where a planted second-order process must be found, a
first-order process must not show depth, and the shuffle of the planted process must not
gain from a longer context.

**One artefact worth naming.** The control's k = 0 sits *below* the real corpus (2.879
against 3.284). The shuffle spreads each species' tokens evenly across its bouts, so train
and test marginals nearly coincide; real bouts are clumped — a bout tends to repeat one
type — so a held-out bout can be mostly a type the train half barely saw. That clumping is
itself structure, and it is why the gate reads *within-corpus* deltas rather than the two
absolute curves against each other.

**What this settles for the roadmap.** P1's verdict stands and is reinforced: first order
is what this corpus supports. P2/P3's premise — that the tokens carry real sequence
structure — is confirmed by the 0.98-bit gain. What is now measured rather than assumed is
that **the depth question is data-limited, not method-limited**: 217 of 2 421 species have
enough bouts to ask it at all, and the 25 % that hint at second order are the argument for
P0-style depth on *more* species rather than for a cleverer sequence model.

## 23.3 W3 — Fitting the syrinx by inference, not by search

**The failure.** docs/21's verdict is that the model is correct and the fit is what
fails. docs/19 measured the fit objective's correlation with audible distortion at
r ≈ 0.1. The blended objective failed adoption at n = 80 (§19.5). Through all of it the
*method* went unquestioned: a search over parameters, scored by one scalar.

**What has not been tried.**

- **Simulation-based inference** (neural posterior estimation). The situation — a good
  mechanistic forward simulator, and parameters wanted from data — is what astrophysics
  and computational neuroscience built SBI for, and it is the standard tool there for
  mechanistic ODE models. It returns a **posterior** per syllable rather than a point.
  That matters beyond tidiness: a fit that parks at a noise ceiling is the signature of
  a degenerate likelihood, and a posterior shows degeneracy where a scalar hides it.
- **Differentiable DSP.** Make the render chain differentiable, or train a surrogate
  network to emulate it, so gradients flow from a multi-resolution spectral loss to the
  synth parameters. Then the audible objective docs/19 asked for becomes the thing that
  is optimised rather than the thing measured afterwards.

**Gate.** On the docs/19 bench, not on the cosine: median MCD improvement over the
current fit on a held-out set of types, with the resynthesis cosine held as a guardrail
(the §19.4 shape). A pilot on one species first, because a method that cannot beat
coordinate search on one bird will not beat it on 2 423.

**Cost.** Days, and it is the only workstream here that is a research programme rather
than an experiment.

## 23.4 W4 — Function without playback

**The failure.** Playback is the only proof of function, there is no playback, so the
interface correctly says "real acoustics, no documented function" for almost everything.
That is honest and it is also a ceiling the corpus cannot lift, because every recording
is one bird with no interaction and no receiver.

**What has not been tried.** Two routes that are not playback and not invention:

- **Weak labels from the metadata already in the store.** Xeno-canto records carry
  behavioural annotations — call, song, alarm, flight call — plus date and location.
  Programmatic-supervision methods from machine learning (label models over noisy
  sources) turn those into a graded function signal with an explicit noise model.
  Nothing in the pipeline reads them today.
- **Cross-species convergence.** Motivational-structural rules predict that alarm calls
  converge in acoustic form across species. `relations.json` holds 6 441 cross-species
  pairs and the inventory holds 44 documented functions. Do convergent pairs share
  function more often than chance?

**Gate.** For the weak labels: held-out agreement with the 44 documented functions,
above the marginal-frequency baseline. For convergence: a permutation test over the
species-pair graph. Either way the output ships as a **candidate with a share**, never
as a function — §8.5 is not relaxed for this.

**Cost.** Days. No network for the convergence test.

## 23.5 W5 — Stop contaminating the analysis space

**The failure, measured 2026-08-01** (docs/22 §22.6). The critic is trained with realism
as its leading term. The galaxy is then built in that space out of both real and
synthetic points, so the map's geometry depends on how good our synthesiser is. Every
learned type splits into two seeds, the cap binds at twice the type count, and 12 879
types lose their only knot. Deflating the axis fails: it removes 42 % of the space's
energy, drives the source mean gap to exactly 0.0, and every type still splits.

**What the measurement says to do.** Give a type with member observations no synthetic
point at all. It already exists in the map as the real syllables `typing.json` assigned
to it. Measured: seeds per type exactly 1.000, purity 0.423 to 0.577, coverage 0.432,
on 25 % fewer points.

Beyond that, the same measurement points at the vote itself. 96 % of points carry a type
by construction, so the build discards a label it holds and re-derives it by
point-count majority over a partition. At production scale the honest form is to assign
labelled points to their own type and cluster only what has no label — which also
removes the k-means cost that the raised cap re-introduces.

**Gate.** Type coverage, cluster purity, and the count of documented calls that keep a
knot, measured on a subset **chosen to contain authored species** — the debug-100 corpus
is the deepest hundred and holds none, which is why today's documented-knot column reads
zero in every arm and proves nothing either way.

**Cost.** The first half is a flag that already exists. The second half is a build-side
change of a few hundred lines.

## 23.6 W6 — A pretrained bird embedding as a second opinion

**The failure.** Two of them, and they are the same failure seen from two sides. The
recordist confound survived every attempt to train it away (§17.3, §17.5). And the map's
own space is contaminated by our synthesiser, because the critic's leading loss term is
realism and the galaxy is then built in that space out of both kinds of point (docs/22
§22.6). Both say the analysis space is doing a job it was not designed for.

**What has not been tried.** BirdNET is an open bird classifier trained on the same
archives as this corpus, at roughly a hundred times the scale. Its code is MIT and its
models are CC BY-NC-SA 4.0 — non-commercial, which the owner has accepted for research
use (2026-08-01). Three properties matter here:

- a 320-d embedding taken from the second-to-last layer, at 3-second resolution;
- **no realism term anywhere in it** — it was never trained to tell our resynthesis from
  a bird, so it cannot encode the axis that splits every type into two seeds here;
- a species-occurrence meta-model over latitude, longitude and week of year, which is a
  kind of prior this pipeline has nothing equivalent to.

**The boundary, stated so nobody expects more.** BirdNET is species-level at 3 seconds.
This project is syllable-level at 20 ms to 2 s with a physical synthesiser. So it can
improve *which bird, is this new, where and when*, and it can say nothing about what a
sound is made of. It does not touch the syrinx model, the typing, the grammar, the knot
budget or the song funnel.

**Gate, stated before the run.** Three read-only tests on the fixed store, through
`geometry.measure` and its permutation null — no training, no new data:

- **T1** recordist lift and source lift in the BirdNET space against the critic space.
- **T2** novelty AUC against the critic's 0.846 / TPR 32.2 % at 5 % false positives.
- **T3** species retrieval lift against the critic's 0.513.

T1 is the whole bet. Note what it can return: BirdNET has never seen synthetic audio
either, and out-of-distribution input often clumps on its own, so a *higher* source lift
is a real possible outcome and not a bug.

**A negative result is the valuable one.** If a model trained on the same archives at a
hundred times the scale is no more recorder-invariant than ours, the confound lives in
the archives rather than in our critic, and the question §17.3 and §17.5 both failed to
close is closed — by measurement, from the outside.

**What it would let go of, if T1 and T3 land.** The critic's species head exists to stop
the embedding being about our synthesiser (docs/09 §9.2b); a grounded external space
makes that term redundant and collapses the critic to the realism head the fit actually
consumes. Perch's 409 MB ONNX port may also become redundant at a tenth the size.

**Implementation.** The Perch pattern of AGENTS.md exactly: optional extra, lazy import,
model in a gitignored local directory, **labels are metadata and never typing ground
truth**, nothing ships to the browser. Practical check first — BirdNET ships TFLite and
this repo deliberately carries no TensorFlow, so it is `tflite-runtime` or an ONNX
export. Two embeddings are worth writing, not one: **per recording** (a session and
channel descriptor computed independently of our own features, which is what W1 wants as
its batch representation) and **per syllable** (the 3-second window centred on it, which
gives a syllable descriptor with context that neither the 28-d nor the critic space has).

### 23.6.1 T1 run with Perch instead of BirdNET, 2026-08-01 — THE CONFOUND SURVIVES

**Why Perch and not BirdNET.** T1 turns on two properties: a model trained on the same
archives at roughly a hundred times our scale, and **no realism term anywhere in it**.
Perch 2.0 has both, and it is already ported here — `perch.py`, a community ONNX export,
1536-d at the second-to-last layer, 5 s windows at 32 kHz. So T1 could be asked today
instead of after a BirdNET port, and if the answer is "no better", the port is not the
next thing to build. BirdNET keeps its own reasons (the occurrence prior over latitude,
longitude and week; a third opinion at a tenth the size), and this does not replace it.

**What was measured.** One point per recording, which is what §23.6 says W1 wants as its
batch representation and which has a property the syllable-level test had to block for:
two points from the same recording cannot exist, so same-recording leakage is impossible
by construction rather than by exclusion. Perch's point is the mean of the first six 5 s
window embeddings; the critic's is the mean of that recording's syllable embeddings from
`embeddings.f32`. Both scored by `geometry.measure` against its own permutation null, the
same estimator W1 used, on the same rows.

Population: the audio cache is the constraint and it turns out not to bind — all 6 453
cached iNat recordings carry a recordist (1 836 distinct), so no new harvest was needed.
Selection was fixed before the run: recordists with ≥ 8 cached recordings, at most 20 each
(seeded), capped at 2 000. That gave **1 567 recordings, 135 recordists, 1 341 species**,
coverage 0.907 in both spaces.

| space | dims | recordist lift | species lift |
|---|---|---|---|
| critic 32-d | 32 | **0.0891** | not estimable here |
| Perch 1536-d | 1 536 | **0.0744** | not estimable here |

**T1 fails: −16.5 % against a −30 % gate.** A model trained on the same archives at a
hundred times the scale, which has never been asked to tell our resynthesis from a bird
and therefore cannot have learned the axis that splits our types in two, still carries
**five sixths** of the recordist structure our own critic carries. §23.6 said in advance
what that means, and it is worth quoting rather than softening: *if a model trained on the
same archives at a hundred times the scale is no more recorder-invariant than ours, the
confound lives in the archives rather than in our critic.* It does. §17.3 closed the road
during training, §17.5 closed it with a factored target, §23.1.1 closed it post-hoc, and
this closes it **from outside our own loss function entirely** — the fourth end, and the
first one that could not be blamed on anything we built. The action §17.4 named is now the
only action left: more recordists per species, in the data.

**One honest limit on this population, and it is not a selection mistake.** No species
reaches `geometry.MIN_GROUP` = 8 recordings here (1 341 species over 1 567 recordings), so
the species half of the T1 gate could not be estimated. Re-drawing for species replication
returned **zero** recordings, and the reason is structural: **the audio cache holds at most
two recordings per species** — 2 616 species with exactly two, 1 221 with one, none with
three. The iNat ingest took no more than two apiece, and the xeno-canto audio was deleted
at harvest by design. So an 8-recording species group does not exist on any audio this
machine holds, and no selection rule can produce one.

That is worth stating as a constraint on the whole workstream rather than as a footnote to
one run: **any test in W6 that needs several recordings of one species needs audio to be
re-fetched first**, which is an owner-called network step. What the cache does support is
the pair test — with `min_group=2`, is a recording's nearest neighbour from its own species?
— and `geometry.measure` allows exactly that, keeping `min_group` for callers testing a
small population deliberately, where the permutation null rather than the group size is
what keeps the test honest. §23.6.2 runs it.

### 23.6.2 T3, and T1 on a second draw — Perch wins species 8x, and the two draws disagree

The pair test §23.6.1's constraint forces: 958 species with two cached recordings each,
1 644 recordings, 760 recordists, `min_group=2` for species and the usual 8 for recordist.
Same estimator, same per-recording representation, same rows in both spaces.

| space | dims | species lift (cov 0.834) | recordist lift (cov 0.329) |
|---|---|---|---|
| critic 32-d | 32 | 0.0074 | 0.1684 |
| Perch 1536-d | 1 536 | **0.0588** | **0.1155** |

**T3 passes, and not narrowly: Perch retrieves a species' other recording 8x better than
our critic does** (0.0588 against 0.0074, same rows, same null). One caveat belongs with
that number rather than after it: the critic's embedding is a *syllable* space being
averaged over a recording, which is not what it was fitted for, so this says Perch is the
better **per-recording** space — the representation W1 wants as its batch descriptor — and
it does not say Perch beats the critic syllable for syllable. That comparison has not been
run.

**T1 passes here (−31.4 %) and failed in §23.6.1 (−16.5 %), and the disagreement is the
result.** The two draws hold different things constant, and the tie-break is coverage:
§23.6.1's population was built for this question and its recordist estimate covers **0.907**
of rows; this one was built for species and covers **0.329**, because only a third of these
recordings belong to a recordist with eight of them. The instrument designed for the
question is the one to believe, so the honest verdict on T1 is **fail** — Perch reduces the
recordist structure by something between a sixth and a third, and does not remove it.

**The finding that holds in both draws, and is the one to carry forward.** In the Perch
space the recordist lift (0.1155) is still **twice the species lift** (0.0588). A model
trained on the same archives at a hundred times our scale, which has never been shown a
resynthesis, still encodes *who recorded it* more strongly than *which bird it is*. That is
the confound stated without reference to anything this project built, and it is the fourth
independent closure of the road §17.4 opened.

**What this does and does not license.** It licenses Perch as the per-recording batch
descriptor for W1 (better species structure, weaker recordist structure than ours) and it
weakens the case for building the BirdNET port to answer T1 — T1 is answered. It does not
license retiring the critic's species head, which §23.6 made conditional on T1 *and* T3
landing: T3 landed, T1 did not. And it leaves T2 (novelty AUC) unrun.

## 23.7 W7 — Mimicry as ground truth

**The failure it attacks.** Every cross-species similarity claim this project makes is
judged against a permutation null, because there is no ground truth for "these two
species' sounds are alike". `relations.json` ships 6 441 such pairs as candidates and
says so. The same gap makes docs/19's problem unfixable from inside: we have no measure
of audible fidelity that does not come from our own metric.

**What has not been tried.** Vocal mimics supply both, from outside.

- **A mimic is a labelled cross-species similarity.** A lyrebird singing a grey
  shrike-thrush produces syllables whose acoustics are shrike-thrush and whose label is
  lyrebird. That is ground truth nature produced, and it tests directly whether our
  embedding encodes acoustic form or species identity.
- **The accuracy has been certified by the receiving birds, not by us.** Dalziell and
  Magrath used playback bioassays: shrike-thrushes responded to lyrebird imitations as
  strongly as to conspecific song. Mimic and model recordings are therefore pairs known
  to be *perceptually equivalent to the animals concerned*. That is a fidelity yardstick
  for the docs/19 bench which owes nothing to our synthesiser or to our cosine.
- **A note for docs/21.** Lyrebirds have three pairs of syringeal muscles where
  songbirds typically have four, and whether that simplification helps mimicry is
  explicitly unknown. The most accurate imitator known has the *simpler* apparatus,
  which argues the expressive bottleneck is the control signal rather than the
  oscillator — the bet W3 already makes, now with an animal behind it.

**Pilot, run 2026-08-01, and it is a data verdict.** The store holds **31** lyrebird
syllables (the 221 and 33 in `seenPerSpecies` are records seen, not syllables kept).
Against the 12 393 type centroids of the production fit, those 31 syllables match **13
distinct non-lyrebird species** where random syllables of the corpus match 29.9 (sd
1.0) — concentrated, in the direction mimicry predicts. Two of the top matches,
`philemon_citreogularis` and `haliastur_sphenurus`, are Australian species that co-occur
with lyrebirds and are plausible models. The rest are Neotropical and African and cannot
be mimicry. At n = 31 this is a well-formed test with an empty corpus, and the
"nearest centroid is its own type" figure of 83.9 % is circular by construction, since
those syllables are inside those centroids.

**The action is a targeted harvest, not a method.** Xeno-canto's lyrebird recordings
frequently name the mimicked species in the remarks, so the harvest returns *labelled*
mimic-to-model pairs. Other mimics — mockingbirds, starlings, marsh warblers, drongos —
extend the same set.

**Gate.** With a corpus of a few hundred mimetic syllables and their named models: the
share whose nearest non-conspecific type belongs to the named model species, against the
null of a random species drawn from the same geography. And, for the fidelity half, the
resynthesis metric's ordering of mimic-versus-model pairs against the published
behavioural equivalence.

## 23.8 Order, and why

1. **W2**, because it is an afternoon and it can refute the premise of the whole syntax
   roadmap before more is built on it.
2. **W1**, because it is hours and it attacks the most-recorded failure in the project
   with a method the project has never tried.
3. **W5**, because the measurement is already done and what remains is a decision.
4. **W6**, straight after W1: it runs on the same fixed store through the same battery,
   and its T1 either explains W1's result or replaces it.
5. **W4**, because it is the only route to function this corpus can support.
6. **W3**, because it is the largest and it should start after W2 says what the units
   are.
7. **W7** whenever a harvest is being run anyway: it costs a species list, and it is the
   only ground truth for cross-species similarity this corpus can obtain.

One heavy job at a time (AGENTS.md). W1 and W2 are read-only against a fixed store and
can share a session with anything else.
