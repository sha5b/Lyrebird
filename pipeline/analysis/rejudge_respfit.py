"""Re-judge a cosine-gated adoption on the spectral bench. The paper says this is owed.

The Limitations section: *"A re-judgment of every cosine-gated adoption on the spectral bench is
owed."* This pays that debt for the one adoption that can be paid without refitting.

**Why respiration and not the others.** `respfit` ships a respiratory block on a type only where
it beats that type's resynthesis cosine by `--margin` (0.02). In the shipped v9 inventory the
`respiration` field is present on **exactly** the types where it won and on none of the others,
so the adoption is isolated and additively reversible: strip the field and you have the
pre-adoption syllable, byte-for-byte in every other respect. The two-voice adoption is not
usable this way --- `two` is present on winners and non-winners alike, so stripping it does not
reconstruct a clean control. `docrefit` and the fricative routing would each need their own
reversibility argument. Those three remain owed.

**Why this is not circular.** The adoption was decided on the 28-d descriptor cosine. It is
re-judged here on mel-cepstral distortion, an independent metric that agrees with multi-resolution
STFT error at 0.925 and which the cosine correlates with at Spearman **+0.200** --- significant,
and the wrong sign (`analysis/specbench_n1200.json`, n = 1200). No selection happens on the
metric being reported.

**PRE-REGISTERED, before the run.** If the cosine gate were neutral with respect to audible
fidelity, about half of the adopted types would improve on MCD by chance. The measured
cosine-MCD relationship is positive, meaning higher cosine goes with *more* distortion, so the
prediction is:

    MCD win share < 50 %, and the median dMCD <= 0 dB.

A win share at or above 50 % would mean the cosine gate is at worst harmless here, and the
n = 1200 anti-correlation does not reach into this adoption. Either outcome is reportable and
neither moves the bar afterwards.

Usage:  .venv/bin/python analysis/rejudge_respfit.py
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent

INVENTORY = REPO / "data/learned-inventory.json"
STORE = ROOT / "out/harvest-gan"
CALIB_DIR = ROOT / "out"
WORK = ROOT / "out/rejudge"
OUT = Path(__file__).resolve().parent / "rejudge_respfit.json"

#: Pre-registered above. Stated as constants so the verdict cannot drift.
PREDICTED_WIN_SHARE_BELOW = 50.0
BENCH_LIMIT = 4000


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def subset(inv: dict, keys: set[tuple[str, str]], strip_respiration: bool) -> dict:
    """The inventory cut to `keys`, optionally with the respiration block removed.

    Everything else about each syllable is left exactly as it shipped, so the two arms
    differ in one field and nothing else.
    """
    out = {k: v for k, v in inv.items() if k != "species"}
    species = []
    for sp in inv.get("species", []):
        keep = []
        for s in sp.get("syllables", []):
            if (sp["id"], str(s.get("id"))) not in keys:
                continue
            s2 = copy.deepcopy(s)
            if strip_respiration:
                s2.pop("respiration", None)
            keep.append(s2)
        if keep:
            sp2 = {k: v for k, v in sp.items() if k != "syllables"}
            sp2["syllables"] = keep
            species.append(sp2)
    out["species"] = species
    return out


def bench(inv_path: Path, out_path: Path) -> dict:
    cmd = [
        str(ROOT / ".venv/bin/lyrebird-pipeline"), "specbench",
        "--store", str(STORE),
        "--inventory", str(inv_path),
        "--calibration-dir", str(CALIB_DIR),
        "--limit", str(BENCH_LIMIT),
        "--out", str(out_path),
    ]
    log(f"  benching {inv_path.name} ...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        log(r.stdout[-2000:]); log(r.stderr[-2000:])
        raise SystemExit(f"specbench failed on {inv_path.name}")
    return json.loads(out_path.read_text())


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    inv = json.loads(INVENTORY.read_text())

    adopted = {
        (sp["id"], str(s.get("id")))
        for sp in inv.get("species", [])
        for s in sp.get("syllables", [])
        if s.get("respiration") not in (None, {}, [])
    }
    log(f"types carrying a shipped respiration block: {len(adopted)}")
    if len(adopted) < 20:
        log("too few to measure")
        return 1

    after_p = WORK / "after.json"
    before_p = WORK / "before.json"
    after_p.write_text(json.dumps(subset(inv, adopted, False)))
    before_p.write_text(json.dumps(subset(inv, adopted, True)))

    a = bench(after_p, WORK / "bench-after.json")
    b = bench(before_p, WORK / "bench-before.json")

    def rows(rep):
        # specbench names the columns `species` and `typeId`, not `speciesId`.
        return {(r["species"], r["typeId"]): r for r in rep.get("types", [])}

    ra, rb = rows(a), rows(b)
    common = sorted(set(ra) & set(rb))
    log(f"benched both ways: {len(common)} types")
    if not common:
        log("no type benched in both arms — check the bench's skip reasons")
        return 1

    import statistics as st
    d_mcd, d_stft, d_cos = [], [], []
    for k in common:
        # MCD is a distortion: lower is better, so a win is before - after > 0.
        d_mcd.append(rb[k]["mcdDb"] - ra[k]["mcdDb"])
        d_stft.append(rb[k]["stftDb"] - ra[k]["stftDb"])
        d_cos.append((ra[k].get("cosine") or 0) - (rb[k].get("cosine") or 0))

    wins = sum(1 for v in d_mcd if v > 0)
    share = 100.0 * wins / len(d_mcd)
    result = {
        "adopted_types": len(adopted),
        "benched_both_arms": len(common),
        "mcd_win_share_percent": share,
        "mcd_wins": wins,
        "median_delta_mcd_db": st.median(d_mcd),
        "mean_delta_mcd_db": st.fmean(d_mcd),
        "median_delta_stft_db": st.median(d_stft),
        "median_delta_cosine": st.median(d_cos),
        "prediction": f"win share < {PREDICTED_WIN_SHARE_BELOW} % and median dMCD <= 0",
        "prediction_held": bool(share < PREDICTED_WIN_SHARE_BELOW
                               and st.median(d_mcd) <= 0.0),
    }

    print("=" * 74)
    print("Re-judging the respiration adoption on the spectral bench")
    print("=" * 74)
    print(f"  adopted types (cosine gain >= 0.02)   {len(adopted):5d}")
    print(f"  benched in both arms                  {len(common):5d}")
    print()
    print(f"  MCD win share      {share:6.1f} %   ({wins}/{len(d_mcd)})")
    print(f"  median dMCD        {result['median_delta_mcd_db']:+6.2f} dB   "
          "(positive = the adoption improved audible distortion)")
    print(f"  mean   dMCD        {result['mean_delta_mcd_db']:+6.2f} dB")
    print(f"  median dSTFT       {result['median_delta_stft_db']:+6.2f} dB")
    print(f"  median dcosine     {result['median_delta_cosine']:+6.3f}   "
          "(the gate's own number, for the sanity check)")
    print()
    print(f"  PRE-REGISTERED PREDICTION: {result['prediction']}")
    print(f"  held: {result['prediction_held']}")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
