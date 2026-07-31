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
| aug (EQ 3 dB + MixStyle 0.2) | +0.283 | +0.442 | 0.988 | 0.906 | 0.456 |
| aug + w_record 0.05 | +0.191 | +0.305 | 0.984 | 0.761 | 0.293 |
| aug + w_record 0.1 | +0.243 | +0.399 | 0.989 | 0.843 | 0.288 |
| aug + w_record 0.3 | +0.110 | +0.172 | 0.862 | 0.199 | 0.119 |

**Verdict: no adoption.** The four gates, in order: augmentation alone is perfectly
species-safe and moves the recordist needle *not at all* (−0.7 % relative — the
simulated ±3 dB channel simply does not span how much real channels differ). The
adversarial head does move it, and the trade is almost perfectly linear in log
weight: −33 % recordist at w 0.05 (but species lift −29 %, accuracy −14.7 points),
−61 % at w 0.3 (with the embedding destroyed: species accuracy 0.199, realism AUC
0.862). No swept weight buys the required −30 % recordist while holding species
within the gates. **You can purchase recorder invariance with species information at
roughly 1:1 — and nothing in this recipe makes it cheaper than that.** The knobs
stay at zero; the machinery stays in critic.py for the next attempt.

What the sweep teaches for that attempt (recorded, not pursued post-hoc): (a) the
recordist confound on this corpus may be partially *species-correlated* — an
adversarial target of *recording within species* (channel identity with the bird
factored out by construction) is the cleaner label and was not tried; (b) w in
0.01–0.03 would land on the same trade line, and the gates say where that line must
move to, not just where to step on it; (c) augmentation failing *completely* says
the discriminating channel cue is not band-response-shaped — the per-recording
signatures (noise floor shape, codec, mic proximity) live elsewhere in the patch.

## 17.4 The AVEX experiment (same day): data, not mechanism — confirmed

The literature's answer held. Three arms on the **12** species present in BOTH
debug stores (iNat soundscape vs xeno-canto focal — the overlap is 12, not 13:
`horornis_diphone` has zero observations in the xeno store), same seed, same fake
side, cross-domain species retrieval as the measure (chance 0.083):

| arm | cross-domain retrieval | held-out realism AUC | species acc |
|---|---|---|---|
| A — single domain (iNat only) | 0.360 | 0.952 | 0.894 |
| **B — naive merge** | **0.504 (+14.4 pts)** | 0.964 | 0.923 |
| C — merge + cross-domain contrastive positives | 0.638 (+27.8) | 0.940 | 0.939 |

Pre-registered gate (≥ +10 pts cross-domain, AUC no drop, acc within 2): **B
passes — the naive merge alone buys real invariance.** C buys another +13.4 on top
and is the best embedding on every geometry measure, but drops AUC 0.012 — the
gate as registered fails it (whether 0.012 is noise on a 3-species holdout is a
genuine question; the honest move is a bigger C re-test, not a post-hoc pass).
Supporting detail worth keeping: the `domain` grouping's kNN lift is ≈ 0 in all
arms — at neighbour level the domains interleave in every critic, so the confound
lives in the *retrieval gap*, not in local geometry; and recordist lift *rises*
slightly with diversity (more recordist classes), so retrieval, not lift, is the
right verdict metric.

**Consequence: invariance is a data action, not a loss action.** The road is more
genuinely-different domains per species (BirdCLEF/BirdSet/iNat merges), not more
loss engineering. critic.py gained the machinery default-off (`merge_patchsets`,
`PatchSet.domains`, `CriticConfig.cross_domain_positives`, pairing covered by
self-test); the driver is `/tmp/birdy-debug/avex_driver.py`, report
`/tmp/birdy-debug/avex/avex-report.json`.
