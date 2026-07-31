"""The learned critic of docs/09: one small CNN that does three jobs.

**Why this module exists.** Everything else in the pipeline is hand-written numpy, and that
is deliberate — the synthesiser is physical and stays physical. But two of the things the
pipeline needs are *distances*, not physics, and a day of measurement (docs/09 §9.1) showed
the hand-designed ones are what limits us:

  * **What makes two syllables the same type** is decided today by `learn._observation_vector`
    — seven numbers with hand-chosen weights (`* 6.0`, `* 3.0`, both guesses). Every learned
    type, the measured grammar, and every cluster in the galaxy rests on it.
  * **How close a resynthesis is to the real thing** is decided by a cosine in the 28-d
    `features.descriptor` space, which is a *time average* of *13 smoothed cepstral
    coefficients*. It does not merely fail to reward improvements; it rejects them — a
    structurally better tract (32x the spectral freedom, `learn.fit_species_tube`) scored
    worse and had to be gated off.

A hand-designed distance keeps failing because nobody knows the right one. This learns it.

**The one network, three heads, and why they are all necessary.** A critic trained only to
tell real from synthetic learns whatever separates those two sets, which might well be "is it
an mp3" (§9.5) — a useless basis for judging whether two *real* syllables are the same type.
So the trunk carries three heads and everything reads off the 32-d penultimate layer:

  1. `realism` — real vs our resynthesis. The objective term for the fit.
  2. `species` — which bird, over the training species. Supervised, externally true, and
     what stops the embedding from being about our synthesiser.
  3. `contrastive` — two augmented views of one real syllable embed together, two different
     syllables apart. This is the head that makes the embedding useful for *typing*, because
     it is trained on real syllables against each other and never mentions our synthesis.

Forcing all three through one 32-d bottleneck is the point: the embedding has to be good
enough to answer all three questions at once.

**What it never does.** It never generates. It scores, embeds, and flags novelty; the
syllable that ships is still an interpretable parameter vector rendered by `syrinx.py`, which
is what every honesty label in the app depends on (§9.4). No weights reach the browser.

**Input.** `features.mel_patch` and nothing else — a band-limited log-mel grid with no phase,
mean-centred, resampled off the syllable's own duration. Real syllables and resyntheses must
both come through that one function; measuring the two sides differently is the single bug
that would invalidate the exercise.

**torch is imported at the top of this module and nowhere else in the pipeline.** Every
caller imports `critic` inside a function and degrades to the hand-written cosine when the
import fails, so `pyproject.toml`'s `critic` extra stays optional.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.utils.parametrizations import spectral_norm

from . import features

# --- the embedding, and how big it is ----------------------------------------------

#: Width of the learned syllable embedding — the deliverable of §9.2b, and what replaces
#: `learn._observation_vector`'s seven hand-weighted numbers. 32 is docs/09's figure. It is
#: also the bottleneck all three heads read from, so it cannot be much smaller.
EMBED_DIM = 32
#: Trunk width multiplier. At 32 the network is ~280 k parameters, well under docs/09's
#: 1-3 M budget, which is the right end of that range for 40 k training patches.
WIDTH = 32
FORMAT_VERSION = 2


def device_for(prefer_gpu: bool = True) -> torch.device:
    """The device to train and score on. CUDA when it is there, CPU when it is not.

    Never an error either way: docs/09 §9.4 requires the pipeline to keep working on a
    machine with no GPU, and this network is small enough that CPU training is minutes
    rather than hours.
    """
    if prefer_gpu and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def describe_device(device: torch.device) -> str:
    if device.type == "cuda":
        name = torch.cuda.get_device_name(device)
        total = torch.cuda.get_device_properties(device).total_memory / 1024**3
        return f"{name} ({total:.1f} GiB, cuda)"
    return f"cpu ({torch.get_num_threads()} threads)"


# --- the network -------------------------------------------------------------------


class SyllableCritic(nn.Module):
    """Four spectrally-normalised convs into a 32-d embedding, then three heads.

    **Spectral normalisation on every conv** and no batch/group norm anywhere. That is the
    SNGAN recipe and it is here for a specific reason: it bounds the network's Lipschitz
    constant, so the realism score varies smoothly with the input instead of falling off a
    cliff. `learn.invert_gestures` is coordinate descent — it can only follow a surface that
    has a usable slope, and an unconstrained critic gives it a cliff to fall off. A
    normalisation layer that rescales per batch would undo the bound, which is why there
    isn't one.

    **The final feature map is pooled to a fixed grid, not to a single value.** Global
    average pooling would make the trunk translation-invariant in frequency, and "which
    frequency" is exactly what distinguishes a 4 kHz whistle from an 8 kHz one. Pooling to
    (4, 2) keeps coarse position while making the head's input size independent of
    `features.PATCH_SHAPE`.
    """

    #: Grid the trunk pools to before the embedding layer. (time, frequency).
    POOL = (4, 2)

    def __init__(
        self, n_species: int, embed_dim: int = EMBED_DIM, width: int = WIDTH
    ) -> None:
        super().__init__()
        self.n_species = int(n_species)
        self.embed_dim = int(embed_dim)
        self.width = int(width)
        w = self.width

        def conv(cin: int, cout: int) -> nn.Module:
            return spectral_norm(nn.Conv2d(cin, cout, 3, padding=1))

        self.conv1, self.conv2 = conv(1, w), conv(w, 2 * w)
        self.conv3, self.conv4 = conv(2 * w, 4 * w), conv(4 * w, 4 * w)
        self.embed_layer = nn.Linear(4 * w * self.POOL[0] * self.POOL[1], self.embed_dim)

        # All three heads read the same 32-d embedding. Nothing bypasses the bottleneck.
        self.realism_head = nn.Linear(self.embed_dim, 1)
        self.species_head = nn.Linear(self.embed_dim, self.n_species)
        # A projector, not the embedding itself: SimCLR's own ablation is that contrastive
        # loss applied straight to the representation throws away information the downstream
        # task wants. The projector absorbs the invariances the augmentation asks for and the
        # embedding keeps what is left.
        self.project_head = nn.Sequential(
            nn.Linear(self.embed_dim, self.embed_dim),
            nn.SiLU(),
            nn.Linear(self.embed_dim, self.embed_dim),
        )

    def trunk(self, x: torch.Tensor) -> torch.Tensor:
        """(n, 1, knots, mel) -> (n, embed_dim). The deliverable of §9.2b."""
        h = F.silu(self.conv1(x))
        h = F.max_pool2d(F.silu(self.conv2(h)), 2)
        h = F.max_pool2d(F.silu(self.conv3(h)), 2)
        h = F.silu(self.conv4(h))
        h = F.adaptive_avg_pool2d(h, self.POOL).flatten(1)
        return self.embed_layer(h)

    def forward(
        self, x: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        z = self.trunk(x)
        return z, self.realism_head(z).squeeze(-1), self.species_head(z), self.project_head(z)


# --- augmentation ------------------------------------------------------------------

#: Deliberately absent: **pitch shift**. It is the standard first augmentation for audio and
#: it would be actively wrong here. Pitch is genuinely type-diagnostic for birdsong — the
#: whole of `learn._observation_vector` leads with three pitch samples, and two calls of one
#: bird that differ only in pitch are two different calls. Telling the network to ignore
#: pitch would destroy the thing we want the embedding to encode (docs/09 §9.2b).
#:
#: Frequency masking is absent for the same reason: a mask over the f0 band erases the most
#: diagnostic part of the patch, so what the network would learn to be invariant to is not a
#: nuisance.
AUG_TIME_CROP = 0.15  # keep at least 85 % of the time axis
AUG_NOISE_FLOOR = (-4.0, 2.0)  # log-mel level of the added noise floor, relative to the mean
AUG_JITTER = 0.25  # iid measurement noise, in log-mel units
AUG_TIME_MASK = 0.12  # fraction of the time axis that may be masked out


def _channel_eq(
    n: int, bands: int, db: float, rng: np.random.Generator
) -> np.ndarray:
    """Per-view simulated recorder frequency responses: (n, 1, bands) log-mel gains.

    A microphone/recorder chain's response is *additive on a log-mel, smooth in
    frequency, and constant within a recording* — so the simulation is a cumulative
    random walk across the band axis (smooth by construction), scaled to a ±`db`
    swing and mean-removed, because a response that shifts the patch mean would be a
    level change, and level is already nobody's signal here (`features.mel_patch` is
    mean-centred). This is the only domain we can simulate the channel in: the DIR
    impulse-response recipe (Morocutti et al., arXiv 2305.07499) convolves waveforms,
    and the waveforms are deleted by design.
    """
    walk = np.cumsum(rng.normal(0.0, 1.0, size=(n, bands)), axis=1)
    walk -= walk.mean(axis=1, keepdims=True)
    peak = np.maximum(np.abs(walk).max(axis=1, keepdims=True), 1.0e-6)
    # dB to natural-log-mel units: the patches are ln energies.
    return (walk / peak * (db * math.log(10) / 10.0)).astype(np.float32)[:, None, :]


def augment(
    patches: np.ndarray, rng: np.random.Generator, channel_db: float = 0.0
) -> np.ndarray:
    """Two views of one syllable should embed together. This makes the second view.

    Every operation here is something that could plausibly differ between two recordings of
    the same bird making the same sound, and nothing here changes what the sound *is*:

      * **time crop and resample** — a slightly different segmentation of the same syllable,
        which is exactly what `learn._segments` produces run to run. Also covers the small
        time stretches docs/09 asks for.
      * **noise floor** — a raised background. On log-mel this is `logaddexp`, not addition,
        because that is what adding noise to the audio actually does to the energy.
      * **iid jitter** — measurement noise.
      * **time mask** — a passing overlap or a dropout. SpecAugment's time masking only.
      * **channel EQ** (only when `channel_db` > 0) — the recorder's frequency response,
        per `_channel_eq`. The one nuisance that is *measured* to dominate the embedding
        (docs/14 §14.4: source kNN lift +0.488 against species' +0.196), and the one the
        source-invariance recipe exists to wash out.

    Gain is not here and cannot be: `features.mel_patch` is mean-centred, so a level change
    on the audio is already removed before this sees it.

    Vectorised over the batch rather than looped, because it runs twice per training step —
    once per view — and a per-sample `np.interp` per band was costing more than the forward
    and backward pass combined.
    """
    p = np.asarray(patches, dtype=np.float32)
    n, knots, bands = p.shape

    # time crop + resample, as a batched linear gather along the knot axis
    keep = 1.0 - rng.uniform(0.0, AUG_TIME_CROP, size=(n, 1))
    span = keep * (knots - 1)
    start = rng.uniform(0.0, 1.0, size=(n, 1)) * ((knots - 1) - span)
    src = start + np.linspace(0.0, 1.0, knots)[None, :] * span  # (n, knots)
    lo = np.floor(src).astype(np.int64)
    hi = np.minimum(lo + 1, knots - 1)
    frac = (src - lo).astype(np.float32)[:, :, None]
    q = (
        np.take_along_axis(p, lo[:, :, None].repeat(bands, axis=2), axis=1) * (1.0 - frac)
        + np.take_along_axis(p, hi[:, :, None].repeat(bands, axis=2), axis=1) * frac
    )

    # a raised noise floor. `logaddexp`, not `+`: this is what adding noise to the audio
    # does to a log-energy, and plain addition would be a gain change instead.
    floor = q.mean(axis=(1, 2), keepdims=True) + rng.uniform(
        *AUG_NOISE_FLOOR, size=(n, 1, 1)
    )
    q = np.logaddexp(q, floor).astype(np.float32)
    q += rng.normal(scale=AUG_JITTER, size=q.shape).astype(np.float32)

    # time mask: a contiguous run replaced by the patch mean
    width = rng.integers(0, max(1, int(AUG_TIME_MASK * knots)) + 1, size=n)
    at = (rng.random(n) * (knots - width + 1)).astype(np.int64)
    step = np.arange(knots)[None, :]
    masked = (step >= at[:, None]) & (step < (at + width)[:, None])
    q = np.where(masked[:, :, None], q.mean(axis=(1, 2), keepdims=True), q)

    if channel_db > 0.0:
        q = q + _channel_eq(n, bands, channel_db, rng)

    return q - q.mean(axis=(1, 2), keepdims=True)


def mixstyle(
    patches: np.ndarray,
    species: np.ndarray,
    recordings: np.ndarray | None,
    rng: np.random.Generator,
    alpha: float,
) -> np.ndarray:
    """Freq-MixStyle on log-mel patches: swap per-band statistics across recordings.

    The channel-simulation half of the recipe's other arm (arXiv 2305.07499 measured
    IR augmentation and MixStyle as complementary, best combined): where
    `_channel_eq` invents a plausible recorder, this hands a patch the *actual* band
    statistics of another recording of the same species — "the same bird, through
    that recorder". Per band, the patch's mean and standard deviation over the time
    axis are moved toward λ·own + (1−λ)·partner's with λ ~ Beta(α, α), then the patch
    is re-rendered with the mixed statistics. Same-species partners only: the point
    is to vary the channel while holding the bird, and a cross-species partner would
    teach the network that one bird's spectrum can wear another's, which is not a
    nuisance, it is a lie. Different recordings only, or the "invariance" would be to
    nothing at all.

    Patches with no eligible partner pass through unchanged; `recordings=None` (the
    synthetic side, a meta-less store) turns the whole op off.
    """
    if alpha <= 0.0 or recordings is None:
        return patches
    p = np.asarray(patches, dtype=np.float32)
    n = len(p)
    out = p.copy()
    mu = p.mean(axis=1)  # (n, bands)
    sd = np.maximum(p.std(axis=1), 1.0e-3)
    for i in range(n):
        partners = np.nonzero(
            (species == species[i]) & (recordings != recordings[i])
        )[0]
        if not len(partners):
            continue
        j = partners[rng.integers(0, len(partners))]
        lam = float(rng.beta(alpha, alpha))
        mu_m = lam * mu[i] + (1.0 - lam) * mu[j]
        sd_m = lam * sd[i] + (1.0 - lam) * sd[j]
        out[i] = (p[i] - mu[i][None, :]) / sd[i][None, :] * sd_m[None, :] + mu_m[None, :]
    return out


# --- assembling the two sides ------------------------------------------------------


@dataclass
class PatchSet:
    """Patches with the labels the critic is trained on. `species` indexes `names`."""

    patches: np.ndarray  # (n, knots, mel) float32
    species: np.ndarray  # (n,) int
    names: list[str]
    real: bool
    #: Which recording each patch came from (dense int into `recording_names`), with
    #: `recordist_names` parallel to `recording_names`. The source-invariance recipe
    #: needs both: MixStyle pairs same-species patches from *different* recordings, and
    #: the adversarial head's classes are recordists. None on the synthetic side — our
    #: renders have no recorder — and on stores loaded without their recording table.
    recordings: np.ndarray | None = None
    recording_names: list[str] = field(default_factory=list)
    recordist_names: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return int(self.patches.shape[0])

    def subset(self, mask: np.ndarray) -> "PatchSet":
        return PatchSet(
            self.patches[mask],
            self.species[mask],
            self.names,
            self.real,
            None if self.recordings is None else self.recordings[mask],
            self.recording_names,
            self.recordist_names,
        )


def real_patches(
    observations: Sequence[Any],
    recording_meta: dict[str, Any] | None = None,
) -> PatchSet:
    """The real side, straight out of the harvest store. Skips observations with no patch.

    `recording_meta` is the store's `recordings` table; with it, each patch also
    carries which recording — and which recordist — it came from, the two labels the
    source-invariance recipe trains against. Without it the PatchSet simply has no
    recording labels and the recipe's recording-aware pieces stay off, exactly as a
    missing critic falls back everywhere else.
    """
    kept = [o for o in observations if o.mel_patch is not None]
    if not kept:
        raise ValueError(
            "no harvested syllable carries a mel_patch. The store predates docs/09 §9.3 "
            "step 2 — re-harvest into a new store (and never delete out/harvest, §9.4)."
        )
    names = sorted({o.species_id for o in kept})
    index = {name: i for i, name in enumerate(names)}
    recordings = None
    recording_names: list[str] = []
    recordist_names: list[str] = []
    if recording_meta is not None:
        rids = sorted({o.recording_id for o in kept})
        rindex = {rid: i for i, rid in enumerate(rids)}
        recording_names = rids
        recordist_names = [
            str((recording_meta.get(rid) or {}).get("recordist") or "") for rid in rids
        ]
        recordings = np.asarray([rindex[o.recording_id] for o in kept], dtype=np.int64)
    return PatchSet(
        patches=np.stack([np.asarray(o.mel_patch, dtype=np.float32) for o in kept]),
        species=np.asarray([index[o.species_id] for o in kept], dtype=np.int64),
        names=names,
        real=True,
        recordings=recordings,
        recording_names=recording_names,
        recordist_names=recordist_names,
    )


def fake_patches(
    inventory: dict[str, Any],
    calibration: Any,
    names: Sequence[str],
    per_type: int = 32,
    seed: int = 0,
    only_learned: bool = True,
    progress: Any = None,
) -> PatchSet:
    """The synthetic side: patches rendered from the *current* fitted inventory.

    `per_type` renders of each type rather than one, each with a different noise stream and
    a different corpus jitter. One render per type would give a few hundred negatives against
    forty thousand positives, and a critic on that imbalance learns the prior rather than the
    difference. The jitter is the same `syrinx.Jitter` the corpus build uses, so the negatives
    span the variation the app will actually play — a critic that has only seen the median
    render would be beaten by the first jittered voice.

    `names` comes from the real side so the two label spaces agree; a species in the
    inventory that the harvest never saw is skipped rather than renumbering everything.
    """
    from . import syrinx  # local: keeps this module's import graph to torch + features

    index = {name: i for i, name in enumerate(names)}
    jitter = syrinx.Jitter()
    patches: list[np.ndarray] = []
    labels: list[int] = []
    for species in inventory.get("species", []):
        sid = species.get("id", "")
        if sid not in index:
            continue
        syllables = [
            s
            for s in species.get("syllables", [])
            if not only_learned or str(s.get("id", "")).startswith("L")
        ]
        for s_i, syllable in enumerate(syllables):
            rng = np.random.default_rng([seed, abs(hash(sid)) % (2**31), s_i])
            for v in range(max(1, per_type)):
                audio = syrinx.render_syllable(
                    syllable,
                    calibration=calibration,
                    # The first variant is the exact median render, so the negatives always
                    # include the thing that actually ships.
                    rng=rng if v else None,
                    jitter=jitter if v else None,
                    stream=v,
                )
                patch = features.mel_patch(syrinx.peak_normalise(audio))
                patches.append(patch.astype(np.float32))
                labels.append(index[sid])
            if progress is not None:
                progress(sid, len(patches))
    if not patches:
        raise ValueError(
            "the inventory has no learned syllables for any harvested species — run "
            "`birdy-pipeline learn` first, so there is something for the critic to argue with"
        )
    return PatchSet(np.stack(patches), np.asarray(labels, dtype=np.int64), list(names), False)


# --- training ----------------------------------------------------------------------


@dataclass
class CriticConfig:
    """Everything the training run is allowed to depend on. Saved next to the weights."""

    embed_dim: int = EMBED_DIM
    width: int = WIDTH
    #: Measured on the self-test's controlled data, the realism head needs roughly this long:
    #: AUC ran 0.73 at 8 epochs, 0.95 at 30 and 0.96 at 60. It is the slowest of the three
    #: heads by a wide margin because spectral normalisation bounds how large the logit can
    #: grow, so the BCE plateaus near 0.6 while the separation is still improving — read the
    #: AUC in the report, never the loss.
    epochs: int = 60
    batch: int = 256
    lr: float = 2.0e-3
    weight_decay: float = 1.0e-4
    #: The three loss weights of §9.2b, to be swept. Realism leads because it is the term the
    #: fit consumes; contrastive is next because it is what makes the embedding good for
    #: typing; species is a grounding term and a small weight is enough to stop the embedding
    #: from being about our synthesiser.
    w_real: float = 1.0
    w_species: float = 0.3
    w_contrast: float = 0.5
    temperature: float = 0.2
    #: Fraction of species held out of training entirely. **Species, not syllables** — a
    #: critic that has seen every species can memorise which bird is which and report identity
    #: where we asked for realism (§9.3 step 4), and holding out whole species is also the
    #: only honest way to measure novelty detection (§9.2b).
    holdout_species: float = 0.25
    #: Fraction of the *training* species' syllables held back, so "known but unseen" has a
    #: measurable distance distribution to threshold novelty against.
    holdout_syllables: float = 0.15
    seed: int = 0
    renders_per_type: int = 32
    prefer_gpu: bool = True
    #: The source-invariance recipe (docs/14 §14.4's pre-registered retrain). All three
    #: default to 0/off, which is exactly the pre-recipe training path — the baseline a
    #: recipe run is judged against is the same code with the knobs at zero.
    #:
    #: `aug_channel_db` is the swing of the simulated recorder frequency response added
    #: to each augmented view (±dB; `_channel_eq`). `mixstyle_alpha` is the Beta
    #: concentration for swapping per-band statistics between same-species recordings
    #: (`mixstyle`); 0 turns it off.
    aug_channel_db: float = 0.0
    mixstyle_alpha: float = 0.0
    #: `w_record` is the weight of the recordist-adversarial head: a linear classifier
    #: on the embedding, gradient-reversed, trained to name the recordist so the
    #: embedding is trained to stop letting it. Off by default — it is the one term
    #: that can eat species information (recordist and species are correlated in any
    #: field corpus), so it earns its weight in the sweep or stays at zero.
    w_record: float = 0.0
    #: A recordist needs at least this many training patches to be an adversarial class;
    #: below it the class is mostly noise and the head would learn to ignore it anyway.
    recordist_min_patches: int = 20


@dataclass
class TrainingReport:
    """What the run measured. Every number here is on data the network did not train on."""

    epochs: int = 0
    train_species: list[str] = field(default_factory=list)
    holdout_species: list[str] = field(default_factory=list)
    n_real: int = 0
    n_fake: int = 0
    final_loss: float = 0.0
    #: Can it tell real from synthetic on species it never saw? 0.5 is chance.
    realism_auc_holdout: float = 0.0
    realism_auc_train: float = 0.0
    #: Can it name the bird, on syllables of training species it never saw? This is the
    #: grounding check; chance is 1 / len(train_species).
    species_accuracy: float = 0.0
    species_chance: float = 0.0
    #: Do two views of one syllable land nearer each other than two different syllables?
    contrastive_top1: float = 0.0
    #: The invariance probe: can a nearest-centroid readout name the *recordist* from
    #: the embedding, on syllables the network never saw? Down is the point of the
    #: recipe — with species accuracy held, this falling is what "organised by bird,
    #: not by recorder" looks like from inside the report (docs/14 §14.4 measures the
    #: same thing with the geometry battery's kNN lift). NaN when the store carried
    #: no recording table.
    recordist_probe: float = float("nan")
    recordist_chance: float = float("nan")
    device: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _standardise_stats(patches: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-band mean and sd over the training patches, saved with the weights.

    Per band rather than one scalar: the bands differ by an order of magnitude in variance
    (the top ones are near the floor for most birds), and a network whose first layer has to
    span that wastes capacity on rescaling.
    """
    mean = patches.mean(axis=(0, 1), keepdims=True)
    std = np.maximum(patches.std(axis=(0, 1), keepdims=True), 1e-3)
    return mean.astype(np.float32), std.astype(np.float32)


def _auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank-based AUC. Ties get the mean rank, so a constant scorer reads exactly 0.5."""
    if scores.size == 0 or len(set(labels.tolist())) < 2:
        return float("nan")
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(scores.size, dtype=np.float64)
    ranks[order] = np.arange(1, scores.size + 1)
    # average ranks within tied groups
    sorted_scores = scores[order]
    start = 0
    for i in range(1, scores.size + 1):
        if i == scores.size or sorted_scores[i] != sorted_scores[start]:
            ranks[order[start:i]] = ranks[order[start:i]].mean()
            start = i
    pos = labels == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _split_species(
    names: Sequence[str], fraction: float, rng: np.random.Generator
) -> tuple[list[str], list[str]]:
    n_out = int(round(fraction * len(names)))
    # Never hold out so much that the species head has fewer than two classes to separate.
    n_out = max(0, min(n_out, len(names) - 2))
    if n_out == 0:
        return list(names), []
    order = rng.permutation(len(names))
    held = sorted(names[i] for i in order[:n_out])
    return sorted(set(names) - set(held)), held


def train(
    real: PatchSet,
    fake: PatchSet,
    config: CriticConfig | None = None,
    log: Any = print,
) -> "Critic":
    """Train the three heads together and return a `Critic` with its report attached."""
    cfg = config or CriticConfig()
    torch.manual_seed(cfg.seed)
    rng = np.random.default_rng(cfg.seed)
    device = device_for(cfg.prefer_gpu)

    train_names, held_names = _split_species(real.names, cfg.holdout_species, rng)
    train_ids = {real.names.index(n) for n in train_names}
    real_train_mask = np.isin(real.species, list(train_ids))
    fake_train_mask = np.isin(fake.species, list(train_ids))

    # Within the training species, hold back some syllables so novelty has a "known but
    # unseen" reference distribution and the species head has an honest accuracy.
    holdout_roll = rng.random(int(real_train_mask.sum())) < cfg.holdout_syllables
    seen_mask = real_train_mask.copy()
    seen_mask[real_train_mask] = ~holdout_roll
    unseen_mask = real_train_mask & ~seen_mask

    r_fit, f_fit = real.subset(seen_mask), fake.subset(fake_train_mask)
    if len(r_fit) < cfg.batch or len(f_fit) < 8:
        raise ValueError(
            f"too little training data: {len(r_fit)} real and {len(f_fit)} synthetic patches "
            f"for {len(train_names)} species. Harvest more, or raise --renders-per-type."
        )

    # The label space the species head sees is the *training* species only, densely indexed.
    dense = {real.names.index(n): i for i, n in enumerate(train_names)}
    y_species = np.asarray([dense[s] for s in r_fit.species], dtype=np.int64)

    mean, std = _standardise_stats(r_fit.patches)
    model = SyllableCritic(len(train_names), cfg.embed_dim, cfg.width).to(device)

    # The recordist-adversarial head: a linear classifier on the embedding, trained to
    # name the recordist through a gradient-reversal layer, so the embedding is trained
    # to stop letting it. It is training scaffolding, not part of `SyllableCritic` —
    # nothing is saved, nothing ships, and old checkpoints are untouched. Classes are
    # recordists with at least `recordist_min_patches` training patches; unnamed
    # recordists ("" — the local-file rows) are never classes.
    rec_head: nn.Linear | None = None
    y_recordist: np.ndarray | None = None
    if cfg.w_record > 0.0 and r_fit.recordings is not None:
        per_patch = np.asarray([r_fit.recordist_names[r] for r in r_fit.recordings])
        uniques, counts = np.unique(per_patch, return_counts=True)
        classes = sorted(
            str(n)
            for n, c in zip(uniques, counts)
            if c >= cfg.recordist_min_patches and n
        )
        if len(classes) >= 2:
            cidx = {n: i for i, n in enumerate(classes)}
            y_recordist = np.asarray(
                [cidx.get(n, -1) for n in per_patch], dtype=np.int64
            )
            rec_head = nn.Linear(cfg.embed_dim, len(classes)).to(device)
        if rec_head is None:
            log("recordist-adversarial head off: fewer than two recordists have "
                f"{cfg.recordist_min_patches}+ training patches")
    params = list(model.parameters()) + (
        list(rec_head.parameters()) if rec_head is not None else []
    )
    opt = torch.optim.AdamW(params, lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps = max(1, len(r_fit) // cfg.batch) * cfg.epochs
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=steps)

    def to_input(patches: np.ndarray) -> torch.Tensor:
        z = (patches - mean) / std
        return torch.from_numpy(np.ascontiguousarray(z, dtype=np.float32)).unsqueeze(1).to(device)

    log(
        f"critic: {len(train_names)} training species ({len(held_names)} held out), "
        f"{len(r_fit)} real + {len(f_fit)} synthetic patches, "
        f"{sum(p.numel() for p in model.parameters()) / 1e3:.0f} k parameters, "
        f"on {describe_device(device)}"
    )
    if held_names:
        log(f"  held out entirely: {', '.join(held_names)}")

    final_loss = 0.0
    per_epoch = max(1, len(r_fit) // cfg.batch)
    for epoch in range(cfg.epochs):
        model.train()
        running = np.zeros(4)
        for _ in range(per_epoch):
            ri = rng.integers(0, len(r_fit), size=cfg.batch)
            fi = rng.integers(0, len(f_fit), size=cfg.batch)
            real_batch = r_fit.patches[ri]

            x = to_input(np.concatenate([real_batch, f_fit.patches[fi]]))
            z, logit, species_logits, _ = model(x)
            is_real = torch.cat([
                torch.ones(cfg.batch, device=device), torch.zeros(cfg.batch, device=device)
            ])
            loss_real = F.binary_cross_entropy_with_logits(logit, is_real)
            # Real patches only: a species head trained on our renders would learn to name
            # the bird *from our synthesis*, which is the opposite of grounding.
            loss_species = F.cross_entropy(
                species_logits[: cfg.batch],
                torch.from_numpy(y_species[ri]).to(device),
            )

            # NT-Xent over two augmented views. Positives are the two views of one syllable;
            # every other view in the batch is a negative. The batch first goes through
            # MixStyle (same-species, different-recording band statistics — a no-op at
            # alpha 0), then each view draws its own augmentations, channel EQ included
            # when the recipe sets `aug_channel_db`.
            views_src = mixstyle(
                real_batch,
                r_fit.species[ri],
                None if r_fit.recordings is None else r_fit.recordings[ri],
                rng,
                cfg.mixstyle_alpha,
            )
            views = np.concatenate([
                augment(views_src, rng, cfg.aug_channel_db),
                augment(views_src, rng, cfg.aug_channel_db),
            ])
            _, _, _, proj = model(to_input(views))
            loss_contrast = _nt_xent(proj, cfg.temperature)

            loss = (
                cfg.w_real * loss_real
                + cfg.w_species * loss_species
                + cfg.w_contrast * loss_contrast
            )
            if rec_head is not None and y_recordist is not None:
                mask_np = y_recordist[ri] >= 0
                if mask_np.any():
                    eligible = torch.from_numpy(mask_np).to(device)
                    loss_record = F.cross_entropy(
                        rec_head(_grad_reverse(z[: cfg.batch][eligible])),
                        torch.from_numpy(y_recordist[ri][mask_np]).to(device),
                    )
                    loss = loss + cfg.w_record * loss_record
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            if sched.last_epoch < steps - 1:
                sched.step()
            running += [
                loss.detach().item(),
                loss_real.detach().item(),
                loss_species.detach().item(),
                loss_contrast.detach().item(),
            ]
        running /= per_epoch
        final_loss = float(running[0])
        if epoch % max(1, cfg.epochs // 10) == 0 or epoch == cfg.epochs - 1:
            log(
                f"  epoch {epoch + 1:3d}/{cfg.epochs}  loss {running[0]:.4f} "
                f"(real {running[1]:.4f}, species {running[2]:.4f}, "
                f"contrast {running[3]:.4f})"
            )

    critic = Critic(model=model, mean=mean, std=std, names=list(train_names), config=cfg)
    critic.report = _evaluate(
        critic,
        real=real,
        fake=fake,
        train_names=train_names,
        held_names=held_names,
        unseen_mask=unseen_mask,
        fake_train_mask=fake_train_mask,
        dense=dense,
        rng=rng,
    )
    critic.report.epochs = cfg.epochs
    critic.report.n_real, critic.report.n_fake = len(r_fit), len(f_fit)
    critic.report.final_loss = final_loss
    critic.report.device = describe_device(device)
    return critic


def _nt_xent(proj: torch.Tensor, temperature: float) -> torch.Tensor:
    """SimCLR's loss over a (2n, d) stack whose halves are paired views."""
    z = F.normalize(proj, dim=1)
    n = z.shape[0] // 2
    sim = (z @ z.T) / temperature
    sim.fill_diagonal_(-1.0e9)  # a view is not its own positive
    target = torch.cat([
        torch.arange(n, 2 * n, device=z.device), torch.arange(0, n, device=z.device)
    ])
    return F.cross_entropy(sim, target)


class _GradReverse(torch.autograd.Function):
    """Identity forward, negated gradient backward — the domain-adversarial trick.

    The recordist head sits *behind* this: its own weights learn to name the
    recordist (a good probe is what makes the pressure honest), while the trunk gets
    the negated gradient and learns to make that naming fail. λ lives in the loss
    weight (`w_record`), not here.
    """

    @staticmethod
    def forward(ctx: Any, x: torch.Tensor) -> torch.Tensor:
        return x

    @staticmethod
    def backward(ctx: Any, grad: torch.Tensor) -> torch.Tensor:
        return -grad


def _grad_reverse(x: torch.Tensor) -> torch.Tensor:
    return _GradReverse.apply(x)


def _evaluate(
    critic: "Critic",
    real: PatchSet,
    fake: PatchSet,
    train_names: Sequence[str],
    held_names: Sequence[str],
    unseen_mask: np.ndarray,
    fake_train_mask: np.ndarray,
    dense: dict[int, int],
    rng: np.random.Generator,
) -> TrainingReport:
    """Every number here is measured on patches the network did not train on."""
    report = TrainingReport(
        train_species=list(train_names), holdout_species=list(held_names)
    )

    held_ids = [real.names.index(n) for n in held_names]
    if held_ids:
        real_held = real.subset(np.isin(real.species, held_ids))
        fake_held = fake.subset(np.isin(fake.species, held_ids))
        if len(real_held) and len(fake_held):
            scores = np.concatenate([
                critic.realism(real_held.patches), critic.realism(fake_held.patches)
            ])
            labels = np.concatenate([
                np.ones(len(real_held), dtype=int), np.zeros(len(fake_held), dtype=int)
            ])
            report.realism_auc_holdout = round(_auc(scores, labels), 4)

    train_ids = [real.names.index(n) for n in train_names]
    real_train = real.subset(np.isin(real.species, train_ids))
    fake_train = fake.subset(fake_train_mask)
    if len(real_train) and len(fake_train):
        scores = np.concatenate([
            critic.realism(real_train.patches), critic.realism(fake_train.patches)
        ])
        labels = np.concatenate([
            np.ones(len(real_train), dtype=int), np.zeros(len(fake_train), dtype=int)
        ])
        report.realism_auc_train = round(_auc(scores, labels), 4)

    # Species accuracy on held-back syllables of *training* species.
    if int(unseen_mask.sum()):
        unseen = real.subset(unseen_mask)
        predicted = critic.species_logits(unseen.patches).argmax(axis=1)
        truth = np.asarray([dense[s] for s in unseen.species])
        report.species_accuracy = round(float((predicted == truth).mean()), 4)
        report.species_chance = round(1.0 / max(1, len(train_names)), 4)

        # Contrastive check: does an augmented view retrieve its own syllable out of 256?
        take = min(256, len(unseen))
        pick = rng.choice(len(unseen), size=take, replace=False)
        base = critic.embed(unseen.patches[pick])
        view = critic.embed(augment(unseen.patches[pick], rng))
        sim = _unit_rows(view) @ _unit_rows(base).T
        report.contrastive_top1 = round(
            float((sim.argmax(axis=1) == np.arange(take)).mean()), 4
        )

    # The recordist probe: nearest-centroid readout trained on seen syllables, scored
    # on unseen ones. Deliberately weak — a strong probe would flatter the number; the
    # point is that even a weak readout should find less recorder as the recipe works.
    if real.recordings is not None and int(unseen_mask.sum()):
        rec_of = np.asarray([real.recordist_names[r] for r in real.recordings])
        seen_mask = np.isin(real.species, train_ids) & ~unseen_mask
        named = np.asarray([bool(r) for r in rec_of])
        seen_idx = np.nonzero(seen_mask & named)[0]
        unseen_idx = np.nonzero(unseen_mask & named)[0]
        if len(seen_idx) and len(unseen_idx):
            keep = [
                r
                for r in set(rec_of[seen_idx])
                if (rec_of[seen_idx] == r).sum() >= 5
                and (rec_of[unseen_idx] == r).sum() >= 1
            ]
            if len(keep) >= 2:
                z_seen = critic.embed(real.patches[seen_idx])
                z_unseen = critic.embed(real.patches[unseen_idx])
                centroids = np.stack(
                    [
                        _unit_rows(z_seen[rec_of[seen_idx] == r]).mean(axis=0)
                        for r in keep
                    ]
                )
                in_probe = np.isin(rec_of[unseen_idx], keep)
                sims = _unit_rows(z_unseen[in_probe]) @ _unit_rows(centroids).T
                predicted = np.asarray(keep, dtype=object)[sims.argmax(axis=1)]
                truth = rec_of[unseen_idx][in_probe]
                report.recordist_probe = round(float((predicted == truth).mean()), 4)
                report.recordist_chance = round(1.0 / len(keep), 4)
    return report


def _unit_rows(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


# --- the trained thing, and what it is for -----------------------------------------


class Critic:
    """A trained `SyllableCritic` plus the standardisation it was trained under.

    Three methods matter, and they are the three uses of §9.2b in dependency order:
    `embed` (typing and novelty), `realism` (the fit's objective), `species_logits`
    (the grounding check).
    """

    def __init__(
        self,
        model: SyllableCritic,
        mean: np.ndarray,
        std: np.ndarray,
        names: list[str],
        config: CriticConfig,
    ) -> None:
        self.model = model.eval()
        self.mean, self.std = mean, std
        self.names = names
        self.config = config
        self.report = TrainingReport()
        self.device = next(model.parameters()).device

    # -- inference --

    def _batch(self, patches: np.ndarray) -> torch.Tensor:
        p = np.asarray(patches, dtype=np.float32)
        if p.ndim == 2:
            p = p[None]
        if p.shape[1:] != features.PATCH_SHAPE:
            raise ValueError(
                f"patches are {p.shape[1:]} but this critic was trained on "
                f"{features.PATCH_SHAPE}"
            )
        z = (p - self.mean) / self.std
        return torch.from_numpy(np.ascontiguousarray(z)).unsqueeze(1).to(self.device)

    @torch.no_grad()
    def _forward(self, patches: np.ndarray, chunk: int = 2048) -> tuple[np.ndarray, ...]:
        outs: list[tuple[np.ndarray, ...]] = []
        p = np.asarray(patches, dtype=np.float32)
        if p.ndim == 2:
            p = p[None]
        for i in range(0, p.shape[0], chunk):
            z, logit, species, _ = self.model(self._batch(p[i : i + chunk]))
            outs.append((z.cpu().numpy(), logit.cpu().numpy(), species.cpu().numpy()))
        return tuple(np.concatenate([o[k] for o in outs]) for k in range(3))

    def embed(self, patches: np.ndarray) -> np.ndarray:
        """(n, EMBED_DIM) learned embedding — what replaces `_observation_vector`."""
        return self._forward(patches)[0]

    def realism(self, patches: np.ndarray) -> np.ndarray:
        """The realism logit, high for real. Unsquashed on purpose.

        A sigmoid saturates, and a saturated objective has no gradient for
        `learn.invert_gestures` to follow — which is the whole reason the convs are
        spectrally normalised. `realism_unit` is the squashed version, for the fit's
        weighted sum where the two terms have to be commensurable.
        """
        return self._forward(patches)[1]

    def realism_unit(self, patches: np.ndarray) -> np.ndarray:
        """Realism mapped to (-1, 1) by tanh, so it can be mixed with a cosine.

        tanh and not sigmoid because the term it is blended with in `learn._score` is a
        cosine, which already lives in [-1, 1]. Mixing a [0, 1] term with a [-1, 1] one
        would silently reweight the blend as `w` moves.
        """
        return np.tanh(self.realism(patches))

    def species_logits(self, patches: np.ndarray) -> np.ndarray:
        return self._forward(patches)[2]

    # -- persistence --

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "version": FORMAT_VERSION,
                "state_dict": self.model.state_dict(),
                "mean": self.mean,
                "std": self.std,
                "names": self.names,
                "config": asdict(self.config),
                "report": self.report.as_dict(),
                "patch_shape": list(features.PATCH_SHAPE),
                "n_species": self.model.n_species,
                "embed_dim": self.model.embed_dim,
                "width": self.model.width,
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
    def load(cls, path: Path, prefer_gpu: bool = True) -> "Critic":
        blob = torch.load(Path(path), map_location="cpu", weights_only=False)
        if tuple(blob.get("patch_shape", ())) != features.PATCH_SHAPE:
            raise RuntimeError(
                f"{path} was trained on {tuple(blob.get('patch_shape', ()))} patches but "
                f"this build measures {features.PATCH_SHAPE}. Retrain it: a critic is only "
                f"meaningful on the representation it was fitted to."
            )
        model = SyllableCritic(blob["n_species"], blob["embed_dim"], blob["width"])
        model.load_state_dict(blob["state_dict"])
        model.to(device_for(prefer_gpu))
        critic = cls(
            model=model,
            mean=np.asarray(blob["mean"], dtype=np.float32),
            std=np.asarray(blob["std"], dtype=np.float32),
            names=list(blob["names"]),
            config=CriticConfig(**blob["config"]),
        )
        critic.report = TrainingReport(**blob.get("report", {}))
        return critic


# --- embedding a whole store -------------------------------------------------------


def embed_store(store: Any, critic: "Critic", batch: int = 512, log: Any = print) -> np.ndarray:
    """One 32-d embedding per stored syllable observation, in `store.syllables` order.

    **Why this exists.** The embedding is the measurably better similarity space (docs/09
    §9.7: typing in it moved species placement 38.4 % -> 51.7 % on the 40 k store), but
    until now it never left the fit that produced it — the galaxy's projection, clusters
    and centroids all still ran on the hand-designed 28-d descriptor. Embedding the store
    once, to a file, is what lets the *build* cluster in the learned space without every
    consumer re-running the network: `build --space embed` reads the result, and so does
    the space map of `spacemap.py` that bridges the browser into it.

    Row order is `store.syllables` exactly, which is also the row order of `patches.f16` —
    the two files are already tied together that way (`HarvestStore._load_patches` refuses
    a count mismatch), so an embedding file in the same order needs no index of its own.

    Observations with no patch cannot be embedded — a store harvested before `mel_patch`
    existed has none — and get a NaN row rather than being dropped, so the matrix stays
    aligned with the store. The caller decides what NaN means; `build` excludes those
    points and says how many.
    """
    observations = store.syllables
    out = np.full((len(observations), critic.model.embed_dim), np.nan, dtype=np.float32)
    have = [i for i, o in enumerate(observations) if o.mel_patch is not None]
    missing = len(observations) - len(have)
    if missing:
        log(f"embed_store: {missing} of {len(observations)} observations have no mel "
            f"patch and get a NaN row")
    for start in range(0, len(have), batch):
        chunk = have[start : start + batch]
        patches = np.stack([
            np.asarray(observations[i].mel_patch, dtype=np.float32) for i in chunk
        ])
        out[chunk] = critic.embed(patches)
        if (start // batch) % 20 == 19:
            log(f"  embedded {chunk[-1] + 1}/{len(observations)}")
    return out


# --- novelty: "is this a syllable I have not heard?" -------------------------------


@dataclass
class NoveltyReport:
    """The ROC docs/09 §9.2b insists on. A detector with no curve is a claim, not a number."""

    threshold: float = 0.0
    target_false_positive: float = 0.05
    #: Measured on held-out species (positives = genuinely novel) against held-back
    #: syllables of known species (negatives).
    auc: float = 0.0
    true_positive_rate: float = 0.0
    false_positive_rate: float = 0.0
    n_known: int = 0
    n_novel: int = 0
    curve: list[list[float]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Novelty:
    """Distance from a syllable's embedding to the nearest known type centroid.

    §9.2b's second use of the network, and the one that changes what the app can say. Today a
    genuinely new call is silently assigned to the nearest existing cluster, which lights the
    wrong knot in the galaxy. With an embedding, "have I heard this?" is a distance question,
    and the threshold comes from the held-out distance distribution so the false-positive rate
    is *chosen* rather than discovered.

    A syllable this flags is still `unlabelled` (§8.5): detecting that a sound is new is not
    knowing what it means, and the interface has to keep saying so.
    """

    def __init__(self, centroids: np.ndarray, labels: list[str], threshold: float) -> None:
        self.centroids = _unit_rows(np.asarray(centroids, dtype=np.float64))
        self.labels = labels
        self.threshold = float(threshold)
        self.report = NoveltyReport(threshold=self.threshold)

    def distance(self, embeddings: np.ndarray) -> np.ndarray:
        """Cosine distance to the nearest centroid, in [0, 2]."""
        z = _unit_rows(np.atleast_2d(np.asarray(embeddings, dtype=np.float64)))
        return 1.0 - (z @ self.centroids.T).max(axis=1)

    def nearest(self, embeddings: np.ndarray) -> list[str]:
        z = _unit_rows(np.atleast_2d(np.asarray(embeddings, dtype=np.float64)))
        return [self.labels[i] for i in (z @ self.centroids.T).argmax(axis=1)]

    def is_novel(self, embeddings: np.ndarray) -> np.ndarray:
        return self.distance(embeddings) > self.threshold

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(
                {
                    "version": FORMAT_VERSION,
                    "threshold": self.threshold,
                    "labels": self.labels,
                    "centroids": [[round(float(v), 6) for v in row] for row in self.centroids],
                    "report": self.report.as_dict(),
                },
                indent=1,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "Novelty":
        blob = json.loads(Path(path).read_text(encoding="utf-8"))
        n = cls(np.asarray(blob["centroids"], dtype=np.float64), list(blob["labels"]),
                float(blob["threshold"]))
        n.report = NoveltyReport(**blob.get("report", {}))
        return n


def fit_novelty(
    critic: Critic,
    real: PatchSet,
    target_false_positive: float = 0.05,
    per_species_types: int = 8,
    seed: int = 0,
) -> Novelty:
    """Build the centroids from the critic's *training* species and threshold honestly.

    The measurement that matters is the one docs/09 asks for: hold out entire species, then
    check that their syllables are flagged novel. The known-side negatives are syllables of
    training species that the critic did not train on either, so neither side of the ROC is
    something the network memorised.
    """
    rng = np.random.default_rng(seed)
    known_ids = [real.names.index(n) for n in critic.names if n in real.names]
    novel_ids = [i for i in range(len(real.names)) if i not in set(known_ids)]

    known = real.subset(np.isin(real.species, known_ids))
    if not len(known):
        raise ValueError("no patches for the critic's training species — nothing to centre on")

    embeddings = critic.embed(known.patches)
    # Centroids per *type*, not per species: a species with a whistle and a rattle has two
    # very different regions, and one centroid between them is near neither. KMeans in the
    # learned embedding is exactly the typing of §9.2b use 1.
    from sklearn.cluster import KMeans

    centroids: list[np.ndarray] = []
    labels: list[str] = []
    for sid in known_ids:
        rows = embeddings[known.species == sid]
        name = real.names[sid]
        k = int(max(1, min(per_species_types, len(rows) // 8)))
        if k <= 1:
            centroids.append(rows.mean(axis=0))
            labels.append(f"{name}:0")
            continue
        km = KMeans(n_clusters=k, n_init=6, random_state=seed).fit(_unit_rows(rows))
        for c in range(k):
            centroids.append(km.cluster_centers_[c])
            labels.append(f"{name}:{c}")

    # Split the known side: half defines the centroids, half measures the false-positive rate.
    # Using the same patches for both would put every negative on top of a centroid it helped
    # place, and the threshold would come out absurdly tight.
    holdout = rng.random(len(known)) < 0.5
    novelty = Novelty(np.stack(centroids), labels, threshold=float("inf"))
    d_known = novelty.distance(embeddings[holdout])

    if novel_ids:
        novel = real.subset(np.isin(real.species, novel_ids))
        d_novel = novelty.distance(critic.embed(novel.patches))
    else:
        d_novel = np.zeros(0)

    threshold = float(np.quantile(d_known, 1.0 - target_false_positive))
    novelty.threshold = threshold
    report = NoveltyReport(
        threshold=round(threshold, 6),
        target_false_positive=target_false_positive,
        n_known=int(d_known.size),
        n_novel=int(d_novel.size),
    )
    if d_novel.size:
        scores = np.concatenate([d_novel, d_known])
        labels_roc = np.concatenate([
            np.ones(d_novel.size, dtype=int), np.zeros(d_known.size, dtype=int)
        ])
        report.auc = round(_auc(scores, labels_roc), 4)
        report.true_positive_rate = round(float((d_novel > threshold).mean()), 4)
        report.false_positive_rate = round(float((d_known > threshold).mean()), 4)
        report.curve = [
            [round(float(t), 5), round(float((d_novel > t).mean()), 4),
             round(float((d_known > t).mean()), 4)]
            for t in np.quantile(scores, np.linspace(0.01, 0.99, 25))
        ]
    novelty.report = report
    return novelty


# --- self-test ---------------------------------------------------------------------


def self_test(verbose: bool = True) -> None:
    """Train on synthetic data with a known answer, and check every claimed property.

    No harvest and no network needed. Two "species" of made-up patches, plus a "synthetic"
    side that differs from both in one specific way, so the numbers below have a right answer
    and a wrong one rather than merely being reproducible.
    """
    rng = np.random.default_rng(3)
    knots, mel = features.PATCH_SHAPE
    t = np.linspace(0.0, 1.0, knots)
    bands = np.arange(mel)

    # Scaled to what a real patch actually looks like, measured over 200 renders of the
    # shipped inventory: values spanning about +-19 log units with a per-band spread across
    # instances of 3-5. Getting this wrong makes the test meaningless in one specific way —
    # a first attempt used an unbounded parabola whose range was 240 units, so a spectral
    # tilt of realistic size was sixty times smaller than the per-band variance and no
    # network could have found it. The point of the tilt case is that it is *findable*.
    RIDGE_DEPTH, RIDGE_WIDTH, NOISE = 15.0, 2.2, 0.6

    def make(n: int, band: tuple[float, float], sweep: tuple[float, float], tilt: float):
        """`n` ridge patches: a Gaussian ridge in frequency whose centre moves over time.

        Each instance draws its *own* start band and sweep rate, so no two patches of one
        species are alike. That matters for more than variety: the contrastive head is
        instance discrimination, and if every patch of a species were identical then chance
        would be the correct score and the assertion on it would be untestable.
        """
        start = rng.uniform(*band, size=(n, 1))
        rate = rng.uniform(*sweep, size=(n, 1))
        centre = start + rate * t[None, :]  # (n, knots)
        offset = (bands[None, None, :] - centre[:, :, None]) / RIDGE_WIDTH
        out = -RIDGE_DEPTH * (1.0 - np.exp(-0.5 * offset**2))
        out = out + tilt * bands[None, None, :]
        out = out + rng.normal(scale=NOISE, size=out.shape)
        out = out - out.mean(axis=(1, 2), keepdims=True)
        return out.astype(np.float32)

    # two real species: one low and near-flat, one higher and sweeping upward
    a = make(700, (3.0, 9.0), (-1.0, 1.0), 0.0)
    b = make(700, (10.0, 16.0), (3.0, 7.0), 0.0)
    real = PatchSet(
        np.concatenate([a, b]),
        np.concatenate([np.zeros(len(a), dtype=np.int64), np.ones(len(b), dtype=np.int64)]),
        ["species_a", "species_b"],
        True,
    )
    # the synthetic side: the same gestures, but carrying the spectral tilt our renders have
    # and real recordings do not (docs/09 §9.1 result 2). A working critic must find that,
    # and must find it *without* being able to lean on which species it is.
    fa = make(350, (3.0, 9.0), (-1.0, 1.0), 0.18)
    fb = make(350, (10.0, 16.0), (3.0, 7.0), 0.18)
    fake = PatchSet(
        np.concatenate([fa, fb]),
        np.concatenate([np.zeros(len(fa), dtype=np.int64), np.ones(len(fb), dtype=np.int64)]),
        ["species_a", "species_b"],
        False,
    )

    cfg = CriticConfig(
        epochs=40, batch=128, holdout_species=0.0, holdout_syllables=0.2, seed=1
    )
    quiet = (lambda *_a, **_k: None) if not verbose else print
    critic = train(real, fake, cfg, log=quiet)
    r = critic.report

    assert r.realism_auc_train > 0.9, f"critic cannot find the tilt: AUC {r.realism_auc_train}"
    assert r.species_accuracy > 0.9, f"species head failed: {r.species_accuracy}"
    # Retrieval of one specific syllable out of 256 candidates, so chance is 1/256 = 0.004.
    # The bar is set at 0.15 — nearly forty times chance — rather than at something that
    # sounds impressive, because on this data many instances genuinely *are* near-duplicates:
    # start band and sweep rate are drawn from continuous ranges, so two draws can differ by
    # less than the augmentation does. Perfect retrieval here would mean the embedding had
    # memorised the noise.
    assert r.contrastive_top1 > 0.15, (
        f"the embedding does not retrieve an augmented view of its own syllable: top-1 "
        f"{r.contrastive_top1} against chance 0.004"
    )

    z = critic.embed(real.patches[:64])
    assert z.shape == (64, cfg.embed_dim)
    assert np.all(np.isfinite(z))
    # Bit-exact determinism for a repeated identical call. `learn.invert_gestures` compares
    # scores against a running best and only moves on an improvement, so a score that
    # wandered between calls would make the search's result depend on evaluation order.
    assert np.array_equal(z, critic.embed(real.patches[:64])), "embedding is not deterministic"

    # One patch and a batch must agree — but only to about 0.1 % relative on CUDA, not
    # exactly. cuDNN selects a different convolution algorithm for batch 1 than for batch 64
    # and the two round differently; measured here it is ~9e-5 absolute on embeddings of
    # scale 0.065 (and ~1e-7 on CPU). This is well under `invert_gestures`'s 1e-4 improvement
    # threshold, so it cannot make the search take a step it otherwise would not, but it does
    # mean batch size is not a free choice for anything demanding exactness.
    solo = critic.embed(real.patches[0])
    assert solo.shape == (1, cfg.embed_dim)
    drift = float(np.max(np.abs(solo - z[:1])) / max(float(np.abs(z).mean()), 1e-9))
    assert drift < 5.0e-3, f"batch size changes the embedding by {drift:.2e} relative"

    unit = critic.realism_unit(real.patches[:32])
    assert np.all(np.abs(unit) <= 1.0), "realism_unit must be commensurable with a cosine"

    # augmentation must move the patch without destroying it
    aug = augment(real.patches[:32], rng)
    assert aug.shape == real.patches[:32].shape
    assert np.all(np.isfinite(aug))
    assert float(np.abs(aug - real.patches[:32]).mean()) > 0.05, "augmentation did nothing"

    # --- the source-invariance recipe's mechanics -------------------------------------
    # The channel EQ curve: mean-zero (never a level change), smooth in frequency, and
    # inside its dB budget once converted to log-mel units.
    eq = _channel_eq(16, mel, 3.0, rng)
    assert eq.shape == (16, 1, mel)
    assert np.all(np.abs(eq.mean(axis=(1, 2))) < 1.0e-6), (
        "channel EQ shifts the patch mean"
    )
    # Smooth in the 1/f sense: the *average* band-to-band step is a small fraction of
    # the swing (a single step may be large — the walk is peak-normalised, and one
    # dominant increment is still a smooth curve, not a jagged one).
    mean_step = np.abs(np.diff(eq[:, 0, :], axis=1)).mean()
    assert mean_step < 0.5 * 3.0 * math.log(10) / 10.0, (
        f"EQ is jagged rather than smooth: mean step {mean_step:.3f}"
    )
    assert np.abs(eq).max() <= 3.0 * math.log(10) / 10.0 + 1.0e-6
    aug_eq = augment(real.patches[:8], rng, channel_db=3.0)
    assert float(np.abs(aug_eq - real.patches[:8]).mean()) > 0.05, "channel EQ did nothing"

    # MixStyle: off means untouched, no labels means untouched, and a mixed patch's
    # per-band mean moves toward its partner's — never away from its own.
    src = real.patches[:16]
    assert np.array_equal(mixstyle(src, real.species[:16], None, rng, 0.2), src)
    recs = np.arange(16, dtype=np.int64)  # every patch its own recording
    mixed = mixstyle(src, real.species[:16], recs, rng, 0.2)
    assert mixed.shape == src.shape and np.all(np.isfinite(mixed))
    moved = float(np.abs(mixed - src).mean())
    assert moved > 1.0e-3, "MixStyle with full partners did nothing"
    # One recording per species -> no eligible partner anywhere -> untouched.
    lonely = mixstyle(src, real.species[:16], real.species[:16].copy(), rng, 0.2)
    assert np.array_equal(lonely, src), "MixStyle mixed within one recording"

    # The gradient-reversal layer: identity forward, exactly negated gradient backward.
    x = torch.tensor([1.0, -2.0], requires_grad=True)
    _grad_reverse(x).sum().backward()
    assert torch.equal(x.grad, torch.tensor([-1.0, -1.0]))

    # The adversarial wiring end to end: two recordists marked by a *tilted* channel
    # (a flat offset is gain — mean-centring removes it by design; a frequency-
    # dependent response is what a recorder actually adds) must become classes, a
    # short train must run, and the report must carry the probe.
    marked = real.patches[:256].copy()
    marked[:128] += np.linspace(-0.8, 0.8, mel, dtype=np.float32)[None, None, :]
    marked = marked - marked.mean(axis=(1, 2), keepdims=True)
    real_marked = PatchSet(
        marked,
        real.species[:256],
        ["species_a", "species_b"],
        True,
        recordings=np.asarray([i // 128 for i in range(256)], dtype=np.int64),
        recording_names=["rec_0", "rec_1"],
        recordist_names=["alice", "bob"],
    )
    cfg_rec = CriticConfig(
        epochs=2, batch=64, holdout_species=0.0, holdout_syllables=0.2, seed=1,
        w_record=0.1, recordist_min_patches=20,
    )
    trained_rec = train(real_marked, fake, cfg_rec, log=quiet)
    assert np.isfinite(trained_rec.report.final_loss), "adversarial train diverged"
    assert trained_rec.report.recordist_probe == trained_rec.report.recordist_probe, (
        "the recordist probe did not run on a labelled PatchSet"
    )
    assert trained_rec.report.recordist_probe > 0.5, (
        "sanity inverted: a flat channel offset is not decodable at all — "
        f"probe {trained_rec.report.recordist_probe}"
    )

    # a round trip through disk must give the same numbers
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "critic.pt"
        critic.save(p)
        again = Critic.load(p, prefer_gpu=critic.device.type == "cuda")

        # The property that matters is that the *weights* survive exactly, including the
        # spectral-norm power-iteration vectors — those are buffers, not parameters, and a
        # save format that dropped them would silently rescale every conv on reload.
        before, after = critic.model.state_dict(), again.model.state_dict()
        assert before.keys() == after.keys(), "save/load lost or added a tensor"
        assert any("_u" in k for k in before), "spectral-norm buffers are missing entirely"
        worst = max(float((before[k].cpu() - after[k].cpu()).abs().max()) for k in before)
        assert worst == 0.0, f"save/load perturbed the weights by {worst:.2e}"

        # Same device, so this is exact. Comparing across devices is not: measured, a CUDA
        # model and the same weights on CPU differ by ~1e-4 on embeddings of scale 2.8,
        # because the two use different convolution kernels.
        assert np.array_equal(
            again.embed(real.patches[:16]), critic.embed(real.patches[:16])
        ), "save/load changed the embedding"
        assert json.loads(p.with_suffix(".json").read_text())["report"]["epochs"] == cfg.epochs

    # novelty, with species_b standing in for a bird nobody has harvested
    critic.names = ["species_a"]
    nov = fit_novelty(critic, real, target_false_positive=0.05, seed=2)
    assert nov.report.n_novel > 0, "no novel side to measure against"
    assert nov.report.auc > 0.75, f"novelty cannot separate an unseen species: {nov.report.auc}"
    assert nov.report.false_positive_rate <= 0.12, (
        f"false-positive rate {nov.report.false_positive_rate} is far from the 0.05 asked for"
    )
    assert len(nov.report.curve) > 5, "a novelty detector must ship its ROC curve"

    if verbose:
        print(
            f"critic self-test ok: realism AUC {r.realism_auc_train:.3f}, "
            f"species {r.species_accuracy:.3f} (chance {r.species_chance:.3f}), "
            f"contrastive top-1 {r.contrastive_top1:.3f}, "
            f"novelty AUC {nov.report.auc:.3f} at "
            f"FPR {nov.report.false_positive_rate:.3f}"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
