# Where to put this so the people who care will find it

Every venue here is **free**. No article-processing charge, no submission fee, no membership.
arXiv is deliberately absent.

Two constraints come from this project and not from the venues. Read them before anything
else, because they rule some options out.

| constraint | where it comes from | what it forbids |
|---|---|---|
| **CC BY-NC-SA 4.0** | `NOTICE.md` | any venue that requires CC BY or CC0 for the text |
| **No audio may be redistributed** | `NOTICE.md` — the recordings are the recordists', under per-recording licences | uploading audio anywhere. Embeddings, descriptors and metadata are fine; the store holds no audio by design |

The second one is a feature here, not a problem. A dataset release of *derived numbers* is
exactly what this project already is, and it is the reason the release can be made at all.

---

## Do these in order. The first two unblock the papers.

### 1. Zenodo — because both papers have a `\todo` waiting on it

Both `docs/whitepaper/arxiv/main.tex` and `docs/whitepaper/w0-arxiv/main.tex` carry
`\todo{Zenodo DOI}` in their data-availability sections. Nothing else can be finished until
this exists. Zenodo is free, run by CERN, gives a permanent DOI, and accepts any licence.

See [`zenodo/`](zenodo/). Roughly 30 minutes.

### 2. GitHub release + `CITATION.cff`

A DOI people cannot resolve to code is half a release. `CITATION.cff` at the repository root
makes GitHub show a "Cite this repository" button and makes the work machine-readable to
Zotero and friends. Zenodo can be wired to mint a DOI on every GitHub release.

See [`../CITATION.cff`](../CITATION.cff), which is written and needs your ORCID.

### 3. A preprint server, and only one of them

Do **not** post the same paper to two preprint servers. It splits the citation record and
looks careless. See [`preprint/`](preprint/) for which paper goes where and why.

### 4. Hugging Face — this is where the audience actually is

BirdSet, Perch and BirdNET all live on Hugging Face. The people who would act on paper one
read dataset and model cards there, not preprint servers. See [`huggingface/`](huggingface/).

### 5. Tell the four groups who would act on it

Paper one is about how *their* models get evaluated. A preprint they never see changes
nothing. See [`community/`](community/).

---

## The venues, with what each is actually for

| venue | cost | what to put there | why this one |
|---|---|---|---|
| **Zenodo** | free | derived data, code snapshot, both PDFs | the DOI, permanent archive, any licence |
| **GitHub** | free | the code, a tagged release | where anyone reproducing it will start |
| **EcoEvoRxiv** | free | the **system paper** | ecology/evolution/conservation, not-for-profit, already hosts bioacoustics work, and accepts reports and postprints rather than only pre-submission manuscripts |
| **bioRxiv** | free | alternative for the system paper | larger audience, Animal Behavior and Cognition section. Pick this **or** EcoEvoRxiv |
| **TechRxiv** | free | the **W0 paper** | IEEE-run, engineering and signal processing. The natural non-arXiv home for an evaluation-methods result |
| **Hugging Face** | free | dataset card: the W0 population, both models' embeddings, recordist metadata. **No audio** | the benchmark community is here, and so are both models under test |
| **WILDLABS** | free | a short community post | conservation-technology practitioners with an acoustics group — the people deploying these models |
| **xeno-canto forum** | free | a courtesy post | the recordists whose work this is. They are also the only people who can fix the confound, by recording more species |
| **BirdNET / Perch / BirdSet issue trackers** | free | one concrete message each | the maintainers are the ones who would change a split |

## What only you can do

- [ ] An **ORCID** (free, 2 minutes, orcid.org) — every venue above wants one and `CITATION.cff` has a slot
- [ ] A **Zenodo** account (log in with GitHub)
- [ ] A **Hugging Face** account
- [ ] A **WILDLABS** account, if you want the community post
- [ ] Decide **EcoEvoRxiv or bioRxiv** for the system paper
- [ ] Fill the acknowledgements `\todo` in both papers, or write "none" explicitly
- [ ] Read `community/benchmark-maintainers.md` before sending it — it names other people's
      models and says their evaluation is optimistic. That should go out in your voice, not mine.

## Both papers are ready

The W0 full run finished and the gate is met on both models. Paper one's results, class-count
sweep, dose-response curve and cross-model recordist section are all written; paper two's
Table 10, phase-0 section and Limit 2 carry the new numbers. Both build clean with zero
undefined references.

The only `\todo` left in either is the **Zenodo DOI** and the **acknowledgements**, which is
why Zenodo is step 1 above.
