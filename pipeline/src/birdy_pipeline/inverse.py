"""The amortised inverse of docs/09 §9.3 Part 2: mel patch -> syrinx parameters.

**Why this module exists.** `learn.invert_gestures` is coordinate descent over thirteen
gesture axes, three passes, a few hundred renders per type. It only ever moves on an
improvement, so it cannot escape a bad basin: the cluster median carries measured contour,
duration and timbre, but the §8.1a gesture fields (`gammaScale`, `tractQ`, `noise`, `rough`)
start from their *defaults* — 1.0, 0, 0, 0 — regardless of what the syllable sounds like.
Measured over the fitted inventory, those defaults are wrong for 78 % of types on
`gammaScale` alone. This module learns the inverse map directly: one forward pass from the
critic's `(32, 23)` log-mel patch to a full parameter vector, after which the same descent
polishes. The encoder finds the basin; the search keeps the last few per cent.

**Why the training data is free, and why that matters.** We own the forward model. Sampling
a parameter vector, rendering it through `syrinx.render_syllable` and measuring the result
with `features.mel_patch` — the *same* function the critic consumes, so real and synthetic
are never measured differently — yields an unlimited, perfectly labelled dataset. No audio
retention, no annotation, no licensing: this is DDSP's encoder-decoder with the syrinx as
the decoder, which is exactly why the interpretability DDSP gives up survives here (§9.3
Part 2). The synthesiser stays physical; the network only ever *proposes a starting point*.

**The sampler is empirical, not uniform.** "Plausible" parameter vectors are drawn from the
marginal distributions of the *fitted* inventory (`data/learned-inventory.json`, ids `L*`),
with small jitter, rather than from uniform boxes. A uniform box over 16 axes puts most of
its mass in regions no fit ever lands in — a 2 s buzz at 12 kHz with full roughness — and an
encoder trained there spends its capacity interpolating between syllables that do not exist.
The fitted marginals are the measure of what the model is actually asked to invert. The
cost is real and acknowledged: independent marginals break the joint (a buzz's correlation
with `noise` is lost), so the sampled set is a *superset* of the plausible manifold, not a
sample from it. The contour is the one joint kept: 70 % of samples perturb a real fitted
contour (shape preserved, pitch shifted and knots jittered), 30 % draw fresh 2-6 knot
contours from the empirical knot-count and log-Hz marginals.

**What the patch cannot see, and the honest consequence.** `features.mel_patch` is
mean-centred and resampled onto the syllable's *own* duration. Two parameters are therefore
structurally invisible in it: **level** (loudness is removed by the centring) and
**duration** (the time axis is normalised). The network heads for both exist — the
parameters are part of the vector — but they can only learn the marginal mean, and their
loss weights are set near zero to say so. At the seam in `learn` (`init_syllable`) the
measured contour and duration are kept and only the gesture fields are taken from the
encoder: pitch and duration are the two things the F0 tracker already gets to ~1 % and the
descent never moves (`learn._SEARCH_AXES` excludes them deliberately), so replacing a
measurement with a regression estimate could only hurt.

**torch is imported at the top of this module and nowhere else outside `critic.py`.** Every
caller imports `inverse` inside a function and degrades to the un-initialised descent when
the import fails, so `pyproject.toml`'s `critic` extra stays optional.

---

## Results: measured 2026-07-29, and the ship rule says no

The pre-registered bake-off of the plan: 24 fitted types over 10 species, taken at the
~10/50/90 % shipped-cosine quantiles of the eight most-fitted species (plus two to fill
slots), with their member observations from `out/harvest-gan`. Baseline is the path
`learn.py` takes today — cluster median, then `invert_gestures`. Challenger is the same
median re-initialised by the encoder on the gesture axes (contour and duration stay
measured; see above), then the *same* descent at the same budget. The per-species trachea
fit is excluded from both arms: it is per-bird, orthogonal to the initialisation seam, and
would add the identical formant bank to both starting syllables. Dataset: 150 k sampled
pairs (~516 render+patch/s under background load, 295 s; ~810/s unloaded), encoder 509 k
parameters, best validation loss 1.309 at epoch 14 of 80 (early-stopped at 26).

| species | type | n | shipped | b_start | b_cos | b_s | e_only | c_cos | c_s |
|---|---|---|---|---|---|---|---|---|---|
| luscinia_svecica | L45 | 118 | 0.630 | 0.465 | 0.630 | 0.2 | 0.426 | 0.640 | 0.3 |
| troglodytes_troglodytes | L33 | 301 | 0.649 | 0.544 | 0.643 | 0.2 | 0.559 | 0.715 | 0.2 |
| parus_major | L26 | 121 | 0.662 | 0.491 | 0.712 | 0.3 | 0.105 | 0.752 | 0.3 |
| cuculus_solitarius | L06 | 9 | 0.609 | 0.333 | 0.609 | 0.3 | 0.158 | 0.743 | 0.3 |
| luscinia_megarhynchos | L44 | 264 | 0.552 | 0.067 | 0.552 | 0.2 | 0.111 | 0.547 | 0.2 |
| strix_aluco | L13 | 36 | 0.499 | 0.306 | 0.499 | 0.8 | 0.324 | 0.586 | 0.4 |
| turdus_philomelos | L06 | 257 | 0.543 | 0.056 | 0.543 | 0.2 | -0.099 | 0.545 | 0.2 |
| cuculus_clamosus | L03 | 94 | 0.517 | 0.086 | 0.517 | 0.2 | 0.062 | 0.710 | 0.2 |
| poecile_cinctus | L04 | 148 | 0.616 | -0.576 | 0.616 | 0.9 | 0.066 | 0.611 | 0.4 |
| parus_minor | L04 | 194 | 0.563 | 0.292 | 0.563 | 0.2 | 0.451 | 0.472 | 0.2 |
| luscinia_svecica | L26 | 185 | 0.789 | 0.626 | 0.789 | 0.2 | 0.672 | 0.730 | 0.1 |
| troglodytes_troglodytes | L02 | 57 | 0.761 | 0.690 | 0.765 | 0.2 | 0.576 | 0.825 | 0.2 |
| parus_major | L09 | 48 | 0.780 | 0.572 | 0.777 | 0.2 | 0.210 | 0.767 | 0.2 |
| cuculus_solitarius | L27 | 10 | 0.900 | 0.650 | 0.900 | 0.4 | 0.719 | 0.878 | 0.3 |
| luscinia_megarhynchos | L20 | 185 | 0.757 | 0.720 | 0.757 | 0.1 | 0.443 | 0.807 | 0.2 |
| strix_aluco | L10 | 74 | 0.682 | 0.377 | 0.682 | 0.2 | 0.279 | 0.604 | 0.2 |
| turdus_philomelos | L07 | 286 | 0.811 | 0.616 | 0.811 | 0.4 | 0.360 | 0.722 | 0.4 |
| cuculus_clamosus | L07 | 150 | 0.756 | 0.419 | 0.756 | 0.8 | 0.260 | 0.784 | 0.9 |
| poecile_cinctus | L10 | 79 | 0.706 | 0.047 | 0.706 | 0.2 | 0.152 | 0.783 | 0.4 |
| parus_minor | L01 | 292 | 0.779 | 0.298 | 0.779 | 0.5 | 0.074 | 0.600 | 0.2 |
| luscinia_svecica | L08 | 49 | 0.883 | 0.563 | 0.883 | 0.2 | 0.430 | 0.871 | 0.2 |
| troglodytes_troglodytes | L27 | 143 | 0.882 | 0.772 | 0.893 | 0.2 | 0.789 | 0.882 | 0.2 |
| parus_major | L33 | 74 | 0.892 | 0.380 | 0.895 | 0.1 | 0.389 | 0.882 | 0.2 |
| luscinia_megarhynchos | L45 | 71 | 0.876 | 0.484 | 0.876 | 0.2 | 0.369 | 0.887 | 0.1 |
| **MEDIAN** | | | **0.731** | **0.442** | **0.734** | **0.2** | **0.342** | **0.737** | **0.2** |

(`shipped` is the cosine in `data/learned-inventory.json`, which includes the per-species
trachea both arms lack — orientation only, not comparable. `b_start` = cluster median,
`b_cos`/`b_s` = baseline after descent and its wall time; `e_only` = encoder init with no
polish; `c_cos`/`c_s` = challenger after descent and its total time including the forward
pass.)

**The ship rule was: median challenger cosine >= baseline - 0.01 AND median challenger
time <= 0.5x baseline. The cosine arm passes (0.737 >= 0.724) and the time arm fails
outright (0.2 s vs a 0.1 s bar), so the encoder is NOT wired into `learn`.** The module
stays as experimental code; this table is the deliverable.

Three honest readings, in increasing order of consequence:

1. **The time premise does not hold on this hardware.** Coordinate descent over thirteen
   axes costs ~0.2 s per type median because a render+score is ~2 ms; the encoder forward
   pass is milliseconds, so total time is the descent's and the descent's cost is fixed
   per pass — a better starting point does not make a pass evaluate fewer candidates. A
   2x speedup was never available: the only saving would be passes skipped entirely, and
   the descent exits early on neither arm.
2. **The final cosine is a wash (+0.003 median, and the variance is the story).** The
   encoder finds genuinely better basins where the median starts badly
   (cuculus_solitarius/L06 0.609 -> 0.743, cuculus_clamosus/L03 0.517 -> 0.710) and loses
   exactly as loudly elsewhere (parus_minor/L01 0.779 -> 0.600, strix_aluco/L10 0.682 ->
   0.604). That is the signature of an initialiser that sometimes knows something the
   median does not and sometimes overwrites something the median knew.
3. **The mechanism of the losses is visible in the start column.** The encoder-only start
   scores *below* the cluster median it modifies (0.342 vs 0.442): on the fields the
   median already measures — timbre, attack, hold, harmonic, the modulations — the
   encoder's regression estimate is worse than the measurement it replaces. Its only
   *new* information is on the §8.1a axes the median carries no value for (`gammaScale`,
   `tractQ`, `noise`, `rough`), and the wins cluster exactly there. A variant that
   initialises only those four axes was not run: it was not the pre-registered arm, and
   registering it after seeing this table would be the HARKing docs/09's discipline
   exists to prevent. It is the obvious next experiment if anyone revisits this.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from . import features, syrinx

FORMAT_VERSION = 1

# --- the parameter vector ----------------------------------------------------------

#: The contour is predicted as log-Hz at these six fixed fractions of the syllable's own
#: duration — the simpler of the two options (a fixed grid, against K knots plus a validity
#: mask). A mask would let the network say "this syllable has two knots", but the renderer
#: log-interpolates whatever it is given, the descent never moves the contour, and at the
#: seam the measured contour is kept anyway — so the extra machinery would buy nothing.
CONTOUR_GRID = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
K_KNOTS = len(CONTOUR_GRID)

#: Physical bounds, taken from the search axes of `learn._SEARCH_AXES` and the observed
#: fitted ranges, so a decoded prediction can never propose a syllable the search itself
#: could not reach. The contour bounds are the store's f0 span (docs/08 §8.1's 80 Hz floor
#: to the top of what the harvest contains).
HZ_LO, HZ_HI = 80.0, 16000.0
DUR_LO, DUR_HI = 0.02, 2.3
LEVEL_LO, LEVEL_HI = 0.3, 1.35
ATTACK_LO, ATTACK_HI = 0.002, 0.12
HARMONIC_HI = 1.0
AM_LO, AM_HI = 12.0, 140.0
AM_DEPTH_HI = 0.85
VIB_RATE_LO, VIB_RATE_HI = 4.0, 34.0
VIB_DEPTH_HI = 0.3
GAMMA_SCALE_LO, GAMMA_SCALE_HI = 0.5, 6.0
TRACT_Q_HI = 30.0
NOISE_HI = 0.85
ROUGH_HI = 0.65

TIMBRES = ("pure", "reed", "buzz")

#: The continuous outputs, in head order. Rates are log-scaled like every positive span;
#: `tractQ` is `log1p` because 0 is a common and meaningful value. The two modulation
#: *rates* are only defined when their depth is non-zero — an AM depth with no rate is
#: silent and a rate with no depth is inaudible (`learn._with`) — so their loss is masked
#: and the mask is stored with the dataset.
CONT_NAMES = (
    [f"contour{i}" for i in range(K_KNOTS)]
    + [
        "ln_dur",
        "level",
        "ln_attack",
        "harmonic",
        "ln_am",
        "am_depth",
        "ln_vib_rate",
        "vib_depth",
        "ln_gamma_scale",
        "log1p_tract_q",
        "noise",
        "rough",
    ]
)
N_CONT = len(CONT_NAMES)
_I = {name: i for i, name in enumerate(CONT_NAMES)}
#: Outputs whose supervision is conditional: the rate heads only get a gradient where the
#: syllable actually modulates. Every other output is supervised on every sample.
_MASKED = {"ln_am": "am_depth", "ln_vib_rate": "vib_depth"}

#: Loss weights, proportional to each parameter's audible effect — the criterion the plan
#: sets — judged against what the patch can express:
#:
#:   * contour 3.0 — pitch trajectory is the dominant perceptual feature of a syllable;
#:     the hand-written typing vector leads with it at 6x for the same reason.
#:   * ln_dur 0.25, level 0.1 — **structurally invisible in a mean-centred,
#:     duration-normalised patch** (see the module docstring). These heads predict the
#:     marginal mean and the weight says so rather than pretending otherwise.
#:   * ln_gamma_scale 1.0 — the axis with the most leverage in the descent (`gammaScale`
#:     goes first in `_SEARCH_AXES` because it decides how harmonically rich the *source*
#:     is), and richness is a spectral property the patch shows plainly.
#:   * noise 1.0 — turbulence moves spectral flatness across the whole band, the exact
#:     measurement the §8.1a calibration was made against.
#:   * am_depth / vib_depth 1.0 — modulation depth is a strong time/frequency ripple in
#:     the patch; the rates (0.5) matter only through it and are masked without it.
#:   * attack 0.5, harmonic 0.5, tractQ 0.5, rough 0.5 — audible but second-order in the
#:     patch: onset shape is two knots at this resolution, and a tract Q moves dB within
#:     an already-correct band rather than moving the band.
#:   * timbre CE 1.0 — a 3-way decision that flips the whole source regime.
#:   * hold CE 0.5 — envelope shape, visible but coarse at 32 knots.
LOSS_WEIGHTS = {
    **{f"contour{i}": 3.0 for i in range(K_KNOTS)},
    "ln_dur": 0.25,
    "level": 0.1,
    "ln_attack": 0.5,
    "harmonic": 0.5,
    "ln_am": 0.5,
    "am_depth": 1.0,
    "ln_vib_rate": 0.5,
    "vib_depth": 1.0,
    "ln_gamma_scale": 1.0,
    "log1p_tract_q": 0.5,
    "noise": 1.0,
    "rough": 0.5,
}
W_TIMBRE = 1.0
W_HOLD = 0.5

#: Reporting groups for the validation summary: which outputs are read together when
#: judging whether the encoder learned a *parameter*, not a loss.
GROUPS = {
    "contour": [f"contour{i}" for i in range(K_KNOTS)],
    "dur": ["ln_dur"],
    "level": ["level"],
    "attack": ["ln_attack"],
    "harmonic": ["harmonic"],
    "am": ["ln_am", "am_depth"],
    "vib": ["ln_vib_rate", "vib_depth"],
    "gammaScale": ["ln_gamma_scale"],
    "tractQ": ["log1p_tract_q"],
    "noise": ["noise"],
    "rough": ["rough"],
}


# --- the sampler ---------------------------------------------------------------------


class EmpiricalSampler:
    """Draws plausible syllable parameter sets from the fitted inventory's marginals.

    Built once from an inventory document; every field of every `L*` syllable (with the
    renderer's defaults for absent fields, which is what absence *means* in the schema)
    becomes one empirical distribution. Sampling is a bootstrap draw plus jitter —
    multiplicative in log space for positive spans, additive otherwise, none at all on a
    point mass at zero, which is where `noise`, `rough` and the modulation depths honestly
    live half the time — clipped back into the physical bounds above.
    """

    def __init__(self, inventory: dict[str, Any]) -> None:
        rows = [
            s
            for sp in inventory.get("species", [])
            for s in sp.get("syllables", [])
            if str(s.get("id", "")).startswith("L")
        ]
        if len(rows) < 20:
            raise ValueError(
                f"only {len(rows)} fitted syllables in the inventory — too few to call "
                "an empirical distribution. Run `learn` first."
            )
        self.contours = [
            [[float(a), float(b)] for a, b in s["contour"]] for s in rows
        ]
        self.knot_counts = np.asarray([len(c) for c in self.contours])
        self.knot_hz = np.asarray(
            [p[1] for c in self.contours for p in c], dtype=np.float64
        )
        self.fields = {
            "dur": np.asarray([s.get("dur", 0.1) for s in rows]),
            "level": np.asarray([s.get("level", 0.85) for s in rows]),
            "attack": np.asarray([s.get("attack", syrinx.DEFAULT_ATTACK) for s in rows]),
            "harmonic": np.asarray([s.get("harmonic", 0.0) for s in rows]),
            "am": np.asarray([s.get("am", 0.0) for s in rows]),
            "amDepth": np.asarray([s.get("amDepth", 0.0) for s in rows]),
            "vibRate": np.asarray([(s.get("vib") or {}).get("rate", 0.0) for s in rows]),
            "vibDepth": np.asarray(
                [(s.get("vib") or {}).get("depth", 0.0) for s in rows]
            ),
            "gammaScale": np.asarray([s.get("gammaScale", 1.0) or 1.0 for s in rows]),
            "tractQ": np.asarray([s.get("tractQ", 0.0) or 0.0 for s in rows]),
            "noise": np.asarray([s.get("noise", 0.0) for s in rows]),
            "rough": np.asarray([s.get("rough", 0.0) for s in rows]),
        }
        timbres = [str(s.get("timbre", "pure")) for s in rows]
        self.timbre_p = np.asarray([timbres.count(t) for t in TIMBRES], dtype=np.float64)
        self.timbre_p /= self.timbre_p.sum()
        self.hold_p = float(np.mean([bool(s.get("hold", False)) for s in rows]))

    def _field(
        self,
        rng: np.random.Generator,
        name: str,
        lo: float,
        hi: float,
        sigma_log: float = 0.15,
        sigma_abs: float = 0.0,
    ) -> float:
        """One bootstrap draw + jitter from a field's empirical marginal, clipped."""
        v = float(self.fields[name][rng.integers(0, len(self.fields[name]))])
        if v > 0.0:
            v *= float(math.exp(rng.normal(0.0, sigma_log)))
        elif sigma_abs > 0.0:
            v += float(rng.normal(0.0, sigma_abs))
        return float(np.clip(v, lo, hi))

    def _contour(self, rng: np.random.Generator) -> list[list[float]]:
        """A perturbed fitted contour 70 % of the time, a fresh one otherwise.

        The perturbation keeps the *shape* — real contours are arches, sweeps and trills,
        not random walks — while moving it in pitch (a global log2 shift, so the dataset
        spans the store's 80-16000 Hz rather than only the fitted 420-11000) and in
        detail (per-knot jitter). The fresh draw covers shapes no fitted type happens to
        carry, from the same marginals.
        """
        if rng.random() < 0.7:
            pts = [list(p) for p in self.contours[rng.integers(0, len(self.contours))]]
            shift = float(rng.normal(0.0, 0.75))  # octaves
            out = []
            for i, (frac, hz) in enumerate(pts):
                f = float(frac)
                if 0.0 < f < 1.0:
                    f = float(np.clip(f + rng.normal(0.0, 0.03), 0.02, 0.98))
                h = hz * 2.0 ** (shift + rng.normal(0.0, 0.1))
                out.append([f, float(np.clip(h, HZ_LO, HZ_HI))])
            out.sort(key=lambda p: p[0])
            out[0][0], out[-1][0] = 0.0, 1.0
            return out
        k = int(
            np.clip(
                self.knot_counts[rng.integers(0, len(self.knot_counts))], 2, K_KNOTS
            )
        )
        fracs = [0.0] + sorted(rng.uniform(0.05, 0.95, size=k - 2).tolist()) + [1.0]
        return [
            [
                round(float(f), 4),
                float(
                    np.clip(
                        2.0 ** (math.log2(self.knot_hz[rng.integers(0, len(self.knot_hz))])
                                + rng.normal(0.0, 0.4)),
                        HZ_LO,
                        HZ_HI,
                    )
                ),
            ]
            for f in fracs
        ]

    def sample(self, rng: np.random.Generator) -> dict[str, Any]:
        """One syllable dict, ready for `syrinx.render_syllable`."""
        syl: dict[str, Any] = {
            "id": "inv",
            "dur": round(self._field(rng, "dur", DUR_LO, DUR_HI), 4),
            "level": round(self._field(rng, "level", LEVEL_LO, LEVEL_HI), 3),
            "timbre": TIMBRES[int(rng.choice(len(TIMBRES), p=self.timbre_p))],
            "contour": self._contour(rng),
            "attack": round(self._field(rng, "attack", ATTACK_LO, ATTACK_HI), 4),
            "hold": bool(rng.random() < self.hold_p),
            "harmonic": round(
                self._field(rng, "harmonic", 0.0, HARMONIC_HI, sigma_abs=0.02), 3
            ),
            "gammaScale": round(
                self._field(rng, "gammaScale", GAMMA_SCALE_LO, GAMMA_SCALE_HI), 3
            ),
            "tractQ": round(self._field(rng, "tractQ", 0.0, TRACT_Q_HI), 2),
            "noise": round(self._field(rng, "noise", 0.0, NOISE_HI, sigma_abs=0.02), 3),
            "rough": round(self._field(rng, "rough", 0.0, ROUGH_HI, sigma_abs=0.02), 3),
        }
        am_depth = self._field(rng, "amDepth", 0.0, AM_DEPTH_HI, sigma_abs=0.05)
        if am_depth > 0.0:
            syl["am"] = round(self._field(rng, "am", AM_LO, AM_HI), 2)
            syl["amDepth"] = round(am_depth, 3)
        vib_depth = self._field(rng, "vibDepth", 0.0, VIB_DEPTH_HI, sigma_abs=0.01)
        if vib_depth > 0.0:
            syl["vib"] = {
                "rate": round(self._field(rng, "vibRate", VIB_RATE_LO, VIB_RATE_HI), 2),
                "depth": round(vib_depth, 3),
            }
        return syl


# --- target encoding / decoding --------------------------------------------------------


def encode_target(syllable: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, int, int]:
    """The regression target of one syllable: (values, mask, timbre idx, hold idx).

    The mask is 1 everywhere except on the conditional rate heads (`ln_am`, `ln_vib_rate`)
    of syllables that do not modulate — supervising a rate whose depth is zero would teach
    the head to fit noise, because the renderer ignores it too.
    """
    syl = syrinx.Syllable.from_dict(syllable)
    hz = syrinx.contour_f0(syl.contour, np.asarray(CONTOUR_GRID))
    v = np.zeros(N_CONT, dtype=np.float32)
    v[:K_KNOTS] = np.log(np.maximum(hz, HZ_LO))
    v[_I["ln_dur"]] = math.log(np.clip(syl.dur, DUR_LO, DUR_HI))
    v[_I["level"]] = np.clip(syl.level, LEVEL_LO, LEVEL_HI)
    v[_I["ln_attack"]] = math.log(np.clip(syl.attack, ATTACK_LO, ATTACK_HI))
    v[_I["harmonic"]] = np.clip(syl.harmonic, 0.0, HARMONIC_HI)
    v[_I["ln_am"]] = math.log(np.clip(syl.am if syl.am > 0 else AM_LO, AM_LO, AM_HI))
    v[_I["am_depth"]] = np.clip(syl.am_depth, 0.0, AM_DEPTH_HI)
    v[_I["ln_vib_rate"]] = math.log(
        np.clip(syl.vib_rate if syl.vib_rate > 0 else VIB_RATE_LO, VIB_RATE_LO, VIB_RATE_HI)
    )
    v[_I["vib_depth"]] = np.clip(syl.vib_depth, 0.0, VIB_DEPTH_HI)
    v[_I["ln_gamma_scale"]] = math.log(
        np.clip(syl.gamma_scale, GAMMA_SCALE_LO, GAMMA_SCALE_HI)
    )
    v[_I["log1p_tract_q"]] = math.log1p(np.clip(syl.tract_q, 0.0, TRACT_Q_HI))
    v[_I["noise"]] = np.clip(syl.noise, 0.0, NOISE_HI)
    v[_I["rough"]] = np.clip(syl.rough, 0.0, ROUGH_HI)

    mask = np.ones(N_CONT, dtype=np.float32)
    for rate, depth in _MASKED.items():
        if v[_I[depth]] <= 0.0:
            mask[_I[rate]] = 0.0
    timbre = TIMBRES.index(syl.timbre) if syl.timbre in TIMBRES else 0
    return v, mask, timbre, int(syl.hold)


def decode_target(v: np.ndarray) -> dict[str, Any]:
    """Physical parameter values from a (de-standardised) head output, clipped to bounds."""
    contour = [
        [float(t), float(np.clip(math.exp(float(h)), HZ_LO, HZ_HI))]
        for t, h in zip(CONTOUR_GRID, v[:K_KNOTS])
    ]
    return {
        "contour": contour,
        "dur": float(np.clip(math.exp(v[_I["ln_dur"]]), DUR_LO, DUR_HI)),
        "level": float(np.clip(v[_I["level"]], LEVEL_LO, LEVEL_HI)),
        "attack": float(np.clip(math.exp(v[_I["ln_attack"]]), ATTACK_LO, ATTACK_HI)),
        "harmonic": float(np.clip(v[_I["harmonic"]], 0.0, HARMONIC_HI)),
        "am": float(np.clip(math.exp(v[_I["ln_am"]]), AM_LO, AM_HI)),
        "amDepth": float(np.clip(v[_I["am_depth"]], 0.0, AM_DEPTH_HI)),
        "vibRate": float(np.clip(math.exp(v[_I["ln_vib_rate"]]), VIB_RATE_LO, VIB_RATE_HI)),
        "vibDepth": float(np.clip(v[_I["vib_depth"]], 0.0, VIB_DEPTH_HI)),
        "gammaScale": float(
            np.clip(math.exp(v[_I["ln_gamma_scale"]]), GAMMA_SCALE_LO, GAMMA_SCALE_HI)
        ),
        "tractQ": float(np.clip(math.expm1(v[_I["log1p_tract_q"]]), 0.0, TRACT_Q_HI)),
        "noise": float(np.clip(v[_I["noise"]], 0.0, NOISE_HI)),
        "rough": float(np.clip(v[_I["rough"]], 0.0, ROUGH_HI)),
    }


def apply_prediction(syllable: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """A copy of `syllable` with the predicted gesture fields written in.

    `params` carries decoded physical values plus `timbre` and `hold`. The modulation
    pairs are written atomically — a depth implies its rate and vice versa — and dropped
    below audibility rather than shipped as decoration, mirroring `learn._with`.
    Everything the encoder does not predict (id, labels, formants, tube) passes through
    untouched.
    """
    out = dict(syllable)
    for key in ("contour", "dur", "level", "timbre", "attack", "hold", "harmonic",
                "gammaScale", "tractQ", "noise", "rough"):
        if key in params:
            out[key] = params[key]
    if params.get("amDepth", 0.0) > 0.05:
        out["am"] = round(float(params["am"]), 2)
        out["amDepth"] = round(float(params["amDepth"]), 3)
    else:
        out.pop("am", None)
        out.pop("amDepth", None)
    if params.get("vibDepth", 0.0) > 0.01:
        out["vib"] = {
            "rate": round(float(params["vibRate"]), 2),
            "depth": round(float(params["vibDepth"]), 3),
        }
    else:
        out.pop("vib", None)
    return out


# --- the dataset -------------------------------------------------------------------------


def build_dataset(
    pairs: int,
    sampler: EmpiricalSampler,
    calibration: Any = None,
    seed: int = 0,
    log: Any = print,
) -> dict[str, np.ndarray]:
    """Render `pairs` sampled syllables and return patches + encoded targets.

    Measured 2026-07-29 on this machine: ~810 render+patch/s single-core at the fitted
    duration distribution (median 77 ms), so 150 k pairs is ~3-4 minutes and the
    multiprocessing the plan allowed for is not worth its determinism and numba-warmup
    complications. `stream=i` gives every pair its own deterministic turbulence/roughness
    realisation — the renderer's xorshift streams stay intact, and the dataset is
    reproducible from `seed` alone.
    """
    rng = np.random.default_rng(seed)
    patches = np.zeros((pairs,) + features.PATCH_SHAPE, dtype=np.float16)
    values = np.zeros((pairs, N_CONT), dtype=np.float32)
    masks = np.zeros((pairs, N_CONT), dtype=np.float32)
    timbre = np.zeros(pairs, dtype=np.int64)
    hold = np.zeros(pairs, dtype=np.int64)
    t0 = time.time()
    for i in range(pairs):
        syl = sampler.sample(rng)
        audio = syrinx.render_syllable(syl, calibration=calibration, stream=i)
        patch = features.mel_patch(syrinx.peak_normalise(audio))
        v, m, tb, hd = encode_target(syl)
        patches[i] = patch.astype(np.float16)
        values[i], masks[i], timbre[i], hold[i] = v, m, tb, hd
        if log and (i + 1) % 20000 == 0:
            rate = (i + 1) / (time.time() - t0)
            log(f"  {i + 1}/{pairs} pairs ({rate:.0f}/s)")
    return {
        "patches": patches,
        "values": values,
        "masks": masks,
        "timbre": timbre,
        "hold": hold,
    }


def save_dataset(data: dict[str, np.ndarray], path: Path) -> None:
    np.savez_compressed(Path(path), **data)


def load_dataset(path: Path) -> dict[str, np.ndarray]:
    with np.load(Path(path)) as z:
        return {k: z[k] for k in z.files}


# --- the network -------------------------------------------------------------------------


class InverseEncoder(nn.Module):
    """The critic's trunk shape, read as a regressor: patch -> parameter vector.

    Four 3x3 convs (1 -> w -> 2w -> 4w -> 4w) on the `1x32x23` patch, pooled to the
    critic's (4, 2) grid — coarse position kept, because *which* frequency is the whole
    question — then a small MLP to the heads. **No spectral normalisation**, and that is
    deliberate rather than a departure: the critic is spectrally normalised because its
    gradient is used as a *distance* coordinate descent must follow. This network's
    gradient is never consumed — only its point prediction, which the descent then
    re-scores against the true objective — so the Lipschitz bound would cost capacity for
    nothing.
    """

    POOL = (4, 2)

    def __init__(self, width: int = 32, hidden: int = 256) -> None:
        super().__init__()
        self.width = int(width)
        self.hidden = int(hidden)
        w = self.width
        self.conv1 = nn.Conv2d(1, w, 3, padding=1)
        self.conv2 = nn.Conv2d(w, 2 * w, 3, padding=1)
        self.conv3 = nn.Conv2d(2 * w, 4 * w, 3, padding=1)
        self.conv4 = nn.Conv2d(4 * w, 4 * w, 3, padding=1)
        self.head = nn.Sequential(
            nn.Linear(4 * w * self.POOL[0] * self.POOL[1], hidden),
            nn.SiLU(),
            nn.Linear(hidden, N_CONT + len(TIMBRES) + 2),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        h = F.silu(self.conv1(x))
        h = F.max_pool2d(F.silu(self.conv2(h)), 2)
        h = F.max_pool2d(F.silu(self.conv3(h)), 2)
        h = F.silu(self.conv4(h))
        h = F.adaptive_avg_pool2d(h, self.POOL).flatten(1)
        out = self.head(h)
        return out[:, :N_CONT], out[:, N_CONT : N_CONT + len(TIMBRES)], out[:, N_CONT + len(TIMBRES) :]


# --- training ----------------------------------------------------------------------------


@dataclass
class InverseConfig:
    """Everything the training run is allowed to depend on. Saved next to the weights."""

    width: int = 32
    hidden: int = 256
    epochs: int = 80
    batch: int = 512
    lr: float = 2.0e-3
    weight_decay: float = 1.0e-4
    #: Early stopping on the validation loss; the metric that decides is never the one
    #: still improving on training data.
    patience: int = 12
    val_fraction: float = 0.05
    seed: int = 0
    pairs: int = 0  # recorded, not used: how many pairs the dataset held
    prefer_gpu: bool = True


@dataclass
class InverseReport:
    """What the run measured. Every number is on the validation split."""

    epochs: int = 0
    n_train: int = 0
    n_val: int = 0
    final_val_loss: float = 0.0
    group_val_mse: dict[str, float] = field(default_factory=dict)
    timbre_val_accuracy: float = 0.0
    hold_val_accuracy: float = 0.0
    device: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def device_for(prefer_gpu: bool = True) -> torch.device:
    """CUDA when it is there, CPU when it is not; never an error either way (§9.4)."""
    if prefer_gpu and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def train(
    data: dict[str, np.ndarray],
    config: InverseConfig | None = None,
    log: Any = print,
) -> "Inverse":
    """Train the encoder on a `build_dataset` result and return it with its report."""
    cfg = config or InverseConfig()
    torch.manual_seed(cfg.seed)
    rng = np.random.default_rng(cfg.seed)
    device = device_for(cfg.prefer_gpu)

    patches = data["patches"].astype(np.float32)
    values, masks = data["values"], data["masks"]
    timbre, hold = data["timbre"], data["hold"]
    n = patches.shape[0]
    order = rng.permutation(n)
    n_val = max(cfg.batch, int(round(n * cfg.val_fraction)))
    val_idx, train_idx = order[:n_val], order[n_val:]

    # Standardisation statistics from the training split only: per-band for the input
    # (the bands differ by an order of magnitude in variance), per-output for the targets
    # over valid entries only, so the masked rate heads are centred on the syllables that
    # actually supervise them.
    tr = patches[train_idx]
    in_mean = tr.mean(axis=(0, 1), keepdims=True).astype(np.float32)
    in_std = np.maximum(tr.std(axis=(0, 1), keepdims=True), 1e-3).astype(np.float32)
    tgt_mean = np.zeros((1, N_CONT), dtype=np.float32)
    tgt_std = np.ones((1, N_CONT), dtype=np.float32)
    for j in range(N_CONT):
        valid = values[train_idx][masks[train_idx][:, j] > 0, j]
        if valid.size:
            tgt_mean[0, j] = valid.mean()
            tgt_std[0, j] = max(float(valid.std()), 1e-3)

    model = InverseEncoder(cfg.width, cfg.hidden).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps_per_epoch = max(1, len(train_idx) // cfg.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=cfg.lr, total_steps=steps_per_epoch * cfg.epochs
    )
    weight = torch.tensor(
        [LOSS_WEIGHTS[name] for name in CONT_NAMES], dtype=torch.float32, device=device
    )

    def to_input(p: np.ndarray) -> torch.Tensor:
        z = (p - in_mean) / in_std
        return torch.from_numpy(np.ascontiguousarray(z, dtype=np.float32)).unsqueeze(1).to(device)

    def to_targets(idx: np.ndarray) -> tuple[torch.Tensor, ...]:
        v = torch.from_numpy((values[idx] - tgt_mean) / tgt_std).to(device)
        m = torch.from_numpy(masks[idx]).to(device)
        tb = torch.from_numpy(timbre[idx]).to(device)
        hd = torch.from_numpy(hold[idx]).to(device)
        return v, m, tb, hd

    def batch_loss(idx: np.ndarray) -> torch.Tensor:
        pred, t_logit, h_logit = model(to_input(patches[idx]))
        v, m, tb, hd = to_targets(idx)
        mse = ((pred - v) ** 2) * m * weight
        cont = mse.sum() / (m * weight).sum().clamp_min(1e-9)
        return (
            cont
            + W_TIMBRE * F.cross_entropy(t_logit, tb)
            + W_HOLD * F.cross_entropy(h_logit, hd)
        )

    log(
        f"inverse: {len(train_idx)} train + {len(val_idx)} val pairs, "
        f"{sum(p.numel() for p in model.parameters()) / 1e3:.0f} k parameters, "
        f"on {device.type}"
    )

    best_val, best_state, stale = math.inf, None, 0
    epochs_run = 0
    for epoch in range(cfg.epochs):
        model.train()
        running = 0.0
        for _ in range(steps_per_epoch):
            idx = train_idx[rng.integers(0, len(train_idx), size=cfg.batch)]
            loss = batch_loss(idx)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            if sched.last_epoch < steps_per_epoch * cfg.epochs - 1:
                sched.step()
            running += loss.detach().item()
        running /= steps_per_epoch
        epochs_run = epoch + 1

        model.eval()
        with torch.no_grad():
            val_loss = 0.0
            for i in range(0, len(val_idx), 4096):
                val_loss += float(batch_loss(val_idx[i : i + 4096])) * len(
                    val_idx[i : i + 4096]
                )
            val_loss /= len(val_idx)
        if epoch % max(1, cfg.epochs // 10) == 0 or epoch == cfg.epochs - 1:
            log(f"  epoch {epoch + 1:3d}/{cfg.epochs}  train {running:.4f}  val {val_loss:.4f}")
        if val_loss < best_val - 1.0e-4:
            best_val, stale = val_loss, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= cfg.patience:
                log(f"  early stop at epoch {epoch + 1} (val flat for {cfg.patience})")
                break
    if best_state is not None:
        model.load_state_dict(best_state)

    inverse = Inverse(
        model=model,
        in_mean=in_mean,
        in_std=in_std,
        tgt_mean=tgt_mean,
        tgt_std=tgt_std,
        config=cfg,
    )
    inverse.report = _evaluate(inverse, patches, values, masks, timbre, hold, val_idx)
    inverse.report.epochs = epochs_run
    inverse.report.n_train, inverse.report.n_val = len(train_idx), len(val_idx)
    inverse.report.final_val_loss = round(best_val, 5)
    inverse.report.device = device.type
    return inverse


def _evaluate(
    inverse: "Inverse",
    patches: np.ndarray,
    values: np.ndarray,
    masks: np.ndarray,
    timbre: np.ndarray,
    hold: np.ndarray,
    idx: np.ndarray,
) -> InverseReport:
    """Per-group validation MSE in physical units, plus the two classification accuracies.

    Physical units on purpose: a z-scored MSE of 0.1 means nothing until it is "the
    contour is wrong by a fifth of an octave" or "gammaScale is off by 30 %", which is the
    judgement the bake-off then gets to make.
    """
    report = InverseReport()
    pred_cont, pred_t, pred_h = inverse._forward(patches[idx])
    physical = pred_cont * inverse.tgt_std + inverse.tgt_mean
    for group, names in GROUPS.items():
        errs = []
        for name in names:
            j = _I[name]
            keep = masks[idx][:, j] > 0
            if not keep.any():
                continue
            diff = physical[keep, j] - values[idx][keep, j]
            if name.startswith("contour"):
                diff = diff / math.log(2.0)  # octaves, the readable unit of pitch error
            errs.append(float(np.mean(diff**2)))
        if errs:
            report.group_val_mse[group] = round(float(np.mean(errs)), 5)
    report.timbre_val_accuracy = round(float((pred_t == timbre[idx]).mean()), 4)
    report.hold_val_accuracy = round(float((pred_h == hold[idx]).mean()), 4)
    return report


# --- the trained thing, and what it is for ------------------------------------------------


class Inverse:
    """A trained `InverseEncoder` plus the standardisation it was trained under.

    Two methods matter: `predict` (patch -> physical parameters, for evaluation) and
    `init_syllable` (the seam `learn` consumes — a syllable dict re-initialised from a
    patch). Duck-typed like `learn.RealismTerm`, so nothing in `learn.py` imports torch.
    """

    def __init__(
        self,
        model: InverseEncoder,
        in_mean: np.ndarray,
        in_std: np.ndarray,
        tgt_mean: np.ndarray,
        tgt_std: np.ndarray,
        config: InverseConfig,
    ) -> None:
        self.model = model.eval()
        self.in_mean, self.in_std = in_mean, in_std
        self.tgt_mean, self.tgt_std = tgt_mean, tgt_std
        self.config = config
        self.report = InverseReport()
        self.device = next(model.parameters()).device

    def _batch(self, patches: np.ndarray) -> torch.Tensor:
        p = np.asarray(patches, dtype=np.float32)
        if p.ndim == 2:
            p = p[None]
        if p.shape[1:] != features.PATCH_SHAPE:
            raise ValueError(
                f"patches are {p.shape[1:]} but this encoder was trained on "
                f"{features.PATCH_SHAPE}"
            )
        z = (p - self.in_mean) / self.in_std
        return torch.from_numpy(np.ascontiguousarray(z)).unsqueeze(1).to(self.device)

    @torch.no_grad()
    def _forward(self, patches: np.ndarray, chunk: int = 4096) -> tuple[np.ndarray, ...]:
        outs: list[tuple[np.ndarray, ...]] = []
        p = np.asarray(patches, dtype=np.float32)
        if p.ndim == 2:
            p = p[None]
        for i in range(0, p.shape[0], chunk):
            cont, t_logit, h_logit = self.model(self._batch(p[i : i + chunk]))
            outs.append(
                (
                    cont.cpu().numpy(),
                    t_logit.cpu().numpy().argmax(axis=1),
                    h_logit.cpu().numpy().argmax(axis=1),
                )
            )
        return tuple(np.concatenate([o[k] for o in outs]) for k in range(3))

    def predict(self, patches: np.ndarray) -> list[dict[str, Any]]:
        """One physical parameter dict per patch, clipped to the searchable bounds."""
        cont, timbre_idx, hold_idx = self._forward(patches)
        out = []
        for i in range(cont.shape[0]):
            params = decode_target(cont[i])
            params["timbre"] = TIMBRES[int(timbre_idx[i])]
            params["hold"] = bool(hold_idx[i])
            out.append(params)
        return out

    def init_syllable(self, syllable: dict[str, Any], patch: np.ndarray) -> dict[str, Any]:
        """The inversion seam: `syllable` re-initialised from one real patch.

        **The measured contour and duration are kept.** They come from the F0 tracker and
        the segmentation, which are measurements good to ~1 % that the descent never moves
        (`learn._SEARCH_AXES` excludes both on purpose); the encoder's own contour/duration
        heads exist for the dataset's completeness and for uses that have no measurement,
        but at this seam a regression estimate replaces a measurement only over the
        gesture axes — timbre, level, attack, hold, harmonic, the modulations, and the
        §8.1a fields the cluster median carries no value for at all.
        """
        params = self.predict(patch)[0]
        params.pop("contour", None)
        params.pop("dur", None)
        return apply_prediction(syllable, params)

    # -- persistence --

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "version": FORMAT_VERSION,
                "state_dict": self.model.state_dict(),
                "in_mean": self.in_mean,
                "in_std": self.in_std,
                "tgt_mean": self.tgt_mean,
                "tgt_std": self.tgt_std,
                "config": asdict(self.config),
                "report": self.report.as_dict(),
                "patch_shape": list(features.PATCH_SHAPE),
                "width": self.model.width,
                "hidden": self.model.hidden,
            },
            path,
        )
        # A readable sibling, because the weights are not auditable and the report is the
        # part anyone reviewing this will want to read.
        path.with_suffix(".json").write_text(
            json.dumps(
                {
                    "version": FORMAT_VERSION,
                    "patchShape": list(features.PATCH_SHAPE),
                    "config": asdict(self.config),
                    "report": self.report.as_dict(),
                },
                indent=1,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path, prefer_gpu: bool = True) -> "Inverse":
        blob = torch.load(Path(path), map_location="cpu", weights_only=False)
        if tuple(blob.get("patch_shape", ())) != features.PATCH_SHAPE:
            raise RuntimeError(
                f"{path} was trained on {tuple(blob.get('patch_shape', ()))} patches but "
                f"this build measures {features.PATCH_SHAPE}. Retrain it: an encoder is "
                "only meaningful on the representation it was fitted to."
            )
        model = InverseEncoder(blob["width"], blob["hidden"])
        model.load_state_dict(blob["state_dict"])
        model.to(device_for(prefer_gpu))
        inverse = cls(
            model=model,
            in_mean=np.asarray(blob["in_mean"], dtype=np.float32),
            in_std=np.asarray(blob["in_std"], dtype=np.float32),
            tgt_mean=np.asarray(blob["tgt_mean"], dtype=np.float32),
            tgt_std=np.asarray(blob["tgt_std"], dtype=np.float32),
            config=InverseConfig(**blob["config"]),
        )
        inverse.report = InverseReport(**blob.get("report", {}))
        return inverse


def self_test(verbose: bool = True) -> None:
    """Sampler/codec invariants, on a handful of renders. No network training."""
    rng = np.random.default_rng(0)
    inventory = {
        "species": [
            {
                "id": "test_bird",
                "syllables": [
                    {
                        "id": f"L{i:02d}",
                        "dur": 0.05 + 0.01 * i,
                        "level": 0.6,
                        "timbre": TIMBRES[i % 3],
                        "contour": [[0.0, 2000.0 + 200 * i], [1.0, 3000.0 + 100 * i]],
                        "attack": 0.008,
                        "hold": i % 2 == 0,
                        "harmonic": 0.1,
                        "gammaScale": 1.5,
                        "tractQ": 6.0,
                        "noise": 0.1 if i % 2 else 0.0,
                        "rough": 0.0,
                    }
                    for i in range(24)
                ],
            }
        ]
    }
    sampler = EmpiricalSampler(inventory)
    syl = sampler.sample(rng)
    v, m, tb, hd = encode_target(syl)
    assert v.shape == (N_CONT,) and m.shape == (N_CONT,)
    params = decode_target(v)
    # The codec round-trips: what was sampled is what is decoded, to clip precision.
    assert abs(params["dur"] - syl["dur"]) < 1e-3
    assert TIMBRES[tb] == syl["timbre"]
    rebuilt = apply_prediction(syl, params)
    audio = syrinx.render_syllable(rebuilt, stream=0)
    patch = features.mel_patch(syrinx.peak_normalise(audio))
    assert patch.shape == features.PATCH_SHAPE
    # A silent-modulation syllable masks its rate heads.
    syl.pop("am", None)
    syl.pop("amDepth", None)
    syl.pop("vib", None)
    _, m2, _, _ = encode_target(syl)
    assert m2[_I["ln_am"]] == 0.0 and m2[_I["ln_vib_rate"]] == 0.0
    if verbose:
        print("inverse self_test: ok")
