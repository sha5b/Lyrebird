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
| **field recording** | real audio of a known species, with no documented function at all |
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
                      harvests and learns from field audio, builds the galaxy
app/                  SvelteKit + TypeScript: realtime synthesis, mic analysis, 3D galaxy
```

## The galaxy

The app opens with **no bird selected**: nothing is dimmed, the whole corpus is the
subject, and the camera fits all of it. One camera rule covers everything after that —
it frames the most specific thing you have chosen, and flies there when that changes.
Pick a bird and it fits the region that bird's clusters occupy; pin a node and it fits
that node; pick a phrase out of the history and it fits the phrase. The fit is to the
85th percentile of the reach rather than the furthest member, because a species is not a
region in the acoustic layout — two of its calls sound like some other bird's and sit
across the cloud — and fitting to the maximum would frame those two strays and show you
the whole galaxy again.

The shipped galaxy is **31,328 points in 176 clusters**: 11,328 clips rendered from the
inventory, and 20,000 descriptors of real xeno-canto audio from 434 recordings across
twelve species. One cluster per syllable type — the 44 authored ones and the 132 fitted
to field recordings — because a cluster is what carries a name, a function and a
citation, and merging two types into one loses all three.

Points are individual clips; clusters are call types. Selecting a bird dims the other
species and narrows the floating node labels to that repertoire, so the picture changes
with the selection instead of showing all twelve species at once regardless. Each node
carries a specimen tag — what the cluster is, how many points fell into it, how tight it
is — that opens up and shows the documented function and the live match percentage when
its cluster responds.

At most twenty-six tags are drawn at once, and they are spent in a fixed order:
whatever is responding, then whatever has a documented function, then whatever is
nearest. Collision culling alone was written for 44 clusters and does not scale to 176 —
the exclusion boxes tile the middle of the view and you get a wall of text that happens
not to overlap. The middle term matters most now that most clusters are field audio: a
named cluster carries a function and a citation, and "unlabelled field cluster" repeated
forty times carries neither, so it should not be what crowds the named ones out.

Points respond **individually**, not as clusters. The pipeline ships an 8-dimensional
per-point projection of the descriptor space, and the browser takes a cosine against
every point each frame, so a knot lights from the inside out and you can see which
members of a call type a sound actually resembles. The reported match still uses the
28-d centroids the contract specifies; the per-point space only decides brightness.

The chorus comes in two forms. **This bird** is the selected species and its
neighbours, drawn against its own backdrop of songs. **All species** sets the selection
aside entirely — no focus, no backdrop — and every bird that starts singing adds its own
trajectory, so a dozen threads light in parallel and the whole corpus is visibly moving
rather than one diagram being redrawn.

**Distance** is one control over two things: it drives air absorption and reverb in the
audio, and the viewing scale in the picture, so a bird across the field is further away
in both. The scale is exponential over roughly a seven-fold range, and the camera's
reach was raised to match: at the far end the cloud is several times its own radius
across, and a viewer that cannot back away from it turns the control into a wall.

**Tempo** slows the whole aviary — the drift, the pulse, how long each syllable
lasts and how often a bird starts. It stretches time and nothing else: pitch comes from
a syllable's contour and length from its `dur`, so unlike a tape slowing down, a bird
slowed here keeps its pitch and simply sings longer. Trill and vibrato rates are divided
by the same factor, or a slowed call stops sounding like itself.

**What has been sung** runs along the bottom of the view, in the lane between the two
panels: newest against the reading card and older ones extending left until they clip. A
chorus goes past faster than anyone can read; clicking an entry draws that phrase's path
back onto the galaxy, selects its bird, and **flies the camera to it** — the knot it
lives in is one of a hundred and seventy in a cloud you may have orbited away from, and
"it is highlighted somewhere behind you" is not a way to find anything.

The flight ends the moment you touch the controls. The *lock* on the phrase does not:
the cloud is drifting, and without it the thing you just asked to see rotates back out of
frame while you look at it. Orbiting and zooming stay yours throughout — the lock only
writes the point they happen around. Clicking empty space clears nothing, because
orbiting is a click-and-drag on that same surface; the reading card carries an explicit
**clear selection** instead.

### Rearranging

Colour can say which points are the same bird. It cannot make you *see* it, because the
points do not move — and the acoustic layout answers "what sounds like what", not "which
of these are the same bird".

**Arrange** does move them. Each grouped layout keeps every point's offset from its own
group's centre and pushes the centres apart, so a group's internal shape survives the
journey and you can follow individual points across it. Two species that overlapped
acoustically visibly tear apart; a species that was already one knot barely moves. That
contrast is the information, and it is not available from a recolour.

Trajectory threads, context paths and node labels all read the same moving centroids, so
they stay welded to their knots through the transition. Nothing about the clustering, the
matching or the descriptors changes — it is a rearrangement of where the marks are drawn,
and *Sound* is always one click away.

### Nothing matching has to look like nothing matching

Softmax is a relative measure — its outputs sum to 1, so whatever you feed it, some
cluster always wins. Fed room tone or a fan, the matcher used to pin 100 % on an
arbitrary call and hold it there indefinitely, which is what made the galaxy hang on one
node while nothing was playing.

The activation is scaled by an absolute measure of how well the best centroid actually
matches, and the thresholds come from the corpus rather than from taste. Re-measured by
`birdy-pipeline thresholds` against the shipped assets:

| input | best-centroid cosine | spectral flatness |
|---|---|---|
| real harvested syllables (n = 2000) | p10 0.654 · p50 0.801 · max 0.992 | p99 0.345 |
| a 1 kHz hum | 0.917 | 0.000 |
| white noise | **0.996** | 0.848 |
| room tone at −60 dBFS | **0.996** | 0.848 |

**The cosine alone no longer separates birdsong from noise, and pretending otherwise
would be the easiest lie in this project.** Those two bold numbers are above the *median*
real syllable. The reason is not a bad threshold: against a corpus that is two thirds
field audio, some clusters are bins of wind and rain, and averaging 59 noise-leaning
syllables produces a centroid more noise-like than any of its members — they score
p99 0.941 individually and 0.996 pooled. Dropping the worst cluster only promotes the
next one, and the top three (1064 points, 3.4 % of the corpus) shade into a genuine
continuum: a wren's trill really is broadband.

So there are two tests now, and both have to pass. The cosine ramps from **0.62 to
0.86**, which lets in about nine real syllables in ten. On top of it a **tonality gate**
zeroes anything whose spectral flatness runs from 0.40 to 0.55 — a margin that touches
under 1 % of genuine birdsong and kills both noise probes outright.

The hum is deliberately *not* rejected. A 1 kHz sine has flatness 0.000 and scores 0.917
against a tawny owl whose learned call sits at 907 Hz; those two sounds really are close
in this feature space, and reporting a strong match is the honest answer rather than a
bug. `npm run verify:features` asserts all of this on every build, so the gate cannot
quietly stop holding.

The **match** meter in the header shows the resulting number, so a stuck reading is
visible rather than mysterious. Below about 25 % the reading panel reports nothing.

If your input device is a system-audio loopback rather than a microphone, Birdy will
hear its own output — the match meter is the way to tell.

### Listening

The Listen tab chooses between a **microphone** (with a device picker) and **computer
audio** via display capture — tick "share audio" in the browser's dialog or no sound
arrives. Echo cancellation, noise suppression and gain control are all switched off:
they are tuned for speech and they gate exactly the quiet broadband texture a distant
bird is made of.

A recording can be sent straight into the learning store with **Learn from this**. It
goes through the pipeline's own segmenter — the same function that processes downloaded
audio — rather than a second implementation in the browser, so a bird recorded at your
desk and one fetched from xeno-canto are analysed by identical code.

### Colour

Every point has a **pale resting tint** and a **saturated responding one** in the same
hue. Response is a walk between them, so identity never moves and intensity always
does — and unlike a walk from dark to darker it stays legible when forty points of one
cluster overlap. Anything responding also gets a ring of the background colour around
it; without that a lit knot fuses into a single silhouette and the per-point response,
which is the entire point of the view, disappears.

Since the arrangement now says what the grouping is, colour only has to say whether to
carry it: the display control offers **Monochrome** and **Coloured**, and what a colour
*means* follows the arrangement — species hues under Sound and Bird, the three-step
claim palette under Meaning. Monochrome drops the category entirely and leaves response
to value, size and the ring, which is most of what carried it anyway.

**Meaning** gives each cluster a colour for
how much meaning is claimed for it — *referential* (names something outside the bird),
*social* (says something about the singer), *structural* (a song element carrying syntax
and no referential meaning). The pipeline sorts each documented function into a
behavioural class using a keyword table it writes into `manifest.json`, so the grouping
can be audited.

**What colour can and cannot carry here.** Twelve species hues cannot be told apart by
colour alone, and that is arithmetic rather than a failure of taste: at usable chroma,
clearing the ΔE 15 normal-vision floor needs about 52° between hues, so a wheel holds
roughly seven, and colour-vision deficiency cuts that to about three. Separating on
lightness as well as hue takes the worst species pair from ΔE 5 to 12.9, which is better
but still short. So colour in the Bird view is *orienting*: every cluster carries a
label naming its species, selecting a bird dims the others, and the reading panel says
which bird it heard. Turn the colour off entirely and nothing becomes unreadable. The
three-step Meaning palette is the one held to the full gate — worst pair ΔE 9.2 deutan,
24.0 normal — because there it is doing real categorical work.

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

## Growing the corpus from real recordings

The shipped galaxy is rendered from the hand-authored inventory. Two further commands
grow it from field audio without ever holding more than one recording at a time:

```bash
cp .env.example .env && $EDITOR .env                   # your xeno-canto v3 key
uv run birdy-pipeline harvest --per-species 40         # stream in, keep a bounded sample
uv run birdy-pipeline learn                            # fit syllables + syntax, verify them
uv run birdy-pipeline build --inventory ../data/learned-inventory.json \
                            --harvest-store out/harvest
```

`harvest` fetches, decodes, analyses and **deletes** each recording before the next one
starts, keeping a species-stratified reservoir of 28-d descriptors capped at a size you
choose. It also tracks statistics over every descriptor it discards, so it can tell you
how far the sample it kept has drifted from the stream it came from.

`learn` fits syllable parameters to the segmented audio, then renders each fitted
syllable through the same syrinx oscillator the app uses and records how close it lands
— descriptor cosine and F0 error, written next to every learned syllable. Syllable order
within a recording gives a first-order grammar, which is what lets Birdy compose phrases
no bird sang in a syntax measured from birds that did. Those phrases are labelled
*invented*; their syllables are labelled *field recording*.

Still nothing is sampled. The recordings are the *measurement*, not the material: what
survives one is a few dozen numbers per syllable — duration, level, attack, an F0
contour, modulation depths, a timbre class — and the note you hear afterwards is
integrated from the oscillator, as every note in Birdy is. That is the route the
research names for "record a real bird, then re-sing it synthetically"
([`docs/04-synthetic-bird-voices.md`](docs/04-synthetic-bird-voices.md) §4.2, Boari
et al. 2015), and the resynthesis cosine printed next to each fitted syllable is how
you know whether the model really caught the bird.

`learn` writes the fitted types **next to** the documented ones rather than instead of
them: fitted ids start with `L`, carry `unlabelled` confidence and no function, and
every playback-verified call keeps its citation. `--learned-only` writes the fitted
repertoire on its own.

### What the fitted voices actually achieve

On the shipped harvest — 434 recordings, 31,653 segmented syllables, 12 fitted types per
species:

| measure | before inversion | after inversion |
|---|---|---|
| F0 error of the resynthesis against its own contour | — | **median 0.80 %** |
| resynthesis cosine to the syllables it was fitted to | median 0.31 | **median 0.547** |
| cosine to the *nearest rival* type | — | **median 0.533** |
| resynthesis nearest its *own* type rather than another | 40 of 132 | **67 of 132** |

The gesture search (nine contour knots, three passes over ten parameter axes) nearly
doubles the resynthesis cosine and takes own-type nearest from 30 % to 51 %. It does not
rescue the result, and the fourth row is why: **0.547 against its own type, 0.533
against the nearest rival.** The fit is barely better at resembling the call it was
fitted to than it is at resembling a different call by the same bird.

Read against the frame those cosines live in — two real syllables of one type score
about 0.78, two of *different* types about 0.49 — the fitted voices sit at 0.547, which
is nearer the different-type baseline than the same-type one. That is a clear result and
not a flattering one: **the oscillator reaches the pitch and does not reach the timbre.**
The F0 error is 0.80 %, so the contour is essentially exact; everything the descriptor
still objects to is spectral. A field recording carries wind, distance, a second bird and
a room; a two-parameter oscillator carries none of that, and 26 MFCC dimensions notice.

How much they notice is worth stating as its own number, because it turns out to be the
largest single effect in the whole system. Of the 176 clusters in the shipped galaxy,
**82 hold nothing but field audio, 86 hold nothing but synthetic renders, and exactly one
is a mixture.** A real call and Birdy's resynthesis of that same call do not merely score
poorly against each other — they are never even grouped together. The dominant axis of
this feature space is *was this recorded or synthesised*, not *what does it sound like*,
and that is why one sound can light two knots on opposite sides of the galaxy: the note
being sung is the synthetic cluster, and the field cluster of the same call is somewhere
else. See the pipeline README, "The loudest thing in this space is the microphone", for
what it costs and what would fix it.

The numbers only say this because of how they are taken, and that is worth stating,
because the previous version of this check said nothing at all. It compared a fitted
syllable against the *recording-level* descriptor — a five-second window average over
everything that recording contained, identical for every type of a species — in the
corpus statistics of a synthetic build. In that frame every field syllable scores 0.99
against every other, so the check could not fail. It now compares against the syllable's
own audio, in a frame centred on the harvested population, where 0.78 and 0.49 are
measurably different numbers.

### Why not just play the recordings back?

It would sound better — it would sound perfect, because it would be the bird. Two things
stop it, and only one of them is philosophy.

The first is the licence, and it is measured rather than assumed. Of the 435 recordings
in the current harvest: 344 are CC BY-NC-SA, 68 are CC BY-NC-**ND**, 18 are CC BY-NC,
three are CC BY-SA, one is CC0. So **four** of them could be redistributed in a product
that might one day be commercial, and the 68 ND ones cannot legally be pitch-shifted or
time-stretched at all, because that makes a derivative. A shipped sample bank means
accepting non-commercial for the whole app, excluding the ND clips, and carrying
per-clip attribution into the interface.

The second is the claim. "Nothing is sampled; every note is integrated from the syrinx
model" is what makes the galaxy's response mean anything — the app is showing you what a
physical model of a bird does, and a played-back sample is a recording of a bird rather
than a claim about one.

There is a version that costs neither: a **local** sample bank, never shipped, that
plays the real syllable next to its resynthesis. Nothing is redistributed, so the licence
question does not arise, and it is the strongest possible demonstration of the science —
you can hear exactly how far 0.61 cosine is from the real thing.

Every harvested recording's recordist and licence is written to `CREDITS.md` in the
store. xeno-canto recordings are individually licensed and CC-BY-NC-SA is common.
See [`pipeline/README.md`](pipeline/README.md) for the details.

### Driving it from the interface instead

`npm run dev` starts the control process for you — a Vite plugin
([`app/vite-plugin-pipeline.ts`](app/vite-plugin-pipeline.ts)) runs
`uv run birdy-pipeline serve` in the background, hands its job log to Vite's output and
kills it when the dev server stops. If something already answers on the port it is left
alone, and if `uv` is missing dev keeps serving and the Learn tab says how to start the
process yourself. `BIRDY_PIPELINE=0` turns the autostart off; `BIRDY_PIPELINE_PORT`
moves it.

The app's **Learn** tab picks that up and gives you the same three operations with the
store's figures in front of you and the job's log streaming back. It binds to
`127.0.0.1` only and the address is not configurable — every endpoint runs pipeline
code, so exposing it on a network would be handing out remote execution.

The running app still needs no backend. This is a developer-facing process for driving
the offline stage; the built site never talks to it.

**A build re-places every point at once**, and there is no way around that: clustering,
the projection and the per-point feature space are all computed over the whole corpus, so
a syllable learned a minute ago has no position until the build that places every other
point again. What the app does do is remove the step after it. Each build stamps
`manifest.json` with `builtAt`; the Learn tab compares that stamp with the one the
running session loaded, and when they differ it re-fetches the assets under that stamp
and swaps the galaxy, the inventory and the voices in place. New nodes, new birds and
new syntax appear without a page reload.

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
quietly lights the wrong clusters. Current: **25/44 exact, 26/44 same species** — down
from 35/44, and the drop is the price of the learned inventory rather than drift. The
galaxy went from 44 clusters to 176 when the fitted types joined the documented ones, so
a rendered `cuck` now competes with a tawny owl's `L01` fitted to real audio that happens
to resemble it. Build without the fitted types (the checkbox in the Learn tab, or plain
`--inventory ../data/inventory.json`) and the old figure comes back.

`uv run birdy-pipeline verify` checks the generated assets, including that the per-point
feature rows are unit vectors and still separate their own cluster from the rest — a
mirrored PCA sign would otherwise light the wrong points with total confidence.

## Credits

The science behind each design decision is cited inline in `docs/`, and every call
function in `data/inventory.json` carries its reference. The syrinx model is Mindlin and
Laje's; the compositional-syntax result is Suzuki, Wheatcroft and Griesser (2016); the
pure-tone-by-resonance-filtering result that makes the tracking formant mandatory rather
than cosmetic is Beckers, Suthers and ten Cate (2003).
