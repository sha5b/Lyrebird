#!/usr/bin/env bash
# The full production chain on the re-derived corpus, run unattended.
#
# v10 = the v9 recipe on a corpus that has been re-segmented in band from local audio.
# Derived from run_production_v9.sh rather than replacing it, because that script IS the
# record of what produced the shipped v9 build. The RECIPE is unchanged except where noted
# below; what changed is the store underneath it.
#
# WHAT CHANGED, and why a re-learn is not a no-op:
#
#   * The corpus is re-segmented. v9's store, out/harvest-gan, is MIXED: only rows ingested
#     after `learn.SEGMENT_BAND_HZ` landed were segmented in band, so roughly 340 000 of its
#     378 224 rows are full-band and `state.json`'s `segmentBand` records only the latest
#     regime — it cannot say the store is mixed. Every per-row statistic on v9's corpus is
#     therefore pooled across two different meters. out/harvest-inband is re-segmented in
#     band throughout, from the local audio caches, and is the first internally consistent
#     store this project has had.
#   * A 0 dB SNR floor is applied (owner decision 2026-08-05): rows with a negative ratio are
#     dropped. The near-free floor — 3.6 % of rows and 97 species for +0.5 dB on the census —
#     chosen over 3/6 dB because the project's resource claim is breadth.
#   * The corpus GREW. Measured, not projected: 378 215 -> 435 630 syllables, retention 1.15,
#     where `v10_resegment_yield.py` had projected 0.777. The projection measured per-recording
#     yield and then applied it as if the recording set were fixed; it is not. state.json lists
#     11 687 recordings but only 9 026 contributed a syllable, because `add_syllables` enforces
#     the cap by retiring whole recordings. In band each recording yields about a fifth fewer
#     rows, so the cap binds less and 2 661 previously-retired recordings return.
#   * Species over learn.MIN_OBSERVATIONS = 24: 2 648 -> 2 488. The cost is 160 species, not
#     the ~710 projected. Expect the fit to cover ~2 488 species.
#   * The store's syllableCap is 600 000, not v9's 400 000. This is a deliberate deviation:
#     v9's cap never bound (378 224 rows under 400 000), while the in-band yield of 435 630
#     does. Leaving it at 400 000 would have made this store differ from v9's by the
#     segmentation AND by cap trimming — two changes at once. Measured afterwards: the cap
#     made no difference to the species count (2 488 either way), so it removed a confound
#     rather than buying coverage.
#
# THE DEVIATION THAT WAS ATTEMPTED AND DID NOT HAPPEN: `learn --jobs 8`. The intent was to
# parallelise a fit that took v9 2 h 58 m serially on a corpus 15 % smaller. **The flag was
# silently ignored and the fit ran serially, exactly as v9 did.** `learn.py:3492` refuses the
# pool whenever `--inverse` is passed — the encoder holds a torch model that cannot cross into
# a worker process — and this recipe passes `--inverse`, so the pool was never built:
#
#   learn.log:5  --jobs 8 ignored: the inverse encoder holds a torch model and cannot
#                cross into a worker process — fitting serially
#
# The flag is left in place because removing it would erase the record of the attempt, and
# because the outcome is the better one: v10's fit used v9's method, so the comparison between
# them is of the corpus and nothing else. Measured: 3 h 03 m against v9's 2 h 58 m.
# To actually parallelise, `--inverse` would have to go — which changes the recipe.
#
# Order matters and is not arbitrary — see run_production_v9.sh for the reasoning behind each
# stage. The current inventory is NOT touched: everything lands in a staging directory and the
# install is a separate, deliberate step once `verify` has passed.
#
# `--clustering label`, matching v9, so the built assets are comparable to what shipped. The
# hdbscan "unknown" map is deliberately NOT built here: measuring how many points a density
# clustering leaves unassigned is worth doing, but as its own build rather than as a change to
# the one run that has to stay comparable.

set -uo pipefail
cd "$(dirname "$0")/.."          # pipeline/

STAGE=out/v10
STORE=out/harvest-inband
INV=../data/learned-inventory.json
LEARNED=$STAGE/learned-v10.json
LOG=$STAGE/chain.log

if [ ! -f "$STORE/state.json" ]; then
    printf 'no store at %s — run analysis/v10_resegment_store.py first\n' "$STORE"
    exit 1
fi

mkdir -p "$STAGE"
: > "$LOG"

say() { printf '\n=== %s :: %s ===\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }
die() { printf '\nFAILED at %s (see %s)\n' "$1" "$LOG" | tee -a "$LOG"; exit 1; }

say "stage 0: seed the staging inventory so learn keeps the existing type ids"
# `learn` reads its id-stability prior from its own --out path (cli.py: previous_fit(out)),
# so the staging file is SEEDED with the current inventory. Without that, every learned
# syllable is renamed and the galaxy's labels stop meaning anything.
cp -f "$INV" "$LEARNED" || die "seed"
python3 - "$LEARNED" <<'PY' | tee -a "$LOG"
import json, sys
d = json.load(open(sys.argv[1]))
n = sum(len(s['syllables']) for s in d['species'])
print(f"  seeded with {len(d['species'])} species / {n} syllables of prior ids")
PY

python3 - "$STORE" <<'PY' | tee -a "$LOG"
import json, sys
s = json.load(open(f"{sys.argv[1]}/state.json"))
print(f"  store: {s['syllableObservations']} syllables, cap {s['syllableCap']}, "
      f"segmentBand {s['segmentBand']}")
PY

say "stage 1: learn, with the two-start descent (the long one; v9 took 2 h 58 m serially)"
# NO --inventory. `cmd_learn` ends with
#   write_learned_inventory(out, merge_learned_inventory(inventory, document))
# so --inventory is MERGED BACK INTO THE FIT to preserve the hand-authored calls. It wants
# the authored data/inventory.json (12 species, 44 syllables), which is the default. Passing
# data/learned-inventory.json instead merges every fitted type back in as though a person had
# written it and the inventory comes out doubled. Omit it.
uv run lyrebird-pipeline learn \
    --store "$STORE" \
    --out "$LEARNED" \
    --inverse out/inverse.pt \
    --inverse-two-start \
    --jobs 8 \
    >> "$STAGE/learn.log" 2>&1 || die "learn"
tail -4 "$STAGE/learn.log" | tee -a "$LOG"

say "stage 2: docrefit - a measured texture for the authored documented calls"
uv run lyrebird-pipeline docrefit \
    --store "$STORE" \
    --inventory "$LEARNED" \
    --out "$LEARNED" \
    --report "$STAGE/docrefit-report.json" \
    >> "$STAGE/docrefit.log" 2>&1 || die "docrefit"
tail -6 "$STAGE/docrefit.log" | tee -a "$LOG"

say "stage 3: respfit - respiration and two-voice where they win their gate"
uv run lyrebird-pipeline respfit \
    --store "$STORE" \
    --inventory "$LEARNED" \
    --out "$LEARNED" \
    --report "$STAGE/respfit-report.json" \
    --jobs 8 \
    >> "$STAGE/respfit.log" 2>&1 || die "respfit"
tail -6 "$STAGE/respfit.log" | tee -a "$LOG"

say "stage 4: build the galaxy from the re-derived inventory"
uv run lyrebird-pipeline build \
    --harvest-store "$STORE" \
    --inventory "$LEARNED" \
    --space embed \
    --clustering label \
    --out "$STAGE/assets" \
    --projection pacmap \
    --no-compare-projections \
    --no-relations \
    >> "$STAGE/build.log" 2>&1 || die "build"
tail -20 "$STAGE/build.log" | tee -a "$LOG"

say "stage 5: verify the built assets"
uv run lyrebird-pipeline verify --out "$STAGE/assets" >> "$STAGE/verify.log" 2>&1 || die "verify"
tail -6 "$STAGE/verify.log" | tee -a "$LOG"

say "stage 6: the song funnel, against the inventory currently installed"
uv run python analysis/song_funnel.py "$INV" "$LEARNED" 2>&1 | tee -a "$LOG"

say "CHAIN COMPLETE - nothing installed yet, by design"
printf '  inventory : %s\n  assets    : %s\n' "$LEARNED" "$STAGE/assets" | tee -a "$LOG"
