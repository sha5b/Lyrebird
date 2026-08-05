"""Stage 1 of the authorised re-derivation: re-segment the corpus in band, from local audio.

**Owner decisions, 2026-08-05.** Apply the segmenter band fix to the corpus (not only to new
harvests), and apply a **0 dB SNR floor** — the near-free one, 3.6 % of rows and 97 species for
+0.5 dB, chosen over 3/6 dB because the project's headline claim is breadth.

Three things make this worth doing, and the third was only found while checking feasibility:

1. **The band fix is a real bug fix.** `learn._segments` used to threshold on the full-band
   envelope while every description downstream reads 400 Hz - 12 kHz, so on a rumbling
   recording the segmenter put syllable boundaries on rumble peaks and the description then
   read whatever tonal haze sat inside them.
2. **It buys quality.** +2.9 dB median SNR per recording with 77 % of recordings improving
   (`v10_snr_reconcile.py`), at 0.71 retention.
3. **The corpus is currently MIXED, and its own state.json cannot say so.**
   `out/harvest-gan/state.json` records `segmentBand [400, 12000]`, but that field describes
   the *latest* ingest only (see `harvest.HarvestStore.save`): roughly 340 000 of its 378 224
   rows were segmented full-band and the remainder in band. So every per-row statistic on this
   corpus is currently pooled across two different meters. Re-deriving makes the corpus
   internally consistent for the first time, which no amount of re-measuring can do.

**The cost, measured rather than projected where possible.** 11 685 of the store's 11 687
recordings have cached audio, so this runs entirely locally and loses only the 2 permanent
xeno-canto fetch failures. `v10_resegment_yield.py` projects the corpus at 0.777 of its rows
and species over the fitting floor of 24 falling 2 648 -> ~1 938. This script measures what
actually happens instead of projecting it.

**The ~1 938 projection is probably pessimistic, and the reason is worth knowing.**
`state.json` lists **11 687** recordings but only **9 026** of them contribute a syllable to
the corpus: `add_syllables` enforces `syllableCap` 400 000 by retiring whole recordings, oldest
first within whichever species is currently largest, so 2 661 harvested recordings were trimmed
back out. The 0.777 projection was measured per recording and then applied to the corpus as if
the recording set were fixed. It is not — and because in-band segmentation yields about a fifth
fewer syllables, the cap binds *less* on the way back, so recordings the full-band ingest had to
retire can now stay. This script therefore re-runs the ingest faithfully — every recording with
cached audio, then `add_syllables` caps and rebalances exactly as harvest does — rather than
re-cutting only the 9 026. That is what "re-derive" means, and it is the arrangement under which
the species count is an outcome instead of an assumption.

**Nothing is destroyed.** `out/harvest-gan` is opened read-only and a new store is written to
`--out`, defaulting to `out/harvest-inband`. The descriptor reservoir (`descriptors.f32` +
`points.jsonl`) is copied across unchanged, because those are per-recording-window descriptors
and the segmentation does not touch them; only `syllables.jsonl`, `patches.f16` and `state.json`
are rebuilt. The original remains the canonical store until the owner says otherwise.

This is stage 1 of 3. Stage 2 is `learn` on the new store (the expensive one — it refits every
type), stage 3 is `build`. Neither is launched from here: a re-segmentation whose yield nobody
has looked at is not something to hang hours of fitting on.

Usage:
    .venv/bin/python analysis/v10_resegment_store.py [--limit N] [--out DIR] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from birdy_pipeline import harvest, learn, specbench  # noqa: E402

SOURCE = ROOT / "out/harvest-gan"
CACHES = [ROOT / "out/audio-cache", ROOT / "out/audio-xc"]
OUT_REPORT = Path(__file__).resolve().parent / "v10_resegment_store.json"

#: Owner decision 2026-08-05: the near-free floor. A row under this is dropped.
SNR_FLOOR_DB = 0.0
#: Harvest's own window, so spans match what the corpus was built from.
MAX_SECONDS = harvest.DEFAULT_MAX_SECONDS
#: Files copied across untouched — per-recording-window descriptors, which the
#: segmentation does not affect.
CARRY_OVER = ("descriptors.f32", "points.jsonl")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "out/harvest-inband"))
    ap.add_argument("--limit", type=int, default=None,
                    help="only process this many recordings (for a smoke run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="measure the yield and write the report, but no store")
    # **Why this is raised rather than inherited.** `out/harvest-gan` was built under a
    # syllableCap of 400 000 and held 378 224 rows, so its cap never bound and the
    # per-species retirement in `add_syllables` never ran. In band the corpus keeps
    # 435 630, which does bind — and then the new store would differ from the old by the
    # segmentation *and* by cap trimming, two changes at once. Raising the cap past the
    # yield keeps the segmentation the only difference, which is the whole point of
    # deriving a comparison store.
    ap.add_argument("--syllable-cap", type=int, default=600_000,
                    help="store syllable cap (default %(default)s, chosen to not bind: "
                         "the in-band yield is ~435 630 against the old store's 378 224 "
                         "under a 400 000 cap that never bound)")
    args = ap.parse_args()

    out_root = Path(args.out)
    if out_root.resolve() == SOURCE.resolve():
        log("refusing to write over the source store")
        return 2

    state = json.loads((SOURCE / "state.json").read_text(encoding="utf-8"))
    recordings: dict = state["recordings"]
    order = list(recordings)
    if args.limit:
        order = order[: args.limit]
    log(f"source {SOURCE}: {len(recordings)} recordings, "
        f"{state.get('syllableObservations')} syllables")
    log(f"re-segmenting {len(order)} in band {learn.SEGMENT_BAND_HZ}, "
        f"SNR floor {SNR_FLOOR_DB} dB -> {out_root}")

    # Old per-recording counts, so the yield is measured per recording rather than only
    # in total. Read with load_syllables=True because that is the only way to count them.
    src = harvest.HarvestStore(SOURCE, load_syllables=True)
    old_per_rec: dict[str, int] = {}
    old_snr: list[float] = []
    for o in src.syllables:
        old_per_rec[o.recording_id] = old_per_rec.get(o.recording_id, 0) + 1
        if o.snr is not None:
            old_snr.append(float(o.snr))
    log(f"loaded {len(src.syllables)} source syllables")

    new_obs: list = []
    new_snr: list[float] = []
    per_rec = []
    missing_audio = 0
    yielded_nothing = 0
    dropped_by_floor = 0
    for i, rid in enumerate(order, 1):
        info = recordings[rid]
        sid = info.get("speciesId") or "?"
        path = specbench.resolve_audio(rid, CACHES)
        if path is None:
            missing_audio += 1
            continue
        try:
            mono, rate = harvest.decode(path)
            obs = learn.extract_syllables(
                mono, rate, sid, rid, max_seconds=MAX_SECONDS
            )
        except Exception as exc:  # noqa: BLE001
            log(f"  skip {rid}: {exc}")
            missing_audio += 1
            continue
        before = len(obs)
        kept = [o for o in obs if o.snr is None or float(o.snr) >= SNR_FLOOR_DB]
        dropped_by_floor += before - len(kept)
        if not kept:
            yielded_nothing += 1
        new_obs.extend(kept)
        new_snr.extend(float(o.snr) for o in kept if o.snr is not None)
        per_rec.append({
            "recording": rid, "species": sid,
            "old": old_per_rec.get(rid, 0),
            "inBand": before, "kept": len(kept),
        })
        if i % 250 == 0:
            log(f"  {i}/{len(order)} recordings, {len(new_obs)} syllables kept")

    # species over the fitting floor, before and after
    def over_floor(counts: dict[str, int]) -> int:
        return sum(1 for c in counts.values() if c >= 24)

    # **Compare like with like.** Every "old" figure is restricted to the recordings this
    # run actually processed. On a full run that is the whole store, but on `--limit 40`
    # the unrestricted version divides 40 recordings' output by 378 224 and reports a
    # retention of 0.0035 — a ratio between two different populations, which is the
    # trap this file exists to avoid rather than to reproduce.
    processed = {r["recording"] for r in per_rec}
    old_rows = [o for o in src.syllables if o.recording_id in processed]
    old_snr = [float(o.snr) for o in old_rows if o.snr is not None]
    old_species: dict[str, int] = {}
    for o in old_rows:
        old_species[o.species_id] = old_species.get(o.species_id, 0) + 1
    new_species: dict[str, int] = {}
    for o in new_obs:
        new_species[o.species_id] = new_species.get(o.species_id, 0) + 1

    report = {
        "source": str(SOURCE),
        "out": str(out_root),
        "segmentBand": list(learn.SEGMENT_BAND_HZ) if learn.SEGMENT_BAND_HZ else None,
        "snrFloorDb": SNR_FLOOR_DB,
        "maxSeconds": MAX_SECONDS,
        "syllableCap": args.syllable_cap,
        "recordingsConsidered": len(order),
        "recordingsMissingAudio": missing_audio,
        "recordingsYieldingNothing": yielded_nothing,
        # Both restricted to the recordings processed, so the ratio is one population.
        "syllablesOld": len(old_rows),
        "syllablesNew": len(new_obs),
        "retention": round(len(new_obs) / max(len(old_rows), 1), 4),
        "syllablesInWholeSourceStore": len(src.syllables),
        "partialRun": len(processed) < len(recordings),
        "droppedByFloor": dropped_by_floor,
        "speciesOldOverFitFloor": over_floor(old_species),
        "speciesNewOverFitFloor": over_floor(new_species),
        "medianSnrOld": round(st.median(old_snr), 2) if old_snr else None,
        "medianSnrNew": round(st.median(new_snr), 2) if new_snr else None,
        "projectionForComparison": {
            "retention": 0.777, "speciesOverFitFloor": 1938,
            "source": "analysis/v10_resegment_yield.json",
        },
        "perRecording": per_rec[:2000],
    }

    print("=" * 78)
    print("Re-segmenting the corpus in band, from local audio")
    print("=" * 78)
    print(f"  recordings         {len(order)} considered, {missing_audio} without audio, "
          f"{yielded_nothing} yielding nothing")
    if report["partialRun"]:
        print(f"  PARTIAL RUN        {len(processed)} of {len(recordings)} recordings; "
              f"every figure below is restricted to those")
    print(f"  syllables          {len(old_rows)} -> {len(new_obs)} "
          f"(retention {report['retention']}, projected 0.777)")
    print(f"  dropped by floor   {dropped_by_floor} rows under {SNR_FLOOR_DB} dB")
    print(f"  species >= 24      {report['speciesOldOverFitFloor']} -> "
          f"{report['speciesNewOverFitFloor']} (projected ~1 938)")
    print(f"  median SNR         {report['medianSnrOld']} -> {report['medianSnrNew']} dB")

    OUT_REPORT.write_text(json.dumps(report, indent=1))
    print(f"\n  report written to {OUT_REPORT.name}")

    if args.dry_run:
        print("  --dry-run: no store written")
        return 0

    # Write the new store. The descriptor reservoir is carried over untouched; only the
    # syllable half is rebuilt, and the source store is never opened for writing.
    out_root.mkdir(parents=True, exist_ok=True)
    for name in CARRY_OVER:
        srcf = SOURCE / name
        if srcf.exists():
            shutil.copy2(srcf, out_root / name)
    shutil.copy2(SOURCE / "state.json", out_root / "state.json")
    dst = harvest.HarvestStore(
        out_root, load_syllables=True, syllable_cap=args.syllable_cap
    )
    dst.syllables = []
    for rid, info in recordings.items():
        dst.note_recording(rid, info)
    added = dst.add_syllables(new_obs)
    dst.save()
    print(f"  wrote {out_root}: {added} syllables added, "
          f"{dst.syllable_count} in the store")
    print("  stage 2 is `learn` on this store, and it is NOT launched from here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
