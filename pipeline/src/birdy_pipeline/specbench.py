"""The spectral bench: is a cosine gain an *audible* gain?

**The gap this fills.** Every fit, gate and sweep in the pipeline — the learn inversion,
respfit, docrefit, the fricative routing — is judged by one number: the cosine between
28-d descriptors ("resynthesis cosine", learn.py). Nobody has ever measured whether
+0.05 of that cosine is audible. This module measures the two standard spectral
distances of the speech/birdsong literature between a resynthesis and the original
audio it was fitted from, alongside the cosine, so the two can be correlated:

* **MCD** — mel-cepstral distortion in dB (Kubichek's formula), the distance measure
  statistical parametric speech synthesis is optimised and reported against;
* **multi-resolution STFT error** — log-spectral distance at three FFT sizes
  (512/1024/2048), the loss the neural-vocoder literature converged on, sensitive at
  once to formant-scale structure (2048) and to texture (512).

The correlation across types **is** the deliverable: if the cosine does not track MCD,
then every gate in the pipeline is hill-climbing a proxy that does not measure the
sound, and docs/17's verdicts inherit that caveat. (Verdict, docs/19 §19.2: it does
not — Pearson 0.106, Spearman 0.100 over 200 types.) Each row therefore also carries
`melTarget`, the promoted successor of docs/19 §19.3: `learn.MelTargetTerm`'s
`exp(-LSD)` similarity of the render against the type's mean member mel-path,
computed on the same render the cosine is recomputed from. The bench is the verdict
instrument for that promotion — the mel target must correlate with MCD materially
better than the cosine's ~0.1 or the premise fails.

**Why channel normalisation comes first.** The recordings are field audio through an
unknown mic chain — iNatSounds is phones and handheld recorders, each with its own
spectral tilt. The Stage-1 sweep (docs/17) showed channel is the dominant nuisance
variable: a stationary recording filter moves every spectral distance far more than
the fit errors we are trying to measure. A stationary channel is a constant per-band
offset in the log domain, so before MCD we match the *global* spectral envelope: the
render's per-band log-mel mean over the whole clip is shifted onto the original's
(`channel_correct`). The same per-bin correction is applied inside the STFT distance.
Both metrics are also reported *without* the correction (`mcdDbRaw`, `stftDbRaw`), so
the size of the nuisance is measured rather than assumed.

**Alignment.** The render is the fitted type; the original is one member syllable's
slice of its recording (`start`, `dur` on the store observation). The two differ in
length by construction — the fitted `dur` is a cluster summary, the member's is one
realisation. Like `features.mel_path`, the bench treats time within a syllable as
relative: the longer clip is resampled to the shorter (`scipy.signal.resample`,
a Fourier-domain linear time warp) and frames are then paired 1:1 — DTW-free, because
the two sides are the *same syllable*, not two utterances that need alignment search.
Both sides are RMS-normalised (not peak: a peak is one sample and says nothing about
the envelope).

**Coefficient count.** 25 mel-cepstral coefficients from the pipeline's own 26-band
mel filterbank (`features.mel_filterbank`), so MCD lives in the same perceptual
frequency scale as everything else the pipeline measures. c0 is excluded from the
distance: it is log energy, which loudness and channel normalisation already own.

**Band limiting.** The iNat cache is 22.05 kHz audio: above 11 kHz the original holds
nothing, and after resampling to the pipeline's 48 kHz those mel bands sit at the
log floor while the render — which rolls off gently from `syrinx.TRACT_LP_HZ` — holds
real energy there. That gap measures the recorder's Nyquist, not the fit, and left in
it inflates MCD by tens of dB (this is exactly the mp3 tell `features.PATCH_LP_HZ`
exists to hide from the critic). The bench therefore drops every mel band and STFT
bin above the source file's own Nyquist (`band_hz`), read from the file header before
decoding. Within the kept band both sides hold real energy and the distance is about
the bird.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import soundfile as sf

from . import features, harvest, learn, syrinx

#: Mel-cepstral coefficients kept per frame. 25 of the 26 mel bands, the conventional
#: count for MCD (Kubichek 1993; the HTS/merlin lineage uses 25 or 39).
N_MCEC = 25
#: c0 is log energy; loudness normalisation owns it. The distance runs over c1..c24.
MCD_SCALE = 10.0 / math.log(10.0)  # natural-log cepstra -> dB
#: FFT sizes of the multi-resolution STFT distance (Yamamoto 2019; the auraloss/
#: neural-vocoder convention): 2048 sees formant-scale structure, 512 sees texture.
STFT_SIZES = (512, 1024, 2048)
STFT_FLOOR_DB = -200.0  # magnitude floor: 20*log10(eps) with eps = 1e-10

_WINDOW = features.hann_window(features.FRAME)
_BANK = features.mel_filterbank()
_MEL_CENTRES = features.mel_centres_hz()
_STFT_WINDOWS = {n: features.hann_window(n) for n in STFT_SIZES}
#: DCT-II matrices per surviving band count, built on demand — the band limit makes
#: the matrix a property of the pair, not of the module.
_DCTS: dict[int, np.ndarray] = {}


def _dct(n_bands: int) -> np.ndarray:
    if n_bands not in _DCTS:
        _DCTS[n_bands] = features.dct2_matrix(min(N_MCEC, n_bands), n_bands)
    return _DCTS[n_bands]


# --- framing -----------------------------------------------------------------------


def _voiced_mask(frames: np.ndarray) -> np.ndarray:
    """The voicing rule of `features.frame_features`, so the bench listens where the
    descriptor does."""
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    clip_max = float(rms.max()) if rms.size else 0.0
    return (rms > features.RMS_FLOOR) & (rms > features.RMS_REL * clip_max)


def _logmel(
    x: np.ndarray, band_hz: float | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Per-frame natural-log mel energies (n_frames, n_bands) plus the voiced mask.

    Same frame, hop, window, bank, peak normalisation and voicing rule as
    `features.frame_features` — the two sides of every comparison go through exactly
    one analysis path, the one bug that would invalidate the whole exercise. Bands
    centred above `band_hz` (the source file's Nyquist) are dropped; see the module
    docstring for why.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    if x.size < features.FRAME:
        return np.zeros((0, features.N_MEL)), np.zeros(0, dtype=bool)
    peak = float(np.max(np.abs(x)))
    if peak <= 0.0:
        return np.zeros((0, features.N_MEL)), np.zeros(0, dtype=bool)
    x = x * (features.PEAK_NORM / peak)
    starts = np.arange(0, x.size - features.FRAME + 1, features.HOP)
    frames = np.stack([x[s : s + features.FRAME] for s in starts])
    voiced = _voiced_mask(frames)
    mag = np.abs(np.fft.rfft(frames * _WINDOW, axis=1))[:, : features.N_BINS]
    logmel = np.log(np.maximum((mag * mag) @ _BANK.T, features.BAND_FLOOR))
    if band_hz is not None:
        logmel = logmel[:, _MEL_CENTRES <= band_hz]
    return logmel, voiced


def channel_correct(syn_logmel: np.ndarray, ref_logmel: np.ndarray) -> np.ndarray:
    """Shift the render's per-band log-mel mean onto the original's.

    A stationary recording channel (mic, body, codec) is a constant additive offset
    per mel band in the log domain. Subtracting each clip's own per-band mean from its
    frames and re-adding the *reference's* mean removes whatever the channel did to
    the average spectrum while leaving the render's time structure untouched. This is
    the correction docs/17's Stage-1 sweep argues is mandatory: channel, not fit
    error, is the dominant term in any raw spectral distance between a clean render
    and field audio.
    """
    return syn_logmel - syn_logmel.mean(axis=0) + ref_logmel.mean(axis=0)


def mcd_db(
    ref_logmel: np.ndarray,
    syn_logmel: np.ndarray,
    channel: bool = True,
) -> float:
    """Mel-cepstral distortion in dB, Kubichek's formula over c1..c24, frame-paired.

        MCD = (10/ln 10) * sqrt(2 * sum_d (c_ref[d] - c_syn[d])^2)

    averaged over the frames voiced on either side. Natural-log cepstra come from the
    pipeline's own mel bank and DCT-II (`features.dct2_matrix`), so the unit is the
    standard dB of the speech literature: ~1 dB is a just-noticeable spectral
    difference, 5-8 dB is two different sounds.
    """
    n = min(ref_logmel.shape[0], syn_logmel.shape[0])
    if n == 0:
        return math.nan
    ref, syn = ref_logmel[:n], syn_logmel[:n]
    if channel:
        syn = channel_correct(syn, ref)
    cref = _dct(ref.shape[1]) @ ref.T  # (n_mcec, n)
    csyn = _dct(ref.shape[1]) @ syn.T
    d2 = np.sum((cref[1:] - csyn[1:]) ** 2, axis=0)  # c0 excluded: it is gain
    return float(np.mean(MCD_SCALE * np.sqrt(2.0 * d2)))


def _stft_db(x: np.ndarray, n_fft: int, band_hz: float | None = None) -> np.ndarray:
    """(n_frames, n_bins) magnitude spectrogram in dB, hop n_fft//2."""
    x = np.asarray(x, dtype=np.float64).ravel()
    if x.size < n_fft:
        return np.zeros((0, n_fft // 2))
    hop = n_fft // 2
    starts = np.arange(0, x.size - n_fft + 1, hop)
    frames = np.stack([x[s : s + n_fft] for s in starts])
    mag = np.abs(np.fft.rfft(frames * _STFT_WINDOWS[n_fft], axis=1))[:, : n_fft // 2]
    if band_hz is not None:
        bin_hz = np.arange(n_fft // 2) * features.SAMPLE_RATE / n_fft
        mag = mag[:, bin_hz <= band_hz]
    return np.maximum(20.0 * np.log10(mag), STFT_FLOOR_DB)


def _lsd_db(ref_db: np.ndarray, syn_db: np.ndarray, channel: bool) -> float:
    """Log-spectral distance: mean over frames of the per-frame RMS bin error in dB."""
    n = min(ref_db.shape[0], syn_db.shape[0])
    if n == 0:
        return math.nan
    ref, syn = ref_db[:n], syn_db[:n]
    if channel:
        # The same stationary-channel argument as `channel_correct`, per FFT bin:
        # remove the clip-level mean spectrum difference, keep the time structure.
        syn = syn - syn.mean(axis=0) + ref.mean(axis=0)
    return float(np.mean(np.sqrt(np.mean((ref - syn) ** 2, axis=1))))


def stft_error_db(
    ref: np.ndarray,
    syn: np.ndarray,
    channel: bool = True,
    band_hz: float | None = None,
) -> float:
    """Multi-resolution STFT error: LSD in dB at 512/1024/2048, averaged.

    A single FFT size trades time against frequency; the average over three octaves
    of resolution is what the neural-vocoder literature settled on precisely because
    no one scale sees both formants and texture.
    """
    vals = [
        _lsd_db(_stft_db(ref, n, band_hz), _stft_db(syn, n, band_hz), channel)
        for n in STFT_SIZES
    ]
    return float(np.mean(vals))


# --- the pair ----------------------------------------------------------------------
#: A pair shorter than this after alignment has too few frames for either metric.
MIN_PAIR_SECONDS = 2.0 * features.FRAME / features.SAMPLE_RATE


def align_pair(
    ref: np.ndarray, syn: np.ndarray, sample_rate: int = features.SAMPLE_RATE
) -> tuple[np.ndarray, np.ndarray]:
    """Length- and loudness-normalise a (original, render) pair.

    The longer clip is resampled to the shorter with `scipy.signal.resample` — a
    Fourier-domain linear time warp, the same "time within a syllable is relative"
    assumption `features.mel_path` makes when it resamples both sides onto knot
    fractions. Chosen over padding (which would compare bird with silence) and over
    DTW (which answers an alignment question two renditions of the same syllable do
    not pose, and can hide a genuinely wrong time course). Both sides are then scaled
    to unit RMS: loudness is the recorder's gain knob, not the fit's business.
    """
    from scipy.signal import resample

    ref = np.asarray(ref, dtype=np.float64).ravel()
    syn = np.asarray(syn, dtype=np.float64).ravel()
    n = min(ref.size, syn.size)
    if ref.size > n:
        ref = resample(ref, n)
    if syn.size > n:
        syn = resample(syn, n)

    def unit_rms(x: np.ndarray) -> np.ndarray:
        rms = float(np.sqrt(np.mean(x * x))) if x.size else 0.0
        return x / rms if rms > 1.0e-9 else x

    return unit_rms(ref), unit_rms(syn)


def bench_pair(
    ref: np.ndarray,
    syn: np.ndarray,
    sample_rate: int = features.SAMPLE_RATE,
    band_hz: float | None = None,
) -> dict[str, float] | None:
    """MCD and multi-resolution STFT error of one aligned pair, with and without the
    channel correction. None when the pair is too short to frame.

    `band_hz` is the source recording's own Nyquist: bands and bins above it measure
    the file format, not the fit (module docstring, "Band limiting").
    """
    ref, syn = align_pair(ref, syn, sample_rate)
    if ref.size < int(MIN_PAIR_SECONDS * sample_rate):
        return None
    ref_logmel, ref_voiced = _logmel(ref, band_hz)
    syn_logmel, syn_voiced = _logmel(syn, band_hz)
    keep = ref_voiced | syn_voiced
    if not np.any(keep):
        return None
    return {
        "mcdDb": mcd_db(ref_logmel[keep], syn_logmel[keep], channel=True),
        "mcdDbRaw": mcd_db(ref_logmel[keep], syn_logmel[keep], channel=False),
        "stftDb": stft_error_db(ref, syn, channel=True, band_hz=band_hz),
        "stftDbRaw": stft_error_db(ref, syn, channel=False, band_hz=band_hz),
    }


# --- the cosine, recomputed exactly as learn measures it ----------------------------


def type_reference(
    members: Sequence[learn.SyllableObservation],
    frame: tuple[np.ndarray, np.ndarray] | None,
) -> np.ndarray | None:
    """The type's reference vector: the mean of its members' 28-d descriptors,
    standardised into the harvest population frame and unit-normalised — the `real[i]`
    of learn.py's fit loop."""
    rows = [np.asarray(o.descriptor, dtype=float) for o in members if o.descriptor]
    if not rows:
        return None
    mean_row = np.mean(np.stack(rows), axis=0)
    if frame is not None:
        mean_row = features.standardise(mean_row, frame[0], frame[1])
    return learn._unit(mean_row)


def render_cosine(
    syllable: dict[str, Any],
    reference: np.ndarray,
    calibration: syrinx.Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    sample_rate: int = features.SAMPLE_RATE,
) -> float | None:
    """The resynthesis cosine, recomputed through learn's exact path
    (`render_and_measure`): render, peak-normalise, 28-d descriptor, standardise into
    the population frame, unit-normalise, dot with the type's reference."""
    audio = syrinx.peak_normalise(
        syrinx.render_syllable(
            syllable, sample_rate=sample_rate, calibration=calibration
        )
    )
    d = features.descriptor(audio, sample_rate)
    if d is None:
        return None
    if frame is not None:
        d = features.standardise(d, frame[0], frame[1])
    return float(learn._unit(d) @ reference)


# --- the bench run -----------------------------------------------------------------


def _medoid_member(
    members: Sequence[learn.SyllableObservation],
) -> learn.SyllableObservation | None:
    """The member nearest the type's descriptor mean, among members with a descriptor.

    The comparison should hear a *typical* rendition of the type, not whichever row
    the segmenter emitted first: an outlier member would hand the bench a fit error
    the type does not have. The medoid is the cheapest honest choice — same idea as
    the diverse pick's k-medoid in cli.py."""
    rows = [o for o in members if o.descriptor]
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    d = np.stack([np.asarray(o.descriptor, dtype=float) for o in rows])
    centre = d.mean(axis=0)
    return rows[int(np.argmin(np.linalg.norm(d - centre, axis=1)))]


#: Suffixes a cached recording may carry, in preference order. `.wav` first so a lossless
#: copy wins wherever both exist.
BENCH_SUFFIXES = (".wav", ".flac", ".ogg", ".oga", ".aiff", ".aif", ".w64", ".mp3")


def resolve_audio(recording_id: str, caches: "list[Path]") -> Path | None:
    """The first cached file for this recording, across every cache and suffix.

    **Why this is not just `cache / f"{id}.wav"` any more.** `harvest` streams and deletes, so
    for most of the project the only audio on disk was the owner-sanctioned iNaturalist WAV
    cache — which is why this bench was gated on `recording_id.startswith("INAT")` and why the
    paper's population caveat reads "753 skipped, no cached audio". 1 033 fitted types (6.4 %)
    had no iNaturalist member at all and were unreachable here for no reason except which
    archive their audio came from.

    **The two caches are NOT interchangeable references, and this is measured.** On a 60-type
    run the arms come out at median MCD 78.96 dB for WAV-backed types against 111.70 for
    MP3-backed ones — but their comparison bands differ by an octave, because `band_hz` is the
    reference file's own Nyquist and the caches sit at 22.05 kHz and 48 kHz. Most of
    that 33 dB is therefore band, not fit: a wider band admits more high-frequency content,
    which is where the render is weakest. The MP3 cache is also lossy, so its high end is
    attenuated *below* its own Nyquist in a way `band_hz` does not reach at all.

    So `audioFormat` and `bandHz` are recorded on every row, and a cross-arm MCD comparison
    needs a common band before it means anything. **Owed:** an explicit band cap so both arms
    are scored to the same ceiling. Until then, read the arms separately and never average
    them.
    """
    for cache in caches:
        for suffix in BENCH_SUFFIXES:
            p = cache / f"{recording_id}{suffix}"
            if p.exists():
                return p
    return None


def run_bench(
    store: harvest.HarvestStore,
    inventory: dict[str, Any],
    audio_cache: Path,
    calibration: syrinx.Calibration | None,
    limit: int = 200,
    log: Callable[[str], None] = print,
    extra_caches: "list[Path] | None" = None,
) -> dict[str, Any]:
    """Render up to `limit` fitted types against their original audio and correlate.

    A type qualifies when it (a) ships in the inventory with a `learned` block,
    (b) has members in the store's typing.json, and (c) at least one member's
    recording is iNat audio still sitting in `audio_cache` — the only audio that
    exists, per AGENTS.md's owner-sanctioned exception. Everything else is skipped
    with a counted reason, never silently.
    """
    audio_cache = Path(audio_cache)
    caches = [audio_cache] + [Path(p) for p in (extra_caches or [])]
    frame = learn.population_frame(store.syllables)
    if frame is None:
        raise RuntimeError("the store holds no syllable descriptors to frame against")

    typing_path = store.root / learn.TYPING_NAME
    typing = json.loads(typing_path.read_text(encoding="utf-8"))
    obs_by_key = {(o.species_id, o.recording_id, o.order): o for o in store.syllables}
    members_of: dict[tuple[str, str], list[learn.SyllableObservation]] = {}
    for e in typing.get("entries", []):
        o = obs_by_key.get((e["speciesId"], e["recordingId"], int(e["order"])))
        if o is not None:
            members_of.setdefault((e["speciesId"], str(e["typeId"])), []).append(o)

    rows: list[dict[str, Any]] = []
    skipped = {
        "noMembers": 0,
        "noCachedAudio": 0,
        "decode": 0,
        "tooShort": 0,
        "noCosine": 0,
        "noMelPath": 0,
    }
    for sp in inventory.get("species", []):
        if limit is not None and len(rows) >= limit:
            break
        for syl in sp.get("syllables", []):
            if limit is not None and len(rows) >= limit:
                break
            learned_block = syl.get("learned")
            if not learned_block:
                continue
            members = members_of.get((sp["id"], str(syl.get("id", ""))))
            if not members:
                skipped["noMembers"] += 1
                continue
            cached = [o for o in members if resolve_audio(o.recording_id, caches)]
            if not cached:
                skipped["noCachedAudio"] += 1
                continue
            member = _medoid_member(cached)
            reference = type_reference(members, frame)
            if member is None or reference is None:
                skipped["noMembers"] += 1
                continue
            try:
                wav_path = resolve_audio(member.recording_id, caches)
                if wav_path is None:
                    skipped["noCachedAudio"] += 1
                    continue
                # The file's own Nyquist is the band limit of the comparison:
                # anything above it measures the format, not the fit.
                band_hz = float(sf.info(str(wav_path)).samplerate) / 2.0
                mono, rate = harvest.decode(wav_path, features.SAMPLE_RATE)
            except Exception as exc:
                log(f"  skip {sp['id']}/{syl['id']}: decode failed: {exc}")
                skipped["decode"] += 1
                continue
            i0 = max(0, int(member.start * rate))
            i1 = min(mono.size, int((member.start + member.dur) * rate))
            original = mono[i0:i1]
            render = syrinx.peak_normalise(
                syrinx.render_syllable(
                    syl, sample_rate=features.SAMPLE_RATE, calibration=calibration
                )
            )
            pair = bench_pair(original, render, band_hz=band_hz)
            if pair is None:
                skipped["tooShort"] += 1
                continue
            cosine = render_cosine(syl, reference, calibration, frame)
            if cosine is None:
                skipped["noCosine"] += 1
                continue
            # The docs/19-promoted fit target, scored on the same render the cosine
            # was recomputed from, against the same members' mean mel-path the fit
            # would aim at — the correlation of this column with MCD is the verdict
            # on whether the promotion was right.
            mel_term = learn.mel_target_term(members, 1.0)
            if mel_term is None:
                skipped["noMelPath"] += 1
                continue
            rows.append(
                {
                    "species": sp["id"],
                    "typeId": str(syl.get("id", "")),
                    "members": len(members),
                    "recordingId": member.recording_id,
                    # The reference's container, so a lossless arm and a lossy one can be
                    # read separately instead of averaged. See `resolve_audio`.
                    "audioFormat": wav_path.suffix.lstrip(".").lower(),
                    "bandHz": round(band_hz, 1),
                    "storedCosine": learned_block.get("resynthesisCosine"),
                    "cosine": round(cosine, 4),
                    "melTarget": round(mel_term.similarity(render), 4),
                    **{k: round(v, 3) for k, v in pair.items()},
                }
            )
            if len(rows) % 25 == 0:
                log(f"  {len(rows)} types benched")

    report: dict[str, Any] = {
        "store": str(store.root),
        "audioCache": str(audio_cache),
        "types": rows,
        "skipped": skipped,
        "correlations": correlations(rows),
    }
    return report


def correlations(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Pearson and Spearman of each fit-objective candidate against MCD and STFT error.

    Pearson asks "is the relationship linear", Spearman asks "does it even rank" —
    the second is the one that matters for the gates, which only ever compare two
    fits. Expect negative signs: a better fit means a *higher* score and a *lower*
    distortion, so a working proxy shows up as a negative correlation. n < 3 reports
    nothing rather than a noise correlation on two points. The candidates are the
    incumbent 28-d cosine and, when the rows carry it, the docs/19 mel target.
    """
    from scipy import stats

    out: dict[str, Any] = {"n": len(rows)}
    if len(rows) < 3:
        return out
    for score_key, dist_key, label in (
        ("cosine", "mcdDb", "cosineVsMcd"),
        ("cosine", "stftDb", "cosineVsStft"),
        ("melTarget", "mcdDb", "melTargetVsMcd"),
        ("melTarget", "stftDb", "melTargetVsStft"),
    ):
        if score_key not in rows[0]:
            continue
        s = np.asarray([r[score_key] for r in rows], dtype=float)
        v = np.asarray([r[dist_key] for r in rows], dtype=float)
        ok = np.isfinite(v) & np.isfinite(s)
        if int(ok.sum()) < 3:
            continue
        p = stats.pearsonr(s[ok], v[ok])
        sp = stats.spearmanr(s[ok], v[ok])
        out[label] = {
            "pearson": round(float(p.statistic), 4),
            "pearsonP": float(p.pvalue),
            "spearman": round(float(sp.statistic), 4),
            "spearmanP": float(sp.pvalue),
            "n": int(ok.sum()),
        }
    return out


def format_report(report: dict[str, Any]) -> str:
    """The correlation table and the three rows a reader reaches for first."""
    rows = report["types"]
    lines = [
        f"specbench: {len(rows)} types benched "
        f"(skipped {sum(report['skipped'].values())}: "
        + ", ".join(f"{k} {v}" for k, v in report["skipped"].items())
        + ")",
    ]
    corr = report["correlations"]
    lines.append(
        f"{'correlation':<16} {'pearson':>8} {'p':>10} {'spearman':>9} "
        f"{'p':>10} {'n':>4}"
    )
    for label in ("cosineVsMcd", "cosineVsStft", "melTargetVsMcd", "melTargetVsStft"):
        c = corr.get(label)
        if c:
            lines.append(
                f"{label:<16} {c['pearson']:>8.3f} {c['pearsonP']:>10.2e} "
                f"{c['spearman']:>9.3f} {c['spearmanP']:>10.2e} {c['n']:>4}"
            )
    if rows:
        by_cos = sorted(rows, key=lambda r: r["cosine"])
        picked = [
            ("worst", by_cos[0]),
            ("median", by_cos[len(by_cos) // 2]),
            ("best", by_cos[-1]),
        ]
        lines.append(
            f"\n{'':<7} {'type':<38} {'cos':>6} {'stored':>6} {'mel':>6} {'mcdDb':>6} "
            f"{'raw':>6} {'stft':>6} {'raw':>6}"
        )
        for tag, r in picked:
            stored = r["storedCosine"]
            lines.append(
                f"{tag:<7} {r['species'] + '/' + r['typeId']:<38} "
                f"{r['cosine']:>6.3f} "
                f"{stored if stored is not None else float('nan'):>6.3f} "
                f"{r.get('melTarget', float('nan')):>6.3f} "
                f"{r['mcdDb']:>6.2f} {r['mcdDbRaw']:>6.2f} "
                f"{r['stftDb']:>6.2f} {r['stftDbRaw']:>6.2f}"
            )
        mcd = [r["mcdDb"] for r in rows]
        stft = [r["stftDb"] for r in rows]
        lines.append(
            f"\nMCD median {float(np.median(mcd)):.2f} dB "
            f"(p10 {float(np.percentile(mcd, 10)):.2f}, "
            f"p90 {float(np.percentile(mcd, 90)):.2f}); "
            f"STFT error median {float(np.median(stft)):.2f} dB "
            f"(p10 {float(np.percentile(stft, 10)):.2f}, "
            f"p90 {float(np.percentile(stft, 90)):.2f})"
        )
    return "\n".join(lines)


# --- self-test ----------------------------------------------------------------------


def self_test(verbose: bool = True) -> None:
    """Prove the bench measures something the cosine does not, and that the channel
    correction undoes a channel.

    1. A render against itself must score ~0 dB on both metrics.
    2. A *time-varying* distortion — the second half of the syllable low-passed at
       2.5 kHz — is plainly audible, and no stationary-channel correction can absorb
       it. The corrected MCD and STFT error must rise sharply while the 28-d cosine
       barely moves (measured on this fixture: +77.9 dB MCD and +7.0 dB STFT against
       a cosine drop of 0.015). This is the whole reason the bench exists.
    3. A *stationary* channel — an FIR tilt [1, -0.6], a first-difference high shelf
       of the sort a cheap mic's presence rise produces — must score a large raw MCD
       that the channel correction mostly removes (measured: 105 dB raw -> 4.3 dB
       corrected). That asymmetry between fixtures 2 and 3 is the design: the
       correction exists because docs/17's Stage-1 sweep found channel is the
       dominant nuisance, and it is only allowed to remove what does not vary in time.
    """
    sr = features.SAMPLE_RATE
    syllable: dict[str, Any] = {
        "id": "benchTest",
        "dur": 0.25,
        "level": 0.85,
        "timbre": "reed",
        "contour": [[0.0, 3200.0], [0.4, 4400.0], [0.7, 2800.0], [1.0, 3600.0]],
        "noise": 0.12,
        "formants": [[2400.0, 6.0, 0.5], [5400.0, 6.0, 0.25]],
    }
    ref = syrinx.peak_normalise(syrinx.render_syllable(syllable, sample_rate=sr))

    identical = bench_pair(ref, ref)
    assert identical is not None
    assert identical["mcdDb"] < 0.01, f"identity MCD {identical['mcdDb']}"
    assert identical["stftDb"] < 0.01, f"identity STFT {identical['stftDb']}"

    def raw_cosine(a: np.ndarray, b: np.ndarray) -> float:
        da, db = features.descriptor(a, sr), features.descriptor(b, sr)
        assert da is not None and db is not None
        return float(learn._unit(da) @ learn._unit(db))

    # 2: time-varying damage. Low-pass only the back half — audibly wrong, and not a
    # channel, so the corrected metrics must say so.
    half = ref.copy()
    half[len(half) // 2 :] = syrinx._one_pole_lp(
        ref[len(half) // 2 :].copy(), 2500.0, sr
    )
    half = syrinx.peak_normalise(half)
    dist = bench_pair(ref, half)
    assert dist is not None
    cos_drop = 1.0 - raw_cosine(ref, half)
    mcd_rise = dist["mcdDb"] - identical["mcdDb"]
    stft_rise = dist["stftDb"] - identical["stftDb"]
    assert mcd_rise > 2.0, f"MCD must hear the damaged half: +{mcd_rise:.2f} dB"
    assert stft_rise > 2.0, f"STFT must hear the damaged half: +{stft_rise:.2f} dB"
    assert cos_drop < 0.10, (
        f"the 28-d cosine moved {cos_drop:.3f} on a +{mcd_rise:.1f} dB distortion — "
        "the premise of this bench (cosine is blind to audible damage) is not "
        "demonstrated by this fixture"
    )

    # 2b. The docs/19-promoted successor must NOT share that blindness: the mel target
    # of the damaged render against the undamaged render's own path must fall far
    # (measured: 1.0 -> 0.46, LSD 0.78 log units, a 0.54 drop against the cosine's
    # 0.015), and identity must score 1.
    mel_term = learn.MelTargetTerm(features.mel_path(ref)[:, : features.PATCH_MEL], 1.0)
    assert mel_term.similarity(ref) == 1.0
    mel_drop = 1.0 - mel_term.similarity(half)
    assert mel_drop > 5.0 * cos_drop, (
        f"the mel target must out-see the cosine on audible damage: "
        f"{mel_drop:.3f} vs {cos_drop:.3f}"
    )

    # 3: a stationary channel must be caught raw and corrected away.
    tilted = np.convolve(ref, [1.0, -0.6])[: ref.size]
    tilt = bench_pair(ref, tilted)
    assert tilt is not None
    assert tilt["mcdDbRaw"] > 2.0, (
        f"the raw MCD must see the channel ({tilt['mcdDbRaw']:.2f} dB) — else the "
        "nuisance docs/17 warns about is not in this fixture"
    )
    assert tilt["mcdDb"] < tilt["mcdDbRaw"] * 0.5, (
        f"channel correction must remove most of a stationary channel: "
        f"{tilt['mcdDb']:.2f} dB corrected vs {tilt['mcdDbRaw']:.2f} dB raw"
    )

    if verbose:
        print(
            f"specbench self-test ok: identity {identical['mcdDb']:.3f} dB; "
            f"damaged half +{mcd_rise:.2f} dB MCD / +{stft_rise:.2f} dB STFT while "
            f"cosine drops {cos_drop:.3f} and the mel target drops {mel_drop:.3f}; "
            f"channel {tilt['mcdDbRaw']:.2f} -> "
            f"{tilt['mcdDb']:.2f} dB after correction"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
