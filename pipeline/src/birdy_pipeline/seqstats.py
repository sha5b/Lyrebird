"""W2 of docs/23 — model-free sequence statistics over the shipped type inventory.

Every syntax result this project holds comes from fitting a model and comparing it with
another model. P1 kept first order (docs/18). P2's kernel lost to bag-of-types. The
rhythm term cost lift. All three answer "does this model beat that one". **None of them
asks whether the tokens are units at all**, and every song-level encoder on the roadmap
is built on the assumption that they are.

This module asks that question with three statistics that fit nothing. They are the
standard tools of quantitative linguistics and comparative animal-communication
research, and none of them has been run on this corpus.

**Menzerath-Altmann.** The longer a construct, the shorter its constituents. Reported
across human language, primate calls, whale and dolphin sequences and birdsong. Here the
construct is a bout and the constituent is a syllable, so the law predicts that a bout of
many syllables is built of *shorter* syllables. What makes it a test rather than a
description is that arbitrary clusters have no reason to obey it: if `learn_types` cut
the acoustic space into convenient pieces, bout length and syllable duration are
independent, and the fitted exponent sits at zero. The fit is the standard
`y = a * x^b` on log-log, and **b < 0 is the law**.

**Predictive information.** How much the past tells about the future, as a function of
how much past is taken. Estimated here as the conditional entropy of the next token given
the previous `k`, for k = 0, 1, 2, .... A first-order process flattens after k = 1: knowing
two tokens back tells nothing extra. Anything that keeps falling has structure the
transition table cannot hold. This is the question the P1 bake-off could not ask, because
a bake-off can only say which of two models fits better, never whether either is enough.

**Normalised compression distance.** Sequence similarity with no features and no
alphabet assumptions: how much shorter two strings compress together than apart. It is
the other classic baseline a learned song encoder must beat, and P2 left it out.

**The control is the gate.** Each statistic is computed on the real bouts and on
docs/12's permutation control — each species' tokens redealt, bout lengths and marginals
kept. Small-sample bias hits both sides equally, which is exactly why the control is the
reference rather than an absolute threshold. A statistic the shuffle reproduces says
nothing about birds, however pretty it looks.

Nothing here ships to the app. This is a measurement of the inventory, and its result is
a decision about the roadmap.
"""

from __future__ import annotations

import json
import math
import sys
import time
import zlib
from collections import Counter, defaultdict
from typing import Any, Sequence

import numpy as np

#: Longest history the conditional-entropy curve is taken to. Beyond four tokens the
#: contexts outnumber the bouts on any species this corpus holds, so the estimate is
#: measuring its own sample size. The control curve is reported beside it for exactly
#: that reason: both sides suffer the same bias, and only the gap between them is read.
MAX_ORDER = 4
#: Fewest bouts a species needs before its curve is estimated at all.
MIN_BOUTS = 30
#: Fewest syllables a bout needs to enter the Menzerath fit. Two is where "a construct
#: of constituents" starts to mean anything.
MIN_MENZERATH_TOKENS = 2
#: Bouts sampled per species for the NCD matrix, which is quadratic.
NCD_SAMPLE = 40


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- Menzerath-Altmann -------------------------------------------------------------


def menzerath(
    bouts: Sequence[tuple[str, list[str], list[float]]],
) -> dict[str, Any]:
    """Fit `mean constituent duration = a * (bout length)^b` per species, in logs.

    `bouts` is (species, token list, per-token duration list). The exponent `b` is the
    law: negative means longer bouts are built of shorter syllables. Species are fitted
    separately and never pooled, because bout length distributions and syllable
    inventories differ by species and a pooled fit would measure that instead.
    """
    by_species: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for species_id, tokens, durations in bouts:
        if len(tokens) < MIN_MENZERATH_TOKENS or not durations:
            continue
        mean_dur = float(np.mean(durations))
        if mean_dur <= 0:
            continue
        by_species[species_id].append((float(len(tokens)), mean_dur))

    exponents: list[float] = []
    per_species: list[dict[str, Any]] = []
    for species_id, points in sorted(by_species.items()):
        if len(points) < MIN_BOUTS:
            continue
        x = np.log(np.array([p[0] for p in points]))
        y = np.log(np.array([p[1] for p in points]))
        if float(x.std()) < 1e-9:
            continue  # every bout the same length: the law has nothing to bite on
        b, a = np.polyfit(x, y, 1)
        r = float(np.corrcoef(x, y)[0, 1])
        exponents.append(float(b))
        per_species.append({
            "species": species_id,
            "bouts": len(points),
            "exponent": round(float(b), 4),
            "r": round(r, 4),
        })
    exponents_array = np.array(exponents) if exponents else np.zeros(0)
    return {
        "speciesFitted": len(exponents),
        "medianExponent": round(float(np.median(exponents_array)), 4) if exponents else None,
        "shareNegative": (
            round(float((exponents_array < 0).mean()), 4) if exponents else None
        ),
        "perSpecies": sorted(per_species, key=lambda row: row["exponent"])[:20],
    }


# --- conditional entropy ------------------------------------------------------------


def _entropy(counts: Counter[Any]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return -sum(
        (n / total) * math.log2(n / total) for n in counts.values() if n > 0
    )


def conditional_entropies(
    sequences: Sequence[list[str]], max_order: int = MAX_ORDER
) -> list[float]:
    """H(next | previous k) in bits, for k = 0 .. max_order, over one species' bouts.

    Plug-in estimator. It is biased low, and increasingly so with k, which is the whole
    reason the control curve is computed with the same estimator on the same number of
    tokens: the bias cancels in the comparison and never in the absolute value.
    """
    out: list[float] = []
    for k in range(max_order + 1):
        joint: Counter[tuple[str, ...]] = Counter()
        context: Counter[tuple[str, ...]] = Counter()
        for seq in sequences:
            for i in range(k, len(seq)):
                ctx = tuple(seq[i - k : i])
                joint[(*ctx, seq[i])] += 1
                context[ctx] += 1
        if not joint:
            out.append(0.0)
            continue
        out.append(_entropy(joint) - (_entropy(context) if k else 0.0))
    return out


def entropy_curves(
    bouts: Sequence[tuple[str, list[str], list[float]]], max_order: int = MAX_ORDER
) -> dict[str, Any]:
    """The conditional-entropy curve per deep species, and the corpus median."""
    by_species: dict[str, list[list[str]]] = defaultdict(list)
    for species_id, tokens, _ in bouts:
        by_species[species_id].append(tokens)
    curves: list[list[float]] = []
    rows: list[dict[str, Any]] = []
    for species_id, seqs in sorted(by_species.items()):
        if len(seqs) < MIN_BOUTS:
            continue
        curve = conditional_entropies(seqs, max_order)
        curves.append(curve)
        rows.append({
            "species": species_id,
            "bouts": len(seqs),
            "curve": [round(v, 4) for v in curve],
            # What the second order buys over the first. A first-order process gives
            # roughly zero here; the estimator's own bias also gives a positive number,
            # which is why this is only ever read against the control's value.
            "drop1to2": round(curve[1] - curve[2], 4) if len(curve) > 2 else None,
        })
    median = (
        [round(float(v), 4) for v in np.median(np.array(curves), axis=0)]
        if curves
        else []
    )
    return {"speciesMeasured": len(curves), "medianCurve": median, "perSpecies": rows[:20]}


# --- normalised compression distance -------------------------------------------------


def _compressed(data: bytes) -> int:
    return len(zlib.compress(data, 9))


def ncd(a: bytes, b: bytes) -> float:
    """Normalised compression distance, Cilibrasi and Vitanyi's form."""
    ca, cb = _compressed(a), _compressed(b)
    cab = _compressed(a + b)
    lo, hi = min(ca, cb), max(ca, cb)
    return (cab - lo) / hi if hi else 0.0


def ncd_recovery(
    bouts: Sequence[tuple[str, list[str], list[float]]],
    song_types: dict[tuple[str, int], str] | None = None,
    sample: int = NCD_SAMPLE,
    seed: int = 0,
) -> dict[str, Any]:
    """Do same-species bouts sit closer under NCD than cross-species ones?

    The weakest possible question, asked on purpose: species is a grouping the corpus
    cannot get wrong, so it is the sanity floor for a distance that knows nothing about
    the alphabet. Tokens are encoded as bytes over the species' own alphabet, so the
    comparison is about order and repetition rather than about which ids happen to sort
    together.
    """
    rng = np.random.default_rng(seed)
    by_species: dict[str, list[bytes]] = defaultdict(list)
    for species_id, tokens, _ in bouts:
        alphabet = {t: i for i, t in enumerate(sorted(set(tokens)))}
        by_species[species_id].append(
            bytes(32 + (alphabet[t] % 90) for t in tokens)
        )
    deep = [sp for sp, seqs in by_species.items() if len(seqs) >= sample]
    if len(deep) < 2:
        return {"species": len(deep), "verdict": "untestable"}
    picked = [str(sp) for sp in rng.permutation(np.asarray(deep, dtype=object))[:12]]
    within: list[float] = []
    across: list[float] = []
    for i, sp in enumerate(picked):
        seqs = by_species[sp][:sample]
        for a in range(0, len(seqs), 4):
            for b in range(a + 1, min(a + 5, len(seqs))):
                within.append(ncd(seqs[a], seqs[b]))
        other = by_species[picked[(i + 1) % len(picked)]][:sample]
        for a in range(0, min(len(seqs), len(other)), 4):
            across.append(ncd(seqs[a], other[a]))
    return {
        "species": len(picked),
        "withinMedian": round(float(np.median(within)), 4) if within else None,
        "acrossMedian": round(float(np.median(across)), 4) if across else None,
        "separation": (
            round(float(np.median(across) - np.median(within)), 4)
            if within and across
            else None
        ),
        "pairs": len(within) + len(across),
    }


# --- the control ---------------------------------------------------------------------


def shuffled(
    bouts: Sequence[tuple[str, list[str], list[float]]], seed: int = 0
) -> list[tuple[str, list[str], list[float]]]:
    """docs/12's control: each species' tokens redealt, lengths and marginals kept.

    Durations travel with their token, so the Menzerath control asks the sharpest
    version of its question — the syllables are the same syllables, only their order and
    their grouping into bouts have been destroyed.
    """
    rng = np.random.default_rng(seed)
    pools: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for species_id, tokens, durations in bouts:
        for t, d in zip(tokens, durations):
            pools[species_id].append((t, d))
    dealt = {
        sp: [items[i] for i in rng.permutation(len(items))]
        for sp, items in pools.items()
    }
    position: dict[str, int] = defaultdict(int)
    out: list[tuple[str, list[str], list[float]]] = []
    for species_id, tokens, _ in bouts:
        i = position[species_id]
        chunk = dealt[species_id][i : i + len(tokens)]
        position[species_id] = i + len(tokens)
        out.append((species_id, [t for t, _ in chunk], [d for _, d in chunk]))
    return out


def evaluate(
    bouts: Sequence[tuple[str, list[str], list[float]]], seed: int = 0
) -> dict[str, Any]:
    """All three statistics on the real bouts and on the control, side by side."""
    t0 = time.time()
    control = shuffled(bouts, seed)
    report: dict[str, Any] = {
        "bouts": len(bouts),
        "species": len({sp for sp, _, _ in bouts}),
        "tokens": sum(len(t) for _, t, _ in bouts),
        "params": {
            "maxOrder": MAX_ORDER,
            "minBouts": MIN_BOUTS,
            "minMenzerathTokens": MIN_MENZERATH_TOKENS,
            "ncdSample": NCD_SAMPLE,
            "seed": seed,
        },
    }
    for name, data in (("real", bouts), ("control", control)):
        report[name] = {
            "menzerath": menzerath(data),
            "entropy": entropy_curves(data),
            "ncd": ncd_recovery(data, seed=seed),
        }
    report["seconds"] = round(time.time() - t0, 2)
    report["verdict"] = _verdict(report)
    return report


def _verdict(report: dict[str, Any]) -> dict[str, Any]:
    """The pre-registered rule: each statistic must separate real from control."""
    real, control = report["real"], report["control"]
    m_real = real["menzerath"]["medianExponent"]
    m_ctl = control["menzerath"]["medianExponent"]
    e_real = real["entropy"]["medianCurve"]
    e_ctl = control["entropy"]["medianCurve"]
    n_real = real["ncd"].get("separation")
    n_ctl = control["ncd"].get("separation")
    # The second order's contribution over the first, real against control.
    drop_real = (e_real[1] - e_real[2]) if len(e_real) > 2 else None
    drop_ctl = (e_ctl[1] - e_ctl[2]) if len(e_ctl) > 2 else None
    # **Where the plug-in estimator stops being readable, and it is not far.** Shuffled
    # tokens make every long context near-unique, so the estimator reports "the next
    # token is determined" and the control's curve collapses *below* the real one. On
    # the production corpus that happens at k = 3 (real 0.435, control 0.293). Past that
    # point neither curve measures structure, and comparing their drops is comparing two
    # different amounts of bias. The honest form of this question is the held-out
    # cross-entropy the docs/18 bake-off already used, which is unbiased by construction.
    collapsed_at = next(
        (k for k in range(1, min(len(e_real), len(e_ctl))) if e_ctl[k] < e_real[k]),
        None,
    )
    # And a second reason the drop comparison is not a test, which the production run
    # made obvious: the two curves start 2.4 bits apart (real 0.94, control 3.34), so
    # the control drops further from k=1 to k=2 for the trivial reason that it has more
    # entropy to lose. A drop-against-drop rule silently reads that as "the shuffle has
    # more structure". The comparison is only meaningful while the two curves are close
    # enough at k=1 for the same drop to mean the same thing.
    comparable = (
        len(e_real) > 1
        and len(e_ctl) > 1
        and abs(e_real[1] - e_ctl[1]) < 0.5
    )
    readable = (collapsed_at is None or collapsed_at > 2) and comparable
    return {
        "rule": (
            "each statistic must separate the real corpus from its own permutation "
            "control (tokens redealt within species, bout lengths and marginals kept); "
            "an absolute value the shuffle reproduces says nothing about birds"
        ),
        "menzerathExponent": {"real": m_real, "control": m_ctl},
        "menzerathHolds": bool(
            m_real is not None and m_ctl is not None and m_real < 0 and m_real < m_ctl - 0.02
        ),
        "firstOrderStructure": {
            "real": e_real[1] if len(e_real) > 1 else None,
            "control": e_ctl[1] if len(e_ctl) > 1 else None,
        },
        "secondOrderGain": {"real": drop_real, "control": drop_ctl},
        "controlCollapsesAt": collapsed_at,
        "beyondFirstOrder": (
            bool(drop_real is not None and drop_ctl is not None and drop_real > drop_ctl + 0.02)
            if readable
            else None
        ),
        "beyondFirstOrderNote": (
            None
            if readable
            else (
                "untestable with a plug-in estimator on this corpus. "
                + (
                    f"the control's curve falls below the real one at k={collapsed_at}, "
                    "so both are bias past that point. "
                    if collapsed_at is not None and collapsed_at <= 2
                    else ""
                )
                + (
                    f"the two curves start {abs(e_real[1] - e_ctl[1]):.2f} bits apart at "
                    "k=1, so the control drops further only because it has more to lose. "
                    if not comparable
                    else ""
                )
                + "Use the held-out cross-entropy of docs/18, which is unbiased."
            )
        ),
        "ncdSeparation": {"real": n_real, "control": n_ctl},
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "W2 model-free sequence statistics (docs/23 §23.2)",
        f"corpus: {report['bouts']} bouts, {report['tokens']} tokens, "
        f"{report['species']} species",
        f"params: {json.dumps(report['params'], sort_keys=True)}",
        "",
        f"  {'statistic':34} {'real':>12} {'control':>12}",
    ]
    real, control = report["real"], report["control"]
    lines.append(
        f"  {'Menzerath exponent (median)':34} "
        f"{str(real['menzerath']['medianExponent']):>12} "
        f"{str(control['menzerath']['medianExponent']):>12}"
    )
    lines.append(
        f"  {'  species with a negative one':34} "
        f"{str(real['menzerath']['shareNegative']):>12} "
        f"{str(control['menzerath']['shareNegative']):>12}"
    )
    lines.append(
        f"  {'  species fitted':34} "
        f"{real['menzerath']['speciesFitted']:>12} "
        f"{control['menzerath']['speciesFitted']:>12}"
    )
    lines.append(
        f"  {'NCD across - within':34} "
        f"{str(real['ncd'].get('separation')):>12} "
        f"{str(control['ncd'].get('separation')):>12}"
    )
    lines += ["", "conditional entropy H(next | previous k), bits, median over species:",
              f"  {'k':>3}  {'real':>8}  {'control':>8}"]
    for k, (a, b) in enumerate(
        zip(real["entropy"]["medianCurve"], control["entropy"]["medianCurve"])
    ):
        lines.append(f"  {k:>3}  {a:8.3f}  {b:8.3f}")
    v = report["verdict"]
    lines += [
        "",
        f"verdict rule: {v['rule']}",
        f"  Menzerath: real {v['menzerathExponent']['real']} vs control "
        f"{v['menzerathExponent']['control']} -> "
        f"{'HOLDS' if v['menzerathHolds'] else 'does NOT hold'}",
        f"  first order: real {v['firstOrderStructure']['real']} bits vs control "
        f"{v['firstOrderStructure']['control']} -> "
        f"{'strong sequence structure' if (v['firstOrderStructure']['real'] or 9) < (v['firstOrderStructure']['control'] or 0) - 0.5 else 'none'}",
        (
            f"  beyond first order: {v['beyondFirstOrderNote']}"
            if v["beyondFirstOrder"] is None
            else f"  beyond first order: real {v['secondOrderGain']['real']} vs control "
            f"{v['secondOrderGain']['control']} -> "
            f"{'structure' if v['beyondFirstOrder'] else 'nothing the transition table does not hold'}"
        ),
    ]
    return "\n".join(lines)


# --- self-test -------------------------------------------------------------------------


def self_test(verbose: bool = True) -> None:
    """Two fixtures with known answers, because a statistic that cannot fail is not one.

    The Menzerath fixture plants the law — longer bouts made of shorter syllables — and
    the control must destroy it, since the shuffle keeps every duration and only moves
    it. The entropy fixture plants a second-order dependency the transition table cannot
    hold, and the first-order fixture must show the curve flattening instead.
    """
    rng = np.random.default_rng(0)

    # 1. Menzerath, planted: duration falls as 1/sqrt(bout length).
    planted: list[tuple[str, list[str], list[float]]] = []
    for _ in range(200):
        n = int(rng.integers(2, 12))
        dur = 0.2 / math.sqrt(n)
        planted.append((
            "sp",
            [f"T{int(rng.integers(6)):02d}" for _ in range(n)],
            [dur * float(rng.uniform(0.95, 1.05)) for _ in range(n)],
        ))
    got = menzerath(planted)["medianExponent"]
    assert got is not None and -0.75 < got < -0.25, f"planted exponent not recovered: {got}"
    control_exponent = menzerath(shuffled(planted))["medianExponent"]
    assert control_exponent is not None and control_exponent > got + 0.1, (
        f"the shuffle must destroy the law: real {got}, control {control_exponent}"
    )

    # 2. A second-order process: the next token depends on the previous *two*, so the
    #    curve must keep falling past k = 1. Its own shuffle must not.
    # The rule is parity — the next token repeats when the last two agreed and flips
    # when they did not — so the last token alone leaves it genuinely ambiguous. (A map
    # that resolves on one token is a first-order process wearing two, which is what the
    # first version of this fixture was.) A tenth of the steps are flipped, so the
    # process has entropy to fall *from* rather than being a single cycle.
    second: list[list[str]] = []
    for _ in range(400):
        seq = ["A", "B"]
        for _ in range(20):
            nxt = "A" if seq[-2] == seq[-1] else "B"
            if rng.random() < 0.1:
                nxt = "B" if nxt == "A" else "A"
            seq.append(nxt)
        second.append(seq)
    curve = conditional_entropies(second)
    assert curve[1] - curve[2] > 0.15, f"second-order dependency missed: {curve}"

    # 3. A first-order process must flatten after k = 1.
    first: list[list[str]] = []
    for _ in range(400):
        seq = ["A"]
        for _ in range(20):
            seq.append("B" if seq[-1] == "A" else ("A" if rng.random() < 0.7 else "B"))
        first.append(seq)
    flat = conditional_entropies(first)
    assert flat[1] - flat[2] < 0.05, f"first-order fixture shows false depth: {flat}"

    # 4. NCD: a repeated motif compresses against itself, noise does not.
    motif = bytes(b"ABCABCABCABC")
    noise = bytes(int(c) for c in rng.integers(65, 90, size=12))
    assert ncd(motif, motif + motif) < ncd(motif, noise), "NCD ordering wrong"

    if verbose:
        print(
            f"seqstats self-test ok: Menzerath exponent {got:+.3f} recovered and "
            f"destroyed by its shuffle ({control_exponent:+.3f}), second-order drop "
            f"{curve[1] - curve[2]:.3f} against first-order {flat[1] - flat[2]:.3f}"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
