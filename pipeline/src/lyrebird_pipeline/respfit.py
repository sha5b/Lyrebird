"""The per-species fit for the two synth extensions of docs/15 — respiration (§1) and
two-voice coupling (§5) — with the honest gate.

Both extensions shipped with hand-set defaults and pre-registered bake-offs that said
*no*: the default respiratory set scored a wash (median resynthesis cosine 0.343 ->
0.336 on the five-species store), the default second voice a loss (0.343 -> 0.294), and
both `learn` flags stay off for exactly that reason. But both bake-offs attached one
hand-set parameter set to *every* type of *every* species, and the per-species numbers
showed the signal the medians hid: respiration helped the wren and the great tit and
hurt the short-note species (the shaped attack eats a third of a sub-50 ms note), and
two-voice helped exactly the two species whose single-voice fit was worst (cuckoo
0.153 -> 0.187, tawny owl 0.181 -> 0.189). The fit that was always planned — docs/15
§1 and §5 both end with "how the fit will work (pre-registered, not built)" — is
therefore per-species (respiration) and per-type (two-voice), with a gate that ships a
fitted block only where it individually wins.

**The search (pre-registered before the first run).** Coordinate descent, the same
discipline as `learn.invert_gestures` and for the same reason: the objective surface is
smooth, the seed is a measured default, and a few hundred renders per species find what
a full grid finds at a fraction of the cost. It cannot escape a bad basin and does not
have to — it starts from the default set and only ever moves on an improvement of more
than 1e-4, so the worst case is staying where the default put it. Deterministic by
construction: fixed candidate grids, no RNG anywhere, so a re-run reproduces the fit
bit for bit (up to the process pool's scheduling, which changes nothing each worker
sees).

- *Respiration — one set per species*, as Table S2 fits one set per bird ("a single
  set per bird reproduces the whole syllable-type diversity"). The five parameters are
  searched over five-point geometric grids spanning the Table S2 ranges, seeded from
  `respiration.DEFAULT_PARAMS`, maximising the mean of the types' resynthesis cosines
  — the *same* objective `learn._score` computes, against the *same* per-type
  reference (the standardised mean descriptor of the type's member observations,
  rebuilt from the store's `typing.json`). Nothing about the objective is new; only
  what is being searched is.
- *Two-voice — one block per type*, and only where a screen says a second source could
  help. **The screen**: the type's single-voice cosine is below its species' median —
  the worst half of the repertoire. Chosen over a spectral sideband test because the
  §5 bake-off *measured* this rule: the two species two-voice helped were the two
  worst fitted, and every well-fitted species paid for its phantom fourth. A sideband
  detector would be the finer instrument, but the observations carry no spectra to run
  it on (the 28-d descriptor is a mean over frames; the mel patches are the critic's),
  and the residual screen needs nothing the store does not already have. Searched axes:
  the voice-B pitch ratio (octave down to octave up, seeded at the Fig. 6 ratio), the
  voice-B gamma (half/same/double the contour rule's, inside the syrinx's clamps), and
  the injection strength `betaInj` — capped at 0.20, inside the measured weak-coupling
  regime: at 0.25 the twovoice.py measurements show the fundamental collapsing into
  period doubling, so the search never goes where the dropped implicit terms stop
  being small. Level, trachea and reflection stay at the twovoice defaults — the
  screen already decided the second voice exists, and three axes is the search the
  render budget can honestly run per type.
- *Composition*: respiration first (it is the pressure gesture everything else runs
  on), then two-voice searched against the syllable as it stands after the respiration
  gate — so every shipped configuration is one the objective actually scored, never an
  untested combination of two independent winners.

**The honest gate.** A fitted block ships on a type ONLY if it beats that type's
current cosine by at least `SHIP_MARGIN = 0.02`, measured in the same process, the
same frame, the same render path. The number is a judgment call, registered here
before the first run: the per-type score is deterministic, so there is no sampling
noise to guard against — what the margin guards is shipping a new synth dimension for
a wash. The bake-offs' per-species median moves were 0.007 (respiration, a wash) and
0.05 (two-voice, a loss); 0.02 sits between them, at the scale where an effect stops
being a wash, and two hundred times the 1e-4 search threshold. A type that does not
clear it keeps the default path — no block, bit-identical to what `learn` wrote. There
is no global flip, ever: the output is a per-type decision written into the
inventory's syllable blocks.

**The pre-registered judgment** (fixed store `out/harvest-gan`; iteration on a /tmp
copy of `out/harvest-mp`; reported in docs/15 §1 and §5 after the run):

1. median resynthesis cosine over all scored learned types, before vs after;
2. nearest-own placement over the same types, before vs after;
3. the share of types where the fitted set won the gate (respiration: of all scored
   types; two-voice: of the screened ones).

The mechanism earns its place if (1) rises and (2) does not fall. The `learn
--respiration` / `--two-voice` flags stay off regardless of the outcome — this
per-type decision supersedes the global attach the flags do — and a negative result is
recorded in place, per docs/09 §9.7's pattern.

No torch, no critic, no learned components anywhere in this module: the objective is
the 28-d descriptor cosine in the harvested population's own frame, the number the
critic cannot game.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from . import features, learn, respiration, syrinx, twovoice
from .learn import SyllableObservation
from .syrinx import Calibration, peak_normalise, render_syllable


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- the pre-registered search grids -------------------------------------------------
# Five-point geometric grids spanning the Table S2 ranges (respiration.py's clamps),
# endpoints inclusive. Geometric because every one of these ranges spans a decade or
# more and the dynamics care about ratios, not absolute steps — the same reason the
# paper grid-searched them in log space.
SEARCH_PASSES = 3  # INVERT_PASSES, the same coordinate-descent budget
SEARCH_THRESHOLD = 1.0e-4  # the accept threshold of learn.invert_gestures
TAU_X_GRID = tuple(
    float(v) for v in np.geomspace(respiration.TAU_X_MIN, respiration.TAU_X_MAX, 5)
)
TAU_P_GRID = tuple(
    float(v) for v in np.geomspace(respiration.TAU_P_MIN, respiration.TAU_P_MAX, 5)
)
ALPHA_I_GRID = tuple(
    float(v) for v in np.geomspace(respiration.ALPHA_I_MIN, respiration.ALPHA_I_MAX, 5)
)
ALPHA_REL_GRID = tuple(
    float(v)
    for v in np.geomspace(respiration.ALPHA_REL_MIN, respiration.ALPHA_REL_MAX, 5)
)
FORCING_GRID = tuple(
    float(v) for v in np.geomspace(respiration.FORCING_MIN, respiration.FORCING_MAX, 5)
)

# The two-voice axes. The ratio grid is octave-down to octave-up around the Fig. 6
# seed (twovoice.DEFAULT_RATIO): 0.5 and 1.0 are the subharmonic and locking regimes
# the paper's feedback produces, 0.75/1.5 the consonant fourth/fifth both ways, and
# the seed itself the measured inharmonic case.
RATIO_GRID = (0.5, 0.75, 1.0, twovoice.DEFAULT_RATIO, 1.5, 2.0)
GAMMA_SCALE_GRID = (0.5, 1.0, 2.0)
#: Injection strengths, all inside the measured weak-coupling regime: twovoice.py's
#: sweep shows pi reaching ~4x ps and the fundamental collapsing at 0.25, so the
#: search's ceiling 0.20 stays where the small-coupling approximation the renderer is
#: built on still holds (the parser's 0.5 ceiling is a stability guard, not a fit bound).
BETA_INJ_GRID = (0.02, 0.05, 0.10, 0.20)

#: The honest gate: a fitted block ships on a type only if it beats that type's
#: current cosine by at least this much. Registered before the first run — see the
#: module docstring for the reasoning.
SHIP_MARGIN = 0.02


# --- references: where each type's real audio sits -----------------------------------


def type_members(
    observations: Sequence[SyllableObservation],
    typing: dict[tuple[str, str, int], str],
    recording_descriptors: dict[str, np.ndarray] | None = None,
) -> dict[str, dict[str, list[np.ndarray]]]:
    """Member descriptor rows per species and type id, rebuilt from the store's typing.

    The fit does not re-cluster: membership is exactly what the parallel learn wrote
    into `typing.json`, so the type a block is fitted against is the type that ships.
    Rows keyed `(speciesId, recordingId, order)` — the same keying
    `HarvestStore.syllable_point_set` uses. Observations with no per-syllable
    descriptor fall back to their recording's mean descriptor, the same fallback
    `learn_species` uses when the store kept no per-syllable rows.
    """
    by_key = {(o.species_id, o.recording_id, o.order): o for o in observations}
    members: dict[str, dict[str, list[np.ndarray]]] = {}
    for key, type_id in typing.items():
        species_id = key[0]
        if species_id == learn.UNLABELLED_SPECIES or type_id.startswith("U"):
            # The unlabelled pool's candidates are provisional and never inverted
            # (learn.py: no species reference to judge them against) — the same rule
            # keeps them out of this fit.
            continue
        o = by_key.get(key)
        if o is None:
            continue
        row = np.asarray(o.descriptor, dtype=np.float64) if o.descriptor else None
        if row is None and recording_descriptors is not None:
            raw = recording_descriptors.get(o.recording_id)
            row = np.asarray(raw, dtype=np.float64) if raw is not None else None
        if row is None:
            continue
        members.setdefault(species_id, {}).setdefault(type_id, []).append(row)
    return members


def type_reference(
    rows: Sequence[np.ndarray], frame: tuple[np.ndarray, np.ndarray] | None
) -> np.ndarray:
    """The type's reference vector: mean member descriptor, standardised, unit-normed.

    Exactly `learn_species`' `real[i]`, so the cosine this fit maximises is the cosine
    the verification reports.
    """
    mean_row = np.mean(np.stack(rows), axis=0)
    if frame is not None:
        mean_row = features.standardise(mean_row, frame[0], frame[1])
    return learn._unit(mean_row)


def _render_z(
    syllable: dict[str, Any],
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    sample_rate: int,
) -> np.ndarray | None:
    """Where one syllable's resynthesis lands in the harvest's frame (unit-normed).

    `learn._score` computes this and dots it with one reference; the placement
    verdict needs it dotted with *all* of a species' references, so the render happens
    once here instead of once per comparison. Identical arithmetic to `_score` —
    same render, same descriptor, same standardisation.
    """
    audio = peak_normalise(
        render_syllable(syllable, sample_rate=sample_rate, calibration=calibration)
    )
    d = features.descriptor(audio, sample_rate)
    if d is None:
        return None
    if frame is not None:
        d = features.standardise(d, frame[0], frame[1])
    return learn._unit(d)


# --- the searches --------------------------------------------------------------------


def fit_species_respiration(
    syllables: Sequence[dict[str, Any]],
    refs: Sequence[np.ndarray | None],
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    sample_rate: int = features.SAMPLE_RATE,
    passes: int = SEARCH_PASSES,
) -> tuple[respiration.RespirationParams, float, float]:
    """One respiratory set for the whole bird. Returns (params, seed score, best score).

    Coordinate descent over the five Table S2 grids, seeded from the default set,
    objective = mean resynthesis cosine over the types that have a reference —
    per species, because Table S2 fits one set per bird and the pressure gesture is a
    property of that bird's air sacs, not of any one note. Only ever moves on an
    improvement, so the worst case is the seed: the hand-set default whose bake-off is
    already recorded.
    """
    blockless = [{k: v for k, v in s.items() if k != "respiration"} for s in syllables]

    def objective(params: respiration.RespirationParams) -> float:
        block = params.as_dict()
        total, n = 0.0, 0
        for syl, ref in zip(blockless, refs):
            if ref is None:
                continue
            total += learn._score(
                {**syl, "respiration": block}, ref, calibration, frame, sample_rate
            )
            n += 1
        return total / n if n else -1.0

    axes = [
        ("tau_x", TAU_X_GRID),
        ("tau_p", TAU_P_GRID),
        ("alpha_i", ALPHA_I_GRID),
        ("alpha_rel", ALPHA_REL_GRID),
        ("forcing", FORCING_GRID),
    ]
    best_params = respiration.DEFAULT_PARAMS
    seed_score = objective(best_params)
    best = seed_score
    for _ in range(max(1, passes)):
        improved = False
        for name, grid in axes:
            current = getattr(best_params, name)
            for value in grid:
                if abs(value - current) < 1.0e-12:
                    continue
                trial_params = replace(best_params, **{name: value})
                score = objective(trial_params)
                if score > best + SEARCH_THRESHOLD:
                    best, best_params, current = score, trial_params, value
                    improved = True
        if not improved:
            break
    return best_params, seed_score, best


def two_voice_block(
    contour: Sequence[Sequence[float]],
    ratio: float,
    gamma_scale: float,
    beta_inj: float,
) -> dict[str, Any]:
    """One candidate `voices` block: the type's contour at `ratio`, the rest defaults."""
    contour_b = [[float(f), float(hz) * ratio] for f, hz in contour]
    gamma_b = float(
        np.clip(
            syrinx.gamma_for_contour(contour_b) * gamma_scale,
            twovoice.GAMMA_MIN,
            twovoice.GAMMA_MAX,
        )
    )
    return twovoice.TwoVoiceParams(
        contour=tuple((f, hz) for f, hz in contour_b),
        gamma=gamma_b,
        level=twovoice.DEFAULT_LEVEL,
        trachea_cm=twovoice.DEFAULT_TRACHEA_CM,
        refl=twovoice.DEFAULT_REFL,
        beta_inj=beta_inj,
    ).as_dict()


def fit_type_two_voice(
    syllable: dict[str, Any],
    ref: np.ndarray,
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    sample_rate: int = features.SAMPLE_RATE,
    passes: int = SEARCH_PASSES,
) -> tuple[dict[str, Any], float, float]:
    """One second voice for one type. Returns (best block, seed score, best score).

    Per type rather than per species because that is what the §5 bake-off measured: a
    second voice is a property of the *note* (the cuckoo's two tones are not the
    blackbird's one), and the hand-set default failed exactly where it attached a
    phantom voice to a type with one dominant fundamental. Coordinate descent over
    (ratio, gamma scale, betaInj), seeded at the defaults the bake-off ran.
    """
    base = {k: v for k, v in syllable.items() if k != "voices"}

    def objective(ratio: float, gamma_scale: float, beta_inj: float) -> float:
        trial = dict(base)
        trial["voices"] = two_voice_block(base["contour"], ratio, gamma_scale, beta_inj)
        return learn._score(trial, ref, calibration, frame, sample_rate)

    ratio, gamma_scale, beta_inj = (
        twovoice.DEFAULT_RATIO,
        1.0,
        twovoice.DEFAULT_BETA_INJ,
    )
    seed_score = objective(ratio, gamma_scale, beta_inj)
    best = seed_score
    for _ in range(max(1, passes)):
        improved = False
        for value in RATIO_GRID:
            if abs(value - ratio) < 1.0e-12:
                continue
            score = objective(value, gamma_scale, beta_inj)
            if score > best + SEARCH_THRESHOLD:
                best, ratio, improved = score, value, True
        for value in GAMMA_SCALE_GRID:
            if abs(value - gamma_scale) < 1.0e-12:
                continue
            score = objective(ratio, value, beta_inj)
            if score > best + SEARCH_THRESHOLD:
                best, gamma_scale, improved = score, value, True
        for value in BETA_INJ_GRID:
            if abs(value - beta_inj) < 1.0e-12:
                continue
            score = objective(ratio, gamma_scale, value)
            if score > best + SEARCH_THRESHOLD:
                best, beta_inj, improved = score, value, True
        if not improved:
            break
    return (
        two_voice_block(base["contour"], ratio, gamma_scale, beta_inj),
        seed_score,
        best,
    )


def two_voice_screen(scores: Sequence[float | None]) -> list[bool]:
    """Which types a second source could help: the worst half of the repertoire.

    Below the species' median single-voice cosine — the rule the §5 bake-off measured
    (it helped the two worst-fitted species and hurt every well-fitted one). A
    one-type species has no "worst half" and screens nothing; an unscored type has no
    residual to judge and screens nothing either.
    """
    scored = [s for s in scores if s is not None]
    if len(scored) < 2:
        return [False for _ in scores]
    median = float(np.median(scored))
    return [s is not None and s < median for s in scores]


# --- one species through the fit and the gate -----------------------------------------


def respfit_species(
    syllables: Sequence[dict[str, Any]],
    refs: Sequence[np.ndarray | None],
    calibration: Calibration | None,
    frame: tuple[np.ndarray, np.ndarray] | None,
    sample_rate: int = features.SAMPLE_RATE,
    margin: float = SHIP_MARGIN,
    fit_respiration: bool = True,
    fit_two_voice: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Fit and gate one species' learned types. Returns (updated syllables, records, summary).

    `syllables` are the species' learned type dicts as the inventory carries them
    (already gesture-inverted by `learn`); `refs` the matching references (None where
    a type has no measured audio to score against — such a type keeps the default
    path, since a win cannot be demonstrated). Each record is one type's audit trail:
    the before/after cosines, what shipped and what was screened.
    """
    out = [dict(s) for s in syllables]

    # Baseline, rendered once per type: own cosine (and the z for the nearest-own
    # verdict in step 3) against the same references the after-pass uses, so
    # before/after differ only by the blocks the gate shipped.
    baseline: list[float | None] = []
    z0: list[np.ndarray | None] = []
    for syl in out:
        z0.append(_render_z(syl, calibration, frame, sample_rate))
    for i, ref in enumerate(refs):
        if ref is None or z0[i] is None:
            baseline.append(None)
            continue
        baseline.append(float(z0[i] @ ref))

    records: list[dict[str, Any]] = []
    for i, syl in enumerate(out):
        records.append(
            {
                "typeId": syl.get("id", f"#{i}"),
                "members": syl.get("learned", {}).get("members", 0),
                "before": round(baseline[i], 4) if baseline[i] is not None else None,
                "nearestBefore": None,  # filled below
                "respiration": None,
                "twoVoice": None,
                "screened": False,
            }
        )

    # 1. Respiration: one set for the bird, then the per-type gate decides where it ships.
    if fit_respiration and any(r is not None for r in refs):
        params, seed_score, best_score = fit_species_respiration(
            out, refs, calibration, frame, sample_rate
        )
        block = params.as_dict()
        for i, syl in enumerate(out):
            if baseline[i] is None:
                continue
            trial = {k: v for k, v in syl.items() if k != "respiration"}
            trial["respiration"] = block
            after = learn._score(trial, refs[i], calibration, frame, sample_rate)
            gain = after - float(baseline[i])
            if gain >= margin:
                out[i] = trial
                records[i]["respiration"] = {"gain": round(gain, 4), **block}
            else:
                records[i]["respiration"] = {"gain": round(gain, 4)}
        species_resp = {
            "params": block,
            "seedScore": round(seed_score, 4),
            "bestScore": round(best_score, 4),
        }
    else:
        species_resp = None

    # 2. Two-voice: screened types only, searched against the syllable as it now
    #    stands (respiration block included where it shipped), gated the same way.
    current: list[float | None] = []
    for i, syl in enumerate(out):
        if baseline[i] is None:
            current.append(None)
        elif records[i]["respiration"] and "tauX" in records[i]["respiration"]:
            current.append(float(baseline[i]) + records[i]["respiration"]["gain"])
        else:
            current.append(baseline[i])
    screened = two_voice_screen(baseline)  # the screen reads the single-voice residual
    if fit_two_voice:
        for i, syl in enumerate(out):
            if not screened[i] or refs[i] is None:
                continue
            records[i]["screened"] = True
            block, _, _ = fit_type_two_voice(
                syl, refs[i], calibration, frame, sample_rate
            )
            trial = dict(syl)
            trial["voices"] = block
            after = learn._score(trial, refs[i], calibration, frame, sample_rate)
            gain = after - float(current[i])
            if gain >= margin:
                out[i] = trial
                records[i]["twoVoice"] = {"gain": round(gain, 4), "block": block}
            else:
                records[i]["twoVoice"] = {"gain": round(gain, 4)}

    # 3. Measure what ships: the reported cosine has to describe the syllable that
    #    ships, not the one the fit started from — learn's own rule. nearest-own is
    #    recomputed for every scored type, because a rival's new block moves the
    #    comparison even where this type kept the default path.
    nearest_before = 0
    nearest_after = 0
    z1 = [_render_z(syl, calibration, frame, sample_rate) for syl in out]
    for i, ref in enumerate(refs):
        if ref is None or z1[i] is None:
            continue
        sims = [float(z1[i] @ r) if r is not None else -1.0 for r in refs]
        rivals = [s for j, s in enumerate(sims) if j != i]
        nearest = all(sims[i] >= s for s in rivals)
        nearest_after += 1 if nearest else 0
        sims0 = [float(z0[i] @ r) if r is not None else -1.0 for r in refs]
        rivals0 = [s for j, s in enumerate(sims0) if j != i]
        was_nearest = all(sims0[i] >= s for s in rivals0)
        nearest_before += 1 if was_nearest else 0
        records[i]["nearestBefore"] = was_nearest
        records[i]["nearestAfter"] = nearest
        records[i]["after"] = round(sims[i], 4)
        learned = dict(out[i].get("learned", {}))
        learned["resynthesisCosine"] = round(sims[i], 4)
        learned["rivalCosine"] = round(max(rivals), 4) if rivals else 0.0
        learned["nearestOwn"] = nearest
        out[i]["learned"] = learned

    summary = {
        "types": len(out),
        "scored": sum(1 for b in baseline if b is not None),
        "nearestBefore": nearest_before,
        "nearestAfter": nearest_after,
        "respiration": species_resp,
        "respirationWon": sum(
            1 for r in records if r["respiration"] and "tauX" in r["respiration"]
        ),
        "twoVoiceScreened": sum(1 for r in records if r["screened"]),
        "twoVoiceWon": sum(
            1 for r in records if r["twoVoice"] and "block" in r["twoVoice"]
        ),
    }
    return out, records, summary


# --- parallel driver -------------------------------------------------------------------


def _respfit_worker(
    task: tuple[
        str,
        list[dict[str, Any]],
        list[np.ndarray | None],
        Calibration | None,
        tuple[np.ndarray, np.ndarray] | None,
        int,
        float,
        bool,
        bool,
    ],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """One species through `respfit_species`, for the pool."""
    (
        species_id,
        syllables,
        refs,
        calibration,
        frame,
        sample_rate,
        margin,
        fit_respiration,
        fit_two_voice,
    ) = task
    out, records, summary = respfit_species(
        syllables,
        refs,
        calibration,
        frame,
        sample_rate,
        margin=margin,
        fit_respiration=fit_respiration,
        fit_two_voice=fit_two_voice,
    )
    return species_id, out, records, summary


def respfit_inventory(
    observations: Sequence[SyllableObservation],
    typing_rows: Sequence[dict[str, Any]],
    inventory: dict[str, Any],
    calibration: Calibration | None,
    recording_descriptors: dict[str, np.ndarray] | None = None,
    sample_rate: int = features.SAMPLE_RATE,
    margin: float = SHIP_MARGIN,
    fit_respiration: bool = True,
    fit_two_voice: bool = True,
    jobs: int = 1,
    verbose: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fit and gate every species' learned types. Returns (document, report).

    `inventory` is the learned inventory the parallel learn wrote (read, never the
    authored one); the returned document is that same document with the gated
    `respiration`/`voices` blocks written into its syllable dicts and the `learned`
    metadata re-measured on what ships. The report carries the per-type audit and the
    pre-registered before/after numbers.
    """
    typing = {
        (str(e["speciesId"]), str(e["recordingId"]), int(e["order"])): str(e["typeId"])
        for e in typing_rows
    }
    members = type_members(observations, typing, recording_descriptors)
    frame = learn.population_frame(observations)

    tasks = []
    species_index: dict[str, dict[str, Any]] = {}
    for sp in inventory.get("species", []):
        species_id = sp.get("id", "")
        if species_id == learn.UNLABELLED_SPECIES or species_id not in members:
            continue
        fitted = [
            s for s in sp.get("syllables", []) if str(s.get("id", "")).startswith("L")
        ]
        if not fitted:
            continue
        refs: list[np.ndarray | None] = []
        kept: list[dict[str, Any]] = []
        for syl in fitted:
            rows = members[species_id].get(str(syl["id"]))
            if not rows:
                refs.append(None)
            else:
                refs.append(type_reference(rows, frame))
            kept.append(syl)
        species_index[species_id] = sp
        tasks.append(
            (
                species_id,
                kept,
                refs,
                calibration,
                frame,
                sample_rate,
                margin,
                fit_respiration,
                fit_two_voice,
            )
        )

    if verbose:
        log(
            f"respfit: {len(tasks)} species with a fit, "
            f"{sum(len(t[1]) for t in tasks)} learned types, margin {margin}"
        )

    results: dict[
        str, tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]
    ] = {}
    t0 = time.time()
    if jobs > 1 and len(tasks) > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        with ProcessPoolExecutor(
            max_workers=jobs, initializer=learn._pool_worker_init
        ) as pool:
            futures = [pool.submit(_respfit_worker, task) for task in tasks]
            for done, future in enumerate(as_completed(futures), 1):
                species_id, out, records, summary = future.result()
                results[species_id] = (out, records, summary)
                if verbose and done % 200 == 0:
                    log(
                        f"  respfit {done}/{len(tasks)} species ({time.time() - t0:.0f}s)"
                    )
    else:
        for task in tasks:
            species_id, out, records, summary = _respfit_worker(task)
            results[species_id] = (out, records, summary)

    # Reassemble the document: only the fitted L* syllables are replaced (matched by
    # id); authored syllables, U* candidates and every other field are untouched.
    document = dict(inventory)
    document["species"] = [dict(sp) for sp in inventory.get("species", [])]
    all_records: list[dict[str, Any]] = []
    per_species: dict[str, Any] = {}
    for i, sp in enumerate(document["species"]):
        species_id = sp.get("id", "")
        if species_id not in results:
            continue
        out, records, summary = results[species_id]
        by_id = {str(s["id"]): s for s in out}
        sp["syllables"] = [
            by_id.get(str(s.get("id")), s) for s in sp.get("syllables", [])
        ]
        document["species"][i] = sp
        per_species[species_id] = summary
        for r in records:
            all_records.append({"speciesId": species_id, **r})

    scored = [r for r in all_records if r["before"] is not None and "after" in r]
    before = [float(r["before"]) for r in scored]
    after = [float(r["after"]) for r in scored]
    report = {
        "margin": margin,
        "fitRespiration": fit_respiration,
        "fitTwoVoice": fit_two_voice,
        "species": per_species,
        "records": all_records,
        "global": {
            "typesScored": len(scored),
            "medianBefore": round(float(np.median(before)), 4) if before else None,
            "medianAfter": round(float(np.median(after)), 4) if after else None,
            "worstBefore": round(min(before), 4) if before else None,
            "worstAfter": round(min(after), 4) if after else None,
            "nearestBefore": sum(1 for r in scored if r["nearestBefore"]),
            "nearestAfter": sum(1 for r in scored if r.get("nearestAfter")),
            "respirationWon": sum(
                1 for r in scored if r["respiration"] and "tauX" in r["respiration"]
            ),
            "twoVoiceScreened": sum(1 for r in scored if r["screened"]),
            "twoVoiceWon": sum(
                1 for r in scored if r["twoVoice"] and "block" in r["twoVoice"]
            ),
        },
    }
    return document, report


def load_typing(store_root: Path) -> list[dict[str, Any]]:
    """The store's typing.json rows, or a hard error — the fit is nothing without them."""
    path = Path(store_root) / learn.TYPING_NAME
    if not path.exists():
        raise RuntimeError(
            f"{path} does not exist — run `learn` on this store first; the respfit "
            "fits the types learn wrote, it does not invent its own"
        )
    return json.loads(path.read_text(encoding="utf-8")).get("entries", [])


# --- self-test ---------------------------------------------------------------------


def self_test(verbose: bool = True) -> None:
    """Check the search mechanics and the gate without any store.

    The load-bearing properties, not the numerology: the grids must sit inside the
    Table S2 / twovoice clamps (a search that can propose an unstable set is a bug,
    not a find); the descent must never score below its seed (it only moves on
    improvement); the gate must ship nothing when there is nothing to win — a
    reference rendered from the very syllable being fitted is cosine 1.0, and no
    respiration or two-voice block can beat that by the margin; the screen must pick
    the worst half and nothing else; and the whole thing must be deterministic.
    """
    sr = features.SAMPLE_RATE

    # 1. Grids inside the clamps.
    assert (
        respiration.TAU_X_MIN <= min(TAU_X_GRID)
        and max(TAU_X_GRID) <= respiration.TAU_X_MAX
    )
    assert (
        respiration.TAU_P_MIN <= min(TAU_P_GRID)
        and max(TAU_P_GRID) <= respiration.TAU_P_MAX
    )
    assert (
        respiration.ALPHA_I_MIN <= min(ALPHA_I_GRID)
        and max(ALPHA_I_GRID) <= respiration.ALPHA_I_MAX
    )
    assert (
        respiration.ALPHA_REL_MIN <= min(ALPHA_REL_GRID)
        and max(ALPHA_REL_GRID) <= respiration.ALPHA_REL_MAX
    )
    assert (
        respiration.FORCING_MIN <= min(FORCING_GRID)
        and max(FORCING_GRID) <= respiration.FORCING_MAX
    )
    assert all(twovoice.BETA_INJ_MIN < b <= 0.20 for b in BETA_INJ_GRID)
    assert all(b <= twovoice.BETA_INJ_MAX for b in BETA_INJ_GRID)

    # 2. The screen: worst half, and only the worst half; one-type species screens nothing.
    assert two_voice_screen([0.9, 0.1, 0.5, 0.3]) == [False, True, False, True]
    assert two_voice_screen([0.2]) == [False]
    assert two_voice_screen([None, 0.4, 0.8]) == [False, True, False]

    # 3. Two syllables: one fitted against its own envelope-path render (nothing may
    #    ship — the baseline is cosine 1.0 and the gate cannot be cleared), one
    #    against a render carrying a respiration block far from the default (the
    #    descent must score at least its seed, and whatever ships must have cleared
    #    the margin — the gate's own invariant, checked from the record).
    base_syllable: dict[str, Any] = {
        "id": "L00",
        "label": "",
        "function": "",
        "confidence": "unlabelled",
        "refs": [],
        "dur": 0.12,
        "level": 0.9,
        "timbre": "pure",
        "contour": [[0.0, 2800.0], [1.0, 2600.0]],
        "attack": 0.008,
        "hold": False,
        "harmonic": 0.2,
    }
    far_set = respiration.RespirationParams(
        tau_x=TAU_X_GRID[1],
        tau_p=TAU_P_GRID[1],
        alpha_i=ALPHA_I_GRID[2],
        alpha_rel=ALPHA_REL_GRID[1],
        forcing=FORCING_GRID[3],
    )
    assert far_set != respiration.DEFAULT_PARAMS

    def ref_of(syllable: dict[str, Any]) -> np.ndarray:
        audio = peak_normalise(render_syllable(syllable, sample_rate=sr))
        d = features.descriptor(audio, sr)
        assert d is not None
        return learn._unit(d)

    own = dict(base_syllable, id="L00")
    moved = dict(base_syllable, id="L01", contour=[[0.0, 3600.0], [1.0, 3400.0]])
    refs = [ref_of(own), ref_of({**moved, "respiration": far_set.as_dict()})]
    syllables = [own, moved]

    out, records, summary = respfit_species(
        syllables, refs, None, None, sr, margin=SHIP_MARGIN
    )
    # The type fitted against its own render: baseline 1.0, nothing can ship.
    assert records[0]["before"] is not None and records[0]["before"] > 0.999
    assert records[0]["respiration"] is None or "tauX" not in records[0]["respiration"]
    assert records[0]["twoVoice"] is None or "block" not in records[0]["twoVoice"]
    assert "respiration" not in out[0] and "voices" not in out[0]
    # Whatever shipped anywhere must have cleared the gate — the gate's invariant,
    # asserted from the audit rather than assumed from the code path.
    for rec, syl in zip(records, out):
        if rec["respiration"] and "tauX" in rec["respiration"]:
            assert rec["respiration"]["gain"] >= SHIP_MARGIN
            assert syl.get("respiration") == {
                k: v for k, v in rec["respiration"].items() if k != "gain"
            }
        if rec["twoVoice"] and "block" in rec["twoVoice"]:
            assert rec["twoVoice"]["gain"] >= SHIP_MARGIN
            assert syl.get("voices") == rec["twoVoice"]["block"]
        if rec["after"] is not None and rec["before"] is not None:
            # the shipped syllable never scores below the one the fit started from,
            # because every attached block individually cleared the margin
            assert rec["after"] >= rec["before"]

    # 4. The descent never scores below its seed, and is deterministic.
    _, seed1, best1 = fit_species_respiration(syllables, refs, None, None, sr)
    p2, seed2, best2 = fit_species_respiration(syllables, refs, None, None, sr)
    assert best1 >= seed1 and best2 >= seed2
    assert seed1 == seed2 and best1 == best2

    # 5. The block builder stays inside the twovoice clamps however it is driven.
    block = two_voice_block([[0.0, 200.0], [1.0, 190.0]], 2.0, 2.0, BETA_INJ_GRID[-1])
    parsed = twovoice.parse(block)
    assert parsed is not None
    assert twovoice.GAMMA_MIN <= parsed.gamma <= twovoice.GAMMA_MAX
    assert parsed.level == twovoice.DEFAULT_LEVEL
    assert parsed.trachea_cm == twovoice.DEFAULT_TRACHEA_CM

    if verbose:
        print(
            "respfit self-test ok: grids inside the clamps, screen picks the worst "
            "half, the gate ships nothing against a perfect baseline, whatever ships "
            "cleared the margin, the descent is seeded and deterministic"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
