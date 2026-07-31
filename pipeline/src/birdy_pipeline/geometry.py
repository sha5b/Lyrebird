"""
Does a grouping have geometric structure, or does it only look like it does?

Every number the build already prints answers a question about *one* labelling —
`clusterPurity` scores the KMeans clusters, `knnAgreement` scores the syllable types. None
of them answers the question this module exists for: **given some way of grouping the
recordings, is there a relation between that grouping and where the points sit — and is it
more of a relation than the same labels shuffled at random would produce?**

That last clause is the whole point. Any labelling of 47,000 points into a dozen groups will
produce a non-zero agreement score, because points near each other are near each other
whatever you call them. A silhouette of 0.04 and a kNN agreement of 0.31 look like weak
evidence of something; they are usually strong evidence of nothing, and the only way to tell
is to compute the same statistic on labels that have been permuted and see where the real
one falls. So every figure here comes with a p-value from a label permutation, and a
grouping that cannot beat its own shuffle is reported as **no relation** rather than as a
small effect.

## The two spaces, and why both

A relation can exist in the descriptors and be destroyed by the projection, which matters
because the projection is what a viewer actually looks at. So each grouping is measured
twice: in the standardised 28-d space where the clustering and the live matching happen, and
in the 3-d arrangement that gets drawn. A grouping that scores well in 28-d and badly in 3-d
is real and invisible; one that scores badly in both is not there; one that scores better in
3-d than in 28-d is an artefact of the layout and should be distrusted.

## The controls matter more than the results

`source` — was this recorded or synthesised — is included deliberately, and if it wins, every
other row on the table is suspect, because it means the geometry is mostly answering a
question about microphones. Same for `sampleRate` and `recordist`. A grouping only tells you
something about birds if it beats the equipment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from sklearn.neighbors import NearestNeighbors

# Neighbourhood size for the agreement statistic. 10 is what the build already uses for
# `knnAgreement`, and keeping it identical means the two numbers are comparable.
KNN_K = 10
# Permutations for the null. 199 gives a resolution of 0.005 on p, which is far finer than
# any decision here needs, and costs one kNN lookup reuse per permutation because the
# neighbour graph is computed once and only the labels move.
PERMUTATIONS = 199
# Silhouette is O(n^2) in distance computations, so it runs on a stratified subsample. 4000
# points give a standard error around 0.01 on the statistic, which is well inside the
# margin any of these conclusions turn on.
SILHOUETTE_SAMPLE = 4000
# A group with fewer members than this is noise as far as geometry goes: its silhouette is
# dominated by one or two points and its neighbours are mostly other groups by necessity.
MIN_GROUP = 8
# Below this many labelled points a permutation test is arithmetic rather than evidence. The
# metadata groupings only cover recordings harvested since the extra xeno-canto fields were
# kept, so early on several of them legitimately have almost nothing to test — and reporting
# a nonsense figure as "no relation" would be the same class of mistake as reporting a
# blocked-out grouping as "no relation".
MIN_LABELLED = 200


@dataclass
class Relation:
    """One grouping, measured in one space."""

    grouping: str
    space: str
    groups: int
    labelled: int
    coverage: float
    knn: float
    knn_null: float
    knn_p: float
    silhouette: float
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        # nan is not JSON, and `null` is the honest encoding of "not measured" anyway.
        def num(v: float) -> float | None:
            return None if math.isnan(v) else round(v, 4)

        return {
            "grouping": self.grouping,
            "space": self.space,
            "groups": self.groups,
            "labelled": self.labelled,
            "coverage": round(self.coverage, 4),
            "knn": num(self.knn),
            "knnNull": num(self.knn_null),
            "knnP": num(self.knn_p),
            "silhouette": num(self.silhouette),
            "verdict": self.verdict,
        }


def _unit_rows(z: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(z, axis=1, keepdims=True)
    return z / np.maximum(norm, 1.0e-12)


def _neighbours(
    x: np.ndarray, metric: str, k: int, blocks: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Each point's k nearest neighbours *from outside its own block*, and a validity mask.

    **Blocking is what makes the statistic mean anything, and without it every grouping
    scored about 0.98.** The samples here are nowhere near independent. The synthetic corpus
    renders ninety-six jittered variants of each syllable, so a rendered point's ten nearest
    neighbours are almost always the other ninety-five copies of itself; the harvester slides
    overlapping windows along one recording, so a field point's neighbours are the adjacent
    windows of the same audio. Measuring label agreement over those pairs asks whether a
    recording resembles itself, and the answer is yes for every labelling anyone can invent —
    including `recordist` and `country`, which is how a corpus of forty-seven thousand points
    can appear to be strongly organised by who held the microphone.

    So a point's own block is excluded. The block is the recording for harvested audio and the
    syllable type for a rendered variant, because ninety-six jitters of one parameter set are
    one observation, not ninety-six. A row with no out-of-block neighbour is dropped, and the
    caller reports how many survived.
    """
    k = min(k, len(x) - 1)
    if blocks is None:
        nn = NearestNeighbors(n_neighbors=k + 1, metric=metric).fit(x)
        found = nn.kneighbors(x, return_distance=False)[:, 1:]
        return found, np.ones(found.shape, dtype=bool)

    # Ask for enough that k out-of-block neighbours usually survive the mask. The largest
    # block dominates the requirement, capped so a pathological corpus cannot ask for n.
    largest = int(np.max(np.bincount(blocks))) if len(blocks) else 1
    want = min(len(x) - 1, k + largest)
    nn = NearestNeighbors(n_neighbors=want + 1, metric=metric).fit(x)
    found = nn.kneighbors(x, return_distance=False)[:, 1:]
    same = blocks[found] == blocks[:, None]
    out = np.full((len(x), k), -1, dtype=np.int64)
    for i in range(len(x)):
        allowed = found[i][~same[i]]
        take = min(k, len(allowed))
        if take:
            out[i, :take] = allowed[:take]
    return out, out >= 0


def _agreement(codes: np.ndarray, neighbours: np.ndarray, valid: np.ndarray) -> float:
    """Share of *valid* neighbour pairs sharing a label."""
    if not valid.any():
        return float("nan")
    hits = (codes[np.maximum(neighbours, 0)] == codes[:, None]) & valid
    return float(hits.sum() / valid.sum())


def _silhouette(x: np.ndarray, codes: np.ndarray, metric: str, rng: np.random.Generator) -> float:
    """Mean silhouette over a subsample, or nan when there is nothing to measure.

    Computed by hand rather than through sklearn's helper so the subsample is stratified —
    an unstratified draw from a corpus whose largest group is fifty times its smallest gives
    the small groups two points each and a meaningless answer.
    """
    groups = [np.nonzero(codes == c)[0] for c in np.unique(codes)]
    groups = [g for g in groups if len(g) >= MIN_GROUP]
    if len(groups) < 2:
        return float("nan")
    per_group = max(2, SILHOUETTE_SAMPLE // len(groups))
    picked = np.concatenate(
        [rng.choice(g, size=min(len(g), per_group), replace=False) for g in groups]
    )
    sub = x[picked]
    sub_codes = codes[picked]
    if metric == "cosine":
        u = _unit_rows(sub)
        d = np.maximum(1.0 - u @ u.T, 0.0)
    else:
        # Squared euclidean via the Gram matrix: ||a-b||² = |a|²+|b|²-2a·b. The
        # (n,n,d) outer-subtraction form allocated n²·d floats — 212 GB at the
        # 4 000 x 1 658 songspace scale (the HANDOFF OOM); this form is n² and
        # value-identical up to float summation order.
        sq = (sub**2).sum(axis=1)
        d = np.sqrt(np.maximum(sq[:, None] + sq[None, :] - 2.0 * sub @ sub.T, 0.0))
    np.fill_diagonal(d, 0.0)

    scores: list[float] = []
    unique = np.unique(sub_codes)
    for i in range(len(sub)):
        own = sub_codes == sub_codes[i]
        own[i] = False
        if not own.any():
            continue
        a = float(d[i, own].mean())
        b = math.inf
        for c in unique:
            if c == sub_codes[i]:
                continue
            other = sub_codes == c
            if other.any():
                b = min(b, float(d[i, other].mean()))
        if not math.isfinite(b):
            continue
        scores.append((b - a) / max(a, b, 1.0e-12))
    return float(np.mean(scores)) if scores else float("nan")


def measure(
    x: np.ndarray,
    labels: Sequence[str],
    grouping: str,
    space: str,
    metric: str,
    seed: int = 0,
    blocks: Sequence[str] | None = None,
    min_group: int = MIN_GROUP,
    min_labelled: int = MIN_LABELLED,
) -> Relation | None:
    """One grouping in one space, with the permutation null attached.

    Unlabelled points (empty string) are dropped rather than pooled into an "other" group:
    "no recorded call type" is an absence of information, and turning it into a category
    would let the *pattern of missingness* score as a relation. The share that survives is
    reported as `coverage`, because a relation over 3 % of the corpus is a different claim
    from one over all of it.

    `min_group`/`min_labelled` exist for callers that test a small population on
    purpose — songspace.py's within-species individual test runs one species at a
    time, where the corpus-level gates of 8/200 would leave almost nothing
    testable and the permutation null, not the gate, is what keeps a small test
    honest. The statistic itself does not move.
    """
    labels = list(labels)
    keep = np.array([bool(v) for v in labels])
    if keep.sum() < min_group * 2:
        return None
    codes, counts = np.unique(np.array(labels)[keep], return_inverse=False, return_counts=True)
    # Drop groups too small to have a neighbourhood, then re-index.
    big = {c for c, n in zip(codes, counts) if n >= min_group}
    keep = np.array([bool(v) and v in big for v in labels])
    if keep.sum() < min_group * 2:
        return None
    kept_labels = np.array(labels)[keep]
    uniq, coded = np.unique(kept_labels, return_inverse=True)
    if len(uniq) < 2:
        return None

    if int(keep.sum()) < min_labelled:
        return Relation(
            grouping=grouping, space=space, groups=len(uniq), labelled=int(keep.sum()),
            coverage=float(keep.sum()) / len(labels), knn=float("nan"), knn_null=float("nan"),
            knn_p=float("nan"), silhouette=float("nan"),
            verdict=f"untestable ({int(keep.sum())} labelled, need {min_labelled})",
        )

    sub = x[keep]
    block_codes = None
    if blocks is not None:
        _, block_codes = np.unique(np.array(list(blocks))[keep], return_inverse=True)
        # **A grouping nested one-to-one inside the blocking cannot be tested by this
        # statistic, and must not be reported as absent.** If every member of a label sits in
        # a single block, excluding the block excludes every pair that could have agreed, so
        # the agreement is exactly zero for reasons of bookkeeping rather than acoustics.
        # `syllableType` on rendered audio is precisely this case: the ninety-six variants of
        # one syllable are one observation, so the label and the block are the same partition.
        # Answering it needs independent recordings of the same call type, which is what the
        # harvest is for — not a different sum over the same points.
        per_label = {}
        for lab, blk in zip(coded, block_codes):
            per_label.setdefault(int(lab), set()).add(int(blk))
        if max(len(v) for v in per_label.values()) <= 1:
            return Relation(
                grouping=grouping, space=space, groups=len(uniq), labelled=int(keep.sum()),
                coverage=float(keep.sum()) / len(labels), knn=float("nan"),
                knn_null=float("nan"), knn_p=float("nan"),
                silhouette=_silhouette(x[keep], coded, metric, np.random.default_rng(seed + 1)),
                verdict="untestable (one observation per group)",
            )
    neighbours, valid = _neighbours(sub, metric, KNN_K, block_codes)
    if not valid.any():
        return None
    observed = _agreement(coded, neighbours, valid)
    if math.isnan(observed):
        return None

    rng = np.random.default_rng(seed)
    # Only the labels move. Re-fitting the neighbour graph per permutation would be the
    # same null at a hundred times the cost — the geometry is not what is being tested.
    null = np.empty(PERMUTATIONS)
    shuffled = coded.copy()
    for i in range(PERMUTATIONS):
        rng.shuffle(shuffled)
        null[i] = _agreement(shuffled, neighbours, valid)
    # The usual +1 convention, so p is never exactly zero with a finite number of draws.
    p = float((np.sum(null >= observed) + 1) / (PERMUTATIONS + 1))

    sil = _silhouette(sub, coded, metric, np.random.default_rng(seed + 1))
    lift = observed - float(null.mean())
    if p > 0.05:
        verdict = "none"
    elif lift < 0.02:
        verdict = "negligible"
    elif lift < 0.10:
        verdict = "weak"
    elif lift < 0.25:
        verdict = "clear"
    else:
        verdict = "strong"

    return Relation(
        grouping=grouping,
        space=space,
        groups=len(uniq),
        labelled=int(np.count_nonzero(valid.any(axis=1))),
        coverage=float(keep.sum()) / len(labels),
        knn=observed,
        knn_null=float(null.mean()),
        knn_p=p,
        silhouette=sil,
        verdict=verdict,
    )


def analyse(
    spaces: dict[str, tuple[np.ndarray, str]],
    groupings: dict[str, Sequence[str]],
    seed: int = 0,
    blocks: Sequence[str] | None = None,
) -> list[Relation]:
    """Every grouping in every space. `spaces` maps a name to (matrix, metric).

    `blocks` names the unit of independent observation per point — see `_neighbours`. Pass it;
    the unblocked numbers are not interpretable on this corpus.
    """
    out: list[Relation] = []
    for space, (x, metric) in spaces.items():
        for grouping, labels in groupings.items():
            found = measure(x, labels, grouping, space, metric, seed=seed, blocks=blocks)
            if found is not None:
                out.append(found)
    return out


def blocks_for(
    species_id: Sequence[str],
    syllable_id: Sequence[str],
    recording_id: Sequence[str],
    source: Sequence[str],
) -> list[str]:
    """The unit of independent observation per point.

    A harvested recording is one observation however many overlapping windows were sliced from
    it. A rendered syllable is one observation however many jittered variants were drawn from
    it — the jitter is a few per cent on pitch and duration, not a new bird. Getting this wrong
    in the permissive direction is what made every grouping look strong.
    """
    out: list[str] = []
    for sp, syl, rid, src in zip(species_id, syllable_id, recording_id, source):
        if src == "field" and rid:
            out.append(f"rec:{rid}")
        elif syl:
            out.append(f"type:{sp}/{syl}")
        else:
            out.append(f"song:{sp}/{rid}")
    return out


def _season(date: str) -> str:
    """Meteorological season from an ISO date, northern hemisphere.

    Northern because every species in the inventory breeds there. A southern record would be
    mislabelled, which is why `country` is tested alongside: if season carries a relation and
    country carries the same one, the season result is probably geography.
    """
    parts = str(date or "").split("-")
    if len(parts) < 2 or not parts[1].isdigit():
        return ""
    month = int(parts[1])
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return ""


def _call_type(raw: str) -> str:
    """xeno-canto's `type` string reduced to its primary term.

    The field is free text with comma-separated qualifiers — `"call, call female"`,
    `"song, excitement call"`, `"aberrant, call, song"` — and testing it verbatim would score
    hundreds of one-member groups as hundreds of distinct call types. The first term is the
    recordist's primary judgement, and collapsing to it is what makes the group sizes large
    enough for a neighbourhood to mean anything.
    """
    first = str(raw or "").split(",")[0].strip().lower()
    if not first or first in ("uncertain", "unknown", "aberrant"):
        return ""
    # Fold the handful of near-duplicates the corpus actually contains.
    for stem in ("alarm call", "flight call", "begging call", "drumming", "song", "call"):
        if stem in first:
            return stem
    return first


def label_sets(
    species_id: Sequence[str],
    syllable_id: Sequence[str],
    recording_id: Sequence[str],
    source: Sequence[str],
    recordings: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[str]]:
    """Every grouping worth testing, as parallel label arrays over the same points.

    The recording-derived ones only cover the harvested points — a rendered syllable has no
    recordist and no sample rate — which is exactly what `coverage` reports. They are worth
    testing on that subset anyway: if `recordist` explains the field points' geometry, then
    the field half of this corpus is a map of microphones and the rest of the table has to be
    read in that light.
    """
    recordings = recordings or {}
    n = len(species_id)
    info = [recordings.get(rid, {}) if rid else {} for rid in recording_id]

    def field_only(values: Sequence[Any]) -> list[str]:
        # Blank for anything that is not a harvested recording, so it drops out rather than
        # forming a giant "synthetic" group that would swamp the statistic.
        return [str(v) if v else "" for v in values]

    sets: dict[str, list[str]] = {
        # Acoustic structure.
        "species": [str(s or "") for s in species_id],
        "syllableType": [
            f"{sp}/{sy}" if sy else "" for sp, sy in zip(species_id, syllable_id)
        ],
        # The control that decides how to read everything else.
        "source": [str(s or "") for s in source],
        # The call type xeno-canto hands us and the pipeline used to discard.
        "callType": field_only([_call_type(i.get("type", "")) for i in info]),
        # Recording conditions.
        "sampleRate": field_only([i.get("sampleRate") for i in info]),
        "recordist": field_only([i.get("recordist") for i in info]),
        "automatic": field_only([i.get("automatic") for i in info]),
        "backgroundSpecies": field_only(
            ["some" if i.get("also") else ("none" if i else "") for i in info]
        ),
        # Time and place.
        "country": field_only([i.get("country") for i in info]),
        "season": field_only([_season(i.get("date", "")) for i in info]),
        "quality": field_only([i.get("quality") for i in info]),
    }
    return {k: v for k, v in sets.items() if len(v) == n}


def format_table(relations: Sequence[Relation]) -> str:
    """The table, ordered so the strongest relation in the descriptor space reads first."""
    if not relations:
        return "no grouping had enough labelled points to test"
    spaces = sorted({r.space for r in relations})
    lines: list[str] = []
    for space in spaces:
        rows = [r for r in relations if r.space == space]
        rows.sort(
            key=lambda r: (
                math.isnan(r.knn), -(0.0 if math.isnan(r.knn) else r.knn - r.knn_null), r.grouping
            )
        )
        lines.append(f"  in {space}:")
        lines.append(
            f"    {'grouping':22} {'groups':>6} {'cover':>6} {'kNN':>6} "
            f"{'chance':>7} {'lift':>6} {'sil':>6} {'p':>6}  verdict"
        )
        for r in rows:
            sil = "   n/a" if math.isnan(r.silhouette) else f"{r.silhouette:6.3f}"
            if math.isnan(r.knn):
                lines.append(
                    f"    {r.grouping:22} {r.groups:6d} {r.coverage:6.0%} "
                    f"{'—':>6} {'—':>7} {'—':>6} {sil} {'—':>6}  {r.verdict}"
                )
                continue
            lines.append(
                f"    {r.grouping:22} {r.groups:6d} {r.coverage:6.0%} {r.knn:6.3f} "
                f"{r.knn_null:7.3f} {r.knn - r.knn_null:+6.3f} {sil} {r.knn_p:6.3f}  {r.verdict}"
            )
    return "\n".join(lines)


def summarise(relations: Sequence[Relation]) -> dict[str, Any]:
    """The manifest form, plus the one sentence that reading the table is supposed to give.

    The headline is not the best grouping, it is whether the best grouping beats the
    recording-condition controls. That is the difference between "this corpus has structure
    about birds" and "this corpus has structure about equipment".
    """
    controls = {"source", "sampleRate", "recordist", "automatic", "backgroundSpecies"}
    real = [r for r in relations if r.grouping not in controls]
    control = [r for r in relations if r.grouping in controls]

    def best(rows: Sequence[Relation]) -> Relation | None:
        usable = [
            r for r in rows
            if r.verdict not in ("none", "negligible")
            and not r.verdict.startswith("untestable")
            and not math.isnan(r.knn)
        ]
        return max(usable, key=lambda r: r.knn - r.knn_null) if usable else None

    top = best(real)
    worst_control = best(control)
    verdict = "no grouping tested beat its own permutation"
    if top and worst_control:
        if (top.knn - top.knn_null) > (worst_control.knn - worst_control.knn_null):
            verdict = (
                f"{top.grouping} is the strongest relation and it beats the strongest "
                f"recording-condition control ({worst_control.grouping})"
            )
        else:
            verdict = (
                f"{worst_control.grouping} — a recording condition, not a bird — is the "
                f"strongest relation in this space; every other result is suspect until "
                f"the representation is invariant to it"
            )
    elif top:
        verdict = f"{top.grouping} is the strongest relation; no control was testable"
    return {
        "definition": (
            "per grouping: share of a point's 10 nearest neighbours sharing its label, "
            "against the same statistic over 199 label permutations. Groups under "
            f"{MIN_GROUP} points and unlabelled points are excluded; coverage says how "
            "much of the corpus was testable."
        ),
        "knnK": KNN_K,
        "permutations": PERMUTATIONS,
        "headline": verdict,
        "relations": [r.to_dict() for r in relations],
    }
