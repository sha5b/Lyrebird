"""W6 T1b — the Perch recordist result, re-run on audio Perch cannot have seen.

**Why this exists.** `w6_t1_perch_recordist.py` measured the recordist confound in Perch
2.0's embedding space over the cached iNaturalist audio, and that result is one of the four
ends at which the whitepaper says the confound was closed. On 2026-08-04 the Perch 2.0 tech
report (arXiv 2508.04665) was read properly: Perch trained on **Xeno-canto and iNaturalist
research-grade audio**, ~1.5 M recordings. Our iNat cache comes from `visipedia/inat_sounds`
(2024), which is drawn from exactly that population. **Perch may have been recognising its
own training data, and a model that memorised a recording will place it next to that
recording's siblings for reasons that have nothing to do with acoustics.**

There is no escape inside the existing cache. Every wav in `out/audio-cache` is iNat Sounds
2024, the ids are dataset indices rather than observation ids, and no date is stored. So
this fetches new audio instead.

**The discriminator, and why upload date rather than recording date.** Xeno-canto's `since:`
tag filters on when a recording was *uploaded*. A recording uploaded after Perch 2.0's data
snapshot cannot have been in that snapshot no matter when it was recorded, which makes it a
one-directional guarantee rather than an estimate. Perch 2.0 was published 2025-08
(arXiv 2508.04665), so `SINCE` is set a month past that with no attempt at precision — the
argument only needs the bound to be safe, not tight.

**What a comparison against T1 can and cannot say.** These are different recordings, a
different archive and a different species mix, so an absolute difference in lift is not
attributable to contamination alone. What the arm does establish is whether the recordist
structure Perch shows is **present at all** in audio it provably never trained on. That is
the claim the whitepaper actually leans on, and it is the one that was in doubt.

Nothing here writes to the store. Audio lands in its own cache.

Usage:  .venv/bin/python analysis/w6_t1b_perch_postcutoff.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lyrebird_pipeline import geometry, perch  # noqa: E402
from lyrebird_pipeline.harvest import XenoCanto  # noqa: E402

CACHE = ROOT / "out/audio-postcutoff"
CATALOGUE = CACHE / "_catalogue.json"
#: recording id -> {recordist, species}. Written here and consumed by
#: `w0_recordist_split.py`, so the W0 pilot runs on exactly this population.
META = CACHE / "_meta.json"
MODEL_DIR = ROOT / "out/perch"
#: Frozen Perch features for this population, shared with `w0_recordist_split.py`.
EMB = ROOT / "out/external/postcutoff-perch.npz"
OUT = Path(__file__).resolve().parent / "w6_t1b_perch_postcutoff.json"

#: One month past Perch 2.0's publication. Safe, not tight.
SINCE = "2025-09-01"
#: `grp:birds` is not optional, and leaving it out did not fail loudly.
#:
#: Xeno-canto hosts bats, frogs, grasshoppers and land mammals alongside birds. Without the
#: group tag, `since:{SINCE} q:A` returned 6 000 recordings — the 60-page cap — of which
#: **zero were birds**: 3 035 bats, 1 568 frogs, 926 grasshoppers, 471 land mammals. The
#: pagination simply never reached the birds. Nothing errored; the first three downloads
#: were 256 kHz ultrasonic bat clips that decoded perfectly well and would have gone into
#: a bird model as if they were birdsong.
#: `q:A` keeps the audio quality comparable to T1's cache.
QUERY = f"grp:birds since:{SINCE} q:A"
SEARCH_PAGES = 60
MIN_PER_RECORDIST = 8
MAX_PER_RECORDIST = 20
#: Every recordist with >= 8, at <= 20 each: 137 recordists in this catalogue, so ~2 700.
#:
#: 900 was T1's number and it is enough to measure recordist structure, but the same audio
#: feeds `w0_recordist_split.py`, whose unit is the *species* — and 900 recordings spread
#: over 467 species is two per species, far below what a probe can be trained and tested
#: on. Selection is by recordist either way, so the wider fetch costs only download time
#: and serves both arms.
RECORDING_CAP = 2800
WINDOW_BUDGET = 6  # 30 s per recording, as T1
SEED = 0


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def audio_for(rid: str) -> Path | None:
    """The cached file for a recording, whatever extension the server redirected to."""
    for path in CACHE.glob(f"xc{rid}.*"):
        if path.suffix.lower() != ".json":
            return path
    return None


def catalogue(client: XenoCanto) -> dict[str, dict]:
    """Recording metadata for everything uploaded since the cutoff, by id.

    Cached to disk, because the search is 60 paced pages and re-running the embedding or
    the selection is otherwise held behind a minute of paging that returns the same thing
    every time. Delete `_catalogue.json` to force a fresh search.
    """
    if CATALOGUE.exists():
        return json.loads(CATALOGUE.read_text())
    found: dict[str, dict] = {}
    for rec in client.search(QUERY, max_pages=SEARCH_PAGES):
        rid = str(rec.get("id") or "")
        if rid:
            found[rid] = rec
    CATALOGUE.parent.mkdir(parents=True, exist_ok=True)
    CATALOGUE.write_text(json.dumps(found))
    return found


def select(found: dict[str, dict]) -> list[str]:
    """Same selection rule as T1: >= 8 per recordist, <= 20 each, seeded, capped."""
    by_recordist: dict[str, list[str]] = defaultdict(list)
    for rid, rec in sorted(found.items()):
        who = (rec.get("rec") or "").strip()
        if who and (rec.get("file") or ""):
            by_recordist[who].append(rid)

    rng = np.random.default_rng(SEED)
    chosen: list[str] = []
    for who in sorted(by_recordist, key=lambda w: (-len(by_recordist[w]), w)):
        recs = by_recordist[who]
        if len(recs) < MIN_PER_RECORDIST:
            continue
        take = recs if len(recs) <= MAX_PER_RECORDIST else [
            recs[i] for i in rng.permutation(len(recs))[:MAX_PER_RECORDIST]
        ]
        chosen.extend(sorted(take))
        if len(chosen) >= RECORDING_CAP:
            break
    return sorted(chosen[:RECORDING_CAP])


def load_model() -> perch.PerchModel:
    """The shipped Perch session without the class list — T1's loader, verbatim in intent."""
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(MODEL_DIR / "hf"))
    onnx_path = hf_hub_download(perch.HF_REPO, perch.HF_FILE)
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    return perch.PerchModel(session=session, labels=[])


def perch_embed(model: perch.PerchModel, path: Path) -> np.ndarray | None:
    import soundfile as sf

    audio, rate = sf.read(str(path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != perch.PERCH_SAMPLE_RATE:
        n = int(round(len(audio) * perch.PERCH_SAMPLE_RATE / rate))
        if n < 2:
            return None
        audio = np.interp(
            np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio
        ).astype(np.float32)
    win = int(perch.PERCH_WINDOW_SECONDS * perch.PERCH_SAMPLE_RATE)
    if len(audio) < win:
        audio = np.pad(audio, (0, win - len(audio)))
    starts = list(range(0, max(1, len(audio) - win + 1), win))[:WINDOW_BUDGET]
    batch = np.stack([audio[s : s + win] for s in starts]).astype(np.float32)
    _scores, emb = model.label(batch)
    return np.asarray(emb, dtype=np.float64).mean(axis=0)


def main() -> int:
    key = os.environ.get("XC_API_KEY", "")
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("XC_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        log("XC_API_KEY is not set and pipeline/.env does not carry one.")
        return 2

    CACHE.mkdir(parents=True, exist_ok=True)
    client = XenoCanto(key)

    t0 = time.time()
    log(f"searching xeno-canto for {QUERY!r} ...")
    found = catalogue(client)
    log(f"  {len(found)} recordings uploaded since {SINCE}")

    chosen = select(found)
    recordists = {(found[r].get("rec") or "").strip() for r in chosen}
    species = {
        f"{found[r].get('gen', '')} {found[r].get('sp', '')}".strip() for r in chosen
    }
    log(f"selected {len(chosen)} recordings from {len(recordists)} recordists, "
        f"{len(species)} species")
    if len(chosen) < 200:
        log("too few recordings to measure anything; widen QUERY or SEARCH_PAGES")
        return 1

    # `XenoCanto.download` takes the destination **directory** and names the file itself,
    # `xc<id><suffix>`, choosing the suffix from the redirected URL. Passing a file path
    # here instead made every write target a parent that does not exist, and because the
    # failure came back through the `except` below it looked exactly like 900 redacted
    # recordings rather than like one wrong argument. Hence `audio_for`, which asks the
    # directory what is already there rather than guessing an extension.
    got: list[str] = []
    failures: Counter[str] = Counter()
    for i, rid in enumerate(chosen):
        if audio_for(rid) is None:
            try:
                client.download(found[rid], CACHE)
            except Exception as exc:  # a redacted or missing file is a skip with a count
                failures[type(exc).__name__] += 1
                if sum(failures.values()) <= 5:
                    log(f"  {rid}: {exc}")
                continue
        if audio_for(rid) is None:
            failures["no file after download"] += 1
            continue
        got.append(rid)
        if (i + 1) % 100 == 0:
            log(f"  fetched {len(got)}/{i + 1} in {time.time() - t0:.0f}s")
    log(f"have audio for {len(got)} recordings; skipped {sum(failures.values())} "
        f"({dict(failures)})")
    if not got:
        log("nothing downloaded — check the failure reasons above before re-running")
        return 1

    # Written before the embedding pass, so the W0 pilot has its population even if the
    # embed is interrupted — the download is the expensive half and is what this protects.
    META.write_text(json.dumps({
        rid: {
            "recordist": (found[rid].get("rec") or "").strip(),
            "species": f"{found[rid].get('gen', '')} {found[rid].get('sp', '')}".strip(),
            "uploaded_since": SINCE,
        }
        for rid in got
    }, indent=1))

    model = load_model()
    rows: list[str] = []
    vecs: list[np.ndarray] = []
    for i, rid in enumerate(got):
        path = audio_for(rid)
        if path is None:
            continue
        try:
            v = perch_embed(model, path)
        except Exception as exc:
            log(f"  embed {rid}: {exc}")
            continue
        if v is None:
            continue
        rows.append(rid)
        vecs.append(v)
        if (i + 1) % 100 == 0:
            log(f"  embedded {len(rows)}/{i + 1} in {time.time() - t0:.0f}s")

    x = np.stack(vecs)
    who = [(found[r].get("rec") or "").strip() for r in rows]
    spp = [f"{found[r].get('gen', '')} {found[r].get('sp', '')}".strip() for r in rows]

    # Saved so `w0_recordist_split.py` reuses them instead of spending another half hour
    # putting the same audio through the same frozen model.
    EMB.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(EMB, x=x, ids=np.array(rows, dtype=object))
    log(f"wrote {EMB.name} ({x.shape[0]} x {x.shape[1]})")

    print("=" * 74)
    print("W6 T1b — Perch's recordist structure on audio it provably never trained on")
    print("=" * 74)
    print(f"  uploaded to xeno-canto since   {SINCE}")
    print(f"  recordings embedded            {len(rows):5d}")
    print(f"  recordists                     {len({w for w in who if w}):5d}")
    print(f"  species                        {len({s for s in spp if s}):5d}")

    result: dict[str, object] = {
        "since": SINCE, "query": QUERY, "recordings": len(rows),
        "recordists": len({w for w in who if w}), "species": len({s for s in spp if s}),
    }
    def arm(name: str, keep: np.ndarray) -> dict[str, object]:
        out: dict[str, object] = {}
        print()
        print(f"  {name}  ({int(keep.sum())} recordings)")
        for grouping, labels in (("species", spp), ("recordist", who)):
            sub = [l for l, k in zip(labels, keep) if k]
            rel = geometry.measure(
                x[keep], sub, grouping=grouping, space="perch", metric="cosine", seed=SEED
            )
            if rel is None:
                print(f"    {grouping:10s} untestable")
                out[grouping] = None
                continue
            lift = rel.knn - rel.knn_null
            out[grouping] = {
                "groups": rel.groups, "labelled": rel.labelled,
                "coverage": round(rel.coverage, 4), "knn": round(rel.knn, 4),
                "null": round(rel.knn_null, 4), "lift": round(lift, 4),
                "p": rel.knn_p, "verdict": rel.verdict,
            }
            print(f"    {grouping:10s} groups {rel.groups:4d}   knn {rel.knn:.3f}   "
                  f"null {rel.knn_null:.3f}   LIFT {lift:+.3f}   p {rel.knn_p:.3g}   "
                  f"{rel.verdict}")
            print(f"    {'':10s} tested on {rel.labelled} of {int(keep.sum())} "
                  f"({rel.coverage:.1%})")
        return out

    print()
    result["all"] = arm("ARM A — every recording", np.ones(len(rows), dtype=bool))

    # ARM B, and it is here for the same reason G3 needed its Arm C. `geometry.measure`
    # drops any group under 8, and in this population ~137 recordists clear that while only
    # ~36 species do. Subtracting a species lift measured on 36 species from a recordist
    # lift measured on 137 recordists compares two different populations and says nothing.
    # This arm keeps only recordings whose species AND recordist both clear the floor.
    def matched(idx: list[int]) -> list[int]:
        for _ in range(20):  # dropping rows can push a group back under the floor
            sc, rc = Counter(spp[i] for i in idx), Counter(who[i] for i in idx)
            keep = [i for i in idx
                    if sc[spp[i]] >= geometry.MIN_GROUP and rc[who[i]] >= geometry.MIN_GROUP]
            if len(keep) == len(idx):
                return keep
            idx = keep
        return idx

    both = matched(list(range(len(rows))))
    if len(both) >= 2 * geometry.MIN_GROUP:
        mask = np.zeros(len(rows), dtype=bool)
        mask[both] = True
        result["matched"] = arm(
            "ARM B — matched rows (species AND recordist both >= 8), the fair margin", mask
        )
    else:
        print()
        print(f"  ARM B — matched rows: only {len(both)} recordings qualify, not measured")
        result["matched"] = None

    fair = result.get("matched") or result.get("all") or {}
    sp_l = fair.get("species")
    rc_l = fair.get("recordist")
    if isinstance(sp_l, dict) and isinstance(rc_l, dict):
        print()
        print(f"  recordist lift {rc_l['lift']:+.3f}  vs  species lift {sp_l['lift']:+.3f}")
        print("  T1, on the contaminated iNat cache, is the comparison — but these are")
        print("  different recordings from a different archive, so the question this arm")
        print("  answers is whether the recordist structure is PRESENT at all here.")
        result["recordist_structure_present"] = bool(
            rc_l["lift"] > 0.02 and rc_l["p"] <= 0.05
        )
        print(f"  recordist structure present on unseen audio: "
              f"{'YES' if result['recordist_structure_present'] else 'NO'}")

    OUT.write_text(json.dumps(result, indent=1, default=float))
    print(f"\n  written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
