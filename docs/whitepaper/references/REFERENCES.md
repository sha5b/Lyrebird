# Verified reference ledger — Lyrebird whitepaper

Every work cited anywhere in this repository, checked against the primary literature.

**Audit date:** 2026-08-01. **Scope:** `docs/07-references.md`, the `REFERENCES` list inside
`docs/whitepaper/build_whitepaper.py`, `docs/01`–`docs/23`, `README.md`, `AGENTS.md`,
`HANDOFF.md`, `pipeline/README.md`, and the docstrings/comments in
`pipeline/src/birdy_pipeline/*.py`.

**Method.** Bibliographic fields were resolved against the Crossref REST API, Europe PMC,
arXiv, HAL and publisher pages. Open-access status came from Unpaywall plus direct fetch.
Claim-level checks were done against the abstract at minimum, and against full text wherever
it was legitimately reachable (the Mindlin lab's own reprint server at `lsd.df.uba.ar`, PMC,
arXiv, PLOS, Frontiers, Nature Communications, eLife).

**Status flags.**

| flag | meaning |
|---|---|
| `VERIFIED` | every bibliographic field the repo asserted is correct, and the attributed claim is supported |
| `CORRECTED` | at least one field or one attributed claim was wrong; the correction is stated in the entry |
| `NEW` | the work is not cited anywhere in the repo but should be — either because a method is used uncited, or because it is the true source of a claim currently attributed elsewhere. Bibliographic fields verified. |
| `UNVERIFIABLE` | the work could not be identified, or a load-bearing claim could not be checked |

Claim-level problems are the ones that matter. They are collected separately in
[CITATION-FINDINGS.md](CITATION-FINDINGS.md). Downloaded PDFs and the reason for every
skipped download are in [pdf/MANIFEST.md](pdf/MANIFEST.md).

**Counts.** 118 ledger entries: **44 VERIFIED · 62 CORRECTED · 11 NEW · 1 UNVERIFIABLE**.
Section 8 holds the 14 works added on 2026-08-01 for the arXiv manuscript's own citations.
A further six works appear in `references.bib` without a ledger entry of their own — five
resources listed under §7 ("Other resources cited by URL only") plus `podos2001`, which is
covered in the appendix table. **65 PDFs** held locally in `pdf/`, named `<key>.pdf`.

---

## 1. The syrinx source model — Laje & Mindlin (UBA) lineage

This is the model the project implements. It is also where the project's citations are
densest and where three claim-level errors were found.

### `gardner2001` — VERIFIED
Gardner, T., Cecchi, G., Magnasco, M., Laje, R. & Mindlin, G. B. (2001). Simple motor
gestures for birdsongs. *Physical Review Letters* **87**(20), 208101.
<https://doi.org/10.1103/PhysRevLett.87.208101>
· OA: no (subscription). Author copy: <http://lsd.df.uba.ar/papers/simplemotorgestures.pdf>
· **Used for:** the founding result that two scalar gesture curves — air-sac pressure and
labial tension — suffice to reproduce canary song. This is the justification for the
project's two-parameter gesture representation.
· Claim check: **supported**. Exactly two driving parameters (eqs. 9–10); species is canary
(*Serinus canaria*).

### `laje2002a` — VERIFIED
Laje, R., Gardner, T. J. & Mindlin, G. B. (2002). Neuromuscular control of vocalizations in
birdsong: A model. *Physical Review E* **65**(5), 051921.
<https://doi.org/10.1103/PhysRevE.65.051921>
· OA: no. Author copy: <http://lsd.df.uba.ar/papers/PRE65-2002-neuromuscular.pdf>
· **Used for:** cited in `docs/21` §21.1 as one of the two papers defining the model class.
· Claim check: fields correct. Species is rufous-collared sparrow (*Zonotrichia capensis*).
See the finding on the Takens–Bogdanov attribution under `laje2002b`.

### `laje2002b` — CORRECTED (claim)
Laje, R. & Mindlin, G. B. (2002). Diversity within a birdsong. *Physical Review Letters*
**89**(28), 288102. <https://doi.org/10.1103/PhysRevLett.89.288102>
· OA: no. Author copy: <http://lsd.df.uba.ar/papers/diversity.pdf>
· **Used for:** `docs/whitepaper/build_whitepaper.py` annotates it "the normal form Birdy
implements"; `docs/21` line 13–16 cites it for "the minimal dynamical system sitting at the
Takens–Bogdanov point".
· **Corrected:** bibliographic fields are right; the **attribution is wrong**. This paper is
a neural-circuit model of RA (Wilson–Cowan-type populations) driving the *pre-existing*
syrinx oscillator in raw physiological variables `p(t)`, `k(t)`. It contains no Hopf,
saddle-node or Takens–Bogdanov analysis and no (α, β, γ) notation. The dimensionless normal
form the project actually integrates is derived in `amador2008` and written out with the γ
time-rescaling in `sitt2010`. Cite those for the normal form.

### `mindlin2005` — VERIFIED
Mindlin, G. B. & Laje, R. (2005). *The Physics of Birdsong*. Springer, Berlin/Heidelberg
(Biological and Medical Physics, Biomedical Engineering). ISBN 978-3-540-25399-0.
<https://doi.org/10.1007/3-540-28249-1>
· OA: no. Controlled-lending scan only:
<https://archive.org/details/physicsofbirdson0000mind>
· **Used for:** the book-length account of the model class.
· Author order Mindlin-then-Laje is correct in both repo forms.

### `laje2005` — CORRECTED (title)
Laje, R. & Mindlin, G. B. (2005). **Modeling source-source and source-filter acoustic
interaction in birdsong**. *Physical Review E* **72**(3), 036218.
<https://doi.org/10.1103/PhysRevE.72.036218>
· OA: no. Author copy: <http://lsd.df.uba.ar/papers/PhysRevE.72.036218.pdf>
· **Used for:** the two-voice coupling kernel (`twovoice.py`, `docs/15` §5) and the
√ps · y tract-injection form used on the respiration path (`syrinx.py`, `docs/15` §1).
· **Corrected:** the repo title "Source–source and source–filter *coupling in birdsong
production*" is not the paper's title. Correct title above.
· Claim check: **supported at equation level**. Coupling is acoustic through the shared
tracheal pressure with no direct mechanical spring (eqs. 62–67); subharmonics can arise from
two sides sharing a trachea rather than from labial nonlinearity (Fig. 6 and the paper's own
conclusion); the low-frequency inertive limit gives s(t) ≈ √ps · y (eqs. 18–25, β ∝ v₀ =
√(2·ps·M/ρ)); Table I values α = 1.2×10⁶ cm/s, β = 1.5×10³ s⁻¹, τ = 1×10⁻⁴ s,
γ_refl = 0.9, L = 2.0 cm all appear verbatim.

### `laje2008` — CORRECTED (title supplied)
Laje, R., Sciamarella, D., Zanella, J. & Mindlin, G. B. (2008). **Bilateral source acoustic
interaction in a syrinx model of an oscine bird**. *Physical Review E* **77**(1), 011912.
<https://doi.org/10.1103/PhysRevE.77.011912>
· OA: no. Author copy: <http://lsd.df.uba.ar/papers/Bilateral%20source%20acoustic%20interaction%20in%20a%20syrinx%20model%20of%20an%20oscine%20bird.pdf>
· **Used for:** `docs/15` line 180, "follow-up applying it to an oscine".
· **Corrected:** the repo never states the title. Claim check: supported.

### `sitt2008` — CORRECTED (claim)
Sitt, J. D., Amador, A., Goller, F. & Mindlin, G. B. (2008). Dynamical origin of spectrally
rich vocalizations in birdsong. *Physical Review E* **78**(1), 011905.
<https://doi.org/10.1103/PhysRevE.78.011905>
· OA: no. Author copy: <http://lsd.df.uba.ar/papers/PRE2008-Sitt-zffinch.pdf>
· **Used for:** the load-bearing timbre claim — the SNILC-vs-Hopf dichotomy, and
"the spectral content index is a function of `beta` alone and is invariant to `gamma`"
(`docs/07` lines 50–54, `docs/08` §8.1a, `syrinx.py` `gamma_scale` docstring, `docs/21`).
· Claim check: **partially supported**. The SNILC/Hopf dichotomy — oscillations born in a
saddle-node-on-a-limit-cycle are pulse-like and harmonically dense, Hopf-born ones tonal —
**is** this paper's result. "SCI is a function of β alone and invariant to γ" is **not**.
This paper has no γ parameter at all; its variables are `ps`, `k(x)`, `β(y)` (a *dissipation*
coefficient, not the later tension parameter), and it reports SCI as depending on
distance-from-threshold pressure for low-f₀ sounds and on gating force for high-f₀ ones.
γ-invariance is a structural corollary of the normal form's construction (rescaling γ
rescales time, so it cannot change a dimensionless ratio), first available once `sitt2010`
introduces γ. And `perl2011` Fig. 5 displays SCI as a joint isolevel function of **both**
α and β — so "β alone" is not literally supported anywhere in the lineage. See
CITATION-FINDINGS #1.

### `amador2008` — CORRECTED (claim)
Amador, A. & Mindlin, G. B. (2008). Beyond harmonic sounds in a simple model for birdsong
production. *Chaos* **18**(4), 043123. <https://doi.org/10.1063/1.3041023>
· OA: no. Author copy: <http://lsd.df.uba.ar/papers/Chaos_18_043123.pdf>
· **Used for:** `docs/21` lines 158–160 cites it (with `sitt2008`) for "period-doubled and
chaotic solutions" living in the middle of the model. It is also the paper where the
Takens–Bogdanov reduction to the dimensionless normal form is actually done.
· Claim check: **not supported** for period doubling/chaos. Neither this paper nor `sitt2008`
demonstrates period doubling; the only mention of chaotic solutions is in the introduction,
referring to *other*, higher-dimensional two-mass models. The model here is a 2-D autonomous
flow, which by Poincaré–Bendixson cannot be chaotic. Period doubling in this lineage comes
from `laje2005` (tract feedback delay makes the system effectively infinite-dimensional) and
`laje2008` (two-source Hopf–Hopf coupling). See CITATION-FINDINGS #2.

### `sitt2010` — VERIFIED
Sitt, J. D., Arneodo, E. M., Goller, F. & Mindlin, G. B. (2010). Physiologically driven avian
vocal synthesizer. *Physical Review E* **81**(3), 031927.
<https://doi.org/10.1103/PhysRevE.81.031927>
· OA: no. Author copy: <http://lsd.df.uba.ar/papers/electronic_jaco.pdf>
· **Used for:** the γ-fitting method, the state-of-the-art error figures the project measures
itself against, and the fixed-resonator constants in `docs/08` and `learn.py`.
· Claim check: **supported, number for number**. γ fitted from two (f₀, SCI) points, minimum
at γ = 23 500; ⟨d_pitch⟩ = 0.152, ⟨d_SCI⟩ = 0.263 for the offline synthesis; Fig. 2 caption
reads "L = 1.9 cm, r = −0.9" exactly as `docs/08` line 477 states. This is also where the
γ-scaled normal form is written out in full.

### `perl2011` — CORRECTED (title supplied)
Perl, Y. S., Arneodo, E. M., Amador, A., Goller, F. & Mindlin, G. B. (2011).
**Reconstruction of physiological instructions from Zebra finch song**. *Physical Review E*
**84**(5), 051909. <https://doi.org/10.1103/PhysRevE.84.051909>
· OA: no. Author copy: <http://lsd.df.uba.ar/papers/PhysRevE.84.051909.pdf>
· **Used for:** the χ²(γ) fit that fixes γ = 24 000, the value the project's calibration
table is measured at (`syrinx.py` `GAMMA_REFERENCE`).
· **Corrected:** the repo omits the title entirely. Claim check: **supported verbatim** —
"we selected 28 segments of songs, from 28 different syllables from three different birds…
For γ = 24 000 we found a minimum of χ²(γ)."

### `arneodo2012` — CORRECTED (citation absent; framing overstated)
Arneodo, E. M., Perl, Y. S., Goller, F. & Mindlin, G. B. (2012). **Prosthetic avian vocal
organ controlled by a freely behaving bird based on a low dimensional model of the
biomechanical periphery**. *PLOS Computational Biology* **8**(6), e1002546.
<https://doi.org/10.1371/journal.pcbi.1002546>
· OA: yes (CC BY). PDF: <https://journals.plos.org/ploscompbiol/article/file?id=10.1371/journal.pcbi.1002546&type=printable>
· **Used for:** evidence the model runs in real time (`docs/04` line 53), and the stopped-tube
tract structure (`syrinx.py` line 182).
· **Corrected:** the repo gives no title, volume, article number or DOI anywhere. Also,
"neural prosthesis" (`docs/04`, whitepaper) overstates it — the device is driven by the
bird's own **air-sac pressure** signal, not by neural recordings. "Real-time biomechanical
prosthesis" is the accurate phrase.

### `amador2013` — CORRECTED (author list in `docs/21`; claim overstated)
Amador, A., Perl, Y. S., Mindlin, G. B. & Margoliash, D. (2013). Elemental gesture dynamics
are encoded by song premotor cortical neurons. *Nature* **495**(7439), 59–64.
<https://doi.org/10.1038/nature11967>
· OA: no at publisher; free author manuscript: <https://pmc.ncbi.nlm.nih.gov/articles/PMC3878432/>
· **Used for:** the strongest neural claim in the project — that synthetic song from this
model drives HVC neurons like real song. Also the primary source for the
noise-on-tension requirement.
· **Corrected:** `docs/21` line 24 cites it as "Mindlin & Margoliash 2013", dropping Amador
(first author) and Perl. And "indistinguishably from real song" (whitepaper) / "fools HVC
neurons" (`docs/07`) overstates it: the best synthetic song elicited **58 % ± 8 %** of the
response to real song, and the paper's own wording is "similar". Its robust result is a
timing claim about bursts near gesture-trajectory extrema. See CITATION-FINDINGS #3.

### `boari2015` — CORRECTED (end page)
Boari, S., Perl, Y. S., Amador, A., Margoliash, D. & Mindlin, G. B. (2015). Automatic
reconstruction of physiological gestures used in a model of birdsong production. *Journal of
Neurophysiology* **114**(5), 2912–**2922**. <https://doi.org/10.1152/jn.00385.2015>
· OA: free author manuscript: <https://pmc.ncbi.nlm.nih.gov/articles/PMC4737419/>
· **Used for:** the precedent for automatic gesture inversion (`learn.py` line 1474,
`docs/07` line 62).
· **Corrected:** the repo writes "114:2912" with no end page.
· Claim check: **supported**. The method really is a nearest-neighbour lookup in a
precomputed table, not an optimiser. The reference implementation the repo points to
(`github.com/kylerbrown/mindlin_auto`) exists and ships `OEC.new.dat`, a 4-column table
documented as "(-alpha), (-beta), FF, sci".

### `amador2021` — CORRECTED (title wrong; article type; attribution)
Amador, A. & Mindlin, G. B. (2021). **Synthetic birdsongs as a tool to induce, and listen to,
replay activity in sleeping birds**. *Frontiers in Neuroscience* **15**, 647978.
<https://doi.org/10.3389/fnins.2021.647978>
· OA: yes (CC BY). PDF: <https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2021.647978/pdf>
· **Used for:** the justification that `rough` must perturb tension rather than pressure or
the output, with an intermediate magnitude optimal (`docs/07` lines 68–71, `docs/21`,
`syrinx.py` line ~1262, `AGENTS.md`).
· **Corrected, three ways.** (1) The title the repo gives — "Low-dimensional dynamics of
birdsong production and imitation" — **does not exist for this DOI**. (2) Frontiers labels
this article a **Review**, so `docs/07` line 31's "full syrinx ODE published" is misleading.
(3) The noise-on-tension finding *is* discussed here, but the figure is captioned "Adapted
from Amador et al. (2013)" — the primary source is `amador2013`. `syrinx.py`'s
"(Front. Neurosci. 2021) fitted this model to zebra finch song" is therefore wrong in kind:
the species is right, but this paper fits nothing. See CITATION-FINDINGS #4.

### `bistel2024` — VERIFIED
Bistel, R., Amador, A. & Mindlin, G. B. (2024). Response of wild songbirds to songs
synthesized with a low-dimensional model. *Physical Review E* **109**(5), 054410.
<https://doi.org/10.1103/PhysRevE.109.054410>
· OA: no at publisher. Author copy: <http://www.lsd.df.uba.ar/wp-content/uploads/2024/07/wild.pdf>
· **Used for:** the single most load-bearing citation in the project — the reason it stays
procedural. `docs/07` calls it "the strongest possible realism test, and this architecture
passes it."
· Claim check: **supported, verbatim, against full text**. "In total, 26 individuals were
recorded in 15 different sites. These individuals were exposed to 256 protocols, of which 90
were carried out with real songs, 81 with synthetic songs, and 85 with heterospecific songs."
No significant difference real vs synthetic (p > α = 0.05 throughout); heterospecific song
evoked significantly lower responses. All three numbers (256/26/15) correct.

### `fainstein2025` — VERIFIED (preprint)
Fainstein, F., Goller, F. & Mindlin, G. B. (2025). Nonlinear biomechanical resonances in
birdsong. arXiv:2509.11019 [physics.bio-ph].
<https://arxiv.org/abs/2509.11019> · <https://doi.org/10.48550/arXiv.2509.11019>
· OA: yes. PDF: <https://arxiv.org/pdf/2509.11019v2>
· **Used for:** the respiratory oscillator of `respiration.py` (`docs/15` §1, `docs/09` §9.6).
· **Preprint status:** no journal version as of 2026-08-01. Note the title applies to **v2
only** — v1 was "Birds breathe and sing at resonances of the biomechanics", so citing the
version is necessary.
· Claim check: **supported**, essentially every figure verified against the v2 full text —
two first-order states; the Heaviside α(p) = αᵢ − (αᵢ − α_o)Θ(p); |EMG| through a critically
damped second-order filter with τ = 5 ms; five male canaries; bandwidth broadening
"approximately 5 (5.4 ± 1.5)"; "~94 % (94.22 ± 0.03) of theoretically maximal
magnification"; quiet breathing ≈ 2 Hz; song respiratory rates up to 15× resting;
mini-breath trills to ≈ 30 Hz; displacement 2× / pressure 15× during song. The five-parameter
count is consistent but rests on Supplemental Table S2, which could not be fetched
independently of the repo's own extraction.

### `garcia2017` — VERIFIED
Garcia, S. M., Kopuchian, C., Mindlin, G. B., Fuxjager, M. J., Tubaro, P. L. & Goller, F.
(2017). **Evolution of vocal diversity through morphological adaptation without vocal
learning or complex neural control**. *Current Biology* **27**(17), 2677–2683.e3.
<https://doi.org/10.1016/j.cub.2017.07.059>
· OA: yes via PMC: <https://pmc.ncbi.nlm.nih.gov/articles/PMC5599221/>
· **Used for:** the three-source tracheophone model of `docs/15` §3.
· Claim check: **supported**. Three sound sources confirmed verbatim ("the largest described
number of sound sources for a vocal organ"); disabling the membrana trachealis raises duty
cycle, drops amplitude and raises frequency; g1 = 5000, g2 = 4000 confirmed in STAR Methods.
The `x1 + 0.1·x2` mix is in the released code, and the code uses μ3 = 3.5 against the paper's
6.0 — a genuine paper-vs-code discrepancy that `docs/15` §3 already flags correctly.

### `amador2023` — VERIFIED
Amador, A. & Mindlin, G. B. (2023). The dynamics behind diversity in suboscine songs.
*Journal of Experimental Biology* **226**(12), jeb227975.
<https://doi.org/10.1242/jeb.227975>
· OA: bronze at publisher. Author copy:
<http://www.lsd.df.uba.ar/wp-content/uploads/2023/11/Amador-Mindlin-2023-jeb227975.pdf>
· **Used for:** comparative framing of suboscine mechanisms (`docs/15` §3).
· Claim check: **supported** — the PDF header reads "REVIEW", confirming the repo's
characterisation. The implementable equations correctly come from `garcia2017`.

### `uribarri2020` — CORRECTED (title supplied)
Uribarri, G., Rodríguez-Cajarville, M. J., Tubaro, P. L., Goller, F. & Mindlin, G. B. (2020).
**Unusual avian vocal mechanism facilitates encoding of body size**. *Physical Review
Letters* **124**(9), 098101. <https://doi.org/10.1103/PhysRevLett.124.098101>
· OA: green. Author copy: <http://lsd.df.uba.ar/papers/PhysRevLett.124.098101.pdf>
· **Used for:** the plantcutter pulse-generator model ranked first in `docs/15` §6.
· **Corrected:** the repo never gives the title.
· Claim check: **supported** — θ̇ = γ₁[μ − sin θ] verbatim; pulse rate 50–300 Hz verbatim;
(γ1, γ2, r, ωr) = (9×10³, 18.0, 0.3, 148.2), μ ≈ 1.005 verbatim from the Fig. 1 caption;
within-bird CV ≈ 6.5 % verbatim. Minor: the OEC resonance is stated as "about 4 kHz" in
prose; the repo's "3.5–4.1 kHz" is a reasonable read of Fig. 3, not a quoted range.

### `doppler2020` — CORRECTED (title supplied)
Döppler, J. F., Amador, A., Goller, F. & Mindlin, G. B. (2020). **Dynamics behind rough
sounds in the song of the *Pitangus sulphuratus***. *Physical Review E* **102**(6), 062415.
<https://doi.org/10.1103/PhysRevE.102.062415>
· OA: no at publisher. Author copy:
<http://lsd.df.uba.ar/wp-content/uploads/2021/02/con_juan_benteveo.pdf>
· **Used for:** kiskadee AM from two detuned coupled sources (`docs/15` §3).
· **Corrected:** the repo never gives the title. The "Döppler" diacritic is correct as cited.
· Claim check: **supported**.

---

## 2. Syrinx and vocal-tract biology

### `fee1998` — CORRECTED (claim misattributed in one place)
Fee, M. S., Shraiman, B., Pesaran, B. & Mitra, P. P. (1998). The role of nonlinear dynamics
of the syrinx in the vocalizations of a songbird. *Nature* **395**(6697), 67–71.
<https://doi.org/10.1038/25725>
· OA: no. No legitimate free copy located.
· **Used for:** two different claims in the repo. `docs/07` line 76 says "period doubling,
mode locking and chaos in the excised syrinx". `docs/21` line 148 and the whitepaper say
"measured skewed, pulse-like labial waveforms".
· **Corrected:** the first characterisation is supported — the paper's *in vitro* excised
zebra-finch syrinx preparation is the canonical source for period doubling, mode locking,
biphonation and chaos, and the abstract states the syrinx "can produce a sequence of
oscillatory states that are both spectrally and temporally complex". The second is **not
supported**: nothing in this paper images labial motion or reports waveform skew. That
attribution should be dropped or re-sourced. See CITATION-FINDINGS #5.

### `nowicki1987` — CORRECTED (pages)
Nowicki, S. (1987). Vocal tract resonances in oscine bird sound production: evidence from
birdsongs in a helium atmosphere. *Nature* **325**(6099), **53–55**.
<https://doi.org/10.1038/325053a0>
· OA: no.
· **Used for:** "the original proof that the filter is a filter" (`docs/07` line 100).
· **Corrected:** the repo gives the start page only ("325:53").
· Claim check: **supported** — the tract acts as an acoustic filter whose characteristics are
actively coordinated with the syrinx; harmonics apparent in heliox are suppressed in air
regardless of absolute frequency.

### `beckers2003` — CORRECTED (volume/pages supplied)
Beckers, G. J. L., Suthers, R. A. & ten Cate, C. (2003). Pure-tone birdsong by resonance
filtering of harmonic overtones. *PNAS* **100**(12), **7372–7376**.
<https://doi.org/10.1073/pnas.1232227100>
· OA: yes via PMC: <https://pmc.ncbi.nlm.nih.gov/articles/PMC165882/>
· **Used for:** "the tract is not cosmetic" (`docs/08` line 124, `docs/04` line 22).
· **Corrected:** the repo gives neither volume nor pages. Note the species are **doves**
(*Streptopelia risoria*, *S. decaocto*), not passerines — worth stating when the citation is
used to argue about songbird tracts.
· Claim check: **supported**.

### `beckers2004` — CORRECTED (title supplied)
Beckers, G. J. L., Nelson, B. S. & Suthers, R. A. (2004). **Vocal-tract filtering by lingual
articulation in a parrot**. *Current Biology* **14**(17), 1592–1597.
<https://doi.org/10.1016/j.cub.2004.08.057>
· OA: no. Paywalled, not downloaded.
· **Used for:** the parrot lingual-formant mapping of `docs/15` §4 and the "biological
licence for a tongue gesture" in `docs/04` line 45.
· Claim check: **supported, all four numbers**. 5 monk parakeets (*Myiopsitta monachus*),
syrinx replaced by a broadband speaker, 4 formants between 0.5 and 10 kHz, tongue movement
changing the frequency of 2 of the 4 and the amplitude of all 4.

### `nelson2005` — CORRECTED (formula scope)
Nelson, B. S., Beckers, G. J. L. & Suthers, R. A. (2005). Vocal tract filtering and sound
radiation in a songbird. *Journal of Experimental Biology* **208**(2), 297–308.
<https://doi.org/10.1242/jeb.01378>
· OA: bronze (free at publisher after embargo); automated fetch blocked.
<https://journals.biologists.com/jeb/article/208/2/297/15809/>
· **Used for:** the eastern-towhee tracheal measurement that justifies the stopped-tube comb,
and the beak-gape shelf `A = −5 + 32·log(B)` used in `docs/07`, `docs/21` and planned for the
dynamic-tract extension.
· Claim check: **partially supported.** Sweep range 0.5–11.0 kHz, species eastern towhee
(*Pipilo erythrophthalmus*), and resonances ~2.0/~5.5 kHz against 1.88/5.67 kHz predicted for
a 45 mm stopped tube are all verbatim. The formula `A = −5 + 32·log(B)` is verbatim **but is
reported only at 6.5 kHz**, a single probe point, not as a law across 4–7.5 kHz. `A` is
amplitude in dB, `B` is beak gape in mm (0–11 mm tested), and the log is base 10. Presenting
it as a general 4–7.5 kHz high-shelf over-extends the source. See CITATION-FINDINGS #6.

### `riede2006` — CORRECTED (dB range; ratio label)
Riede, T., Suthers, R. A., Fletcher, N. H. & Blevins, W. E. (2006). Songbirds tune their
vocal tract to the fundamental frequency of their song. *PNAS* **103**(14), 5543–5548.
<https://doi.org/10.1073/pnas.0601262103>
· OA: yes via PMC: <https://pmc.ncbi.nlm.nih.gov/articles/PMC1459391/>
· **Used for:** the reason the f₀-tracking band is kept (`docs/08` §8.1a), the OEC Q ≈ 30 that
sets `TRACHEA_Q`'s comparison point, and the cardinal resonance series in `syrinx.py`.
· Claim check: **supported with two corrections.** Species northern cardinal, OEC volume
2.0 → 0.6 ml, f₀ 1.5 → 5 kHz and modelled Q ≈ 30 are all confirmed. The f₀-to-harmonic
difference is **≈ 11–15 dB**, not the repo's "11–14 dB". And 2/5/8/12 kHz is not literally a
1:3:5:7 odd-harmonic series (1:3:5:7 of 2 kHz is 2/6/10/14) — the "1:3:5:7" label in
`docs/07`, `docs/08` and `syrinx.py` line 139 is an interpretive gloss, not the paper's ratio.
See CITATION-FINDINGS #7.

### `riede2009` — CORRECTED (title supplied)
Riede, T. & Suthers, R. A. (2009). **Vocal tract motor patterns and resonance during constant
frequency song: the white-throated sparrow**. *Journal of Comparative Physiology A*
**195**(2), 183–192. <https://doi.org/10.1007/s00359-008-0397-0>
· OA: free author manuscript: <https://pmc.ncbi.nlm.nih.gov/articles/PMC2826496/>
· **Used for:** the trachea-length sanity range and the 20 dB figure that keeps
`TRACHEAL_GAIN` small (`syrinx.py` lines 140–147).
· **Corrected:** the repo omits the title.
· Claim check: **supported** — trachea 3.4 cm dissected / 3.8 cm from cast, first tracheal
resonance ≈ 2.2 kHz sitting ≈ 20 dB below the moving OEC peak, second ≈ 6.6 kHz.

### `fletcher2006` — CORRECTED (title, end page, DOI supplied)
Fletcher, N. H., Riede, T. & Suthers, R. A. (2006). **Model for vocalization by a bird with
distensible vocal cavity and open beak**. *Journal of the Acoustical Society of America*
**119**(2), 1005–**1011**. <https://doi.org/10.1121/1.2159434>
· OA: no. Paywalled, not downloaded.
· **Used for:** grouped with `riede2006` in `docs/07` line 98; `syrinx.py` line 150 credits
"Fletcher; Riede et al. 2006" for the modelled OEC Q ≈ 30.
· **Corrected:** the repo gives only "JASA 119:1005 (2006)".
· Claim check: **could not fully check** — the abstract does not itself state a numeric Q.
The Q ≈ 30 value is confirmed in `riede2006`, so attribute it there.

### `kazemi2023` — CORRECTED (author list)
Kazemi, A., Kesba, M. & Provini, P. (2023). Realistic three-dimensional avian vocal tract
model demonstrates how shape affects sound filtering (*Passer domesticus*). *Journal of the
Royal Society Interface* **20**(198), 20220728.
<https://doi.org/10.1098/rsif.2022.0728>
· OA: yes (CC BY). PDF: <https://pmc.ncbi.nlm.nih.gov/articles/PMC9874979/>
· **Used for:** `docs/07` line 98, "FEM of a real house sparrow tract".
· **Corrected:** the repo writes "**Kazemi, Riede et al.**" — **Riede is not an author.**
Species (house sparrow) and the finite-element characterisation are correct.

### `suthers1990` — VERIFIED
Suthers, R. A. (1990). Contributions to birdsong from the left and right sides of the intact
syrinx. *Nature* **347**(6292), 473–477. <https://doi.org/10.1038/347473a0>
· OA: no.
· **Used for:** the two-independent-sides basis for `twovoice.py` (`docs/21` §21.3 item 5).
· Claim check: supported. Species brown thrasher and gray catbird.

### `goller1996a` — CORRECTED (split from a merged entry; title supplied)
Goller, F. & Suthers, R. A. (1996). **Role of syringeal muscles in gating airflow and sound
production in singing brown thrashers**. *Journal of Neurophysiology* **75**(2), 867–876.
<https://doi.org/10.1152/jn.1996.75.2.867>
· OA: no. Paywalled, not downloaded.
· **Used for:** independent control of the two syringeal sides (`docs/21` line 273).
· **Corrected:** the repo merges two distinct papers into one entry with no titles.
This one is about per-side airflow gating.

### `goller1996b` — CORRECTED (split from a merged entry; title supplied)
Goller, F. & Suthers, R. A. (1996). **Role of syringeal muscles in controlling the phonology
of bird song**. *Journal of Neurophysiology* **76**(1), 287–300.
<https://doi.org/10.1152/jn.1996.76.1.287>
· OA: no. Paywalled, not downloaded.
· **Used for:** as above.
· Claim check: **supported** — m. syringealis ventralis EMG "increases exponentially with the
fundamental frequency of the ipsilaterally generated sound", and birds switch sound
production between sides. Together with `goller1996a` this carries the repo's claim; cite
both, not a merged entry.

### `zollinger2008` — CORRECTED (one percentage wrong)
Zollinger, S. A., Riede, T. & Suthers, R. A. (2008). Two-voice complexity from a single side
of the syrinx in northern mockingbird *Mimus polyglottos* vocalizations. *Journal of
Experimental Biology* **211**(12), 1978–1991. <https://doi.org/10.1242/jeb.014092>
· OA: bronze (free at publisher); automated fetch blocked.
<https://journals.biologists.com/jeb/article/211/12/1978/17631>
· **Used for:** the prevalence of nonlinear phenomena in real song, which is why the project
fits nonlinearity per syllable instead of enabling it globally (`docs/07` lines 78–82).
· **Corrected:** the repo's two descriptions are two summaries of **one** paper, not a
conflict. But `docs/07`'s breakdown has an error: total unilateral NLP 8.5 % is correct
(1.2 % frequency jumps + 1.3 % subharmonics + 1.7 % unilateral chaos + 4.3 % biphonation),
subharmonics 1.3 % and biphonation 4.3 % are correct, and the frequency-jump range
"45–450 Hz" is verbatim — but **"chaos 6.7 %" is wrong**. Chaos is 8.3 % overall across
birds, or 1.7 % as the unilateral contributor inside the 8.5 % total; 6.7 % is one
individual bird's rate. Also the repo cites the start page only. See CITATION-FINDINGS #8.

### `elemans2010` — CORRECTED (**wrong first author in the repo**)
Elemans, C. P. H., Laje, R., Mindlin, G. B. & Goller, F. (2010). Smooth operator: avoidance
of subharmonic bifurcations through mechanical mechanisms simplifies song motor control in
adult zebra finches. *Journal of Neuroscience* **30**(40), 13246–13253.
<https://doi.org/10.1523/JNEUROSCI.1130-10.2010>
· OA: free via PMC: <https://pmc.ncbi.nlm.nih.gov/articles/PMC3487382/>
· **Used for:** `docs/07` line 81 — the counterexample that adult zebra finches *avoid*
subharmonics, hence "nonlinearity must be fitted per syllable, never enabled globally".
· **Corrected:** the repo cites this as "**Zollinger et al.**, J Neurosci 30:13246 (2010)".
The authors are Elemans, Laje, Mindlin & Goller — two of them the authors of the project's
own source model. The claim itself is supported. See CITATION-FINDINGS #9.

### `elemans2008` — VERIFIED
Elemans, C. P. H., Mead, A. F., Rome, L. C. & Goller, F. (2008). Superfast vocal muscles
control song production in songbirds. *PLOS ONE* **3**(7), e2581.
<https://doi.org/10.1371/journal.pone.0002581>
· OA: yes (CC BY). PDF: <https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0002581&type=printable>
· **Used for:** the measured headroom for tremor — syringeal muscles work up to 250 Hz
(`docs/21` line 211).
· Claim check: **supported** verbatim ("positive work and power at cycle frequencies up to
250 Hz"). Species European starling and zebra finch.

### `elemans2008dove` — CORRECTED (**year, volume and pages all wrong in the repo**)
Elemans, C. P. H., Zaccarelli, R. & Herzel, H. (**2008**). Biomechanics and control of
vocalization in a non-songbird. *Journal of the Royal Society Interface* **5**(24),
**691–703**. <https://doi.org/10.1098/rsif.2007.1237>
· OA: free via PMC: <https://pmc.ncbi.nlm.nih.gov/articles/PMC2607454/>
· **Used for:** the dove/pigeon two-mass membrane model of `docs/15` §2, planned as
`dove.py`.
· **Corrected:** the repo cites "**Elemans et al. 2009 … J. R. Soc. Interface 6:491–506**"
(`docs/15` §2 header, `docs/13` line 234, whitepaper, `docs/21` line 18). Year, volume and
page range are all wrong. The PMC ID the repo links (PMC2607454) is correct and does point at
this paper, so the content extraction is sound.
· Claim check: **supported on every checked point** — two-mass model with three massless
plates; output = flow derivative dU/dt in the Ishizaka & Flanagan convention; m1 = m2 =
1.7×10⁻³ g, k1 = k2 = 22.0×10⁻³ g/ms², kc = 6.0×10⁻³ g/ms², a01 = a02 = 0.3 mm²;
F₀ = (1/2π)√(k/m) = 572.6 Hz ≈ 573 Hz; Q ∈ [0.8, 1.2] → 458–688 Hz; max air-sac pressure
3.5 kPa; and the paper's own caveat that "independent control of amplitude and frequency
seems not to be possible with the simple syringeal morphology of the ring dove."
· Note: `docs/21` line 18 calls the two-mass model "Titze's lineage". It is properly the
**Ishizaka & Flanagan (1972)** lineage — see `ishizaka1972` and CITATION-FINDINGS #10.

### `riedegoller2010` — CORRECTED (year and subtitle missing)
Riede, T. & Goller, F. (**2010**). Peripheral mechanisms for vocal production in birds –
**differences and similarities to human speech and singing**. *Brain and Language*
**115**(1), 69–80. <https://doi.org/10.1016/j.bandl.2009.11.003>
· OA: free author manuscript: <https://pmc.ncbi.nlm.nih.gov/articles/PMC2896990/>
· **Used for:** the frequency split that sets `ROUGH_LP_HZ = 140` (`docs/07` line 73,
`syrinx.py` line 1272).
· **Corrected:** `docs/07` line 73 gives neither year nor the subtitle.
· Claim check: **supported**, though not in the abstract — the body text states "Modulations
of airflow at frequencies below 80 Hz are correlated with air sac pressure modulations…
Modulations at higher frequencies (80–250 Hz) are controlled by the faster syringeal gating
muscles." But see CITATION-FINDINGS #11 for how the project reasons from this to a 140 Hz
**low-pass**.

### `hartley1989` — CORRECTED (title supplied; threshold imprecise)
Hartley, R. S. & Suthers, R. A. (1989). **Airflow and pressure during canary song: direct
evidence for mini-breaths**. *Journal of Comparative Physiology A* **165**(1), 15–26.
<https://doi.org/10.1007/BF00613795>
· OA: no. Paywalled, not downloaded.
· **Used for:** the mini-breath/pulsatile regime split that sets the 12 ms interior-silence
rule in `respiration.py` (line 33) and the "~30 Hz" crossover in `docs/15` §1 and `docs/09`.
· **Corrected:** the repo omits the title. Species is canary.
· Claim check: **supported, with a more precise number available.** The paper reports
mini-breaths for syllable repetition rates of 2–27 notes/s and pulsatile expiration for
30–38 notes/s — a gap, not a single threshold. "~30 Hz" is a defensible approximation;
"mini-breaths below ≈27/s, pulsatile above ≈30/s" is what the source actually says.

### `larsen1999` — CORRECTED (title supplied); claim partly unverified
Larsen, O. N. & Goller, F. (1999). **Role of syringeal vibrations in bird vocalizations**.
*Proceedings of the Royal Society B* **266**(1429), 1609–1615.
<https://doi.org/10.1098/rspb.1999.0822>
· OA: green in principle (PMC1690181) but full text could not be retrieved through any
available route. Not downloaded.
· **Used for:** the single-LTM-pair parrot source of `docs/15` §4.
· **Corrected:** the repo omits the title, and lists only "cockatiels (and hill myna)" —
the abstract also covers pigeons.
· Claim check: **partially supported.** The abstract confirms the core mechanism (vibration
frequency and amplitude "highly similar to" the emitted sound; first direct evidence for a
vibratory sound-generating mechanism). The narrower claim that "cockatiels show a continuum
from harmonic-rich to tonal *without* altered vibratory behaviour" is a Results-level detail
that could not be confirmed — which `docs/15` line 220 already discloses honestly.

### `ohms2010` — CORRECTED (**claim not supported as stated**)
Ohms, V. R., Snelderwaard, P. Ch., ten Cate, C. & Beckers, G. J. L. (2010). **Vocal tract
articulation in zebra finches**. *PLOS ONE* **5**(7), e11923.
<https://doi.org/10.1371/journal.pone.0011923>
· OA: yes (CC BY). PDF: <https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0011923&type=printable>
· **Used for:** `docs/07`, `docs/21` line 151 and the whitepaper all state "beak gape
correlates with fundamental frequency in zebra finch song", used to motivate the planned
dynamic-tract shelf.
· **Corrected:** the repo omits the title and the author list. More seriously, the claim is
**not what the paper found**. Using playback through excised tracts, it reports that beak
gape acts as a **passive filter emphasising frequencies ≥ 5 kHz**, while OEC expansion shifts
energy lower and raises amplitude. The paper explicitly notes high-frequency notes are not
always produced with a large gape. The correct gloss is "gape emphasises ≥ 5 kHz spectral
energy", not "gape correlates with f₀". See CITATION-FINDINGS #12.

### `ohms2012` — VERIFIED
Ohms, V. R., Beckers, G. J. L., ten Cate, C. & Suthers, R. A. (2012). Vocal tract
articulation revisited: the case of the monk parakeet. *Journal of Experimental Biology*
**215**(1), 85–92. <https://doi.org/10.1242/jeb.064717>
· OA: yes (free at publisher); automated fetch blocked.
<https://journals.biologists.com/jeb/article/215/1/85/10797>
· **Used for:** the parrot articulation numbers of `docs/15` §4 and the tract-length
modulation idea in `docs/21` §21.3 item 7.
· Claim check: **supported, every number verbatim** — tongue depresses 2.9–4.3 mm at call
onset; beak opens 5.6–6.7 mm (contact) / 3.0–4.8 mm (greeting); trachea shortens 9–44 %;
trachea 55 mm / 65 mm giving predicted stopped-tube resonances 1570 / 1330 Hz; "tongue back
→ F3 rises, F1 slightly falls" (this paper's own summary of `beckers2004`); no OEC inflation
in monk parakeets.

### `podos2004` — CORRECTED (claim conflates two findings)
Podos, J., Southall, J. A. & Rossi-Santos, M. R. (2004). **Vocal mechanics in Darwin's
finches: correlation of beak gape and song frequency**. *Journal of Experimental Biology*
**207**(4), 607–619. <https://doi.org/10.1242/jeb.00770>
· OA: no. Paywalled, not downloaded.
· **Used for:** `docs/07`, `docs/21` line 151 — "gape tracks the trill-rate / frequency
trade-off in Darwin's finches".
· **Corrected:** the repo omits the title. And the claim conflates two results: this paper
shows song frequency regressing positively on beak gape (38/56 individuals, all 7 species).
The **trill-rate/frequency trade-off** is a different result, from Podos (2001), *Nature*
409:185–188. Cite the right one for the right claim. See CITATION-FINDINGS #13.

### `ballintijn1998` — VERIFIED
Ballintijn, M. R. & ten Cate, C. (1998). Sound production in the collared dove: a test of
the 'whistle' hypothesis. *Journal of Experimental Biology* **201**(10), 1637–1649.
<https://doi.org/10.1242/jeb.201.10.1637>
· OA: bronze (free at publisher); automated fetch blocked.
· **Used for:** the heliox test that kills the whistle hypothesis for doves (`docs/15` §2).
· Claim check: **supported** — fundamental of unmodulated coo elements unchanged in heliox;
FM-element modulation frequency rose with helium concentration, saturating at 1.5× the base
frequency; a half-frequency band appeared in some individuals. Species collared dove
(*Streptopelia decaocto*).

### `riede2004` — VERIFIED
Riede, T., Beckers, G. J. L., Blevins, W. & Suthers, R. A. (2004). **Inflation of the
esophagus and vocal tract filtering in ring doves**. *Journal of Experimental Biology*
**207**(23), 4025–4036. <https://doi.org/10.1242/jeb.01256>
· OA: no. Paywalled, not downloaded.
· **Used for:** "doves coo with beak/nares closed into an inflating esophageal crop"
(`docs/15` line 123).
· Claim check: **supported**. The repo's short form "Riede et al. 2004, JEB 207:4025" is
correct as far as it goes; full citation above.

### `warren1996` — CORRECTED (one sub-claim unsupported)
Warren, D. K., Patterson, D. K. & Pepperberg, I. M. (1996). Mechanisms of American English
vowel production in a grey parrot (*Psittacus erithacus*). *The Auk* **113**(1), 41–58.
<https://doi.org/10.2307/4088934>
· OA: no. Paywalled, not downloaded. (The journal was renamed *Ornithology* in 2021; "The
Auk" is the correct historical name for a 1996 article.)
· **Used for:** African grey speech mimicry in `docs/15` line 172 — "/a/ = trachea protracted
+ beak closed. /i/ = the opposite. Front-back tongue position is the mimicked-vowel axis."
· Claim check: **partially supported.** The trachea/beak half is confirmed. The
**"front-back tongue position is the mimicked-vowel axis" half is not**: `ohms2012`, which
reviews this study, states that in Warren et al.'s X-ray videos "the tongue is not visible
and therefore likely rests low within the oral cavity" — tongue position was not measurable.
See CITATION-FINDINGS #14.

### `fletcher1988` — VERIFIED
Fletcher, N. H. (1988). Bird song — a quantitative acoustic model. *Journal of Theoretical
Biology* **135**(4), 455–481. <https://doi.org/10.1016/S0022-5193(88)80270-4>
· OA: no at publisher. Author copy:
<https://www.phys.unsw.edu.au/music/people/publications/Fletcher1988.pdf>
· **Used for:** `twovoice.py` line 45 — "Fletcher 1988's [verdict]" that coupling arises only
because tracheal pressure acts on both membranes.
· Claim check: consistent with the paper's model. `docs/15` line 194 cites it correctly.

### `fletcher1999` — VERIFIED
Fletcher, N. H. & Tarnopolsky, A. (1999). Acoustics of the avian vocal tract. *Journal of the
Acoustical Society of America* **105**(1), 35–49. <https://doi.org/10.1121/1.424620>
· OA: bronze. Author copy:
<https://www.phys.unsw.edu.au/music/people/publications/Fletcheretal1999a.pdf>
· **Used for:** `docs/15` §6 item 2, the oilbird/swiftlet formant discussion.
· Note: the author-copy filename says "etal" but the paper has exactly two authors.

### `suthers1985` — CORRECTED (**wrong paper for the attributed claim**)
Suthers, R. A. & Hector, D. H. (1985). The physiology of vocalization by the echolocating
oilbird, *Steatornis caripensis*. *Journal of Comparative Physiology A* **156**(2), 243–266.
<https://doi.org/10.1007/BF00610867>
· OA: no. Paywalled, not downloaded.
· **Used for:** `docs/15` §6 item 2 — "the oilbird's asymmetric bronchial semi-syrinxes make
each bronchus contribute a formant, which gives individuals unique formant signatures".
· **Corrected:** this paper covers oilbird click physiology and the asymmetric bronchial
syrinx generally. The **individual formant-signature** claim belongs to `suthers1994`.
See CITATION-FINDINGS #15.

### `suthers1994` — NEW (the correct source for the individual-signature claim)
Suthers, R. A. (1994). Variable asymmetry and resonance in the avian vocal tract: a
structural basis for individually distinct vocalizations. *Journal of Comparative Physiology
A* **175**(4), 457–466. <https://doi.org/10.1007/BF00199253>
· OA: no. Paywalled, not downloaded.
· **Used for:** should replace `suthers1985` for the individual-formant-signature claim. The
paper states that oilbird social vocalisations concentrate energy into three formants from
the asymmetric bronchial syrinx, that plugging either bronchus removes the corresponding
formant, and that "the degree of vocal tract asymmetry varies between individuals, endowing
them with different formant frequencies."
· Related: Suthers, R. A. & Hector, D. H. (1988). Individual variation in vocal tract
resonance may assist oilbirds in recognizing echoes of their own sonar clicks. In *Animal
Sonar*, pp. 87–91. <https://doi.org/10.1007/978-1-4684-7493-0_9>

### `brinklov2013` — CORRECTED (**wrong author in the repo**)
Brinkløv, S., Fenton, M. B. & Ratcliffe, J. M. (2013). Echolocation in oilbirds and
swiftlets. *Frontiers in Physiology* **4**, 123.
<https://doi.org/10.3389/fphys.2013.00123>
· OA: yes (CC BY). PDF: <https://www.frontiersin.org/articles/10.3389/fphys.2013.00123/pdf>
· **Used for:** `docs/15` §6 item 2, cited there as "**Suthers 2013 review**, Front. Physiol."
· **Corrected:** Suthers is not an author. His earlier primary work is cited extensively
inside the review, which is the likely source of the mix-up. Rename the key.
See CITATION-FINDINGS #16.

### `clark2015` — VERIFIED
Clark, C. J. & Prum, R. O. (2015). Aeroelastic flutter of feathers, flight, and the evolution
of nonvocal communication in birds. *Journal of Experimental Biology* **218**(21),
3520–3527. <https://doi.org/10.1242/jeb.126458>
· OA: bronze (free at publisher); automated fetch blocked.
· **Used for:** `docs/15` §6 item 3, the aeroelastic-flutter sonation class.
· Note: the published title uses "nonvocal", not the repo's "non-vocal".

### `bostwick2009` — VERIFIED
Bostwick, K. S., Elias, D. O., Mason, A. & Montealegre-Z, F. (2009). Resonating feathers
produce courtship song. *Proceedings of the Royal Society B* **277**(1683), 835–841.
<https://doi.org/10.1098/rspb.2009.1576>
· OA: green via PMC: <https://pmc.ncbi.nlm.nih.gov/articles/PMC2842718/>
· **Used for:** `docs/15` §6 item 3, club-winged manakin resonant stridulation.
· Note: published online 2009, issue dated 2010 — "2009" as the repo has it is defensible;
state both if precision matters.

### `ishizaka1972` — NEW (the correct lineage attribution)
Ishizaka, K. & Flanagan, J. L. (1972). Synthesis of voiced sounds from a two-mass model of
the vocal cords. *Bell System Technical Journal* **51**(6), 1233–1268.
<https://doi.org/10.1002/j.1538-7305.1972.tb02651.x>
· OA: no. Paywalled, not downloaded.
· **Used for:** `docs/15` line 94 already credits the "Ishizaka & Flanagan convention" for
the dU/dt sound output correctly. This entry supplies the citation, and is the paper
`docs/21` line 18 should point at instead of "Titze's lineage".

---

## 3. Song variability and micro-modulation

### `tumer2007` — CORRECTED (title supplied); key number unverified
Tumer, E. C. & Brainard, M. S. (2007). **Performance variability enables adaptive plasticity
of 'crystallized' adult birdsong**. *Nature* **450**(7173), 1240–1244.
<https://doi.org/10.1038/nature06390>
· OA: no. Paywalled, not downloaded.
· **Used for:** the "~1 % rendition-to-rendition f₀ CV" figure that the project's
micro-modulation extension is targeted at (`docs/07` line 74 region, `docs/21` lines 150
and 208, whitepaper).
· **Corrected:** the repo omits the title. The paper is correctly identified and the
species (Bengalese finch) is right.
· Claim check: **could not verify the number.** The abstract states only that "significant
trial-by-trial variation persists even in the most practiced skills" and frames variability
as adaptive motor exploration. No "~1 % CV" figure appears in the accessible text; the
paper's subject is reinforcement-driven vocal plasticity under real-time auditory
disruption. If the 1 % figure is load-bearing, verify it against full text or re-source it
(Sober & Brainard 2009, *Nature Neuroscience* 12:927–931, and Sober, Wohlgemuth & Brainard
2008, *J. Neurosci.* 28:10370–10379, both quantify baseline pitch variability directly).
See CITATION-FINDINGS #17.

### `wood2013` — CORRECTED (authors and species)
Wood, W. E., Osseward, P. J. II, Roseberry, T. K. & Perkel, D. J. (2013). **A daily
oscillation in the fundamental frequency and amplitude of harmonic syllables of zebra finch
song**. *PLOS ONE* **8**(12), e82327. <https://doi.org/10.1371/journal.pone.0082327>
· OA: yes (CC BY). PDF: <https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0082327&type=printable>
· **Used for:** slow within-day drift of f₀ and amplitude (`docs/07`, `docs/21` line 150).
**And** — see next entry — this is the true source of the R² ≈ 0.03 figure.
· **Corrected:** the repo gives "Wood, W. E. et al." with no title. Species is zebra finch.
· Claim check: **supported**, and the paper explicitly reports "very low rendition-to-rendition
correlation of FF and amplitude", mean R² = 0.03323 ± 0.00816.

### `chen2013` — UNVERIFIABLE (**this citation appears not to exist**)
Cited in `docs/07` line 74 and the whitepaper as "Chen, R. et al. *PLOS ONE*, 2013 —
rendition-to-rendition f₀ and amplitude near-uncorrelated, R² ≈ 0.03". Also used without
attribution in `syrinx.py` line ~1268.
· No 2013 *PLOS ONE* paper by any author named Chen on this topic could be found via
Crossref or Europe PMC. The R² ≈ 0.03 figure is an exact match to `wood2013`
(mean R² = 0.03323 ± 0.00816), whose four authors include no Chen.
· **Recommendation: delete this entry and attribute the claim to `wood2013`.** The
underlying claim is real and correctly used; only the citation is phantom.
See CITATION-FINDINGS #18.

---

## 4. Syntax, semantics and sequence models

### `rutz2023` — CORRECTED (authors, volume, pages, article type)
Rutz, C., Bronstein, M., Raskin, A., Vernes, S. C., Zacarian, K. & Blasi, D. E. (2023).
Using machine learning to decode animal communication. *Science* **381**(6654), 152–155.
<https://doi.org/10.1126/science.adg7314>
· OA: no. Paywalled, not downloaded.
· **Used for:** the project's central honesty framing (`docs/03` §3.1, `README.md` line 16,
`docs/01`, `docs/08` line 683) — that ML can characterise repertoires and functionally decode
but cannot translate into propositional human language.
· **Corrected:** the repo says only "Rutz, C. et al." with no volume or pages, and does not
say it is a **Perspective**, not a research article. Both matter for an arXiv reference list.
· Claim check: **partially supported.** The characterise/functionally-decode framing and the
role of playback experiments are consistent with the paper. The specific wording "playback
experiments… exist for only a handful of systems" could not be confirmed from accessible
text.

### `suzuki2016` — CORRECTED (**claim overstated**)
Suzuki, T. N., Wheatcroft, D. & Griesser, M. (2016). Experimental evidence for compositional
syntax in bird calls. *Nature Communications* **7**, 10986.
<https://doi.org/10.1038/ncomms10986>
· OA: yes (CC BY). PDF: <https://www.nature.com/articles/ncomms10986.pdf>
· **Used for:** the great tit ABC-D construction, the project's strongest word-order example
(`docs/03` line 24, `docs/07` line 12, whitepaper).
· **Corrected:** volume and article number missing in the repo. Two claim problems:
(1) "reversed order elicits **nothing**" is wrong — the paper reports tits "made fewer
horizontal scans… and only rarely approached the loudspeaker" for D-ABC, i.e. a strongly
**reduced** response, not zero. (2) "> 10 note types **with referential meaning**"
over-generalises: the paper describes "over ten different notes" in the repertoire but the
experiment tests only A, B, C and D. See CITATION-FINDINGS #19.
· Note for the manuscript: this result has attracted published methodological criticism and a
deflationary "one-utterance" alternative account in the formal-semantics literature. Worth a
sentence if the claim is load-bearing.

### `griesser2008` — CORRECTED (volume/pages supplied)
Griesser, M. (2008). Referential calls signal predator behavior in a group-living bird
species. *Current Biology* **18**(1), 69–73.
<https://doi.org/10.1016/j.cub.2007.11.069>
· OA: no. Paywalled, not downloaded.
· **Used for:** Siberian jay referential alarms (`docs/03` line 25, `docs/07` line 13).
· Claim check: **supported** — alarm calls vary with hawk *behaviour* (perched, searching,
attacking) and elicit distinct escape responses. Do not confuse with Griesser (2009),
*Proc. R. Soc. B* 276:2887–2892, which is about predator *category*.

### `freeberg2003` — CORRECTED (**three-way misattribution**)
Freeberg, T. M., Lucas, J. R. & Clucas, B. (2003). Variation in chick-a-dee calls of a
Carolina chickadee population, *Poecile carolinensis*: identity and redundancy within note
types. *Journal of the Acoustical Society of America* **113**(4), 2127–2136.
<https://doi.org/10.1121/1.1559175>
· OA: no. Paywalled, not downloaded.
· **Used for:** `docs/03` line 26 and `docs/07` line 14 attribute three findings to
"Freeberg et al. 2003": four note types with strict A→B→C→D order; D-count scaling with
threat; and notes carrying flock/individual identity.
· **Corrected:** the repo gives no journal, volume or title, **and only the third claim
belongs to this paper** — and in a narrower form (sex identity and microgeographic
differences, in the **Carolina** chickadee, not the black-capped chickadee the repo names).
The other two belong to `hailman1985` and `templeton2005`. See CITATION-FINDINGS #20.

### `hailman1985` — NEW (correct source for the A→B→C→D syntax)
Hailman, J. P., Ficken, M. S. & Ficken, R. W. (1985). The 'chick-a-dee' calls of *Parus
atricapillus*: a recombinant system of animal communication compared with written English.
*Semiotica* **56**(3–4), 191–224. <https://doi.org/10.1515/semi.1985.56.3-4.191>
· OA: no. Paywalled, not downloaded.
· **Used for:** should carry the "four note types, strict A→B→C→D order" claim in `docs/03`
and `docs/07`. Species is black-capped chickadee.
· Companion: Hailman, Ficken & Ficken (1987), *Ethology* **75**(1), 62–80,
<https://doi.org/10.1111/j.1439-0310.1987.tb00642.x>.

### `templeton2005` — NEW (correct source for D-count scaling with threat)
Templeton, C. N., Greene, E. & Davis, K. (2005). Allometry of alarm calls: black-capped
chickadees encode information about predator size. *Science* **308**(5730), 1934–1937.
<https://doi.org/10.1126/science.1108841>
· OA: no. Paywalled, not downloaded.
· **Used for:** should carry the "D-count scales with threat" claim in `docs/03` and
`docs/07`, currently attributed to Freeberg.

### `hultsch1989` — CORRECTED (replaces an unusable citation)
Hultsch, H. & Todt, D. (1989). Memorization and reproduction of songs in nightingales
(*Luscinia megarhynchos*): evidence for package formation. *Journal of Comparative Physiology
A* **165**(2), 197–203. <https://doi.org/10.1007/BF00619194>
· OA: no. Paywalled, not downloaded.
· **Used for:** nightingale song-type count and package organisation (`docs/03` line 27,
whitepaper).
· **Corrected:** the repo cites "Hultsch, H. & Todt, D." with **no year, no title and no
journal** — unusable in a reference list. This is the paper for package formation
(packages of 3–5, max 7 song types).

### `hultsch1981` — NEW (correct source for countersinging rules)
Hultsch, H. & Todt, D. (1981). Repertoire sharing and song-post distance in nightingales
(*Luscinia megarhynchos* B.). *Behavioral Ecology and Sociobiology* **8**(3), 183–188.
<https://doi.org/10.1007/BF00299828>
· OA: no. Paywalled, not downloaded.
· **Used for:** should carry the countersinging/matching-rule half of the repo's
Hultsch & Todt claim. See also Hultsch, Kipper, Mundry & Todt (2004), *Behaviour*
**141**(3), 371–390, <https://doi.org/10.1163/156853904322981914>.

### `jackel2022` — CORRECTED (spelling)
Jäckel, D., Mortega, K. G., Brockmeyer, U., Lehmann, G. U. C. & Voigt-Heucke, S. L. (2022).
Unravelling the stability of nightingale song over time and space using open, citizen science
and shared data. *Frontiers in Ecology and Evolution* **10**, 778610.
<https://doi.org/10.3389/fevo.2022.778610>
· OA: yes (CC BY). PDF: <https://www.frontiersin.org/articles/10.3389/fevo.2022.778610/pdf>
· **Used for:** `docs/03` line 27, beside Hultsch & Todt.
· **Corrected:** the repo gives no title, journal or volume. The umlaut in "Jäckel" is
correct as written.

### `okanoya2004` — CORRECTED (full citation supplied)
Okanoya, K. (2004). The Bengalese finch: a window on the behavioral neurobiology of birdsong
syntax. *Annals of the New York Academy of Sciences* **1016**, 724–735.
<https://doi.org/10.1196/annals.1298.026>
· OA: no. Paywalled, not downloaded.
· **Used for:** Bengalese finch finite-state syntax (`docs/03` line 28, `docs/07`,
whitepaper).
· **Corrected:** the repo gives "Okanoya, K., 2004" with nothing else. Note this is a review
contrasting the domesticated Bengalese finch with its wild ancestor, not a syntax-model
paper — the finite-state model is `katahira2011`.

### `katahira2011` — CORRECTED (full citation supplied)
Katahira, K., Suzuki, K., Okanoya, K. & Okada, M. (2011). Complex sequencing rules of
birdsong can be explained by simple hidden Markov processes. *PLOS ONE* **6**(9), e24516.
<https://doi.org/10.1371/journal.pone.0024516>
· OA: yes (CC BY). PDF: <https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0024516&type=printable>
· **Used for:** cited only as "Katahira, K. et al." in `docs/03` and the whitepaper.
· **Corrected:** full citation supplied. Do not confuse with `jin2011` — the two were posted
to arXiv the same week on closely related problems and are frequently conflated.
· Note: `docs/03` line 28's "females prefer syntactic complexity" is supported by neither
`okanoya2004` nor this paper. It traces to separate operant-preference work from the Okanoya
group, which found preference varies *between individual females* rather than being uniform.
See CITATION-FINDINGS #21.

### `elie2018` — CORRECTED (volume/article supplied)
Elie, J. E. & Theunissen, F. E. (2018). Zebra finches identify individuals using vocal
signatures unique to each call type. *Nature Communications* **9**, 4026.
<https://doi.org/10.1038/s41467-018-06394-9>
· OA: yes (CC BY). PDF: <https://www.nature.com/articles/s41467-018-06394-9.pdf>
· **Used for:** `docs/03` line 29, individual recognition as the zebra finch's main
"semantic" layer.
· **Corrected:** the repo gives "Elie & Theunissen 2018" only. A published Author Correction
exists (2020, PMC7272431).

### `tu2011` — CORRECTED (full citation supplied)
Tu, H.-W., Osmanski, M. S. & Dooling, R. J. (2011). Learned vocalizations in budgerigars
(*Melopsittacus undulatus*): the relationship between contact calls and warble song.
*Journal of the Acoustical Society of America* **129**(4), 2289–2297.
<https://doi.org/10.1121/1.3557035>
· OA: hybrid. Author copy: <http://doolinglab.umd.edu/publications/2011/tu_JASA.pdf>
· **Used for:** `docs/03` line 30, budgerigar warble syntax and "two phonological systems".
· **Corrected:** the repo gives "Tu et al. 2011" only. Claim check: supported.

### `jin2011` — CORRECTED (published version missing)
Jin, D. Z. & Kozhevnikov, A. A. (2011). A compact statistical model of the song syntax in
Bengalese finch. *PLOS Computational Biology* **7**(3), e1001108.
<https://doi.org/10.1371/journal.pcbi.1001108> · preprint arXiv:1011.2998 (2010).
· OA: yes (CC BY). PDF: <https://journals.plos.org/ploscompbiol/article/file?id=10.1371/journal.pcbi.1001108&type=printable>
· **Used for:** the reason `syntax.py` goes beyond first-order Markov (`syntax.py` line 5,
`docs/18` line 14, whitepaper).
· **Corrected:** `syntax.py` cites the arXiv preprint only. Cite the published version, or
both. Claim check: **supported** — the paper's partially observable Markov model with
adaptation makes self-transition probabilities depend on repeat count.

### `lu2025` — CORRECTED (**claim overstated**)
Lu, J., Surendralal, S., Bouchard, K. E. & Jin, D. Z. (2025). Partially observable Markov
models inferred using statistical tests reveal context-dependent syllable transitions in
Bengalese finch songs. *Journal of Neuroscience* **45**(9), e0522242024.
<https://doi.org/10.1523/JNEUROSCI.0522-24.2024>
· OA: free via PMC: <https://pmc.ncbi.nlm.nih.gov/articles/PMC11866996/>
· **Used for:** `syntax.py` line 7, `docs/18` line 14 and the whitepaper all say POMMs
"**beat**" plain HMMs on Bengalese finch song.
· **Corrected:** the repo gives "Lu, K. et al., 2025" — the first author's initial is **J**,
not K, and the full citation was missing. And the claim overstates the paper, which says
"HMMs offer no clear advantage over POMMs and may be unnecessarily more complex due to the
increased number of parameters required." The argued advantage is parsimony and biological
interpretability, not a categorical win on fit. See CITATION-FINDINGS #22.

### `sharma2024` — CORRECTED (**wrong number**)
Sharma, P., Gero, S., Payne, R., Gruber, D. F., Rus, D., Torralba, A. & Andreas, J. (2024).
Contextual and combinatorial structure in sperm whale vocalisations. *Nature Communications*
**15**, 3617. <https://doi.org/10.1038/s41467-024-47221-8>
· OA: yes (CC BY). PDF: <https://www.nature.com/articles/s41467-024-47221-8.pdf>
· **Used for:** `docs/18` line 57 and the whitepaper — "sperm-whale codas factorised into a
combinatorial **156-unit** alphabet", the cross-taxon precedent for the project's
combinatorial typing.
· **Corrected:** the number **156 does not appear in the paper**. Figure 3 documents "at
least **143** combinations frequently realised", and the abstract's framing is "nearly an
order of magnitude more" distinguishable codas than the previously known ~21 types.
See CITATION-FINDINGS #23.

### `patelgrosz2023` — CORRECTED (attribution loose)
Patel-Grosz, P., Mascarenhas, S., Chemla, E. & Schlenker, P. (2023). Super Linguistics: an
introduction. *Linguistics and Philosophy* **46**(4), 627–692.
<https://doi.org/10.1007/s10988-022-09377-8>
· OA: hybrid. Author copy: <https://hal.science/hal-04573423>
· **Used for:** `docs/03` line 13 attributes to it "bird *song* has rich syntax but weak/no
referential meaning. Bird *calls* carry meaning but little syntax."
· **Corrected:** the repo gives no year, title, journal or volume. And the paper does not
make this claim: it is a programmatic argument that formal-linguistic tools apply to
non-linguistic domains (pictures, music, dance, animal communication). The song/call
asymmetry is the project's own synthesis of the empirical literature. Either present it that
way, citing `okanoya2004`/`suzuki2016` for the two halves, or drop the attribution.
See CITATION-FINDINGS #24.

### `finchgpt2025` — VERIFIED (preprint)
Kobayashi, K., Matsuzaki, K., Taniguchi, M., Sakaguchi, K., Inui, K. & Abe, K. (2025).
FinchGPT: a Transformer based language model for birdsong analysis. arXiv:2502.00344.
<https://arxiv.org/abs/2502.00344>
· OA: yes (CC BY-NC-ND 4.0). PDF: <https://arxiv.org/pdf/2502.00344>
· **Used for:** `docs/04` line 83, `docs/13` line 267, `docs/07` line 118 — the template for
a sequence model over syllable-type strings.
· **Preprint only** as of 2026-08-01; cite as such. "FinchGPT" is the authors' own name.

---

## 5. Embeddings, learned scoring and corpora

### `sainburg2020` — VERIFIED
Sainburg, T., Thielk, M. & Gentner, T. Q. (2020). Finding, visualizing, and quantifying
latent structure across diverse animal vocal repertoires. *PLOS Computational Biology*
**16**(10), e1008228. <https://doi.org/10.1371/journal.pcbi.1008228>
· OA: yes (CC BY). PDF: <https://journals.plos.org/ploscompbiol/article/file?id=10.1371/journal.pcbi.1008228&type=printable>
· **Used for:** the closest published precedent for the galaxy — latent projections of animal
vocal repertoires (`docs/01`, `docs/05`, `docs/07`).
· Claim check: supported; the paper explicitly prefers UMAP over t-SNE for global structure.

### `goffinet2021` — VERIFIED
Goffinet, J., Brudner, S., Mooney, R. & Pearson, J. (2021). Low-dimensional learned feature
spaces quantify individual and group differences in vocal repertoires. *eLife* **10**,
e67855. <https://doi.org/10.7554/eLife.67855>
· OA: yes (CC BY). PDF: <https://cdn.elifesciences.org/articles/67855/elife-67855-v2.pdf>
· **Used for:** the VAE+UMAP precedent (`docs/01` line 27, `docs/07` line 22).
· Claim check: supported. Code: `github.com/pearsonlab/autoencoded-vocal-analysis`.

### `perch2` — CORRECTED (**three numbers and the backbone wrong**)
van Merriënboer, B., Dumoulin, V., Hamer, J., Harrell, L., Burns, A. & Denton, T. (2025).
Perch 2.0: the bittern lesson for bioacoustics. arXiv:2508.04665.
<https://arxiv.org/abs/2508.04665>
· OA: yes. PDF: <https://arxiv.org/pdf/2508.04665>. Code Apache 2.0,
`github.com/google-research/perch`.
· **Used for:** the second-opinion pseudo-labeller of `perch.py` (`docs/13` §A1).
· **Corrected.** From the paper: embedding width **1536** (not 1280 — that was Perch 1.0);
backbone **EfficientNet-B3** (not B1 — that was Perch 1.0); **14 795 output classes**, of
which **14 597 are species** and 198 are non-species sound events; window 5 s at 32 kHz
(correct in the repo). So `docs/03` lines 37–39 mixes Perch 1.0 and 2.0 specs, and
`perch.py` line 78's "14 795-class **species** list" is numerically right but mislabelled.
See CITATION-FINDINGS #25. No peer-reviewed version as of 2026-08-01.

### `birdnet2021` — VERIFIED (licence needs splitting)
Kahl, S., Wood, C. M., Eibl, M. & Klinck, H. (2021). BirdNET: a deep learning solution for
avian diversity monitoring. *Ecological Informatics* **61**, 101236.
<https://doi.org/10.1016/j.ecoinf.2021.101236>
· OA: hybrid; no confirmed free PDF.
· **Used for:** the non-commercial constraint that shapes the project's model choices
(`docs/03`, `docs/07`, `AGENTS.md`).
· The technical figures (3 s at 48 kHz, 1024-d embedding, 6 522 classes) check out against
BirdNET-Analyzer v2.4. But the repo's blanket "CC BY-NC-SA" applies to the **model weights**;
the **BirdNET-Analyzer code is MIT**. Split the two when the licence claim is load-bearing.

### `aves2022` — VERIFIED
Hagiwara, M. (2023). AVES: Animal vocalization encoder based on self-supervision. In
*ICASSP 2023*. Preprint arXiv:2210.14493 (2022).
<https://arxiv.org/abs/2210.14493>
· OA: yes. PDF: <https://arxiv.org/pdf/2210.14493>
· **Used for:** `docs/03` line 44, `docs/07` line 9.
· The repo's "MIT" licence claim for the code is probably right but was not hard-verified.

### `birdmae2025` — VERIFIED (published version supplied)
Rauch, L., Heinrich, R., Moummad, I., Joly, A., Sick, B. & Scholz, C. (2025). Can masked
autoencoders also listen to birds? *Transactions on Machine Learning Research*, 08/2025.
Preprint arXiv:2504.12880. <https://arxiv.org/abs/2504.12880>
· OA: yes. PDF: <https://arxiv.org/pdf/2504.12880>
· **Used for:** `docs/03` line 45, "BirdMAE (SOTA on BirdSet)" — which is the paper's own
claim. The model's own name is "Bird-MAE".

### `avex2025` — CORRECTED (software and paper are the same project)
Miron, M., Robinson, D., Alizadeh, M., Gilsenan-McMahon, E., Narula, G., Chemla, E.,
Cusimano, M., Effenberger, F., Hagiwara, M., Hoffman, B., Keen, S., Kim, D., Lawton, J.,
Liu, J.-Y., Raskin, A., Pietquin, O. & Geist, M. (2025). AVEX: what matters for animal
vocalization encoding. arXiv:2508.11845; accepted at ICLR 2026.
<https://arxiv.org/abs/2508.11845> · <https://openreview.net/forum?id=MFuM9KAEYc>
· OA: yes. PDF: <https://arxiv.org/pdf/2508.11845>. Code MIT, `github.com/earthspecies/avex`.
· **Used for:** the "corpus diversity over architecture" result behind `critic.py`'s arm-C
recipe (`docs/17` §17.4), and separately as a software package in `docs/03` and `docs/07`.
· **Corrected:** the repo treats these as two unrelated things. They are one project — the
package is the paper's code release. Merge the entries. Claim check: **supported** — the
paper's central finding is that a diverse mixed pretraining corpus dominates architecture
choice. Note earlier arXiv revisions carry the working title "What Matters for Bioacoustic
Encoding".

### `naturelm2024` — VERIFIED
Robinson, D., Miron, M., Hagiwara, M., Weck, B., Keen, S., Alizadeh, M., Narula, G.,
Geist, M. & Pietquin, O. (2024). NatureLM-audio: an audio-language foundation model for
bioacoustics. arXiv:2411.07186; ICLR 2025.
<https://arxiv.org/abs/2411.07186>
· OA: yes. PDF: <https://arxiv.org/pdf/2411.07186>
· **Used for:** `docs/03` line 47, `docs/07` line 11.
· ICLR 2025 acceptance is corroborated by the Earth Species Project publications page; the
arXiv metadata itself does not state it.

### `birdset2024` — VERIFIED
Rauch, L., Schwinger, R., Wirth, M., Heinrich, R., Huseljic, D., Herde, M., Lange, J.,
Kahl, S., Sick, B., Tomforde, S. & Scholz, C. (2024). BirdSet: a large-scale dataset for
audio classification in avian bioacoustics. arXiv:2403.10380; ICLR 2025.
<https://arxiv.org/abs/2403.10380>
· OA: yes. PDF: <https://arxiv.org/pdf/2403.10380>
· **Used for:** `docs/03` line 75, `docs/07` line 16, `docs/13`.
· Note: later mirrors carry a retitled variant ("…a multi-task benchmark for classification
in avian bioacoustics") — check which arXiv version you cite.

### `moummad2024` — CORRECTED (title was a paraphrase)
Moummad, I., Serizel, R., Benetos, E. & Farrugia, N. (2024). **Domain-invariant
representation learning of bird sounds**. arXiv:2409.08589.
<https://arxiv.org/abs/2409.08589>
· OA: yes. PDF: <https://arxiv.org/pdf/2409.08589>
· **Used for:** the domain-invariant contrastive recipe of `critic.py` (`docs/17` line 9).
· **Corrected:** the repo's title "Domain-invariant contrastive learning for bioacoustics"
is a paraphrase, not the paper's title. Preprint only as of 2026-08-01 despite a long
revision history. The method is ProtoCLR, a prototype-based contrastive loss.

### `morocutti2023` — CORRECTED (title was a paraphrase; domain scope)
Morocutti, T., Schmid, F., Koutini, K. & Widmer, G. (2023). **Device-robust acoustic scene
classification via impulse response augmentation**. In *Proc. 31st European Signal Processing
Conference (EUSIPCO 2023)*. Preprint arXiv:2305.07499.
<https://arxiv.org/abs/2305.07499>
· OA: yes. PDF: <https://arxiv.org/pdf/2305.07499>
· **Used for:** the impulse-response augmentation implemented in `critic.py` lines 193 and
276 (`docs/17` line 10).
· **Corrected:** the repo's title is a paraphrase. More importantly, the paper's domain is
**acoustic scene classification across recording devices**, not bioacoustics. `critic.py`
line 276's "arXiv 2305.07499 measured [the channel-simulation half]" reads as if the paper
measured this in a bioacoustic setting. It did not. Label the transfer as the project's own
scope extension. See CITATION-FINDINGS #26.

### `denton2021` — CORRECTED (year)
Denton, T., Wisdom, S. & Hershey, J. R. (**2021**). Improving bird classification with
unsupervised sound separation. arXiv:2110.03209.
<https://arxiv.org/abs/2110.03209>
· OA: yes. PDF: <https://arxiv.org/pdf/2110.03209>
· **Used for:** `docs/13` line 170.
· **Corrected:** the arXiv posting is October **2021**, not 2022.

### `inatsounds2024` — CORRECTED (title)
Chasmai, M., Shepard, A., Maji, S. & Van Horn, G. (2024). **The iNaturalist Sounds Dataset**.
In *Advances in Neural Information Processing Systems 37 (NeurIPS 2024), Datasets and
Benchmarks Track*. Preprint arXiv:2506.00343 (posted 2025).
<https://arxiv.org/abs/2506.00343> · <https://neurips.cc/virtual/2024/poster/97701>
· OA: yes. PDF: <https://arxiv.org/pdf/2506.00343>
· **Used for:** the top-ranked new source in `docs/13` §1.
· **Corrected:** "iNatSounds" is the dataset nickname, not the paper title. The apparent
year clash the repo's citation invites (a 2025 arXiv ID for a "NeurIPS 2024 paper") is
benign — the paper really was a NeurIPS 2024 D&B poster and the preprint was posted late.
Say so explicitly. The 230 000 files / > 5 500 species / 27 000 recordists figures check out.

### `nbm2026` — CORRECTED (**licence claim wrong**)
Airale, L., Pajot, A. & Linossier, J. (2026). An open dataset for the acoustic monitoring of
nocturnal migratory birds in Europe. *Scientific Data* **13**, 925.
<https://doi.org/10.1038/s41597-026-07176-5> · preprint arXiv:2412.03633 (2024).
· OA: yes. PDF: <https://www.nature.com/articles/s41597-026-07176-5.pdf>
· **Used for:** `docs/13` §3, proposed as a segmenter-validation and calls-axis source.
· **Corrected:** the repo states **CC-BY-4.0**. The live dataset (Zenodo 15655748, v2) is
**CC BY-NC-ND 3.0**. Only the superseded record 14864129 — explicitly a "double blind review
version" — is CC BY 4.0. For a non-commercial project this is workable, but the NC-ND terms
forbid derivatives, which matters for an ingest pipeline. The 2026 Nature DOI is genuine and
resolves. The 38 h / 2 077 files / 13 359 vocalisations / 117 species figures check out.
See CITATION-FINDINGS #27.

### `lostanlen2024` — VERIFIED
Lostanlen, V. (2024). Towards differentiable motor control of bird vocalizations. In *Proc.
4th International Symposium on Vocal Interactivity in-and-between Humans, Animals and Robots
(VIHAR 2024)*, Kos, Greece.
<https://hal.science/hal-04660514> · PDF: <https://hal.science/hal-04660514/document>
· OA: yes.
· **Used for:** `docs/04` line 62, `docs/07` line 118 — the differentiable-syrinx direction.
· Note: an extended abstract, not a full paper; a lighter review bar than the repo's framing
implies.

### `rhinehart2020` — CORRECTED (full citation; it is a review)
Rhinehart, T. A., Chronister, L. M., Devlin, T. & Kitzes, J. (2020). Acoustic localization of
terrestrial wildlife: current practices and future opportunities. *Ecology and Evolution*
**10**(13), 6794–6818. <https://doi.org/10.1002/ece3.6216>
· OA: yes (CC BY). PDF: <https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/ece3.6216>
· **Used for:** `docs/03` line 65, `docs/07` line 17 — mic-array localisation.
· **Corrected:** the repo gives "Rhinehart et al. 2020" only. It is a **review** of
localisation methods across terrestrial taxa, not a bird-specific empirical result. Cite it
as "as reviewed in".

### `umap2018` — NEW (**the project uses UMAP with no citation anywhere**)
McInnes, L., Healy, J. & Melville, J. (2018). UMAP: Uniform Manifold Approximation and
Projection for dimension reduction. arXiv:1802.03426.
<https://arxiv.org/abs/1802.03426> · PDF: <https://arxiv.org/pdf/1802.03426>
· **Used for:** `galaxy.py` runs UMAP as the galaxy projection. There is no citation for it
in the repo. See CITATION-FINDINGS #28.

### `umapsoft2018` — NEW
McInnes, L., Healy, J., Saul, N. & Großberger, L. (2018). UMAP: Uniform Manifold
Approximation and Projection. *Journal of Open Source Software* **3**(29), 861.
<https://doi.org/10.21105/joss.00861>
· OA: yes. PDF: <https://www.theoj.org/joss-papers/joss.00861/10.21105.joss.00861.pdf>
· **Used for:** the software citation to pair with `umap2018`.

### `hdbscan2013` — NEW (**the project uses HDBSCAN with no citation anywhere**)
Campello, R. J. G. B., Moulavi, D. & Sander, J. (2013). Density-based clustering based on
hierarchical density estimates. In *PAKDD 2013*, LNCS **7819**, 160–172.
<https://doi.org/10.1007/978-3-642-37456-2_14>
· OA: no (Springer). The extended journal version is often cited instead: Campello, Moulavi,
Zimek & Sander (2015), *ACM TKDD* **10**(1), 5, <https://doi.org/10.1145/2733381>.
· **Used for:** `density.py` and `learn.py` both use `sklearn.cluster.HDBSCAN` as the core
clustering method. No citation exists in the repo. See CITATION-FINDINGS #28.

### `hdbscansoft2017` — NEW
McInnes, L., Healy, J. & Astels, S. (2017). hdbscan: hierarchical density based clustering.
*Journal of Open Source Software* **2**(11), 205. <https://doi.org/10.21105/joss.00205>
· OA: yes. PDF: <https://www.theoj.org/joss-papers/joss.00205/10.21105.joss.00205.pdf>

### `simclr2020` — NEW (**used by name in code with no citation**)
Chen, T., Kornblith, S., Norouzi, M. & Hinton, G. (2020). A simple framework for contrastive
learning of visual representations. In *Proc. 37th International Conference on Machine
Learning (ICML)*, PMLR **119**, 1597–1607. arXiv:2002.05709.
<https://arxiv.org/abs/2002.05709> · <http://proceedings.mlr.press/v119/chen20j.html>
· OA: yes. PDF: <https://arxiv.org/pdf/2002.05709>
· **Used for:** `critic.py` lines 139, 519, 849, 941 reference "SimCLR's own ablation",
"NT-Xent" and "SimCLR's loss" with no citation. See CITATION-FINDINGS #28.

### `rff2007` — NEW (**used with no citation**)
Rahimi, A. & Recht, B. (2007). Random features for large-scale kernel machines. In *Advances
in Neural Information Processing Systems 20 (NIPS 2007)*.
<https://papers.nips.cc/paper_files/paper/2007/hash/013a006f03dbc5392effeb8f18fda755-Abstract.html>
· OA: yes. PDF: <https://papers.nips.cc/paper_files/paper/2007/file/013a006f03dbc5392effeb8f18fda755-Paper.pdf>
· **Used for:** random Fourier features, which the whitepaper illustrates in
`figures/eq/rff.png`. No citation exists in the repo. Commonly cited as pp. 1177–1184; the
page range was not independently verified.

---

## 6. Habitat acoustics — deliberately not fitted

### `slabbekoorn2002` — VERIFIED
Slabbekoorn, H., Ellers, J. & Smith, T. B. (2002). Birdsong and sound transmission: the
benefits of reverberations. *The Condor* **104**(3), 564–573.
<https://doi.org/10.1093/condor/104.3.564>
· OA: bronze. PDF: <https://academic.oup.com/condor/article-pdf/104/3/564/29712015/condor0564.pdf>
(automated fetch blocked).
· **Used for:** `docs/07` line 108, the reverberation argument for keeping habitat as a
post-process outside the fitted parameters.
· Note: the repo cites the BioOne-style DOI implicitly; the registered DOI is the OUP one
above.

### `nemeth2006` — VERIFIED
Nemeth, E., Dabelsteen, T., Pedersen, S. B. & Winkler, H. (2006). Rainforests as concert
halls for birds: are reverberations improving sound transmission of long song elements?
*Journal of the Acoustical Society of America* **119**(1), 620–626.
<https://doi.org/10.1121/1.2139072>
· OA: no. Paywalled, not downloaded.
· **Used for:** as above.

### `dabelsteen1993` — VERIFIED
Dabelsteen, T., Larsen, O. N. & Pedersen, S. B. (1993). Habitat-induced degradation of sound
signals: quantifying the effects of communication sounds and bird location on blur ratio,
excess attenuation, and signal-to-noise ratio in blackbird song. *Journal of the Acoustical
Society of America* **93**(4), 2206–2220. <https://doi.org/10.1121/1.406682>
· OA: green (submitted version in an institutional repository).
· **Used for:** the excess-attenuation figure in `docs/07` line 110 ("~10 dB/100 m at
1 kHz"). The paper does measure excess attenuation in blackbird song in a deciduous forest;
the specific 10 dB/100 m number was not isolated in the accessible text and should be
checked or attributed as a general figure from this literature rather than to one paper.

---

## 7. Corpora, benchmarks and software

Cited as resources rather than as evidence. Bibliographic details verified; claim-checking
does not apply.

### `chronister2021` — VERIFIED
Chronister, L. M., Rhinehart, T. A., Place, A. & Kitzes, J. (2021). An annotated set of audio
recordings of Eastern North American birds containing frequency, time, and species
information. *Ecology* **102**(6), e03329. <https://doi.org/10.1002/ecy.3329>
· OA: bronze. PDF: <https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/ecy.3329>
(automated fetch blocked). **Used for:** `docs/13` segmenter-validation ground truth.

### `a2o2021` — VERIFIED
Roe, P., Eichinski, P., Fuller, R. A., McDonald, P. G., Schwarzkopf, L., Towsey, M.,
Truskinger, A., Tucker, D. & Watson, D. M. (2021). The Australian Acoustic Observatory.
*Methods in Ecology and Evolution* **12**(10), 1802–1808.
<https://doi.org/10.1111/2041-210X.13660>
· OA: bronze (automated fetch blocked). **Used for:** `docs/13` second-tier source table.

### `nips4bplus2019` — CORRECTED (full citation supplied)
Morfi, V., Bas, Y., Pamuła, H., Glotin, H. & Stowell, D. (2019). NIPS4Bplus: a richly
annotated birdsong audio dataset. *PeerJ Computer Science* **5**, e223.
<https://doi.org/10.7717/peerj-cs.223>
· OA: yes (CC BY). **Used for:** `docs/13` line 87. The repo links the PeerJ article page
but gives no authors, year or DOI.

### `ddsp2020` — VERIFIED
Engel, J., Hantrakul, L., Gu, C. & Roberts, A. (2020). DDSP: Differentiable Digital Signal
Processing. In *ICLR 2020*. arXiv:2001.04643. <https://arxiv.org/abs/2001.04643>
· OA: yes. **Used for:** `docs/04` §4.3 and `docs/07` line 115, as an approach the project
deliberately rejects (`docs/21` §21.4).

### `rave2021` — VERIFIED
Caillon, A. & Esling, P. (2021). RAVE: a variational autoencoder for fast and high-quality
neural audio synthesis. arXiv:2111.05011. <https://arxiv.org/abs/2111.05011>
· OA: yes. **Used for:** as above.

### Other resources cited by URL only
These appear in `docs/07`, `docs/03`, `docs/05` and `docs/13` as links, not as literature.
They need no ledger entry beyond a stable URL, but they do need one in a LaTeX bibliography
if the manuscript names them:
xeno-canto (<https://xeno-canto.org>), Macaulay Library
(<https://www.macaulaylibrary.org>), Bengalese Finch Song Repository
(<https://vocalpy.org/bfsongrepo>), 887 isolated zebra finch syllables
(Zenodo <https://doi.org/10.5281/zenodo.5545872>), XCDC
(Zenodo <https://doi.org/10.5281/zenodo.15420487>), Tierstimmenarchiv via GBIF
(<https://doi.org/10.15468/0bpalr>), Borror Lab via GBIF
(<https://doi.org/10.15468/wyz5x9>), BirdVox (Zenodo
<https://doi.org/10.5281/zenodo.1205569>), BEANS
(<https://github.com/earthspecies/beans>), BioCPPNet
(<https://github.com/earthspecies/cocktail-party-problem>), Google Creative Lab "Bird
Sounds" (<https://github.com/googlecreativelab/aiexperiments-bird-sounds>), TensorFlow
Embedding Projector (<https://projector.tensorflow.org>), Apple Embedding Atlas
(<https://github.com/apple/embedding-atlas>), Threlte (<https://threlte.xyz>), Meyda
(<https://meyda.js.org>), pitchy (<https://github.com/ianprime0509/pitchy>), hvcc
(<https://github.com/Wasted-Audio/hvcc>), `syrinxsynth`
(<https://github.com/zekearneodo/syrinxsynth>), `birdsongs`
(<https://github.com/saguileran/birdsongs>), `mindlin_auto`
(<https://github.com/kylerbrown/mindlin_auto>), `tracheophones`
(<https://github.com/gabomindlin/tracheophones>), Farnell, A. (2010). *Designing Sound*.
MIT Press (ISBN 978-0-262-01441-0), Windytan, "Speech to birdsong conversion"
(<https://www.windytan.com>, 2021).

---

---

## 8. Borrowed methods and comparative work cited only by the arXiv manuscript

Added 2026-08-01. `docs/whitepaper/arxiv/main.tex` cites 14 works that appear nowhere in the
repository itself, so the original audit did not reach them. They are almost all methods
borrowed from other fields — information theory, speech quality assessment, language modelling,
single-cell genomics, computer vision, domain generalisation — plus four comparative or
cautionary works from animal-communication research. All 14 were resolved and verified here
against Crossref, arXiv, JMLR or Europe PMC. Keys are fixed by the manuscript.

### `beans2022` — CORRECTED (key year vs publication year)
Hagiwara, M., Hoffman, B., Liu, J.-Y., Cusimano, M., Effenberger, F. & Zacarian, K. (2023).
BEANS: The Benchmark of Animal Sounds. In *Proc. IEEE ICASSP*, pp. 1–5.
<https://doi.org/10.1109/ICASSP49357.2023.10096686> · preprint arXiv:2210.12300 (2022).
· OA: no at IEEE; preprint OA. PDF: <https://arxiv.org/pdf/2210.12300>
· **Used for:** cited beside `birdset2024` in the manuscript's related-work section as the
benchmark literature that arrived with the bioacoustic foundation models.
· **Corrected:** the key says 2022 (the preprint), the paper is ICASSP **2023**. The entry
carries both so the key can stay as the manuscript has it.

### `berwick2011` — VERIFIED
Berwick, R. C., Okanoya, K., Beckers, G. J. L. & Bolhuis, J. J. (2011). Songs to syntax: the
linguistics of birdsong. *Trends in Cognitive Sciences* **15**(3), 113–121.
<https://doi.org/10.1016/j.tics.2011.01.002>
· OA: no. Paywalled, not downloaded.
· **Used for:** the manuscript's cautionary framing on how far the birdsong-to-syntax analogy
can be pushed, and the reason the project claims nothing above sequence structure.
· Claim check: **supported, almost verbatim.** The abstract states that "birdsong structure is
best characterized as 'phonological syntax', resembling aspects of human sound structure.
Crucially, birdsong lacks semantics and words." That is exactly the reading the manuscript
attributes to it. This is the strongest available support for the project's own restraint about
"translation", and pairs well with `rutz2023`.

### `cilibrasi2005` — VERIFIED
Cilibrasi, R. & Vitányi, P. M. B. (2005). Clustering by Compression. *IEEE Transactions on
Information Theory* **51**(4), 1523–1545. <https://doi.org/10.1109/TIT.2005.844059>
· preprint arXiv:cs/0312044 (2003). OA: preprint only.
PDF: <https://arxiv.org/pdf/cs/0312044>
· **Used for:** normalised compression distance as the model-free sequence baseline — which the
project then **refutes** as a measure for this corpus, because the within-species shuffle
control separates species better than the real corpus does (0.038 against 0.018).
· Claim check: supported as the NCD source.

### `li2004` — VERIFIED
Li, M., Chen, X., Li, X., Ma, B. & Vitányi, P. M. B. (2004). The Similarity Metric. *IEEE
Transactions on Information Theory* **50**(12), 3250–3264.
<https://doi.org/10.1109/TIT.2004.838101>
· preprint arXiv:cs/0111054 (2001). OA: preprint only.
PDF: <https://arxiv.org/pdf/cs/0111054>
· **Used for:** the normalised information distance underlying NCD.
· Claim check: **supported.** The manuscript's framing — that NID is the theory and is
uncomputable, so NCD is the computable stand-in — is correct: NID is defined via Kolmogorov
complexity, which is not computable.

### `cranmer2020` — VERIFIED
Cranmer, K., Brehmer, J. & Louppe, G. (2020). The frontier of simulation-based inference.
*PNAS* **117**(48), 30055–30062. <https://doi.org/10.1073/pnas.1912789117>
· preprint arXiv:1911.01429. OA: preprint OA.
PDF: <https://arxiv.org/pdf/1911.01429>
· **Used for:** named, with `ddsp2020`, as the right next step for fitting a mechanistic
simulator — i.e. the principled alternative to the project's current coordinate search.

### `dalziell2012` — VERIFIED (with a presentation-context caveat)
Dalziell, A. H. & Magrath, R. D. (2012). Fooling the experts: accurate vocal mimicry in the
song of the superb lyrebird, *Menura novaehollandiae*. *Animal Behaviour* **83**(6),
1401–1410. <https://doi.org/10.1016/j.anbehav.2012.03.009>
· OA: no (Elsevier, closed; confirmed via Unpaywall). Not downloaded. Metadata record:
<https://openresearch-repository.anu.edu.au/handle/1885/64477>
· **Used for:** the project's only source of cross-species acoustic ground truth — a lyrebird
singing a grey shrike-thrush produces syllables whose acoustics are shrike-thrush and whose
label is lyrebird, with the accuracy certified by the receiving birds. Also the namesake of the
renamed application.
· Claim check: **supported.** The species imitated is the grey shrike-thrush (*Colluricincla
harmonica*), the playback subjects were grey shrike-thrushes, and they "reacted just as
strongly towards mimetic song as to their own when songs were presented alone". Caveat worth
carrying: that equivalence is for songs presented **alone** — when the mimicry was embedded in
the lyrebird's own song sequence, shrike-thrushes approached less often. See
CITATION-FINDINGS #31.

### `favaro2020` — CORRECTED (mechanism differs from the paper it is paired with)
Favaro, L., Gamba, M., Cresta, E., Fumagalli, E., Bandoli, F., Pilenga, C., Isaja, V.,
Mathevon, N. & Reby, D. (2020). Do penguins' vocal sequences conform to linguistic laws?
*Biology Letters* **16**(2), 20190589. <https://doi.org/10.1098/rsbl.2019.0589>
· OA: green via PMC. PDF: <https://pmc.ncbi.nlm.nih.gov/articles/PMC7058940/>
· **Used for:** paired with `gustison2016` as the reference shape for a Menzerath–Altmann
result, against which the project's own weakly-positive exponent is reported as *not* the law.
· **Corrected:** species is the African penguin, and the paper does find Menzerath–Altmann —
but by a **different mechanism** than the gelada study it is paired with. See
CITATION-FINDINGS #30.

### `ganin2016` — VERIFIED
Ganin, Y., Ustinova, E., Ajakan, H., Germain, P., Larochelle, H., Laviolette, F., Marchand, M.
& Lempitsky, V. (2016). Domain-Adversarial Training of Neural Networks. *Journal of Machine
Learning Research* **17**(59), 1–35. <https://jmlr.org/papers/v17/15-239.html>
· preprint arXiv:1505.07818. OA: yes (JMLR).
PDF: <https://www.jmlr.org/papers/volume17/15-239/15-239.pdf>
· **Used for:** the gradient-reversal adversarial head in `critic.py`, and the measured
one-for-one exchange rate between removing recordist structure and losing species structure.
· No DOI — JMLR does not assign them. Note that JMLR's own exported BibTeX truncates the
seventh author to "Mario March"; the correct name is **Marchand**, and the entry in
`references.bib` fixes it.

### `gustison2016` — VERIFIED
Gustison, M. L., Semple, S., Ferrer-i-Cancho, R. & Bergman, T. J. (2016). Gelada vocal
sequences follow Menzerath's linguistic law. *PNAS* **113**(19), E2750–E2758.
<https://doi.org/10.1073/pnas.1522072113>
· OA: green via PMC. PDF: <https://pmc.ncbi.nlm.nih.gov/articles/PMC4868448/>
· **Used for:** as above.
· Claim check: **supported** — "to our knowledge, we present the first evidence that
Menzerath's law holds in the vocal communication of a nonhuman species", in wild male geladas
(*Theropithecus gelada*), with most call types abbreviated in larger sequences.

### `kneser1995` — VERIFIED
Kneser, R. & Ney, H. (1995). Improved backing-off for M-gram language modeling. In *Proc. IEEE
ICASSP*, vol. 1, pp. 181–184. <https://doi.org/10.1109/ICASSP.1995.479394>
· OA: no. Paywalled, not downloaded.
· **Used for:** the continuation-count backoff in the shipped grammar, which repaired the
smoothing rather than adopting an HMM for a smoothing artefact (+1.90 and +2.32 nats/token on
unseen-context transitions).
· This is the original Kneser–Ney paper, and the correct source for continuation counts.

### `korsunsky2019` — VERIFIED
Korsunsky, I., Millard, N., Fan, J., Slowikowski, K., Zhang, F., Wei, K., Baglaenko, Y.,
Brenner, M., Loh, P.-r. & Raychaudhuri, S. (2019). Fast, sensitive and accurate integration of
single-cell data with Harmony. *Nature Methods* **16**(12), 1289–1296.
<https://doi.org/10.1038/s41592-019-0619-0>
· OA: green (free author manuscript):
<https://pmc.ncbi.nlm.nih.gov/articles/PMC6884693/> — PDF render endpoint errored; fetch by
hand.
· **Used for:** Harmony as the strongest post-hoc batch-correction candidate for removing
recordist structure. It reaches the confound and pays the same −71 % recordist / −70 % species
exchange rate as the adversarial head — two unrelated mechanisms landing on the same rate,
which the manuscript reads as evidence about the data rather than about either method. A good
use of a borrowed tool.

### `kubichek1993` — VERIFIED
Kubichek, R. (1993). Mel-cepstral distance measure for objective speech quality assessment. In
*Proc. IEEE Pacific Rim Conference on Communications, Computers and Signal Processing
(PACRIM)*, vol. 1, pp. 125–128. <https://doi.org/10.1109/PACRIM.1993.407206>
· OA: no. Paywalled, not downloaded.
· **Used for:** mel-cepstral distortion as one of the two independent audible-distance metrics
that showed the 28-d descriptor cosine carries essentially no information about spectral
distance (Pearson +0.106, Spearman +0.100). This is the citation behind the project's most
self-critical measurement.

### `prince2007` — CORRECTED (field of origin)
Prince, S. J. D. & Elder, J. H. (2007). Probabilistic Linear Discriminant Analysis for
Inferences About Identity. In *Proc. IEEE ICCV*, pp. 1–8.
<https://doi.org/10.1109/ICCV.2007.4409052>
· OA: no (confirmed closed via Unpaywall). Not downloaded.
· **Used for:** PLDA as a post-hoc candidate for removing recording-condition structure,
described in the manuscript as "from speaker verification".
· **Corrected:** this is a **face-recognition** paper. PLDA was adopted by the
speaker-verification community afterwards. See CITATION-FINDINGS #29.

### `zhou2021mixstyle` — VERIFIED
Zhou, K., Yang, Y., Qiao, Y. & Xiang, T. (2021). Domain Generalization with MixStyle. In *Proc.
International Conference on Learning Representations (ICLR)*. arXiv:2104.02008.
<https://arxiv.org/abs/2104.02008>
· OA: yes. PDF: <https://arxiv.org/pdf/2104.02008>
· **Used for:** feature-statistic style mixing inside the learned critic.
· Extended journal version: Zhou et al. (2024), *MixStyle Neural Networks for Domain
Generalization and Adaptation*, *IJCV* **132**(3), 822–836,
<https://doi.org/10.1007/s11263-023-01913-8>. The ICLR paper is the right one for the method as
implemented; the entry notes the journal version.

## Appendix — works the repo should cite but does not

Beyond the four missing method citations (`umap2018`, `hdbscan2013`, `simclr2020`,
`rff2007`), the corrections above introduce these as the correct sources for claims currently
attributed elsewhere:

| work | carries the claim currently attributed to |
| --- | --- |
| `hailman1985` | `freeberg2003` (A→B→C→D note syntax) |
| `templeton2005` | `freeberg2003` (D-count scales with threat) |
| `hultsch1981` | `hultschtodt` (countersinging rules) |
| `suthers1994` | `suthers1985` (individual formant signatures) |
| `ishizaka1972` | `docs/21`'s "Titze's lineage" for the two-mass model |
| `elemans2010` | the repo's "Zollinger et al. 2010" |
| `brinklov2013` | the repo's "Suthers 2013" |
| `podos2001` (*Nature* 409:185–188, <https://doi.org/10.1038/35051570>) | `podos2004` (trill-rate/frequency trade-off) |
| `wood2013` | the non-existent `chen2013` (R² ≈ 0.03) |
| `amador2013` | `amador2021` (noise on tension drives HVC neurons) |
| `sitt2010` / `amador2008` | `laje2002b` (the dimensionless normal form) |
| `laje2005` / `laje2008` | `sitt2008` + `amador2008` (period doubling and chaos) |
