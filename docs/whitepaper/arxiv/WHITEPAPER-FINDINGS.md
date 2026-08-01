# Findings from the whitepaper rewrite

Collected while reading `HANDOFF.md`, `AGENTS.md`, `docs/01`–`docs/23`,
`pipeline/analysis/*`, `docs/whitepaper/build_whitepaper.py` and the pipeline/app source
docstrings, in order to write `docs/whitepaper/arxiv/main.tex`.

**Nothing here was fixed.** These are things that look wrong in the code, in the numbers or
in a stated assumption. Each entry gives the location, what it claims, why that is
questionable, and how serious it is.

Severity scale: **high** = a published claim may be wrong or unsupported, or a live loose end
blocks a decision. **medium** = a reader can be misled, or a passing gate rests on something
undisclosed in the place it is quoted. **low** = documentation drift.

---

## HIGH

### 1. `source` names two different groupings, and one of them is four times worse than the other

- `docs/11-critic-47k-map-coverage.md` §11.4: "the strongest relation is `source` — recorded
  vs synthesised (**kNN 0.990** vs 0.513 for species)".
- `docs/14-xccoverbl-ingest.md` §14.4: "In the 32-d embedding, `source` kNN lift is
  **+0.488**, species +0.196".
- `docs/22-song-funnel-and-knots.md` §22.5 quotes the first; `docs/23` §23.1 and the whole
  invariance line quote the second.

Two entirely different questions share one grouping name. §11.4's `source` is
*recorded vs our own resynthesis*. §14.4's `source` is *the recording condition / recordist*.
The numbers are not comparable and neither is a substitute for the other.

Why serious: 0.990 is the number a casual reader will pick up for "the recorder confound",
because §11.4 states it in the same sentence as species lift and in the same form. It is not
that confound. It also means the phrase "source lift" in `geometry.py`'s battery output and in
the whitepaper's figure captions is ambiguous at the point of reading. Rename one of them
(`synthetic` vs `recordist`) or the ambiguity will be re-inherited by every future doc.

**Severity: high** (misreading risk on the project's single most-cited number).

### 2. The two-start descent has a pre-registered gate, a measured cost, and no recorded result

- `pipeline/analysis/inverse_gate.md`, final section "The two-start run: conditions, written
  before the result was readable (2026-08-01)". It states the arms, the selection rule, the
  harness validation against arm B (reproducing $+0.0140$ and $-0.0815$), and
  "**Cost, measured while running:** roughly 61 minutes against arm B's ~11".
- `pipeline/analysis/score_two_start.py` exists and is the scoring harness.
- `HANDOFF.md` (2026-08-01 evening) lists the two-start as "pre-registered" and no more.

The result table is missing. The run happened — its wall-clock cost was measured — and the
gate ($+0.02$ median, **no** species worse at all) is written. So either the run finished and
its numbers were not written down, or it was interrupted after the timing was read.

Why serious: this is the project's own discipline turned on itself. A gate that was registered
and run but not reported is the one failure mode the `analysis/` convention exists to prevent,
and it is the one number the manuscript could not fill (`\todo{}` in
Section~"Where the descent starts").

**Severity: high** (open loose end, and it is the last live arm on the fit roadmap).

### 3. The `>35 %` species-placement gate does not scale with the task, so it can no longer be passed or failed

- Target set in `docs/09-learned-objective-plan.md` §9.3: "nearest own **species** | 23.1 %
  (chance 4.5 %) | **> 35 %**", on a 22-species store.
- `docs/14` §14.3 measures 11.5 % at 121 species and records "**down in absolute, up over
  chance**: 8.8× → 12.8×", against the same 35 % bar.
- The production corpus has 2\,421 fitted species, i.e.\ chance ≈ 0.04 %.

An absolute-percentage bar on a retrieval task whose number of distractors grew a hundredfold
is not a gate. `docs/14` visibly notices this — it reports the ratio to chance as the real
reading — but it still records the row as a fail against the old bar, and nothing re-registers
a scaled bar.

Why serious: the placement number appears in the abstract of the old whitepaper and in the
`placement` verb's output. Every future ingest will "fail" it by construction. Either
re-register it as a ratio-to-chance or as a fixed-distractor-count retrieval, before the next
harvest.

**Severity: high** (a gate design flaw, not a measurement error).

### 4. The whole fidelity argument rests on one scalar that has been measured not to measure fidelity, and there is no acoustic example anywhere

- `docs/19-spectral-bench.md` §19.2: the 28-d cosine correlates with audible distortion at
  Pearson $+0.106$ / Spearman $+0.100$ against MCD, $n = 200$, "neither correlation is
  distinguishable from zero" and "the point estimates lean the wrong way".
- Everything gated on that cosine: respfit's 445 winners, two-voice's 2\,027, docrefit's 14 of
  15, the fricative routing, the inverse encoder's gate, `learn`'s entire gesture search.
- `docs/19` §19.3 states the consequence: "**Caveated: every cosine-gated adoption**".
- No spectrogram comparison, listening test, MOS, or rendered audio example exists in `docs/`
  or in `docs/whitepaper/`. `docs/16` §16.7 mentions "The **debug** spectrogram comparison"
  but does not include or reference an artefact.

Why serious: this is stated honestly in `docs/19` and then not acted on. The bench re-judgment
of the shipped set is "owed" in `docs/21` §21.3 and has not been run. Until it is, the claim
"the model is right and the fit is what fails" rests on a ruler that has been shown not to
rank the thing being claimed. A reviewer will ask for one spectrogram pair and there is not one
in the repository.

**Severity: high** (scientific gap, acknowledged but unclosed).

### 5. T3 — the only external gate that PASSES — depends on a threshold relaxed after the population constraint was discovered, at 0.329 coverage

- `docs/23-what-we-have-not-tried.md` §23.6.1 discovers that no species reaches
  `geometry.MIN_GROUP = 8` and that the cache holds at most two recordings per species.
- §23.6.1 then states: "`geometry.measure` allows exactly that, keeping `min_group` for callers
  testing a small population deliberately, where the permutation null rather than the group
  size is what keeps the test honest."
- §23.6.2 runs T3 at `min_group=2`, species coverage 0.834, **recordist coverage 0.329**.

The relaxation is disclosed and argued, and the permutation null is a real defence. But the
sequence is: gate written with `MIN_GROUP = 8` → population found not to support it →
threshold lowered → gate passes. That is the shape the pre-registration discipline exists to
catch, even when the reasoning is sound.

Also in the same section: T1 *passes* on this draw ($-31.4$ %) and *fails* on the draw built
for it ($-16.5$ %), and the tie-break is coverage. The tie-break rule is stated clearly and
the fail verdict is kept, which is the right call — but the two verdicts from one estimator on
one store should be flagged as a stability problem with the estimator, not only as a
population difference.

**Severity: high** (the passing external gate is the one with the weakest population).

---

## MEDIUM

### 6. A pre-registered re-measurement was never reported

`docs/16-inat-critic-naturalness.md` §16.2 states: "We re-measure the docs/14 §14.4 question
after the production build (§16.6): does the embedding still organize by recorder before bird?
The measure is **source-lift against species-lift** on the new geometry."

§16.6 does not contain it. No source-vs-species lift for the 2\,686-species critic exists
anywhere in `docs/`. The next comparable pair is `docs/23` §23.1.1's baseline (species 0.1643,
recordist 0.1665) — a different estimator, a different population (20\,000 syllables of 885
species), and blocked by recording.

Consequence for the manuscript: the paper has to quote $+0.488$ / $+0.196$ from `docs/14`, i.e.
from the *121-species store with the un-retrained 16-species critic read off-distribution*, as
its headline confound figure. That is the number the project keeps citing, and it was measured
on the worst-conditioned embedding in the record.

**Severity: medium**, rising to high if the paper ships with that number as its headline.
Re-running `critic groupings` on the production store is hours and would replace it.

### 7. `docs/20`'s own instruction was not honoured before a production build shipped

`docs/20-spacemap-agreement.md` §20.2, "Caveat recorded": "these are debug-build numbers.
Production reported 0.66 with the same structure expected. **Re-run on the production store
before any production decision.**"

Production assets v5 were built and installed (`409b4d3`) without that re-run. The manifest's
`centroidAgreement`, `centroidAgreementTieAdjusted` and `speciesAgreement` for v5 are not
quoted anywhere in `HANDOFF.md` or `docs/`, and v5 also switched clustering mode to `label`,
which `docs/22` §22.8 measures as *costing* 2.6 points of raw and 5.9 of species agreement.
So the shipped build changed the thing the caveat was about, in the direction the caveat
warned about, without the measurement.

The numbers are presumably sitting in the built manifest. The manuscript carries a `\todo{}`
for them.

**Severity: medium** (a one-command read closes it).

### 8. Perch's embedding dimensionality is stated two ways, and the discrepancy is a version conflation

- `docs/13-sources-and-complexification.md`, in a bullet headed **Perch 2.0**: "the same forward
  pass yields a 1280-d **second embedding**".
- `docs/16` §16.6, `docs/23` §23.6.1/2/3, `pipeline/src/birdy_pipeline/perch.py`: **1536-d**.

Resolved by external check: **1280 is Perch 1.0's embedding dimension and 1536 is Perch 2.0's.**
Perch 1.0 is an EfficientNet-B1 with a 1280-d embedding at 5 s / 32 kHz; Perch 2.0 is an
EfficientNet-B3 whose spatial embedding of shape (5, 3, 1536) is averaged to a 1536-d vector,
also at 5 s / 32 kHz. So `docs/13` has attached Perch 1.0's dimension to a bullet about Perch
2.0. Everything the code does is 1536, which is correct for the model it loads.

Also worth carrying: Perch 2.0's class count is **14 795** (14 597 species labels plus 198
FSD50K sound-event classes), not the "~14.6k species classes" of `docs/13` or the "14 597" of
the old whitepaper's comparison table — both of those quote one component of the total.

**Severity: medium** (a published dimension in a comparison, now explained).

### 8b. BirdNET's "320-d" in the pre-registration was a version mismatch, not an export difference

`docs/23` §23.6 states BirdNET has "a **320-d** embedding taken from the second-to-last layer,
at 3-second resolution". §23.6.3 then corrects it: "the backbone export
(`biodiversica/BirdNET-onnx-backbone`) outputs **1024-d**, not the 320-d §23.6 states".

The correction is right but the attribution is not. **320-d is BirdNET V2.2's embedding
dimension; V2.3 and V2.4 are 1024-d** (V2.1 was 420-d). All are 48 kHz / 3.0 s. So the
discrepancy is not a property of the ONNX export — it is that §23.6 was written against an
older model version's specification. Anyone re-reading §23.6.3 will conclude the export changed
the architecture, which it did not.

Shipped BirdNET is **V2.4**. Its species count is also unresolved in the wild: the official
repository README says 6 512 and the standard review table says 6 522 — `docs/23` §23.6.3
quotes **6 522** for the occurrence meta-model's output. Worth pinning against the artefact
rather than the review.

**Severity: medium** (the corrected number is right; the recorded reason for it is wrong).

### 9. `docs/16` §16.6 asserts a result its own cross-reference does not contain

§16.6: "it found the fricative gap, **fixed in §16.7 with measured wins**".

§16.7 is headed "The fricative path (**design, pre-registered**)" and contains no post-fix
numbers — only the evidence that motivated it and the gate. The actual wins (bench
$0.584 \to 0.656$, 13 wins / 0 losses) live in `HANDOFF.md` 2026-07-30 and in
`AGENTS.md`'s fricative note.

A section claiming "fixed with measured wins" and pointing at a section marked "design" is the
kind of drift that turns into an unsupported claim when someone quotes the pointer instead of
the HANDOFF.

**Severity: medium**.

### 10. The confidence-label vocabulary exists in two incompatible forms

- `docs/08-implementation.md` §8.5 (normative) and `data/inventory.json` enum:
  `experimental` | `documented` | `inferred` | `invented` | `unlabelled`.
- Root `README.md`: **playback-verified** | documented | inferred | **field recording** |
  invented.

Four of five map cleanly. The fifth does not: `unlabelled` means "real acoustics, no documented
function, and we do not know what this sound is" while "field recording" means "real audio of a
*known species*, with no documented function". Those are different claims, and the
`unlabelled` tier is specifically the one `docs/08` §8.5 protects with extra prose ("Detecting
that a sound is new is not knowing what it means").

Why serious: the honesty ladder is the project's central non-quantitative claim. If its own
five names are not stable across two files, the claim is weaker than the mechanism.

**Severity: medium**.

### 11. A shipped UI claim overstates what type retrieval supports

Root `README.md`: "the browser takes a cosine against every point each frame, so a knot lights
from the inside out and **you can see which members of a call type a sound actually
resembles**."

`docs/22` §22.8 measures type retrieval at **0.602** with every type owning a cluster — for
40 % of syllables the nearest centroid belongs to a *different type*. The per-member brightness
is a real computation, but "which members a sound actually resembles" asserts a resolution the
space does not have, and it carries no confidence label.

The same section calls 0.602 "the honest bound on 'sing and the right knot lights'". The README
sentence is a stronger claim than that bound allows.

**Severity: medium** (exactly the class of claim §8.5 exists to police).

### 12. `docs/22` §22.6 contradicts itself in place about what the default is

Within one section:

- "**Owner's call, not a default**: it gives up the rendered voice's own place on the map."
- "it ships as `--member-variants 0 --no-member-anchor` and not as a default"
- and, appended above those: "**ADOPTED as the default, 2026-08-01** … the flag inverted:
  `--member-anchor` buys the rendered voice back, `--no-member-anchor` is gone."

The adoption note was appended at the top of the sub-block and the older paragraphs were left
below it, so a linear reader reaches "not a default" *after* reading "adopted as the default",
and the flag named in the older text no longer exists.

The project's convention is to record refutations in place, which is right. This is a
*reversed decision*, not a refutation, and it needs a strike-through or a dated marker the way
`docs/10` §10.6 does it.

**Severity: medium** (a reader could ship the wrong build).

### 13. `docs/22` §22.6 also carries a stale cap regime inside a section whose numbers are current

Same section: "the cap still binds on this corpus (2 155 wanted against k = 1 024), so 1 119
types still lose their only knot in every arm".

`K_CAP` was raised 1\,024 → 8\,192 the same day (`HANDOFF.md`, and `docs/22` §22.6's own later
adoption note reports a build at k = 2\,155 with type coverage 2\,143/2\,143). The production
build ships 14\,003 clusters. So the quoted constraint no longer holds and the sentence is
inside a table's discussion that is otherwise current.

**Severity: medium** (same paragraph as live numbers).

### 14. `docs/09`'s novelty ROC of 0.825 was effectively retracted and never marked

`docs/09` §9.7 reports "**ROC AUC 0.825**" and "flags 22.1 % of genuinely unheard syllables".
`docs/10` §10.3 measures the honest version — six species held out of training entirely — at
"**AUC 0.596**, TPR 7.4 % at the 5 % operating point", and says so explicitly: "much weaker
than doc 09 §9.7's 0.825 on the 9 k store."

They are different tests (held-back syllables of training species vs whole held-out species).
`docs/09` is not marked, so it is quotable in isolation as a much better result than the
project's own honest instrument gives. The chain that follows — 0.596 → 0.672 → 0.786 → 0.846
— is the real one.

**Severity: medium**.

### 15. The mel patch is specified at one size and implemented at another

`docs/09` §9.3: "a fixed `32 × 26` grid of log-mel energies" and "**832 numbers**".
`docs/17` opening, `critic.py`, and the old whitepaper's Table 1: "**(32, 23)** log-mel patch,
**736 numbers**".

`docs/09` is a plan document and the implementation moved, which is fine — but §9.3's number is
also the basis of its storage-cost estimate ("~1.6 KB per syllable, ~65 MB for a 40 k store"),
and `docs/09` §9.8 later reports the measured figure as 58.9 MB and calls the estimate "the
§9.3 estimate was ~65 MB", i.e.\ the doc reconciles the *bytes* without correcting the
*dimensions*.

**Severity: low–medium**.

### 16. `HANDOFF.md`'s open-items list contradicts a fix recorded above it in the same file

The 2026-08-01 night entry contains, in this order: the `relations.json` fix
("760 MB -> 5.6 MB", installed, "produced by running the pipeline's own `shipped_relations`"),
and then "**Open, for whoever is next** … 3. **The pipeline's `relations.json` size** (above)
— an app guard is not a fix."

Item 3 refers to the state before the fix that is described 30 lines earlier. Likely just an
un-updated list, but `HANDOFF.md` is the file the project's own rules say to trust most for
current state.

**Severity: low–medium**.

---

## LOW

### 17. `AGENTS.md`'s parity invariant is stale

`AGENTS.md`: "**Parity:** `app/scripts/verify-parity.mjs` must stay **14/14** and
`render-syllable.mjs` 44/44".

`app/scripts/verify-parity.mjs`'s `CASES` array holds **18** entries. `docs/21` §21.1 and
`HANDOFF.md` 2026-07-30 both say 18/18. `docs/15` §1 says 14/14 and §5 says 16/16, which is the
count as fixtures were added (12 → 14 → 16 → 18).

`AGENTS.md` is dated later than `docs/21` and reports the earlier number, so an agent following
`AGENTS.md` would accept a run that silently dropped four fixtures.

**Severity: low** (but it is a stated hard constraint).

### 18. `docs/05`'s architecture is a plan, not the system, and is not marked as superseded

`docs/05-embedding-galaxy.md` §5.2 specifies "Perch embeddings → UMAP → positions". The shipped
build projects the critic's 32-d embedding with landmark cMDS and seeded $k$-means, and Perch
never touches the map (it is a metadata-only labeller). `docs/README.md` does tier docs 01–07 as
foundations, but §5.2 reads as a build spec.

**Severity: low** (a methods reader would describe the wrong system).

### 19. Root `README.md` describes a corpus three generations old

"The shipped galaxy is **31,328 points in 176 clusters**: 11,328 clips rendered from the
inventory, and 20,000 descriptors of real xeno-canto audio from 434 recordings across twelve
species." Also "One cluster per syllable type — the 44 authored ones and the 132 fitted",
"At most twenty-six tags are drawn at once", "an 8-dimensional per-point projection".

Shipped today: 348\,461 points, 14\,003 clusters, 2\,421 species, 10\,184 recordings, and a
28-slot label pool. The 26-tag figure survives as `MAX_LABELS` but the pool is
`LABEL_SLOTS = 28`.

**Severity: low** (first thing a reader sees, though).

### 20. `docs/whitepaper/figures/corpus.png` has a rendering defect

In the left panel the per-row species-count annotations are drawn on top of the store names, so
five of five row labels are illegible ("original 22-species" overprinted with "22 sp", etc.).
The figure ships in `birdy-whitepaper.pdf`. `fig_corpus` in `build_whitepaper.py` places the
annotation at a fixed x inside the label gutter.

The new manuscript does not use this figure and requests a corrected one.

**Severity: low** (cosmetic, but it is in the published PDF).

### 21. The old whitepaper's Table 5 caption cites the wrong reference numbers

`build_whitepaper.py`, Table 5 caption: "Sources for the external rows are references [42] to
[45]". In its own numbering [40]–[41] are Sainburg and Goffinet (two of the compared rows) and
[42]–[44] are Bird Sounds, Perch and BirdNET; [45] is Moummad, which is not a row.

**Severity: low**.

### 22. The fitted-species count is 2 421 in some places and 2 423 in others, and the arithmetic says 2 421

- `docs/22` §22.1 opening, `docs/23` §23.2.1/§23.2.2, `HANDOFF.md` 2026-07-31: **2 421** fitted
  species.
- `docs/16` §16.3 ("2 423 species, 12 724 types", "2 423 of 2 423 fitted species carry real
  names"), `HANDOFF.md` 2026-07-30, and `HANDOFF.md` 2026-08-01: "**2 929 410** species pairs
  = 760 MB **at 2 423 species**".

The last one is checkable. $\binom{2421}{2} = 2\,929\,410$ exactly;
$\binom{2423}{2} = 2\,933\,253$. So the relations document with 2 929 410 pairs was computed
over **2 421** species and the "2 423" in that sentence is wrong. The 2 423 in `docs/16` is
from an earlier learn (12 724 types) and is presumably correct for its own run — the count
appears to have moved 2 423 → 2 421 between learns, and the later HANDOFF entry carried the old
figure forward.

Worth resolving because both numbers are quoted as "the corpus" and the delta is used nowhere,
so it reads as a typo either way.

**Severity: low** (but it is arithmetically settled, so it is cheap to fix).

### 23. Two generations of the song-type statistic coexist without a marker

`docs/12` reports "**50 song types over 13 of 35 species**, placed 693 of 2 419 candidate
bouts" (47 k store). `docs/22` §22.2 reports 48 species / 96 types / 1\,052 bouts as the
*shipped baseline* and 98 / 356 / 3\,741 after repeat classes (production store). The old
whitepaper §6 quotes the `docs/12` figures as current in the same document that quotes
`docs/22`'s funnel.

Both are correct for their store. Neither says which store in the sentence that states the
number.

**Severity: low**.

### 24. The ABC–D compositionality result is attributed to the wrong species in two places

- `docs/07-references.md`: "Suzuki, Wheatcroft & Griesser, Nature Comms 2016 (**great tit**
  ABC-D compositionality)".
- The old whitepaper's claim-ladder figure and body: "**great tit** ABC–D".
- `docs/03-decoding-science.md` §3.2 is closer: "**Japanese great tit**".

The animal in Suzuki, Wheatcroft & Griesser (2016), *Nature Communications* 7:10986, is the
**Japanese tit, *Parus minor***. "Great tit" without qualification reads as *Parus major*, a
different species, and *Parus major* is separately present in this corpus as one of its
deepest-sampled birds — so the ambiguity is not academic here. "Japanese great tit" is a
tolerated vernacular for *P. minor* but is not the standard English name.

Worth fixing because the ABC–D result is one of only ten `experimental` (playback-verified)
entries in the whole inventory, and the citation is displayed in the interface next to the
rendered call.

**Severity: medium** (a species-level attribution error on a playback-verified claim).

### 25. `docs/17` cites a device-robustness paper as part of the bioacoustics literature

`docs/17-source-invariance.md` opening: "The literature is unambiguous that this is a
**training-time** problem (domain-invariant contrastive learning, Moummad et al. arXiv
2409.08589; impulse-response augmentation + Freq-MixStyle, Morocutti et al. arXiv 2305.07499;
corpus diversity over architecture, AVEX arXiv 2508.11845)."

arXiv:2305.07499 is Morocutti, Schmid, Koutini & Widmer, "Device-Robust Acoustic Scene
Classification via Impulse Response Augmentation", **EUSIPCO 2023**. It is **not a bioacoustics
paper** — it is acoustic scene classification, and its subject is generalisation to unseen
recording *devices*. That is a good and relevant prior for this project's problem, arguably a
better one than a bioacoustics paper would be, but the sentence presents it as evidence about
what the bioacoustics literature says. It is evidence about what the audio-ML literature says.

The two other entries in that list check out: arXiv:2409.08589 is Moummad, Serizel, Benetos &
Farrugia, "Domain-Invariant Representation Learning of Bird Sounds" (now ICASSP 2026), and
arXiv:2508.11845 is "AVEX: What Matters for Animal Vocalization Encoding" (ICLR 2026), an
empirical sweep over 26 datasets whose finding is indeed that data diversity dominates.

The manuscript reframes this correctly; `docs/17` should too, because the sentence is the
justification for a whole workstream.

**Severity: medium** (the borrowed method is sound; the claim about the literature is not).

### 26. The reference audit reclassified 59 of 104 entries — read it before quoting anything

`docs/whitepaper/references/REFERENCES.md`, produced alongside this manuscript, reports
"**101 works. 40 VERIFIED · 59 CORRECTED · 2 UNVERIFIABLE**" (the keyed entry count is 104).
Several corrections are claim-level, not bibliographic. Two of them changed sentences in this
manuscript (findings #24 and #25 above). Others flagged there and worth acting on:

- **Amador, Sanz Perl, Mindlin & Margoliash 2013** — the surname is the compound **"Sanz
  Perl"**, not "Perl". The repo writes "Perl, Y." throughout, including in `docs/21` §21.1.
- **`amador2021`'s published title contains a publisher typo**, "Iisten" with a capital I for
  "listen". It is in both the Frontiers record and Crossref, so any reference manager will
  import it. Decide deliberately whether to reproduce or silently fix.
- **`fainstein2025`'s title changed between arXiv versions.** v1 (Sep 2025) was "Birds breathe
  and sing at resonances of the biomechanics"; v2 (Dec 2025) is "Nonlinear Biomechanical
  Resonances in Birdsong". `docs/15` uses the v2 title. Still an unpublished preprint. The same
  three authors have a peer-reviewed 2025 *J. Comp. Physiol. A* paper if a published citation is
  preferred.
- **`li2004` is the wrong citation for NCD.** It defines the normalised *information* distance,
  which is uncomputable. The compressor-based estimator the project actually computes is
  Cilibrasi & Vitányi 2005. `docs/23` §23.2 and the shipped `seqstats.py` docstring both
  describe NCD without citing either.
- The audit also notes the standard Menzerath citation the field uses is **not** the macaque
  paper often reached for, which tests Zipf's law of brevity rather than Menzerath–Altmann.
  `docs/23` §23.2 cites Menzerath work only generically ("Tested in primates, whales, dolphins
  and birds") so nothing is currently mis-cited — but the specific avian result (penguins) and
  the specific primate result (geladas) should be named when this is written up.

**Severity: medium** as a class, and it is cheap to act on because the ledger states each
correction in place.

---

## Not a defect, recorded so nobody re-hunts it

- **Cluster purity 94.5 % on the production build is an identity, not a measurement**, and the
  manifest already says so in `clusterPurityNote`. It is still printed in the same block as
  real measurements, so it will be re-quoted; the note is the right mitigation and is working.
- **The 3D projection's distance faithfulness fell 0.903 → 0.747** when synthetic anchors were
  removed. `docs/22` §22.6 explains it correctly (removing rendered copies removed structure
  the projection found easy) and notes nothing about knots or matching uses those positions.
  It is a real cost of an adopted change, not an error.
- **The anchors and `centroids.json`'s 28-d `vector` are both already standardised** — checked
  in `HANDOFF.md` 2026-08-01 and recorded as *not* a space mismatch. `SessionGate`'s
  passed-in `dims` stride remains a desync hazard with both call sites currently correct.

---

## Suggested order of action

1. **#2** — read the two-start numbers out of the run's log with `score_two_start.py`, or
   re-run it. It is the last live arm and the manuscript has a `\todo{}` for it.
2. **#6** — `critic groupings` on the production store, to replace the $+0.488$ / $+0.196$
   headline with a number measured on the current critic rather than on an off-distribution
   read of a 16-species one.
3. **#7** — read v5's three agreement fields out of the built manifest; closes the second
   `\todo{}`.
4. **#1** and **#10** — two renames. Cheap, and both prevent a recurring misreading.
5. **#3** — re-register the placement gate as a ratio to chance before the next harvest.
6. **#12**, **#13**, **#17**, **#19** — documentation drift, one pass.
7. **#4** — the bench re-judgment of the cosine-gated set, and one spectrogram pair. This is
   the largest piece of work on the list and the one a reviewer will ask for first.

---

# Findings from building the figures

Appended 2026-08-01 by the agent that wrote `docs/whitepaper/arxiv/figures.py`.
Collected while joining `data/learned-inventory.json` to
`pipeline/out/harvest-gan/{typing.json,syllables.jsonl}` and the audio cache,
rendering through `birdy_pipeline.syrinx`, and re-plotting every chart in
`docs/whitepaper/build_whitepaper.py` against `docs/01`–`docs/23`.

**Nothing here was fixed.** Numbering continues from the list above.

## HIGH

### 24. The old builder's `fig_corpus` plots a "harvest-gan at 40 k" row that is a different measurement from the rows around it, and the figure never says so

`build_whitepaper.py` lines 391–397 plot five store rows with species counts
`22, 13, 121, 3 811, 3 811`. The `13` is the store-trim bug of finding #3 /
`docs/09` §9.8 — the row is a *13-species* store where chance placement is 7.7 %,
sitting between a 22-species row and a 121-species row where chance is 4.5 % and
0.8 %. In the PNG the species counts are also drawn with
`transform=a1.get_yaxis_transform()` at `x=-0.02`, which puts them on top of the
store names, so the defect is invisible *and* illegible (this is finding #20's
rendering defect, and the two compound).

The new `corpus.pdf` splits the two units into two panels and marks that row in
clay with the caveat in the caption. But the underlying issue is that **the repo
has no single place that lists the five stores with their species counts and their
chance levels together**, so any future figure will re-inherit the same trap.
`docs/14` §14.3 and `docs/09` §9.8 each hold half of it.

**Severity: high** for a published figure; the fix in the figure is done, the fix
in the docs is not.

### 25. The audio cache is 22.05 kHz mono, while the whole descriptor and fit path is specified at 48 kHz — and every spectral comparison in `docs/19` was measured against it

`pipeline/out/audio-cache/INAT*.wav` is uniformly `22050 Hz, 1 ch, PCM_16`
(checked with `soundfile.info` over the directory). `docs/08` §8.2 and
`features.SAMPLE_RATE` specify 48 kHz mono, and `render_syllable`'s default is
48 kHz.

Consequences that are not stated where the numbers are quoted:

- Nothing above **11.025 kHz** exists in the cache. The corpus holds syllables
  whose fitted contours reach 8–9 kHz, whose second and third partials are
  therefore simply absent from any cached-audio comparison.
- `docs/19`'s MCD and multi-resolution STFT distances, `docs/21`'s spectral bench,
  and the specbench fixtures are all computed against this cache. Whatever
  resampling happens on the way in is a *fixed* transformation applied to the real
  side and not to the render side, so it is a systematic asymmetry in the very
  measurement used to argue that the cosine cannot hear. It does not overturn the
  argument — a 0.1 correlation is not going to become 0.4 — but "the ruler is
  measured on half-bandwidth audio" belongs next to the ruler's numbers.
- The tonal-pin comparison of §21.2 (real spectral flatness 0.044 against ours
  0.0005) is a real-versus-render comparison across that same asymmetry.

**Severity: high**, because it is a stated-methods gap in the paper's central
negative result, and cheap to state.

### 26. Every cached member of a fitted type routinely comes from ONE recording, so the type's own within-type spread is unmeasurable from the cache

Joining `typing.json` to the cache for the three types the new
`spectral-examples.pdf` plots: `monarcha_melanopsis/L02` has 18 cached members
from **1** recording, `arundinax_aedon/L06` has 23 from **1**, and
`pellorneum_tickelli/L02` has 19 from **1**. Sampling more widely: of the 2 773
fitted types with at least 8 cached members and a fitted duration in
0.10–0.45 s, the overwhelming majority draw all of them from a single recording,
**2 573 of those 2 773 types (92.8 %) draw every cached member from
exactly one recording**, and the remaining 200 draw from two; none from three.
That follows directly from the cache holding at most two recordings per species
(`docs/23` §23.6.1).

This matters beyond the figure. `docs/22` §22.8's field-point retrieval, and any
"the type's members agree" statement, are being read on populations where "member"
and "same recording" are nearly the same predicate — which is exactly the
recordist confound of Wall 2 re-entering through the query population rather than
through the embedding. `docs/20` is careful to gate on held-out *recordings* for
the bridge; the type-level statistics are not gated the same way and it is not
recorded that they cannot be.

**Severity: high** as a scope statement on the type-level numbers.

## MEDIUM

### 27. `main.tex` is a one-column `article`, but the figure brief and the figure set are sized for two columns

`main.tex` line 36 is `\documentclass[11pt,a4paper]{article}` with
`\usepackage[margin=2.6cm]{geometry}`, so `\linewidth` is 6.22 in and there is no
second column. Every existing `\includegraphics` uses `width=\linewidth`.

`figures.py` provides the two widths the brief asked for (3.4 in and 7.0 in) and
carries font-size headroom for the resulting 0.89 scale, but the mismatch is real
and someone has to decide it: either the manuscript goes two-column (in which case
the single-column width is right and the full-width figures need `figure*`), or
the figures should be drawn at 6.22 in and 3.0 in. Drawn widths are recorded per
figure in `figures/MANIFEST.md`.

Also, and separately: `\graphicspath{{../figures/}}` points at the old PNG
directory, and the `\includegraphics` calls name `.png` explicitly, so **the
manuscript as committed will not pick up any of the new PDFs**. Two one-line edits,
listed at the top of the manifest. Not made here, because `main.tex` is another
agent's file.

**Severity: medium** — the paper does not compile against the new figures until
those two lines change.

### 28. The old `fig_spaces` figure quotes a bridge cosine of 0.962 as "the debug build", which is right, next to a 0.8 gate — but `docs/11` §11.3 reports 0.9268 for the same mechanism on the 47 k store, and the two are used interchangeably

`build_whitepaper.py` line 533 prints "The debug build passes at 0.962; the linear
ridge it replaced broke at 0.7997." Both numbers check out —
`docs/20` line 5 gives 0.962 / 0.9623 for the end-to-end debug build, and
`docs/11` line 52 gives 0.7997 for the linear map — but `docs/11` line 79's
in-build comparison is `0.7997 → 0.9268`, i.e. the RFF ridge scores 0.9268 there,
not 0.962. Three RFF numbers (0.9268, 0.962, 0.9623) exist for three different
stores and the docs do not always name which. The new `spaces-bridge.pdf` plots
0.8585 / 0.7997 / 0.9623 and names the store for each in its footnote; a reader
of `docs/11` alone would build a different bar chart from the same claim.

**Severity: medium** (a reader can quote the wrong one).

### 29. `docs/21` §21.2's clamp count is 6 617 of 12 724 types, but none of the three types the acoustic figure plots rides the clamp at all, and `clamp_incidence` disagrees with the headline on the examples

`syrinx.clamp_incidence` measured on the three pinned example types returns zero
floor and zero ceiling incidence while audible, on a 0.15–16.0 clamp. That is
consistent with 52 % of types clamping — three types are a tiny sample — but it
means the corpus-level statistic cannot be illustrated on an arbitrary type, and
`gestures.pdf` says "no clamp while audible" on all three panels. Worth checking
whether the 6 617 figure is dominated by a particular timbre class or pitch range
before it is quoted again as "over half the corpus"; `cli.py report_reachability`
logs it but the docs record no breakdown.

**Severity: medium** — the number is probably fine, its *distribution* is
undocumented, and the paper leans on it as a headline in Wall 5.

### 30. `data/learned-inventory.json` holds 13 903 syllable entries over 2 423 species, of which 13 859 carry a `resynthesisCosine` — and the manuscript quotes 13 859 types over 2 421 species

Counted directly: 2 423 species entries, 13 903 syllable entries, 13 859 with
`learned.resynthesisCosine`. The 44-entry difference is the authored inventory
(`data/inventory.json`'s hand-written syllables, which have no `learned` block and
should not be counted as fitted types). So "13 859 types" is right and "2 421
species" is right *for fitted species*, while the file's own species array is
2 423 — the 2 421 / 2 423 discrepancy of finding #22, now located: **the species
array includes species that contribute only authored syllables.** No code change
needed; the arithmetic just needs one sentence somewhere, because three plausible
counts (2 421, 2 423, 3 811) are all live in the docs.

Median resynthesis cosine over the 13 859 recomputes to **0.6477**, mean 0.597,
min $-0.4447$, max 0.9797, share above 0.7 = 40.5 %, share below 0.3 = 12.0 %.
That reproduces `docs/16` §16.3's 0.648 and the worst type's $-0.445$ exactly.

**Severity: medium** (reproduces cleanly; only the species-count provenance is
undocumented).

## LOW

### 31. The old figure set's palette contains a colour that fails the project's own accessibility bar, and the failure is load-bearing

`build_whitepaper.py`'s `VIOLET_PALE` (`#e7dff0`) and `SLATE_PALE` (`#dcdee4`) are
used as *series* fills carrying distinct meanings — for example
`fig_avex` distinguishes arms A, B and C as `SLATE_PALE / VIOLET / VIOLET_PALE`,
and `fig_map_quality`'s stack uses `VIOLET_PALE` against `SLATE_PALE` for two
adjacent segments. Run through the house data-viz validator against a white
surface, that pair measures normal-vision ΔE **2.3** against a floor of 15 (and
ΔE 1.7 under simulated protanopia), with contrast 1.35:1 and 1.30:1 against the
page — so on a greyscale print, or for a colour-blind reader, or at any
reasonable reading distance, the two arms are one colour. The new set keeps the violet/clay/slate *semantics* and
replaces the pale-against-pale distinctions with a validated
violet / moss / ochre / clay set plus a single-hue ordinal ramp for the one
part-to-whole stack.

**Severity: low** (cosmetic in effect, but it silently removed a distinction the
old figures needed).

### 32. `docs/whitepaper/figures/eq/*.png` are matplotlib mathtext renders of equations the manuscript now sets in LaTeX

`render_equations()` writes eight transparent PNGs (`syrinx`, `gamma`, `comb`,
`respiration`, `ntxent`, `rff`, `cosine`, `knnlift`). `main.tex` sets all of these
as real LaTeX. They have no consumer once the DOCX builder goes, and
`figures.py` deliberately does not reproduce them.

**Severity: low** (cleanup note).

### 33. cmr10, the only Computer Modern face matplotlib bundles, silently renders `>` as an inverted question mark

Not a repo defect, recorded because it bit this work and will bit anyone who
matches the manuscript's `lmodern` in a matplotlib figure: with
`font.serif = ['cmr10']`, a literal `>` or `<` in figure text renders as a glyph
from TeX's OT1 slot, not as a comparison operator, **with no warning**. The first
build of `tonal-pin.pdf` read "SCI ¿ 1.5". cmr10 also has no bold face and no em
dash. `figures.py` routes all comparison operators and signs through mathtext and
uses no bold anywhere; the reason is in its module docstring.

**Severity: low**, but it is a silent-corruption class of bug in any figure code
that uses this font.
