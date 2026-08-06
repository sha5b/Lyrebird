"""Two SNR gains are on record for the same band fix. Which statistic, and which meter?

`v10_snr_floor.py` measures the in-band re-segmentation at **+0.77 dB** on 60 recordings.
docs/23 §23.9.1 reports **12.73 -> 15.85 dB, +3.2 dB, 81 % of recordings improving** on 120.
The whitepaper quotes the docs/23 figure at \\S`sec:noisegates`, and the SNR-floor decision
rests on the exchange rate between the two, so one of them has to be retired.

Two explanations are on the table and one run separates them.

**H1, the statistic.** +0.77 is the median over every row pooled; docs/23's "81 % of
recordings improving" is per-recording language, so its median is likely the median of
per-recording medians. Those differ whenever the prolific recordings are the noisy ones: a
recording with 300 weak syllables contributes 300 low rows to a pooled median and one value
to a per-recording one. Prediction if H1 is the whole story: the per-recording statistic
computed here lands near 12.7 -> 15.9 while the pooled one lands near 6.4 -> 7.1.

**H2, the meter.** `extract_syllables` measures SNR *in the band it segments in*
(`learn.py` ~573-587): the in-band arm divides a 400 Hz - 12 kHz segment level by a
400 Hz - 12 kHz noise floor, the full-band arm divides a full-band level by a full-band
floor. Each is a correct ratio inside its own arm, and that is deliberate — the comment
there explains that mixing them is how a 98.7 %-rumble recording reports a healthy SNR. But
it means **every cross-arm SNR comparison published so far, +0.77 and +3.2 alike, is a
comparison between two different meters**, and part of any gain is the band the meter reads
rather than the spans it reads. This is the same trap `specbench`'s `bandHz` guard exists
for. Prediction if H2 carries weight: scoring both arms' spans through one common band
shrinks the gain relative to the as-stored figure.

The common-band arm is the answer to "does the fix choose better spans", which is the
question the exchange rate actually needs. Both arms' spans are scored against one
numerator band and one noise floor, so only span selection can move the number.

Nothing is written to the store. This prices a decision; it does not take it.

**RESULT — H1 carries it, H2 is refuted, and the +0.77 figure is retired.**

```
                        n=60, seed 0            n=120, seed 0        docs/23 (n=120)
as stored, pooled rows  6.36 -> 7.13  (+0.77)   6.45 -> 9.02 (+2.57)
as stored, per rec.     9.52 -> 11.98 (+2.46)   9.65 -> 12.55 (+2.90)  12.73 -> 15.85 (+3.2)
  share improving             0.783                   0.775                 0.81
common band, pooled     2.13 -> 7.09  (+4.96)   2.91 -> 8.95 (+6.04)
common band, per rec.   6.39 -> 11.96 (+5.56)   8.57 -> 12.48 (+3.91)
retention                     0.711                   0.712                 0.775
```

**The +0.77 dB figure is exactly reproduced at n=60 seed 0, and it is a sample artefact of an
unstable statistic.** The same statistic on 120 recordings gives +2.57. The pooled-row median
moves by 1.8 dB between nested samples because one recording with hundreds of near-floor rows
outweighs fifty clean recordings — it is a median over rows, so a prolific noisy recording
votes hundreds of times. Do not quote it.

**docs/23's statistic is the per-recording one, and its gain replicates.** +2.46 at n=60 and
+2.90 at n=120 against its +3.2, with 77.5-78.3 % of recordings improving against its 81 %.
Its absolute pair (12.73 -> 15.85) sits about 3 dB above what this sample gives (9.65 ->
12.55), which is a different draw of 120 from a cache that has grown since — so **quote the
gain and the share, not the absolute pair.**

**The meter is not manufacturing the gain; holding it constant makes the gain larger.** Scored
through one common band, the full-band arm's spans fall to 2.91 dB while the in-band arm's stay
at 8.95. That is the mechanism named in `learn.py`'s comment, measured: full-band spans are
placed on rumble peaks, so in the band that actually describes them they are nearly floor. H2
predicted the gain would shrink. It grew, and the direction is the informative part.

**What this does to the exchange rate in `v10_snr_floor.py`.** The band fix buys about +2.6 dB
per recording at 0.71 retention, against an SNR floor at 6 dB buying +3.3 dB at 0.77 retention.
Comparable, not four to one. And the two gains are not the same kind of number: the floor
selects rows *on the field it then reports*, so its median SNR rises by construction and no
span is improved, while the band fix changes which spans exist and is not selecting on SNR at
all. The floor still keeps 224 more species. The trade is the owner's; it is now much closer
than the four-to-one paragraph implied.

Usage:
    .venv/bin/python analysis/v10_snr_reconcile.py [--n 120] [--seed 0]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

import numpy as np

from lyrebird_pipeline import learn
from lyrebird_pipeline.harvest import decode

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "out/audio-cache"
STORE = ROOT / "out/harvest-gan"
OUT = Path(__file__).resolve().parent / "v10_snr_reconcile.json"

#: `v10_resegment_yield.py`'s value, which is harvest's own.
MAX_SECONDS = 90.0


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def med(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 2) if xs else None


def row_f0(r) -> float | None:
    """A row's pitch, as the median of its stored contour in Hz."""
    hz = [p[1] for p in r.contour if p and p[1]]
    return float(st.median(hz)) if hz else None


def common_band_snr(mono: np.ndarray, rate: int, rows: list) -> list[float]:
    """Score `rows`' spans against one fixed band envelope and one fixed noise floor.

    The reference is the in-band envelope and the in-band segmentation's floor, applied to
    both arms. The formula is `extract_syllables`' own (`learn.py` ~573-587) with the band
    held constant instead of following the arm, so a difference between arms can only come
    from which spans they chose.
    """
    mono = learn.peak_normalise(mono[: int(MAX_SECONDS * rate)])
    env = learn.band_envelope(mono, rate, learn.F0_MIN_HZ, learn.F0_MAX_HZ)
    if not env.size:
        return []
    floor = learn._noise_floor(env, learn._segments(env, rate))
    out = []
    for r in rows:
        s0 = int(r.start * rate)
        s1 = int((r.start + r.dur) * rate)
        frames = env[
            max(0, s0 // learn.ENV_HOP) : max(
                s0 // learn.ENV_HOP + 1, (s1 + learn.ENV_HOP - 1) // learn.ENV_HOP
            )
        ]
        if not frames.size:
            continue
        rms = float(np.sqrt(np.mean(frames * frames)))
        out.append(20.0 * math.log10(max(rms, 1e-9) / max(floor, 1e-9)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    state = json.loads((STORE / "state.json").read_text())
    species_of = {k: v.get("speciesId", "?") for k, v in state["recordings"].items()}

    files = sorted(CACHE.glob("INAT*.wav"))
    sample = random.Random(args.seed).sample(files, min(args.n, len(files)))
    log(f"both segmentations on {len(sample)} recordings, two meters each")

    # pooled rows
    pool: dict[str, list[float]] = {
        "full_stored": [], "band_stored": [], "full_common": [], "band_common": [],
        "full_f0": [], "band_f0": [],
    }
    per_rec = []
    for i, path in enumerate(sample, 1):
        rid = path.stem
        sid = species_of.get(rid, "unlabelled")
        try:
            mono, rate = decode(path)
        except Exception as exc:  # noqa: BLE001
            log(f"  skip {rid}: {exc}")
            continue
        full = learn.extract_syllables(
            mono, rate, sid, rid, max_seconds=MAX_SECONDS, segment_band=None
        )
        band = learn.extract_syllables(mono, rate, sid, rid, max_seconds=MAX_SECONDS)
        if not full or not band:
            log(f"  {rid}: full {len(full)}, band {len(band)} — no pair, recorded as such")

        fs = [r.snr for r in full if r.snr is not None]
        bs = [r.snr for r in band if r.snr is not None]
        fc = common_band_snr(mono, rate, full)
        bc = common_band_snr(mono, rate, band)
        ff = [x for x in (row_f0(r) for r in full) if x]
        bf = [x for x in (row_f0(r) for r in band) if x]

        pool["full_stored"] += fs
        pool["band_stored"] += bs
        pool["full_common"] += fc
        pool["band_common"] += bc
        pool["full_f0"] += ff
        pool["band_f0"] += bf

        per_rec.append({
            "recording": rid,
            "n_full": len(full), "n_band": len(band),
            "full_stored": med(fs), "band_stored": med(bs),
            "full_common": med(fc), "band_common": med(bc),
            "full_f0": med(ff), "band_f0": med(bf),
        })
        if i % 20 == 0:
            log(f"  {i}/{len(sample)} ...")

    def paired(key_f: str, key_b: str) -> dict:
        """Per-recording statistic: median of per-recording medians, plus the share up."""
        pairs = [
            (r[key_f], r[key_b]) for r in per_rec
            if r[key_f] is not None and r[key_b] is not None
        ]
        if not pairs:
            return {"n_recordings": 0}
        f = [p[0] for p in pairs]
        b = [p[1] for p in pairs]
        return {
            "n_recordings": len(pairs),
            "full": round(st.median(f), 2),
            "band": round(st.median(b), 2),
            "gain_db": round(st.median(b) - st.median(f), 2),
            "share_improving": round(sum(1 for x, y in pairs if y > x) / len(pairs), 3),
        }

    def pooled(key_f: str, key_b: str) -> dict:
        f, b = pool[key_f], pool[key_b]
        return {
            "n_rows_full": len(f), "n_rows_band": len(b),
            "full": med(f), "band": med(b),
            "gain_db": round(med(b) - med(f), 2) if f and b else None,
            "retention": round(len(b) / len(f), 3) if f else None,
        }

    result = {
        "recordings": len(per_rec),
        "max_seconds": MAX_SECONDS,
        "seed": args.seed,
        "cache": "out/audio-cache (iNat wav), the cache docs/23 used",
        "snr_as_stored": {
            "note": "each arm's own meter — the band follows the arm, so this is a "
                    "cross-meter comparison and part of any gain is the meter",
            "pooled_rows": pooled("full_stored", "band_stored"),
            "per_recording": paired("full_stored", "band_stored"),
        },
        "snr_common_band": {
            "note": "both arms' spans scored through the in-band envelope and one shared "
                    "noise floor — only span selection can move this",
            "pooled_rows": pooled("full_common", "band_common"),
            "per_recording": paired("full_common", "band_common"),
        },
        "f0_median": {
            "note": "docs/23 also reports f0 2622 -> 3179 Hz; whichever statistic "
                    "reproduces that is the statistic docs/23 used",
            "pooled_rows": pooled("full_f0", "band_f0"),
            "per_recording": paired("full_f0", "band_f0"),
        },
        "on_record": {
            "docs23": {"full": 12.73, "band": 15.85, "gain_db": 3.2,
                       "share_improving": 0.81, "n_recordings": 120,
                       "f0_full": 2622, "f0_band": 3179},
            "v10_snr_floor": {"full": 6.36, "band": 7.13, "gain_db": 0.77,
                              "n_recordings": 60, "statistic": "pooled rows, as stored"},
        },
        "per_recording_rows": per_rec,
    }

    print("=" * 82)
    print("Reconciling the band fix's two SNR gains: which statistic, which meter")
    print("=" * 82)
    print(f"  recordings {len(per_rec)}, max_seconds {MAX_SECONDS}, seed {args.seed}")
    for name in ("snr_as_stored", "snr_common_band", "f0_median"):
        blk = result[name]
        p, q = blk["pooled_rows"], blk["per_recording"]
        print()
        print(f"  {name}")
        print(f"    pooled rows      full {p['full']}  band {p['band']}  "
              f"gain {p['gain_db']}   (rows {p['n_rows_full']} -> {p['n_rows_band']}, "
              f"retention {p['retention']})")
        print(f"    per recording    full {q.get('full')}  band {q.get('band')}  "
              f"gain {q.get('gain_db')}   (share improving {q.get('share_improving')}, "
              f"n {q['n_recordings']})")
    print()
    d = result["on_record"]["docs23"]
    print(f"  on record: docs/23 {d['full']} -> {d['band']} (+{d['gain_db']}), "
          f"{d['share_improving']:.0%} improving, f0 {d['f0_full']} -> {d['f0_band']}")
    print(f"             v10_snr_floor 6.36 -> 7.13 (+0.77), pooled rows, n 60")
    print()
    print("  Read the common-band block as the exchange rate's input: it is the only one")
    print("  of the three where both arms are measured by the same meter.")

    OUT.write_text(json.dumps(result, indent=1))
    print(f"\n  written to {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
