# One-off measurement runners

Arms that were run once, against a fixed store or a fixed dumped matrix, to settle a
question recorded in `docs/`. They are here rather than in `src/birdy_pipeline/` because
nothing imports them and nothing ships them — but they are here rather than in `/tmp`
because **the pre-registered gate of each run is the docstring at the top of its file**,
and a result whose gate cannot be re-read is not evidence.

Each one states its gate before its code, names the population it drew, and prints a table.
Paths are absolute and point at this machine's stores; a different machine needs those three
constants changed and nothing else.

| file | question | verdict | evidence |
|---|---|---|---|
| `w2_heldout_orders.py` | is there structure beyond first order? | no — median species loses 0.09 bits/token at order 2 | docs/23 §23.2.2 |
| `w5_label_arms.py` | label assignment against the shipped kmeans path | +2.5 pts uncapped (gate wanted +10), +14.2 at production's shed ratio | docs/22 §22.8 |
| `w5_field_retrieval.py` | the same four arms on one query population | label assignment +4.3 pts; W5 itself +0.02 | docs/22 §22.8 |
| `w6_t1_perch_recordist.py` | does an external 100x-scale space escape the recordist confound? | no — recordist lift 0.0891 -> 0.0744, gate wanted -30 % | docs/23 §23.6.1 |
| `w6_t3_perch_species.py` | does it retrieve species better? | yes, 8x (0.0074 -> 0.0588), and recordist still outranks species | docs/23 §23.6.2 |

`w5_field_retrieval.py` and `w6_t3_perch_species.py` import helpers from their siblings, so
run them from this directory (or with it on `sys.path`; the W6 pair does that itself).

The two W5 runners read one fixed matrix, `/tmp/birdy-debug/points-debug100.npz` — the
debug-100 `build --dump-points` set (214 154 points, 2 143 types, 96 MB) that docs/22 §22.6's
table was measured on. It is outside the repo on purpose and it is not backed up: regenerate
it with `build --dump-points` and expect the absolute numbers to move, since the arms are
only comparable to each other while the matrix is fixed.

The W6 runners need the `perch` extra and the 391 MB Perch ONNX, which downloads on first
use: `uv sync --extra perch`. They read the embedding only and never fetch Perch's class
list — the labels are the one thing docs/23 §23.6 says must never become ground truth.
