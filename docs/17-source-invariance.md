# 17 — Source-invariance: the recorder-invariant critic retrain

docs/14 §14.4 left the pipeline's most honest open measurement: in the critic's 32-d
embedding, `source` (recorded or synthesised — and within recorded, *which* recorder)
is the strongest relation, kNN lift **+0.488** against species' +0.196. Every
consumer of the embedding — typing, the galaxy, relations, novelty, the unknown-bird
pipeline — inherits that confound. The literature is unambiguous that this is a
**training-time** problem (domain-invariant contrastive learning, Moummad et al.
arXiv 2409.08589; impulse-response augmentation + Freq-MixStyle, Morocutti et al.
arXiv 2305.07499; corpus diversity over architecture, AVEX arXiv 2508.11845), and
that no post-hoc fix exists.

**What we cannot do:** convolve with microphone impulse responses — that needs
waveforms, and harvest deletes audio by design. What we have is the (32, 23) log-mel
patch, and a recorder chain's response on a log-mel is *additive, smooth in
frequency, constant within a recording* — simulable exactly in the patch domain.

## 17.1 The recipe (critic.py; all knobs default off = the pre-recipe path)

- **Channel EQ simulation** (`aug_channel_db`): per augmented view, a smooth random
  gain curve across the 23 mel bands (cumulative random walk, peak-normalised to the
  dB budget, mean-removed so it is never a level change) added to the log-mel. This
  *is* a recorder frequency response in this domain.
- **Freq-MixStyle** (`mixstyle_alpha`): pairs of same-species patches from
  *different recordings* swap per-band mean/std with λ ~ Beta(α, α). Same-species
  only, because the invariance being taught is "same bird, other channel" — a
  cross-species partner would teach that one bird's spectrum can wear another's,
  which is a lie, not a nuisance.
- **Recordist-adversarial head** (`w_record`): a linear classifier on the embedding,
  gradient-reversed, trained to name the recordist so the trunk learns to stop
  letting it. Training scaffolding only — nothing ships. Off by default because it
  is the one term that can eat species information (recordist and species correlate
  in any field corpus); it earns its weight in the sweep or stays at zero.
- **The recordist probe** (in the training report): nearest-centroid readout trained
  on seen syllables, scored on unseen ones — the in-report read of the same leak the
  geometry battery measures with kNN lift.
- **`critic groupings`**: the docs/14 geometry battery run directly on a store's
  embeddings, no build — the sweep's verdict instrument.

## 17.2 The pre-registered verdict

Baseline = a retrain on the debug store (37 species, /tmp copy of `out/harvest`) with
the **unchanged** recipe, same seed. Adopt the recipe iff, against that baseline:

1. recordist kNN lift drops ≥ 30 % relative,
2. species kNN lift holds within 10 % relative,
3. realism AUC (held-out species) does not drop,
4. species accuracy does not drop more than 2 points.

A wash or regression is documented here and the recipe stays off.

## 17.3 The numbers

**Baseline** (knobs at zero): realism AUC 0.989 held-out, species accuracy 0.908
(chance 0.038), contrastive top-1 0.793, **recordist probe 0.442 (chance 0.007)**,
novelty ROC 0.754 / TPR 13.0 %. Grouping battery on the stored embeddings:

| grouping | kNN lift |
|---|---|
| species | **+0.429** |
| recordist | **+0.285** |
| country | +0.286 |
| sampleRate | +0.206 |

(The debug store's species still beats its recordist — the gan store's inversion,
+0.488 vs +0.196, is what the production retrain would be judged on. The debug
verdict is about the recipe's *direction*, not the gan numbers.)

**Sweep** (same store, same seed, one knob set at a time):

| run | recordist lift | species lift | realism AUC | species acc | recordist probe |
|---|---|---|---|---|---|
| baseline | +0.285 | +0.429 | 0.989 | 0.908 | 0.442 |
| aug (EQ 3 dB + MixStyle 0.2) | _running_ | | | | |
| aug + w_record 0.05 | _running_ | | | | |
| aug + w_record 0.1 | _running_ | | | | |
| aug + w_record 0.3 | _running_ | | | | |

**Verdict:** _pending the sweep._
