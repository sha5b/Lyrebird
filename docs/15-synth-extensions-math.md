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
- `alpha(p) = alpha_i - (alpha_i - alpha_o)*Theta(p)` — **the Heaviside**: different conductance for inflow (inspiration, p<0) vs outflow (expiration, p>0). This is the inflow/outflow asymmetry docs/09 §9.6 mentions. It makes expiration pulse shapes asymmetric (fast rise, shaped decay) with no hand-designed envelope.
- `f(t)` = amplitude-normalized muscle forcing. Expiratory part: |EMG| through a critically damped 2nd-order filter with **tau = 5 ms** (eqs. 3–4: `x1' = x2; x2' = -(x1 - m(t))/tau^2 - 2*x2/tau`), normalized by its P10/P90 percentiles. The inspiratory part is a half-wave sinusoid that fills each expiratory-silence interval (mini-breath). `F0` scales forcing amplitude.

### Parameter values (Supplemental Table S2, grid-search intervals; 5 canaries)

| Parameter | Interval | Meaning |
|---|---|---|
| `tau_x` | 0.01–0.25 s | restitution/dissipation time (beta/k) |
| `tau_p` | 0.005–0.2 s | cavity filling time (V0·beta/(P0·A²)) |
| `alpha_i` | 0.05–6 | inlet conductance asymmetry term |
| `alpha_rel = alpha_i/alpha_o` | 0.025–0.125 | i.e. `alpha_o` is 8–40× `alpha_i` |
| `F0` | 20–200 | forcing amplitude |

Five fitted parameters per bird. A **single set per bird reproduces the whole syllable-type diversity** of that bird's song. Quiet-breathing fit: hold `tau_x` and `tau_p` fixed, set `alpha_i = alpha_o`, and use square-wave forcing. Quiet breathing ≈ 2 Hz. Song respiratory rates go up to 15× resting. Canary mini-breath trills go up to ~30 Hz. Nonlinear broadening multiplies the amplified bandwidth by ~5 (5.4±1.5). This lets the bird produce syllables at ~94 % of the theoretical max magnification.

### How pressure enters the labial model

The paper is respiration-only. The coupling to the syrinx is the standard one in this lineage: **the labial restitution constant IS air-sac pressure**. In Birdy's terms, `p(t)` drives `alpha(t)`. Concretely, replace `ps = level * env * gain` in `render_plan` with `ps(t) = scale * p(t)` from eq. (2). `alpha = ALPHA_OFFSET + ALPHA_SLOPE * ps` stays as is. Normalization reference: the paper normalizes pressure so quiet breathing oscillates in [-1, 1]. Song peaks reach ~15× quiet amplitude, so clip or map into Birdy's `[0, 1.4]` ps range (or rescale ALPHA_SLOPE).

### What "ẏ injection" is — with an honest caveat

docs/09 §9.6's claim, verified against the two public reference implementations:

- **saguileran/birdsongs (WaveSongs lineage)** injects the labial **acceleration**: `pi[t] = (0.5 * envelope[t]) * dv[1] + pb[t - L/c]` where `dv[1] = ẏ`, and the back-wave `pb[t] = -r * pi[t - L/c]`, output `pout = (1-r)*pi[t-L/c]` — i.e. ẏ × pressure-envelope, then a **feedback delay-line trachea** (L = 0.025 m, r = 0.65, c = 343 m/s), then a Helmholtz OEC (Ch = 1.43e-10, MG = 20, MB = 1e4, RB = 5e6, Rh = 24e3 — "measured by Gabo Mindlin", Zonotrichia). [syllable.py, `MotorGestures`](https://raw.githubusercontent.com/saguileran/birdsongs/main/birdsongs/syllable.py)
- **zekearneodo/syrinxsynth** injects the **velocity**: `tract_in = t_in * A_1 * x[1]`, with `A_1 = sqrt(envelope) * (1 + 0.1*noise)` — note **√(pressure)**, which is not arbitrary: [Laje & Mindlin 2005, eq. 18–25](http://lsd.df.uba.ar/papers/PhysRevE.72.036218.pdf) derive the tract-input pressure `s(t) = alpha_c*(x - tau*y) + beta_c*(y - tau*ẏ)` with `beta_c ∝ v0 = sqrt(2*ps*M/rho)`, and in the inertive low-frequency limit (crossover `c/(2*pi*d1) ≈ 55 kHz`) only the velocity term survives: **s(t) ≈ (√ps)·y**. [finch.py](https://raw.githubusercontent.com/zekearneodo/syrinxsynth/master/syrinxsynth/dynamo/finch.py)

So "every reference implementation injects ẏ" is **only half true**: birdsongs injects ẏ, syrinxsynth injects y, and the Laje & Mindlin 2005 physics says velocity × √ps. ẏ against y is a one-pole highpass (+6 dB/oct, 90° phase), audible as brightness. Birdy currently injects y with the amplitude normalized out (ampPP) and applies the envelope as a gain **after** the ODE output. Both references apply the pressure **multiplicatively at the injection point** (before the tract), so the tract is genuinely driven harder at higher pressure. That part of §9.6 is uniformly supported.

### Effect on syllable envelopes/attack (measured)

The model reproduces not just syllabic rhythm but the **morphology of individual pressure gestures** from measured EMG (Fig. 2, all 5 birds, Fig. S1). Attack shape, sub-syllable pressure microstructure, and cross-syllable memory all emerge from the 2-state dynamics. Cross-syllable memory means that air left in the sacs after the previous syllable shapes the next onset. The Heaviside makes inspiration (mini-breath) fast and expiration shaped. Integration cost is trivial: τ ≥ 5 ms means no oversampling. Update the states once per output sample, in the same numba kernel / worklet loop. The forcing `f(t)` is the new creative gesture: expiratory pulses + half-sine mini-breaths. These are exactly the two Hartley & Suthers (1989) regimes: mini-breaths below ~30 Hz syllable rate, pulsatile expiration above.

**Integration note:** a new module `respiration.py` (2 ODE states, 5 params per species + forcing gesture) replaces `envelope()` in `render_plan`, with `ps(t) = clamp(k * p(t))`. It pairs with injecting the `ps`-scaled source at the tract input (one multiply, parity-tested). This is docs/13 B1, top priority. It also unblocks song-level rendering (cross-syllable timing lives here).

### Implementation status (2026-07-30)

Shipped as written above, with three refinements the extraction implies but does not spell out:

- **AM stays at the labia.** The within-syllable `am` gate is *not* part of the forcing. Pushing a 12-40 Hz gate through `tau_p` of pressure dynamics smears a trill into mush. This is the physics telling you that fast AM is syringeal, not respiratory (Hartley & Suthers' two regimes are about *syllable* rate, not within-syllable modulation). The gate modulates `ps` after the ODE exactly as on the envelope path. The tract-input drive uses the un-gated air-sac pressure, because that is what the sacs hold.
- **The steady state is p = 0.** Under any constant forcing, eq. (2) equilibrates at `alpha*p = 0`. Sustained pressure requires the muscle command to keep growing against the piston's cubic restitution (the paper's "pressure grows 15x while displacement grows 2x"). A hand-set flat envelope cannot do that, so the default set sits at the weak-damping, slow-piston corner of Table S2 (`tau_x=0.25, tau_p=0.2, alpha_i=0.05, alpha_rel=0.125, forcing=35`). We chose it among twelve candidates on the pre-registered bake-off below.
- **Mini-breaths are bout-level.** Interior silences of ≥ 12 ms in the forcing get a negative half-sine (implemented, unit-tested, state-carry bit-exact for chaining). Per-syllable envelopes have no interior silences, so the path stays dormant until song-level rendering drives the oscillator across a bout.

Schema: syllables carry an optional `respiration: {tauX, tauP, alphaI, alphaRel, forcing}` block (`forcing` is the paper's F0 — the name means pitch everywhere else here). No block → the envelope path, bit-identical to before. The parity fixtures `respiration` and `respiration+am` pin the new path on both sides (14/14, worst diff 2.8e-08).

**Bake-off, pre-registered** (`learn --no-invert` on the five-species harvest-mp copy, 81 types, the feature attaching the default set to every fitted type): median resynthesis cosine **0.343 → 0.336**, nearest-own **17/81 → 20/81**, worst −0.281 → −0.235. Per species: wren 0.589 → 0.600, great tit 0.408 → 0.419, blackbird 0.283 → 0.268, tawny owl 0.181 → 0.168, cuckoo 0.153 → 0.110. The losses concentrate in sub-50 ms notes. There the shaped attack (~20-40 ms, the physically correct onset) eats a third of the note, and no hand-set constant forcing can rebuild it faster. Raising `level` does not recover these notes, so the problem is the onset *shape*, not loudness.

**How the fit will work (pre-registered, not built).** One parameter set per species. A coordinate search over the five Table S2 ranges uses the same machinery as `learn.invert_gestures`, seeded from the default set. The judge is docs/09's numbers: median resynthesis cosine and species placement on the fixed store, against the envelope baseline of the same run. The forcing for the fit is the type's measured gesture (attack/duration/AM from the observations), not the median envelope. This is what gives short-note species the impulsive commands their onsets need. We record a negative result in place per §9.7's pattern. The flag `learn --respiration` stays off by default until the fit wins.

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
- `p_t = p_ICAS - p_CTAS` (eq. 2.1). `p_t` oscillates in phase with ICAS pressure and tracks f0 — **this is what drives f0 in doves: air-sac (transmural) pressure, through membrane tension**, not syringeal muscle tension directly. Bronchial (CTAS) pressure sets the driving gradient, and so the onset and amplitude.

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

Derived: `F0 = (1/2π)√(k/m) ≈ 573 Hz`. Q ∈ [0.8, 1.2] spans ≈ 460–690 Hz — the ring-dove coo band. Bifurcation behavior: the onset pressure drops as rest area → 0 (adduct to phonate). A slightly divergent pre-phonatory shape lowers the onset and adds period-doubling instabilities.

**Tract:** the model is explicitly *without* tracheal filtering. Doves coo with beak/nares closed into an inflating esophageal crop (Riede et al. 2004, JEB 207:4025). **Ballintijn & ten Cate 1998** ([PubMed 9556544](https://pubmed.ncbi.nlm.nih.gov/9556544/), JEB 201:1637–1649, collared dove heliox): the fundamental of unmodulated coo elements is **unchanged in heliox**. This kills the whistle hypothesis: a whistle's pitch tracks tract resonances, which shift with sound speed. The membrane vibration sets f0 directly. Only the *modulation* frequency of FM elements rose with He concentration, saturating at **1.5× the base frequency**, with a half-frequency band appearing in some birds. This is evidence that resonance properties touch the modulation mechanism only. Tract resonances do not actively shape coos. At most they passively enhance the fundamental. → Renderer: membrane source + *fixed* stopped-tube tract, exactly as docs/13 B3 says.

**Integration note:** a new module `dove.py` holds 4 ODE states + aperture/tension gestures (`a0(t)`, `Q(t)`), driven by a pressure gesture. It reuses Birdy's existing `formants`/tube-comb tract, fixed per species. The f0 gesture enters through `Q(t)` (tension). Amplitude and onset enter through `Ps(t)` and `a0(t)`. Note the honest caveat from the paper: independent AM/FM control is **not** possible with this morphology. The fit should not expect separable contours.

---

## 3. Tracheophone suboscine three-source model — Garcia et al. 2017 + Amador & Mindlin 2023

Sources: [Garcia et al. 2017, PMC5599221, full text incl. STAR Methods model](https://pmc.ncbi.nlm.nih.gov/articles/PMC5599221/) (Curr. Biol. 27:2677–2683); [Amador & Mindlin 2023, JEB 226:jeb227975](https://journals.biologists.com/jeb/article/226/12/jeb227975/316747/The-dynamics-behind-diversity-in-suboscine-songs) ([PDF](http://www.lsd.df.uba.ar/wp-content/uploads/2023/11/Amador-Mindlin-2023-jeb227975.pdf)); reference code [gabomindlin/tracheophones](https://github.com/gabomindlin/tracheophones) ([armando_una_revision.c](https://raw.githubusercontent.com/gabomindlin/tracheophones/master/armando_una_revision.c)).

**Anatomy (Garcia 2017):** tracheophones have **three** sources: two oscine-like bronchial labial pairs (BL) plus the unique *membrana trachealis* (MT) pair in the trachea above the bifurcation. Disabling the MT: the pulse-like quality drops (duty cycle rises), the amplitude drops, and f0 rises. The 2023 paper is a **review**. The quantitative model lives in Garcia 2017's STAR Methods. The review's contribution is the comparative framing (plantcutter, kiskadee, tracheophone) and the justification that synchronized identical BL pairs collapse to one oscillator.

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
- Pressure crosses the pulsation↔locking transition, so a single slow pressure gesture sweeps both regimes. Different tracheophone species sit at different points (large f0 shift in *Furnarius*, small in *Thamnophilus*).
- Related regimes in the same review: plantcutter pulses from a SNILC-born pulse generator filtered by a static Helmholtz OEC ([Uribarri et al. 2020, PRL 124:098101](http://lsd.df.uba.ar/papers/PhysRevLett.124.098101.pdf): `θ̇ = γ1(μ - sinθ)`, pulse rate 50–300 Hz; `Pb(t) = ẋ(t) - r*Pb(t-2T)`; OEC `z'' = -γ2²ωr²z - 60γ2 z' - γ2²PT`; sim values `(γ1, γ2, r, ωr) = (9×10³, 18.0, 0.3, 148.2)`, `μ ≈ 1.005`, OEC resonance ~3.5–4.1 kHz measured, ~6.5 % within-bird CV — a *static* filter encoding body size); kiskadee AM from **two slightly detuned coupled sources** whose frequency difference grows with pressure until synchrony breaks ([Döppler et al. 2020, PRE 102:062415](https://doi.org/10.1103/PhysRevE.102.062415); AM band 160–190 Hz, accentuated by the ovm muscle).

**Integration note:** a new module `tracheophone.py` holds two 2-state oscillators with cross-pressure coupling (4 states total). The MT oscillator is Birdy's existing normal form with the cubic restitution swapped to the Duffing-Rayleigh form above. (Or keep Birdy's form and add the `-0.25*x2` pressure coupling. Both are defensible, but the released code is the citation-grade version.) Output = weighted sum before the tract. Honesty label "three-source tracheophone model".

---

## 4. Parrot articulation — Larsen & Goller 1999 + Beckers et al. 2004 (+ Ohms et al. 2012)

Sources: Larsen & Goller 1999, Proc. R. Soc. B 266:1609–1615 ([JSTOR 51514](https://www.jstor.org/stable/51514); RS page 403s scrapers, content verified via the [Cambridge excerpt of Suthers, Beckers & Nelson's chapter](https://assets.cambridge.org/97805218/29182/excerpt/9780521829182_excerpt.pdf) and secondary excerpts); [Beckers, Nelson & Suthers 2004, PubMed 15341748](https://pubmed.ncbi.nlm.nih.gov/15341748/) (Curr. Biol. 14:1592–1597); [Ohms et al. 2012, JEB 215:85–92, open access](https://journals.biologists.com/jeb/article/215/1/85/10797/Vocal-tract-articulation-revisited-the-case-of-the).

- **Source (Larsen & Goller 1999):** endoscopy + optical vibration measurement in cockatiels (and hill myna). The **single pair of lateral tympaniform membranes (LTMs)**, adducted into the tracheal lumen, oscillates and generates the sound. The emitted f0 matches the measured membrane vibration frequency. Cockatiels show a continuum from harmonic-rich to tonal *without* altered vibratory behavior, so the tract does the tonal shaping. One source, tracheal location → no two-voice.
- **Tongue → formants (Beckers et al. 2004):** the team replaced the syrinx with a broadband speaker in 5 monk parakeets. Tongue movements cause significant **frequency changes in two of the four formants between 0.5 and 10 kHz, and amplitude changes in all four**. Quantified direction (via Ohms 2012's summary): **tongue back → F3 rises, F1 slightly falls**. Vertical (high-low) tongue manipulations have a general attenuating effect on formant amplitudes.
- **Natural articulation (Ohms et al. 2012, X-ray of spontaneously calling birds):** the tongue rests high against the upper mandible and **depresses 2.9–4.3 mm** at call onset. The beak opens 5.6–6.7 mm (contact) / 3.0–4.8 mm (greeting). The **trachea shortens 9–44 %** during calls. This is a previously unknown articulator: the trachea is 55–65 mm long, so its stopped-tube resonances sit at 1570/1330 Hz, inside the measured spectral-peak range. Articulators move *before* sound onset (pre-shaping). No OEC inflation in parrots (unlike songbirds).
- African grey speech mimicry (Warren et al. 1996, Auk 113:41): /a/ = trachea protracted + beak closed. /i/ = the opposite. Front-back tongue position is the mimicked-vowel axis.

**Integration note:** keep one Birdy source (existing ODE, LTM = one labium pair) and replace the f0-tracking OEC band with a **2–3 formant bank driven by a tongue gesture** `g(t) ∈ [0,1]`: F1 ≈ base*(1 − 0.1*g), F3 ≈ base*(1 + k*g), amplitude attenuation with the vertical component. A fixed tracheal formant comes from the (shortenable) tube comb. The existing `formants`/`tube` mechanisms already do this. The new piece is the gesture mapping. Honesty label "one source + lingual formant bank (Beckers 2004 mapping)".

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

Each source injects into the shared trachea. The sum (plus the round-trip reflection `-γ_refl*pi(t-T)`, T = 2L/c) acts back on **both** sources through `(ps - pi)` in their interlabial pressure. There is no direct spring between the sources. The coupling is the shared pressure field. In the low-frequency inertive limit each source's injection ≈ `βj*yj` with `βj ∝ √(2 ps M/ρ)`. That is **∝ √air-sac pressure × velocity**, the formula syrinxsynth implements.

**Strength (Table I):** `α = 1.2×10⁶ cm/s`, `β = 1.5×10³ s⁻¹`, `τ = 1×10⁻⁴ s`, `γ_refl = 0.9`, `L = 2.0 cm`, `ps = 6×10⁶`, `eps = 3×10⁸ s⁻²`, `b = 2×10⁴ s⁻¹`, `c = 2×10⁸ s⁻¹cm⁻²`, `f0 = 4.9×10⁴ cm/s²`, `x0 = 0.04 cm`, `h = 0.1 cm`, `M = 5×10⁻³ g/cm²`, `A = 1.0`, `D = 5×10⁻³ cm`. Small-coupling condition: `βj ≪ 1/τj` (here 1.5×10³ ≪ 10⁴ — satisfied). **Weak but consequential**: with both sources active and feedback off, sums and differences of the two fundamentals appear. These are subharmonics: every spectral line is a multiple of the frequency difference (their Fig. 6 with `eps_l = 2.4×10⁸`, `eps_r = 1.4×10⁸`). With one source active, feedback alone produces period-doubling. Fletcher's earlier verdict ([1988, "Bird Song — A Quantitative Acoustic Model"](https://www.phys.unsw.edu.au/music/people/publications/Fletcher1988.pdf)) agrees: coupling arises *only* because tracheal pressure acts on both membranes. The coupling is weak, and it suffices to lock sources already near coincidence.

**Integration note:** this is docs/13 B2. Use two instances of the existing ODE with independent `(α, β)` streams. The coupling is a shared scalar `pi(t)` with one tracheal delay `T = 2L/c` (Birdy already has the fractional-delay machinery in `_tube_comb`) and reflection `γ_refl ≈ 0.9`. Each source's effective pressure becomes `ps - pi`. The weak-coupling approximation means we can drop the implicit acceleration terms. Plain Euler stays explicit and parity-testable.

### Implementation status (2026-07-30)

Shipped as written above, with the mapping choices the extraction leaves open made explicit:

- **The back-action lands on `alpha`, not on the output.** In Birdy's nondimensionalization the labial restitution constant IS the air-sac pressure (`alpha = 0.05 + 0.40*ps`), so `(ps - pi)` becomes `alpha_j - 0.40*pi` per source. A positive tracheal pressure subtracts from the drive. This is the mechanism that locks near-coincident sources and period-doubles a lone one. The injection keeps the paper's low-frequency form: `betaInj * sqrt(ps_j) * y_j/gamma_j` per source, velocity times root pressure. This is the same √ps lineage as the respiration path's tract drive.
- **Update discipline is per output sample**, like alpha and beta themselves. The renderer computes `pi` from the oscillator states at the top of the sample and holds it across the sample's oversampled substeps. The delay line is fractional with linear interpolation. This is the `_tube_comb` discipline: a 2 cm round trip is 5.6 samples at 48 kHz, and an integer delay would move the tracheal resonances by hundreds of Hz. A closed right bronchus (`level: 0`) injects nothing (`sqrt(0)*y = 0`), and the mix drops it. This is the single-source-plus-feedback case.
- **Measured strength** (120 ms two-voice syllable at ps ~ 0.85, the parity fixture's parameters). At the default `betaInj = 0.05`, mean |pi| is ~0.04 of peak ps, with transients to ~0.2, against the uncoupled render. The difference-frequency line |f_a − f_b| triples and the f_a/2 subharmonic quadruples. At `betaInj = 0.25`, pi reaches ~4x ps and the fundamental collapses into the period-doubled regime. This is the strong-coupling boundary past which the dropped implicit terms are no longer small. It is also the reason the parser's ceiling is a stability guard, not a fit bound.

Schema: syllables carry an optional `voices: {contour, gamma, level, tracheaCm, refl, betaInj}` block (`twovoice.py`). No block → the old path, bit-identical. A block with `betaInj = 0, level = 0` renders bit-identically to no block (asserted in `learn.self_test`). `two: true` stays the uncoupled 7-cent shimmer, and the renderer ignores it when a block exists. The parity fixtures `voices` (both sources active) and `voices one active` (single-source feedback) pin the path on both sides (16/16, worst diff 2.8e-08).

**Bake-off, pre-registered** (`learn --no-invert` on the five-species harvest-mp copy, 81 types, the flag attaching the hand-set default — the type's contour shifted by √(2.4/1.4), the Fig. 6 eps ratio — to every fitted type): the default-off path is bit-identical to before the change (median cosine **0.343**, nearest-own **17/81**, learned blocks literally equal), and the two-voice render scores median **0.343 → 0.294**, nearest-own **17/81 → 15/81**, worst −0.281 → −0.311. Per species: wren 0.589 → 0.496, great tit 0.408 → 0.297, blackbird 0.283 → 0.282, tawny owl 0.181 → 0.189, cuckoo 0.153 → 0.187. The loss concentrates where it should. The two-tonal species are fitted to audio with one dominant fundamental. For them a phantom second voice a fourth above it is a spectral cost, not a feature. The two low-pitched, already-poor fits *improve* instead. This is what a coupling that adds real structure looks like when the single-voice model was furthest from the audio. Same verdict as B1: the flag stays off by default, and the per-species fit is what the plan expects to win.

**How the fit will work (pre-registered, not built).** One second-voice contour per fitted type. The search runs against the type's measured second-source evidence: inter-harmonic sidebands in the observation spectra are the observable the hand-set default cannot see. The judge is docs/09's numbers (median resynthesis cosine and species placement on the fixed store) against the single-voice baseline of the same run. We record a negative result in place per §9.7's pattern.

---

## 6. What else is out there — ranked

1. **Pulse-rattle suboscines (plantcutter class) — implementable now, with published parameters.** The Uribarri 2020 model above (overdamped SNILC pulse generator + feedback trachea + static Helmholtz OEC) is a complete renderer for "rusty-hinge" birds. It needs five fitted numbers and gives a body-size validation. It is arguably a cheaper first per-taxon pilot than the dove. 2. **Echolocation clicks (oilbird, swiftlets):** syringeal click trains. The oilbird's asymmetric bronchial semi-syrinxes make each bronchus contribute a formant, which gives individuals unique formant signatures (Suthers & Hector 1985; Fletcher & Tarnopolsky 1999 [vocal-tract acoustics PDF](https://www.phys.unsw.edu.au/music/people/publications/Fletcheretal1999a.pdf); [Suthers 2013 review, Front. Physiol.](https://public-pages-files-2025.frontiersin.org/journals/physiology/articles/10.3389/fphys.2013.00123/epub)). Renderer: short pulse train + two fixed resonators — trivially in scope. 3. **Non-syringeal sonations (in scope for "all natural sounds", but they need a new module class, not the syrinx):** feather **aeroelastic flutter** (snipe winnowing, hummingbird tail/wing, dove wing whistles) is a limit-cycle oscillator switched on above a threshold airspeed. Feather stiffness and geometry set the frequency. The sound is tonal with strong harmonics ([Clark et al. 2015, JEB 218:3520](https://journals.biologists.com/jeb/article/218/21/3520/14411/Aeroelastic-flutter-of-feathers-flight-and-the)). Manakin **stridulation/wing percussion** covers the club-winged manakin's resonant stridulation ([Bostwick et al. 2009, PMC2842718](https://pmc.ncbi.nlm.nih.gov/articles/PMC2842718/)) and the golden-collared manakin's wing-collision snap (~5 kHz peak, JEB 219:1524). **Woodpecker drumming, stork bill-clattering, and grouse drumming** are damped resonant bursts in rhythmic trains (modal synthesis). All are honest, physically labelled renderers. None belongs inside `syrinx.py`. 4. **Owls, galliforms, ratites, nightjars:** no quantitatively specified low-dimensional production model exists. The current synth + fixed tract can already approximate owl hoots and nightjar churring. Nightjars do have bronchial semi-syrinxes per the Cambridge excerpt — a two-source candidate if measurements ever appear. Rank them last: the honest claim today is "existing oscine model, no taxon-specific physics published".

### Caveats

- Paywalls blocked the Royal Society (Larsen & Goller 1999) and Cell Press (Beckers 2004) full texts. Their content here comes from the Cambridge chapter excerpt, PubMed abstracts, and Ohms 2012's quantified summary — all cited above. We read everything else in full text or from author-released code.
- The Amador & Mindlin 2023 JEB paper is a review. The implementable equations for the tracheophone come from Garcia 2017's STAR Methods + the released C code (`mu3` differs: 6.0 in the paper, 3.5 in the code — noted).
- docs/09 §9.6's "every reference implementation injects ẏ" is inaccurate for syrinxsynth, which injects y × √envelope and matches Laje & Mindlin 2005's low-frequency physics. Birdsongs does inject ẏ × envelope. Both apply pressure multiplicatively at the tract input, which Birdy does not. That shared part is the defensible change.
