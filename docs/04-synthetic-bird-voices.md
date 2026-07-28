# 4. Synthetic Bird Voices — as scientific as possible

## 4.1 The biology that must drive the model

- Birds sing with the **syrinx** (at the trachea/bronchi junction), not the larynx.
  Sound = soft-tissue **labia** vibrating in airflow — a *nonlinear flow-induced
  oscillator* with an on/off threshold (Hopf bifurcation).
- **Two independent voices** (left/right sides): two simultaneous independently
  frequency-modulated tones, or mid-syllable side switching.
- Two control parameters explain nearly everything: **air-sac pressure** (≈
  amplitude/onset) and **syringeal tension** (≈ fundamental frequency). The nonlinear
  regimes (pure tone → period doubling → chaos) explain both flute-like whistles and
  harsh buzzes.
- **The pure-tone quality is a filter effect**: the vocal tract suppresses harmonics
  and birds actively track F0 with the tract's first resonance (proven by heliox
  experiments, Nowicki 1987; Beckers et al. PNAS 2003). → a **formant that follows
  the pitch contour is scientifically mandatory**, not cosmetic. The existing
  procedural engine's tracking bandpass "throat" (see
  `02-procedural-voice-engine.md`) is exactly right.
- Trills = rapid AM gated by the respiratory cycle; parrots articulate human-like
  formants with the tongue (Beckers et al. 2004) — the biological license for a
  "speaking parrot" mode.

## 4.2 The gold standard: Mindlin–Laje low-dimensional syrinx model

Gabriel Mindlin / Rodrigo Laje (UBA) — a small ODE system driven by two time-varying
gestures `p_s(t)` (pressure) and `β(t)` (tension) that produces synthetic song good
enough to fool the birds' own auditory neurons (Amador et al., *Nature* 2013) and to
run as a real-time neural prosthesis (Arneodo et al., PLOS Comp Biol 2012).

- Full equations published: Amador & Mindlin 2021, *Front. Neurosci.* (review with
  the complete ODE + vocal-tract tube filter).
- Open implementations: `zekearneodo/syrinxsynth`, `saguileran/birdsongs` (pip
  packages; the latter fits real xeno-canto recordings with <10% error).
- **Automatic inversion exists** (Boari et al. 2015): real audio → pressure/tension
  gesture curves. This is the missing link for "record a real bird, then re-sing it
  synthetically."
- Modern direction: Lostanlen, *Towards Differentiable Motor Control of Bird
  Vocalizations* (VIHAR 2024) — differentiable syrinx decoders.

## 4.3 Alternatives

- **Procedural recipes** (Andy Farnell's sparrow patch in *Designing Sound*): FM/AM/
  ring-mod + resonant filters. Compilable to WebAssembly via **hvcc** (Pd → Web Audio
  AudioWorklet). Fast win, less principled.
- **DDSP** (Google Magenta): train on ~10 min of isolated syllables → (f0, loudness)
  → harmonic+noise synth; runs client-side (Tone Transfer proves it). Good for
  high-fidelity timbre of a *specific* bird.
- **RAVE** (IRCAM): realtime neural timbre transfer; heavier.
- **Diffusion/TTS** (BirdDiff, AudioLDM 2, ElevenLabs): best raw quality but
  server/GPU-bound and not parametrically controllable — wrong tool for an
  interactive app.

## 4.4 "Choose words the bird sings" — the design space

No off-the-shelf text-to-birdsong exists, but every piece does:

1. word → syllable-token sequence via a **syntax model**: Bengalese-finch
   finite-state grammar, or **FinchGPT** (arXiv:2502.00344) — literally a Transformer
   trained on syllable tokens, validating the token→sequence→render pipeline;
2. token → motor gestures `p_s(t)`, `β(t)` — hand-designed, or inverted from real
   recordings (Boari 2015);
3. render through the syrinx ODE + tract filter;
4. optionally overlay **spoken-word prosody**: the Windytan method (2021) extracts
   the F0 contour + amplitude envelope of speech and re-voices it with a bird-like
   carrier — "sounds surprisingly blackbird-like," words remain perceptible as
   prosody. Drive `β(t)` with word F0 and `p_s(t)` with the amplitude envelope;
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
