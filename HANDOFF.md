# Birdy — Session Handoff

## 2026-07-30 (later): respiratory oscillator shipped (docs/13 B1, docs/15 §1)

Uncommitted. `pipeline/src/birdy_pipeline/respiration.py` is new: the two-state
air-sac model of Fainstein, Goller & Mindlin (2025), Table S2 ranges, hand-set default
per species. A syllable carrying a `respiration` block renders through it — `ps` is
the pressure gesture (scaled to peak where the envelope peaked) and the source is
multiplied by **√ps at the tract input** (Laje & Mindlin 2005 low-frequency physics —
the docs/09 §9.6 "every reference injects ẏ" claim was wrong and is corrected in
place); a syllable without the block renders bit-identically to before. Mirrored in
`syrinx-processor.js`; parity now **14/14** (two new fixtures: `respiration`,
`respiration+am`). `learn --respiration` attaches the default set to fitted types.
Bake-off on the harvest-mp copy, `learn --no-invert`: median cosine 0.343 → 0.336,
nearest-own 17/81 → 20/81 — a wash on the median, a win on placement; losses are
sub-50 ms notes' shaped onsets, which the pre-registered per-species fit (not built;
plan in docs/15 §1) is expected to own. AM stays at the labia by design — air-sac
pressure cannot swing at syringeal AM rates. Next here: that fit, then bout-level
rendering (the state carry is bit-exact and tested; mini-breaths are implemented and
dormant per-syllable).

---

# Birdy — Session Handoff (2026-07-30, late)

**What this session did:** (1) song-level type discovery — bouts clustered into song
types with a measured control (docs/12); (2) the first real `sources fetch` —
xccoverbl, 36 → 121 species, full re-derivation, novelty recalibration, verified
production assets (docs/14); (3) a research report on new sources and
complexification routes (docs/13); (4) fixed the Learn-tab hand-harvest: dropdown hid
all but the 12 documented birds, and every hand harvest died on a `NameError`
(regression from `287d49c`). **Everything is shipped**: assets verified, `serve`
restarted on current code with `--store out/harvest-gan`.

## Shipped, with the headline numbers

| What | Key measurement |
|---|---|
| Song-level typing (`learn.cluster_song_types`) | 50 song types / 13 species on the old store, own-medoid 0.246 vs 1.000, control yield 0.2 % at `SONG_MIN_CLUSTER=6`; two measured failure modes → `SONG_MIN_MOTIF=3` + medoid-radius gate 0.5 (docs/12) |
| xccoverbl ingest | 259 recordings, 291.9 min, 21 325 syllables; store 36 → **121 species**, 1 539 recordings, cap-bound at 39 874 syllables (drift 0.054 sd) |
| Re-derivation | inventory 35 → **116 species / 1 452 types**; galaxy **1 024 clusters / 75 743 points**; space map **0.9531/0.5921**; relations 6 441 pairs / 915 shared; `verify` green |
| Placement (docs/09's four) | species 24.6 % → 11.5 % but chance 2.8 % → 0.9 % (**8.8× → 12.8× over chance**); type 62.6 %; cosine 0.742; F0 3.1 % |
| Novelty recalibration | threshold 0.1912 → **0.1737**; ROC 0.786 / TPR 22.3 % @ 5 % FPR — on a harder test (105 truly non-training species vs 5 holdouts); not the same measurement as 0.672/14.8 % (docs/14 §14.3) |
| The cost, honestly | type coverage 94.6 % → **54.1 %** (85 species × ~3 recordings can't reach min cluster size), purity 56.7 % → 30.3 %, and the embedding's strongest structure is now `source` (+0.488) over species (+0.196) — variety without a retrain buys coverage and costs invariance (docs/14 §14.4) |
| Learn-tab fix | `harvestOptions` = documented ∪ discovered (44 species selectable); hand-harvest `NameError` fixed in `server.py:372`; `npm run check` clean (4 known errors) |

## Current state

- **Assets:** `app/static/birdy/` = 121-species embed galaxy, RFF map accepted,
  verified. Dev server serves it — reload the browser.
- **Store of record:** `out/harvest-gan` (39 874 syllables, 121 species, typing +
  song-typing + embeddings from this session). Critic still the 16-species
  `out/critic.pt`; novelty threshold 0.1737.
- **`serve` running:** current code, `--store out/harvest-gan`, :8781.
- **Uncommitted:** learn.py song-typing, cli.py/server.py wiring, server.py
  NameError fix, `+page.svelte` harvestOptions, docs/12+13+14, AGENTS.md, HANDOFF.md,
  and the rebuilt assets + `data/learned-inventory.json`.

## Open items (updated)

1. **Critic retrain with source-invariance pre-registered** — the top item now. The
   embedding organises by recorder before bird (+0.488 vs +0.196, docs/14 §14.4);
   docs/13's order says bigger ingest first (iNatSounds 230k/5 500 species, GBIF
   sound-archive adapter), then retrain. Either way the retrain judges itself on
   species-lift vs source-lift, not just the four numbers.
2. **App-side, with the other session:** relations overlay, "what comes next" from
   `grammar.chunks`, translator novelty branch, Learn-tab `sources fetch` button,
   and now: surface `grammar.songTypes`; also note coverage is 54 % — the UI should
   not imply the 651 orphan types failed (they're shallow-harvest species).
3. **Perch 2.0 `label-novel`** (docs/13 A1, verified accessible, Apache-2.0) —
   pseudo-labels as metadata, never as type identity.
4. **Harvest depth for the 85 shallow species** — the coverage remedy: XC top-ups or
   iNatSounds; 651 orphan types are waiting on it.
5. Song-typing follow-ups (docs/12 §12.5): id stability, `grow` placing bouts, the
   blackbird ×77 repeat-recording check.
6. Doc 09's alternation — moot (docs/11 §11.6).

**Operational reminders:** restart `serve` after any pipeline code change; run it with
`--store out/harvest-gan`; iterate clustering via `build --dump-points`; verification
runs to `/tmp`. `serve` defaults to the *old* store — it has now been caught on the
wrong store twice; consider making `out/harvest-gan` the default.
