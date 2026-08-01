# 2 — The procedural voice engine we already have

A SvelteKit codebase already exists on this machine, a sibling project whose main
feature is unrelated 3D rendering. It contains a **fully procedural, sample-free,
ML-free birdsong synthesizer**. The synthesizer is the ideal seed for Lyrebird's voice
engine. This document analyzes that engine generically, as a reusable component.

## 2.1 Design

- **Zero samples, zero ML** — the engine synthesizes everything with the raw Web
  Audio API (no audio libraries). The stated model is a physical, syrinx-inspired
  oscillator synthesizer. It cites Scholarpedia *Models of birdsong (physics)* and
  Kahrs & Avanzini, *Computer Synthesis of Bird Songs and Calls* (DAFx-01).
- Two files split **data** from **synthesis**:

### Data model (`birdsongs.ts`, ~525 lines)

A `Song` is a list of `Syllable`s. Each syllable is a continuous **pitch contour**
(breakpoints `[timeFraction, Hz]`) plus timbre/effect flags:

```ts
interface Syllable {
  t: number; dur: number;
  contour: Point[];              // pitch path, ≥2 points — the melodic sweep
  timbre: 'pure' | 'reed' | 'buzz';
  level: number;
  harmonic?: number;             // 2nd-harmonic amount
  two?: boolean;                 // two detuned voices = syrinx shimmer
  am?: number; amDepth?: number; // AM buzz rate for trills/rattles
  vib?: { rate: number; depth: number }; // owl-hoot quaver
  attack?: number; hold?: boolean;
}
```

- 12 hand-authored species songs (Japanese bush warbler/uguisu, mejiro, great tit,
  sparrow, blackbird, robin, wren, cuckoo, dove, bulbul, koel, owl), grouped into
  regional banks (`jp | east | west | tropical`).
- The authors tuned the owl to measured calls (Galeotti & Pavan 1991).

### Synthesizer (`birds.ts`, ~190 lines)

- `synthSyllable` builds 1–2 oscillators (`sine`/`triangle`. Two voices detuned ±7
  cents = bilateral-syrinx beating) whose frequency follows the contour.
- A **tracking bandpass "throat" formant** whose center follows the same contour
  (biologically important — see `04-synthetic-bird-voices.md` §4.1).
- Exponential attack/decay envelope, square-wave AM for buzzy trills, LFO vibrato,
  optional 2nd-harmonic partial.
- `playSong` adds distance rendering: low-pass air absorption (`12000 - 9500·d` Hz),
  dry/wet reverb mix, pan narrowing.

### Scheduling (`engine.ts`, `voice.ts`)

- Poisson event scheduling on a 100 ms look-ahead tick. Scene-driven song rates
  (dawn 22 songs/min, midday 5, night owls). Occasional answering-bird duets (25%
  chance of a second bird answering 0.4–1.3 s later).

## 2.2 What's missing for Lyrebird

- **No audio analysis** of any kind (no FFT, pitch tracking, spectrograms) — it is
  synthesis-only.
- **No recording** (`getUserMedia`/`MediaRecorder`).
- **No ML** — no embeddings, clustering, or classification.
- **No generative grammar** — the engine picks songs uniformly at random from a
  fixed library. There is no per-individual variation beyond slight detune jitter.
- **No point-cloud / embedding visualization** (its 3D code renders unrelated
  geometry).

## 2.3 Verdict

Reuse the `Syllable`/`Song` contour data model and the syrinx-ish synth voice as
Lyrebird's **rendering layer**. The transfer cost is low: the code is compact,
dependency-free, and already Svelte/Web-Audio native. The scientifically stronger
move is to evolve the oscillator core toward the Mindlin–Laje syrinx ODE (see
`04-synthetic-bird-voices.md`). Keep the same data model and scheduling patterns.
Everything else — embeddings, decoding, grammar, galaxy — is new work.
