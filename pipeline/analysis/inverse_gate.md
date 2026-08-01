# The amortised inverse — gate, stated before the run (2026-08-01)

docs/09 §9.3 Part 2 specified the method and never fixed a number. This is the number,
written before the encoder was trained, because the module has been sitting complete and
unreachable in the tree and "it looks better" is not why anything ships here.

## What is being compared

Two `learn` runs on the **debug-100 subset**, identical but for one flag:

- **A (shipped):** `learn --store /tmp/birdy-debug/harvest-100`
- **B (encoder):** the same, `+ --inverse out/inverse.pt`

Everything else is held: same store, same seed, same inventory, same calibration, same
`invert` passes. B differs only in where the four §8.1a gesture axes *start* —
`gammaScale`, `tractQ`, `noise`, `rough` — plus timbre, level, attack, hold and the
modulations. The measured contour and duration are kept in both (`init_syllable` drops
them), because they are measurements and a regression estimate must not replace one.

## The gate

The number that ships next to every learned syllable is the **resynthesis cosine**, so
that is what decides. All three, or the encoder does not become a default:

1. **Median resynthesis cosine over fitted types rises by ≥ 0.02.**
2. **At least 60 % of types improve** — the same bar docs/19 §19.5 used, which caught the
   mel-weight probe's small-sample luck.
3. **No species' median falls by more than 0.05.** A mean gain that hides a bird whose
   whole repertoire got worse is not a gain.

## What the gate deliberately does not read

- **The validation loss of the encoder itself.** It measures agreement with a sampler
  drawn from the fitted inventory's marginals, so it can be excellent while the fit is
  unchanged. It is reported and it is not evidence.
- **Audible fidelity.** docs/19 measured the cosine's correlation with audible distortion
  at ≈ 0.1, so a cosine gain is *not* an audible gain. If the gate passes, MCD on the
  docs/19 bench is the follow-up before anyone claims it sounds better — and if it fails,
  the bench does not rescue it.

## What a negative result means

That the descent's starting point was not the binding constraint — that the basin
`invert_gestures` finds from the cluster median is already the basin the encoder proposes,
and docs/21's "the fit is what fails" has to be attacked at the objective or the search
instead. That is a real finding about a road this repo has had half-built for weeks, and
it gets recorded either way.


## The encoder as trained, 2026-08-01 (before the fit was run)

150 000 pairs sampled from `learned-100.json`'s marginals, early-stopped at epoch 26 of
80, best validation loss **1.3331**, on the RTX 3500 Ada (`device cuda`). That reproduces
the behaviour the module's own docstring records from its development run (best 1.309 at
epoch 14, early-stopped at 26), which is the first evidence in weeks that the unreachable
code still does what it says.

Per-group validation MSE, written down now so the fit result cannot retroactively flatter
them:

| head | val MSE | |
|---|---|---|
| noise | 0.021 | |
| rough | 0.046 | |
| harmonic | 0.052 | |
| contour | 0.068 | not used at the seam — the measured contour is kept |
| dur | 0.100 | not used at the seam, and structurally invisible in the patch |
| gammaScale | 0.102 | **the axis the seam exists for** |
| level | 0.111 | structurally invisible in the patch (mean-centred) |
| attack | 0.169 | |
| vib | 0.255 | |
| am | 0.325 | |
| tractQ | **1.125** | the worst head by an order of magnitude |

Two weaknesses to hold against any positive result: **`tractQ` is barely learned** (1.125
against `gammaScale`'s 0.102), and **timbre classification is 0.442** over three classes,
where chance is 0.333. Both feed the seam. If the gate passes, it passes despite them; if
it fails, they are the first place to look, and neither is a reason to re-run the gate
with a different bar.


## Result, 2026-08-01 — THE GATE FAILS, on all three conditions

Two `learn` runs on the debug-100 store, serial, seed 0, 1 661 fitted types in both, all
1 661 shared.

| | baseline | encoder | |
|---|---|---|---|
| median resynthesis cosine | 0.7411 | 0.7546 | **+0.0135**, gate wanted +0.02 |
| mean | 0.6824 | 0.6997 | +0.0173 |
| types improved | | 877 / 1 661 | **52.8 %**, gate wanted 60 % |
| worst species | | `gampsonyx_swainsonii` | **−0.0816**, gate allowed −0.05 |

**The encoder is not adopted and the default is unchanged** (`--inverse` stays opt-in and
off). Read plainly: the median and the mean both rise, so the encoder is doing *something*
real — but it improves barely more types than a coin would, and it costs one species a
tenth of its fit. A starting point that is better on average and worse for half of what it
touches is not a starting point you turn on for 13 903 types.

**What this says about docs/21's "the fit is what fails".** The starting point was *not*
the binding constraint. Coordinate descent from the cluster median already reaches a
comparable basin about half the time, which is more than §9.3 Part 2 assumed when it
described the search as unable to escape a bad basin. The remaining fit error is therefore
mostly *not* a basin problem, and the two candidates left are the ones docs/19 and docs/21
already name: the objective (the 28-d cosine correlates ~0.1 with audible distortion) and
the physics beyond the oscillator (periphery, jitter, static tract).

**The predicted reasons were written down before the run and both survive.** `tractQ` was
the worst-learned head by an order of magnitude (val MSE 1.125 against `gammaScale`'s
0.102) and timbre classification reached 0.442 over three classes. Both feed the seam, and
neither is a reason to move the bar.

## The one follow-up worth pre-registering, and why it is not a re-run

The failure is specifically *inconsistency* — 52.8 % — with the median still up. The
standard response to that is not a better encoder but a **two-start descent**: run
`invert_gestures` from the cluster median *and* from the encoder's proposal, keep whichever
scores better on the objective that already decides. That is a different mechanism, not a
softened gate: it cannot regress by construction (the baseline start is always one of the
two candidates), so G3 is satisfied trivially and the honest question becomes cost — two
descents per type, roughly doubling the inversion phase.

Its gate, stated now: **median resynthesis cosine ≥ baseline + 0.02, and no species worse
than baseline at all** (not −0.05: with the baseline start always available, any regression
is a bug in the selection rather than a trade). If it cannot clear +0.02 even while taking
the better of two starts, then the encoder's proposals are not adding reachable basins and
this road closes with a measurement rather than a shrug.
