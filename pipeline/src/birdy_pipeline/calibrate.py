"""Measure beta <-> f0 for the syrinx model and build `syrinx-calibration.json` (8.4).

The mapping is not analytic, and in this model f0 depends on the air-sac pressure as
well as on beta (pressure moves the fixed point, which shifts the oscillation
frequency), so the table is 2D and the client does a bilinear lookup.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from . import syrinx
from .syrinx import (
    ALPHA_OFFSET,
    ALPHA_SLOPE,
    GAMMA_REFERENCE,
    OVERSAMPLE,
    PS_MAX,
    PS_MIN,
    SAMPLE_RATE,
    _ode_source,
    beta_analytic,
    measure_f0_zero_crossings,
)

# The pressure axis spans the clamp range of p_s; the beta axis spans the clamp range
# of beta (8.1), i.e. 0.15 .. 16, which covers ~1.3 kHz .. ~14.8 kHz.
N_PRESSURE = 29
CV_LIMIT = 0.25  # crossing-interval CV above this = aperiodic -> 0
RUN_SECONDS = 0.25
STEADY_FROM = 0.4  # measure the last 60 %
N_F0_GRID = 192

# Contract 8.6: alpha -> [(beta, f0Hz, ampPP)]. Reproduced by this implementation to
# within 0.1 % on F0 and 2 % on ampPP; `check_reference` is the regression test.
REFERENCE_8_6: dict[float, list[tuple[float, float, float]]] = {
    0.02: [(0.2, 1483, 0.27), (0.5, 2720, 0.41), (1, 3865, 0.67), (2, 5494, 1.30),
           (4, 7823, 2.71), (7, 10382, 4.90), (14, 14684, 10.0)],
    0.10: [(0.2, 1950, 0.81), (0.5, 3039, 0.92), (1, 4095, 1.13), (2, 5623, 1.66),
           (4, 7880, 2.93), (7, 10413, 5.04), (14, 14697, 10.1)],
    0.30: [(0.2, 3015, 1.68), (0.5, 3714, 1.75), (1, 4575, 1.92), (2, 5917, 2.34),
           (4, 8023, 3.43), (7, 10482, 5.38), (14, 14725, 10.3)],
    0.60: [(0.2, 3955, 2.54), (0.5, 4448, 2.60), (1, 5135, 2.73), (2, 6291, 3.09),
           (4, 8227, 4.05), (7, 10586, 5.83), (14, 14765, 10.6)],
}


def pressure_grid(n: int = N_PRESSURE) -> np.ndarray:
    return np.linspace(PS_MIN, PS_MAX, n)


def beta_grid() -> np.ndarray:
    """The clamp range of 8.1, dense at the low end where df0/dbeta is steepest."""
    return np.unique(
        np.concatenate(
            [
                np.arange(syrinx.BETA_MIN, 1.0, 0.01),
                np.arange(1.0, 4.0, 0.05),
                np.arange(4.0, syrinx.BETA_MAX + 1.0e-9, 0.2),
            ]
        )
    )


def measure_alpha_cell(
    alpha: float, beta: float, sample_rate: int = SAMPLE_RATE
) -> tuple[float, float, float]:
    """Steady-state (f0, cv, peak-to-peak of y/gamma) for constant (alpha, beta).

    F0 is measured from upward zero crossings of the last 60 % of a 250 ms run; a cell
    that is silent or has crossing-interval CV > 0.25 reports f0 = 0 (8.4).
    """
    n = int(RUN_SECONDS * sample_rate)
    y = _ode_source(
        np.full(n, alpha), np.full(n, beta), GAMMA_REFERENCE, OVERSAMPLE, sample_rate,
        1.0e-4, 0.0,
    )
    seg = y[int(n * STEADY_FROM) :] / GAMMA_REFERENCE
    amp_pp = float(seg.max() - seg.min()) if seg.size else 0.0
    f0, cv = measure_f0_zero_crossings(y, sample_rate, STEADY_FROM)
    if amp_pp < 1.0e-6 or cv > CV_LIMIT:
        return 0.0, cv, amp_pp
    return f0, cv, amp_pp


def measure_cell(
    pressure: float, beta: float, sample_rate: int = SAMPLE_RATE
) -> tuple[float, float, float]:
    return measure_alpha_cell(ALPHA_OFFSET + ALPHA_SLOPE * pressure, beta, sample_rate)


def f0_landscape(
    pressures: np.ndarray, betas: np.ndarray, verbose: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    """Measured (F0, ampPP) for every (pressure, beta) cell; F0 0 = silent/aperiodic."""
    f0 = np.zeros((len(pressures), len(betas)))
    amp = np.zeros((len(pressures), len(betas)))
    for i, p in enumerate(pressures):
        for j, b in enumerate(betas):
            f0[i, j], _, amp[i, j] = measure_cell(float(p), float(b))
        if verbose:
            live = f0[i][f0[i] > 0]
            print(
                f"  pressure {p:5.3f}: {len(live):3d}/{len(betas)} cells oscillate"
                + (f", f0 {live.min():7.1f}..{live.max():7.1f} Hz" if len(live) else "")
                + f", ampPP {amp[i].min():.2f}..{amp[i].max():.2f}",
                file=sys.stderr,
            )
    return f0, amp


def check_reference(verbose: bool = True) -> tuple[float, float]:
    """Compare this implementation against the 8.6 table; returns worst % errors."""
    worst_f0 = 0.0
    worst_amp = 0.0
    for alpha, rows in REFERENCE_8_6.items():
        for beta, f0_ref, amp_ref in rows:
            f0, _, amp = measure_alpha_cell(alpha, float(beta))
            worst_f0 = max(worst_f0, abs(f0 - f0_ref) / f0_ref * 100.0)
            worst_amp = max(worst_amp, abs(amp - amp_ref) / amp_ref * 100.0)
    if verbose:
        print(
            f"  contract 8.6 regression: worst error {worst_f0:.2f} % on F0, "
            f"{worst_amp:.2f} % on ampPP",
            file=sys.stderr,
        )
    return worst_f0, worst_amp


def _fill_zeros(betas: np.ndarray, row: np.ndarray) -> np.ndarray:
    """Replace 0 cells by interpolation along beta (8.4); clamps at the edges."""
    valid = np.nonzero(row > 0.0)[0]
    if valid.size == 0:
        return row.copy()
    return np.interp(betas, betas[valid], row[valid])


def _fill_and_invert(
    betas: np.ndarray, f0_row: np.ndarray, f0_grid: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Fill zeros along beta, then invert to beta(f0) for one pressure row.

    Returns (filled f0 row, inverse beta row). Outside the oscillating span the
    inverse clamps to the nearest beta that actually produces sound - a request for
    an unreachable f0 comes out at the reachable edge rather than as silence.
    """
    valid = np.nonzero(f0_row > 0.0)[0]
    if valid.size < 2:
        filled = np.zeros_like(f0_row)
        return filled, np.asarray(beta_analytic(f0_grid), dtype=np.float64)

    filled = np.interp(betas, betas[valid], f0_row[valid])
    lo, hi = valid[0], valid[-1]
    seg_b = betas[lo : hi + 1]
    seg_f = np.maximum.accumulate(filled[lo : hi + 1])  # enforce monotone in beta
    # np.interp needs strictly increasing x; nudge duplicate f0 plateaus
    seg_f = seg_f + np.arange(seg_f.size) * 1.0e-6
    inverse = np.interp(f0_grid, seg_f, seg_b)
    return filled, inverse


def build_calibration(
    sample_rate: int = SAMPLE_RATE, verbose: bool = True
) -> dict[str, Any]:
    pressures = pressure_grid()
    betas = beta_grid()
    if verbose:
        print(
            f"calibrating syrinx: {len(pressures)} pressures x {len(betas)} betas "
            f"x {RUN_SECONDS * 1000:.0f} ms",
            file=sys.stderr,
        )
    check_reference(verbose=verbose)
    f0, amp_pp = f0_landscape(pressures, betas, verbose=verbose)

    live = f0[f0 > 0.0]
    if live.size == 0:  # pragma: no cover - would mean the model is dead
        raise RuntimeError("no oscillating cell found; the syrinx model is silent")
    f0_min, f0_max = float(live.min()), float(live.max())
    f0_grid = np.geomspace(f0_min, f0_max, N_F0_GRID)

    filled = np.zeros_like(f0)
    amp_filled = np.zeros_like(amp_pp)
    inverse = np.zeros((len(pressures), len(f0_grid)))
    for i in range(len(pressures)):
        filled[i], inverse[i] = _fill_and_invert(betas, f0[i], f0_grid)
        # ampPP ships filled: the client divides the source by it, so a 0 cell inside
        # the grid would blow up. Cells are only 0 where the oscillator is silent.
        amp_filled[i] = _fill_zeros(betas, np.where(f0[i] > 0.0, amp_pp[i], 0.0))

    if verbose:
        print(
            f"  f0 range {f0_min:.1f}..{f0_max:.1f} Hz; "
            f"inverse table {inverse.shape[0]}x{inverse.shape[1]}",
            file=sys.stderr,
        )

    return {
        "gamma": GAMMA_REFERENCE,
        "// gamma this table was measured at; a voice at another gamma looks up f0 * gamma/gammaVoice": None,
        "oversample": OVERSAMPLE,
        "sampleRate": sample_rate,
        "pressureGrid": [round(float(p), 6) for p in pressures],
        "// p_s values swept (alpha = 0.05 + 0.40*p_s)": None,
        "betaGrid": [round(float(b), 6) for b in betas],
        "// beta values swept, 0.15 .. 16": None,
        "f0Hz": [[round(float(v), 3) for v in row] for row in f0],
        "// [pressure][beta] measured F0, 0 = silent/aperiodic": None,
        "ampPP": [[round(float(v), 6) for v in row] for row in amp_filled],
        "// [pressure][beta] peak-to-peak of y/gamma (zeros filled along beta)": None,
        "inverse": {
            "f0Grid": [round(float(v), 4) for v in f0_grid],
            "beta": [[round(float(v), 8) for v in row] for row in inverse],
        },
        "f0Range": [round(f0_min, 3), round(f0_max, 3)],
        "betaClamp": [syrinx.BETA_MIN, syrinx.BETA_MAX],
        "gammaRule": {
            "f0Ref": "geometric mean of the contour frequencies, each floored at 80 Hz",
            "phiReference": syrinx.PHI_REFERENCE,
            "gammaClamp": [syrinx.GAMMA_MIN, syrinx.GAMMA_MAX],
            "oversample": "clamp(ceil(gamma / (0.06*sampleRate)), 16, 64)",
            "lookup": "f0_lookup = f0_target * gamma_table / gamma_syllable",
        },
        "ampPPFallback": "0.5 + 3.4*alpha + 0.62*beta",
        "alphaFromPressure": {"offset": ALPHA_OFFSET, "slope": ALPHA_SLOPE, "sign": "+1"},
        "measurement": {
            "runSeconds": RUN_SECONDS,
            "steadyStateFrom": STEADY_FROM,
            "cvLimit": CV_LIMIT,
            "f0": "upward zero crossings of the steady-state segment",
            "ampPP": "max(y/gamma) - min(y/gamma) over the same segment",
        },
    }


def write_calibration(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def monotonic_fraction(data: dict[str, Any]) -> float:
    """Fraction of (pressure, beta) steps where measured f0 increases with beta.

    Reported by the CLI as a sanity check on the table.
    """
    f0 = np.asarray(data["f0Hz"], dtype=np.float64)
    steps = 0
    up = 0
    for row in f0:
        live = np.nonzero(row > 0.0)[0]
        for a, b in zip(live[:-1], live[1:]):
            steps += 1
            if row[b] >= row[a] - 1.0:
                up += 1
    return up / steps if steps else 0.0
