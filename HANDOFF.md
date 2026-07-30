# Birdy — Session Handoff (2026-07-30)

**What this session did:** song-level type discovery (open item 4 from the last
handoff) — the typing machinery run one level up, clustering bouts of type ids into
song types. Shipped in the pipeline, validated against the permutation control,
end-to-end verified on a `/tmp` store copy. **Not yet re-derived into production
assets** — that takes a deliberate `learn` on `out/harvest-gan` (writes
`song-typing.json` + `grammar.songTypes` into `data/learned-inventory.json`).
Full evidence record: [`docs/12-song-level-types.md`](docs/12-song-level-types.md).

## Shipped, with the headline numbers

| What | Key measurement |
|---|---|
| Song-level typing (`learn.cluster_song_types`, wired into `cmd_learn` + Learn-tab fit) | **50 song types over 13 of 35 species**, 693/2 419 candidate bouts placed, own-medoid separation 0.246 vs 1.000 (**92 %** nearer own) |
| Two measured failure modes → two gates | short strings chain by chance → `SONG_MIN_MOTIF = 3` (3 062/5 481 bouts are bigram business); EOM carves clusters from uniform noise → medoid-radius gate `SONG_MAX_RADIUS = 0.5` |
| `SONG_MIN_CLUSTER = 6` set by control sweep | permutation control: 3.0 % placed at 4, **0.2 % at 6**, real types 113→50→23 at 4→6→8 — six is the knee |
| Honest negatives | nightingale: **0 types / 275 bouts** (the improviser, as documented); blackbird's single type ×77 is one-recording recurrence, flagged not smoothed |

## Current state

- **Pipeline code:** `learn.py` (`bout_sequences`, `cluster_song_types`,
  `attach_song_types`, self-test case 11 — green), `cli.py` (writes `song-typing.json`,
  logs song types), `server.py` `_fit` (same tail). Ruff: 6 pre-existing errors, no new
  ones.
- **Assets:** unchanged — `app/static/birdy/` is still the 986-cluster galaxy from
  2026-07-29. The song types appear in the learned inventory after the next production
  `learn`; nothing consumes `grammar.songTypes` in the app yet (app-side item).
- **Store of record:** `out/harvest-gan` untouched this session (validation ran
  read-only; end-to-end ran on a `/tmp` copy of `harvest-mp`).
- Uncommitted: everything above plus the previous session's asset/doc changes.

## Open items (updated)

1. **App-side, with the other session:** relations overlay from `relations.json`
   (never fetched; page shows only `manifest.relations.headline`), "what comes next"
   from `grammar.chunks` (not consumed), translator novelty branch (absent from
   `lang/translate.ts`), Learn-tab button for `sources fetch` (no `/api/sources` route)
   — and now: surface `grammar.songTypes` (id, medoid sequence, count, share) once a
   production `learn` has run.
2. **A real `expand` / first `sources fetch` into the store** — XC rate budget, Kaggle
   key (BirdCLEF), or keyless xccoverbl. Any large ingest → full re-derivation +
   novelty recalibration (docs/10 §10.3).
3. **Perch-2.0 labelling of novel arrivals** — species-level novelty TPR is 14.8 %,
   a research problem, not tuning.
4. ~~Song-level type discovery~~ — done, this session (docs/12). Follow-ups: song-type
   id stability across refits (blocked on syllable-id stability), `grow` placing new
   bouts incrementally, and the blackbird repeat-recording check (recordist/location
   diversity of the ×77 type).
5. Doc 09's alternation — moot while the realism term stays refuted (docs/11 §11.6).

**Operational reminders:** restart `serve` after any pipeline code change; run it with
`--store out/harvest-gan`; iterate clustering via `build --dump-points` (fixed corpus in
`/tmp/birdy-points.npz`); verification runs to `/tmp`.

