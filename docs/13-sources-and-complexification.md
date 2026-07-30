# Birdy research report: new sources + honest complexification routes

Scope note: I read `docs/07`, `docs/09`, `docs/11` (§11.5–11.6) and `sources.py` first. Everything below excludes the five wired adapters (xeno-canto, Zenodo-XCDC, Internet Archive xccoverbl/warblr/ff1010, Kaggle BirdCLEF, HF BirdSet) and the already-planned Perch labelling route. Links marked (verified) were fetched or confirmed live; a few rest on search-snippet evidence and are flagged.

---

## Deliverable 1 — New audio/data sources

### The headliners

**1. iNatSounds — the single biggest legal variety gain available.** [visipedia/inat_sounds](https://github.com/visipedia/inat_sounds/tree/main/2024) (verified via repo content) · [NeurIPS 2024 paper](https://arxiv.org/html/2506.00343v1). 230,000 audio files, **>5,500 species**, 27,000 recordists, ~131 GB as one freely downloadable archive (22 kHz mono, one file per observation, per-observation CC licences inherited from iNaturalist — filter to CC0/BY/BY-NC like everywhere else). Single-species presence labels (weak, no time-freq boxes). This is the same source Perch 2.0 trains on. Variety: thousands of species Birdy has never seen, and a completely different recording-condition regime (phone mics, opportunistic) — precisely the two axes docs/11 §11.5 says the critic is blind on.
- *Plugs into Birdy:* new adapter in `sources.py` (name `inat-sounds`): stream the archive, licence-filter, decode→describe→delete via `ingest_file`, CREDITS.md row. Direct attack on the 14.8 % novelty TPR: retrain critic, recalibrate novelty per §10.3, re-run the pre-registered numbers.

**2. Tierstimmenarchiv (Animal Sound Archive, Museum für Naturkunde Berlin) via GBIF.** [GBIF dataset](https://www.gbif.org/pl/dataset/b7ec1bf8-819b-11e2-bad2-00145eb45e9a) (verified) · DOI `10.15468/0bpalr`. ~130,000 recordings, ~1,800 bird species, collected since 1951 — the archive Perch 2.0 also trains on. GBIF DwC-A occurrence download is keyless; media URLs per record with **per-record CC licences**. Variety: European/historic/captive recordings — a third archive with a different provenance and era, i.e. exactly the "new microphone, new country" confounder the novelty detector currently fails on.
- *Plugs into Birdy:* `sources.py` adapter `gbif-soundarchives`: GBIF download → multimedia extension → stage+ingest. Same code path generalises to Borror and BioAcoustica (below), so build this as a *generic GBIF-multimedia adapter* with a dataset key, not one adapter per archive.

**3. NBM — Nocturnal Bird Migration dataset.** [Zenodo 14864129](https://zenodo.org/records/14864129) / [15655748](https://zenodo.org/records/15655748) (verified) · [Nature Sci. Data 2026](https://www.nature.com/articles/s41597-026-07176-5) · [arXiv:2412.03633](https://arxiv.org/abs/2412.03633). **CC-BY-4.0**, 38 h, 2,077 files, **13,359 time-frequency-boxed vocalizations from 117 Western-Palaearctic species**. Two wins in one: (a) a genuinely new sound *form* — short nocturnal flight calls, not song — which widens what "a syllable" is in the embedding; (b) human time-freq annotations = free ground truth for evaluating Birdy's hand-written segmenter, which nothing in the current stores provides.
- *Plugs into Birdy:* `sources.py` adapter (Zenodo pattern already exists); boxes let `ingest_file` cut labelled syllables directly. Novelty/typing stores gain a calls-vs-song axis; honesty label stays "unlabelled: real acoustics, no documented function" for anything the fit can't match.

**4. The two lab-bird sets already cited in docs/07 but never wired.** [Bengalese Finch Song Repository](https://vocalpy.org/bfsongrepo) and [887 isolated zebra-finch syllables, Zenodo 5545872](https://zenodo.org/record/5545872). Small, but they carry what no wild archive does: **syllable-level human annotations of complete song bouts from known individuals** — ground truth for the just-shipped song-level type discovery (commit c03bdda) and for grammar measurement. Cost is trivial (Zenodo adapter exists).
- *Plugs into Birdy:* validation stores in `/tmp`, not the production galaxy: check that `song-typing.json` clusters recover human annotation structure. This is a *measurement* source, not a coverage source.

### Second tier — real value, higher cost or narrower

| source | licence / access | size & labels | variety vs cost | plugs into Birdy |
|---|---|---|---|---|
| **A2O — Australian Acoustic Observatory** ([portal](https://acousticobservatory.org/), [MEE paper](https://besjournals.onlinelibrary.wiley.com/doi/10.1111/2041-210X.13660)) | CC-BY, open Ecosounds portal+API, keyless | ~2 PB target, hundreds of sensors, presence-level labels only | Australian endemics + true long-duration soundscapes — a second, far larger XCDC. Cost: high; must pull targeted windows via the Ecosounds API, not bulk | `sources.py` `ecosounds` adapter; feeds novelty controls + soundscape work, **not** typing (same honest scope as XCDC in §11.5) |
| **Borror Lab of Bioacoustics via GBIF** ([dataset](https://www.gbif.org/dataset/f11db245-3f9f-4fc6-a0cc-12b4124d081b), DOI `10.15468/wyz5x9`) | per-record, GBIF download | 40k+ recordings, historic, North-America heavy | 1948–2001 era tape recordings — a fourth provenance regime. Same adapter as Tierstimmenarchiv, so near-zero marginal cost | `gbif-soundarchives` adapter with dataset key |
| **BirdVox family** ([Zenodo 1205569](https://zenodo.org/records/1205569), [5856260](https://zenodo.org/records/5856260); indexed in [open-bioacoustic-benchmarks](https://github.com/jackgle/open-bioacoustic-benchmarks)) | CC-BY, keyless | 60–296 h, NYC rooftop mics, flight calls; species labels partial | Overlaps NBM's role but adds urban-noise conditions and US species. Take NBM first; BirdVox if more call-form data is wanted | Zenodo-pattern adapter; calls-axis for the embedding |
| **NIPS4Bplus** ([PeerJ CS](https://peerj.com/articles/cs-223/)) and **Chronister et al. 2021** ([E&Ecology DOI](https://doi.org/10.1002/ecy.3329)) | CC-BY, keyless | small (hours), **rich time-freq annotations** | not coverage — segmentation/feature *validation* ground truth, same role as item 4 | `/tmp` eval stores; measure segmenter boundary accuracy before touching `extract_syllables` |
| **Individual-ID datasets** ([Zenodo 15054394](https://zenodo.org/records/15054394) — verified) | CC, keyless | ~880 MB; cockatoo, penguin audio + BirdNET/Perch embeddings for 5 species × 10–16 individuals | enables the "which individual" axis (see Deliverable 2a.5). Niche but unique | eval store for an individual-ID probe; honesty label "individual match (statistical, validated on 10–16 birds)" |
| **iNaturalist API live** ([API practices](https://www.inaturalist.org/pages/api+recommended+practices)) | keyless, ~60 req/min, 10k-result cap per query; per-observation CC | ongoing stream vs iNatSounds' Feb-2024 snapshot | targeted top-ups for `expand` (specific missing species), not bulk | `expand` route beside xccoverbl; same decode→describe→delete |
| **freesound.org bird tags** | CC per-file, **OAuth key required**, tag labels not species | large | mostly duplicates the warblr/ff1010 "not our kind of sound" control role. Low priority | skip unless control-set diversity is measured as a bottleneck |

### Dead ends (checked, candidly)

- **Macaulay Library.** No API, no bulk. The [official media-request process](https://support.ebird.org/en/support/solutions/articles/48001064551-using-and-requesting-media) (verified) is a human ticketing system: free for research, but ≤40k assets per request, licence agreement, and *their own page redirects ML researchers to iNaturalist datasets instead*. Scraping violates ToS. The one adjacent asset, [Merlin L48](https://github.com/visipedia/ml48s) (verified), is 129k **spectrogram JPEGs** (not audio) with bounding boxes under a TOU click-through — beautiful labels, but nothing `ingest_file` can eat, and the images-to-patches idea would break the "real and synthetic measured identically" rule from docs/09 §9.3. Verdict: not a source for this pipeline; at most a one-off human-mediated request for a specific enrolled bird.
- **British Library wildlife sounds (BLOWS).** Rights-restricted, listen-online only; licensing is per-use negotiation. Dead end for bulk.
- **MNHN Sonothèque (Paris).** Documented and lovely, but distribution is CD/paywalled; no bulk CC route found. Dead end.
- **BioAcoustica (NHM London).** Real GBIF presence ([dataset](https://www.gbif.org/dataset/30f55c63-a829-4cb2-9676-3b1b6f981567), CC-BY aggregate) but ornithologically thin — it's an insect archive. Skip for birds; one line of config if insects are ever wanted as a "not-a-bird" control stratum.
- **GBIF's xeno-canto mirror** ([dataset](https://www.gbif.org/dataset/b1047888-ae52-4179-9dd5-5448ea342a24)). It's the *same audio* (subset, links back to XC servers). Its actual value is keyless **metadata**: licence filtering, taxonomy, dedupe across sources — worth one utility function in `sources.py`, not an adapter.
- **Arbimon/RFCx public projects.** Audio is visible per public project, but reuse rights are per-project and the [platform ToS](https://rfcx.org/terms-of-service) doesn't grant bulk redistribution. High effort, murky licence — skip.
- **"IaFE"** (from the task brief): I could not identify this — possibly a typo (IBAC? a conflation with the Internet Archive xccoverbl mirror, which is already wired?). Flagging rather than guessing.

### Ranked summary (variety × integration cost)

1. **iNatSounds** — one archive, thousands of new species, new mic regime.
2. **Generic GBIF-sound-archive adapter** (Tierstimmenarchiv first, Borror nearly free after) — third and fourth provenance regimes.
3. **NBM flight calls** — new sound form + annotation ground truth, keyless CC-BY.
4. **bfsongrepo + ZF-887** — nearly free; validates the song-typing that just shipped.
5. **iNat API targeted top-ups** — gives `expand` a keyless route beyond UK species.
6. **A2O/Ecosounds** — soundscape scale; do only when XCDC's role needs growing, and after BirdMixIT (below).
7. BirdVox / NIPS4Bplus / Chronister — small, eval-role.
8. Individual-ID sets — niche enabler for 2a.5.
9. freesound — redundant controls. Skip: Macaulay, BL, Sonothèque, BioAcoustica-birds, Arbimon.

---

## Deliverable 2 — Complexification, honestly ranked

### (a) Analysis

**A1. Perch 2.0 as the second-opinion pseudo-labeller — top pick, but with a discipline warning.** [Perch 2.0 paper](https://arxiv.org/html/2508.04665v1) · [google-research/perch](https://github.com/google-research/perch) + Perch-Hoplite for inference · model on [Kaggle](https://www.kaggle.com/models/google/bird-vocalization-classifier) (TF SavedModel, Apache 2.0). Trained on XC + iNaturalist + Tierstimmenarchiv + FSD50K, ~14.6k species classes. This is the handoff's planned route and the research confirms it's the right one: state of the art on BirdSet/BEANS, and the licence is clean. Prefer it over BirdNET ([CC BY-NC-SA licence](https://github.com/birdnet-team/BirdNET-Analyzer) and weaker transfer scores) for anything that touches shipped assets.
- *Plugs into Birdy:* offline only — new `critic label-novel` command; Perch's logit+embedding for a flagged syllable lands in the store as *metadata*, never as typing ground truth. UI honesty label: "closest documented species (Perch 2.0 inference, unverified)". The discipline: if a Perch label ever becomes a type's identity silently, model error has been laundered into the canonical inventory — the pre-registered-metric discipline dies there.
- Also noted: the same forward pass yields a 1280-d **second embedding** — a cheap external cross-check of the critic's 32-d space ("does Perch's space agree this is novel?"), which is exactly the kind of second opinion docs/11 §11.6 calls a research problem, not a tuning one.

**A2. BirdMixIT source separation before soundscape ingestion.** [arXiv:2110.03209](https://arxiv.org/abs/2110.03209) (Denton et al., Google; Apache 2.0 code in google-research/sound-separation). Unsupervised MixIT separator trained on birdsong; 2026 bioRxiv crow paper uses it off-the-shelf for denoising focal vocalizations. This upgrades XCDC (and eventually A2O) from "novelty controls only" to *usable syllable candidates*: separate → run the existing syllable extractor on stems → type what separates cleanly, keep the rest as controls.
- *Plugs into Birdy:* optional pre-stage inside the Zenodo/Ecosounds adapters (audio still never retained); success measured by the same store metrics — does typing coverage on soundscape-derived syllables beat the controls baseline?

**A3. Self-supervised segmentation (TweetyBERT lineage) — promising, but validate on NBM/bfsongrepo first.** [TweetyBERT](https://www.biorxiv.org/content/10.1101/2025.04.09.648029v1), code [georgevenven/tweety_bert](https://github.com/georgevenven/tweety_bert) (verified) — self-supervised transformer that recovers notes/syllables/phrases, but demonstrated on *canary only*. [AVN](https://avn.readthedocs.io/) ([eLife 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC11370480/)) is zebra-finch-only by design. Neither transfers off the shelf to 35+ wild species. The honest sequence: first *measure* the current hand-written segmenter against NBM's boxes and bfsongrepo's annotations (cheap, items 1.3/1.4); retrain a TweetyBERT-style model only if the measured boundary error is the actual bottleneck.
- *Plugs into Birdy:* `features.py`/`extract_syllables` replacement candidate; any change re-judged by the §9.7 ablation numbers on the fixed store.

**A4. Individual/singer ID.** The [Monash datasets](https://zenodo.org/records/15054394) (verified) exist precisely because BirdNET/Perch embeddings separate individuals of 5 species (10–16 birds each). For Birdy this is the difference between "a bird sang X" and "the *same* bird sang X again" — a translator claim users will immediately ask for.
- *Plugs into Birdy:* critic-space nearest-neighbour over a session's syllables; claim carries "individual match (statistical, small-N validation)" and nothing stronger. Do this only after A1's embedding exists.

**A5. Close the docs/09 §9.7 leftover: use the critic embedding for the galaxy's clustering/projection**, so typing and the 3-D map stop disagreeing about what is near what. Internal, cheap, already written down as open — listed so it stops being invisible.

### (b) Synthesis — per-taxon renderers, what the literature actually specifies

The current synth is the oscine two-labium model (Mindlin–Laje). The literature supports exactly four principled extensions, in this order:

**B1. Finish §9.6 first (respiratory oscillator + ẏ injection).** [Fainstein, Goller & Mindlin, arXiv:2509.11019] — already in-repo as the top open bet; research found nothing that demotes it. It's also the *enabler* for song-level rendering (B4), because cross-syllable timing and attack shape live in respiration, not in the labia.

**B2. Two-voice oscines (biphonation renderer).** The two sides of the oscine syrinx are independently controlled sound sources (Suthers 1990; Greenewalt 1968; lateralization patterns tabulated in [Suthers' review lineage](https://www.sciencedirect.com/topics/immunology-and-microbiology/songbird)); Laje & Mindlin 2005 (already cited) models the coupling through the shared trachea; Zollinger 2008 (already cited) measured 4.3 % biphonation in mockingbird syllables. Implementation is embarrassingly aligned with the codebase: two instances of the existing synth with independent (α, β) gesture streams, summed, with an optional weak shared-trachea coupling term. This is the only structurally honest way to render the biphonation class the fit currently must approximate with one source.
- *Plugs into Birdy:* `syrinx` gets a `voices=2` parameter set; parity tests + tail check per AGENTS.md; new fit axis "second voice present (fitted, not assumed)" per the Zollinger per-syllable rule already in docs/07.

**B3. Per-taxon models — what each taxon needs, per the literature:**
- **Doves/pigeons:** not labia — flow-driven *membrane* oscillation with a strong, fixed tracheal resonance. The full quantitative two-mass model with measured parameters exists: [Elemans et al. 2009, *Biomechanics and control of vocalization in a non-songbird*](https://pmc.ncbi.nlm.nih.gov/articles/PMC2607454/) (ring dove; simulations match in-vivo coos), plus Ballintijn & ten Cate 1998 (heliox test killing the "whistle" hypothesis) and Beckers' dove thesis. Renderer: membrane source at low f0 + fixed stopped-tube tract — simpler than the oscine model, genuinely different parameters.
- **Parrots:** single pair of lateral tympaniform membranes ([Larsen & Goller 1999, via Cambridge excerpt](https://assets.cambridge.org/97805218/29182/excerpt/9780521829182_excerpt.pdf)) — so a *one-source* model — but the perceptual action is **tongue-articulated formants**: Beckers et al. 2004 (already cited) showed parrot vowel-like formants track lingual articulation. Renderer: one source + a moving two/three-formant bank driven by a "tongue" gesture instead of the f0-tracking OEC band.
- **Tracheophone suboscines:** **three sound sources** — the oscine-like labial pair plus a unique tracheal membrane pair ([Garcia et al. 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5599221/)), and crucially the low-dimensional dynamical model already exists in the Mindlin lineage: [Amador & Mindlin 2023, JEB 226:jeb227975](https://journals.biologists.com/jeb/article/226/12/jeb227975/316747/The-dynamics-behind-diversity-in-suboscine-songs) (verified) — "The dynamics behind diversity in suboscine songs." This is a direct, cited extension of the math the synth already implements.
- Reference implementation worth reading (not copying): [WaveSongs](https://github.com/wavesongs) (verified; GPL-3.0) — Aguilera's maintained Python packaging of the Mindlin physical model with gesture inversion. GPL means read-for-understanding only.
- *Plugs into Birdy:* each taxon is a new renderer module beside `syrinx`, selected per species at fit time (never per syllable); the honesty label names the model class ("dove membrane model", "three-source tracheophone model") so the UI claim stays interpretable. Pre-registered judgement: same §9.7 ablation on the fixed store, per-taxon rows.

**B4. Song-level generation from the measured grammar + song types.** With song-typing just shipped, the next step is a sequence model over type-id strings: FinchGPT ([arXiv:2502.00344], already cited) is the template — a small transformer over syllable tokens reproducing zebra-finch syntax. Rendered by chaining fitted syllables with B1's respiratory gaps. The crucial Birdy-specific point: the *generator stays a grammar over physical syllables* — every rendered song remains a list of interpretable parameter vectors, so the hard constraint holds.
- *Plugs into Birdy:* `grammar.chunks` + `song-typing.json` → `song-gen` module → parity-tested renderer; UI label "simulated sequence from measured transition statistics".

### (c) What NOT to do (with evidence)

- **Revisit the realism/GAN objective a third time.** Refuted on two independent stores (§9.7: monotonically harmful in w; §9.8: 38.4→31.9 %). The alternation step is moot while this stands — docs/11 §11.6 already says so. Don't relitigate without a structurally new idea.
- **Any learned *generator* (DDSP/RAVE/diffusion/FinchGPT-as-audio).** Weakest realism evidence in the field, no playback validation, and it breaks the physical-interpretable constraint the galaxy and honesty labels stand on (§9.6's own verdict). RAVE/DDSP stay exactly where docs/07 put them: the one-enrolled-bird stretch goal, quarantined from the synth.
- **Scraping Macaulay.** ToS violation, and Cornell itself redirects ML users to iNatSounds. The legal route (media request) is human-scale, not pipeline-scale.
- **BirdNET/Perch in the browser.** The [birdnet.cornell.edu TF.js demo](https://birdnet.cornell.edu/demo) proves it's possible; it still violates "no learned weights ship to the browser / app works with no Python" and adds megabytes for a claim the honesty rule would have to label "unverified" anyway. Server-side or nothing.
- **Pseudo-labels as ground truth.** The moment a Perch inference becomes a type's identity, the critic's ROC numbers stop meaning anything (training on your own test labels). Metadata, labelled, always.
- **Tuning novelty thresholds across harvest epochs without recalibration** (docs/10 §10.3 — measured that thresholds don't transfer). Any new source ingest → recalibrate, then re-report the pre-registered numbers.
- **Fitting reverb/habitat into synthesis parameters.** docs/07 records why: XC recordings already carry the recordist's habitat; fitting it double-counts. Keep habitat a post-process.
- **Buying BirdCLEF-adjacent "mirror" dumps of xeno-canto from third parties** (various Kaggle re-uploads, HF repacks beyond BirdSet): same audio, worse licence provenance, dedupe hell. The xccoverbl + BirdSet + GBIF-metadata combination already covers this need honestly.

### Suggested order (analysis + synthesis interleaved)

1. iNatSounds + GBIF-archives ingest → critic retrain → novelty recalibration (attacks the 14.8 % TPR directly).
2. Perch 2.0 `label-novel` (handoff route; now with verified model access).
3. B1 respiratory oscillator (already open, unblocks B4).
4. Measure segmenter vs NBM/bfsongrepo ground truth → decide A3.
5. B2 two-voice renderer (fits the existing architecture; measurable).
6. B4 song-level generation; B3 dove renderer as the first per-taxon pilot (simplest anatomy, best-specified model: Elemans 2009).
7. A2 BirdMixIT + A2O soundscapes when call/song coverage saturates; A4 individual ID as the translator's next claim.

**Caveats on verification:** URLs for iNatSounds' README, NBM Zenodo records, the GBIF datasets, TweetyBERT code, WaveSongs, ml48s, and the eBird/Macaulay terms page were fetched or confirmed live today. The A2O Ecosounds API details and Arbimon rights situation were assessed from secondary sources, not probed — worth a `sources list`-style live probe before writing either adapter.