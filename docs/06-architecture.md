# 6 — Architecture, risks, build order

Two halves and one direction. Python runs offline, measures a corpus and writes
static assets. The SvelteKit app reads those assets and never calls back. The
line between them is the 28-d descriptor of docs/08 §8.2, which both sides
compute sample for sample alike.

## 6.1 Architecture

```
OFFLINE (Python, one-off)                SVELTEKIT APP
─────────────────────────                ─────────────────────────────────
xeno-canto corpus ─┐                     CLIENT
Perch embeddings   ├→ UMAP → positions   ├─ Threlte 3D galaxy (Points + bloom)
cluster centroids ─┘      .bin + JSON    ├─ AudioWorklet: Meyda + pitchy
                                         ├─ syrinx synth (evolved procedural
syllable inventory                         │   voice engine, see doc 02)
 (from real recordings                    ├─ word→syllable grammar + prosody
  via gesture inversion)                   │   transfer ("choose words")
                                         ├─ optional BirdNET-TF.js species label
                                         │
                                         SERVER (mostly static)
                                         ├─ adapter-static/node; corpus metadata API
                                         ├─ (optional) Perch inference endpoint
                                         └─ (optional) WS broadcast of feature
                                             vectors for multi-user "bird rooms"
```

- **v1 needs no backend beyond static hosting** — precomputed galaxy + client-side
  features + client-side synth.
- **"Multiple birds" v1** = broadcast tiny feature vectors (a few floats @ 10–30 Hz)
  over WebSocket (`adapter-node` + `ws`, standard SvelteKit pattern), not audio. Use
  an SFU (LiveKit) only if real audio streaming becomes a requirement.
- **Recording**: use `getUserMedia` + `MediaRecorder` to save clips. Test the Safari
  AudioWorklet/MediaRecorder quirks early.
- **Adapters**: use `adapter-static` (or vercel/cloudflare) while inference stays
  client-side. Move to `adapter-node` once WebSockets or a persistent inference
  endpoint are needed.

## 6.2 Risk register

1. **Licensing**: BirdNET + BirdCLEF are CC BY-NC-SA (non-commercial). Xeno-canto
   carries per-file CC flags. If Birdy is ever commercial, use Perch (Apache 2.0) and
   license-checked audio only.
2. **Perch SavedModel → web conversion**: avoid by keeping Perch
   offline/server-side.
3. **Bloom at >200k points**: shader-driven animation, lower-res bloom targets.
4. **Science/marketing honesty**: present translations as *documented call functions
   with confidence*, not literal language (see `03-decoding-science.md` §3.1).
5. **Repo maturity varies**: `syrinxsynth` is notebook-documented. `birdsongs` is
   mid-migration. BirdDiff/H2NH-VC are fresh preprints. Verify before depending.

## 6.3 Suggested build order

1. Port the existing procedural voice engine (data model + synth, see doc 02) into
   Birdy. Wire a live galaxy that lights up when the *synthetic* bird sings (closed
   loop, no ML yet).
2. Add mic → Meyda/pitchy → nearest-centroid activation (live reactivity).
3. Precomputed Perch+UMAP galaxy from a curated xeno-canto subset.
4. Word→syllable grammar + Windytan prosody transfer ("choose words").
5. Species ID (Perch server endpoint or BirdNET-TF.js), few-shot "learn this call".
6. Add multi-user feature-vector rooms. Then the stretch goals: gesture inversion of
   user recordings, mic-array localization, DDSP signature voices.
