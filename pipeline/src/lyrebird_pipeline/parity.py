"""Python half of the two-sided contract check. See `app/scripts/verify-parity.mjs`.

Reads the worklet's rendering of a set of syllables and renders the same syllables here,
then reports the worst absolute sample difference per case. Run through the Node script,
which produces the input:

    cd app && node scripts/verify-parity.mjs

The two sides run the same arithmetic in the same order, so they are expected to agree to
float32 rounding (~1e-7 on signals that peak near 0.2). A larger difference means §8.1 has
drifted on one side, which is exactly the failure this exists to catch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from .syrinx import Calibration, render_syllable

#: float32 round-trip through the worklet's Float32Array output, with headroom for the
#: `atanh` inversion of the output saturation. Well below anything audible or structural.
TOLERANCE = 5.0e-6


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python -m lyrebird_pipeline.parity <parity-js.json>", file=sys.stderr)
        return 2
    cases = json.loads(Path(argv[1]).read_text(encoding="utf-8"))

    cal_path = Path(__file__).resolve().parents[3] / "app/static/lyrebird/syrinx-calibration.json"
    calibration = Calibration.from_dict(json.loads(cal_path.read_text(encoding="utf-8")))

    print(f"parity against the worklet, tolerance {TOLERANCE:.0e}")
    print(f"{'case':14} {'n':>6} {'peak':>9} {'worst diff':>11} {'tail':>7}  verdict")
    worst_overall = 0.0
    failures = 0
    for name, case in cases.items():
        js = np.asarray(case["samples"], dtype=np.float64)
        py = render_syllable(case["syllable"], calibration=calibration)
        n = min(js.size, py.size)
        if js.size != py.size:
            print(f"{name:14} {js.size:>6} length mismatch: python {py.size}  FAIL")
            failures += 1
            continue
        diff = float(np.max(np.abs(js[:n] - py[:n]))) if n else float("inf")
        peak = float(np.max(np.abs(py[:n]))) if n else 0.0
        # The 20 ms the worklet runs past Python's array is a decay, so nothing out there may
        # rise above the body. See the note in verify-parity.mjs: this is the check that a
        # sample-for-sample comparison structurally cannot make.
        tail = float(case.get("tailPeak", 0.0))
        tail_ratio = tail / peak if peak > 0 else 0.0
        ok = diff <= TOLERANCE and tail_ratio <= 1.0
        worst_overall = max(worst_overall, diff)
        if not ok:
            failures += 1
        verdict = "ok" if ok else ("TAIL" if diff <= TOLERANCE else "DRIFT")
        print(
            f"{name:14} {n:>6} {peak:>9.5f} {diff:>11.2e} {tail_ratio:>6.2f}x  {verdict}"
        )

    print()
    if failures:
        print(f"{failures} case(s) disagree — §8.1 has drifted between the two renderers")
        return 1
    print(f"all {len(cases)} cases agree; worst difference {worst_overall:.2e}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
