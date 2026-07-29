# 7. Key References

## Decoding

- Rutz et al., *Using machine learning to decode animal communication*, Science 2023
  (DOI 10.1126/science.adg7314)
- Perch / Perch 2.0 — github.com/google-research/perch · arXiv:2508.04665 (Apache 2.0)
- BirdNET — github.com/birdnet-team/BirdNET-Analyzer (CC BY-NC-SA)
- AVES — arXiv:2210.14493 · BirdMAE — arXiv:2504.12880 · avex —
  github.com/earthspecies/avex (MIT)
- NatureLM-audio — arXiv:2411.07186
- Suzuki, Wheatcroft & Griesser, Nature Comms 2016 (great tit ABC-D compositionality)
- Griesser 2008, Current Biology (Siberian jay referential alarms)
- Freeberg et al. 2003 (chickadee combinatorial syntax)
- BioCPPNet — github.com/earthspecies/cocktail-party-problem
- BirdSet — arXiv:2403.10380 · BEANS — github.com/earthspecies/beans · DCASE Task 5
- Rhinehart et al. 2020 (mic-array localization)

## Embeddings & visualization

- Sainburg, Thielk & Gentner, PLOS Comp Biol 2020 (10.1371/journal.pcbi.1008228)
- Goffinet et al., eLife 2021 (VAE+UMAP vocal latent spaces)
- Google Bird Sounds — github.com/googlecreativelab/aiexperiments-bird-sounds
  (Apache 2.0)
- TensorFlow Embedding Projector — projector.tensorflow.org
- Apple Embedding Atlas — github.com/apple/embedding-atlas (MIT)

## Synthesis

- Mindlin & Laje, *The Physics of Birdsong* (Springer 2005)
- Amador & Mindlin 2021, Front. Neurosci. — full syrinx ODE published
- Amador et al., Nature 2013 — synthetic song fools HVC neurons
- Boari et al. 2015 — automatic gesture inversion (audio → pressure/tension curves)
- Implementations: zekearneodo/syrinxsynth · saguileran/birdsongs
- Beckers et al., PNAS 2003 — pure-tone birdsong by resonance filtering
- Beckers et al., Current Biology 2004 — parrot lingual formants

### Naturalness — what §8.1a is built on

Validation that this model class is enough:

- **Bistel, Amador & Mindlin, Phys Rev E 109:054410 (2024)** — *Response of wild songbirds
  to songs synthesized with a low-dimensional model.* 256 playback tests, 26 wild
  rufous-collared sparrows, 15 sites: **no significant difference** between responses to
  real and to synthetic song, while heterospecific song evoked none. The strongest possible
  realism test, and this architecture passes it. The reason Birdy stays procedural.

Spectral richness comes from `beta`, not from the filter:

- **Sitt, Amador, Goller & Mindlin, Phys Rev E 78:011905 (2008)** — *Dynamical origin of
  spectrally rich vocalizations in birdsong.* Oscillations born in a saddle-node-on-a-limit-
  cycle are pulse-like and harmonically dense; those born in a Hopf are tonal. The spectral
  content index (SCI = spectral centroid ÷ f0) is a function of `beta` alone and is invariant
  to `gamma`. This is the finding §8.1a's `gammaScale` acts on.
- Sitt et al., Phys Rev E 81:031927 (2010) — *Physiologically driven avian vocal
  synthesizer.* Fits `gamma` from two (f0, SCI) points; reports `d_pitch` ≈ 0.15 and
  `d_SCI` ≈ 0.26 as the state of the art. Worth reading against our own numbers: our F0
  error is far *better* than theirs and our SCI error was far worse, which is what
  identified the problem.
- Perl, Arneodo, Amador, Goller & Mindlin, Phys Rev E 84:051909 (2011) — `chi^2(gamma)`
  fit over 28 segments → `gamma = 24000`, the value our table is measured at.
- Boari, Perl, Amador, Margoliash & Mindlin, J Neurophysiol 114:2912 (2015) — the
  production pipeline is a nearest-neighbour lookup in a precomputed `(alpha, beta, f0, SCI)`
  table, not an optimiser. Code + table: github.com/kylerbrown/mindlin_auto

Noise belongs on tension, and is required:

- **Amador & Mindlin, Front Neurosci 15:647978 (2021)** — matching the fundamental and the
  filters "was not enough" to drive selective HVC neurons; noise on `beta` (labial tension)
  had to be added, and an *intermediate* magnitude scored best. Directly why §8.1a's `rough`
  perturbs tension rather than pressure or the output.
- Riede & Goller — *Peripheral mechanisms for vocal production in birds*: modulation below
  80 Hz is respiratory, 80–250 Hz syringeal. Sets `ROUGH_LP_HZ = 140`.
- Chen et al., PLOS ONE 2013 — rendition-to-rendition f0 and amplitude are near-uncorrelated
  (R² ≈ 0.03), so independent output jitter and shimmer would be the wrong model.
- Fee, Shraiman, Pesaran & Mitra, Nature 395:67 (1998) — period doubling, mode locking and
  chaos in the excised syrinx.
- Zollinger, Riede & Suthers, J Exp Biol 211:1978 (2008) — prevalence in real song:
  8.5 % of mockingbird syllables show nonlinear phenomena (chaos 6.7 %, biphonation 4.3 %,
  subharmonics 1.3 %); frequency jumps 45–450 Hz. Counterexample worth knowing:
  Zollinger et al., J Neurosci 30:13246 (2010) — adult zebra finches *avoid* subharmonics.
  So nonlinearity must be fitted per syllable, never enabled globally.

The tract has a fixed part and a moving part:

- **Nelson, Beckers & Suthers, J Exp Biol 208:297 (2005)** — syrinx replaced by a
  loudspeaker and swept 0.5–11 kHz. Eastern towhee resonances ~2.0 and ~5.5 kHz against
  1.88 and 5.67 kHz predicted for a stopped tube of 45 mm. Also: beak gape does **not**
  shift resonances below 4 kHz — it is a high-shelf on 4–7.5 kHz, `A = −5 + 32·log(B)`, so
  modelling gape as a formant would be wrong.
- **Riede, Suthers, Beckers & Nelson, PNAS 103:5543 (2006)** — songbirds actively tune the
  oropharyngeal-esophageal cavity to track f0 (1.5 → 5 kHz within a syllable as volume goes
  2.0 → 0.6 ml), modelled Q ≈ 30, accounting for 11–14 dB of f0-to-harmonic difference.
  Cardinal tracheal resonances ≈ 2, 5, 8, 12 kHz (1:3:5:7). **This is why §8.1's
  f0-tracking band is kept rather than replaced** — and why a fixed comb is added beside it.
- Riede & Suthers, J Comp Physiol A 195:183 (2009) — white-throated sparrow trachea
  3.4–3.8 cm, first resonance ≈ 2.2 kHz sitting ~20 dB below the moving OEC peak.
- Fletcher, Riede & Suthers, JASA 119:1005 (2006); Kazemi, Riede et al., J R Soc Interface
  20:20220728 (2023) — FEM of a real house sparrow tract.
- Nowicki, Nature 325:53 (1987) — heliox: harmonics that appear in He–O₂ are suppressed in
  air regardless of absolute frequency. The original proof that the filter is a filter.
- Laje & Mindlin, Phys Rev E 72:036218 (2005) — source–source and source–filter coupling;
  subharmonics attributed to syringeal nonlinearity can instead come from the two sides
  interacting through a shared trachea.

Habitat, deliberately **not** fitted:

- Slabbekoorn et al., Condor 104:564 (2002); Nemeth et al., JASA 119:620 (2006);
  Dabelsteen et al., JASA 93:2206 (1993) — reverberation is part of the received signal, and
  forest excess attenuation runs ~10 dB/100 m at 1 kHz. Kept as a post-process outside the
  fitted parameters: xeno-canto recordings already contain the recordist's habitat, so
  fitting reverb against them would double-count it — and the dry-vs-reverberant mismatch
  inflates our descriptor distance on its own.
- Farnell, *Designing Sound* (procedural birds) · hvcc — github.com/Wasted-Audio/hvcc
- DDSP — github.com/magenta/ddsp · Tone Transfer — sites.research.google/tonetransfer
- RAVE — github.com/acids-ircam/rave
- Windytan, *Speech to birdsong conversion* (windytan.com, 2021)
- FinchGPT — arXiv:2502.00344 · Lostanlen, VIHAR 2024 (differentiable syrinx)

## Web stack

- Threlte — threlte.xyz (Svelte wrapper for Three.js)
- Meyda — meyda.js.org (real-time audio features)
- pitchy — github.com/ianprime0509/pitchy (fast pitch detection)
- BirdNET browser demo — birdnet.cornell.edu/demo (client-side TF.js proof)
- sveltekit-sse — github.com/razshare/sveltekit-sse · LiveKit — livekit.io

## Datasets

- xeno-canto.org (REST API, per-file CC licenses) · macaulaylibrary.org
- Bengalese Finch Song Repository — vocalpy.org/bfsongrepo
- 887 isolated zebra finch syllables — Zenodo 5545872
