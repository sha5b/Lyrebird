# 22 — The song funnel and the knot budget

**One line each.** Repeat classes ship and double the corpus's songs (48 species to 98).
A per-species recurrence bar and a per-species bout rule both fail their controls and
ship off. Fewer rendered variants and deflating the source axis both fail to move the
seed demand — the split is binary and it is not one direction. What halves the seed
demand is rendering nothing for a type that has real members, which is the owner's call
because it changes what the map contains. Assigning typed points to their own type
instead of clustering them (§22.8) is worth +14 to +18 points of type retrieval where the
cap binds, +2.5 where it does not, and it ships as `--clustering label`, not as the
default. The Learn tab was fixed separately (§22.7).

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
default — and then removed with its flag, because a per-species bar that no candidate
requirement can license is not machinery anyone should be able to switch on by accident.
This table is what survives of it, and `cluster_song_types` still takes
`min_cluster_size`, so re-running the arm is a parameter and a loop.

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
The rule was removed with its flag on the same day it was measured: a refuted policy
that nothing can reach is surface, not machinery, and this table is what survives of it.
`bout_sequences`, `type_sequences`, `learn_grammar` and `attach_song_types` still take
the bout rule as an argument, so re-running this arm is a one-line change.

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

Links one and two looked like the cheap fixes. §22.6 measures them, and they are not.
Links three and four are design decisions, not defects to fix quietly, and they are
recorded here for the owner.

## 22.6 What actually halves the seed demand

One debug-100 build wrote its clustering matrix with `--dump-points` (214 154 points,
2 143 types, 160 279 of the points field). Every arm below runs on that one matrix,
through the shipped functions — `cluster_plan`, `type_seeds`, `_purity`, `label_cluster`
— so no arm is a re-implementation of the build, and no arm re-rendered anything.
Dropping renders is modelled exactly by dropping rows, because renders are deterministic
and independent per `(seed, species, syllable, variant)`.

Pre-registered before the run: seeds per type toward 1.0, with cluster purity and type
coverage no worse.

| arm | points | seeds/type | purity | type coverage |
|---|---|---|---|---|
| base, as built | 214 154 | 2.000 | 0.4232 | 0.4260 |
| member variants -> anchor only | 162 722 | 1.993 | 0.5677 | 0.4316 |
| source axis deflated | 214 154 | 1.999 | 0.4119 | 0.4228 |
| **no synthetic point for a type with members** | 160 579 | **1.000** | **0.5768** | **0.4316** |

**Fewer member variants does not touch the seed demand** (2.000 to 1.993). The
prediction behind §22.5's first link was wrong, and the reason is worth keeping: the
source split is *binary*. `_type_seed_means` splits a type whenever it holds points on
both sides, and it gates on the cosine between the two means. Twenty-four renders and
one render split a type equally well. What the arm does buy is real and large — cluster
purity 0.423 to 0.568, on 24 % fewer points and a build that renders 24 times less.

**Deflating the source axis fails on all three numbers.** The deflation works exactly as
specified: it removes 42.0 % of the space's energy and drives the gap between the two
source means from 7.233 to **0.0**. Every type still splits (1.999 seeds per type), and
purity falls 1.1 points, which is what throwing away 42 % of a space costs. So the
recorded-versus-synthesised difference is **not one direction**. The global offset is one
direction, and removing it leaves each type's own two clouds pointing as differently as
before. The critic's realism head names a hyperplane for the corpus, not the per-type
geometry the seeding gates on. `deflate_direction` was removed with its flag: 42 % of a space's energy for no change
in the split is not a knob worth keeping reachable. What survives is the finding — the
recorded-versus-synthesised difference is per-type geometry, not one direction — and it
is the reason the arm below is the one that works.

**What works is not rendering the type at all.** A learned type with member observations
*is* those observations — `typing.json` says so, and that is a label the build already
holds. Give the type no synthetic point and there is nothing for a source split to split:
seeds per type falls to exactly 1.000, `wanted` falls 4 298 to 2 155, purity rises to
0.577 (the best of the four) and type coverage to 0.432 (tied best), on 25 % fewer
points. Types with no observations keep their renders, because renders are all the
evidence they have.

Two honest limits on that row. It gives up the rendered voice's own place on the map,
which is a claim about our synthesiser rather than about a bird — a design decision, so
it ships as `--member-variants 0 --no-member-anchor` and not as a default. And the cap
still binds on this corpus (2 155 wanted against k = 1 024), so 1 119 types still lose
their only knot in every arm: **halving the seed demand does not undo the cap**, it
halves what the cap has to shed. The documented-knot column reads zero in all four arms
because the debug-100 subset is the deepest 100 species and holds no authored calls —
that question needs a subset chosen to contain them.

## 22.7 The Learn tab was not running the cycle

The Learn tab is the product surface: it adds data, fits, builds, and is meant to keep
going. It ran a configuration the command line abandoned. Four gaps, all in `server.py`,
all fixed on 2026-08-01:

- **The fit was serial.** `_fit` called `build_learned_inventory` without `jobs`, so it
  took the default of 1. The fork pool is measured bit-identical to the serial loop and
  turned about 3 h into about 15 min on the production store (docs/16). The tab now
  defaults to `default_jobs()` — cores minus two, capped at 8, the two left for the
  thread that streams the job log.
- **The fit left stale embeddings.** `build --space auto` takes the critic's 32-d
  embedding only when the store's sidecar exists and matches. A tab fit re-keyed the
  store and never rewrote `embeddings.f32`, so the next tab build quietly used the 28-d
  descriptor space, where the command-line cycle uses the space measured better for
  typing (docs/09 §9.7: species placement 38.4 % to 51.7 %). `_refresh_embeddings` now
  writes it through the same `write_store_embeddings` the CLI uses. Failure is logged,
  never fatal.
- **The build ran the expensive analysis every time.** The tab passed
  `--no-compare-projections` but not `--no-relations`, so every build ran the geometry
  permutation battery — the phase behind a 33-minute debug build. `--no-relations` skips
  the battery and not the shipped asset: `relations.json` is written from the store's
  embeddings either way. `critic groupings` runs the battery when it is the question.
- **The build shipped unverified assets.** The command-line cycle ends in `verify`. The
  tab ended at "wrote the assets". It now verifies what it just wrote, and a failure
  fails the job.

`serve` holds the pipeline in memory, so these reach a running control surface only
after a restart (AGENTS.md).

## 22.8 Label assignment: the vote removed, and where removing it is worth anything

§22.5's third link is not a defect but a design decision, and this is the arm that takes
the other side of it. 96 % of a production corpus's points carry a `(species, syllable)`
by construction — rendered points because we rendered them from that type, field points
because `typing.json` assigned them — and the kmeans path throws that away, partitions
the space geometrically, and asks each partition to vote a name back. `label_assign`
(`galaxy.py`, `build --clustering label`) sends every labelled point to its own type's
source blob and fits k-means only over the points with no label. The seeding and the
assignment now read *one* partition, `_type_blobs`, and `galaxy.self_test` pins that they
cannot drift apart.

Measured on §22.6's fixed matrix — the same debug-100 `--dump-points` set, 214 154 points,
2 143 types — through the shipped `type_seeds` / `label_assign` / `_purity` /
`label_cluster`. Two checks say the harness is sound before any arm is read: the k = 1 024
row reproduces §22.6's base row exactly (purity 0.4232, coverage 0.4260), and the k = 4 298
row reproduces the shipped debug build's own manifest (`clusterPurity` 0.5797,
`typeCoverage` 0.9258).

**Pre-registered before the run.** G1: *type retrieval* — for each labelled point, is the
nearest centroid by cosine in the standardised 32-d space (the lookup `SpectralMatcher`
performs on live audio) a cluster whose majority name is that point's own type? Gate:
label assignment ≥ kmeans + 10 points. G2: type coverage = 1.000. G3: clustering wall
clock below kmeans. G4: documented knots — reported, not gated, because debug-100 is the
deepest hundred species and holds no authored calls.

| arm | k | purity | type coverage | **type retrieval** | clustering s |
|---|---|---|---|---|---|
| kmeans, uncapped (as shipped) | 4 298 | 0.5797 | 0.9258 | 0.5775 | 64.9 |
| kmeans, k at production's shed ratio | 1 264 | 0.4601 | 0.5114 | 0.4599 | 25.5 |
| kmeans, k = 1 024 (§22.6's base) | 1 024 | 0.4232 | 0.4260 | 0.4227 | 27.2 |
| **label assignment** | 4 298 | 0.9988 | **1.0000** | **0.6020** | **0.2** |

**G1 fails as written, and the failure is the useful part.** Against the uncapped kmeans
build — the one shipped today — label assignment buys **+2.5 points** of type retrieval
against a +10 gate. The mechanism G1 was predicted from is types shedding their only knot,
and at `K_CAP` 8 192 this corpus wants 4 298 and gets all 4 298, so that mechanism never
fires. **On a corpus that fits under the cap, seeded kmeans is already almost as good as
knowing the answer**, which is a real result about the seeding and an argument against
making this the default.

Production is not that corpus. It wants 27 862 seeds against the same 8 192 and keeps
29.4 % of them. Putting this corpus in that ratio (k = 1 264) and at §22.6's k = 1 024
gives the comparison that matches production's condition, and there label assignment wins
by **+14.2** and **+17.9** points. That is the scope of the claim: *label assignment is
worth what the cap costs, and nothing more.*

**Two of the build's headline numbers stop being measurements.** Purity is 0.9988 and type
coverage is 1.0000 because a type *is* a cluster here — by construction, not by finding.
(The 0.12 % is the 300 song-level points, which carry a song id and no syllable.) Any
report that keeps quoting those two as evidence of a good map is quoting an identity. Type
retrieval is the statistic that survives, because nothing forces it.

**And it exposes a ceiling the cap was hiding.** Even with every type owning its own knot,
type retrieval is **0.602** — for 40 % of points the nearest centroid belongs to another
type. That is not the clustering's failure; it is the embedding's own confusion between
types, and the k-means arm could not show it because a type with no knot could not be
retrieved anyway. It is the honest bound on "sing and the right knot lights", and it is
now measurable at every k. Raising it is a space problem (docs/17, docs/23 W1/W6), not a
clustering one.

**Built end to end, and it verifies.** `build --clustering label` on the debug-100 store
(`/tmp/birdy-debug/assets-label`, 214 154 points, 375 s after the render): k = 4 298 read
off the labels — 2 143 types, all 2 143 source-split, plus 12 kmeans clusters for the 300
song-level points that carry no syllable — **type coverage 2 143/2 143 (100.0 %)**, every
`verify` check green. Against the kmeans build of the same corpus
(`/tmp/birdy-debug/assets-8192`), where coverage is 1 984/2 143.

**One measured cost, and it is in the live path.** The browser reaches the galaxy through
the 28-d → 32-d bridge, and docs/20's agreement numbers move against this arm:

| | kmeans | label |
|---|---|---|
| centroid agreement | 0.6572 | **0.6316** |
| tie-adjusted | 0.8032 | **0.8136** |
| species agreement | 0.7421 | **0.6831** |

Raw agreement falls 2.6 points and species agreement 5.9, while the tie-adjusted figure
*rises* 1.0. Read together that is more near-ties, not worse decisions: centroids placed
at label means are less separated than centroids Lloyd's iteration pushed apart, so more
live sounds land between two knots — and the ones that land decisively land better. It is
the same trade docs/20 already named, arriving from the other side. A build that wants
the species claim to be its headline should know this before switching.

**What it gives up** is the discovery claim over the labelled 96 %: those knots are no
longer a geometric finding that agrees with the labels, they are the labels. Every asset
and the app's Reading panel say so — the manifest's `clustering` reads `label`, its
`kmeans` block states that k-means ran over the unlabelled points only, and the panel's
map line reads "the knots are the labels, not a second finding". `--clustering hdbscan`
remains the map that can answer "none of these", and `--clustering kmeans` remains the
default.

**What it costs at production scale.** k becomes 27 762 type blobs + 100 for the 20 241
untyped points = **27 862 clusters**, and the constraint moves from the clustering to the
assets: `centroids.json` is written whole and the browser loads it whole. Measured on the
debug build, a label row is **1 596 bytes** (against kmeans' 1 716), so production would
ship about **44 MB** of centroids — the next thing to fix, and the fix `inventory.json`
already has: shard it, or move the two float vectors to an `.f32` sidecar the way
`point-features` is. The build warns with the projected size whenever k passes `K_CAP`. The renderer is not the limit any more
(the cluster-state `DataTexture` is 1 024 wide, so 27 862 knots is 28 rows), and the
clustering itself stops being a cost at all — 0.2 s against 65 s here, and against a
k = 8 192 Lloyd's iteration over 694 936 points there.
