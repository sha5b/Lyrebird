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
