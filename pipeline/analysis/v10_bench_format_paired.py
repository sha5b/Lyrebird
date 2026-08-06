"""A common band did not make the two bench arms addable. Is the residual format, or population?

The band cap was built so rows from the lossless iNat cache and the lossy xeno-canto cache
could be compared at all. It works — every row is measured at 11 025 Hz — and the gap between
the arms survives it:

    at the cap, n=1200      wav  n=230   median MCD  71.49 dB
                            mp3  n=970   median MCD  95.23 dB
                            Mann-Whitney p 3.3e-06, median gap 23.74 dB

So "mostly band, not fit" was only half right. 18 dB of the original 33 was the band; **23.7 dB
is something else**, and the arms still may not be averaged. Two candidates:

**Population.** The two arms are different types. `wav` covers 230 types and `mp3` 970 mostly
different ones, so the gap could be nothing but which birds each cache happens to hold and how
well the fit did on them.

**The recording, format included.** Lossy coding damages content below its own Nyquist, and the
two archives differ in recording conditions besides — so the same render scored against an
xeno-canto reference could genuinely land further away.

**The design that separates them.** 1 110 types have cached members in *both* formats. For each,
render the type **once** and score that one render against a wav reference and against an mp3
reference, both at the same 11 025 Hz cap. The type, its fit, and its render are then held
fixed, and population is gone by construction.

What remains inside the paired gap is the reference recording: coding loss and whatever else
separates an iNat recording of a bird from a xeno-canto one. The two are not separated here and
the result must not be read as coding alone.

**PRE-REGISTERED, before the run.**

1. If the 23.74 dB arm gap is mostly population, the paired median gap is under 5 dB.
2. If it is mostly the reference recording, the paired median gap keeps the sign (mp3 worse)
   and is at least 10 dB.
3. A gap between 5 and 10 dB is reported as "both contribute" and neither clause is claimed.

The Wilcoxon signed-rank test on the paired differences is the significance statement. Any
outcome is reportable and no threshold moves afterwards.

Usage:
    .venv/bin/python analysis/v10_bench_format_paired.py [--n 400] [--seed 0]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lyrebird_pipeline import features, harvest, learn, specbench, syrinx  # noqa: E402

STORE = ROOT / "out/harvest-gan"
INVENTORY = ROOT.parent / "data/learned-inventory.json"
CACHES = [ROOT / "out/audio-cache", ROOT / "out/audio-xc"]
OUT = Path(__file__).resolve().parent / "v10_bench_format_paired.json"

BAND_CAP_HZ = specbench.DEFAULT_BAND_CAP_HZ
#: Pre-registered thresholds, in dB of median paired MCD difference.
POPULATION_MAX = 5.0
REFERENCE_MIN = 10.0


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def score(render: np.ndarray, member, cache_path: Path) -> dict | None:
    """Bench one render against one member's own recording, at the common cap."""
    import soundfile as sf

    file_band = float(sf.info(str(cache_path)).samplerate) / 2.0
    band_hz = min(file_band, BAND_CAP_HZ)
    if file_band < BAND_CAP_HZ:
        return None  # below the cap: a different band, so not comparable
    mono, rate = harvest.decode(cache_path, features.SAMPLE_RATE)
    i0 = max(0, int(member.start * rate))
    i1 = min(mono.size, int((member.start + member.dur) * rate))
    return specbench.bench_pair(mono[i0:i1], render, band_hz=band_hz)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    store = harvest.HarvestStore(STORE)
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    typing = json.loads((store.root / learn.TYPING_NAME).read_text(encoding="utf-8"))
    frame = learn.population_frame(store.syllables)

    cal_path = ROOT / "out/syrinx-calibration.json"
    calibration = (
        syrinx.Calibration.from_dict(json.loads(cal_path.read_text(encoding="utf-8")))
        if cal_path.exists() else None
    )
    log(f"calibration: {'loaded' if calibration else 'analytic fallback'}")

    obs = {(o.species_id, o.recording_id, o.order): o for o in store.syllables}
    members_of: dict[tuple[str, str], list] = {}
    for e in typing.get("entries", []):
        o = obs.get((e["speciesId"], e["recordingId"], int(e["order"])))
        if o is not None:
            members_of.setdefault((e["speciesId"], str(e["typeId"])), []).append(o)

    # types whose members reach both caches
    candidates = []
    for sp in inventory.get("species", []):
        for syl in sp.get("syllables", []):
            if not syl.get("learned"):
                continue
            members = members_of.get((sp["id"], str(syl.get("id", ""))))
            if not members:
                continue
            by_fmt: dict[str, list] = {}
            for o in members:
                p = specbench.resolve_audio(o.recording_id, CACHES)
                if p is not None:
                    by_fmt.setdefault(p.suffix.lstrip(".").lower(), []).append((o, p))
            if "wav" in by_fmt and "mp3" in by_fmt:
                candidates.append((sp, syl, members, by_fmt))
    log(f"types with members in both formats: {len(candidates)}")

    sample = random.Random(args.seed).sample(
        candidates, min(args.n, len(candidates))
    )

    pairs = []
    for i, (sp, syl, members, by_fmt) in enumerate(sample, 1):
        render = syrinx.peak_normalise(
            syrinx.render_syllable(
                syl, sample_rate=features.SAMPLE_RATE, calibration=calibration
            )
        )
        got = {}
        for fmt in ("wav", "mp3"):
            # medoid among this format's members, so each side is that format's most
            # typical rendition of the type rather than an arbitrary one
            cand = by_fmt[fmt]
            member = specbench._medoid_member([o for o, _ in cand])
            if member is None:
                continue
            path = dict((o.recording_id, p) for o, p in cand).get(member.recording_id)
            if path is None:
                continue
            try:
                r = score(render, member, path)
            except Exception as exc:  # noqa: BLE001
                log(f"  skip {sp['id']}/{syl.get('id')} {fmt}: {exc}")
                r = None
            if r is not None:
                got[fmt] = r
        if "wav" in got and "mp3" in got:
            pairs.append({
                "species": sp["id"],
                "typeId": str(syl.get("id", "")),
                "wavMcd": got["wav"]["mcdDb"],
                "mp3Mcd": got["mp3"]["mcdDb"],
                "wavStft": got["wav"]["stftDb"],
                "mp3Stft": got["mp3"]["stftDb"],
                "dMcd": got["mp3"]["mcdDb"] - got["wav"]["mcdDb"],
                "dStft": got["mp3"]["stftDb"] - got["wav"]["stftDb"],
            })
        if i % 25 == 0:
            log(f"  {i}/{len(sample)} types, {len(pairs)} paired")

    if not pairs:
        log("no paired types scored")
        return 1

    from scipy import stats

    d_mcd = np.array([p["dMcd"] for p in pairs])
    d_stft = np.array([p["dStft"] for p in pairs])
    med = float(np.median(d_mcd))
    w = stats.wilcoxon(d_mcd)
    ws = stats.wilcoxon(d_stft)

    if abs(med) < POPULATION_MAX:
        verdict = "population — the arm gap does not survive holding the type fixed"
        clause = 1
    elif med >= REFERENCE_MIN:
        verdict = "the reference recording — the gap survives with the same sign"
        clause = 2
    else:
        verdict = "both contribute; neither pre-registered clause is claimed"
        clause = 3

    result = {
        "bandCapHz": BAND_CAP_HZ,
        "typesBothFormats": len(candidates),
        "sampled": len(sample),
        "paired": len(pairs),
        "seed": args.seed,
        "armGapForComparison": {
            "wavMedianMcd": 71.49, "mp3MedianMcd": 95.23, "gapDb": 23.74,
            "source": "analysis/specbench_capped_n1200.json, unpaired",
        },
        "pairedMcd": {
            "medianDiffDb": round(med, 2),
            "meanDiffDb": round(float(np.mean(d_mcd)), 2),
            "p10": round(float(np.percentile(d_mcd, 10)), 2),
            "p90": round(float(np.percentile(d_mcd, 90)), 2),
            "shareMp3Worse": round(float(np.mean(d_mcd > 0)), 3),
            "wilcoxonP": float(w.pvalue),
            "wavMedian": round(float(np.median([p["wavMcd"] for p in pairs])), 2),
            "mp3Median": round(float(np.median([p["mp3Mcd"] for p in pairs])), 2),
        },
        "pairedStft": {
            "medianDiffDb": round(float(np.median(d_stft)), 2),
            "shareMp3Worse": round(float(np.mean(d_stft > 0)), 3),
            "wilcoxonP": float(ws.pvalue),
        },
        "thresholds": {"populationMax": POPULATION_MAX, "referenceMin": REFERENCE_MIN},
        "clause": clause,
        "verdict": verdict,
        "caveat": "The paired gap holds the type, its fit and its render fixed, so it is "
                  "free of population. It still contains BOTH lossy coding and whatever "
                  "separates an iNat recording from a xeno-canto one; this design does "
                  "not separate those two.",
        "pairs": pairs,
    }

    print("=" * 78)
    print("Same type, same render, two references: is the arm gap format or population?")
    print("=" * 78)
    print(f"  {len(pairs)} types paired of {len(candidates)} available, cap {BAND_CAP_HZ:.0f} Hz")
    print(f"  unpaired arm gap (for comparison)   23.74 dB")
    print()
    m = result["pairedMcd"]
    print(f"  paired MCD   wav median {m['wavMedian']:.2f} dB   "
          f"mp3 median {m['mp3Median']:.2f} dB")
    print(f"               median difference {m['medianDiffDb']:+.2f} dB "
          f"(p10 {m['p10']:+.2f}, p90 {m['p90']:+.2f})")
    print(f"               mp3 worse on {m['shareMp3Worse']:.1%} of types, "
          f"Wilcoxon p {m['wilcoxonP']:.3g}")
    s = result["pairedStft"]
    print(f"  paired STFT  median difference {s['medianDiffDb']:+.2f} dB, "
          f"mp3 worse on {s['shareMp3Worse']:.1%}, p {s['wilcoxonP']:.3g}")
    print()
    print(f"  clause {clause}: {verdict}")
    print(f"  {result['caveat']}")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
