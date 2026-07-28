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
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

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
CONTOUR_KNOTS = 5
COLLINEAR_TOL = 0.035
MAX_PER_RECORDING = 400

# --- fitting -----------------------------------------------------------------------

MIN_OBSERVATIONS = 24  # per species, below which a repertoire is not worth fitting
DEFAULT_TYPES = 8
OBS_PER_TYPE = 12
GRAMMAR_MIN_COUNT = 2
END = "end"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


@dataclass
class SyllableObservation:
    """One segmented syllable, as syrinx parameters. No audio, ~30 floats."""

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SyllableObservation":
        return cls(**d)


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


def fit_types(
    observations: Sequence[SyllableObservation], k: int, seed: int = 0
) -> list[LearnedType]:
    """Cluster one species' observations and take the median of each cluster."""
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
    for rank, t in enumerate(types):
        new_id = f"L{rank:02d}"
        t.id = new_id
        t.syllable["id"] = new_id
        t.syllable["label"] = (
            f"learned {new_id} · {syrinx.f0_reference(t.syllable['contour']):.0f} Hz · "
            f"{t.syllable['dur'] * 1000:.0f} ms"
        )
    return types


# --- can the model actually sing it? -----------------------------------------------


def verify_type(
    t: LearnedType,
    reference: np.ndarray | None,
    calibration: Calibration | None,
    sample_rate: int = features.SAMPLE_RATE,
) -> None:
    """Render the fitted syllable and record how close it lands to the real thing.

    Two independent checks, because they fail differently: the descriptor cosine says
    whether it lands in the right region of the feature space the galaxy is built from,
    and the F0 error says whether the oscillator reached the pitch it was asked for. A
    syllable can pass one and fail the other — a buzz whose pitch is right but whose
    texture is not, or a clean whistle a semitone flat.
    """
    audio = peak_normalise(render_syllable(t.syllable, sample_rate=sample_rate, calibration=calibration))
    descriptor = features.descriptor(audio, sample_rate)
    if descriptor is not None and reference is not None:
        a = descriptor / max(float(np.linalg.norm(descriptor)), 1e-12)
        b = reference / max(float(np.linalg.norm(reference)), 1e-12)
        t.resynthesis_cosine = round(float(a @ b), 4)

    requested = syrinx.f0_reference(t.syllable["contour"])
    measured, _ = syrinx.measure_f0_zero_crossings(audio, steady_from=0.2)
    if requested > 0:
        t.f0_error_percent = round(100.0 * (measured - requested) / requested, 2)


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


def learn_species(
    species_id: str,
    observations: Sequence[SyllableObservation],
    descriptors: dict[str, np.ndarray] | None,
    calibration: Calibration | None,
    types: int = DEFAULT_TYPES,
    seed: int = 0,
    verbose: bool = True,
) -> dict[str, Any] | None:
    """Fitted syllables + a measured grammar for one species, or None if too little data."""
    if len(observations) < MIN_OBSERVATIONS:
        if verbose:
            log(f"  {species_id:26} {len(observations)} observations — below the "
                f"{MIN_OBSERVATIONS} needed, skipped")
        return None

    k = max(2, min(types, len(observations) // OBS_PER_TYPE))
    fitted = fit_types(observations, k, seed=seed)

    index = {id(o): i for i, o in enumerate(observations)}
    type_of = {index[id(o)]: t.id for t in fitted for o in t.members}

    for t in fitted:
        reference = None
        if descriptors:
            rows = [descriptors[o.recording_id] for o in t.members if o.recording_id in descriptors]
            if rows:
                reference = np.mean(np.stack(rows), axis=0)
        verify_type(t, reference, calibration)

    grammar = learn_grammar(observations, type_of)
    cosines = [t.resynthesis_cosine for t in fitted if t.resynthesis_cosine]
    errors = [abs(t.f0_error_percent) for t in fitted]
    if verbose:
        log(
            f"  {species_id:26} {len(observations):5d} obs -> {len(fitted)} types, "
            f"resynthesis cosine "
            + (f"{np.median(cosines):.3f}" if cosines else "n/a")
            + f", |F0 error| median {np.median(errors):.1f} %"
        )

    return {
        "id": species_id,
        "syllables": [
            {
                **t.syllable,
                "learned": {
                    "members": len(t.members),
                    "resynthesisCosine": t.resynthesis_cosine,
                    "f0ErrorPercent": t.f0_error_percent,
                },
            }
            for t in fitted
        ],
        "grammar": grammar,
        "observations": len(observations),
        "recordings": len({o.recording_id for o in observations}),
    }


def build_learned_inventory(
    observations: Iterable[SyllableObservation],
    inventory: dict[str, Any],
    calibration: Calibration | None,
    descriptors: dict[str, np.ndarray] | None = None,
    types: int = DEFAULT_TYPES,
    seed: int = 0,
    verbose: bool = True,
) -> dict[str, Any]:
    """A full inventory document in the schema of `data/inventory.json`.

    It can be fed straight back into `build --inventory`, so the app renders learned
    syllables through the same path as the hand-authored ones — and shows the same
    honesty labels next to them.
    """
    grouped: dict[str, list[SyllableObservation]] = defaultdict(list)
    for o in observations:
        grouped[o.species_id].append(o)

    known = {sp["id"]: sp for sp in inventory.get("species", [])}
    species_out: list[dict[str, Any]] = []
    for species_id in sorted(grouped, key=lambda s: -len(grouped[s])):
        learned = learn_species(
            species_id, grouped[species_id], descriptors, calibration,
            types=types, seed=seed, verbose=verbose,
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


def write_learned_inventory(path: Path, document: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(document, indent=1), encoding="utf-8")
