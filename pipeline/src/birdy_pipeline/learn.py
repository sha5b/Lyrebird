"""Learn syllables and syntax from real recordings, and check the model can sing them.

Three stages, and each one only exists because the one before it can be *measured*:

  1. **Observe.** While a harvested recording is briefly in memory, segment it into
     syllables and reduce each one to the parameters `data/inventory.json` uses:
     duration, level, attack, an f0 contour, amplitude modulation, vibrato, a harmonic
     ratio and a timbre class. That is a few dozen floats per syllable, so the
     observations survive the recording by four orders of magnitude less storage.

  2. **Fit.** Cluster a species' observations into types and take the median of each
     type. This is the learned repertoire: what this bird actually sings, as opposed to
     what the hand-authored inventory says it sings.

  3. **Verify.** Render each fitted type through the same Mindlin-Laje oscillator the
     app uses and compare the result with the real thing — 28-d descriptor cosine, and
     F0 error against the requested contour. Both numbers are written next to every
     learned syllable. A syllable the physical model cannot reproduce says so instead
     of quietly shipping as if it could.

Then the syntax. Because the observations keep their order within their recording,
typing them turns each recording into a string of type ids, and counting the
transitions gives the same first-order grammar the app already improvises from. New
phrases composed that way are novel — no bird sang them — but they are novel *in a
measured syntax* rather than in one we invented, which is the only sense in which
"new words" is an honest claim. They stay labelled `invented`, and their syllables stay
labelled `unlabelled`: real acoustics, no documented function.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
from sklearn.cluster import KMeans

from . import density, features, syrinx
from .syrinx import Calibration, peak_normalise, render_syllable

# --- segmentation ------------------------------------------------------------------

ENV_FRAME = 512
ENV_HOP = 128
F0_FRAME = 1024
F0_HOP = 256
F0_MIN_HZ = 400.0
F0_MAX_HZ = 12000.0
ONSET_REL = 0.14  # of the recording's envelope peak
MIN_SYLLABLE_S = 0.018
MAX_SYLLABLE_S = 1.2
MERGE_GAP_S = 0.022
# A syllable's pitch is sampled at this many points before redundant ones are dropped,
# so it is the ceiling on how much shape a fitted call can have. Five was enough for a
# whistle and a two-note call and too few for anything with a wobble in it: a nightingale
# phrase came back as a straight line between its endpoints. Nine costs four more floats
# per syllable and is what the resynthesis has to work with.
CONTOUR_KNOTS = 9
COLLINEAR_TOL = 0.025
MAX_PER_RECORDING = 400

# --- fitting -----------------------------------------------------------------------

MIN_OBSERVATIONS = 24  # per species, below which a repertoire is not worth fitting
DEFAULT_TYPES = 8
# Ceiling on the fitted repertoire of one species, however much audio there is. A nightingale
# really has ~180 song types (docs/03-decoding-science.md), so this is generous rather than
# principled; it exists so a KMeans on forty thousand observations cannot ask for four
# thousand clusters and spend an hour producing types with three members each.
MAX_TYPES = 64
OBS_PER_TYPE = 12
GRAMMAR_MIN_COUNT = 2
END = "end"
#: The fit's membership table, written beside `syllables.jsonl` in the store it was
#: fitted from. It is a property of the store's observations, not of the inventory the
#: fit produced, so it lives with the store and a store moved elsewhere carries its
#: typing with it.
TYPING_NAME = "typing.json"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


@dataclass
class SyllableObservation:
    """One segmented syllable, as syrinx parameters. No audio, ~60 floats."""

    species_id: str
    recording_id: str
    order: int
    start: float
    dur: float
    level: float
    attack: float
    hold: bool
    contour: list[list[float]]
    am: float
    am_depth: float
    vib_rate: float
    vib_depth: float
    harmonic: float
    timbre: str
    flatness: float
    gap_before: float
    #: Measured amplitude of each partial, `harmonics[0]` = 1 (§8.1b), and the share of
    #: in-band energy sitting between the partials. Both optional: stores harvested before
    #: they existed do not have them, and the renderer falls back to `harmonic`/`timbre`.
    harmonics: list[float] = field(default_factory=list)
    noise_frac: float = 0.0
    #: Log-mel energies at MEL_KNOTS points across the syllable, flattened row-major
    #: (knots x 26). The time-resolved spectral target the fit optimises against; the 28-d
    #: `descriptor` is a mean over frames and cannot say whether a spectrum moved.
    mel_path: list[float] = field(default_factory=list)
    # The 28-d descriptor of this syllable's own audio (§8.2), taken while the recording
    # is still in memory. It is what `verify_type` compares a resynthesis against: the
    # recording-level descriptor averages five-second windows over everything that
    # recording contains, so it is the same vector for every type of a species and
    # cannot say which of them the model caught. Optional, because stores harvested
    # before this field existed do not have it.
    descriptor: list[float] | None = None
    #: True when the novelty scorer judged this syllable unlike every known type
    #: centroid (docs/09 §9.2b use 2: cosine distance in the critic's embedding past a
    #: threshold calibrated to a chosen false-positive rate). Set at *ingest* time by
    #: the control surface, never by the fit — the flag is evidence about one
    #: observation, not a property a refit should redecide. A flagged syllable is still
    #: `unlabelled` (§8.5): detecting that a sound is new is not knowing what it means.
    #: Keyword with a default because rows harvested before the flag existed carry no
    #: such key, and False is the truth for them — nobody ever measured them.
    novel: bool = False
    #: `features.mel_patch` of this syllable: a (32, 23) band-limited log-mel grid, the
    #: critic's entire view of it (docs/09 §9.3). Deliberately **not** JSON: 736 floats per
    #: syllable would take `syllables.jsonl` from 26 MB to about 200 MB and make every load
    #: a JSON-parse of a matrix. `HarvestStore` writes these to a `patches.f16` sidecar in
    #: row order instead — 1.4 KB each, ~57 MB for a 40 k store, which is the cost docs/09
    #: budgeted. `None` on any store harvested before this field existed, and every consumer
    #: has to handle that: the critic is optional by construction (§9.4).
    mel_patch: np.ndarray | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe fields only — `mel_patch` is persisted as a binary sidecar."""
        d = asdict(self)
        d.pop("mel_patch", None)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SyllableObservation":
        return cls(
            **{
                k: v
                for k, v in d.items()
                if k in cls.__dataclass_fields__ and k != "mel_patch"
            }
        )


def _frames(x: np.ndarray, frame: int, hop: int) -> np.ndarray:
    if x.size < frame:
        return np.zeros((0, frame))
    starts = np.arange(0, x.size - frame + 1, hop)
    return np.stack([x[s : s + frame] for s in starts])


def envelope(x: np.ndarray) -> np.ndarray:
    """Frame RMS at ENV_HOP. The segmentation runs on this, not on the samples."""
    f = _frames(x, ENV_FRAME, ENV_HOP)
    return np.sqrt(np.mean(f * f, axis=1)) if f.size else np.zeros(0)


def _segments(env: np.ndarray, sample_rate: int) -> list[tuple[int, int]]:
    """Envelope -> [start, end) sample ranges, merged across short gaps."""
    if not env.size:
        return []
    threshold = max(ONSET_REL * float(env.max()), 1.0e-4)
    above = env > threshold
    spans: list[tuple[int, int]] = []
    start = -1
    for i, on in enumerate(above):
        if on and start < 0:
            start = i
        elif not on and start >= 0:
            spans.append((start, i))
            start = -1
    if start >= 0:
        spans.append((start, above.size))

    merge = MERGE_GAP_S * sample_rate / ENV_HOP
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a - merged[-1][1] <= merge:
            merged[-1][1] = b
        else:
            merged.append([a, b])

    out: list[tuple[int, int]] = []
    for a, b in merged:
        s0 = int(a * ENV_HOP)
        s1 = int(b * ENV_HOP + ENV_FRAME)
        dur = (s1 - s0) / sample_rate
        if MIN_SYLLABLE_S <= dur <= MAX_SYLLABLE_S:
            out.append((s0, s1))
    return out


def track_f0(seg: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    """(f0 per frame, spectral flatness per frame) by parabolic-interpolated peak.

    Birdsong is close to a pure tone far more often than speech is — that is the whole
    reason the tracking formant in 8.1 exists — so the spectral peak is a sound f0
    estimate here and costs one FFT per frame. Frames whose peak is outside the birdy
    band, or which are too flat to be tonal, are dropped rather than guessed at.
    """
    f = _frames(seg, F0_FRAME, F0_HOP)
    if not f.size:
        return np.zeros(0), np.zeros(0)
    window = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(F0_FRAME) / (F0_FRAME - 1))
    mag = np.abs(np.fft.rfft(f * window, axis=1))
    bin_hz = sample_rate / F0_FRAME

    lo = max(1, int(F0_MIN_HZ / bin_hz))
    hi = min(mag.shape[1] - 2, int(F0_MAX_HZ / bin_hz))
    band = mag[:, lo:hi]
    if not band.size:
        return np.zeros(0), np.zeros(0)
    k = band.argmax(axis=1) + lo

    rows = np.arange(mag.shape[0])
    left, centre, right = mag[rows, k - 1], mag[rows, k], mag[rows, k + 1]
    denom = left - 2.0 * centre + right
    shift = np.where(np.abs(denom) > 1e-12, 0.5 * (left - right) / np.where(denom == 0, 1e-12, denom), 0.0)
    f0 = (k + np.clip(shift, -0.5, 0.5)) * bin_hz

    flatness = np.exp(np.mean(np.log(mag + 1e-10), axis=1)) / (np.mean(mag, axis=1) + 1e-10)
    tonal = (centre > 4.0 * np.median(mag, axis=1)) & (f0 > F0_MIN_HZ) & (f0 < F0_MAX_HZ)
    return f0[tonal], flatness[tonal]


def measure_harmonics(
    seg: np.ndarray, sample_rate: int, n_harmonics: int = syrinx.HARMONIC_MAX
) -> tuple[list[float], float]:
    """Amplitude of each partial and the noise fraction, measured from the audio (§8.1b).

    Returns `([a1..aK] normalised so a1 = 1, noise_fraction)`.

    **Why per frame and not over the whole segment.** A syllable's f0 sweeps, so a single FFT
    of the whole segment smears every partial across a band and the harmonic structure is gone
    before it can be read. Instead the pitch is tracked per frame and the partials are sampled
    at `k * f0(t)` in that frame, so each measurement is taken where the partial actually is.
    The per-frame amplitudes are normalised by the fundamental *before* averaging — otherwise
    loud frames dominate and the result is a loudness profile rather than a spectral one — and
    combined with a median, because octave errors in the tracker are common and move a mean.

    The noise fraction is the share of in-band energy that sits *between* the partials: total
    magnitude minus what the harmonic peaks account for. That is the quantity `noise` models,
    and measuring it is what lets a rasp be fitted rather than searched for.
    """
    f = _frames(seg, F0_FRAME, F0_HOP)
    if not f.size:
        return [], 0.0
    window = 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(F0_FRAME) / (F0_FRAME - 1))
    mag = np.abs(np.fft.rfft(f * window, axis=1))
    bin_hz = sample_rate / F0_FRAME
    nyq_bin = mag.shape[1] - 2

    lo = max(1, int(F0_MIN_HZ / bin_hz))
    hi = min(nyq_bin, int(F0_MAX_HZ / bin_hz))
    if hi <= lo:
        return [], 0.0
    k0 = mag[:, lo:hi].argmax(axis=1) + lo
    rows = np.arange(mag.shape[0])
    tonal = mag[rows, k0] > 4.0 * np.median(mag, axis=1)
    if not np.any(tonal):
        return [], 0.0

    profiles: list[np.ndarray] = []
    noise_shares: list[float] = []
    for r in np.flatnonzero(tonal):
        f0_bin = float(k0[r])
        amps = np.zeros(n_harmonics)
        for k in range(1, n_harmonics + 1):
            centre = int(round(k * f0_bin))
            if centre >= nyq_bin:
                break
            # +/- 1 bin, because a swept partial does not sit exactly on a bin centre
            amps[k - 1] = float(mag[r, max(0, centre - 1) : centre + 2].max())
        if amps[0] <= 0.0:
            continue
        profiles.append(amps / amps[0])
        # Energy *between* the partials, as a share of the total.
        #
        # In power, and over the window's main lobe rather than a single bin: a Hann window
        # spreads a pure sinusoid over about four bins, so comparing single-bin peaks against
        # a full-band sum charges that leakage to "noise" and reports a clean tone as half
        # noise. Summing +/-2 bins per partial captures the lobe, and what is left over is
        # genuinely inharmonic.
        power = mag[r] * mag[r]
        total = float(power[lo:hi].sum()) or 1.0
        harmonic_power = 0.0
        for k in range(1, n_harmonics + 1):
            centre = int(round(k * f0_bin))
            if centre >= nyq_bin:
                break
            harmonic_power += float(power[max(0, centre - 2) : centre + 3].sum())
        noise_shares.append(float(np.clip(1.0 - harmonic_power / total, 0.0, 1.0)))

    if not profiles:
        return [], 0.0
    median = np.median(np.stack(profiles), axis=0)
    median[0] = 1.0
    out = [float(round(v, 4)) for v in median]
    while out and out[-1] < syrinx.HARMONIC_FLOOR:
        out.pop()
    return out, float(round(float(np.median(noise_shares)), 4))


def fit_contour(f0: np.ndarray, knots: int = CONTOUR_KNOTS) -> list[list[float]]:
    """f0 track -> [timeFraction, Hz] breakpoints, with redundant knots removed.

    The median within each window rather than the mean: an octave-jumped frame is a
    common tracking failure and it moves a mean a long way.
    """
    if f0.size == 0:
        return [[0.0, 3000.0]]
    n = min(knots, max(2, f0.size))
    edges = np.linspace(0, f0.size, n + 1).astype(int)
    pts: list[list[float]] = []
    for i in range(n):
        chunk = f0[edges[i] : max(edges[i] + 1, edges[i + 1])]
        t = 0.0 if n == 1 else i / (n - 1)
        pts.append([round(t, 4), round(float(np.median(chunk)), 1)])

    # drop knots the neighbours already predict, so a flat whistle is two points
    keep = [pts[0]]
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        span = c[0] - a[0]
        predicted = a[1] + (c[1] - a[1]) * ((b[0] - a[0]) / span) if span > 0 else b[1]
        if abs(b[1] - predicted) > COLLINEAR_TOL * max(predicted, 1.0):
            keep.append(b)
    keep.append(pts[-1])
    return keep


def _modulation(signal: np.ndarray, rate: float, lo: float, hi: float) -> tuple[float, float]:
    """Dominant modulation rate in [lo, hi] Hz and its depth, as a fraction of the mean."""
    n = signal.size
    if n < 8:
        return 0.0, 0.0
    centred = signal - signal.mean()
    spectrum = np.abs(np.fft.rfft(centred * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    band = (freqs >= lo) & (freqs <= hi)
    if not np.any(band) or not np.any(spectrum[band]):
        return 0.0, 0.0
    idx = np.flatnonzero(band)[int(np.argmax(spectrum[band]))]
    mean = float(np.mean(np.abs(signal))) or 1.0
    depth = float(2.0 * spectrum[idx] / (0.5 * n) / mean)
    return float(freqs[idx]), float(np.clip(depth, 0.0, 1.0))


def _timbre(flatness: float, harmonic: float) -> str:
    """The three classes 8.1 defines, from how noisy and how harmonic the segment is."""
    if flatness > 0.28:
        return "buzz"
    if flatness > 0.10 or harmonic > 0.35:
        return "reed"
    return "pure"


def extract_syllables(
    mono: np.ndarray,
    sample_rate: int,
    species_id: str,
    recording_id: str,
    max_seconds: float | None = None,
) -> list[SyllableObservation]:
    """Segment a recording and describe each syllable in syrinx parameters."""
    if max_seconds is not None:
        mono = mono[: int(max_seconds * sample_rate)]
    if mono.size < F0_FRAME:
        return []
    mono = peak_normalise(mono)
    env = envelope(mono)
    if not env.size:
        return []
    env_peak = float(env.max()) or 1.0

    out: list[SyllableObservation] = []
    previous_end = 0.0
    for order, (s0, s1) in enumerate(_segments(env, sample_rate)):
        if order >= MAX_PER_RECORDING:
            break
        seg = mono[s0:s1]
        f0, flatness = track_f0(seg, sample_rate)
        if f0.size < 2:
            continue

        seg_env = envelope(seg)
        if not seg_env.size:
            continue
        peak = float(seg_env.max()) or 1.0
        dur = seg.size / sample_rate

        # attack: to 90 % of the peak. hold: still loud three quarters of the way in.
        reached = np.flatnonzero(seg_env >= 0.9 * peak)
        attack = float(reached[0] * ENV_HOP / sample_rate) if reached.size else syrinx.DEFAULT_ATTACK
        tail = seg_env[int(0.75 * seg_env.size) :]
        hold = bool(tail.size and float(tail.mean()) > 0.7 * peak)

        am_rate, am_depth = _modulation(seg_env, sample_rate / ENV_HOP, 8.0, 200.0)
        vib_rate, vib_depth = _modulation(f0, sample_rate / F0_HOP, 3.0, 40.0)

        # harmonic ratio: energy above 1.6*f0 against energy around f0
        spectrum = np.abs(np.fft.rfft(seg * np.hanning(seg.size)))
        bins = np.fft.rfftfreq(seg.size, 1.0 / sample_rate)
        centre = float(np.median(f0))
        above = spectrum[bins > 1.6 * centre].sum()
        at = spectrum[(bins > 0.6 * centre) & (bins <= 1.6 * centre)].sum()
        harmonic = float(np.clip(above / (at + 1e-9), 0.0, 1.0))
        mean_flatness = float(np.mean(flatness)) if flatness.size else 0.0
        harmonics, noise_frac = measure_harmonics(seg, sample_rate)
        normalised = peak_normalise(seg)
        path = features.mel_path(normalised, sample_rate=sample_rate)
        # The critic's patch, taken here and only here: this is the last moment the audio
        # exists. `harvest.py` deletes the recording as soon as this function returns, and
        # nothing downstream can recover a spectrogram from the parameters.
        patch = features.mel_patch(normalised, sample_rate=sample_rate)

        start = s0 / sample_rate
        own = features.descriptor(normalised, sample_rate)
        out.append(
            SyllableObservation(
                species_id=species_id,
                recording_id=recording_id,
                order=order,
                start=round(start, 4),
                dur=round(dur, 4),
                level=round(float(np.clip(peak / env_peak, 0.35, 1.0)), 4),
                attack=round(float(np.clip(attack, 0.002, 0.12)), 4),
                hold=hold,
                contour=fit_contour(f0),
                am=round(am_rate, 2),
                am_depth=round(am_depth, 4),
                vib_rate=round(vib_rate, 2),
                vib_depth=round(min(vib_depth, 0.4), 4),
                harmonic=round(harmonic, 4),
                timbre=_timbre(mean_flatness, harmonic),
                flatness=round(mean_flatness, 5),
                gap_before=round(max(0.0, start - previous_end), 4),
                harmonics=harmonics,
                noise_frac=noise_frac,
                mel_path=[round(float(v), 3) for v in path.ravel()],
                mel_patch=patch.astype(np.float16),
                descriptor=(
                    [round(float(v), 5) for v in own]
                    if own is not None and np.all(np.isfinite(own))
                    else None
                ),
            )
        )
        previous_end = (s1 / sample_rate)
    return out


# --- fitting a repertoire ----------------------------------------------------------


def _observation_vector(o: SyllableObservation) -> np.ndarray:
    """What makes two syllables the same type: pitch shape, length, texture, rhythm.

    Seven numbers with hand-chosen weights, and the weights (`* 6.0`, `* 3.0`) were guesses.
    Everything downstream rests on this — the fitted repertoire, the measured grammar, the
    galaxy's clusters — which is why docs/09 §9.2b wants it replaced by something learned.
    It stays as the fallback, and as the baseline any learned basis has to beat.
    """
    hz = np.asarray([p[1] for p in o.contour], dtype=np.float64)
    t = np.asarray([p[0] for p in o.contour], dtype=np.float64)
    at = np.interp([0.0, 0.5, 1.0], t, np.log2(np.maximum(hz, 50.0)))
    return np.asarray(
        [
            at[0], at[1], at[2],
            np.log2(max(o.dur, 1e-3)),
            np.log1p(o.am) * (1.0 if o.am_depth > 0.15 else 0.0),
            o.flatness * 6.0,
            o.harmonic * 3.0,
        ]
    )


#: A callable turning observations into the space types are clustered in. `None` means the
#: seven hand-weighted numbers above; `critic.Critic.embed` composed with the patches is the
#: learned alternative of docs/09 §9.2b use 1. Typed as a plain callable on purpose, so
#: `learn.py` never imports torch and the critic stays an optional dependency (§9.4).
Embedder = Callable[[Sequence[SyllableObservation]], np.ndarray]


def typing_space(
    observations: Sequence[SyllableObservation], embedder: Embedder | None = None
) -> np.ndarray:
    """The standardised matrix that `fit_types` and `choose_k` cluster in.

    Both used to build this inline, and they have to agree: `choose_k` picking k in one space
    while `fit_types` clusters in another would make the silhouette that chose k a statement
    about a different geometry. One function, called by both.
    """
    if embedder is not None:
        x = np.asarray(embedder(observations), dtype=np.float64)
        if x.ndim != 2 or x.shape[0] != len(observations):
            raise ValueError(
                f"embedder returned {x.shape} for {len(observations)} observations; "
                f"expected ({len(observations)}, d)"
            )
    else:
        x = np.stack([_observation_vector(o) for o in observations])
    return (x - x.mean(axis=0)) / np.maximum(x.std(axis=0), 1e-6)


def critic_embedder(critic: Any, fallback_ok: bool = True) -> Embedder:
    """Wrap a trained critic as an `Embedder` over harvested observations.

    **This is the part of docs/09 that worked.** Swapping `_observation_vector`'s seven
    hand-weighted numbers for the critic's 32-d embedding, changing nothing else, moved species
    placement 26.6 % -> 32.9 %, own-type placement 63.0 % -> 63.9 % and median F0 error
    5.4 % -> 3.1 %, with the guardrail cosine held at 0.755 against 0.762 (docs/09 §9.7).
    Nothing regressed. The plan expected this to be the easy half and the realism objective to
    be the substance; it is the other way round.

    Observations with no patch cannot be embedded at all. Rather than drop them — which would
    silently shrink a species' repertoire and break the alignment between `observations` and
    the labels `learn_grammar` needs — they are given the mean embedding, which puts them at
    the centre of the space and lets KMeans assign them to whichever type is nearest overall.
    That is the honest behaviour for "no evidence", and `learn_species` reports how many.
    """

    def embed(observations: Sequence[SyllableObservation]) -> np.ndarray:
        have = [i for i, o in enumerate(observations) if o.mel_patch is not None]
        if not have:
            raise ValueError("no observation carries a mel_patch — cannot embed")
        if len(have) < len(observations) and not fallback_ok:
            raise ValueError(
                f"only {len(have)} of {len(observations)} observations carry a mel_patch"
            )
        patches = np.stack([
            np.asarray(observations[i].mel_patch, dtype=np.float32) for i in have
        ])
        z = np.asarray(critic.embed(patches), dtype=np.float64)
        out = np.repeat(z.mean(axis=0, keepdims=True), len(observations), axis=0)
        out[have] = z
        return out

    return embed


class RealismTerm:
    """The critic's realism logit, blended into `_score` as docs/09 §9.3 step 5 specifies.

    `score = (1 - w) * cosine + w * realism`. **Keeping the cosine term is a guardrail, not
    politeness**: it is a metric the critic cannot game, so a fit that improves the blend
    while collapsing the cosine is visibly cheating rather than invisibly cheating. At `w = 0`
    this class is a no-op and the objective is bit-identical to the one that shipped before it
    existed.

    **The sweep was run and it refuted the idea. `w = 0` is the default and should stay there.**
    Measured on `out/harvest-gan` with the typing held fixed (docs/09 §9.7), every metric falls
    monotonically as `w` rises — species placement 26.6 / 27.2 / 23.7 / 17.3 % at
    `w = 0 / 0.25 / 0.5 / 1.0`, with the guardrail cosine going 0.762 / 0.686 / 0.655 / 0.335.
    The collapse at `w = 1` is precisely the failure §9.5 listed as "the fit games the critic",
    and the retained cosine is the only reason it was visible rather than a silent success.

    This is not a critic that failed to train: the same network reads AUC 0.990 telling real
    recordings from our resyntheses *on species it never saw*. Being able to separate two
    distributions is not the same as having a gradient that points from one to the other, and
    coordinate descent needs the second. The class is kept because the sweep should be
    reproducible and because the same critic earns its place elsewhere — see `critic_embedder`,
    which is a clean win on the same store.

    The critic is duck-typed (`realism_unit`), so nothing here imports torch.
    """

    def __init__(self, critic: Any, weight: float, sample_rate: int = features.SAMPLE_RATE):
        self.critic = critic
        self.weight = float(np.clip(weight, 0.0, 1.0))
        self.sample_rate = sample_rate
        self.calls = 0

    def blend(self, cosine: float, audio: np.ndarray) -> float:
        if self.weight <= 0.0 or self.critic is None:
            return cosine
        patch = features.mel_patch(audio, sample_rate=self.sample_rate)
        self.calls += 1
        # `realism_unit` and not `realism`: the raw logit is unbounded and the cosine lives in
        # [-1, 1], so mixing them directly would let the weight mean something different at
        # every point on the surface.
        realism = float(np.asarray(self.critic.realism_unit(patch)).ravel()[0])
        return (1.0 - self.weight) * cosine + self.weight * realism


def _median_contour(members: Sequence[SyllableObservation]) -> list[list[float]]:
    """Elementwise median over the members, resampled onto a shared time grid."""
    grid = np.linspace(0.0, 1.0, CONTOUR_KNOTS)
    stacked = []
    for o in members:
        t = np.asarray([p[0] for p in o.contour], dtype=np.float64)
        hz = np.asarray([p[1] for p in o.contour], dtype=np.float64)
        stacked.append(np.interp(grid, t, np.log2(np.maximum(hz, 50.0))))
    median = np.median(np.stack(stacked), axis=0)
    return fit_contour_from_grid(grid, 2.0**median)


def fit_contour_from_grid(grid: np.ndarray, hz: np.ndarray) -> list[list[float]]:
    pts = [[round(float(t), 4), round(float(f), 1)] for t, f in zip(grid, hz)]
    keep = [pts[0]]
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        span = c[0] - a[0]
        predicted = a[1] + (c[1] - a[1]) * ((b[0] - a[0]) / span) if span > 0 else b[1]
        if abs(b[1] - predicted) > COLLINEAR_TOL * max(predicted, 1.0):
            keep.append(b)
    keep.append(pts[-1])
    return keep


def _median_syllable(members: Sequence[SyllableObservation], type_id: str) -> dict[str, Any]:
    """The base syllable dict of one cluster's median: the fields every fitted type carries.

    Factored out of `fit_types` so the label-free path (`learn_unlabelled`) fits its
    candidate types with exactly this median logic rather than a copy of it. What is NOT
    here is deliberate: the conditional AM/vibrato extras `fit_types` adds on top, and
    everything the gesture inversion writes. A `U*` type is never inverted — there is no
    species reference to judge it against — so its syllable is this dict and only this.
    """
    return {
        "id": type_id,
        "label": "",  # filled in once the types are ordered by pitch
        "function": "",
        "confidence": "unlabelled",
        "refs": [],
        "dur": round(float(np.median([o.dur for o in members])), 4),
        "level": round(float(np.median([o.level for o in members])), 3),
        "timbre": Counter(o.timbre for o in members).most_common(1)[0][0],
        "contour": _median_contour(members),
        "attack": round(float(np.median([o.attack for o in members])), 4),
        "hold": bool(np.mean([o.hold for o in members]) > 0.5),
        "harmonic": round(float(np.median([o.harmonic for o in members])), 3),
    }


@dataclass
class LearnedType:
    id: str
    members: list[SyllableObservation] = field(default_factory=list)
    syllable: dict[str, Any] = field(default_factory=dict)
    resynthesis_cosine: float = 0.0
    f0_error_percent: float = 0.0
    #: Best cosine the resynthesis scored against a *different* type of the same bird.
    #: A syllable is only reproduced in any useful sense if this is the lower number.
    rival_cosine: float = 0.0
    nearest_own: bool = False


def fit_types(
    observations: Sequence[SyllableObservation],
    k: int,
    seed: int = 0,
    previous: dict[str, dict[str, Any]] | None = None,
    embedder: Embedder | None = None,
) -> list[LearnedType]:
    """Cluster one species' observations and take the median of each cluster.

    `previous` is the species' fitted syllables from the last run, keyed by id, so a refit
    can inherit its ids instead of renumbering — see `assign_ids`.

    `embedder` chooses the space the clustering happens in: `None` for the seven hand-weighted
    numbers of `_observation_vector`, or a learned one from `critic_embedder`. The *members* of
    a type change with the space, so the median contour, duration and timbre all change with
    it too — this parameter decides what a "syllable type" means.
    """
    x = typing_space(observations, embedder)
    k = max(1, min(k, len(observations)))
    labels = (
        KMeans(n_clusters=k, n_init=10, random_state=seed).fit(x).labels_
        if k > 1
        else np.zeros(len(observations), dtype=int)
    )

    types: list[LearnedType] = []
    for c in range(k):
        members = [o for o, lab in zip(observations, labels) if lab == c]
        if not members:
            continue
        # a type is named by rank so the ids are stable for a given corpus and seed
        t = LearnedType(id=f"L{c:02d}", members=members)
        t.syllable = _median_syllable(members, t.id)
        am_depths = [o.am_depth for o in members]
        vib_depths = [o.vib_depth for o in members]
        # **The measured harmonic spectrum is deliberately NOT written into the syllable.**
        #
        # `measure_harmonics` works — validated against synthetic signals it recovers a
        # 1 / 0.5 / 0.25 series exactly and reads a pure tone as a single partial with zero
        # noise — and the observations carry it, so it is available for analysis. But feeding
        # it to the fit made the fit *worse*. Ablated over five acoustically distinct species
        # (wren, tawny owl, cuckoo, blackbird, great tit; 1562 syllables), median cosine went
        # 0.776 -> 0.768 and correct-species placement 61.7 % -> 55.6 %.
        #
        # The reason is in the measurement itself: real syllables here resolve to a mean of
        # **2.2 partials**. Birdsong is genuinely near-sinusoidal — that is the whole point of
        # the tract in 8.1 — so a measured partial series carries almost nothing the single
        # `harmonic` scalar did not already carry, while `harmonics` supersedes that scalar and
        # so costs the search a degree of freedom it had been using productively.
        #
        # Recorded here rather than deleted because the hypothesis was reasonable and the
        # refutation is the useful part: the missing evidence is not the harmonic structure.
        # Whatever is still wrong lives in the noise residual, the time envelope of the
        # spectrum, or somewhere that is not the partial amplitudes at all.
        if float(np.median(am_depths)) > 0.15:
            t.syllable["am"] = round(float(np.median([o.am for o in members])), 2)
            t.syllable["amDepth"] = round(float(np.median(am_depths)), 3)
        if float(np.median(vib_depths)) > 0.04:
            t.syllable["vib"] = {
                "rate": round(float(np.median([o.vib_rate for o in members])), 2),
                "depth": round(float(np.median(vib_depths)), 3),
            }
        types.append(t)

    # order by median pitch so L00 is the lowest type, which makes the ids readable
    types.sort(key=lambda t: syrinx.f0_reference(t.syllable["contour"]))
    assign_ids(types, previous)
    return types


def _id_key(syllable: dict[str, Any]) -> tuple[float, float]:
    """Where a type sits, for matching one fit's types against another's."""
    return (
        math.log2(max(20.0, syrinx.f0_reference(syllable["contour"]))),
        math.log2(max(0.005, float(syllable.get("dur", 0.1)))),
    )


# How far a refitted type may move and still be considered the same type. In octaves of
# pitch and octaves of duration, added: a third of an octave in each is generous for a
# median that has absorbed a few more recordings and tight enough that two genuinely
# different calls of one bird cannot swap identities.
ID_MATCH_TOLERANCE = 0.66


def assign_ids(
    types: list[LearnedType],
    previous: dict[str, dict[str, Any]] | None,
    prefix: str = "L",
) -> None:
    """Give each fitted type an id, keeping the one it had in the previous fit.

    **An id that changes meaning between runs is worse than no id.** These were assigned by
    rank: sort the types by pitch, number them `L00` upward. Refit after another twenty
    recordings, one type's median moves, the order changes, and every id from there on names
    a different syllable than it did an hour ago — while the grammar written beside them, the
    trajectory paths built from them and the clusters labelled with them all still refer to
    the old meaning. The visible symptom is a bird singing something audibly new that lights
    nothing in the galaxy, because the id it sang under belongs to a cluster fitted to a
    different sound.

    So a refit inherits: each new type takes the id of the nearest type in the previous fit,
    matched on pitch and duration and only within `ID_MATCH_TOLERANCE`, greedily from the
    closest pair outward. Types with no acceptable match are genuinely new and get fresh ids
    after the highest one already used, so an id is never silently recycled onto a different
    sound. With no previous fit it falls back to numbering by rank, which is where all of
    these came from.

    `prefix` is `L` for a species' learned types and `U` for the unlabelled pool's
    candidates (`learn_unlabelled`), so the two namespaces can never collide inside one
    inventory.
    """
    if previous:
        pairs: list[tuple[float, int, str]] = []
        for i, t in enumerate(types):
            f0_new, dur_new = _id_key(t.syllable)
            for pid, syl in previous.items():
                f0_old, dur_old = _id_key(syl)
                cost = abs(f0_new - f0_old) + abs(dur_new - dur_old)
                if cost <= ID_MATCH_TOLERANCE:
                    pairs.append((cost, i, pid))
        pairs.sort()
        taken_new: set[int] = set()
        taken_old: set[str] = set()
        assigned: dict[int, str] = {}
        for cost, i, pid in pairs:
            if i in taken_new or pid in taken_old:
                continue
            assigned[i] = pid
            taken_new.add(i)
            taken_old.add(pid)
    else:
        assigned = {}
        taken_old = set()

    used = {int(pid[1:]) for pid in previous or {} if pid[1:].isdigit()}
    used |= {int(pid[1:]) for pid in assigned.values() if pid[1:].isdigit()}
    next_free = (max(used) + 1) if used else 0
    for i, t in enumerate(types):
        if i in assigned:
            new_id = assigned[i]
        elif previous:
            new_id = f"{prefix}{next_free:02d}"
            next_free += 1
        else:
            new_id = f"{prefix}{i:02d}"
        t.id = new_id
        t.syllable["id"] = new_id
        t.syllable["label"] = (
            f"learned {new_id} · {syrinx.f0_reference(t.syllable['contour']):.0f} Hz · "
            f"{t.syllable['dur'] * 1000:.0f} ms"
        )


# --- can the model actually sing it? -----------------------------------------------


def population_frame(
    observations: Sequence[SyllableObservation],
) -> tuple[np.ndarray, np.ndarray] | None:
    """Mean and sd of the harvested syllables' own descriptors — the frame to judge in.

    Not the corpus statistics from `feature-space.json`, and this is the whole point.
    Those are measured over a *synthetic* build, so every field recording sits far from
    that mean in the same direction — the direction of "was recorded outdoors". Cosines
    taken there run at 0.99 between two syllables that share nothing but a hedgerow: on
    this store, a real syllable scored 0.995 against its own type and 0.991 against a
    different one, which is a measurement of nothing.

    Centred on the harvested population instead, the same comparison separates: 0.78
    within a type against 0.49 across types. That is a frame in which a claim about a
    resynthesis can be either true or false.
    """
    rows = [np.asarray(o.descriptor, dtype=float) for o in observations if o.descriptor]
    if len(rows) < 2:
        return None
    d = np.stack(rows)
    return d.mean(axis=0), np.maximum(d.std(axis=0), 1.0e-6)


def _unit(v: np.ndarray) -> np.ndarray:
    return v / max(float(np.linalg.norm(v)), 1.0e-12)


def _unit_rows(z: np.ndarray) -> np.ndarray:
    return z / np.maximum(np.linalg.norm(z, axis=1, keepdims=True), 1.0e-12)


def render_and_measure(
    t: LearnedType,
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    sample_rate: int = features.SAMPLE_RATE,
) -> np.ndarray | None:
    """Render the fitted syllable, record its F0 error, and return where it landed.

    The returned vector is the resynthesis in the frame above, ready to be compared
    with the real types. The F0 error is independent of all of that: it asks only
    whether the oscillator reached the pitch the contour asked for, and the two fail
    separately — a buzz whose pitch is right but whose texture is not, or a clean
    whistle a semitone flat.
    """
    audio = peak_normalise(
        render_syllable(t.syllable, sample_rate=sample_rate, calibration=calibration)
    )
    requested = syrinx.f0_reference(t.syllable["contour"])
    # Spectral peak with octave correction, not zero crossings: see `measure_f0_robust`.
    # A syllable fitted to low beta is pulse-like and crosses zero several times per period,
    # which the crossing counter reports as a pitch error the synthesis does not have.
    measured = syrinx.measure_f0_robust(audio, requested)
    if requested > 0:
        t.f0_error_percent = round(100.0 * (measured - requested) / requested, 2)

    descriptor = features.descriptor(audio, sample_rate)
    if descriptor is None:
        return None
    if frame is None:
        return _unit(descriptor)
    mean, std = frame
    return _unit(features.standardise(descriptor, mean, std))


def _score(
    syllable: dict[str, Any],
    reference: np.ndarray,
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    sample_rate: int,
    realism: "RealismTerm | None" = None,
) -> float:
    """How good this syllable's resynthesis is: the 28-d cosine, optionally blended.

    Without `realism` this is exactly what it always was — the cosine between the resynthesis
    and the real audio the type stands for. With it, the learned critic gets a share `w` of
    the objective (docs/09 §9.3 step 5). The cosine never goes away entirely, so there is
    always one term the critic cannot game.
    """
    audio = peak_normalise(
        render_syllable(syllable, sample_rate=sample_rate, calibration=calibration)
    )
    d = features.descriptor(audio, sample_rate)
    if d is None:
        return -1.0
    if frame is not None:
        d = features.standardise(d, frame[0], frame[1])
    cosine = float(_unit(d) @ reference)
    return cosine if realism is None else realism.blend(cosine, audio)


#: What the search may move, and to where. The pitch *contour* is deliberately absent:
#: the F0 tracker already gets it to about 1 %, and letting a texture search move pitch
#: would trade the one thing the model does well for the one it does badly. Duration stays
#: measured for the same reason. Everything here is a property of the gesture rather than
#: of the note — how hard the bird was blowing, how the tract was shaped, whether both
#: sides of the syrinx were driven — and those are exactly what a median over a cluster
#: cannot recover, because they vary within a type while the pitch does not.
_SEARCH_AXES: list[tuple[str, list[Any]]] = [
    # `gammaScale` goes first because it is the axis with the most leverage and the others
    # are conditioned on it: it decides how harmonically rich the *source* is, and there is
    # no point tuning a tract before there is something for the tract to shape. See the note
    # on `Syllable.gamma_scale` — the 8.1 gamma rule pins every syllable near beta = 1, and
    # measured over this harvest that put 100 % of the resynthesis in the tonal regime
    # against 15.6 % of the real syllables being spectrally rich.
    ("gammaScale", [0.5, 1.0, 1.5, 2.0, 3.0, 4.5, 6.0]),
    ("timbre", ["pure", "reed", "buzz"]),
    ("tractQ", [0.0, 3.0, 6.0, 12.0, 20.0, 30.0]),
    ("level", [0.3, 0.45, 0.6, 0.75, 0.9, 1.05, 1.2, 1.35]),
    ("harmonic", [0.0, 0.1, 0.2, 0.35, 0.5, 0.7, 0.9]),
    # The tracheal comb is deliberately **not** here. It is fitted once per species by
    # `fit_species_trachea`, because a trachea is a property of the bird and not of the note.
    ("noise", [0.0, 0.05, 0.12, 0.25, 0.4, 0.6, 0.85]),
    ("rough", [0.0, 0.08, 0.2, 0.4, 0.65]),
    ("amDepth", [0.0, 0.15, 0.3, 0.45, 0.6, 0.8]),
    ("am", [12.0, 25.0, 45.0, 80.0, 140.0]),
    ("attack", [0.004, 0.008, 0.016, 0.03, 0.06]),
    ("hold", [False, True]),
    ("two", [False, True]),
    ("vibDepth", [0.0, 0.01, 0.025, 0.05, 0.09]),
    ("vibRate", [4.0, 8.0, 14.0, 22.0, 34.0]),
]
INVERT_PASSES = 3


def _with(syllable: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    """A copy of the syllable with one axis moved. `vib` is nested, so it needs a case."""
    trial = dict(syllable)
    if key in ("vibDepth", "vibRate"):
        vib = dict(trial.get("vib") or {"rate": 12.0, "depth": 0.0})
        vib["depth" if key == "vibDepth" else "rate"] = value
        if vib["depth"] <= 0.0:
            trial.pop("vib", None)
        else:
            trial["vib"] = vib
        return trial
    trial[key] = value
    # An AM depth with no rate is silent, and a rate with no depth is inaudible.
    if key == "amDepth" and value and not trial.get("am"):
        trial["am"] = 30.0
    if key == "am" and not trial.get("amDepth"):
        trial["amDepth"] = 0.3
    return trial


def _axis_value(syllable: dict[str, Any], key: str) -> Any:
    if key == "vibDepth":
        return (syllable.get("vib") or {}).get("depth", 0.0)
    if key == "vibRate":
        return (syllable.get("vib") or {}).get("rate", 12.0)
    if key == "gammaScale":
        return syllable.get("gammaScale", 1.0)
    if key == "tractQ":
        return syllable.get("tractQ", 0.0)
    if key in ("noise", "rough"):
        return syllable.get(key, 0.0)
    return syllable.get(key)


# --- one trachea per bird ----------------------------------------------------------

#: Search range for the measured first resonance, in Hz. A range and not a list of values:
#: `measure_trachea_f1` scans it finely against the species' own spectrum, so a bird nobody
#: has seen before gets its trachea measured rather than matched to a table. The bounds are
#: physical — a stopped tube resonating below 500 Hz would be longer than any bird in this
#: corpus, and above ~4.5 kHz the second partial has already left the 12 kHz tract roll-off.
TRACHEA_F1_LO, TRACHEA_F1_HI = 600.0, 6000.0
TRACHEA_F1_STEPS = 96
#: Bands the envelope is smoothed over to remove the overall spectral tilt. Without this the
#: comb score is dominated by "the spectrum is loudest at the low end", which is true of every
#: recording and says nothing about any bird.
TRACHEA_DETREND_BANDS = 7
TRACHEA_GAIN_GRID = [0.15, 0.3, 0.6, 1.0]
#: Types the comb is fitted over. It is one shared quantity, so the best-evidenced dozen
#: estimate it as well as sixty do and at a fifth of the cost.
TRACHEA_FIT_TYPES = 12


def measure_trachea_f1(observations: Sequence[SyllableObservation]) -> float:
    """Measure the bird's first tracheal resonance from its own recordings, in Hz.

    Derived, not looked up: nothing here knows which species it is being handed, so a species
    discovered an hour ago is measured on the same footing as one that has been in the
    inventory since the start. There is no table of birds to keep in step with the harvest.

    How it works. Average the per-syllable MFCC means over every observation of the species
    and invert them to a 26-band log spectral envelope (`features.mel_envelope`). Those
    syllables span many recordings and a wide range of f0, so anything that follows pitch
    averages away and anything fixed in Hz survives — the resonance is what is left standing.
    Detrend to remove the overall spectral tilt, then score a fine grid of candidate `f1` by
    how much envelope energy sits at the odd harmonics `(2n-1)*f1` a stopped tube would put
    there, weighted `1/(2n-1)` as the measured combs are. The best-scoring candidate wins.

    Returns 0.0 when there is nothing to measure from.

    **Known limit, and why it is safe.** For a bird whose f0 barely moves — a cuckoo sings two
    notes — the average spectrum's largest peak *is* the fundamental, so the scan can lock onto
    f0 instead of onto a resonance. There is no way to tell those apart from a spectrum alone,
    and coincidence is not even a fault: cardinals sing near 2 kHz and their first tracheal
    resonance is also near 2 kHz. This is why the frequency measured here is never trusted on
    its own — `fit_species_trachea` still has to show that the comb *improves the resynthesis*
    before any of it ships, and a bird whose comb does not earn its place keeps none. The
    measurement proposes; the resynthesis decides.
    """
    rows = [
        np.asarray(o.descriptor, dtype=np.float64)[: features.N_MFCC]
        for o in observations
        if o.descriptor
    ]
    if len(rows) < 2:
        return 0.0
    envelope = features.mel_envelope(np.mean(np.stack(rows), axis=0))
    hz = features.mel_centres_hz()

    # detrend: subtract a moving average, so what is scored is the peaks and not the tilt
    k = TRACHEA_DETREND_BANDS
    pad = np.pad(envelope, (k // 2, k // 2), mode="edge")
    smooth = np.convolve(pad, np.ones(k) / k, mode="valid")[: envelope.size]
    peaks = envelope - smooth

    best_f1, best = 0.0, -np.inf
    for f1 in np.geomspace(TRACHEA_F1_LO, TRACHEA_F1_HI, TRACHEA_F1_STEPS):
        score, weight = 0.0, 0.0
        for n in range(1, syrinx.TRACHEA_PARTIALS + 1):
            f = (2 * n - 1) * f1
            if f > syrinx.TRACT_LP_HZ or f > hz[-1]:
                break
            w = 1.0 / (2 * n - 1)
            score += w * float(np.interp(f, hz, peaks))
            weight += w
        if weight <= 0.0:
            continue
        score /= weight
        if score > best:
            best, best_f1 = score, float(f1)
    return best_f1 if best > 0.0 else 0.0


#: Reflection coefficients tried at the beak end. Low r is a weakly resonant tract (the
#: released zebra-finch parameters use 0.1), high r a strongly resonant one (the sparrow set
#: uses 0.65; Sitt 2010 uses 0.9). It is the depth-of-colour control and worth searching.
TUBE_R_GRID = [0.3, 0.5, 0.7, 0.85]
#: Multipliers on the length implied by the measured resonance, in case the measurement landed
#: on a different partial or on the fundamental (see `measure_trachea_f1`).
TUBE_LEN_SCALES = [0.8, 1.0, 1.25]
TUBE_FIT_TYPES = 8


def fit_species_tube(
    fitted: Sequence[LearnedType],
    real: Sequence[np.ndarray | None],
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    f1_hz: float,
    sample_rate: int = features.SAMPLE_RATE,
    realism: "RealismTerm | None" = None,
) -> tuple[float, float]:
    """One stopped-tube waveguide for the whole bird: returns `(length_cm, r)` or `(0, 0)`.

    The length is not searched from nothing — it comes straight out of the resonance already
    measured from the species' own spectra, since a stopped tube's first peak is `c / 4L`. So
    `measure_trachea_f1` and this function are the same measurement expressed two ways, and
    what is left to decide is how strongly the tube resonates (`r`) plus a small correction on
    the length in case the measurement locked onto the wrong partial.

    Replaces the f0-tracking band entirely (§8.1c). "No tube" is the incumbent, so a species
    the waveguide does not help keeps the tracking tract.

    **Scored against the species, not against each type**, and that distinction decides the
    result. A tube belongs to the bird: one length shared by every syllable it sings. Judged
    per type it loses, because a per-type reference rewards whatever fits that one call and the
    tracking band can always chase a single call more closely than a fixed tract can. Judged
    against where the species' audio sits as a whole — which is the question a listener asks,
    and the metric that was failing — it wins. Measured on five species, fitting against the
    species reference took correct-species placement from 61.7 % to 67.9 % while also improving
    both the cosine and the spectral-trajectory distance; fitting the same tube per type left
    the 22-species figure unchanged at ~23 %.
    """
    if f1_hz <= 0.0:
        return 0.0, 0.0
    order = sorted(range(len(fitted)), key=lambda i: -len(fitted[i].members))
    idx = [i for i in order if real[i] is not None][:TUBE_FIT_TYPES]
    if not idx:
        return 0.0, 0.0
    base_len = syrinx.SOUND_SPEED_CM_S / (4.0 * f1_hz)

    # one species-level reference: where this bird's audio sits, averaged over its types
    stacked = np.stack([real[i] for i in idx])
    species_ref = stacked.mean(axis=0)
    species_ref = species_ref / max(float(np.linalg.norm(species_ref)), 1.0e-12)

    def mean_score(length: float, r: float) -> float:
        total = 0.0
        for i in idx:
            syl = dict(fitted[i].syllable)
            if length > 0.0:
                syl["tube"] = [length, r]
                syl["formants"] = [[round(f1_hz, 1), syrinx.TRACHEA_Q, 1.0]]
            else:
                syl.pop("tube", None)
                syl.pop("formants", None)
            total += _score(syl, species_ref, calibration, frame, sample_rate, realism)
        return total / len(idx)

    best_len, best_r = 0.0, 0.0
    best = mean_score(0.0, 0.0)
    for scale in TUBE_LEN_SCALES:
        length = float(np.clip(base_len * scale, syrinx.TUBE_LEN_MIN, syrinx.TUBE_LEN_MAX))
        for r in TUBE_R_GRID:
            score = mean_score(length, r)
            if score > best + 1.0e-4:
                best, best_len, best_r = score, length, r
    return best_len, best_r


def fit_species_trachea(
    fitted: Sequence[LearnedType],
    real: Sequence[np.ndarray | None],
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    f1_hz: float,
    sample_rate: int = features.SAMPLE_RATE,
    realism: "RealismTerm | None" = None,
) -> tuple[float, float]:
    """One absolute tracheal comb for the whole bird. Returns `(f1_hz, gain)`, or `(0, 0)`.

    **This is fitted per species, and that is the entire point.** The first version searched
    it per syllable with `f1` as a multiple of that syllable's own pitch, which measured well
    per type and did nothing for what the ear actually complains about: with the comb tied to
    pitch, two species singing at the same pitch get the same resonances, so no species
    signature ever forms. Cross-species placement stayed at 24 % while within-type cosine ran
    to 0.78 — the syllables were individually well fitted and collectively interchangeable.

    A trachea is a tube of fixed length closed at the syrinx. Its resonances belong to the
    bird, not to the note, so one frequency is shared by every syllable that bird sings and
    every syllable is coloured the same way. That is what a listener uses to tell two birds
    apart, and it costs one float per species rather than nine per syllable.

    `f1_hz` is *measured* from the species' own spectra by `measure_trachea_f1`, so this
    function only decides how loudly the comb should sound — a two-stage split that matches
    what each stage can actually know. Where the resonance sits is a fact about the recordings
    and is read off them directly; how much of it survives into the mix depends on everything
    else in the chain, so it is settled by resynthesis, against the same cosine the
    verification reports.

    The objective is the *mean* cosine over the species' types, because a shared parameter has
    to earn its place across the repertoire rather than on any one call. `(0, 0)` — comb off —
    is the incumbent, so a bird whose recordings show no tracheal colour keeps none.
    """
    if f1_hz <= 0.0:
        return 0.0, 0.0
    order = sorted(range(len(fitted)), key=lambda i: -len(fitted[i].members))
    idx = [i for i in order if real[i] is not None][:TRACHEA_FIT_TYPES]
    if not idx:
        return 0.0, 0.0

    def mean_score(f1: float, gain: float) -> float:
        comb = syrinx.tracheal_comb(f1, gain) if gain > 0.0 else []
        total = 0.0
        for i in idx:
            syl = dict(fitted[i].syllable)
            if comb:
                syl["formants"] = comb
            else:
                syl.pop("formants", None)
            total += _score(syl, real[i], calibration, frame, sample_rate, realism)
        return total / len(idx)

    best_gain = 0.0
    best = mean_score(0.0, 0.0)
    for gain in TRACHEA_GAIN_GRID:
        score = mean_score(f1_hz, gain)
        if score > best + 1.0e-4:
            best, best_gain = score, gain
    return (f1_hz, best_gain) if best_gain > 0.0 else (0.0, 0.0)


def invert_gestures(
    t: LearnedType,
    reference: np.ndarray,
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    sample_rate: int = features.SAMPLE_RATE,
    passes: int = INVERT_PASSES,
    realism: "RealismTerm | None" = None,
) -> tuple[float, float]:
    """Search the fitted syllable towards the audio it was fitted to. Returns (before, after).

    This is the cheap end of the inversion the literature describes (Boari et al. 2015,
    `docs/04-synthetic-bird-voices.md` §4.2): rather than solving for the pressure and
    tension gestures directly, it renders candidates through the same oscillator the app
    uses and keeps whichever lands closest to the real syllable in the 28-d space. The
    objective is therefore exactly the number the verification reports, which is the
    point — the median that came out of the clustering is a description of the cluster,
    not an attempt to sound like it, and nothing before this ever asked the model to try.

    Coordinate descent over ten axes, three passes: a couple of hundred renders per type,
    against the tens of thousands a full grid would need for the same answer on a surface
    this smooth. It cannot escape a bad basin, and it does not have to — it starts from
    the measured values and only ever moves on an improvement, so the worst case is that
    it stays exactly where the median put it.
    """
    before = _score(t.syllable, reference, calibration, frame, sample_rate, realism)
    best = before
    for _ in range(max(1, passes)):
        improved = False
        for key, candidates in _SEARCH_AXES:
            current = _axis_value(t.syllable, key)
            for value in candidates:
                if value == current:
                    continue
                trial = _with(t.syllable, key, value)
                score = _score(trial, reference, calibration, frame, sample_rate, realism)
                if score > best + 1.0e-4:
                    best = score
                    t.syllable = trial
                    current = value
                    improved = True
        if not improved:
            break
    return before, best


# --- syntax ------------------------------------------------------------------------


def learn_grammar(
    observations: Sequence[SyllableObservation], type_of: dict[int, str]
) -> dict[str, Any]:
    """First-order transitions between syllable types, within each recording.

    `type_of` maps an observation's position in `observations` to its learned type id.
    Transitions across a gap longer than a second are treated as the end of a bout
    rather than as a transition, or every pause in a recording would become a
    (spurious) link between two unrelated phrases.
    """
    by_recording: dict[str, list[tuple[int, SyllableObservation]]] = defaultdict(list)
    for i, o in enumerate(observations):
        by_recording[o.recording_id].append((i, o))

    starts: Counter[str] = Counter()
    transitions: dict[str, Counter[str]] = defaultdict(Counter)
    for items in by_recording.values():
        items.sort(key=lambda pair: pair[1].order)
        previous: str | None = None
        for i, o in items:
            current = type_of.get(i)
            if current is None:
                continue
            if previous is None or o.gap_before > 1.0:
                if previous is not None:
                    transitions[previous][END] += 1
                starts[current] += 1
            else:
                transitions[previous][current] += 1
            previous = current
        if previous is not None:
            transitions[previous][END] += 1

    def normalise(counts: Counter[str]) -> dict[str, float]:
        kept = {k: v for k, v in counts.items() if v >= GRAMMAR_MIN_COUNT} or dict(counts)
        total = sum(kept.values()) or 1
        return {k: round(v / total, 4) for k, v in sorted(kept.items(), key=lambda kv: -kv[1])}

    return {
        "start": [k for k, _ in starts.most_common(4)],
        "transitions": {k: normalise(v) for k, v in sorted(transitions.items())},
    }


# --- syntax mining: chunks ------------------------------------------------------------

#: A chunk must occur at least this often to be reported at all. Three is the floor at
#: which "repeated" means anything; anything rarer is indistinguishable from chance
#: co-occurrence at these corpus sizes.
CHUNK_MIN_COUNT = 3
#: Longest chunk mined. Six syllables covers the documented cases — the chickadee's
#: A→B→C→D ordering is four (docs/03 §3.2) — and longer exact repeats essentially do not
#: occur in a 47k-syllable corpus.
CHUNK_MAX_LEN = 6
#: How many chunks a grammar carries, ranked by count. The tail past fifty is rare
#: n-grams that say nothing the transition table does not already say.
CHUNK_TOP = 50
#: Pseudocount added to the baseline's *expected* occurrences before the ratio is
#: taken. A pmi built on an expectation of one or two occurrences is prior noise, not
#: signal — under the permutation null, length-5 candidates at counts of five to eight
#: were reporting three bits of surprise on expected counts below two. Add-four is the
#: standard small-count guard, and measured on this store it is what returns the
#: control's yield to zero without touching the count-~100 motifs.
CHUNK_PSEUDOCOUNT = 4.0
#: The evidence gate: a chunk's (smoothed) pmi must also clear its own sampling noise,
#: not merely zero. pmi is estimated from the same counts it scores, so the best of
#: thousands of null candidates lands positive by selection. The standard error of the
#: estimate is ~1.44/√count bits, so pmi·√count ≥ 6 is roughly four standard errors
#: from zero, and it sits past the permutation control's measured tail (≈ 4.6 here).
CHUNK_MIN_EVIDENCE = 6.0


def type_sequences(
    observations: Sequence[SyllableObservation],
    typing: Sequence[dict[str, Any]],
) -> list[tuple[str, list[str]]]:
    """Per-recording type-id sequences, one per bout: `(species_id, [typeId, ...])`.

    The keyless view of `bout_sequences`, which see: rebuilt from the store's
    observations and the fit's membership rows — the same two inputs `learn_grammar`
    sees, under the same two rules, so a chunk mined over these is a chunk of the
    grammar's own strings: order within a recording is meaningful and across recordings
    it is not (sequences are never concatenated), and a gap over a second breaks a bout.
    Observations with no type id are skipped without breaking the bout, exactly as
    `learn_grammar` skips them.
    """
    return [(species_id, seq) for species_id, _, seq in bout_sequences(observations, typing)]


def mine_chunks(
    sequences: Iterable[tuple[str, Sequence[str]]],
    min_count: int = CHUNK_MIN_COUNT,
) -> list[dict[str, Any]]:
    """Repeated contiguous subsequences of type ids — the "new syllable syntaxes" deliverable.

    What this is: discovered *structure with counts*. Over every typed bout (all species
    and the unlabelled pool — see `type_sequences`), find the subsequences that recur
    more than their own parts predict, and report them with where they were heard. What
    it is not: meaning. A chunk says these types occur together, in this order, more
    often than the bigram statistics of its pieces account for — the formal shape of the
    chickadee's A→B→C→D ordering or the great tit's ABC-D composition (docs/03 §3.2),
    with no gloss attached. Anything beyond that is playback-experiment territory, and
    this function cannot go there.

    Method. Count every n-gram up to `CHUNK_MAX_LEN`. A candidate is an n-gram with
    n ≥ 3 (pairs are the transition table's business) and count ≥ `min_count` whose
    pointwise mutual information against the bigram baseline is positive:

        pmi(c) = log2( P(c) / Σₛ wₛ · ( Pₛ(x₁) · Πᵢ Pₛ(xᵢ | xᵢ₋₁) ) )

    — the chunk occurs more often than chaining the bigram probabilities of its parts
    expects: the whole is more predictable than the parts. The ratio is taken against
    the baseline's expected occurrences plus `CHUNK_PSEUDOCOUNT`, so a candidate whose
    baseline expects one or two occurrences cannot report unbounded surprise. The
    trigram (order-2) counts are where the mining starts, because order-1 exactly
    cancels in this score — for a bigram the ratio is identically 1. The conditionals
    are taken over bigram-*start* counts, not raw unigram counts: a bout-final token
    starts no transition, and dividing by it anyway deflates every chain probability
    (a third of it at the median bout length here), which inflates every pmi by the
    same factor — the control's residue before this was measured.

    **The baseline is a mixture over species, and that is load-bearing.** Ids are
    species-local, so the pooled corpus aliases twenty-one different sounds named `L04`
    into one token; a plain pooled bigram baseline then reports positive pmi for any
    frequent trigram purely because species differ in their type-frequency profiles —
    measured on this store, a per-species permutation control "found" fifty such chunks
    at pmi up to 1.2 against the pooled baseline. Scoring each species against its own
    chain (weighted by its share `wₛ` of the n-grams) removes the artifact.

    **Runs of a single type are excluded.** `[L04, L04, L04]` is a trill, and a trill is
    already fully expressed by the grammar's self-transition probability; the documented
    cases this exists for — the chickadee's A→B→C→D, the great tit's ABC-D (docs/03
    §3.2) — are sequences of *distinct* types. Measured on the 47k store, admitting
    mono-runs puts forty-nine trill variants in the top fifty and the alternating
    motifs below them out of sight.

    The honest control: permute each species' tokens *globally* (not within bouts — a
    three-syllable bout keeps its order by chance a third of the time, which is not a
    null). A global permutation destroys exactly the sequential information while
    keeping each species' marginals, so against the mixture baseline every candidate's
    pmi collapses to ~0 — and the `CHUNK_MIN_EVIDENCE` gate, set past the control's
    measured selection-noise tail, is what sends its yield to zero. A bare `pmi > 0`
    was tried first and failed exactly this way: thousands of null candidates, and the
    luckiest of them looked like structure.

    Maximality: a chunk that only ever occurs inside a longer chunk with the same count
    is a fragment of it, not a chunk of its own, and is dropped in the longer one's
    favour. The result is capped at `CHUNK_TOP` by count.

    **Ids are species-local.** A chunk reported with two species means the two birds
    share a pattern of rank-ordered type ids — and because ids are assigned by pitch
    rank, at most a similar pitch-ordered structure — NOT that they share sounds. Shared
    acoustics across species is `relations.py`'s question, asked in the embedding space.
    """
    counts: dict[int, Counter[tuple[str, ...]]] = {
        n: Counter() for n in range(1, CHUNK_MAX_LEN + 1)
    }
    species_of: dict[tuple[str, ...], set[str]] = defaultdict(set)
    totals = {n: 0 for n in counts}
    # Per-species unigram/bigram statistics and n-gram totals, for the mixture baseline.
    uni_s: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    bi_s: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    tot_s: dict[str, dict[int, int]] = defaultdict(lambda: {n: 0 for n in counts})
    for species_id, seq in sequences:
        seq = list(seq)
        for n in counts:
            for i in range(len(seq) - n + 1):
                gram = tuple(seq[i : i + n])
                counts[n][gram] += 1
                totals[n] += 1
                tot_s[species_id][n] += 1
                if n == 1:
                    uni_s[species_id][gram] += 1
                elif n == 2:
                    bi_s[species_id][gram] += 1
                if n >= 3:
                    species_of[gram].add(species_id)

    # Occurrences of each token in a *non-final* position — the proper denominator for a
    # transition probability (a bout-final token starts none).
    starts_s: dict[str, Counter[str]] = defaultdict(Counter)
    for sid, bi in bi_s.items():
        for (a, _), c in bi.items():
            starts_s[sid][a] += c

    def pmi(gram: tuple[str, ...], count: int) -> float:
        n = len(gram)
        p_chain = 0.0
        for sid, uni in uni_s.items():
            weight = tot_s[sid][n] / max(1, totals[n])
            if weight <= 0.0:
                continue
            starts = starts_s[sid]
            p = starts[gram[0]] / max(1, tot_s[sid][2])
            for a, b in zip(gram, gram[1:]):
                p *= bi_s[sid][(a, b)] / max(1, starts[a])
            p_chain += weight * p
        expected = p_chain * totals[n]
        return math.log2(count / (expected + CHUNK_PSEUDOCOUNT))

    # A fragment is a chunk that occurs exactly as often as a longer chunk containing
    # it: every one of its occurrences is inside the longer one, so it adds nothing.
    fragment: set[tuple[str, ...]] = set()
    for n in range(3, CHUNK_MAX_LEN):
        for gram, c in counts[n + 1].items():
            if c < min_count:
                continue
            for i in (0, 1):
                sub = gram[i : i + n]
                if counts[n][sub] == c:
                    fragment.add(sub)

    chunks: list[dict[str, Any]] = []
    for n in range(3, CHUNK_MAX_LEN + 1):
        for gram, c in counts[n].items():
            if c < min_count or gram in fragment or len(set(gram)) == 1:
                continue
            score = pmi(gram, c)
            if score * math.sqrt(c) < CHUNK_MIN_EVIDENCE:
                continue
            chunks.append(
                {
                    "sequence": list(gram),
                    "count": int(c),
                    "species": sorted(species_of[gram]),
                    "pmi": round(score, 3),
                }
            )
    chunks.sort(key=lambda ch: (-ch["count"], ch["sequence"]))
    return chunks[:CHUNK_TOP]


# --- song-level typing: clustering bouts ----------------------------------------------

#: Name of the store-side table `attach_song_types`'s rows land in, beside `typing.json`:
#: one row per typed bout, keyed by the bout's first syllable the way `typing.json` keys
#: each syllable.
SONG_TYPING_NAME = "song-typing.json"
#: Fewest bouts of one kind that may be called a song type. The grammar's transitions
#: already carry what two observations of a sequence say; a *type* of song is a claim
#: about recurrence across recordings, and a handful of bouts is where chance stops
#: being distinguishable from recurrence. Measured on the 47k store against the global
#: permutation control (docs/12): at 4 the control chains 103 bouts (3.0 %) into 17
#: spurious types; at 6 it finds one type and 6 bouts (0.2 %) while the real corpus
#: keeps 50 types over 28.6 % of candidate bouts; at 8 half the real types are gone.
#: Six is the knee.
SONG_MIN_CLUSTER = 6
#: Fewest run-collapsed tokens a bout needs before song-level clustering will look at
#: it. One or two tokens is a unigram or a bigram — already the transition table's
#: content, and measured to be chainable into spurious clusters by chance alone (see
#: `cluster_song_types`). The cuckoo's two-note song is the honest cost: it lives in
#: the grammar, not here.
SONG_MIN_MOTIF = 3
#: Largest normalised edit distance at which two bouts may end up in one song type.
#: Without it HDBSCAN's EOM selection carves "clusters" out of uniformly far-apart
#: noise — measured: five random six-token strings, all ~0.8 apart, reported as one
#: song type. Two renditions of a motif differ by a syllable or two (≤ 0.4 at motif
#: lengths), chance strings by most of their length, so the cut sits between the two.
SONG_MAX_RADIUS = 0.5


def bout_sequences(
    observations: Sequence[SyllableObservation],
    typing: Sequence[dict[str, Any]],
) -> list[tuple[str, tuple[str, int], list[str]]]:
    """Per-recording type-id sequences, one per bout, with the bout's store key.

    The general form of `type_sequences`: same bouts under the same two rules (order is
    meaningful within a recording and meaningless across; a gap over a second breaks a
    bout; untyped observations are skipped without breaking it), but each bout also
    carries `(recording_id, first_order)` — the order of its first typed syllable — so a
    song-level fit can name the bouts it claims, the way `typing_rows` names syllables.
    """
    type_of = {
        (e["speciesId"], e["recordingId"], int(e["order"])): str(e["typeId"])
        for e in typing
    }
    by_recording: dict[tuple[str, str], list[SyllableObservation]] = defaultdict(list)
    for o in observations:
        by_recording[(o.species_id, o.recording_id)].append(o)
    out: list[tuple[str, tuple[str, int], list[str]]] = []
    for (species_id, recording_id), items in by_recording.items():
        items.sort(key=lambda o: o.order)
        bout: list[str] = []
        first = 0
        for o in items:
            if o.gap_before > 1.0 and bout:
                out.append((species_id, (recording_id, first), bout))
                bout = []
            tid = type_of.get((o.species_id, o.recording_id, o.order))
            if tid is not None:
                if not bout:
                    first = o.order
                bout.append(tid)
        if bout:
            out.append((species_id, (recording_id, first), bout))
    return out


def _collapse_runs(seq: Sequence[str]) -> tuple[str, ...]:
    """One token per run of repeats: `A A A B B A` reads as the motif `A B A`.

    A trill is a syllable repeating, and how many times it repeats is tempo, not syntax
    — the grammar's self-transition probability already carries that axis. Without the
    collapse, two bouts of one motif sung at different speeds sit an edit distance of
    twenty apart and song-level clustering measures repeat counts instead of order.
    `mine_chunks` excludes mono-runs for the same reason.
    """
    out: list[str] = []
    for t in seq:
        if not out or out[-1] != t:
            out.append(t)
    return tuple(out)


def _edit_distance(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    """Levenshtein distance over token tuples, substitution cost one."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ta in enumerate(a, 1):
        current = [i]
        for j, tb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (ta != tb)))
        previous = current
    return previous[-1]


def cluster_song_types(
    sequences: Sequence[tuple[str, tuple[str, int], Sequence[str]]],
    min_cluster_size: int = SONG_MIN_CLUSTER,
) -> dict[str, dict[str, Any]]:
    """Cluster each species' bouts into song types: motifs that recur across recordings.

    What this is: `learn_types` one level up. Syllable typing answers "which of these
    sounds are the same sound"; this answers "which of these bouts are the same bout" —
    a song type is a cluster of similar type-id sequences, and a bout in no cluster is
    the song-level novelty answer: a sequence this bird has not been heard repeating.
    The machinery is deliberately the same shape as the syllable level's (docs/08):
    distances, density, and a noise category rather than a declared k.

    Method. Each bout is run-collapsed (`_collapse_runs`), so the distance is about the
    order of distinct acts. **Bouts that collapse to fewer than `SONG_MIN_MOTIF` tokens
    are set aside, not clustered**: a one- or two-token string is a unigram or a bigram,
    and those are the transition table's business, not a song type's — `mine_chunks`
    starts at n = 3 for the same reason. The measured cost of skipping this gate: at the
    store's alphabet sizes, chance two-token strings sit one substitution (a normalised
    distance of 0.5) from each other often enough for HDBSCAN to chain them into
    clusters of pure noise — the first run of this function reported a "song type" of
    six unrelated random bouts, and the permutation control catches exactly that shape.
    What remains is reported under the summary's `short`, honestly out of scope rather
    than silently unplaced.

    Similarity between two candidate bouts is the Levenshtein distance between their
    collapsed strings, normalised by the longer string's length — two bouts of one song
    type differ by a syllable or two, not by half their length, so the ratio, not the
    raw count, is what "a few edits" means for bouts of three tokens and bouts of
    thirty. Identical strings are deduplicated before the O(n²) matrix and re-expanded
    after (a corpus of five hundred bouts holds a hundred-odd distinct strings), then
    HDBSCAN over the precomputed matrix finds the dense motifs, for the same two reasons
    it clusters descriptors in density.py: the number of song types is the thing we do
    not know, and "this bout belongs to none of them" must be an answerable question. A
    species with fewer candidate bouts than `min_cluster_size` reports no types and
    every candidate unplaced — too rare to call is an answer, not a failure.

    **Per species, never pooled.** Type ids are species-local — `L04` names a different
    sound for every bird — so a pooled distance matrix would alias twenty birds' strings
    into one alphabet, the artifact `mine_chunks`'s mixture baseline exists to remove.
    Cross-species song structure is asked in the embedding space (relations.py), not
    here.

    The honest control is the chunk miner's: permute each species' tokens globally,
    keeping bout lengths and the type marginals, and count what the same clustering
    finds in the shuffled strings — random strings should share no motifs, but a skewed
    type distribution makes short chance strings genuinely edit-close, so the yield is
    not automatically zero. The measured yields on the 47k store are in docs/12;
    `SONG_MIN_CLUSTER` is set at the knee where the control's yield is 0.2 % of
    candidate bouts (and the residual is reported, not hidden).

    Ids are `S01`, `S02`, … ranked by bout count. Unlike syllable ids (`assign_ids`)
    they are **not** stabilised across refits — a re-learnt typing renumbers the strings
    themselves, so stability has to wait on the syllable ids it would be defined over.
    """
    from sklearn.cluster import HDBSCAN

    by_species: dict[str, list[tuple[tuple[str, int], tuple[str, ...]]]] = defaultdict(list)
    for species_id, key, seq in sequences:
        collapsed = _collapse_runs(seq)
        if collapsed:
            by_species[species_id].append((key, collapsed))

    out: dict[str, dict[str, Any]] = {}
    for species_id in sorted(by_species):
        short = [(key, c) for key, c in by_species[species_id] if len(c) < SONG_MIN_MOTIF]
        items = [(key, c) for key, c in by_species[species_id] if len(c) >= SONG_MIN_MOTIF]
        uniques = sorted({collapsed for _, collapsed in items})
        summary = {
            "bouts": len(items) + len(short),
            "short": len(short),
            "candidates": len(items),
            "types": 0,
            "inTypes": 0,
            "unplaced": len(items),
            "minClusterSize": int(min_cluster_size),
        }
        entry: dict[str, Any] = {"types": [], "rows": [], "summary": summary}
        out[species_id] = entry
        if len(items) < max(2, min_cluster_size) or len(uniques) < 2:
            continue

        index = {collapsed: i for i, collapsed in enumerate(uniques)}
        n = len(uniques)
        distances = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(i + 1, n):
                d = _edit_distance(uniques[i], uniques[j]) / max(
                    len(uniques[i]), len(uniques[j])
                )
                distances[i, j] = distances[j, i] = d
        per_bout = np.array([index[collapsed] for _, collapsed in items])
        model = HDBSCAN(
            min_cluster_size=int(max(2, min_cluster_size)),
            metric="precomputed",
            cluster_selection_method="eom",
            copy=True,
        ).fit(distances[np.ix_(per_bout, per_bout)])
        labels = model.labels_.astype(int)
        k = int(labels.max()) + 1 if labels.size and labels.max() >= 0 else 0

        clusters: list[dict[str, Any]] = []
        for c in range(k):
            member_rows = np.nonzero(labels == c)[0]
            member_strings = sorted({int(per_bout[i]) for i in member_rows})
            # The exemplar is the medoid: the member string least far from the rest of
            # the cluster, weighted by how often each string was heard — an observed
            # bout, never an average of bouts, so the app could play exactly this.
            weights = np.array(
                [(per_bout[member_rows] == u).sum() for u in member_strings],
                dtype=np.float64,
            )
            sub = distances[np.ix_(member_strings, member_strings)]
            medoid = uniques[member_strings[int((sub * weights).sum(axis=1).argmin())]]
            # The radius gate. EOM will select a cluster out of uniformly far-apart
            # noise if it is slightly denser than its surroundings (measured: five
            # random six-token strings, ~0.8 from their own medoid, reported as a song
            # type). Density decides *where* clusters are; this decides whether what it
            # found is one — a cluster whose members are not actually near their medoid
            # is noise wearing a label, and is demoted to it.
            to_medoid = distances[np.ix_(member_strings, [uniques.index(medoid)])][:, 0]
            if float((to_medoid * weights).sum() / weights.sum()) > SONG_MAX_RADIUS:
                labels[member_rows] = -1
                continue
            clusters.append({"sequence": list(medoid), "count": int(len(member_rows)),
                             "label": c})
        clusters.sort(key=lambda t: (-t["count"], t["sequence"]))
        id_of = {t["label"]: f"S{rank + 1:02d}" for rank, t in enumerate(clusters)}

        entry["types"] = [
            {
                "id": id_of[t["label"]],
                "sequence": t["sequence"],
                "count": t["count"],
                # Of every bout this species sang, short ones included — the shares,
                # `short` and `unplaced` sum to the whole.
                "share": round(t["count"] / (len(items) + len(short)), 4),
            }
            for t in clusters
        ]
        for i, (key, _) in enumerate(items):
            if labels[i] >= 0:
                entry["rows"].append({
                    "speciesId": species_id,
                    "recordingId": key[0],
                    "firstOrder": int(key[1]),
                    "songTypeId": id_of[int(labels[i])],
                })
        summary["types"] = len(clusters)
        summary["inTypes"] = int((labels >= 0).sum())
        summary["unplaced"] = int((labels < 0).sum())
    return out


def attach_song_types(
    document: dict[str, Any],
    observations: Sequence[SyllableObservation],
    typing: Sequence[dict[str, Any]],
    min_cluster_size: int = SONG_MIN_CLUSTER,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """Cluster every species' bouts into song types and hang them on each grammar.

    The song-level counterpart of `attach_chunks`: one pass over `bout_sequences`, then
    each species' grammar carries its song types under `grammar.songTypes` (id, medoid
    sequence, bout count, share of the species' bouts) and the census under
    `grammar.songTyping` (how many bouts, how many too short to be a motif, how many
    placed, how many heard once and never again). Returns the flat membership rows —
    the store-side `song-typing.json` table, so a later build or grow can key a bout to
    its song type without reclustering.
    """
    if not typing:
        return []
    found = cluster_song_types(
        bout_sequences(observations, typing), min_cluster_size=min_cluster_size
    )
    rows: list[dict[str, Any]] = []
    for sp in document.get("species", []):
        entry = found.get(sp["id"])
        if not entry:
            continue
        if entry["types"]:
            sp.setdefault("grammar", {})["songTypes"] = entry["types"]
        sp.setdefault("grammar", {})["songTyping"] = entry["summary"]
        rows.extend(entry["rows"])
    if verbose:
        total = sum(e["summary"]["candidates"] for e in found.values())
        placed = sum(e["summary"]["inTypes"] for e in found.values())
        short = sum(e["summary"]["short"] for e in found.values())
        log(f"song-level typing: {sum(e['summary']['types'] for e in found.values())} "
            f"song types over {total} candidate bouts, {placed} placed and "
            f"{total - placed} heard once (never repeated — the song-level novelty "
            f"answer); {short} short bouts left to the transition table")
    return rows


# --- typing without a species label ---------------------------------------------------

#: The species_id every browser-ingested recording arrives under (server.py
#: `/api/ingest`), and the id of the pseudo-species the pool becomes in the learned
#: inventory.
UNLABELLED_SPECIES = "unlabelled"
#: Below this many arrivals the pool is left alone. Sixteen is two min-clusters' worth —
#: the smallest pool in which "some of this is a known sound and some is not" can both
#: be said at once.
UNLABELLED_MIN_OBSERVATIONS = 16
#: Fewest arrivals of one kind that may be called a candidate type. Much lower than the
#: galaxy's 25 (density.py): the pool is small by construction — it is what ingest
#: brought in — and a sound heard eight times in it is past accident.
UNLABELLED_MIN_CLUSTER = 8


def known_type_centroids(
    observations: Sequence[SyllableObservation],
    typing: Sequence[dict[str, Any]],
    embeddings: np.ndarray,
) -> dict[str, np.ndarray]:
    """Mean raw embedding of each fitted type, keyed `species/typeId`.

    The reference set `learn_unlabelled` inherits against: one centroid per (species,
    type) the current fit produced, in the critic's raw 32-d space — the space the
    novelty threshold was calibrated in, so standardising here would move every distance
    the threshold is about to judge. The key carries the species because type ids are
    species-local (`L03` names a different sound for every bird), and the whole point of
    the inheritance is to say *whose* type an arrival matches. Rows for the unlabelled
    pool itself are excluded: its verdicts are what is being decided.
    """
    row_of = {
        (o.species_id, o.recording_id, o.order): i for i, o in enumerate(observations)
    }
    members: dict[str, list[int]] = defaultdict(list)
    for e in typing:
        if e["speciesId"] == UNLABELLED_SPECIES:
            continue
        i = row_of.get((e["speciesId"], e["recordingId"], int(e["order"])))
        if i is not None:
            members[f"{e['speciesId']}/{e['typeId']}"].append(i)
    z = np.asarray(embeddings, dtype=np.float64)
    out: dict[str, np.ndarray] = {}
    for tid, rows in members.items():
        vecs = z[rows]
        finite = np.all(np.isfinite(vecs), axis=1)
        if finite.any():
            out[tid] = vecs[finite].mean(axis=0)
    return out


def learn_unlabelled(
    observations: Sequence[SyllableObservation],
    embedder: Embedder | None,
    novelty: Any,
    known_types: dict[str, np.ndarray],
    seed: int = 0,
    previous: dict[str, dict[str, Any]] | None = None,
) -> list[LearnedType]:
    """Type the unlabelled pool: inherit what matches a known type, cluster the rest.

    Everything else in this module is conditioned on xeno-canto's species label — typing
    and grammar run per species, so audio that arrives without one (browser ingest stores
    it as `unlabelled`) had no path to either. This is the label-free path, and it works
    precisely because the critic's embedding needs no label: "which known type is this
    nearest, and how near" and "which of these arrivals sound like each other" are both
    distance questions in a space that was trained without being told what it would hear.

    Two verdicts, kept apart because they are not equally strong:

    - **Inheritance.** An arrival within the novelty threshold of a known type centroid
      is *evidence for that type*: a `LearnedType` whose id is the qualified
      `species/typeId` and whose syllable is empty — the type already exists, this adds
      no new one. The threshold is the novelty scorer's own, calibrated to a chosen
      false-positive rate (critic.py), so the verdict's error rate is known rather than
      assumed; it is borrowed from a calibration over the scorer's own centroids, which
      is the same kind of distance in the same space, not a re-measurement. The
      observation's species is never relabelled: matching a sound is not identifying a
      bird.
    - **Candidates.** The remainder is clustered with HDBSCAN (min_cluster_size
      `UNLABELLED_MIN_CLUSTER`) over the standardised embedding. Each dense cluster is a
      candidate type `U00…`, fitted by the same median logic as any other type
      (`_median_syllable`) but carrying the base fields only — there is no species
      reference to invert or verify against, so nothing is searched and no resynthesis
      cosine is claimed. Arrivals HDBSCAN leaves as noise stay untyped: "too rare to
      call yet" is an answer, not a failure (density.py).

    `previous` is the last fit's `U*` syllables keyed by id, so candidates keep their ids
    across refits at the same tolerance as any species' types (`assign_ids`).
    """
    pool = [o for o in observations if o.species_id == UNLABELLED_SPECIES]
    if len(pool) < UNLABELLED_MIN_OBSERVATIONS or embedder is None:
        return []
    z = np.asarray(embedder(pool), dtype=np.float64)

    assigned = np.zeros(len(pool), dtype=bool)
    nearest_id = [""] * len(pool)
    if known_types and novelty is not None:
        keys = sorted(known_types)
        sims = _unit_rows(z) @ _unit_rows(np.stack([known_types[k] for k in keys])).T
        best = sims.argmax(axis=1)
        # Cosine distance against the novelty threshold — the same comparison
        # `Novelty.distance` makes, with a type id instead of a novelty flag as the answer.
        assigned = (1.0 - sims[np.arange(len(pool)), best]) <= novelty.threshold
        nearest_id = [keys[i] for i in best]

    types: list[LearnedType] = []
    by_type: dict[str, list[SyllableObservation]] = defaultdict(list)
    rest_idx: list[int] = []
    for i, o in enumerate(pool):
        if assigned[i]:
            by_type[nearest_id[i]].append(o)
        else:
            rest_idx.append(i)
    for tid, members in sorted(by_type.items()):
        types.append(LearnedType(id=tid, members=members))

    n_noise = len(rest_idx)
    if len(rest_idx) >= UNLABELLED_MIN_CLUSTER:
        rest = z[rest_idx]
        standardised = (rest - rest.mean(axis=0)) / np.maximum(rest.std(axis=0), 1e-6)
        result = density.cluster(standardised, min_cluster_size=UNLABELLED_MIN_CLUSTER)
        n_noise = result.noise
        candidates: list[LearnedType] = []
        for c in range(result.k):
            members = [pool[rest_idx[i]] for i in np.nonzero(result.labels == c)[0]]
            t = LearnedType(id=f"U{c:02d}", members=members)
            t.syllable = _median_syllable(members, t.id)
            candidates.append(t)
        candidates.sort(key=lambda t: syrinx.f0_reference(t.syllable["contour"]))
        assign_ids(candidates, previous, prefix="U")
        types.extend(candidates)

    log(
        f"  {UNLABELLED_SPECIES:26} {len(pool)} arrivals: {int(assigned.sum())} within "
        f"the novelty threshold of {len(by_type)} known type(s), "
        f"{sum(1 for t in types if t.syllable)} candidate type(s) from the remaining "
        f"{len(rest_idx)}, {n_noise} unplaceable"
    )
    return types


def unlabelled_entry(
    types: Sequence[LearnedType],
    pool: Sequence[SyllableObservation],
    grammar: dict[str, Any],
) -> dict[str, Any]:
    """The pseudo-species the typed unlabelled pool becomes in the learned inventory.

    Kept in the same schema as every learned species so the galaxy build, the grammar
    and the interface treat it uniformly: one entry, id `unlabelled`, bank `learned`.
    The `U*` syllables carry the base fields only (see `_median_syllable`) and stay
    `unlabelled`: clustered acoustics, no documented function. The inheritance verdicts
    travel separately under `assigned` — they are evidence *about other species' types*,
    so they are not syllables of this one — and the summary states the numbers rather
    than a gloss: matching a sound is not knowing what it means (§8.5).
    """
    candidates = [t for t in types if t.syllable]
    inherited = [t for t in types if not t.syllable]
    n_inherited = sum(len(t.members) for t in inherited)
    n_clustered = sum(len(t.members) for t in candidates)
    n_noise = len(pool) - n_inherited - n_clustered
    return {
        "id": UNLABELLED_SPECIES,
        "common": "Unlabelled arrivals",
        "scientific": "",
        "bank": "learned",
        "summary": (
            f"Arrivals with no species label, typed in the critic's embedding: "
            f"{n_inherited} of {len(pool)} syllables matched a known type within the "
            f"novelty-calibrated threshold (evidence for that type, not an "
            f"identification); {len(candidates)} candidate type(s) clustered from the "
            f"remaining {n_clustered}; {n_noise} could not be placed. No documented "
            f"function is attached to any of them."
        ),
        "syllables": [
            {**t.syllable, "learned": {"members": len(t.members)}} for t in candidates
        ],
        "songs": [],
        "grammar": grammar,
        "assigned": [
            {"type": t.id, "observations": len(t.members)}
            for t in sorted(inherited, key=lambda t: -len(t.members))
        ],
    }


def fit_unlabelled(
    document: dict[str, Any],
    observations: Sequence[SyllableObservation],
    typing: list[dict[str, Any]],
    embedder: Embedder | None,
    novelty: Any,
    seed: int = 0,
    previous: dict[str, dict[str, Any]] | None = None,
    verbose: bool = True,
) -> dict[str, Any] | None:
    """Run the label-free fit over a store's unlabelled pool and fold it into `document`.

    The shared tail of `cmd_learn` and the control surface's fit, so the two cannot
    drift: the pseudo-species is appended to the document, its membership rows are
    appended to `typing` (and so land in the store's typing.json beside every other
    fit's), and its grammar is measured by the same `learn_grammar` as any species —
    per recording, never concatenated across recordings, because order within a
    recording is meaningful and order across them is not.

    Gated on evidence, in the order it runs out: enough arrivals to say anything
    (`UNLABELLED_MIN_OBSERVATIONS`), an embedder to see them with, and a novelty scorer
    to threshold inheritance with. Without the scorer the calibrated distance is missing
    and inheritance would happen at an invented threshold, so the pool is skipped with a
    logged reason rather than typed dishonestly. With no pool at all it returns None
    silently — a store without arrivals is the ordinary case, not a finding.
    """
    pool = [o for o in observations if o.species_id == UNLABELLED_SPECIES]
    if not pool:
        return None
    if len(pool) < UNLABELLED_MIN_OBSERVATIONS:
        if verbose:
            log(f"  {UNLABELLED_SPECIES:26} {len(pool)} arrivals — below the "
                f"{UNLABELLED_MIN_OBSERVATIONS} needed, left untyped")
        return None
    if embedder is None:
        if verbose:
            log(f"  {UNLABELLED_SPECIES:26} {len(pool)} arrivals, but no critic is "
                "available to embed them — label-free typing needs the learned "
                "embedding, so the pool is left untyped")
        return None
    if novelty is None:
        if verbose:
            log(f"  {UNLABELLED_SPECIES:26} {len(pool)} arrivals, but no novelty scorer "
                "(<critic>-novelty.json, written by `critic train`) — without the "
                "calibrated threshold there is no honest distance to inherit at, so "
                "the pool is left untyped")
        return None

    # One embedding pass serves both halves: the centroids of the types the per-species
    # fit just wrote into `typing`, and (inside `learn_unlabelled`) the arrivals.
    z_all = np.asarray(embedder(observations), dtype=np.float64)
    known = known_type_centroids(observations, typing, z_all)
    types = learn_unlabelled(pool, embedder, novelty, known, seed=seed, previous=previous)
    if not types:
        return None

    index = {id(o): i for i, o in enumerate(pool)}
    type_of = {index[id(o)]: t.id for t in types for o in t.members}
    grammar = learn_grammar(pool, type_of)
    typing.extend(typing_rows(types))
    entry = unlabelled_entry(types, pool, grammar)
    document["species"].append(entry)
    return entry


def attach_chunks(
    document: dict[str, Any],
    observations: Sequence[SyllableObservation],
    typing: Sequence[dict[str, Any]],
    min_count: int = CHUNK_MIN_COUNT,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """Mine chunks over every typed sequence and hang them on each species' grammar.

    One global mining — all species plus the unlabelled pool, because a chunk whose
    *pattern* crosses a species boundary is exactly the thing worth reporting — then
    each grammar carries the chunks heard in its own species under `grammar.chunks`.
    The `start`/`transitions` schema is untouched. Returns the global chunk list.
    """
    if not typing:
        return []
    chunks = mine_chunks(type_sequences(observations, typing), min_count=min_count)
    for sp in document.get("species", []):
        mine = [c for c in chunks if sp["id"] in c["species"]]
        if mine:
            sp.setdefault("grammar", {})["chunks"] = mine
    if verbose:
        shared = sum(1 for c in chunks if len(c["species"]) > 1)
        log(f"chunk mining: {len(chunks)} repeated subsequence(s) at count >= "
            f"{min_count}, {shared} repeating across species (as id patterns — "
            "species-local ids; see mine_chunks)")
    return chunks


# --- putting it together -----------------------------------------------------------


def typing_rows(fitted: Sequence[LearnedType]) -> list[dict[str, Any]]:
    """The fit's membership as flat rows: which learned type each observation is.

    This is how the clustering leaves the fit. A `LearnedType`'s members are the store's
    own `SyllableObservation`s, so the table only has to name them — keyed by
    `(speciesId, recordingId, order)`, exactly as the store keys them — for the build to
    label every stored syllable with its type, and to render the measured member sets,
    without refitting anything.
    """
    return [
        {
            "speciesId": o.species_id,
            "recordingId": o.recording_id,
            "order": o.order,
            "typeId": t.id,
        }
        for t in fitted
        for o in t.members
    ]


def choose_k(
    observations: Sequence[SyllableObservation],
    floor: int = DEFAULT_TYPES,
    seed: int = 0,
    verbose: bool = False,
    species_id: str = "",
    embedder: Embedder | None = None,
) -> int:
    """Pick the number of types by silhouette over a sweep, not by a flag or by corpus size.

    The candidates are geometric between `floor` and what the data could support at
    `OBS_PER_TYPE` observations per type, capped at `MAX_TYPES`. Geometric rather than every
    integer because the silhouette curve over k is smooth and a six-point sweep finds the
    shoulder as well as a sixty-point one at a tenth of the cost.

    Silhouette is computed on a subsample: it is O(n^2) in distances and these species have
    thousands of observations, while the statistic itself stabilises long before that.
    """
    from sklearn.metrics import silhouette_score

    n = len(observations)
    ceiling = max(2, min(MAX_TYPES, n // OBS_PER_TYPE))
    lowest = max(2, min(floor, ceiling))
    if ceiling <= lowest:
        return lowest

    candidates: list[int] = []
    k = lowest
    while k < ceiling:
        candidates.append(k)
        k = max(k + 1, int(round(k * 1.7)))
    candidates.append(ceiling)
    candidates = sorted(set(candidates))

    x = typing_space(observations, embedder)
    rng = np.random.default_rng(seed)
    sample = x if n <= 2000 else x[rng.choice(n, size=2000, replace=False)]

    best_k, best_score = lowest, -2.0
    scores: list[tuple[int, float]] = []
    for cand in candidates:
        if cand >= len(sample):
            continue
        labels = KMeans(n_clusters=cand, n_init=4, random_state=seed).fit_predict(sample)
        if len(set(labels)) < 2:
            continue
        score = float(silhouette_score(sample, labels))
        scores.append((cand, score))
        if score > best_score:
            best_k, best_score = cand, score
    if verbose and scores:
        shown = ", ".join(f"k={c}:{s:+.3f}" for c, s in scores)
        log(f"  {species_id:26} type-count sweep {shown} -> {best_k}")
    return best_k


def learn_species(
    species_id: str,
    observations: Sequence[SyllableObservation],
    descriptors: dict[str, np.ndarray] | None,
    calibration: Calibration | None,
    types: int = DEFAULT_TYPES,
    seed: int = 0,
    verbose: bool = True,
    frame: tuple[np.ndarray, np.ndarray] | None = None,
    invert: bool = True,
    previous: dict[str, dict[str, Any]] | None = None,
    embedder: Embedder | None = None,
    realism: "RealismTerm | None" = None,
    use_tube: bool = False,
) -> dict[str, Any] | None:
    """Fitted syllables + a measured grammar for one species, or None if too little data.

    `embedder` and `realism` are the two halves of docs/09 §9.2b/§9.3 and they are independent:
    the first changes what a *type* is, the second changes what *close* means. Both default to
    off, so a run that passes neither is bit-identical to the fit that shipped before the critic
    existed — which is what makes the comparison in the plan's results table meaningful.

    `use_tube` re-enables the waveguide tract. It is written, tested, and gated off because the
    28-d objective rejected it (§9.1 result 5). docs/09 calls it "the cleanest available test of
    whether the new objective is actually better", so it is a flag here rather than a constant:
    the waveguide is known to be structurally right, and an objective that still rejects it is
    not fixed.
    """
    if len(observations) < MIN_OBSERVATIONS:
        if verbose:
            log(f"  {species_id:26} {len(observations)} observations — below the "
                f"{MIN_OBSERVATIONS} needed, skipped")
        return None

    # **How many types to fit is a question for the data, and it needs a criterion.**
    #
    # Two wrong answers came before this one. `min(types, n // OBS_PER_TYPE)` pinned the
    # repertoire to a flag, so a species with seven thousand observations got the same eight
    # types as one with two hundred and a loop could run for an hour without the repertoire
    # growing. Replacing that with `n // OBS_PER_TYPE` swung too far the other way: one type
    # per twelve observations is not evidence of anything, it is a linear function of corpus
    # size, and measured on this harvest it drove every well-recorded species to the ceiling
    # and cost half the fit quality — types landing nearest their own source audio fell from
    # 51 % to 28 %.
    #
    # So the count is chosen by silhouette over a candidate sweep: fit each k, ask how
    # separated the resulting types actually are in the observation space, and keep the best.
    # That is a statement about the recordings rather than about the corpus size, it cannot
    # be gamed by harvesting more of the same call, and `--types` becomes the floor of the
    # sweep rather than its answer.
    #
    # `embedder` changes the space this silhouette is computed in. That is the substance of
    # docs/09 §9.2b use 1: the plan's own expectation is that the silhouette "becomes
    # meaningful rather than a proxy fitted to guessed weights", so the k it picks is expected
    # to move — and the fitted repertoire moves with it.
    k = choose_k(
        observations, floor=types, seed=seed, verbose=verbose, species_id=species_id,
        embedder=embedder,
    )
    fitted = fit_types(observations, k, seed=seed, previous=previous, embedder=embedder)

    index = {id(o): i for i, o in enumerate(observations)}
    type_of = {index[id(o)]: t.id for t in fitted for o in t.members}

    # Where each type's *real* audio sits, in the frame the whole harvest defines. The
    # type's own recordings when the store kept them, and the recording averages
    # otherwise — a much weaker reference, identical for every type of a species.
    real: list[np.ndarray | None] = []
    for t in fitted:
        rows = [np.asarray(o.descriptor, dtype=float) for o in t.members if o.descriptor]
        if not rows and descriptors:
            rows = [descriptors[o.recording_id] for o in t.members if o.recording_id in descriptors]
        if not rows:
            real.append(None)
            continue
        mean_row = np.mean(np.stack(rows), axis=0)
        if frame is not None:
            mean_row = features.standardise(mean_row, frame[0], frame[1])
        real.append(_unit(mean_row))

    # The bird's trachea, before any per-syllable gesture: it is the one parameter shared by
    # the whole repertoire, and the gestures should be searched against a tract that is
    # already in place rather than have one imposed on them afterwards.
    trachea_f1, trachea_gain = (0.0, 0.0)
    if invert:
        # measured from this species' own spectra, then its level settled by resynthesis
        measured_f1 = measure_trachea_f1(observations)
        # The waveguide first: it is the same trachea, modelled as a tube rather than as a
        # parallel bank, and it replaces the f0-tracking band instead of sitting beside it.
        #
        # Off by default, and the reason is a measurement rather than a doubt: the waveguide is
        # mechanically right (32x the spectral freedom against 1.3x for the tracking band) and
        # wins in isolation, but over 22 species of `out/harvest` it cost more than it bought,
        # so shipping it unconditionally would have been a measured regression (docs/09 §9.1
        # result 5).
        #
        # **That diagnosis has since been revised, and the revision is why this is a flag and
        # not a deletion.** §9.1 blamed the objective: a structurally better tract, scored by a
        # weak metric, loses. Re-measured on `out/harvest-gan` (docs/09 §9.7) the waveguide
        # *wins* — +3.5 points of species placement with the hand-written typing vector and
        # +4.1 with the learned embedding, reaching 37.0 % together with it. What had been
        # rejecting it was not the objective but the **typing**: a tract fixed for the whole
        # bird cannot match a per-type reference that is itself a blend of several different
        # sounds, which is what seven hand-weighted numbers were producing. It still costs
        # cosine (0.755 -> 0.706), and it has not been confirmed on a 40 k store, so it stays
        # opt-in until it is.
        tube_len, tube_r = (0.0, 0.0)
        if use_tube:
            tube_len, tube_r = fit_species_tube(
                fitted, real, calibration, frame, measured_f1, realism=realism
            )
        if tube_r > 0.0:
            for t in fitted:
                t.syllable["tube"] = [round(tube_len, 3), tube_r]
                t.syllable["formants"] = [[round(measured_f1, 1), syrinx.TRACHEA_Q, 1.0]]
            if verbose:
                log(f"  {species_id:26} waveguide tract L {tube_len:.2f} cm, r {tube_r:.2f} "
                    f"(f1 {measured_f1:.0f} Hz)")
            trachea_f1, trachea_gain = measured_f1, 1.0
        else:
            trachea_f1, trachea_gain = fit_species_trachea(
                fitted, real, calibration, frame, measured_f1, realism=realism
            )
        if trachea_gain > 0.0:
            comb = [
                [round(hz, 1), q, round(g, 4)]
                for hz, q, g in syrinx.tracheal_comb(trachea_f1, trachea_gain)
            ]
            for t in fitted:
                t.syllable["formants"] = comb
            if verbose:
                log(f"  {species_id:26} trachea measured f1 {trachea_f1:.0f} Hz "
                    f"(comb {', '.join(f'{c[0]:.0f}' for c in comb)} Hz), gain "
                    f"{trachea_gain:.2f}, L_eff {34400.0 / (4.0 * trachea_f1):.1f} cm")
        elif verbose:
            log(f"  {species_id:26} measured f1 {measured_f1:.0f} Hz, but no comb "
                f"earned its place in the resynthesis")

    gains: list[float] = []
    for i, t in enumerate(fitted):
        # Search first, then measure: the reported cosine has to describe the syllable
        # that ships, not the median it started from.
        if invert and real[i] is not None:
            before, after = invert_gestures(
                t, real[i], calibration, frame, realism=realism
            )
            gains.append(after - before)
        # **Measured with the pure cosine, always — never with the blend.** This is the other
        # half of the guardrail: the search may optimise a blended objective, but the number
        # that ships next to every learned syllable, and the number docs/09's results table
        # compares against, is the 28-d cosine the critic has no access to. A rise in
        # placement with the cosine collapsing is the signature of a gamed critic, and it is
        # only visible if the report keeps measuring the thing the critic cannot touch.
        z = render_and_measure(t, calibration, frame)
        if z is None or real[i] is None:
            continue
        sims = [float(z @ r) if r is not None else -1.0 for r in real]
        t.resynthesis_cosine = round(sims[i], 4)
        rivals = [s for j, s in enumerate(sims) if j != i]
        t.rival_cosine = round(max(rivals), 4) if rivals else 0.0
        t.nearest_own = all(sims[i] >= s for s in rivals)
        if verbose:
            # One line per type, as it lands, in a shape something else can read.
            #
            # The per-species summary below is the right thing to read afterwards and the
            # wrong thing to watch: it arrives once, at the end, after two or three seconds
            # in which the only evidence the fit is doing anything is that it has not
            # returned. These are the numbers that decide whether a fitted voice is worth
            # shipping — how close it landed, how close it landed to the *wrong* call, and
            # whether the oscillator reached the pitch — and they exist per type well before
            # the summary does. The fixed `FIT` prefix is so the app can parse them out of
            # the job log it already streams, without a second channel to keep in step.
            log(
                f"FIT {species_id} {t.syllable['id']} "
                f"f0={syrinx.f0_reference(t.syllable['contour']):.0f} "
                f"dur={t.syllable['dur'] * 1000:.0f} "
                f"cos={t.resynthesis_cosine:.3f} rival={t.rival_cosine:.3f} "
                f"own={1 if t.nearest_own else 0} "
                f"f0err={abs(t.f0_error_percent):.2f} members={len(t.members)}"
            )

    grammar = learn_grammar(observations, type_of)
    cosines = [t.resynthesis_cosine for t in fitted if t.resynthesis_cosine]
    errors = [abs(t.f0_error_percent) for t in fitted]
    placed = sum(1 for t in fitted if t.nearest_own)
    if verbose:
        log(
            f"  {species_id:26} {len(observations):5d} obs -> {len(fitted)} types, "
            f"resynthesis cosine "
            + (f"{np.median(cosines):.3f}" if cosines else "n/a")
            + f", nearest own {placed}/{len(fitted)}"
            + f", |F0 error| median {np.median(errors):.1f} %"
            + (f", inversion +{np.median(gains):.3f}" if gains else "")
        )

    return {
        "id": species_id,
        "syllables": [
            {
                **t.syllable,
                "learned": {
                    "members": len(t.members),
                    "resynthesisCosine": t.resynthesis_cosine,
                    "rivalCosine": t.rival_cosine,
                    "nearestOwn": t.nearest_own,
                    "f0ErrorPercent": t.f0_error_percent,
                },
            }
            for t in fitted
        ],
        "grammar": grammar,
        # Not part of the document: `build_learned_inventory` pops this out and hands it
        # to the caller, who writes it as the store's typing.json.
        "typing": typing_rows(fitted),
        "observations": len(observations),
        "recordings": len({o.recording_id for o in observations}),
        # Recorded so the fitted tract is auditable as a claim about the bird rather than an
        # anonymous list of biquads inside each syllable.
        "trachea": (
            {"f1Hz": round(trachea_f1, 1), "gain": round(trachea_gain, 3)}
            if trachea_gain > 0.0
            else None
        ),
    }


def previous_fit(path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """The fitted syllables of an already-written inventory, per species and keyed by id.

    Only the machine-assigned ones (`L` for a species' learned types, `U` for the
    unlabelled pool's candidates): the authored syllables keep their own ids by definition
    and a refit never touches them. Missing or unreadable file means "no previous fit",
    which is the correct answer for a first run and the safe one for a corrupted file.
    """
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for sp in doc.get("species", []):
        fitted = {
            syl["id"]: syl
            for syl in sp.get("syllables", [])
            if str(syl.get("id", ""))[:1] in ("L", "U")
        }
        if fitted:
            out[sp["id"]] = fitted
    return out


def build_learned_inventory(
    observations: Iterable[SyllableObservation],
    inventory: dict[str, Any],
    calibration: Calibration | None,
    descriptors: dict[str, np.ndarray] | None = None,
    types: int = DEFAULT_TYPES,
    seed: int = 0,
    verbose: bool = True,
    should_stop: Callable[[], bool] | None = None,
    invert: bool = True,
    prior: dict[str, dict[str, dict[str, Any]]] | None = None,
    embedder: Embedder | None = None,
    realism: "RealismTerm | None" = None,
    use_tube: bool = False,
    discovered: Sequence[dict[str, Any]] | None = None,
    typing: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A full inventory document in the schema of `data/inventory.json`.

    It can be fed straight back into `build --inventory`, so the app renders learned
    syllables through the same path as the hand-authored ones — and shows the same
    honesty labels next to them.

    `prior` is the previous fit's learned syllables, per species and keyed by id, so a refit
    keeps its ids rather than renumbering them. `previous_fit` builds it from a written
    inventory. Passing nothing means "this is the first fit", which renumbers.

    `typing`, when given a list, is extended with one `{speciesId, recordingId, order,
    typeId}` row per observation the fit assigned to a type (see `typing_rows`). It is a
    statement about the store's observations rather than about this document, which is
    why it travels separately and lands in the store's `typing.json`.

    `discovered` is `data/discovered-species.json` — the registry `harvest --discover` writes.
    **It is where the common name of a discovered bird lives, and not passing it is why every
    one of them was called by its own id.** `inventory` is the authored file, so a species
    nobody has written about is deliberately absent from it; the fallback below then had
    nothing to fall back to and wrote `common: "zosterops_simplex"` and `scientific: ""`.
    Fourteen of the shipped corpus's twenty-six birds were named that way, in the species
    dropdown, the island headings, every cluster tag and the history strip — all of which read
    `common` and were correct to. Xeno-Canto had already told us the bird was Swinhoe's
    White-eye and the answer was on disk the whole time.
    """
    grouped: dict[str, list[SyllableObservation]] = defaultdict(list)
    for o in observations:
        grouped[o.species_id].append(o)

    # One frame for the whole harvest, not one per species: a resynthesis has to be
    # judged against the same axes every other syllable was measured on.
    frame = population_frame([o for group in grouped.values() for o in group])
    if verbose and frame is None:
        log("no per-syllable descriptors in the store — the resynthesis cosine will be "
            "taken raw, where it barely separates one call from another")

    if verbose and (embedder is not None or realism is not None):
        with_patch = sum(1 for o in observations if o.mel_patch is not None)
        log(
            f"learned components active: "
            + ", ".join(
                filter(None, [
                    "embedding typing" if embedder is not None else "",
                    f"realism w={realism.weight:.2f}" if realism is not None else "",
                    "waveguide tract" if use_tube else "",
                ])
            )
            + f" — {with_patch}/{len(observations)} observations carry a mel_patch"
        )
        if embedder is not None and with_patch < len(observations):
            log(
                f"  {len(observations) - with_patch} observations have no patch and will be "
                f"placed at the centre of the embedding, not dropped — see `critic_embedder`"
            )

    # The authored inventory wins wherever both know a bird — it is the file a person edited —
    # and the discovery registry supplies the rest.
    known: dict[str, dict[str, Any]] = {
        e["id"]: e for e in (discovered or []) if e.get("id")
    }
    known.update({sp["id"]: sp for sp in inventory.get("species", [])})
    species_out: list[dict[str, Any]] = []
    for species_id in sorted(grouped, key=lambda s: -len(grouped[s])):
        # One species is the unit of work here, as one recording is in `harvest`: the
        # species already fitted are kept and written out.
        if should_stop and should_stop():
            log("stopping: asked to")
            break
        if species_id == UNLABELLED_SPECIES:
            # Not a species: these arrived without a label, and fitting them as one would
            # invent a bird. The label-free path (`fit_unlabelled`) types them after the
            # per-species loop, when the known types exist to be matched against.
            if verbose:
                log(f"  {species_id:26} {len(grouped[species_id])} arrivals — typed by "
                    "the label-free path, not fitted as a species")
            continue
        learned = learn_species(
            species_id, grouped[species_id], descriptors, calibration,
            types=types, seed=seed, verbose=verbose, frame=frame, invert=invert,
            previous=(prior or {}).get(species_id),
            embedder=embedder, realism=realism, use_tube=use_tube,
        )
        if learned is None:
            continue
        rows = learned.pop("typing")
        if typing is not None:
            typing.extend(rows)
        base = known.get(species_id, {})
        syllable_ids = [s["id"] for s in learned["syllables"]]
        species_out.append(
            {
                "id": species_id,
                # `or` rather than a default: an entry that carries the key with an empty
                # value is the same absence as not carrying it, and it happens — a
                # Xeno-Canto record with no English name harvests as `"common": ""`.
                "common": base.get("common") or species_id,
                "scientific": base.get("scientific") or "",
                "bank": base.get("bank") or "learned",
                "summary": (
                    f"Learned from {learned['recordings']} field recordings: "
                    f"{len(syllable_ids)} syllable types fitted from "
                    f"{learned['observations']} segmented syllables. No documented "
                    "function is attached to any of them."
                ),
                "syllables": learned["syllables"],
                # A bout of the most common start type, so the app has something to play
                # before anyone asks it to improvise. Labelled invented, because the
                # sequence is ours even though the syllables are measured.
                "songs": [
                    {
                        "id": "learned_bout",
                        "label": "learned bout",
                        "gloss": "a phrase in this bird's measured syntax",
                        "function": "",
                        "confidence": "invented",
                        "refs": [],
                        "sequence": _sample_bout(learned["grammar"], syllable_ids),
                        "gaps": [],
                    }
                ],
                "grammar": learned["grammar"],
            }
        )
        species_out[-1]["songs"][0]["gaps"] = [0.06] * max(
            0, len(species_out[-1]["songs"][0]["sequence"]) - 1
        )

    return {
        "version": int(inventory.get("version", 1)),
        "note": (
            "Learned inventory. Syllable parameters are fitted to real recordings and "
            "carry the cosine between their resynthesis and the audio they came from; "
            "no syllable here has a documented function, and every sequence is our "
            "composition in a measured syntax."
        ),
        "refs": dict(inventory.get("refs", {})),
        "banks": {**inventory.get("banks", {}), "learned": "fitted to field recordings"},
        "species": species_out,
    }


MAX_REPEATS = 2


def _sample_bout(grammar: dict[str, Any], syllable_ids: Sequence[str], limit: int = 6) -> list[str]:
    """Most probable path through the measured grammar: the bird's most typical phrase.

    Self-transitions are real and common — a trill is a syllable repeating — but a
    greedy walk through one gets stuck there and reports a bout of six identical notes
    as if that were the whole repertoire. After `MAX_REPEATS` in a row the walk takes
    the next most probable transition instead, which is a presentational choice, not a
    claim: the measured probabilities are written out untouched in `grammar`.
    """
    starts = grammar.get("start") or list(syllable_ids[:1])
    if not starts:
        return []
    sequence = [starts[0]]
    for _ in range(limit - 1):
        row = grammar.get("transitions", {}).get(sequence[-1], {})
        options = [k for k in row if k != END]
        if not options:
            break
        run = 1
        while run < len(sequence) and sequence[-1 - run] == sequence[-1]:
            run += 1
        if run >= MAX_REPEATS:
            options = [k for k in options if k != sequence[-1]]
        if not options:
            break
        sequence.append(options[0])
    return sequence


def merge_learned_inventory(base: dict[str, Any], learned: dict[str, Any]) -> dict[str, Any]:
    """The hand-authored inventory with each species' learned types appended to it.

    A learned-only document is honest but lossy: every documented function goes with it,
    including the three that playback experiments actually established (§8.5). Since the
    learned ids are `L00`, `L01`, … and no authored syllable is named that way, the two
    repertoires can sit in one species without colliding — the documented calls keep
    their citations and confidence, the learned types arrive as `unlabelled`, and the
    interface already draws that distinction.

    The measured grammar comes across as-is. It only ever mentions learned ids, so
    improvising from it cannot silently put a documented syllable in a sequence nobody
    observed.
    """
    fitted = {sp["id"]: sp for sp in learned.get("species", [])}
    species_out: list[dict[str, Any]] = []
    for base_sp in base.get("species", []):
        sp = dict(base_sp)
        add = fitted.pop(sp["id"], None)
        if add:
            sp["syllables"] = list(sp.get("syllables", [])) + list(add.get("syllables", []))
            sp["songs"] = list(sp.get("songs", [])) + list(add.get("songs", []))
            if add.get("grammar"):
                sp["grammar"] = add["grammar"]
            sp["learnedFrom"] = add.get("summary", "")
        species_out.append(sp)
    # A species that was harvested but is not in the authored inventory keeps its
    # learned-only entry rather than being dropped.
    species_out.extend(fitted.values())

    return {
        "version": int(base.get("version", 1)),
        "note": (
            base.get("note", "")
            + "  Extended with syllable types fitted to field recordings: their ids start "
            "with `L`, they carry the cosine between their resynthesis and the audio "
            "they came from, and none of them has a documented function."
        ).strip(),
        "refs": dict(base.get("refs", {})),
        "banks": {**base.get("banks", {}), **learned.get("banks", {})},
        "species": species_out,
    }


def write_learned_inventory(path: Path, document: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(document, indent=1), encoding="utf-8")


# --- self-test ---------------------------------------------------------------------


def self_test(verbose: bool = True) -> None:
    """Check the learned-critic plumbing of docs/09 without needing torch.

    The critic is duck-typed everywhere it is used (`embed`, `realism_unit`), so a stub with
    a known answer tests every wire: whether the typing space is really the one that changed,
    whether `w = 0` is exactly the old objective, and whether an observation with no patch is
    handled rather than silently dropped. Those are the three ways this integration could be
    wrong while still running.
    """

    def observation(hz: float, dur: float, patch: bool = True, **kw: Any) -> SyllableObservation:
        return SyllableObservation(
            species_id=kw.pop("species_id", "test_bird"),
            recording_id=kw.pop("recording_id", "r0"),
            order=kw.pop("order", 0),
            start=0.0,
            dur=dur,
            level=0.9,
            attack=0.006,
            hold=True,
            contour=[[0.0, hz], [1.0, hz * 1.1]],
            am=0.0,
            am_depth=0.0,
            vib_rate=0.0,
            vib_depth=0.0,
            harmonic=0.2,
            timbre="pure",
            flatness=0.05,
            gap_before=0.05,
            mel_patch=(
                np.full(features.PATCH_SHAPE, hz / 1000.0, dtype=np.float16) if patch else None
            ),
            descriptor=[0.0] * features.DIM,
            **kw,
        )

    observations = [observation(2000.0 + 500 * i, 0.05 + 0.01 * i) for i in range(6)]

    # 1. With no embedder, `typing_space` must be exactly the standardised stack of
    #    `_observation_vector` — the computation `fit_types` and `choose_k` used to inline.
    #    If this drifts, every previously fitted repertoire silently stops being reproducible.
    manual = np.stack([_observation_vector(o) for o in observations])
    manual = (manual - manual.mean(axis=0)) / np.maximum(manual.std(axis=0), 1e-6)
    assert np.array_equal(typing_space(observations), manual), "typing_space changed the default"

    # 2. An embedder must actually be used, and a badly shaped one must be caught rather than
    #    broadcast into nonsense.
    space = typing_space(observations, lambda obs: np.arange(len(obs) * 4).reshape(len(obs), 4))
    assert space.shape == (6, 4)
    for bad in (lambda obs: np.zeros((len(obs) + 1, 4)), lambda obs: np.zeros(len(obs))):
        try:
            typing_space(observations, bad)
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError("typing_space accepted an embedder of the wrong shape")

    # 3. `critic_embedder` must keep row alignment and place a patch-less observation at the
    #    centre rather than dropping it — dropping would desynchronise `observations` from the
    #    labels `learn_grammar` indexes by position, and silently shrink the repertoire.
    class StubCritic:
        """Embeds a patch as (mean, first value, 0...); realism is minus the patch mean."""

        def embed(self, patches: np.ndarray) -> np.ndarray:
            p = np.asarray(patches, dtype=np.float64)
            out = np.zeros((p.shape[0], 4))
            out[:, 0] = p.mean(axis=(1, 2))
            out[:, 1] = p[:, 0, 0]
            return out

        def realism_unit(self, patches: np.ndarray) -> np.ndarray:
            p = np.atleast_3d(np.asarray(patches, dtype=np.float64))
            return -p.mean(axis=(1, 2))

    stub = StubCritic()
    mixed = [*observations[:4], observation(9000.0, 0.09, patch=False), *observations[4:]]
    z = critic_embedder(stub)(mixed)
    assert z.shape == (len(mixed), 4), f"embedder lost rows: {z.shape}"
    assert np.allclose(z[4], z[[0, 1, 2, 3, 5, 6]].mean(axis=0)), (
        "a patch-less observation must land at the mean embedding"
    )
    assert np.isclose(z[0, 0], 2.0), "embeddings are misaligned with their observations"

    # 4. **`w = 0` must be bit-identical to the objective that shipped before the critic.**
    #    This is what makes docs/09's before/after table a comparison rather than two
    #    unrelated runs.
    audio = np.sin(2 * np.pi * 3000.0 * np.arange(4096) / features.SAMPLE_RATE)
    assert RealismTerm(stub, 0.0).blend(0.42, audio) == 0.42
    assert RealismTerm(None, 0.9).blend(0.42, audio) == 0.42, "no critic must be a no-op"

    # 5. ...and `w = 1` must be exactly the critic, with the cosine gone.
    patch = features.mel_patch(audio)
    expected = float(np.asarray(stub.realism_unit(patch)).ravel()[0])
    assert np.isclose(RealismTerm(stub, 1.0).blend(0.42, audio), expected)
    # a middling weight blends linearly, and clipping keeps w in range
    half = RealismTerm(stub, 0.5).blend(0.42, audio)
    assert np.isclose(half, 0.5 * 0.42 + 0.5 * expected)
    assert RealismTerm(stub, 5.0).weight == 1.0 and RealismTerm(stub, -1.0).weight == 0.0

    # 6. `_score` itself: passing no realism term must leave it exactly the cosine.
    syllable = {"id": "T", "dur": 0.06, "level": 0.9, "timbre": "pure",
                "contour": [[0.0, 3000.0], [1.0, 3200.0]], "attack": 0.006, "hold": True,
                "harmonic": 0.2}
    reference = _unit(np.ones(features.DIM))
    plain = _score(syllable, reference, None, None, features.SAMPLE_RATE)
    assert plain == _score(syllable, reference, None, None, features.SAMPLE_RATE, None)
    assert plain == _score(syllable, reference, None, None, features.SAMPLE_RATE,
                           RealismTerm(stub, 0.0))
    blended = _score(syllable, reference, None, None, features.SAMPLE_RATE,
                     RealismTerm(stub, 1.0))
    assert blended != plain, "a w=1 realism term must change the score"

    # 7. Patches must survive `to_dict` being JSON-serialisable — they go to a binary sidecar,
    #    and an ndarray left in the dict would make `harvest.HarvestStore.save` raise.
    d = observations[0].to_dict()
    assert "mel_patch" not in d, "mel_patch must not reach syllables.jsonl"
    json.dumps(d)
    assert SyllableObservation.from_dict(d).mel_patch is None

    # 8. The novelty flag survives the JSON round trip in both directions: a flagged
    #    observation stays flagged through save/load (or ingest would mark a syllable that
    #    the next load quietly unmarked), and a row written before the flag existed —
    #    every store on disk today — loads as False rather than raising.
    flagged = observation(2500.0, 0.07)
    flagged.novel = True
    assert SyllableObservation.from_dict(flagged.to_dict()).novel is True
    legacy = flagged.to_dict()
    del legacy["novel"]
    assert SyllableObservation.from_dict(legacy).novel is False

    # 9. `type_sequences` breaks bouts at the same one-second gap the grammar does, and
    #    `mine_chunks` finds a planted syntax while its shuffled control does not — the
    #    pmi filter is exactly what a shuffle collapses (see its docstring).
    gap_obs = [
        observation(3000.0, 0.05, species_id="s", recording_id="r", order=i)
        for i in range(4)
    ]
    gap_obs[2].gap_before = 2.0
    rows = [
        {"speciesId": "s", "recordingId": "r", "order": i, "typeId": f"T{i}"}
        for i in range(4)
    ]
    assert type_sequences(gap_obs, rows) == [("s", ["T0", "T1"]), ("s", ["T2", "T3"])]

    rng = np.random.default_rng(0)
    planted = [("sp", ["A", "B", "C", "D"]) for _ in range(40)]
    # length-2 filler: contributes unigrams and bigrams to the baseline without adding
    # 4-gram noise of its own, so the planted chunk's pmi is legible
    planted += [
        ("sp", [str(v) for v in rng.integers(10, size=2)]) for _ in range(10)
    ]
    chunks = mine_chunks(planted)
    assert chunks and chunks[0]["sequence"] == ["A", "B", "C", "D"], (
        f"planted A->B->C->D not found: {chunks[:2]}"
    )
    assert chunks[0]["count"] == 40 and chunks[0]["species"] == ["sp"]
    shuffled = [("sp", list(rng.permutation(seq))) for _, seq in planted]
    assert not any(c["sequence"] == ["A", "B", "C", "D"] for c in mine_chunks(shuffled)), (
        "the shuffled control must not reproduce the planted chunk"
    )

    # 10. `learn_unlabelled`: an arrival near a known type centroid inherits its id as
    #     evidence (empty syllable — the type already exists); the remainder clusters
    #     into `U*` candidates carrying the base fields only.
    def angle_embed(obs: Sequence[SyllableObservation]) -> np.ndarray:
        a = np.log2([max(50.0, o.contour[0][1]) for o in obs])
        return np.stack([np.cos(a), np.sin(a), np.zeros_like(a)], axis=1)

    stub_novelty = type("StubNovelty", (), {"threshold": 0.05})()
    known = {"sp/L00": angle_embed([observation(2000.0, 0.05)])[0]}
    arrivals = [
        observation(2000.0 * (1.0 + 0.002 * i), 0.05, species_id="unlabelled",
                    recording_id=f"u{i // 4}", order=i % 4)
        for i in range(12)
    ]
    arrivals += [
        observation(9000.0 * (1.0 + 0.002 * i), 0.09, species_id="unlabelled",
                    recording_id=f"v{i // 4}", order=i % 4)
        for i in range(16)
    ]
    found = learn_unlabelled(
        arrivals, angle_embed, stub_novelty, known, seed=0
    )
    inherited = [t for t in found if not t.syllable]
    candidates = [t for t in found if t.syllable]
    assert len(inherited) == 1 and inherited[0].id == "sp/L00", (
        f"inheritance wrong: {[t.id for t in found]}"
    )
    assert len(inherited[0].members) == 12
    assert candidates and all(t.id.startswith("U") for t in candidates), (
        f"candidates wrong: {[t.id for t in candidates]}"
    )
    assert sum(len(t.members) for t in candidates) >= 14
    assert all(t.syllable["confidence"] == "unlabelled" for t in candidates)
    # ...and below the observation floor the pool is left alone entirely.
    assert learn_unlabelled(arrivals[:4], angle_embed, stub_novelty, known) == []

    # 11. Song-level typing: two planted motifs (one hidden under a trill's repeats, one
    #     with a syllable dropped) must cluster into two song types while singletons stay
    #     unplaced — and the global-permutation control must find nothing, or the
    #     clustering is reporting chance string similarity as syntax. The alphabet is 40
    #     types with a flat filler distribution because that is what a real species'
    #     typing produces; at toy alphabets or a skewed bag, chance strings are
    #     genuinely edit-close and the control fails honestly.
    vocab = [f"T{i:02d}" for i in range(40)]
    m1, m2 = ("T00", "T01", "T02"), ("T10", "T11", "T12", "T10", "T11")
    songs = [("sp", ("r", i), [m1[0]] * 3 + list(m1[1:])) for i in range(8)]
    songs += [("sp", ("r", 100 + i), list(m1) + [m1[-1]]) for i in range(4)]
    songs += [("sp", ("r", 200 + i), list(m2)) for i in range(8)]
    songs += [
        ("sp", ("r", 300 + i), [vocab[v] for v in rng.integers(40, size=int(n))])
        for i, n in enumerate(rng.integers(3, 9, size=60))
    ]
    found = cluster_song_types(songs, min_cluster_size=4)["sp"]
    assert len(found["types"]) == 2, (
        f"planted motifs not recovered: {found['types']}"
    )
    assert {tuple(t["sequence"]) for t in found["types"]} == {
        m1, m2,
    }, f"run-collapse or edit-tolerant matching wrong: {found['types']}"
    # Edit tolerance may pull a chance look-alike in, never plant one out.
    assert found["types"][0]["count"] >= 12  # trilled and un-trilled m1 together
    assert found["types"][1]["count"] >= 8
    shuffled_songs: list[tuple[str, tuple[str, int], list[str]]] = []
    pool = [t for _, _, seq in songs for t in seq]
    pool = list(rng.permutation(pool))
    pos = 0
    for _, key, seq in songs:
        shuffled_songs.append(("sp", key, pool[pos : pos + len(seq)]))
        pos += len(seq)
    control = cluster_song_types(shuffled_songs, min_cluster_size=4)["sp"]
    assert not control["types"], f"permutation control found song types: {control['types']}"
    # `type_sequences` and `bout_sequences` must agree bout for bout — they are one code
    # path, and a drift between them is a grammar mined over different strings than the
    # song types were clustered from.
    keyed = bout_sequences(gap_obs, rows)
    assert [(sid, seq) for sid, _, seq in keyed] == type_sequences(gap_obs, rows)
    assert [key for _, key, _ in keyed] == [("r", 0), ("r", 2)]

    if verbose:
        print(
            f"learn self-test ok: typing space unchanged by default, "
            f"{len(mixed)} rows aligned through the embedder, "
            f"w=0 exactly the old objective, w=1 exactly the critic"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
