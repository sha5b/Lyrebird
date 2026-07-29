# 8. Implementation Contract (v1)

This document is the interface between the two halves of Birdy:

- `pipeline/` — offline Python (uv-managed): renders a corpus, calibrates the syrinx
  model, computes features, builds the galaxy.
- `app/` — SvelteKit + TypeScript: realtime syrinx synthesis, mic analysis, 3D galaxy.

Both halves implement the *same* physical model and the *same* feature extractor.
Every number that both sides need is written here or shipped in a generated JSON file.
Nothing is duplicated in source: the canonical inventory is `data/inventory.json`.

## 8.1 The syrinx model

The source is the low-dimensional Mindlin–Laje "flapping" oscillator
(`04-synthetic-bird-voices.md` §4.2, Amador & Mindlin 2021):

```
x' = y
y' = -a*g^2 - b*g^2*x - g^2*x^3 - g*x^2*y + g^2*x^2 - g*x*y
```

- `g` (gamma) — time-scale constant, **chosen per syllable**, see below.
- `a` (alpha) — air-sac pressure. **Both `a` and `b` are positive here**: with the
  equation written as above, the limit cycle lives at `a > 0`, `b > 0`. The published
  form states the threshold as `alpha < 0`; the difference is the sign convention on
  `x`, and the dynamics are identical. This was verified numerically before the
  mapping below was fixed — see the measurements in §8.6.
- `b` (beta) = syringeal tension — sets the fundamental frequency.

Integration: forward Euler at `oversample * sampleRate` (oversample = 16 at 48 kHz,
i.e. dt ≈ 1.3 µs); RK4 agrees to within 2 % of F0, so Euler is what ships. Both sides start
from `(x, y) = (1e-4, 0)`. The state is bounds-checked **once per output sample** against
`|x| < 1e6, |y| < 1e12` and reset to the start if it escapes — outside those bounds there is
no basin left to be in. Do **not** clamp every Euler step to a tight range: that flattens the
peaks of the large-amplitude regimes the model legitimately reaches at high `beta`.

The source fed to the vocal tract is the labial velocity `y`, scaled to unit-ish amplitude:

```
source = (y / g) * 0.35 / ampPP(a, b)
```

`ampPP` is the measured peak-to-peak swing of `y/g`, which varies from ~0.3 to ~10
across the usable parameter range — without dividing it out, high notes are twenty
times louder than low ones. It is measured by the pipeline into the calibration table
(§8.4); the analytic fallback is `0.5 + 3.4*a + 0.62*b`. The result is DC-blocked.

### gamma is per syllable, not a constant

Rescaling time by `g` leaves the equations unchanged, so `g` is a pure time-scale:

```
f0     = g * PHI(alpha, beta)          PHI(0.1, 1) = 0.17061   (measured)
ampPP  = A(alpha, beta)                independent of g
```

This is why the literature fits `g` per bird, and Birdy must do the same. With `g`
pinned at 24000 the oscillator cannot be driven below roughly 1.4 kHz — every owl,
dove and cuckoo in the inventory then lands one to three octaves sharp, because the
`beta` floor binds instead. So each syllable gets its own time-scale, picked so its
median pitch sits at `beta = 1`, in the middle of the well-behaved region:

```
f0_ref     = geometric mean of the syllable's contour frequencies (Hz, floored at 80)
gamma      = clamp(f0_ref / 0.17061, 1200, 150000)
oversample = clamp(ceil(gamma / (0.06 * sampleRate)), 16, 64)   # keeps gamma*dt ~ 0.06
```

The calibration table is measured once at `gamma = 24000`. A voice running at another
`gamma` looks up the frequency it *would* have there — multiply the target F0 by
`24000 / gamma` before indexing the table, and the returned `beta` is correct because
the mapping is dimensionless. With this rule the `beta` clamp almost never binds:
a syllable only reaches it if its contour spans more than about 3.6x in frequency.

Verified: owl `hooLong` at 530 Hz measures 532 Hz and wren trill at 6400 Hz measures
6391 Hz, both at `beta ≈ 1`.

**Two caveats added later, both in §8.1a.** The 1.4 kHz floor above is a consequence of the
`beta` clamp, not of the model: a table built at `--beta-min 0.002` reaches 81 Hz at
`gamma = 24000`. And "`beta = 1`, in the middle of the well-behaved region" is the tonal end
of the model, not its middle — pinning every syllable there is what made 100 % of the
resynthesis tonal against 15.6 % of real syllables being spectrally rich. `gammaScale`
exists to move off it.

### Parameter mapping (identical on both sides)

| Syllable field | Model parameter |
|---|---|
| `contour` → `f0(t)` (log-interpolated between breakpoints) | `beta = betaForF0(f0, alpha)`, clamped to the table's own `betaClamp` (contract default [0.15, 16]; shipped table 0.002 — see §8.1a) |
| `level` × envelope → `p_s(t)` | `alpha = 0.05 + 0.40 * p_s` |
| `timbre: 'pure'` | pressure gain 1.00, tract Q 9.0 |
| `timbre: 'reed'` | pressure gain 1.25, tract Q 5.0 |
| `timbre: 'buzz'` | pressure gain 1.75, tract Q 3.0 (drives the nonlinear regime) |
| `harmonic` | adds `harmonic * 0.5` of a second tract band at `2*f0`, **at the same Q as the tract** |
| `two: true` | second independent oscillator at `f0 * 2^(+7/1200)`, mixed 0.5/0.5 (bilateral syrinx) |
| `am`, `amDepth` | multiplies `p_s` by `1 - amDepth*(0.5 - 0.5*cos(2*pi*am*t))` (respiratory gating). **`p_s` only** — never the output gain, or the tremolo is applied twice |
| `vib: {rate, depth}` | `f0 *= 1 + depth*sin(2*pi*rate*t)` |
| `attack` (default 0.008 s) | envelope attack time |
| `hold: true` | envelope sustains at 1.0 until the last 25 % of the syllable, else exponential decay with tau = dur/2.5 |

Envelope: linear attack over `attack` seconds, then sustain/decay as above, then a
6 ms release. `p_s` is `level * envelope * timbreGain`, clamped to [0, 1.4].

The envelope is applied **twice, on purpose**: once through `p_s` (which is what shapes
the timbre, since pressure decides how nonlinear the oscillator is) and once as a linear
output gain on the filtered sample. The AM gate is **not** part of the second application:
it modulates `p_s` and leaves the output gain clean. Folding it into a single envelope used
for both doubles the tremolo depth, which is a divergence the browser carried for a while
(§8.1a). The output gain is what makes a syllable start and
stop: dividing the source by `ampPP` deliberately removes level from the ODE, so
pressure alone would produce a note that never fades.

### Vocal tract

Pure tones are a filter effect and the tract tracks F0 (`04-…` §4.1,
Beckers et al. 2003), so the tract is **not** cosmetic:

- one two-pole resonant bandpass (RBJ biquad, `bandpass` form) centred on the
  *instantaneous* `f0`, Q per timbre above, coefficients recomputed every 32 samples;
- optional second bandpass at `2*f0` scaled by `harmonic`;
- a fixed 180 Hz one-pole highpass (DC block) and a 12 kHz one-pole lowpass
  (tracheal roll-off) on the sum.

## 8.1a Naturalness: richness, absolute resonances, turbulence, roughness

Everything in this section is optional and defaults to off, so a syllable that does not
carry these fields renders exactly as §8.1 always specified. They exist because §8.1 on
its own has a measurable ceiling, and the measurements are below.

### What was wrong, measured against 39 976 harvested syllables

The fit already renders every learned syllable through the model and scores it against the
recording it came from (§8.5). Before this section existed, that verification said:

| | before | after |
|---|---|---|
| 28-d descriptor cosine, median | 0.533 | **0.775** |
| types above 0.7 | 26.2 % | **66 %** |
| types below 0.5 | 44.2 % | **11 %** |
| nearest its own *type* | 35.7 % | **56.5 %** |
| nearest its own *species* | 20.8 % | 23.1 % (chance 4.5 %) |
| median \|F0 error\| | 1.7 % | 3.8 % |

Two things to read out of that. F0 was never the problem — it was already at 1–2 % while
the timbre cosine sat near 0.5. And the last row is the one that **did not move**: three
quarters of fitted syllables still resynthesise closer to a different species than to their
own. See "still open" at the end — it is a real limit, not a tuning issue, and it is the
next thing to fix.

The two structural causes:

**1. Every resonance was relative to pitch.** The tract of §8.1 is a bandpass retuned to
the instantaneous `f0`, so the spectral envelope is pitch-invariant — transposing a
syllable transposes its whole spectrum, and two species at the same pitch are the same
instrument. Real birds do move a resonance with f0 (Riede et al. 2006 measured the
oropharyngeal-esophageal cavity tracking it from 1.5 to 5 kHz within a syllable), so the
tracking band is *not* wrong. What was missing is the part that does **not** move: the
trachea is a tube closed at the syrinx, so it resonates as a stopped quarter-wave pipe at
the odd harmonics of a single frequency, fixed by the bird's body.

**2. Every syllable was pinned to the tonal regime.** The spectral content index
(SCI = spectral centroid ÷ f0) is a function of `beta` alone and is invariant to `gamma`,
because `gamma` is a pure time-scale. The §8.1 gamma rule chooses `gamma` so the syllable's
median pitch sits at `beta ≈ 1` — which is the tonal end of the model. Oscillations born at
low `beta` in a saddle-node-on-a-limit-cycle are pulse-like and harmonically dense; those
born at high `beta` in a Hopf are tonal (Sitt et al. 2008).

Measured, our SCI had the right *median* and no tail at all:

| | real harvested syllables | our resynthesis (before) |
|---|---|---|
| SCI median | 1.092 | 1.099 |
| SCI > 1.5 | **15.6 %** | 1.4 % |
| SCI > 3 | **5.3 %** | 0 % |
| spectral flatness, median | 0.044 | **0.0005** |

Three orders of magnitude too pure. The rich half of every repertoire was not mis-fitted,
it was *unreachable*.

### The fields

| Syllable field | Model parameter |
|---|---|
| `gammaScale` (default 1) | multiplies the per-syllable `gamma`, then clamped to [1200, 150000]. For a fixed target f0, raising `gamma` forces `beta` down — this is the tonal-to-rich axis. Needs a calibration table built with a lower `--beta-min` to have anywhere to go. |
| `formants: [[hz, q, gain], …]` | up to **4** extra bandpasses at **absolute** frequencies, summed into the tract output. Same RBJ bandpass form as the tract, coefficients computed **once** — they do not track f0. |
| `noise` (0..1) | turbulence at the labia, added to the source *before* the tract, scaled by `max(p_s − 0.05, 0)` so a bird with no airflow does not hiss, and by `NOISE_GAIN = 2 × SOURCE_GAIN`. |
| `rough` (0..1) | multiplies **beta** by `clamp(1 + 0.12·rough·w·G, 0.5, 1.5)`, where `w` is xorshift noise one-pole lowpassed to 140 Hz and `G` normalises it to unit standard deviation. `ampPP` is read at the *clean* beta. |
| `tractQ` (default: from timbre) | overrides the tract band's Q, clamped to [0.7, 40]. |

The tracheal comb is the intended way to populate `formants`:
`f_n = (2n−1) · f_1`, `n = 1…4`, gain falling as `1/(2n−1)`, `Q = 6`. One number, four
resonances. Measured agreement that justifies the tube formula: eastern towhee, syrinx
replaced by a loudspeaker and swept, resonances at ~2.0 and ~5.5 kHz against 1.88 and
5.67 kHz predicted for its 45 mm trachea (Nelson, Beckers & Suthers 2005); northern
cardinal ~2, 5, 8, 12 kHz, i.e. 1:3:5:7 (Riede et al. 2006).

**The comb is fitted once per species, and `f_1` is measured rather than searched.** A
trachea is a tube of fixed length belonging to the bird, not to the note, so every syllable
that species sings carries the same absolute resonances. `learn.measure_trachea_f1` averages
the per-syllable MFCC means over all of a species' observations, inverts them to a 26-band log
spectral envelope, detrends the overall tilt and scans for the `f_1` whose odd-harmonic series
best aligns with what is left. Because those syllables span many recordings and a wide range
of f0, pitch-dependent structure averages away and only resonances fixed in Hz survive — the
long-term-average-spectrum argument applied to a store that kept no audio.

Nothing in that function knows which species it is looking at, so **a bird discovered an hour
ago is measured on the same footing as one that has been in the inventory from the start.**
There is no per-species table to keep in step with the harvest. Sanity check on this corpus:
implied effective tube lengths of 1.7–6.6 cm, against 3.4–4.5 cm measured in the literature.

The measurement proposes and the resynthesis decides: `fit_species_trachea` chooses the comb's
gain by rendering, with "comb off" as the incumbent, so a species whose recordings show no
tracheal colour keeps none — 10 of 22 species here earned one. That gate matters because for a
bird whose f0 barely moves, the largest peak in an average spectrum *is* the fundamental and no
spectral method can tell that from a resonance.

**`rough` acts on tension, not on pressure and not on the output.** This is the one point
the literature is specific about: Amador & Mindlin (2021) fitted this model to zebra finch
song and found that matching the fundamental and the filters "was not enough" to drive
selective forebrain neurons — noise on `beta` was required, and an *intermediate* amount
scored best. Perturbing tension also makes the f0 and amplitude wobble arrive *correlated*,
through the oscillator's own dynamics, which is what separates a rough voice from a clean
voice with hiss added. Rendition-to-rendition f0 and amplitude are near-uncorrelated in
real song (R² ≈ 0.03), so independent output-level jitter and shimmer would be wrong.
140 Hz sits inside the 80–250 Hz band syringeal muscle can actually follow; below 80 Hz the
modulation is respiratory, which is what `am` already models.

### The noise generator is part of the contract

`noise` and `rough` draw from **xorshift32**, not from `Math.random` or `np.random`, seeded
`(stream · 2654435761 + 1) mod 2³²` with the first eight outputs discarded. Both sides must
produce bit-identical noise from the same syllable, or "the same turbulence" is not a claim
anyone can test. The offline renderer and the verification use `stream = 0` so a fitted
cosine is reproducible; the browser gives each voice its own index, so two birds singing
one syllable are not noisy in the same places. The second syringeal side uses
`stream + 1024` — sharing a stream would correlate the two sides, and correlated noise
through two near-identical tracts sums to one louder voice instead of two.

Any roughness scaling must be **analytic**, never taken from a buffer maximum: a worklet
does not have the whole syllable, and normalising by a maximum makes the effect depend on
syllable length.

### The beta clamp is read from the table, not hard-coded

`--beta-min` moves the clamp and the sweep is then measured over the wider range, so the
value is written into `syrinx-calibration.json` as `betaClamp` and **both** renderers read
it from there. The shipped table is built at `--beta-min 0.002`, which reaches f0 down to
81 Hz (from 906 Hz) and opens the spectrally rich region. Below 0.15 the beta grid is
geometric rather than linear: f0 goes roughly as `beta^0.39`, so 0.002…0.15 covers about
two and a half octaves and a linear 0.01 step would put fifteen samples in it.

### Verification: the two renderers must agree sample-for-sample

`app/scripts/verify-parity.mjs` renders a case list through the real AudioWorklet and
through the Python renderer and compares them. §8.1 has always said the two halves
implement the same model; nothing enforced it, and six divergences had accumulated —
including AM applied *twice* in the browser, a `hold` decay of `dur*0.12` against the
spec's `dur/2.5`, a missing pre-tract highpass, ODE initial conditions of 0.001 against
1e-4, a per-Euler-step clamp at ±40 that flattened the peaks of the high-amplitude
regimes, and an invented `Q*0.8` on the harmonic band. All twelve cases now agree to
2.8e-08, which is float32 rounding.

The harness also checks the ~20 ms each voice runs *past* the envelope's grid, where
Python has no samples to compare against. That region is a decay, so nothing in it may
exceed the body level. This is not hypothetical: a release ramp that continued past its
endpoint went negative there, reaching about −3.3× and reading as an audible click on the
tail of every note, while a sample-for-sample check over the first `n` samples reported
all-clear.

### F0 of a rich waveform is not measured by counting zero crossings

`measure_f0_zero_crossings` is right for the calibration sweep, where every solution is a
clean near-sinusoid, and wrong for verifying §8.1a: a pulse train crosses zero several
times per period. On a 3 kHz tone swept across `gammaScale` the crossing counter reported
errors rising to 41 % while the spectral peak stayed inside 3.7 % — the pitch was never
drifting, the ruler was. The verification uses `measure_f0_robust`: spectral peak over the
steady middle, corrected for octave errors by testing small integer sub-multiples and
keeping whichever lands nearest what was asked for. That correction can only choose between
candidates the spectrum actually contains, so it cannot invent agreement.

### Still open: species identity

`nearest its own species` sits at 23.1 % against 4.5 % chance. Everything above improved
within-bird timbre and left this almost untouched, so it is worth writing down what has
already been ruled out.

The first hypothesis was that the tracheal comb was fitted **per syllable**, with `f_1` as a
multiple of that syllable's own pitch — so two species at the same pitch got the same
resonances and no signature could form. That was a genuine error and it is fixed: the comb is
now measured once per species at absolute Hz by `learn.measure_trachea_f1` and shared by every
syllable that bird sings. The measurement is sane (implied effective tube lengths of 1.7–6.6 cm,
against 3.4–4.5 cm measured in the literature for towhee, cardinal and white-throated sparrow).
**It moved cross-species placement by about two points.** So the parameterisation was wrong,
and fixing it was not sufficient.

Two further hypotheses were tested and **both are disproved**, which is worth recording so
they are not tried again.

*"Our syntheses are all narrowband tones clustered together, so which real centroid is nearest
is near-arbitrary."* Measured on mean mel envelopes (`features.mel_envelope`) over the 22
species: between-species spread is 1.92 for our resynthesis against 1.87 for the real
recordings, and within-envelope detail 1.13 against 1.06. **We express 103 % of the real
between-species variation and 106 % of the spectral shape.** The envelopes are not collapsed
and not smooth — they are as varied and as detailed as the real ones. They are varied along
*different axes*.

*"There is a systematic spectral tilt error."* There is one — relative energy above 6 kHz sits
at −0.01 for us against −1.59 for the recordings, so our tract roll-off is far too gentle (one
pole at 12 kHz). But correcting it does not help: a 6 kHz two-pole roll-off lands the bias at
−1.588, essentially exactly on the real figure, and cross-species placement *falls* from
23.1 % to 20.2 %. Every roll-off tried was worse than none. (Part of that −1.59 is a recording
artifact rather than a bird: xeno-canto is largely mp3, which lowpasses.)

So the error is neither a lack of spectral variety nor a global bias. It is per-species and
per-syllable, and that points at the **evidence** rather than at the filter chain. A harvested
syllable is kept as 28 numbers, of which the spectral envelope is 13 heavily smoothed cepstral
coefficients — and that vector is simultaneously the fit's only evidence *and* its objective.
A median cosine of 0.775 against it therefore means the fit has largely saturated what the
stored descriptor can express, while the sound is still not right. **The ceiling is the
descriptor, not the synthesiser.** Going further requires measuring more from the audio while
it is briefly in memory — a harmonic-amplitude trajectory and a noise residual per syllable
type, on the order of 60–80 extra floats — rather than another parameter fitted against the
same 28 numbers.

### Four hypotheses tested, four refuted — and what that leaves

Written down as a list because each cost real work and each is worth not repeating. All were
measured on the same two numbers: median resynthesis cosine, and how often a resynthesis lands
nearest its own species.

1. **"The envelopes are collapsed."** Refuted. We produce 103 % of the real between-species
   spread and 106 % of the spectral detail. Not collapsed — varied along different axes.
2. **"There is a systematic spectral tilt."** There is (relative energy above 6 kHz: −0.01 for
   us, −1.59 for the recordings) but correcting it *hurts*. A 6 kHz two-pole roll-off lands the
   bias at −1.588, essentially exactly right, and drops placement from 23.1 % to 20.2 %. Every
   roll-off tried was worse than none.
3. **"The harmonic structure is missing."** Refuted, with a measurement to explain why. Real
   syllables resolve to a mean of **2.2 partials** — birdsong is genuinely near-sinusoidal —
   so a measured partial series adds almost nothing over the single `harmonic` scalar. Feeding
   it to the fit moved median cosine 0.776 → 0.768 and placement 61.7 % → 55.6 %.
4. **"The objective is too coarse — it is a time *average*, so it cannot see a spectrum
   move."** The premise is true and the fix does not help. `features.mel_path` gives a
   time-resolved target (4 knots × 26 log-mel bands, 104 floats, harvested per syllable) and
   optimising against it improves the thing it measures by 36 % — mel-path distance 3.67 → 2.33
   — while placement in the 28-d space *falls* from 61.7 % to 43.2 %.

Point 4 is the informative one. **The two objectives conflict**: matching the spectral
trajectory costs the spectral average and vice versa. That is not a bad proxy being replaced by
a better one, it is the synthesiser being unable to satisfy both at once. Combined with points
1–3 — variety is not lacking, no global correction helps, and richer evidence does not help —
the remaining constraint is the **expressive capacity of the filter chain**, not the fit, not
the objective and not the measurements.

Which finally makes the structural change the one worth doing, because it is the only candidate
that adds capacity instead of re-aiming the search at a fixed capacity.

### The missing building block, found: the tract must not track f0 (§8.1c)

**No implementation in this literature contains an f0-tracking resonance.** In every reference
version — Arneodo 2012, Perl 2011, Boari 2015, and the released code — the tract is *fixed*
(tube length, reflection coefficient, cavity volume, beak gape) and spectral change across a
syllable comes entirely from harmonics of a moving f0 sweeping through *stationary* resonances.
§8.1 removed exactly that mechanism and then asked a fitter to recover its effect.

Measured here, relative partial gains against f0:

| f0 | tracking band, p2 | p3 | fixed waveguide, p2 | p3 |
|---|---|---|---|---|
| 700 Hz | 0.0233 | 0.0015 | 1.4838 | 1.8841 |
| 1400 | 0.0189 | 0.0012 | 0.4927 | 0.0101 |
| 2800 | 0.0175 | 0.0009 | 0.0467 | 0.0015 |
| 4000 | 0.0178 | 0.0009 | 0.0946 | 0.0050 |

The tracking band's spectrum is **frozen** — a 1.3× spread over a 5.7× change in f0, i.e. a
rigid translation along log frequency parameterised by f0 alone. The waveguide's second partial
spans **32×** and its third **1250×**.

That is the mechanism behind the objective conflict above. With the spectral shape structurally
locked to f0, the *only* lever the fit had for moving a spectral trajectory was bending the
pitch contour — which is strongly species-diagnostic, so placement collapsed. Fixed resonances
give the model an f0-independent spectral degree of freedom for the first time.

Verified on the five-species store (wren, tawny owl, cuckoo, blackbird, great tit), swapping
only the tract and fitting `(L, r)` per species on a coarse grid:

| | nearest own species | cosine to own species | mel-path distance |
|---|---|---|---|
| tracking bandpass | 61.7 % | 0.433 | 3.67 |
| fixed waveguide | **67.9 %** | **0.460** | **3.23** |

**All three improve together.** Under the tracking tract, gaining on the trajectory metric cost
placement (61.7 % → 43.2 %); under the waveguide there is no trade. The conflict was a symptom
of the missing degree of freedom, not a property of the objectives.

Structure, as implemented in `_tube_comb`: `pi[t] = src[t] − r·pi[t−2D]`, output
`(1−r)·pi[t−D]`, with `D = L·sr/c` a **fractional** delay — at 48 kHz a 2 cm trachea is 2.8
samples one way, so integer rounding would quantise tube length into a handful of useless steps
and make the parameter unfittable. Resonators after it are **cascaded, not summed**: a sum of
bandpasses with positive gains cannot produce a spectral zero, and hollow, reedy and nasal
timbres live in the antiresonances. `(L, r)` is also two *physical* numbers where the formant
bank was twelve free ones, and tube length goes with body size — so it carries species
information that free-floating triples destroy.

**And then it did not generalise.** Wired into `learn_species` and run over the full 22-species
harvest, the waveguide is a regression on the shipped metrics:

| | nearest own species | median cosine | types on the waveguide |
|---|---|---|---|
| tracking band | **23.1 %** | **0.775** | 0 / 446 |
| waveguide, scored per type | 22.9 % | 0.750 | 68 / 446 |
| waveguide, scored per species | 22.2 % | 0.722 | 196 / 446 |

So it is **gated off by default** (`fit_species_tube` is not called; the kernel, the schema and
the fit function all remain). Shipping it would have been a measured regression, and the five-
species result above is real but did not survive the wider set.

Worth being precise about what this does and does not show. The mechanism is not in doubt — the
32× vs 1.3× spectral freedom is arithmetic, and in isolation the waveguide improved all three
metrics at once. What failed is the *combination* of the waveguide with the 28-d descriptor as
the objective. Scoring per species rather than per type roughly tripled adoption (68 → 196
types) and still lost, which says the objective, not the scoring level, is the binding
constraint. That is the same conclusion the four refutations above reached from the other
direction, and it now has a second, independent line of evidence behind it: **the next thing to
fix is what "closer to the real bird" means, not what the filter chain contains.**

Still to do before the waveguide can be judged fairly: an objective that is not a 28-number
time-averaged summary, then re-enable and re-measure; and mirror `_tube_comb` in the worklet. Ranked next after that, from the same
review: inject `ẏ` rather than `y` at the tract input, and replace the per-syllable envelope
with the two-state respiratory oscillator of Fainstein, Goller & Mindlin (arXiv:2509.11019),
which generates attack shape, asymmetry and cross-syllable memory from five parameters instead
of a designed envelope.

The delay-line waveguide the Mindlin implementations use (`Pi[n] = src[n] − r·Pi[n−N]`,
`N = round(2L·fs/c)`, cascaded into a fixed resonator; Sitt et al. 2010 `L = 1.9 cm, r = −0.9`)
remains worth trying, because it passes a whole harmonic comb instead of isolating one partial.
But on the evidence above it should be expected to change *which* axes we vary along, not how
much we vary — and it cannot be verified beyond the descriptor's own resolution either.

### betaForF0

`beta` vs `f0` is not analytic and depends on `alpha` too, so the pipeline measures it
once and ships a 2D table (`syrinx-calibration.json`, §8.4). The fallback when the table
is missing is the small-oscillation approximation `beta = (2*pi*f0/g)^2`, which the
measurements in §8.6 put within about 5 % at low pressure and 30 % at the top of the
pressure range.

## 8.2 Feature extractor

One 28-dimensional descriptor per clip (offline) or per rolling window (live). Both
sides implement this exactly; do **not** rely on library defaults.

Framing:

- sample rate **48000**, mono, peak-normalised to 0.9;
- frame 1024, hop 512, window = symmetric Hann: `w[i] = 0.5 - 0.5*cos(2*pi*i/(N-1))`;
- `mag[k] = |rfft(frame * w)[k]|` for `k` in `[0, 512)` — no normalisation;
- `rms` is computed on the **unwindowed** frame;
- a frame is *voiced* if `rms > 1e-4` and `rms > 0.05 * clipMaxRms`. Unvoiced frames
  are dropped. A clip with no voiced frame is skipped.

Per voiced frame:

- **MFCC (13)**: 26 triangular mel filters applied to the *power* spectrum `mag^2`;
  band energy floored at 1e-10; natural log; then unnormalised DCT-II:
  `c[i] = sum_j log(E[j]) * cos(pi*i*(j+0.5)/26)`, `i` in `[0, 13)`.

  The bank is built as follows — this is normative, because a different triangle
  convention would silently shift the whole feature space:

  ```
  M       = 26                              # bands
  N       = 1024                            # frame size
  mel(hz) = 1125*ln(1 + hz/700)             # inverse: 700*(exp(mel/1125) - 1)
  melMax  = mel(sampleRate/2)
  binPt[i] = mel^-1(i/(M+1) * melMax) * N/sampleRate   for i in [0, M+2)   # float bin positions
  # filter j spans binPt[j] .. binPt[j+2] with its peak at binPt[j+1]
  # for every integer bin k in [ceil(binPt[j]), floor(binPt[j+2])] and k < N/2:
  #   w = (k - left)/(peak - left)   if k <  peak
  #       (right - k)/(right - peak) if k >= peak
  #   w = max(w, 0)
  E[j] = sum_k w * mag[k]^2
  ```
- **centroid**: `sum(f[k]*mag[k]) / sum(mag[k])` in Hz, then `log2(max(centroid, 20))`.
- **flatness**: `exp(mean(log(mag+1e-10))) / (mean(mag)+1e-10)`.

Descriptor (order is fixed; `dimNames` is shipped in `feature-space.json`):

| index | value |
|---|---|
| 0–12 | mean of `mfcc[0..12]` over voiced frames |
| 13–25 | population std of `mfcc[0..12]` |
| 26 | mean `log2(centroid Hz)` |
| 27 | mean flatness |

Standardisation: `z = (x - mean) / std` with the corpus `mean`/`std` vectors from
`feature-space.json` (`std` floored at 1e-6).

Activation of the galaxy from live audio (client-side, cheap):

```
sim_c   = cosine(z_live, z_centroid_c)
act     = softmax(sim / temperature)          # temperature from feature-space.json
act_ema = 0.82 * act_ema + 0.18 * act          # ~120 ms smoothing at 60 Hz
```

## 8.3 Generated asset layout

The pipeline writes only into `app/static/birdy/`. Everything is fetched at runtime.

```
app/static/birdy/
  manifest.json            what was built, when, with which parameters
  inventory.json           verbatim copy of data/inventory.json
  syrinx-calibration.json  beta <-> f0 table (§8.4)
  feature-space.json       extractor spec + corpus mean/std + temperature
  positions.f32            Float32Array, 3*N, xyz per point, max|coord| = 1
  points.json              parallel metadata arrays, length N
  centroids.json           K labelled clusters with 3D position + 28-d vector
```

`points.json`:

```json
{ "n": 0, "speciesId": [], "syllableId": [], "songId": [], "clusterId": [],
  "durations": [], "source": [] }
```

`centroids.json`:

```json
{ "k": 0, "dims": 28,
  "items": [{ "id": 0, "label": "", "speciesId": "", "syllableId": "",
              "function": "", "confidence": "", "refs": [],
              "position": [0,0,0], "vector": [], "count": 0 }] }
```

## 8.4 syrinx-calibration.json

```json
{ "gamma": 24000, "oversample": 16, "sampleRate": 48000,
  "pressureGrid": [],          "// p_s values swept (alpha = 0.05 + 0.40*p_s)": null,
  "betaGrid": [],              "// beta values swept, 0.15 .. 16": null,
  "f0Hz": [[]],                "// [pressure][beta] measured F0, 0 = silent/aperiodic": null,
  "ampPP": [[]],               "// [pressure][beta] peak-to-peak of y/gamma": null,
  "inverse": { "f0Grid": [], "beta": [[]] },
  "f0Range": [0, 0] }
```

`inverse.beta[p][i]` is the beta that produces `inverse.f0Grid[i]` at
`pressureGrid[p]`, so the client does a 2D lerp — no solving at audio rate. F0 is
measured from zero crossings of the steady-state segment (last 60 % of a 250 ms run);
bins where the oscillator is silent or aperiodic (crossing-interval CV > 0.25) are
written as 0 and filled by interpolation along beta. `ampPP` is measured over the same
segment and is what the source normalisation in §8.1 divides by.

## 8.6 Measured behaviour of the oscillator

Reference numbers from the Euler integrator at 48 kHz, oversample 16, gamma 24000,
measured as peak-to-peak of `y/gamma` and F0 by zero crossings. `alpha` is the pressure
parameter, `beta` the tension parameter. Any reimplementation should reproduce these
within a few percent — they are the regression test for the model.

| alpha | beta = 0.2 | 0.5 | 1 | 2 | 4 | 7 | 14 |
|---|---|---|---|---|---|---|---|
| 0.02 | 1483 Hz / 0.27 | 2720 / 0.41 | 3865 / 0.67 | 5494 / 1.30 | 7823 / 2.71 | 10382 / 4.90 | 14684 / 10.0 |
| 0.10 | 1950 / 0.81 | 3039 / 0.92 | 4095 / 1.13 | 5623 / 1.66 | 7880 / 2.93 | 10413 / 5.04 | 14697 / 10.1 |
| 0.30 | 3015 / 1.68 | 3714 / 1.75 | 4575 / 1.92 | 5917 / 2.34 | 8023 / 3.43 | 10482 / 5.38 | 14725 / 10.3 |
| 0.60 | 3955 / 2.54 | 4448 / 2.60 | 5135 / 2.73 | 6291 / 3.09 | 8227 / 4.05 | 10586 / 5.83 | 14765 / 10.6 |

Notes that matter for the mapping:

- F0 is set mainly by `beta` but rises with `alpha` too — hence the 2D table.
- Amplitude is set mainly by `alpha`, and grows with `beta`, which is why the source is
  normalised by `ampPP`.
- Below `beta ≈ 0.15` at low pressure the oscillator falls silent (below threshold);
  clamp rather than letting a contour ask for it.
- Crossing-interval CV stays under 0.15 across this range, rising with `beta`: the
  buzzy timbres come from pushing pressure high, not from instability.
- These numbers are all measured **above** `beta = 0.2`, i.e. in the tonal regime. Below
  about `beta = 0.05` the waveform turns pulse-like and harmonically dense, spectral
  flatness rises by two orders of magnitude, and zero-crossing counting stops being a valid
  F0 estimator — see §8.1a. That region is where the model's spectrally rich voices live and
  it is reachable only with a table built at a lower `--beta-min`.

## 8.5 Honesty rule

Every rendered phrase carries its `confidence` from `data/inventory.json`:
`experimental` (playback-verified function), `documented` (described in the
literature), `inferred` (plausible, not established). Word-driven phrases are always
labelled as an invented mapping. This is a product requirement, not a nicety — see
`03-decoding-science.md` §3.1 and Rutz et al. 2023.
