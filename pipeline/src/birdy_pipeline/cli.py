"""`birdy-pipeline` command line: build, calibrate, demo, verify."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from . import features, syrinx
from .calibrate import build_calibration, check_reference, monotonic_fraction, write_calibration
from .corpus import dump_clip_wavs, load_inventory, local_corpus, synthetic_corpus, write_wav
from . import galaxy
from .galaxy import build_galaxy
from .syrinx import (
    Calibration,
    Syllable,
    contour_f0,
    measure_f0_zero_crossings,
    peak_normalise,
    render_song,
    render_syllable,
    spectral_peak_hz,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO_ROOT / "app" / "static" / "birdy"
DEFAULT_INVENTORY = REPO_ROOT / "data" / "inventory.json"
DEFAULT_DEMO_OUT = REPO_ROOT / "pipeline" / "out" / "demo"
CALIBRATION_NAME = "syrinx-calibration.json"

DEMO_SYLLABLES = [
    ("parus_minor", "A"),
    ("strix_aluco", "hooLong"),
    ("cuculus_canorus", "cuck"),
    ("turdus_merula", "flute1"),
    ("troglodytes_troglodytes", "wrenTrill"),
]
DEMO_SONGS = [
    ("parus_minor", "abc_d"),
    ("horornis_diphone", "hokekyo"),
    ("lonchura_striata", "bf_motif"),
]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def ensure_calibration(out_dir: Path, force: bool = False) -> Calibration:
    path = out_dir / CALIBRATION_NAME
    if force or not path.exists():
        data = build_calibration()
        write_calibration(path, data)
        log(f"wrote {path} (monotonic in beta: {monotonic_fraction(data) * 100:.1f} % of steps)")
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        log(f"using existing {path}")
    return Calibration.from_dict(data)


def apply_beta_min(value: float) -> None:
    """`--beta-min` overrides the 8.1 clamp for the sweep and for rendering."""
    if value != syrinx.BETA_MIN:
        log(f"beta clamp lowered from {syrinx.BETA_MIN} to {value} (non-contract; "
            "the browser must read betaClamp from syrinx-calibration.json)")
        syrinx.BETA_MIN = value


def report_reachability(inventory: dict[str, Any], calibration: Calibration) -> None:
    """Report the per-syllable gamma range and how often the beta clamp really bites."""
    offenders: list[tuple[float, str]] = []
    gammas: list[float] = []
    beta_lo, beta_hi = math.inf, -math.inf
    for sp in inventory["species"]:
        for raw in sp["syllables"]:
            syl = Syllable.from_dict(raw)
            gammas.append(syrinx.gamma_for_contour(syl.contour))
            at_floor, at_ceiling, raw_lo, raw_hi = syrinx.clamp_incidence(syl, calibration)
            beta_lo = min(beta_lo, raw_lo)
            beta_hi = max(beta_hi, raw_hi)
            worst = max(at_floor, at_ceiling)
            if worst > 0.01:
                offenders.append(
                    (worst, f"{sp['id']}/{syl.id}: {worst * 100:.1f} % of audible samples "
                     f"(raw beta {raw_lo:.3f}..{raw_hi:.2f})")
                )
    log(f"  per-syllable gamma: {min(gammas):.0f}..{max(gammas):.0f} "
        f"(oversample {syrinx.oversample_for_gamma(min(gammas))}.."
        f"{syrinx.oversample_for_gamma(max(gammas))})")
    log(f"  beta actually used: {beta_lo:.3f}..{beta_hi:.2f} "
        f"(clamp {syrinx.BETA_MIN}..{syrinx.BETA_MAX})")
    if offenders:
        offenders.sort(reverse=True)
        log(f"  beta clamp bites in {len(offenders)} of {len(gammas)} syllables:")
        for _, line in offenders[:5]:
            log(f"    {line}")
        if len(offenders) > 5:
            log(f"    ... and {len(offenders) - 5} more")
    else:
        log("  beta clamp never bites")


def species_by_id(inventory: dict[str, Any], sid: str) -> dict[str, Any]:
    for sp in inventory["species"]:
        if sp["id"] == sid:
            return sp
    raise KeyError(sid)


# --- commands ---------------------------------------------------------------------


def cmd_calibrate(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    apply_beta_min(args.beta_min)
    t0 = time.time()
    data = build_calibration()
    write_calibration(out / CALIBRATION_NAME, data)
    log(
        f"calibration written to {out / CALIBRATION_NAME} in {time.time() - t0:.1f}s; "
        f"f0Range {data['f0Range']}, monotonic in beta over "
        f"{monotonic_fraction(data) * 100:.1f} % of measured steps"
    )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    t0 = time.time()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    apply_beta_min(args.beta_min)
    features.self_test(verbose=False)
    log("features self-test ok")

    inventory_path = Path(args.inventory)
    inventory = load_inventory(inventory_path)
    calibration = ensure_calibration(out, force=args.recalibrate)
    if args.source == "synthetic":
        report_reachability(inventory, calibration)

    if args.source == "synthetic":
        log(f"rendering synthetic corpus (variants={args.variants}, seed={args.seed})")
        clips = synthetic_corpus(
            inventory,
            calibration,
            variants=args.variants,
            song_variants=args.song_variants,
            seed=args.seed,
        )
    else:
        if not args.audio_dir:
            log("--source local requires --audio-dir")
            return 2
        log(f"reading local corpus from {args.audio_dir}")
        clips = local_corpus(Path(args.audio_dir))
    log(f"corpus: {len(clips)} clips, {sum(c.duration for c in clips):.1f} s of audio")

    if args.wav_out:
        dump_clip_wavs(clips, Path(args.wav_out))

    stats = build_galaxy(
        clips,
        inventory,
        out_dir=out,
        inventory_path=inventory_path,
        seed=args.seed,
        k=args.k,
        min_dist=args.min_dist,
        projection=args.projection,
        compare_projections=not args.no_compare_projections,
        build_info={
            "source": args.source,
            "audioDir": str(args.audio_dir) if args.audio_dir else None,
            "variantsPerSyllable": args.variants if args.source == "synthetic" else None,
            "variantsPerSong": args.song_variants if args.source == "synthetic" else None,
            "betaClamp": [syrinx.BETA_MIN, syrinx.BETA_MAX],
            "envelopeAsOutputGain": True,
        },
    )

    log("")
    log(f"built {stats.n_points} points in {stats.k} clusters "
        f"({stats.n_dropped} clips dropped, {time.time() - t0:.1f}s)")
    log(f"durations {stats.duration_range[0]:.3f}..{stats.duration_range[1]:.3f} s, "
        f"cluster sizes {min(stats.cluster_counts)}..{max(stats.cluster_counts)}")
    log(f"cluster purity {stats.purity * 100:.1f} %, mean radius {stats.spread:.3f} "
        f"of max|coord| = 1")
    log(f"projection {stats.projection}: distance faithfulness pearson "
        f"{stats.faithfulness['pearson']:.3f}, spearman "
        f"{stats.faithfulness['spearman']:.3f}; 3D kNN agreement "
        f"{stats.knn_agreement * 100:.1f} %")
    return verify(out)


def cmd_demo(args: argparse.Namespace) -> int:
    out = Path(args.out)
    wav_out = Path(args.wav_out)
    inventory = load_inventory(Path(args.inventory))
    calibration = ensure_calibration(out)
    rng = np.random.default_rng(args.seed)

    log("")
    log(f"{'demo wav':38} {'requested f0':>14} {'measured f0':>12} {'err':>7} "
        f"{'peak bin':>9} {'rms':>7} {'gamma':>7} {'os':>3}")
    for sid, yid in DEMO_SYLLABLES:
        sp = species_by_id(inventory, sid)
        raw = next(s for s in sp["syllables"] if s["id"] == yid)
        syl = Syllable.from_dict(raw)
        audio = peak_normalise(render_syllable(syl, calibration=calibration))
        name = f"{sid}--{yid}.wav"
        write_wav(wav_out / name, audio)

        n = len(audio)
        f0_req = contour_f0(syl.contour, np.arange(n) / max(n - 1, 1))
        req = float(np.exp(np.mean(np.log(f0_req))))
        meas, cv = measure_f0_zero_crossings(audio, steady_from=0.2)
        err = 100.0 * (meas - req) / req if req else 0.0
        gamma = syrinx.gamma_for_contour(syl.contour)
        at_floor, at_ceiling, _, _ = syrinx.clamp_incidence(syl, calibration)
        bite = max(at_floor, at_ceiling)
        clamped = f"  betaClamp bites for {bite * 100:.1f} % of audible samples" if bite > 0.01 else ""
        log(
            f"{name:38} {req:11.0f} Hz {meas:9.0f} Hz {err:6.1f}% "
            f"{spectral_peak_hz(audio):8.0f} {float(np.sqrt(np.mean(audio ** 2))):7.3f} "
            f"{gamma:7.0f} {syrinx.oversample_for_gamma(gamma):3d}{clamped}"
        )

    for sid, gid in DEMO_SONGS:
        sp = species_by_id(inventory, sid)
        song = next(s for s in sp["songs"] if s["id"] == gid)
        table = {s["id"]: Syllable.from_dict(s) for s in sp["syllables"]}
        audio = peak_normalise(render_song(song, table, rng=rng, calibration=calibration))
        name = f"{sid}--song-{gid}.wav"
        write_wav(wav_out / name, audio)
        log(
            f"{name:38} {'(sequence)':>14} {'':>12} {'':>7} "
            f"{spectral_peak_hz(audio):8.0f} {float(np.sqrt(np.mean(audio ** 2))):7.3f}"
        )
    log(f"\nwrote {len(DEMO_SYLLABLES) + len(DEMO_SONGS)} wavs to {wav_out}")
    log("requested f0 = geometric mean of the contour; measured = upward zero crossings")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    return verify(Path(args.out))


def verify(out: Path) -> int:
    """Check the generated asset set for the invariants of 8.3/8.4."""
    problems: list[str] = []

    points = json.loads((out / "points.json").read_text())
    n = points["n"]
    raw = (out / "positions.f32").read_bytes()
    if len(raw) != 3 * n * 4:
        problems.append(f"positions.f32 is {len(raw)} bytes, expected {3 * n * 4}")
    pos = np.frombuffer(raw, dtype="<f4")
    if not np.all(np.isfinite(pos)):
        problems.append("positions.f32 contains NaN/inf")
    extent = float(np.max(np.abs(pos))) if pos.size else 0.0
    if abs(extent - 1.0) > 1e-4:
        problems.append(f"max|coord| is {extent}, expected 1")
    for key in ("speciesId", "syllableId", "songId", "clusterId", "durations", "source"):
        if len(points[key]) != n:
            problems.append(f"points.json[{key}] has {len(points[key])} entries, expected {n}")

    centroids = json.loads((out / "centroids.json").read_text())
    vectors = np.asarray([it["vector"] for it in centroids["items"]], dtype=np.float64)
    if vectors.shape != (centroids["k"], centroids["dims"]):
        problems.append(f"centroid vectors are {vectors.shape}, expected "
                        f"{(centroids['k'], centroids['dims'])}")
    if not np.all(np.isfinite(vectors)):
        problems.append("centroids.json contains NaN/inf")
    empty = [it["id"] for it in centroids["items"] if not it["label"] or it["count"] == 0]
    if empty:
        problems.append(f"clusters without a label or with no members: {empty}")

    space = json.loads((out / "feature-space.json").read_text())
    flat = {
        "sampleRate": features.SAMPLE_RATE,
        "frameSize": features.FRAME,
        "hopSize": features.HOP,
        "melBands": features.N_MEL,
        "mfccCoeffs": features.N_MFCC,
        "dims": features.DIM,
        "temperature": 0.12,
    }
    for key, want in flat.items():
        if space.get(key) != want:
            problems.append(f"feature-space.json {key} is {space.get(key)!r}, expected {want!r}")
    if not space.get("window"):
        problems.append("feature-space.json is missing the flat `window` key")
    if len(space["mean"]) != features.DIM or len(space["std"]) != features.DIM:
        problems.append("feature-space.json mean/std are not 28-d")
    if space["dimNames"] != features.DIM_NAMES:
        problems.append("feature-space.json dimNames do not match the extractor")
    if not np.all(np.isfinite(space["mean"] + space["std"])):
        problems.append("feature-space.json contains NaN/inf")

    cal = json.loads((out / CALIBRATION_NAME).read_text())
    mono = monotonic_fraction(cal)
    if mono < 0.98:
        problems.append(f"calibration only monotonic over {mono * 100:.1f} % of beta steps")
    inv = np.asarray(cal["inverse"]["beta"], dtype=np.float64)
    if not np.all(np.isfinite(inv)):
        problems.append("calibration inverse table contains NaN/inf")
    amp = np.asarray(cal["ampPP"], dtype=np.float64)
    f0_table = np.asarray(cal["f0Hz"], dtype=np.float64)
    if amp.shape != f0_table.shape:
        problems.append(f"ampPP is {amp.shape}, expected the f0Hz shape {f0_table.shape}")
    if not np.all(np.isfinite(amp)) or float(amp.min()) <= 0.0:
        problems.append("ampPP contains NaN/inf or a non-positive cell (source divides by it)")
    worst_f0, worst_amp = check_reference(verbose=False)
    if worst_f0 > 3.0 or worst_amp > 5.0:
        problems.append(
            f"contract 8.6 regression: {worst_f0:.1f} % F0 / {worst_amp:.1f} % ampPP error"
        )

    log("")
    log(f"verify {out}:")
    log(f"  points            {n}")
    log(f"  positions.f32     {len(raw)} bytes = 3 x {n} x float32, max|coord| = {extent:.6f}")
    log(f"  clusters          {centroids['k']} x {centroids['dims']}-d, "
        f"sizes {min(it['count'] for it in centroids['items'])}.."
        f"{max(it['count'] for it in centroids['items'])}")
    log(f"  calibration       f0 {cal['f0Range'][0]:.0f}..{cal['f0Range'][1]:.0f} Hz, "
        f"monotonic over {mono * 100:.1f} % of measured beta steps")
    log(f"  ampPP             {amp.min():.3f}..{amp.max():.3f} (peak-to-peak of y/gamma)")
    log(f"  contract 8.6      worst error {worst_f0:.2f} % F0, {worst_amp:.2f} % ampPP")
    log(f"  confidence mix    " + ", ".join(
        f"{k}={v}" for k, v in sorted(_count_confidence(centroids).items())))
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        man = json.loads(manifest_path.read_text())
        if "faithfulness" in man:
            f = man["faithfulness"]
            log(f"  projection        {man.get('projection', '?')}: distance pearson "
                f"{f['pearson']:.3f} / spearman {f['spearman']:.3f} over {f['pairs']} "
                f"pairs, purity {man.get('clusterPurity', 0) * 100:.1f} %")
    if problems:
        for p in problems:
            log(f"  FAIL: {p}")
        return 1
    log("  all checks passed")
    return 0


def _count_confidence(centroids: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in centroids["items"]:
        key = it["confidence"] or "unlabelled"
        out[key] = out.get(key, 0) + 1
    return out


# --- argument parsing -------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="birdy-pipeline", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="render the corpus and build the galaxy")
    b.add_argument("--source", choices=("synthetic", "local"), default="synthetic")
    b.add_argument("--audio-dir", default=None, help="corpus root for --source local")
    b.add_argument("--variants", type=int, default=96, help="renders per syllable")
    b.add_argument("--song-variants", type=int, default=3, help="renders per song")
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--k", type=int, default=None, help="clusters (default: syllable types)")
    b.add_argument("--out", default=str(DEFAULT_OUT))
    b.add_argument("--wav-out", default=None, help="also write every clip as a wav")
    b.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    b.add_argument("--recalibrate", action="store_true")
    b.add_argument("--min-dist", type=float, default=None,
                   help="UMAP min_dist; visual spread only, does not affect clustering "
                        "(default %s)" % galaxy.UMAP_MIN_DIST)
    b.add_argument("--projection", choices=galaxy.PROJECTIONS,
                   default=galaxy.DEFAULT_PROJECTION,
                   help="3D layout: cmds = classical MDS on cosine distance "
                        "(distance-faithful), pca = first 3 PCs, umap = neighbourhood "
                        "only (default %s)" % galaxy.DEFAULT_PROJECTION)
    b.add_argument("--no-compare-projections", action="store_true",
                   help="skip building the other projections just to measure them")
    b.add_argument("--beta-min", type=float, default=syrinx.BETA_MIN,
                   help="beta clamp floor (contract default 0.15; -0.45 unlocks sub-kHz f0)")
    b.set_defaults(func=cmd_build)

    c = sub.add_parser("calibrate", help="measure beta <-> f0 and write the table")
    c.add_argument("--out", default=str(DEFAULT_OUT))
    c.add_argument("--beta-min", type=float, default=syrinx.BETA_MIN)
    c.set_defaults(func=cmd_calibrate)

    d = sub.add_parser("demo", help="render a few example wavs for listening")
    d.add_argument("--wav-out", default=str(DEFAULT_DEMO_OUT))
    d.add_argument("--out", default=str(DEFAULT_OUT), help="where the calibration lives")
    d.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    d.add_argument("--seed", type=int, default=0)
    d.set_defaults(func=cmd_demo)

    v = sub.add_parser("verify", help="check a generated asset directory")
    v.add_argument("--out", default=str(DEFAULT_OUT))
    v.set_defaults(func=cmd_verify)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
