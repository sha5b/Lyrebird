# Birdy — Session Handoff (2026-07-29, evening)

**What this session did:** found and repaired a post-handoff asset regression (stale `serve`
process), retrained the critic on the 47 k store with a proper species holdout (all four
metrics up), re-derived the full chain, and fixed the browser's 28→32 space map when the
new critic broke it — replacing the linear ridge with an RFF ridge, chosen and graded by
the same recording-split protocol. Also wired the app side of that map.

## The regression, and why it happened

- The previous session's "final learn+build" ran **through a `serve` process started 11:47,
  before the afternoon's embedding code existed**. It wrote a descriptor-space galaxy from
  the *old* `out/harvest` store over the embed galaxy (committed at 3f0d1f6), and a
  chunk-less typing/inventory. No `space` key in the manifest was the tell.
- Fixed: `serve` restarted with current code (port 8781); `learn --embed-typing` re-run
  (47 185/47 185 typed, 357→ types, **50 grammar chunks** folded in); `build --space embed`
  re-run. **Lesson recorded: restart `serve` after pulling pipeline code — it holds the
  module in memory and its Learn-tab builds use whatever it started with.**

## Critic retrain (open item #2 — done)

`critic train --store out/harvest-gan` (16 species trained, 5 held out, 47 185 real +
11 424 rendered patches, 346 s GPU). Old critic backed up to `out/critic-20260729-pre47k.*`.

| metric | old critic | new critic |
|---|---|---|
| realism AUC, held-out species | 0.9897 | **0.997** |
| species accuracy | 0.9175 | **0.939** |
| contrastive top-1 | 0.6953 | **0.820** |
| novelty ROC AUC | 0.596 | **0.672** (different holdout five — indicative, not paired) |
| novelty TPR @ 5 % FPR | 7.4 % | **14.8 %** (threshold auto-recalibrated 0.1558 → 0.1912) |

Full re-derivation followed: `critic embed` → `learn --embed-typing` (485 types, finer than
357 — the new embedding types differently) → `build --space embed` (503 clusters, purity
48.3 %, species kNN lift +0.444 — strongest yet; relations 129 shared-type candidates).

## The space map broke, and the fix shipped (new work)

The new critic's embedding is **not linearly recoverable** from the 28-d descriptor: the
ridge map scored **0.7997 < the 0.8 gate → `accepted: false`**, agreement 0.226 — the
browser would have stayed on the descriptor path with the embed galaxy shipped.

- **Fix: RFF ridge** (`spacemap.py`): `sqrt(2/D) cos(x @ R + phase) @ w + b`, D=2048,
  sigma and lambda swept on validation *recordings*, and the map **class** itself chosen
  on the validation split — the eval rows grade a decision already made. Measured in-build:
  **median cosine 0.9267, nearest-centroid agreement 0.5822** (linear on identical inputs:
  0.7997 / 0.2263; the old critic's accepted linear map was 0.8585 / 0.3739). The
  refutation of "linear is the honest choice" is recorded in the module docstring.
- Weights ship as **`space-map.f32`** (123 k floats; layout + apply formula in
  `feature-space.json`'s `embedding.map`, `kind: "rff-ridge"`). `verify` checks it;
  linear maps keep shipping inline as before (backward compatible).
- **App side wired** (`app/src`): `types.ts` map union, `assets.ts` fetches+validates the
  sidecar (drops the embedding block on any mismatch → honest 28-d fallback),
  `features.ts` applies the RFF in `ActivationTracker`. `npm run check`: 4 known errors
  only, none new. **The shipped assets still carry the old linear map until the next
  production build** — the app code is ready ahead of them.

## In flight at handoff

- **cluster_plan re-tune** (open item #1): experiment running on `/tmp/birdy-points.npz`
  (59 700 fixed points, dumped by the new `build --dump-points` flag — use it, never
  re-render per idea). Candidates: status quo / more k / 2×k / **source-split seeds**
  (a type with field + synthetic members gets two seeds — the source axis is the
  strongest relation in the space, kNN 0.99, so one midpoint seed sits in empty space).
  Coverage has been stuck at ~70 % across three builds (148/496 orphaned now, mostly
  cuculus_solitarius). Result + the winning change → then production build.
- **sources subagent** (`agent-0`, resumable): multi-source harvest adapters
  (`sources.py` + `birdy-pipeline sources list/fetch`) so `expand` isn't bottlenecked on
  xeno-canto's rate budget — Zenodo (no key), Kaggle/BirdCLEF, HuggingFace/BirdSet,
  Internet Archive; every source skips cleanly when its key is missing; extended
  `pipeline/.env.example`. Its `sources` subcommand is already in cli.py (it raced my
  build once — a `cmd_grow` NameError at import, harmless, retry worked).

## Current state

- **Assets in `app/static/birdy/`:** new-critic embed galaxy (503 clusters, 485 types,
  relations.json) but **linear map `accepted: false`** — the app matches in 28-d until the
  RFF production build runs. `/tmp/birdy-build-rff` is the exact asset set the production
  build will produce (verify green: map 0.9267/0.5822, coverage 71.0 %).
- **Store of record:** `out/harvest-gan` (47 185, typing.json + embeddings.f32 from the
  new critic). `out/critic.pt` = 16-species critic; novelty threshold 0.1912.
- **Uncommitted:** everything above (pipeline + app + assets). No commits this session.

## Open items (updated)

1. **cluster_plan re-tune** — experiment in flight; implement winner, production build.
2. ~~Critic retrain~~ — done; doc 09's alternation still never run (the realism term stays
   refuted; the alternation is moot while it is).
3. **expand / new sources** — subagent in flight; a real expand still spends XC budget,
   the new sources are the answer to that.
4. **App-side** — map activation **done** (this session). Still with the other session:
   relations overlay, "what comes next" from `grammar.chunks`, novelty branch in the
   translator ("unheard syllable — no documented function").
5. **Docs** — docs/10 evidence entry for the retrain + map (numbers above) not yet written.

**Next-time order:** (a) cluster experiment verdict → galaxy.py change → production build;
(b) docs/10 entry + AGENTS.md refresh; (c) sources integration + a real `expand` decision;
(d) app-side overlays with the other session.
