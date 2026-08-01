# Citation findings — claims this repository makes that its sources do not support

Companion to [REFERENCES.md](REFERENCES.md). Audit date 2026-08-01.

This file records places where the repository's text or code attributes something to a paper
that the paper does not say, or says differently. It does **not** record pure formatting
problems — those are in the ledger, marked `CORRECTED`.

Nothing here has been fixed in code. This is a list.

**Severity.**

| level | meaning |
|---|---|
| **HIGH** | a load-bearing claim, a wrong number that is used, or an attribution to the wrong paper. Fix before submission. |
| **MEDIUM** | a real over-reach or over-generalisation. The underlying point survives a rewording. |
| **LOW** | imprecision, missing scope caveat, or a citation that is right but incomplete in a way that could mislead. |

**Tally.** 31 findings: 13 HIGH, 13 MEDIUM, 5 LOW.

Findings 1–28 came from the repository audit. Findings 29–31 came from a second pass over
`docs/whitepaper/arxiv/main.tex`, which cites 14 works the repository itself never cited.

---

## 1. "SCI is a function of `beta` alone" is not in Sitt et al. 2008 — HIGH

**Where.**
`docs/07-references.md:52-54` · `docs/08-implementation.md:172-179` ·
`docs/21-syrinx-fidelity.md:50` and `:242` ·
`pipeline/src/birdy_pipeline/syrinx.py:844-852` (the `gamma_scale` docstring)

**Claimed.** "The spectral content index (SCI = spectral centroid ÷ f0) is a function of
`beta` alone and is invariant to `gamma`", attributed to Sitt et al. 2008 (*Phys. Rev. E*
78:011905), and in `syrinx.py` to "Sitt et al., Phys Rev E 2008; Perl et al. 2011".

**What the sources say.** Sitt et al. 2008 establishes the SNILC-vs-Hopf dichotomy — that
part is solid and is the real finding. But that paper has **no γ parameter at all**. Its
variables are `ps`, `k(x)` and `β(y)`, where `β` is a *dissipation* coefficient, not the
tension parameter of the later normal form. It reports SCI as depending on
distance-from-threshold pressure for low-f₀ sounds and on gating force for high-f₀ ones.
γ appears in this lineage only from Sitt et al. 2010 onwards. And Perl et al. 2011 Fig. 5
plots SCI as a **joint isolevel function of both α and β** at fixed γ — the opposite of
"β alone".

**Why it matters.** This is the load-bearing justification for `gammaScale`, the whole
tonal-to-rich axis of §8.1a. The *mechanism* is sound: γ is a pure time-scale, so rescaling
γ cannot change a dimensionless ratio like SCI, and holding f₀ fixed while raising γ does
force β down. That is a correct structural corollary of the normal form's construction. But
it is the project's own derivation, not a result quoted from Sitt 2008, and SCI is not a
function of β alone even in the later papers.

**Suggested wording.** "SCI is dimensionless, so it is invariant under the pure time-rescaling
γ (a corollary of the normal form of `sitt2010`); at fixed f₀, raising γ moves the operating
point toward low tension, which `sitt2008` shows is the pulse-like SNILC regime."

---

## 2. Period doubling and chaos are attributed to the wrong two papers — HIGH

**Where.**
`docs/21-syrinx-fidelity.md:158-161` · `pipeline/src/birdy_pipeline/syrinx.py:1248-1251`

**Claimed.** docs/21: "The model *contains* that middle: period-doubled and chaotic solutions
(Sitt et al. 2008; Amador & Mindlin 2008, *Chaos* 18:043123)." syrinx.py: `rough` reaches
the sound through the ODE, giving "the frequency jitter, subharmonics and — at the top of the
range — the aperiodicity that **the model's chaotic regime already contains**."

**What the sources say.** Neither Sitt et al. 2008 nor Amador & Mindlin 2008 demonstrates
period doubling. Amador & Mindlin 2008's only mention of chaotic solutions is in the
introduction, referring to *other*, higher-dimensional two-mass models. Its own model — the
one the project implements — is a **2-D autonomous flow**, which by Poincaré–Bendixson cannot
be chaotic at all. Period doubling in this lineage is demonstrated in Laje & Mindlin 2005
(where tract feedback delay makes the system effectively infinite-dimensional) and in Laje
et al. 2008 (two-source Hopf–Hopf coupling).

**Why it matters.** The project's own renderer is the 2-D flow with time-varying α and β. It
can produce aperiodicity through the *forcing* (which is what `rough` supplies) and, once a
delay-line tract or a second coupled voice is enabled, genuinely chaotic dynamics. But "the
model's chaotic regime" as an intrinsic property of the plain ODE is not a thing, and the two
papers cited do not claim it.

**Suggested wording.** Cite `laje2005` and `laje2008` for period doubling and chaos, and say
explicitly that they arise from tract feedback or two-source coupling, not from the isolated
2-D oscillator.

---

## 3. "Drives HVC neurons indistinguishably from real song" overstates Amador et al. 2013 — HIGH

**Where.**
`docs/whitepaper/build_whitepaper.py:861` and `:1521` · `docs/07-references.md:32` ("synthetic
song fools HVC neurons") · `docs/04-synthetic-bird-voices.md:52` ("enough to fool the birds'
own auditory neurons")

**Claimed.** Synthetic song from the low-dimensional model drives HVC neurons
indistinguishably from real song.

**What the source says.** The best synthetic song elicited on average **58 % ± 8 %** of the
response to real song. The paper's own word is "similar", and the model-based song without
the OEC filter component elicited no response at all. Its robust, quantified result is a
*timing* claim: HVC projection-neuron bursts and interneuron suppression occur within a few
milliseconds of the gesture-trajectory extrema, consistent with a forward-model
interpretation.

**Why it matters.** This is one of two citations the project uses to argue that the model
class is sufficient. Overstating it weakens the argument rather than strengthening it,
because `bistel2024` — which *does* report no significant difference, behaviourally — is
sitting right beside it and needs no inflation.

**Suggested wording.** "Synthetic song from the model drives HVC neurons at 58 % ± 8 % of the
response to real song, with burst timing locked to gesture-trajectory extrema."

---

## 4. `amador2021`'s title does not exist, and the noise-on-tension claim is second-hand — HIGH

**Where.**
`docs/whitepaper/build_whitepaper.py:872-873` (the fabricated title) ·
`docs/07-references.md:31` ("full syrinx ODE published") and `:68-71` ·
`docs/21-syrinx-fidelity.md:150` and `:213-214` ·
`pipeline/src/birdy_pipeline/syrinx.py:1261-1266` ·
`pipeline/src/birdy_pipeline/syrinx.py:216-219`

**Claimed.** Three separate things: (a) that the Front. Neurosci. 15:647978 article is titled
"Low-dimensional dynamics of birdsong production and imitation"; (b) that it is where "the
full syrinx ODE [is] published"; (c) that it "fitted this model to zebra finch song and
reported that matching the fundamental and the filters 'was not enough'… noise on beta was
required, and an *intermediate* amount scored best."

**What the source says.** (a) The real title is "Synthetic Birdsongs as a Tool to Induce, and
Listen to, Replay Activity in Sleeping Birds". The title the repo gives does not correspond
to this DOI. (b) Frontiers labels it a **Review**. It publishes no new ODE. (c) The
noise-on-tension result *is* discussed, and the wording the repo quotes is genuinely there —
but the figure carrying it is captioned "Adapted from Amador et al. (2013)". This paper fits
nothing; it restates 2013 data.

**Why it matters.** `rough`'s entire design — noise on tension rather than pressure or
output, with a narrow useful range and a clamp — is justified from this citation in four
places including `ROUGH_DEPTH`'s comment. The justification survives, but its source is
`amador2013`. A wrong title in an arXiv reference list is also the kind of thing a reviewer
notices immediately.

---

## 5. "Skewed, pulse-like labial waveforms" is not in Fee et al. 1998 — HIGH

**Where.**
`docs/21-syrinx-fidelity.md:148` · `docs/whitepaper/build_whitepaper.py:851-853` ·
`docs/21-syrinx-fidelity.md:241`

**Claimed.** "Real labial motion at low tension is a skewed, pulse-like waveform with rich
harmonics (Fee et al. 1998, *Nature* 395:67–71)", and in the whitepaper reference list
"measured skewed, pulse-like labial waveforms".

**What the source says.** Fee et al. 1998 is an *in vitro* excised-syrinx study plus analysis
of intact-bird song. Its finding is that the syrinx "can produce a sequence of oscillatory
states that are both spectrally and temporally complex" — it is the canonical source for
period doubling, mode locking, biphonation and chaos. It does **not** image labial motion and
does not report waveform skew. `docs/07-references.md:76-77`'s own characterisation ("period
doubling, mode locking and chaos in the excised syrinx") is the accurate one; the whitepaper's
and docs/21's is not.

**Why it matters.** The claim is used as the physical warrant for opening the pulse regime
(`gammaScale` + the `--beta-min 0.002` table). The warrant should be the nonlinear-dynamics
finding, which this paper does support, not a waveform-shape measurement it never made.

---

## 6. The beak-gape formula is reported at one frequency, not across a band — HIGH

**Where.**
`docs/07-references.md:88-90` · `docs/04-synthetic-bird-voices.md:41` ·
`docs/21-syrinx-fidelity.md:151` and `:256-258`

**Claimed.** "Beak gape does **not** shift resonances below 4 kHz — it is a high-shelf on
4–7.5 kHz, `A = −5 + 32·log(B)`", from Nelson, Beckers & Suthers 2005.

**What the source says.** The formula appears verbatim, but it is a regression reported
**only at 6.5 kHz**, one probe point in Fig. 7 — not a law across 4–7.5 kHz. `A` is amplitude
in dB, `B` is beak gape in mm over the 0–11 mm tested, and the log is base 10 (base *e* would
give a physically implausible ~72 dB swing against ~28 dB for log₁₀). The broader "high-shelf
on 4–7.5 kHz, no shift below 4 kHz" statements are supported qualitatively only.

**Why it matters.** `docs/21` §21.3 item 4 proposes shipping this as a fitted shelf. If the
formula is implemented as a 4–7.5 kHz shelf gain, the implementation is extrapolating a
single-frequency regression across a 1.9-octave band. That is a defensible modelling choice
but must be labelled as the project's own, not as the paper's.

---

## 7. Two small errors in the Riede et al. 2006 numbers — MEDIUM

**Where.**
`docs/07-references.md:93-94` · `docs/08-implementation.md:207` ·
`docs/21-syrinx-fidelity.md:81` · `pipeline/src/birdy_pipeline/syrinx.py:139` and `:870-874`

**Claimed.** (a) The OEC resonance accounts for "11–14 dB of f0-to-harmonic difference".
(b) "Cardinal tracheal resonances ≈ 2, 5, 8, 12 kHz **(1:3:5:7)**".

**What the source says.** (a) The paper states **≈ 11–15 dB**. (b) The 2/5/8/12 kHz values
are correct, but they are not a 1:3:5:7 odd-harmonic series — 1:3:5:7 of 2 kHz is
2/6/10/14 kHz. The measured series is closer to 1:2.5:4:6.

**Why it matters.** (b) is the physical justification for `tracheal_comb`, which *does*
generate a strict odd-harmonic series `f_n = (2n−1)·f₁`. The stopped-quarter-wave argument
justifies the odd series on its own; presenting the cardinal measurement as confirming
1:3:5:7 exactly overstates the agreement. `syrinx.py:135-141` gets the towhee comparison right
(2.0/5.5 measured against 1.88/5.67 predicted, which is genuinely close) — the cardinal line
should carry a similar "approximately" rather than an exact ratio.

---

## 8. The Zollinger et al. 2008 chaos percentage is wrong — HIGH

**Where.** `docs/07-references.md:78-80`

**Claimed.** "8.5 % of mockingbird syllables show nonlinear phenomena (**chaos 6.7 %**,
biphonation 4.3 %, subharmonics 1.3 %); frequency jumps 45–450 Hz."

**What the source says.** The 8.5 % total, the 4.3 % biphonation, the 1.3 % subharmonics and
the 45–450 Hz frequency-jump range are all correct and verbatim. But chaos is **8.3 %**
overall across birds, or **1.7 %** as the unilateral contributor that actually sums into the
8.5 % total (1.2 % frequency jumps + 1.3 % subharmonics + 1.7 % unilateral chaos + 4.3 %
biphonation = 8.5 %). The figure 6.7 % is **one individual bird's** rate (m130).

**Why it matters.** The four numbers are quoted as an internally consistent breakdown, and
they do not add up with 6.7 % in place of 1.7 %. Anyone checking the arithmetic will spot it.

---

## 9. "Zollinger et al., J Neurosci 30:13246 (2010)" is by Elemans, Laje, Mindlin & Goller — HIGH

**Where.** `docs/07-references.md:81`

**Claimed.** "Zollinger et al., J Neurosci 30:13246 (2010) — adult zebra finches *avoid*
subharmonics."

**What the source is.** Elemans, C. P. H., Laje, R., Mindlin, G. B. & Goller, F. (2010).
"Smooth operator: avoidance of subharmonic bifurcations through mechanical mechanisms
simplifies song motor control in adult zebra finches." *J. Neurosci.* 30(40):13246–13253.
Zollinger is not an author. Two of the actual authors are the authors of the project's own
source model.

**The claim itself is correct** — subharmonic transitions appear in developing song and in the
driven excised syrinx but are avoided in adult in-vivo song. This is a pure attribution error,
and an unfortunate one given who the real authors are.

---

## 10. The two-mass model is Ishizaka & Flanagan's lineage, not Titze's — LOW

**Where.** `docs/21-syrinx-fidelity.md:17-19`

**Claimed.** The project's model is "deliberately **not** the two-mass / mucosa-wave model
(Titze's lineage, implemented for birds by Elemans et al. 2009)".

**What is the case.** The discrete two-mass mass-spring model — Bernoulli/jet-separation
driving forces, dU/dt sound output — is the **Ishizaka & Flanagan (1972)** lineage. Elemans
et al. cite Ishizaka & Flanagan explicitly for their output convention, and `docs/15:94`
already gets this right ("Ishizaka & Flanagan convention"). Titze's own signature
contributions are the continuum body-cover / mucosal-wave models, a related but distinct
tradition. The repo conflates the two, and inside a single sentence
("two-mass / mucosa-wave") merges both families into one name.

---

## 11. A 140 Hz low-pass does not select the 80–250 Hz band — MEDIUM

**Where.**
`pipeline/src/birdy_pipeline/syrinx.py:1271-1273` · `docs/08-implementation.md:244` ·
`docs/07-references.md:73` · `pipeline/src/birdy_pipeline/syrinx.py:211-214`

**Claimed.** "ROUGH_LP_HZ sits inside the 80-250 Hz band that syringeal muscle can actually
follow (Riede & Goller); below 80 Hz the modulation would be respiratory, which is what `am`
already models."

**What Riede & Goller 2010 says.** The band split is real and correctly quoted: airflow
modulation below 80 Hz tracks air-sac pressure (respiratory), and 80–250 Hz is controlled by
syringeal gating muscles.

**The problem is the inference, not the citation.** `ROUGH_LP_HZ = 140` is the corner of a
**one-pole low-pass**, so the noise it produces has most of its energy *below* 140 Hz —
including the whole sub-80 Hz respiratory band the comment says is deliberately excluded.
A 140 Hz low-pass on white noise is not "inside the 80–250 Hz band"; it is a band from 0 to
about 140 Hz. If the intent is genuinely to place the roughness in the syringeal band, the
filter needs to be a band-pass. If the intent is the plainer one that `syrinx.py:211-213`
states — "real cycle-to-cycle irregularity in birdsong lives in the tens of Hz, and at that
rate it reads as a rough voice" — then that is a fine justification and the Riede & Goller
framing should be dropped, because the two justifications contradict each other.

**Note** that the roadmap in `docs/21:216-221` already proposes splitting `rough` into a
respiratory low band and a syringeal high band, which is the physically coherent version of
this. The current single 140 Hz low-pass sits across both.

---

## 12. `syrinx.py`'s own docstring says `rough` perturbs alpha; the code perturbs beta — HIGH

**Where.**
`pipeline/src/birdy_pipeline/syrinx.py:1247` (docstring) against `:1258-1281` (code) ·
`pipeline/src/birdy_pipeline/syrinx.py:210-211` (the `ROUGH_LP_HZ` comment)

**Claimed.** Line 1247: "`rough` perturbs **alpha** before integration". Line 210: "Pressure
perturbation is lowpassed to this before it reaches **alpha**."

**What the code does.** It multiplies **beta** (`beta = np.clip(beta * np.clip(factor, …))`),
and the comment eight lines further down says so explicitly: "Noise on the labial tension,
not on the pressure and not on the output."

**Why it matters.** This is not a formatting slip. The whole point of the citation chain
(`amador2013` via `amador2021`) is that the noise must be on **tension**, not pressure —
`docs/07:66` heads that section "Noise belongs on tension, and is required". Two comments in
the file assert the opposite of both the code and the literature. Anyone reading the docstring
to check the implementation against the paper will conclude, wrongly, that it is wrong.

---

## 13. Ohms et al. 2010 does not report a gape–f₀ correlation — HIGH

**Where.**
`docs/21-syrinx-fidelity.md:151` · `docs/21-syrinx-fidelity.md:258` ·
`docs/whitepaper/build_whitepaper.py:919-920` · `docs/07-references.md` (via docs/21)

**Claimed.** "Beak gape correlates with fundamental frequency in zebra finch song (Ohms et al.
2010, *PLoS ONE* 5:e11923)."

**What the source says.** Using playback through excised vocal tracts, the paper reports that
beak gape acts as a **passive filter emphasising frequencies at and above ~5 kHz**, while OEC
expansion shifts energy to lower frequencies and raises amplitude. It explicitly notes that
high-frequency notes are not always produced with a large gape. It is a filtering result, not
an f₀-tracking correlation.

**Why it matters.** This is one of the two citations behind the proposed dynamic-tract
extension (`docs/21` §21.3 item 4), where the fitted quantity is a shelf gain regressed
against pressure **and f₀**. The f₀ half of that regression is motivated by a correlation this
paper did not find. The gape-as-high-shelf half is supported — indeed better supported than
by Nelson 2005's single-frequency regression (finding #6). Reword to "gape emphasises
spectral energy above ~5 kHz".

---

## 14. Podos et al. 2004 is the gape–frequency paper, not the trill-rate trade-off paper — MEDIUM

**Where.**
`docs/whitepaper/build_whitepaper.py:922-924` · `docs/21-syrinx-fidelity.md:151` and `:258` ·
`docs/07-references.md` (via docs/21)

**Claimed.** "Podos, Southall & Rossi-Santos 2004, *J. Exp. Biol.* 207:607–619 — gape tracks
the **trill-rate / frequency trade-off** in Darwin's finches."

**What the source says.** This paper shows song frequency regressing positively on beak gape
(38 of 56 individuals, all 7 species) — its own title is "correlation of beak gape and song
frequency". The **trill-rate/frequency trade-off** is a different result from the same
research programme: Podos (2001), *Nature* 409:185–188.

**Fix.** Cite `podos2004` for gape–frequency and `podos2001` for the trade-off.

---

## 15. The oilbird individual-formant-signature claim belongs to a different paper — MEDIUM

**Where.** `docs/15-synth-extensions-math.md:216`

**Claimed.** "The oilbird's asymmetric bronchial semi-syrinxes make each bronchus contribute a
formant, which gives individuals unique formant signatures (Suthers & Hector 1985; …)"

**What the sources say.** Suthers & Hector 1985 (*J. Comp. Physiol. A* 156:243–266) covers
oilbird click physiology and the bilaterally asymmetric bronchial syrinx generally. The
individual-signature claim is the subject of **Suthers (1994)**, *J. Comp. Physiol. A*
175:457–466, which states that plugging either bronchus removes the corresponding formant and
that "the degree of vocal tract asymmetry varies between individuals, endowing them with
different formant frequencies." See also Suthers & Hector (1988), in *Animal Sonar*, pp.
87–91.

---

## 16. "Suthers 2013 review, Front. Physiol." is by Brinkløv, Fenton & Ratcliffe — MEDIUM

**Where.** `docs/15-synth-extensions-math.md:216`

**Claimed.** A link labelled "Suthers 2013 review, Front. Physiol." pointing at
`10.3389/fphys.2013.00123`.

**What the source is.** Brinkløv, S., Fenton, M. B. & Ratcliffe, J. M. (2013). "Echolocation
in oilbirds and swiftlets." *Frontiers in Physiology* 4:123. Suthers is not an author; his
earlier primary work is cited extensively inside the review, which is the likely source of
the mix-up. The review does cover what the repo says it covers.

---

## 17. Tumer & Brainard 2007's "~1 % f₀ CV" could not be found in the paper — HIGH

**Where.**
`docs/21-syrinx-fidelity.md:150` and `:208-209` ·
`docs/whitepaper/build_whitepaper.py:911-914`

**Claimed.** "Rendition-to-rendition fundamental-frequency CV of about 1 % in crystallised
adult Bengalese finch song (Tumer & Brainard 2007, *Nature* 450:1240–1244)."

**What the source says.** The paper is correctly identified and the species is right. Its
abstract states only that "significant trial-by-trial variation persists even in the most
practiced skills", and its subject is reinforcement-driven vocal plasticity under real-time
auditory disruption. The specific **~1 % CV figure could not be located** in any accessible
text; the full text is paywalled.

**Why it matters.** This number is the *target* for the micro-modulation extension in
`docs/21` §21.3 item 2 — a pre-registered gate will be judged against it. A pre-registered
target must be traceable. Either verify it against full text, or re-source it: Sober &
Brainard (2009), *Nature Neuroscience* 12:927–931, and Sober, Wohlgemuth & Brainard (2008),
*J. Neurosci.* 28:10370–10379, quantify baseline pitch variability directly.

---

## 18. "Chen et al., PLOS ONE 2013" appears not to exist — HIGH

**Where.**
`docs/07-references.md:74-75` · `docs/whitepaper/build_whitepaper.py:916-917` ·
`docs/08-implementation.md:243` (claim used, no citation) ·
`pipeline/src/birdy_pipeline/syrinx.py:1269` (claim used, no citation)

**Claimed.** "Chen et al., PLOS ONE 2013 — rendition-to-rendition f0 and amplitude are
near-uncorrelated (R² ≈ 0.03), so independent output jitter and shimmer would be the wrong
model."

**What was found.** No 2013 *PLOS ONE* paper by any author named Chen on this topic exists in
Crossref or Europe PMC. The figure R² ≈ 0.03 is an exact match to **Wood, Osseward, Roseberry
& Perkel (2013)**, *PLOS ONE* 8:e82327, which reports "very low rendition-to-rendition
correlation of FF and amplitude", mean R² = 0.03323 ± 0.00816. None of its four authors is
named Chen — and that paper is *already cited separately* in the same reference list
(`docs/07` and the whitepaper both list `wood2013`).

**Why it matters.** The claim is real, correctly used, and load-bearing for the design
decision that jitter must arrive through the ODE rather than as independent output modulation.
The citation is a duplicate of `wood2013` under a wrong author name. Delete the entry and
point the claim at `wood2013`.

---

## 19. Suzuki et al. 2016: reversed order gave a reduced response, not no response — MEDIUM

**Where.** `docs/03-decoding-science.md:24`

**Claimed.** "ABC = 'scan for danger', D = 'approach', ABC-D = compound; **reversed order
elicits nothing**" and ">10 note types **with referential meaning**".

**What the source says.** For the reversed D-ABC playback, tits "made fewer horizontal scans…
and only **rarely approached** the loudspeaker" — a strongly reduced response, not zero. And
the paper describes "over ten different notes" in the *repertoire*; the experiment tests four
(A, B, C, D). Attributing referential meaning to all ten over-generalises.

**Note for the manuscript.** This result has attracted published methodological criticism
(missing raw data, undeposited stimuli, possible coarticulation artefacts in the spliced
D-ABC sequences) and a deflationary "one-utterance" alternative in the formal-semantics
literature. Given that `docs/03` calls it "strongest evidence for word-order rules in birds",
one sentence of hedging is warranted.

---

## 20. "Freeberg et al. 2003" is carrying three findings from three papers — HIGH

**Where.** `docs/03-decoding-science.md:26` · `docs/07-references.md:14` ·
`docs/whitepaper/build_whitepaper.py:838-841`

**Claimed.** Attributed to Freeberg et al. 2003: black-capped chickadee chick-a-dee call has
four note types with strict A→B→C→D order; D-count scales with threat; notes carry
flock/individual identity.

**What the sources say.** The intended paper is Freeberg, Lucas & Clucas (2003), *JASA*
113:2127–2136 — and it is about the **Carolina** chickadee (*Poecile carolinensis*), not the
black-capped chickadee the repo names. Of the three claims:

- **A→B→C→D syntax, four note types** → Hailman, Ficken & Ficken (1985), *Semiotica*
  56(3–4):191–224 (black-capped chickadee).
- **D-count scaling with threat** → Templeton, Greene & Davis (2005), *Science*
  308:1934–1937 (black-capped chickadee, predator size).
- **Note identity** → this *is* Freeberg et al. 2003, but narrower than stated: single notes
  carry information predicting the **sex** of the signaller, plus significant **sex and
  microgeographic** differences. Not flock identity, and not individual identity in the usual
  sense.

**Why it matters.** `docs/03` §3.2 states that its table "*is* the language set: a curated
vocabulary of call/syllable types per species, each annotated with its documented function —
not invented meanings." A row of that table currently attributes three findings, two of them
from a different species, to one paper that makes neither. This is exactly the failure mode
the honesty rule exists to prevent.

---

## 21. "Females prefer syntactic complexity" is not in either cited paper — MEDIUM

**Where.** `docs/03-decoding-science.md:28`

**Claimed.** Bengalese finch: "Finite-state song syntax… ; **females prefer syntactic
complexity**", attributed to "Okanoya 2004; Katahira et al."

**What the sources say.** Okanoya (2004) is a review contrasting the domesticated Bengalese
finch with its wild ancestor — a domestication/relaxed-selection argument. Katahira et al.
(2011) is the HMM syntax model. Neither is a female-preference study. The preference result
comes from separate operant work from the Okanoya group, which found that preference **varies
between individual females** — roughly half preferred complex song — rather than being
uniform.

**Fix.** Either drop the sub-claim or cite the preference studies directly, with the
between-individual variability stated.

---

## 22. Lu et al. 2025 does not claim POMMs beat HMMs — MEDIUM

**Where.**
`docs/18-syntax-roadmap.md:14` · `pipeline/src/birdy_pipeline/syntax.py:7` ·
`docs/whitepaper/build_whitepaper.py:944-945`

**Claimed.** "Lu et al. 2025 show POMMs **beat** HMMs on Bengalese finch song."

**What the source says.** "For birdsong, HMMs offer **no clear advantage** over POMMs and may
be unnecessarily more complex due to the increased number of parameters required." The
argument is parsimony plus biological interpretability (POMM states map onto HVC syllable-chain
networks), not superior fit.

**Also.** The first author's initial is **J** (Jiali Lu), not K as the whitepaper has it.

**Suggested wording.** "POMMs match HMM fit with fewer parameters and a more direct mapping to
HVC circuitry."

---

## 23. Sharma et al. 2024's "156-unit alphabet" is not a number in the paper — HIGH

**Where.**
`docs/18-syntax-roadmap.md:56` · `docs/whitepaper/build_whitepaper.py:946-948`

**Claimed.** "Sperm-whale codas factorised into a combinatorial **156-unit** alphabet."

**What the source says.** The number 156 does not appear in the paper in this sense. Figure 3
documents "at least **143** combinations frequently realised", built from two
context-independent features (rhythm, tempo) and two context-sensitive ones (rubato,
ornamentation). The abstract's framing is "nearly an order of magnitude more" distinguishable
codas than the previously known ~21 discrete types.

**Why it matters.** It is a precise number used as the cross-taxon precedent for the project's
own combinatorial typing. Precise wrong numbers are the easiest thing for a reviewer to check.

---

## 24. Patel-Grosz et al. does not make the song-syntax / call-meaning claim — MEDIUM

**Where.** `docs/03-decoding-science.md:13-15`

**Claimed.** "A central ethological asymmetry (Patel-Grosz et al., 'Super Linguistics'): bird
*song* has rich syntax but weak/no referential meaning. Bird *calls* carry meaning but little
syntax."

**What the source says.** "Super Linguistics: an introduction" (*Linguistics and Philosophy*
46:627–692, 2023) is a programmatic paper arguing that formal-linguistic tools — constituency,
logical variables, semantic and pragmatic inference types — apply productively to
non-linguistic domains including pictures, visual narrative, music, dance and animal
communication. It does not assert this empirical asymmetry.

**Why it matters.** The asymmetry is the load-bearing premise for the project's whole product
framing ("the scientifically defensible product is **functional translation**"). It is a sound
synthesis of the empirical literature — `okanoya2004` for song syntax without reference,
`suzuki2016` and `griesser2008` for calls with reference — but it is the project's synthesis.
Present it as such, and cite Patel-Grosz et al. only for the methodological framing.

---

## 25. The Perch 2.0 numbers are internally inconsistent, and `docs/03` describes Perch 1.0 — HIGH

**Where.**
`docs/03-decoding-science.md:37-39` · `pipeline/src/birdy_pipeline/perch.py:58-59` and `:78` ·
`docs/whitepaper/build_whitepaper.py:933-934` and `:2596` ·
`pipeline/analysis/w6_t1_perch_recordist.py:88`

**Claimed, in four mutually inconsistent forms.** `docs/03`: "EfficientNet-**B1**, 5 s @
32 kHz → **1280-d** embedding, **14,597 species** (v2, 2025)". `perch.py:58`: the embedding
width is **1536**, and "Perch 1.0's was 1280". `perch.py:78`: "its **14 795**-class species
list". Whitepaper: "a 14 597-species bioacoustic embedding model".

**What the paper says.** Embedding width **1536**. Backbone **EfficientNet-B3**. **14 795**
output classes, of which **14 597 are species** and 198 are non-species sound events. Window
5 s at 32 kHz.

**So.** The code comments are the accurate ones. `docs/03` gives Perch **1.0's** backbone and
embedding width while labelling them v2. And `perch.py:78`'s "14 795-class **species** list"
is numerically right but mislabelled — 198 of those classes are not species, which matters for
a module whose whole job is to name a species conservatively.

---

## 26. Morocutti et al. 2023 measured device shift, not bioacoustic shift — MEDIUM

**Where.**
`pipeline/src/birdy_pipeline/critic.py:193` and `:276` · `docs/17-source-invariance.md:10`

**Claimed.** `critic.py:276` refers to "the channel-simulation half of the recipe's other arm
(**arXiv 2305.07499 measured** …)", implying the paper measured this effect in the project's
setting.

**What the source is.** "Device-robust acoustic scene classification via impulse response
augmentation" (EUSIPCO 2023). The domain is **acoustic scene classification across recording
devices** — microphone mismatch — not bioacoustics, not species classification, and not
recordist/provenance shift in wild recordings. The augmentation method transfers plausibly;
the *measurement* does not.

**Why it matters.** `docs/17` is the source-invariance work, where the whole question is
whether a nuisance factor measured in one domain carries to another. The repo should label
this as its own scope extension. `docs/17:9-11` is otherwise careful about exactly this.

---

## 27. The NBM dataset licence is CC BY-NC-ND, not CC BY — MEDIUM

**Where.** `docs/13-sources-and-complexification.md:58-61`

**Claimed.** "NBM — Nocturnal Bird Migration dataset. Zenodo 14864129 / 15655748 · … **CC-BY-4.0**,
38 h, 2,077 files, 13,359 time-frequency-boxed vocalizations from 117 Western-Palaearctic
species."

**What is the case.** The size figures and the 2026 *Scientific Data* DOI all check out. But
the live dataset — Zenodo record **15655748**, v2 — is licensed **CC BY-NC-ND 3.0**. The
CC BY 4.0 licence belongs to the *superseded* record 14864129, which is explicitly labelled
"DOUBLE BLIND REVIEW VERSION".

**Why it matters.** The project is non-commercial, so NC is fine. **ND is not**: no-derivatives
terms are in tension with an ingest pipeline that decodes, segments and re-describes. `docs/13`
proposes this as a wired `sources.py` adapter that "cut[s] labelled syllables directly". The
licence needs checking against that plan before the adapter is built, not after.

---

## 28. Four methods are used with no citation anywhere in the repository — MEDIUM

**Where.**
UMAP — `pipeline/src/birdy_pipeline/galaxy.py:25`, `:30-36`, `:344-355` ·
HDBSCAN — `pipeline/src/birdy_pipeline/density.py:11-46`,
`pipeline/src/birdy_pipeline/learn.py:1998-2030` ·
SimCLR / NT-Xent — `pipeline/src/birdy_pipeline/critic.py:139`, `:519`, `:849`, `:941` ·
random Fourier features — `docs/whitepaper/figures/eq/rff.png`

**What is missing.** These four are load-bearing methods, and `critic.py:139` even appeals to
"SimCLR's **own ablation**" as evidence for a design choice — an argument from a paper the
repository never cites. The correct citations are `umap2018` / `umapsoft2018`,
`hdbscan2013` / `hdbscansoft2017`, `simclr2020` and `rff2007`; all four are now in
`references.bib`.

**Why it matters.** For a project whose stated rule is "no claim goes beyond what the cited
source states", an argument from an uncited paper's ablation is the same category of problem as
a wrong citation.

---

---

## 29. PLDA is credited to speaker verification; the paper is face recognition — MEDIUM

**Where.** `docs/whitepaper/arxiv/main.tex:365-368`

**Claimed.** "Batch-effect correction from genomics and probabilistic linear discriminant
analysis **from speaker verification**, as post-hoc candidates for removing recording-condition
structure \citep{korsunsky2019,prince2007}."

**What the source is.** Prince & Elder (2007), "Probabilistic Linear Discriminant Analysis for
Inferences About Identity", *Proc. IEEE ICCV*, pp. 1–8 — a **computer-vision, face-recognition**
paper. PLDA was taken up by the speaker-verification community afterwards, where it became
standard on i-vectors; that adoption is a different literature.

**Why it matters.** Small, but it is the same class of error the audit found elsewhere: a method
attributed to the field the project borrowed it *from* rather than the field that produced it.
The parallel sentence gets `korsunsky2019` right ("from genomics" — Harmony is indeed a
single-cell genomics method). Either say "probabilistic linear discriminant analysis, as used in
speaker verification" and cite Prince & Elder for the method, or cite a speaker-verification
adoption paper alongside it.

---

## 30. Geladas and penguins reach Menzerath by different mechanisms — MEDIUM

**Where.** `docs/whitepaper/arxiv/main.tex:370-372` and `:1261`

**Claimed.** The two are cited as one reference shape: "The Menzerath--Altmann law as a
falsification test on a unit inventory, which has been applied to gelada and to penguin vocal
sequences \citep{gustison2016,favaro2020}", and then the project's own result is "a weak effect
in the law's direction, not the law, and **not the shape reported for geladas or penguins**".

**What the sources say.** Both do find Menzerath–Altmann, so the pairing is legitimate. But the
mechanism differs, and the difference is directly relevant to using the law as a falsification
test on a *unit inventory*:

- `gustison2016` (geladas): "most call types are **abbreviated** in larger sequences" — the
  constituents themselves shorten.
- `favaro2020` (African penguins): the negative correlation is "a consequence of **increasing the
  relative number of the shortest syllable type**, rather than reducing the duration across all
  syllable types, thus preserving the communication of size-rel[ated cues]".

**Why it matters.** These are two different generative stories. The gelada version is a
compression effect on the units; the penguin version is a shift in sequence *composition* with
unit durations preserved. A test that measures only the exponent cannot distinguish them — and
the project's own reported statistic is exactly an exponent (median $+0.019$, 45.7 % of species
negative). Naming both as "the shape" implies a single expected signature that the two papers do
not share. Worth one clause, because the project is using this as a falsification instrument,
and the instrument is less specific than the pairing suggests.

---

## 31. The lyrebird-mimicry equivalence holds only for songs presented alone — LOW

**Where.** `docs/whitepaper/arxiv/main.tex:327-330` and `:1830-1833`

**Claimed.** "Lyrebird imitations of grey shrike-thrush song elicit responses from
shrike-thrushes as strongly as conspecific song does \citep{dalziell2012}, so a mimic and its
model are a pair **certified perceptually equivalent** by the animals concerned" — and later,
"the accuracy of the imitation has been certified by the receiving birds rather than by us".

**What the source says.** Supported, with a scope condition. Grey shrike-thrushes "reacted just
as strongly towards mimetic song as to their own **when songs were presented alone**". When the
lyrebird imitations were presented embedded in the lyrebird's own characteristic song sequences,
shrike-thrushes approached the loudspeaker **less** often than when hearing either the mimicry or
the authentic model in isolation. The paper also reports that lyrebirds abbreviate model songs,
singing fewer repetitions of individual elements — a trade-off between mimetic accuracy and
vocal versatility.

**Why it matters.** For this project the isolated-song condition is the relevant one, since the
pilot compares individual syllables rather than bouts, so the claim stands as used. But
"certified perceptually equivalent" is doing a lot of work for a result with a stated
presentation-context dependency, and the abbreviation finding means mimic and model are not
identical at the sequence level. One clause — "when presented in isolation" — makes the claim
exactly as strong as the evidence.

## Two smaller notes, recorded for completeness

**"Respond to it indistinguishably from real song"** —
`docs/09-learned-objective-plan.md:308`. `bistel2024` reports **no statistically significant
difference** between responses to real and synthetic song (p > 0.05 throughout). That is not
the same as indistinguishability: a non-significant result at n = 81 synthetic protocols
bounds the effect, it does not eliminate it. Given how much weight the project puts on this
citation, "no significant difference was found" is both the accurate phrasing and the stronger
rhetorical position, because it is the phrasing that survives scrutiny. Severity **LOW**.

**Hartley & Suthers' crossover is a gap, not a threshold** —
`docs/15-synth-extensions-math.md:61` and `:69`, `docs/09-learned-objective-plan.md:269`,
`pipeline/src/birdy_pipeline/respiration.py:33`. The repo says "mini-breaths below ~30 Hz
syllable rate, pulsatile expiration above". The paper reports mini-breaths at **2–27
notes/s** and pulsatile expiration at **30–38 notes/s** — with no data between 27 and 30.
"~30 Hz" is a fair approximation; stating the two measured ranges is better, and makes clear
that the boundary is unobserved rather than measured. Severity **LOW**.

**Excess attenuation figure not isolated** — `docs/07-references.md:110-111` gives "forest
excess attenuation runs ~10 dB/100 m at 1 kHz" against a group of three habitat-acoustics
papers. Dabelsteen et al. 1993 does measure excess attenuation in blackbird song in a
deciduous forest, but the specific 10 dB/100 m figure could not be isolated in accessible
text. Either attribute it to a specific table or present it as a general figure from this
literature. Severity **LOW**.
