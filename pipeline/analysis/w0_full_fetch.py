"""W0 full run, stage 1 — fetch the scorable population and embed it through both models.

The pilot ran on 2 158 recordings over 62 species, one model, and said so. Two things were
missing from a publishable version and this stage supplies both.

  1. **The population.** `_catalogue_full.json` holds the complete post-cutoff q:A bird
     catalogue: 21 928 recordings, of which 13 646 sit inside the 886 species that have at
     least 6 recordings from at least 2 recordists. Those 886 species are W0's scorable
     classes, against the pilot's 62. `MAX_PER_SPECIES` then trims those 13 646 down to
     **8 321** without losing a single species — see the cap's own note below for why that
     is a better experiment and not only a cheaper one. **8 321 is the number to quote as
     the population; 13 646 is the uncapped pool it was drawn from.**
  2. **The second model.** BirdNET, so that agreement between two architectures trained by
     different groups is evidence about *the archives* rather than about one model. The
     ONNX backbone `w6_birdnet_arms.py` already uses needs no new runtime.

**Selection is by species here, not by recordist, and that is a deliberate change from
`w6_t1b_perch_postcutoff.py`.** That script selected recordists because its unit was the
recordist; W0's unit is the species, and selecting by recordist is what left the pilot with
62 scorable classes out of 827 species fetched. Every recording inside a scorable species
is taken.

**Why one process and no GPU.** Measured on this machine: Perch 0.19 s and BirdNET 0.24 s
per recording on CPU, against a download paced at 1.0 s by `XenoCanto._wait`. Embedding is
not the bottleneck and a CUDA build would buy nothing, so the downloader runs on its own
thread and the embedding happens in the shadow of the next fetch. Expect the wall clock to
be the download: about four hours.

**Resumable, because a four-hour unattended job will be interrupted.** Embeddings are
checkpointed every `CHECKPOINT` recordings; re-running skips whatever is already in the
npz. Audio is kept — the download is the expensive half, and re-embedding from disk is
minutes.

Usage:  .venv/bin/python analysis/w0_full_fetch.py
        .venv/bin/python analysis/w0_full_fetch.py --limit 300   # smoke test
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from birdy_pipeline.harvest import XenoCanto  # noqa: E402

CACHE = ROOT / "out/audio-postcutoff"
FULL = CACHE / "_catalogue_full.json"
OUTDIR = ROOT / "out/external"
EMB = OUTDIR / "w0-full-embeddings.npz"
META = OUTDIR / "w0-full-meta.json"

#: W0's floor, from `w0_recordist_split.py`. A species below either bound cannot be scored
#: under a recordist-blocked split at all.
MIN_RECORDINGS_PER_SPECIES = 6
MIN_RECORDISTS_PER_SPECIES = 2
#: A cap per species, and it improves the experiment rather than only shortening it.
#:
#: The scorable population is savagely skewed: 6 recordings at the floor, a median of 9, and
#: a maximum of 338. Uncapped, a handful of species would supply a fifth of the probe's
#: training rows and the class prior would do work that the features are supposed to do. At
#: 12 the imbalance is at most 2:1 against the floor instead of 56:1, **no species is lost**
#: because the floor is 6, and the download drops from 12 208 recordings to 6 883.
#: Recordings within an over-cap species are chosen by seeded permutation, not by id order,
#: because id order on xeno-canto is upload order and would take each species' earliest
#: uploads together.
MAX_PER_SPECIES = 12
CHECKPOINT = 400
QUEUE_DEPTH = 24


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def api_key() -> str:
    key = os.environ.get("XC_API_KEY", "")
    if key:
        return key
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("XC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def audio_for(rid: str) -> Path | None:
    for path in CACHE.glob(f"xc{rid}.*"):
        if path.suffix.lower() != ".json":
            return path
    return None


def scorable(found: dict[str, dict]) -> tuple[list[str], dict[str, dict], dict]:
    """Every recording inside a species that W0 can actually score.

    Returns the chosen ids, their metadata, and the census that justifies the choice.
    """
    by_sp_rec: dict[str, set[str]] = defaultdict(set)
    by_sp: dict[str, list[str]] = defaultdict(list)
    meta: dict[str, dict] = {}
    for rid, rec in sorted(found.items()):
        if not (rec.get("file") or ""):
            continue  # redacted audio; no query gets round it
        who = (rec.get("rec") or "").strip()
        sp = f"{rec.get('gen', '')} {rec.get('sp', '')}".strip()
        if not who or not sp:
            continue
        by_sp_rec[sp].add(who)
        by_sp[sp].append(rid)
        meta[rid] = {"recordist": who, "species": sp}

    keep = {
        s for s in by_sp
        if len(by_sp[s]) >= MIN_RECORDINGS_PER_SPECIES
        and len(by_sp_rec[s]) >= MIN_RECORDISTS_PER_SPECIES
    }

    # **The cap has to be recordist-aware, or it quietly destroys what W0 measures.** Take a
    # species with 20 recordings where one recordist supplied 19 and another supplied 1: an
    # ordinary random sample of 12 drops that second recordist about 40 % of the time, the
    # species falls to a single recordist, and it becomes unscorable under a blocked split —
    # after having been counted as scorable. So this round-robins across recordists, which
    # keeps every recordist a species has for as long as the cap allows and spreads the rows
    # across them rather than concentrating them.
    rng = np.random.default_rng(0)
    chosen: list[str] = []
    for sp in sorted(keep):
        per_rec: dict[str, list[str]] = defaultdict(list)
        for rid in by_sp[sp]:
            per_rec[meta[rid]["recordist"]].append(rid)
        order = sorted(per_rec)
        for who in order:
            recs = per_rec[who]
            per_rec[who] = [recs[i] for i in rng.permutation(len(recs))]
        take: list[str] = []
        depth = 0
        while len(take) < MAX_PER_SPECIES:
            added = False
            for who in order:
                if depth < len(per_rec[who]):
                    take.append(per_rec[who][depth])
                    added = True
                    if len(take) >= MAX_PER_SPECIES:
                        break
            if not added:
                break
            depth += 1
        chosen.extend(take)

    chosen = sorted(chosen)
    # The floor is re-checked on the capped set, because a census that describes the
    # uncapped population would overstate what the run can actually score.
    capped_rec: dict[str, set[str]] = defaultdict(set)
    capped_n: Counter[str] = Counter()
    for rid in chosen:
        capped_rec[meta[rid]["species"]].add(meta[rid]["recordist"])
        capped_n[meta[rid]["species"]] += 1
    still = {
        s for s in capped_n
        if capped_n[s] >= MIN_RECORDINGS_PER_SPECIES
        and len(capped_rec[s]) >= MIN_RECORDISTS_PER_SPECIES
    }
    assert still == keep, (
        f"the cap changed the scorable species set ({len(keep)} -> {len(still)}); "
        "the round-robin above is meant to make that impossible"
    )
    census = {
        "catalogue": len(found),
        "playable": len(meta),
        "species_all": len(by_sp),
        "species_scorable": len(keep),
        "recordings_scorable": len(chosen),
        "max_per_species": MAX_PER_SPECIES,
        "recordists_all": len({m["recordist"] for m in meta.values()}),
    }
    return chosen, {r: meta[r] for r in chosen}, census


def load_checkpoint() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    if not EMB.exists():
        return {}, {}
    z = np.load(EMB, allow_pickle=True)
    ids = list(z["ids"])
    return (
        {r: v for r, v in zip(ids, z["perch"])},
        {r: v for r, v in zip(ids, z["birdnet"])},
    )


def save_checkpoint(perch_v: dict[str, np.ndarray], bird_v: dict[str, np.ndarray]) -> None:
    ids = sorted(set(perch_v) & set(bird_v))
    if not ids:
        return
    OUTDIR.mkdir(parents=True, exist_ok=True)
    # The temp name has to END in `.npz`: `savez_compressed` appends `.npz` to anything
    # that does not, so a `.npz.tmp` target silently became `.npz.tmp.npz` and the rename
    # below failed on a file that was never there.
    tmp = EMB.with_name(EMB.stem + ".partial.npz")
    np.savez_compressed(
        tmp,
        ids=np.array(ids, dtype=object),
        perch=np.stack([perch_v[r] for r in ids]).astype(np.float32),
        birdnet=np.stack([bird_v[r] for r in ids]).astype(np.float32),
    )
    tmp.replace(EMB)  # atomic: an interrupted write must not destroy the last good one


def main() -> int:
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    if not FULL.exists():
        log(f"{FULL} is missing — run analysis/w0_full_catalogue.py first.")
        return 2
    key = api_key()
    if not key:
        log("XC_API_KEY is not set and pipeline/.env does not carry one.")
        return 2

    found = json.loads(FULL.read_text())
    chosen, meta, census = scorable(found)
    if limit:
        chosen = chosen[:limit]
        meta = {r: meta[r] for r in chosen}

    perch_v, bird_v = load_checkpoint()
    done = set(perch_v) & set(bird_v)
    todo = [r for r in chosen if r not in done]

    print("=" * 74)
    print("W0 full run, stage 1 — fetch and dual-model embed")
    print("=" * 74)
    for k, v in census.items():
        print(f"  {k:24s} {v:7d}")
    print(f"  already embedded         {len(done & set(chosen)):7d}")
    print(f"  to do                    {len(todo):7d}")
    print(f"  on disk already          {sum(1 for r in todo if audio_for(r)):7d}")
    # Measured, not assumed: the 1.0 s pace `XenoCanto._wait` enforces plus the transfer of
    # a ~6 MB mp3 came out at 2.3 s per recording over the first few hundred.
    est = len(todo) * 2.3 / 3600
    print(f"  estimated wall clock     {est:7.1f} h  (download-bound at ~2.3 s each)")
    # **Written before the download starts, not after it finishes.** The embeddings are
    # useless without the labels that go with them, so a metadata file that only appears at
    # the end means an interrupted four-hour run leaves a checkpoint nobody can read — and
    # it also made the interim `w0_full.py` report 6 recordings out of 400, because it was
    # still reading the previous run's file. This holds the whole intended population; the
    # analysis intersects it with whatever the npz actually has.
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps({"census": census, "meta": meta}, indent=1))

    if not todo:
        print("\n  nothing to do.")
        return 0

    # --- the downloader, on its own thread so embedding happens between fetches.
    client = XenoCanto(key)
    work: queue.Queue = queue.Queue(maxsize=QUEUE_DEPTH)
    failures: Counter[str] = Counter()

    def fetch_all() -> None:
        # The sentinel is in a `finally` because the consumer blocks on `work.get()` with no
        # timeout. Anything escaping this loop — and `audio_for` touches the filesystem, so
        # something can — would otherwise leave a four-hour job hung on an empty queue with
        # a dead producer and no error printed, which reads exactly like slow progress.
        try:
            fetch_loop()
        finally:
            work.put(None)

    def fetch_loop() -> None:
        for rid in todo:
            path = audio_for(rid)
            if path is None:
                try:
                    path = client.download(found[rid], CACHE)
                except Exception as exc:
                    failures[type(exc).__name__] += 1
                    continue
            work.put((rid, path))

    thread = threading.Thread(target=fetch_all, daemon=True)
    thread.start()

    import w6_birdnet_arms as bn
    import w6_t1b_perch_postcutoff as t1b

    os.environ.setdefault("HF_HOME", str(ROOT / "out/perch/hf"))
    model = t1b.load_model()
    session = bn.load_backbone()

    t0 = time.time()
    n = 0
    while True:
        item = work.get()
        if item is None:
            break
        rid, path = item
        try:
            pv = t1b.perch_embed(model, path)
            bv = bn.birdnet_embed(session, path)
        except Exception as exc:
            failures[f"embed:{type(exc).__name__}"] += 1
            continue
        if pv is None or bv is None:
            failures["embed:empty"] += 1
            continue
        perch_v[rid] = pv.astype(np.float32)
        bird_v[rid] = bv.astype(np.float32)
        n += 1
        if n % CHECKPOINT == 0:
            save_checkpoint(perch_v, bird_v)
            rate = n / max(1e-9, time.time() - t0)
            left = (len(todo) - n) / max(1e-9, rate) / 3600
            log(f"  {n}/{len(todo)} embedded  {rate * 3600:.0f}/h  ~{left:.1f} h left  "
                f"skips {sum(failures.values())}")

    thread.join(timeout=30)
    save_checkpoint(perch_v, bird_v)
    ids = sorted(set(perch_v) & set(bird_v) & set(chosen))
    # Rewritten with the outcome, but still carrying the FULL intended population rather
    # than only what embedded — the gap between the two is a result, not a detail to drop.
    META.write_text(json.dumps({
        "census": census,
        "embedded": len(ids),
        "failures": dict(failures),
        "meta": meta,
    }, indent=1))
    print()
    print(f"  embedded this run        {n:7d}")
    print(f"  total in {EMB.name}  {len(ids):7d}")
    print(f"  skipped                  {sum(failures.values()):7d}  {dict(failures)}")
    print(f"  elapsed                  {(time.time() - t0) / 3600:7.2f} h")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
