"""P2 of docs/18 — a song-level space, hand-written kernel first.

docs/18 §P2 states the rule: whole bouts as points — syllable-type tokens plus
the measured gaps — and a parameter-free sequence kernel *before* any learned
encoder, "so the learned one has something to beat". This module is that
baseline. It builds one point per bout (the same bouts the shipped grammar and
the P1 bake-off are defined over: order within a recording, a gap over
`GAP_BOUT_SECONDS` breaks a bout, bouts shorter than `MIN_BOUT_TOKENS` drop
out), places the bouts in a space defined by a pairwise sequence kernel, and
grades the space with geometry.py's kNN-lift + permutation-null battery — the
same statistic, the same blocking discipline, the same null, no new numbers
invented for the occasion.

**The kernel.** Two bouts are compared by a weighted edit distance over their
(species-qualified) type-token strings: substitution and indel cost 1, and a
*match* costs `RHYTHM_WEIGHT` times the absolute log-gap difference at the
aligned positions — so the rhythm term is aligned by the edit path because it
prices the path (a match the rhythm cannot afford is worse than two indels,
and the DP then prefers the indels; the cost model degrades gracefully instead
of needing a cap). The sum is normalised by the longer string, the same
normalisation `learn.cluster_song_types` measured its radius gate against. Two
token-level choices, both deliberate:

- **Tokens are species-qualified** (`strix_aluco/L04`), never bare type ids —
  `L04` names a different sound for every bird, and pooling bare ids would
  alias twenty species' alphabets into one (the artifact
  `learn.cluster_song_types` documents). The price is honest and stated:
  cross-species distances saturate (disjoint alphabets → distance ~1), so the
  species lift below is a sanity floor, not the goal. A cross-species song
  space needs a shared sound-class alphabet (critic embeddings), which is a
  later stage, not this one.
- **Substitution costs 1 for every token pair.** Types are nominal here;
  acoustic similarity between a species' types is deliberately *not* imported
  from the syllable space, because that space carries the recorder confound
  (docs/14 §14.4) this space is required to be invariant to.

The runs are *not* collapsed (docs/12's song typing collapses them): a trill's
repeat count is syntax, not noise — Jin & Kozhevnikov 2011 is the load-bearing
citation of the P1 bake-off — and the rhythm term is what prices tempo here,
which is the job the collapse did for docs/12's rhythm-free distance. The
first token's `gap_before` is excluded from the rhythm cost: it is the bout
boundary itself (> 1 s by construction), not rhythm.

**Pre-registered verdict** (stated before any number was seen): the kernel
baseline *holds* on a store iff

1. species kNN lift in the kernel space **beats** species kNN lift in the
   bag-of-types cosine space over the same bouts (baseline a — word order
   must be earning its keep, or the kernel is an expensive histogram);
2. recordist kNN lift in the kernel space stays **< 0.05** — a song space
   that clusters microphones is the Stage-1 failure one level up (docs/18's
   own words), and geometry.py's recording-blocked kNN is exactly the test
   that caught it at the syllable level.

Baseline (b) — docs/12's song typing — is judged differently because it is
not a space: it defines no cross-species geometry to score species lift in.
The honest comparison is recovery: songType kNN lift in the kernel space vs
in the bag space says whether the continuous kernel space contains the
discrete types `learn.cluster_song_types` found, and whether it contains them
*better* than the histogram does. Reported alongside, not folded into the
pass/fail. The individual/dialect question — the thing the space is FOR — is
reported per deep species: within one species, unblocked kNN lift by
*recording* (blocked it would be bookkeeping-zero; the question is precisely
whether same-recording bouts sit together). Read that number under the
recordist caveat: within a species, recording identity and recording
conditions are entangled, and a lift there is a lead, not a claim.

**From distances to geometry.py.** The battery wants coordinates, the kernel
gives a distance matrix, so the space enters as a classical-MDS embedding
(top eigenpairs of the double-centred squared-distance matrix, enough for
MDS_VARIANCE of the positive spectrum, capped at MDS_MAX_RANK). The
approximation is measured, not assumed: the report carries the kept spectral
share and the negative-eigenvalue mass (the non-Euclidean residual the
truncation dropped). The weight=0 ablation — pure normalised edit distance,
docs/12's metric with rhythm off — is run beside it so the rhythm term's
contribution is a number, not a hope.

Nothing here ships to the app: this is the measurement baseline the learned
encoder of a later stage must beat, judged on the debug stores.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from . import geometry, harvest, learn, syntax


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


#: The bout rule and the minimum length are the shipped grammar's, imported so
#: this space is defined over exactly the strings P1 scored.
GAP_BOUT_SECONDS = syntax.GAP_BOUT_SECONDS
MIN_BOUT_TOKENS = syntax.MIN_BOUT_TOKENS
#: Price of one nat of log-gap difference at a matched position. Hand-set,
#: pre-registered: within-song-type rendition jitter on measured gaps runs a
#: few tenths of a nat, so a true match stays cheap (< a substitution); a
#: full nat of rhythm mismatch costs one edit, and anything wilder is priced
#: above two indels, which the DP then prefers — the alignment gives up on the
#: match instead of paying an unbounded rhythm bill. The weight=0 ablation
#: isolates whatever this term earns.
RHYTHM_WEIGHT = 1.0
#: Gaps are logged; a zero gap (syllables touch) would be -inf. 5 ms is below
#: anything the segmenter resolves, so the floor binds only true zeros.
GAP_FLOOR_SECONDS = 0.005
#: Classical-MDS rank: smallest rank keeping this share of the positive
#: spectrum, capped. The cap exists because kNN geometry lives in the top
#: eigen-directions anyway; the kept share is reported so the truncation is
#: measured.
MDS_VARIANCE = 0.95
MDS_MAX_RANK = 128
#: The pre-registered invariance gate: recordist lift above this fails the
#: space, whatever the species number says. geometry.py's own verdict bands
#: call < 0.02 "negligible"; 0.05 is the task's gate, stated as given.
RECORDIST_MAX_LIFT = 0.05
#: The individual question, per species: at least this many recordings with at
#: least INDIV_MIN_BOUTS bouts each, and at least INDIV_MIN_LABELLED bouts in
#: play. Looser than geometry.py's corpus-level gates (8/200) on purpose —
#: within one species those would leave three testable species on the debug
#: store, and the permutation null, not the gate, is what keeps a small test
#: honest. The loosened gates are passed explicitly to `geometry.measure`;
#: the statistic is untouched.
INDIV_MIN_RECORDINGS = 10
INDIV_MIN_BOUTS = 4
INDIV_MIN_LABELLED = 60
#: Pair-chunk budget for the vectorised DP: pairs_per_chunk x (padded length +
#: 1) cells. ~4M cells keeps the two live DP rows around 64 MB of float64.
DP_CHUNK_CELLS = 4_000_000


# --- bouts ---------------------------------------------------------------------


@dataclass
class Bout:
    """One bout: a type-token string with each token's measured `gap_before`."""

    species_id: str
    recording_id: str
    first_order: int
    types: list[str] = field(default_factory=list)
    gaps: list[float] = field(default_factory=list)


def bouts_with_gaps(
    observations: Sequence[learn.SyllableObservation],
    typing: Sequence[dict[str, Any]],
) -> list[Bout]:
    """`learn.bout_sequences`, with each token's `gap_before` kept alongside.

    Same observations, same typing, same two rules (order meaningful within a
    recording only; a gap over `GAP_BOUT_SECONDS` breaks the bout; untyped
    observations skipped without breaking it) — reimplemented rather than
    wrapped because the wrapped version discards the gaps this space exists to
    use. `self_test` pins the token strings to `learn.bout_sequences`'s on a
    synthetic recording, so a drift in the upstream rule fails loudly here
    instead of silently redefining the space.
    """
    type_of = {
        (e["speciesId"], e["recordingId"], int(e["order"])): str(e["typeId"])
        for e in typing
    }
    by_recording: dict[tuple[str, str], list[learn.SyllableObservation]] = {}
    for o in observations:
        by_recording.setdefault((o.species_id, o.recording_id), []).append(o)
    out: list[Bout] = []
    for (species_id, recording_id), items in by_recording.items():
        items.sort(key=lambda o: o.order)
        bout = Bout(species_id, recording_id, 0)
        for o in items:
            if o.gap_before > GAP_BOUT_SECONDS and bout.types:
                out.append(bout)
                bout = Bout(species_id, recording_id, 0)
            tid = type_of.get((o.species_id, o.recording_id, o.order))
            if tid is not None:
                if not bout.types:
                    bout.first_order = o.order
                bout.types.append(tid)
                bout.gaps.append(float(o.gap_before))
        if bout.types:
            out.append(bout)
    return [b for b in out if len(b.types) >= MIN_BOUT_TOKENS]


def load_song_types(store_root: Any) -> dict[tuple[str, str, int], str]:
    """song-typing.json as `(species, recording, first_order) -> songTypeId`."""
    path = store_root / learn.SONG_TYPING_NAME
    if not path.exists():
        return {}
    entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    return {
        (e["speciesId"], e["recordingId"], int(e["firstOrder"])): str(e["songTypeId"])
        for e in entries
    }


# --- the kernel ------------------------------------------------------------------


def _encode(
    bouts: Sequence[Bout],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Bouts as padded integer arrays: tokens, lengths, log-gaps, vocab size.

    Tokens are species-qualified (`species/typeId`) and mapped to ints over the
    pooled sorted vocabulary — the same vocabulary the bag-of-types baseline
    counts over, so the two spaces differ in structure, not in alphabet.
    Padding token -1 never occurs in a bout; padding cells sit beyond a pair's
    lengths and never feed its DP answer cell, so they may compare however
    they like.
    """
    vocab = sorted({f"{b.species_id}/{t}" for b in bouts for t in b.types})
    index = {t: i for i, t in enumerate(vocab)}
    n = len(bouts)
    width = max(len(b.types) for b in bouts)
    tokens = np.full((n, width), -1, dtype=np.int32)
    loggaps = np.zeros((n, width), dtype=np.float64)
    lengths = np.zeros(n, dtype=np.int32)
    for i, b in enumerate(bouts):
        lengths[i] = len(b.types)
        tokens[i, : len(b.types)] = [index[f"{b.species_id}/{t}"] for t in b.types]
        loggaps[i, : len(b.gaps)] = np.log(np.maximum(b.gaps, GAP_FLOOR_SECONDS))
    return tokens, lengths, loggaps, len(vocab)


def _dp_block(
    a: np.ndarray,
    b: np.ndarray,
    la: np.ndarray,
    lb: np.ndarray,
    ga: np.ndarray,
    gb: np.ndarray,
    weight: float,
) -> np.ndarray:
    """Weighted edit distances for one pair chunk, batch-vectorised over pairs.

    Wagner–Fischer with substitution/indel cost 1 and match cost
    `weight * |log gap_i - log gap_j|` — the rhythm term is priced inside the
    DP, so the optimal path is the rhythm alignment (see the module docstring).
    The batch dimension is free in the recurrence, so all pairs in the chunk
    advance together: the inner loop runs padded-length squared vectorised
    steps instead of one Python DP per pair (on the 37-species debug store:
    7.0M pairs, ~0.7G cell-updates, which pure Python would not survive).
    First-position matches are free regardless of gaps: the bout-first token's
    `gap_before` is the bout boundary, not rhythm. The answer is read at each
    pair's own (la, lb) cell, so mixed lengths inside a chunk are exact.
    """
    p, width = a.shape
    prev = np.broadcast_to(np.arange(width + 1, dtype=np.float64), (p, width + 1)).copy()
    ans = np.zeros(p, dtype=np.float64)
    for i in range(1, width + 1):
        cur = np.empty((p, width + 1), dtype=np.float64)
        cur[:, 0] = i
        ai = a[:, i - 1]
        gi = ga[:, i - 1]
        for j in range(1, width + 1):
            if i == 1 or j == 1:
                sub = np.where(ai == b[:, j - 1], 0.0, 1.0)
            else:
                sub = np.where(
                    ai == b[:, j - 1], weight * np.abs(gi - gb[:, j - 1]), 1.0
                )
            cur[:, j] = np.minimum(
                np.minimum(prev[:, j] + 1.0, cur[:, j - 1] + 1.0), prev[:, j - 1] + sub
            )
        done = la == i
        if done.any():
            ans[done] = cur[done, lb[done]]
        prev = cur
    return ans


def pairwise_distance(
    tokens: np.ndarray,
    lengths: np.ndarray,
    loggaps: np.ndarray,
    weight: float = RHYTHM_WEIGHT,
) -> tuple[np.ndarray, dict[str, Any]]:
    """The full normalised NxN kernel distance matrix, plus the cost ledger.

    Pairs are processed longest-side-first in chunks padded to the chunk's own
    maximum length, sized to `DP_CHUNK_CELLS` — the DP for a pair only needs
    its own lengths, so sorting by length keeps the padding waste near zero
    instead of paying max_len squared for every pair.
    """
    n = len(lengths)
    ii, jj = np.triu_indices(n, k=1)
    side = np.maximum(lengths[ii], lengths[jj])
    total = int(lengths.astype(np.int64).sum())
    cells = (total * total - int((lengths.astype(np.int64) ** 2).sum())) // 2
    order = np.argsort(side, kind="stable")
    distances = np.zeros((n, n), dtype=np.float32)
    t0 = time.time()
    pos = 0
    while pos < len(order):
        # Growing the chunk costs one padded column per pair; stop when the
        # next pair would push pairs x padded-width past the cell budget.
        take = 1
        while pos + take < len(order) and (take + 1) * (
            int(side[order[pos + take]]) + 1
        ) <= DP_CHUNK_CELLS:
            take += 1
        sel = order[pos : pos + take]
        pos += take
        width = int(side[sel].max())
        p_ii, p_jj = ii[sel], jj[sel]
        d = _dp_block(
            tokens[p_ii, :width],
            tokens[p_jj, :width],
            lengths[p_ii],
            lengths[p_jj],
            loggaps[p_ii, :width],
            loggaps[p_jj, :width],
            weight,
        )
        d /= np.maximum(lengths[p_ii], lengths[p_jj])
        distances[p_ii, p_jj] = d
        distances[p_jj, p_ii] = d
    stats = {
        "bouts": n,
        "pairs": n * (n - 1) // 2,
        "cellUpdates": cells,
        "seconds": round(time.time() - t0, 2),
    }
    return distances, stats


def bag_of_types(
    tokens: np.ndarray, lengths: np.ndarray, vocab: int
) -> np.ndarray:
    """Baseline (a): raw type-count vectors over the same pooled vocabulary."""
    counts = np.zeros((len(lengths), vocab), dtype=np.float32)
    for i, n in enumerate(lengths):
        np.add.at(counts[i], tokens[i, :n], 1.0)
    return counts


def classical_mds(
    distances: np.ndarray,
    variance: float = MDS_VARIANCE,
    max_rank: int = MDS_MAX_RANK,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Coordinates for geometry.py from a distance matrix, with the receipt.

    Double-centre the squared distances, take the top eigenpairs up to
    `variance` of the positive spectrum (capped at `max_rank`). The normalised
    edit-plus-rhythm distance is not exactly Euclidean (the ratio
    normalisation breaks the triangle inequality at the edges), so the
    negative-eigenvalue mass is returned as the non-Euclidean residual the
    truncation dropped — a number to read next to the lifts, not to hide.
    """
    n = distances.shape[0]
    d2 = distances.astype(np.float64) ** 2
    centre = np.eye(n) - 1.0 / n
    gram = -0.5 * centre @ d2 @ centre
    values, vectors = np.linalg.eigh(gram)
    order = np.argsort(values)[::-1]
    positive = values[order] > 0
    total = float(values[order][positive].sum())
    cumulative = np.cumsum(np.where(positive, values[order], 0.0)) / max(total, 1e-12)
    rank = int(np.searchsorted(cumulative, variance) + 1)
    rank = min(rank, max_rank, n - 1, int(positive.sum()))
    keep = order[:rank]
    coords = vectors[:, keep] * np.sqrt(np.maximum(values[keep], 0.0))
    info = {
        "rank": rank,
        "keptShare": round(float(cumulative[rank - 1]), 4) if rank else 0.0,
        "negativeMass": round(float(-values[values < 0].sum() / max(total, 1e-12)), 4),
    }
    return coords.astype(np.float64), info


# --- the verdict battery ------------------------------------------------------------


def _relation_dict(found: geometry.Relation | None, grouping: str, space: str) -> dict[str, Any]:
    """A Relation as JSON, or the honest absence of one."""
    if found is None:
        return {"grouping": grouping, "space": space, "verdict": "untestable"}
    return found.to_dict()


def _lift(row: dict[str, Any]) -> float | None:
    """kNN lift of a measured relation; None when untested."""
    if row.get("knn") is None or row.get("knnNull") is None:
        return None
    return row["knn"] - row["knnNull"]


def evaluate(
    store: harvest.HarvestStore,
    rhythm_weight: float = RHYTHM_WEIGHT,
    seed: int = 0,
) -> dict[str, Any]:
    """Build the song space of one store and run the pre-registered battery.

    Three spaces over the same bouts: `kernel` (edit + rhythm), `kernelTokens`
    (the weight=0 ablation — docs/12's metric, scored for the species grouping
    only, so the rhythm term's contribution is visible), and `bag` (baseline
    a). Every grouping goes through `geometry.measure` with recordings as the
    block, except the two questions that are *about* same-recording pairs —
    recordist spans recordings so it stays blocked; the within-species
    individual test is unblocked by construction (see the module docstring).
    """
    typing = syntax.load_typing(store.root)
    if not typing:
        raise ValueError(f"{store.root} has no {learn.TYPING_NAME} — run `learn` first")
    t0 = time.time()
    bouts = bouts_with_gaps(store.syllables, typing)
    log(f"{len(bouts)} bouts of >= {MIN_BOUT_TOKENS} tokens over "
        f"{len({b.species_id for b in bouts})} species")
    tokens, lengths, loggaps, vocab = _encode(bouts)
    song_types = load_song_types(store.root)

    distances, cost = pairwise_distance(tokens, lengths, loggaps, weight=rhythm_weight)
    log(f"kernel: {cost['pairs']} pairs, ~{cost['cellUpdates'] / 1e6:.0f}M cell "
        f"updates in {cost['seconds']}s")
    coords, mds_info = classical_mds(distances)
    distances_tokens, cost_tokens = pairwise_distance(tokens, lengths, loggaps, 0.0)
    coords_tokens, mds_tokens_info = classical_mds(distances_tokens)
    log(f"ablation (rhythm off): {cost_tokens['seconds']}s; MDS rank "
        f"{mds_info['rank']} keeping {mds_info['keptShare']:.0%} of the positive "
        f"spectrum (non-Euclidean residual {mds_info['negativeMass']:.1%})")
    counts = bag_of_types(tokens, lengths, vocab)

    blocks = [b.recording_id for b in bouts]
    species = [b.species_id for b in bouts]
    recordist = [
        str(store.recordings.get(b.recording_id, {}).get("recordist", "") or "")
        for b in bouts
    ]
    song_type = [
        (
            f"{b.species_id}/{song_types[(b.species_id, b.recording_id, b.first_order)]}"
            if (b.species_id, b.recording_id, b.first_order) in song_types
            else ""
        )
        for b in bouts
    ]
    spaces = {
        "kernel": (coords, "euclidean"),
        "kernelTokens": (coords_tokens, "euclidean"),
        "bag": (counts, "cosine"),
    }
    relations: dict[str, dict[str, Any]] = {}
    for space_name, (x, metric) in spaces.items():
        groupings = {"species": species, "recordist": recordist, "songType": song_type}
        if space_name == "kernelTokens":
            groupings = {"species": species}  # the ablation answers one question
        for grouping, labels in groupings.items():
            found = geometry.measure(
                x, labels, grouping, space_name, metric, seed=seed, blocks=blocks
            )
            relations[f"{grouping}@{space_name}"] = _relation_dict(
                found, grouping, space_name
            )

    # The individual/dialect question, per deep species: within one species,
    # unblocked kNN lift by recording. Unblocked because blocked same-recording
    # pairs are exactly the pairs under test; the permutation null is what
    # keeps "recordings are internally consistent" from scoring by accident.
    individual: list[dict[str, Any]] = []
    by_species: dict[str, list[int]] = {}
    for i, b in enumerate(bouts):
        by_species.setdefault(b.species_id, []).append(i)
    for sp in sorted(by_species):
        idx = by_species[sp]
        rec_counts: dict[str, int] = {}
        for i in idx:
            rec_counts[bouts[i].recording_id] = rec_counts.get(
                bouts[i].recording_id, 0
            ) + 1
        deep = {r for r, n in rec_counts.items() if n >= INDIV_MIN_BOUTS}
        if len(deep) < INDIV_MIN_RECORDINGS:
            continue
        rec_labels = [bouts[i].recording_id for i in idx]
        row: dict[str, Any] = {
            "species": sp,
            "bouts": len(idx),
            "recordings": len(deep),
        }
        for space_name, (x, metric) in spaces.items():
            if space_name == "kernelTokens":
                continue
            found = geometry.measure(
                x[idx],
                rec_labels,
                "recording",
                space_name,
                metric,
                seed=seed,
                blocks=None,
                min_group=INDIV_MIN_BOUTS,
                min_labelled=INDIV_MIN_LABELLED,
            )
            row[space_name] = _relation_dict(found, "recording", space_name)
        individual.append(row)

    verdict = _verdict(relations)
    return {
        "params": {
            "rhythm_weight": rhythm_weight,
            "gap_bout_seconds": GAP_BOUT_SECONDS,
            "min_bout_tokens": MIN_BOUT_TOKENS,
            "mds_variance": MDS_VARIANCE,
            "mds_max_rank": MDS_MAX_RANK,
            "recordist_max_lift": RECORDIST_MAX_LIFT,
            "indiv_min_recordings": INDIV_MIN_RECORDINGS,
            "indiv_min_bouts": INDIV_MIN_BOUTS,
            "indiv_min_labelled": INDIV_MIN_LABELLED,
            "seed": seed,
        },
        "bouts": len(bouts),
        "species": len(by_species),
        "vocab": vocab,
        "cost": {"kernel": cost, "kernelTokens": cost_tokens},
        "mds": {"kernel": mds_info, "kernelTokens": mds_tokens_info},
        "relations": relations,
        "individual": individual,
        "verdict": verdict,
        "seconds": round(time.time() - t0, 2),
    }


def _verdict(relations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Apply the pre-registered rule of the module docstring to the lifts."""
    kernel_species = _lift(relations.get("species@kernel", {}))
    bag_species = _lift(relations.get("species@bag", {}))
    kernel_recordist = _lift(relations.get("recordist@kernel", {}))
    beats_bag = (
        kernel_species is not None
        and bag_species is not None
        and kernel_species > bag_species
    )
    recordist_ok = kernel_recordist is not None and kernel_recordist < RECORDIST_MAX_LIFT
    return {
        "rule": (
            "the kernel baseline holds iff species kNN lift in the kernel space "
            "beats bag-of-types over the same bouts AND recordist kNN lift stays "
            f"< {RECORDIST_MAX_LIFT}; the songType rows (baseline b, docs/12) are "
            "recovery evidence reported alongside, not part of the gate"
        ),
        "speciesLift": {"kernel": kernel_species, "bag": bag_species},
        "recordistLift": {"kernel": kernel_recordist},
        "kernelBeatsBag": beats_bag,
        "recordistNegligible": recordist_ok,
        "holds": beats_bag and recordist_ok,
    }


def format_report(report: dict[str, Any]) -> str:
    """The lift tables plus the verdict, as plain text for the terminal."""
    lines = [
        "P2 song-level space (docs/18) — the hand-written kernel baseline",
        f"params: {json.dumps(report['params'], sort_keys=True)}",
        f"bouts: {report['bouts']} over {report['species']} species, "
        f"vocab {report['vocab']} species-qualified types",
        f"kernel cost: {report['cost']['kernel']['pairs']} pairs, "
        f"~{report['cost']['kernel']['cellUpdates'] / 1e6:.0f}M cell updates in "
        f"{report['cost']['kernel']['seconds']}s "
        f"(+{report['cost']['kernelTokens']['seconds']}s ablation)",
        f"MDS: rank {report['mds']['kernel']['rank']} keeping "
        f"{report['mds']['kernel']['keptShare']:.0%} of the positive spectrum, "
        f"non-Euclidean residual {report['mds']['kernel']['negativeMass']:.1%}",
        "",
        "kNN lift by grouping (recordings blocked; lift = kNN - permutation null):",
        f"  {'grouping':10} {'space':13} {'groups':>6} {'cover':>6} {'kNN':>6} "
        f"{'chance':>7} {'lift':>7} {'p':>6}  verdict",
    ]
    for key in sorted(report["relations"]):
        r = report["relations"][key]
        lift = _lift(r)
        if r.get("knn") is None:
            lines.append(f"  {r['grouping']:10} {r['space']:13} {'—':>66} {r['verdict']}")
            continue
        lines.append(
            f"  {r['grouping']:10} {r['space']:13} {r['groups']:6d} "
            f"{r['coverage']:6.0%} {r['knn']:6.3f} {r['knnNull']:7.3f} "
            f"{lift:+7.3f} {r['knnP']:6.3f}  {r['verdict']}"
        )
    lines += ["", "within-species structure by recording (unblocked — the "
              "dialect/individual question; read under the recordist caveat):",
              f"  {'species':28} {'bouts':>5} {'recs':>4} {'kernel lift':>11} "
              f"{'bag lift':>8}  verdict (kernel)"]
    for row in sorted(
        report["individual"],
        key=lambda r: -(_lift(r.get("kernel", {})) or 0.0),
    ):
        k_lift = _lift(row.get("kernel", {}))
        b_lift = _lift(row.get("bag", {}))
        k = row.get("kernel", {})
        lines.append(
            f"  {row['species']:28} {row['bouts']:5d} {row['recordings']:4d} "
            f"{(f'{k_lift:+11.3f}' if k_lift is not None else '         —')} "
            f"{(f'{b_lift:+8.3f}' if b_lift is not None else '       —')}  "
            f"{k.get('verdict', 'untestable')}"
        )
    v = report["verdict"]
    ks, bs = v["speciesLift"]["kernel"], v["speciesLift"]["bag"]
    lines += [
        "",
        f"verdict rule: {v['rule']}",
        f"  species lift: kernel {ks:+.3f} vs bag {bs:+.3f} -> "
        f"{'kernel wins' if v['kernelBeatsBag'] else 'kernel does NOT beat the histogram'}",
        f"  recordist lift: kernel {v['recordistLift']['kernel']:+.3f} "
        f"(gate < {report['params']['recordist_max_lift']}) -> "
        f"{'negligible' if v['recordistNegligible'] else 'FAILS the invariance gate'}",
        f"  -> the kernel baseline {'HOLDS' if v['holds'] else 'DOES NOT HOLD'}",
    ]
    return "\n".join(lines)


# --- self-test ---------------------------------------------------------------------


def _synthetic_observations() -> tuple[list[learn.SyllableObservation], list[dict[str, Any]]]:
    """One recording with an untyped syllable and a bout break, for the bout-rule pin."""
    obs: list[learn.SyllableObservation] = []
    typing: list[dict[str, Any]] = []
    gaps = [0.0, 0.3, 0.3, 1.5, 0.3, 0.3, 0.3]
    typed = [True, True, False, True, True, True, True]
    for order, (gap, is_typed) in enumerate(zip(gaps, typed)):
        obs.append(learn.SyllableObservation(
            species_id="pin_species", recording_id="PIN1", order=order,
            start=float(order), dur=0.2, level=-30.0, attack=0.01, hold=False,
            contour=[[0.0, 3000.0]], am=0.0, am_depth=0.0, vib_rate=0.0,
            vib_depth=0.0, harmonic=0.0, timbre="tonal", flatness=0.1,
            gap_before=gap,
        ))
        if is_typed:
            typing.append({
                "speciesId": "pin_species", "recordingId": "PIN1",
                "order": order, "typeId": f"L{order:02d}",
            })
    return obs, typing


def self_test(verbose: bool = True) -> None:
    """The kernel must see grammar the histogram cannot, and nothing else.

    The fixture's two "species" share one alphabet and identical unigram
    marginals — `spA` alternates A B A B …, `spB` sings paired blocks A A B B
    A A B B … — so bag-of-types is blind to the difference by construction and
    any species structure the battery reports comes from order alone. The
    checks are the pre-registration in miniature: kernel species lift > 0.2
    and clearly above the bag baseline's; recording lift near zero (bouts are
    iid within a species, so a recording signal would be the machinery
    hallucinating); rhythm priced where rhythm is the only difference; and
    the bout builder pinned to `learn.bout_sequences` on a synthetic
    recording.
    """
    rng = np.random.default_rng(0)

    # 0. The bout-rule pin: same bouts as `learn.bout_sequences`, gaps kept.
    obs, typing = _synthetic_observations()
    mine = bouts_with_gaps(obs, typing)
    theirs = [
        (sp, key, seq)
        for sp, key, seq in learn.bout_sequences(obs, typing)
        if len(seq) >= MIN_BOUT_TOKENS
    ]
    assert len(mine) == len(theirs) == 1, (len(mine), len(theirs))
    assert mine[0].types == theirs[0][2], (mine[0].types, theirs[0][2])
    assert mine[0].first_order == theirs[0][1][1]
    # The untyped syllable was skipped without breaking the bout; the 1.5 s
    # gap did break it; the short first bout (2 typed tokens) dropped out.
    assert mine[0].gaps[0] == 1.5 and len(mine[0].gaps) == len(mine[0].types)

    # 1. Rhythm is priced: identical strings, different tempo. With the weight
    #    on, same-tempo pairs must sit closer than cross-tempo ones; with it
    #    off, the distance is exactly zero (pure edit distance sees no
    #    difference) — the ablation is a controlled zero, measured anyway.
    def gap_bouts(scale: float, count: int) -> list[Bout]:
        return [
            Bout("tempo", f"{scale}:{k}", k, ["A", "B", "A", "B", "A"],
                 [1.5] + [0.3 * scale] * 4)
            for k in range(count)
        ]

    tb = gap_bouts(1.0, 3) + gap_bouts(2.5, 3)
    tt, tl, tg, _ = _encode(tb)
    d_rhythm, _ = pairwise_distance(tt, tl, tg, weight=RHYTHM_WEIGHT)
    d_plain, _ = pairwise_distance(tt, tl, tg, weight=0.0)
    within = d_rhythm[0, 1]
    across = d_rhythm[0, 3]
    assert across > within + 0.1, (within, across)
    assert float(d_plain.max()) == 0.0, "rhythm off must be blind to tempo"

    # 2. The grammar fixture: order separates, marginals cannot. All bouts
    #    carry one dummy species id so `_encode` keeps the alphabet *shared*
    #    (its species-qualification is a store necessity, not part of what is
    #    being tested); the group labels live beside the bouts.
    bouts: list[Bout] = []
    labels: list[str] = []
    for species, motif in (("spA", ["a", "b"]), ("spB", ["a", "a", "b", "b"])):
        for rec in range(12):
            for _ in range(10):
                n_tokens = int(rng.integers(8, 15))
                reps = (n_tokens + len(motif) - 1) // len(motif)
                seq = (motif * reps)[:n_tokens]
                bouts.append(Bout(
                    "fixture", f"{species}-r{rec:02d}", 0, seq,
                    [1.5] + [0.25 + 0.05 * float(rng.random())] * (n_tokens - 1),
                ))
                labels.append(species)
    tokens, lengths, loggaps, vocab = _encode(bouts)
    distances, _ = pairwise_distance(tokens, lengths, loggaps)
    coords, _ = classical_mds(distances)
    counts = bag_of_types(tokens, lengths, vocab)
    rec_labels = [b.recording_id for b in bouts]
    blocks = [b.recording_id for b in bouts]

    kernel = geometry.measure(
        coords, labels, "species", "kernel", "euclidean", blocks=blocks
    )
    bag = geometry.measure(counts, labels, "species", "bag", "cosine", blocks=blocks)
    assert kernel is not None and bag is not None
    kernel_lift = kernel.knn - kernel.knn_null
    bag_lift = bag.knn - bag.knn_null
    assert kernel_lift > 0.2, f"kernel must separate shared-alphabet grammars: {kernel_lift:+.3f}"
    assert kernel_lift > bag_lift, (
        f"order must beat marginals on an order-only fixture: "
        f"kernel {kernel_lift:+.3f} vs bag {bag_lift:+.3f}"
    )
    recording = geometry.measure(
        coords, rec_labels, "recording", "kernel", "euclidean", blocks=None
    )
    assert recording is not None
    rec_lift = recording.knn - recording.knn_null
    assert rec_lift < 0.05, (
        f"iid bouts must show no recording structure: {rec_lift:+.3f}"
    )

    if verbose:
        print(
            "songspace self-test ok: bout rule pinned to learn.bout_sequences, "
            f"rhythm priced ({within:.3f} within vs {across:.3f} across tempo), "
            f"kernel species lift {kernel_lift:+.3f} vs bag {bag_lift:+.3f} on an "
            f"order-only fixture, recording lift {rec_lift:+.3f}"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
