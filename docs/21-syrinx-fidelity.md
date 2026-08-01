# 21 — Syrinx fidelity: did we implement the model correctly, and why does it still sound like a machine

Three questions, answered against the project's own measurements and the canonical
literature. Nothing here is re-derived. Every internal number is cited to the doc or
session that measured it. Every external claim carries its paper.

## 21.1 The correctness verdict: the model is right; the failures are elsewhere

### Which model class ours is

Birdy's source is the **normal-form flapping oscillator** of the UBA lineage. It is
the minimal dynamical system sitting at the Takens–Bogdanov point of the labial
model, where a Hopf line is tangent to a saddle-node curve (Laje, Gardner & Mindlin
2002, "Neuromuscular control of vocalizations in birdsong: A model", *Phys. Rev. E*
65:051921; Laje & Mindlin 2002, "Diversity within a birdsong", *Phys. Rev. Lett.*
89:288102; the book-length account is Mindlin & Laje 2005, *The Physics of
Birdsong*, Springer). It is deliberately **not** the two-mass / mucosa-wave model
(Titze's lineage, implemented for birds by Elemans et al. 2009 — docs/15 §2 keeps
that for doves), and not a kinematic synthesizer.

The normal form is the point of the lineage. Gardner, Cecchi, Magnasco, Laje &
Mindlin 2001 (*Phys. Rev. Lett.* 87:208101) showed that two scalar gesture curves
suffice to reproduce canary song: air-sac pressure and labial tension. Amador, Perl,
Mindlin & Margoliash 2013 (*Nature* 495:59–64) showed the bird's own premotor
neurons encode exactly those gestures. Fee, Shraiman, Pesaran & Mitra 1998 (*Nature*
395:67–71) is the measurement the whole class stands on: nonlinear labial dynamics,
not a whistle.

### Which equations match

The ODE ships bit-identically on both sides of the contract (Python
`pipeline/src/birdy_pipeline/syrinx.py`, JS `app/src/lib/audio/worklets/syrinx-processor.js`):

```
x' = y
y' = -a*g^2 - b*g^2*x - g^2*x^3 - g*x^2*y + g^2*x^2 - g*x*y
```

This is the published normal form term for term, with `x` sign-flipped (the
literature states the onset threshold as `alpha < 0`, while ours lives at
`a, b > 0`, verified numerically before the mapping was fixed, docs/08 §8.1/§8.6).
The parameter reading is the literature's. `alpha` is air-sac pressure, and `beta`
is labial tension (≈ fundamental frequency). `gamma` is a pure time-scale fitted
per syllable (docs/08 §8.1, "gamma is per syllable, not a constant"). The literature
fits it per bird.

The bifurcation structure that carries the timbre physics is Sitt et al. 2008
(*Phys. Rev. E* 78:011905). Hopf-born oscillations are tonal.
Saddle-node-on-a-limit-cycle-born ones are pulse-like and harmonically dense. The
spectral content index is a function of `beta` alone. This is what §8.1a's
`gammaScale` exploits.

Forward Euler at 16–64× oversampling is validated against RK4 to within 2 % of F0
(docs/08 §8.1). The calibration table reproduces the §8.6 reference measurements to
0.1 % on F0 and 2 % on ampPP (`calibrate.check_reference`). Python↔JS parity is a
project invariant and stands at 18/18 fixtures (HANDOFF 2026-07-30), with the
two-voice fixtures' worst diff at 2.8e-08 (docs/15 §5).

The two-voice coupling kernel implements Laje & Mindlin 2005 (*Phys. Rev. E*
72:036218, eqs. 62–67) in its own weak-coupling approximation (Table I: β of 1.5e3
against 1/τ of 1e4). Its measured strong-coupling boundary is exactly where the
paper says the approximation dies (docs/15 §5): `betaInj` 0.25 collapses the
fundamental into period doubling. The respiratory oscillator is Fainstein, Goller &
Mindlin 2025 (arXiv:2509.11019, eqs. 1–4, Table S2 ranges) as written (docs/15 §1).
It includes the correction that the tract input is **velocity times root pressure**.
That is Laje & Mindlin 2005's low-frequency inertive limit, not the "every reference
injects ẏ" of docs/09 §9.6, corrected in place.

### The deviations the project itself has measured and recorded

These are the honest list, and every one of them sits **outside** the oscillator
equations:

1. **The tract, not the source, was the first failure.** A single f0-tracking
   bandpass makes the spectral envelope pitch-invariant — a 1.3× partial spread
   over a 5.7× change in f0, i.e. a rigid translation parameterized by pitch
   alone (docs/08 §8.1c, measured). Fixed formants, the stopped-tube waveguide
   and the tracheal comb (§8.1a/§8.1c) came in against the tube formula's
   measured agreement: eastern towhee resonances 2.0/5.5 kHz vs 1.88/5.67
   predicted for its 45 mm trachea (Nelson, Beckers & Suthers 2005, *J. Exp.
   Biol.* 208:297–308), cardinal 1:3:5:7 (Riede et al. 2006, *PNAS*
   103:5543–5548), white-throated sparrow ~2.2/~6.6 kHz (Riede & Suthers 2009,
   *J. Comp. Physiol. A* 195:183–192), all cited in `syrinx.py`.
2. **The tonal-regime pin.** The §8.1 gamma rule parks every syllable's median
   pitch at `beta ≈ 1` — the *tonal end* of the model, not its middle. Measured:
   SCI median right (1.099 vs 1.092 real) and no tail (SCI > 1.5: 1.4 % of ours
   vs 15.6 % real, and flatness median 0.0005 vs 0.044, three orders too pure)
   (docs/08 §8.1a). `gammaScale` plus a calibration table built at
   `--beta-min 0.002` opened the pulse regime. The pin was a parameterization
   choice, and its fix is fitted, not structural.
3. **The beta clamp still bites.** The production learn's reachability report
   (`cli.py report_reachability`) logged the clamp biting in **6 617 of 12 724**
   types. Over half the fitted corpus has contour excursions that hit the
   tension floor/ceiling while audible. Their pitch rides the clamp instead
   of the dynamics. A parameterization ceiling, again: the fit asks the ODE
   for frequencies outside the range the table measures. The honest fix is
   the fit-side one (per-syllable gamma, wider sweeps), not new equations.
4. **Pressure arrives as a designed envelope, not as respiratory physics.** B1
   (respiration.py) replaces it with the measured 2-state air-sac dynamics and
   √ps tract drive. The hand-set default **lost** the pre-registered
   bake-off: median cosine 0.343 → 0.336, with losses concentrated in sub-50 ms
   notes whose onsets the physically correct ~20–40 ms attack eats
   (docs/15 §1). Parked default-off. The per-species fit pass won 445 of 12 680
   scored types (docs/16 §16.4, `out/respfit-gan-report.json`).
5. **Two-voice coupling shipped and parked the same way.** Hand-set default:
   0.343 → 0.294 — but the two worst-fitting low-pitched species *improved*
   (docs/15 §5). The fit pass won 2 027 of 5 922 screened types (docs/16 §16.4).
6. **The fricative path** (docs/16 §16.7): turbulence routed around the
   f0-tracking band into the syllable's own formants, because a fricative is a
   noise burst filtered by the tract, not a tone with noise added. Shipped
   per-type where the pre-registered gate wins (bench 0.584 → 0.656, end-to-end
   13 wins / 0 losses — HANDOFF 2026-07-30).
7. **docrefit** (docs/16 §16.4): authored one-tone calls re-fitted against the
   same bird's learned types — 14/15 shipped a measured `noise`/`rough`
   texture, median gain +0.148.

### The verdict

**Model equations: correct.** Term-for-term the published normal form, validated
against RK4, the reference measurements, the two-sided parity harness, and the
literature's own coupling boundary conditions. Nothing the project has measured
in two years points at the ODE.

**Fit and parameterization: failing, in three separable ways.** (i) The
*representation* of a syllable — one contour + one envelope + a static tract —
cannot hold what real notes carry (§21.2). (ii) The *gesture sources* are
designed (envelope-as-pressure) or hand-set (B1/B2 defaults), and hand-set
physics loses bake-offs — the per-species fit is the only path that has ever won
(§21.3).

(iii) The *objective* is unproven as a fidelity ranking. The 28-d
cosine carries essentially no information about spectral distance to the
original: Pearson/Spearman ≈ 0.1 against both MCD and multi-res STFT, n = 200,
two independent distances agreeing at 0.925 (docs/19 §19.2). The honest state
is docs/19 §19.5's: **measure spectrally, optimize descriptor-ly** — the
cosine is a bounded, cluster-safe optimizer and the bench is the verdict
instrument. "The fit is failing" and "the ruler is unproven" are now both true,
and any extension judged only on the cosine inherits that caveat.

## 21.2 The noise/machine taxonomy

What a listener calls "noise" or "digital" decomposes into six measured causes.
Every row is pinned by a number the project already owns.

| Symptom | Measured cause | Citation |
|---|---|---|
| **Hiss where a chip note should be** — flat white noise, no formant shape | Fricative-class fits parked at the noise ceiling and still failed: oropendola L02/L04 `noise=0.85` at cosine 0.12–0.77, Algerian nuthatch 5/8 types at 0.60–0.85 scoring 0.16–0.60. The fit was reporting that the *shape* was missing, not the amount: turbulence shaped only by an f0-tracking band, a filter tuned to a pitch a broadband burst does not have | docs/16 §16.7; fix bench 0.584 → 0.656, 13/0 (HANDOFF 2026-07-30) |
| **Flute/organ purity** — a whistle too clean to be an animal | The tonal-regime pin: every syllable at `beta ≈ 1`, SCI tail amputated (1.4 % vs 15.6 % above 1.5; 0 % vs 5.3 % above 3), spectral flatness three orders low (0.0005 vs 0.044). Real labial motion at low tension is a skewed, pulse-like waveform with rich harmonics (Fee et al. 1998, *Nature* 395:67–71); the SNILC regime that produces it was unreachable until `gammaScale` + the 0.002 table | docs/08 §8.1a |
| **"A sine with an organ envelope"** — authored one-tone calls | Authored inventory carried `noise=0, rough=0, timbre=pure` while the same bird's learned types measure noise 0.05–0.25 and rough up to 0.65. docrefit shipped a measured texture to 14/15 (owl `hooLong` noise 0.05 / rough 0.65, +0.052; median +0.148) — and the honest caveat is that median cosine after is 0.270: texture is a real but modest move | docs/16 §16.4 |
| **Metronomic** — the same note, identical, every time | No physiological micro-variation: the ODE is deterministic, the envelope a fixed 8 ms attack + exponential + 6 ms release, and variation exists only per *variant* (`jitter_syllable`, corpus-level). Real birdsong has measured rendition-to-rendition fundamental-frequency CV of ~1 % even in crystallised adult song (Tumer & Brainard 2007, *Nature* 450:1240–1244, Bengalese finch) and slow within-day drift (Wood et al. 2013, *PLoS ONE* 8:e82327); and noise on the *tension* parameter is required for the model's own output to drive the bird's song-selective neurons — intermediate noise optimal, zero noise failing (Amador & Mindlin 2021, *Front. Neurosci.* 15:647978). Birdy's `rough` implements exactly that mechanism but only as one fitted constant depth per type — a static dose, not a living gesture | docs/08 §8.1a (fields); `syrinx.py` `rough` docstring |
| **No loudness life** — loud notes don't brighten, onsets arrive pre-shaped | The tract is static per syllable: formant coefficients computed once, nothing couples pressure to filter. Real birds articulate per note — beak gape acts as a high-shelf on 4–7.5 kHz, `A = −5 + 32·log(B)` (Nelson et al. 2005, cited above), gape correlates with fundamental frequency in zebra finch song (Ohms et al. 2010, *PLoS ONE* 5:e11923) and tracks trill rate/frequency trade-offs in Darwin's finches (Podos, Southall & Rossi-Santos 2004, *J. Exp. Biol.* 207:607–619). And the envelope is an output *gain*: dividing by ampPP removes level from the ODE by design, so pressure shapes timbre only through `alpha` — the √ps multiplicative tract drive that makes the tract genuinely driven harder exists only on the default-off respiration path | docs/08 §8.1 (the deliberate double envelope), §8.1a; docs/15 §1 |
| **Learned (machine-fitted) types sound worse than their cosine says** | The objective is the suspect: the cosine does not rank audible fit (r ≈ 0.1, docs/19 §19.2), so a type can climb the proxy into a spectrally wrong corner. Median resynthesis cosine across the 200 k learn is 0.650 with thin 2-recording species pulling it down (docs/16 §16.3); sub-0.3-cosine types are the audible floor, and most of them are an *unfixed* gap — the fricative shaped-noise win does not reach them (HANDOFF 2026-07-30: "most sub-0.3 types are a different, unfixed gap") | docs/19 §19.2/§19.5; docs/16 §16.3/§16.7 |

Two reading notes. First, "noise" and "machine" are *opposite* failure modes of
the same cause family. The representation has one noise axis and one envelope.
A fricative collapses to unshaped hiss (too random), and a tonal note collapses
to a metronomic sine (not random enough). The ear classifies both as artificial,
because real syringes live between the regimes. The model *contains* that
middle: period-doubled and chaotic solutions (Sitt et al. 2008; Amador & Mindlin
2008, *Chaos* 18:043123). The fit simply cannot find its way there under the
current objective and defaults.

Second, none of the six rows is an ODE fault. That is §21.1's verdict wearing its
consequences.

## 21.3 The extension roadmap, ranked

Constraints, restated because they do the ranking. The synthesizer stays
physical and interpretable. No ML/neural audio generation, ever (AGENTS.md hard
rules). Every addition ships only where it wins a per-species
**pre-registered fit**. The B1/B2 lesson: hand-set defaults lose bake-offs,
however correct the physics (docs/15 §1/§5). Ranked by realism gain ÷
interpretability cost ÷ implementation risk, with the docs/19 bench (MCD/STFT
against the cached audio) as the verdict instrument wherever cached audio
exists.

**1. Per-species respiratory pressure fit (B1's fit path — the attack and the life of a note).**
Basis: Fainstein, Goller & Mindlin 2025 (arXiv:2509.11019), the 2-state air-sac
dynamics with the Heaviside inflow/outflow asymmetry. Also the
mini-breath/pulsatile regimes of Hartley & Suthers 1989 (*J. Comp. Physiol. A*
165:15–26).

Equations already shipped (`respiration.py`, docs/15 §1):
`τx ẋ = −(1+x²)x − p + F0 f(t)`,
`τp ṗ = −(1+x²)x − (1+α(p))p + F0 f(t)`, `ps(t) = scale·p(t)`, tract drive
`√ps·y`. Fixes the "no loudness life" row and the onset-shape losses the
hand-set default took in sub-50 ms notes.

**Fit (pre-registered, docs/15 §1): one 5-parameter set per species**, coordinate
search over the Table S2 ranges seeded from the default set. The forcing is the
type's *measured* gesture (attack/duration/AM from the observations), not the
median envelope, which is what short-note species need. Evidence the path works:
the respfit pass already won 445 of 12 680 types with the gate holding
everywhere, and median cosine moved 0.650 → 0.6623 across both extension fits
(docs/16 §16.4). What the bake-off missed is now measurable on the bench instead
of argued about.

*Pre-registration sketch — metric:* median ΔMCD (and multi-res STFT) against
the medoid member's cached audio per fitted type, cosine as clustering
guardrail. *Gate:* MCD win share ≥ 60 %, median ΔMCD > +1 dB better, median
cosine drop ≤ 0.02 and max ≤ 0.05 (docs/19 §19.5's gate set, which killed the
mel-weight objective — apply the same noose). *Dataset:* the debug-100 store
with the iNat audio cache, the wren/great-tit/blackbird/owl/cuckoo panel of
docs/15 §1 retained as the regression bench, sub-50 ms note species
deliberately included. Ships per-species, default-off globally until it wins.

**2. Measured micro-modulation: physiological jitter and tremor, fitted per type.**
Basis: rendition-to-rendition FF CV ~1 % in crystallized adult song (Tumer &
Brainard 2007, cited above). Within-day slow drift of FF and amplitude (Wood et
al. 2013, cited above). Syringeal muscles can modulate up to 250 Hz, so the
headroom for real tremor is measured, not assumed (Elemans et al. 2008,
*PLoS ONE* 3:e2581; review: Riede & Goller 2010, *Brain Lang.* 115:69–80). And
the neural-evidence requirement that tension carry noise (Amador & Mindlin
2021, cited above).

Equation: extend the existing `rough` mechanism from one
static depth to a two-band measured gesture. The low band is respiratory, tens
of Hz, on `alpha`, sharing the `am` machinery's discipline. The high band is the
existing 140 Hz-lowpassed band on `beta`. Band powers are measured per type,
with a rendition-level seed (the xorshift stream discipline already gives
independent realizations per voice). Fixes the "metronomic" row directly.

**Fit, not hand-set:** measure the modulation spectrum of f0 and amplitude per
type from the harvest (`features.mel_path` + the f0 track), match band powers
by the same coordinate search, judge on the bench plus a distribution match (KS
on cycle-to-cycle Δf0/Δamp against the type's members). Cost: two scalars and
one existing filter per band — the cheapest realism per line of code on this
list, and the ear is exquisitely sensitive to exactly this cue. Risk: the clamp
discipline of `rough` (Amador & Mindlin's intermediate-optimum) must be
re-derived per band, and rendition-level variation must not leak into the
descriptor used for typing (the fit corpus renders are deterministic by design).

*Pre-registration sketch — metric:* KS distance between rendered and harvested
cycle-to-cycle Δf0 and Δamp distributions per type + MCD non-inferiority on the
bench. *Gate:* median KS halved against the unmodulated render, zero types with
MCD regression > 1 dB, cosine drop ≤ 0.02 — *dataset:* the 100 deepest species
of the P0 depth harvest (median 29 recordings/species — HANDOFF 2026-07-31),
which is the first corpus with the rendition count to measure the target.

**3. Waveform-regime fit: getting the pulse regime reached, not just reachable.**
Basis: Fee et al. 1998 (measured skewed, pulse-like labial waveforms). Sitt et
al. 2008 (SCI is a function of `beta` alone). Amador et al. 2013 (gesture-space
elemental dynamics).

Nothing new to add to the model — the SNILC regime is in
the equations and `gammaScale` + the 0.002 table opened the road (docs/08
§8.1a). The extension is fit-side: an SCI/waveform-skew target in the
inversion, so the rich tail is *fitted to*, per type, with the §19 bench as
judge. The cosine cannot see spectral richness, which is precisely why the tail
stayed amputated after the machinery shipped. Fixes the "flute purity" row
where it survives `gammaScale`. Risk is objective-side, not model-side: this is
the docs/19 program (measure spectrally) applied to a second dimension. Ranked
below 1–2 only because its win is gated on the objective work, not because the
physics is uncertain.

**4. Dynamic tract: beak-gape shelf and pressure-filter coupling.**
Basis: gape as high-shelf, `A = −5 + 32·log(B)` over 4–7.5 kHz (Nelson et al.
2005). Gape–frequency coupling in song (Ohms et al. 2010; Podos et al. 2004).
The OEC's f0-tracking already justifies the moving band (Riede et al. 2006).

Equation: one scalar shelf gain `s(t) = clip(a·ps(t) + b·f0(t)/f0_ref + c)` on
a 4 kHz-high shelving filter — two fitted constants and a fixed corner, fully
interpretable. Fixes "loud notes don't brighten". Fit from measurements:
per-type regression of 4–7.5 kHz band energy against pressure/f0 in the
harvest, shipped only where the measured coupling is significant and the bench
wins. Risk: the static-formant chain is delicate (cascade order is
contract-pinned on both sides). A shelf is additive and cheap, but the fit must
show it is not just re-discovering the channel tilt docs/17 measured as the
dominant nuisance. The regression must run per recording, not per store.

**5. Two-voice per-type fit (B2's fit path — biphonation and subharmonics).**
Basis: two independently controlled sides measured in the intact syrinx
(Suthers 1990, *Nature* 347:473–477; Goller & Suthers 1996a/b, *J.
Neurophysiol.* 75:867–876, 76:287–300). Also two-voice complexity even from a
single side (Zollinger, Riede & Suthers 2008, *J. Exp. Biol.* 211:1978–1991).
Plus the coupling mathematics of Laje & Mindlin 2005, already shipped
(`twovoice.py`, docs/15 §5).

Fit (pre-registered, docs/15 §5): one second-voice
contour per fitted type searched against the type's **measured second-source
evidence** — inter-harmonic sidebands in the observation spectra, the
observable the hand-set default cannot see. Evidence the path works: 2 027 of
5 922 screened types won (docs/16 §16.4). The hand-set bake-off already showed
the coupling adding real structure exactly where the single voice was furthest
from the audio (docs/15 §5). Ranked below 1–4 because its win is
concentrated in the biphonation minority of species — for
one-dominant-fundamental species the phantom voice is a cost, which is what the
screen is for.

**6. The fricative remainder.**
The three pieces of docs/16 §16.7 are all in. Formant-filtered noise shipped
(bench 0.584 → 0.656, 13/0). The pressure-driven noise envelope rides the
respiratory drive on the respiration path and the output envelope on the
envelope path (`syrinx.py`'s fricative docstring). The noise-first start for
flatness-heavy types (median member flatness ≥ 0.14, the harvest's p90) ships
where the resynthesis cosine beats the tonal fit (AGENTS.md).

What remains open is honest: most sub-0.3-cosine types are a *different*,
unfixed gap (HANDOFF 2026-07-30). The docs/19 caveat applies retroactively:
every fricative ship was cosine-gated, so a bench re-judgment of the shipped
set is owed. The expectation is that part of that floor is the objective, not
the renderer. The bench is how we find out which.

**7. Tracheal comb per-species measurement and slow modulation.**
The comb is the main carrier of species identity (docs/04 §4.1) and already
ships as one measured float (trachea_f1, `learn.measure_trachea_f1`). What
remains is small: per-species fitted length/reflection from the harvest rather
than per-type defaults, and possibly slow tract-length modulation (the monk
parakeet's trachea shortens 9–44 % during calls — Ohms et al. 2012, *J. Exp.
Biol.* 215:85–92, cited in docs/15 §4). Realism gain within a note is modest.
Species separability gain is real. Ranked last: highest measurement cost per
decibel of naturalness.

## 21.4 What we deliberately will NOT do

No neural audio generation: no DDSP decoder, no RAVE, no diffusion vocoder, no
neural "timbre transfer". This is a decision, not a gap in tooling. docs/04
§4.3/§4.5 already ranked the alternatives and rejected them for this project.
They are not parametrically controllable and not interpretable. They ship
weights the browser contract forbids (no torch in the app, ever). And, the
load-bearing argument, they cannot carry the honesty rule (docs/08 §8.5): every
claim in the UI needs a confidence label grounded in a mechanism a user can
inspect, and a neural generator's mechanism is a weight matrix.

The project's own evidence discipline makes the same point from the other side.
Hand-set *physical* extensions, with five interpretable parameters and the
literature's own equations, still had to lose two bake-offs in public before
earning a fit pass (docs/15 §1/§5). A generator that cannot even state its loss
in physical terms could never be judged that way.

And the one measurement that matters here is already in. The failure mode this
report documents is fit and periphery, not model class. The fix is more physics,
fitted better, not a bigger function approximator. Learned components analyze
and score (the critic, Perch, the bench). They never generate audio. That line
holds.
