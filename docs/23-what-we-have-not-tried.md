# 23 — What we have not tried

A plan written from the failures, not from the roadmap. Every workstream below names
the measured failure it attacks, the method, the gate stated before the run, and what a
negative result would mean. Methods are taken from fields that solved the same problem
on other data. Birdsong is the subject here, not the boundary of the reading list.

The order is by cost over payoff, not by ambition. Two of the five need no new data, no
network and no training run.

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

## 23.6 Order, and why

1. **W2**, because it is an afternoon and it can refute the premise of the whole syntax
   roadmap before more is built on it.
2. **W1**, because it is hours and it attacks the most-recorded failure in the project
   with a method the project has never tried.
3. **W5**, because the measurement is already done and what remains is a decision.
4. **W4**, because it is the only route to function this corpus can support.
5. **W3**, because it is the largest and it should start after W2 says what the units
   are.

One heavy job at a time (AGENTS.md). W1 and W2 are read-only against a fixed store and
can share a session with anything else.
