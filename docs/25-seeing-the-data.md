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

The statistic that does say this is already computed and already shipped: **`knnAgreement`**,
*"share of a point's 3D k nearest neighbours sharing its type"* at k = 10 — **0.4574 on this
build**, 0.4462 on v9. That is per-point by construction — the manifest reports its mean — and
it measures the projection we actually ship rather than a mapping the browser never uses.

**BUILT, and on a different channel than this section proposed.** The proposal was radius:
agreement out on the rim, ambiguity sinking toward the core. What shipped is **saturation** — a
low-agreement mark keeps its size, its weight and its place and loses its colour toward its own
luminance — behind the Display panel's "Neighbours disagree" switch. Radius was the wrong
channel and the reason generalises: size and ink are how this view says *this sound is
responding*, so spending either on a doubtful position would draw an unsupported mark as a
quiet sound. What is in doubt is not the sound, it is where the map put it. Draining the hue
says "the colour here is standing on less" and moves nothing, which is also what lets the same
frame be compared with the channel on and off.

Measured, per point rather than as a mean: **109 293 of 444 213 sounds (24.6 %) sit among ten
strangers** — agreement exactly 0. A mean of 46 % cannot say that, and it is the number the
panel now prints next to the switch.

**4. A linked attribute panel, not another colour mode.**
For many attributes that must stay distinguishable *and* show interaction, the established
answer is coordinated views with brushing rather than more encodings on one view: brush a
range on an `snr` or `dur` histogram and the galaxy dims to the selection; lasso in the galaxy
and the histograms redraw. This is what stops attributes competing for a single channel.

**5. Density contours under the core.**
At 387 287 points the middle is saturated. Contour the dense core and draw individual points
only where density is low, which is the standard overplotting remedy and makes the core
legible.

**6. Relations on selection, bundled. — BUILT, and the asset was missing for the whole life
of the v10 build.**
`RelationThreads` and the species panel's "Sounds like" chips both read `relations.json`, and
on selection they draw the eight nearest partners rather than the hairball. The finding was
that **the asset did not exist**: the v10 chain runs `build --no-relations`, and
`out/harvest-inband` carried no `embeddings.f32`, so the build logged *"relations skipped"*
and `app/static/birdy/relations.json` was never written. Because the asset is optional by
design — the loader treats absent and over-32 MB identically — nothing failed and nothing
said so; the threads simply drew zero segments and the chips never rendered.

The fix cost eight minutes of compute, which is the part worth recording: `critic embed` on
the store took **7 seconds** and `compute_relations` **219 s**, giving 3 093 828 species
pairs and **950 shared-type candidates** under a threshold of **0.0412** (the median
within-species nearest-type distance). Trimmed to 8 partners per species that is **14 488
pairs, 3.8 MB** — `analysis/v10_relations_ship.py`, which exists because the standalone
`relations --out` verb deliberately writes the *complete* document and on this corpus that is
the 760 MB file that once hung the tab.

*One thing to look at:* the nearest pair comes back at distance −0.0 with 8 shared types
(`bleda_notatus` / `eurillas_latirostris`). Two different species with identical type
centroids is either a duplicated recording across two species labels or a real degeneracy in
the fit, and either way it is not a relation.

**7. Draw the residual, to show whether a render fits. — BLOCKED, and the reason is a
measurement.** This step assumes every fitted type has a synthetic point to draw the segment
*from*. It does not. Counting the shipped build by provenance:

| points | share | class | what it is |
|---|---|---|---|
| 367 196 | 94.8 % | `field` | real audio carrying a fitted type |
| 11 028 | 2.8 % | `candidate` | real audio that nothing has named |
| 8 007 | 2.1 % | `documented` | our whole-song renders, no type id |
| 1 056 | 0.3 % | `documented` | our renders of the 44 authored calls (44 x 24 variants) |
| **0** | — | `learned` | **our synthesis of a fitted type** |
| 0 | — | `unlabelled` | the `grow` arrival pool, empty in this build |

**Zero points are a render of a fitted type.** `PROVENANCE.learned` needs `syllableId[0] === 'L'`
with a non-field source, and the only renders in the cloud are the authored calls (single-letter
ids) and the song renders (no id at all). So two of the five provenance classes are never
painted, and the residual segment has no origin for any of the 16 283 learned types. Either the
build has to emit a render point per fitted type, or the residual has to be drawn as a property
of the field knot itself — a halo sized by the type's MCD — rather than as a segment between two
points.

**Also, `manifest.clusterPlan.unlabelledPoints` = 19 035 pools two unlike things.** It is exactly
11 028 unnamed *field* syllables + 8 007 of *our own* song renders. Only the first 11 028 are a
discovery surface; the rest are ours. §25.1 leaned on the combined figure.

**8. Draw the residual, to show whether a render fits.**
Per type there is a resynthesis cosine and, from the spectral bench, an MCD. A short segment
from a synthetic point to its field centroid with length set by the render's error makes
fidelity visible per type. This is what the xeno-canto audio cache buys: the bench can only
score a type whose audio is cached, and that cache now reaches the 39.9 % of the corpus it
never could.

## 25.4 What each step costs to ship

Two columns, not one, per §25.4b: a channel is not shipped until both halves exist, and this
table used to name only the pipeline half.

| step | pipeline half | view half | asset cost |
|---|---|---|---|
| unknown map | none — `--clustering both` | `uUnheard` figure/ground swap **BUILT**; needs the joined `unassigned` | a second asset set |
| SNR | **BUILT** — `PointSet.snr` -> `points.json` | **BUILT** as saturation on a p5..p95 ramp, not brightness — "Recording is noisy" | ~0.4 MB |
| kNN agreement | **BUILT** — `points.knnAgreement` | **BUILT** as saturation — `aTrust`/`uTrust`, "Neighbours disagree" | ~0.4 MB |
| attribute panel | 3-4 arrays for the brushed fields | not started | ~1.5 MB |
| density contours | none, view-side | not started | none |
| relations arcs | **BUILT** — `relations.json`, 14 488 pairs | **BUILT** — `RelationThreads`, "Sounds like" chips | none |
| per-knot tearing | ratios computed then discarded | nothing to read | small |
| residual segments | per-type MCD into the inventory | not started | small |

Against a 30 MB `points.json`, every one of these is affordable. The work is in the view, not
in the pipeline, which is the argument for doing them in this order.

## 25.4b Shipped and undrawn: check the view half, not just the pipeline half

Two of the channels this document asked for are in `points.json` right now, at 444 213 values
each, and **nothing in `app/src` reads either of them.** A grep for `points.snr` and
`points.knnAgreement` across the app returns the type declaration, two manifest-level reads
for the HUD's aggregate, and one comment. So about 4 MB of the 41 MB asset is a measurement
the browser downloads every load and never draws.

The table in §25.4 is what let this sit: it marked brightness = SNR as **BUILT**, and the
pipeline half genuinely is. A channel is not built until something draws it, and the row said
"BUILT" while the view had never been touched. That table now has a column per half.

**One of the two is now closed.** `knnAgreement` drives saturation (§25.3 above records which
channel and why it is not radius). The measured proof that it draws — because "wired, compiled
and multiplied by zero" passes every other check — is `probe:trust`: mean chroma over the ink
falls **14.9 %** when the switch comes up while the ink area holds to **1.2 %**, so colour is
spent and nothing else is. `verify:trust` asserts the other half, that the per-point mean equals
the manifest aggregate to four places (0.4574), because a per-point array and an aggregate
measured on different point sets is a failure a row-index join produces in silence.

**`points.snr` draws too, and it did not get a channel of its own — it shares one.** The row
this document asked for was *brightness* = SNR, and brightness is the one channel it could not
have: tone is the depth cue, and the aerial-perspective mix deliberately darkens the near side
as well as paling the far one, because that is what makes a rotating scatter read as a volume.
The inner gradient is pitch. The mark's edge is pinned to one pixel by `fwidth` for the same
reason a constant feather was rejected — five-pixel marks become smudges. Size and ink weight
are activation and the figure/ground swap. Hue is provenance or genus.

So **saturation carries both doubts and the two take turns on it**, the way the provenance and
bird-colour modes already share hue. Choosing one clears the other, and the comparison that
buys is the point: the same marks, the same frame, drained first by *where the map put this*
and then by *what the recording was like*. Measured, they are different pictures — 23.0 % and
20.7 % chroma down from the same frame, 3.0 % apart from each other, with the ink area holding
to 0.7 %. `probe:trust` asserts that difference, because two sources sharing one buffer fail by
drawing identically, which looks like success from every other angle.

Two rules the SNR ramp needed, both in `doubt.ts`:

- **The ramp is the corpus's own p5..p95, 2.14 to 39.34 dB, and everything outside saturates.**
  The array reaches **166.95 dB** and 85 values sit above 100 dB — a ratio of ten billion,
  which is a noise floor estimated at nearly zero rather than a clean recording. Linear, those
  85 points would own the top of the scale and the 14.5 % of the corpus below 6 dB would be
  crowded into the bottom few percent. The panel prints both ends, so "fully coloured" cannot
  be read as "cleanest in the corpus" when it means "at or above the 95th percentile".
- **Absent stays absent.** All 8 583 nulls are the rendered inventory rows, which have no noise
  floor to measure a ratio against, so a zero would report our own synthesis as the noisiest
  audio in the corpus. They fill with `NO_DOUBT` and draw exactly as they always did.

**A third case, found the same way and still open.** `torn_clusters` scores every knot for
whether the projection draws it in two places, then throws all 6 316 per-knot ratios away and
keeps five aggregates. The manifest says 2 035 torn and 0.43 Pearson faithfulness while a
viewer reading distance off one specific knot has no way to learn whether *that* knot is one of
them. Same shape as the two above: measured in the pipeline, discarded before it could reach a
reader.

The same trap caught the density verdict from the other side. The shader has drawn unassigned
points **35 % smaller and 45 % fainter** since density clustering was added — defensible on
the label map, where the class is empty, and exactly backwards on the map whose entire purpose
is refusing: the discovery surface was the quietest thing on the stage. `uUnheard` now swaps
figure and ground on that verdict (placed marks to 0.55 size and 0.30 ink, refused ones to 1.6
and full weight), and the joined `unassigned` channel is what makes it readable on the map that
actually ships.

## 25.5 The rule to keep

Colour is spent. It carries provenance or genus, one at a time, and `palette.ts` has already
paid for that decision with a measured accessibility argument. Everything proposed above uses
position, radius, brightness, size, opacity or interaction — so each new answer arrives on its
own channel and the legend can still be one line.
