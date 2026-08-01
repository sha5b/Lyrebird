"""Corpus sources: `synthetic` (render the inventory) and `local` (read a folder).

A clip is one point in the galaxy. The synthetic source is fully deterministic given
`--seed`: every variant draws from a generator seeded with
`(seed, species index, syllable index, variant index)`, so adding a species or
changing the iteration order does not move the other points.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

import numpy as np
import soundfile as sf

from .learn import SyllableObservation
from .syrinx import (
    SAMPLE_RATE,
    Calibration,
    Jitter,
    Syllable,
    peak_normalise,
    render_song,
    render_syllable,
)

AUDIO_SUFFIXES = (".wav", ".flac", ".ogg", ".oga", ".aiff", ".aif", ".w64")
LOCAL_CLIP_SECONDS = 0.6
LOCAL_HOP_SECONDS = 0.3


@dataclass
class Clip:
    """One rendered or loaded clip plus the metadata that lands in points.json."""

    audio: np.ndarray
    sample_rate: int
    species_id: str
    syllable_id: str
    song_id: str
    duration: float
    source: str


def load_inventory(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def syllable_table(species: dict[str, Any]) -> dict[str, Syllable]:
    return {s["id"]: Syllable.from_dict(s) for s in species.get("syllables", [])}


def _rng(seed: int, *parts: int) -> np.random.Generator:
    return np.random.default_rng([seed, *parts])


class Cancelled(RuntimeError):
    """A build was asked to stop. Nothing has been written; the old assets still stand."""


def synthetic_corpus(
    inventory: dict[str, Any],
    calibration: Calibration | None,
    variants: int = 24,
    song_variants: int = 3,
    seed: int = 0,
    sample_rate: int = SAMPLE_RATE,
    jitter: Jitter | None = None,
    verbose: bool = True,
    should_stop: Callable[[], bool] | None = None,
) -> list[Clip]:
    """`variants` renders of every syllable + `song_variants` of every song.

    `should_stop` is polled per species. A build that is asked to stop raises rather
    than returning what it has: half a corpus embeds into a galaxy that looks finished
    and is not, and the assets on disk are still a complete older build.
    """
    jit = Jitter() if jitter is None else jitter
    clips: list[Clip] = []
    for si, species in enumerate(inventory["species"]):
        if should_stop and should_stop():
            raise Cancelled("stopped while rendering the corpus")
        sid = species["id"]
        table = syllable_table(species)
        n_before = len(clips)
        for yi, syl in enumerate(table.values()):
            for v in range(variants):
                rng = _rng(seed, si, yi, v)
                audio = render_syllable(
                    syl,
                    sample_rate=sample_rate,
                    rng=rng,
                    jitter=jit if v > 0 else Jitter.none(),
                    calibration=calibration,
                )
                clips.append(
                    Clip(
                        audio=peak_normalise(audio),
                        sample_rate=sample_rate,
                        species_id=sid,
                        syllable_id=syl.id,
                        song_id="",
                        duration=len(audio) / sample_rate,
                        source="synthetic",
                    )
                )
        for gi, song in enumerate(species.get("songs", [])):
            for v in range(song_variants):
                rng = _rng(seed, si, 1000 + gi, v)
                audio = render_song(
                    song,
                    table,
                    sample_rate=sample_rate,
                    rng=rng,
                    jitter=jit if v > 0 else Jitter.none(),
                    calibration=calibration,
                )
                clips.append(
                    Clip(
                        audio=peak_normalise(audio),
                        sample_rate=sample_rate,
                        species_id=sid,
                        syllable_id="",
                        song_id=song["id"],
                        duration=len(audio) / sample_rate,
                        source="synthetic-song",
                    )
                )
        if verbose:
            print(
                f"  {sid:24} {len(clips) - n_before:4d} clips "
                f"({len(table)} syllables x {variants} + "
                f"{len(species.get('songs', []))} songs x {song_variants})",
                file=sys.stderr,
            )
    return clips


def _observation_syllable(obs: SyllableObservation, type_id: str) -> dict[str, Any]:
    """A stored observation as an inventory syllable dict, under its learned type's id.

    Only what the observation measured. AM and vibrato cross the same depth thresholds
    `learn.fit_types` uses to decide they are real rather than tracker noise, and the id
    is the *type's*, so the render is labelled with the type it realises rather than the
    recording it came from.
    """
    d: dict[str, Any] = {
        "id": type_id,
        "dur": obs.dur,
        "level": obs.level,
        "timbre": obs.timbre,
        "contour": obs.contour,
        "attack": obs.attack,
        "hold": obs.hold,
        "harmonic": obs.harmonic,
    }
    if obs.am_depth > 0.15:
        d["am"] = obs.am
        d["amDepth"] = obs.am_depth
    if obs.vib_depth > 0.04:
        d["vib"] = {"rate": obs.vib_rate, "depth": obs.vib_depth}
    return d


def measured_corpus(
    inventory: dict[str, Any],
    typing_observations: dict[str, dict[str, list[SyllableObservation]]],
    calibration: Calibration | None,
    variants: int = 24,
    song_variants: int = 3,
    seed: int = 0,
    sample_rate: int = SAMPLE_RATE,
    verbose: bool = True,
    should_stop: Callable[[], bool] | None = None,
    anchor: bool = True,
) -> list[Clip]:
    """The anchor render plus `variants` measured realisations per learned type.

    **The difference from `synthetic_corpus` is what a knot's extent is made of.** There
    it is `Jitter` — 3 % pitch, 8 % duration, 10 % level — applied to one median render
    over and over: a sampling distribution of our own parameters. Here every variant is
    a real bird: one stored observation's measured contour, duration, level, attack and
    modulation, rendered exactly as measured. The knot's extent is then the repertoire's
    actual variance, which is the only extent the galaxy can honestly claim.

    The fitted median still leads, unjittered, as the anchor — it is the type's identity
    and the point the cluster gets its name from. Songs keep the jittered `render_song`
    path: what makes a *sequence* measured is the grammar, not the syllable acoustics,
    and this does not touch it.

    `typing_observations` maps species id -> type id -> that type's member observations,
    built from the store and its `typing.json`. Species without an entry are skipped —
    they are the hand-authored inventory's business and `synthetic_corpus` covers them.
    Members are sampled without replacement while there are at least `variants` of them;
    a type with fewer is cycled deterministically, so the same store and seed render the
    same corpus, on the same `(seed, species, syllable, variant)` scheme as
    `synthetic_corpus`.
    """
    clips: list[Clip] = []
    for si, species in enumerate(inventory["species"]):
        if should_stop and should_stop():
            raise Cancelled("stopped while rendering the corpus")
        sid = species["id"]
        types = typing_observations.get(sid)
        if not types:
            continue
        table = syllable_table(species)
        n_before = len(clips)
        n_types = 0
        for yi, tid in enumerate(sorted(types)):
            fitted = table.get(tid)
            members = types[tid]
            if fitted is None or not members:
                continue
            n_types += 1
            # The anchor: the fitted median exactly as fitted, jitter off.
            #
            # `anchor=False` renders nothing at all for a type that has members, so the
            # type exists in the galaxy only as the real observations `typing.json`
            # already assigned to it. Measured on the debug-100 dump (docs/22 §22.6):
            # the seed demand falls from 2.00 to exactly 1.00 seeds per type — every
            # source split disappears, because a split needs a point on both sides —
            # and cluster purity rises 0.423 -> 0.577. What it gives up is the rendered
            # voice's own place on the map, which is a claim about our synthesiser
            # rather than about the bird, so it is the owner's call and not a default.
            if not anchor:
                continue
            audio = render_syllable(
                fitted,
                sample_rate=sample_rate,
                rng=_rng(seed, si, yi, 0),
                jitter=Jitter.none(),
                calibration=calibration,
            )
            clips.append(
                Clip(
                    audio=peak_normalise(audio),
                    sample_rate=sample_rate,
                    species_id=sid,
                    syllable_id=tid,
                    song_id="",
                    duration=len(audio) / sample_rate,
                    source="synthetic",
                )
            )
            if len(members) >= variants:
                picked = _rng(seed, si, yi).choice(len(members), size=variants, replace=False)
            else:
                picked = np.arange(variants) % len(members)
            for v, m in enumerate(picked):
                syl = Syllable.from_dict(_observation_syllable(members[int(m)], tid))
                audio = render_syllable(
                    syl,
                    sample_rate=sample_rate,
                    rng=_rng(seed, si, yi, v + 1),
                    jitter=Jitter.none(),
                    calibration=calibration,
                )
                clips.append(
                    Clip(
                        audio=peak_normalise(audio),
                        sample_rate=sample_rate,
                        species_id=sid,
                        syllable_id=tid,
                        song_id="",
                        duration=len(audio) / sample_rate,
                        source="synthetic",
                    )
                )
        for gi, song in enumerate(species.get("songs", [])):
            for v in range(song_variants):
                rng = _rng(seed, si, 1000 + gi, v)
                audio = render_song(
                    song,
                    table,
                    sample_rate=sample_rate,
                    rng=rng,
                    jitter=Jitter() if v > 0 else Jitter.none(),
                    calibration=calibration,
                )
                clips.append(
                    Clip(
                        audio=peak_normalise(audio),
                        sample_rate=sample_rate,
                        species_id=sid,
                        syllable_id="",
                        song_id=song["id"],
                        duration=len(audio) / sample_rate,
                        source="synthetic-song",
                    )
                )
        if verbose:
            print(
                f"  {sid:24} {len(clips) - n_before:4d} clips "
                f"({n_types} types x (1 anchor + {variants} measured) + "
                f"{len(species.get('songs', []))} songs x {song_variants})",
                file=sys.stderr,
            )
    return clips


# --- local audio ------------------------------------------------------------------


def _lowpass_fir(cutoff_norm: float, taps: int = 63) -> np.ndarray:
    """Hann-windowed sinc, cutoff in cycles/sample (<= 0.5)."""
    n = np.arange(taps, dtype=np.float64) - (taps - 1) / 2.0
    h = np.sinc(2.0 * cutoff_norm * n)
    h *= 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(taps) / (taps - 1))
    return h / h.sum()


def resample(x: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear-interpolation resampler.

    Documented choice: **linear interpolation**, preceded by a 63-tap
    Hann-windowed-sinc lowpass at 0.45 * dst_rate when downsampling (without it,
    decimation would fold energy above the new Nyquist into the descriptor).
    """
    if src_rate == dst_rate or x.size == 0:
        return x
    y = x
    if dst_rate < src_rate:
        y = np.convolve(y, _lowpass_fir(0.45 * dst_rate / src_rate), mode="same")
    n_out = int(math.floor(y.size * dst_rate / src_rate))
    if n_out < 2:
        return np.zeros(0)
    pos = np.arange(n_out, dtype=np.float64) * src_rate / dst_rate
    i0 = np.floor(pos).astype(np.int64)
    i1 = np.minimum(i0 + 1, y.size - 1)
    frac = pos - i0
    return y[i0] * (1.0 - frac) + y[i1] * frac


def iter_audio_files(audio_dir: Path) -> Iterator[Path]:
    for p in sorted(Path(audio_dir).rglob("*")):
        if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES:
            yield p


def local_corpus(
    audio_dir: Path,
    sample_rate: int = SAMPLE_RATE,
    clip_seconds: float = LOCAL_CLIP_SECONDS,
    hop_seconds: float = LOCAL_HOP_SECONDS,
    verbose: bool = True,
) -> list[Clip]:
    """Read wav/flac/ogg under `audio_dir`, mono-mix, resample, slice into clips.

    Points are labelled by the *parent directory* name, so
    `audio/parus_minor/XC12345.wav` becomes `speciesId = "parus_minor"`.
    """
    audio_dir = Path(audio_dir)
    if not audio_dir.is_dir():
        raise FileNotFoundError(f"--audio-dir {audio_dir} is not a directory")
    clips: list[Clip] = []
    files = list(iter_audio_files(audio_dir))
    if not files:
        raise FileNotFoundError(
            f"no {'/'.join(s.lstrip('.') for s in AUDIO_SUFFIXES)} files under {audio_dir}"
            " (soundfile cannot read mp3 on older libsndfile - see README)"
        )
    win = int(round(clip_seconds * sample_rate))
    hop = max(1, int(round(hop_seconds * sample_rate)))
    for path in files:
        try:
            data, rate = sf.read(str(path), dtype="float64", always_2d=True)
        except Exception as exc:  # unreadable/unsupported codec
            print(f"  skip {path.name}: {exc}", file=sys.stderr)
            continue
        mono = data.mean(axis=1)
        mono = resample(mono, int(rate), sample_rate)
        label = path.parent.name if path.parent != audio_dir else "unlabelled"
        n_before = len(clips)
        for start in range(0, max(1, mono.size - win + 1), hop):
            seg = mono[start : start + win]
            if seg.size < win // 2:
                continue
            clips.append(
                Clip(
                    audio=peak_normalise(seg),
                    sample_rate=sample_rate,
                    species_id=label,
                    syllable_id="",
                    song_id=path.stem,
                    duration=seg.size / sample_rate,
                    source="local",
                )
            )
        if verbose:
            print(
                f"  {path.relative_to(audio_dir)}: {len(clips) - n_before} clips "
                f"({rate} Hz -> {sample_rate} Hz)",
                file=sys.stderr,
            )
    return clips


# --- wav output -------------------------------------------------------------------


def write_wav(path: Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), peak_normalise(audio).astype(np.float32), sample_rate, subtype="PCM_16")


def dump_clip_wavs(clips: Iterable[Clip], out_dir: Path, verbose: bool = True) -> int:
    """Write every clip as `<out_dir>/<speciesId>/<syllable|song>-<n>.wav`."""
    out_dir = Path(out_dir)
    counters: dict[tuple[str, str], int] = {}
    written = 0
    for clip in clips:
        stem = clip.syllable_id or f"song-{clip.song_id}"
        key = (clip.species_id, stem)
        n = counters.get(key, 0)
        counters[key] = n + 1
        write_wav(out_dir / clip.species_id / f"{stem}-{n:03d}.wav", clip.audio, clip.sample_rate)
        written += 1
    if verbose:
        print(f"  wrote {written} wavs to {out_dir}", file=sys.stderr)
    return written
