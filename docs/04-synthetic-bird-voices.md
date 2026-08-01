# 4 — Synthetic bird voices, as scientific as possible

## 4.1 The biology that must drive the model

- Birds sing with the **syrinx** (at the trachea/bronchi junction), not the larynx.
  Sound = soft-tissue **labia** vibrating in airflow — a *nonlinear flow-induced
  oscillator* with an on/off threshold. **Two different bifurcations start it, and which
  one decides the timbre.** At high tension the oscillation is born in a Hopf and is
  tonal. At low tension it is born in a saddle-node-on-a-limit-cycle, with finite
  amplitude at zero frequency. The result is pulse-like and harmonically dense (Sitt et
  al., Phys Rev E 78:011905, 2008). The spectral content index — spectral centroid ÷ f0 —
  is a function of tension alone. Treating the threshold as "just a Hopf" is what led
  Lyrebird to synthesize every species as a pure tone. See `08-implementation.md` §8.1a.
- **Two independent voices** (left/right sides): two simultaneous independently
  frequency-modulated tones, or mid-syllable side switching.
- Two control parameters explain nearly everything: **air-sac pressure** (≈
  amplitude/onset) and **syringeal tension** (≈ fundamental frequency). The nonlinear
  regimes (pure tone → period doubling → chaos) explain both flute-like whistles and
  harsh buzzes.
- **The pure-tone quality is a filter effect.** The vocal tract suppresses harmonics,
  and birds actively track F0 with the tract's first resonance (proven by heliox
  experiments, Nowicki 1987; Beckers et al. PNAS 2003). A **formant that follows
  the pitch contour is scientifically mandatory**, not cosmetic. The existing
  procedural engine's tracking bandpass "throat" (see
  `02-procedural-voice-engine.md`) is exactly right. X-ray cinematography of singing
  cardinals has since confirmed the mechanism directly (Riede et al., PNAS 103:5543,
  2006). The oropharyngeal-esophageal cavity shrinks from 2.0 to 0.6 ml, which carries
  its resonance from 1.5 to 5 kHz *within* a syllable.
- **But a tracking formant alone is not sufficient, and this was Lyrebird's largest error.**
  If every resonance follows f0, the spectral envelope is pitch-invariant. Transposing
  a syllable transposes its whole spectrum, so two species at the same pitch are the
  same instrument. The trachea does **not** move. It is a tube closed at the syrinx. It
  resonates as a stopped quarter-wave pipe at the odd harmonics of one frequency set by
  the bird's body: `f_n = (2n−1)·c/4L`. Measurements give 2.0 and 5.5 kHz in the
  eastern towhee, against 1.88 and 5.67 kHz predicted for its 45 mm trachea (Nelson,
  Beckers & Suthers, JEB 208:297, 2005). The cardinal gives ≈ 2, 5, 8, 12 kHz. Because
  it is fixed per bird rather than per note, it is the main carrier of **species
  identity** — the thing a listener uses to tell two birds apart. See
  `08-implementation.md` §8.1a.
- Beak gape is **not** a resonance shifter. It does not move resonances below 4 kHz at
  all. It acts as a high-shelf on 4–7.5 kHz, `A = −5 + 32·log(B)` (Nelson et al. 2005).
  The earlier gape-tracks-f0 correlations are real, but the causation is the OEC and
  the tongue.
- Trills = rapid AM gated by the respiratory cycle. Parrots articulate human-like
  formants with the tongue (Beckers et al. 2004). This is the biological license for a
  "speaking parrot" mode.

## 4.2 The gold standard: Mindlin–Laje low-dimensional syrinx model

Gabriel Mindlin and Rodrigo Laje (UBA) built a small ODE system. Two time-varying
gestures drive it: `p_s(t)` (pressure) and `β(t)` (tension). The synthetic song is good
enough to fool the birds' own auditory neurons (Amador et al., *Nature* 2013). It also
runs as a real-time neural prosthesis (Arneodo et al., PLOS Comp Biol 2012).

- Full equations published: Amador & Mindlin 2021, *Front. Neurosci.* (review with
  the complete ODE + vocal-tract tube filter).
- Open implementations: `zekearneodo/syrinxsynth` and `saguileran/birdsongs` (pip
  packages). The latter fits real xeno-canto recordings with <10% error.
- **Automatic inversion exists** (Boari et al. 2015): real audio → pressure/tension
  gesture curves. This is the missing link for "record a real bird, then re-sing it
  synthetically."
- Modern direction: Lostanlen, *Towards Differentiable Motor Control of Bird
  Vocalizations* (VIHAR 2024) — differentiable syrinx decoders.

## 4.3 Alternatives

- **Procedural recipes** (Andy Farnell's sparrow patch in *Designing Sound*): FM/AM/
  ring-mod + resonant filters. The patch compiles to WebAssembly via **hvcc** (Pd →
  Web Audio AudioWorklet). Fast win, less principled.
- **DDSP** (Google Magenta): train on ~10 min of isolated syllables → (f0, loudness)
  → harmonic+noise synth. It runs client-side (Tone Transfer proves it). Good for
  the high-fidelity timbre of a *specific* bird.
- **RAVE** (IRCAM): realtime neural timbre transfer, but heavier.
- **Diffusion/TTS** (BirdDiff, AudioLDM 2, ElevenLabs): best raw quality, but
  server/GPU-bound and not parametrically controllable. Wrong tool for an
  interactive app.

## 4.4 "Choose words the bird sings" — the design space

No off-the-shelf text-to-birdsong exists, but every piece does:

1. word → syllable-token sequence via a **syntax model**: Bengalese-finch
   finite-state grammar, or **FinchGPT** (arXiv:2502.00344). FinchGPT is literally a
   Transformer trained on syllable tokens. It validates the token→sequence→render
   pipeline.
2. token → motor gestures `p_s(t)`, `β(t)` — hand-designed, or inverted from real
   recordings (Boari 2015).
3. render through the syrinx ODE + tract filter.
4. optionally overlay **spoken-word prosody**: the Windytan method (2021) extracts
   the F0 contour + amplitude envelope of speech and re-voices it with a bird-like
   carrier. The result "sounds surprisingly blackbird-like," and the words remain
   perceptible as prosody. Drive `β(t)` with word F0 and `p_s(t)` with the amplitude
   envelope.
5. for a "parrot" mode, add a 2–3 formant bank per phoneme (biologically defensible,
   Beckers 2004).

## 4.5 Feasibility ranking

1. **Realtime parametric syrinx in an AudioWorklet** — pure math, zero weights, two
   knobs, all regimes. Evolve the existing oscillator synth toward the Amador–Mindlin
   ODE. ✅ recommended core.
2. Word conditioning without ML (grammar + Windytan prosody transfer). ✅
3. hvcc port of Farnell's Pd bird. Quick win.
4. DDSP for a specific signature timbre. Stretch.
5. Server diffusion. Avoid.
