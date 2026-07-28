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
uv run birdy-pipeline harvest          # stream real recordings into a bounded store
uv run birdy-pipeline learn            # fit syllables + syntax to what was harvested
uv run birdy-pipeline serve            # drive the above from the app's Learn tab
uv run birdy-pipeline demo             # a few example wavs into pipeline/out/demo
uv run birdy-pipeline verify           # re-check an existing asset directory
```

A synthetic-only build takes about 27 s on a laptop: 4287 clips, 882 s of synthesised
audio, 5974 calibration cells. The shipped build is larger — the learned inventory and
the harvested store together — at 31,328 points and a few minutes. The ODE kernels are `numba`-compiled (numba arrives with
`umap-learn`; there is a pure-Python fallback, which is ~100x slower).

### build options

| flag | default | meaning |
|---|---|---|
| `--source synthetic\|local\|harvest` | `synthetic` | render the inventory, read real audio, or embed a harvested store |
| `--audio-dir DIR` | - | corpus root, required by `--source local` |
| `--harvest-store DIR` | - | also embed a harvested store alongside `--source` |
| `--variants N` | 96 | jittered renders per syllable |
| `--song-variants N` | 3 | renders per whole song |
| `--seed N` | 0 | seeds the jitter, UMAP and KMeans; a build is byte-reproducible |
| `--k N` | number of syllable types, cap 256 | KMeans clusters |
| `--out DIR` | `app/static/birdy` | where the assets go |
| `--wav-out DIR` | - | also write every corpus clip as a wav |
| `--projection umap\|pca\|cmds` | `cmds` | 3D layout; see "Galaxy shape" below |
| `--no-compare-projections` | off | skip building the other two just to measure them |
| `--min-dist F` | 0.25 | UMAP `min_dist`; visual spread only |
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
| `positions.f32` | little-endian float32, `3*n`, xyz per point, `max abs coord == 1` (layout per `manifest.json` `projection`) |
| `point-features.f32` | little-endian float32, `8*n`, unit rows: the per-point render response space |
| `points.json` | parallel metadata arrays of length `n` |
| `centroids.json` | `k` labelled clusters: 3D position, 28-d standardised vector, 8-d `featuresLo`, `count`, and per-cluster summary figures |

### `point-features.f32`: why each point reacts on its own

The browser matches live audio to the 28-d **cluster centroids**, as contract 8.2 says,
and that match is what the reading panel reports. It is not enough to draw with. A
cluster holds up to 195 points; lighting all of them equally makes an active knot a flat
disc and throws away the thing the galaxy exists to show, which is that a repertoire is
a continuum and a live sound sits somewhere particular inside it.

So the build also writes the top-8 principal components of the standardised descriptors,
one unit row per point, plus the same projection of each centroid as `featuresLo`. The
client reconstructs the live query in that space from the centroids it matched and takes
a cosine against every point — 31,328 × 8 multiply-adds a frame, less work than the FFT
that produced the descriptor. A cluster then lights from the inside out.

On the shipped corpus the 8 components keep **76.1 %** of the 28-d variance, and each
point's mean cosine to its own centroid is **0.922** against **-0.004** to all centroids.
(On a synthetic-only build, where every point is a render of one of 44 types rather than
a second of a windy field, the same figures are 82.3 % and 0.984 against 0.005.)
Both numbers are printed by every build and stored in `manifest.json`; `verify` fails
the build if the separation collapses, which is what would happen if the PCA signs came
back mirrored between the points and the centroids.

`pipeline/out/demo/` holds the demo wavs. Nothing else is written outside `--out`.

### Galaxy shape: do the distances mean anything?

KMeans, the centroid vectors and the client's activation lookup all live in the
**standardised 28-d descriptor space** and never touch the 3D positions. The projection
is therefore free to change; what it changes is whether *distance on screen* carries
information. `--projection` picks it, and every build measures the answer instead of
asserting it: 200k seeded random point pairs, 28-d cosine distance against 3D Euclidean
distance, Pearson and Spearman.

Measured on the shipped corpus (31,328 points — 11,328 rendered, 20,000 harvested —
176 clusters, seed 0):

| projection | Pearson | Spearman | purity | 3D kNN agreement | notes |
|---|---|---|---|---|---|
| **`umap` (`min_dist` 0.25, shipped)** | 0.300 | 0.296 | 35.4 % | **73.0 %** | neighbourhoods only |
| `pca` | 0.485 | 0.484 | 35.4 % | 44.0 % | variance 29/12/9 % |
| `cmds` (default) | **0.752** | **0.740** | 35.4 % | 43.4 % | variance 26/12/8 %, negative eigenvalue mass 38 % |

The purity is 35.4 % rather than the 90.7 % a synthetic-only build reports, and that is
the corpus, not the clustering: two thirds of these points are seconds of field audio
whose call type nobody has labelled, so they land wherever they sound like they belong.

`cmds` is classical (Torgerson/PCoA) multidimensional scaling on the cosine distance
matrix - the same metric everything else uses. Up to `CMDS_FULL_MAX = 6000` points the
full double-centred matrix is decomposed exactly (`numpy.linalg.eigh`, about 7 s at 4287
points); above it, and so on the shipped build, it switches to landmark MDS with 800
landmarks and says so in the log and in `manifest.json`.

**The trade-off, stated plainly, and the choice has changed.** UMAP scores best on kNN
agreement (73.0 %) and worst on distance faithfulness (0.300) because it exaggerates
separation: it guarantees only that neighbours stay neighbours, so *gaps between distant
clusters are not interpretable*. cMDS gives the most honest distances (0.752) and a
picture that is a near-featureless ball — the knots overlap so completely that at the
framing which holds the whole corpus you cannot see there are knots at all.

The shipped build is now **UMAP**, on the ground that a viewer who cannot see the
structure cannot be helped by the fact that the distances between the parts they cannot
see are accurate. Two things keep this honest rather than merely prettier: the trade is
recorded here and in `manifest.json` with both correlations, and no part of the interface
quotes a distance. Nothing in the app reads a position — matching, clustering and the
per-point response all happen in the 28-d space. `--projection cmds` still produces a
valid asset set for anyone who wants the faithful-distance version.

Neither linear projection is degenerate: cMDS spreads its variance 26/12/8 % over the
three axes, so the cloud is a genuine volume rather than a line.
The 38 % negative eigenvalue mass is expected and worth knowing: cosine distance is not
a Euclidean metric, so a perfect embedding does not exist at any dimensionality, and
that share of the structure cannot be drawn.

Cluster purity - the share of points carrying their cluster's majority
`(speciesId, syllableId)` - is **identical for all three projections**, as it
must be, since the clustering never sees a position. It is the control for this whole
exercise: if it ever differs between projections, something is wired wrong. It is
printed by every build and stored as `clusterPurity`.

Within UMAP, `min_dist` is also purely visual (purity is unchanged at 0.25, 0.5 and 0.8
alike); raising it loosens the knots, filling 0.8 % -> 1.4 % -> 2.4 % of a 32^3 voxel
grid.

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

### mp3

`soundfile` cannot read mp3 on older libsndfile (mp3 support arrived in libsndfile
1.1.0, 2021), and most xeno-canto downloads are mp3. `--source local` skips unreadable
files with a message rather than failing the build; `harvest` falls back to ffmpeg,
transcoding to a wav at the file's own rate so the mono mix and the resampler stay the
ones documented above.

## Harvesting: learn from a lot of audio, keep almost none of it

```bash
cp .env.example .env             # then paste your key into it
uv run birdy-pipeline harvest --per-species 20 --quality A --dry-run
uv run birdy-pipeline harvest --per-species 20 --quality A
uv run birdy-pipeline harvest --stats
uv run birdy-pipeline build --harvest-store ../pipeline/out/harvest
```

The point of `harvest` is what it throws away. One recording is fetched, decoded,
analysed and deleted before the next one starts, so peak memory is one recording rather
than one corpus, and a session that streams several gigabytes of audio leaves a store of
a few megabytes. What survives is a **species-stratified reservoir** of 28-d
descriptors: Algorithm R against a persisted counter, so a store built over ten sessions
is the same uniform sample as one built in a single pass, and a species with 900
recordings on xeno-canto cannot bury one with 12.

Whether that sample is honest is measurable, so it is measured. Welford accumulators run
over **every** descriptor the stream produces, discarded ones included, and `--stats`
prints how far the retained sample's mean and spread have drifted from the full stream's
— in units of the stream's own standard deviation. Near zero means the reservoir is a
faithful miniature of everything fed through it. If it is not, raise `--cap`.

### The API key

`pipeline/.env`, from the template in `pipeline/.env.example`:

```
XC_API_KEY=your-key-here
```

It is read by `birdy-pipeline` at startup and never overrides a variable already in the
environment, so `XC_API_KEY=... uv run ...` still wins. `.env` is gitignored.

**It does not go in `app/`.** Vite inlines anything it finds there into the bundle it
ships to the browser, and the browser never talks to xeno-canto in the first place —
harvesting is entirely an offline step, so the key is only ever seen by Python.

| flag | default | meaning |
|---|---|---|
| `--store DIR` | `pipeline/out/harvest` | where the descriptors and observations live |
| `--cap N` | 20000 | descriptors the store may hold, over all runs |
| `--per-species N` | 20 | recordings per species |
| `--max-seconds F` | 90 | analyse at most this much of each recording |
| `--quality Q` | `A` | xeno-canto quality filter |
| `--query Q` | - | raw xeno-canto query instead of the inventory's species |
| `--from-dir DIR` | - | ingest files already on disk; no network, no key |
| `--dry-run` | off | list what would be fetched |
| `--stats` | off | describe an existing store and exit |

**Licensing.** Every retained recording's id, recordist and licence is written to
`CREDITS.md` in the store, because xeno-canto recordings are individually licensed and
CC-BY-NC-SA is common — which matters if Birdy is ever commercial (see
`docs/06-architecture.md` §6.2). Check the licences before shipping a harvested galaxy.
An earlier version of this README argued no downloader should exist at all; the position
now is that one should exist and should carry the attribution with it, since the
alternative in practice was people scraping without recording the licence.

**Honesty.** Harvested points are real audio of a known species and nothing more. A
cluster the inventory cannot name gets `confidence: "unlabelled"` — a fifth label
alongside the four in the root README — which the app renders as *field recording*. It
is a different claim from `invented`, and both are different from having a citation.

## Learning: fit the model to what was heard

```bash
uv run birdy-pipeline learn --types 8
uv run birdy-pipeline build --inventory ../data/learned-inventory.json \
                            --harvest-store ../pipeline/out/harvest
```

While a recording is briefly in memory, `harvest` runs a second analysis beside the
sliding descriptors: it segments the audio into syllables and reduces each one to the
parameters `data/inventory.json` uses — duration, level, attack, an f0 contour, AM,
vibrato, a harmonic ratio and a timbre class. A few dozen floats per syllable, and the
audio is gone a moment later.

`learn` then clusters those observations per species, takes the median of each type,
**searches that median towards the audio it came from**, and renders the result through
the same Mindlin-Laje oscillator the app uses to find out whether the model can sing what
it just described.

The search is the cheap end of the gesture inversion the literature describes (Boari et
al. 2015, `docs/04-synthetic-bird-voices.md` §4.2). Rather than solving for the pressure
and tension curves analytically, it renders candidates and keeps whichever lands closest
to the real syllable in the 28-d space — coordinate descent over ten axes (timbre class,
level, harmonic ratio, AM rate and depth, vibrato rate and depth, attack, hold, bilateral
voice), three passes, a couple of hundred renders per type, two or three seconds per
species. Pitch and duration are excluded on purpose: the tracker already gets F0 to about
1 %, and a texture search allowed to move pitch would trade the one thing the model does
well for the one it does badly.

It is worth what it costs, and it does not close the gap. Across all 132 fitted types on
the current harvest the median resynthesis cosine goes from **0.31 to 0.547** and the
share landing nearest their own type from 30 % to **51 %** (67 of 132). But the median
*rival* cosine is **0.533** — the fit resembles its own call barely more than it
resembles a different call by the same bird — and 0.547 still sits nearer the "two
different calls" baseline of 0.49 than the "two recordings of the same call" baseline of
0.78. Median F0 error is 0.80 %, so what is missing is entirely timbre.
`--no-invert` ships the cluster medians instead, which is what every build before this
did. Three numbers go next to every learned syllable, because they fail differently:

- `resynthesisCosine` — the 28-d descriptor of the resynthesis against the mean
  descriptor of **the syllables of that type**, in a frame centred on the harvested
  population. Does it land in the right part of the feature space?
- `nearestOwn` / `rivalCosine` — whether it lands nearer its own type than any other
  type of the same bird, and what the best rival scored. This is the number that
  matters: a cosine has no scale of its own, and "0.4" means nothing until you know
  that two real syllables of one type score 0.78 and two of different types 0.49.
- `f0ErrorPercent` — measured F0 of the resynthesis against the contour it was asked
  for. Did the oscillator reach the pitch?

A syllable can pass one and fail the other: a buzz whose pitch is right but whose
texture is not, or a clean whistle a semitone flat. A type the model cannot reproduce
says so in the file instead of shipping as though it could — and on the current harvest
half of them say exactly that (67 of 132 land nearest their own type, and the margin over
the nearest rival is 0.014). See the root README for what that means.

**The frame is the measurement.** The reference used to be the recording-level
descriptor, standardised against a synthetic build's corpus statistics. Every field
recording is far from a synthetic mean in the same direction — the direction of "was
recorded outdoors" — so in that space a real syllable scored 0.995 against its own type
and 0.991 against a different one, and the check could not fail. Centred on the
harvested syllables instead, the same comparison gives 0.78 within a type and 0.49
across, which is a frame in which a claim can be false.

`learn` writes its result into `data/learned-inventory.json` **merged onto the
hand-authored inventory**: the documented calls stay exactly as they are, with their
functions, confidences and citations, and the fitted types are appended to their
species. Fitted ids are `L00`, `L01`, … so they cannot collide with an authored id, and
the measured grammar only ever mentions them — improvising from it cannot put a
documented syllable into a sequence nobody observed. `--learned-only` writes the fitted
repertoire on its own, which is the old behaviour and throws every citation away.

Because the observations keep their order within their recording, typing them also turns
each recording into a string of type ids, and counting the transitions gives a
first-order grammar in exactly the shape `app/src/lib/lang/grammar.ts` already
improvises from. That is the sense in which Birdy can produce **new phrases**: sequences
no bird sang, generated in a syntax measured from birds that did. They are labelled
`invented`, and their syllables stay `unlabelled`. Neither label is a claim about
meaning.

## `serve`: the same three operations, from the interface

```bash
uv run birdy-pipeline serve            # http://127.0.0.1:8781
```

`npm run dev` in `app/` already starts this for you and stops it again on exit
(`app/vite-plugin-pipeline.ts`), so the command above is for running it by hand — with
your own `--port`, or without a dev server at all. A hand-started process wins: the
plugin never spawns a second one if the port already answers.

Harvest, learn and rebuild, driven from the app's **Learn** tab, with the store's
figures on screen and the job's stderr streaming back so progress is the real log rather
than a spinner. One job at a time.

**It binds to the loopback interface and the address is not configurable.** Every
endpoint runs pipeline code — downloading, decoding, writing files — so exposing it on a
network would be handing out remote code execution. `--port` is the only knob.

This does not give the app a backend. The galaxy is precomputed and `adapter-static`
still serves it with no server at all; this is a developer-facing process for the
offline stage, and the Learn tab degrades to instructions when it is not running.

## What the visualisation encodes

`build` writes two things the renderer uses that are not part of the acoustic contract:

- **`functionClass`** on every cluster — the behavioural class of its documented
  function (alarm, recruitment, courtship, territorial, contact, structural,
  unclassified), matched against a keyword table stored in `manifest.json` under
  `functionClasses.rules`. First hit wins, and the order matters: "mate attraction /
  countersinging" is courtship before it is territorial. On the shipped inventory:
  structural 23, alarm 8, territorial 6, contact 4, courtship 2, recruitment 1.
- **`point-features.f32`** — described above.

The app collapses the seven classes into three for colour, because with every pair of
series on screen at once only three categorical hues stay separable under colour-vision
deficiency. The full class is in the cluster's label.

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
