# 9. Plan: learn the syllables, recognise new ones, and get a better objective for free

**Status: built and measured. §9.7 has the results, and they are not the ones this document
expected — read that section before acting on anything below it.** In one line: the learned
embedding works and the learned objective does not. Everything from §9.1 to §9.6 is left as
written, because it is the hypothesis that got tested and the refutation is only legible next
to it.

Read §8.1a–c of `08-implementation.md` first; this document assumes it.

**The goal, in one sentence: learn what a syllable is from the ones we have, so the system can
recognise ones it has never heard.** Everything else here serves that. §9.2b is the primary
work; §9.3 Part 1 falls out of it for free and happens to fix a second problem, which is that a
day of measurement converged on our *objective* — how we score closeness to a real bird — being
what limits realism, not the synthesiser.

Note on what exists today: **there is no neural network anywhere in Birdy.** Analysis is
hand-written numpy (`features.py`, `learn.py`); the only machine learning is KMeans/HDBSCAN for
clusters and UMAP/PCA for the 3D projection. This would be the first learned component, and it
belongs in *representation and scoring*, never in generation.

## 9.1 Why. Five results, all pointing the same way

Everything below was measured on the 39 976-syllable harvest, with the pipeline's own
verification (`learn.learn_species` → `resynthesisCosine`, `nearestOwn`).

Where the synthesiser got to: median resynthesis cosine **0.533 → 0.775**, types above 0.7
**26 % → 66 %**, buzz-class species **0.438 → 0.780**. Those are real gains and they came from
§8.1a (absolute formants, turbulence, tension noise, `gammaScale`, fittable tract Q).

Where it did **not** get to: `nearestOwn` **species** stuck at **23.1 %** against 4.5 % chance.
Three quarters of fitted syllables still resynthesise closer to a *different* bird than to their
own. That is the audible complaint — "a lot of them sound similar" — and five separate attempts
failed to move it:

1. **Envelope collapse.** Refuted: we produce 103 % of the real between-species mel-envelope
   spread and 106 % of the within-envelope detail. Variety is not lacking.
2. **Global spectral tilt.** Real recordings sit at −1.59 relative energy above 6 kHz, we sit at
   −0.01. Correcting it *exactly* dropped placement 23.1 % → 20.2 %. Every roll-off hurt.
3. **Missing harmonic structure.** Real syllables resolve to a mean of **2.2 partials**;
   feeding measured partial amplitudes to the fit moved cosine 0.776 → 0.768.
4. **Objective too coarse.** A time-resolved 4×26 log-mel target improved *its own* metric 36 %
   (3.67 → 2.33) and dropped 28-d placement 61.7 % → 43.2 %. **The two objectives conflict.**
5. **The tract structure.** The f0-tracking band is provably rigid — relative partial gains vary
   1.3× across a 5.7× change in f0, versus 32× for a fixed waveguide. Swapping it improved all
   three metrics on five species (placement 61.7 % → 67.9 %) and was a **regression** over 22
   species (23.1 % → 22.2 %), so it is gated off in `fit_species_tube`.

Result 5 is the decisive one. A structurally better tract, scored by our objective, loses.
Scoring it per species instead of per type tripled adoption (68 → 196 types) and still lost. So
the objective is not merely a weak proxy — **it actively rejects improvements.** Every remaining
idea will be judged by it, so it has to be fixed first.

## 9.2 What is wrong with the objective, precisely

`learn._score` renders a candidate and returns a cosine in a 28-dimensional space
(`features.descriptor`: 13 MFCC means, 13 MFCC standard deviations, log centroid, flatness),
standardised in the harvest population frame. Three structural problems:

- It is a **time average**. A syllable that sweeps and one that holds still with the same mean
  score identically. Result 4 shows that fixing this naively trades one blindness for another.
- Its spectral part is **13 smoothed cepstral coefficients** — a heavy lowpass on the spectrum.
- It is simultaneously the fit's **objective and its only evidence**. A median cosine of 0.775
  therefore means the fit has largely saturated what the vector can express, which is not the
  same as sounding right.

A hand-designed distance keeps failing because nobody knows the right one. **Learning it from
data is what a discriminator is for.**

## 9.2b The primary goal: learn the syllables we have, then recognise new ones

**This is the point of the exercise**, and the good news is that it is the *same network*. A
discriminator trained on syllables produces, in its penultimate layer, an embedding of "what a
syllable is" learned from data. That embedding is the deliverable. The realism logit in §9.3
Part 1 is a by-product of getting it.

What it replaces. Today, syllable identity is decided by seven hand-written numbers —
`learn._observation_vector`: three pitch samples, log duration, an AM term, flatness × 6 and
harmonic × 3, with hand-chosen weights. KMeans on that is what defines a "syllable type", and
`choose_k` picks the count by silhouette. Everything downstream depends on it: the fitted
repertoire, the measured grammar, the galaxy's clusters, the trajectory the visualisation draws.
Seven hand-weighted numbers is a thin basis for all of that, and the weights (`* 6.0`, `* 3.0`)
were guesses.

**Three uses of one network, in dependency order:**

1. **A learned syllable embedding** (say 32-d) replacing `_observation_vector` for typing.
   Cluster in the embedding instead. Expect better-separated types, and expect `choose_k`'s
   silhouette to become meaningful rather than a proxy fitted to guessed weights.
2. **Novelty detection — "is this a syllable I have not heard?"** With the embedding in hand
   this is a distance question: a new syllable is one whose embedding is far from every known
   type centroid, or whose critic score is out-of-distribution. Threshold on the held-out
   distance distribution, so the false-positive rate is *chosen* rather than discovered. This is
   what lets the app say "this bird just sang something new" instead of silently assigning it to
   the nearest existing cluster — which is what happens today, and is why a genuinely novel call
   currently lights the wrong knot in the galaxy.
3. **The realism objective** (Part 1 below), which is the same forward pass read at the logit.

**Train it multi-task, not purely real-vs-fake.** A critic trained only to separate real from
synthetic learns whatever distinguishes those two sets — possibly the mp3 artifact (§9.5) — and
that is a poor basis for judging whether two *real* syllables are the same type. Give it three
heads on a shared trunk:

- **real / synthetic** (the realism logit),
- **species identity** over the known species (supervised — the harvest already labels every
  syllable with its species),
- **contrastive**: two augmented views of the same syllable patch should embed close together,
  two different syllables apart. Augment with small time stretches, gain changes and added
  noise — *not* pitch shifts, since pitch is genuinely type-diagnostic here.

The contrastive head is what makes the embedding useful for typing and novelty, because it is
trained on real syllables against each other rather than against our synthesis. The species head
grounds it in something externally true. Weight the three losses and sweep.

**How to know it worked**, in order of directness:

- **Typing:** refit with embedding-based clustering. `nearestOwn` type should rise from 56.5 %.
- **Novelty, honestly measured:** hold out entire species from training, then check that their
  syllables are flagged novel. Report the ROC — a novelty detector with no false-positive curve
  is a claim, not a measurement. This is the number that says whether "identify new ones" works.
- **Grammar stability:** the ids must stay meaningful across refits (`learn.assign_ids` exists
  precisely because renumbering silently broke the galaxy once). An embedding change renumbers
  everything unless the id-inheritance path is respected.

**Honesty rule (§8.5) still applies, and it gets sharper here.** A syllable the network flags as
novel is `unlabelled`: real acoustics, no documented function. Detecting that a sound is new is
not the same as knowing what it means, and the interface must keep saying so.

## 9.3 The plan, in two parts

### Part 1 — Discriminator as the objective (do this first)

A small CNN learns to tell real syllables from our resyntheses. The fit then maximises its
confusion. This replaces the *metric*, not the synthesiser: the physics, the parameter vector,
the galaxy and the grammar are all untouched.

**The data problem, and its solution.** A discriminator needs real spectrograms, and the harvest
deletes audio by design (`harvest.py` decodes → describes → deletes; peak memory is one
recording). Do **not** change that. Instead retain a **log-mel patch** per syllable — a fixed
`32 × 26` grid of log-mel energies, resampled onto the syllable's own duration, mean-centred.

- This is a measurement, not a recording. 832 numbers, log-magnitude only, no phase: you cannot
  reconstruct recognisable audio from it, so the licensing and "keeps no audio" properties hold.
- Cost at `float16`: ~1.6 KB per syllable, ~65 MB for a 40 k store. Acceptable. Quantise to
  `int8` over a fixed dB range if it needs to be smaller.
- `features.mel_path` (§8.1a, already written) is exactly this at `knots=4`. **Reuse it with
  `knots=32`** — do not write a second spectrogram path, or real and synthetic will be measured
  differently, which is the one bug that would invalidate the whole exercise.

**Steps.**

1. `features.py`: nothing new needed. Confirm `mel_path(audio, knots=32)` behaves; add a
   `self_test` case asserting a sweeping tone and a steady tone differ, and that identical input
   gives distance 0.
2. `learn.py` `SyllableObservation`: add `mel_patch: list[float]` (832 floats, rounded to 2 dp
   or `float16`). Populate in `extract_syllables` beside the existing `mel_path`.
3. Re-harvest into a **new** store (`out/harvest-gan`). Never delete `out/harvest` — it is
   39 976 observations gathered under xeno-canto rate limits and is the only copy. Five species
   already exist in `out/harvest-mp` if a fast loop is wanted first.
4. New module `pipeline/src/birdy_pipeline/critic.py`:
   - `uv add torch` (CPU is enough at this scale; ~1–3 M parameters).
   - Architecture: 4 conv layers on the `1×32×26` patch → global pool → 1 logit. Spectral
     normalisation on every conv, so the critic stays Lipschitz and its gradient is a usable
     distance rather than a cliff.
   - Train: real patches (label 1) vs patches rendered from the *current* fitted inventory
     (label 0). Binary cross-entropy or a hinge loss.
   - **Hold out species**, not syllables. A critic that has seen every species can memorise
     which bird is which and will report identity rather than realism.
5. Expose `critic.realism(patch) -> float` and add it to `learn._score` as a weighted term
   alongside the existing cosine:
   `score = (1 − w)·cosine + w·realism`, `w` swept over `{0, 0.25, 0.5, 0.75, 1}`.
   Keeping the cosine term is a guardrail: it is a metric the critic cannot game.
6. **Alternate.** Refit with the critic, retrain the critic against the new resyntheses, repeat
   2–3 rounds. One round proves nothing — a critic beaten once will find a new tell.

**How to know it worked.** These are the numbers to beat, all on `out/harvest`, 22 species:

| metric | current | target |
|---|---|---|
| nearest own **species** | 23.1 % (chance 4.5 %) | **> 35 %** |
| nearest own type | 56.5 % | ≥ 56 % (do not regress) |
| median resynthesis cosine | 0.775 | ≥ 0.74 (a small loss is acceptable here) |
| median \|F0 error\| | 3.8 % | ≤ 5 % |

A rise in species placement *with* the cosine roughly held is the win condition. A rise in
placement with the cosine collapsing means the critic is being gamed — check by ear.

**Then, immediately: re-enable the waveguide.** `fit_species_tube` is written, tested and gated
off in `learn_species` because the old objective rejected it. It is the cleanest available test
of whether the new objective is actually better: the waveguide is known to be structurally
right (32× vs 1.3× spectral freedom) and known to win in isolation. If a learned objective still
rejects it, the objective is not fixed.

### Part 2 — Neural encoder for the inverse problem (after Part 1 works)

`invert_gestures` is coordinate descent over ~16 axes, three passes, a few hundred renders per
type. It cannot escape a bad basin and it only ever moves on an improvement. Replace it with an
amortised inverse: spectrogram → parameters, in one forward pass.

**Why this is unusually easy here: we own the forward model, so training data is free.** Sample
parameter vectors, render them with `syrinx.render_syllable`, compute the patch, and you have an
unlimited perfectly-labelled dataset. No audio retention, no annotation, no licensing.

1. Sample plausible parameters (contour, `dur`, `level`, `gammaScale`, `tractQ`, `noise`,
   `rough`, `tube`, `formants`), render, extract the patch. Aim ~200 k pairs.
2. Train a CNN regressor patch → parameters. Weight the loss by each parameter's audible
   effect; predict the contour in log-Hz.
3. Run it on real patches to initialise, then let coordinate descent (with the Part 1 objective)
   polish. Encoder for the basin, search for the last few per cent.

This is DDSP's architecture with our syrinx as the decoder instead of a learned one — which is
why it keeps the interpretability DDSP normally gives up.

## 9.4 Hard constraints — do not break these

- **No audio is retained.** Log-mel patches only. `harvest.py`'s decode → describe → delete
  loop is load-bearing for licensing (xeno-canto is largely CC-BY-NC-SA) and for peak memory.
- **No weights ship to the browser.** All training and inference is offline in `pipeline/`. What
  reaches the app is still a few dozen floats per syllable. The app must keep working with no
  Python process at all — see `PipelineClient`, where everything degrades to "not running".
- **The synthesiser stays physical.** The critic scores; it never generates. The galaxy, the
  grammar and every honesty label depend on a syllable being an interpretable parameter vector.
- **The two-sided contract stays verified.** `app/scripts/verify-parity.mjs` must stay at 12/12
  and `render-syllable.mjs` at 44/44. If a new synthesis parameter is added, add a parity case
  *and* check the ~20 ms tail, which is where a real click hid once.
- **Never delete `pipeline/out/harvest`.**

## 9.5 Risks

- **The critic learns "is it an mp3"**, not "is it a bird". xeno-canto is largely mp3, which
  lowpasses; our renders are not. Mitigate by matching bandwidth *before* the critic sees
  either side — lowpass both to 15 kHz — or the critic will win on a codec artifact and teach
  the fit nothing. This is the single most likely failure mode.
- **The critic learns species identity** rather than realism. Hence held-out species.
- **The fit games the critic.** Hence the retained cosine term, the alternating rounds, and
  listening to the output.
- **It works and sounds worse.** Possible, and the reason `--wav` output and human listening
  stay in the loop. Every metric here is a proxy; the ear is the arbiter.

## 9.6 If it fails

Two further items from the literature review, both structural and both cheaper than a GAN:

- **Inject `ẏ`, not `y`, at the tract input**, with the pressure envelope applied multiplicatively
  at the injection point. Every reference implementation in this lineage does this and we do not.
- **Replace the per-syllable envelope with a respiratory oscillator** — Fainstein, Goller &
  Mindlin, arXiv:2509.11019. Two coupled states, a Heaviside asymmetry between inflow and
  outflow, five parameters per species, and it generates attack shape, sub-syllable
  microstructure and *cross-syllable memory* that a designed envelope cannot. Likely the fix for
  onset realism and trill texture. Pairs with Hartley & Suthers 1989 (mini-breaths below ~30 Hz
  syllable rate, pulsatile expiration above it) — two regimes we currently model as one.

A generative GAN producing audio directly is **not** in this plan, deliberately. It has the
weakest realism evidence of any option (no bird-playback or neural-response validation, and the
field's own admission that there is no accepted quality metric), while the physical model this
project already uses has the strongest: wild territorial rufous-collared sparrows respond to it
indistinguishably from real song (Bistel, Amador & Mindlin, Phys. Rev. E 109:054410, 2024).
The discriminator is worth having. The generator is not.

---

## 9.7 Results: the embedding works, the objective does not

Everything above was implemented. `pipeline/src/birdy_pipeline/critic.py` is the network,
`features.mel_patch` is its input, `learn.typing_space` / `learn.RealismTerm` are the two
places it attaches, and `birdy-pipeline critic train` / `learn --embed-typing` /
`placement` are the commands.

**The measurement store is not the one in the table in §9.3.** `out/harvest` has no patches —
it was gathered before `mel_patch` existed and §9.4 forbids deleting it — so a fresh store
`out/harvest-gan` was harvested: 150 recordings, **9 041 syllables, 25 species**, every one
carrying a 32x23 patch. Its baseline is 26.6 % species placement rather than §9.1's 23.1 %,
so absolute numbers here are *not* comparable to the ones above. The ablation is, because
every row is the same store, the same critic and the same seed with one thing changed.

### What the critic itself learned

| head | measured | chance | reading |
|---|---|---|---|
| realism, species it trained on | AUC 1.000 | 0.5 | separates real from our resynthesis perfectly |
| realism, **species held out entirely** | **AUC 0.990** | 0.5 | the gap generalises; it is not species memorisation |
| species identity, held-back syllables | 0.917 | 0.053 | the embedding is grounded in something externally true |
| contrastive, retrieve own augmented view | 0.695 | 0.004 | out of 256 candidates |

The critic is *good*. That matters for reading the next table: what follows is not a network
that failed to train.

### The ablation, on `out/harvest-gan`

`species` is the headline number of §9.1 — does a resynthesis land nearest its own bird out
of 25. `cosine` is the guardrail the critic cannot touch, measured with the pure 28-d cosine
in every row.

| variant | types | species | own type | cosine | \|F0 err\| |
|---|---|---|---|---|---|
| baseline: hand typing, cosine objective | 346 | 26.6 % | 63.0 % | 0.762 | 5.4 % |
| + realism at `w=0.25` | 346 | 27.2 % | 52.3 % | 0.686 | 6.6 % |
| + realism at `w=0.50` | 346 | 23.7 % | 49.1 % | 0.655 | 6.5 % |
| + realism at `w=1.00` | 346 | 17.3 % | 22.0 % | **0.335** | 5.7 % |
| **learned-embedding typing** | 319 | **32.9 %** | **63.9 %** | **0.755** | **3.1 %** |
| hand typing + waveguide | 346 | 30.1 % | 57.5 % | 0.719 | 5.4 % |
| **learned typing + waveguide** | 319 | **37.0 %** | 58.3 % | 0.706 | 3.6 % |
| learned typing + realism `w=0.5` | 319 | 29.8 % | 56.7 % | 0.704 | 4.2 % |

**1. The realism objective is refuted, and it fails in exactly the way §9.5 predicted.** It
is monotonically harmful in `w`: every metric falls as the critic gets more of the objective,
and at `w=1` the cosine collapses from 0.762 to 0.335 while placement drops to 17.3 %. That
is "the fit games the critic", and the only reason it is visible is the retained cosine
term — §9.3's guardrail earned its place by catching the thing it was put there to catch.
`--critic-weight` therefore defaults to **0**.

So the diagnosis in §9.2 was wrong, or at least incomplete. The 28-d cosine is a weak proxy,
but a learned realism logit is a *worse* objective, and a critic at AUC 0.990 rules out "the
critic was not good enough" as the explanation. A discriminator that can tell real from
synthetic perfectly still cannot say which *direction* to move a syllable — being able to
separate two distributions is not the same as having a gradient that points at the nearer one.

**2. The learned embedding is a clean win, and it was §9.2b's primary goal all along.**
Typing in the 32-d embedding instead of `_observation_vector`'s seven hand-weighted numbers
moves species placement 26.6 % -> 32.9 % *and* own-type placement 63.0 % -> 63.9 % *and* F0
error 5.4 % -> 3.1 %, with the cosine held at 0.755. Nothing regresses. §9.2b called this use
1 and treated the objective as the thing that would fall out for free; it is the other way
round.

**3. The waveguide wins once, and the reason revises §9.1 result 5.** Re-enabling
`fit_species_tube` helps under *both* typings (+3.5 points with the hand vector, +4.1 with
the embedding), and learned typing plus the waveguide reaches **37.0 %** — past this
document's own `> 35 %` target. §9.3 proposed the waveguide as the test of whether a learned
*objective* is better. It turns out the waveguide was not being rejected by the objective at
all; it was being rejected by badly-defined types. A tract fixed for the whole bird cannot
match a per-type reference that is itself a blend of several different sounds, and that is
what the hand-weighted typing was producing.

Caveat, and it is a real one: §9.1 measured the waveguide as a regression over 22 species on
`out/harvest`, and this is a different store. The 37.0 % row also pays for its placement in
cosine (0.755 -> 0.706), missing the `>= 0.74` guardrail. **`--embed-typing` alone is the
result to trust**; `--use-tube` on top of it is promising and unconfirmed.

### Novelty detection, honestly

Six species were held out of training entirely. Against held-back syllables of the 19
training species: **ROC AUC 0.825**, and at a threshold calibrated to a chosen 5 % false
positive rate the measured rate is 4.7 % and **22.1 %** of genuinely unheard syllables are
flagged. The threshold is honest; the low-false-positive end of the curve is weak.

Per species, the detection rate is not about taxonomy:

| held-out species | flagged novel | closest relative in training |
|---|---|---|
| `perisoreus_infaustus` | 50.0 % | none |
| `horornis_diphone` | 33.5 % | `horornis_canturians` |
| `cuculus_solitarius` | 31.2 % | `cuculus_canorus`, `cuculus_clamosus` |
| `parus_minor` | 24.0 % | `parus_major` |
| `zosterops_simplex` | 22.3 % | two congeners |
| `troglodytes_troglodytes` | 8.2 % | none |

The obvious explanation — congeners sound alike, so a held-out congener is genuinely hard —
fits five rows and is contradicted by the sixth. The wren has no relative in the training set
and is the *worst* detected of the six. So what the embedding measures is acoustic
neighbourhood rather than relatedness: a loud broadband trill sits near other species' trills
regardless of the family tree. That is arguably the correct behaviour for the question being
asked, and it means "hold out a species" is a harder test than "hear a genuinely new sound".

### What to run

```bash
uv sync --extra critic                                   # torch; CUDA wheels, CPU works too
uv run birdy-pipeline harvest --store out/harvest-gan    # a store WITH patches
uv run birdy-pipeline learn   --store out/harvest-gan --out /tmp/base.json --learned-only
uv run birdy-pipeline critic train --store out/harvest-gan --inventory /tmp/base.json \
                                   --out out/critic.pt
uv run birdy-pipeline learn   --store out/harvest-gan --critic out/critic.pt --embed-typing
uv run birdy-pipeline placement --store out/harvest-gan --inventory <the fit>
```

### What is still open

- **Re-run this ablation on a 40 k store.** `out/harvest-gan` is a quarter the size of
  `out/harvest` and the waveguide row in particular needs the larger corpus before it is
  believable. Harvesting with patches is the only prerequisite, and it is now the default.
- **The alternation of §9.3 step 6 was never run**, because the objective it feeds was
  refuted at round one. If anyone revisits the realism term, retrain the critic against the
  new resyntheses first — a critic beaten once will find a new tell.
- **Use the embedding for the galaxy's clustering**, not only for typing. `--embed-typing`
  changes what a syllable type is; the 3-D projection and the density field are still built
  from the 28-d descriptor, so the two now disagree about what is near what.
- **§9.6 is untouched and is now the better bet.** Injecting `ẏ` at the tract input and
  replacing the per-syllable envelope with a respiratory oscillator are both structural, both
  cheaper than this was, and neither depends on a learned objective.

---

## 9.8 The same ablation at 40 k, and a store bug it exposed

`out/harvest-gan` was grown to **39 993 syllables, every one carrying a patch** (58.9 MB of
`patches.f16` — the §9.3 estimate was ~65 MB) over 1 036 recordings. The ablation was re-run
on it end to end.

**Read the caveat first, because it changes what these numbers are.** Growing the store past
`DEFAULT_SYLLABLE_CAP` triggered `add_syllables`' trim, and that trim dropped the *oldest*
recordings — which, because a harvest works through its species one at a time, meant **twelve
of the twenty-five species were deleted outright**, `parus_major` and `parus_minor` among them.
`strata` still listed all twenty-five, because the descriptor reservoir trims per stratum and
never had this problem, so the galaxy showed birds the learning set no longer contained. This
is therefore a **13-species** measurement and chance is 7.7 %, not 4.0 %. It is not comparable
to §9.7's absolute numbers. The trim is fixed (per species now, mirroring `_rebalance`) and
`harvest.self_test` asserts it, but the deleted rows are gone from that store.

| variant | types | species | own type | cosine | \|F0 err\| |
|---|---|---|---|---|---|
| baseline: hand typing, cosine objective | 138 | 38.4 % | 62.3 % | 0.807 | 3.3 % |
| **learned-embedding typing** | 294 | **51.7 %** | 55.1 % | **0.796** | **2.2 %** |
| **learned typing + waveguide** | 294 | **57.1 %** | 44.9 % | 0.723 | 2.1 % |
| realism objective at `w=0.5` | 138 | 31.9 % | 52.2 % | 0.642 | 4.0 % |

Chance 7.7 %. The critic itself: realism **AUC 0.992 on three entirely held-out species**,
species accuracy 0.941 (chance 0.100), contrastive top-1 **0.832** out of 256.

**Both §9.7 conclusions hold, and more strongly.** Learned typing takes species placement
38.4 % → 51.7 % — a **+13.3 point** gain against +6.3 at 9 k — with the guardrail cosine
essentially held (0.807 → 0.796) and F0 error improving 3.3 % → 2.2 %. The realism objective is
refuted again and by a wider margin: 38.4 % → 31.9 % with the cosine falling 0.807 → 0.642.
Two independent stores, two different species counts, same answer both times.

**One number needs care: `own type` falls as placement rises,** and that is mostly an artefact
rather than a regression. The learned embedding drove `choose_k` from 138 types to 294, and
own-type placement asks whether a resynthesis beats *every other type of the same bird* — with
twice as many rivals it is a strictly harder question. It is not comparable across rows with
different type counts, which is exactly why `nearest own species` is the headline metric: the
number of species references is fixed no matter how the typing changes.

That §9.7 hoped for and this confirms: `choose_k`'s silhouette does become a more willing
instrument in the learned space, which is what more than doubling the type count means.

### Still open

- **A balanced 25-species measurement at 40 k has not been made.** It needs a fresh harvest
  with the fixed trim — the fix cannot restore rows already dropped — and that is ~1 000
  downloads against a rate-limited key, so it is a deliberate decision rather than a
  free re-run.
- The waveguide row still trades cosine for placement (0.796 → 0.723). It is the most
  promising unconfirmed thing here and it should be judged **by ear** before it ships,
  per §9.5's last risk.
