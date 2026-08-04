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
import os
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
from scipy import signal
from sklearn.cluster import KMeans

from . import density, features, respiration, syrinx, twovoice
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

#: The band the segmentation is allowed to see, and it is `F0_MIN_HZ..F0_MAX_HZ` on
#: purpose: **the band every description below already restricts itself to.**
#:
#: This was full-band until it was measured, and the measurement is the reason it is not.
#: `_segments` thresholds at `ONSET_REL` of the recording's own envelope peak, so whatever
#: is loudest in a file decides what counts as a syllable — while `track_f0` and
#: `measure_harmonics` throw away everything outside 400 Hz - 12 kHz. On a recording with
#: wind, handling noise or traffic rumble under it those two facts disagree, and the
#: segmenter wins: it slices the rumble, and the description then reads whatever tonal
#: haze happens to sit inside those spans.
#:
#: The owner found one by ear (INAT227259, "just noise, no bird call"). Measured, **98.7 %
#: of that file's energy is below 400 Hz** — the segmenter was thresholding almost entirely
#: on content nothing downstream ever looks at, and it is not a rare shape. Over a
#: 200-recording sample of the iNat cache, the share of energy under 400 Hz runs
#: median 35.5 %, p75 86.8 %, p90 97.5 %: **23 % of recordings put over nine tenths of
#: their energy outside the band that describes them**, and that is the population whose
#: segmentation was being decided by rumble.
#:
#: This is why no per-syllable filter could catch that recording, and three were tried and
#: measured dead on it (HANDOFF, this round): an absolute SNR floor would need 19 dB when
#: the corpus median is 17.1; its spectral flatness is at the 21st percentile, i.e. it
#: reads as *more* tonal than average; and Perch 2.0 ranks it at the 88th percentile of
#: bird confidence in the cache. All three were asking "is this syllable a bird" about
#: syllables that had already been chosen by the noise.
#:
#: `None` restores the full-band envelope, which is what every store harvested before this
#: constant existed used. It is not a preference — it is how `quality.remeasure_store`
#: reproduces such a store's segmentation exactly instead of misattributing one syllable's
#: measurement to another.
SEGMENT_BAND_HZ: tuple[float, float] | None = (F0_MIN_HZ, F0_MAX_HZ)

# --- ingest-time quality -------------------------------------------------------------

#: Full-scale threshold for the clipping flag. Integer-sourced audio decoded to float
#: pins clipped samples at +-1.0 (16-bit: 32767/32768 = 0.99997), and lossy decoders
#: plus the resampler's overshoot can push a clipped region *past* 1.0, so 0.999
#: catches both without flagging an honest peak. Measured on the raw decoded samples,
#: before `peak_normalise` — afterwards every recording's loudest sample is 0.9 by
#: construction and the evidence is gone.
CLIP_FULL_SCALE = 0.999
#: Share of a syllable's samples at full scale that flags it as clipped. One sample is
#: nothing; a sustained run at the rail is a recorder that ran out of headroom.
CLIP_SHARE_MIN = 0.001
#: The SNR that counts as full weight in the fit (`quality_weight`). 20 dB is a factor
#: of ten in amplitude: a syllable that far above the floor is dominated by the bird,
#: not by the hedgerow.
SNR_FULL_WEIGHT_DB = 20.0


def _noise_floor(env: np.ndarray, segments: Sequence[tuple[int, int]]) -> float:
    """The recording's noise floor: median frame RMS outside every segmented syllable.

    The estimator is the median of the *outside* frames rather than a low percentile
    of all frames, because a dense song leaves almost no low-percentile frames that
    are not syllable — a nightingale mid-bout is mostly bird, and a percentile of
    everything would report the quiet end of the song itself as "noise". The median
    rather than the minimum because the minimum is one lucky frame, while the quiet
    texture between phrases is the level the floor actually sits at. When the
    segmenter left fewer than eight outside frames the fallback is the 10th
    percentile of all frames: a recording that is nearly all bird still has some
    quieter texture at its edges, and a biased-low floor only ever *raises* the
    reported SNR of everything in that one recording uniformly.
    """
    if not env.size:
        return 0.0
    outside = np.ones(env.size, dtype=bool)
    for s0, s1 in segments:
        lo = max(0, s0 // ENV_HOP)
        hi = min(env.size, (s1 + ENV_HOP - 1) // ENV_HOP)
        outside[lo:hi] = False
    rest = env[outside]
    if rest.size >= 8:
        return float(np.median(rest))
    return float(np.percentile(env, 10))

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
    #: Ingest-time quality evidence, measured by `extract_syllables` in the one window
    #: where the audio exists. `snr` is the syllable's RMS against the recording's
    #: noise floor in dB (see `_noise_floor`); `clipped` is True when more than
    #: `CLIP_SHARE_MIN` of the syllable's raw samples sat at full scale. Both are
    #: **scores, never filters** — denoising was considered and rejected because it
    #: erases the fricative signal with the noise, so a bad recording is weighed, not
    #: deleted. None on every row harvested before these fields existed: unmeasured,
    #: which `quality_weight` treats as neutral, not as bad.
    snr: float | None = None
    clipped: bool | None = None
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


def band_limit(x: np.ndarray, sample_rate: int, lo: float, hi: float) -> np.ndarray:
    """`x` with everything outside `lo..hi` Hz taken out. Zero phase, same length.

    **A filter and not a spectral mask, and the first attempt was the mask.** Weighting
    `ENV_FRAME`-point rfft bins looks equivalent and is not: 512 points at 44.1 kHz is 86 Hz
    per bin, so `F0_MIN_HZ` is bin 4.6 and a Hann main lobe is four bins wide — the band edge
    is as wide as the band's own lower reach. Measured on `self_test`'s fixture (a 60 Hz
    rumble at 0.9 under four 5.2 kHz chirps at 0.05), the mask leaked enough rumble to find
    **11 segments where there are four**, and the envelope's peak-to-median ratio was 15
    against this filter's 234 060. A Butterworth skirt has stopband rejection; a window's
    sidelobes do not.

    `sosfiltfilt`, so the filter is zero-phase: the whole point of this pass is *when* a
    syllable starts, and a causal filter would move every onset by its own group delay.
    """
    nyquist = 0.5 * sample_rate
    low = max(lo, 1.0) / nyquist
    high = min(hi, 0.999 * nyquist) / nyquist
    if low >= high:  # a rate too low to have the band at all
        return np.asarray(x, dtype=np.float64)
    if high >= 0.999:
        sos = signal.butter(4, low, btype="highpass", output="sos")
    else:
        sos = signal.butter(4, [low, high], btype="bandpass", output="sos")
    # filtfilt needs more samples than its padding; a fragment shorter than that is not
    # something the segmenter can use anyway.
    if x.size <= 3 * (sos.shape[0] * 2 + 1):
        return np.asarray(x, dtype=np.float64)
    return np.asarray(signal.sosfiltfilt(sos, np.asarray(x, dtype=np.float64)))


def band_envelope(x: np.ndarray, sample_rate: int, lo: float, hi: float) -> np.ndarray:
    """`envelope`, but hearing only `lo..hi` Hz. Same frames, same units, same length.

    Literally `envelope(band_limit(...))`, which is what keeps it comparable: it is the same
    rectangular frame RMS in the same units, measured on the same frame grid, of a signal
    with the out-of-band content removed. That matters because `_noise_floor` reads this
    envelope while `snr` divides a segment's level by it — the two have to be the same
    measurement of the same thing in the same band, or the ratio is a unit conversion
    wearing a dB sign.

    Cost: measured at 0.03 s for a 90-second recording on top of the 0.07 s the plain RMS
    already takes, against the hundreds of milliseconds describing that recording costs.
    """
    return envelope(band_limit(x, sample_rate, lo, hi))


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
    segment_band: tuple[float, float] | None = SEGMENT_BAND_HZ,
) -> list[SyllableObservation]:
    """Segment a recording and describe each syllable in syrinx parameters.

    `segment_band` is the band the segmentation and its noise floor are measured in; see
    `SEGMENT_BAND_HZ` for why it is not the whole spectrum, and pass `None` to reproduce a
    store harvested before it existed.
    """
    if max_seconds is not None:
        mono = mono[: int(max_seconds * sample_rate)]
    if mono.size < F0_FRAME:
        return []
    # Clipping is read off the raw decode: `peak_normalise` rescales the recording so
    # its loudest sample is 0.9, which erases exactly the evidence the flag needs.
    unscaled = mono
    mono = peak_normalise(mono)
    env = (
        envelope(mono)
        if segment_band is None
        else band_envelope(mono, sample_rate, *segment_band)
    )
    if not env.size:
        return []
    env_peak = float(env.max()) or 1.0

    segments = _segments(env, sample_rate)
    noise_floor = _noise_floor(env, segments)
    out: list[SyllableObservation] = []
    previous_end = 0.0
    for order, (s0, s1) in enumerate(segments):
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

        # Quality, measured while the samples exist. The SNR is a ratio inside one
        # recording, so the peak normalisation above cancels out of it; the clipping
        # flag cannot use the normalised copy at all (see `unscaled`).
        #
        # The numerator has to be read in the same band as `noise_floor`, which comes from
        # `env`. Dividing a full-band segment level by a 400 Hz - 12 kHz floor is how you
        # report a recording that is 98.7 % rumble as having a healthy SNR — the numerator
        # counts the rumble and the denominator does not, so the worse the rumble the better
        # the number. That is measured, not hypothetical: it is why INAT227259's stored SNR
        # is a respectable 11.5 dB median.
        # On the legacy full-band path both sides were already the same band, so the
        # formula there is left exactly as it was — `quality.remeasure_store` reproduces
        # that path's numbers on 188 986 rows of the existing corpus, and "exactly" is the
        # only property that makes such a pass safe to write back.
        band_frames = (
            np.zeros(0)
            if segment_band is None
            else env[
                max(0, s0 // ENV_HOP) : max(
                    s0 // ENV_HOP + 1, (s1 + ENV_HOP - 1) // ENV_HOP
                )
            ]
        )
        seg_rms = (
            float(np.sqrt(np.mean(band_frames * band_frames)))
            if band_frames.size
            else (float(np.sqrt(np.mean(seg * seg))) if seg.size else 0.0)
        )
        snr = 20.0 * math.log10(max(seg_rms, 1.0e-9) / max(noise_floor, 1.0e-9))
        raw = unscaled[s0:s1]
        clipped = bool(np.mean(np.abs(raw) >= CLIP_FULL_SCALE) > CLIP_SHARE_MIN)

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
                snr=round(snr, 2),
                clipped=clipped,
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
            # Name the batch. This is reached with one species' observations far more often
            # than with a whole store's, and the bare message read as "the store is broken"
            # when the truth was "these 1 758 Common Cuckoo syllables predate patches".
            # Callers that can fall back are expected to check before calling (see
            # `learn_species`); this stays an error because silently embedding nothing at
            # the origin would invent a type out of no evidence.
            species = sorted({o.species_id for o in observations})
            where = species[0] if len(species) == 1 else f"{len(species)} species"
            raise ValueError(
                f"none of the {len(observations)} observations for {where} carries a "
                "mel_patch — cannot embed. Patches are written at harvest time and cannot "
                "be recovered afterwards; re-harvest into a new store to gain them."
            )
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


class MelTargetTerm:
    """The type's mean member mel-path as a fit target, blended into `_score` exactly
    the way `RealismTerm` blends the critic.

    `score = (1 - w) * cosine + w * mel-path similarity`. docs/19 measured that the
    28-d cosine does not rank audible distortion (Pearson 0.106 / Spearman 0.100
    against channel-normalised MCD over 200 types of the debug-100 store — neither
    distinguishable from zero): it is a clustering statistic being used as a fidelity
    metric. The mel-path is the time-resolved spectral summary the harvest kept
    (`SyllableObservation.mel_path`: knots x 26 log-mel energies, `features.mel_path`),
    the same family of quantity MCD measures, so an objective built on it optimises
    what the bench actually listens to. The cosine never leaves the blend: it is the
    ungameable *clustering* guardrail, the role docs/19 §19.3 says it is proven for —
    and the reported `resynthesis_cosine` is still measured with the pure cosine, so a
    mel-driven fit that collapses the descriptor match stays visible.

    **The similarity is `exp(-LSD)`, not a cosine over the flattened paths** — and that
    choice was measured, not aesthetic. The cosine was tried first: on a render whose
    back half is low-passed at 2.5 kHz (plainly audible; specbench's self-test
    fixture, +77.9 dB MCD) the 104-d path cosine drops 0.017 — no more than the 28-d
    cosine's 0.015 on the same damage, because a cosine in 104 dimensions where most
    of the structure is shared compresses every difference into the same sliver below
    1. Standardising the cells in the store's population frame barely moved it
    (0.975 vs 0.983). The term would have inherited the exact blindness it was built
    to fix. LSD — mean over knots of the per-knot RMS log-mel difference, the
    multi-resolution-STFT convention applied at mel resolution — is MCD one step
    earlier in the transform (before the DCT), so the objective and the audible
    metric become the same quantity, which is the whole point of docs/19 §19.3's
    promotion. On the same fixtures it reads 0.78 log units for the damaged half and
    0.47 for an 800 Hz formant shift where the 28-d cosine moves 0.003. `exp(-LSD)`
    maps that into (0, 1] with 1 = identical: the cosine's own working range, so `w`
    keeps one meaning along the blend — the commensurability argument `RealismTerm`
    makes for `realism_unit`, ruling out the raw, unbounded -LSD.

    Two alignment decisions, both following existing precedent:

    * **Bands**: only the 23 bands at or below `features.PATCH_LP_HZ` (15 kHz) enter
      the distance — the exact cut the critic's patch makes, for the exact measured
      reason (docs/09 §9.5): xeno-canto's mp3s cut near 16 kHz, so the top three
      bands of a stored path measure the codec, not the bird, and an objective that
      matched them would teach the fit to reproduce an mp3. (The iNat half was
      checked too: field noise keeps its top bands off the floor, so no further cut
      is needed.) Both sides are centred over all 26 bands by `features.mel_path`
      first and cut afterwards, so the centring convention is identical on both.
    * **Time**: no DTW. Both sides are resampled onto the same knot fractions of
      their own duration, so time is aligned by construction — the assumption
      `features.mel_path` and specbench's `align_pair` already make.

    The target is the *mean of the type's members'* mel-paths — the same cluster-level
    reference the 28-d objective uses (`learn_species`' `real[i]`), so both terms of
    the blend aim at the same notion of "the type". A type whose members predate
    `mel_path` (stores harvested before the field existed) gets no term and the
    objective falls back to the pure cosine — the same no-op rule as `RealismTerm`
    with no critic. At `w = 0` the blend is bit-identical to the objective that
    shipped before this class existed, which is what keeps every gate that reads
    `_score` unchanged by default.
    """

    def __init__(
        self,
        target: np.ndarray | None,
        weight: float,
        sample_rate: int = features.SAMPLE_RATE,
    ):
        self.weight = float(np.clip(weight, 0.0, 1.0))
        self.sample_rate = sample_rate
        self.target = None if target is None else np.asarray(target, dtype=np.float64)
        self.calls = 0

    def similarity(self, audio: np.ndarray) -> float:
        """The unblended mel-target score of one render: `exp(-LSD)` in (0, 1].

        0 (not -1) when the render has no voiced frame — `features.mel_path` returns
        zeros, LSD against any real target is then the distance to silence, and the
        exponential already floors the answer at 0; no special case is needed beyond
        computing it. NaN when the term has no target: callers should have used
        `mel_target_term`, which returns None in that case so the question never
        arises.
        """
        if self.target is None:
            return math.nan
        path = features.mel_path(audio, sample_rate=self.sample_rate)
        d = path[:, : features.PATCH_MEL] - self.target
        lsd = float(np.mean(np.sqrt(np.mean(d * d, axis=1))))
        return float(np.exp(-lsd))

    def blend(self, cosine: float, audio: np.ndarray) -> float:
        if self.weight <= 0.0 or self.target is None:
            return cosine
        self.calls += 1
        return (1.0 - self.weight) * cosine + self.weight * self.similarity(audio)


def mel_target_term(
    members: Sequence[SyllableObservation],
    weight: float,
    sample_rate: int = features.SAMPLE_RATE,
) -> "MelTargetTerm | None":
    """The per-type mel target for the fit loop, or None when there is nothing to aim at.

    None — not a zero-weight term — so `_score` stays on exactly its old code path
    when the term is off (w = 0, the default) or when no member carries a mel-path.
    The target is the mean of the members' stored paths, cut to the bands at or below
    `features.PATCH_LP_HZ` (the codec-artifact cut the term's docstring argues for);
    the paths were rounded to 3 decimals at harvest, which costs at most ~1e-3 of
    log-energy per cell — nothing next to the tenths of log-units of spectral
    disagreement the term exists to see.
    """
    if weight <= 0.0:
        return None
    rows = [o.mel_path for o in members if o.mel_path]
    if not rows:
        return None
    target = np.mean(
        np.asarray(rows, dtype=np.float64).reshape(len(rows), -1, features.N_MEL), axis=0
    )
    return MelTargetTerm(
        target[:, : features.PATCH_MEL], weight, sample_rate=sample_rate
    )


# --- quality-weighted fitting --------------------------------------------------------


def quality_weight(o: SyllableObservation) -> float:
    """How much this observation's measurements count in a fit, in [0, 1].

    `snr / SNR_FULL_WEIGHT_DB` clamped to [0, 1]: a syllable 20 dB above its
    recording's noise floor counts in full, one at or below the floor not at all. A
    clipped syllable weighs zero — its samples ran out of headroom, so its spectrum is
    the recorder's, not the bird's. Zero weight excludes a member from the type's
    *parameter median and exemplar reference*, never from the type itself: it still
    counts in `members`, and nothing anywhere deletes it — quality is a weight, not a
    filter (denoising was rejected for the same reason: it erases the fricative
    signal with the noise).

    Unmeasured is neutral, not bad: an observation with no `snr` — every row of every
    store harvested before the field existed — weighs 1.0, so a legacy store fits
    bit-identically to the fit that shipped before weighting.
    """
    if o.clipped:
        return 0.0
    if o.snr is None:
        return 1.0
    return float(np.clip(o.snr / SNR_FULL_WEIGHT_DB, 0.0, 1.0))


def _member_weights(members: Sequence[SyllableObservation]) -> np.ndarray:
    """One `quality_weight` per member, with the degenerate case neutralised.

    A type whose members all weigh zero — every one clipped, or all of them at the
    noise floor — falls back to uniform weights: no evidence about *which* member is
    best is not a reason to fit nothing, and the alternative is a median over an
    empty set. The `membersClean` count in the learned block still reports what
    happened.
    """
    w = np.asarray([quality_weight(o) for o in members], dtype=np.float64)
    return w if w.sum() > 0.0 else np.ones(len(members), dtype=np.float64)


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """The value at which the sorted cumulative weight reaches its half.

    Deterministic by construction: the sort is stable and an exact half takes the
    lower of the two middle values (`searchsorted` from the left), so a refit on the
    same store lands on the same number.
    """
    order = np.argsort(values, kind="stable")
    v, w = values[order], weights[order]
    return float(v[np.searchsorted(np.cumsum(w), 0.5 * w.sum())])


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
    mel: "MelTargetTerm | None" = None,
) -> float:
    """How good this syllable's resynthesis is: the 28-d cosine, optionally blended.

    Without `realism` or `mel` this is exactly what it always was — the cosine between
    the resynthesis and the real audio the type stands for. With them, the learned
    critic gets a share `w` of the objective (docs/09 §9.3 step 5) and the type's mean
    member mel-path gets its own share (docs/19 §19.3). Terms compose in the order
    cosine -> realism -> mel, each blending over whatever the previous one returned;
    at their default weights (0) both are no-ops. The cosine never goes away
    entirely, so there is always one term neither the critic nor the target can game.
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
    if realism is not None:
        cosine = realism.blend(cosine, audio)
    if mel is not None:
        cosine = mel.blend(cosine, audio)
    return cosine


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
    mel: "MelTargetTerm | None" = None,
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
    before = _score(t.syllable, reference, calibration, frame, sample_rate, realism, mel)
    best = before
    for _ in range(max(1, passes)):
        improved = False
        for key, candidates in _SEARCH_AXES:
            current = _axis_value(t.syllable, key)
            for value in candidates:
                if value == current:
                    continue
                trial = _with(t.syllable, key, value)
                score = _score(trial, reference, calibration, frame, sample_rate,
                               realism, mel)
                if score > best + 1.0e-4:
                    best = score
                    t.syllable = trial
                    current = value
                    improved = True
        if not improved:
            break
    return before, best


# --- the noise-first start (docs/16 §16.7 piece 3) -----------------------------------

#: The flatness gate for the fricative class. The harvest's own distribution
#: (syrinx.py's NOISE_GAIN calibration note) runs median 0.044 with p90 at 0.141, so
#: a type whose median member flatness clears 0.14 is in the noisiest tenth of the
#: corpus — a noise-burst call, not a tone. Below the gate the tonal start is left
#: alone, and the gate itself is judged on the probe's bench (gated vs all).
FRICATIVE_FLATNESS_GATE = 0.14
FRICATIVE_NOISE_GRID = [0.25, 0.4, 0.6, 0.85]
FRICATIVE_SEED_QS = [2.0, 4.0, 8.0]
FRICATIVE_SEED_GAINS = [0.5, 1.0, 2.0]


def _fricative_seed_formants(mfcc_mean: np.ndarray, n: int = 2) -> list[list[float]]:
    """Top-n detrended mel-envelope peaks as `[hz, q, gain]` formant seeds.

    The only spectral evidence left after harvest deletes the audio: the type's mean
    MFCC inverted to a 26-band log envelope — the same move `measure_trachea_f1`
    makes, detrended the same way so the peaks, not the tilt, are picked.
    """
    env = features.mel_envelope(np.asarray(mfcc_mean, dtype=float))
    hz = features.mel_centres_hz()
    k = 7
    pad = np.pad(env, (k // 2, k // 2), mode="edge")
    smooth = np.convolve(pad, np.ones(k) / k, mode="valid")[: env.size]
    peaks = env - smooth
    chosen: list[float] = []
    for i in np.argsort(-peaks):
        f = float(hz[i])
        if f < 500.0 or f > 9000.0 or peaks[i] <= 0.0:
            continue
        if any(abs(np.log2(f / c)) < 0.5 for c in chosen):
            continue
        chosen.append(f)
        if len(chosen) >= n:
            break
    return [[f, 4.0, 1.0] for f in sorted(chosen)]


def fricative_seed(
    t: LearnedType,
    reference: np.ndarray,
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    sample_rate: int = features.SAMPLE_RATE,
    mel: "MelTargetTerm | None" = None,
) -> tuple[float, float] | None:
    """The noise-first start for the fricative class: try "noise, shaped how" against
    the tonal fit, keep it only where the fit's own number says it wins.

    Returns (before, shipped score), or None when the type is not fricative-class —
    so the caller can count. The candidates, all judged by `_score` against the same
    reference the gesture search used: the fitted syllable flagged `fricative`, the
    noise axis re-searched under the flag, then the formant set re-seeded from the
    type's mean-MFCC envelope peaks (replacing the species trachea set, and
    extending it) over a small q x gain grid. The flag ships only when the seeded
    candidate beats the syllable as fitted — the pre-registered rule of docs/16
    §16.7, and the reason the two best tonal fits on the probe bench (oropendola
    L02, nuthatch L00) keep their old shape: rerouting good noise costs more than
    shaping it buys when the mixed path was already reproducing the call.
    """
    members = [o for o in t.members if o.descriptor]
    if len(members) < 2:
        return None
    if float(np.median([o.flatness for o in members])) < FRICATIVE_FLATNESS_GATE:
        return None
    before = _score(t.syllable, reference, calibration, frame, sample_rate, mel=mel)

    best_syl = {**t.syllable, "fricative": True}
    best = _score(best_syl, reference, calibration, frame, sample_rate, mel=mel)
    for nz in FRICATIVE_NOISE_GRID:
        cand = {**best_syl, "noise": nz}
        s = _score(cand, reference, calibration, frame, sample_rate, mel=mel)
        if s > best:
            best, best_syl = s, cand

    mfcc_mean = np.mean(
        np.stack(
            [np.asarray(o.descriptor, dtype=float)[: features.N_MFCC] for o in members]
        ),
        axis=0,
    )
    seeds = _fricative_seed_formants(mfcc_mean)
    variants = [v for v in (seeds, list(t.syllable.get("formants") or []) + seeds) if v]
    for fm in variants:
        for q in FRICATIVE_SEED_QS:
            for g in FRICATIVE_SEED_GAINS:
                cand = {**best_syl, "formants": [[f, q, g] for f, _, _ in fm]}
                s = _score(cand, reference, calibration, frame, sample_rate, mel=mel)
                if s > best:
                    best, best_syl = s, cand

    if best > before + 1.0e-4:
        t.syllable = best_syl
        return before, best
    return before, before


# --- syntax: the bout rule ----------------------------------------------------------------------

#: A gap longer than this ends a bout. One second, and until 2026-08-01 it was three
#: separate literals — `learn_grammar`'s, `bout_sequences`' and `syntax`'s — for one
#: rule that the grammar, the chunk miner, the bake-off and the song types must all be
#: defined over or they are measuring different strings. One name, one number.
GAP_BOUT_SECONDS = 1.0




def learn_grammar(
    observations: Sequence[SyllableObservation],
    type_of: dict[int, str],
    gap_seconds: float = GAP_BOUT_SECONDS,
) -> dict[str, Any]:
    """First-order transitions between syllable types, within each recording.

    `type_of` maps an observation's position in `observations` to its learned type id.
    Transitions across a gap longer than `gap_seconds` — `GAP_BOUT_SECONDS`, or a
    per-species map from `species_bout_gaps` — are treated as the end of a bout rather
    than as a transition, or every pause in a recording would become a (spurious) link
    between two unrelated phrases.

    Also measures the one rhythm number the app can honestly play back: `gaps`, the
    median `gap_before` of the second token of each transition, keyed `"L29>L14"`.
    Until this existed, every sequence the app rendered used invented constants
    (0.035–0.12 s) while the measured inter-syllable gaps sat unused in the store.
    Medians, not means — gap distributions are right-skewed, and the same
    `GRAMMAR_MIN_COUNT` filter as the transitions themselves keeps a two-observation
    "median" from looking like a measurement.
    """
    by_recording: dict[str, list[tuple[int, SyllableObservation]]] = defaultdict(list)
    for i, o in enumerate(observations):
        by_recording[o.recording_id].append((i, o))

    starts: Counter[str] = Counter()
    transitions: dict[str, Counter[str]] = defaultdict(Counter)
    gaps: dict[str, list[float]] = defaultdict(list)
    for items in by_recording.values():
        items.sort(key=lambda pair: pair[1].order)
        previous: str | None = None
        for i, o in items:
            current = type_of.get(i)
            if current is None:
                continue
            if previous is None or o.gap_before > gap_seconds:
                if previous is not None:
                    transitions[previous][END] += 1
                starts[current] += 1
            else:
                transitions[previous][current] += 1
                gaps[f"{previous}>{current}"].append(o.gap_before)
            previous = current
        if previous is not None:
            transitions[previous][END] += 1

    def normalise(counts: Counter[str]) -> dict[str, float]:
        kept = {k: v for k, v in counts.items() if v >= GRAMMAR_MIN_COUNT} or dict(counts)
        total = sum(kept.values()) or 1
        return {k: round(v / total, 4) for k, v in sorted(kept.items(), key=lambda kv: -kv[1])}

    table = {k: normalise(v) for k, v in sorted(transitions.items())}
    kept_keys = {
        f"{a}>{b}" for a, row in table.items() for b in row if b != END
    }
    return {
        "start": [k for k, _ in starts.most_common(4)],
        "transitions": table,
        "gaps": {
            k: round(float(np.median(v)), 3)
            for k, v in sorted(gaps.items())
            if k in kept_keys and len(v) >= GRAMMAR_MIN_COUNT
        },
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
    gap_seconds: float = GAP_BOUT_SECONDS,
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
    return [
        (species_id, seq)
        for species_id, _, seq in bout_sequences(observations, typing, gap_seconds)
    ]


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
#: Fewest syllables a *short* bout needs before it may be called a repeat class.
#:
#: **Why repeat classes exist at all.** `_collapse_runs` reads `A A A A A` as the motif
#: `A`, which then falls under `SONG_MIN_MOTIF` and is set aside as "short" — so a bird
#: whose song *is* a trill has never been able to have a song type, however many times
#: it was heard. Measured on the 340 079-syllable store: 19 738 of 34 696 bouts (57 %)
#: collapse to one token, and **6 940 of those are three syllables or more** — genuine
#: repeats, not single notes. That is the largest single loss in the song funnel, and
#: it is a loss of accounting, not of evidence.
#:
#: The claim a repeat class makes is deliberately weaker than a motif's: not "these
#: bouts share an order of distinct acts" but "this bird was heard repeating this one
#: sound, this often". The recurrence bar is the same `min_cluster_size`, the same
#: permutation control judges it, and `kind` on the shipped type says which of the two
#: it is, so nothing downstream has to guess. Three is the floor because two syllables
#: of one type is the transition table's self-loop, already carried by the grammar.
SONG_MIN_REPEATS = 3


def bout_sequences(
    observations: Sequence[SyllableObservation],
    typing: Sequence[dict[str, Any]],
    gap_seconds: float = GAP_BOUT_SECONDS,
) -> list[tuple[str, tuple[str, int], list[str]]]:
    """Per-recording type-id sequences, one per bout, with the bout's store key.

    The general form of `type_sequences`: same bouts under the same two rules (order is
    meaningful within a recording and meaningless across; a gap over `gap_seconds`
    breaks a bout; untyped observations are skipped without breaking it), but each bout
    also carries `(recording_id, first_order)` — the order of its first typed syllable —
    so a song-level fit can name the bouts it claims, the way `typing_rows` names
    syllables. `gap_seconds` is the constant, or a per-species map from
    `species_bout_gaps`; every caller of the bout rule takes the same argument, so the
    grammar, the chunks, the bake-off and the song types cannot drift onto different
    strings.
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
            if o.gap_before > gap_seconds and bout:
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


def _motif_clusters(
    items: Sequence[tuple[Any, tuple[str, ...]]], min_cluster_size: int
) -> tuple[list[dict[str, Any]], np.ndarray]:
    """HDBSCAN over collapsed strings: the motif half of `cluster_song_types`.

    Split out of the loop body so the permutation control can run exactly the clustering
    it is a control for, rather than a re-implementation of it. Returns the surviving
    clusters (medoid sequence, bout count, HDBSCAN label) and the per-bout label array,
    with the radius gate's demotions already written back into the labels.
    """
    from sklearn.cluster import HDBSCAN

    labels = np.full(len(items), -1, dtype=int)
    uniques = sorted({collapsed for _, collapsed in items})
    if len(items) < max(2, min_cluster_size) or len(uniques) < 2:
        return [], labels

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
        clusters.append({
            "sequence": list(medoid),
            "count": int(len(member_rows)),
            "label": c,
            "kind": "motif",
        })
    return clusters, labels


def _repeat_classes(
    short: Sequence[tuple[Any, tuple[str, ...], int]], min_cluster_size: int
) -> tuple[list[dict[str, Any]], np.ndarray]:
    """Recurring repeats: the bouts `_collapse_runs` reduced below `SONG_MIN_MOTIF`.

    `short` is `(key, collapsed, raw_length)` per set-aside bout. A repeat class is one
    collapsed string — `('L03',)`, or a two-token alternation — heard `min_cluster_size`
    times or more in bouts of at least `SONG_MIN_REPEATS` syllables. No distance and no
    density: at one or two tokens the only honest similarity is equality, which is the
    same reason `SONG_MIN_MOTIF` refuses to hand these strings to HDBSCAN (chance
    two-token strings sit one substitution apart and chain into clusters of pure noise).
    Equality cannot chain, so the noise mode the motif path has to gate against does not
    exist here; what remains to check is recurrence, which the shared permutation control
    checks — shuffling a species' tokens destroys runs, so a control that still produces
    repeat classes is a species whose repeats were an artefact of its type marginals.

    Returns the classes and the per-bout label array, aligned to `short`, -1 for unplaced.
    """
    labels = np.full(len(short), -1, dtype=int)
    counts = Counter(
        collapsed for _, collapsed, raw in short if raw >= SONG_MIN_REPEATS
    )
    kept = [
        collapsed
        for collapsed, n in counts.items()
        if n >= max(2, min_cluster_size)
    ]
    if not kept:
        return [], labels
    label_of = {collapsed: i for i, collapsed in enumerate(sorted(kept))}
    for i, (_, collapsed, raw) in enumerate(short):
        if raw >= SONG_MIN_REPEATS and collapsed in label_of:
            labels[i] = label_of[collapsed]
    return [
        {
            "sequence": list(collapsed),
            "count": int(counts[collapsed]),
            "label": label_of[collapsed],
            "kind": "repeat",
        }
        for collapsed in sorted(kept)
    ], labels




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
    are not handed to the density clustering**: a one- or two-token string is a unigram
    or a bigram, and those are the transition table's business — `mine_chunks` starts at
    n = 3 for the same reason. The measured cost of skipping that gate: at the store's
    alphabet sizes, chance two-token strings sit one substitution (a normalised distance
    of 0.5) from each other often enough for HDBSCAN to chain them into clusters of pure
    noise — the first run of this function reported a "song type" of six unrelated
    random bouts, and the permutation control catches exactly that shape.

    They are not, however, thrown away. `_repeat_classes` reads the set-aside bouts by
    *equality* — the one similarity a two-token string can carry honestly — and calls a
    string heard `min_cluster_size` times in bouts of `SONG_MIN_REPEATS` syllables or
    more a **repeat class**: "this bird was heard repeating this sound, this often". On
    the 340 079-syllable store that recovers 6 940 bouts the collapse used to drop,
    which is the largest single loss in the song funnel and the reason a trilling
    species could never have a song type. Both kinds carry `kind` (`motif` or `repeat`)
    so no reader has to infer which claim is being made, and both answer to the same
    control. What is still out of scope is reported under the summary's `short`.

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

    **`floor` turns that one global number into a per-species question.** With it set,
    a species with at least `floor_min_candidates` candidate bouts may drop its
    `min_cluster_size` one step at a time toward the floor, and takes each step only if
    `_control_placed` places *zero* bouts at that size in every shuffle of its own
    tokens — the first step that fails ends the descent. The candidate requirement is
    what makes the control mean anything: without it, 2 398 of 2 421 species took the
    loosest bar on the strength of a control too small to place a bout at any size, and
    the corpus-wide shuffle yield went 0.170 % -> 0.442 % of candidate bouts. The reason
    to want it: the corpus grew eight-fold since the knee was measured, and the median
    species that clears the candidate gate has eight candidate bouts, so a six-member
    bar asks HDBSCAN to find six of eight and finds nothing for 318 of 366 species. The
    reason it is a control and not a looser constant: at 4 the *global* control chained
    3.0 % of bouts into spurious types, so the licence to go there has to be earned by
    the species that goes. `summary.minClusterSize` records where each species landed
    and `summary.controlPlaced` what its control found there. `floor=None` (the default)
    is the pre-registered behaviour, bit-identical.

    Ids are `S01`, `S02`, … ranked by bout count, motifs and repeat classes ranked
    together. Unlike syllable ids (`assign_ids`) they are **not** stabilised across
    refits — a re-learnt typing renumbers the strings themselves, so stability has to
    wait on the syllable ids it would be defined over.
    """
    by_species: dict[str, list[tuple[tuple[str, int], tuple[str, ...], list[str]]]] = (
        defaultdict(list)
    )
    for species_id, key, seq in sequences:
        collapsed = _collapse_runs(seq)
        if collapsed:
            by_species[species_id].append((key, collapsed, list(seq)))

    out: dict[str, dict[str, Any]] = {}
    for species_id in sorted(by_species):
        rows = by_species[species_id]
        short = [(key, c, len(raw)) for key, c, raw in rows if len(c) < SONG_MIN_MOTIF]
        items = [(key, c) for key, c, _ in rows if len(c) >= SONG_MIN_MOTIF]
        summary = {
            "bouts": len(items) + len(short),
            "short": len(short),
            "candidates": len(items),
            "repeatCandidates": sum(1 for _, _, n in short if n >= SONG_MIN_REPEATS),
            "types": 0,
            "repeatTypes": 0,
            "inTypes": 0,
            "unplaced": len(items),
            "minClusterSize": int(min_cluster_size),
        }
        entry: dict[str, Any] = {"types": [], "rows": [], "summary": summary}
        out[species_id] = entry

        clusters, labels = _motif_clusters(items, min_cluster_size)
        repeats, repeat_labels = _repeat_classes(short, min_cluster_size)
        if not clusters and not repeats:
            continue

        # Ranked together: a repeat class heard forty times is more of this bird's
        # repertoire than a motif heard six, and the ids are a ranking, not a taxonomy.
        ranked = sorted(clusters + repeats, key=lambda t: (-t["count"], t["sequence"]))
        id_of = {
            (t["kind"], t["label"]): f"S{rank + 1:02d}" for rank, t in enumerate(ranked)
        }

        entry["types"] = [
            {
                "id": id_of[(t["kind"], t["label"])],
                "sequence": t["sequence"],
                "count": t["count"],
                # Of every bout this species sang, short ones included — the shares,
                # `short` and `unplaced` sum to the whole.
                "share": round(t["count"] / (len(items) + len(short)), 4),
                # Which claim this type makes: an order of distinct acts, or one sound
                # heard repeating. The app says them differently; nothing should have
                # to infer it from the sequence length.
                "kind": t["kind"],
            }
            for t in ranked
        ]
        for kind, source, label_array in (
            ("motif", items, labels),
            ("repeat", short, repeat_labels),
        ):
            for i, row in enumerate(source):
                if label_array[i] < 0:
                    continue
                key = row[0]
                entry["rows"].append({
                    "speciesId": species_id,
                    "recordingId": key[0],
                    "firstOrder": int(key[1]),
                    "songTypeId": id_of[(kind, int(label_array[i]))],
                })
        summary["types"] = len(ranked)
        summary["repeatTypes"] = len(repeats)
        summary["inTypes"] = int((labels >= 0).sum() + (repeat_labels >= 0).sum())
        summary["unplaced"] = int((labels < 0).sum())
    return out


def attach_song_types(
    document: dict[str, Any],
    observations: Sequence[SyllableObservation],
    typing: Sequence[dict[str, Any]],
    min_cluster_size: int = SONG_MIN_CLUSTER,
    gap_seconds: float = GAP_BOUT_SECONDS,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """Cluster every species' bouts into song types and hang them on each grammar.

    The song-level counterpart of `attach_chunks`: one pass over `bout_sequences`, then
    each species' grammar carries its song types under `grammar.songTypes` (id, medoid
    sequence, bout count, share of the species' bouts, and `kind`) and the census under
    `grammar.songTyping` (how many bouts, how many too short to be a motif, how many
    placed, how many heard once and never again, and where the species' recurrence bar
    landed). `floor` is `cluster_song_types`'s, which see. Returns the flat membership
    rows — the store-side `song-typing.json` table, so a later build or grow can key a
    bout to its song type without reclustering.
    """
    if not typing:
        return []
    found = cluster_song_types(
        bout_sequences(observations, typing, gap_seconds),
        min_cluster_size=min_cluster_size,
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
        types = sum(e["summary"]["types"] for e in found.values())
        repeats = sum(e["summary"]["repeatTypes"] for e in found.values())
        named = sum(1 for e in found.values() if e["summary"]["types"])
        log(f"song-level typing: {types} song types ({types - repeats} motifs, "
            f"{repeats} repeat classes) over {named} species, {total} candidate bouts, "
            f"{placed} bouts placed; {short} short bouts, "
            f"{sum(e['summary']['repeatCandidates'] for e in found.values())} of them "
            "long enough to be a repeat class")
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
    # Same trap as the per-species fit (see `learn_species`), with no fallback available:
    # this path types an arrival by comparing its embedding against the known types'
    # embeddings, so without a patch there is nothing to compare. There is no hand-written
    # substitute here — the known-type centroids are embedding vectors — so an unpatched
    # pool means these arrivals cannot be typed, which is a result rather than an error.
    if not any(o.mel_patch is not None for o in pool):
        log(f"  {UNLABELLED_SPECIES:26} {len(pool)} arrivals, none carrying a log-mel "
            "patch — cannot be typed against the known types, left untyped")
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
    gap_seconds: float = GAP_BOUT_SECONDS,
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
    chunks = mine_chunks(
        type_sequences(observations, typing, gap_seconds), min_count=min_count
    )
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
    use_respiration: bool = False,
    use_two_voice: bool = False,
    mel_weight: float = 0.0,
    gap_seconds: float = GAP_BOUT_SECONDS,
    inverse: "Any | None" = None,
    inverse_two_start: bool = False,
) -> dict[str, Any] | None:
    """Fitted syllables + a measured grammar for one species, or None if too little data.

    `embedder` and `realism` are the two halves of docs/09 §9.2b/§9.3 and they are independent:
    the first changes what a *type* is, the second changes what *close* means. Both default to
    off, so a run that passes neither is bit-identical to the fit that shipped before the critic
    existed — which is what makes the comparison in the plan's results table meaningful.

    `use_respiration` attaches the default respiratory set of docs/15 §1 to every fitted
    type: hand-set, one set for every species, until the pre-registered per-species fit
    exists (respiration.py's module docstring says how it will be fitted). The reported
    resynthesis cosine then measures the respiratory render, which is the comparison the
    bake-off is run on.

    `use_two_voice` attaches the default second voice of docs/15 §5 to every fitted
    type: the type's own contour shifted by twovoice.DEFAULT_RATIO (the eps_l/eps_r
    ratio of the paper's Fig. 6), Table I's trachea and reflection, the measured
    injection strength — hand-set until the pre-registered per-species fit exists, the
    same status as the respiratory set. The reported cosine then measures the
    two-voice render, which is the comparison its bake-off is run on.

    `use_tube` re-enables the waveguide tract. It is written, tested, and gated off because the
    28-d objective rejected it (§9.1 result 5). docs/09 calls it "the cleanest available test of
    whether the new objective is actually better", so it is a flag here rather than a constant:
    the waveguide is known to be structurally right, and an objective that still rejects it is
    not fixed.

    `mel_weight` gives each type's mean member mel-path a share `w` of the inversion's
    objective (docs/19 §19.3: the 28-d cosine does not rank audible distortion,
    r ≈ 0.1 vs MCD; the mel-path is the same family of quantity MCD measures). At the
    default 0 the objective is bit-identical to the one that shipped before the term
    existed. The cosine stays in the blend as the clustering guardrail, and the
    reported `resynthesis_cosine` below is measured with the pure cosine regardless.
    """
    if len(observations) < MIN_OBSERVATIONS:
        if verbose:
            log(f"  {species_id:26} {len(observations)} observations — below the "
                f"{MIN_OBSERVATIONS} needed, skipped")
        return None

    # **A species can be entirely patchless even when the store is not, and that used to
    # kill the whole run.**
    #
    # `_learn_objective` decides whether to type in the embedding by counting patches
    # across the *store*, but the embedder is applied one species at a time. `out/harvest`
    # holds 27 271 patches over 39 969 observations, so the store-wide check passes — yet
    # two of its 37 species (`cuculus_canorus`, `zosterops_japonicus`, ~1 750 observations
    # each) were harvested entirely before `features.mel_patch` existed and carry none at
    # all. Reaching either one, `critic_embedder` raised "no observation carries a
    # mel_patch" and took the entire fit down with it, after the 35 learnable species had
    # already been paid for. The error also named no species, so it read as a broken store
    # rather than as two legacy birds.
    #
    # The fallback is the one `_learn_objective` already documents for the store-wide case:
    # the learned path is a preference, and anything missing lands on the hand-written
    # objective with a logged reason rather than a traceback. Dropping to
    # `_observation_vector` for this species alone is honest — its types are still real
    # groupings of its own syllables — and it costs nothing that was recoverable, because
    # patches are written at harvest time and the audio is gone by design. Nothing
    # downstream is misled either: an embed-space galaxy already places only observations
    # that carry a patch, so these were never going to be plotted in it.
    #
    # Checked here rather than inside `typing_space` so that `choose_k` and `fit_types`
    # cannot disagree about the space, and so the reason is logged once per species.
    if embedder is not None and not any(o.mel_patch is not None for o in observations):
        if verbose:
            log(f"  {species_id:26} {len(observations)} observations, none carrying a "
                "log-mel patch — typing with the hand-written vector for this species")
        embedder = None

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

    if use_respiration:
        # docs/15 §1's top bet, hand-set until the per-species fit exists: every fitted
        # type carries the default respiratory set, so the pressure gesture the reported
        # cosine measures is the one the syllable ships with — the air sacs' own
        # dynamics, not the designed envelope. Attached before any tract or gesture
        # step so everything downstream is searched against the render that ships.
        for t in fitted:
            t.syllable["respiration"] = respiration.DEFAULT_PARAMS.as_dict()

    if use_two_voice:
        # docs/15 §5, same hand-set status as the respiratory set: every fitted type
        # carries a second voice — its own contour shifted by the Fig. 6 ratio, Table
        # I's trachea — so the reported cosine measures the coupled two-voice render
        # that ships. gamma_b comes from the contour rule of 8.1 applied to the
        # shifted contour; the coupling numbers are twovoice's defaults.
        for t in fitted:
            contour_b = [
                [frac, hz * twovoice.DEFAULT_RATIO] for frac, hz in t.syllable["contour"]
            ]
            t.syllable["voices"] = twovoice.default_block(
                contour_b, syrinx.gamma_for_contour(contour_b)
            )

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
    fricative_shipped = 0
    # How often the encoder's basin beat the median's under `--inverse-two-start`. Reported
    # per species: a two-start whose encoder never wins is paying double for nothing, and
    # that is a thing the run should say out loud rather than leave to be inferred from an
    # unmoved median.
    two_start_encoder_wins = 0
    # One mel target per type (docs/19 §19.3), built from the same members the 28-d
    # reference is built from; all None at the default weight, so `_score` keeps its
    # old code path exactly.
    mels = [mel_target_term(t.members, mel_weight) for t in fitted]
    for i, t in enumerate(fitted):
        # Search first, then measure: the reported cosine has to describe the syllable
        # that ships, not the median it started from.
        # **The encoder proposes the basin; the descent still decides.** `invert_gestures`
        # only ever moves on an improvement, so it cannot leave a bad starting point — and
        # the §8.1a gesture fields start at their defaults (gammaScale 1.0, tractQ/noise/
        # rough 0) no matter what the syllable sounds like, which `inverse.py` measured as
        # wrong for 78 % of types on gammaScale alone. One forward pass from the type's own
        # mean mel patch re-initialises those axes; the measured contour and duration are
        # kept by `init_syllable`, because they are measurements and the prediction is not.
        #
        # Nothing is forced: the search re-scores from wherever this lands, against the
        # same objective, and a worse start simply costs a few renders. `inverse=None` is
        # the shipped path and is bit-identical to the fit before this existed.
        #
        # **Two-start descent** (`--inverse-two-start`, pre-registered in
        # `pipeline/analysis/inverse_gate.md`). The single-start encoder failed its gate on
        # consistency, not on direction: the median rose (+0.0135) while only 52.8 % of
        # types improved — barely more than a coin. The standard answer to inconsistency is
        # not a better encoder but to descend from *both* starts and keep the winner, which
        # **cannot regress by construction** because the median start is always one of the
        # two candidates. The cost is the honest objection: two descents per type.
        #
        # The selection reads `invert_gestures`'s own returned objective, not the pure
        # cosine measured further down. That is deliberate and is what the
        # pre-registration says: the objective that already decides the descent is the one
        # that decides between descents, or the comparison would be judged on a number the
        # search never optimised.
        encoder_start = None
        if inverse is not None and real[i] is not None:
            patches = [o.mel_patch for o in t.members if o.mel_patch is not None]
            if patches:
                encoder_start = inverse.init_syllable(
                    t.syllable, np.mean(np.asarray(patches, dtype=np.float64), axis=0)
                )
        two_start = inverse_two_start and encoder_start is not None and invert
        if encoder_start is not None and not two_start:
            t.syllable = encoder_start
        if invert and real[i] is not None:
            if two_start:
                # No copying needed, and this was checked rather than assumed:
                # `invert_gestures` only ever *reassigns* `t.syllable` to a fresh `_with`
                # trial and touches nothing else on `t`, and `inverse.apply_prediction`
                # returns `dict(syllable)`. So the encoder start is a distinct dict and the
                # median descent's result survives being set aside.
                # **A candidate is the descent AND the fricative seed, scored as it will
                # ship.** The first version of this selected on the descent's score alone
                # and then ran the fricative seed on the winner, which lost 48 of 1 661
                # types against the baseline — by up to 0.049 — and **100 % of those 48
                # were types that ship `fricative: true`**, against 19.3 % of the corpus.
                # The mechanism: `fricative_seed` is a second refinement whose benefit
                # depends on the basin, so the better *pre*-fricative candidate can land on
                # the worse *post*-fricative fit, and post-fricative is what ships and what
                # the gate reads. Selecting on a proxy for the shipped quantity is the bug
                # the pre-registration predicted when it said any regression here "is a bug
                # in the selection rather than a trade".
                def candidate() -> tuple[float, float, bool]:
                    b, a = invert_gestures(
                        t, real[i], calibration, frame, realism=realism, mel=mels[i]
                    )
                    seeded_ = fricative_seed(
                        t, real[i], calibration, frame, mel=mels[i]
                    )
                    if seeded_ is not None:
                        # Re-scored under the FULL objective rather than reusing
                        # `fricative_seed`'s return: that function scores without the
                        # realism term, so its number is only comparable to the descent's
                        # when there is no critic in the objective. One extra render on the
                        # fricative class buys a comparison that is right either way.
                        a = _score(
                            t.syllable, real[i], calibration, frame,
                            features.SAMPLE_RATE, realism, mels[i],
                        )
                    return b, a, seeded_ is not None and bool(t.syllable.get("fricative"))

                before, after, fricative = candidate()
                from_median = (t.syllable, after, fricative)
                t.syllable = encoder_start
                _, after_e, fricative_e = candidate()
                if after_e > after:
                    two_start_encoder_wins += 1
                    # `before` stays the *median* start's score, so the reported gain keeps
                    # meaning "how far the inversion moved from where the fit would have
                    # started without any of this" — what `gains` means everywhere else.
                    after, fricative = after_e, fricative_e
                else:
                    t.syllable, after, fricative = from_median
                gains.append(after - before)
                if fricative:
                    fricative_shipped += 1
            else:
                before, after = invert_gestures(
                    t, real[i], calibration, frame, realism=realism, mel=mels[i]
                )
                gains.append(after - before)
                # docs/16 §16.7 piece 3: the fricative class gets its noise-first start
                # after the tonal search has settled — and keeps it only where the fit's
                # own number prefers it, so a good tonal fit is never rerouted.
                seeded = fricative_seed(t, real[i], calibration, frame, mel=mels[i])
                if seeded is not None and t.syllable.get("fricative"):
                    fricative_shipped += 1
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

    grammar = learn_grammar(observations, type_of, gap_seconds)
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
            + (
                f", fricative start shipped on {fricative_shipped}"
                if invert and fricative_shipped
                else ""
            )
            # Printed even at zero, unlike the fricative count: "the encoder's basin never
            # won" is the single most useful thing a two-start run can tell you, and it is
            # exactly the case an `if` on truthiness would hide.
            + (
                f", encoder basin won {two_start_encoder_wins}/{len(fitted)}"
                if inverse_two_start and inverse is not None
                else ""
            )
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


# --- parallel per-species fitting ----------------------------------------------------

#: Embedding rows for every observation, keyed `(species_id, recording_id, order)`,
#: filled by the parent *before* the process pool forks. With the fork start method
#: the workers inherit it copy-on-write — no 25 MB pickle per task, and no torch in
#: the child at all (the critic embeds once, in the parent, before forking).
_PRE_EMBED: dict[tuple[str, str, int], np.ndarray] = {}


def _precomputed_embedder(observations: Sequence[SyllableObservation]) -> np.ndarray:
    """An `Embedder` that answers from `_PRE_EMBED` instead of running the critic.

    Same contract as `critic_embedder`'s wrapper: one row per observation, in order.
    A missing key means the pool was not forked after the parent's embedding pass —
    on a non-fork start method this is a hard error, not a silent recompute, because
    silently recomputing would load torch (and CUDA) into a forked child.
    """
    try:
        return np.stack(
            [_PRE_EMBED[(o.species_id, o.recording_id, o.order)] for o in observations]
        )
    except KeyError as exc:
        raise RuntimeError(
            "parallel fit: an observation is missing from the precomputed embedding — "
            "the pool must fork after the parent's embedding pass (Linux/fork only)"
        ) from exc


def _pool_worker_init() -> None:
    """One BLAS thread per worker: the pool already holds the machine, and N workers
    times M OpenMP threads is a slowdown dressed as parallelism."""
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"


def _learn_species_worker(
    task: tuple[str, list[SyllableObservation], dict[str, np.ndarray] | None,
                 Calibration | None, int, int, bool,
                 tuple[np.ndarray, np.ndarray] | None,
                 dict[str, dict[str, Any]] | None, bool, bool, bool, float, float],
) -> tuple[str, dict[str, Any] | None]:
    """One species through `learn_species`, for the pool. Verbose off: the parent logs."""
    (species_id, observations, descriptors, calibration, types, seed, invert, frame,
     previous, use_tube, use_respiration, use_two_voice, mel_weight, gap_seconds) = task
    learned = learn_species(
        species_id, observations, descriptors, calibration,
        types=types, seed=seed, verbose=False, frame=frame, invert=invert,
        previous=previous,
        embedder=_precomputed_embedder if _PRE_EMBED else None,
        use_tube=use_tube, use_respiration=use_respiration,
        use_two_voice=use_two_voice, mel_weight=mel_weight, gap_seconds=gap_seconds,
    )
    return species_id, learned


def _fit_species_parallel(
    order: Sequence[str],
    grouped: dict[str, list[SyllableObservation]],
    observations: Sequence[SyllableObservation],
    descriptors: dict[str, np.ndarray] | None,
    calibration: Calibration | None,
    types: int,
    seed: int,
    invert: bool,
    frame: tuple[np.ndarray, np.ndarray] | None,
    prior: dict[str, dict[str, dict[str, Any]]] | None,
    embedder: Embedder | None,
    use_tube: bool,
    use_respiration: bool,
    use_two_voice: bool,
    jobs: int,
    verbose: bool,
    mel_weight: float = 0.0,
    gap_seconds: float = GAP_BOUT_SECONDS,
) -> dict[str, dict[str, Any] | None]:
    """Fit every species in a fork pool: same function, same seeds, same results as the
    serial loop — just all cores instead of one.

    Why this exists: a full learn on the 3 800-species store is thousands of small
    *independent* fits (silhouette sweep, KMeans, gesture inversion per species), and
    the serial loop used one core of twenty-eight. The embedding is the one shared,
    GPU-shaped part, so the parent runs it once (the critic stays out of the children
    entirely) and the workers read precomputed rows (`_PRE_EMBED`). Per-species seeds
    and inputs are unchanged, so the fit is identical to the serial one — the
    parallelism is invisible to every downstream number, which is what makes it safe
    to switch on in a pipeline that judges itself on fixed-store metrics.

    Fork-only (Linux): the workers inherit `_PRE_EMBED` at fork. `realism` is refused
    by the caller — a RealismTerm holds the critic and cannot cross into a child.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    if embedder is not None:
        if verbose:
            log(f"embedding {len(observations)} observations once, before the pool")
        keys = [(o.species_id, o.recording_id, o.order) for o in observations]
        z_all = np.asarray(embedder(observations), dtype=np.float64)
        _PRE_EMBED.clear()
        _PRE_EMBED.update({k: z_all[i] for i, k in enumerate(keys)})
    tasks = [
        (species_id, grouped[species_id], descriptors, calibration, types, seed,
         invert, frame, (prior or {}).get(species_id), use_tube, use_respiration,
         use_two_voice, mel_weight, gap_seconds)
        for species_id in order
        if species_id != UNLABELLED_SPECIES
    ]
    results: dict[str, dict[str, Any] | None] = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=jobs, initializer=_pool_worker_init) as pool:
        futures = [pool.submit(_learn_species_worker, task) for task in tasks]
        for done, future in enumerate(as_completed(futures), 1):
            species_id, learned = future.result()
            results[species_id] = learned
            if verbose and done % 100 == 0:
                log(f"  fitted {done}/{len(tasks)} species "
                    f"({time.time() - t0:.0f}s)")
    return results


def recording_names(
    recordings: dict[str, dict[str, Any]],
    already: set[str],
) -> list[dict[str, str]]:
    """Common names the harvest already knew, as discovered-registry entries.

    Every fetch adapter records the recording's English name into the store
    (`note_recording`: xccoverbl's `en`, iNatSounds' `common_name`), and until now
    `build_learned_inventory` never saw it — a species absent from both the authored
    inventory and the discovered registry was named by its own id everywhere
    ("odontophorus_hyperythrus sings odontophorus_hyperythrus"). `already` keeps the
    authored inventory and the registry authoritative; this only fills what neither
    covers. The first recording wins on collisions: they are all the same name.
    """
    out: dict[str, dict[str, str]] = {}
    for info in recordings.values():
        sid = info.get("speciesId")
        en = info.get("english")
        if sid and en and sid not in already and sid not in out:
            out[sid] = {
                "id": sid,
                "common": en,
                "scientific": info.get("scientific", ""),
            }
    return list(out.values())


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
    use_respiration: bool = False,
    use_two_voice: bool = False,
    mel_weight: float = 0.0,
    discovered: Sequence[dict[str, Any]] | None = None,
    typing: list[dict[str, Any]] | None = None,
    on_species: "Callable[[dict[str, Any], list[dict[str, Any]]], None] | None" = None,
    jobs: int = 1,
    gap_seconds: float = GAP_BOUT_SECONDS,
    inverse: "Any | None" = None,
    inverse_two_start: bool = False,
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

    `on_species`, when given, is called once per fitted species with that species'
    finished inventory entry and its typing rows — the streaming hook. A full learn on
    a large store runs for the better part of an hour, and for most of its history the
    only way to see progress was to wait for the single write at the end (which was
    also the only copy of the work: one crash lost the hour). Callers use it to journal
    progress and to checkpoint the typing; the fit itself is unchanged either way.

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
    # Flat, grouping-order copy for the embedding pass and the parallel pool — the
    # caller's iterable may be a generator, and both consumers need to revisit it.
    observations_list = [o for group in grouped.values() for o in group]

    # One frame for the whole harvest, not one per species: a resynthesis has to be
    # judged against the same axes every other syllable was measured on.
    frame = population_frame(observations_list)
    if verbose and frame is None:
        log("no per-syllable descriptors in the store — the resynthesis cosine will be "
            "taken raw, where it barely separates one call from another")

    if verbose and (embedder is not None or realism is not None):
        with_patch = sum(1 for o in observations if o.mel_patch is not None)
        log(
            "learned components active: "
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
    order = sorted(grouped, key=lambda s: -len(grouped[s]))
    parallel: dict[str, dict[str, Any] | None] | None = None
    if jobs > 1 and len(order) > 1:
        if realism is not None or inverse is not None:
            held = "a realism term holds the critic" if realism is not None else (
                "the inverse encoder holds a torch model")
            log(f"--jobs {jobs} ignored: {held} and cannot "
                "cross into a worker process — fitting serially")
        else:
            parallel = _fit_species_parallel(
                order, grouped, observations_list, descriptors, calibration, types,
                seed, invert, frame, prior, embedder, use_tube, use_respiration,
                use_two_voice, jobs, verbose, mel_weight=mel_weight,
                gap_seconds=gap_seconds,
            )
    species_out: list[dict[str, Any]] = []
    for species_id in order:
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
        if parallel is not None:
            learned = parallel.get(species_id)
        else:
            learned = learn_species(
                species_id, grouped[species_id], descriptors, calibration,
                types=types, seed=seed, verbose=verbose, frame=frame, invert=invert,
                previous=(prior or {}).get(species_id),
                embedder=embedder, realism=realism, use_tube=use_tube,
                use_respiration=use_respiration, use_two_voice=use_two_voice,
                mel_weight=mel_weight,
                gap_seconds=gap_seconds,
                inverse=inverse,
                inverse_two_start=inverse_two_start,
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
        if on_species is not None:
            on_species(species_out[-1], rows)

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

    # 6b. Respiration (docs/15 §1): a syllable carrying the default respiratory set
    #     renders through the same pipeline and lands somewhere different from the
    #     envelope render — the gesture is not the envelope. A block that fails to
    #     parse must fall back to the envelope path *bit-identically*, because that
    #     fallback is what keeps every inventory written before this feature valid.
    resp_syllable = {**syllable, "respiration": respiration.DEFAULT_PARAMS.as_dict()}
    parsed = syrinx.Syllable.from_dict(resp_syllable)
    assert parsed.respiration == respiration.DEFAULT_PARAMS
    env_audio = render_syllable(syllable)
    resp_audio = render_syllable(resp_syllable)
    assert resp_audio.shape == env_audio.shape and np.all(np.isfinite(resp_audio))
    assert not np.allclose(env_audio, resp_audio), (
        "the respiratory gesture must actually change the sound"
    )
    for junk in ({"respiration": {"tauX": 0.1}}, {"respiration": "yes"}):
        assert np.array_equal(render_syllable({**syllable, **junk}), env_audio), (
            f"an unparseable respiration block must be the envelope path: {junk}"
        )
    # ...and the plan tells the renderer not to apply the envelope twice.
    plan = syrinx.render_plan(resp_syllable)
    assert plan.respiratory and plan.drive is not None
    assert np.array_equal(plan.env, plan.drive), (
        "on the respiratory path `env` is the diagnostic amplitude shape: the drive"
    )
    assert not syrinx.render_plan(syllable).respiratory

    # 6c. Two voices (docs/15 §5): a syllable carrying a `voices` block renders
    #     through the same pipeline and lands somewhere different — two sources and
    #     a coupling are not one source. A block that fails to parse must fall back
    #     to the single-voice path *bit-identically* (same argument as the
    #     respiration fallback above), and — the sharper property — a block with
    #     zero injection and a closed right side must BE the single voice, bit for
    #     bit: the coupling recurrence then gives pi = 0 identically and voice A
    #     integrates exactly as `_ode_source` does. If that ever drifts, the two
    #     paths have silently become different models.
    voices_block = twovoice.default_block([[0.0, 2400.0], [1.0, 2600.0]], 14000.0)
    voice_syllable = {**syllable, "voices": voices_block}
    parsed = syrinx.Syllable.from_dict(voice_syllable)
    assert parsed.voices is not None
    assert parsed.voices.as_dict() == voices_block
    two_audio = render_syllable(voice_syllable)
    assert two_audio.shape == env_audio.shape and np.all(np.isfinite(two_audio))
    assert not np.allclose(env_audio, two_audio), (
        "a second coupled voice must actually change the sound"
    )
    for junk in ({"voices": {"level": 0.5}}, {"voices": "yes"}):
        assert np.array_equal(render_syllable({**syllable, **junk}), env_audio), (
            f"an unparseable voices block must be the single-voice path: {junk}"
        )
    uncoupled = {
        **voices_block,
        "betaInj": 0.0,
        "level": 0.0,
    }
    assert np.array_equal(
        render_syllable({**syllable, "voices": uncoupled}), env_audio
    ), "betaInj=0 with a closed right side must be the single voice, bit for bit"

    # ...and the fit-time flag attaches a parseable block whose contour rides the
    # type's own, shifted by the Fig. 6 ratio.
    attached = twovoice.default_block(
        [[f, hz * twovoice.DEFAULT_RATIO] for f, hz in syllable["contour"]],
        syrinx.gamma_for_contour(
            [[f, hz * twovoice.DEFAULT_RATIO] for f, hz in syllable["contour"]]
        ),
    )
    assert syrinx.Syllable.from_dict({**syllable, "voices": attached}).voices is not None

    # 6d. The fricative path (docs/16 §16.7): a flagged syllable with turbulence
    #     renders somewhere different from the mixed path — routing the noise
    #     through the formant set instead of the f0-tracking band is not the same
    #     filter. With `noise = 0` the flag must be a no-op *bit for bit* (there is
    #     no turbulence to route), and an unflagged syllable renders exactly as it
    #     always has — all eighteen parity fixtures stand on that.
    fric_syllable = {
        **syllable,
        "noise": 0.6,
        "fricative": True,
        "formants": [[2400.0, 4.0, 1.0], [5200.0, 6.0, 0.6]],
    }
    parsed = syrinx.Syllable.from_dict(fric_syllable)
    assert parsed.fricative is True
    mixed_audio = render_syllable({k: v for k, v in fric_syllable.items() if k != "fricative"})
    fric_audio = render_syllable(fric_syllable)
    assert fric_audio.shape == mixed_audio.shape and np.all(np.isfinite(fric_audio))
    assert not np.allclose(mixed_audio, fric_audio), (
        "formant-shaped noise must not equal tracking-band noise"
    )
    quiet = {**fric_syllable, "noise": 0.0}
    assert np.array_equal(
        render_syllable(quiet),
        render_syllable({k: v for k, v in quiet.items() if k != "fricative"}),
    ), "fricative with noise=0 must be a no-op, bit for bit"
    # ...and the respiration path stays deterministic with the burst separated.
    resp_fric = {**fric_syllable, "respiration": respiration.DEFAULT_PARAMS.as_dict()}
    assert np.array_equal(render_syllable(resp_fric), render_syllable(resp_fric))

    # 6e. The noise-first start (docs/16 §16.7 piece 3): a flatness-heavy type whose
    #     reference IS shaped noise must ship the flag — the seeded candidate is
    #     then the very render the evidence came from, so the fit's own number has
    #     to prefer it. A low-flatness type must be left alone: the gate is what
    #     keeps the tonal start where it belongs.
    ref_audio = peak_normalise(render_syllable(fric_syllable))
    ref_desc = features.descriptor(ref_audio, features.SAMPLE_RATE)

    def flat_observation(flatness: float) -> SyllableObservation:
        o = observation(3000.0, 0.06)
        o.flatness = flatness
        o.descriptor = [float(v) for v in ref_desc]
        return o

    seeded_type = LearnedType(
        id="TF",
        members=[flat_observation(0.2) for _ in range(3)],
        syllable={k: v for k, v in fric_syllable.items() if k != "fricative"},
    )
    result = fricative_seed(seeded_type, _unit(ref_desc), None, None, features.SAMPLE_RATE)
    assert result is not None and seeded_type.syllable.get("fricative") is True, (
        "a fricative-class type with shaped-noise evidence must ship the flag"
    )
    plain_type = LearnedType(
        id="TP",
        members=[flat_observation(0.05) for _ in range(3)],
        syllable=dict(syllable),
    )
    assert fricative_seed(plain_type, _unit(ref_desc), None, None, features.SAMPLE_RATE) is None
    assert "fricative" not in plain_type.syllable, (
        "below the flatness gate the fit must not reroute"
    )

    # 6f. The mel target (docs/19 §19.3). Three properties, in ascending order of how
    #     much they matter:
    #     (a) `w = 0` and a missing target are no-ops — bit-identical to the objective
    #         that shipped before the term existed, which is what keeps every gate
    #         that reads `_score` unchanged by default;
    #     (b) identity scores 1.0 and the blend is linear in `w`;
    #     (c) the term must hear a plainly audible, *time-varying* distortion that the
    #         28-d cosine is nearly blind to — the exact premise of docs/19. The
    #         fixture is specbench's: low-passing the back half of the syllable at
    #         2.5 kHz costs +77.9 dB MCD while the 28-d cosine drops 0.015. Measured
    #         here: the mel target falls 1.0 -> 0.46 (LSD 0.78 log units) on that
    #         damage, and 0.63 on an 800 Hz formant shift where the cosine drops
    #         0.003. A path cosine was tried for this and rejected — it dropped 0.017
    #         on the same fixture, no better than the 28-d (the class docstring keeps
    #         the numbers).
    mel_syllable = {
        "id": "melTest", "dur": 0.25, "level": 0.85, "timbre": "reed",
        "contour": [[0.0, 3200.0], [0.4, 4400.0], [0.7, 2800.0], [1.0, 3600.0]],
        "noise": 0.12,
        "formants": [[2400.0, 6.0, 0.5], [5400.0, 6.0, 0.25]],
    }
    mel_audio = peak_normalise(render_syllable(mel_syllable))
    mel_target = features.mel_path(mel_audio)[:, : features.PATCH_MEL]
    term = MelTargetTerm(mel_target, 1.0)
    assert term.similarity(mel_audio) == 1.0, "a render against its own path must score 1"
    assert MelTargetTerm(mel_target, 0.0).blend(0.42, mel_audio) == 0.42
    assert MelTargetTerm(None, 1.0).blend(0.42, mel_audio) == 0.42, "no target must be a no-op"
    assert np.isnan(MelTargetTerm(None, 1.0).similarity(mel_audio))
    half_blend = MelTargetTerm(mel_target, 0.5).blend(0.8, mel_audio)
    assert np.isclose(half_blend, 0.5 * 0.8 + 0.5 * 1.0), "the blend must be linear in w"
    assert MelTargetTerm(mel_target, 5.0).weight == 1.0
    assert MelTargetTerm(mel_target, -1.0).weight == 0.0
    # `_score` with the term at w=0 must be bit-identical to `_score` without it.
    mel_ref = _unit(np.ones(features.DIM))
    plain_score = _score(mel_syllable, mel_ref, None, None, features.SAMPLE_RATE)
    assert plain_score == _score(
        mel_syllable, mel_ref, None, None, features.SAMPLE_RATE,
        mel=MelTargetTerm(mel_target, 0.0),
    ), "w=0 must be bit-identical to the old objective"
    blended_score = _score(
        mel_syllable, mel_ref, None, None, features.SAMPLE_RATE,
        mel=MelTargetTerm(mel_target, 1.0),
    )
    assert blended_score != plain_score, "a w=1 mel term must change the score"
    # The sensitivity premise: time-varying spectral damage must move the mel target
    # far where the 28-d cosine barely moves.
    damaged = mel_audio.copy()
    damaged[len(damaged) // 2:] = syrinx._one_pole_lp(
        mel_audio[len(mel_audio) // 2:].copy(), 2500.0, features.SAMPLE_RATE
    )
    damaged = peak_normalise(damaged)
    mel_drop = 1.0 - term.similarity(damaged)
    d_damaged = features.descriptor(damaged, features.SAMPLE_RATE)
    d_clean = features.descriptor(mel_audio, features.SAMPLE_RATE)
    cos_drop = 1.0 - float(_unit(d_clean) @ _unit(d_damaged))
    assert mel_drop > 0.25, (
        f"the mel target must hear the damaged half: drop {mel_drop:.3f} — the "
        "exp(-LSD) form is not doing what docs/19 needs"
    )
    assert mel_drop > 5.0 * cos_drop, (
        f"the mel target must out-see the 28-d cosine on audible damage: "
        f"{mel_drop:.3f} vs {cos_drop:.3f}"
    )
    shifted = {**mel_syllable, "formants": [[3000.0, 6.0, 0.5], [6800.0, 6.0, 0.25]]}
    shifted_audio = peak_normalise(render_syllable(shifted))
    assert term.similarity(shifted_audio) < 0.8, (
        "an 800 Hz formant shift must cost the mel target clearly"
    )
    # The helper: w=0 or no member paths -> None (the no-op path); otherwise the term
    # holds the members' mean path, band-cut.
    mel_obs = observation(3000.0, 0.06)
    mel_obs.mel_path = [0.1] * (features.MEL_KNOTS * features.N_MEL)
    assert mel_target_term([mel_obs], 0.0) is None
    assert mel_target_term([observation(3000.0, 0.06)], 1.0) is None, (
        "members without mel_path must mean no term"
    )
    built = mel_target_term([mel_obs, mel_obs], 1.0)
    assert built is not None and built.target.shape == (
        features.MEL_KNOTS, features.PATCH_MEL
    )


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

    # 8b. The ingest-time quality fields round-trip the same way: a scored observation
    #     keeps its numbers through save/load, and a legacy row — every store on disk —
    #     loads them as None, which the fit reads as "unmeasured", not as bad.
    scored = observation(2500.0, 0.07)
    scored.snr, scored.clipped = 14.3, True
    back = SyllableObservation.from_dict(scored.to_dict())
    assert (back.snr, back.clipped) == (14.3, True), "quality fields did not round-trip"
    legacy = scored.to_dict()
    del legacy["snr"], legacy["clipped"]
    back = SyllableObservation.from_dict(legacy)
    assert back.snr is None and back.clipped is None, (
        f"legacy rows must load quality as unmeasured: {back.snr}, {back.clipped}"
    )

    # 8c. The estimator itself: a tone over a quiet floor must come out of
    #     `extract_syllables` carrying a high SNR and no clipping flag, and the same
    #     tone at the rail must be flagged. Both measured on the audio, at ingest —
    #     nothing here is a filter: the clipped syllable is still an observation.
    rng_q = np.random.default_rng(11)
    n_floor = int(0.40 * features.SAMPLE_RATE)
    n_tone = int(0.10 * features.SAMPLE_RATE)

    def _quality_case(tone_amp: float) -> SyllableObservation:
        floor = 0.002 * rng_q.normal(size=n_floor)
        tone = tone_amp * np.sin(
            2 * np.pi * 3000.0 * np.arange(n_tone) / features.SAMPLE_RATE
        )
        signal = np.concatenate([floor, tone, floor])
        found = extract_syllables(signal, features.SAMPLE_RATE, "sp", "q0")
        assert len(found) == 1, f"expected one syllable, got {len(found)}"
        return found[0]

    quiet = _quality_case(0.5)
    assert quiet.snr is not None and quiet.snr > SNR_FULL_WEIGHT_DB, (
        f"a tone 40+ dB over the floor must score high: {quiet.snr}"
    )
    assert quiet.clipped is False
    loud = _quality_case(1.0)
    assert loud.clipped is True, "a syllable at the rail must be flagged clipped"
    assert loud.snr is not None and loud.snr > quiet.snr - 1.0

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

    # `learn_grammar`'s gap medians: measured per transition, filtered at the same
    # count floor as the transitions, and keyed so the app can look up "A>B" directly.
    rhythm_obs = [
        observation(3000.0, 0.05, species_id="s", recording_id="r2", order=i)
        for i in range(5)
    ]
    for o, g in zip(rhythm_obs, [0.0, 0.2, 0.4, 0.2, 0.6]):
        o.gap_before = g
    rhythm_types = {i: t for i, t in enumerate(["A", "B", "A", "B", "A"])}
    rhythm = learn_grammar(rhythm_obs, rhythm_types)
    assert rhythm["gaps"] == {"A>B": 0.2, "B>A": 0.5}, rhythm["gaps"]
    assert set(rhythm["gaps"]) <= {
        f"{a}>{b}" for a, row in rhythm["transitions"].items() for b in row if b != END
    }

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

    # 11b. Repeat classes: a bird whose song *is* a trill. Eight bouts of one type
    #      repeated five times collapse to a single token, so the motif path cannot see
    #      them by construction — before `_repeat_classes` they were 6 940 bouts of the
    #      production store's silence. Two things must hold: the class is found and
    #      marked `repeat`, and a single-syllable bout never becomes one (that is the
    #      transition table's self-loop, not a song).
    trills = list(songs)
    trills += [("sp", ("t", i), ["T20"] * 5) for i in range(8)]
    trills += [("sp", ("t", 100 + i), ["T21"]) for i in range(8)]
    with_repeats = cluster_song_types(trills, min_cluster_size=4)["sp"]
    kinds = {t["id"]: t["kind"] for t in with_repeats["types"]}
    repeat_ids = [i for i, k in kinds.items() if k == "repeat"]
    assert len(repeat_ids) == 1, f"trill class not recovered: {with_repeats['types']}"
    repeat_type = next(t for t in with_repeats["types"] if t["kind"] == "repeat")
    assert repeat_type["sequence"] == ["T20"] and repeat_type["count"] == 8, repeat_type
    assert with_repeats["summary"]["repeatTypes"] == 1
    assert with_repeats["summary"]["repeatCandidates"] == 8, (
        "single-syllable bouts must not count as repeat candidates: "
        f"{with_repeats['summary']}"
    )
    assert sum(1 for r in with_repeats["rows"] if r["songTypeId"] == repeat_type["id"]) == 8
    # The motifs are untouched by the addition. The corpus-wide shuffle control is in
    # docs/22 §22.2: it places the same 0.170 % of candidate bouts with repeat classes
    # on as without them, because a shuffle destroys runs and so cannot make one.
    assert {tuple(t["sequence"]) for t in with_repeats["types"] if t["kind"] == "motif"} == {
        m1, m2,
    }, with_repeats["types"]

    # 11d. The bout rule is one rule. Every caller takes the same argument, so a
    #      argument moves the grammar, the chunks and the song types together — the
    #      failure this replaces is three literal 1.0s drifting apart. The gap fixture's
    #      one break is at 1.5 s, so a 2 s rule sees one bout where the default sees two.
    assert len(bout_sequences(gap_obs, rows, 2.0)) == 1
    assert len(bout_sequences(gap_obs, rows)) == 2
    wide = learn_grammar(gap_obs, {i: r["typeId"] for i, r in enumerate(rows)}, 2.0)
    narrow = learn_grammar(gap_obs, {i: r["typeId"] for i, r in enumerate(rows)})
    assert wide["transitions"] != narrow["transitions"], (
        "the grammar must follow the bout rule it is given"
    )

    # 12. The segmentation band (`SEGMENT_BAND_HZ`). Five properties, and the fixture is
    #     the failure the owner reported: a bird buried under rumble that carries almost
    #     all of the energy. Full-band, the segmenter thresholds at 14 % of the *rumble's*
    #     peak and finds the rumble; band-limited, it finds the bird.
    rate = features.SAMPLE_RATE
    t = np.arange(int(3.0 * rate)) / rate
    rumble = 0.9 * np.sin(2 * np.pi * 60.0 * t) * (1.0 + 0.6 * np.sin(2 * np.pi * 2.0 * t))
    chirps = np.zeros_like(t)
    for onset in (0.5, 1.2, 1.9, 2.6):
        span = (t >= onset) & (t < onset + 0.09)
        chirps[span] = 0.05 * np.sin(2 * np.pi * 5200.0 * t[span]) * np.hanning(int(span.sum()))
    fixture = rumble + chirps

    # 12a. The band-limiter must actually reject, and by a lot: this is where the spectral
    #      mask that was tried first failed (see `band_limit`). 60 Hz at 0.9 against 5.2 kHz
    #      at 0.05 is a 25 dB deficit for the thing we want to keep, so anything less than
    #      ~40 dB of rejection leaves the rumble in charge of the threshold.
    kept = band_limit(fixture, rate, *SEGMENT_BAND_HZ)
    assert kept.shape == fixture.shape, "band_limit changed the length"
    rumble_only = band_limit(rumble, rate, *SEGMENT_BAND_HZ)
    rejection_db = 20.0 * math.log10(
        float(np.sqrt(np.mean(rumble ** 2)))
        / max(float(np.sqrt(np.mean(rumble_only ** 2))), 1e-12)
    )
    assert rejection_db > 40.0, f"only {rejection_db:.1f} dB of rumble rejection"
    # Zero phase: an onset must not move. A causal filter would shift every one of them.
    tone = np.sin(2 * np.pi * 5200.0 * t) * (t > 1.5)
    shifted = band_limit(tone, rate, *SEGMENT_BAND_HZ)
    assert abs(int(np.argmax(np.abs(shifted) > 0.4)) - int(1.5 * rate)) < 0.002 * rate, (
        "band_limit moved an onset — sosfiltfilt should be zero phase"
    )

    # 12b. The band envelope must ignore the rumble the full-band one is dominated by.
    full_env = envelope(peak_normalise(fixture))
    band_env = band_envelope(peak_normalise(fixture), rate, *SEGMENT_BAND_HZ)
    assert full_env.argmax() != band_env.argmax(), (
        "the fixture is meant to peak in different places in the two bands"
    )
    # The four chirps are the only in-band energy, so the band envelope's peak has to
    # land inside one of them.
    band_peak_s = band_env.argmax() * ENV_HOP / rate
    assert any(onset <= band_peak_s <= onset + 0.09 for onset in (0.5, 1.2, 1.9, 2.6)), (
        f"the band envelope peaks at {band_peak_s:.3f} s, which is not a chirp"
    )

    # 12c. ...so the segmentation finds the bird instead of the rumble. Four chirps in,
    #      four segments out, each one on a chirp.
    band_segments = _segments(band_env, rate)
    assert len(band_segments) == 4, f"expected the four chirps, got {len(band_segments)}"
    for (s0, s1), onset in zip(band_segments, (0.5, 1.2, 1.9, 2.6)):
        assert abs(s0 / rate - onset) < 0.02, (
            f"segment at {s0 / rate:.3f} s is not the chirp at {onset} s"
        )
    full_segments = _segments(full_env, rate)
    assert not any(
        any(abs(s0 / rate - onset) < 0.02 for onset in (0.5, 1.2, 1.9, 2.6))
        for s0, _ in full_segments
    ), "the full-band segmenter was supposed to miss every chirp — fixture is wrong"

    # 12d. The whole path agrees, and `segment_band=None` really is the old behaviour:
    #      it has to be, because `quality.remeasure_store` reproduces 188 986 rows of the
    #      existing corpus through it.
    banded = extract_syllables(fixture, rate, "test_bird", "fixture")
    legacy = extract_syllables(fixture, rate, "test_bird", "fixture", segment_band=None)
    assert banded, "the band-limited path described nothing"
    assert [round(o.start, 3) for o in banded] != [round(o.start, 3) for o in legacy], (
        "the band must change which syllables are described"
    )
    #      The legacy SNR must still be the old formula — a time-domain segment RMS over an
    #      envelope-derived floor, both full-band. `quality.measure_recording` holds a copy
    #      of exactly this arithmetic, so if the two ever part company the re-measurement
    #      pass starts writing numbers the corpus was not harvested with.
    legacy_env = envelope(peak_normalise(fixture))
    legacy_floor = _noise_floor(legacy_env, _segments(legacy_env, rate))
    normalised_fixture = peak_normalise(fixture)
    for o in legacy:
        s0 = int(round(o.start * rate))
        seg = normalised_fixture[s0 : s0 + int(round(o.dur * rate))]
        expected = 20.0 * math.log10(
            max(float(np.sqrt(np.mean(seg * seg))), 1e-9) / max(legacy_floor, 1e-9)
        )
        assert abs(o.snr - round(expected, 2)) < 0.02, (
            f"segment_band=None changed the SNR formula: {o.snr} vs {expected:.2f}"
        )

    # 12e. The SNR reads its numerator in the band its floor came from. On the fixture the
    #      in-band chirps sit far above the in-band floor, and the *legacy* full-band SNR of
    #      the same recording is flattered by the rumble it counts in the numerator only —
    #      which is the mechanism behind INAT227259's respectable 11.5 dB.
    assert all(o.snr is not None for o in banded)
    assert min(o.snr for o in banded) > 6.0, (
        f"the chirps should stand clear of the in-band floor: "
        f"{[round(o.snr, 1) for o in banded]}"
    )

    if verbose:
        print(
            f"learn self-test ok: typing space unchanged by default, "
            f"{len(mixed)} rows aligned through the embedder, "
            f"w=0 exactly the old objective, w=1 exactly the critic, "
            f"segmentation band finds {len(band_segments)}/4 chirps the full band misses"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
