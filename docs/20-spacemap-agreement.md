# 20 — The spacemap's 0.66: a metric problem, not a map problem

The browser cannot run the critic, so `spacemap.py`'s RFF ridge bridges live 28-d
descriptors into the 32-d embedding galaxy. Its quality gate passes cleanly: median
mapped-vs-true cosine 0.962 on held-out recordings, `accepted: true`. Yet
`centroidAgreement` reads only 0.61–0.66, the share of held-out
syllables whose nearest galaxy knot is the same through the map as through the
critic. It looked like the bridge failing. docs/20 decomposes the loss before anyone
fixes or replaces anything.

Protocol first: the debug build reproduces the shipped eval bit-for-bit (same
recording split, same RFF knobs). Median cosine 0.9623 = gate, agreement 0.6143 =
shipped. The shipped `space-map.f32`, refit on all pairs, scores 0.834 on the same
rows. That score is optimistic by construction. 0.6143 is the honest held-out
estimate, and what ships is better than it.

## 20.1 The decomposition (3 731 held-out syllables, 1 439 flips)

| cause | share of the 38.6 % loss |
|---|---|
| **Boundary near-ties** (true-space margin < 0.05; 74 % of ALL rows sit there) | **76.4 %** |
| Mid-margin (0.05–0.1), mostly bad-session rows | 18.5 % |
| Big-margin genuine map failure (unseen recordist) | 2.6 % |
| Big-margin, seen recordist, map cos < 0.90 | 1.7 % |
| Residual unlucky geometry | 0.8 % |

Cross-cutting:

- **Tie-adjusted agreement is 0.91** (free ties at margin < 0.05 — 0.98 at 0.1).
  41 % of flips have the true knot as the mapped point's *runner-up* — near-misses
  between adjacent knots, not jumps to the wrong bird.
- **Flips cluster by session.** The worst 5 of 45 held-out recordings hold 37 % of
  the loss. All 8 "bad sessions" (median map cos < 0.90) are xeno-canto
  recordings, and iNat sessions map cleanly. One recording alone (a Wryneck session,
  99 % flip) carries 9.3 % of the entire loss.
- The recorder confound is real but modest (unseen-recordist rows flip 0.43 vs
  0.35). The country confound is nil.
- **Species-level agreement is 0.781** (chance 0.033). Ward-merging the 1 024
  knots, the curve flattens at ~0.84 — the residual is the bad sessions plus the
  ~2 % true map failure.

## 20.2 The recommendation (adopted direction, 2026-07-31)

1. **Report margin-aware and species-level agreement** in `mapQuality` (raw 0.61
   undersells what ships by construction with 1 024 dense knots).
2. **Live activation stays soft.** The app already does softmax + EMA, the right
   shape. Where a single label is needed, **species-level matching is the honest
   claim (0.78)**. Knot-level claims carry "nearest of several close knots".
3. **No k-NN bridge, no per-species maps, no ONNX-in-browser** — the addressable
   loss is ≤ 2.6 % of rows. A better map class cannot fix near-ties.
4. **The one double-digit lever is the xeno-canto bad sessions** (8 recordings,
   24 % of the loss): per-session quality gating or normalization on the live
   path, and possibly down-weighting pathological sessions in the fit.

Caveat recorded: these are debug-build numbers. Production reported 0.66 with the
same structure expected. Re-run on the production store before any production
decision.

## 20.3 Per-session quality gating (pre-registered 2026-07-31, before any run)

Item 4's lever, made concrete. Two action sites, measured in order on a /tmp copy
of `out/harvest-d100`. That store holds 100 species and 453 recordings — 269 XC /
184 iNat — with `snr`/`clipped` per observation. The embedding uses the current
production critic.

The map protocol is this module's exact one (RFF knobs, seed 0, split by
recording). The 28-d frame is the store's own descriptor mean/std, not the
window-corpus frame, so absolute cosines shift slightly from the §20.1 numbers.
The session *structure* is what is under test. "Bad session" keeps §20.1's
definition: median mapped-vs-true cosine < 0.90 across the session's held-out
syllables.

**Candidate live signals** (per session, computable from the 28-d side alone —
that is all the browser will ever have):

1. off-manifold distance: mean 5-NN distance of the session's standardized
   descriptors to the fit-side descriptors.
2. Mahalanobis (diagonal) distance of the session's median descriptor to the
   fit cloud.
3. session dispersion (mean distance to the session's own median).
4. mapped-norm deviation: |‖mapped z‖ − median ‖true z‖ over the fit side|.
5. harvest quality: mean `snr`, share `clipped`.

**Gates.**

- **G1 (detection).** A signal — or a thresholded combination of at most two —
  separates bad from clean held-out sessions at AUC ≥ 0.9. Below that there is
  nothing to ship: a gate that flags clean sessions is its own honesty problem.
- **G2 (lever).** Gate the sessions the signal flags, at a flag rate ≤ 20 % of
  held-out sessions. This must raise the *remaining* rows' centroid agreement by
  ≥ 5 points on the end-to-end debug build, with tie-adjusted agreement not
  falling. Measure it on the real build (phase 2), not the cosine proxy.
- **G3 (fit-side, the "possibly").** Down-weighting fit-side sessions the same
  signal flags must not drop the eval median cosine by more than 0.005 — the
  recorded risk is that pruning weird sessions shrinks the manifold and hurts
  the next unseen weird session. If it helps eval agreement without breaking
  that, it ships. Either way the number is recorded here.

A signal that passes G1 but fails G2 still ships as an *honesty* gate: the app
says "this session is off everything the galaxy knows" instead of lighting
knots. That fallback is pre-registered too, so nobody can invent it
post-hoc to save a failed lever.

### 20.3.1 Interim: the proxies, and G3's verdict (2026-07-31)

Measured on store-only replications: 28-d frame = store window statistics, no
render corpus. The build's frame mixes renders in, so absolute cosines run
~0.02–0.06 low here. Rankings are what is read:

- **Signal 5 (harvest quality) is untestable on both debug stores** — `snr` is
  unpopulated and `clipped` never true in harvest-d100/b100 (the fields arrived
  with the 2026-07-30 quality work, and these stores predate its harvests). It
  stays a candidate for the next harvest epoch.
- **Signal 1 (off-manifold 5-NN) separates consistently**: AUC 0.875 (d100) /
  0.808 (b100) against the bad-session label, Spearman −0.82 with session
  cosine. Below the 0.9 gate so far. The real-build frame (phase 3) and the
  pre-registered two-signal combination are still to come.
- **G3 (fit-side pruning): FAILS, both stores.** Dropping the worst-quintile
  off-manifold fit sessions moves eval median cosine −0.0147 (d100) and
  −0.0062 (b100) against the ≤ 0.005 allowance. The recorded risk was real:
  the weird sessions *are* manifold coverage, and pruning them hurts the next
  unseen weird session. The fit keeps every session. Gating is a live-path
  action only.
- Regime caveat: on these store-only replications the "bad session" count is
  far higher than §20.1's 8/45 and includes iNat. That is an artifact of the
  missing render corpus in the frame. Phase 3 settles it on the real build. The
  Wryneck session (XC122542, cos 0.116, 99 % flip, 9 % of the loss)
  reproduces exactly.

### 20.3.2 Phase 3 (the real build): G1 passes, G2 fails raw — the honesty gate ships

The store-only regime caveat was right. The end-to-end debug build uses
`harvest-b100` + the production learned inventory, embed space, 331 439
points, 1 024 knots, verified green. On it, §20.1's structure reproduces *exactly*:
median cosine 0.9708, knot agreement 0.6025, **8 bad sessions, all xeno-canto,
zero iNat**, top-5 sessions 35 % of the flip loss, the bad eight holding
**22.9 %** of it (§20.1 said 24 %). The "iNat maps badly too" of the proxies
was a frame artifact, recorded as such.

**G1 — PASSES.** The off-manifold 5-NN signal separates the 8 bad sessions at
**AUC 0.953** (normdev 0.922 — the pre-registered two-signal combination adds
nothing at 0.954). A shipped cloud of **256 random anchors holds AUC ≥ 0.92**
over draws and costs 28 KB — the gate needs no full descriptor dump in the
browser.

**G2 — fails as written, and the pre-registered fallback fires.** Gating the
signal's top sessions raises *raw* agreement +3.5 pts (bar: +5). The
tie-adjusted figure moves from +8.7 (flag 4/45) to +13.7 (flag 9/45, one clean
session caught, 23 % of the flip loss removed). The raw bar was written
expecting the bad sessions' flips to be denser than they are (their flip
rates run 0.30–0.99, not ~1). So the gate ships as the **honesty gate** the
pre-registration allowed: `sessionGate` in feature-space.json's embedding
block — 256 anchors, k = 5, a threshold, and its own calibration text. The
app's side is app-side work, handed off: compute the statistic over the live
session, and show "this session is off everything the galaxy knows" instead of
lighting knots.

One calibration trap is worth recording, because it will bite any repeat. A
threshold calibrated on fit sessions does **not** transfer to unseen sessions,
even excluding the session's own rows. Sibling sessions of the same recordists
deflate every fit session's distance. q95 fit-side flags **29 %** of held-out
sessions. The shipped threshold is calibrated *cross-wise*: each fit session
judged against the other seeded half of fit sessions.

The shipped gate's measured operating point on the end-to-end build's held-out
recordings: **8/45 sessions flag (18 %)**. That is still above nominal 5 %,
partly *because* unseen-recordist sessions are exactly what the gate exists to
catch. It catches **5 of the 8 bad sessions including the three worst
loss-carriers** (XC101377, the Wryneck, XC814278).

The 3 clean false-flags all sit within 0.02 of the bad line (cos 0.916–0.921).
The uncaught three are the mildest bad sessions (cos 0.876–0.897). The shipped
calibration string says what a flag means. The app chooses whether to show it as
a hard flag or a continuous score.

`mapQuality` gains the two §20.2 fields in the same build:
`centroidAgreementTieAdjusted` (near-ties at margin < 0.05 excluded) and
`speciesAgreement` (knots labeled by majority species — the honest
single-label claim). `build --dump-spacemap-eval <npz>` is the instrument all
of the above was measured with: held-out rows + recording ids + the fit cloud
+ the galaxy's centroids, off one build.
