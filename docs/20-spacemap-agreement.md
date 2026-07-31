# 20 — The spacemap's 0.66: a metric problem, not a map problem

The browser cannot run the critic, so `spacemap.py`'s RFF ridge bridges live 28-d
descriptors into the 32-d embedding galaxy. Its quality gate passes cleanly
(median mapped-vs-true cosine 0.962 on held-out recordings, `accepted: true`),
yet `centroidAgreement` — the share of held-out syllables whose nearest galaxy
knot is the same through the map as through the critic — reads only 0.61–0.66,
which looked like the bridge failing. docs/20 decomposes the loss before anyone
fixes or replaces anything.

Protocol first: the shipped eval was reproduced bit-for-bit on the debug build
(same recording split, same RFF knobs): median cosine 0.9623 = gate, agreement
0.6143 = shipped. (The shipped `space-map.f32`, refit on all pairs, scores 0.834
on the same rows — optimistic by construction; 0.6143 is the honest held-out
estimate and what ships is better than it.)

## 20.1 The decomposition (3 731 held-out syllables, 1 439 flips)

| cause | share of the 38.6 % loss |
|---|---|
| **Boundary near-ties** (true-space margin < 0.05; 74 % of ALL rows sit there) | **76.4 %** |
| Mid-margin (0.05–0.1), mostly bad-session rows | 18.5 % |
| Big-margin genuine map failure (unseen recordist) | 2.6 % |
| Big-margin, seen recordist, map cos < 0.90 | 1.7 % |
| Residual unlucky geometry | 0.8 % |

Cross-cutting:

- **Tie-adjusted agreement is 0.91** (free ties at margin < 0.05; 0.98 at 0.1).
  41 % of flips have the true knot as the mapped point's *runner-up* — near-misses
  between adjacent knots, not jumps to the wrong bird.
- **Flips cluster by session**: the worst 5 of 45 held-out recordings hold 37 % of
  the loss, and all 8 "bad sessions" (median map cos < 0.90) are xeno-canto
  recordings — iNat sessions map cleanly. One recording alone (a Wryneck session,
  99 % flip) carries 9.3 % of the entire loss.
- Recorder confound real but modest (unseen-recordist rows flip 0.43 vs 0.35);
  country confound nil.
- **Species-level agreement is 0.781** (chance 0.033); Ward-merging the 1 024
  knots, the curve flattens at ~0.84 — the residual is the bad sessions plus the
  ~2 % true map failure.

## 20.2 The recommendation (adopted direction, 2026-07-31)

1. **Report margin-aware and species-level agreement** in `mapQuality` (raw 0.61
   undersells what ships by construction with 1 024 dense knots).
2. **Live activation stays soft** (the app already does softmax + EMA — the right
   shape); where a single label is needed, **species-level matching is the honest
   claim (0.78)**, and knot-level claims carry "nearest of several close knots".
3. **No k-NN bridge, no per-species maps, no ONNX-in-browser** — the addressable
   loss is ≤ 2.6 % of rows; a better map class cannot fix near-ties.
4. **The one double-digit lever is the xeno-canto bad sessions** (8 recordings,
   24 % of the loss): per-session quality gating or normalisation on the live
   path, and possibly down-weighting pathological sessions in the fit.

Caveat recorded: these are debug-build numbers; production reported 0.66 with the
same structure expected. Re-run on the production store before any production
decision.
