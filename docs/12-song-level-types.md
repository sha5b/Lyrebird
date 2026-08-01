# 12 — Song-level type discovery: clustering bouts, not syllables

Evidence record for the fourth open item of the 2026-07-29 handoff: run the existing
machinery one level up. Syllable typing answers "which of these sounds are the same
sound". This item answers "which of these bouts are the same bout". A **song type** is a
cluster of similar type-id sequences. A bout in no cluster is the song-level novelty
answer: a sequence this bird has not been heard repeating.

Implementation: `learn.bout_sequences` / `cluster_song_types` / `attach_song_types`
(pipeline/src/birdy_pipeline/learn.py), wired into `cmd_learn` and the Learn-tab fit
(server.py `_fit`) right after `attach_chunks`. Output: `grammar.songTypes` +
`grammar.songTyping` per species in the learned inventory, and a store-side
`song-typing.json` (one row per typed bout, keyed by first syllable, beside
`typing.json`).

## 12.1 Method

- The rebuild uses the grammar's own bout rules. Order is meaningful within a recording
  only. A gap over one second breaks a bout. Untyped syllables are skipped.
- Each bout is **run-collapsed** (`A A A B B A` → `A B A`). A trill is one act, and repeat
  count is tempo. The grammar's self-transition already carries that axis.
- Distance is **Levenshtein over the collapsed strings, normalised by the longer string's
  length**. Two renditions of a motif differ by a syllable or two (≤ ~0.4 at motif
  lengths). Chance strings differ by most of their length.
- Clustering is HDBSCAN over the precomputed matrix, per species, never pooled. Type ids
  are species-local, so a pooled alphabet would alias twenty birds' strings into one. That
  is the artifact that `mine_chunks`'s mixture baseline exists to remove.
- Everything below was measured on one corpus: `out/harvest-gan`, 47 185 typed syllables →
  **5 481 bouts over 35 species** (median bout 2–7 tokens after collapse).

## 12.2 Two failure modes, two gates (both measured, both in the code)

**Short strings chain by chance.** At the store's alphabet sizes, chance two-token strings
often sit one substitution (normalised distance 0.5) from each other. HDBSCAN can chain
them: the first run reported a "song type" of six unrelated random bouts. Gate: bouts that
collapse to fewer than **`SONG_MIN_MOTIF = 3`** tokens are set aside, not clustered. A
one- or two-token string is a unigram or bigram, which is already the transition table's
content. `mine_chunks` starts at n = 3 for the same reason.

The honest cost: the cuckoo's two-note song lives in the grammar, not here. On this store
3 062 of 5 481 bouts (56 %) are short. They are reported as `short`, not silently dropped.

**Density carves clusters out of uniform noise.** EOM selection selects a cluster wherever
noise is slightly denser than its surroundings. The measured case: five random six-token
strings, all ~0.8 from their own medoid, reported as one song type.
(`cluster_selection_epsilon` does not fix this. It merges, it does not gate.)

Gate: a cluster survives only if its members' weighted mean distance to their medoid is ≤
**`SONG_MAX_RADIUS = 0.5`**. Otherwise the cluster is demoted to noise. Density decides
where clusters are. The radius decides whether what it found is one.

## 12.3 The control, and where the knee is

The control is the chunk miner's: permute each species' tokens globally (bout lengths and
type marginals preserved), cluster the shuffled strings, count the yield. A skewed type
distribution makes short chance strings genuinely edit-close, so the yield is not
automatically zero. The minimum-cluster-size constant is what moves it:

| `SONG_MIN_CLUSTER` | real types | real placed | control types | control placed |
|---|---|---|---|---|
| 4 | 113 | 979 / 2 419 (40.5 %) | 17 | 103 / 3 386 (3.0 %) |
| **6 (shipped)** | **50** | **693 / 2 419 (28.6 %)** | **1** | **6 / 3 386 (0.2 %)** |
| 8 | 23 | 394 / 2 419 (16.3 %) | 1 | 15 / 3 386 (0.4 %) |
| 12 | 9 | 209 / 2 419 (8.6 %) | 0 | 0 |

Six is the knee. The control's yield drops from 3.0 % to 0.2 %: one spurious type of six
bouts, in the species with the most skewed type marginals. The real corpus keeps 50 types.
At 8 the control gains nothing and half the real types are gone. This record reports the
0.2 % residual rather than tuning it to zero, because the price of zero is half the
signal.

(Control candidate counts are higher than real, 3 386 vs 2 419 in total, because permuted
adjacency destroys runs. Fewer shuffled bouts then collapse below the length gate.)

## 12.4 What the real corpus holds

The corpus holds 50 song types over 13 of 35 species. It placed 693 of 2 419 candidate
bouts, and 1 726 were heard once (the song-level novelty pool). Homogeneity, over 616
placed bouts in multi-type species: median distance to the own medoid **0.246** vs
**1.000** to the nearest other type's medoid. **92.0 %** of placed bouts are nearer their
own medoid than any other. The separation that the clustering assumes is actually there.

Per species, the shape of the answer varies the way the literature says it should:

- **parus_major** (great tit): 11 types, 151/213 placed — stereotyped repeated motifs,
  exactly the bird docs/03 describes. Top type: an alternating two-syllable motif heard 35
  times.
- **cuculus_canorus**: 8 types of short alternating patterns (its famous two-note song
  itself is below the length gate, in the grammar where it belongs).
- **turdus_merula** (blackbird): one type, `L26-L38-L19-L06`, 77 bouts. That single type
  is suspicious. 77 identical four-token strings are more likely one much-replayed
  recording or one much-recorded individual than a species-level repertoire claim. The
  machinery reports recurrence across the store. Whether the store's recurrence is the
  bird's is a harvest question (recordist/location diversity), flagged here rather than
  smoothed over.
- **luscinia_megarhynchos** (nightingale): **zero types over 275 candidate bouts** — the
  famous improviser, hundreds of motifs, essentially never repeating. The noise category
  saying "no repeated songs" about a nightingale is the method agreeing with a century of
  field notes.
- **poecile_atricapillus** (chickadee): zero types. 330 of its 407 bouts are short. The
  chick-a-dee call's A→B→C→D *ordering* (docs/03 §3.2) is chunk/grammar structure, and its
  bout strings collapse below the motif gate. The two levels of the pipeline divide the
  bird between them.

## 12.5 Known limits, honestly stated

- **Song-type ids (`S01`…) are not stable across refits** — they rank bouts of ids that
  syllable refits renumber. Stability has to wait on the syllable ids it would be defined
  over.
- The radius gate is on the weighted *mean*, so a cluster's tail can hold members past 0.5
  (p90 within-type distance is 0.667). That is edit-tolerance working as intended. But a
  bout placed at 0.67 from its medoid is a weak claim, and the app should treat it as one.
- Nothing here says what a song type is *for*. Like the chunks, these are structure with
  counts, not meaning (§8.5).
- `grow` does not place new bouts incrementally yet. Song typing is a learn-time pass. The
  novelty answer for arrivals is still syllable-level.

## 12.6 Self-test coverage

`learn.self_test` case 11: two planted motifs (one under trill repeats, one with a dropped
syllable) must be recovered as two types, with the run-collapse intact. Junk must stay
unplaced, and the global-permutation control must find nothing. The synthetic uses a
40-type alphabet with flat filler. At toy alphabets or a skewed bag, chance strings are
genuinely edit-close and the control fails honestly. This is the same phenomenon that
§12.3 measures on the store.
