"""The pure-tone documented re-fit (docs/16 §16.4): measured texture for authored calls.

Every syllable in the hand-authored inventory is a designed tone: `timbre=pure`, no
`noise`, no `rough` — a sine with an organ envelope. The learned types of the *same
birds* say the recordings do not sound like that: the tawny owl's fitted types carry
noise 0.05–0.6 and roughness up to 0.65, and the "digital" quality of the documented
calls is exactly this missing texture. This module re-fits the two texture axes of a
documented call against the bird's own recordings, without touching the things the
documentation actually established — the contour, the duration, the function, the
citation.

**Why a re-fit and not a copy.** Transferring a learned type's `noise`/`rough` onto a
documented call wholesale would assume the call is that type. It is not necessarily:
the authored contour is the literature's, the fitted type is whatever the harvest
held. What can be done honestly is weaker and still useful: take the learned type
whose pitch is nearest the documented call as the stand-in for "how this call sounds
in the wild", render the documented syllable across the texture grid, and keep the
candidate that moves its resynthesis closest to that reference — the same 28-d
standardised cosine every other fit in the pipeline is judged by, and the same gate:
a candidate ships only where it beats the syllable as authored by `SHIP_MARGIN`. If
no texture helps, the call stays pure, and the report says so.

The reference exists because the audio does not: harvest deletes recordings by
design, so the nearest type's *member descriptors* (mean, standardised, unit-normed —
`respfit.type_reference`, exactly `learn_species`' `real[i]`) are all there is to
score against. Scoring a 950 ms authored hoot against a reference built from shorter
observed fragments is legitimate because the 28-d descriptor is a frame mean —
duration-normalised by construction (`features.descriptor`).
"""

from __future__ import annotations

import math
import sys
import time
from typing import Any, Sequence

import numpy as np

from . import features, learn, respfit, syrinx

#: Furthest pitch gap allowed between a documented call and the learned type it is
#: re-fitted against. Half an octave is generous — within it, texture is a property
#: of the bird's voice production more than of the particular note; past it, the
#: matched type is a different call and its texture says nothing about this one.
#: Duration is *not* capped: segmentation cuts long calls into short observations,
#: so a documented 950 ms hoot legitimately matches a 60 ms learned type.
F0_CAP_OCTAVES = 0.5

#: The searched axes are learn's own gesture grids (`learn._SEARCH_AXES`) — the same
#: values the inversion may land on, so a re-fitted call never carries a texture the
#: fit machinery could not have chosen for a learned type.
def _grid(axis: str) -> list[float]:
    return [float(v) for v in dict(learn._SEARCH_AXES)[axis]]  # type: ignore[misc]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _contour_f0(syllable: dict[str, Any]) -> float:
    return float(syrinx.f0_reference(syllable.get("contour", [])))


def match_type(
    documented: dict[str, Any],
    learned: Sequence[dict[str, Any]],
    f0_cap: float = F0_CAP_OCTAVES,
) -> tuple[dict[str, Any], float] | None:
    """The learned type nearest the documented call in pitch, or None past the cap.

    Distance is `|log2(f0 ratio)|` on the contour reference F0 — the number the
    tracker gets right to about 1 %. Ties break toward the nearer duration, a much
    weaker signal (segmentation fragments long calls, so duration is evidence, not
    identity). Deterministic: remaining ties go to the lexicographically smaller id,
    so two runs of the same store re-fit against the same type.
    """
    if not learned:
        return None
    f0 = _contour_f0(documented)
    dur = float(documented.get("dur", 0.0))
    if f0 <= 0.0 or dur <= 0.0:
        return None
    best: tuple[float, float, str, dict[str, Any]] | None = None
    for t in learned:
        tf0 = _contour_f0(t)
        tdur = float(t.get("dur", 0.0))
        if tf0 <= 0.0 or tdur <= 0.0:
            continue
        df0 = abs(math.log2(tf0 / f0))
        key = (df0, abs(math.log2(tdur / dur)), str(t.get("id", "")), t)
        if best is None or key[:3] < best[:3]:
            best = key
    if best is None or best[0] > f0_cap:
        return None
    return best[3], best[0]


def qualifies(syllable: dict[str, Any]) -> bool:
    """The one-tone class docs/16 names: a documented, designed-pure call.

    `timbre == "pure"` and neither texture key set — anything else already carries a
    measured or hand-designed texture and re-fitting it would second-guess that.
    Learned (`L*`) and candidate (`U*`) ids are excluded by the caller, which selects
    authored syllables; this checks the shape of the call itself.
    """
    return (
        syllable.get("timbre") == "pure"
        and "noise" not in syllable
        and "rough" not in syllable
    )


def docrefit_species(
    documented: Sequence[dict[str, Any]],
    learned: Sequence[dict[str, Any]],
    refs: dict[str, np.ndarray],
    calibration: Any,
    frame: tuple[np.ndarray, np.ndarray] | None,
    sample_rate: int = features.SAMPLE_RATE,
    margin: float = respfit.SHIP_MARGIN,
    f0_cap: float = F0_CAP_OCTAVES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Re-fit the texture of one species' documented calls. Returns (syllables, records, summary).

    `documented` are the species' authored syllable dicts (all of them, qualifying or
    not — the non-qualifying pass through untouched); `learned` the fitted `L*` types;
    `refs` maps a learned type id to its reference vector (`respfit.type_reference`).
    A learned type with no reference cannot stand in for the wild sound — a win
    against it cannot be demonstrated — so it is not a match candidate.
    """
    candidates = [t for t in learned if str(t.get("id", "")) in refs]
    out = [dict(s) for s in documented]
    records: list[dict[str, Any]] = []
    noise_grid, rough_grid = _grid("noise"), _grid("rough")
    for i, syl in enumerate(out):
        sid = str(syl.get("id", f"#{i}"))
        record: dict[str, Any] = {
            "syllableId": sid,
            "matchedType": None,
            "matchOctaves": None,
            "before": None,
            "after": None,
            "shipped": False,
        }
        records.append(record)
        if not qualifies(syl):
            record["reason"] = "not a pure-tone call"
            continue
        match = match_type(syl, candidates, f0_cap)
        if match is None:
            record["reason"] = (
                f"no learned type within {f0_cap} octaves"
                if candidates
                else "no learned type with a measured reference"
            )
            continue
        matched, match_octaves = match
        ref = refs[str(matched["id"])]
        record["matchedType"] = matched["id"]
        record["matchOctaves"] = round(match_octaves, 4)
        before = learn._score(syl, ref, calibration, frame, sample_rate)
        record["before"] = round(before, 4)

        best, best_syl = before, syl
        for noise in noise_grid:
            for rough in rough_grid:
                cand = dict(syl)
                if noise:
                    cand["noise"] = noise
                if rough:
                    cand["rough"] = rough
                score = learn._score(cand, ref, calibration, frame, sample_rate)
                if score > best:
                    best, best_syl = score, cand
        gain = best - before
        record["gain"] = round(gain, 4)
        if gain >= margin:
            fitted = dict(best_syl)
            fitted["refit"] = {
                "matchedType": matched["id"],
                "matchOctaves": round(match_octaves, 4),
                "before": round(before, 4),
                "after": round(best, 4),
            }
            out[i] = fitted
            record["after"] = round(best, 4)
            record["shipped"] = True
            record["noise"] = fitted.get("noise", 0.0)
            record["rough"] = fitted.get("rough", 0.0)

    shipped = [r for r in records if r["shipped"]]
    summary = {
        "calls": len(records),
        "scored": sum(1 for r in records if r["before"] is not None),
        "shipped": len(shipped),
        "medianGain": (
            round(float(np.median([r["gain"] for r in shipped])), 4) if shipped else None
        ),
    }
    return out, records, summary


def docrefit_inventory(
    observations: Sequence[learn.SyllableObservation],
    typing_rows: Sequence[dict[str, Any]],
    inventory: dict[str, Any],
    calibration: Any,
    recording_descriptors: dict[str, np.ndarray] | None = None,
    sample_rate: int = features.SAMPLE_RATE,
    margin: float = respfit.SHIP_MARGIN,
    f0_cap: float = F0_CAP_OCTAVES,
    verbose: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Re-fit every species' documented one-tone calls. Returns (document, report).

    `inventory` is the merged learned inventory (authored calls plus fitted `L*`
    types); the returned document is that same document with `noise`/`rough` and a
    `refit` audit block written into the calls where the gate shipped them. Species
    with no learned types in the store, and calls with no pitch-near type, pass
    through untouched and say why in the report. Serial: the authored corpus is tens
    of calls, so a process pool would be ceremony (respfit has one because it fits
    12 680 types, not 44 calls).
    """
    typing = {
        (str(e["speciesId"]), str(e["recordingId"]), int(e["order"])): str(e["typeId"])
        for e in typing_rows
    }
    members = respfit.type_members(observations, typing, recording_descriptors)
    frame = learn.population_frame(observations)

    document = dict(inventory)
    document["species"] = [dict(sp) for sp in inventory.get("species", [])]
    all_records: list[dict[str, Any]] = []
    per_species: dict[str, Any] = {}
    t0 = time.time()
    for i, sp in enumerate(document["species"]):
        species_id = sp.get("id", "")
        documented = [
            s
            for s in sp.get("syllables", [])
            if not str(s.get("id", "")).startswith(("L", "U"))
        ]
        learned = [
            s
            for s in sp.get("syllables", [])
            if str(s.get("id", "")).startswith("L")
        ]
        if not documented or not learned or species_id not in members:
            continue
        refs: dict[str, np.ndarray] = {}
        for syl in learned:
            rows = members[species_id].get(str(syl["id"]))
            if rows:
                refs[str(syl["id"])] = respfit.type_reference(rows, frame)
        out, records, summary = docrefit_species(
            documented, learned, refs, calibration, frame, sample_rate, margin, f0_cap
        )
        by_id = {str(s["id"]): s for s in out}
        sp["syllables"] = [
            by_id.get(str(s.get("id")), s) for s in sp.get("syllables", [])
        ]
        document["species"][i] = sp
        per_species[species_id] = summary
        for r in records:
            all_records.append({"speciesId": species_id, **r})
        if verbose and summary["shipped"]:
            log(
                f"  {species_id:26} {summary['shipped']} of {summary['scored']} "
                f"one-tone calls re-fitted (median gain {summary['medianGain']})"
            )

    scored = [r for r in all_records if r["before"] is not None]
    shipped = [r for r in all_records if r["shipped"]]
    report = {
        "margin": margin,
        "f0CapOctaves": f0_cap,
        "species": per_species,
        "records": all_records,
        "global": {
            "callsScored": len(scored),
            "shipped": len(shipped),
            "medianBefore": (
                round(float(np.median([r["before"] for r in scored])), 4)
                if scored
                else None
            ),
            "medianAfterShipped": (
                round(float(np.median([r["after"] for r in shipped])), 4)
                if shipped
                else None
            ),
            "medianGainShipped": (
                round(float(np.median([r["gain"] for r in shipped])), 4)
                if shipped
                else None
            ),
        },
    }
    if verbose:
        log(
            f"docrefit: {len(shipped)} of {len(scored)} scored one-tone calls shipped "
            f"a measured texture ({time.time() - t0:.1f}s)"
        )
    return document, report


# --- self-test ---------------------------------------------------------------------


def self_test(verbose: bool = True) -> None:
    """The matcher, the gate, and the pass-through, without any store.

    The three ways this fit could be wrong while still running: matching a call to a
    type too far away to speak for it, shipping a texture that did not win, and
    touching a call that was never pure. All three are checked on synthetic syllables
    whose references are other renders — no store, no audio, no critic.
    """
    pure = {
        "id": "hoo",
        "timbre": "pure",
        "dur": 0.4,
        "level": 0.9,
        "contour": [[0.0, 500.0], [1.0, 480.0]],
        "attack": 0.01,
        "hold": True,
    }
    # 1. The cap: a type a full octave away is not this call, however good its texture.
    far = {"id": "L99", "timbre": "buzz", "dur": 0.1,
           "contour": [[0.0, 1000.0], [1.0, 1000.0]]}
    assert match_type(pure, [far]) is None, "matched a type a full octave away"
    near = {"id": "L01", "timbre": "buzz", "dur": 0.1,
            "contour": [[0.0, 520.0], [1.0, 510.0]]}
    got = match_type(pure, [far, near])
    assert got is not None and got[0]["id"] == "L01", "nearest pitch did not win"

    # 2. The gate holds when nothing helps: scored against the pure render's own
    #    reference, every textured candidate is a move *away*, so nothing may ship.
    from .syrinx import peak_normalise, render_syllable

    def ref_of(syllable: dict[str, Any]) -> np.ndarray:
        audio = peak_normalise(render_syllable(syllable, sample_rate=features.SAMPLE_RATE))
        d = features.descriptor(audio, features.SAMPLE_RATE)
        assert d is not None
        return learn._unit(d)

    out, records, summary = docrefit_species(
        [pure], [near], {"L01": ref_of(pure)}, None, None
    )
    assert summary["shipped"] == 0, "texture shipped against a pure reference"
    assert "noise" not in out[0] and "rough" not in out[0], "untouched call gained keys"

    # 3. A measured texture ships when the wild reference says so: the reference is a
    #    render of the same contour with noise and roughness, and the grid contains
    #    exactly those values, so the winning candidate must beat the pure baseline.
    wild = dict(pure, noise=0.4, rough=0.4)
    out, records, summary = docrefit_species(
        [pure], [near], {"L01": ref_of(wild)}, None, None
    )
    assert summary["shipped"] == 1, "a winning texture did not ship"
    shipped = out[0]
    assert shipped.get("noise") == 0.4 and shipped.get("rough") == 0.4, (
        f"shipped {shipped.get('noise')}/{shipped.get('rough')}, not the wild 0.4/0.4"
    )
    assert shipped["refit"]["matchedType"] == "L01"
    assert shipped["refit"]["after"] > shipped["refit"]["before"]

    # 4. A call that was never pure — or already carries texture — passes through.
    textured = dict(pure, id="buzzcall", timbre="buzz")
    out, records, summary = docrefit_species(
        [textured], [near], {"L01": ref_of(wild)}, None, None
    )
    assert out[0] == textured and records[0]["reason"] == "not a pure-tone call"

    if verbose:
        log("docrefit self-test ok: cap holds, gate holds, winners ship, others pass")
