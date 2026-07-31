# 5. The 3D Embedding Galaxy — the "it jumps" visualization

## 5.1 Prior art

- **Google "Bird Sounds" experiment** — the concept, open-sourced (Apache 2.0):
  feature extraction → t-SNE → JSON coordinates → WebGL points, highlight on
  playback. github.com/googlecreativelab/aiexperiments-bird-sounds
- **TensorFlow Embedding Projector** — 3D UMAP galaxy UX, audio-sprite playback per
  point (projector.tensorflow.org).
- **Apple Embedding Atlas** (MIT, Svelte components, WebGPU, millions of points, Wasm
  UMAP) — reference for scale, or a 2D companion explorer
  (github.com/apple/embedding-atlas).

## 5.2 Building the map (offline, one-off)

Corpus (xeno-canto API) → embeddings (Perch server-side, or BirdNET, or even MFCCs
for v1) → UMAP (`umap-learn`, Python) → ship `positions.bin` + metadata + cluster
centroids as static assets.

**Precompute server-side. Never run UMAP in the browser.** The galaxy is static
content. Recompute only when the corpus changes. To project a *new live sound* into
the map, use a nearest-centroid / kNN lookup in feature space. This is trivially
cheap. Do not re-run UMAP.

## 5.3 Making it live (client-side)

Audio taps: `getUserMedia` (48 kHz, echoCancellation off) →

- `AnalyserNode` for per-frame RMS/band energies, and
- `AudioWorklet` running **Meyda.js** (MFCC, spectral centroid/flux, RMS) +
  **pitchy** (McLeod pitch, fast pure-JS) at 30–60 Hz → a live 20–40-dim feature
  vector.

Mapping to the galaxy (all cheap):

- cosine/Euclidean distance of the live vector to precomputed cluster centroids →
  softmax → per-cluster activation weights.
- Pass the activations as **shader uniforms**. The vertex shader scales point
  size/brightness (`pulse = activation · sin(t·f)`). **Selective UnrealBloom** makes
  only active clusters flare → the viral look.
- pitch → vertical jump/hue. Spectral flux (onsets) → impulse triggers. Melody
  contour → moving highlight along nearest-point trajectories (the "trajectory
  lines" of the Sainburg figures).
- Smooth with EMA to avoid flicker.

## 5.4 Rendering with SvelteKit

- **Threlte** (Svelte-native Three.js) with `THREE.Points` + custom
  `ShaderMaterial`. Per-point attributes (`aActivation`, `aSize`) with
  `DynamicDrawUsage` — or better, zero per-frame CPU uploads (uniform-driven
  animation).
- Scale guidance: 10–100k points — trivial. >500k — shader-driven animation +
  lower-res bloom, or Embedding Atlas's WebGPU approach.
- Skip deck.gl (React-first) for a SvelteKit team.
- GPU picking via raycast threshold works up to ~100k points. Beyond that, use a
  color-id picking pass.

Client-side species labels: Cornell's own BirdNET browser demo runs BirdNET in TF.js
fully client-side. This is proven, but BirdNET is non-commercial. Converting Perch to
TF.js/ONNX is extra work, so keep Perch server-side.
