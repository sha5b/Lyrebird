# Birdy — Session Handoff (2026-07-29)

**What this session did:** turned the galaxy from a visualization driven by render-parameter
jitter into a measurement instrument: real-data clouds, the learned embedding as the display
space, live novelty detection, and label-free structure discovery. Full evidence record:
[`docs/10-real-data-galaxy.md`](docs/10-real-data-galaxy.md). Contract amendments:
`docs/08-implementation.md` §8.3/§8.5. The plan that was executed:
`~/.kimi-code/sessions/wd_birdy_51d52dc1b84f/.../plans/huntress-nova-silver-surfer.md`.

## Shipped, with the headline numbers

| Phase | What changed | Key measurement |
|---|---|---|
| 1. Measured clouds | `typing.json` per store; syllable-level galaxy points; `corpus.measured_corpus` renders real member realisations; jitter only for hand-authored species | 47 185/47 185 observations typed; knot radius now varies per type (0.049–0.296 measured vs 0.023–0.150 jitter) |
| 2. Embedding galaxy | `build --space embed` runs projection+clustering on the critic's 32-d embedding; ridge 28→32 map shipped for the browser | subset purity 70.9 % → 90.9 %; map gate **0.8585** median cosine on 117 held-out recordings (accepted) |
| 3. Live novelty | `novel` flag at `/api/ingest`; `grow` founds "unheard syllable" knots at quorum (≥8 coherent) instead of force-assigning | threshold recalibrated 0.1048 → 0.1558: store-wide false flags **29.8 % → 5.6 %**; held-out-species ROC AUC 0.596 (honest, weaker than the 9 k store's 0.825 — see docs/10 §10.3) |
| 4. Label-free discovery | `learn_unlabelled` (U* candidate types), `mine_chunks`, `relations.py` → `relations.json`, `expand` command + `/api/expand` | relabel-recovery 97.4 % inherited / 65.2 % correct species; chunks: great-tit alternation, chickadee ABA, **0 in shuffled control**; relations: cuckoo congeners #1, zosterops #2 |
| 5.2 Learned inverse | `inverse.py` built, trained on 150 k free pairs, pre-registered bake-off on 24 real types | **FAILED the ship rule**: cosine 0.737 vs 0.734 (pass), time 0.2 s vs 0.2 s (the 2× speedup never existed — descent is ~2 ms/render). Stays experimental, not wired in |

## Current state

- **Store of record:** `pipeline/out/harvest-gan` — 47 185 syllables, 21 species, all with
  mel patches + descriptors + embeddings (`embeddings.f32`) + `typing.json`.
  `out/harvest` (39 989, 23 species, no patches) is the pre-embedding store — **never delete
  either** (docs/09 §9.4).
- **Assets:** `app/static/birdy/` is an embed-space galaxy (375 clusters × 32-d,
  `vector32` centroids, `embedding` block in `feature-space.json`, `relations.json`).
  A final learn+build was running at handoff time to fold chunks + relations in — check
  `manifest.json`'s `builtAt`/`space`.
- **Critic:** `out/critic.pt` trained on 19 of the 21 store species;
  `out/critic-novelty.json` recalibrated this session (5 % FPR by construction).
- **Two sessions work in this repo.** This session owns **pipeline + asset builds**; the
  other session owns **the app UI** (it deleted FitMonitor/Island* and added
  SpeciesPicker). Uncommitted Phase-3 app-side leftovers from this session: `pipeline.ts`
  status/ingest types + an "unheard syllables" block in `+page.svelte` — keep or drop.

## Open items (docs/10 §10.6 has the full list)

1. **Type coverage 70 %** — `cluster_plan`'s unlabelled allowance shrank when all field
   points became typed; re-tune k for the typed regime (110 types have no cluster and
   cannot light or label).
2. **Critic retrain on the 47 k store** with a proper species holdout, then the full
   re-derivation (critic train → embed → learn --embed-typing → build). The current critic
   predates the store's growth; doc 09's alternation was never run either.
3. **`expand` has only been dry-run** — a real run spends xeno-canto rate-limit budget
   (targets today: `strix_seloputo`, `zosterops_flavilateralis`).
4. **App-side pieces waiting on the other session:** relations overlay from
   `relations.json`, "what comes next" from `grammar.chunks`, novelty branch in the
   translator ("unheard syllable — no documented function"), activation via the shipped
   28→32 map (code exists in `features.ts`, gated on `mapQuality.accepted`).

## Next-time questions, researched

### "Identify songs in new, unseen data" — without a GAN

Two different problems hide in that sentence:

- **Species/song identification in unseen recordings** — solved problem, use a foundation
  model, no training needed: [Perch 2.0](https://arxiv.org/html/2508.04665v1) (Apache 2.0,
  14 597 species) embeddings + linear probes are SOTA for few-shot transfer, [even
  cross-taxa to underwater](https://arxiv.org/html/2512.03219v1) (Dec 2025). BirdNET is
  CC BY-NC-SA — non-commercial only. [NatureLM-audio](https://pdf.arxiv.org/pdf/2411.07186)
  adds text-promptable zero-shot ("does this recording contain a song with X?").
  Comparative review: [Foundation Models for Bioacoustics](https://ui.adsabs.harvard.edu/abs/2025arXiv250801277S/abstract).
  Integration path for Birdy: server-side Perch embeddings of ingested audio → projected
  next to our own 32-d space (or distilled into it via the same ridge-map trick), giving
  species labels to `unlabelled` arrivals the critic flags novel. This directly upgrades
  the Phase-4 pseudo-species into named birds.
- **Song-*type*/motif discovery in unseen data** (what Birdy already does at syllable
  level): the project's own critic embedding + `mine_chunks` is the in-house route.
  External references that validate the approach: [AVN](https://pmc.ncbi.nlm.nih.gov/articles/PMC11370480/)
  (syllable segmentation + labelling that transfers across colonies without retraining),
  TweetyBERT (self-supervised transformer for birdsong annotation),
  [unsupervised repertoire-size estimation](https://arxiv.org/pdf/2303.10678.pdf), and
  near-expert [semi-supervised segmentation with very few labels](https://dael.euracoustics.org/confs/fa2023/data/articles/000897.pdf).
  Song-level = run the existing machinery on bout sequences (type-id strings) instead of
  syllables; a "song type" is a cluster of similar sequences (edit distance / DTW over
  type ids), novelty-gated the same way as syllables.

### "Do we need more models than the syrinx? Do birds differ that much?"

Yes, birds differ anatomically — and the same modelling family covers it, which is the
good news:

- **Syrinx anatomy varies by taxon**: tracheal / bronchial / tracheobronchial; one sound
  source (parrots, pigeons — single membrane pair), two independent sources (oscine
  songbirds — duplex labia, 4+ muscle pairs), even **three** (tracheophone suboscines).
  [Suthers 2004 review](https://pubmed.ncbi.nlm.nih.gov/15313772/),
  [respiratory contributions review 2025](https://royalsocietypublishing.org/rstb/article/380/1920/20230431/109730).
  So per-taxon parameterisation is real: doves regulate f0 by air-sac pressure on
  membranes, parrots articulate with the tongue (the doc-04 "parrot mode"), songbirds do
  rapid independent two-sided FM.
- **But the Mindlin–Laje low-dimensional model is the across-species framework**: fitted
  to zebra finch, canary, chingolo/rufous-collared sparrow, with automatic gesture
  inversion from recordings ([Boari et al. 2015](https://pmc.ncbi.nlm.nih.gov/articles/PMC4737419/))
  and a maintained package ([saguileran/birdsongs → WaveSongs](https://github.com/saguileran/birdsongs))
  that fits xeno-canto audio with <10 % error. Birdy's two-voice `two:` flag, tracheal
  comb, `noise`/`rough` axes are exactly these degrees of freedom. The honest per-species
  knob set is: number of sources, membrane-vs-labia regime, tract anatomy — parameter
  choices inside the physical family, not new models.
- **Neural alternatives exist and trade interpretability for fidelity**:
  [DDSP for birdsong](https://hal.science/hal-04660514v2/document) (Lostanlen VIHAR 2024 —
  differentiable decoder, unsupervised), neural codecs, diffusion. This project's own
  measurements (docs/09 §9.7/9.8, docs/10 §10.5) say: keep the physical generator (it's
  bird-validated and every downstream feature needs interpretable parameters), spend
  neural effort on analysis. A DDSP/RAVE "signature voice" for one enrolled bird remains
  a legitimate stretch goal — as an additional renderer per species, selected in the
  inventory, not a replacement.

**Recommended next-time order:** (a) critic retrain + full re-derivation; (b) Perch-2.0
server-side species labelling for novel/unlabelled arrivals; (c) song-level type discovery
(sequence clustering over type-id bouts); (d) cluster_plan re-tune; (e) only then consider
per-taxon synthesis variants (dove membrane, parrot formant bank) — each gated by the same
pre-registered bake-off discipline as everything else this session.
