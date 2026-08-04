"""Re-judge the two-voice adoption on the spectral bench. The paper says this is owed.

The Limitations section: *"A re-judgment of every cosine-gated adoption on the spectral bench
is owed."* `rejudge_respfit.py` paid that for respiration and said the two-voice adoption
"is not usable this way --- `two` is present on winners and non-winners alike, so stripping it
does not reconstruct a clean control".

**That was the wrong field, and the right one isolates perfectly.** `two` is a boolean gesture
axis of the descent (`learn.py`'s axis list), searched for every type. The *fitted second
voice* is `voices`, and `respfit.fit_type_two_voice` writes it exactly the way respiration is
written --- `trial = dict(syl); trial["voices"] = block`, kept only when the gain clears
`--margin` --- so it is present on winners and on nothing else, and removing it restores the
syllable the fit started from in every other respect.

Checked against the run's own report rather than argued (`out/v9/respfit-report.json`):

    shipped syllables carrying `voices`   2144
    report's twoVoiceWon                  2144
    shipped but not a winner                 0
    winners lacking `voices`                 0
    block differing from the report's        0

Note what stays in place in *both* arms: a type that also won respiration keeps its
respiration block on both sides, so this measures the two-voice adoption alone.

**Why this is not circular.** The adoption was decided on the 28-d descriptor cosine and is
re-judged here on mel-cepstral distortion, an independent metric that agrees with
multi-resolution STFT error at 0.925 and which the cosine correlates with at Spearman
**+0.200** --- significant, and the wrong sign (`analysis/specbench_n1200.json`, n = 1200).
No selection happens on the metric being reported.

**PRE-REGISTERED, before the run.** The same prediction as the respiration re-judgment, made
for the same reason and not adjusted after seeing that one lose:

    MCD win share < 50 %, and the median dMCD <= 0 dB.

A win share at or above 50 % would mean the cosine gate is at worst harmless here. Either
outcome is reportable and neither moves the bar afterwards. This population is 2 144 types
against respiration's 204, so it is the stronger test of the two.

Usage:  .venv/bin/python analysis/rejudge_twovoice.py
"""

from __future__ import annotations

import copy
import json
import statistics as st
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent

INVENTORY = REPO / "data/learned-inventory.json"
STORE = ROOT / "out/harvest-gan"
CALIB_DIR = ROOT / "out"
REPORT = ROOT / "out/v9/respfit-report.json"
WORK = ROOT / "out/rejudge-twovoice"
OUT = Path(__file__).resolve().parent / "rejudge_twovoice.json"

#: Pre-registered above. Constants so the verdict cannot drift.
PREDICTED_WIN_SHARE_BELOW = 50.0
#: Above the adopted count, so the bench takes every adopted type and the population is
#: the adoption rather than a sample of it.
BENCH_LIMIT = 3000

#: The field that isolates the adoption, and the one that does not.
ADOPTION_FIELD = "voices"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def subset(inv: dict, keys: set[tuple[str, str]], strip: bool) -> dict:
    """The inventory cut to `keys`, optionally with the fitted second voice removed."""
    out = {k: v for k, v in inv.items() if k != "species"}
    species = []
    for sp in inv.get("species", []):
        keep = []
        for s in sp.get("syllables", []):
            if (sp["id"], str(s.get("id"))) not in keys:
                continue
            s2 = copy.deepcopy(s)
            if strip:
                s2.pop(ADOPTION_FIELD, None)
            keep.append(s2)
        if keep:
            sp2 = {k: v for k, v in sp.items() if k != "syllables"}
            sp2["syllables"] = keep
            species.append(sp2)
    out["species"] = species
    return out


def verify_isolation(inv: dict) -> tuple[set[tuple[str, str]], dict]:
    """The reversibility argument, as a check rather than a claim.

    Returns the adopted keys and the audit counts, and refuses to continue if the field
    is not exactly the set of winners the run's own report recorded.
    """
    shipped = {
        (sp["id"], str(s.get("id")))
        for sp in inv.get("species", [])
        for s in sp.get("syllables", [])
        if s.get(ADOPTION_FIELD)
    }
    audit = {"shipped": len(shipped)}
    if REPORT.exists():
        recs = {
            (r["speciesId"], str(r["typeId"])): r
            for r in json.loads(REPORT.read_text())["records"]
        }
        winners = {
            k for k, r in recs.items() if ((r.get("twoVoice") or {}).get("block"))
        }
        blocks = {k: recs[k]["twoVoice"]["block"] for k in winners}
        by_key = {
            (sp["id"], str(s.get("id"))): s
            for sp in inv.get("species", [])
            for s in sp.get("syllables", [])
        }
        audit |= {
            "report_winners": len(winners),
            "shipped_not_winner": len(shipped - winners),
            "winner_not_shipped": len(winners - shipped),
            "block_mismatch": sum(
                1
                for k in winners & shipped
                if by_key[k].get(ADOPTION_FIELD) != blocks[k]
            ),
        }
        bad = (
            audit["shipped_not_winner"]
            or audit["winner_not_shipped"]
            or audit["block_mismatch"]
        )
        if bad:
            raise SystemExit(
                f"`{ADOPTION_FIELD}` is not exactly the winner set: {audit}. "
                "The strip-the-field control is invalid; do not report a number from it."
            )
    else:
        log(f"  WARNING: {REPORT} absent, isolation unverified against the run's report")
    return shipped, audit


def bench(inv_path: Path, out_path: Path) -> dict:
    # Benching 2 144 types twice is about ten minutes, so a completed arm is reused
    # unless `--refresh` is passed. Delete out/rejudge-twovoice to force both arms.
    if out_path.exists() and "--refresh" not in sys.argv:
        log(f"  reusing {out_path.name} (pass --refresh to re-bench)")
        return json.loads(out_path.read_text())
    cmd = [
        str(ROOT / ".venv/bin/birdy-pipeline"), "specbench",
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

    adopted, audit = verify_isolation(inv)
    log(f"types carrying a fitted second voice: {len(adopted)}")
    log(f"isolation audit: {audit}")
    if len(adopted) < 20:
        log("too few to measure")
        return 1

    after_p, before_p = WORK / "after.json", WORK / "before.json"
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
        log("no type benched in both arms - check the bench's skip reasons")
        return 1

    d_mcd, d_stft, d_cos = [], [], []
    for k in common:
        # MCD is a distortion: lower is better, so a win is before - after > 0.
        d_mcd.append(rb[k]["mcdDb"] - ra[k]["mcdDb"])
        d_stft.append(rb[k]["stftDb"] - ra[k]["stftDb"])
        d_cos.append((ra[k].get("cosine") or 0) - (rb[k].get("cosine") or 0))

    wins = sum(1 for v in d_mcd if v > 0)
    share = 100.0 * wins / len(d_mcd)

    # Whether a win share this far from half is distinguishable from a coin. The
    # respiration arm did not need this — 33.1 % on 175 types is not a near-miss — but
    # 55.6 % is, and a "held" verdict cannot rest on an eyeballed majority. Sign test on
    # the win counts, Wilcoxon signed-rank on the magnitudes, both metrics.
    from scipy import stats  # noqa: PLC0415 — only this block needs it

    sig = {
        "sign_test_mcd_p": float(stats.binomtest(wins, len(d_mcd), 0.5).pvalue),
        "wilcoxon_mcd_p": float(stats.wilcoxon(d_mcd).pvalue),
        "wilcoxon_stft_p": float(stats.wilcoxon(d_stft).pvalue),
        # Within the adopted set only, and note this is deltas against deltas, not the
        # absolute cosine-against-absolute-MCD relation of specbench_n1200. A positive
        # value here does not contradict that anti-correlation; it is a different pair
        # of quantities on a population selected for having won the gate.
        "spearman_dcosine_vs_dmcd": float(stats.spearmanr(d_cos, d_mcd).statistic),
        "spearman_dcosine_vs_dmcd_p": float(stats.spearmanr(d_cos, d_mcd).pvalue),
    }

    result = {
        "adoption": "two-voice, per-type fit (respfit stage 2)",
        "isolating_field": ADOPTION_FIELD,
        "isolation_audit": audit,
        "adopted_types": len(adopted),
        "benched_both_arms": len(common),
        "mcd_win_share_percent": share,
        "mcd_wins": wins,
        "median_delta_mcd_db": st.median(d_mcd),
        "mean_delta_mcd_db": st.fmean(d_mcd),
        "median_delta_stft_db": st.median(d_stft),
        "stft_win_share_percent": 100.0 * sum(1 for v in d_stft if v > 0) / len(d_stft),
        "median_delta_cosine": st.median(d_cos),
        "min_delta_cosine": min(d_cos),
        "significance": sig,
        "prediction": f"win share < {PREDICTED_WIN_SHARE_BELOW} % and median dMCD <= 0",
        "prediction_held": bool(
            share < PREDICTED_WIN_SHARE_BELOW and st.median(d_mcd) <= 0.0
        ),
    }

    print("=" * 74)
    print("Re-judging the two-voice adoption on the spectral bench")
    print("=" * 74)
    print(f"  adopted types (cosine gain >= 0.02)   {len(adopted):5d}")
    print(f"  benched in both arms                  {len(common):5d}")
    print()
    print(f"  MCD win share      {share:6.1f} %   ({wins}/{len(d_mcd)})")
    print(f"  median dMCD        {result['median_delta_mcd_db']:+6.2f} dB   "
          "(positive = the adoption improved audible distortion)")
    print(f"  mean   dMCD        {result['mean_delta_mcd_db']:+6.2f} dB")
    print(f"  median dSTFT       {result['median_delta_stft_db']:+6.2f} dB   "
          f"(win share {result['stft_win_share_percent']:.1f} %)")
    print(f"  median dcosine     {result['median_delta_cosine']:+6.3f}   "
          f"(the gate's own number; the smallest is {min(d_cos):+.3f}, and the gate "
          "required +0.02, so the arms are paired correctly)")
    print()
    print(f"  sign test on MCD wins        p = {sig['sign_test_mcd_p']:.2e}")
    print(f"  Wilcoxon on dMCD             p = {sig['wilcoxon_mcd_p']:.2e}")
    print(f"  Wilcoxon on dSTFT            p = {sig['wilcoxon_stft_p']:.2e}")
    print()
    print(f"  PRE-REGISTERED PREDICTION: {result['prediction']}")
    print(f"  held: {result['prediction_held']}")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
