# Which paper goes where

There are two papers and they want two different rooms. `docs/24` §24.3 already settled why
they are separate: the system paper depends on this pipeline being correct, and the W0 paper
depends on no part of it.

**Post each paper to exactly one preprint server.** Posting the same manuscript to two splits
the citation record, confuses indexers, and reads as careless. This is the single easiest
mistake to make here.

---

## The system paper → EcoEvoRxiv

`docs/whitepaper/arxiv/main.tex` · 40 pages · **complete, could go today**

[EcoEvoRxiv](https://ecoevorxiv.org) is free, not-for-profit, and scoped to ecology,
evolution and conservation. Three reasons it fits better than the alternatives:

1. It already hosts bioacoustics and passive-acoustic-monitoring work, so the readership is
   the one that would care about a syllable inventory over 2,650 species.
2. **It accepts reports and postprints**, not only manuscripts destined for a journal. This
   paper is a system, a resource and a ledger of 37 refusals. It is not obviously on its way
   to a journal, and most preprint servers assume it is.
3. Accepting CC BY-NC-SA is not a problem there.

**Alternative: bioRxiv.** Free, much larger audience, section *Animal Behavior and Cognition*.
Choose it over EcoEvoRxiv if reach matters more than fit. It is stricter about looking like a
journal submission, and it will screen a 40-page methods-and-refusals paper more sceptically.

Pick one. My recommendation is EcoEvoRxiv, on fit.

---

## The W0 paper → TechRxiv

`docs/whitepaper/w0-arxiv/main.tex` · 6 pages · **NOT READY — results section is still `\todo`**

This one is an evaluation-methodology result about two machine-learning models. Its natural
home is arXiv `cs.SD`, which is excluded, so: [TechRxiv](https://www.techrxiv.org), run by
IEEE, free, and scoped to engineering and signal processing. That is the right audience for
"here is what your split costs you".

**Do not post it until `pipeline/analysis/w0_full.json` is complete and its numbers are in the
text.** The `\todo` macro renders as loud red `[TODO: ...]`, so this is hard to do by accident,
but the point stands.

**Alternative:** hold it and put it directly in front of the maintainers instead — see
[`../community/benchmark-maintainers.md`](../community/benchmark-maintainers.md). For a result
whose whole purpose is to change four teams' behaviour, a preprint is a slower path than an
issue on their tracker. Doing both is fine; the preprint is what makes it citable.

---

## Checklist, either venue

- [ ] ORCID (free, orcid.org)
- [ ] Zenodo DOI in the data-availability section, and the paper **rebuilt** so the PDF
      carries it
- [ ] Acknowledgements `\todo` resolved — an explicit "none" is a valid answer and better
      than a blank
- [ ] Every figure legible in greyscale. `figures.py` uses a violet/clay/slate palette; check
      `fig_confound` and `fig_corpus`, where colour carries meaning
- [ ] The abstract standing alone. Both abstracts currently reference section numbers; that
      is fine in the PDF and reads badly in a web abstract field, so keep a plain-text
      version for the form
- [ ] A licence declared to match `NOTICE.md`: **CC BY-NC-SA 4.0**

## What to write in the "competing interests" and "funding" fields

Competing interests: none, unless something changed. Funding: if there is none, say "This
research received no external funding." Leaving it blank invites a query.
