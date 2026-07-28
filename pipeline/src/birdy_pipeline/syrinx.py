"""Mindlin-Laje syrinx model + tracking vocal tract (docs/08-implementation.md 8.1).

Everything in this module is part of the two-sided contract with the browser engine:
the ODE, the integration scheme, the parameter mapping and the filter forms must be
identical on both sides.

The ODE reproduces the reference measurements of contract 8.6 to within 0.1 % on F0
and 2 % on ampPP (`calibrate.check_reference`).

`gamma` is per syllable (8.1, "gamma is per syllable, not a constant"): it is a pure
time-scale, so `f0 = gamma * PHI(alpha, beta)` and `ampPP` does not depend on it. The
calibration table is measured once at `GAMMA_REFERENCE = 24000`; a voice at another
gamma looks up `f0 * GAMMA_REFERENCE / gamma` and the returned beta is correct because
the mapping is dimensionless.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

# --- contract constants (8.1 / 8.4) -----------------------------------------------
# The gamma the calibration table is measured at, and the reference for the lookup
# conversion. Rendering uses `gamma_for_syllable`, not this value.
GAMMA_REFERENCE = 24000.0
OVERSAMPLE = 16  # oversample at GAMMA_REFERENCE; see `oversample_for_gamma`
SAMPLE_RATE = 48000
# gamma rule of 8.1: gamma = clamp(f0_ref / PHI_REFERENCE, GAMMA_MIN, GAMMA_MAX)
PHI_REFERENCE = 0.17061  # PHI(0.1, 1), i.e. f0/gamma at beta = 1
GAMMA_MIN, GAMMA_MAX = 1200.0, 150000.0
F0_REF_FLOOR_HZ = 80.0
GAMMA_DT_TARGET = 0.06  # oversample keeps gamma*dt near this
OVERSAMPLE_MIN, OVERSAMPLE_MAX = 16, 64
SOURCE_GAIN = 0.35
ALPHA_OFFSET = 0.05
ALPHA_SLOPE = 0.40
PS_MIN, PS_MAX = 0.0, 1.4
# beta clamp of the 8.1 mapping table. BETA_MIN is deliberately a module attribute:
# `--beta-min` overrides it for both the calibration sweep and the render clamp, and
# the value used is written into syrinx-calibration.json as `betaClamp` so the browser
# can read it instead of hard-coding it. Contract default = 0.15; below ~0.15 lives the
# only route to sub-1.4 kHz f0 (see README, "The beta clamp and low-pitched species").
BETA_MIN, BETA_MAX = 0.15, 16.0
AMP_PP_FLOOR = 0.05  # never divide the source by ~0
COEFF_UPDATE = 32  # tract coefficients recomputed every N samples
TRACT_HP_HZ = 180.0  # one-pole highpass / DC block
TRACT_LP_HZ = 12000.0  # one-pole lowpass, tracheal roll-off
DETUNE_CENTS = 7.0  # `two: true` second oscillator
DEFAULT_ATTACK = 0.008
RELEASE_S = 0.006
DECAY_TAU_DIVISOR = 2.5
HOLD_FRACTION = 0.75

# timbre -> (pressure gain, tract Q)
TIMBRE: dict[str, tuple[float, float]] = {
    "pure": (1.00, 9.0),
    "reed": (1.25, 5.0),
    "buzz": (1.75, 3.0),
}

try:  # numba arrives with umap-learn; the ODE is ~100x faster with it
    from numba import njit

    _HAVE_NUMBA = True
except ImportError:  # pragma: no cover - fallback only
    _HAVE_NUMBA = False

    def njit(*args: Any, **kwargs: Any):  # type: ignore[misc]
        def wrap(fn):
            return fn

        return wrap(args[0]) if args and callable(args[0]) else wrap


# --- kernels ----------------------------------------------------------------------


@njit(cache=True, fastmath=False)
def _ode_source(
    alpha: np.ndarray,
    beta: np.ndarray,
    gamma: float,
    oversample: int,
    sample_rate: int,
    x0: float,
    y0: float,
) -> np.ndarray:
    """Forward-Euler integrate the flapping oscillator, one output sample per step.

        x' = y
        y' = -a*g^2 - b*g^2*x - g^2*x^3 - g*x^2*y + g^2*x^2 - g*x*y

    `alpha`/`beta` are per-output-sample; the returned array is `y` (labial velocity)
    decimated to `sample_rate`, before the 0.35 source gain.
    """
    n = alpha.shape[0]
    dt = 1.0 / (sample_rate * oversample)
    out = np.zeros(n)
    g = gamma
    g2 = g * g
    x = x0
    y = y0
    for i in range(n):
        a = alpha[i]
        b = beta[i]
        for _ in range(oversample):
            dx = y
            dy = (
                -a * g2
                - b * g2 * x
                - g2 * x * x * x
                - g * x * x * y
                + g2 * x * x
                - g * x * y
            )
            x += dx * dt
            y += dy * dt
        if not (abs(x) < 1.0e6 and abs(y) < 1.0e12):
            # outside every basin of the model: restart from rest rather than
            # poison the buffer with inf/nan.
            x = 1.0e-4
            y = 0.0
        out[i] = y
    return out


@njit(cache=True, fastmath=False)
def _one_pole_hp(x: np.ndarray, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    """y[n] = x[n] - x[n-1] + R*y[n-1], R = exp(-2*pi*fc/sr)."""
    r = math.exp(-2.0 * math.pi * cutoff_hz / sample_rate)
    out = np.zeros(x.shape[0])
    xp = 0.0
    yp = 0.0
    for i in range(x.shape[0]):
        yp = x[i] - xp + r * yp
        xp = x[i]
        out[i] = yp
    return out


@njit(cache=True, fastmath=False)
def _one_pole_lp(x: np.ndarray, cutoff_hz: float, sample_rate: int) -> np.ndarray:
    """y[n] = (1-c)*x[n] + c*y[n-1], c = exp(-2*pi*fc/sr)."""
    c = math.exp(-2.0 * math.pi * cutoff_hz / sample_rate)
    out = np.zeros(x.shape[0])
    yp = 0.0
    for i in range(x.shape[0]):
        yp = (1.0 - c) * x[i] + c * yp
        out[i] = yp
    return out


@njit(cache=True, fastmath=False)
def _tracking_bandpass(
    x: np.ndarray,
    centre_hz: np.ndarray,
    q: float,
    sample_rate: int,
    update: int,
) -> np.ndarray:
    """RBJ bandpass (constant 0 dB peak gain, i.e. Web Audio `bandpass`).

    b0 = A, b1 = 0, b2 = -A, a0 = 1+A, a1 = -2cos(w0), a2 = 1-A, A = sin(w0)/(2Q).
    Coefficients are refreshed every `update` samples from the instantaneous centre.
    """
    n = x.shape[0]
    out = np.zeros(n)
    nyq = 0.45 * sample_rate
    b0 = b1 = b2 = a1 = a2 = 0.0
    x1 = x2 = y1 = y2 = 0.0
    for i in range(n):
        if i % update == 0:
            f = centre_hz[i]
            if f < 20.0:
                f = 20.0
            elif f > nyq:
                f = nyq
            w0 = 2.0 * math.pi * f / sample_rate
            amp = math.sin(w0) / (2.0 * q)
            a0 = 1.0 + amp
            b0 = amp / a0
            b1 = 0.0
            b2 = -amp / a0
            a1 = (-2.0 * math.cos(w0)) / a0
            a2 = (1.0 - amp) / a0
        xi = x[i]
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2 = x1
        x1 = xi
        y2 = y1
        y1 = yi
        out[i] = yi
    return out


# --- calibration table ------------------------------------------------------------


def beta_analytic(
    f0_hz: np.ndarray | float, gamma: float = GAMMA_REFERENCE
) -> np.ndarray:
    """Small-oscillation fallback, `beta = (2*pi*f0/gamma)^2` (8.1).

    Scale-free: passing `f0` with the voice's own gamma gives the same answer as
    passing `f0 * GAMMA_REFERENCE / gamma` with the reference gamma.
    """
    return (2.0 * np.pi * np.asarray(f0_hz, dtype=np.float64) / gamma) ** 2


def amp_pp_analytic(alpha: np.ndarray | float, beta: np.ndarray | float) -> np.ndarray:
    """Fallback peak-to-peak of `y/gamma`: `0.5 + 3.4*alpha + 0.62*beta` (8.1)."""
    return np.maximum(
        0.5
        + 3.4 * np.asarray(alpha, dtype=np.float64)
        + 0.62 * np.asarray(beta, dtype=np.float64),
        AMP_PP_FLOOR,
    )


def _bilinear(
    x_grid: np.ndarray, y_grid: np.ndarray, table: np.ndarray, x: np.ndarray, y: np.ndarray
) -> np.ndarray:
    """table[x_grid, y_grid] sampled at (x, y), clamped at the grid edges."""
    xi = np.clip(np.searchsorted(x_grid, x) - 1, 0, len(x_grid) - 2)
    yi = np.clip(np.searchsorted(y_grid, y) - 1, 0, len(y_grid) - 2)
    tx = np.clip((x - x_grid[xi]) / (x_grid[xi + 1] - x_grid[xi]), 0.0, 1.0)
    ty = np.clip((y - y_grid[yi]) / (y_grid[yi + 1] - y_grid[yi]), 0.0, 1.0)
    top = table[xi, yi] + (table[xi, yi + 1] - table[xi, yi]) * ty
    bot = table[xi + 1, yi] + (table[xi + 1, yi + 1] - table[xi + 1, yi]) * ty
    return top + (bot - top) * tx


@dataclass
class Calibration:
    """`syrinx-calibration.json` (8.4) with the client-side 2D lerps."""

    pressure_grid: np.ndarray
    beta_grid: np.ndarray
    amp_pp: np.ndarray  # [pressure][beta]
    f0_grid: np.ndarray
    beta: np.ndarray  # inverse: [pressure][f0]
    f0_range: tuple[float, float]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Calibration":
        inv = data["inverse"]
        return cls(
            pressure_grid=np.asarray(data["pressureGrid"], dtype=np.float64),
            beta_grid=np.asarray(data["betaGrid"], dtype=np.float64),
            amp_pp=np.asarray(data["ampPP"], dtype=np.float64),
            f0_grid=np.asarray(inv["f0Grid"], dtype=np.float64),
            beta=np.asarray(inv["beta"], dtype=np.float64),
            f0_range=(float(data["f0Range"][0]), float(data["f0Range"][1])),
        )

    def beta_for(
        self, f0_hz: np.ndarray, pressure: np.ndarray, gamma: float = GAMMA_REFERENCE
    ) -> np.ndarray:
        """beta that yields `f0_hz` at `pressure` for a voice running at `gamma`.

        The table is measured at GAMMA_REFERENCE, so the target is first converted to
        the frequency it would have there (8.1); the beta that comes back is correct
        because the mapping is dimensionless. Clamped to [BETA_MIN, BETA_MAX].
        """
        f0_lookup = np.asarray(f0_hz, dtype=np.float64) * (GAMMA_REFERENCE / gamma)
        return np.clip(
            _bilinear(
                self.pressure_grid,
                self.f0_grid,
                self.beta,
                np.asarray(pressure, dtype=np.float64),
                f0_lookup,
            ),
            BETA_MIN,
            BETA_MAX,
        )

    def amp_pp_for(self, beta: np.ndarray, pressure: np.ndarray) -> np.ndarray:
        """Measured peak-to-peak of `y/gamma` at (pressure, beta)."""
        return np.maximum(
            _bilinear(
                self.pressure_grid,
                self.beta_grid,
                self.amp_pp,
                np.asarray(pressure, dtype=np.float64),
                np.asarray(beta, dtype=np.float64),
            ),
            AMP_PP_FLOOR,
        )

    def reachable(
        self, pressure: float, gamma: float = GAMMA_REFERENCE
    ) -> tuple[float, float]:
        """(min, max) f0 in Hz reachable at this pressure, for a voice at `gamma`."""
        row = _bilinear(
            self.pressure_grid,
            self.f0_grid,
            self.beta,
            np.full(self.f0_grid.shape, pressure),
            self.f0_grid,
        )
        inside = np.nonzero((row > BETA_MIN) & (row < BETA_MAX))[0]
        scale = gamma / GAMMA_REFERENCE
        if inside.size == 0:
            return (float(self.f0_grid[0]) * scale, float(self.f0_grid[-1]) * scale)
        return (
            float(self.f0_grid[inside[0]]) * scale,
            float(self.f0_grid[inside[-1]]) * scale,
        )


def beta_for(
    f0_hz: np.ndarray,
    pressure: np.ndarray,
    calibration: Calibration | None,
    gamma: float = GAMMA_REFERENCE,
) -> np.ndarray:
    if calibration is None:
        return np.clip(beta_analytic(f0_hz, gamma), BETA_MIN, BETA_MAX)
    return calibration.beta_for(f0_hz, pressure, gamma)


def amp_pp_for(
    beta: np.ndarray,
    pressure: np.ndarray,
    alpha: np.ndarray,
    calibration: Calibration | None,
) -> np.ndarray:
    if calibration is None:
        return amp_pp_analytic(alpha, beta)
    return calibration.amp_pp_for(beta, pressure)


# --- syllable model ---------------------------------------------------------------


@dataclass
class Syllable:
    """A syllable exactly as it appears in `data/inventory.json`."""

    id: str = ""
    dur: float = 0.1
    level: float = 0.85
    timbre: str = "pure"
    contour: list[list[float]] = field(default_factory=lambda: [[0.0, 3000.0]])
    attack: float = DEFAULT_ATTACK
    hold: bool = False
    harmonic: float = 0.0
    two: bool = False
    am: float = 0.0
    am_depth: float = 0.0
    vib_rate: float = 0.0
    vib_depth: float = 0.0
    label: str = ""
    function: str = ""
    confidence: str = ""
    refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Syllable":
        vib = d.get("vib") or {}
        return cls(
            id=str(d.get("id", "")),
            dur=float(d.get("dur", 0.1)),
            level=float(d.get("level", 0.85)),
            timbre=str(d.get("timbre", "pure")),
            contour=[[float(a), float(b)] for a, b in d.get("contour", [[0.0, 3000.0]])],
            attack=float(d.get("attack", DEFAULT_ATTACK)),
            hold=bool(d.get("hold", False)),
            harmonic=float(d.get("harmonic", 0.0)),
            two=bool(d.get("two", False)),
            am=float(d.get("am", 0.0)),
            am_depth=float(d.get("amDepth", 0.0)),
            vib_rate=float(vib.get("rate", 0.0)),
            vib_depth=float(vib.get("depth", 0.0)),
            label=str(d.get("label", "")),
            function=str(d.get("function", "")),
            confidence=str(d.get("confidence", "")),
            refs=list(d.get("refs", [])),
        )


def f0_reference(contour: Sequence[Sequence[float]]) -> float:
    """Geometric mean of the contour frequencies, each floored at 80 Hz (8.1)."""
    hz = np.maximum(
        np.asarray([p[1] for p in contour], dtype=np.float64), F0_REF_FLOOR_HZ
    )
    return float(np.exp(np.mean(np.log(hz))))


def gamma_for_contour(contour: Sequence[Sequence[float]]) -> float:
    """`gamma = clamp(f0_ref / PHI_REFERENCE, GAMMA_MIN, GAMMA_MAX)` (8.1).

    Picks the time-scale that puts the syllable's median pitch at beta ~ 1.
    """
    return float(
        np.clip(f0_reference(contour) / PHI_REFERENCE, GAMMA_MIN, GAMMA_MAX)
    )


def gamma_for_syllable(syllable: "Syllable | dict[str, Any]") -> float:
    syl = Syllable.from_dict(syllable) if isinstance(syllable, dict) else syllable
    return gamma_for_contour(syl.contour)


def oversample_for_gamma(gamma: float, sample_rate: int = SAMPLE_RATE) -> int:
    """`clamp(ceil(gamma / (0.06*sr)), 16, 64)` - keeps `gamma*dt` near 0.06 (8.1)."""
    need = math.ceil(gamma / (GAMMA_DT_TARGET * sample_rate))
    return int(min(max(need, OVERSAMPLE_MIN), OVERSAMPLE_MAX))


def contour_f0(contour: Sequence[Sequence[float]], t_norm: np.ndarray) -> np.ndarray:
    """Log-interpolate the [timeFraction, Hz] breakpoints (8.1)."""
    pts = np.asarray(contour, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[0] == 0:
        raise ValueError("contour must be a non-empty list of [fraction, hz] pairs")
    if pts.shape[0] == 1:
        return np.full(t_norm.shape, pts[0, 1])
    order = np.argsort(pts[:, 0])
    pts = pts[order]
    return np.exp(np.interp(t_norm, pts[:, 0], np.log(np.maximum(pts[:, 1], 1.0))))


def envelope(n: int, sample_rate: int, attack: float, hold: bool) -> np.ndarray:
    """Linear attack, sustain-or-exponential-decay, 6 ms release (8.1)."""
    if n <= 1:
        return np.zeros(max(n, 0))
    t = np.arange(n, dtype=np.float64) / sample_rate
    dur = n / sample_rate
    atk = float(np.clip(attack, 1.0 / sample_rate, 0.9 * dur))
    tau = dur / DECAY_TAU_DIVISOR

    env = np.ones(n)
    rising = t < atk
    env[rising] = t[rising] / atk
    if hold:
        knee = HOLD_FRACTION * dur
        tail = t > knee
        env[tail] = np.exp(-(t[tail] - knee) / tau)
    else:
        tail = t >= atk
        env[tail] = np.exp(-(t[tail] - atk) / tau)
    env[rising] = t[rising] / atk  # attack always wins over the tail

    rel = int(round(RELEASE_S * sample_rate))
    if 0 < rel < n:
        env[n - rel :] *= np.linspace(1.0, 0.0, rel, endpoint=True)
    return env


@dataclass
class Jitter:
    """Per-variant corpus jitter (corpus.py)."""

    pitch: float = 0.03
    duration: float = 0.08
    level: float = 0.10
    am_rate: float = 0.06
    warp: float = 0.04

    @classmethod
    def none(cls) -> "Jitter":
        return cls(0.0, 0.0, 0.0, 0.0, 0.0)


def jitter_syllable(syl: Syllable, rng: np.random.Generator, j: Jitter) -> Syllable:
    """Return a jittered copy: pitch, duration, level, AM rate, contour warp."""

    def u(amount: float) -> float:
        return 1.0 + amount * rng.uniform(-1.0, 1.0) if amount else 1.0

    pitch = u(j.pitch)
    contour = []
    n = len(syl.contour)
    for i, (frac, hz) in enumerate(syl.contour):
        f = frac
        if j.warp and 0 < i < n - 1:
            f = float(np.clip(frac + j.warp * rng.uniform(-1.0, 1.0), 0.01, 0.99))
        wob = 1.0 + 0.5 * j.pitch * rng.uniform(-1.0, 1.0) if j.pitch else 1.0
        contour.append([f, hz * pitch * wob])
    contour.sort(key=lambda p: p[0])

    return Syllable(
        id=syl.id,
        dur=max(0.01, syl.dur * u(j.duration)),
        level=float(np.clip(syl.level * u(j.level), 0.05, 1.2)),
        timbre=syl.timbre,
        contour=contour,
        attack=syl.attack,
        hold=syl.hold,
        harmonic=syl.harmonic,
        two=syl.two,
        am=max(0.0, syl.am * u(j.am_rate)),
        am_depth=syl.am_depth,
        vib_rate=syl.vib_rate,
        vib_depth=syl.vib_depth,
        label=syl.label,
        function=syl.function,
        confidence=syl.confidence,
        refs=syl.refs,
    )


# --- rendering --------------------------------------------------------------------


@dataclass
class RenderPlan:
    """Everything the parameter mapping of 8.1 produces, before any integration."""

    n: int
    t: np.ndarray
    f0: np.ndarray  # Hz, contour + vibrato
    env: np.ndarray
    ps: np.ndarray  # pressure, clamped to [0, 1.4]
    alpha: np.ndarray
    q: float
    gamma: float
    oversample: int


def render_plan(
    syllable: Syllable | dict[str, Any], sample_rate: int = SAMPLE_RATE
) -> RenderPlan:
    """Apply the 8.1 parameter mapping. Shared by the renderer and the diagnostics."""
    syl = Syllable.from_dict(syllable) if isinstance(syllable, dict) else syllable
    n = max(2, int(round(syl.dur * sample_rate)))
    t = np.arange(n, dtype=np.float64) / sample_rate
    t_norm = t / (n / sample_rate)
    gain, q = TIMBRE.get(syl.timbre, TIMBRE["pure"])

    # f0(t): contour, then vibrato
    f0 = contour_f0(syl.contour, t_norm)
    if syl.vib_rate > 0.0 and syl.vib_depth != 0.0:
        f0 = f0 * (1.0 + syl.vib_depth * np.sin(2.0 * np.pi * syl.vib_rate * t))

    # p_s(t): level * envelope * timbre gain * respiratory AM gate, clamped
    env = envelope(n, sample_rate, syl.attack, syl.hold)
    ps = syl.level * env * gain
    if syl.am > 0.0 and syl.am_depth > 0.0:
        ps = ps * (1.0 - syl.am_depth * (0.5 - 0.5 * np.cos(2.0 * np.pi * syl.am * t)))
    ps = np.clip(ps, PS_MIN, PS_MAX)

    gamma = gamma_for_contour(syl.contour)  # per syllable (8.1)
    return RenderPlan(
        n=n,
        t=t,
        f0=f0,
        env=env,
        ps=ps,
        alpha=ALPHA_OFFSET + ALPHA_SLOPE * ps,
        q=q,
        gamma=gamma,
        oversample=oversample_for_gamma(gamma, sample_rate),
    )


def clamp_incidence(
    syllable: Syllable | dict[str, Any],
    calibration: Calibration,
    sample_rate: int = SAMPLE_RATE,
    audible_env: float = 0.1,
) -> tuple[float, float, float, float]:
    """How often the beta clamp actually bites while the syllable is audible.

    Returns (fraction at the floor, fraction at the ceiling, min raw beta, max raw
    beta). "Raw" = the table lookup before clamping. This is the honest measure: a
    contour excursion only matters where the envelope is actually open.
    """
    plan = render_plan(syllable, sample_rate)
    raw = _bilinear(
        calibration.pressure_grid,
        calibration.f0_grid,
        calibration.beta,
        plan.ps,
        plan.f0 * (GAMMA_REFERENCE / plan.gamma),
    )
    audible = plan.env > audible_env
    if not np.any(audible):
        return 0.0, 0.0, float(raw.min()), float(raw.max())
    seg = raw[audible]
    return (
        float(np.mean(seg <= BETA_MIN)),
        float(np.mean(seg >= BETA_MAX)),
        float(seg.min()),
        float(seg.max()),
    )


def _voice(
    f0: np.ndarray,
    alpha: np.ndarray,
    pressure: np.ndarray,
    q: float,
    harmonic: float,
    gamma: float,
    oversample: int,
    sample_rate: int,
    calibration: Calibration | None,
) -> np.ndarray:
    """One oscillator plus its own tract band(s).

    beta from the table (converted to the table's gamma), integrate, scale by
    `(y/gamma) * 0.35 / ampPP`, DC-block, then bandpass on this oscillator's own
    instantaneous f0 - so a `two: true` syllable gets two tracts, each tracking its
    own voice, which is what keeps the bilateral shimmer.
    """
    beta = beta_for(f0, pressure, calibration, gamma)
    amp = amp_pp_for(beta, pressure, alpha, calibration)
    y = _ode_source(alpha, beta, gamma, oversample, sample_rate, 1.0e-4, 0.0)
    src = _one_pole_hp((y / gamma) * SOURCE_GAIN / amp, TRACT_HP_HZ, sample_rate)

    out = _tracking_bandpass(src, f0, q, sample_rate, COEFF_UPDATE)
    if harmonic > 0.0:
        out = out + harmonic * 0.5 * _tracking_bandpass(
            src, 2.0 * f0, q, sample_rate, COEFF_UPDATE
        )
    return out


def render_syllable(
    syllable: Syllable | dict[str, Any],
    sample_rate: int = SAMPLE_RATE,
    rng: np.random.Generator | None = None,
    jitter: Jitter | None = None,
    calibration: Calibration | None = None,
    envelope_gain: bool = True,
) -> np.ndarray:
    """Render one syllable through the syrinx ODE and the tracking tract.

    `rng` + `jitter` apply the corpus variation of 8.1/corpus.py before rendering.
    gamma and oversample come from the (possibly jittered) contour via the rule in 8.1.
    """
    syl = Syllable.from_dict(syllable) if isinstance(syllable, dict) else syllable
    if jitter is not None:
        syl = jitter_syllable(syl, rng or np.random.default_rng(0), jitter)
    plan = render_plan(syl, sample_rate)

    # one oscillator+tract, or two detuned by +7 cents mixed 0.5/0.5 (bilateral syrinx)
    out = _voice(
        plan.f0, plan.alpha, plan.ps, plan.q, syl.harmonic,
        plan.gamma, plan.oversample, sample_rate, calibration,
    )
    if syl.two:
        f0b = plan.f0 * (2.0 ** (DETUNE_CENTS / 1200.0))
        out = 0.5 * out + 0.5 * _voice(
            f0b, plan.alpha, plan.ps, plan.q, syl.harmonic,
            plan.gamma, plan.oversample, sample_rate, calibration,
        )

    # 180 Hz one-pole highpass and 12 kHz one-pole lowpass on the sum
    out = _one_pole_lp(_one_pole_hp(out, TRACT_HP_HZ, sample_rate), TRACT_LP_HZ, sample_rate)

    if envelope_gain:  # see module docstring
        out = out * plan.env
    return out


def render_song(
    song: dict[str, Any],
    syllables: dict[str, Syllable | dict[str, Any]],
    sample_rate: int = SAMPLE_RATE,
    rng: np.random.Generator | None = None,
    jitter: Jitter | None = None,
    calibration: Calibration | None = None,
    envelope_gain: bool = True,
) -> np.ndarray:
    """Render `sequence` with `gaps` (seconds of silence) between the syllables."""
    seq: list[str] = list(song.get("sequence", []))
    gaps: list[float] = list(song.get("gaps", []))
    parts: list[np.ndarray] = []
    for i, sid in enumerate(seq):
        if sid not in syllables:
            raise KeyError(f"song {song.get('id')!r} references unknown syllable {sid!r}")
        parts.append(
            render_syllable(
                syllables[sid],
                sample_rate=sample_rate,
                rng=rng,
                jitter=jitter,
                calibration=calibration,
                envelope_gain=envelope_gain,
            )
        )
        if i < len(seq) - 1:
            gap = gaps[i] if i < len(gaps) else 0.05
            if jitter is not None and rng is not None and jitter.duration:
                gap *= 1.0 + jitter.duration * rng.uniform(-1.0, 1.0)
            parts.append(np.zeros(max(0, int(round(gap * sample_rate)))))
    return np.concatenate(parts) if parts else np.zeros(0)


# --- measurement helpers (sanity checks, calibration, reports) --------------------


def peak_normalise(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(x))) if x.size else 0.0
    return x * (peak / m) if m > 0.0 else x


def measure_f0_zero_crossings(
    x: np.ndarray, sample_rate: int = SAMPLE_RATE, steady_from: float = 0.4
) -> tuple[float, float]:
    """(f0Hz, interval CV) from upward zero crossings of the steady-state segment.

    Returns (0.0, inf) when the segment is silent or has too few crossings; this is
    the measurement used for the calibration table (8.4).
    """
    if x.size < 16:
        return 0.0, math.inf
    seg = x[int(x.size * steady_from) :]
    seg = seg - seg.mean()
    if float(np.max(np.abs(seg))) < 1.0e-9:
        return 0.0, math.inf
    lo = seg[:-1]
    hi = seg[1:]
    idx = np.nonzero((lo <= 0.0) & (hi > 0.0))[0]
    if idx.size < 4:
        return 0.0, math.inf
    frac = -lo[idx] / (hi[idx] - lo[idx])
    times = (idx + frac) / sample_rate
    d = np.diff(times)
    mean = float(d.mean())
    if mean <= 0.0:
        return 0.0, math.inf
    return 1.0 / mean, float(d.std() / mean)


def spectral_peak_hz(x: np.ndarray, sample_rate: int = SAMPLE_RATE) -> float:
    """Frequency of the largest FFT magnitude (Hann-windowed whole clip)."""
    if x.size < 64:
        return 0.0
    w = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(x.size) / (x.size - 1))
    mag = np.abs(np.fft.rfft(x * w))
    k = int(np.argmax(mag))
    return k * sample_rate / x.size
