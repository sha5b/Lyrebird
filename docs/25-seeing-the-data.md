# 25. Seeing the data: channels, not more colour

The galaxy places every sound and says very little about any of them. This document is the
design for closing that gap, and it starts from what is measured rather than from a wish
list.

## 25.1 What is already placed, and what has nowhere to go

Nothing is missing positionally. The shipped build holds **387 287 points**: every one of the
store's 378 224 field syllables, plus 8 007 synthetic-song and 1 056 synthetic renders. Every
point carries a cluster, because the shipped `label` clustering assigns all of them.

What is thin is the number of **channels**. Today the galaxy encodes:

| channel | carries |
|---|---|
| position (3 floats) | the projection of the critic's embedding |
| colour | provenance (5 classes) **or** genus hue — one at a time |

And that is the list. Meanwhile each syllable in the store measures about twenty fields —
`snr`, `flatness`, `harmonic`, `noise_frac`, `am`, `am_depth`, `vib_rate`, `vib_depth`,
`attack`, `level`, `dur`, `gap_before`, `novel`, `timbre` — and each recording carries
`recordist`, `country`, `date`, `quality`, `sex`, `stage`. Almost none of it reaches the
browser, and what does reach it is visible only by selecting a single point.

This is also why a corpus that grew 11 % looked unchanged. The projector and every one of its
parameters is identical between v8 and v9 (PaCMAP, `nNeighbors` 10, `mnRatio` 0.5,
`fpRatio` 2.0, chord metric) and `meanRadius` is the same 0.51, so more points through an
identical projector in the same volume is a denser copy of the same shape. Density moved;
nothing that shapes the cloud did.

**One trap to know before building.** `point-features.f32` ships 8 floats per point, and they
are a *reduced acoustic basis for the live "sing and light up" cosine* (`features.ts`), not
interpretable attributes. They cannot be repurposed as data channels. New attributes have to
be shipped, and that is cheap: `points.json` is already parallel arrays, so one byte per
point is 387 kB against a 30 MB file.

## 25.2 The discipline worth copying

Colibrì's expert atlas draws 13 260 points and stays readable. Its rules, and each is
transferable:

- **One question per channel, declared in the header.** Position is measured routing
  affinity, size separates specialists from generalists, colour is storage tier, brightness
  is routing heat, and a white flash is a live activation. The legend states the mapping in
  one line above the canvas.
- **Figure and ground are designed.** 1 041 of 13 260 points are emphasised; the other 92 %
  are deliberately a faint cloud. The eye is given something to land on.
- **Labels are few and off-point.** About ten, anchored at outlying cluster centroids, never
  on individual points.
- **Time is its own channel.** Live events flash rather than recolour, so change does not
  compete with structure.

This project already holds the first rule in as many words — the galaxy's colour tooltip says
*"colour says one thing at a time"* — and `palette.ts` already argues that five categorical
hues cannot survive colour-vision deficiency. Both point the same way: **add channels that
are not hue.** Size, radius, opacity and brightness are unused and free.

## 25.3 The design, in the order it pays

**1. Ship the unknown map and let "none of these" be the figure.**
`build --clustering both` writes the `label` map to `known/` and the hdbscan map to
`unknown/`, and the app already detects the pair and offers a runtime toggle. In the unknown
map, the points hdbscan leaves unassigned *are* the discovery surface: draw assigned points as
the faint cloud and dense-but-unassigned regions bright and larger. This is the project's
stated purpose made visible, and it is the one map where a sound can answer "none of these" —
the shipped `label` map assigns everything by construction.

**2. Brightness = SNR.**
SNR is the corpus's real quality axis: median 11.96 dB, p10 2.62, and an exact census shows an
SNR floor dominates the segmentation-band fix on both species retained and quality gained
(`analysis/v10_snr_floor.py`). Mapping brightness to it makes the weak fifth of the corpus
visibly faint, so the quality distribution is seen rather than read. One byte per point.

**3. Radius = whether a sound's neighbours share its type.**
Colibrì sinks generalists to the core, and the analogue here is worth building. **The
statistic this section originally cited for it was the wrong one**, and the correction
changes which number the channel reports.

`speciesAgreement` = 0.4895 does *not* measure "is my nearest knot my own type". Its own
definition in the manifest reads: *"share of held-out syllables whose nearest knot carries the
same majority species **through the map as through the critic**"* — it scores the 28-d → 32-d
map against the critic on a held-out set, so it is a property of that mapping, not of a shipped
point. There is no per-point version of it, and 387 287 points cannot be given a radius from it.

The statistic that does say this is already computed and already shipped: **`knnAgreement` =
0.4462**, *"share of a point's 3D k nearest neighbours sharing its type"* at k = 10. That is
per-point by construction — the manifest reports its mean — so the channel is its per-point
value, one byte each: a point whose ten nearest neighbours are all its own type sits on the
rim, a point surrounded by other types sinks toward the core. It also measures the projection
we actually ship rather than a mapping the browser never uses.

**4. A linked attribute panel, not another colour mode.**
For many attributes that must stay distinguishable *and* show interaction, the established
answer is coordinated views with brushing rather than more encodings on one view: brush a
range on an `snr` or `dur` histogram and the galaxy dims to the selection; lasso in the galaxy
and the histograms redraw. This is what stops attributes competing for a single channel.

**5. Density contours under the core.**
At 387 287 points the middle is saturated. Contour the dense core and draw individual points
only where density is low, which is the standard overplotting remedy and makes the core
legible.

**6. Relations on selection, bundled.**
`relations.json` ships 14 425 species pairs and nothing draws them. All at once is a
hairball; the selected species' eight nearest partners as bundled arcs answers "how do these
interact" without permanent clutter.

**7. Draw the residual, to show whether a render fits.**
Per type there is a resynthesis cosine and, from the spectral bench, an MCD. A short segment
from a synthetic point to its field centroid with length set by the render's error makes
fidelity visible per type. This is what the xeno-canto audio cache buys: the bench can only
score a type whose audio is cached, and that cache now reaches the 39.9 % of the corpus it
never could.

## 25.4 What each step costs to ship

| step | pipeline change | asset cost |
|---|---|---|
| unknown map | none — `--clustering both` | a second asset set |
| brightness = SNR | **BUILT** — `PointSet.snr` -> `points.json` | ~0.4 MB |
| radius = kNN agreement | one parallel array | ~0.4 MB |
| attribute panel | 3-4 arrays for the brushed fields | ~1.5 MB |
| density contours | none, view-side | none |
| relations arcs | none — already shipped | none |
| residual segments | per-type MCD into the inventory | small |

Against a 30 MB `points.json`, every one of these is affordable. The work is in the view, not
in the pipeline, which is the argument for doing them in this order.

## 25.5 The rule to keep

Colour is spent. It carries provenance or genus, one at a time, and `palette.ts` has already
paid for that decision with a measured accessibility argument. Everything proposed above uses
position, radius, brightness, size, opacity or interaction — so each new answer arrives on its
own channel and the legend can still be one line.
