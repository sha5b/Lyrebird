"""`birdy-pipeline` command line: build, calibrate, demo, verify."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
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
DEFAULT_DISCOVERED = REPO_ROOT / "data" / "discovered-species.json"
DEFAULT_CRITIC = REPO_ROOT / "pipeline" / "out" / "critic.pt"
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


def warn_if_stale_inventory(chosen: Path) -> None:
    """Say so when `learn` has written a newer inventory than the one being built.

    **A build is only as current as its input, and its input is a file another command
    rewrites underneath it.** `learn` refits `data/learned-inventory.json` from scratch on
    every run, and `build` defaults to the hand-authored `data/inventory.json`; so the
    ordinary way to use this pipeline — learn, then build — quietly produces a galaxy with
    none of the learning in it, and the ordinary way to use it *twice* produces a galaxy
    built from a fit that has since been replaced. Neither said anything.

    It warns rather than switching the input, because which inventory to build is a claim
    about what the galaxy contains, and guessing it would be the pipeline overruling an
    explicit flag. Loud is enough; silent was the problem.
    """
    learned = DEFAULT_LEARNED_INVENTORY
    if not learned.exists():
        return
    try:
        chosen_resolved = chosen.resolve()
    except OSError:
        return
    if chosen_resolved == learned.resolve():
        return
    when = datetime.fromtimestamp(learned.stat().st_mtime, timezone.utc)
    log(
        f"NOTE: building from {chosen.name}, but {learned.name} was written "
        f"{when.isoformat(timespec='seconds')} and holds the fitted repertoire. "
        f"Use --inventory {learned} to include it."
    )


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
    warn_if_stale_inventory(inventory_path)
    calibration = ensure_calibration(out, force=args.recalibrate)

    # **The rendered inventory is not one option among several — it is the frame.**
    #
    # This used to be a choice: `--source synthetic` OR `harvest` OR `local`, and the harvest
    # store folded in only if you remembered the second flag. That framing is wrong, and it
    # has a measured cost: `--source harvest` produces a galaxy in which not one cluster
    # carries a syllable name, so nothing the app sings can light a knot, draw a path or be
    # labelled — a corpus with no anchor cannot identify anything. The rendered clips are what
    # carry the names, the functions and the citations; the field audio is what fills in the
    # shape of the real repertoire around them and is *identified by* them.
    #
    # So the composition is additive and the anchor is always present. What accumulates is one
    # corpus: the current inventory rendered, plus every descriptor the harvest has kept, plus
    # a local directory if one is given. `--no-synthetic` still exists because looking at the
    # field audio on its own is a legitimate diagnostic, and it says loudly what it costs.
    render_synthetic = not args.no_synthetic
    if args.source == "harvest":
        log("NOTE: --source harvest is now --no-synthetic; the rendered anchor is otherwise "
            "always included, because a galaxy without it can name nothing")
        render_synthetic = False
    if render_synthetic:
        report_reachability(inventory, calibration)

    parts: list[PointSet] = []
    harvest_info: dict[str, Any] | None = None
    # Per-recording metadata (call type, sample rate, recordist, country, date...) so the
    # build can test which of them the geometry actually corresponds to.
    harvest_recordings: dict[str, Any] = {}

    if render_synthetic:
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

    # Additive, not exclusive: a local directory sits alongside the rendered anchor.
    if args.source == "local" or args.audio_dir:
        if not args.audio_dir:
            log("--source local requires --audio-dir")
            return 2
        log(f"reading local corpus from {args.audio_dir}")
        clips = local_corpus(Path(args.audio_dir))
        log(f"corpus: {len(clips)} clips, {sum(c.duration for c in clips):.1f} s of audio")
        if args.wav_out:
            dump_clip_wavs(clips, Path(args.wav_out))
        parts.append(galaxy.descriptors(clips, should_stop=should_stop))

    # Always, when there is one. Everything collected stays in the corpus; the point of
    # harvesting is that it accumulates, and a build that silently left it out was a build
    # that threw away every recording since the last time someone typed the flag.
    store_path = Path(args.harvest_store or DEFAULT_HARVEST_STORE)
    if (store_path / "state.json").exists() and not args.no_harvest:
        store = harvest.HarvestStore(store_path)
        field = store.to_point_set()
        log(f"harvest store {store_path}: {len(field)} field descriptors "
            f"from {len(store.recordings)} recordings")
        rep = store.representativeness()
        harvest_recordings = dict(store.recordings)
        harvest_info = {
            "store": str(store_path),
            "points": len(field),
            "recordings": len(store.recordings),
            "descriptorsSeen": store.stream_n,
            "sampleDrift": {k: round(v, 4) for k, v in rep.items()},
        }
        parts.append(field)

    if not parts:
        log("nothing to embed: no rendered inventory, no harvest store, no local corpus")
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
        clustering=args.clustering,
        min_cluster_size=args.min_cluster_size,
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
        recordings=harvest_recordings,
        test_relations=not args.no_relations,
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
    # Milliseconds, and it guards the two failures in this module that are silent: a cap that
    # drops whole species, and a lightweight store that saves an empty corpus over a real one.
    harvest.self_test(verbose=False)
    store = harvest.HarvestStore(
        Path(args.store), cap=args.cap, seed=args.seed,
        syllable_cap=getattr(args, "syllable_cap", harvest.DEFAULT_SYLLABLE_CAP),
    )
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
            discovered = harvest.load_discovered(DEFAULT_DISCOVERED)
            if args.discover:
                genera = sorted(
                    {sp["scientific"].split()[0]
                     for sp in inventory.get("species", [])
                     if sp.get("scientific")}
                )
                known = {sp["id"] for sp in inventory.get("species", [])} | {
                    e["id"] for e in discovered
                }
                found = harvest.discover_species(
                    client, known, limit=args.discover, query=args.discover_query,
                    genera=genera, max_pages=args.discover_pages,
                )
                if found:
                    discovered = [*discovered, *found]
                    harvest.save_discovered(DEFAULT_DISCOVERED, discovered)
                    log(f"added {len(found)} species to {DEFAULT_DISCOVERED.name}; "
                        f"{len(discovered)} discovered in total")
                else:
                    log("no new species found")
            if discovered:
                log(f"including {len(discovered)} discovered species: "
                    + ", ".join(e["id"] for e in discovered[:6])
                    + (f", +{len(discovered) - 6}" if len(discovered) > 6 else ""))
            targets = harvest.species_queries(
                inventory, quality=args.quality, extra=discovered
            )
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
                max_length_seconds=args.max_length,
                clean_only=args.clean_only,
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


def cmd_grow(args: argparse.Namespace) -> int:
    """Add the harvest store's newest descriptors to the built galaxy, in place.

    The corpus stops arriving as a discontinuity: existing points keep their coordinates
    and the cloud gains marks around them. What it cannot do is discover a cluster — new
    audio joins the nearest existing knot — so the drift figures it prints are the signal
    for when a real rebuild is due.
    """
    from datetime import datetime, timezone

    from . import grow

    out = Path(args.out)
    store_path = Path(args.harvest_store or DEFAULT_HARVEST_STORE)
    store = harvest.HarvestStore(store_path)
    field = store.to_point_set()
    if not len(field):
        log("the harvest store is empty; nothing to add")
        return 1

    points = json.loads((out / "points.json").read_text(encoding="utf-8"))
    total = int(points["n"])
    # **Count the field points, not all of them.** This compared the store's descriptor
    # count against the galaxy's *total* point count, and a mixed build's total includes
    # ~12000 synthetic renders — so `take` came out negative and `grow --only-new` reported
    # "nothing new to add" on every run, forever. The loop's third step was a no-op from the
    # day the harvest joined the corpus, which is why an hour of learning left the galaxy
    # at exactly the size it started.
    have = sum(1 for s in points.get("source", []) if s == "field") or 0
    take = len(field) - have if args.only_new else len(field)
    if take <= 0:
        log(f"the galaxy holds {have} field points of {total} and the store has "
            f"{len(field)}; nothing new to add")
        # A capped reservoir does not grow, it *replaces*: Algorithm R swaps random slots,
        # so once the store is full the descriptors that changed are not a suffix and no
        # append can express them. Saying so is the difference between "nothing happened"
        # and "nothing can happen this way" — the second one means rebuild.
        if len(field) >= getattr(store, "cap", 0) > 0:
            log(f"the store is at its cap of {store.cap}, so new audio replaces old rather "
                "than adding to it — only a rebuild can take it in")
        return 0
    fresh = galaxy.PointSet(
        x=field.x[-take:],
        species_id=field.species_id[-take:],
        syllable_id=field.syllable_id[-take:],
        song_id=field.song_id[-take:],
        duration=field.duration[-take:],
        source=field.source[-take:],
    )
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # The newest fitted repertoire rides along, so a grown point that belongs to a syllable
    # or a species the shipped inventory has never seen arrives with a voice.
    inventory_path = Path(args.inventory)
    result = grow.extend_build(out, fresh, stamp, inventory_path=inventory_path)
    log(f"generation {result['generation']}: {result['points']} points")
    if result["drift"]["unmatched"] > 0.35:
        log("more than a third of the new audio matched no existing knot — "
            "the arrangement no longer describes its own contents; rebuild")
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    """Fit syllables and syntax to the harvested observations, and check the model sings them."""
    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    inventory = load_inventory(Path(args.inventory))
    calibration = ensure_calibration(Path(args.calibration_dir))
    # Cheap, and it checks the one property that would otherwise fail silently: that a fit
    # with no critic is bit-identical to the one that shipped before the critic existed.
    features.self_test(verbose=False)
    learn.self_test(verbose=False)

    t0 = time.time()
    with_own = sum(1 for o in store.syllables if o.descriptor)
    log(f"fitting {len(store.syllables)} syllable observations from "
        f"{len({o.recording_id for o in store.syllables})} recordings "
        f"({with_own} with their own descriptor)")

    # The two learned components of docs/09, independently switchable. `--critic` alone
    # changes the *objective*; `--embed-typing` changes what a syllable *type* is. Neither is
    # on by default, so the numbers in the plan's results table stay comparable.
    trained = load_critic(args.critic, prefer_gpu=not args.cpu)
    if trained is None and (args.embed_typing or args.critic_weight > 0.0):
        log("no critic loaded, so --embed-typing and --critic-weight have no effect; "
            "fitting against the 28-d cosine with the hand-written typing vector")
    realism, embedder = learned_components(
        trained, store.syllables, args.critic_weight, args.embed_typing
    )

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
        embedder=embedder,
        realism=realism,
        use_tube=args.use_tube,
        # Inherit the ids the last fit used, so `L03` keeps naming the same sound. See
        # `learn.assign_ids`: renumbering was why a refitted bird sang something new and lit
        # a cluster that had been fitted to something else.
        prior=learn.previous_fit(Path(args.out)),
        # Where a discovered bird's common name is. Without it every species that is not in
        # the authored inventory is called by its own id everywhere in the app.
        discovered=harvest.load_discovered(DEFAULT_DISCOVERED),
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


#: Fallback copies of `critic.CriticConfig`'s defaults, for building the parser on a machine
#: with no torch. The parser is constructed on *every* invocation, including `build` and
#: `verify`, so it cannot import `critic`. `critic_default` prefers the real dataclass when it
#: is importable and only falls back to this table, which keeps the two in step wherever it
#: matters and keeps `--help` honest wherever it does not.
_CRITIC_FALLBACK_DEFAULTS: dict[str, Any] = {
    "epochs": 60,
    "batch": 256,
    "lr": 2.0e-3,
    "w_real": 1.0,
    "w_species": 0.3,
    "w_contrast": 0.5,
    "holdout_species": 0.25,
    "renders_per_type": 32,
}


def critic_default(name: str) -> Any:
    try:
        from .critic import CriticConfig

        return getattr(CriticConfig(), name)
    except ImportError:
        return _CRITIC_FALLBACK_DEFAULTS[name]


def load_critic(path: str | None, prefer_gpu: bool = True) -> Any | None:
    """A trained critic, or `None` with a printed reason. Never raises on a missing torch.

    Every caller of this must work without it (docs/09 §9.4), so a machine that has not
    installed the `critic` extra gets a message and the hand-written objective rather than a
    stack trace.
    """
    if not path:
        return None
    try:
        from . import critic as critic_mod
    except ImportError as exc:
        log(f"cannot load {path}: {exc}. Install the extra with `uv sync --extra critic`, "
            f"or drop --critic to fit against the 28-d cosine alone.")
        return None
    p = Path(path)
    if not p.exists():
        log(f"no critic at {p} — train one with `birdy-pipeline critic train`")
        return None
    trained = critic_mod.Critic.load(p, prefer_gpu=prefer_gpu)
    r = trained.report
    log(f"critic {p.name}: {len(trained.names)} training species, realism AUC "
        f"{r.realism_auc_holdout or r.realism_auc_train:.3f}, species accuracy "
        f"{r.species_accuracy:.3f}, on {critic_mod.describe_device(trained.device)}")
    return trained


def learned_components(
    trained: Any | None,
    observations: Any,
    critic_weight: float,
    embed_typing: bool,
) -> tuple[Any | None, Any | None]:
    """`(realism, embedder)` for `build_learned_inventory`, with every fallback taken here.

    One function because `cmd_learn` and the server's Learn-tab fit have to agree, and because
    the fallbacks are the whole contract: the learned path is a *preference*, and anything
    missing — torch, a trained critic, patches in the store — has to land on the hand-written
    objective with a logged reason rather than a traceback.

    The patch check is the one that bites. `out/harvest` is 39 979 observations gathered before
    `features.mel_patch` existed and it is the default store, so switching the interface to
    embedding typing without this turned its fit button into a `ValueError`.
    """
    if trained is None:
        return None, None

    realism = learn.RealismTerm(trained, critic_weight) if critic_weight > 0.0 else None
    embedder = None
    if embed_typing:
        with_patch = sum(1 for o in observations if o.mel_patch is not None)
        if with_patch == 0:
            log("this store holds no log-mel patches, so syllable types will be clustered "
                "with the hand-written vector. Patches are recorded at harvest time and "
                "cannot be recovered afterwards — the audio is gone by design — so this "
                "needs a harvest into a new store to change.")
        else:
            embedder = learn.critic_embedder(trained)
            if with_patch < len(observations):
                log(f"typing in the learned embedding; {len(observations) - with_patch} of "
                    f"{len(observations)} observations have no patch and will sit at its "
                    f"centre rather than be dropped")
            else:
                log(f"typing in the learned embedding ({with_patch} patches)")
    return realism, embedder


def cmd_critic(args: argparse.Namespace) -> int:
    """Train the learned critic of docs/09 §9.3 and measure novelty detection honestly."""
    try:
        from . import critic as critic_mod
    except ImportError as exc:
        log(f"torch is not installed ({exc}). `uv sync --extra critic` and try again.")
        return 2

    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    with_patch = sum(1 for o in store.syllables if o.mel_patch is not None)
    if not with_patch:
        log(f"{store.root} holds {len(store.syllables)} observations but no mel patches. "
            f"The store predates the critic; re-harvest into a *new* store — and never "
            f"delete out/harvest, it is the only copy (docs/09 §9.4).")
        return 2
    log(f"{with_patch}/{len(store.syllables)} observations carry a "
        f"{features.PATCH_SHAPE[0]}x{features.PATCH_SHAPE[1]} patch")

    inventory = load_inventory(Path(args.inventory))
    calibration = ensure_calibration(Path(args.calibration_dir))

    t0 = time.time()
    real = critic_mod.real_patches(store.syllables)
    log(f"real side: {len(real)} patches over {len(real.names)} species")

    # The synthetic side is rendered *now*, from the inventory as it currently stands. That is
    # what makes the alternation of §9.3 step 6 meaningful: refit with the critic, retrain the
    # critic against the new resyntheses, repeat. A critic beaten once will find a new tell.
    shown: set[str] = set()

    def note(species_id: str, total: int) -> None:
        if species_id not in shown:
            shown.add(species_id)
            log(f"  rendering {species_id} ({total} patches so far)")

    fake = critic_mod.fake_patches(
        inventory, calibration, real.names,
        per_type=args.renders_per_type, seed=args.seed,
        progress=note if args.verbose else None,
    )
    log(f"synthetic side: {len(fake)} patches from the fitted inventory "
        f"({args.renders_per_type} renders per type) in {time.time() - t0:.1f}s")

    config = critic_mod.CriticConfig(
        epochs=args.epochs,
        batch=args.batch,
        lr=args.lr,
        w_real=args.w_real,
        w_species=args.w_species,
        w_contrast=args.w_contrast,
        holdout_species=args.holdout_species,
        seed=args.seed,
        renders_per_type=args.renders_per_type,
        prefer_gpu=not args.cpu,
    )
    trained = critic_mod.train(real, fake, config, log=log)
    novelty = critic_mod.fit_novelty(
        trained, real, target_false_positive=args.false_positive, seed=args.seed
    )

    out = Path(args.out)
    trained.save(out)
    novelty.save(out.with_name(out.stem + "-novelty.json"))

    r, n = trained.report, novelty.report
    log("")
    log(f"wrote {out} and {out.with_name(out.stem + '-novelty.json')} "
        f"({time.time() - t0:.1f}s total)")
    log("")
    log("**Realism** — can it tell our resynthesis from a real recording?")
    log(f"  on species it trained on:  AUC {r.realism_auc_train:.3f}")
    log(f"  on species held out:       AUC {r.realism_auc_holdout:.3f}   <- the honest one")
    log("  (0.5 is chance. A high held-out AUC means the gap it found generalises, which is")
    log("   what makes it usable as an objective. If held-out is near chance while train is")
    log("   high, it memorised the training birds and the objective would teach the fit"
        " nothing.)")
    log("")
    log("**Species** — is the embedding grounded in something externally true?")
    log(f"  accuracy {r.species_accuracy:.3f} on held-back syllables of training species "
        f"(chance {r.species_chance:.3f})")
    log("")
    log("**Embedding** — does it retrieve an augmented view of the same syllable?")
    log(f"  top-1 {r.contrastive_top1:.3f} out of 256 candidates (chance 0.004)")
    log("")
    log("**Novelty** — 'is this a syllable I have not heard?' (docs/09 §9.2b use 2)")
    if n.n_novel:
        log(f"  ROC AUC {n.auc:.3f} separating {n.n_novel} syllables of entirely held-out "
            f"species from {n.n_known} held-back syllables of known ones")
        log(f"  at threshold {n.threshold:.4f}: {n.true_positive_rate:.1%} of genuinely new "
            f"syllables flagged, {n.false_positive_rate:.1%} false positives "
            f"(asked for {n.target_false_positive:.0%})")
    else:
        log(f"  not measured: --holdout-species {args.holdout_species} left no species out, "
            f"so there is nothing genuinely novel to test against. The threshold "
            f"({n.threshold:.4f}) is calibrated but its detection rate is unknown.")
    log("")
    log("A syllable flagged novel is still `unlabelled` (§8.5): knowing a sound is new is not")
    log("knowing what it means, and the interface has to keep saying so.")
    log("")
    log(f"next: uv run birdy-pipeline learn --store {store.root} --critic {out} --embed-typing")
    log("      then: uv run birdy-pipeline placement --store " + str(store.root) +
        " --inventory <the fit you just wrote>")
    log("")
    log("Note the flag that is *not* in that line. `--critic-weight` defaults to 0 because a")
    log("swept realism term measured worse at every weight above it; the embedding is what")
    log("earns its place. See the note on `--critic-weight` in cli.py for the numbers.")
    return 0


def cmd_placement(args: argparse.Namespace) -> int:
    """Score a fitted inventory on the four numbers of docs/09 §9.3, all at once.

    **The headline one, `nearest own species`, could not be measured before this command.**
    `learn` reports whether a resynthesis lands nearer its own *type* than another type of the
    same bird, which is a within-species question. docs/09's complaint is between species —
    "three quarters of fitted syllables still resynthesise closer to a *different* bird than to
    their own" — and that is the number that stuck at 23.1 % while everything else improved.
    Comparing two fits on it is the whole point of the exercise, so it needs to be one command
    against a written inventory rather than a number recomputed by hand each time.
    """
    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations")
        return 2
    inventory = load_inventory(Path(args.inventory))
    calibration = ensure_calibration(Path(args.calibration_dir))

    # The same frame `learn` judges in: centred on the harvested population, not on a
    # synthetic build. See `learn.population_frame` for why that distinction decides whether
    # the cosines mean anything at all.
    frame = learn.population_frame(store.syllables)
    by_species: dict[str, list[np.ndarray]] = {}
    for o in store.syllables:
        if o.descriptor:
            by_species.setdefault(o.species_id, []).append(np.asarray(o.descriptor, dtype=float))
    references: dict[str, np.ndarray] = {}
    for sid, rows in by_species.items():
        mean_row = np.mean(np.stack(rows), axis=0)
        if frame is not None:
            mean_row = features.standardise(mean_row, frame[0], frame[1])
        references[sid] = mean_row / max(float(np.linalg.norm(mean_row)), 1e-12)
    if len(references) < 2:
        log("need at least two species with per-syllable descriptors to place anything")
        return 2

    names = sorted(references)
    matrix = np.stack([references[n] for n in names])

    rows: list[tuple[str, str, bool, bool, float, float]] = []
    for species in inventory.get("species", []):
        sid = species.get("id", "")
        if sid not in references:
            continue
        # Per-type references, for the within-species question, in the same frame.
        learned_types = [s for s in species.get("syllables", []) if s.get("learned")]
        for syllable in learned_types:
            audio = peak_normalise(
                render_syllable(syllable, calibration=calibration)
            )
            d = features.descriptor(audio)
            if d is None:
                continue
            if frame is not None:
                d = features.standardise(d, frame[0], frame[1])
            z = d / max(float(np.linalg.norm(d)), 1e-12)
            sims = matrix @ z
            own_species = names[int(np.argmax(sims))] == sid

            learned = syllable.get("learned", {})
            rows.append((
                sid,
                syllable.get("id", ""),
                own_species,
                bool(learned.get("nearestOwn")),
                float(learned.get("resynthesisCosine") or 0.0),
                abs(float(learned.get("f0ErrorPercent") or 0.0)),
            ))

    if not rows:
        log(f"{args.inventory} has no learned syllables for any species in {store.root}")
        return 2

    placed_species = sum(1 for r in rows if r[2])
    placed_type = sum(1 for r in rows if r[3])
    cosines = [r[4] for r in rows if r[4]]
    errors = [r[5] for r in rows]
    chance = 1.0 / len(names)

    log("")
    log(f"{Path(args.inventory).name}: {len(rows)} learned types over "
        f"{len({r[0] for r in rows})} species, placed against {len(names)} species references")
    log("")
    log(f"{'metric':44} {'measured':>12} {'docs/09 target':>16}")
    log(f"{'nearest own SPECIES':44} "
        f"{placed_species / len(rows):11.1%} {'> 35 %':>16}")
    log(f"{'  (chance)':44} {chance:11.1%} {'':>16}")
    log(f"{'nearest own type':44} {placed_type / len(rows):11.1%} {'>= 56 %':>16}")
    log(f"{'median resynthesis cosine':44} "
        f"{(np.median(cosines) if cosines else float('nan')):11.3f} {'>= 0.74':>16}")
    log(f"{'median |F0 error|':44} "
        f"{np.median(errors):10.1f} % {'<= 5 %':>16}")
    log("")
    log("A rise in species placement *with* the cosine roughly held is the win condition.")
    log("A rise in placement with the cosine collapsing means the critic is being gamed —")
    log("check by ear (docs/09 §9.3).")

    if args.per_species:
        log("")
        log(f"{'species':28} {'types':>6} {'own species':>12} {'own type':>9} {'cosine':>8}")
        for sid in sorted({r[0] for r in rows}):
            mine = [r for r in rows if r[0] == sid]
            cos = [r[4] for r in mine if r[4]]
            log(f"{sid:28} {len(mine):6d} "
                f"{sum(1 for r in mine if r[2]) / len(mine):11.0%} "
                f"{sum(1 for r in mine if r[3]) / len(mine):8.0%} "
                f"{(np.median(cos) if cos else float('nan')):8.3f}")
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
            critic_path=Path(args.critic) if args.critic else None,
            critic_weight=args.critic_weight,
            embed_typing=args.embed_typing,
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
    b.add_argument(
        "--source",
        choices=("synthetic", "local", "harvest"),
        default="synthetic",
        help="kept for compatibility; the rendered inventory is always included unless "
             "--no-synthetic, and `harvest` is an alias for it",
    )
    b.add_argument(
        "--no-synthetic",
        action="store_true",
        help="diagnostic: leave the rendered inventory out. The result can name nothing, so "
             "the app cannot light, label or draw a path for anything it sings",
    )
    b.add_argument(
        "--no-harvest",
        action="store_true",
        help="diagnostic: leave the harvested field audio out, for a galaxy of the "
             "documented repertoire alone",
    )
    b.add_argument("--harvest-store", default=None,
                   help="where the harvested descriptor store lives (included by default)")
    b.add_argument("--audio-dir", default=None, help="corpus root for --source local")
    b.add_argument("--variants", type=int, default=96, help="renders per syllable")
    b.add_argument("--song-variants", type=int, default=3, help="renders per song")
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--k", type=int, default=None, help="clusters (default: syllable types)")
    b.add_argument(
        "--clustering",
        choices=("kmeans", "hdbscan"),
        default="kmeans",
        help="kmeans fits exactly --k groups and puts every point in one of them; "
             "hdbscan discovers how many dense regions there are and leaves the rest "
             "unassigned, which is the only way a sound can come out as 'none of these'",
    )
    b.add_argument(
        "--min-cluster-size",
        type=int,
        default=25,
        help="hdbscan: fewest points that may be called a syllable type (default %(default)s)",
    )
    b.add_argument("--out", default=str(DEFAULT_OUT))
    b.add_argument("--wav-out", default=None, help="also write every clip as a wav")
    # **The accumulating inventory, not the hand-authored one.**
    #
    # `learn` merges its fitted types *onto* the authored ones and writes the result here, so
    # `learned-inventory.json` is a superset: every documented call with its function and
    # citation, plus everything fitted from field audio. Defaulting to the authored file meant
    # the ordinary sequence — harvest, learn, build — produced a galaxy with none of the
    # learning in it, and there was no reading of that which was what anybody wanted.
    b.add_argument(
        "--inventory",
        default=str(DEFAULT_LEARNED_INVENTORY if DEFAULT_LEARNED_INVENTORY.exists()
                    else DEFAULT_INVENTORY),
        help="inventory to render; defaults to the learned superset when it exists",
    )
    b.add_argument(
        "--no-relations",
        action="store_true",
        help="skip the permutation tests that say which groupings the geometry corresponds "
             "to; they are the only part of a build that is analysis rather than output",
    )
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
    # Exposed because it silently decides how much of the *learning* set survives, and it was
    # only reachable in Python. A harvest that grew `out/harvest-gan` past this evicted whole
    # recordings to stay under it; the eviction is now species-stratified (`add_syllables`), but
    # the ceiling is still a ceiling, and a corpus that wants 25 species at depth needs to be
    # told it may hold more than 40 000 syllables.
    h.add_argument("--syllable-cap", type=int, default=harvest.DEFAULT_SYLLABLE_CAP,
                   help="syllable observations the store may hold, over all runs. These are "
                        "what `learn` fits and what carries the log-mel patches, so this is "
                        "the ceiling on the learning set (default %(default)s)")
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
    h.add_argument(
        "--max-length",
        type=float,
        default=harvest.DEFAULT_MAX_LENGTH_SECONDS,
        help="decline recordings longer than this many seconds before downloading them "
             "(0 disables); xeno-canto reports the duration in the search result",
    )
    h.add_argument(
        "--clean-only",
        action="store_true",
        help="skip recordings with other species audible in them, which xeno-canto lists "
             "in its `also` field — the contamination the descriptor space is most sensitive to",
    )
    h.add_argument(
        "--discover",
        type=int,
        default=0,
        metavar="N",
        help="before harvesting, find up to N species xeno-canto has that the inventory does "
             "not — by default congeners of the birds already modelled — and add them to "
             "data/discovered-species.json so every later run collects them too",
    )
    h.add_argument(
        "--discover-pages",
        type=int,
        default=1,
        help="pages of each genus query to read while discovering. One page is 100 "
             "recordings, which for a common genus is a shallow look at it — raise this to "
             "reach the less-recorded congeners a single page never shows",
    )
    h.add_argument(
        "--discover-query",
        default=None,
        help="raw xeno-canto query to discover from, instead of the genus sweep",
    )
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
    # --- the learned components of docs/09. Both off by default. ---
    lrn.add_argument("--critic", default=None,
                     help="trained critic (out/critic.pt) whose realism logit joins the "
                          "objective; see `critic train`")
    # **Defaults to 0, and that is a measured decision rather than caution.** Swept on
    # out/harvest-gan (25 species, 9041 syllables) with the typing held fixed, the realism
    # term made every number worse the more of it there was: species placement 26.6 % at
    # W=0, 27.2 % at 0.25, 23.7 % at 0.5, 17.3 % at 1.0, with the cosine falling 0.762 ->
    # 0.686 -> 0.655 -> 0.335. The collapse at W=1 is docs/09 §9.5's "the fit games the
    # critic" happening exactly as predicted, and the guardrail cosine is what made it
    # visible. The critic is worth having — see --embed-typing, which is a clear win — but
    # not as a term in this objective.
    lrn.add_argument("--critic-weight", type=float, default=0.0, metavar="W",
                     help="share of the objective the critic gets: "
                          "score = (1-W)*cosine + W*realism. Measured harmful at every "
                          "W > 0 tried, so the default is 0; raise it only to re-run that "
                          "sweep (default %(default)s)")
    lrn.add_argument("--embed-typing", action="store_true",
                     help="cluster syllable types in the critic's learned 32-d embedding "
                          "instead of the seven hand-weighted numbers of "
                          "`learn._observation_vector`. **This is the part that works**: "
                          "species placement 26.6 %% -> 32.9 %% with the cosine held at "
                          "0.755 and F0 error 5.4 %% -> 3.1 %%. Changes what a type *is*, "
                          "so it renumbers unless the id-inheritance path holds")
    lrn.add_argument("--use-tube", action="store_true",
                     help="re-enable the waveguide tract, gated off because the 28-d "
                          "objective rejected it. Turning this on together with --critic is "
                          "the plan's own test of whether the learned objective is better")
    lrn.add_argument("--cpu", action="store_true",
                     help="run the critic on the CPU even where a GPU is available")
    lrn.set_defaults(func=cmd_learn)

    cr = sub.add_parser(
        "critic",
        help="train the learned critic: a realism objective, a syllable embedding, and "
             "novelty detection (docs/09)",
    )
    cr_sub = cr.add_subparsers(dest="critic_command", required=True)
    crt = cr_sub.add_parser(
        "train",
        help="train on harvested patches against the current fitted inventory",
    )
    crt.add_argument("--store", default=str(DEFAULT_HARVEST_STORE),
                     help="harvest store holding the real log-mel patches")
    crt.add_argument("--inventory", default=str(DEFAULT_LEARNED_INVENTORY),
                     help="the fitted inventory whose renders are the synthetic side")
    crt.add_argument("--out", default=str(DEFAULT_CRITIC))
    crt.add_argument("--calibration-dir", default=str(DEFAULT_OUT))
    crt.add_argument("--epochs", type=int, default=critic_default("epochs"))
    crt.add_argument("--batch", type=int, default=critic_default("batch"))
    crt.add_argument("--lr", type=float, default=critic_default("lr"))
    crt.add_argument("--renders-per-type", type=int, default=critic_default("renders_per_type"),
                     help="synthetic patches per fitted type, each with its own jitter and "
                          "noise stream (default %(default)s)")
    crt.add_argument("--w-real", type=float, default=critic_default("w_real"),
                     help="weight on the real-vs-synthetic head")
    crt.add_argument("--w-species", type=float, default=critic_default("w_species"),
                     help="weight on the species head, which grounds the embedding")
    crt.add_argument("--w-contrast", type=float, default=critic_default("w_contrast"),
                     help="weight on the contrastive head, which is what makes the "
                          "embedding useful for typing")
    crt.add_argument("--holdout-species", type=float,
                     default=critic_default("holdout_species"), metavar="FRACTION",
                     help="species held out of training entirely. Species and not "
                          "syllables: it is what stops the critic reporting identity where "
                          "realism was asked for, and it is the only honest way to measure "
                          "novelty (default %(default)s)")
    crt.add_argument("--false-positive", type=float, default=0.05, metavar="RATE",
                     help="novelty false-positive rate to calibrate the threshold to, so it "
                          "is chosen rather than discovered (default %(default)s)")
    crt.add_argument("--seed", type=int, default=0)
    crt.add_argument("--cpu", action="store_true", help="train on the CPU even with a GPU present")
    crt.add_argument("--quiet", dest="verbose", action="store_false",
                     help="do not log each species as its synthetic side renders")
    crt.set_defaults(func=cmd_critic, verbose=True)

    pl = sub.add_parser(
        "placement",
        help="score a fitted inventory on docs/09's four numbers, including the one `learn` "
             "cannot report: whether a resynthesis lands nearest its own *species*",
    )
    pl.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    pl.add_argument("--inventory", default=str(DEFAULT_LEARNED_INVENTORY))
    pl.add_argument("--calibration-dir", default=str(DEFAULT_OUT))
    pl.add_argument("--per-species", action="store_true",
                    help="also break the placement down species by species")
    pl.set_defaults(func=cmd_placement)

    g = sub.add_parser(
        "grow",
        help="add the harvest store's newest audio to the built galaxy without rebuilding",
    )
    g.add_argument("--out", default=str(DEFAULT_OUT), help="built asset directory")
    g.add_argument("--harvest-store", default=None)
    # Defaults to the fitted repertoire rather than the authored one: a grow only ever adds
    # field audio, and field audio is what `learn` names.
    g.add_argument(
        "--inventory",
        default=str(DEFAULT_LEARNED_INVENTORY),
        help="inventory to copy alongside the grown points, so new voices arrive with them",
    )
    g.add_argument(
        "--all",
        dest="only_new",
        action="store_false",
        help="re-add every descriptor in the store, not just the ones past the "
             "galaxy's current count",
    )
    g.set_defaults(func=cmd_grow, only_new=True)

    s = sub.add_parser(
        "serve", help="local control surface for the app's Learn tab (loopback only)"
    )
    s.add_argument("--port", type=int, default=8781)
    s.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    s.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    s.add_argument("--learned", default=str(DEFAULT_LEARNED_INVENTORY))
    s.add_argument("--out", default=str(DEFAULT_OUT))
    # Off unless asked for, so `serve` behaves exactly as it did until someone opts in.
    # **Auto-discovered, unlike `learn --critic`.** The Learn tab is the surface where the
    # right default is "use the better method if it is available", and the learned embedding
    # beat the hand-written typing vector on every metric simultaneously (docs/09 §9.7). If
    # nothing has been trained yet, or torch is not installed, `load_critic` returns None with
    # a logged reason and every fit falls back to the hand-written vector — so this is a
    # preference, not a requirement.
    s.add_argument("--critic", default=str(DEFAULT_CRITIC),
                   help="trained critic every fit started from the Learn tab should use, when "
                        "it exists (default %(default)s)")
    s.add_argument("--no-critic", dest="critic", action="store_const", const=None,
                   help="ignore any trained critic; fit exactly as the pipeline did before it")
    # 0 for the reason given on `learn --critic-weight`: measured harmful at every weight.
    s.add_argument("--critic-weight", type=float, default=0.0, metavar="W")
    s.add_argument("--no-embed-typing", dest="embed_typing", action="store_false",
                   help="cluster syllable types with the seven hand-weighted numbers of "
                        "`learn._observation_vector` instead of the critic's learned "
                        "embedding, even when a critic is loaded")
    s.set_defaults(func=cmd_serve, embed_typing=True)

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
