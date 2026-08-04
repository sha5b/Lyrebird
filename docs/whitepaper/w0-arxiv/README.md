# Paper one — what a recordist-blocked split costs a bioacoustic foundation model

This is **not** the system paper. `docs/24` §24.3 separates the two on purpose:

| | what it claims | depends on our pipeline being correct? |
|---|---|---|
| `../arxiv/` | the system, the resource, and 36 written refusals | **yes** |
| `w0-arxiv/` (here) | what a recordist-blocked split costs Perch 2.0 and BirdNET V2.4 | **no** |

The independence is the point. This paper needs no part of the Lyrebird pipeline to be
correct, which is what gives it the wider reach, and is why it is a separate document rather
than a section.

## Building it

```
cd docs/whitepaper/w0-arxiv
tectonic -X compile main.tex --outdir build
```

`tectonic` is at `~/.local/bin/tectonic` on this machine. Last build: **6 pages, 0 overfull
boxes, 0 undefined references, 0 undefined citations.**

## What is measured and what is still a placeholder

Everything in §§1–5 and §7–10 is written and its numbers are in the repository. The two
`\todo` blocks are:

- **§6 Results** — filled from `pipeline/analysis/w0_full.json`. The full run was still
  fetching when this draft was written. **Nothing under that marker should be read as
  measured until the marker is gone.**
- Zenodo DOI and acknowledgements, as in the system paper.

The `\todo` macro renders as loud red `[TODO: ...]` in the PDF, so no placeholder can ship
unnoticed.

## The numbers that are already real

| claim | value | where from |
|---|---|---|
| complete post-cutoff q:A catalogue | 21 928 recordings, 4 305 species, 961 recordists | `w0_full_catalogue.py` |
| scorable species (≥6 recordings, ≥2 recordists) | 886, over 13 646 recordings | same |
| population after the 12-per-species cap | 8 321 recordings, 886 species, 649 recordists | `w0_full_fetch.py` |
| pilot, for comparison | 730 recordings scored of 2 158 embedded, 62 species, one model | `w0_recordist_split.json` |
| pilot drop | 9.68 points (93.29 → 83.61), 20/20 folds, 2.44× the errors | same |
| cross-model disagreement | Perch −16.5 %, BirdNET +24 % against the 32-d critic, same rows | `docs/23` §23.6.3 |
| structure on unseen audio | recordist +0.441, species +0.750, 293 matched rows | `w6_t1b_perch_postcutoff.json` |

## Two claims that were checked against sources rather than abstracts

- **Stowell & Plumbley 2014** (PeerJ 2:e488) is the origin of the recordist-stratified split
  and the rationale quoted in §2. Verified against the full text: the stratification applies
  to the `bldawn` dataset only — 20 recordings each from three UK recordists, three-fold —
  and the paper reports **no** random-against-blocked comparison. That absence is this
  paper's opening.
- **BirdNET V2.4 was released June 2023**, EfficientNetB0-like backbone, 1024-d embedding.
  That date is what makes the post-cutoff bound (uploads after 2025-09-01) safe for BirdNET
  as well as for Perch, and it is what dissolves the design constraint that had ruled out
  testing both models on an xeno-canto corpus.

## The pilot's two mistakes, kept visible on purpose

Both were invisible from inside the pilot and are worth remembering:

1. Its catalogue held exactly **6 000** recordings. That was `SEARCH_PAGES = 60` × 100 per
   page, not the archive. The same query has 21 928.
2. It selected by **recordist**, inheriting the rule from `w6_t1b_perch_postcutoff.py`, whose
   unit was the recordist. W0's unit is the species, and that is what left 62 scorable
   classes out of 827 species fetched.

`w0_recordist_split.py` is kept runnable and unchanged, because it is the measurement the
system paper's pilot row was computed from and should stay reproducible against the
catalogue it actually used.
