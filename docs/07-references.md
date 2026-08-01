# 7 — Key references

Corrected against the primary literature on 2026-08-01. Full bibliographic detail, open-access
status and per-entry verification status live in
[`whitepaper/references/REFERENCES.md`](whitepaper/references/REFERENCES.md); BibTeX in
[`whitepaper/references/references.bib`](whitepaper/references/references.bib); downloaded PDFs
in [`whitepaper/references/pdf/`](whitepaper/references/pdf/).

Claims in this repo that the cited source does **not** support are listed in
[`whitepaper/references/CITATION-FINDINGS.md`](whitepaper/references/CITATION-FINDINGS.md).
Several are corrected inline below and flagged **[was wrong]**.

## Decoding

- Rutz, C., Bronstein, M., Raskin, A., Vernes, S. C., Zacarian, K. & Blasi, D. E., *Using
  machine learning to decode animal communication*, Science 381:152–155 (2023), a Perspective
  ([10.1126/science.adg7314](https://doi.org/10.1126/science.adg7314))
- Perch 2.0 — van Merriënboer et al., *Perch 2.0: The Bittern Lesson for Bioacoustics*,
  [arXiv:2508.04665](https://arxiv.org/abs/2508.04665) ·
  [github.com/google-research/perch](https://github.com/google-research/perch) (Apache 2.0).
  **[was wrong]** 1536-d embedding, EfficientNet-B3 trunk, 14 795 output classes of which
  14 597 are species — docs/03 still quotes Perch 1.0's B1/1280-d figures.
- BirdNET — Kahl, S., Wood, C. M., Eibl, M. & Klinck, H., Ecological Informatics 61:101236
  (2021) ([10.1016/j.ecoinf.2021.101236](https://doi.org/10.1016/j.ecoinf.2021.101236)).
  Model weights CC BY-NC-SA 4.0; the BirdNET-Analyzer *code* is MIT ·
  [github.com/birdnet-team/BirdNET-Analyzer](https://github.com/birdnet-team/BirdNET-Analyzer)
- AVES — Hagiwara, ICASSP 2023, [arXiv:2210.14493](https://arxiv.org/abs/2210.14493) ·
  Bird-MAE — Rauch et al., TMLR 2025, [arXiv:2504.12880](https://arxiv.org/abs/2504.12880) ·
  AVEX — Miron et al., ICLR 2026, [arXiv:2508.11845](https://arxiv.org/abs/2508.11845), whose
  code release is [github.com/earthspecies/avex](https://github.com/earthspecies/avex) (MIT).
  **[was wrong]** the paper and the package are the same project, not two things.
- NatureLM-audio — Robinson et al., ICLR 2025,
  [arXiv:2411.07186](https://arxiv.org/abs/2411.07186)
- Suzuki, T. N., Wheatcroft, D. & Griesser, M., *Experimental evidence for compositional syntax
  in bird calls*, Nature Communications 7:10986 (2016)
  ([10.1038/ncomms10986](https://doi.org/10.1038/ncomms10986)) — the Japanese great tit ABC-D
  construction. **[was wrong]** reversed order (D-ABC) produced a *reduced* response, not none.
- Griesser, M., *Referential calls signal predator behavior in a group-living bird species*,
  Current Biology 18:69–73 (2008)
  ([10.1016/j.cub.2007.11.069](https://doi.org/10.1016/j.cub.2007.11.069)) — Siberian jay;
  calls encode predator *behaviour*, not category.
- **[was wrong]** the chickadee row needs three papers, not one:
  - Hailman, J. P., Ficken, M. S. & Ficken, R. W., Semiotica 56:191–224 (1985)
    ([10.1515/semi.1985.56.3-4.191](https://doi.org/10.1515/semi.1985.56.3-4.191)) — the four
    note types and the A→B→C→D order, black-capped chickadee.
  - Templeton, C. N., Greene, E. & Davis, K., Science 308:1934–1937 (2005)
    ([10.1126/science.1108841](https://doi.org/10.1126/science.1108841)) — D-count scales with
    predator size.
  - Freeberg, T. M., Lucas, J. R. & Clucas, B., JASA 113:2127–2136 (2003)
    ([10.1121/1.1559175](https://doi.org/10.1121/1.1559175)) — note-level identity, but for the
    **Carolina** chickadee, and about *sex* and microgeographic difference rather than flock or
    individual identity.
- Nightingale song-type organisation — Hultsch, H. & Todt, D., J. Comp. Physiol. A 165:197–203
  (1989) ([10.1007/BF00619194](https://doi.org/10.1007/BF00619194)) for package formation, and
  Hultsch & Todt, Behav. Ecol. Sociobiol. 8:183–188 (1981)
  ([10.1007/BF00299828](https://doi.org/10.1007/BF00299828)) for countersinging rules. Later
  stability: Jäckel et al., Front. Ecol. Evol. 10:778610 (2022)
  ([10.3389/fevo.2022.778610](https://doi.org/10.3389/fevo.2022.778610)).
- Bengalese finch syntax — Okanoya, K., Ann. N.Y. Acad. Sci. 1016:724–735 (2004), a review
  ([10.1196/annals.1298.026](https://doi.org/10.1196/annals.1298.026)); the finite-state model
  is Katahira, K., Suzuki, K., Okanoya, K. & Okada, M., PLOS ONE 6:e24516 (2011)
  ([10.1371/journal.pone.0024516](https://doi.org/10.1371/journal.pone.0024516)).
- BioCPPNet —
  [github.com/earthspecies/cocktail-party-problem](https://github.com/earthspecies/cocktail-party-problem)
- BirdSet — Rauch et al., ICLR 2025,
  [arXiv:2403.10380](https://arxiv.org/abs/2403.10380) ·
  BEANS — [github.com/earthspecies/beans](https://github.com/earthspecies/beans) · DCASE Task 5
- Rhinehart, T. A., Chronister, L. M., Devlin, T. & Kitzes, J., *Acoustic localization of
  terrestrial wildlife: current practices and future opportunities*, Ecology and Evolution
  10:6794–6818 (2020) ([10.1002/ece3.6216](https://doi.org/10.1002/ece3.6216)) — a review
  across terrestrial taxa, not a bird-specific result. Cite as "as reviewed in".

## Embeddings & visualization

- Sainburg, T., Thielk, M. & Gentner, T. Q., PLOS Comp. Biol. 16:e1008228 (2020)
  ([10.1371/journal.pcbi.1008228](https://doi.org/10.1371/journal.pcbi.1008228))
- Goffinet, J., Brudner, S., Mooney, R. & Pearson, J., eLife 10:e67855 (2021)
  ([10.7554/eLife.67855](https://doi.org/10.7554/eLife.67855)) — VAE + UMAP vocal latent spaces
- **[was missing]** the methods this repo actually runs had no citation anywhere:
  - UMAP — McInnes, Healy & Melville, [arXiv:1802.03426](https://arxiv.org/abs/1802.03426);
    software [10.21105/joss.00861](https://doi.org/10.21105/joss.00861)
  - HDBSCAN — Campello, Moulavi & Sander, PAKDD 2013
    ([10.1007/978-3-642-37456-2_14](https://doi.org/10.1007/978-3-642-37456-2_14)); software
    [10.21105/joss.00205](https://doi.org/10.21105/joss.00205)
  - SimCLR / NT-Xent — Chen, Kornblith, Norouzi & Hinton, ICML 2020,
    [arXiv:2002.05709](https://arxiv.org/abs/2002.05709). `critic.py` argues from "SimCLR's own
    ablation" without citing it.
  - Random Fourier features — Rahimi & Recht, NIPS 2007
    ([proceedings](https://papers.nips.cc/paper_files/paper/2007/hash/013a006f03dbc5392effeb8f18fda755-Abstract.html))
- Domain invariance — Moummad, I., Serizel, R., Benetos, E. & Farrugia, N.,
  *Domain-invariant representation learning of bird sounds*,
  [arXiv:2409.08589](https://arxiv.org/abs/2409.08589) (preprint). **[was wrong]** the title in
  earlier drafts was a paraphrase.
- Channel simulation — Morocutti, T., Schmid, F., Koutini, K. & Widmer, G., *Device-robust
  acoustic scene classification via impulse response augmentation*, EUSIPCO 2023,
  [arXiv:2305.07499](https://arxiv.org/abs/2305.07499). **[was wrong]** the title was a
  paraphrase, and the paper's domain is **microphone-device shift in acoustic scene
  classification**, not bioacoustics. Transferring it to recordist shift is our extension.
- Google Bird Sounds —
  [github.com/googlecreativelab/aiexperiments-bird-sounds](https://github.com/googlecreativelab/aiexperiments-bird-sounds)
  (Apache 2.0)
- TensorFlow Embedding Projector — [projector.tensorflow.org](https://projector.tensorflow.org)
- Apple Embedding Atlas — [github.com/apple/embedding-atlas](https://github.com/apple/embedding-atlas) (MIT)

## Synthesis

- Mindlin, G. B. & Laje, R., *The Physics of Birdsong* (Springer 2005)
  ([10.1007/3-540-28249-1](https://doi.org/10.1007/3-540-28249-1))
- Gardner, T., Cecchi, G., Magnasco, M., Laje, R. & Mindlin, G. B., *Simple motor gestures for
  birdsongs*, Phys. Rev. Lett. 87:208101 (2001)
  ([10.1103/PhysRevLett.87.208101](https://doi.org/10.1103/PhysRevLett.87.208101)) — two scalar
  gestures reproduce canary song.
- Laje, R., Gardner, T. J. & Mindlin, G. B., Phys. Rev. E 65:051921 (2002)
  ([10.1103/PhysRevE.65.051921](https://doi.org/10.1103/PhysRevE.65.051921)); Laje, R. &
  Mindlin, G. B., *Diversity within a birdsong*, Phys. Rev. Lett. 89:288102 (2002)
  ([10.1103/PhysRevLett.89.288102](https://doi.org/10.1103/PhysRevLett.89.288102)).
  **[was wrong]** neither is the source of the dimensionless (α, β, γ) normal form this repo
  integrates. That is derived by Takens–Bogdanov reduction in Amador & Mindlin 2008 and written
  out with the γ rescaling in Sitt et al. 2010 (both below).
- Amador, A. & Mindlin, G. B., Front. Neurosci. 15:647978 (2021) —
  **[was wrong]** the real title is *Synthetic Birdsongs as a Tool to Induce, and Listen to,
  Replay Activity in Sleeping Birds*
  ([10.3389/fnins.2021.647978](https://doi.org/10.3389/fnins.2021.647978)), and it is a
  **review**, not the paper that publishes the ODE.
- Amador, A., Perl, Y. S., Mindlin, G. B. & Margoliash, D., Nature 495:59–64 (2013)
  ([10.1038/nature11967](https://doi.org/10.1038/nature11967)) — **[was wrong]** synthetic song
  elicits **58 % ± 8 %** of the response to real song, not an indistinguishable response. Its
  robust result is burst timing at gesture-trajectory extrema.
- Boari, S., Perl, Y. S., Amador, A., Margoliash, D. & Mindlin, G. B., J. Neurophysiol.
  114:2912–2922 (2015) ([10.1152/jn.00385.2015](https://doi.org/10.1152/jn.00385.2015)) —
  automatic gesture inversion (audio → pressure/tension curves).
- Arneodo, E. M., Perl, Y. S., Goller, F. & Mindlin, G. B., *Prosthetic avian vocal organ
  controlled by a freely behaving bird…*, PLOS Comp. Biol. 8:e1002546 (2012)
  ([10.1371/journal.pcbi.1002546](https://doi.org/10.1371/journal.pcbi.1002546)) — real time,
  driven by the bird's own **air-sac pressure**. It is a biomechanical prosthesis, not a neural
  one.
- Implementations: [zekearneodo/syrinxsynth](https://github.com/zekearneodo/syrinxsynth) ·
  [saguileran/birdsongs](https://github.com/saguileran/birdsongs) ·
  [kylerbrown/mindlin_auto](https://github.com/kylerbrown/mindlin_auto) (Boari's table)
- Beckers, G. J. L., Suthers, R. A. & ten Cate, C., *Pure-tone birdsong by resonance filtering
  of harmonic overtones*, PNAS 100:7372–7376 (2003)
  ([10.1073/pnas.1232227100](https://doi.org/10.1073/pnas.1232227100)) — note the species are
  **doves**, not passerines.
- Beckers, G. J. L., Nelson, B. S. & Suthers, R. A., *Vocal-tract filtering by lingual
  articulation in a parrot*, Current Biology 14:1592–1597 (2004)
  ([10.1016/j.cub.2004.08.057](https://doi.org/10.1016/j.cub.2004.08.057))

### Naturalness — what §8.1a is built on

Validation that this model class is enough:

- **Bistel, R., Amador, A. & Mindlin, G. B., Phys. Rev. E 109:054410 (2024)** — *Response of
  wild songbirds to songs synthesized with a low-dimensional model*
  ([10.1103/PhysRevE.109.054410](https://doi.org/10.1103/PhysRevE.109.054410),
  [author PDF](http://www.lsd.df.uba.ar/wp-content/uploads/2024/07/wild.pdf)). 256 playback
  protocols, 26 wild rufous-collared sparrows, 15 sites: **no statistically significant
  difference** between responses to real and to synthetic song, while heterospecific song
  evoked significantly lower responses. Every number checked against full text. The strongest
  realism test in this literature, and this architecture passes it. The reason Lyrebird stays
  procedural. Say "no significant difference was found", not "indistinguishable" — a
  non-significant result bounds an effect, it does not eliminate it.

Spectral richness comes from `beta`, not from the filter:

- **Sitt, J. D., Amador, A., Goller, F. & Mindlin, G. B., Phys. Rev. E 78:011905 (2008)** —
  *Dynamical origin of spectrally rich vocalizations in birdsong*
  ([10.1103/PhysRevE.78.011905](https://doi.org/10.1103/PhysRevE.78.011905)). Oscillations born
  in a saddle-node-on-a-limit-cycle are pulse-like and harmonically dense; those born in a Hopf
  are tonal. This dichotomy is the finding §8.1a's `gammaScale` acts on.
  **[was wrong]** "SCI is a function of `beta` alone and is invariant to `gamma`" is *not* in
  this paper — it has no γ parameter, and Perl et al. 2011 Fig. 5 shows SCI as a joint function
  of α *and* β. What is true, and is ours to state: SCI is dimensionless, so a pure
  time-rescaling γ cannot change it, and at fixed f₀ raising γ drives β down into the SNILC
  regime.
- Sitt, J. D., Arneodo, E. M., Goller, F. & Mindlin, G. B., Phys. Rev. E 81:031927 (2010) —
  *Physiologically driven avian vocal synthesizer*
  ([10.1103/PhysRevE.81.031927](https://doi.org/10.1103/PhysRevE.81.031927)). Fits `gamma` from
  two (f0, SCI) points (minimum at γ = 23 500); reports `d_pitch` = 0.152 and `d_SCI` = 0.263 as
  the state of the art. Worth reading against our own numbers: our F0 error is far *better* than
  theirs and our SCI error was far worse, which is what identified the problem. This paper is
  also where the γ-scaled normal form is written out in full.
- Perl, Y. S., Arneodo, E. M., Amador, A., Goller, F. & Mindlin, G. B., *Reconstruction of
  physiological instructions from Zebra finch song*, Phys. Rev. E 84:051909 (2011)
  ([10.1103/PhysRevE.84.051909](https://doi.org/10.1103/PhysRevE.84.051909)) — `chi^2(gamma)`
  fit over 28 segments from 28 syllables → `gamma = 24000`, the value our table is measured at.
- Boari et al. 2015 (above) — the production pipeline is a nearest-neighbour lookup in a
  precomputed `(alpha, beta, f0, SCI)` table, not an optimiser. Verified: the released
  `OEC.new.dat` is exactly that table.

Noise belongs on tension, and is required:

- **Amador et al., Nature 495:59–64 (2013)** — this, not the 2021 review, is the primary source.
  Matching the fundamental and the filters was not enough to drive selective HVC neurons; noise
  on `beta` (labial tension) had to be added, and an *intermediate* magnitude scored best.
  Directly why §8.1a's `rough` perturbs tension rather than pressure or the output. The 2021
  review reproduces the figure, captioned "Adapted from Amador et al. (2013)".
- Riede, T. & Goller, F., *Peripheral mechanisms for vocal production in birds — differences and
  similarities to human speech and singing*, Brain and Language 115:69–80 (2010)
  ([10.1016/j.bandl.2009.11.003](https://doi.org/10.1016/j.bandl.2009.11.003)): airflow
  modulation below 80 Hz is respiratory, 80–250 Hz syringeal. **Caveat we owe ourselves:**
  `ROUGH_LP_HZ = 140` is a *low-pass* corner, so most of its energy sits below 140 Hz including
  the sub-80 Hz respiratory band. It does not select the syringeal band. See
  CITATION-FINDINGS #11; the two-band split in docs/21 §21.3 item 2 is the coherent version.
- Wood, W. E., Osseward, P. J., Roseberry, T. K. & Perkel, D. J., PLOS ONE 8:e82327 (2013)
  ([10.1371/journal.pone.0082327](https://doi.org/10.1371/journal.pone.0082327)) — a daily
  oscillation in f0 and amplitude in zebra finch song, **and** the source of
  R² = 0.03323 ± 0.00816 for rendition-to-rendition f0-vs-amplitude correlation, so independent
  output jitter and shimmer would be the wrong model. **[was wrong]** this repo previously
  credited that R² to "Chen et al., PLOS ONE 2013" — no such paper exists. It is this one.
- Tumer, E. C. & Brainard, M. S., *Performance variability enables adaptive plasticity of
  'crystallized' adult birdsong*, Nature 450:1240–1244 (2007)
  ([10.1038/nature06390](https://doi.org/10.1038/nature06390)) — cited for a ~1 % f0 CV in
  crystallised adult Bengalese finch song. **Unverified:** that number could not be found in
  accessible text. If it is going to gate a pre-registered fit, it needs a traceable source
  (Sober & Brainard 2009, Nat. Neurosci. 12:927–931; Sober, Wohlgemuth & Brainard 2008,
  J. Neurosci. 28:10370–10379 both measure baseline pitch variability directly).
- Fee, M. S., Shraiman, B., Pesaran, B. & Mitra, P. P., Nature 395:67–71 (1998)
  ([10.1038/25725](https://doi.org/10.1038/25725)) — period doubling, mode locking and chaos in
  the excised syrinx. **[was wrong]** elsewhere in this repo it is cited for "skewed, pulse-like
  labial waveforms"; the paper does not image labial motion. Use it for the nonlinear-dynamics
  finding only.
- Zollinger, S. A., Riede, T. & Suthers, R. A., J. Exp. Biol. 211:1978–1991 (2008)
  ([10.1242/jeb.014092](https://doi.org/10.1242/jeb.014092)) — prevalence in real song:
  8.5 % of northern mockingbird syllables show unilateral nonlinear phenomena
  (biphonation 4.3 %, **chaos 1.7 %**, subharmonics 1.3 %, frequency jumps 1.2 %); jumps span
  45–450 Hz. **[was wrong]** this entry previously read "chaos 6.7 %", which is one individual
  bird's rate and breaks the sum; chaos across birds overall is 8.3 %.
  Counterexample worth knowing: **Elemans, C. P. H., Laje, R., Mindlin, G. B. & Goller, F.,
  J. Neurosci. 30:13246–13253 (2010)**
  ([10.1523/JNEUROSCI.1130-10.2010](https://doi.org/10.1523/JNEUROSCI.1130-10.2010)) — adult
  zebra finches *avoid* subharmonics. **[was wrong]** this repo credited it to "Zollinger et
  al."; two of the actual authors wrote our source model. So nonlinearity must be fitted per
  syllable, never enabled globally.
- Elemans, C. P. H., Mead, A. F., Rome, L. C. & Goller, F., PLOS ONE 3:e2581 (2008)
  ([10.1371/journal.pone.0002581](https://doi.org/10.1371/journal.pone.0002581)) — syringeal
  muscles do positive work up to 250 Hz, so the headroom for tremor is measured, not assumed.
- Hartley, R. S. & Suthers, R. A., *Airflow and pressure during canary song: direct evidence
  for mini-breaths*, J. Comp. Physiol. A 165:15–26 (1989)
  ([10.1007/BF00613795](https://doi.org/10.1007/BF00613795)) — mini-breaths at 2–27 notes/s,
  pulsatile expiration at 30–38 notes/s. Note there is **no data between 27 and 30**; our
  "~30 Hz" threshold is an approximation across an unobserved gap.
- Fainstein, F., Goller, F. & Mindlin, G. B., *Nonlinear biomechanical resonances in birdsong*,
  [arXiv:2509.11019v2](https://arxiv.org/abs/2509.11019) (2025, preprint) — the 2-state air-sac
  oscillator `respiration.py` implements. Cite the version: v1 had a different title.

The tract has a fixed part and a moving part:

- **Nelson, B. S., Beckers, G. J. L. & Suthers, R. A., J. Exp. Biol. 208:297–308 (2005)**
  ([10.1242/jeb.01378](https://doi.org/10.1242/jeb.01378)) — syrinx replaced by a loudspeaker
  and swept 0.5–11 kHz. Eastern towhee resonances ~2.0 and ~5.5 kHz against 1.88 and 5.67 kHz
  predicted for a stopped tube of 45 mm. Beak gape does **not** shift resonances below 4 kHz, so
  modelling gape as a formant would be wrong. **Scope correction:** the regression
  `A = −5 + 32·log₁₀(B)` (A in dB, B in mm, 0–11 mm tested) is reported **at 6.5 kHz only**, not
  as a law across 4–7.5 kHz. Treating it as a broadband high-shelf is our extrapolation.
- **Riede, T., Suthers, R. A., Fletcher, N. H. & Blevins, W. E., PNAS 103:5543–5548 (2006)**
  ([10.1073/pnas.0601262103](https://doi.org/10.1073/pnas.0601262103)) — songbirds actively tune
  the oropharyngeal-esophageal cavity to track f0 (1.5 → 5 kHz within a syllable as volume goes
  2.0 → 0.6 ml), modelled Q ≈ 30, accounting for **11–15 dB** of f0-to-harmonic difference
  (**[was wrong]**: previously "11–14 dB"). Northern cardinal tracheal resonances ≈ 2, 5, 8,
  12 kHz — **note that is not literally a 1:3:5:7 series** (1:3:5:7 of 2 kHz is 2/6/10/14). The
  odd-harmonic comb is justified by the stopped-quarter-wave physics, not by an exact ratio
  match here. **This is why §8.1's f0-tracking band is kept rather than replaced** — and why a
  fixed comb is added beside it.
- Riede, T. & Suthers, R. A., *Vocal tract motor patterns and resonance during constant
  frequency song: the white-throated sparrow*, J. Comp. Physiol. A 195:183–192 (2009)
  ([10.1007/s00359-008-0397-0](https://doi.org/10.1007/s00359-008-0397-0)) — trachea 3.4–3.8 cm,
  first resonance ≈ 2.2 kHz (second ≈ 6.6 kHz), the first sitting ~20 dB below the moving OEC
  peak.
- Fletcher, N. H., Riede, T. & Suthers, R. A., *Model for vocalization by a bird with
  distensible vocal cavity and open beak*, JASA 119:1005–1011 (2006)
  ([10.1121/1.2159434](https://doi.org/10.1121/1.2159434)); Fletcher, N. H. & Tarnopolsky, A.,
  *Acoustics of the avian vocal tract*, JASA 105:35–49 (1999)
  ([10.1121/1.424620](https://doi.org/10.1121/1.424620));
  **Kazemi, A., Kesba, M. & Provini, P.**, J. R. Soc. Interface 20:20220728 (2023)
  ([10.1098/rsif.2022.0728](https://doi.org/10.1098/rsif.2022.0728)) — 3-D FEM of a real house
  sparrow tract. **[was wrong]** this repo wrote "Kazemi, Riede et al."; **Riede is not an
  author**.
- Nowicki, S., Nature 325:53–55 (1987)
  ([10.1038/325053a0](https://doi.org/10.1038/325053a0)) — heliox: harmonics that appear in
  He–O₂ are suppressed in air regardless of absolute frequency. The original proof that the
  filter is a filter.
- Ohms, V. R., Snelderwaard, P. Ch., ten Cate, C. & Beckers, G. J. L., *Vocal tract articulation
  in zebra finches*, PLOS ONE 5:e11923 (2010)
  ([10.1371/journal.pone.0011923](https://doi.org/10.1371/journal.pone.0011923)) —
  **[was wrong]** this paper reports gape as a passive filter **emphasising energy above
  ~5 kHz**; it does not report a gape–f0 correlation, and notes that high notes are not always
  sung with a large gape.
- Ohms, V. R., Beckers, G. J. L., ten Cate, C. & Suthers, R. A., J. Exp. Biol. 215:85–92 (2012)
  ([10.1242/jeb.064717](https://doi.org/10.1242/jeb.064717)) — monk parakeet; trachea shortens
  9–44 % during calls. Every number in docs/15 §4 verified verbatim against this paper.
- Podos, J., Southall, J. A. & Rossi-Santos, M. R., *Vocal mechanics in Darwin's finches:
  correlation of beak gape and song frequency*, J. Exp. Biol. 207:607–619 (2004)
  ([10.1242/jeb.00770](https://doi.org/10.1242/jeb.00770)) — gape correlates with song
  frequency. **[was wrong]** the **trill-rate / frequency trade-off** is a different paper:
  Podos, Nature 409:185–188 (2001)
  ([10.1038/35051570](https://doi.org/10.1038/35051570)).
- Laje, R. & Mindlin, G. B., *Modeling source-source and source-filter acoustic interaction in
  birdsong*, Phys. Rev. E 72:036218 (2005)
  ([10.1103/PhysRevE.72.036218](https://doi.org/10.1103/PhysRevE.72.036218)) — **[was wrong]**
  the title in earlier drafts was not the paper's. Subharmonics attributed to syringeal
  nonlinearity can instead come from the two sides interacting through a shared trachea; and
  the low-frequency inertive limit gives the tract input as √ps · y. Follow-up on an oscine:
  Laje, R., Sciamarella, D., Zanella, J. & Mindlin, G. B., *Bilateral source acoustic
  interaction in a syrinx model of an oscine bird*, Phys. Rev. E 77:011912 (2008)
  ([10.1103/PhysRevE.77.011912](https://doi.org/10.1103/PhysRevE.77.011912)). **These two, not
  Sitt 2008 / Amador 2008, are where period doubling and chaos live in this lineage** — the
  isolated 2-D oscillator cannot be chaotic (Poincaré–Bendixson).
- Suthers, R. A., Nature 347:473–477 (1990)
  ([10.1038/347473a0](https://doi.org/10.1038/347473a0)); Goller, F. & Suthers, R. A.,
  J. Neurophysiol. 75:867–876
  ([10.1152/jn.1996.75.2.867](https://doi.org/10.1152/jn.1996.75.2.867)) **and** 76:287–300
  ([10.1152/jn.1996.76.1.287](https://doi.org/10.1152/jn.1996.76.1.287)), both 1996 — the two
  syringeal sides are independently controlled. Two separate papers; cite both.
- Elemans, C. P. H., Zaccarelli, R. & Herzel, H., *Biomechanics and control of vocalization in a
  non-songbird*, J. R. Soc. Interface **5**:691–703 (**2008**)
  ([10.1098/rsif.2007.1237](https://doi.org/10.1098/rsif.2007.1237)) — the ring-dove two-mass
  membrane model of docs/15 §2. **[was wrong]** this repo cited it as 2009, vol. 6, pp. 491–506;
  year, volume and pages were all wrong. The model is the **Ishizaka & Flanagan (1972)** two-mass
  lineage ([10.1002/j.1538-7305.1972.tb02651.x](https://doi.org/10.1002/j.1538-7305.1972.tb02651.x)),
  not Titze's mucosal-wave lineage as docs/21 §21.1 says.

Habitat, deliberately **not** fitted:

- Slabbekoorn, H., Ellers, J. & Smith, T. B., The Condor 104:564–573 (2002)
  ([10.1093/condor/104.3.564](https://doi.org/10.1093/condor/104.3.564)); Nemeth, E.,
  Dabelsteen, T., Pedersen, S. B. & Winkler, H., JASA 119:620–626 (2006)
  ([10.1121/1.2139072](https://doi.org/10.1121/1.2139072)); Dabelsteen, T., Larsen, O. N. &
  Pedersen, S. B., JASA 93:2206–2220 (1993)
  ([10.1121/1.406682](https://doi.org/10.1121/1.406682)) — reverberation is part of the received
  signal. Kept as a post-process outside the fitted parameters: xeno-canto recordings already
  contain the recordist's habitat, so fitting reverb against them would double-count it — and
  the dry-vs-reverberant mismatch inflates our descriptor distance on its own.
  **Unverified:** the "~10 dB/100 m at 1 kHz" excess-attenuation figure could not be tied to a
  specific table in these three; treat it as a general figure from this literature.
- Farnell, A., *Designing Sound* (MIT Press 2010, procedural birds) · hvcc —
  [github.com/Wasted-Audio/hvcc](https://github.com/Wasted-Audio/hvcc)
- DDSP — Engel et al., ICLR 2020, [arXiv:2001.04643](https://arxiv.org/abs/2001.04643) ·
  Tone Transfer — [sites.research.google/tonetransfer](https://sites.research.google/tonetransfer)
- RAVE — Caillon & Esling, [arXiv:2111.05011](https://arxiv.org/abs/2111.05011) ·
  [github.com/acids-ircam/rave](https://github.com/acids-ircam/rave).
  Both DDSP and RAVE are rejected for this project — see docs/21 §21.4.
- Windytan, *Speech to birdsong conversion* ([windytan.com](https://www.windytan.com), 2021)
- FinchGPT — Kobayashi et al., [arXiv:2502.00344](https://arxiv.org/abs/2502.00344) (preprint) ·
  Lostanlen, V., *Towards differentiable motor control of bird vocalizations*, VIHAR 2024
  ([HAL hal-04660514](https://hal.science/hal-04660514), extended abstract)

## Sequence models over types

- Jin, D. Z. & Kozhevnikov, A. A., *A compact statistical model of the song syntax in Bengalese
  finch*, PLOS Comp. Biol. 7:e1001108 (2011)
  ([10.1371/journal.pcbi.1001108](https://doi.org/10.1371/journal.pcbi.1001108); preprint
  [arXiv:1011.2998](https://arxiv.org/abs/1011.2998)) — transition structure depends on repeat
  count, so first-order Markov is not enough.
- Lu, J., Surendralal, S., Bouchard, K. E. & Jin, D. Z., J. Neurosci. 45:e0522242024 (2025)
  ([10.1523/JNEUROSCI.0522-24.2024](https://doi.org/10.1523/JNEUROSCI.0522-24.2024)) —
  **[was wrong]** the paper does not say POMMs *beat* HMMs. It says "HMMs offer no clear
  advantage over POMMs and may be unnecessarily more complex". The argument is parsimony plus a
  mapping onto HVC syllable chains. First author's initial is J, not K.
- Sharma, P., Gero, S., Payne, R., Gruber, D. F., Rus, D., Torralba, A. & Andreas, J., Nature
  Communications 15:3617 (2024)
  ([10.1038/s41467-024-47221-8](https://doi.org/10.1038/s41467-024-47221-8)) — sperm-whale codas
  factorised combinatorially. **[was wrong]** "156-unit alphabet" is not in the paper; Fig. 3
  reports **at least 143** frequently realised combinations, against ~21 previously known coda
  types.
- Patel-Grosz, P., Mascarenhas, S., Chemla, E. & Schlenker, P., *Super Linguistics: an
  introduction*, Linguistics and Philosophy 46:627–692 (2023)
  ([10.1007/s10988-022-09377-8](https://doi.org/10.1007/s10988-022-09377-8)) — cite this for the
  methodological programme only. **[was wrong]** the song-syntax / call-meaning asymmetry
  docs/03 attributes to it is our own synthesis of the empirical literature.

## Web stack

- Threlte — [threlte.xyz](https://threlte.xyz) (Svelte wrapper for Three.js)
- Meyda — [meyda.js.org](https://meyda.js.org) (real-time audio features)
- pitchy — [github.com/ianprime0509/pitchy](https://github.com/ianprime0509/pitchy) (fast pitch
  detection)
- BirdNET browser demo — [birdnet.cornell.edu/demo](https://birdnet.cornell.edu/demo)
  (client-side TF.js proof)
- sveltekit-sse — [github.com/razshare/sveltekit-sse](https://github.com/razshare/sveltekit-sse) ·
  LiveKit — [livekit.io](https://livekit.io)

## Datasets

- [xeno-canto.org](https://xeno-canto.org) (REST API, per-file CC licenses) ·
  [macaulaylibrary.org](https://www.macaulaylibrary.org)
- Bengalese Finch Song Repository — [vocalpy.org/bfsongrepo](https://vocalpy.org/bfsongrepo)
- 887 isolated zebra finch syllables — Zenodo
  [10.5281/zenodo.5545872](https://doi.org/10.5281/zenodo.5545872)
- iNatSounds — Chasmai, M., Shepard, A., Maji, S. & Van Horn, G., *The iNaturalist Sounds
  Dataset*, NeurIPS 2024 Datasets & Benchmarks
  ([arXiv:2506.00343](https://arxiv.org/abs/2506.00343), preprint posted after the
  presentation)
- NBM (nocturnal bird migration) — Airale, L., Pajot, A. & Linossier, J., Scientific Data
  13:925 (2026) ([10.1038/s41597-026-07176-5](https://doi.org/10.1038/s41597-026-07176-5)).
  **[was wrong]** the live dataset (Zenodo 15655748) is **CC BY-NC-ND 3.0**, not CC BY 4.0. The
  ND term matters for an ingest pipeline; check it before wiring the adapter.
- NIPS4Bplus — Morfi, V., Bas, Y., Pamuła, H., Glotin, H. & Stowell, D., PeerJ Computer Science
  5:e223 (2019) ([10.7717/peerj-cs.223](https://doi.org/10.7717/peerj-cs.223))
- Chronister, L. M., Rhinehart, T. A., Place, A. & Kitzes, J., Ecology 102:e03329 (2021)
  ([10.1002/ecy.3329](https://doi.org/10.1002/ecy.3329)) — time-frequency annotations for
  segmenter validation
- A2O — Roe, P. et al., *The Australian Acoustic Observatory*, Methods Ecol. Evol. 12:1802–1808
  (2021) ([10.1111/2041-210X.13660](https://doi.org/10.1111/2041-210X.13660))
