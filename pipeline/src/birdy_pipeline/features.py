"""The 28-d descriptor of contract 8.2, from scratch in numpy.

No librosa, no scipy: the browser reimplements this function-for-function, so every
window, every mel triangle and the DCT-II are spelled out here. Nothing depends on a
library default.
"""

from __future__ import annotations

import math

import numpy as np

SAMPLE_RATE = 48000
FRAME = 1024
HOP = 512
N_BINS = FRAME // 2  # k in [0, 512)
N_MEL = 26
N_MFCC = 13
DIM = 28
PEAK_NORM = 0.9
RMS_FLOOR = 1.0e-4
RMS_REL = 0.05
BAND_FLOOR = 1.0e-10
MAG_EPS = 1.0e-10
CENTROID_FLOOR_HZ = 20.0
WINDOW_SPEC = "symmetric hann: w[i] = 0.5 - 0.5*cos(2*pi*i/(N-1))"

DIM_NAMES: list[str] = (
    [f"mfcc{i}_mean" for i in range(N_MFCC)]
    + [f"mfcc{i}_std" for i in range(N_MFCC)]
    + ["log2_centroid_mean", "flatness_mean"]
)


def hz_to_mel(hz: float | np.ndarray) -> float | np.ndarray:
    return 1125.0 * np.log(1.0 + np.asarray(hz, dtype=np.float64) / 700.0)


def mel_to_hz(mel: float | np.ndarray) -> float | np.ndarray:
    return 700.0 * (np.exp(np.asarray(mel, dtype=np.float64) / 1125.0) - 1.0)


def mel_centres_hz(n_mel: int = N_MEL, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Centre frequency of each mel band, in Hz — filter j peaks at `binPt[j+1]`."""
    mel_max = float(hz_to_mel(sample_rate / 2.0))
    j = np.arange(1, n_mel + 1, dtype=np.float64)
    return np.asarray(mel_to_hz(j / (n_mel + 1) * mel_max), dtype=np.float64)


def hann_window(n: int = FRAME) -> np.ndarray:
    """Symmetric Hann: w[i] = 0.5 - 0.5*cos(2*pi*i/(n-1))."""
    i = np.arange(n, dtype=np.float64)
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * i / (n - 1))


def mel_filterbank(
    n_mel: int = N_MEL, frame: int = FRAME, sample_rate: int = SAMPLE_RATE
) -> np.ndarray:
    """(n_mel, frame/2) triangular bank, exactly as normatively specified in 8.2.

    binPt[i] = melToHz(i/(M+1) * melMax) * N/sampleRate, i in [0, M+2); filter j
    rises from binPt[j] to binPt[j+1] and falls to binPt[j+2]; weights are not
    normalised.
    """
    n_bins = frame // 2
    mel_max = float(hz_to_mel(sample_rate / 2.0))
    idx = np.arange(n_mel + 2, dtype=np.float64)
    bin_pt = mel_to_hz(idx / (n_mel + 1) * mel_max) * frame / sample_rate

    bank = np.zeros((n_mel, n_bins))
    for j in range(n_mel):
        left, peak, right = bin_pt[j], bin_pt[j + 1], bin_pt[j + 2]
        k_lo = int(math.ceil(left))
        k_hi = min(int(math.floor(right)), n_bins - 1)
        for k in range(max(k_lo, 0), k_hi + 1):
            if k < peak:
                w = (k - left) / (peak - left) if peak > left else 0.0
            else:
                w = (right - k) / (right - peak) if right > peak else 0.0
            if w > 0.0:
                bank[j, k] = w
    return bank


def dct2_matrix(n_mfcc: int = N_MFCC, n_mel: int = N_MEL) -> np.ndarray:
    """Unnormalised DCT-II: c[i] = sum_j v[j] * cos(pi*i*(j+0.5)/n_mel)."""
    i = np.arange(n_mfcc, dtype=np.float64)[:, None]
    j = np.arange(n_mel, dtype=np.float64)[None, :]
    return np.cos(np.pi * i * (j + 0.5) / n_mel)


_WINDOW = hann_window()
_BANK = mel_filterbank()
_DCT = dct2_matrix()
_BIN_HZ = np.arange(N_BINS, dtype=np.float64) * SAMPLE_RATE / FRAME


def frame_features(
    audio: np.ndarray, sample_rate: int = SAMPLE_RATE
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-voiced-frame (mfcc[n,13], log2 centroid[n], flatness[n]).

    The clip is peak-normalised to 0.9 first; unvoiced frames are dropped.
    """
    x = np.asarray(audio, dtype=np.float64).ravel()
    if x.size < FRAME:
        return np.zeros((0, N_MFCC)), np.zeros(0), np.zeros(0)
    peak = float(np.max(np.abs(x)))
    if peak <= 0.0:
        return np.zeros((0, N_MFCC)), np.zeros(0), np.zeros(0)
    x = x * (PEAK_NORM / peak)

    starts = np.arange(0, x.size - FRAME + 1, HOP)
    frames = np.stack([x[s : s + FRAME] for s in starts])  # (n, FRAME)
    rms = np.sqrt(np.mean(frames * frames, axis=1))  # unwindowed
    clip_max = float(rms.max()) if rms.size else 0.0
    voiced = (rms > RMS_FLOOR) & (rms > RMS_REL * clip_max)
    if not np.any(voiced):
        return np.zeros((0, N_MFCC)), np.zeros(0), np.zeros(0)
    frames = frames[voiced]

    mag = np.abs(np.fft.rfft(frames * _WINDOW, axis=1))[:, :N_BINS]
    power = mag * mag

    energy = np.maximum(power @ _BANK.T, BAND_FLOOR)  # (n, N_MEL)
    mfcc = np.log(energy) @ _DCT.T  # (n, N_MFCC)

    mag_sum = np.sum(mag, axis=1)
    centroid = np.where(mag_sum > 0.0, (mag @ _BIN_HZ) / np.maximum(mag_sum, 1e-30), 0.0)
    log_centroid = np.log2(np.maximum(centroid, CENTROID_FLOOR_HZ))

    flatness = np.exp(np.mean(np.log(mag + MAG_EPS), axis=1)) / (
        np.mean(mag, axis=1) + MAG_EPS
    )
    return mfcc, log_centroid, flatness


def descriptor(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray | None:
    """28-d descriptor, or None when the clip has no voiced frame (8.2)."""
    mfcc, log_centroid, flatness = frame_features(audio, sample_rate)
    if mfcc.shape[0] == 0:
        return None
    return np.concatenate(
        [
            mfcc.mean(axis=0),
            mfcc.std(axis=0),  # population std
            [float(log_centroid.mean())],
            [float(flatness.mean())],
        ]
    )


MEL_KNOTS = 4


def _voiced_log_mel(
    audio: np.ndarray, frame: int, hop: int, window: np.ndarray, bank: np.ndarray
) -> np.ndarray | None:
    """(n_voiced_frames, n_mel) natural-log mel energies, or None if nothing is voiced.

    The voicing rule and the peak normalisation are the ones `frame_features` uses, so a
    clip's patch and its 28-d descriptor are computed over the same set of frames.
    """
    x = np.asarray(audio, dtype=np.float64).ravel()
    if x.size < frame:
        return None
    peak = float(np.max(np.abs(x)))
    if peak <= 0.0:
        return None
    x = x * (PEAK_NORM / peak)
    starts = np.arange(0, x.size - frame + 1, hop)
    frames = np.stack([x[s : s + frame] for s in starts])
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    clip_max = float(rms.max()) if rms.size else 0.0
    voiced = (rms > RMS_FLOOR) & (rms > RMS_REL * clip_max)
    if not np.any(voiced):
        return None
    mag = np.abs(np.fft.rfft(frames[voiced] * window, axis=1))[:, : frame // 2]
    return np.log(np.maximum((mag * mag) @ bank.T, BAND_FLOOR))


def _resample_knots(logmel: np.ndarray, knots: int) -> np.ndarray:
    """Average `logmel`'s frames into `knots` equal shares of its own length, then centre.

    Centring by the single scalar mean — not per band, not per knot — is what makes this a
    description of spectral *shape over time* rather than of loudness, while leaving the
    overall spectral tilt visible. The tilt is a measured real-versus-synthetic difference
    (docs/09 §9.1 result 2: real recordings sit at -1.59 relative energy above 6 kHz and we
    sit at -0.01), so removing it here would hide the very thing a critic should see.
    """
    edges = np.linspace(0, logmel.shape[0], knots + 1).astype(int)
    out = np.stack([
        logmel[edges[i] : max(edges[i] + 1, edges[i + 1])].mean(axis=0) for i in range(knots)
    ])
    return out - out.mean()


def mel_path(audio: np.ndarray, knots: int = MEL_KNOTS, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Log-mel energies at `knots` points across the clip: shape (knots, N_MEL).

    The 28-d descriptor of 8.2 is a *mean* over frames, so it cannot distinguish a syllable
    whose spectrum sweeps from one that holds still with the same average. That mean is
    simultaneously the fit's only evidence and its objective, which is why the fit saturates
    against it while the sound is still wrong. This keeps the time axis, coarsely.

    Each knot is the mean log-mel over its share of the voiced frames, and the whole path is
    centred by its own mean so it describes spectral *shape over time* rather than loudness.
    Comparing two clips of different durations is therefore well defined: both are resampled
    onto the same `knots` fractions of their own length.
    """
    logmel = _voiced_log_mel(audio, FRAME, HOP, _WINDOW, _BANK)
    if logmel is None:
        return np.zeros((knots, N_MEL))
    return _resample_knots(logmel, knots)


# --- the critic's patch (docs/09 §9.3 Part 1) --------------------------------------

#: Time steps across the syllable's own duration. 32 as specified in docs/09.
PATCH_KNOTS = 32
#: The patch gets its own, shorter analysis frame. `FRAME` is 21.3 ms, and the median
#: harvested syllable is 60 ms — three windows, which smears a sweep into a smudge and
#: would hand the critic a representation blind to the exact thing docs/09 §9.2 says the
#: 28-d mean is blind to. 512 samples is 10.7 ms and 94 Hz per bin: still finer than the
#: 400 Hz f0 floor of `learn.F0_MIN_HZ`, and four times the time resolution.
PATCH_FRAME = 512
PATCH_HOP = 128
#: Bands above this are dropped before anything sees the patch. **This is the single most
#: important line in the file for docs/09 §9.5.** xeno-canto is largely mp3, which cuts hard
#: near 16 kHz, so its top mel bands floor at `log(BAND_FLOOR)` = -23; our renders roll off
#: gently from `syrinx.TRACT_LP_HZ` and leave them finite. That is a twenty-log-unit gap that
#: has nothing to do with birds, and a critic handed it would learn "is it an mp3" in one
#: epoch and teach the fit nothing. Only bands whose centre is below the cut survive.
PATCH_LP_HZ = 15000.0

_PATCH_WINDOW = hann_window(PATCH_FRAME)
_PATCH_BANK = mel_filterbank(N_MEL, PATCH_FRAME, SAMPLE_RATE)
#: How many low bands survive `PATCH_LP_HZ` — 23 of 26 at the shipped constants.
PATCH_MEL = int(np.sum(mel_centres_hz() <= PATCH_LP_HZ))
PATCH_SHAPE = (PATCH_KNOTS, PATCH_MEL)
PATCH_DIM = PATCH_KNOTS * PATCH_MEL


def mel_patch(
    audio: np.ndarray, knots: int = PATCH_KNOTS, sample_rate: int = SAMPLE_RATE
) -> np.ndarray:
    """The critic's view of one syllable: `(knots, PATCH_MEL)` band-limited log-mel.

    This is a **measurement, not a recording**: log magnitudes only, no phase, mean-centred,
    resampled off the syllable's own duration. You cannot reconstruct recognisable audio from
    it, so `harvest.py`'s decode -> describe -> delete loop and its licensing consequences
    are untouched (docs/09 §9.4).

    Real syllables and resyntheses must both come through *this* function. Measuring the two
    sides differently is the one bug that would invalidate the whole exercise, which is why
    the band limit, the frame, the hop and the centring all live here rather than in the
    caller.
    """
    logmel = _voiced_log_mel(audio, PATCH_FRAME, PATCH_HOP, _PATCH_WINDOW, _PATCH_BANK)
    if logmel is None:
        return np.zeros((knots, PATCH_MEL))
    return _resample_knots(logmel[:, :PATCH_MEL], knots)


def standardise(
    x: np.ndarray, mean: np.ndarray, std: np.ndarray
) -> np.ndarray:
    """z = (x - mean) / max(std, 1e-6) (8.2)."""
    return (x - mean) / np.maximum(std, 1.0e-6)


_DCT_PINV = np.linalg.pinv(_DCT)  # (N_MEL, N_MFCC)


def mel_envelope(mfcc_mean: np.ndarray) -> np.ndarray:
    """The 26-band log spectral envelope behind a 13-coefficient MFCC mean.

    The forward transform is an unnormalised DCT-II that keeps 13 of 26 coefficients, so it
    is not invertible — but the pseudo-inverse recovers the *smooth* part, which is exactly
    what a spectral envelope is. Truncating to 13 cepstral coefficients is a lowpass on the
    spectrum, so what comes back is the formant structure with the harmonic fine structure
    already removed.

    This is what makes a tract resonance measurable from a store that kept no audio: the
    descriptors are per-syllable means over frames whose f0 is moving, so pitch-dependent
    structure smears out across the average while a resonance fixed in Hz survives it. That
    is the long-term-average-spectrum argument, applied to what we actually kept.
    """
    return _DCT_PINV @ np.asarray(mfcc_mean, dtype=np.float64)[:N_MFCC]


def self_test(verbose: bool = True) -> None:
    """Check the DCT-II matrix against a naive loop, plus bank/window invariants."""
    rng = np.random.default_rng(7)
    v = rng.normal(size=N_MEL)

    naive = np.zeros(N_MFCC)
    for i in range(N_MFCC):
        acc = 0.0
        for j in range(N_MEL):
            acc += v[j] * math.cos(math.pi * i * (j + 0.5) / N_MEL)
        naive[i] = acc
    fast = _DCT @ v
    err = float(np.max(np.abs(naive - fast)))
    assert err < 1.0e-12, f"DCT-II mismatch: {err}"

    w = hann_window(8)
    assert abs(w[0]) < 1e-15 and abs(w[-1]) < 1e-15, "Hann must be symmetric/zero-ended"
    assert _BANK.shape == (N_MEL, N_BINS)
    assert np.all(_BANK >= 0.0)
    assert np.all(_BANK.max(axis=1) > 0.0), "every mel band must catch a bin"
    assert abs(float(_BANK.max()) - 1.0) < 0.15, "triangles peak near 1"

    # a pure tone must land its centroid on the tone
    t = np.arange(4096) / SAMPLE_RATE
    tone = np.sin(2 * np.pi * 4000.0 * t)
    d = descriptor(tone)
    assert d is not None and d.shape == (DIM,)
    centroid_hz = 2.0 ** d[26]
    assert abs(centroid_hz - 4000.0) < 250.0, f"centroid off: {centroid_hz}"
    assert d[27] < 0.05, f"a sine should not be spectrally flat: {d[27]}"

    # --- the critic's patch (docs/09 §9.3 Part 1 step 1) ---
    #
    # The patch exists to see what the 28-d mean cannot, so the test is exactly that: a tone
    # that sweeps and a tone that holds still, chosen to have the *same* mean frequency, so
    # nothing but the time axis can separate them.
    n = int(0.20 * SAMPLE_RATE)
    tt = np.arange(n) / SAMPLE_RATE
    steady = np.sin(2 * np.pi * 4000.0 * tt)
    # 2 kHz -> 6 kHz linear sweep: instantaneous phase is the integral of the frequency.
    sweep = np.sin(2 * np.pi * (2000.0 * tt + 0.5 * (4000.0 / (n / SAMPLE_RATE)) * tt * tt))

    p_steady = mel_patch(steady)
    p_sweep = mel_patch(sweep)
    assert p_steady.shape == PATCH_SHAPE, f"patch shape {p_steady.shape} != {PATCH_SHAPE}"
    assert float(np.max(np.abs(mel_patch(steady) - p_steady))) == 0.0, "patch not deterministic"
    moved = float(np.linalg.norm(p_sweep - p_steady))
    assert moved > 5.0, f"a sweep and a steady tone must differ in the patch: {moved:.3f}"

    # ...and the 28-d descriptor must be the one that struggles, or the patch buys nothing.
    d_steady, d_sweep = descriptor(steady), descriptor(sweep)
    assert d_steady is not None and d_sweep is not None
    # Same claim in a comparable unit: relative distance within each representation.
    patch_rel = moved / max(float(np.linalg.norm(p_steady)), 1e-9)
    desc_rel = float(np.linalg.norm(d_sweep - d_steady)) / max(
        float(np.linalg.norm(d_steady)), 1e-9
    )
    assert patch_rel > desc_rel, (
        f"the patch must separate a sweep more sharply than the 28-d mean does: "
        f"patch {patch_rel:.3f} vs descriptor {desc_rel:.3f}"
    )

    # The band limit is load-bearing for §9.5: nothing above PATCH_LP_HZ may reach the critic.
    assert PATCH_MEL < N_MEL, "the patch must drop at least one band, or the mp3 tell survives"
    assert float(mel_centres_hz()[PATCH_MEL - 1]) <= PATCH_LP_HZ < float(
        mel_centres_hz()[PATCH_MEL]
    ), "PATCH_MEL must be exactly the bands centred below PATCH_LP_HZ"
    # A 20 kHz tone lives only in dropped bands, so it must read as silence to the patch.
    ultrasonic = np.sin(2 * np.pi * 20000.0 * tt)
    assert float(np.max(np.abs(mel_patch(ultrasonic)))) < float(
        np.max(np.abs(p_steady))
    ), "energy above the band limit must not dominate the patch"

    # Silence and a too-short clip must return the right shape rather than raise: the harvest
    # hands this whatever a segmenter produced, including 12-sample slivers.
    assert mel_patch(np.zeros(n)).shape == PATCH_SHAPE
    assert mel_patch(np.zeros(8)).shape == PATCH_SHAPE

    if verbose:
        print(
            f"features self-test ok: DCT-II max err {err:.2e}, "
            f"tone centroid {centroid_hz:.0f} Hz, flatness {d[27]:.4f}"
        )
        print(
            f"  patch {PATCH_KNOTS}x{PATCH_MEL} (<= {PATCH_LP_HZ / 1000:.0f} kHz, "
            f"{PATCH_FRAME}/{PATCH_HOP} frame/hop): sweep-vs-steady {patch_rel:.3f} "
            f"relative, against {desc_rel:.3f} for the 28-d mean"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
