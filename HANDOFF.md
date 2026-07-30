# Birdy — Session Handoff (2026-07-29, late)

**What this session did:** repaired a stale-serve asset regression, retrained the critic on
the 47 k store (all four metrics up), re-derived the chain, replaced the broken linear
space map with an RFF ridge (and wired the app side of it), fixed the 70 % type-coverage
ceiling with source-split cluster seeds, and added the multi-source harvest layer.
**Everything is shipped**: production assets carry all of it, verify is green, and `serve`
runs the current code against the right store. Full evidence record:
[`docs/11-critic-47k-map-coverage.md`](docs/11-critic-47k-map-coverage.md).

## Shipped, with the headline numbers

| What | Key measurement |
|---|---|
| Critic retrain (16 trained / 5 held-out species, 47 185 real + 11 424 rendered) | realism AUC 0.9897→**0.997**, species acc 0.9175→**0.939**, contrastive 0.6953→**0.820**, novelty AUC 0.596→**0.672** (TPR@5%FPR 7.4→**14.8 %**, threshold auto-recalibrated to 0.1912) |
| Re-derivation (embed → learn → build) | **485 types** (finer than 357), species kNN lift **+0.444**, 50 grammar chunks, relations 129 shared-type candidates |
| **RFF space map** (linear refuted: 0.7997 < 0.8 gate) | in-build **0.9268 median / 0.5688 agreement, accepted** (linear on identical inputs: 0.7997/0.2263); weights ship as `space-map.f32`; app applies them in `features.ts` |
| **Source-split cluster seeds** (the 70 % ceiling was a midpoint seed in empty space) | type coverage **70.2 % → 94.6 %** (27 orphans), purity 48.3 → **56.7 %**, k 503 → 986 |
| Multi-source harvesting (`sources.py`, `sources list/fetch`) | 5 adapters live-probed; warblr/ff1010 recorded as **control sets, not species**; BirdCLEF waits on the user's Kaggle key; `.env.example` documents every key; missing key = clean skip |
| `serve` restarted ×2 | runs current code **and** `--store out/harvest-gan` (the default is the old store — that plus stale code caused the morning's regression; docs/11 §11.1, AGENTS.md) |

## Current state

- **Assets:** `app/static/birdy/` = embed galaxy, **986 clusters / 496 types / 59 700
  points**, RFF map `accepted: true`, `space-map.f32`, `relations.json`, coverage 94.6 %.
  `verify` all checks passed. The dev server (:5173) serves it — **reload the browser**.
- **Store of record:** `out/harvest-gan` (47 185 syllables, typing + embeddings from the
  new critic). `out/critic.pt` = 16-species critic; backup `out/critic-20260729-pre47k.*`.
- **App-side map activation is done** (`types.ts` union, `assets.ts` sidecar fetch with
  drop-on-mismatch, `features.ts` RFF apply; `npm run check` = 4 known errors only).
- **Uncommitted on top of the user's bc2f407/8f91210:** galaxy.py split-seeds, cli.py
  verify fix + `--dump-points`, AGENTS.md, HANDOFF.md, docs/10+11+README, pipeline/README.

## UI wiring check (what the view actually shows today)

Verified against the running dev server (:5173) and the shipped assets:

| Feature | Status | Where |
|---|---|---|
| Embed galaxy (986 knots, split-seed blobs, 94.6 % coverage) | **live** — reload the browser | `app/static/birdy/` → PointCloud/Galaxy |
| RFF 32-d live matching | **live** — `listener.ts` builds `ActivationTracker` on the shipped feature-space; sidecar `space-map.f32` fetches 200, `accepted: true`, 28-d fallback on any mismatch | `assets.ts`, `features.ts` (this session) |
| Novelty count in the view | **live (display only)** — "unheard syllables N" + recent list from `/api/status` | `+page.svelte` (~L1677), `pipeline.ts` |
| Relations | **headline only** — the page shows `manifest.relations.headline` (permutation-test text); `relations.json` (210 pairs / 129 shared types) is **never fetched or drawn** | pending: app-side session |
| "What comes next" from `grammar.chunks` | **not consumed** — the only `chunks` in app/src is word syllabification, unrelated | pending: app-side session |
| Translator novelty branch ("unheard syllable — no documented function") | **absent** — `lang/translate.ts` has no novel/unlabelled branch | pending: app-side session |
| `sources fetch` button | **no UI, no `/api/sources` route** — CLI only | pending: server route + app button |

The two effects already visible without any new UI work: far more types light and label
(94.6 % have a knot, was 70 %), and live matches land in the measured 32-d space
(0.9268 map) instead of the descriptor fallback.

## Open items

1. **App-side, with the other session:** relations overlay from `relations.json`, "what
   comes next" from `grammar.chunks`, translator novelty branch ("unheard syllable — no
   documented function"), and a Learn-tab button for `sources fetch` (no `/api/sources`
   route yet — CLI only).
2. **A real `expand` / first `sources fetch` into the store** — deliberate choice: XC rate
   budget, Kaggle key (BirdCLEF), or keyless xccoverbl for UK species. The point is
   *variety* — more species, more recording conditions, more sound forms (soundscapes,
   hasbird controls) — because the critic's measured weaknesses are all coverage
   weaknesses (docs/11 §11.5). Note: nothing generative trains on it ("gan" is only the
   store's fossil name); the physical synth never sees the data. Any large ingest → full
   re-derivation + novelty recalibration (docs/10 §10.3), judged on the fixed-store
   numbers.
3. **Perch-2.0 labelling of novel arrivals** (researched in last handoff) — the upgrade
   path for pseudo-species; species-level novelty TPR is 14.8 % and that's a research
   problem, not tuning.
4. **song-level type discovery** — run the existing machinery on bout sequences of type
   ids (researched in last handoff).
5. Doc 09's alternation — recorded as moot while the realism term stays refuted (docs/11
   §11.6); stop carrying it as "never run".

**Operational reminders:** restart `serve` after any pipeline code change; run it with
`--store out/harvest-gan`; iterate clustering via `build --dump-points` (fixed corpus in
`/tmp/birdy-points.npz` from this session, 59 700 points); verification runs to `/tmp`.
