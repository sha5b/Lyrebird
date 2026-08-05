"""Stage 1 of the v10 sweep: re-fetch the audio for the store's own xeno-canto rows.

**Why this exists.** `harvest` streams, describes and deletes — by design, and for the
licence. So the store's 7 956 iNaturalist recordings have audio on disk
(`out/audio-cache`, the owner-sanctioned WAV cache) and its 3 731 xeno-canto recordings
have none. That is 151 093 of 378 224 syllables, 39.9 % of the corpus, with no audio
behind it.

Re-segmenting in the `SEGMENT_BAND_HZ` band cannot be done from patches or descriptors.
`quality.self_test` proves why: on its own fixture the legacy full-band path lands on the
rumble's amplitude peaks (0.000, 0.508, 1.138, 1.759 s) and the band-limited path lands on
the chirps (0.305, 0.903, 1.504, 2.104 s). Re-segmentation changes *which syllables exist
and where*, so it needs the samples.

**Why the same recordings rather than a fresh query.** Re-harvesting by species would
return whatever xeno-canto holds today, so the new store would differ from the old one in
its corpus *and* its segmentation, and nothing downstream could be attributed to either.
Fetching these exact 3 731 ids makes v10 differ from `harvest-gan` in the segmentation
regime and nothing else, which turns the sweep into a controlled measurement of what the
band fix does to every published number.

**The audio is kept this time.** The owner's instruction, and it buys something specific:
`specbench` can only bench a type whose audio is cached, which is why the paper's own
population caveat reads "of 2 396 types considered, 1 196 were skipped (753 no cached
audio, 443 too short)". Keeping the xeno-canto side lifts the independent fidelity
instrument's coverage over the 40 % of the corpus it has never been able to see.
`out/` is gitignored, and NOTICE.md's no-redistribution rule is unaffected: this is a
local cache, and no dataset release carries audio.

Resumable: an existing file is skipped, so re-running continues where it stopped.

Usage:
    .venv/bin/python analysis/v10_fetch_xc_audio.py [--limit N] [--pause S]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_STORE = ROOT / "out/harvest-gan"
DEST = ROOT / "out/audio-xc"
PROGRESS = DEST / "_fetch-progress.json"

USER_AGENT = "birdy-pipeline/1.0 (research; contact via repository)"
DOWNLOAD_TIMEOUT = 120
#: xeno-canto's public per-recording download endpoint. The catalogue's own `file` field
#: is exactly this URL (`https://xeno-canto.org/1080577/download`), so the id is enough
#: and no API search is needed — which halves the requests and needs no key.
DOWNLOAD_URL = "https://xeno-canto.org/{id}/download"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def xc_recordings(store: Path) -> list[tuple[str, str]]:
    """(store recording id, numeric xeno-canto id) for every XC row in the store."""
    state = json.loads((store / "state.json").read_text())
    out = []
    for rid in sorted(state["recordings"]):
        if rid.startswith("XC"):
            out.append((rid, rid[2:]))
    return out


def fetch_one(numeric_id: str, pause: float) -> tuple[Path | None, str]:
    """Download one recording. Returns (path, status)."""
    url = DOWNLOAD_URL.format(id=numeric_id)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as res:
            suffix = Path(urllib.parse.urlparse(res.geturl()).path).suffix or ".mp3"
            # Some responses land on a query-string URL; keep the suffix sane.
            if len(suffix) > 5 or not suffix.startswith("."):
                suffix = ".mp3"
            tmp = DEST / f"XC{numeric_id}{suffix}.part"
            with tmp.open("wb") as fh:
                shutil.copyfileobj(res, fh, length=1 << 16)
            final = DEST / f"XC{numeric_id}{suffix}"
            tmp.rename(final)
            return final, "ok"
    except urllib.error.HTTPError as exc:
        # 404 on a redacted or withdrawn recording is a policy outcome, not a transient
        # fault, so it is recorded rather than retried.
        return None, f"http {exc.code}"
    except Exception as exc:  # noqa: BLE001 — any transport fault is worth recording
        return None, f"error {type(exc).__name__}: {exc}"
    finally:
        time.sleep(pause)


def existing(numeric_id: str) -> Path | None:
    for p in DEST.glob(f"XC{numeric_id}.*"):
        if p.suffix != ".part":
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after N downloads (0 = all)")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between requests")
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    wanted = xc_recordings(OLD_STORE)
    log(f"xeno-canto rows in {OLD_STORE.name}: {len(wanted)}")

    todo = [(rid, nid) for rid, nid in wanted if existing(nid) is None]
    log(f"already on disk: {len(wanted) - len(todo)}   to fetch: {len(todo)}")
    if args.limit:
        todo = todo[: args.limit]
        log(f"--limit {args.limit}: fetching {len(todo)}")

    est_h = len(todo) * (args.pause + 1.3) / 3600.0
    log(f"estimated wall clock: {est_h:.1f} h at {args.pause:.1f} s pacing")

    done = failed = 0
    failures: dict[str, str] = {}
    t0 = time.time()
    for i, (rid, nid) in enumerate(todo, 1):
        path, status = fetch_one(nid, args.pause)
        if path is None:
            failed += 1
            failures[rid] = status
            log(f"  [{i}/{len(todo)}] {rid} FAILED {status}")
        else:
            done += 1
            if i % 50 == 0 or i == len(todo):
                rate = i / max(time.time() - t0, 1e-9)
                left = (len(todo) - i) / max(rate, 1e-9) / 3600.0
                mb = sum(p.stat().st_size for p in DEST.glob("XC*") if p.suffix != ".part")
                log(f"  [{i}/{len(todo)}] ok={done} failed={failed} "
                    f"{mb/1e9:.2f} GB  {left:.1f} h left")
        if i % 50 == 0 or i == len(todo):
            PROGRESS.write_text(json.dumps({
                "wanted": len(wanted), "attempted": i, "ok": done,
                "failed": failed, "failures": failures,
            }, indent=1))

    PROGRESS.write_text(json.dumps({
        "wanted": len(wanted), "attempted": len(todo), "ok": done,
        "failed": failed, "failures": failures,
    }, indent=1))
    log(f"\ndone: {done} fetched, {failed} failed, progress in {PROGRESS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
