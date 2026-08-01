"""P1 of docs/18 — the pre-registered grammar model bake-off.

docs/18 states the problem: the shipped syntax is first-order only
(`learn.learn_grammar`), and the literature is unambiguous that birdsong is not
first-order — Jin & Kozhevnikov 2011 (arXiv:1011.2998) showed Bengalese finch
transitions depend on how many times the current syllable has already repeated,
and Lu et al. 2025 showed partially observable Markov models beat plain HMMs (and
therefore order-1 chains) on the same species. This module runs the bake-off
docs/18 pre-registers, on the bouts the shipped grammar already defines:

- **M1 first-order**: P(next | current) — the baseline everything must beat.
- **M2 repeat-count**: P(next | current, r), r = consecutive repeats of `current`
  so far, capped at 3+ — the minimal sufficient finch model of Jin & Kozhevnikov.
- **M3 hidden-state**: categorical-emission HMM by Baum–Welch, K chosen on an
  inner validation split — the small honest representative of the POMM family.

All three smooth the same way: add-ALPHA with backoff to the next lower order
(`P(next|ctx) = (c(ctx,next) + α·P_lower(next)) / (c(ctx) + α)`), ALPHA = 0.1.
α = 0.1 is small enough not to move well-observed contexts (a context with 50
observations shifts by < 0.2 %) and large enough that a one-off held-out
continuation costs ~log(1/α·V) rather than −inf — the same discipline
`learn.mine_chunks` applies with its pseudocount, at the transition level.

**Pre-registered verdict rule** (stated here before any number was seen): a
challenger *wins* only if its mean ΔLL/token over M1 exceeds +0.1 nats averaged
across qualifying species AND it beats M1 on the majority of those species. A
wash keeps first-order and is documented as such — a negative result is the
deliverable, not a problem (AGENTS.md's evidence discipline).

Nothing here ships a model: the shipped grammar in `learn.learn_grammar` is
untouched, and this module reads the store exactly as `learn` does — the same
observations, the same typing.json, the same bout rule — so the numbers are about
the strings the pipeline actually sings.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from typing import Any, Sequence

import numpy as np

from . import learn


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


#: The shipped bout rule: a `gap_before` over a second ends a bout rather than
#: making a (spurious) transition across a pause. Re-exported from `learn`, not
#: restated — this was a second literal 1.0 until 2026-08-01, and a bake-off run
#: against a different bout rule than the grammar's is a bake-off of nothing.
GAP_BOUT_SECONDS = learn.GAP_BOUT_SECONDS
#: A bout shorter than this carries no structure a sequence model can score —
#: two tokens are one transition, which is the unigram with extra steps.
MIN_BOUT_TOKENS = 3
#: Fewer bouts than this and an 80/20 split scores a model on a handful of
#: phrases — the species is reported as skipped, not as evidence.
MIN_BOUTS_PER_SPECIES = 20
#: Train share of the seeded per-species bout split.
TRAIN_FRACTION = 0.8
#: The split seed, fixed by the pre-registration so the numbers are reproducible.
SPLIT_SEED = 0
#: The add-α smoothing strength, with backoff to the next lower order (see the
#: module docstring for why 0.1).
ALPHA = 0.1
#: Repeat-count cap: r ∈ {1, 2, 3+}. Jin & Kozhevnikov's finch adaptation runs
#: over a handful of repeats; past three the count is "many" and the counts per
#: context get too thin to estimate anyway.
REPEAT_CAP = 3
#: A repeat-count context with fewer observations than this falls back to plain
#: first-order — a distribution estimated from four observations is prior noise,
#: the same small-count guard as `learn.CHUNK_PSEUDOCOUNT`.
REPEAT_MIN_OBS = 5
#: HMM state counts swept per species, chosen on an *inner* validation split of
#: the train bouts — the held-out test bouts never select K, or the reported ΔLL
#: would be partly selection.
HMM_KS = (4, 8, 16)
#: Baum–Welch cap. Fifty iterations is far past convergence for vocabularies of
#: a few dozen types; the tolerance below usually stops it by ~15.
HMM_MAX_ITER = 50
#: Relative log-likelihood gain below which EM is called converged.
HMM_TOL = 1e-5
#: Fixed HMM seed — the bake-off's numbers must be reproducible to be evidence.
HMM_SEED = 0
#: The pre-registered win bar: mean ΔLL/token over the baseline, in nats.
WIN_DELTA_NATS = 0.1
#: The pre-registered adoption gate for the continuation-count repair of
#: `FirstOrder` (see `smoothing_comparison`): it ships only if held-out LL on
#: unseen-*context* transitions — the only rows the repair touches — improves by
#: at least this much ...
REPAIR_MIN_UNSEEN_GAIN = 1.0
#: ... and held-out LL on seen transitions degrades by no more than this. (By
#: construction the seen rows are bit-identical, so the second half is a
#: controlled zero; it is stated and measured anyway, because a gate you do not
#: measure is a wish.)
REPAIR_MAX_SEEN_LOSS = 0.01

MODELS = ("m1", "m2", "m3")


class _Unstable(RuntimeError):
    """Baum–Welch produced a non-finite or degenerate model for this species."""


# --- bouts -------------------------------------------------------------------------


def species_bouts(
    observations: Sequence[learn.SyllableObservation],
    typing: Sequence[dict[str, Any]],
) -> dict[str, list[list[int]]]:
    """Per-species bouts of per-species integer token ids: `{species: [[t, ...], ...]}`.

    Rebuilt through `learn.bout_sequences`, so the bout definition is exactly the
    shipped grammar's — order within a recording, a gap over `GAP_BOUT_SECONDS`
    breaks a bout, untyped observations are skipped without breaking it. Type ids
    are remapped to 0..V-1 per species (sorted by id) because the HMM wants dense
    emission indices; the mapping is per species because no transition ever
    crosses species. Bouts shorter than `MIN_BOUT_TOKENS` are dropped.
    """
    out: dict[str, list[list[int]]] = defaultdict(list)
    vocab: dict[str, dict[str, int]] = {}
    for species_id, _key, seq in learn.bout_sequences(observations, typing):
        if len(seq) < MIN_BOUT_TOKENS:
            continue
        ids = vocab.setdefault(species_id, {})
        out[species_id].append([ids.setdefault(t, len(ids)) for t in seq])
    return dict(out)


def load_typing(store_root: Any) -> list[dict[str, Any]]:
    """The store's typing.json entries, or [] when learn has not run on this store."""
    path = store_root / learn.TYPING_NAME
    if not path.exists():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get("entries", []))


# --- smoothing ----------------------------------------------------------------------


def _backoff_row(counts: Counter[int], lower: np.ndarray, alpha: float) -> np.ndarray:
    """Add-α with backoff: `(c(ctx,·) + α·P_lower(·)) / (c(ctx) + α)`.

    `lower` is the next lower order's probability row (M2 backs off to M1's row,
    M1 to the unigram, the unigram to the uniform), so every context has a proper
    distribution and an unseen continuation costs a finite, documented price —
    a model backs off, never crashes.
    """
    row = alpha * lower
    for token, n in counts.items():
        row[token] += n
    return row / row.sum()


class FirstOrder:
    """M1: P(next | current), the shipped model of `learn.learn_grammar`, refit here

    under the bake-off's smoothing so the comparison is about structure, not about
    `GRAMMAR_MIN_COUNT` vs add-α. The bout-first token is scored under the unigram,
    so every model scores every token and per-token means are comparable.

    `backoff` selects the lower order an *unseen context* falls back to:

    - `"unigram"` (the default, and the baseline the bake-off was run with): the
      add-α-smoothed raw token frequencies.
    - `"continuation"`: the Kneser–Ney lower order (Kneser & Ney 1995) — P(next)
      proportional to the number of *distinct contexts* next was seen following,
      not its raw frequency. This is the smoothing repair the bake-off's own
      decomposition called for: on the debug store, held-out transitions whose
      context was unseen cost the unigram row −8.07 nats/token and the
      continuation row −6.17 (`smoothing_comparison`), because a token that
      follows *new* contexts is by construction one that already follows *many*
      contexts, and raw frequency cannot say that — the second element of a
      stereotyped pair has high unigram mass and almost no continuation count.

    Seen-context rows are built from the unigram lower order under *both*
    settings, bit-identically: the repair is scoped to the unseen-context
    predictive row and nothing else, so the seen-transition half of the
    comparison is a controlled zero, not a re-measurement.
    """

    name = "m1"

    def __init__(self, vocab: int, alpha: float = ALPHA, backoff: str = "unigram"):
        if backoff not in ("unigram", "continuation"):
            raise ValueError(f"unknown backoff {backoff!r}")
        self.vocab = vocab
        self.alpha = alpha
        self.backoff = backoff
        self.unigram = np.full(vocab, 1.0 / vocab)
        self.continuation = np.full(vocab, 1.0 / vocab)
        self.rows: dict[int, np.ndarray] = {}
        self.pair_counts: Counter[tuple[int, int]] = Counter()

    def fit(self, bouts: Sequence[Sequence[int]]) -> "FirstOrder":
        tokens: Counter[int] = Counter()
        contexts: dict[int, Counter[int]] = defaultdict(Counter)
        for seq in bouts:
            tokens.update(seq)
            for a, b in zip(seq, seq[1:]):
                contexts[a][b] += 1
                self.pair_counts[(a, b)] += 1
        lower = np.full(self.vocab, self.alpha / self.vocab)
        for token, n in tokens.items():
            lower[token] += n
        self.unigram = lower / lower.sum()
        self.rows = {
            a: _backoff_row(counts, self.unigram, self.alpha)
            for a, counts in contexts.items()
        }
        # The continuation counts: one per (context, token) pair ever observed,
        # credited to the token — N₁₊(·,b) in Kneser–Ney notation, smoothed to
        # the uniform with the same α so a token never seen *as a continuation*
        # (bout-initial only, or absent from train) keeps a finite floor.
        continuation: Counter[int] = Counter()
        for (_a, b), n in self.pair_counts.items():
            if n > 0:
                continuation[b] += 1
        lower = np.full(self.vocab, self.alpha / self.vocab)
        for token, n in continuation.items():
            lower[token] += n
        self.continuation = lower / lower.sum()
        return self

    def row(self, current: int) -> np.ndarray:
        """P(· | current); an unseen current backs off to the chosen lower order."""
        row = self.rows.get(current)
        if row is not None:
            return row
        return self.unigram if self.backoff == "unigram" else self.continuation

    def score(self, seq: Sequence[int]) -> tuple[float, int, int]:
        """(log-likelihood, tokens scored, unseen transitions) for one bout."""
        ll = math.log(self.unigram[seq[0]])
        unseen = 0
        for a, b in zip(seq, seq[1:]):
            ll += math.log(self.row(a)[b])
            unseen += self.pair_counts[(a, b)] == 0
        return ll, len(seq), unseen


class RepeatCount:
    """M2: P(next | current, r), r = consecutive repeats of `current` so far, capped.

    The Jin & Kozhevnikov 2011 mechanism: a finch that has sung `A` three times
    transitions differently from one that has sung it once, which an order-1 chain
    cannot express — `current` is the same in both cases. r counts the run the
    *current* token closes (`A A A` scores the third A with context (A, r=2) and
    whatever follows with (A, r=3+)). A context with fewer than `REPEAT_MIN_OBS`
    observations falls back to the M1 row; better-observed ones smooth toward it.
    """

    name = "m2"

    def __init__(self, vocab: int, alpha: float = ALPHA):
        self.vocab = vocab
        self.alpha = alpha
        self.m1 = FirstOrder(vocab, alpha)
        self.rows: dict[tuple[int, int], np.ndarray] = {}
        self.triple_counts: Counter[tuple[int, int, int]] = Counter()

    @staticmethod
    def _runs(seq: Sequence[int]) -> list[int]:
        """Run length each token closes, capped: `A A B A A A A` → `1 2 1 1 2 3 3`."""
        out: list[int] = []
        for token in seq:
            if out and seq[len(out) - 1] == token:
                out.append(min(out[-1] + 1, REPEAT_CAP))
            else:
                out.append(1)
        return out

    def fit(self, bouts: Sequence[Sequence[int]]) -> "RepeatCount":
        self.m1.fit(bouts)
        contexts: dict[tuple[int, int], Counter[int]] = defaultdict(Counter)
        for seq in bouts:
            runs = self._runs(seq)
            for i in range(1, len(seq)):
                ctx = (seq[i - 1], runs[i - 1])
                contexts[ctx][seq[i]] += 1
                self.triple_counts[(*ctx, seq[i])] += 1
        self.rows = {
            ctx: _backoff_row(counts, self.m1.row(ctx[0]), self.alpha)
            for ctx, counts in contexts.items()
            if sum(counts.values()) >= REPEAT_MIN_OBS
        }
        return self

    def score(self, seq: Sequence[int]) -> tuple[float, int, int]:
        ll, _, _ = self.m1.score(seq[:1])
        runs = self._runs(seq)
        unseen = 0
        for i in range(1, len(seq)):
            ctx = (seq[i - 1], runs[i - 1])
            row = self.rows.get(ctx)
            if row is None:
                row = self.m1.row(ctx[0])
            ll += math.log(row[seq[i]])
            unseen += self.triple_counts[(*ctx, seq[i])] == 0
        return ll, len(seq), unseen


# --- M3: categorical HMM by Baum–Welch -----------------------------------------------


def _forward(
    pi: np.ndarray, A: np.ndarray, B: np.ndarray, seq: Sequence[int]
) -> tuple[float, np.ndarray, np.ndarray] | None:
    """Scaled forward pass: (log P(seq), normalised alphas, scaling norms).

    None when the sequence has probability exactly zero — with add-α emissions
    that means the transition matrix itself went degenerate, which is EM's
    failure, not the datum's.
    """
    T = len(seq)
    K = pi.size
    alpha = np.empty((T, K))
    norms = np.empty(T)
    a = pi * B[:, seq[0]]
    for t in range(T):
        if t:
            a = (alpha[t - 1] @ A) * B[:, seq[t]]
        s = float(a.sum())
        if not np.isfinite(s) or s <= 0.0:
            return None
        alpha[t] = a / s
        norms[t] = s
    return float(np.log(norms).sum()), alpha, norms


def _hmm_fit(
    seqs: Sequence[Sequence[int]],
    vocab: int,
    k: int,
    alpha: float,
    seed: int,
    max_iter: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """One Baum–Welch fit: (pi, A, B, final train log-likelihood).

    Init from token-frequency quantiles: the types ranked by frequency are dealt
    round-robin into the K states (most frequent V/K to state 0, and so on), so
    the states start as differently-shaped emission distributions rather than K
    copies of the same near-uniform, which converges to K copies of the mean.
    Transitions start jittered near-uniform. Raises `_Unstable` on any non-finite
    step or zero-probability sequence — the bake-off's rule is to log that species
    and report M1/M2 for it, never to silently ship a broken number.
    """
    rng = np.random.default_rng([HMM_SEED, seed, k])
    freq = np.bincount([t for seq in seqs for t in seq], minlength=vocab)
    ranked = np.argsort(-freq, kind="stable")
    assign = np.zeros(vocab, dtype=int)
    assign[ranked] = np.arange(vocab) * k // vocab
    B = np.full((k, vocab), alpha)
    B[assign, np.arange(vocab)] += 1.0
    B /= B.sum(axis=1, keepdims=True)
    A = rng.random((k, k)) + 0.5
    A /= A.sum(axis=1, keepdims=True)
    pi = rng.random(k) + 0.5
    pi /= pi.sum()

    previous = -math.inf
    for _iteration in range(max_iter):
        pi_num = np.full(k, alpha)
        a_num = np.full((k, k), alpha)
        b_num = np.full((k, vocab), alpha)
        gamma_mass = np.zeros(k)
        ll = 0.0
        for seq in seqs:
            fwd = _forward(pi, A, B, seq)
            if fwd is None:
                raise _Unstable(f"a training bout has probability zero (K={k})")
            f_ll, alpha_t, norms = fwd
            ll += f_ll
            T = len(seq)
            beta = np.ones(k)
            gammas = np.empty((T, k))
            gammas[T - 1] = alpha_t[T - 1]
            for t in range(T - 2, -1, -1):
                # xi needs beta of t+1; compute it before beta is stepped down to t.
                xi = alpha_t[t][:, None] * A * (B[:, seq[t + 1]] * beta)[None, :]
                xi_sum = xi.sum()
                if xi_sum > 0.0 and np.isfinite(xi_sum):
                    a_num += xi / xi_sum
                beta = (A @ (B[:, seq[t + 1]] * beta)) / norms[t + 1]
                g = alpha_t[t] * beta
                g_sum = g.sum()
                if not np.isfinite(g_sum) or g_sum <= 0.0:
                    raise _Unstable(f"non-finite posterior mass (K={k})")
                gammas[t] = g / g_sum
            gamma_mass += gammas.sum(axis=0)
            pi_num += gammas[0]
            for t in range(T):
                b_num[:, seq[t]] += gammas[t]
        if not np.isfinite(ll):
            raise _Unstable(f"non-finite log-likelihood (K={k})")
        pi = pi_num / pi_num.sum()
        # A state nobody occupied keeps its old rows — renormalising a zero row
        # would turn "no evidence" into NaN, and the state is dead anyway.
        occupied = gamma_mass > 1e-10
        A_new = a_num / a_num.sum(axis=1, keepdims=True)
        B_new = b_num / b_num.sum(axis=1, keepdims=True)
        A = np.where(occupied[:, None], A_new, A)
        B = np.where(occupied[:, None], B_new, B)
        # The M-step is add-α smoothed (MAP, not exact ML), so a wobble below
        # this tolerance is numerical jitter, not instability — only a real
        # regression indicts the fit.
        if previous > -math.inf and ll < previous - 1e-4 * max(1.0, abs(previous)):
            raise _Unstable(
                f"EM log-likelihood decreased {previous:.4f} -> {ll:.4f} (K={k})"
            )
        if abs(ll - previous) <= HMM_TOL * max(1.0, abs(ll)):
            previous = ll
            break
        previous = ll
    if not np.all(np.isfinite(A)) or not np.all(np.isfinite(B)):
        raise _Unstable(f"degenerate parameters after EM (K={k})")
    return pi, A, B, previous


class HiddenState:
    """M3: a categorical-emission HMM, the small honest POMM representative.

    Scored by the forward algorithm, so a held-out bout's likelihood integrates
    over the hidden path — an unseen emission is impossible by construction (add-α
    rows), and the "unseen" count is held-out tokens whose type never occurred in
    training, which is the closest analogue of M1/M2's unseen transitions.
    """

    name = "m3"

    def __init__(self, vocab: int, pi: np.ndarray, A: np.ndarray, B: np.ndarray):
        self.vocab = vocab
        self.pi, self.A, self.B = pi, A, B
        self.k = pi.size

    def score(self, seq: Sequence[int]) -> tuple[float, int, int]:
        fwd = _forward(self.pi, self.A, self.B, seq)
        if fwd is None:
            raise _Unstable("a held-out bout has probability zero")
        return fwd[0], len(seq), 0


def fit_hmm(
    train: Sequence[Sequence[int]],
    vocab: int,
    ks: Sequence[int] = HMM_KS,
    alpha: float = ALPHA,
    max_iter: int = HMM_MAX_ITER,
) -> tuple[HiddenState | None, int | None, str]:
    """Fit M3 with K chosen on an inner 80/20 split of the train bouts.

    The test bouts never see the K sweep — choosing K on the set the verdict is
    scored on would inflate ΔLL by selection. The winner is refit on all train
    bouts. Returns (model, k, note); a species whose every K fails EM gets
    (None, None, reason) and the bake-off reports M1/M2 for it, per the
    pre-registered instability rule.
    """
    rng = np.random.default_rng([HMM_SEED, len(train), vocab])
    perm = rng.permutation(len(train))
    n_inner = max(1, int(len(train) * TRAIN_FRACTION))
    inner_train = [train[i] for i in perm[:n_inner]]
    inner_val = [train[i] for i in perm[n_inner:]] or inner_train
    best: tuple[float, int, tuple[np.ndarray, np.ndarray, np.ndarray]] | None = None
    failures: list[str] = []
    for k in ks:
        if k >= vocab * 2:
            failures.append(f"K={k} skipped: {vocab} types cannot fill {k} states")
            continue
        try:
            pi, A, B, _ll = _hmm_fit(inner_train, vocab, k, alpha, seed=11, max_iter=max_iter)
            val = 0.0
            for seq in inner_val:
                fwd = _forward(pi, A, B, seq)
                if fwd is None:
                    raise _Unstable("an inner-validation bout has probability zero")
                val += fwd[0]
        except _Unstable as exc:
            failures.append(f"K={k}: {exc}")
            continue
        if best is None or val > best[0]:
            best = (val, k, (pi, A, B))
    if best is None:
        return None, None, "; ".join(failures) or "no K fittable"
    _val, k, _params = best
    try:
        pi, A, B, _ll = _hmm_fit(train, vocab, k, alpha, seed=23, max_iter=max_iter)
    except _Unstable as exc:
        note = f"K={k} refit on full train failed: {exc}"
        if failures:
            note += "; " + "; ".join(failures)
        return None, None, note
    note = "; ".join(failures)
    return HiddenState(vocab, pi, A, B), k, note


# --- evaluation ----------------------------------------------------------------------


def _split(
    bouts: Sequence[Sequence[int]], seed: int
) -> tuple[list[Sequence[int]], list[Sequence[int]]]:
    """Seeded 80/20 bout split — bouts, never tokens, so no phrase straddles the line."""
    rng = np.random.default_rng([SPLIT_SEED, seed])
    perm = rng.permutation(len(bouts))
    n_train = max(1, int(len(bouts) * TRAIN_FRACTION))
    n_train = min(n_train, len(bouts) - 1)
    return ([bouts[i] for i in perm[:n_train]], [bouts[i] for i in perm[n_train:]])


def bake_off(
    bouts_by_species: dict[str, list[list[int]]],
    alpha: float = ALPHA,
    ks: Sequence[int] = HMM_KS,
    min_bouts: int = MIN_BOUTS_PER_SPECIES,
    max_iter: int = HMM_MAX_ITER,
) -> dict[str, Any]:
    """The pre-registered comparison: per species, fit on 80% of bouts, score 20%.

    Every model scores every held-out token (the bout-first token under its start
    distribution), and the report's per-token numbers are total log-likelihood
    over total tokens, so M1/M2/M3 denominators are identical. `unseen` counts
    held-out transitions with zero train count under the model's finest context
    (for M3: held-out tokens of a type absent from train) — the cases the smoother
    paid for, which a model must back off over, never crash on.
    """
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index, species in enumerate(sorted(bouts_by_species)):
        bouts = bouts_by_species[species]
        if len(bouts) < min_bouts:
            skipped.append({"species": species, "bouts": len(bouts)})
            continue
        vocab = 1 + max(t for seq in bouts for t in seq)
        train, test = _split(bouts, seed=index)
        row: dict[str, Any] = {
            "species": species,
            "vocab": vocab,
            "bouts_train": len(train),
            "bouts_test": len(test),
            "tokens_test": sum(len(s) for s in test),
            "ll": {},
            "unseen": {},
            "k": None,
            "note": "",
        }
        m1 = FirstOrder(vocab, alpha).fit(train)
        m2 = RepeatCount(vocab, alpha).fit(train)
        for name, model in (("m1", m1), ("m2", m2)):
            ll = tokens = unseen = 0
            for seq in test:
                s_ll, s_n, s_u = model.score(seq)
                ll += s_ll
                tokens += s_n
                unseen += s_u
            row["ll"][name] = ll / tokens
            row["unseen"][name] = unseen
        m3, k, note = fit_hmm(train, vocab, ks=ks, alpha=alpha, max_iter=max_iter)
        row["k"] = k
        row["note"] = note
        if m3 is not None:
            try:
                ll = tokens = unseen = 0
                for seq in test:
                    s_ll, s_n, s_u = m3.score(seq)
                    ll += s_ll
                    tokens += s_n
                    unseen += s_u
                row["ll"]["m3"] = ll / tokens
                row["unseen"]["m3"] = unseen
            except _Unstable as exc:
                row["note"] = (note + "; " if note else "") + f"scoring failed: {exc}"
        for name in ("m2", "m3"):
            if name in row["ll"]:
                row[f"d_{name}"] = row["ll"][name] - row["ll"]["m1"]
        rows.append(row)
    return {
        "params": {
            "alpha": alpha,
            "ks": list(ks),
            "min_bouts": min_bouts,
            "split_seed": SPLIT_SEED,
            "train_fraction": TRAIN_FRACTION,
            "win_delta_nats": WIN_DELTA_NATS,
            "repeat_cap": REPEAT_CAP,
            "repeat_min_obs": REPEAT_MIN_OBS,
        },
        "species": rows,
        "skipped": skipped,
        "verdict": verdict(rows),
    }


def verdict(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Apply the pre-registered rule to the per-species rows.

    A challenger wins only if its mean ΔLL/token over M1 exceeds
    `WIN_DELTA_NATS` averaged across qualifying species AND it beats M1 (Δ > 0)
    on the majority of them. Both challengers winning is broken by the larger
    mean Δ. Anything else is a wash, and a wash keeps first-order — that is the
    documented outcome docs/18 §P1 names in advance.
    """
    out: dict[str, Any] = {"challengers": {}, "winner": "m1", "rule": (
        "a challenger wins only if mean ΔLL/token over M1 exceeds "
        f"+{WIN_DELTA_NATS} nats across qualifying species AND it beats M1 on "
        "the majority of them; a wash keeps first-order"
    )}
    for name, label in (("m2", "repeat-count"), ("m3", "hidden-state")):
        deltas = [r[f"d_{name}"] for r in rows if f"d_{name}" in r]
        if not deltas:
            out["challengers"][name] = {
                "label": label, "species": 0, "mean_delta": None, "wins": 0,
                "won": False,
            }
            continue
        wins = sum(1 for d in deltas if d > 0.0)
        mean_delta = float(np.mean(deltas))
        out["challengers"][name] = {
            "label": label,
            "species": len(deltas),
            "mean_delta": mean_delta,
            "wins": wins,
            "won": mean_delta > WIN_DELTA_NATS and wins > len(deltas) / 2,
        }
    winners = [
        (c["mean_delta"], name)
        for name, c in out["challengers"].items()
        if c["won"]
    ]
    if winners:
        out["winner"] = max(winners)[1]
    return out


def format_report(report: dict[str, Any]) -> str:
    """The per-species table plus the verdict, as plain text for the terminal."""
    lines = [
        "P1 grammar bake-off (docs/18) — held-out log-likelihood per token, nats",
        f"params: {json.dumps(report['params'], sort_keys=True)}",
        "",
        f"{'species':34s} {'bouts':>9s} {'tok':>6s} {'V':>3s} "
        f"{'M1':>7s} {'M2':>7s} {'dM2':>6s} {'M3':>7s} {'dM3':>6s} {'K':>3s} "
        f"{'unseen m1/m2/m3':>16s}  note",
    ]
    for r in report["species"]:
        m3 = f"{r['ll']['m3']:7.3f}" if "m3" in r["ll"] else "      -"
        d3 = f"{r['d_m3']:+6.3f}" if "d_m3" in r else "     -"
        k = str(r["k"]) if r["k"] is not None else "-"
        unseen = f"{r['unseen']['m1']}/{r['unseen']['m2']}/{r['unseen'].get('m3', '-')}"
        lines.append(
            f"{r['species']:34s} {r['bouts_train']:>4d}+{r['bouts_test']:<4d} "
            f"{r['tokens_test']:>6d} {r['vocab']:>3d} "
            f"{r['ll']['m1']:7.3f} {r['ll']['m2']:7.3f} {r['d_m2']:+6.3f} "
            f"{m3} {d3} {k:>3s} {unseen:>16s}  {r['note']}"
        )
    v = report["verdict"]
    lines += ["", f"verdict rule: {v['rule']}"]
    for name in ("m2", "m3"):
        c = v["challengers"][name]
        if c["mean_delta"] is None:
            lines.append(f"  {name} ({c['label']}): no qualifying species")
        else:
            lines.append(
                f"  {name} ({c['label']}): mean ΔLL/token {c['mean_delta']:+.4f} nats, "
                f"beats M1 on {c['wins']}/{c['species']} species -> "
                f"{'WINS' if c['won'] else 'does not win'}"
            )
    winner = v["winner"]
    label = v["challengers"].get(winner, {}).get("label", "first-order")
    lines.append(
        f"  winner: {winner} ({label})"
        + ("" if winner != "m1" else " — a wash; first-order stays, documented as such")
    )
    if report["skipped"]:
        names = ", ".join(f"{s['species']}({s['bouts']})" for s in report["skipped"])
        lines.append(f"  skipped (< {report['params']['min_bouts']} bouts): {names}")
    return "\n".join(lines)


# --- the smoothing repair: unigram vs continuation-count backoff ----------------------


def smoothing_comparison(
    bouts_by_species: dict[str, list[list[int]]],
    alpha: float = ALPHA,
    min_bouts: int = MIN_BOUTS_PER_SPECIES,
) -> dict[str, Any]:
    """Old vs repaired first-order backoff on the bake-off's own protocol.

    Same store bouts, same seeded 80/20 splits (`_split`, same per-species seeds
    as `bake_off`), same α — the only difference is the row an unseen *context*
    falls back to: raw unigram (`old`) vs Kneser–Ney continuation counts (`new`).
    Held-out transitions are bucketed three ways: `seen` (the pair occurred in
    train), `unseen_continuation` (context seen, continuation not — 80 % of the
    unseen tail on the debug store, and *untouched* by this repair by design),
    and `unseen_context` (the repair's entire scope). First tokens are scored
    under the unigram by both models, so they contribute equally to `overall`.

    The pre-registered adoption gate (REPAIR_MIN_UNSEEN_GAIN / REPAIR_MAX_SEEN_LOSS)
    is evaluated on the `unseen_context` bucket — judging a repair scoped to
    unseen-context rows on the whole unseen tail would pre-ordain failure: the
    untouched 80 % dilutes the gain arithmetically, and that dilution is reported
    alongside (`unseen_tail`) rather than hidden.
    """
    rows: list[dict[str, Any]] = []
    buckets = ("seen", "unseen_continuation", "unseen_context")
    totals: dict[str, list[float]] = {b: [0.0, 0.0, 0] for b in ("first", *buckets)}
    for index, species in enumerate(sorted(bouts_by_species)):
        bouts = bouts_by_species[species]
        if len(bouts) < min_bouts:
            continue
        vocab = 1 + max(t for seq in bouts for t in seq)
        train, test = _split(bouts, seed=index)
        old = FirstOrder(vocab, alpha, backoff="unigram").fit(train)
        new = FirstOrder(vocab, alpha, backoff="continuation").fit(train)
        acc: dict[str, list[float]] = {b: [0.0, 0.0, 0] for b in ("first", *buckets)}
        for seq in test:
            p_old = math.log(old.unigram[seq[0]])
            acc["first"][0] += p_old
            acc["first"][1] += p_old
            acc["first"][2] += 1
            for a, b in zip(seq, seq[1:]):
                if old.pair_counts[(a, b)] > 0:
                    bucket = "seen"
                elif a in old.rows:
                    bucket = "unseen_continuation"
                else:
                    bucket = "unseen_context"
                acc[bucket][0] += math.log(old.row(a)[b])
                acc[bucket][1] += math.log(new.row(a)[b])
                acc[bucket][2] += 1
        for b in acc:
            for i in range(3):
                totals[b][i] += acc[b][i]
        row: dict[str, Any] = {"species": species}
        for b in acc:
            ll_o, ll_n, n = acc[b]
            row[b] = {
                "n": int(n),
                "old": ll_o / n if n else None,
                "new": ll_n / n if n else None,
            }
        rows.append(row)

    def pooled(*names: str) -> dict[str, Any]:
        ll_o = sum(totals[b][0] for b in names)
        ll_n = sum(totals[b][1] for b in names)
        n = sum(totals[b][2] for b in names)
        return {
            "n": int(n),
            "old": ll_o / n if n else None,
            "new": ll_n / n if n else None,
            "gain": (ll_n - ll_o) / n if n else None,
        }

    summary = {
        "overall": pooled("first", *buckets),
        "seen": pooled("seen"),
        "unseen_tail": pooled("unseen_continuation", "unseen_context"),
        "unseen_continuation": pooled("unseen_continuation"),
        "unseen_context": pooled("unseen_context"),
    }
    unseen_gain = summary["unseen_context"]["gain"]
    seen_loss = -(summary["seen"]["gain"] or 0.0)
    gate = {
        "unseen_context_gain": unseen_gain,
        "unseen_tail_gain": summary["unseen_tail"]["gain"],
        "seen_loss": seen_loss,
        "passed": (
            unseen_gain is not None
            and unseen_gain >= REPAIR_MIN_UNSEEN_GAIN
            and seen_loss <= REPAIR_MAX_SEEN_LOSS
        ),
        "rule": (
            f"the repair ships only if held-out LL on unseen-*context* transitions "
            f"(the only rows it touches) improves by >= +{REPAIR_MIN_UNSEEN_GAIN} "
            f"nat/token AND seen-transition LL degrades by <= {REPAIR_MAX_SEEN_LOSS} "
            f"nats/token; the full pair-level unseen tail is reported alongside so "
            f"the dilution by the untouched 80% (seen contexts, unseen "
            f"continuations) is visible, not hidden"
        ),
    }
    return {
        "params": {
            "alpha": alpha,
            "min_bouts": min_bouts,
            "split_seed": SPLIT_SEED,
            "train_fraction": TRAIN_FRACTION,
            "repair_min_unseen_gain": REPAIR_MIN_UNSEEN_GAIN,
            "repair_max_seen_loss": REPAIR_MAX_SEEN_LOSS,
        },
        "species": rows,
        "summary": summary,
        "gate": gate,
    }


def format_smoothing_report(report: dict[str, Any]) -> str:
    """The per-species repair table plus the adoption gate, as plain text."""
    lines = [
        "M1 backoff repair (Kneser-Ney continuation counts) — held-out LL/token, nats",
        f"params: {json.dumps(report['params'], sort_keys=True)}",
        "",
        f"{'species':34s} {'overall old/new':>18s} {'seen old/new':>18s} "
        f"{'unseen-ctx old/new':>20s} {'n(uctx)':>7s}",
    ]
    for r in report["species"]:

        def fmt(bucket: str) -> str:
            b = r[bucket]
            if b["old"] is None:
                return "-"
            return f"{b['old']:7.3f}/{b['new']:7.3f}"

        overall = {
            k: v for k, v in r.items() if k != "species"
        }
        ll_o = sum(b["old"] * b["n"] for b in overall.values() if b["old"] is not None)
        ll_n = sum(b["new"] * b["n"] for b in overall.values() if b["old"] is not None)
        n = sum(b["n"] for b in overall.values())
        lines.append(
            f"{r['species']:34s} {ll_o / n:8.3f}/{ll_n / n:<8.3f} "
            f"{fmt('seen'):>18s} {fmt('unseen_context'):>20s} "
            f"{r['unseen_context']['n']:>7d}"
        )
    s = report["summary"]
    lines += [
        "",
        "pooled over qualifying species (LL/token in nats):",
        f"  overall:              {s['overall']['old']:+.4f} -> {s['overall']['new']:+.4f} "
        f"(Δ {s['overall']['gain']:+.4f}, n={s['overall']['n']})",
        f"  seen transitions:     {s['seen']['old']:+.4f} -> {s['seen']['new']:+.4f} "
        f"(Δ {s['seen']['gain']:+.4f}, n={s['seen']['n']})",
        f"  unseen tail (pairs):  {s['unseen_tail']['old']:+.4f} -> "
        f"{s['unseen_tail']['new']:+.4f} "
        f"(Δ {s['unseen_tail']['gain']:+.4f}, n={s['unseen_tail']['n']})",
        f"    of which seen ctx:  {s['unseen_continuation']['old']:+.4f} -> "
        f"{s['unseen_continuation']['new']:+.4f} "
        f"(untouched by the repair, n={s['unseen_continuation']['n']})",
        f"    of which new ctx:   {s['unseen_context']['old']:+.4f} -> "
        f"{s['unseen_context']['new']:+.4f} "
        f"(Δ {s['unseen_context']['gain']:+.4f}, n={s['unseen_context']['n']})",
        "",
        f"adoption gate: {report['gate']['rule']}",
        f"  unseen-context gain {report['gate']['unseen_context_gain']:+.4f} nats/token, "
        f"seen loss {report['gate']['seen_loss']:.4f} -> "
        f"{'PASSES: the repair ships' if report['gate']['passed'] else 'FAILS: unigram backoff stays'}",
    ]
    return "\n".join(lines)


# --- self-test ------------------------------------------------------------------------


def self_test(verbose: bool = True) -> None:
    """The three synthetic processes the bake-off must call correctly.

    If the machinery cannot tell a repeat-count process from a first-order one on
    data where the answer is known by construction, its verdict on the store is
    worthless — so the checks are the pre-registration in miniature: M2 must beat
    M1 on repeat-count data, must not lose on first-order data, and the HMM must
    recover a two-state alternating process that no order-1 chain can express.
    """
    rng = np.random.default_rng(0)

    # 1. Repeat-count process (Jin & Kozhevnikov's shape): exactly three `A`s then
    #    a `B`, repeated; 10 % of bouts get one token corrupted so the counts are
    #    not degenerate. P(B|A) is 1/3 to M1 but ~1 to M2 at r=3.
    bouts: list[list[int]] = []
    for _ in range(120):
        seq = [0, 0, 0, 1] * rng.integers(2, 5)
        if rng.random() < 0.1:
            seq[int(rng.integers(len(seq)))] = 1
        bouts.append(seq)
    report = bake_off({"repeat_bird": bouts}, min_bouts=20, ks=(2,))
    row = report["species"][0]
    assert row["d_m2"] > WIN_DELTA_NATS, (
        f"M2 must beat M1 on a repeat-count process: d={row['d_m2']:+.3f}"
    )

    # 2. First-order process: a noisy cycle A->B->C->A (stay/skip with p=0.15),
    #    which order-1 expresses exactly. M2 may tie but must not lose — its extra
    #    contexts are pure noise here, and the backoff must absorb them.
    trans = np.array([[0.15, 0.70, 0.15], [0.15, 0.15, 0.70], [0.70, 0.15, 0.15]])
    bouts = []
    for _ in range(150):
        seq = [int(rng.integers(3))]
        for _ in range(int(rng.integers(6, 14))):
            seq.append(int(rng.choice(3, p=trans[seq[-1]])))
        bouts.append(seq)
    row = bake_off({"order1_bird": bouts}, min_bouts=20, ks=(2,))["species"][0]
    assert row["d_m2"] > -0.05, (
        f"M2 must not lose on a first-order process: d={row['d_m2']:+.3f}"
    )

    # 3. Two-state alternating process with a shared symbol: state 1 emits
    #    {A,B} 50/50, state 2 emits {B,C} 50/50, states alternate deterministically.
    #    After a `B` the order-1 context cannot tell the phase apart, but the
    #    forward posterior integrates the whole history — the HMM must win.
    bouts = []
    for _ in range(150):
        state = int(rng.integers(2))
        seq = []
        for _ in range(int(rng.integers(8, 16))):
            seq.append(state + int(rng.integers(2)))  # s1->{0,1}, s2->{1,2}
            state = 1 - state
        bouts.append(seq)
    report = bake_off({"hidden_bird": bouts}, min_bouts=20, ks=(2, 4))
    row = report["species"][0]
    assert "m3" in row["ll"], f"HMM unstable on a clean two-state process: {row['note']}"
    assert row["d_m3"] > 0.05, (
        f"M3 must beat M1 on a two-state alternating process: d={row['d_m3']:+.3f}"
    )
    assert report["verdict"]["winner"] == "m3"

    # 4. Unseen handling: a held-out transition that never occurred in train must
    #    be backed off (finite, counted), never a crash or a -inf.
    m1 = FirstOrder(3).fit([[0, 0, 1, 0, 0, 1]] * 30)
    ll, n, unseen = m1.score([0, 1, 2, 1])
    assert np.isfinite(ll) and unseen == 2, (ll, unseen)  # 1->2 and 2->1 unseen

    # 5. The continuation-count repair, on the process it exists for: a rigid
    #    trigram (2 -> 1 -> 0, so tokens 0 and 1 carry high unigram mass but a
    #    continuation count of one each) inside a Zipfian flexible vocabulary —
    #    eight common types plus a long flat tail of rare ones whose *frequencies*
    #    are so low they never appear as a train context, which is what makes
    #    held-out unseen contexts exist at all. After a novel context the truth
    #    is a flexible draw, never 0 or 1 — the continuation row knows this and
    #    the unigram row cannot. Seen-context rows must be bit-identical between
    #    the two backoffs: the repair's scope is the unseen-context row, nothing
    #    else. The fixture has its own seed so edits to the other checks cannot
    #    shift it.
    kn_rng = np.random.default_rng(5)
    n_common, n_rare = 8, 200
    vocab = 2 + n_common + n_rare
    p_common = np.array([1.0 / t**2 for t in range(1, n_common + 1)])
    p_common /= p_common.sum()
    p_flex = np.concatenate([0.9 * p_common, np.full(n_rare, 0.1 / n_rare)])

    def zipf_bouts(count: int) -> list[list[int]]:
        out = []
        for _ in range(count):
            seq = [2 + int(kn_rng.choice(vocab - 2, p=p_flex))]
            for _ in range(int(kn_rng.integers(4, 10))):
                if seq[-1] == 2:
                    seq.append(1)
                elif seq[-1] == 1:
                    seq.append(0)
                else:
                    seq.append(2 + int(kn_rng.choice(vocab - 2, p=p_flex)))
            out.append(seq)
        return out

    train, test = zipf_bouts(80), zipf_bouts(200)
    old = FirstOrder(vocab, backoff="unigram").fit(train)
    new = FirstOrder(vocab, backoff="continuation").fit(train)
    for a in old.rows:
        assert np.array_equal(old.row(a), new.row(a)), (
            f"seen-context row for {a} changed under the continuation backoff"
        )
    ll_old = ll_new = n_unseen_ctx = 0
    for seq in test:
        for a, b in zip(seq, seq[1:]):
            if a not in old.rows and old.pair_counts[(a, b)] == 0:
                ll_old += math.log(old.row(a)[b])
                ll_new += math.log(new.row(a)[b])
                n_unseen_ctx += 1
    assert n_unseen_ctx > 20, f"Zipfian fixture made only {n_unseen_ctx} unseen contexts"
    assert ll_new / n_unseen_ctx > ll_old / n_unseen_ctx + 0.15, (
        f"continuation row must beat the unigram row on unseen contexts: "
        f"{ll_old / n_unseen_ctx:+.3f} -> {ll_new / n_unseen_ctx:+.3f}"
    )

    if verbose:
        print(
            "syntax self-test ok: M2 wins on repeat-count data, holds on "
            "first-order data, M3 recovers a two-state process, unseen backs off, "
            "continuation backoff wins unseen contexts and leaves seen rows untouched"
        )


if __name__ == "__main__":  # pragma: no cover
    self_test()
