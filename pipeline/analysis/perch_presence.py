"""Perch 2.0 as a bird-presence measurement over the cached iNat audio — and the
calibration that says a *rejecting* gate on it is not supportable.

**What was asked.** The owner found an ingested recording that sounds like noise
(INAT227259) and asked whether the pipeline has filtering that keeps such things out. Three
candidate gates were measured against it and all three failed, so Perch 2.0 — the only
component in the repository that can answer "is there a bird here" at all — was the chosen
route.

**What it measures.** Per recording: `taxon_max`, the highest score over Perch's 14 595
binomial taxon classes across all its 5-second windows, and `event_max` over the 200
FSD50K sound-event classes. `taxon_max` is the presence signal; it is not "bird" exactly,
because the iNat 2024 class list also carries frogs, insects and mammals, and that
imprecision is stated rather than hidden.

**What it found, and it is the reason nothing here is wired into ingest.** Over a
200-recording random sample of `out/audio-cache`, `taxon_max` runs min 0.035, p25 0.297,
median 0.541, max 0.996 — and **INAT227259 scores 0.899, the 88th percentile.** Perch reads
it as *Trogon curucui* (the store's own label for it) in its first windows and *Passer
domesticus* at up to 0.899 later on. A threshold low enough to reject that recording
rejects roughly 88 % of the corpus with it.

So the honest output of this file is a table and a distribution, not a verdict. It exists so
the next person can pick a threshold *against the distribution* if they ever want one, and
so the claim "Perch cannot gate this" has the numbers behind it rather than an assertion.

The real defect that recording exposed turned out to be elsewhere and is fixed:
`learn.SEGMENT_BAND_HZ`. 98.7 % of INAT227259's energy is below 400 Hz, outside the band
every description uses, and the segmenter was thresholding on it — the syllables had been
chosen by the rumble before any per-syllable gate got to see them. That is why all three
gates failed on it: they were being asked the wrong question about the wrong spans.

Discipline, unchanged from `perch.py`: **nothing here is typing ground truth and `learn.py`
does not read this output.** A presence score is metadata like a label is (docs/13 §A1).

    uv run python analysis/perch_presence.py --limit 200 --out out/perch-presence.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lyrebird_pipeline import harvest, perch  # noqa: E402

#: Perch's class list mixes 14 595 `"Genus species"` taxa with 200 FSD50K sound-event
#: labels (`Wind`, `Engine`, `Chirp_and_tweet`, ...). The binomial pattern is what separates
#: them, and it is checked against the count so a class-list change cannot go unnoticed.
BINOMIAL = re.compile(r"^[A-Z][a-z]+ [a-z-]+$")
EXPECTED_EVENT_CLASSES = 200


def taxon_mask(labels: list[str]) -> np.ndarray:
    mask = np.array([bool(BINOMIAL.match(label)) for label in labels])
    events = int((~mask).sum())
    if events != EXPECTED_EVENT_CLASSES:
        print(
            f"warning: {events} non-binomial classes, expected {EXPECTED_EVENT_CLASSES} — "
            f"the class list has changed and the taxon/event split may be wrong",
            file=sys.stderr,
        )
    return mask


def score_recording(
    model: perch.PerchModel, path: Path, is_taxon: np.ndarray, labels: np.ndarray
) -> dict | None:
    """Whole-recording presence, on non-overlapping windows.

    Non-overlapping and un-centred, unlike `perch.window_at`: this asks about the recording,
    not about a syllable, so every second gets looked at exactly once.
    """
    window = int(perch.PERCH_WINDOW_SECONDS * perch.PERCH_SAMPLE_RATE)
    audio, rate = harvest.decode(path, perch.PERCH_SAMPLE_RATE)
    if audio.size < window:
        audio = np.pad(audio, (0, window - audio.size))
    count = audio.size // window
    windows = np.stack([audio[i * window : (i + 1) * window] for i in range(count)])
    scores, _ = model.label(windows)
    taxa = scores[:, is_taxon]
    per_window = taxa.max(axis=1)
    return {
        "recordingId": path.stem,
        "seconds": round(audio.size / rate, 1),
        "windows": int(count),
        "taxonMax": round(float(per_window.max()), 4),
        "taxonMedian": round(float(np.median(per_window)), 4),
        "eventMax": round(float(scores[:, ~is_taxon].max()), 4),
        "topTaxon": str(labels[is_taxon][taxa.max(axis=0).argmax()]),
        "topEvent": str(labels[~is_taxon][scores[:, ~is_taxon].max(axis=0).argmax()]),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--audio-cache", default="out/audio-cache")
    p.add_argument("--model-dir", default="out/perch")
    p.add_argument("--out", default="out/perch-presence.jsonl")
    p.add_argument("--limit", type=int, default=200,
                   help="recordings to sample (0 = the whole cache, ~6 500)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--include", action="append", default=["INAT227259"],
                   help="always score these ids, sampled or not")
    args = p.parse_args(argv)

    cache = Path(args.audio_cache)
    ids = sorted(q.stem for q in cache.glob("*.wav"))
    if not ids:
        print(f"no wavs in {cache}", file=sys.stderr)
        return 2
    if args.limit and args.limit < len(ids):
        rng = np.random.default_rng(args.seed)
        chosen = [ids[i] for i in rng.choice(len(ids), size=args.limit, replace=False)]
    else:
        chosen = ids
    for rid in args.include:
        if rid not in chosen and (cache / f"{rid}.wav").exists():
            chosen.append(rid)

    model = perch.ensure_model(Path(args.model_dir))
    labels = np.array(model.labels)
    is_taxon = taxon_mask(model.labels)
    print(f"{len(model.labels)} classes, {int(is_taxon.sum())} taxa, "
          f"{int((~is_taxon).sum())} sound events; scoring {len(chosen)} recordings",
          file=sys.stderr)

    rows: list[dict] = []
    start = time.time()
    for n, rid in enumerate(chosen, start=1):
        try:
            row = score_recording(model, cache / f"{rid}.wav", is_taxon, labels)
        except Exception as exc:
            print(f"  skip {rid}: {exc}", file=sys.stderr)
            continue
        if row is not None:
            rows.append(row)
        if n % 25 == 0:
            print(f"  {n}/{len(chosen)}  {time.time() - start:.0f} s", file=sys.stderr,
                  flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "_meta": {
            "model": f"{perch.HF_REPO}/{perch.HF_FILE}",
            "score": f"sigmoid({perch.LOGIT_SLOPE} * logit + {perch.LOGIT_INTERCEPT})",
            "taxonClasses": int(is_taxon.sum()),
            "eventClasses": int((~is_taxon).sum()),
            "windowSeconds": perch.PERCH_WINDOW_SECONDS,
            "sampled": len(rows),
            "ofCached": len(ids),
            "discipline": "measurement only — learn.py does not read this "
                          "(docs/13 section A1)",
            "verdict": "no rejecting threshold is supportable: see the module docstring",
        }
    }
    out.write_text(
        "\n".join(json.dumps(r) for r in [meta, *rows]) + "\n", encoding="utf-8"
    )

    v = np.array([r["taxonMax"] for r in rows])
    print(f"\n{len(rows)} recordings scored in {time.time() - start:.0f} s -> {out}")
    print("taxon_max distribution:")
    for q in (0, 5, 10, 25, 50, 75, 90, 100):
        print(f"  p{q:<3d} {np.percentile(v, q):.3f}")
    print("\nwhat a rejecting threshold would cost:")
    for threshold in (0.1, 0.2, 0.3, 0.5, 0.7, 0.9):
        print(f"  taxon_max < {threshold:.1f}: drops {100 * (v < threshold).mean():5.1f} % "
              f"of recordings")
    for rid in args.include:
        hit = [r for r in rows if r["recordingId"] == rid]
        if hit:
            r = hit[0]
            print(f"\n{rid}: taxon_max {r['taxonMax']:.3f} "
                  f"({100 * (v < r['taxonMax']).mean():.0f}th percentile), "
                  f"top taxon {r['topTaxon']}, top event {r['topEvent']} "
                  f"{r['eventMax']:.3f}")
            print("  -> a threshold that rejects this recording rejects "
                  f"{100 * (v <= r['taxonMax']).mean():.0f} % of the corpus with it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
