# Birdy — Session Handoff (2026-07-30, late)

**What this session did:** the big ingest + retrain (iNatSounds: 3 811 species, audio
cache), the parallel/streaming learn (2 423 named species), the first two synth
extensions (B1 respiration, B2 two-voice — parity 16/16, both default-off), Perch 2.0
label-novel, and a large UI program (wave activations, color language, Compose tab,
camera snap, listen modes). Full evidence: [`docs/16-inat-critic-naturalness.md`](docs/16-inat-critic-naturalness.md)
(+ docs/13 research, docs/15 renderer math).

## Shipped, with the headline numbers

| What | Key measurement |
|---|---|
| iNatSounds ingest | 6 453 recordings, 3 811 species, 226 264 syllables, drift 0.048 sd; **audio cache 6.3 GB** (owner exception, AGENTS.md) |
| Critic retrain | 2 686 training species / 895 held out; realism AUC 1.000; species acc 0.730 (chance 0.0004); **novelty ROC 0.846, TPR 32.2 % @ 5 % FPR** (14.8 → 22.3 → 32.2 % across three epochs) |
| Learn, parallel + streaming | **bit-identical** to serial (verified); ~3 h → ~15 min at 16 workers; progress + checkpoints every 100 species; 2 423 species, 12 724 types, **all with real common names** |
| `grammar.gaps` | 26 897 measured per-transition median gaps — no invented rhythm constants left |
| B1 respiration | parity 14/14; hand-set default a wash (0.343→0.336) → **off**; per-species fit running |
| B2 two-voice | parity 16/16; default 0.343→0.294 but worst-fit species improve → **off**; fit running |
| Perch label-novel | ONNX, ~48 ms/window; 23 697 novel syllables to label; honesty: metadata only |
| Fit pass (running) | gate holds: only winners ship (1/81 respiration, 8/40 two-voice on /tmp); fitted set mostly *catches up* to the envelope — the gate is the point |

## Current state

- **Build running**: the 2 423-species production galaxy (repairs the 149-cluster
  hdbscan accident — 78 % of points had no knot). verify + placement follow; docs/16
  §16.6 gets the numbers.
- **Store of record:** `out/harvest-gan` (199 993 syllables, 3 811 species; caps
  300k/200k now **persisted** in state.json). Critic = 2 686-species `out/critic.pt`;
  novelty threshold 0.1323; backups `out/critic-20260730-pre-inat.*`.
- **serve** on :8781, current code, `--store out/harvest-gan`.
- **Uncommitted:** everything (the user commits periodically).
- **Learn-tab hand-harvest + dropdown:** fixed earlier (NameError + 12-species list).
- **UI:** Compose tab (3 modes), wavefront activations (distance-ordered, signed
  interference ripples, orphan pulses), color language = points provenance / labels
  species-hue, camera snap, listen modes + device picker, tempo-lag fix (rate-aware EMA).

## Open items (ordered)

1. **Build finishes → verify → placement** → docs/16 §16.6; then the user checks:
   `abc_d` 4/4, Bengalese finch knots, Compose activations on the assigned cloud.
2. **Fit pass completes** (full-store run in background) → verdict table; then
   **pure-tone documented re-fit** (hooLong et al. get measured noise/rough).
3. **Full label-novel run** (23 697 novel syllables, ~25 min).
4. **Shard agent** (running): per-species inventory shards + app lazy loading.
5. **App-side queue:** relations overlay + "sing it as \<bird\>" (relations.json is
   ready, 6 441 pairs); unlabelled-arrivals live view (green class shipped, pool empty).
6. **Synth program after fit:** B3 per-taxon pilot (plantcutter 5-param or dove
   Elemans 2009), then the closing all-types fit per docs/15.
7. GBIF archives when the museums' servers recover (both measured dead 2026-07-30).

**Operational reminders:** restart `serve` after any pipeline code change (it has now
been caught on the old store twice — consider making `harvest-gan` the default);
`learn --jobs N` for the pool; verification runs to `/tmp`; never delete
`out/harvest*`; the audio cache is local-only and dies with the training phase.
