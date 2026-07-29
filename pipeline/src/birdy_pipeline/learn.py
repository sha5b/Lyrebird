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

from . import features, syrinx
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
    # The 28-d descriptor of this syllable's own audio (§8.2), taken while the recording
    # is still in memory. It is what `verify_type` compares a resynthesis against: the
    # recording-level descriptor averages five-second windows over everything that
    # recording contains, so it is the same vector for every type of a species and
    # cannot say which of them the model caught. Optional, because stores harvested
    # before this field existed do not have it.
    descriptor: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SyllableObservation":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


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

        start = s0 / sample_rate
        own = features.descriptor(peak_normalise(seg), sample_rate)
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
    """What makes two syllables the same type: pitch shape, length, texture, rhythm."""
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
) -> list[LearnedType]:
    """Cluster one species' observations and take the median of each cluster.

    `previous` is the species' fitted syllables from the last run, keyed by id, so a refit
    can inherit its ids instead of renumbering — see `assign_ids`.
    """
    x = np.stack([_observation_vector(o) for o in observations])
    x = (x - x.mean(axis=0)) / np.maximum(x.std(axis=0), 1e-6)
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
        contour = _median_contour(members)
        am_depths = [o.am_depth for o in members]
        vib_depths = [o.vib_depth for o in members]
        t.syllable = {
            "id": t.id,
            "label": "",  # filled in once the types are ordered by pitch
            "function": "",
            "confidence": "unlabelled",
            "refs": [],
            "dur": round(float(np.median([o.dur for o in members])), 4),
            "level": round(float(np.median([o.level for o in members])), 3),
            "timbre": Counter(o.timbre for o in members).most_common(1)[0][0],
            "contour": contour,
            "attack": round(float(np.median([o.attack for o in members])), 4),
            "hold": bool(np.mean([o.hold for o in members]) > 0.5),
            "harmonic": round(float(np.median([o.harmonic for o in members])), 3),
        }
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


def assign_ids(types: list[LearnedType], previous: dict[str, dict[str, Any]] | None) -> None:
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
            new_id = f"L{next_free:02d}"
            next_free += 1
        else:
            new_id = f"L{i:02d}"
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
) -> float:
    """Cosine between this syllable's resynthesis and the real audio it stands for."""
    audio = peak_normalise(
        render_syllable(syllable, sample_rate=sample_rate, calibration=calibration)
    )
    d = features.descriptor(audio, sample_rate)
    if d is None:
        return -1.0
    if frame is not None:
        d = features.standardise(d, frame[0], frame[1])
    return float(_unit(d) @ reference)


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


def fit_species_trachea(
    fitted: Sequence[LearnedType],
    real: Sequence[np.ndarray | None],
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    f1_hz: float,
    sample_rate: int = features.SAMPLE_RATE,
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
            total += _score(syl, real[i], calibration, frame, sample_rate)
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
    before = _score(t.syllable, reference, calibration, frame, sample_rate)
    best = before
    for _ in range(max(1, passes)):
        improved = False
        for key, candidates in _SEARCH_AXES:
            current = _axis_value(t.syllable, key)
            for value in candidates:
                if value == current:
                    continue
                trial = _with(t.syllable, key, value)
                score = _score(trial, reference, calibration, frame, sample_rate)
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


# --- putting it together -----------------------------------------------------------


def choose_k(
    observations: Sequence[SyllableObservation],
    floor: int = DEFAULT_TYPES,
    seed: int = 0,
    verbose: bool = False,
    species_id: str = "",
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

    x = np.stack([_observation_vector(o) for o in observations])
    x = (x - x.mean(axis=0)) / np.maximum(x.std(axis=0), 1e-6)
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
) -> dict[str, Any] | None:
    """Fitted syllables + a measured grammar for one species, or None if too little data."""
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
    k = choose_k(observations, floor=types, seed=seed, verbose=verbose, species_id=species_id)
    fitted = fit_types(observations, k, seed=seed, previous=previous)

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
        trachea_f1, trachea_gain = fit_species_trachea(
            fitted, real, calibration, frame, measured_f1
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
            before, after = invert_gestures(t, real[i], calibration, frame)
            gains.append(after - before)
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

    Only the `L`-prefixed ones: the authored syllables keep their own ids by definition and
    a refit never touches them. Missing or unreadable file means "no previous fit", which is
    the correct answer for a first run and the safe one for a corrupted file.
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
            if str(syl.get("id", "")).startswith("L")
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
) -> dict[str, Any]:
    """A full inventory document in the schema of `data/inventory.json`.

    It can be fed straight back into `build --inventory`, so the app renders learned
    syllables through the same path as the hand-authored ones — and shows the same
    honesty labels next to them.

    `prior` is the previous fit's learned syllables, per species and keyed by id, so a refit
    keeps its ids rather than renumbering them. `previous_fit` builds it from a written
    inventory. Passing nothing means "this is the first fit", which renumbers.
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

    known = {sp["id"]: sp for sp in inventory.get("species", [])}
    species_out: list[dict[str, Any]] = []
    for species_id in sorted(grouped, key=lambda s: -len(grouped[s])):
        # One species is the unit of work here, as one recording is in `harvest`: the
        # species already fitted are kept and written out.
        if should_stop and should_stop():
            log("stopping: asked to")
            break
        learned = learn_species(
            species_id, grouped[species_id], descriptors, calibration,
            types=types, seed=seed, verbose=verbose, frame=frame, invert=invert,
            previous=(prior or {}).get(species_id),
        )
        if learned is None:
            continue
        base = known.get(species_id, {})
        syllable_ids = [s["id"] for s in learned["syllables"]]
        species_out.append(
            {
                "id": species_id,
                "common": base.get("common", species_id),
                "scientific": base.get("scientific", ""),
                "bank": base.get("bank", "learned"),
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
