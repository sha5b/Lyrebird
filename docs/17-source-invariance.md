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

## 17.5 Follow-up sweep (pre-registered 2026-07-31, before any run)

§17.3's recorded lead (a): the recordist confound may be partially
species-correlated, so the cleaner adversarial target is **recording within
species** — channel identity with the bird factored out by construction. The
construction (`CriticConfig.record_within_species`, default off): adversarial
classes are *recordings* with ≥ `recordist_min_patches` training patches,
restricted to species holding ≥ 2 such recordings, and each patch's
cross-entropy softmax is **masked to its own species's recordings** — the bird
is given, so species information cannot pay down the loss; only the channel
can. Lead (b) is folded in: weights step the same trade line finer
(0.01–0.1 vs §17.3's 0.05–0.3).

**Baseline caveat:** the learned inventory moved since §17.3 (the Stage-0
learn/respfit/docrefit chain wrote `data/` artefacts), and the synthetic side
is rendered from the inventory as it stands — so §17.3's baseline is *not*
reusable and this sweep re-runs knobs-at-zero as its own baseline. All arms
share one store (a /tmp copy of `out/harvest`, 37 species), one seed (0), one
fake side. Treated arms carry the §17.3 augmentation (EQ 3 dB + MixStyle 0.2),
which §17.3 proved species-safe.

| arm | knobs |
|---|---|
| baseline | all zero |
| ws-0.01 | aug + record-within-species w 0.01 |
| ws-0.03 | aug + record-within-species w 0.03 |
| ws-0.05 | aug + record-within-species w 0.05 |
| ws-0.1 | aug + record-within-species w 0.1 |

**Gates** (same shape as §17.2, judged against this sweep's baseline re-run;
lift numbers from `critic groupings` on the store's embeddings, AUC/accuracy
from the training report):

1. recordist kNN lift drops ≥ 30 % relative,
2. species kNN lift holds within 10 % relative,
3. held-out realism AUC does not drop,
4. species accuracy does not drop more than 2 points.

Adopt the best passing weight iff all four hold; a wash or regression is
documented here and the knob stays at zero.

### 17.5.1 The numbers: NO ADOPTION — the factorization works, the target doesn't reach

Sweep ran 2026-07-31 (driver `/tmp/birdy-inv/sweep.sh`, store a /tmp copy of
`out/harvest`, seed 0, 236 recording classes over 22 species for the head).
Baseline re-run sanity: probe 0.425 / lift +0.277 / species +0.412 / AUC 0.986 /
acc 0.891 vs §17.3's 0.442 / +0.285 / +0.429 / 0.989 / 0.908 — close, not
identical, exactly the fake-side drift the caveat predicted.

| arm | recordist lift | Δrel | species lift | Δrel | AUC held | acc | recordist probe |
|---|---|---|---|---|---|---|---|
| baseline | +0.277 | — | +0.412 | — | 0.986 | 0.891 | 0.425 |
| ws-0.01 | +0.280 | +1 % | +0.438 | +6 % | 0.984 | 0.891 | 0.439 |
| ws-0.03 | +0.273 | −1 % | +0.458 | +11 % | 0.980 | 0.903 | 0.416 |
| ws-0.05 | +0.268 | −3 % | +0.453 | +10 % | 0.982 | 0.886 | 0.393 |
| ws-0.1 | +0.260 | **−6 %** | +0.455 | +10 % | 0.968 | 0.874 | 0.376 |

Gate 1 needs −30 % relative on recordist lift; the whole line buys −6 % (and
w 0.1 already fails gate 3 on its own, AUC 0.968 < 0.986). **No adoption; the
knob stays at zero.** The gates are not the interesting part, though:

- **The factorization works.** Where §17.3's recordist head traded species for
  recordist ~1:1, this head *never touches species* — species lift is flat to
  **up 10 %** at every weight, and contrastive top-1 rises with it (0.766 →
  0.812). Masking the softmax to same-species recordings really does fence
  species information out of the adversarial gradient. As machinery it is
  proven and stays in critic.py, default off.
- **The target doesn't reach the confound.** Removing *within-species* session
  identity barely dents the *recordist* grouping (kNN lift −6 % where the
  in-report probe moves −11 %, both far from −30 %). Reading §17.3 lead (a)
  in reverse: the recordist signal in this embedding is mostly
  *between-species* — each species's recordings come from different people, so
  recordist identity is carried by cross-species structure that a
  within-species target is forbidden to touch. The confound is
  species-correlated exactly as suspected, and that is precisely why a
  species-factored head cannot fix it.
- **The combined verdict of §17.3 + §17.4 + this section is now three-sided:**
  you can buy recordist invariance with species information at 1:1 (recordist
  head), you can buy a sliver of it for free (within-species head, −6 %), or
  you can buy real invariance with *data* (naive domain merge, +14.4 pts
  cross-domain retrieval, gates passed). The loss-engineering road is
  exhausted at both ends; AVEX's answer stands.

## 17.6 The bigger arm-C re-test (pre-registered 2026-07-31, before any run)

§17.4's open question: arm C (merge + cross-domain contrastive positives) was
the best embedding on every geometry measure (+27.8 cross-domain retrieval vs
B's +14.4) but failed its gate on a 0.012 realism-AUC drop measured over a
**3-species holdout** — noise range, not evidence. The recorded honest move
was a bigger re-test, and the corpus now allows it: the gan store holds **79
species in both domains** (iNat soundscape + xeno-canto focal), 63 of them
with ≥ 100 syllables, vs the 12 (4 holdout-eligible… 3 held out) of §17.4.

**Protocol** (mirrors §17.4 exactly, only bigger): a /tmp subset of
`out/harvest-gan` restricted to the 63 both-domain species with ≥ 100
syllables, domain labels from the recording-id prefix. Same seed (0), same
fake side for all arms, `holdout_species 0.25` → ~16 held-out species (vs 3 —
this is the whole point). Arms: **A** iNat only, **B** naive merge, **C**
merge + `cross_domain_positives`. Measures as §17.4: cross-domain species
retrieval (nearest per-species centroid of the other domain; chance 1/63 ≈
0.016), held-out realism AUC and species accuracy from the training reports.

**Gates** (same shape as §17.4, judged C against B):

1. cross-domain retrieval ≥ B + 10 points,
2. held-out realism AUC does not drop (B's AUC is the line; any drop fails,
   no tolerance — the 0.012 question is whether a drop *replicates*, and a
   pre-registered tolerance is how the last one got argued with),
3. species accuracy within 2 points of B.

C passes all three → the cross-domain contrastive recipe is adopted as a
candidate for the next production critic retrain (owner's call, like every
learned component). Any failure → documented here; B's "data, not mechanism"
verdict stands, and the machinery stays default-off.

### 17.6.1 The re-test numbers: NO ADOPTION — the mechanism's boost was small-sample

Ran 2026-07-31 (driver `/tmp/birdy-avex/driver.py`, report
`/tmp/birdy-avex/avex2-report.json`): 63 both-domain species, 47 trained / 16
held out, 6 561 real patches (~104/species — the both-domain species are thin,
mostly iNat-side), 14 208 synthetic, seed 0, one shared fake side.

| arm | cross-domain retrieval (chance 0.016) | realism AUC held | species acc |
|---|---|---|---|
| A — iNat only | 0.058 | **0.995** | 0.627 |
| B — naive merge | 0.093 | 0.976 | 0.793 |
| C — merge + cross-domain positives | 0.110 | 0.983 | 0.794 |

Gate 1 (C ≥ B + 10 pts): measured **+1.7 — FAIL**. Gates 2 and 3 pass (AUC
+0.007, acc +0.2): **the 0.012 AUC drop that failed C in §17.4 does not
replicate — it reverses.** But the gate that matters kills it: the +13.4-pt
contrastive boost over B was small-sample structure, like the mel-weight
10-type probe (docs/19 §19.5). **No adoption; the machinery stays default-off.**

The uncomfortable part, recorded plainly: **B's own win also shrank at scale**
(+3.6 pts over A here vs +14.4 in §17.4), and B's AUC is *below* A's here
(0.976 vs 0.995 — mixing domains cost realism where §17.4 gained 0.012). Both
§17.4 deltas were measured on 12 species with a 3-species holdout; treat every
number there as small-sample, in both directions. What survives the bigger
test, and it is the load-bearing claim: **the ordering is stable** — more
domains per species helps (B > A on retrieval and hugely on accuracy), the
mechanism adds ≈ nothing on top of the data (C ≈ B), and no loss term at any
tested scale buys invariance cheaper than data. "Invariance is a data action"
stands, now with the effect sizes honestly shrunk.

Protocol notes: retrieval is over 63 species (harder task than §17.4's 12 —
absolute numbers are only comparable arm-vs-arm within each test); the fake
side renders the current learned inventory, which moved since §17.4 (all arms
share it); chance is 1/63 ≈ 0.016, and B/A/C read 5.9×/3.6×/6.9× chance if a
relative-to-§17.4 read is wanted (6.1×/4.3×/7.7× there — the ratios hold up
better than the points).
