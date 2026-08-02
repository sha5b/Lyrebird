#!/usr/bin/env bash
# The full production chain with every measured-best method applied, run unattended.
#
# Order matters and is not arbitrary:
#   1. learn      re-derives the inventory with the two-start descent (gate: +0.0330 median
#                 resynthesis cosine, 0 of 1661 types worse - inverse_gate.md)
#   2. docrefit   gives the 44 authored documented calls a measured texture. They are at
#                 gesture defaults today (gammaScale 1.0, tractQ/noise/rough 0 on 100 % of
#                 them), which is why they render as "a sine with an organ envelope"
#                 (docs/21 §21.2). Runs AFTER learn because learn rewrites the inventory.
#   3. respfit    per-species respiration + two-voice where they beat the plain render by
#                 the same 0.02 margin (docs/16 §16.4: won 445 of 12 680 types).
#   4. build      the galaxy, --clustering label, which is what shipped and what measured
#                 best (+4.3 points of field-point retrieval, docs/22 §22.8).
#
# The current inventory is NOT touched. Everything lands in a staging directory and the
# install is a separate, deliberate step once `verify` has passed.
#
# `learn` reads its id-stability prior from its own --out path (cli.py: previous_fit(out)),
# so the staging file is SEEDED with the current inventory. Without that, every learned
# syllable is renamed and the galaxy's labels stop meaning anything.

set -uo pipefail
cd "$(dirname "$0")/.."          # pipeline/

STAGE=/tmp/birdy-prod/v6
STORE=out/harvest-gan
INV=../data/learned-inventory.json
LEARNED=$STAGE/learned-v6.json
LOG=$STAGE/chain.log

mkdir -p "$STAGE"
: > "$LOG"

say() { printf '\n=== %s :: %s ===\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }
die() { printf '\nFAILED at %s (see %s)\n' "$1" "$LOG" | tee -a "$LOG"; exit 1; }

say "stage 0: seed the staging inventory so learn keeps the existing type ids"
cp -f "$INV" "$LEARNED" || die "seed"
python3 - "$LEARNED" <<'PY' | tee -a "$LOG"
import json, sys
d = json.load(open(sys.argv[1]))
n = sum(len(s['syllables']) for s in d['species'])
print(f"  seeded with {len(d['species'])} species / {n} syllables of prior ids")
PY

say "stage 1: learn, with the two-start descent (this is the long one, ~2 h)"
# NO --inventory. `cmd_learn` ends with
#   write_learned_inventory(out, merge_learned_inventory(inventory, document))
# so --inventory is MERGED BACK INTO THE FIT to preserve the hand-authored calls. It wants
# the authored data/inventory.json (12 species, 44 syllables), which is the default. The
# first v6 attempt passed data/learned-inventory.json instead — 2 423 species and 13 859
# FITTED types — so every fitted type was merged in as though a person had written it and
# the inventory came out doubled: hirundo_rustica had 16 syllables with L09/L13/L14/L19/L21
# each appearing twice. Arms A-D omitted the flag and were clean. Omit it.
uv run birdy-pipeline learn \
    --store "$STORE" \
    --out "$LEARNED" \
    --inverse out/inverse.pt \
    --inverse-two-start \
    >> "$STAGE/learn.log" 2>&1 || die "learn"
tail -4 "$STAGE/learn.log" | tee -a "$LOG"

say "stage 2: docrefit - a measured texture for the authored documented calls"
uv run birdy-pipeline docrefit \
    --store "$STORE" \
    --inventory "$LEARNED" \
    --out "$LEARNED" \
    --report "$STAGE/docrefit-report.json" \
    >> "$STAGE/docrefit.log" 2>&1 || die "docrefit"
tail -6 "$STAGE/docrefit.log" | tee -a "$LOG"

say "stage 3: respfit - respiration and two-voice where they win their gate"
uv run birdy-pipeline respfit \
    --store "$STORE" \
    --inventory "$LEARNED" \
    --out "$LEARNED" \
    --report "$STAGE/respfit-report.json" \
    --jobs 8 \
    >> "$STAGE/respfit.log" 2>&1 || die "respfit"
tail -6 "$STAGE/respfit.log" | tee -a "$LOG"

say "stage 4: build the galaxy from the re-derived inventory"
uv run birdy-pipeline build \
    --harvest-store "$STORE" \
    --inventory "$LEARNED" \
    --space embed \
    --clustering label \
    --out "$STAGE/assets" \
    --no-compare-projections \
    --no-relations \
    >> "$STAGE/build.log" 2>&1 || die "build"
tail -20 "$STAGE/build.log" | tee -a "$LOG"

say "stage 5: verify the built assets"
uv run birdy-pipeline verify --assets "$STAGE/assets" >> "$STAGE/verify.log" 2>&1 || die "verify"
tail -6 "$STAGE/verify.log" | tee -a "$LOG"

say "CHAIN COMPLETE - nothing installed yet, by design"
printf '  inventory : %s\n  assets    : %s\n' "$LEARNED" "$STAGE/assets" | tee -a "$LOG"
