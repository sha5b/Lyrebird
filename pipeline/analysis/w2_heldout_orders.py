"""W2's second-order arm, re-run with the unbiased estimator (docs/23 §23.2.2).

The gate is pre-registered in `seqstats.HELD_OUT_GAIN_BITS` / `HELD_OUT_SHARE_POINTS`
and was written before this ran:

  median d(1->2) >= 0.05 bits/token, AND >= control + 0.05, AND the share of species
  gaining at all >= control's share + 20 points.

Same corpus as §23.2.1 (34 696 bouts, 327 164 tokens, 2 421 species), same control
(docs/12's within-species shuffle), same 80/20 bout split as the docs/18 bake-off.
"""

import json
import time
from pathlib import Path

from lyrebird_pipeline import seqstats
from lyrebird_pipeline.harvest import HarvestStore

t0 = time.time()
store = HarvestStore(Path("out/harvest-gan"))
store.load()
bouts = seqstats.load_bouts(store)
print(f"corpus: {len(bouts)} bouts, {sum(len(t) for _, t, _ in bouts)} tokens, "
      f"{len({s for s, _, _ in bouts})} species", flush=True)

control = seqstats.shuffled(bouts, seed=0)
out = {}
for name, data in (("real", bouts), ("control", control)):
    t = time.time()
    out[name] = seqstats.held_out_scaling(data, seed=0)
    print(f"{name}: {out[name]['speciesMeasured']} species measured in "
          f"{time.time() - t:.1f}s", flush=True)
    print(f"  median curve (bits/token, k=0..3): {out[name]['medianCurve']}", flush=True)
    print(f"  median d(1->2) {out[name]['medianD12']}  share positive "
          f"{out[name]['sharePositiveD12']} %", flush=True)
    print(f"  median d(2->3) {out[name]['medianD23']}  share positive "
          f"{out[name]['sharePositiveD23']} %", flush=True)

r, c = out["real"], out["control"]
passes = (
    r["medianD12"] >= seqstats.HELD_OUT_GAIN_BITS
    and r["medianD12"] >= c["medianD12"] + seqstats.HELD_OUT_GAIN_BITS
    and r["sharePositiveD12"] >= c["sharePositiveD12"] + seqstats.HELD_OUT_SHARE_POINTS
)
print("\n| statistic | real | control |")
print("|---|---|---|")
print(f"| held-out CE k=0..3 (bits/token) | {r['medianCurve']} | {c['medianCurve']} |")
print(f"| median gain, order 1 -> 2 | {r['medianD12']} | {c['medianD12']} |")
print(f"| species gaining at 1 -> 2 | {r['sharePositiveD12']} % | {c['sharePositiveD12']} % |")
print(f"| median gain, order 2 -> 3 | {r['medianD23']} | {c['medianD23']} |")
print(f"| species gaining at 2 -> 3 | {r['sharePositiveD23']} % | {c['sharePositiveD23']} % |")
print(f"\nGATE (pre-registered): {'PASSES' if passes else 'FAILS'}")
print(f"total {time.time() - t0:.1f}s")

(Path(__file__).resolve().parent / "w2_heldout_orders.json").write_text(
    json.dumps({"real": r, "control": c, "passes": passes}, indent=1)
)
