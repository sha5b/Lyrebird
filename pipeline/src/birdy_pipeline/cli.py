"""`birdy-pipeline` command line: build, calibrate, demo, verify."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import features, syrinx
from .calibrate import build_calibration, check_reference, monotonic_fraction, write_calibration
from .corpus import dump_clip_wavs, load_inventory, local_corpus, synthetic_corpus, write_wav
from . import galaxy, harvest, learn
from .galaxy import PointSet, build_galaxy
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
DEFAULT_HARVEST_STORE = REPO_ROOT / "pipeline" / "out" / "harvest"
DEFAULT_LEARNED_INVENTORY = REPO_ROOT / "data" / "learned-inventory.json"
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


def load_dotenv(path: Path = REPO_ROOT / "pipeline" / ".env") -> None:
    """Read `pipeline/.env` into the environment, if it exists.

    Deliberately tiny and dependency-free, and deliberately *not* overriding anything
    already set: an explicit `XC_API_KEY=... uv run ...` has to win over the file. See
    `pipeline/.env.example` for the template.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


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


def cmd_build(
    args: argparse.Namespace, should_stop: Callable[[], bool] | None = None
) -> int:
    """`should_stop` is polled by the two long loops. A stopped build writes nothing."""
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

    parts: list[PointSet] = []
    harvest_info: dict[str, Any] | None = None

    if args.source == "synthetic":
        log(f"rendering synthetic corpus (variants={args.variants}, seed={args.seed})")
        clips = synthetic_corpus(
            inventory,
            calibration,
            variants=args.variants,
            song_variants=args.song_variants,
            seed=args.seed,
            should_stop=should_stop,
        )
        log(f"corpus: {len(clips)} clips, {sum(c.duration for c in clips):.1f} s of audio")
        if args.wav_out:
            dump_clip_wavs(clips, Path(args.wav_out))
        parts.append(galaxy.descriptors(clips, should_stop=should_stop))
    elif args.source == "local":
        if not args.audio_dir:
            log("--source local requires --audio-dir")
            return 2
        log(f"reading local corpus from {args.audio_dir}")
        clips = local_corpus(Path(args.audio_dir))
        log(f"corpus: {len(clips)} clips, {sum(c.duration for c in clips):.1f} s of audio")
        if args.wav_out:
            dump_clip_wavs(clips, Path(args.wav_out))
        parts.append(galaxy.descriptors(clips, should_stop=should_stop))

    # The harvested store can stand alone or sit alongside the rendered inventory. Mixed
    # is the interesting case: the synthetic clips anchor the clusters that have
    # citations, and the field descriptors fill in the shape of the real repertoire
    # around them.
    if args.source == "harvest" or args.harvest_store:
        store_path = Path(args.harvest_store or DEFAULT_HARVEST_STORE)
        store = harvest.HarvestStore(store_path)
        field = store.to_point_set()
        log(f"harvest store {store_path}: {len(field)} field descriptors "
            f"from {len(store.recordings)} recordings")
        rep = store.representativeness()
        harvest_info = {
            "store": str(store_path),
            "points": len(field),
            "recordings": len(store.recordings),
            "descriptorsSeen": store.stream_n,
            "sampleDrift": {k: round(v, 4) for k, v in rep.items()},
        }
        parts.append(field)

    if not parts:
        log(f"--source {args.source} produced nothing to embed")
        return 2
    points = PointSet.concat(parts)
    log(f"embedding {len(points)} points")

    stats = build_galaxy(
        points,
        inventory,
        out_dir=out,
        inventory_path=inventory_path,
        seed=args.seed,
        k=args.k,
        min_dist=args.min_dist,
        projection=args.projection,
        compare_projections=not args.no_compare_projections,
        separation=args.separation,
        build_info={
            "source": args.source,
            "audioDir": str(args.audio_dir) if args.audio_dir else None,
            "variantsPerSyllable": args.variants if args.source == "synthetic" else None,
            "variantsPerSong": args.song_variants if args.source == "synthetic" else None,
            "harvest": harvest_info,
            "betaClamp": [syrinx.BETA_MIN, syrinx.BETA_MAX],
            "clusterSeparation": args.separation,
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


def cmd_harvest(args: argparse.Namespace) -> int:
    """Stream recordings through the extractor into a bounded store, keeping no audio."""
    store = harvest.HarvestStore(Path(args.store), cap=args.cap, seed=args.seed)
    if args.stats:
        log(store.summary())
        return 0

    t0 = time.time()
    if args.from_dir:
        log(f"harvesting from {args.from_dir} (no network)")
        report = harvest.harvest_directory(
            store, Path(args.from_dir), max_seconds=args.max_seconds, species_id=args.species
        )
    else:
        key = args.xc_key or os.environ.get("XC_API_KEY", "")
        try:
            client = harvest.XenoCanto(key, pause=args.pause)
        except RuntimeError as exc:
            log(str(exc))
            return 2
        inventory = load_inventory(Path(args.inventory))
        if args.query:
            targets = [(args.species or "unlabelled", args.query)]
        else:
            targets = harvest.species_queries(inventory, quality=args.quality)
            if args.species:
                targets = [t for t in targets if t[0] == args.species]
                if not targets:
                    log(f"no species {args.species!r} in {args.inventory}")
                    return 2
        log(f"harvesting {len(targets)} species, up to {args.per_species} recordings each")
        try:
            report = harvest.harvest_xeno_canto(
                store,
                client,
                targets,
                per_species=args.per_species,
                max_seconds=args.max_seconds,
                max_pages=args.max_pages,
                dry_run=args.dry_run,
            )
        except RuntimeError as exc:
            log(str(exc))
            return 2

    if args.dry_run:
        log(f"\ndry run: {report.recordings} recordings would be fetched, nothing written")
        return 0
    store.save()
    log(harvest.format_report(report, store))
    log(f"\nstore written to {store.root} in {time.time() - t0:.1f}s "
        f"(attribution in {store.root / 'CREDITS.md'})")
    log("next: uv run birdy-pipeline build --harvest-store " + str(store.root))
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    """Fit syllables and syntax to the harvested observations, and check the model sings them."""
    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    inventory = load_inventory(Path(args.inventory))
    calibration = ensure_calibration(Path(args.calibration_dir))

    t0 = time.time()
    with_own = sum(1 for o in store.syllables if o.descriptor)
    log(f"fitting {len(store.syllables)} syllable observations from "
        f"{len({o.recording_id for o in store.syllables})} recordings "
        f"({with_own} with their own descriptor)")
    document = learn.build_learned_inventory(
        store.syllables,
        inventory,
        calibration,
        descriptors={
            rid: np.asarray(row, dtype=np.float64)
            for rid, row in store.recording_descriptors.items()
        },
        types=args.types,
        seed=args.seed,
        invert=not args.no_invert,
    )
    if not document["species"]:
        log("no species had enough observations to fit — harvest more recordings")
        return 2

    out = Path(args.out)
    if args.learned_only:
        learn.write_learned_inventory(out, document)
    else:
        # The default keeps the documented calls and adds the fitted ones next to them,
        # so building from this file does not cost the app its citations.
        learn.write_learned_inventory(out, learn.merge_learned_inventory(inventory, document))

    total = sum(len(sp["syllables"]) for sp in document["species"])
    cosines = [
        s["learned"]["resynthesisCosine"]
        for sp in document["species"]
        for s in sp["syllables"]
        if s["learned"]["resynthesisCosine"]
    ]
    log("")
    log(f"wrote {out}: {len(document['species'])} species, {total} learned syllable types "
        f"({time.time() - t0:.1f}s)"
        + ("" if args.learned_only else ", alongside the documented inventory"))
    placed = [
        s["learned"]["nearestOwn"]
        for sp in document["species"]
        for s in sp["syllables"]
        if s.get("learned")
    ]
    if cosines:
        log(f"resynthesis cosine to the source audio: median {np.median(cosines):.3f}, "
            f"worst {min(cosines):.3f} over {len(cosines)} types")
        log(f"  nearest its own type rather than another: {sum(placed)}/{len(placed)}")
        log("  (measured against the harvested syllables themselves, in their own frame:"
            " two real syllables of one type score about 0.78 there, and two of different"
            " types about 0.49. A resynthesis below that second number has not"
            " reproduced the call, whatever its pitch says.)")
    for sp in document["species"]:
        grammar = sp.get("grammar", {})
        log(f"  {sp['id']:26} {len(sp['syllables'])} types, "
            f"{len(grammar.get('transitions', {}))} states, "
            f"example bout {' '.join(sp['songs'][0]['sequence']) or '(none)'}")
    log("")
    log("next: uv run birdy-pipeline build --inventory " + str(out) +
        " --harvest-store " + str(store.root))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Local control surface for the Learn tab. Loopback only — see server.py."""
    from .server import Pipeline, serve

    serve(
        Pipeline(
            store_path=Path(args.store),
            inventory_path=Path(args.inventory),
            learned_path=Path(args.learned),
            out_path=Path(args.out),
        ),
        port=args.port,
    )
    return 0


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


def cmd_thresholds(args: argparse.Namespace) -> int:
    """Re-measure the match ramp the browser uses to say "this is not birdsong".

    `app/src/lib/audio/features.ts` scales every activation by how well the best centroid
    matches, ramping between two constants. Those constants are only meaningful against
    the corpus that is actually shipped: a galaxy of synthetic renders and a galaxy that
    is two thirds field audio put birdsong and noise in different places. This prints
    where each sits now, so the ramp can be set from the measurement instead of from
    memory.
    """
    out = Path(args.out)
    centroids = json.loads((out / "centroids.json").read_text(encoding="utf-8"))
    space = json.loads((out / "feature-space.json").read_text(encoding="utf-8"))
    mean = np.asarray(space["mean"], dtype=float)
    std = np.maximum(np.asarray(space["std"], dtype=float), 1.0e-6)
    vectors = np.stack([np.asarray(c["vector"], dtype=float) for c in centroids["items"]])
    vectors = vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1.0e-12)

    def best_match(descriptor: np.ndarray) -> tuple[float, int]:
        z = features.standardise(descriptor, mean, std)
        z = z / max(float(np.linalg.norm(z)), 1.0e-12)
        scores = vectors @ z
        i = int(np.argmax(scores))
        return float(scores[i]), i

    def best_cosine(descriptor: np.ndarray) -> float:
        return best_match(descriptor)[0]

    def name_of(index: int) -> str:
        item = centroids["items"][index]
        label = item.get("label") or item.get("syllableId") or "?"
        return f"c{index} {item.get('speciesId', '?')} / {label} (n={item.get('count', '?')})"

    rate = features.SAMPLE_RATE
    rng = np.random.default_rng(args.seed)
    seconds = 1.0
    t = np.arange(int(seconds * rate)) / rate
    probes = {
        "1 kHz hum": np.sin(2 * math.pi * 1000.0 * t),
        "white noise": rng.normal(0.0, 1.0, t.size),
        "room tone at -60 dBFS": rng.normal(0.0, 1.0, t.size) * 1.0e-3,
        "silence with a click": np.concatenate([[1.0], np.zeros(t.size - 1)]),
    }
    log("what the corpus says is not birdsong:")
    for name, audio in probes.items():
        d = features.descriptor(syrinx.peak_normalise(audio), rate)
        if d is None:
            log(f"  {name:24} no descriptor")
            continue
        # Naming the winner is the difference between "the matcher is broken" and "one
        # cluster is a bin of wind and rain". Only the second has a fix.
        score, index = best_match(d)
        log(f"  {name:24} {score:.3f}  -> {name_of(index)}")

    # Real birds, from the harvested syllables: this is the case the ramp has to let in.
    store_path = Path(args.store)
    if (store_path / "state.json").exists():
        store = harvest.HarvestStore(store_path)
        rows = [np.asarray(o.descriptor, dtype=float) for o in store.syllables if o.descriptor]
        if rows:
            sample = rows if len(rows) <= args.sample else [
                rows[i] for i in rng.choice(len(rows), args.sample, replace=False)
            ]
            scores = np.array([best_cosine(r) for r in sample])
            log(f"\nreal field syllables (n={len(sample)} of {len(rows)}):")
            for q in (1, 5, 10, 25, 50):
                log(f"  p{q:<3} {np.percentile(scores, q):.3f}")
            log(f"  max  {scores.max():.3f}")
            log("\nMATCH_FLOOR should sit above the loudest thing that is not a bird and "
                "below p10 of the real ones; MATCH_CEILING where a match is unambiguous.")
    else:
        log(f"\nno harvest store at {store_path}: skipping the real-audio side")
    return 0


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

    lo_dim = galaxy.POINT_FEATURE_DIMS
    lo_path = out / "point-features.f32"
    lo = np.zeros((0, lo_dim), dtype=np.float32)
    if not lo_path.exists():
        problems.append("point-features.f32 is missing (rebuild to write it)")
    else:
        lo_raw = lo_path.read_bytes()
        if len(lo_raw) != lo_dim * n * 4:
            problems.append(
                f"point-features.f32 is {len(lo_raw)} bytes, expected {lo_dim * n * 4}"
            )
        else:
            lo = np.frombuffer(lo_raw, dtype="<f4").reshape(n, lo_dim)
            norms = np.linalg.norm(lo, axis=1)
            if not np.all(np.isfinite(lo)):
                problems.append("point-features.f32 contains NaN/inf")
            elif float(np.max(np.abs(norms - 1.0))) > 1e-3:
                problems.append(
                    "point-features.f32 rows are not unit vectors "
                    f"(worst |1-|v|| = {float(np.max(np.abs(norms - 1.0))):.4f})"
                )

    centroids = json.loads((out / "centroids.json").read_text())
    lo_centroids = np.asarray(
        [it.get("featuresLo", []) for it in centroids["items"]], dtype=np.float64
    )
    if lo_centroids.shape != (centroids["k"], lo_dim):
        problems.append(
            f"centroid featuresLo are {lo_centroids.shape}, expected {(centroids['k'], lo_dim)}"
        )
    elif lo.size:
        # The renderer's per-point brightness is only meaningful if a point is closer to
        # its own cluster in the reduced space than to the average cluster. Checking it
        # here is what stops a silently mis-signed PCA from shipping.
        own = np.einsum("ij,ij->i", lo, lo_centroids[np.asarray(points["clusterId"])])
        if float(own.mean()) < float((lo @ lo_centroids.T).mean()) + 0.1:
            problems.append(
                f"point-features.f32 does not separate clusters: mean similarity to own "
                f"centroid {own.mean():.3f} vs {float((lo @ lo_centroids.T).mean()):.3f} to all"
            )
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
    if lo.size:
        own = np.einsum("ij,ij->i", lo, lo_centroids[np.asarray(points["clusterId"])])
        log(f"  point-features    {lo_dim}-d unit rows, mean cosine to own centroid "
            f"{own.mean():.3f} (vs {float((lo @ lo_centroids.T).mean()):.3f} to all)")
    log(f"  clusters          {centroids['k']} x {centroids['dims']}-d, "
        f"sizes {min(it['count'] for it in centroids['items'])}.."
        f"{max(it['count'] for it in centroids['items'])}")
    log(f"  calibration       f0 {cal['f0Range'][0]:.0f}..{cal['f0Range'][1]:.0f} Hz, "
        f"monotonic over {mono * 100:.1f} % of measured beta steps")
    log(f"  ampPP             {amp.min():.3f}..{amp.max():.3f} (peak-to-peak of y/gamma)")
    log(f"  contract 8.6      worst error {worst_f0:.2f} % F0, {worst_amp:.2f} % ampPP")
    log("  confidence mix    " + ", ".join(
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
    b.add_argument("--source", choices=("synthetic", "local", "harvest"), default="synthetic")
    b.add_argument("--harvest-store", default=None,
                   help="also embed a harvested descriptor store alongside --source")
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
    b.add_argument("--separation", type=float, default=galaxy.DEFAULT_SEPARATION,
                   help="push cluster centres this far apart relative to knot size "
                        "(1.0 = the raw projection)")
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

    h = sub.add_parser(
        "harvest",
        help="stream real recordings into a bounded descriptor store (keeps no audio)",
    )
    h.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    h.add_argument("--cap", type=int, default=harvest.DEFAULT_CAP,
                   help="descriptors the store may hold, over all runs (default %(default)s)")
    h.add_argument("--per-species", type=int, default=20, help="recordings per species")
    h.add_argument("--max-seconds", type=float, default=harvest.DEFAULT_MAX_SECONDS,
                   help="analyse at most this much of each recording")
    h.add_argument("--max-pages", type=int, default=3, help="xeno-canto result pages per species")
    h.add_argument("--quality", default="A", help='xeno-canto quality filter, e.g. "A" or ">C"')
    h.add_argument("--xc-key", default=None, help="xeno-canto v3 API key (or set XC_API_KEY)")
    h.add_argument("--query", default=None, help="raw xeno-canto query, instead of the inventory")
    h.add_argument("--species", default=None, help="restrict to one inventory species id")
    h.add_argument("--from-dir", default=None,
                   help="ingest files already on disk instead of downloading")
    h.add_argument("--pause", type=float, default=harvest.XC_PAGE_PAUSE,
                   help="seconds between requests; the service rate-limits")
    h.add_argument("--dry-run", action="store_true", help="list what would be fetched")
    h.add_argument("--stats", action="store_true", help="describe an existing store and exit")
    h.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    h.add_argument("--seed", type=int, default=0)
    h.set_defaults(func=cmd_harvest)

    lrn = sub.add_parser(
        "learn",
        help="fit syllables and syntax to harvested recordings, and verify the resynthesis",
    )
    lrn.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    lrn.add_argument("--out", default=str(DEFAULT_LEARNED_INVENTORY))
    lrn.add_argument("--types", type=int, default=learn.DEFAULT_TYPES,
                     help="syllable types to fit per species (default %(default)s)")
    lrn.add_argument("--inventory", default=str(DEFAULT_INVENTORY),
                     help="used for species names and citations, never overwritten")
    lrn.add_argument("--calibration-dir", default=str(DEFAULT_OUT),
                     help="where syrinx-calibration.json lives")
    lrn.add_argument("--no-invert", action="store_true",
                     help="skip the gesture search and ship the cluster medians as fitted")
    lrn.add_argument("--learned-only", action="store_true",
                     help="write only the fitted repertoire, dropping every documented "
                          "function; the default merges it into the authored inventory")
    lrn.add_argument("--seed", type=int, default=0)
    lrn.set_defaults(func=cmd_learn)

    s = sub.add_parser(
        "serve", help="local control surface for the app's Learn tab (loopback only)"
    )
    s.add_argument("--port", type=int, default=8781)
    s.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    s.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    s.add_argument("--learned", default=str(DEFAULT_LEARNED_INVENTORY))
    s.add_argument("--out", default=str(DEFAULT_OUT))
    s.set_defaults(func=cmd_serve)

    d = sub.add_parser("demo", help="render a few example wavs for listening")
    d.add_argument("--wav-out", default=str(DEFAULT_DEMO_OUT))
    d.add_argument("--out", default=str(DEFAULT_OUT), help="where the calibration lives")
    d.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    d.add_argument("--seed", type=int, default=0)
    d.set_defaults(func=cmd_demo)

    v = sub.add_parser("verify", help="check a generated asset directory")
    v.add_argument("--out", default=str(DEFAULT_OUT))
    v.set_defaults(func=cmd_verify)

    th = sub.add_parser("thresholds", help="re-measure the browser's match ramp on the shipped assets")
    th.add_argument("--out", default=str(DEFAULT_OUT))
    th.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    th.add_argument("--sample", type=int, default=2000, help="field syllables to score")
    th.add_argument("--seed", type=int, default=0)
    th.set_defaults(func=cmd_thresholds)
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
