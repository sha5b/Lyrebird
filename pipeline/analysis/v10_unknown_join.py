"""
What the density map says about the map that ships, joined point by point.

The shipped galaxy uses `--clustering label`: every one of its 444 213 points gets a knot,
by construction, so it can never answer "this sound belongs to none of them". The hdbscan
map can, and `run_production_v10.sh` says in as many words that it should be built as its
own run rather than as a change to the one that has to stay comparable. This is the join
between the two runs, and the numbers only that join can produce.

**Why a join is legitimate here, and why it needs checking anyway.** `cmd_build` builds the
`PointSet` once from (inventory, store, seed) and hands it to `build_galaxy`; nothing
between there and the write shuffles or re-sorts, and the only row-dropping step is a
finite mask over the embeddings, which is a deterministic function of the same input. So
row *i* is the same syllable in both asset sets. That is an argument, not a measurement, so
`_assert_same_rows` re-derives it from the five columns the clustering cannot touch. A
silent misalignment here would produce a plausible, entirely fictional report.

Three things come out:

1. **The per-point channel.** `unassigned` — did the density clustering put this sound in
   any dense region. This is the only cross-map quantity the view actually needs, and it
   makes the discovery surface drawable on the map already on screen, with no second asset
   set and no toggle.

2. **Two named failure shapes**, neither of which has a name anywhere in the repo today:
   *named but not dense* (a label knot whose members hdbscan mostly refuses — the type is
   doing bookkeeping, not describing a cluster) and *dense but not named* (a dense region
   spanning many label knots, or full of syllables nothing has named — the candidate).

3. **A ranked discovery queue**, which is the point of the whole exercise: a dense region
   made mostly of syllables no type claims is a candidate new type, and it can be ordered
   by how many such syllables it holds.

Run: `uv run python analysis/v10_unknown_join.py` from `pipeline/`.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
KNOWN = REPO / "pipeline" / "out" / "v10" / "assets"
UNKNOWN = REPO / "pipeline" / "out" / "v10" / "assets-unknown"
REPORT = Path(__file__).with_suffix(".json")

#: A label knot is called "named but not dense" past this share of refused members. 0.9
#: rather than 1.0 so a knot the density clustering rescues two points of still counts:
#: the claim is "this type is not a dense region", not "not one member landed anywhere".
NOT_DENSE_SHARE = 0.9

#: The provenance rule, mirrored from `app/src/lib/data/assets.ts::pointProvenance`. Kept
#: as one function rather than inlined, because the app's five classes are the vocabulary
#: the report has to speak in — a second, subtly different definition here would make every
#: cross-tab below disagree with the interface it is meant to explain.
def provenance(species_id: str, syllable_id: str, source: str) -> str:
    if species_id == "unlabelled" or syllable_id[:1] == "U":
        return "unlabelled arrival"
    if not syllable_id:
        return "unidentified" if source == "field" else "documented"
    if syllable_id[0] == "L":
        return "recorded" if source == "field" else "synthesized"
    return "documented"


def _load(path: Path) -> dict[str, Any]:
    with (path / "points.json").open() as fh:
        return json.load(fh)


def _assert_same_rows(a: dict[str, Any], b: dict[str, Any]) -> None:
    """The join key is the row index; this is the evidence for that."""
    if a["n"] != b["n"]:
        raise SystemExit(f"row counts differ: {a['n']} vs {b['n']}")
    for col in ("speciesId", "syllableId", "songId", "source"):
        if a[col] != b[col]:
            bad = next(i for i, (x, y) in enumerate(zip(a[col], b[col])) if x != y)
            raise SystemExit(f"{col} differs first at row {bad}: {a[col][bad]!r} vs {b[col][bad]!r}")
    da = np.asarray(a["durations"], dtype=np.float64)
    db = np.asarray(b["durations"], dtype=np.float64)
    if not np.allclose(da, db, rtol=0, atol=1e-9):
        raise SystemExit("durations differ — the two builds are not the same point set")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--known", type=Path, default=KNOWN)
    ap.add_argument("--unknown", type=Path, default=UNKNOWN)
    ap.add_argument("--report", type=Path, default=REPORT)
    ap.add_argument(
        "--enrich",
        type=Path,
        default=None,
        help="also write the `unassigned` channel into this points.json, in place",
    )
    args = ap.parse_args()

    known = _load(args.known)
    unknown = _load(args.unknown)
    _assert_same_rows(known, unknown)
    n = known["n"]
    print(f"joined {n} rows; the five invariant columns agree")

    label = np.asarray(known["clusterId"], dtype=np.int64)
    dens = np.asarray(unknown["clusterId"], dtype=np.int64)
    unassigned = dens < 0
    prov = np.array(
        [
            provenance(s, y or "", src)
            for s, y, src in zip(known["speciesId"], known["syllableId"], known["source"])
        ]
    )

    out: dict[str, Any] = {
        "points": int(n),
        "labelKnots": int(label.max() + 1),
        "densityRegions": int(dens.max() + 1),
        "unassigned": int(unassigned.sum()),
        "unassignedShare": round(float(unassigned.mean()), 4),
        "provenanceMix": {k: int(v) for k, v in sorted(Counter(prov.tolist()).items())},
    }
    print(
        f"label knots {out['labelKnots']}, density regions {out['densityRegions']}, "
        f"in no dense region {out['unassigned']} ({out['unassignedShare'] * 100:.1f} %)"
    )

    # --- agreement between the two labellings -----------------------------------------
    # ARI/AMI over 444 k rows is cheap and is the standard answer to "do these two
    # partitions describe the same structure". Noise is kept as its own label rather than
    # dropped: a partition that refuses 40 % of the corpus disagrees with one that refuses
    # nothing, and excluding the refusals would hide exactly that.
    from sklearn.metrics import adjusted_mutual_info_score, adjusted_rand_score

    out["agreement"] = {
        "adjustedRand": round(float(adjusted_rand_score(label, dens)), 4),
        "adjustedMutualInfo": round(float(adjusted_mutual_info_score(label, dens)), 4),
        "definition": (
            "how much the label partition and the density partition describe the same "
            "grouping; 0 is chance, 1 is identical. hdbscan's noise is kept as one label "
            "rather than dropped, because refusing 40 % of the corpus IS a disagreement"
        ),
    }
    print(
        f"agreement: adjusted Rand {out['agreement']['adjustedRand']}, "
        f"AMI {out['agreement']['adjustedMutualInfo']}"
    )

    # --- shape 1: named but not dense --------------------------------------------------
    knots = out["labelKnots"]
    per_knot_total = np.bincount(label[label >= 0], minlength=knots).astype(np.float64)
    per_knot_refused = np.bincount(label[(label >= 0) & unassigned], minlength=knots).astype(
        np.float64
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        refused_share = np.where(per_knot_total > 0, per_knot_refused / per_knot_total, np.nan)
    measured = np.isfinite(refused_share)
    not_dense = measured & (refused_share >= NOT_DENSE_SHARE)
    out["namedButNotDense"] = {
        "threshold": NOT_DENSE_SHARE,
        "knotsMeasured": int(measured.sum()),
        "knots": int(not_dense.sum()),
        "knotShare": round(float(not_dense.sum() / max(1, measured.sum())), 4),
        "pointsInThem": int(per_knot_total[not_dense].sum()),
        "medianRefusedShare": round(float(np.nanmedian(refused_share)), 4),
        "definition": (
            "a knot the label clustering named whose members the density clustering puts "
            "in no dense region at all. The type is bookkeeping over these points, not a "
            "description of a cluster the data supports"
        ),
    }
    print(
        f"named but not dense: {out['namedButNotDense']['knots']} of "
        f"{out['namedButNotDense']['knotsMeasured']} knots "
        f"({out['namedButNotDense']['knotShare'] * 100:.1f} %), "
        f"median refused share {out['namedButNotDense']['medianRefusedShare']}"
    )

    # --- shape 2: dense but not named -------------------------------------------------
    # Per density region: how many label knots it spans, and what it is made of. A region
    # spanning many knots is the label map over-splitting; a region made of syllables no
    # type claims is a candidate type.
    spans: dict[int, set[int]] = defaultdict(set)
    unnamed: Counter[int] = Counter()
    total: Counter[int] = Counter()
    species: dict[int, Counter[str]] = defaultdict(Counter)
    for d, l, p, sp in zip(dens.tolist(), label.tolist(), prov.tolist(), known["speciesId"]):
        if d < 0:
            continue
        total[d] += 1
        spans[d].add(l)
        species[d][sp] += 1
        if p == "unidentified":
            unnamed[d] += 1

    span_counts = np.array([len(spans[d]) for d in sorted(spans)], dtype=np.float64)
    out["denseButNotNamed"] = {
        "regionsMeasured": int(len(spans)),
        "medianLabelKnotsSpanned": float(np.median(span_counts)) if span_counts.size else 0.0,
        "maxLabelKnotsSpanned": int(span_counts.max()) if span_counts.size else 0,
        "regionsSpanningOverTen": int((span_counts > 10).sum()),
        "definition": (
            "one dense region, and how many of the label map's knots its members are "
            "spread across. Above one means the label map splits what the density of the "
            "data holds together"
        ),
    }
    print(
        f"dense but not named: {out['denseButNotNamed']['regionsMeasured']} regions, "
        f"median {out['denseButNotNamed']['medianLabelKnotsSpanned']} label knots each, "
        f"max {out['denseButNotNamed']['maxLabelKnotsSpanned']}"
    )

    # --- the discovery queue ----------------------------------------------------------
    # The thing the whole exercise is for: a dense region made mostly of syllables no type
    # claims. Ordered by how many such syllables it holds, because that is the size of the
    # finding rather than its purity.
    queue = []
    for d in sorted(total, key=lambda d: (-unnamed[d], d)):
        if not unnamed[d]:
            break
        top_species, top_count = species[d].most_common(1)[0]
        queue.append(
            {
                "region": int(d),
                "points": int(total[d]),
                "unidentified": int(unnamed[d]),
                "unidentifiedShare": round(unnamed[d] / total[d], 3),
                "labelKnotsSpanned": len(spans[d]),
                "topSpecies": top_species,
                "topSpeciesShare": round(top_count / total[d], 3),
            }
        )
    unnamed_total = int((prov == "unidentified").sum())
    in_region = int(sum(unnamed.values()))
    out["discoveryQueue"] = {
        "unidentifiedPoints": unnamed_total,
        "inADenseRegion": in_region,
        "inNoDenseRegion": unnamed_total - in_region,
        "regionsHoldingAny": len(queue),
        "top": queue[:25],
        "definition": (
            "an unidentified point is real field audio carrying no type id. One sitting "
            "in a dense region is a candidate type — the density of the data claims it "
            "even though no type does. One in no dense region is a singleton, and not yet "
            "a finding"
        ),
    }
    print(
        f"discovery queue: {unnamed_total} unidentified points, {in_region} of them in a "
        f"dense region across {len(queue)} regions"
    )

    # --- crossing the two channels that already ship ----------------------------------
    # `knnAgreement` is per point and already in points.json, and nothing reads it. Crossed
    # with the density verdict it says something neither says alone: a point that no dense
    # region claims AND whose neighbours are all other types is one the map places among
    # strangers, which is where a wrong position and a real discovery look alike.
    if known.get("knnAgreement"):
        knn = np.asarray(known["knnAgreement"], dtype=np.float64)
        out["knnByDensity"] = {
            "assignedMean": round(float(knn[~unassigned].mean()), 4),
            "unassignedMean": round(float(knn[unassigned].mean()), 4),
            "unidentifiedAndUnassignedMean": round(
                float(knn[(prov == "unidentified") & unassigned].mean()), 4
            )
            if int(((prov == "unidentified") & unassigned).sum())
            else None,
            "definition": (
                "mean share of a point's ten nearest 3D neighbours sharing its type, split "
                "by whether the density clustering placed it. A gap means the two "
                "measurements agree about which points are badly placed"
            ),
        }
        print(
            f"knn agreement: placed {out['knnByDensity']['assignedMean']}, "
            f"refused {out['knnByDensity']['unassignedMean']}"
        )

    if known.get("snr"):
        snr = np.asarray([v if v is not None else np.nan for v in known["snr"]], dtype=np.float64)
        both = np.isfinite(snr)
        out["snrByDensity"] = {
            "assignedMedian": round(float(np.nanmedian(snr[both & ~unassigned])), 3),
            "unassignedMedian": round(float(np.nanmedian(snr[both & unassigned])), 3),
            "measured": int(both.sum()),
            "definition": (
                "ingest signal-to-noise in dB, split by the density verdict. If the refused "
                "points are simply the quiet ones, the discovery surface is a recording-"
                "quality artefact and has to be read as one"
            ),
        }
        print(
            f"snr: placed median {out['snrByDensity']['assignedMedian']} dB, "
            f"refused {out['snrByDensity']['unassignedMedian']} dB"
        )

    args.report.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {args.report}")

    if args.enrich:
        with args.enrich.open() as fh:
            target = json.load(fh)
        if target["n"] != n:
            raise SystemExit(f"{args.enrich} holds {target['n']} points, joined {n}")
        for col in ("speciesId", "syllableId", "source"):
            if target[col] != known[col]:
                raise SystemExit(f"{args.enrich} is not the same point set ({col} differs)")
        target["unassigned"] = [int(v) for v in unassigned.tolist()]
        target["densityRegion"] = [int(v) for v in dens.tolist()]
        with args.enrich.open("w") as fh:
            json.dump(target, fh, separators=(",", ":"))
        print(f"enriched {args.enrich} with `unassigned` and `densityRegion`")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
