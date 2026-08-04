# The four groups who would actually act on this

A preprint changes nothing on its own. Paper one says that a widely used evaluation protocol is
optimistic, and the people who can change a protocol are its maintainers.

**Read these before sending them.** They name other people's models and say their published
numbers are flattering. That is a defensible claim and it should go out in your voice, not in
mine. The numbers are in now, so these are ready on that count.

Send them **after** the Zenodo DOI exists, so each one can link something permanent.

---

## 1. BirdSet — the most direct, and the friendliest

`DBD-research-group/BirdSet` on Hugging Face → Community tab.

BirdSet already excludes BirdNET from its `XCM`/`XCL` evaluation for training-set leakage, so
they have thought about exactly this problem and will recognise the design immediately.

> **A recordist-blocked split, and a way to include BirdNET after all**
>
> BirdSet excludes BirdNET from XCM/XCL evaluation because both are drawn from xeno-canto. We
> think there is a way around that, and it produced a number we would like to offer.
>
> Filtering xeno-canto on **upload date** rather than archive provenance gives audio that
> postdates a model's training snapshot. `since:2025-09-01` is a month past Perch 2.0's
> publication and two years past BirdNET V2.4's June 2023 release, so the same corpus is
> uncontaminated for both models at once. Freezing both models and training only a linear probe
> puts identical contamination on both sides of any comparison, so whatever either memorised
> cancels out of a difference.
>
> On that population — 8,287 recordings, 884 species, 646 recordists — a recordist-blocked split
> costs a linear probe **18.51 points** of top-1 on frozen Perch 2.0 features and **21.59** on
> frozen BirdNET V2.4 features, against a random split. Blocking was worse in 20 of 20 paired
> folds on both. As error rates that is 2.01x and 2.03x — the two models agree on the ratio to
> two decimal places while differing by three points in the raw figure.
>
> One caution we would pass on: the effect is not a single number. Across nested label sets of
> 62 to 884 species on the same recordings, the points climb from 12.75 to 18.51 while the error
> ratio *falls* from 2.97x to 2.01x. Neither unit is invariant, so a figure without its class
> count cannot be compared against.
>
> Two things we would flag for anyone repeating it. Species carried by a single recordist have
> to be dropped rather than scored: under blocking they land wholly on one side and become an
> empty test class, and counting them as errors manufactures the result. And both arms must be
> restricted to the classes present on both sides — a blocked split strands whole species, and
> dropping those from the blocked arm alone makes it an easier problem and *understates* the
> drop.
>
> Embeddings, metadata and the catalogue are here: [HF LINK]. Code and the archived release:
> [ZENODO DOI]. Happy to run it against a BirdSet split directly if that is useful.

---

## 2. Perch — `google-research/perch` on GitHub, Discussions

Perch comes out of this comparison *well* on the recordist axis: it carries less recordist
structure than our own 32-d space. Lead with that; it is true and it makes the rest readable.

> **What a recordist-blocked split costs a probe on frozen Perch 2.0 features**
>
> We measured recordist leakage on a population uploaded to xeno-canto after Perch 2.0's
> training snapshot, using frozen features and a linear probe so contamination is identical on
> both sides of the comparison.
>
> Perch does comparatively well here. On identical rows it carries **16.5 % less** recordist
> structure than a 32-d space we trained on our own corpus, and BirdNET carries 24 % more. The
> two of you disagree with each other more than either differs from ours, which we read as the
> structure being a property of the archives rather than of any model's loss.
>
> The cost of blocking itself is **18.51 points** of top-1 on frozen Perch features, 2.01x the
> errors, over 884 species and 646 recordists, worse in 20 of 20 paired folds.
>
> Separately: per-recordist findability correlates at +0.85 between your space and BirdNET's after
> removing how many recordings each contributed. The same *individual* recordists are the
> identifiable ones in both, which is why we read this as the archives rather than as either
> model's loss.
>
> Details, embeddings and code: [LINKS].

---

## 3. BirdNET — `birdnet-team/BirdNET-Analyzer` on GitHub, Discussions

BirdNET comes out *worse* on this axis. Say so plainly and say what it does not mean.

> **Recordist structure in the V2.4 backbone, measured on post-cutoff audio**
>
> Using the ONNX backbone export and audio uploaded to xeno-canto well after V2.4's June 2023
> release, we measured how much of the embedding's nearest-neighbour structure is recordist
> identity rather than species.
>
> BirdNET carries about 24 % more recordist structure than a small task-specific space on
> identical rows, and about 40 % more than Perch 2.0. We do not read this as a defect: a model
> trained on archives learns what the archives contain, and recordist identity is in there. It
> does mean a benchmark number from a randomly split archive corpus is optimistic about
> deployment on a new recorder in a new place.
>
> [LINKS]

---

## 4. xeno-canto — the forum

These are the people whose work the whole thing rests on, and they are also the only ones who
can fix the confound. See [`xeno-canto-forum-post.md`](xeno-canto-forum-post.md).

---

## 5. WILDLABS — practitioners, not model authors

See [`wildlabs-post.md`](wildlabs-post.md).

---

## Placeholders to fill before any of this goes out

All the measured numbers are filled in from `pipeline/analysis/w0_full.json` and
`w0_confound_anatomy.json`. Only `[HF LINK]`, `[ZENODO DOI]` and `[LINKS]` remain, and those need
accounts. The cross-model lift figures (16.5 %, 24 %, 40 %) come from `docs/23` §23.6.3.
