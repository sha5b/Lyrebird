# Findings from the licensing / rename / obsolete-docs audit (2026-08-01)

**Nothing in this file has been fixed.** It is a list of things that look wrong in the
**code** or in the project's **assumptions**, found while correcting the documentation. The
doc corrections, the new `LICENSE`/`NOTICE.md` and the Birdy → Lyrebird prose rename are
done; everything below is a decision for the owner.

Ordered by how much it matters. The first three are licensing correctness.

---

## 1. ND-licensed xeno-canto recordings are measured and their derivatives ship — the ND refusal is only on *retention*

**Where:** `pipeline/src/birdy_pipeline/harvest.py` — the licence gate
`audio_may_be_cached` is at line 992 and is called **only** at line 1229, inside the
`if keep_audio is not None:` branch. The ingest path immediately above it
(`ingest_file(store, audio_path, ...)`, line 1214) has **no licence check at all**.
Contrast `pipeline/src/birdy_pipeline/sources.py:735-758`, where the iNat adapter's
`LICENCES_OK = {0, 1, 3, 4, 6}` refuses ND **at ingest** and skips the file entirely.

**What is wrong:** the two adapters apply opposite policies to the same clause. For
xeno-canto, an ND recording is downloaded, decoded, reduced to 28-d descriptors, log-mel
patches and syllable observations, folded into the store, and those measurements go into
`app/static/birdy/` and ship to every browser. Only the *audio file* is refused.
`README.md` measured the old harvest at 68 of 435 recordings CC BY-NC-**ND**, so this is
not hypothetical.

**Why it matters:** the project's own stated reason for refusing ND at retention is that
"everything this pipeline does next produces derived measurements, and ND is the one clause
where that is not clearly covered" (`harvest.py:976-989`, `AGENTS.md`). That argument
applies at least as strongly to *shipping* the derived measurements as to *keeping* the
file — arguably more strongly, because retention is not distribution and shipping is. The
project is currently strict where the risk is lower and silent where it is higher.

**The decision this needs (not made here):** either (a) ND is fine for measurement because
a 28-d descriptor is not a derivative work in the relevant sense — in which case say so
explicitly and the retention refusal is over-strict; or (b) ND is not fine, in which case
`harvest.py` needs the ingest-time filter `sources.py` already has, and the production
store contains ND-derived rows that would need identifying. **Do not guess.** Note that
(b) has a cost: the store cannot tell you which rows came from ND recordings without
re-joining `CREDITS.md`, which it can do, since every recording's licence is recorded.

---

## 2. No attribution ships with the assets, and every CC licence in the corpus requires it

**Where:** `harvest.py:497-514` (`write_credits`) writes `CREDITS.md` into
`<store>/CREDITS.md`. The store lives under `pipeline/out/`, which is **gitignored**.
Checked directly against the built assets: no file in `app/static/birdy/` contains the
string `recordist` or `licence`/`license` — not `manifest.json`, not `points.json`, not
`inventory.json`, not any of the 2 423 `inventory/*.json` shards.

**What is wrong:** the shipped galaxy is derived from 10 184 field recordings, all of which
carry a recordist and most of which are CC BY-NC-SA. Attribution is required to travel with
the Licensed Material *and* with Adapted Material. It travels as far as a gitignored
directory on one machine.

**Why it matters:** this is the single clearest licensing gap in the project. It is also
cheap to close relative to its importance — the shard format already carries a per-species
`summary` string that says "Learned from 2 field recordings", so the species-level place to
put "recordists: …" already exists. The honest minimum is probably a `CREDITS.md` or
`credits.json` copied into the asset set at build time, plus a visible credit surface in the
app. `NOTICE.md` §3.1 records the gap rather than papering over it.

**Second-order:** `harvest.write_credits()` asserted in the file's own header text that
"the audio itself was discarded after analysis", which stopped being unconditionally true
when `--keep-audio` shipped. That sentence has been corrected in this pass (it was prose),
but it is worth knowing that a generated *legal* record had a false statement in it for as
long as the flag existed.

---

## 3. `harmonypy` is GPL-3.0-or-later inside a project that is otherwise CC BY-NC-SA

**Where:** `pipeline/pyproject.toml`, the `analysis` extra:
`analysis = ["harmonypy>=0.0.9", "pandas>=2.0"]`. Confirmed against the installed
distribution metadata: `harmonypy: GPL-3.0-or-later`. Consumer:
`pipeline/src/birdy_pipeline/batcheffect.py` (lazy import).

**What is wrong:** nothing, yet — but it was undeclared anywhere. GPL-3.0 is copyleft and
specifically does not permit adding a NonCommercial restriction to the GPL'd work or to a
combined work derived from it. Every other dependency in the tree is MIT / BSD / Apache-2.0
and raises no such question.

**Why it matters:** it is fine as things stand, because the extra is optional, nothing GPL'd
is vendored, and no result depends on redistributing it. It stops being fine the moment
anybody ships a built environment (a container, a conda pack, a frozen venv) containing both
this code and harmonypy. Recorded in `NOTICE.md` §2.2 with that boundary stated. **If the
`analysis` arm ever needs to be redistributable, the alternative is a non-GPL Harmony
implementation or a re-implementation** — `batcheffect.py`'s mean-centring baselines already
run on numpy alone, so two of the three arms are unaffected either way.

---

## 4. `verify-parity.mjs` reports 18 cases; two normative documents said 12 and 14

**Where:** `app/scripts/verify-parity.mjs` — running it prints
`all 18 cases agree; worst difference 2.78e-08`. `AGENTS.md` hard constraints said
"must stay 14/14"; `docs/09-learned-objective-plan.md` §9.4 said "must stay at 12/12".

**Status:** both numbers have been corrected to 18/18 in this pass, because they are prose.
**It is listed here anyway, because the failure mode is the interesting part:** a
*don't-break-this* gate whose threshold is written down wrong is a gate that passes while
being under-enforced. Two independent documents drifted to two different wrong numbers, and
neither was caught by anything, because the script reports its own count and nobody compares
it to the docs. **Worth fixing structurally, not textually:** have the script fail if its
case count changes without the constant being updated, or have `verify` read the expected
count from one place.

---

## 5. `centroids.json` ships a `note` field containing a stale size figure

**Where:** `pipeline/src/birdy_pipeline/galaxy.py`, the `vectors` block's `"note"` string
(around line 1722), which is written **into the asset** and is therefore present in
`app/static/birdy/centroids.json` on the shipped build. It read "at k = 27 862 that is a
44 MB parse on every cold load" — a pre-W5, pre-sidecar figure describing a build that was
never shipped.

**Status:** corrected in this pass (it is a documentation string, not behaviour). Flagged
because of the general point: **the pipeline writes explanatory prose into its own assets,
and that prose ages with no mechanism to notice.** `galaxy.py:1362`'s cap warning had the
same problem with a "48 MB" figure. Any number embedded in a generated asset should either
be computed at write time from the thing it describes, or not be a number.

---

## 6. The `K_CAP` comment still justifies the cap with two facts that are no longer true

**Where:** `pipeline/src/birdy_pipeline/galaxy.py:44-45` (as it was), inside the `K_CAP`
comment block: "Nothing downstream is quadratic in it — the shader holds one float per
cluster and the labels cull by collision."

**What was wrong:** by the time this was read, the shader held an RGBA `DataTexture`
(`uClusterState`) rather than per-cluster uniform floats — which is precisely the change
that allowed `K_CAP` to rise from 1 024 to 8 192 — and the label layer was a fixed 28-slot
pool rather than one tag per knot. **The conclusion ("nothing downstream is quadratic")
survived; both of its stated reasons had been replaced.**

**Status:** the comment is corrected. Flagged because a load-bearing constant justified by
two obsolete facts is how a cap gets raised or lowered for the wrong reason. The current
`K_CAP = 8192` is bounded by the `DataTexture` (1 024 wide, so 8 192 knots is 8 rows —
nowhere near a limit) and by `centroids.json` size, which the sidecar largely removed. **So
`K_CAP = 8192` may now be lower than anything actually constrains it**, and nobody has
re-derived what the real ceiling is.

---

## 7. The memberless-knot `(0,0,0)` invariant is documented as a lie and still unguarded in three places

**Where:** `app/src/lib/galaxy/layouts.ts` documents a memberless knot's centroid `(0,0,0)`
as a position that is not a position and that every positional effect must check `counts`
before using. Two consumers were fixed (`Framing.svelte`, and the nearest-neighbour median).
Per `HANDOFF.md`, still unguarded: **`ContextPaths` and `Trajectory`** (thread endpoints) and
**`NodeProjector`** (tag position).

**Why it matters:** latent, not live — both current builds have zero memberless knots, which
is exactly why it keeps surviving review. The failure mode when a build does have them is a
thread or a tag anchored at the origin, which reads as a rendering bug rather than as a data
condition. **This is a shared invariant enforced by convention at each call site**, which is
the pattern that produced the two bugs already found. A `centroidOf(i)` accessor that returns
`null` for a memberless knot would make it impossible to get wrong; three more comments will
not.

---

## 8. The pipeline writes 2.9 M relation pairs and ships 14 425 — the analysis path is still quadratic

**Where:** `pipeline/src/birdy_pipeline/relations.py` — `compute_relations` returns every
unordered species pair. `shipped_relations` trims the browser's copy and `write_relations`
applies it by default, which is the fix that took the asset from 760 MB to 5.6 MB.

**What is still true:** the *computation* is unchanged and quadratic in species count. At
2 423 species it is 2 929 410 pairs; the standalone `relations` verb still writes the whole
document, deliberately, because there the file is the analysis. **Species count only grows.**
`HANDOFF.md` names this as "the real bug" and the owner's call, and it still is: only 26 859
of 2.9 M pairs carry a shared type at all, so computing all of them to keep 0.9 % is the
shape of the problem, not the file size. Recorded here so the app-side 32 MB guard is not
mistaken for a fix.

---

## 9. "Lyrebird" the product now collides with lyrebirds the study species

**Where:** `docs/23-what-we-have-not-tried.md` §23.7 (W7, mimicry as ground truth) uses
"lyrebird" as an actual bird throughout — "the store holds **31** lyrebird syllables",
"A lyrebird singing a grey shrike-thrush", "Lyrebirds have three pairs of syringeal muscles".
`HANDOFF.md:773-774` likewise.

**Why it matters:** this is a naming consequence, not a bug, and it is worth knowing before
the repo is renamed. W7 is a live workstream whose entire premise is a specific genus
(*Menura*), and the product is now named after it. Sentences like "Lyrebird's lyrebird
corpus" are ahead. **The rename in this pass deliberately did not touch those occurrences** —
they refer to the animal. If the collision becomes a problem, the cheap mitigation is to use
the scientific name in §23.7 and reserve the capitalised word for the product. The whitepaper
already anticipates something like this: `docs/whitepaper/arxiv/README.md:188` has a "Rename
check" item noting the manuscript uses Lyrebird throughout "with one footnote".

---

## 10. Package identifiers and the product name have permanently diverged

**Where:** distribution `birdy-pipeline`, package `birdy_pipeline`, CLI entry point
`birdy-pipeline`, asset root `app/static/birdy/` (`cli.py:45` `DEFAULT_OUT`, mirrored by
`app/src/lib/data/assets.ts:5` `const ROOT = 'birdy'`), manifest field
`"pipeline": "birdy-pipeline"` (`galaxy.py:1930`), HTTP `Server:` header
`"birdy-pipeline"` (`server.py:1304`, which `vite-plugin-pipeline.ts` health-probes),
env vars `BIRDY_PIPELINE` / `BIRDY_PIPELINE_PORT` / `BIRDY_XC_PAUSE`, sessionStorage key
`birdy:evicted-foreign-sw`, type names `BirdyAssets` / `BirdyEngine`.

**Status:** all left alone deliberately, per the rename brief — they are contracts, and
`app/static/birdy/` in particular is the shipped asset contract. Recorded so the divergence
is a known state rather than an oversight, and so whoever eventually does the code-level
rename has the list. **The three that are more than cosmetic**, because something outside
the repo depends on them: the `Server:` header (probed by the Vite plugin), the asset root
(a URL path in built output), and the outbound `User-Agent`, which embeds the live GitHub URL
`https://github.com/sha5b/Birdy` and must keep resolving until the repo is actually renamed.
That URL was caught being renamed by the sweep and reverted.

---

## 11. `docs/08` §8.3 listed an asset that does not ship and omitted four that do

**Where:** `docs/08-implementation.md` §8.3 — the normative asset layout. It listed
`novel-pool.json`, which is absent from `app/static/birdy/`, and omitted
`point-features.f32`, `space-map.f32`, `projection-basis.json` and the `inventory/` shard
directory, all four of which are present.

**Status:** corrected in this pass, including the note that `novel-pool.json` is written only
once `grow` has a pending pool and is therefore normally absent. Flagged because **§8.3 is
the normative contract between the two halves** and it had drifted from what the build
actually writes. `verify` checks the assets it knows about; nothing checks that the *document*
enumerates them. A build-time cross-check of §8.3's list against the written file set would
have caught this.

---

## Minor, recorded without argument

- `pipeline/src/birdy_pipeline/learn.py:271` — "Frames whose peak is outside the birdy
  band". "birdy" here is a descriptive adjective for the bird-frequency band, not the product
  name, so the rename correctly skipped it. It now reads oddly next to a product called
  Lyrebird. Reword to "the bird band" whenever that file is next touched.
- `docs/README.md` said "These 21 notes" with 23 notes present, and its index stopped at 21,
  omitting docs/22 and docs/23 — the two documents carrying the flags the shipped production
  build is made of. Corrected. Worth a habit: the index is the only route an agent has to
  those sections.
- `pipeline/analysis/README.md` mapped 5 of the 8 runners in its directory, omitting
  `w6_birdnet_arms.py`, `inverse_compare.py`, `score_two_start.py` and `inverse_gate.md` —
  i.e. the whole amortised-inverse negative result. Corrected. `AGENTS.md` points agents at
  that table as the map of one-off measurements, so a gap in it hides a pre-registered gate.
- The `--source harvest` shim was removed from `cli.py` but was still documented as a live
  option in `pipeline/README.md`'s build-options table, and `galaxy.py:1609` still referred to
  it by name. Both corrected.
- `pipeline/README.md` gave `--variants` a default of 96; the actual default is 24
  (`cli.py:3107`). Corrected.
