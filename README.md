# Birdy

Record real birds, match their calls against documented call functions, and sing back
synthetic birdsong from a physical model of the syrinx — inside an audio-reactive 3D
embedding galaxy that flares where the sound lands in the corpus.

Nothing is sampled. Every note is integrated from the Mindlin–Laje syrinx oscillator in
an AudioWorklet, driven by the two parameters real birds control: air-sac pressure and
syringeal tension.

## What it does not do

It does not translate birdsong into sentences, and it says so in the interface. Machine
learning today can characterise a repertoire and link calls to behaviour; it cannot
recover propositional language, and for most species no playback experiment exists to
anchor meaning at all (Rutz et al., *Science* 2023). So every phrase Birdy shows carries
a confidence label:

| label | meaning |
|---|---|
| **playback-verified** | function established by playback experiments on wild birds |
| **documented** | function described in the literature |
| **inferred** | plausible from context, not experimentally established |
| **invented** | our own mapping — not a claim about real birds |

Typed words are rendered through a species' own song syntax and are always labelled
*invented*, except for the handful of calls that really do have experimentally
established functions (the Japanese great tit's ABC-D compound, chickadee note
composition, Siberian jay alarm types), which are rendered as the real syllable sequence
with its citation.

## Layout

```
data/inventory.json   canonical data: 12 species, 44 syllable types, songs, grammars,
                      documented functions with citations. Read by BOTH halves.
docs/                 the research this is built on; 08-implementation.md is the contract
pipeline/             offline Python (uv): renders a corpus, calibrates the oscillator,
                      builds the galaxy -> app/static/birdy/
app/                  SvelteKit + TypeScript: realtime synthesis, mic analysis, 3D galaxy
```

The two halves implement the same physical model and the same feature extractor, both
specified in [`docs/08-implementation.md`](docs/08-implementation.md). That document is
normative: if the halves disagree, the galaxy lights the wrong stars.

## Running it

The galaxy, the cluster centroids and the oscillator calibration table are generated
offline, so build them first:

```bash
cd pipeline
uv sync
uv run birdy-pipeline build      # writes app/static/birdy/
```

Then the app:

```bash
cd app
npm install
npm run dev
```

Birdy v1 needs no backend: `adapter-static`, precomputed assets, client-side features and
client-side synthesis. Audio never leaves the browser and no model runs on a server.

## Verifying it

Two checks run the browser's own DSP outside the browser, by loading the AudioWorklet
under stubbed worklet globals:

```bash
cd app
npm run verify:synth      # renders all 44 syllables, checks measured F0 vs the contour
npm run verify:features   # renders each syllable, then asks which galaxy cluster it lands in
npm run demo:wav          # writes listenable wavs to app/out/wav
```

`verify:features` is the one that matters most: it crosses the language boundary. A high
hit rate means the two ODE implementations, the two MFCC implementations and the
standardisation statistics all agree. Drift shows up here rather than as a galaxy that
quietly lights the wrong clusters.

## Credits

The science behind each design decision is cited inline in `docs/`, and every call
function in `data/inventory.json` carries its reference. The syrinx model is Mindlin and
Laje's; the compositional-syntax result is Suzuki, Wheatcroft and Griesser (2016); the
pure-tone-by-resonance-filtering result that makes the tracking formant mandatory rather
than cosmetic is Beckers, Suthers and ten Cate (2003).
