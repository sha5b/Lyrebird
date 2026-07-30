"""The two-voice coupling of Laje & Mindlin (2005) — docs/15 §5, docs/13 B2.

An oscine syrinx is two independent sound sources — one in each bronchus — sitting
under one shared trachea. The `two: true` of contract 8.1 has always gestured at that,
but it is one gesture stream feeding two oscillators 7 cents apart: no independent
contours, and crucially no *coupling* — the two sides cannot hear each other. Laje &
Mindlin (PRE 72:036218, eqs. 62-67) write down the mechanism by which they do: each
source injects into the shared tracheal pressure `pi(t)`, and that pressure acts back
on both sources through their interlabial pressure `(ps - pi)`:

    pgj = ps + (Dj*yj - Aj)*(ps - pi)
    pi  = sum_j [alpha_j*(xj - tau_j*yj) + beta_j*yj] - gamma_refl * pi(t - T),  T = 2L/c

In the low-frequency inertive limit (crossover ~55 kHz, far above anything here) each
source's injection is `beta_j * y_j` with `beta_j ∝ sqrt(ps)` — velocity times root
pressure, the same result that put `sqrt(ps)` at the tract input on the respiration
path. And in the weak-coupling limit the paper verifies directly (Table I: beta = 1.5e3
against 1/tau = 1e4) the implicit acceleration terms drop out, which is what keeps the
integration here plain explicit Euler — no solve, no iteration, and therefore parity-
testable against the browser worklet sample by sample.

**How the paper's form lands in Birdy's nondimensionalised model.** The labial
restitution constant IS the air-sac pressure (docs/15 §1's lineage: `alpha = 0.05 +
0.40*ps`), so a tracheal back-pressure moves each source's alpha, not its output gain:

    pi[i]      = betaInj * (sqrt(ps_a)*y_a/gamma_a + sqrt(ps_b)*y_b/gamma_b)
                 - refl * pi(i - T)
    alpha_j(i) = alpha_j[i] - 0.40 * pi[i]

with `T = 2L/c` the tracheal round trip (L the one-way syrinx-to-beak length, Table I's
2 cm the default), `refl = 0.9` Table I's reflection coefficient, and `y/gamma` the
velocity in the model's own normalisation (the same one `ampPP` divides by). There is
no direct spring between the sources — the shared pressure field is the whole coupling,
which is what makes "one side active" a well-defined case: a closed bronchus
(`level: 0`) injects nothing (`sqrt(0) * y = 0`) while the active side still gets its
own pressure fed back through the trachea — the configuration the paper shows
period-doubling in with feedback alone.

**Update discipline.** pi is refreshed once per output sample from the oscillator
states at the top of the sample, exactly the way alpha and beta are per-output-sample
in `_ode_source`: the coupling constants are held across the sample's oversampled
Euler substeps. The delay line is fractional (linear interpolation, the `_tube_comb`
discipline — at 48 kHz a 2 cm round trip is 5.6 samples, and rounding that to an
integer would move the tracheal resonances by hundreds of Hz). Weak but consequential
is the paper's own verdict and Fletcher 1988's: with both sources active, sums and
differences of the two fundamentals appear (every spectral line a multiple of the
frequency difference, their Fig. 6); with one, the feedback alone period-doubles.

The per-species fit is deliberately not built — the contours of the second voice are
hand-set (`learn --two-voice` attaches the default: the type's own contour shifted by
DEFAULT_RATIO, Table I's trachea and reflection, and a measured injection strength),
and the fit is pre-registered separately, judged on docs/09's numbers against the
single-voice baseline of the same run, with a negative result recorded in place.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# --- Table I of Laje & Mindlin 2005, translated to Birdy's units --------------------
# L = 2.0 cm one-way (the paper's trachea length) and gamma_refl = 0.9 are the paper's
# own numbers. The 0.8 cm floor keeps the round trip above two samples at 48 kHz, so
# the fractional delay line never reads a slot that has not been written; 20 cm is the
# tube bound of syrinx.py's waveguide (an 8x longer trachea than any bird here).
TRACHEA_CM_MIN, TRACHEA_CM_MAX = 0.8, 20.0
REFL_MIN, REFL_MAX = 0.0, 0.95
# betaInj is Birdy's nondimensional injection strength, not the paper's dimensional
# beta (1.5e3 s^-1): the small-coupling condition beta << 1/tau is about the *ratio*,
# and the measured strength that puts the coupling in the paper's regime is what
# DEFAULT_BETA_INJ records below. The ceiling is a stability guard, not a fit bound.
BETA_INJ_MIN, BETA_INJ_MAX = 0.0, 0.5
LEVEL_MIN, LEVEL_MAX = 0.0, 1.0
# The gamma clamp of syrinx.py, repeated because syrinx imports this module and an
# import back would be circular. Keep the numbers identical.
GAMMA_MIN, GAMMA_MAX = 1200.0, 150000.0

#: The hand-set default pitch relation between the voices: sqrt(eps_l/eps_r) of the
#: paper's Fig. 6 (eps_l = 2.4e8, eps_r = 1.4e8 — the figure that shows sums and
#: differences of the two fundamentals), i.e. the second voice sits a just-noticeably-
#: inharmonic fourth above where the syllable's own contour puts the first. Hand-set,
#: not fitted; the per-species fit is what replaces it.
DEFAULT_RATIO = math.sqrt(2.4 / 1.4)  # ≈ 1.309
DEFAULT_LEVEL = 0.7  # the second bronchus breathes the same sacs, a little weaker
DEFAULT_TRACHEA_CM = 2.0  # Table I's L
DEFAULT_REFL = 0.9  # Table I's gamma_refl
#: Measured, not guessed — see the module note in `syrinx._voice_pair`. At this
#: strength a two-voice syllable at ps ~ 1 carries pi at a few percent of ps: below
#: the threshold where the sources quench each other outright, inside the regime
#: where sum/difference lines and single-source period-doubling are measurable.
DEFAULT_BETA_INJ = 0.05


@dataclass(frozen=True)
class TwoVoiceParams:
    """A syllable's `voices` block — the second syringeal source and the coupling.

    `contour`/`gamma` are the second voice's own pitch gesture (independent of the
    syllable's contour, which drives the first voice); `level` is the share of the
    shared air-sac pressure the second bronchus gets (`ps_b = level * ps`), so 0 is a
    closed right side. `trachea_cm`, `refl` and `beta_inj` are the coupling: one-way
    tube length, round-trip reflection, injection strength.
    """

    contour: tuple[tuple[float, float], ...]
    gamma: float
    level: float
    trachea_cm: float
    refl: float
    beta_inj: float

    def as_dict(self) -> dict[str, Any]:
        """The JSON form a syllable's `voices` block carries (camelCase, as the rest
        of the inventory schema)."""
        return {
            "contour": [[f, hz] for f, hz in self.contour],
            "gamma": self.gamma,
            "level": self.level,
            "tracheaCm": self.trachea_cm,
            "refl": self.refl,
            "betaInj": self.beta_inj,
        }


def default_block(contour_b: Any, gamma_b: float) -> dict[str, Any]:
    """The hand-set default `voices` block around a given second-voice contour.

    `learn --two-voice` derives `contour_b` from the fitted type's own contour
    (shifted by DEFAULT_RATIO) and `gamma_b` from the contour rule of 8.1; the
    coupling numbers are Table I's plus the measured injection strength.
    """
    return TwoVoiceParams(
        contour=tuple((float(f), float(hz)) for f, hz in contour_b),
        gamma=float(gamma_b),
        level=DEFAULT_LEVEL,
        trachea_cm=DEFAULT_TRACHEA_CM,
        refl=DEFAULT_REFL,
        beta_inj=DEFAULT_BETA_INJ,
    ).as_dict()


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi)


def parse(raw: Any) -> TwoVoiceParams | None:
    """A syllable's `voices` block, clamped into the ranges above, or None.

    Silently permissive for the same reason `respiration.parse` is: this reads a
    fitted file, and a block that cannot produce a stable integration is dropped back
    to the single-voice path rather than allowed to change the sound of every syllable
    that parses. Contour points are sorted by time fraction and floored at 1 Hz, so
    the log-interpolation both renderers do cannot disagree about a degenerate point.
    """
    if not isinstance(raw, dict):
        return None
    try:
        contour_raw = raw["contour"]
        gamma = float(raw["gamma"])
        level = float(raw["level"])
        trachea_cm = float(raw["tracheaCm"])
        refl = float(raw["refl"])
        beta_inj = float(raw["betaInj"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (gamma, level, trachea_cm, refl, beta_inj)):
        return None
    if not isinstance(contour_raw, (list, tuple)) or not contour_raw:
        return None
    points: list[tuple[float, float]] = []
    for p in contour_raw:
        try:
            f, hz = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            return None
        if not (math.isfinite(f) and math.isfinite(hz)):
            return None
        points.append((f, max(hz, 1.0)))
    points.sort(key=lambda p: p[0])
    return TwoVoiceParams(
        contour=tuple(points),
        gamma=_clamp(gamma, GAMMA_MIN, GAMMA_MAX),
        level=_clamp(level, LEVEL_MIN, LEVEL_MAX),
        trachea_cm=_clamp(trachea_cm, TRACHEA_CM_MIN, TRACHEA_CM_MAX),
        refl=_clamp(refl, REFL_MIN, REFL_MAX),
        beta_inj=_clamp(beta_inj, BETA_INJ_MIN, BETA_INJ_MAX),
    )


def self_test(verbose: bool = True) -> None:
    """Check the schema half of the two-voice contract without any audio.

    The render-level properties — that zero coupling is the single voice bit for bit,
    and that a block that fails to parse falls back to the envelope path bit-
    identically — live in `learn.self_test`, next to the respiration path's, because
    they need the renderer. Here: the parse must round-trip the default block, clamp
    every number into range, sort and floor the contour, and refuse junk, because the
    fallback is what keeps every inventory written before this feature valid.
    """
    block = default_block([[0.0, 2400.0], [1.0, 2100.0]], 14000.0)
    p = parse(block)
    assert p is not None
    assert p.level == DEFAULT_LEVEL and p.trachea_cm == DEFAULT_TRACHEA_CM
    assert p.refl == DEFAULT_REFL and p.beta_inj == DEFAULT_BETA_INJ
    assert p.as_dict() == block, "the default block must survive its own JSON form"

    # clamps: every number lands inside its range, however far outside the file was
    wide = parse(
        {
            "contour": [[0.0, 3000.0]],
            "gamma": 1.0e9,
            "level": 4.0,
            "tracheaCm": 0.01,
            "refl": 2.0,
            "betaInj": 9.0,
        }
    )
    assert wide is not None
    assert wide.gamma == GAMMA_MAX and wide.level == LEVEL_MAX
    assert wide.trachea_cm == TRACHEA_CM_MIN and wide.refl == REFL_MAX
    assert wide.beta_inj == BETA_INJ_MAX

    # the contour is sorted and floored: a file whose points arrive out of order or
    # with a degenerate frequency still parses into something both renderers agree on
    messy = parse(
        {
            **block,
            "contour": [[1.0, 2100.0], [0.0, 0.0], [0.5, 2400.0]],
        }
    )
    assert messy is not None
    assert [f for f, _ in messy.contour] == [0.0, 0.5, 1.0]
    assert messy.contour[0][1] == 1.0, "a zero-frequency point is floored, not fatal"

    # junk falls back to None — the syllable then renders single-voiced, unchanged
    assert parse("voices") is None
    assert parse({"level": 0.5}) is None  # missing keys
    assert parse({**block, "contour": []}) is None
    assert parse({**block, "contour": [[0.0]]}) is None
    assert parse({**block, "gamma": float("nan")}) is None
    assert parse({**block, "level": "loud"}) is None
    assert parse({**block, "contour": [[0.0, float("inf")]]}) is None

    if verbose:
        print(
            "twovoice self-test ok: default block round-trips, clamps hold, contour "
            "sorted and floored, junk falls back to the single-voice path"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
