"""G3 — does the recordist confound survive species-level aggregation? (docs/24 Phase 0)

Pre-registered in `docs/24-what-this-corpus-could-add-to-ornithology.md` before this
script existed:

    Recompute the confound on species means rather than on points, and on a
    recordist-blocked resample where no species contributes two recordings from one
    recordist. Report the species lift and the recordist lift under both.

    gate: species lift must exceed recordist lift. State the margin.
    if it fails: every comparative question must be restricted to species with three or
                 more independent recordists, and that count must be reported before
                 anything else is run.

**One deviation from the pre-registration, and it is forced.** "Species means" taken
literally is one point per species, and species lift is then untestable by construction —
`geometry.measure` says so itself and returns "untestable (one observation per group)"
rather than a zero. The aggregation that removes the pseudo-replication G3 is aimed at,
while leaving both groupings measurable, is **one point per recording**. That is also the
representation `w6_t1_perch_recordist.py` already uses, so the two results are comparable.
It is written down here rather than quietly substituted.

The estimator is the project's own (`geometry.measure`): kNN label agreement at k = 10
against a 199-draw permutation null, lift = observed - null mean. Nothing new is invented
for this gate, so the number is on the same scale as every previous confound measurement.

ARM A  every recording with a recordist and syllable embeddings, aggregated to one point.
ARM B  the recordist-blocked resample: within each species, at most one recording per
       recordist. This is the arm that asks whether the structure is *the same recordist
       supplying the same species repeatedly*.

Usage:  .venv/bin/python analysis/g3_recordist_aggregation.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from birdy_pipeline import geometry  # noqa: E402
from birdy_pipeline.harvest import HarvestStore  # noqa: E402

STORE = ROOT / "out/harvest-gan"
OUT = Path(__file__).resolve().parent / "g3_recordist_aggregation.json"
SEED = 0


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def recording_means(store: HarvestStore) -> dict[str, np.ndarray]:
    """recording_id -> mean of that recording's syllable embeddings."""
    raw = np.fromfile(STORE / "embeddings.f32", dtype="<f4")
    n = len(store.syllables)
    if raw.size % n:
        raise RuntimeError(f"embeddings.f32 holds {raw.size} floats for {n} syllables")
    emb = raw.reshape(n, -1).astype(np.float64)
    sums: dict[str, np.ndarray] = {}
    counts: dict[str, int] = defaultdict(int)
    for row, o in zip(emb, store.syllables):
        if not np.all(np.isfinite(row)) or not row.any():
            continue
        rid = o.recording_id
        sums[rid] = sums.get(rid, 0.0) + row
        counts[rid] += 1
    return {rid: v / counts[rid] for rid, v in sums.items()}


def arm(
    name: str,
    ids: list[str],
    means: dict[str, np.ndarray],
    store: HarvestStore,
) -> dict[str, object]:
    x = np.stack([means[r] for r in ids])
    species = [store.recordings[r].get("speciesId", "") or "" for r in ids]
    who = [store.recordings[r].get("recordist", "") or "" for r in ids]

    out: dict[str, object] = {
        "arm": name,
        "recordings": len(ids),
        "species": len({s for s in species if s}),
        "recordists": len({w for w in who if w}),
    }
    print()
    print(f"  {name}")
    print(f"    {len(ids):6d} recordings   {out['species']:5d} species   "
          f"{out['recordists']:5d} recordists")
    for grouping, labels in (("species", species), ("recordist", who)):
        rel = geometry.measure(
            x, labels, grouping=grouping, space="critic", metric="cosine", seed=SEED
        )
        if rel is None:
            print(f"    {grouping:10s} untestable")
            out[grouping] = None
            continue
        lift = rel.knn - rel.knn_null
        out[grouping] = {
            "groups": rel.groups,
            "labelled": rel.labelled,
            "coverage": round(rel.coverage, 4),
            "knn": round(rel.knn, 4),
            "null": round(rel.knn_null, 4),
            "lift": round(lift, 4),
            "p": rel.knn_p,
            "verdict": rel.verdict,
        }
        print(f"    {grouping:10s} groups {rel.groups:5d}   knn {rel.knn:.3f}   "
              f"null {rel.knn_null:.3f}   LIFT {lift:+.3f}   p {rel.knn_p:.3g}   "
              f"{rel.verdict}")
        # `measure` drops any group with fewer than 8 members, so both arms are really
        # measured on the well-sampled tail. Reporting the share is the difference
        # between "the corpus behaves like this" and "8 % of it does".
        print(f"    {'':10s} tested on {rel.labelled} of {len(ids)} recordings "
              f"({rel.coverage:.1%} of the arm)")
    return out


def main() -> int:
    store = HarvestStore(STORE)
    store.load()
    means = recording_means(store)
    log(f"per-recording means for {len(means)} recordings")

    usable = sorted(
        r for r in means
        if store.recordings.get(r, {}).get("recordist")
        and store.recordings.get(r, {}).get("speciesId")
    )

    print("=" * 72)
    print("G3 — does the recordist confound survive aggregation to one point per")
    print("     recording, and a recordist-blocked resample?")
    print("=" * 72)
    print(f"  recordings in store with embeddings   {len(means):6d}")
    print(f"  ...that carry BOTH species and recordist {len(usable):6d}")

    results = [arm("ARM A — aggregated, every recording", usable, means, store)]

    # ARM B: within each species, at most one recording per recordist.
    rng = np.random.default_rng(SEED)
    seen: set[tuple[str, str]] = set()
    blocked: list[str] = []
    for r in rng.permutation(np.array(usable, dtype=object)).tolist():
        key = (store.recordings[r]["speciesId"], store.recordings[r]["recordist"])
        if key in seen:
            continue
        seen.add(key)
        blocked.append(r)
    blocked.sort()
    results.append(
        arm("ARM B — recordist-blocked (<=1 recording per species x recordist)",
            blocked, means, store)
    )

    # ARM C. Arms A and B compare two lifts that `measure` computed on different rows —
    # it drops any group under 8 members, and "species with >= 8 recordings" is not the
    # same population as "recordist with >= 8 recordings". A margin between two different
    # populations is not the margin the gate asks about. This arm keeps only recordings
    # whose species AND whose recordist both clear 8, so the two lifts are measured on
    # one identical row set and the subtraction means something.
    def matched(ids: list[str]) -> list[str]:
        for _ in range(20):  # dropping rows can push a group back under 8; iterate
            sp_n: dict[str, int] = defaultdict(int)
            rc_n: dict[str, int] = defaultdict(int)
            for r in ids:
                sp_n[store.recordings[r]["speciesId"]] += 1
                rc_n[store.recordings[r]["recordist"]] += 1
            keep = [
                r for r in ids
                if sp_n[store.recordings[r]["speciesId"]] >= geometry.MIN_GROUP
                and rc_n[store.recordings[r]["recordist"]] >= geometry.MIN_GROUP
            ]
            if len(keep) == len(ids):
                return keep
            ids = keep
        return ids

    both = matched(usable)
    if both:
        results.append(
            arm("ARM C — matched rows (species AND recordist both >= 8), the fair margin",
                both, means, store)
        )

    print()
    print("=" * 72)
    for res in results:
        sp, rc = res.get("species"), res.get("recordist")
        if not isinstance(sp, dict) or not isinstance(rc, dict):
            continue
        margin = sp["lift"] - rc["lift"]
        verdict = "PASS" if margin > 0 else "FAIL"
        print(f"  {res['arm']}")
        print(f"    species lift {sp['lift']:+.3f}  vs  recordist lift {rc['lift']:+.3f}"
              f"   margin {margin:+.3f}   -> {verdict}")

    # The count docs/24 says to report before anything else runs, if G3 fails.
    per_species: dict[str, set[str]] = defaultdict(set)
    for r in usable:
        per_species[store.recordings[r]["speciesId"]].add(
            store.recordings[r]["recordist"]
        )
    three_plus = sum(1 for v in per_species.values() if len(v) >= 3)
    print()
    print("  The fallback population docs/24 asks to be stated up front either way:")
    print(f"    species with >= 3 independent recordists   {three_plus:5d}"
          f" of {len(per_species)}")
    print(f"    species with >= 2                          "
          f"{sum(1 for v in per_species.values() if len(v) >= 2):5d}")
    print(f"    species with exactly 1                     "
          f"{sum(1 for v in per_species.values() if len(v) == 1):5d}")

    OUT.write_text(json.dumps(
        {"arms": results, "species_with_3plus_recordists": three_plus,
         "species_total": len(per_species)}, indent=1))
    print()
    print(f"  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
