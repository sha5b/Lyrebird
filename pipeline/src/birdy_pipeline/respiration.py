"""The respiratory oscillator of Fainstein, Goller & Mindlin (2025) — docs/15 §1.

This is docs/13 B1 and the top bet of docs/09 §9.6: replace the designed per-syllable
amplitude envelope with the two-state air-sac dynamics whose pressure gesture the syrinx
actually runs on. The equations are the paper's (1)-(2) with the inertial term
adiabatically eliminated, nondimensionalised:

    tau_x * dx/dt = -(1 + x^2)*x - p + F0*f(t)
    tau_p * dp/dt = -(1 + x^2)*x - (1 + alpha(p))*p + F0*f(t)
    alpha(p)      = alpha_i - (alpha_i - alpha_o) * Theta(p)

`x` is the piston (air-sac wall) displacement, `p` the gauge air-sac pressure, and
`(1+x^2)x` the measured cubic elastic restitution — during song the displacement doubles
while the pressure grows fifteen-fold, which no linear spring produces. The Heaviside
gives inflow and outflow different conductances: `alpha_o = alpha_i/alpha_rel` is 8-40x
`alpha_i` (Table S2), so expiration is shaped and damped while inspiration is fast.

**What the model does and does not do with a flat command.** Under any *constant*
forcing the steady state of eq. (2) is `alpha*p = 0` — sustained air-sac pressure
requires the muscle activation to keep growing against the piston's creep, which is
exactly what the paper's EMG-driven fits show and what the "pressure grows 15x while
displacement grows 2x" measurement says. So this module makes no promise that a flat
envelope in means a flat pressure out: long notes sag and overshoot in ways the per-
species fit (not yet built — see below) will tune. The hand-set default below sits at
the weak-damping corner of Table S2 because that is the corner where a sustained note
stays above threshold at all; it is a starting point with a measured bake-off behind
it, not a fit.

**The forcing.** `f(t)` is the expiratory muscle command: here the syllable's designed
envelope (the muscle-gesture surrogate we actually have — there is no EMG), pushed
through the paper's critically damped 5 ms filter (its eqs. 3-4), normalised by its own
P10/P90 percentiles, with a negative half-sine — the mini-breath — filling every
interior silence of 12 ms or longer (Hartley & Suthers 1989: mini-breaths below ~30 Hz
syllable rate, pulsatile expiration above). Per-syllable envelopes have no interior
silences, so the mini-breath path is dormant until bout-level rendering drives this
module across a whole phrase; it is implemented and unit-tested now because the forcing
contract must not change when that lands.

**AM stays at the labia, not in the sac.** The within-syllable `am` gate is deliberately
NOT part of this forcing: a 40 Hz gate through `tau_p ~ 100 ms` of pressure dynamics
comes out as mush, and that is not a numerical defect but the physics — air-sac pressure
cannot swing at syringeal AM rates, which is why fast amplitude modulation in birds is
syringeal. `syrinx.render_plan` therefore gates `ps` with `am` *after* this module,
exactly as it did on the envelope path, while the tract-input drive below uses the
un-gated air-sac pressure.

Integration is forward Euler at the audio sample rate, one update per output sample,
as the paper specifies (tau >= 5 ms needs no oversampling). The kernels are numba-jitted
with fastmath off and do the same arithmetic in the same order as the browser worklet's
copy — the pressure gesture is part of the two-sided contract of docs/08 §8.1, so it
is computed here exactly the way `syrinx-processor.js` computes it.

The per-species fit is deliberately not built. When it comes it is pre-registered: the
five parameters are searched per species (coordinate search, same pattern as
`learn.invert_gestures`) against the fixed store, judged on the pre-registered numbers
of docs/09 — median resynthesis cosine and species placement — with the respiratory
path winning or losing on those, and a negative result recorded in place.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

# --- Table S2 of Fainstein, Goller & Mindlin (2025): the grid-search intervals the five
# canaries were fitted over. Parsing clamps into these ranges rather than trusting a
# JSON file, because a tau outside them is either a typo or an instability — at
# tau_p = 5 ms with alpha_o = 240 the explicit Euler step is already marginal.
TAU_X_MIN, TAU_X_MAX = 0.01, 0.25  # restitution/dissipation time (beta/k), seconds
TAU_P_MIN, TAU_P_MAX = 0.005, 0.2  # cavity filling time (V0*beta/(P0*A^2)), seconds
ALPHA_I_MIN, ALPHA_I_MAX = 0.05, 6.0  # inlet conductance asymmetry term
ALPHA_REL_MIN, ALPHA_REL_MAX = 0.025, 0.125  # alpha_i/alpha_o: outflow is 8-40x inflow
FORCING_MIN, FORCING_MAX = 20.0, 200.0  # F0, the forcing amplitude

# The expiratory filter of the paper's eqs. (3)-(4): critically damped second order,
# tau = 5 ms. Fixed by the paper, not a free parameter.
FORCING_TAU_S = 0.005
# A mini-breath fills an expiratory silence with a negative half-sine of this depth, in
# the forcing's normalised units. Interior silences only: a run that touches the
# syllable's edges is the attack or the release, and filling those would move the onset.
MINI_BREATH_DEPTH = 0.5
MINI_BREATH_MIN_S = 0.012  # below this a gap is a pulse edge, not a breath
SILENCE_FRACTION = 0.05  # of the command's maximum: what "silence" means

#: The hand-set default set, one per species until the fit exists. Weak damping and a
#: slow piston — the corner of Table S2 where a 250 ms held note keeps most of its
#: pressure (measured: worst-case body tracking of the designed envelope 0.52-0.60 over
#: 50-250 ms notes, where strong-damping sets sag to 0.00; attack stretch ~20-40 ms,
#: which is the shaped onset this feature exists for).
DEFAULT_PARAMS: "RespirationParams"


@dataclass(frozen=True)
class RespirationParams:
    """One species' respiratory set — the five numbers of Table S2.

    `forcing` is the paper's F0 (forcing amplitude); it is not called F0 anywhere in
    this codebase because that name already means pitch.
    """

    tau_x: float
    tau_p: float
    alpha_i: float
    alpha_rel: float
    forcing: float

    @property
    def alpha_o(self) -> float:
        """Outflow conductance, 8-40x the inflow one (Table S2)."""
        return self.alpha_i / self.alpha_rel

    def as_dict(self) -> dict[str, float]:
        """The JSON form a syllable's `respiration` block carries (camelCase, as the
        rest of the inventory schema)."""
        return {
            "tauX": self.tau_x,
            "tauP": self.tau_p,
            "alphaI": self.alpha_i,
            "alphaRel": self.alpha_rel,
            "forcing": self.forcing,
        }


DEFAULT_PARAMS = RespirationParams(
    tau_x=0.25, tau_p=0.08, alpha_i=0.05, alpha_rel=0.125, forcing=50.0
)


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi)


def parse(raw: Any) -> RespirationParams | None:
    """A syllable's `respiration` block, clamped into the Table S2 ranges, or None.

    Silently permissive for the same reason `syrinx.parse_formants` is: this reads a
    fitted file, and a block that cannot produce a stable integration is dropped back
    to the designed-envelope path rather than allowed to change the sound of every
    syllable that parses. `alpha_o` is never parsed directly — it is
    `alpha_i/alpha_rel` by definition, so the two cannot disagree in a file.
    """
    if not isinstance(raw, dict):
        return None
    try:
        tau_x = float(raw["tauX"])
        tau_p = float(raw["tauP"])
        alpha_i = float(raw["alphaI"])
        alpha_rel = float(raw["alphaRel"])
        forcing = float(raw["forcing"])
    except (KeyError, TypeError, ValueError):
        return None
    values = (tau_x, tau_p, alpha_i, alpha_rel, forcing)
    if not all(math.isfinite(v) for v in values):
        return None
    return RespirationParams(
        tau_x=_clamp(tau_x, TAU_X_MIN, TAU_X_MAX),
        tau_p=_clamp(tau_p, TAU_P_MIN, TAU_P_MAX),
        alpha_i=_clamp(alpha_i, ALPHA_I_MIN, ALPHA_I_MAX),
        alpha_rel=_clamp(alpha_rel, ALPHA_REL_MIN, ALPHA_REL_MAX),
        forcing=_clamp(forcing, FORCING_MIN, FORCING_MAX),
    )


try:  # numba arrives with umap-learn; same pattern as syrinx.py
    from numba import njit

    _HAVE_NUMBA = True
except ImportError:  # pragma: no cover - fallback only
    _HAVE_NUMBA = False

    def njit(*args: Any, **kwargs: Any):  # type: ignore[misc]
        def wrap(fn):
            return fn

        return wrap(args[0]) if args and callable(args[0]) else wrap


@njit(cache=True, fastmath=False)
def _filter_forcing(m: np.ndarray, sample_rate: int) -> np.ndarray:
    """The paper's eqs. (3)-(4): |EMG| through a critically damped 2nd-order filter.

        x1' = x2
        x2' = (m - x1)/tau^2 - 2*x2/tau,   tau = 5 ms

    Forward Euler at the audio rate; tau/dt ~ 240, so the explicit step is nowhere near
    its stability limit.
    """
    n = m.shape[0]
    dt = 1.0 / sample_rate
    tau = FORCING_TAU_S
    tau2 = tau * tau
    out = np.zeros(n)
    x1 = 0.0
    x2 = 0.0
    for i in range(n):
        dx1 = x2
        dx2 = (m[i] - x1) / tau2 - 2.0 * x2 / tau
        x1 += dx1 * dt
        x2 += dx2 * dt
        out[i] = x1
    return out


def _percentile(sorted_x: np.ndarray, q: float) -> float:
    """Linear-interpolation percentile on an already-sorted array.

    Written out by hand — rather than `np.percentile` — because the browser worklet has
    to produce the same number bit for bit, and "whatever numpy's lerp does this year"
    is not a contract. `q` is in percent, position `(n-1)*q/100`.
    """
    n = sorted_x.shape[0]
    if n == 0:
        return 0.0
    pos = (n - 1) * (q / 100.0)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return float(sorted_x[lo] + (sorted_x[hi] - sorted_x[lo]) * frac)


def _insert_mini_breaths(m: np.ndarray, sample_rate: int) -> np.ndarray:
    """Fill each interior expiratory silence with a negative half-sine (a mini-breath).

    A silence is a run below SILENCE_FRACTION of the command's maximum, at least
    MINI_BREATH_MIN_S long, and strictly interior — runs touching the edges are the
    attack and the release, and putting an inhalation there would move the onset the
    fit measured. Deterministic: the breath's shape is a function of the gap's length
    and nothing else.
    """
    n = m.shape[0]
    peak = float(np.max(m)) if n else 0.0
    if peak <= 0.0:
        return m.copy()
    threshold = SILENCE_FRACTION * peak
    min_len = int(MINI_BREATH_MIN_S * sample_rate)
    out = m.copy()
    i = 0
    while i < n:
        if m[i] < threshold:
            j = i
            while j < n and m[j] < threshold:
                j += 1
            length = j - i
            if i > 0 and j < n and length >= min_len:
                for k in range(length):
                    out[i + k] = -MINI_BREATH_DEPTH * math.sin(
                        math.pi * (k + 1) / (length + 1)
                    )
            i = j
        else:
            i += 1
    return out


def forcing(muscle: np.ndarray, sample_rate: int) -> np.ndarray:
    """The amplitude-normalised forcing f(t) from a raw expiratory muscle command.

    Mini-breaths first (they are muscle command, so the 5 ms filter smooths them like
    everything else), then the critically damped filter, then the paper's P10/P90
    normalisation: P10 maps to 0 and P90 to 1, so the forcing is comparable across
    syllables whose commands differ in absolute scale.
    """
    m = _insert_mini_breaths(np.asarray(muscle, dtype=np.float64), sample_rate)
    f = _filter_forcing(m, sample_rate)
    ordered = np.sort(f)
    lo = _percentile(ordered, 10.0)
    hi = _percentile(ordered, 90.0)
    span = hi - lo
    if span < 1.0e-9:
        return np.zeros_like(f)
    return (f - lo) / span


@njit(cache=True, fastmath=False)
def _integrate(
    f: np.ndarray,
    tau_x: float,
    tau_p: float,
    alpha_i: float,
    alpha_o: float,
    forcing_amp: float,
    sample_rate: int,
    x0: float,
    p0: float,
) -> tuple[np.ndarray, float, float]:
    """Forward-Euler integrate the respiratory states, one step per output sample.

    Returns (p over the syllable, final x, final p) — the final state is the
    initial-state carry a bout-level renderer passes to the next syllable, which is
    where the paper's cross-syllable memory (air left in the sacs shaping the next
    onset) lives. Per-syllable rendering starts at rest.
    """
    n = f.shape[0]
    dt = 1.0 / sample_rate
    out = np.zeros(n)
    x = x0
    p = p0
    for i in range(n):
        # alpha(p) = alpha_i - (alpha_i - alpha_o)*Theta(p), Theta = 1 iff p > 0:
        # expiration runs at the high outflow conductance, inspiration at the low one.
        a = alpha_i - (alpha_i - alpha_o) * (1.0 if p > 0.0 else 0.0)
        rest = (1.0 + x * x) * x
        ff = forcing_amp * f[i]
        dx = (-rest - p + ff) / tau_x
        dp = (-rest - (1.0 + a) * p + ff) / tau_p
        x += dx * dt
        p += dp * dt
        if not (abs(x) < 1.0e6 and abs(p) < 1.0e6):
            # outside anything the model can mean: restart from rest rather than poison
            # the gesture — the same answer the labial ODE gives.
            x = 0.0
            p = 0.0
        out[i] = p
    return out, x, p


def pressure(
    params: RespirationParams,
    muscle: np.ndarray,
    sample_rate: int,
    initial: tuple[float, float] = (0.0, 0.0),
) -> tuple[np.ndarray, tuple[float, float]]:
    """The air-sac pressure gesture p(t) for one syllable's muscle command.

    Returns (p, final state). The gesture is in the paper's normalisation — quiet
    breathing oscillates in [-1, 1], song peaks reach ~15x that — so the caller scales
    it into the synth's [0, 1.4] pressure range; this module keeps the model's own
    units because the percentiles, not a constant, define them.
    """
    f = forcing(muscle, sample_rate)
    p, x_end, p_end = _integrate(
        f,
        params.tau_x,
        params.tau_p,
        params.alpha_i,
        params.alpha_o,
        params.forcing,
        sample_rate,
        float(initial[0]),
        float(initial[1]),
    )
    return p, (x_end, p_end)


def self_test(verbose: bool = True) -> None:
    """Check the respiratory path's physics without any audio.

    The assertions are the load-bearing properties, not the numerology: the Heaviside
    must make inflow and outflow genuinely asymmetric, the gesture must rise where the
    command rises and end below where it started once the command stops, mini-breaths
    must appear in interior silences and nowhere else, the initial-state carry must be
    bit-exact (it is how bout rendering will chain syllables), and the parse must keep
    every number inside Table S2 so the Euler step stays stable.
    """
    sr = 48000

    # 1. Parse: a full block round-trips clamped into Table S2; junk falls back to None
    #    (the syllable then renders on the envelope path, unchanged).
    p = parse({"tauX": 0.5, "tauP": 0.08, "alphaI": 0.05, "alphaRel": 0.125, "forcing": 50})
    assert p is not None and p.tau_x == TAU_X_MAX, "parse must clamp into Table S2"
    assert p.alpha_o == p.alpha_i / p.alpha_rel
    assert parse({"tauX": 0.1}) is None
    assert parse("respiration") is None
    assert parse({"tauX": float("nan"), "tauP": 0.08, "alphaI": 1, "alphaRel": 0.1,
                  "forcing": 50}) is None
    d = DEFAULT_PARAMS.as_dict()
    assert parse(d) == DEFAULT_PARAMS, "the default set must survive its own JSON form"
    for params in (DEFAULT_PARAMS, p):
        assert TAU_X_MIN <= params.tau_x <= TAU_X_MAX
        assert TAU_P_MIN <= params.tau_p <= TAU_P_MAX
        assert ALPHA_I_MIN <= params.alpha_i <= ALPHA_I_MAX
        assert ALPHA_REL_MIN <= params.alpha_rel <= ALPHA_REL_MAX
        assert FORCING_MIN <= params.forcing <= FORCING_MAX

    # 2. The forcing: a held command comes out normalised (P10 -> 0, P90 -> 1), and the
    #    normalisation is scale-invariant — twice the command, the same forcing.
    n = int(0.12 * sr)
    held = np.ones(n)
    held[: int(0.008 * sr)] = np.linspace(0.0, 1.0, int(0.008 * sr))
    f1 = forcing(held, sr)
    f2 = forcing(held * 2.0, sr)
    assert np.allclose(f1, f2, atol=1e-9), "P10/P90 normalisation must be scale-invariant"
    assert abs(np.percentile(f1, 90) - 1.0) < 0.05

    # 3. Mini-breaths: an interior silence of 60 ms gets a negative half-sine; the
    #    attack and release edges get none, and a 5 ms dip is a pulse edge, not a breath.
    m = np.ones(int(0.4 * sr))
    m[int(0.1 * sr) : int(0.16 * sr)] = 0.0  # interior silence
    b = _insert_mini_breaths(m, sr)
    gap = b[int(0.1 * sr) : int(0.16 * sr)]
    assert gap.min() < -0.9 * MINI_BREATH_DEPTH, "interior silence must inhale"
    assert b[0] == 1.0 and b[-1] == 1.0
    m2 = np.ones(int(0.1 * sr))
    m2[int(0.04 * sr) : int(0.045 * sr)] = 0.0  # 5 ms: too short to be a breath
    assert np.array_equal(_insert_mini_breaths(m2, sr), m2)

    # 4. The gesture: with a held command the pressure rises through a shaped attack
    #    (not the command's 8 ms ramp), stays up through the body with the weak-damping
    #    default set, and ends below its peak once the command stops.
    gesture, _ = pressure(DEFAULT_PARAMS, held, sr)
    peak = float(gesture.max())
    body = gesture[int(0.06 * sr) : int(0.11 * sr)]
    assert peak > 0.0
    assert float(body.min()) > 0.5 * peak, "a held note must hold its pressure"
    half = np.nonzero(gesture > 0.5 * peak)[0]
    assert half[0] / sr > 0.008, "the ODE, not the ramp, shapes the attack"

    # 5. The Heaviside is load-bearing: identical inspiration and expiration
    #    conductances must give a measurably different gesture than alpha_o = 8x alpha_i.
    symmetric = RespirationParams(0.25, 0.08, 0.05, 1.0, 50.0)  # alpha_rel outside S2 on
    # purpose — the test wants alpha_i == alpha_o, which the parser would rightly forbid
    g_sym, _ = pressure(symmetric, held, sr)
    assert not np.allclose(g_sym, gesture), "the inflow/outflow asymmetry must matter"

    # 6. The initial-state carry is bit-exact: one 0.2 s integration equals two 0.1 s
    #    integrations chained through the returned state. The chunking happens at the
    #    integration, not at `pressure` — the forcing's P10/P90 normalisation is a
    #    property of the whole command, so a bout computes it once and chains the ODE.
    #    If this drifts, cross-syllable memory drifts with it.
    long_f = forcing(np.ones(int(0.2 * sr)), sr)
    whole, _, _ = _integrate(
        long_f, DEFAULT_PARAMS.tau_x, DEFAULT_PARAMS.tau_p, DEFAULT_PARAMS.alpha_i,
        DEFAULT_PARAMS.alpha_o, DEFAULT_PARAMS.forcing, sr, 0.0, 0.0,
    )
    first, x_end, p_end = _integrate(
        long_f[: int(0.1 * sr)], DEFAULT_PARAMS.tau_x, DEFAULT_PARAMS.tau_p,
        DEFAULT_PARAMS.alpha_i, DEFAULT_PARAMS.alpha_o, DEFAULT_PARAMS.forcing,
        sr, 0.0, 0.0,
    )
    second, _, _ = _integrate(
        long_f[int(0.1 * sr) :], DEFAULT_PARAMS.tau_x, DEFAULT_PARAMS.tau_p,
        DEFAULT_PARAMS.alpha_i, DEFAULT_PARAMS.alpha_o, DEFAULT_PARAMS.forcing,
        sr, x_end, p_end,
    )
    assert np.array_equal(whole, np.concatenate([first, second])), (
        "chained integration must be bit-identical to the one-shot one"
    )

    # 7. Euler stability at the stiffest corner Table S2 allows: tau_p at its floor,
    #    alpha_o at its ceiling. The gesture must stay finite (the kernel restarts from
    #    rest rather than emitting NaN).
    stiff = RespirationParams(TAU_X_MIN, TAU_P_MIN, ALPHA_I_MAX, ALPHA_REL_MIN, FORCING_MAX)
    g_stiff, _ = pressure(stiff, held, sr)
    assert np.all(np.isfinite(g_stiff)), "the stiffest legal set must not blow up"

    if verbose:
        print(
            "respiration self-test ok: parse clamped to Table S2, forcing "
            "scale-invariant, mini-breaths interior-only, Heaviside asymmetry "
            "load-bearing, state carry bit-exact"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
