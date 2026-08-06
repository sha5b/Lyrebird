"""Fetch the COMPLETE post-cutoff bird catalogue, not the first 6 000 of it.

The pilot's `_catalogue.json` holds exactly 6 000 recordings, which is not a property of
the archive but of `SEARCH_PAGES = 60` in `w6_t1b_perch_postcutoff.py` multiplied by the
100 records a page. Asked directly, the same query reports **21 925** recordings over 220
pages. The pilot was reading the first 27 % of its own population.

This writes a separate file rather than overwriting the pilot's, so the published pilot
numbers stay reproducible against the catalogue they were actually computed from.

Usage:  .venv/bin/python analysis/w0_full_catalogue.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lyrebird_pipeline.harvest import XenoCanto  # noqa: E402

CACHE = ROOT / "out/audio-postcutoff"
FULL = CACHE / "_catalogue_full.json"

#: Identical to the pilot's query. The only thing that changes is how deep we page.
SINCE = "2025-09-01"
QUERY = f"grp:birds since:{SINCE} q:A"
#: The API reported 220 pages for this query on 2026-08-04. The margin is for growth, and
#: `search` stops at `numPages` anyway, so an over-estimate costs nothing.
SEARCH_PAGES = 400


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


def main() -> int:
    key = api_key()
    if not key:
        log("XC_API_KEY is not set and pipeline/.env does not carry one.")
        return 2
    CACHE.mkdir(parents=True, exist_ok=True)

    if FULL.exists():
        found = json.loads(FULL.read_text())
        log(f"{FULL.name} already holds {len(found)} recordings; delete it to re-search.")
    else:
        client = XenoCanto(key)
        found: dict[str, dict] = {}
        t0 = time.time()
        for i, rec in enumerate(client.search(QUERY, max_pages=SEARCH_PAGES)):
            rid = str(rec.get("id") or "")
            if rid:
                found[rid] = rec
            if (i + 1) % 2000 == 0:
                log(f"  {len(found)} recordings after {i + 1} rows, {time.time() - t0:.0f}s")
        FULL.write_text(json.dumps(found))
        log(f"wrote {FULL.name}: {len(found)} recordings in {time.time() - t0:.0f}s")

    # What the population can actually support is a question about species and recordists,
    # so report it that way rather than as a row count.
    by_sp_rec: dict[str, set[str]] = defaultdict(set)
    by_sp_n: Counter[str] = Counter()
    by_rec_n: Counter[str] = Counter()
    playable = 0
    for rid, rec in found.items():
        who = (rec.get("rec") or "").strip()
        sp = f"{rec.get('gen', '')} {rec.get('sp', '')}".strip()
        if not (rec.get("file") or ""):
            continue  # redacted; no query gets round it
        playable += 1
        if who and sp:
            by_sp_rec[sp].add(who)
            by_sp_n[sp] += 1
            by_rec_n[who] += 1

    # W0's floor, from `w0_recordist_split.py`: a species needs >= 6 recordings and >= 2
    # recordists, or it cannot be scored under a blocked split at all.
    usable = {s for s in by_sp_n if by_sp_n[s] >= 6 and len(by_sp_rec[s]) >= 2}
    print("=" * 74)
    print("Post-cutoff catalogue, complete")
    print("=" * 74)
    print(f"  query                                {QUERY}")
    print(f"  recordings in catalogue        {len(found):7d}")
    print(f"  with downloadable audio        {playable:7d}")
    print(f"  distinct species              {len(by_sp_n):7d}")
    print(f"  distinct recordists           {len(by_rec_n):7d}")
    print()
    print(f"  species with >=6 recs AND >=2 recordists  {len(usable):5d}"
          "   <- W0's scorable classes")
    print(f"  recordings inside those species          "
          f"{sum(by_sp_n[s] for s in usable):6d}")
    for floor in (2, 3, 4):
        n = {s for s in by_sp_n if by_sp_n[s] >= 6 and len(by_sp_rec[s]) >= floor}
        print(f"    at >= {floor} recordists                      {len(n):5d} species, "
              f"{sum(by_sp_n[s] for s in n):6d} recordings")
    print()
    print("  For comparison the pilot scored 62 species over 2 158 recordings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
