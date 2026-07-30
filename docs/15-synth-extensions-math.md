# Birdy synth extensions — extracted mathematics, parameters, and integration notes

## 0. Baseline this extends (so the deltas are precise)

Current contract (`pipeline/src/birdy_pipeline/syrinx.py`, mirrored in `app/src/lib/audio/syrinx-processor.js`):

```
x' = y
y' = -alpha*g^2 - beta*g^2*x - g^2*x^3 - g*x^2*y + g^2*x^2 - g*x*y
```
- Source output = `y` (labial velocity), normalized by ampPP and `SOURCE_GAIN=0.35`, then DC-block + tracking bandpass + static formants/tube comb.
- `alpha = 0.05 + 0.40*ps`; `ps = level * envelope * timbre_gain * (AM gate)`, clamped `[0, 1.4]`. Envelope = linear attack (default 8 ms) + hold/decay + 6 ms release — **per syllable, stateless**.
- `two: true` exists as a second oscillator at `DETUNE_CENTS = 7` — no independent gestures, no coupling.

---

## 1. Respiratory oscillator + injection — Fainstein, Goller & Mindlin (2025), "Nonlinear Biomechanical Resonances in Birdsong"

Sources: [arXiv:2509.11019v2 full text](https://arxiv.org/html/2509.11019v2) (equations 1–4 cited below); Supplemental Material Table S2 (extracted from the arXiv source tarball).

### The respiratory dynamical system

Two **first-order** states (inertial term adiabatically eliminated), nondimensionalized:

```
tau_x * dx/dt = -(1 + x^2)*x - p + F0*f(t)                      (eq. 1)
tau_p * dp/dt = -(1 + x^2)*x - (1 + alpha(p))*p + F0*f(t)      (eq. 2)
```

- `x` = piston (air-sac wall) displacement, `p` = gauge air-sac pressure. The `(1+x^2)x` term is the nonlinear elastic restitution (cubic; measured: during song displacement grows 2× while pressure grows 15×).
- `alpha(p) = alpha_i - (alpha_i - alpha_o)*Theta(p)` — **the Heaviside**: different conductance for inflow (inspiration, p<0) vs outflow (expiration, p>0). This is the inflow/outflow asymmetry docs/09 §9.6 mentions; it makes expiration pulse shapes asymmetric (fast rise, shaped decay) with no hand-designed envelope.
- `f(t)` = amplitude-normalized muscle forcing. Expiratory part: |EMG| through a critically damped 2nd-order filter with **tau = 5 ms** (eqs. 3–4: `x1' = x2; x2' = -(x1 - m(t))/tau^2 - 2*x2/tau`), normalized by its P10/P90 percentiles; inspiratory part: a half-wave sinusoid filling each expiratory-silence interval (mini-breath). `F0` scales forcing amplitude.

### Parameter values (Supplemental Table S2, grid-search intervals; 5 canaries)

| Parameter | Interval | Meaning |
|---|---|---|
| `tau_x` | 0.01–0.25 s | restitution/dissipation time (beta/k) |
| `tau_p` | 0.005–0.2 s | cavity filling time (V0·beta/(P0·A²)) |
| `alpha_i` | 0.05–6 | inlet conductance asymmetry term |
| `alpha_rel = alpha_i/alpha_o` | 0.025–0.125 | i.e. `alpha_o` is 8–40× `alpha_i` |
| `F0` | 20–200 | forcing amplitude |

Five fitted parameters per bird; a **single set per bird reproduces the whole syllable-type diversity** of that bird's song. Quiet-breathing fit: `tau_x`, `tau_p` held fixed, `alpha_i = alpha_o`, square-wave forcing. Quiet breathing ≈ 2 Hz; song respiratory rates up to 15× resting; canary mini-breath trills up to ~30 Hz. Nonlinear broadening multiplies the amplified bandwidth by ~5 (5.4±1.5), letting syllables be produced at ~94 % of theoretical max magnification.

### How pressure enters the labial model

The paper is respiration-only; the coupling to the syrinx is the standard one in this lineage: **the labial restitution constant IS air-sac pressure**. In Birdy's terms, `p(t)` drives `alpha(t)` — i.e. replace `ps = level * env * gain` in `render_plan` with `ps(t) = scale * p(t)` from eq. (2), and `alpha = ALPHA_OFFSET + ALPHA_SLOPE * ps` stays as is. Normalization reference: pressure is normalized so quiet breathing oscillates in [-1, 1]; song peaks reach ~15× quiet amplitude — so clip/map into Birdy's `[0, 1.4]` ps range (or rescale ALPHA_SLOPE).

### What "ẏ injection" is — with an honest caveat

docs/09 §9.6's claim, verified against the two public reference implementations:

- **saguileran/birdsongs (WaveSongs lineage)** injects the labial **acceleration**: `pi[t] = (0.5 * envelope[t]) * dv[1] + pb[t - L/c]` where `dv[1] = ẏ`, and the back-wave `pb[t] = -r * pi[t - L/c]`, output `pout = (1-r)*pi[t-L/c]` — i.e. ẏ × pressure-envelope, then a **feedback delay-line trachea** (L = 0.025 m, r = 0.65, c = 343 m/s), then a Helmholtz OEC (Ch = 1.43e-10, MG = 20, MB = 1e4, RB = 5e6, Rh = 24e3 — "measured by Gabo Mindlin", Zonotrichia). [syllable.py, `MotorGestures`](https://raw.githubusercontent.com/saguileran/birdsongs/main/birdsongs/syllable.py)
- **zekearneodo/syrinxsynth** injects the **velocity**: `tract_in = t_in * A_1 * x[1]`, with `A_1 = sqrt(envelope) * (1 + 0.1*noise)` — note **√(pressure)**, which is not arbitrary: [Laje & Mindlin 2005, eq. 18–25](http://lsd.df.uba.ar/papers/PhysRevE.72.036218.pdf) derive the tract-input pressure `s(t) = alpha_c*(x - tau*y) + beta_c*(y - tau*ẏ)` with `beta_c ∝ v0 = sqrt(2*ps*M/rho)`, and in the inertive low-frequency limit (crossover `c/(2*pi*d1) ≈ 55 kHz`) only the velocity term survives: **s(t) ≈ (√ps)·y**. [finch.py](https://raw.githubusercontent.com/zekearneodo/syrinxsynth/master/syrinxsynth/dynamo/finch.py)

So "every reference implementation injects ẏ" is **only half true**: birdsongs injects ẏ, syrinxsynth injects y, and the Laje & Mindlin 2005 physics says velocity × √ps. ẏ vs y is a one-pole highpass (+6 dB/oct, 90° phase) — audible as brightness. Birdy currently injects y with amplitude normalised out (ampPP) and the envelope applied as a gain **after** the ODE output; both references apply the pressure **multiplicatively at the injection point** (before the tract), so the tract is genuinely driven harder at higher pressure — that part of §9.6 is uniformly supported.

### Effect on syllable envelopes/attack (measured)

The model reproduces not just syllabic rhythm but the **morphology of individual pressure gestures** from measured EMG (Fig. 2, all 5 birds, Fig. S1). Attack shape, sub-syllable pressure microstructure, and cross-syllable memory (air left in the sacs after the previous syllable shapes the next onset) all emerge from the 2-state dynamics; the Heaviside makes inspiration (mini-breath) fast and expiration shaped. Integration cost: trivial — τ ≥ 5 ms means no oversampling; update once per output sample, in the same numba kernel / worklet loop. The forcing `f(t)` is the new creative gesture: expiratory pulses + half-sine mini-breaths, exactly the two Hartley & Suthers (1989) regimes (mini-breaths below ~30 Hz syllable rate, pulsatile expiration above).

**Integration note:** new module `respiration.py` (2 ODE states, 5 params per species + forcing gesture) replacing `envelope()` in `render_plan`; `ps(t) = clamp(k * p(t))`. Pairs with injecting `ps`-scaled source at the tract input (one multiply, parity-tested). This is docs/13 B1, top priority; it also unblocks song-level rendering (cross-syllable timing lives here).

---

## 2. Dove/pigeon membrane model — Elemans et al. 2009, *Biomechanics and control of vocalization in a non-songbird*

Source: [PMC2607454, full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC2607454/) (J. R. Soc. Interface 6:491–506; ring dove *Streptopelia risoria*).

### Equations of motion (symmetric two-mass model with three massless plates, eqs. 4.3–4.6)

```
dx1/dt = v1
dv1/dt = (1/m1) * (F1 - r1*v1 - k1*x1 + I1 - kc*(x1 - x2))
dx2/dt = v2
dv2/dt = (1/m2) * (F2 - r2*v2 - k2*x2 + I2 - kc*(x2 - x1))
```

with `m1 = m2`, `k1 = k2`, `r1 = r2`; `F_i` = Bernoulli/jet-separation pressure forces, `I_i` = collision force linear in the overlap area of the two LVMs. Intraglottal pressure (eq. 4.2): `Pm = Ps*(1 - a2/a1)`. Sound output = **flow derivative `dU/dt`** (Ishizaka & Flanagan convention). Aperture and rest position (eqs. 4.7–4.8): `x0i = a0i/(2L)`, `ai = a0i + 2L*xi`.

### Control gestures

- **TL muscle** → rest areas `a0i(t)` (aperture/adduction): TL stress range [0, 20] kN/m² mapped linearly to `a0i ∈ [-3, +1] mm²`. Negative rest area = closed syrinx (trill gaps).
- **Transmural pressure + TL stress** `p_sum = p_t + p_TL` → tension parameter `Q(t)`: masses and stiffness rescaled as `m(t) = m/Q(t)`, `k(t) = k*Q(t)`, so the natural frequency is `F(t) = Q(t)*F0` (eq. 4.9). `p_sum` rescaled to **Q ∈ [0.8, 1.2]** to match the coo's frequency range.
- `p_t = p_ICAS - p_CTAS` (eq. 2.1); `p_t` oscillates in phase with ICAS pressure and tracks f0 — **this is what drives f0 in doves: air-sac (transmural) pressure, via membrane tension**, not syringeal muscle tension directly. Bronchial (CTAS) pressure sets the driving gradient and hence onset/amplitude.

### Measured parameter values (Tables 1–2, plus text)

| Parameter | Value |
|---|---|
| LVM height (T1–T2) | 2.2 ± 0.4 mm (n=4) |
| LVM width (thickness) | 1.6 ± 0.3 mm (n=8) |
| LVM length | 3.2 mm; tracheal diameter 3.0 mm |
| m1 = m2 | 1.7×10⁻³ g |
| k1 = k2 | 22.0×10⁻³ g/ms² |
| r1 = r2 | 1.2×10⁻³ g/ms (ξ kept at human vocal-fold value) |
| kc | 6.0×10⁻³ g/ms² |
| a01 = a02 | 0.3 mm² |
| base w / L / h1 / h1+h2 / total | 1.5 / 3.0 / 0.4 / 2.4 / 2.8 mm |
| max air-sac pressure (CTAS/PTAS/ICAS) | 3.5 kPa (35 cmH₂O) |
| tracheal (downstream) pressure | ≤ 0.5 kPa → approximated as 0 |
| transmural pressure amplitude | ~1 kPa |
| TL max isometric stress | 20 kN/m² |
| EMG→pressure delays | 7.7 ± 2.6 ms (inflexion), 21.0 ± 7.4 ms (pressure rise) |

Derived: `F0 = (1/2π)√(k/m) ≈ 573 Hz`; Q ∈ [0.8, 1.2] spans ≈ 460–690 Hz — the ring-dove coo band. Bifurcation behavior: onset pressure drops as rest area → 0 (adduct to phonate); slightly divergent pre-phonatory shape lowers onset and adds period-doubling instabilities.

**Tract:** the model is explicitly *without* tracheal filtering; doves coo with beak/nares closed into an inflating esophageal crop (Riede et al. 2004, JEB 207:4025). **Ballintijn & ten Cate 1998** ([PubMed 9556544](https://pubmed.ncbi.nlm.nih.gov/9556544/), JEB 201:1637–1649, collared dove heliox): the fundamental of unmodulated coo elements is **unchanged in heliox** — killing the whistle hypothesis (a whistle's pitch tracks tract resonances, which shift with sound speed); f0 is set by membrane vibration. Only the *modulation* frequency of FM elements rose with He concentration, saturating at **1.5× the base frequency**, with a half-frequency band appearing in some birds — evidence that resonance properties touch the modulation mechanism only. Tract resonances don't actively shape coos; at most they passively enhance the fundamental. → Renderer: membrane source + *fixed* stopped-tube tract, exactly as docs/13 B3 says.

**Integration note:** new module `dove.py` — 4 ODE states + aperture/tension gestures (`a0(t)`, `Q(t)`), driven by pressure gesture; reuse Birdy's existing `formants`/tube-comb tract fixed per species. f0 gesture enters through `Q(t)` (tension), amplitude/onset through `Ps(t)` and `a0(t)`. Note the honest caveat from the paper: independent AM/FM control is **not** possible with this morphology — the fit should not expect separable contours.

---

## 3. Tracheophone suboscine three-source model — Garcia et al. 2017 + Amador & Mindlin 2023

Sources: [Garcia et al. 2017, PMC5599221, full text incl. STAR Methods model](https://pmc.ncbi.nlm.nih.gov/articles/PMC5599221/) (Curr. Biol. 27:2677–2683); [Amador & Mindlin 2023, JEB 226:jeb227975](https://journals.biologists.com/jeb/article/226/12/jeb227975/316747/The-dynamics-behind-diversity-in-suboscine-songs) ([PDF](http://www.lsd.df.uba.ar/wp-content/uploads/2023/11/Amador-Mindlin-2023-jeb227975.pdf)); reference code [gabomindlin/tracheophones](https://github.com/gabomindlin/tracheophones) ([armando_una_revision.c](https://raw.githubusercontent.com/gabomindlin/tracheophones/master/armando_una_revision.c)).

**Anatomy (Garcia 2017):** tracheophones have **three** sources — two oscine-like bronchial labial pairs (BL) plus the unique *membrana trachealis* (MT) pair in the trachea above the bifurcation. Disabling the MT: pulse-like quality drops (duty cycle rises), amplitude drops, f0 rises. The 2023 review is a **review** — the quantitative model lives in Garcia 2017's STAR Methods; the review's contribution is the comparative framing (plantcutter, kiskadee, tracheophone) and the justification that synchronized identical BL pairs collapse to one oscillator.

### The model (verified against the released C code; paper equations in STAR Methods)

```
dx1/dt = y1
dy1/dt = 3*g1*(10*mu1 - x1^2)*y1 - g1^2*(x1 + 0.8*x1^3)      // bronchial labia (BL pair, synchronized → one oscillator)
dx2/dt = y2
dy2/dt = mu3*g2*(10*mu2 - x2^2)*y2 - g2^2*(x2 + 0.8*x2^3)     // MT
```

Rayleigh-type nonlinear damping + Duffing cubic restitution. `mu1`, `mu2` = transluminal pressures at labia and MT; `mu3` = MT damping gain; `g1 = 5000`, `g2 = 4000` (time scales). **Coupling is cross-pressure modulation** — each source's displacement modulates the *other* source's transluminal pressure:

```
mu1 = 0.1 + 0.25*sin(pi*t/1.8) - 0.25*x2     // MT displacement pushes labial pressure
mu2 = -0.1 + 0.25*sin(pi*t/1.8) + 0.1*x1     // labial displacement pushes MT pressure
mu3 = 6.0   (paper; the released code also runs 3.5)
```

Sound output = linear superposition, `x1 + 0.1*x2` in the code. MT disabled: `mu2 = -0.5`.

### Parameter regimes (the "diversity")

- `mu1` small, frequencies disparate → **pulsations**: MT (low freq) amplitude-modulates the labial source — the hornero's up-to-650 Hz AM, achieved with no neuromuscular gating (denervation-proof).
- `mu1` raised → sources **lock** at an intermediate frequency below the labia's autonomous one.
- Pressure crosses the pulsation↔locking transition — so a single slow pressure gesture sweeps both regimes; different tracheophone species sit at different points (large f0 shift in *Furnarius*, small in *Thamnophilus*).
- Related regimes in the same review: plantcutter pulses from a SNILC-born pulse generator filtered by a static Helmholtz OEC ([Uribarri et al. 2020, PRL 124:098101](http://lsd.df.uba.ar/papers/PhysRevLett.124.098101.pdf): `θ̇ = γ1(μ - sinθ)`, pulse rate 50–300 Hz; `Pb(t) = ẋ(t) - r*Pb(t-2T)`; OEC `z'' = -γ2²ωr²z - 60γ2 z' - γ2²PT`; sim values `(γ1, γ2, r, ωr) = (9×10³, 18.0, 0.3, 148.2)`, `μ ≈ 1.005`, OEC resonance ~3.5–4.1 kHz measured, ~6.5 % within-bird CV — a *static* filter encoding body size); kiskadee AM from **two slightly detuned coupled sources** whose frequency difference grows with pressure until synchrony breaks ([Döppler et al. 2020, PRE 102:062415](https://doi.org/10.1103/PhysRevE.102.062415); AM band 160–190 Hz, accentuated by the ovm muscle).

**Integration note:** new module `tracheophone.py` — two 2-state oscillators with cross-pressure coupling (4 states total); the MT oscillator is Birdy's existing normal form with the cubic-restitution swapped to the Duffing-Rayleigh form above (or keep Birdy's form and add the `-0.25*x2` pressure coupling — both defensible, but the released code is the citation-grade version). Output = weighted sum before the tract. Honesty label "three-source tracheophone model".

---

## 4. Parrot articulation — Larsen & Goller 1999 + Beckers et al. 2004 (+ Ohms et al. 2012)

Sources: Larsen & Goller 1999, Proc. R. Soc. B 266:1609–1615 ([JSTOR 51514](https://www.jstor.org/stable/51514); RS page 403s scrapers, content verified via the [Cambridge excerpt of Suthers, Beckers & Nelson's chapter](https://assets.cambridge.org/97805218/29182/excerpt/9780521829182_excerpt.pdf) and secondary excerpts); [Beckers, Nelson & Suthers 2004, PubMed 15341748](https://pubmed.ncbi.nlm.nih.gov/15341748/) (Curr. Biol. 14:1592–1597); [Ohms et al. 2012, JEB 215:85–92, open access](https://journals.biologists.com/jeb/article/215/1/85/10797/Vocal-tract-articulation-revisited-the-case-of-the).

- **Source (Larsen & Goller 1999):** endoscopy + optical vibration measurement in cockatiels (and hill myna): sound is generated by oscillation of the **single pair of lateral tympaniform membranes (LTMs)** adducted into the tracheal lumen; measured membrane vibration frequency matches the emitted f0; cockatiels show a continuum from harmonic-rich to tonal *without* altered vibratory behavior — the tract does the tonal shaping. One source, tracheal location → no two-voice.
- **Tongue → formants (Beckers et al. 2004):** syrinx replaced by a broadband speaker in 5 monk parakeets; tongue movements cause significant **frequency changes in two of the four formants between 0.5 and 10 kHz, and amplitude changes in all four**. Quantified direction (via Ohms 2012's summary): **tongue back → F3 rises, F1 slightly falls**; vertical (high-low) tongue manipulations have a general attenuating effect on formant amplitudes.
- **Natural articulation (Ohms et al. 2012, X-ray of spontaneously calling birds):** tongue rests high against the upper mandible and **depresses 2.9–4.3 mm** at call onset; beak opens 5.6–6.7 mm (contact) / 3.0–4.8 mm (greeting); **trachea shortens 9–44 %** during calls (a previously unknown articulator; trachea 55–65 mm → stopped-tube resonances 1570/1330 Hz, inside the measured spectral-peak range); articulators move *before* sound onset (pre-shaping). No OEC inflation in parrots (unlike songbirds).
- African grey speech mimicry (Warren et al. 1996, Auk 113:41): /a/ = trachea protracted + beak closed; /i/ = opposite — front-back tongue position is the mimicked-vowel axis.

**Integration note:** one Birdy source (existing ODE; LTM = one labium pair) + replace the f0-tracking OEC band with a **2–3 formant bank driven by a tongue gesture** `g(t) ∈ [0,1]`: F1 ≈ base*(1 − 0.1*g), F3 ≈ base*(1 + k*g), amplitude attenuation with vertical component; fixed tracheal formant from the (shortenable) tube comb — the existing `formants`/`tube` mechanisms already do this; the new piece is the gesture mapping. Honesty label "one source + lingual formant bank (Beckers 2004 mapping)".

---

## 5. Two-voice coupling — Laje & Mindlin 2005

Source: [Laje & Mindlin 2005, PRE 72:036218, full PDF](http://lsd.df.uba.ar/papers/PhysRevE.72.036218.pdf). (Follow-up applying it to an oscine: Laje, Sciamarella, Zanella & Mindlin 2008, PRE 77:011912.)

**Coupling form — acoustic, through the shared tracheal pressure `pi(t)`** (main result, eqs. 62–67, small-coupling approximation):

```
ẋj = yj
ẏj = fj(xj,yj) + pgj ,        fj = -eps_j*xj - bj*yj - cj*xj²*yj - f0j ,   j ∈ {l, r}
pgj = ps + (Dj*yj - Aj)*(ps - p̃i)
p̃i(t) = αl(xl - τl*yl) + βl*yl + αr(xr - τr*yr) + βr*yr - γ_refl*pi(t - T)
pi(t) = αl(xl - τl*yl) + βl(yl - τl*ẏl) + αr(xr - τr*yr) + βr(yr - τr*ẏr) - γ_refl*pi(t - T)
```

Each source injects into the shared trachea; the sum (plus the round-trip reflection `-γ_refl*pi(t-T)`, T = 2L/c) acts back on **both** sources through `(ps - pi)` in their interlabial pressure. There is no direct spring between the sources — the coupling is the shared pressure field. In the low-frequency inertive limit each source's injection ≈ `βj*yj` with `βj ∝ √(2 ps M/ρ)` — i.e. **∝ √air-sac pressure × velocity**, the formula syrinxsynth implements.

**Strength (Table I):** `α = 1.2×10⁶ cm/s`, `β = 1.5×10³ s⁻¹`, `τ = 1×10⁻⁴ s`, `γ_refl = 0.9`, `L = 2.0 cm`, `ps = 6×10⁶`, `eps = 3×10⁸ s⁻²`, `b = 2×10⁴ s⁻¹`, `c = 2×10⁸ s⁻¹cm⁻²`, `f0 = 4.9×10⁴ cm/s²`, `x0 = 0.04 cm`, `h = 0.1 cm`, `M = 5×10⁻³ g/cm²`, `A = 1.0`, `D = 5×10⁻³ cm`. Small-coupling condition: `βj ≪ 1/τj` (here 1.5×10³ ≪ 10⁴ — satisfied). **Weak but consequential**: with both sources active and feedback off, sums/differences of the two fundamentals appear (subharmonics; every spectral line a multiple of the frequency difference — their Fig. 6 with `eps_l = 2.4×10⁸`, `eps_r = 1.4×10⁸`); with one source active, feedback alone produces period-doubling. Fletcher's earlier verdict ([1988, "Bird Song — A Quantitative Acoustic Model"](https://www.phys.unsw.edu.au/music/people/publications/Fletcher1988.pdf)) agrees: coupling arises *only* because tracheal pressure acts on both membranes, is weak, and suffices to lock sources already near coincidence.

**Integration note:** this is docs/13 B2. Two instances of the existing ODE with independent `(α, β)` streams; coupling = shared scalar `pi(t)` with one tracheal delay `T = 2L/c` (Birdy already has the fractional-delay machinery in `_tube_comb`) and reflection `γ_refl ≈ 0.9`; each source's effective pressure becomes `ps - pi`. Weak-coupling approximation means the implicit acceleration terms can be dropped — plain Euler stays explicit, parity-testable.

---

## 6. What else is out there — ranked

1. **Pulse-rattle suboscines (plantcutter class) — implementable now, with published parameters.** The Uribarri 2020 model above (overdamped SNILC pulse generator + feedback trachea + static Helmholtz OEC) is a complete renderer for "rusty-hinge" birds with five fitted numbers and a body-size validation; it is arguably a cheaper first per-taxon pilot than the dove. 2. **Echolocation clicks (oilbird, swiftlets):** syringeal click trains; the oilbird's asymmetric bronchial semi-syrinxes make each bronchus contribute a formant, giving individuals unique formant signatures (Suthers & Hector 1985; Fletcher & Tarnopolsky 1999 [vocal-tract acoustics PDF](https://www.phys.unsw.edu.au/music/people/publications/Fletcheretal1999a.pdf); [Suthers 2013 review, Front. Physiol.](https://public-pages-files-2025.frontiersin.org/journals/physiology/articles/10.3389/fphys.2013.00123/epub)). Renderer: short pulse train + two fixed resonators — trivially in scope. 3. **Non-syringeal sonations (in scope for "all natural sounds", but they need a new module class, not the syrinx):** feather **aeroelastic flutter** (snipe winnowing, hummingbird tail/wing, dove wing whistles — a limit-cycle oscillator switched on above a threshold airspeed, frequency set by feather stiffness/geometry, tonal with strong harmonics; [Clark et al. 2015, JEB 218:3520](https://journals.biologists.com/jeb/article/218/21/3520/14411/Aeroelastic-flutter-of-feathers-flight-and-the)); manakin **stridulation/wing percussion** (club-winged manakin resonant stridulation, [Bostwick et al. 2009, PMC2842718](https://pmc.ncbi.nlm.nih.gov/articles/PMC2842718/); golden-collared manakin wing-collision snap, ~5 kHz peak, JEB 219:1524); **woodpecker drumming, stork bill-clattering, grouse drumming** — damped resonant bursts in rhythmic trains (modal synthesis). All are honest, physically labelled renderers; none belongs inside `syrinx.py`. 4. **Owls, galliforms, ratites, nightjars:** no quantitatively specified low-dimensional production model exists; owl hoots and nightjar churring are already approximable by the current synth + fixed tract (nightjars do have bronchial semi-syrinxes per the Cambridge excerpt — a two-source candidate if measurements ever appear). Rank them last: the honest claim today is "existing oscine model, no taxon-specific physics published".

### Caveats

- Royal Society (Larsen & Goller 1999) and Cell Press (Beckers 2004) full texts were paywall-blocked; their content here is via the Cambridge chapter excerpt, PubMed abstracts, and Ohms 2012's quantified summary — all cited above. Everything else was read in full text or from author-released code.
- The Amador & Mindlin 2023 JEB paper is a review; the implementable equations for the tracheophone come from Garcia 2017's STAR Methods + the released C code (parameters `mu3` differs: 6.0 in the paper, 3.5 in the code — noted).
- docs/09 §9.6's "every reference implementation injects ẏ" is inaccurate for syrinxsynth (which injects y × √envelope, matching Laje & Mindlin 2005's low-frequency physics); birdsongs does inject ẏ × envelope. Both apply pressure multiplicatively at the tract input, which Birdy does not — that shared part is the defensible change.