# Lyrebird — arXiv manuscript

`main.tex` is a self-contained LaTeX manuscript, written to replace
`docs/whitepaper/build_whitepaper.py`. It is arXiv-native: standard `article` class,
conventional preprint layout, `natbib` citations, figures pulled from
`docs/whitepaper/figures/` by relative path.

`build_whitepaper.py` was **not** modified. Nothing outside this directory was modified.

- `main.tex` — the manuscript. ~17\,000 words of prose plus 10 tables and 19 figures.
- `WHITEPAPER-FINDINGS.md` — 27 problems found in the code, the numbers and the project's
  own assumptions while reading. Read this before acting on anything else here.
- `README.md` — this file.

---

## Building it

There is **no LaTeX toolchain on this machine**, so the manuscript has been validated
statically (brace balance, environment nesting, table cell counts against column
specifications, `\ref`/`\label` closure) but has **never been compiled**. Expect to fix
overfull boxes on first build.

Install a TeX distribution, then:

```bash
cd docs/whitepaper/arxiv
pdflatex main
bibtex   main
pdflatex main
pdflatex main
```

Or, once `latexmk` is available:

```bash
latexmk -pdf main.tex
```

Fedora: `sudo dnf install texlive-scheme-medium texlive-natbib texlive-booktabs \
texlive-longtable texlive-microtype texlive-babel-english`.

### Packages used

`fontenc`, `inputenc`, `lmodern`, `babel` (british), `geometry`, `amsmath`, `amssymb`,
`graphicx`, `booktabs`, `longtable`, `array`, `caption`, `microtype`, `natbib`, `xcolor`,
`hyperref`. All are in `texlive-scheme-medium` and all are permitted by arXiv.

### First-build expectations

- **Table 1** (`tab:typing`) is 9 columns across the full text width and will probably be
  overfull. If so, drop the three `\todo`-free `---` rows of the right-hand panel, or split it
  into two tables.
- **Table `tab:positioning`** is 6 columns of wrapped text and may need `\small` dropped to
  `\footnotesize`.
- The **ledger** (`tab:ledger`) is a 58-row `longtable` at `\footnotesize`. It will run 3–4
  pages. That is intended.
- `\todo{...}` renders as red bracketed text. **Six of them remain, covering five distinct
  gaps** — see below. They must all be resolved or removed before submission.

---

## The bibliography — action required

`main.tex` cites `\bibliography{../references/references}`, i.e. it expects
`docs/whitepaper/references/references.bib`. **That file does not exist yet.** What exists is
`docs/whitepaper/references/REFERENCES.md` — a verified ledger of **104 keyed entries**
(40 `VERIFIED`, 59 `CORRECTED`, 2 `UNVERIFIABLE`) with 57 PDFs in `references/pdf/`, produced
in parallel with this manuscript. Someone must convert it to BibTeX, or change the
`\bibliography` line to point at whatever the `.bib` is eventually called.

**The keys in `main.tex` have already been renamed to match that ledger.** 77 keys are cited;
**62 match the ledger exactly**. The 15 that do not are listed with full bibliographic detail
in the comment block at the top of `main.tex`, and must be added:

`beans2022` · `berwick2011` · `cilibrasi2005` · `cranmer2020` · `dalziell2012` · `favaro2020` ·
`ganin2016` · `gustison2016` · `kneser1995` · `korsunsky2019` · `kubichek1993` · `li2004` ·
`prince2007` · `xenocanto` · `zhou2021mixstyle`

They are missing because they are **methods and framing literature the repository never cited**
— Kneser–Ney, Harmony, PLDA, NCD, MCD, simulation-based inference, gradient reversal, MixStyle,
BEANS, the Menzerath primary sources, and the archive itself — so the ledger's audit, which was
scoped to what the repo already cited, did not cover them. All 15 have been verified
independently and their details are in the header block.

Twelve keys were **renamed** from my originals to match the ledger (`laje2002a`/`laje2002b`,
`perch2`, `ddsp2020`, `rff2007`, `simclr2020`, `umap2018`, `hdbscan2013`, `hultsch1989`,
`elemans2008dove`, `goller1996a`, `inatsounds2024`). The header block lists the mapping. Do
not revert them.

### Read `REFERENCES.md` before finalising the text

Its audit reclassified **59 of 104 entries as `CORRECTED`**, and several corrections are
claim-level rather than bibliographic. Two of them changed sentences in this manuscript already
(the ABC–D species, and what the impulse-response augmentation paper is actually about — see
`WHITEPAPER-FINDINGS.md` #24 and #25). Assume there are more that touch the body text.

Note also that `docs/07-references.md` has a formatting artefact worth not inheriting: the
DDSP, RAVE, Windytan, FinchGPT and Lostanlen entries sit inside the "Habitat, deliberately not
fitted" bullet list even though they belong to Synthesis. Do not infer a habitat relation.

---

## Figures

### Used (10 of the 12 existing, unchanged, from `../figures/`)

| file | where | what it carries |
|---|---|---|
| `architecture.png` | §5 The system | the five-stage pipeline |
| `signal-chain.png` | §5 The system | the synthesis chain, with the parked extensions dashed |
| `claim-ladder.png` | §5 Verification | the five evidence labels and their corpus counts |
| `tonal-pin.png` | §6 Wall 5 | the missing spectrally rich tail |
| `ruler.png` | §6 Wall 1 | the objective's correlation with audible distortion, and the mel target's win share at two n |
| `confound.png` | §6 Wall 2 | recordist vs species lift, and every swept adversarial point against the empty gate region |
| `map-quality.png` | §6 Wall 4 | the region-disagreement decomposition and the session-gate AUCs |
| `spaces-bridge.png` | §7 Two spaces | the 28-d / 32-d pair and the RFF bridge |
| `avex.png` | §8 Post-hoc batch correction | the domain-merge arms at two scales |
| `syntax-depth.png` | §7 Grammar order | where the HMM's advantage lives, and the depth ceiling |

`confound.png`'s left panel is the `+0.488` / `+0.196` pair — see finding #6, which argues that
number should be re-measured on the current critic before publication.

### Not used

`corpus.png` — its left panel's species-count annotations overprint the store labels and are
illegible (finding #20).

### Wanted, and specified in `main.tex`

Six `% FIGURE WANTED:` comments sit at the bottom of `main.tex`, each with the data and the
source section. No figure-generating Python was written. In priority order:

1. **Held-out order scaling** — the paper's strongest result currently has no figure. Real vs
   shuffle, bits/token against Markov order 0–3. Source: docs/23 §23.2.2.
2. **Type retrieval against the cluster budget** — the four arms on two query populations, with
   the 0.602 ceiling as a line. The point is that the query population changes the answer by 18
   points. Source: docs/22 §22.8.
3. **Three spaces, two populations** — critic / Perch / BirdNET recordist and species lift, with
   the gate and the coverage of each estimate. Source: docs/23 §23.6.1–3,
   `pipeline/analysis/w6_birdnet_arms.json`.
4. **A corrected corpus-growth figure.**
5. **An acoustic example** — mean measured log-mel patch beside the resynthesis, plus the fitted
   pressure and tension contours, for a type near the *median* cosine (0.648), not a best case.
   **This is the biggest gap in the paper**: it contains no spectrogram of any kind. See
   finding #4.
6. **The song funnel** as a stepped bar or Sankey. Source: docs/22 §22.1–22.2.

---

## What is still missing

### The `\todo{}` markers — six, covering five distinct gaps

| # | where | what is needed |
|---|---|---|
| 1 | title block | author name, affiliation, ORCID |
| 2 | §"Where the descent starts" | **the two-start descent's result** — median gain, share improved, worst species. The gate and the run's wall-clock cost are in `pipeline/analysis/inverse_gate.md`; the result table is not. See finding #2. |
| 3 | §Limitations | **production v5's `centroidAgreement`, `centroidAgreementTieAdjusted` and `speciesAgreement`**, from the built manifest at `/tmp/birdy-prod/assets-v5`. See finding #7. |
| 4 | §Reproducibility | repository URL and an archived release DOI (Zenodo) |
| 5 | §Acknowledgements | acknowledgements and funding, or an explicit statement of none |

Numbers 2 and 3 are the only *scientific* gaps; both should be one command each.

### Things stated as unrun rather than as `\todo`

These are experiments that do not exist, not numbers that are missing, and the manuscript says
so in prose:

- A **per-syllable** comparison against Perch and BirdNET. The paper is explicit that
  "Perch is better per-recording" is the claim and "Perch is better syllable-for-syllable" is
  not, because it was never run.
- **T2**, the external novelty-AUC comparison against the critic's 0.846.
- BirdNET's **occurrence prior**, blocked on coordinates the harvester never recorded.
- Simulation-based inference and differentiable DSP for the fit (docs/23 W3).
- Weak function labels from the archives' behavioural annotations (docs/23 W4).
- The **bench re-judgment** of every cosine-gated adoption (docs/21 §21.3). Owed.

---

## Before submitting

1. **Compile it.** It has never been compiled. Fix overfull boxes, especially Table 1.
2. **Reconcile the `.bib`** against the key block at the top of `main.tex`. Check for `[?]`.
3. **Resolve or delete all six `\todo{}`s** (two of them are the same missing two-start number, in the body and in the ledger). `grep -n 'todo{' main.tex`.
4. **Decide on the `+0.488` / `+0.196` headline** (finding #6). It is measured on a store where
   the critic was read off-distribution. Re-measuring is hours and would strengthen the paper's
   central negative result considerably.
5. **Read `WHITEPAPER-FINDINGS.md`** and decide which of the 27 items change the text. Items 1,
   3, 5, 10 and 11 all touch claims that are in the manuscript.
6. **Add at least one acoustic figure** if at all possible.
7. **Check the licence line.** The manuscript states the project is non-commercial research and
   that external model weights are used offline under their own licences. Confirm that is the
   framing you want on a public preprint, and add an explicit licence for the manuscript itself
   (arXiv asks: CC BY 4.0, CC BY-SA, CC BY-NC-SA, CC0, or arXiv's non-exclusive licence).
8. **Rename check.** The manuscript uses **Lyrebird** throughout, with one footnote saying the
   repository is named `Birdy`. If the repository is going to be renamed, do it before the
   preprint cites a URL.

### Suggested arXiv categories

Primary: **`q-bio.QM`** (Quantitative Methods) — this is a measurement paper about a biological
signal, and the syrinx-model, sequence-statistics and embedding work all sit there naturally.

Cross-lists, in order of fit:

- **`cs.SD`** (Sound) — the synthesis, the descriptor, the browser DSP.
- **`eess.AS`** (Audio and Speech Processing) — the conventional companion to `cs.SD`; arXiv
  usually expects both together.
- **`q-bio.NC`** (Neurons and Cognition) — only if the gesture/premotor framing is emphasised
  more than it currently is. Optional.
- **`cs.LG`** (Machine Learning) — defensible for the critic, the batch-effect work and the
  external-model comparison, but the paper is not a methods contribution to ML. Include it only
  if you want the audience.

`nlin.CD` (Chaotic Dynamics) is where much of the Laje–Mindlin literature sits and would be a
legitimate cross-list if the appendix's bifurcation content were expanded. As written, the
oscillator is used rather than analysed, so it is a stretch.

An alternative primary is `cs.SD` with `q-bio.QM` cross-listed, if you would rather reach the
bioacoustic-ML audience first. The results most likely to be cited — the recorder confound
closed four ways, and the held-out order scaling — land in that audience.

---

## Structural notes for anyone editing it

The outline follows the owner's brief exactly:

1. **Premise** — §1
2. **Why** — §2
3. **What has already happened** — §3, a real related-work section covering physical syrinx
   models, birdsong syntax, and the foundation models (Perch, BirdNET, AVES, BirdMAE,
   NatureLM-audio), plus the borrowed methods
4. **Where we pick up** — §4, stating exactly what is taken unchanged and the three deliberate
   departures
5. **What we do differently, and where we hit limits** — §5 (the system) and §6 (five named
   walls)
6. **Our methods against each other** — §7, ten head-to-head arms with tables
7. **Our methods against other approaches** — §8, with the fairness limits stated *before* the
   numbers
8. **Findings** — §9, ten subsections, each with its ceiling attached

The honest negatives are in the narrative body where they belong, and the **complete** gate
ledger — all 58 arms including every refuted one — is Appendix A. Nothing was dropped or
softened; it was relocated so the paper has a narrative spine instead of reading as a test
report. §6, §7, §8 and §9 all carry refutations in prose; the appendix is the audit trail.

Every quantitative claim carries its internal provenance as a LaTeX comment next to it
(`% docs/22 §22.8`), never in the body text. Debug-scale numbers are marked at every
occurrence, per the project's evidence discipline.

British spelling throughout, matching the repository.
