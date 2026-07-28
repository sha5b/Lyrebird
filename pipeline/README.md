# birdy-pipeline

Offline half of Birdy. It calibrates the syrinx model, renders a corpus, computes the
28-d descriptors and builds the 3D galaxy into `app/static/birdy/`.

The contract is `docs/08-implementation.md`. The browser implements the same model and
the same feature extractor, so nothing here may drift from that document without being
written down (see "Contract deviations and clarifications" at the end).

## Run it

Requires `uv` and nothing else. Python 3.11 or 3.12 (numba/umap-learn do not support
3.13+); `uv` fetches an interpreter if needed.

```bash
cd pipeline
uv sync

uv run birdy-pipeline build            # calibrate if needed, render, embed, write assets
uv run birdy-pipeline calibrate        # only re-measure the syrinx table
uv run birdy-pipeline demo             # a few example wavs into pipeline/out/demo
uv run birdy-pipeline verify           # re-check an existing asset directory
```

A full build takes about 27 s on a laptop: 4287 clips, 882 s of synthesised audio,
5974 calibration cells. The ODE kernels are `numba`-compiled (numba arrives with
`umap-learn`; there is a pure-Python fallback, which is ~100x slower).

### build options

| flag | default | meaning |
|---|---|---|
| `--source synthetic\|local` | `synthetic` | render the inventory, or read real audio |
| `--audio-dir DIR` | - | corpus root, required by `--source local` |
| `--variants N` | 96 | jittered renders per syllable |
| `--song-variants N` | 3 | renders per whole song |
| `--seed N` | 0 | seeds the jitter, UMAP and KMeans; a build is byte-reproducible |
| `--k N` | number of syllable types (44), cap 64 | KMeans clusters |
| `--out DIR` | `app/static/birdy` | where the assets go |
| `--wav-out DIR` | - | also write every corpus clip as a wav |
| `--recalibrate` | off | re-measure the syrinx table even if it exists |
| `--beta-min F` | 0.15 | beta clamp floor - see the note below, this one matters |

Progress goes to stderr, so `uv run birdy-pipeline build 2>build.log` keeps it out of
the way.

## What it writes

Into `--out` (all of it is fetched at runtime by the app; contract 8.3):

| file | contents |
|---|---|
| `manifest.json` | what was built, when, with which parameters |
| `inventory.json` | verbatim copy of `data/inventory.json` |
| `syrinx-calibration.json` | measured `f0Hz` and `ampPP` over pressure x beta, plus the inverse `beta(f0)` table (8.4) |
| `feature-space.json` | extractor spec, corpus `mean`/`std`, `dimNames`, `temperature` |
| `positions.f32` | little-endian float32, `3*n`, xyz per point, `max abs coord == 1` |
| `points.json` | parallel metadata arrays of length `n` |
| `centroids.json` | `k` labelled clusters: 3D position, 28-d standardised vector, `count` |

`pipeline/out/demo/` holds the demo wavs. Nothing else is written outside `--out`.

### Galaxy shape

`positions.f32` is built with UMAP `n_neighbors=15`, `min_dist=0.25`, `metric=cosine`,
then centred and scaled so `max abs coord == 1`. KMeans runs on the **standardised
28-d descriptors**, not on the 3D positions, so `min_dist` is purely a visual knob:
cluster purity is 90.7 % at `min_dist` 0.25, 0.5 and 0.8 alike. At 4287 points the
44 clusters have a median internal rms radius of 0.045 and their centres sit at radius
0.21-1.11, so the cloud is a shell of tight knots; raising `min_dist` to 0.5 or 0.8
loosens the knots (voxel fill 0.8 % -> 1.4 % -> 2.4 % of a 32^3 grid) at no cost to
purity, if the render wants a denser look.

Cluster purity - the share of points that carry their cluster's majority
`(speciesId, syllableId)` - is printed by every build and stored in `manifest.json` as
`clusterPurity`. It is how we know the clusters correspond to syllable types, so watch
it when changing the corpus.

### The two modules a reader should start with

- `syrinx.py` - the Mindlin-Laje ODE (forward Euler, per-syllable gamma), the pressure
  and tension mapping, the F0-tracking tract, `render_syllable` and `render_song`.
  `render_plan` applies the 8.1 parameter mapping on its own, and `clamp_incidence`
  reports how often the beta clamp actually bites for a syllable.
- `features.py` - the 28-d descriptor: own Hann window, own mel bank, own DCT-II. Run
  `uv run python -m birdy_pipeline.features` for its self-test (the DCT-II is compared
  against a naive double loop, and a 4 kHz sine must land its centroid on 4 kHz).

`calibrate.py` also carries the reference table of contract 8.6 as a regression test.
`birdy-pipeline verify` fails the build if this implementation drifts from it by more
than 3 % on F0 or 5 % on ampPP. Current worst case: 0.03 % and 1.64 %.

## Using real recordings (`--source local`)

```bash
uv run birdy-pipeline build --source local --audio-dir ~/birdy-corpus --out ../app/static/birdy
```

Expected layout - **the parent directory name becomes the point label**:

```
~/birdy-corpus/
  parus_minor/XC123456.wav
  parus_minor/XC123457.flac
  strix_aluco/XC998877.wav
```

Each file is mono-mixed (channel mean), resampled to 48 kHz and sliced into 0.6 s
clips with a 0.3 s hop. Clips with no voiced frame are dropped by the extractor.
Resampling is **linear interpolation**, preceded by a 63-tap Hann-windowed-sinc
lowpass at `0.45 * dstRate` when downsampling; without that prefilter, decimating a
96 kHz file would fold energy above the new Nyquist into the descriptor.

### mp3 and xeno-canto caveats

- **`soundfile` cannot read mp3 on older libsndfile** (mp3 support arrived in
  libsndfile 1.1.0, 2021). Most xeno-canto downloads are mp3. Unreadable files are
  skipped with a message rather than failing the build. Convert first:
  `for f in *.mp3; do ffmpeg -i "$f" -ac 1 -ar 48000 "${f%.mp3}.wav"; done`.
- **The xeno-canto v3 API needs an API key** (`?key=...`) and applies rate limits; v2
  is retired. No downloader is implemented here on purpose: the key is per-user, the
  per-recording licences vary (CC-BY-NC-SA appears often, which matters if Birdy is
  ever commercial - see `docs/06-architecture.md` 6.2), and a corpus should be curated
  by hand rather than scraped. Fetch and convert the audio yourself, sort it into
  per-species directories, then point `--source local` at it.

## Notes on the model, and clarifications

### Per-syllable gamma, and why the beta clamp is fine

`gamma` follows the rule in 8.1: `f0_ref` is the geometric mean of the contour
frequencies (each floored at 80 Hz), `gamma = clamp(f0_ref / 0.17061, 1200, 150000)`,
`oversample = clamp(ceil(gamma / (0.06*sampleRate)), 16, 64)`. Over this inventory
gamma spans 2934 (tawny owl `hooLong`) to 36022 (Bengalese finch `f`), and every
syllable lands on oversample 16.

The calibration table is measured once at `gamma = 24000`, and a voice at another gamma
looks up `f0 * 24000 / gamma`. That works because gamma is a pure time-scale: measured
here, `f0/gamma` moves from 0.17138 to 0.17018 across gamma 3000-90000 (0.7 %, and
0.3 % across the range this inventory actually uses).

With the rule in place, beta lands between 0.15 and 2.16 for the whole inventory and
the `[0.15, 16]` clamp bites during audible samples in only 4 of 44 syllables, at most
6 % of their samples (`luscinia/flourish` 6.0 %, `lonchura/c` 4.4 %,
`troglodytes/wrenTrill` 3.0 %, `luscinia/jugJug` 1.7 %) - all of them contours whose
deepest dip falls well under their own reference pitch. Every build prints this, and
`--beta-min` can lower the floor, though on the current inventory it changes nothing
measurable: time-aligned tracking error is identical at `0.15` and `-0.6`.

One caveat worth knowing: `ampPP` is gamma-independent analytically, but the Euler
discretisation makes it drift a little, from 0.96 at gamma 3000 to 1.29 at gamma 90000
for `(alpha, beta) = (0.1, 1)`. The table is read at gamma 24000 (1.13), so a low voice
is scaled by up to ~15 % (about 1.4 dB) more than ideal. Clips are peak-normalised, so
it does not reach the descriptor.

### Details the contract does not pin down

Both halves must agree on these, so they are recorded here.

- **Bandpass form**: RBJ `bandpass` in its *constant 0 dB peak gain* form, which is
  what Web Audio's `BiquadFilterNode` type `"bandpass"` implements:
  `A = sin(w0)/(2Q)`, `b0 = A, b1 = 0, b2 = -A, a0 = 1+A, a1 = -2cos(w0), a2 = 1-A`.
  The centre frequency is clamped to `[20, 0.45*sampleRate]`.
- **One-pole highpass** (the 180 Hz DC block): `y[n] = x[n] - x[n-1] + R*y[n-1]` with
  `R = exp(-2*pi*fc/sr)`. **One-pole lowpass** (12 kHz):
  `y[n] = (1-c)*x[n] + c*y[n-1]` with `c = exp(-2*pi*fc/sr)`.
- **DC blocking happens twice**, as 8.1 describes it: once on the source and once on
  the tract sum, both with the 180 Hz one-pole highpass.
- **`two: true`** gives each oscillator **its own tract**, tracking its own detuned
  `f0` (and its own `harmonic` band); the two chains are mixed 0.5/0.5 and the 180 Hz
  highpass and 12 kHz lowpass then run on the sum. A shared tract would narrow the
  bilateral shimmer. Matches the browser worklet.
- **Envelope as an output gain**: the finished syllable is multiplied by the same
  envelope that drives `p_s`, which is now in 8.1. Necessary because the `ampPP`
  normalisation divides the pressure envelope's amplitude effect back out.
- **`hold: true`** sustains at 1.0 until 75 % of the syllable, then decays
  exponentially with `tau = dur/2.5` (8.1 gives the tau only for the non-hold case).
- **AM gating** multiplies `p_s` before the `[0, 1.4]` clamp.
- **`ampPP` ships with its zeros filled** along beta, the same way `f0Hz` zeros are
  filled for the inverse table. `f0Hz` keeps its zeros, as 8.4 specifies. A zero would
  otherwise be a division by zero in the source scaling.
- **Positions** are centred on their bounding-box midpoint before being scaled so that
  `max abs coord == 1`, so the galaxy sits around the origin.
- **UMAP `n_neighbors`** is 15 as specified, and is only clamped to `n-1` for corpora
  smaller than that (impossible for the synthetic source).
- **Cluster labels** come from the majority `(speciesId, syllableId)` among a cluster's
  points, falling back to the majority song, then to the raw label for a local corpus.
  `label`, `function`, `confidence` and `refs` are copied from `data/inventory.json`,
  which keeps the honesty rule of 8.5 attached to every cluster.
