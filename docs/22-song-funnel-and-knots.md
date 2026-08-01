# 22 — The song funnel and the knot budget

Two questions, asked of the data rather than of the code: why does a corpus of 2 423
species hold only 96 measured songs, and why did the first production build ship zero
documented knots. Both answers are accounting, not machinery. The measurements below
run on the production store (`out/harvest-gan`, 340 079 syllable observations, 327 164
of them typed, 2 421 species). No production artifact was rewritten to make them.

## 22.1 The funnel, counted

The shipped rule builds bouts, collapses each bout's repeat runs, and clusters what is
left. Counted stage by stage on the production store:

| stage | count | share |
|---|---|---|
| typed syllables | 327 164 / 340 079 | 96.2 % |
| bouts (a gap over 1.0 s breaks one) | 34 696 | |
| bouts that collapse to **one** token | 19 738 | 56.9 % of bouts |
| bouts that collapse to two tokens | 4 408 | 12.7 % |
| candidate bouts (three tokens or more) | 10 550 | 30.4 % |
| species with 6 candidates and 2 distinct strings | 366 | 15.1 % of species |
| **species that got a song type** | **48** | **2.0 % of species** |

Two losses dominate, and they are different in kind.

**The collapse.** `_collapse_runs` reads `A A A A A` as the motif `A`. That is correct
for a motif distance: a trill sung twice at two speeds must not sit twenty edits apart.
It is wrong as a filter. 19 738 bouts fall below `SONG_MIN_MOTIF` after the collapse,
and **6 940 of them are three syllables or more** — a bird repeating one sound, which
is a repertoire fact and not a measurement error. Until 2026-08-01 a species whose song
is a trill could not have a song type at any recurrence bar. The repository already
held the counter-argument in writing: `songspace.py` refuses the collapse for the P2
kernel and cites Jin & Kozhevnikov 2011 for it.

**The bar.** `SONG_MIN_CLUSTER = 6` was measured once, on the 47 k store, against a
corpus-wide control (docs/12). The corpus has grown eight-fold since. The median species
that clears the candidate gate has **8 candidate bouts**, so HDBSCAN is asked to find a
six-member cluster in eight points. It finds nothing for 318 of the 366.

## 22.2 Repeat classes: adopted

A repeat class is one collapsed string, heard `SONG_MIN_CLUSTER` times or more, in bouts
of at least `SONG_MIN_REPEATS` syllables. Equality is the similarity, because equality is
the only similarity a one-token string carries honestly — and equality cannot chain, so
the noise mode that `SONG_MIN_MOTIF` exists to gate against does not arise. The claim is
weaker than a motif's and the shipped type says which it is (`kind: motif | repeat`).

Pre-registered before the run: species with at least one song type must reach 90, and
the corpus-wide shuffle control must stay at docs/12's 0.2 % of candidate bouts.

| arm | species with songs | song types | placed bouts | control yield |
|---|---|---|---|---|
| shipped (motifs only) | 48 | 96 | 1 052 | 0.170 % |
| **+ repeat classes** | **98** | **356** (96 motifs, 260 repeats) | **3 741** | **0.170 %** |

The gate passes on both halves. The control is unchanged to the bout — shuffling a
species' tokens destroys runs, so the control finds no repeat classes at all, which is
the sharpest available evidence that the ones found are real. Arm 1 reproduces the
shipped corpus exactly (48 species, 96 types, 1 052 rows = `song-typing.json`'s length),
which is what makes the comparison a comparison.

This ships on. It needs a `learn` run to reach the inventory.

## 22.3 A per-species recurrence bar: refuted

The obvious follow-up: let each species set its own bar, on the evidence of its own
shuffled tokens. A species descends from 6 toward 4 one step at a time and takes each
step only where its own control places nothing.

The first version let **2 398 of 2 421 species** take the loosest bar. That is the
failure, not the result: a species with eight candidate bouts has a control that cannot
place a bout at any size, so "the control found nothing" means "the control had nothing
to work with". Corpus-wide control yield went 0.170 % to 0.442 %.

The repair is a power requirement — a species may only use the floor if it has enough
candidate bouts for its control to have failed. Calibrated the way `SONG_MIN_CLUSTER`
was, at the value returning the control to 0.2 %:

| required candidates | species loosened | species with songs | song types | control yield |
|---|---|---|---|---|
| none | 2 398 | 202 | 636 | 0.442 % |
| 10 | 120 | 114 | 535 | 0.399 % |
| 15 | 68 | 108 | 516 | 0.378 % |
| 20 | 56 | 103 | 509 | 0.378 % |
| 30 | 45 | 101 | 488 | 0.356 % |
| 50 | 28 | 99 | 452 | 0.266 % |

**No value passes.** The rows that come closest are the rows that gain almost nothing
over the 98 species repeat classes already reach. Read together the table says one
thing: a looser bar finds chance strings faster than it finds songs, however the licence
to loosen it is earned. The machinery stays in `cluster_song_types` as `floor`, off by
default, with this table as its refutation — the pattern of docs/17 §17.5.

## 22.4 A per-species bout rule: refuted

One constant defines a bout for 2 421 birds whose median inter-syllable gap runs from
0.033 s to 0.291 s (p10 to p90). Twenty-one species have a median gap over the constant,
so every syllable of theirs is its own bout and they can never have a song. The standard
remedy is a bout-criterion interval: a multiple of the species' own gap statistic.

At five times the species median, clamped to [0.3, 10] s, and judged against the same
0.2 % control bar:

| bout rule | bouts | candidate bouts | species with songs | song types | control yield |
|---|---|---|---|---|---|
| fixed 1.0 s | 34 696 | 10 550 | 98 | 356 | 0.170 % |
| adaptive | 45 300 | 11 930 | 105 | 449 | **0.628 %** |

Seven more species, at nearly four times the chance yield. Splitting a fast singer's
bouts finer produces more short strings, and short strings are what chance can chain.
The rule ships as `--adaptive-bouts`, off, with the number recorded.

One repair from this work does ship unconditionally: the bout rule was **three separate
literal `1.0`s** — in `learn_grammar`, in `bout_sequences` and in `syntax` — for a rule
that the grammar, the chunk miner, the P1 bake-off and the song types must all be
defined over. It is now one constant, `learn.GAP_BOUT_SECONDS`, and one argument that
every caller takes, so the four cannot drift onto different strings. A self-test pins it.

## 22.5 The knot budget

The 2026-08-01 production build verified green with 694 936 points and 1 024 clusters,
and named **zero** documented calls. The chain has four links and the last one is not in
this pipeline.

**One. Half the galaxy is a rendered copy of the other half.** `measured_corpus` renders
one anchor plus 24 measured realisations per type. Those realisations are re-syntheses
of member observations that are already in the map as field points. The production
build: **347 531 synthetic against 340 079 field**, 51.1 % synthetic.

**Two. The space is trained to separate the two copies.** The critic's leading loss term
is realism, real against our own resynthesis, at `w_real 1.0`. So `source` is the
strongest relation in its embedding (kNN 0.990, against species at 0.513), and every
type lives in two blobs. The build reports it exactly: `typeSeeds 27 762` for
`types 13 903`, with **13 859 of 13 859 learned types split**. The cap therefore binds
at twice the type count.

**Three. The vote.** `label_cluster` names a cluster by raw point-count majority. At
1 024 clusters the production build runs **13.6 types and 679 points per cluster**, so a
documented call's 24 points are 3.5 % of its cluster and lose every time. Forcing the
name on would mislabel thousands of unrelated field points, which the honesty rule
(docs/08 §8.5) forbids. The deeper oddity is that the vote exists at all: 96 % of points
carry a type by construction, so the build discards a known label and then tries to
recover it by majority vote over a partition.

**Four. `K_CAP = 1024` is an app constraint, not a pipeline one.** The pipeline's comment
says nothing downstream is quadratic in it, and that is true. The renderer declares three
`uniform float[clusterCount]` arrays in its **vertex** shader
(`app/src/lib/galaxy/shaders.ts`). 1 024 clusters is 3 072 vertex uniform floats, which
already sits past the WebGL2 guaranteed minimum and works because the development GPU is
generous. Raising the cap needs those three channels moved to a data texture first. The
second constraint after that is `centroids.json`, at 1.7 kB per cluster — 23 MB at 13 903
— which is the problem `inventory.json` already solved by sharding.

Links one and two are addressed by `build --member-variants` and `build --deflate-source`,
measured in §22.6. Links three and four are design decisions, not defects to fix quietly,
and they are recorded here for the owner.
