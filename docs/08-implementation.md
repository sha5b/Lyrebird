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
i.e. dt ≈ 1.3 µs); RK4 agrees to within 2 % of F0, so Euler is what ships. The source
fed to the vocal tract is the labial velocity `y`, scaled to unit-ish amplitude:

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

### Parameter mapping (identical on both sides)

| Syllable field | Model parameter |
|---|---|
| `contour` → `f0(t)` (log-interpolated between breakpoints) | `beta = betaForF0(f0, alpha)`, clamped to [0.15, 16] |
| `level` × envelope → `p_s(t)` | `alpha = 0.05 + 0.40 * p_s` |
| `timbre: 'pure'` | pressure gain 1.00, tract Q 9.0 |
| `timbre: 'reed'` | pressure gain 1.25, tract Q 5.0 |
| `timbre: 'buzz'` | pressure gain 1.75, tract Q 3.0 (drives the nonlinear regime) |
| `harmonic` | adds `harmonic * 0.5` of a second tract band at `2*f0` |
| `two: true` | second independent oscillator at `f0 * 2^(+7/1200)`, mixed 0.5/0.5 (bilateral syrinx) |
| `am`, `amDepth` | multiplies `p_s` by `1 - amDepth*(0.5 - 0.5*cos(2*pi*am*t))` (respiratory gating) |
| `vib: {rate, depth}` | `f0 *= 1 + depth*sin(2*pi*rate*t)` |
| `attack` (default 0.008 s) | envelope attack time |
| `hold: true` | envelope sustains at 1.0 until the last 25 % of the syllable, else exponential decay with tau = dur/2.5 |

Envelope: linear attack over `attack` seconds, then sustain/decay as above, then a
6 ms release. `p_s` is `level * envelope * timbreGain`, clamped to [0, 1.4].

The envelope is applied **twice, on purpose**: once through `p_s` (which is what shapes
the timbre, since pressure decides how nonlinear the oscillator is) and once as a linear
output gain on the filtered sample. The output gain is what makes a syllable start and
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

## 8.5 Honesty rule

Every rendered phrase carries its `confidence` from `data/inventory.json`:
`experimental` (playback-verified function), `documented` (described in the
literature), `inferred` (plausible, not established). Word-driven phrases are always
labelled as an invented mapping. This is a product requirement, not a nicety — see
`03-decoding-science.md` §3.1 and Rutz et al. 2023.
