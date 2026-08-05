"""`birdy-pipeline` command line: build, calibrate, demo, verify."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import features, syrinx
from .calibrate import build_calibration, check_reference, monotonic_fraction, write_calibration
from .corpus import (
    dump_clip_wavs,
    load_inventory,
    local_corpus,
    measured_corpus,
    synthetic_corpus,
    write_wav,
)
from . import docrefit, galaxy, harvest, learn, quality, respfit, respiration, twovoice
from . import syntax as syntax_mod
from . import songspace as songspace_mod
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
#: Where `inverse train` writes, and where `serve` looks for an encoder to fit with.
DEFAULT_INVERSE = REPO_ROOT / "pipeline" / "out" / "inverse.pt"
CALIBRATION_NAME = "syrinx-calibration.json"
#: The store-sidecar `critic embed` writes: one 32-d embedding per stored syllable, in
#: `syllables.jsonl`/`patches.f16` row order. Its presence is what makes `build --space
#: auto` choose the embedding space.
EMBEDDINGS_NAME = "embeddings.f32"


def read_store_embeddings(
    path: Path, n_syllables: int, log: Any = None
) -> Any | None:
    """The store's embeddings sidecar as an (n_syllables, dim) matrix, or None.

    **The file is keyed by the store's row order, and the store moves.** A harvest
    appends rows, a subset rewrites them, and nothing version-stamps the sidecar — so
    a store and its embeddings can disagree, and the disagreement used to surface as a
    bare numpy error (`cannot reshape array of size 1509920 into shape
    (39999,newaxis)`, from a Learn-tab build against a store that had changed since
    `critic embed` ran). Worse than the crash is what the crash prevented anyone from
    seeing: a stale sidecar that happens to divide evenly would embed every syllable
    with its *neighbour's* vector, silently.

    None means "unusable, re-run `critic embed`"; the caller decides whether that is a
    recompute (build can embed on the spot), a skipped analysis (relations), or an
    error exit (placement, spacemap) — the helper only promises never to return a
    matrix whose rows do not align with `store.syllables`.
    """
    import numpy as np

    raw = np.frombuffer(Path(path).read_bytes(), dtype="<f4")
    if n_syllables <= 0 or raw.size % n_syllables:
        rows = raw.size // 32 if raw.size % 32 == 0 else raw.size
        if log is not None:
            log(
                f"{path} holds {rows} embedding rows but the store has {n_syllables} "
                "syllables — the store changed since `critic embed` wrote it. Re-run "
                "`birdy-pipeline critic embed` against this store."
            )
        return None
    return raw.reshape(n_syllables, -1).astype(np.float64)

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
    galaxy.self_test(verbose=False)
    log("features + galaxy self-tests ok")

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
    if render_synthetic:
        report_reachability(inventory, calibration)

    parts: list[PointSet] = []
    # The same corpus again, but with field points always as 0.6 s windows. It is used
    # only for the standardisation frame feature-space.json ships: the browser's live
    # path analyses windows, so the mean/std it subtracts must describe windows even
    # when the galaxy's points are syllables. Identical to `parts` unless
    # --field-source resolves to syllables.
    frame_parts: list[PointSet] = []
    frame_from_windows = False
    harvest_info: dict[str, Any] | None = None
    # Per-recording metadata (call type, sample rate, recordist, country, date...) so the
    # build can test which of them the geometry actually corresponds to.
    harvest_recordings: dict[str, Any] = {}

    store_path = Path(args.harvest_store or DEFAULT_HARVEST_STORE)
    store: harvest.HarvestStore | None = None
    typing: dict[str, Any] | None = None
    if (store_path / "state.json").exists() and not args.no_harvest:
        store = harvest.HarvestStore(store_path)
        typing_path = store_path / learn.TYPING_NAME
        if typing_path.exists():
            typing = json.loads(typing_path.read_text(encoding="utf-8"))

    # Which species can render measured realisations: the ones `learn` typed. The store's
    # member observations are grouped per (species, type) for `measured_corpus`.
    members: dict[str, dict[str, list[learn.SyllableObservation]]] = {}
    if store is not None and typing is not None:
        type_of = {
            (e["speciesId"], e["recordingId"], int(e["order"])): str(e["typeId"])
            for e in typing.get("entries", [])
        }
        for o in store.syllables:
            tid = type_of.get((o.species_id, o.recording_id, o.order))
            if tid:
                members.setdefault(o.species_id, {}).setdefault(tid, []).append(o)

    if args.field_source == "syllables" and typing is None:
        log("--field-source syllables needs the store's typing.json — run `learn` first")
        return 2
    syllable_points = (
        store is not None
        and typing is not None
        and args.field_source in ("auto", "syllables")
    )

    # --- which feature space the galaxy is built in (docs/09 phase 2) ---
    #
    # The critic's 32-d embedding is the measurably better similarity space (§9.7: typing
    # in it moved species placement 38.4 % -> 51.7 % on the 40 k store), and building in
    # it moves the projection, the clusters and the centroids into the space the live
    # activation will be mapped into. `auto` takes it when the prerequisites exist —
    # stored embeddings, a typing (syllable-level field points are what carries
    # embeddings), and a critic to embed the rendered anchor, without which the synthetic
    # points would all be dropped and the galaxy could name nothing. Anything missing
    # lands on the descriptor space with a logged reason, as every learned component does.
    space = args.space
    critic_obj: Any | None = None
    store_embeddings: np.ndarray | None = None
    embeddings_path = (
        store_path / EMBEDDINGS_NAME if (store_path / "state.json").exists() else None
    )
    if space != "descriptor":
        has_embeddings = (
            store is not None and typing is not None
            and embeddings_path is not None and embeddings_path.exists()
        )
        if has_embeddings or space == "embed":
            critic_obj = load_critic(
                args.critic or (str(DEFAULT_CRITIC) if DEFAULT_CRITIC.exists() else None),
                prefer_gpu=not args.cpu,
            )
        if space == "auto":
            if has_embeddings and critic_obj is not None:
                space = "embed"
            else:
                if has_embeddings and critic_obj is None:
                    log("NOTE: the store holds embeddings.f32 but no critic is available "
                        "to embed the rendered inventory with — building in the 28-d "
                        "descriptor space")
                space = "descriptor"
        elif space == "embed":
            if store is None or typing is None:
                log("--space embed needs syllable-level field points, which need the "
                    "store's typing.json — run `learn` first")
                return 2
            if critic_obj is None:
                log("--space embed needs a critic: the rendered inventory and any "
                    "un-embedded observations must be embedded before they can join a "
                    "galaxy that lives in the embedding space. Pass --critic, or train "
                    "one with `birdy-pipeline critic train`")
                return 2
        log(f"feature space: {space}"
            + (" (auto)" if args.space == "auto" else ""))

    def clip_embedder(clip: Any) -> np.ndarray | None:
        """The 32-d embedding of a rendered clip, through the same `mel_patch` the real
        side was measured with — measuring the two sides differently is the one bug that
        would invalidate the space (critic.py)."""
        patch = features.mel_patch(peak_normalise(clip.audio))
        return critic_obj.embed(patch)[0]

    embed_clips = clip_embedder if space == "embed" else None

    if render_synthetic:
        log(f"rendering synthetic corpus (variants={args.variants}, seed={args.seed})")
        if members:
            typed = [sp for sp in inventory["species"] if sp["id"] in members]
            authored = [sp for sp in inventory["species"] if sp["id"] not in members]
            log(f"measured realisations for the {len(typed)} typed species, "
                f"jitter for the {len(authored)} without harvest data")
            clips = (
                measured_corpus(
                    {"species": typed},
                    members,
                    calibration,
                    variants=(
                        args.variants
                        if args.member_variants is None
                        else args.member_variants
                    ),
                    anchor=args.member_anchor,
                    song_variants=args.song_variants,
                    seed=args.seed,
                    should_stop=should_stop,
                )
                if typed
                else []
            )
            if authored:
                clips += synthetic_corpus(
                    {"species": authored},
                    calibration,
                    variants=args.variants,
                    song_variants=args.song_variants,
                    seed=args.seed,
                    should_stop=should_stop,
                )
            # The syllables of typed species that have no member observations fall
            # between the two paths: measured_corpus only renders types with members,
            # and the whole-species split sent their species down the measured path.
            # Those are the hand-authored calls (wrenChip, hooLong, chickA...) — the
            # inventory's documented knowledge — and a build without them loses every
            # documented knot, which is exactly what the 2026-08-01 production build
            # shipped before this fallback existed. Render them jittered, as before.
            observed = {sp["id"]: set(members.get(sp["id"], {})) for sp in typed}
            fallen = []
            for sp in typed:
                kept = [s for s in sp["syllables"] if s["id"] not in observed[sp["id"]]]
                if not kept:
                    continue
                # Songs are NOT rendered here: measured_corpus already renders every
                # song of a typed species against its full syllable table, and a
                # learned song's sequence references learned types this kept-only
                # table does not have — rendering them again would both duplicate the
                # points and raise KeyError (the 2026-08-01 rebuild died on exactly
                # that). What is missing from the measured path is the syllables.
                fallen.append({**sp, "syllables": kept, "songs": []})
            if fallen:
                log(f"jitter renders for the {sum(len(sp['syllables']) for sp in fallen)} "
                    f"syllables with no observations (authored calls of typed species)")
                clips += synthetic_corpus(
                    {"species": fallen},
                    calibration,
                    variants=args.variants,
                    song_variants=args.song_variants,
                    seed=args.seed,
                    should_stop=should_stop,
                )
        else:
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
        synthetic_points = galaxy.descriptors(
            clips, should_stop=should_stop, embedder=embed_clips
        )
        parts.append(synthetic_points)
        frame_parts.append(synthetic_points)

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
        local_points = galaxy.descriptors(
            clips, should_stop=should_stop, embedder=embed_clips
        )
        parts.append(local_points)
        frame_parts.append(local_points)

    # Always, when there is one. Everything collected stays in the corpus; the point of
    # harvesting is that it accumulates, and a build that silently left it out was a build
    # that threw away every recording since the last time someone typed the flag.
    if store is not None:
        windows = store.to_point_set()
        field = windows
        if syllable_points:
            try:
                field = store.syllable_point_set(typing or {})
            except RuntimeError as exc:
                if args.field_source == "syllables":
                    log(str(exc))
                    return 2
                log(f"syllable-level field points unavailable: {exc} Using windows.")
        used_syllables = field is not windows
        if space == "embed":
            if not used_syllables:
                log("an embed-space build needs syllable-level field points — windows "
                    "carry no mel patch and cannot be embedded")
                return 2
            # The embeddings are keyed by `store.syllables` row order — the same order
            # `patches.f16` is written in — and the field points are that same list
            # filtered to observations with a descriptor, so the two align positionally.
            if store_embeddings is None:
                if embeddings_path is not None and embeddings_path.exists():
                    store_embeddings = read_store_embeddings(
                        embeddings_path, len(store.syllables), log=log
                    )
                if store_embeddings is None:
                    # Missing, or stale past recognition — a stale sidecar is no better
                    # than none, and embedding on the spot is what a missing file gets.
                    log("no usable embeddings.f32 in the store; embedding it now "
                        "(`critic embed` writes it once and for all)")
                    from . import critic as critic_mod

                    store_embeddings = critic_mod.embed_store(store, critic_obj, log=log)
            kept_rows = [i for i, o in enumerate(store.syllables) if o.descriptor]
            if len(kept_rows) != len(field):
                log(f"the store changed since its field points were derived: "
                    f"{len(kept_rows)} observations with descriptors vs {len(field)} "
                    "points. Re-run `learn` so typing.json matches the store.")
                return 2
            field.embeddings = store_embeddings[kept_rows]
        log(f"harvest store {store_path}: {len(field)} "
            f"{'syllable-level' if used_syllables else 'window'} field points "
            f"from {len(store.recordings)} recordings")
        rep = store.representativeness()
        harvest_recordings = dict(store.recordings)
        harvest_info = {
            "store": str(store_path),
            "points": len(field),
            "fieldPoints": "syllables" if used_syllables else "windows",
            "recordings": len(store.recordings),
            "descriptorsSeen": store.stream_n,
            "sampleDrift": {k: round(v, 4) for k, v in rep.items()},
        }
        parts.append(field)
        frame_parts.append(windows)
        frame_from_windows = used_syllables

    if not parts:
        log("nothing to embed: no rendered inventory, no harvest store, no local corpus")
        return 2
    points = PointSet.concat(parts)
    log(f"embedding {len(points)} points")
    frame = None
    if frame_from_windows:
        fx = PointSet.concat(frame_parts).x
        frame = (fx.mean(axis=0), fx.std(axis=0))

    # The embedding block: the 32-d space's own standardisation moments (measured over
    # the embedded points themselves — there is no window corpus in the learned space,
    # unlike the 28-d frame), and the browser's 28-d -> 32-d ridge map fitted on the
    # field syllable pairs, split and graded by recording (spacemap.py).
    embedding_block: dict[str, Any] | None = None
    if space == "embed":
        if points.embeddings is None:
            log("some corpus parts carry no embeddings, so the embed-space build cannot "
                "run — this is a wiring error, not a data problem")
            return 2
        e_all = np.asarray(points.embeddings, dtype=np.float64)
        finite_rows = np.all(np.isfinite(e_all), axis=1)
        if not finite_rows.any():
            log("not one point carries an embedding; cannot build in the embed space")
            return 2
        emb_mean = e_all[finite_rows].mean(axis=0)
        emb_std = e_all[finite_rows].std(axis=0)
        from . import spacemap

        field_rows = np.asarray(
            [s == harvest.SOURCE for s in points.source]
        ) & finite_rows
        if not field_rows.any():
            log("no field syllable pairs to fit the browser's 28-d -> 32-d map on; the "
                "galaxy builds, but feature-space.json ships no map and the browser "
                "stays on the descriptor path")
            embedding_block = {"mean": emb_mean, "std": emb_std, "map": None,
                               "mapQuality": None}
        else:
            mean28, std28 = frame if frame is not None else (
                points.x.mean(axis=0), points.x.std(axis=0)
            )
            x28 = features.standardise(points.x[field_rows], mean28, std28)
            z32 = (e_all[field_rows] - emb_mean) / np.maximum(emb_std, 1.0e-6)
            recordings_of = [points.song_id[i] for i in np.nonzero(field_rows)[0]]
            space_map = spacemap.fit_map(x28, z32, recordings_of, seed=args.seed, log=log)
            embedding_block = {
                "mean": emb_mean,
                "std": emb_std,
                "critic": _critic_provenance(args.critic, embeddings_path),
                "map": space_map,
                "mapQuality": space_map.quality,
                "_evalMapped": space_map.eval_mapped,
                "_evalTrue": space_map.eval_true,
            }
            if args.dump_spacemap_eval:
                # The per-session spacemap debug payload (docs/20 §20.3): which
                # recording each held-out row came from, and the fit-side cloud the
                # off-manifold signal is measured against. The split is recomputed —
                # same call, same seed, so it is the fit's own split, not a copy.
                fit_m, eval_m = spacemap._recording_split(recordings_of, 0.8, args.seed)
                embedding_block["_evalRecs"] = [
                    r for r, m in zip(recordings_of, eval_m) if m
                ]
                embedding_block["_fitX"] = x28[fit_m]
                embedding_block["_fitRecs"] = [
                    r for r, m in zip(recordings_of, fit_m) if m
                ]

    # `--clustering both`: the two maps the comparison workflow always wants side by
    # side — the kmeans map, where every type owns a named knot ("known"), and the
    # hdbscan map, where a point may honestly be in none of them ("unknown"). The
    # corpus above is the expensive half (rendering the inventory) and is built once;
    # clustering, projection and asset-writing run per map into `known/`/`unknown/`
    # subdirectories, each a complete, verifiable asset set.
    #
    # **The known side is `label`, not `kmeans`, and that is deliberate.** `label` is what
    # the production build ships and what every map number in the whitepaper was measured
    # on, so pairing `hdbscan` with `kmeans` here would hand the app a known map that no
    # measurement describes. At production scale kmeans is the wrong instrument anyway
    # (docs/22 §22.5 — 27 862 clusters wanted over 694 936 points, losing every documented
    # call). `--clustering kmeans` still selects it explicitly for the bake-off arm.
    modes: list[tuple[str, Path]] = (
        [("label", out / "known"), ("hdbscan", out / "unknown")]
        if args.clustering == "both"
        else [(args.clustering, out)]
    )
    map_stats: dict[str, Any] = {}
    for mode, mode_out in modes:
        if mode_out != out:
            mode_out.mkdir(parents=True, exist_ok=True)
            (mode_out / CALIBRATION_NAME).write_bytes(
                (out / CALIBRATION_NAME).read_bytes()
            )
        if len(modes) > 1:
            log(f"--- the {'unknown' if mode == 'hdbscan' else 'known'} map "
                f"({mode_out}) ---")
        map_stats[mode] = build_galaxy(
            points,
            inventory,
            out_dir=mode_out,
            inventory_path=inventory_path,
            seed=args.seed,
            k=args.k,
            clustering=mode,
            min_cluster_size=args.min_cluster_size,
            min_dist=args.min_dist,
            projection=args.projection,
            compare_projections=not args.no_compare_projections,
            separation=args.separation,
            type_split_separation=(
                args.type_split_separation if args.type_split else float("inf")
            ),
            build_info={
                "source": args.source,
                "audioDir": str(args.audio_dir) if args.audio_dir else None,
                "variantsPerSyllable": args.variants if args.source == "synthetic" else None,
                "memberVariants": args.member_variants,
                "memberAnchor": args.member_anchor,
                "variantsPerSong": args.song_variants if args.source == "synthetic" else None,
                "harvest": harvest_info,
                "betaClamp": [syrinx.BETA_MIN, syrinx.BETA_MAX],
                "clusterSeparation": args.separation,
                "envelopeAsOutputGain": True,
            },
            recordings=harvest_recordings,
            test_relations=not args.no_relations,
            frame=frame,
            space=space,
            embedding=embedding_block,
            dump_points=(
                Path(args.dump_points) if args.dump_points and len(modes) == 1 else None
            ),
            dump_spacemap_eval=(
                Path(args.dump_spacemap_eval)
                if args.dump_spacemap_eval and len(modes) == 1
                else None
            ),
        )

    # Cross-species relations (phase 4): shared/convergent types and species similarity
    # in the critic's embedding, shipped beside the assets as `relations.json` — data
    # only; what the app draws on top of it is the app's business. Needs the store, its
    # typing and the stored embeddings; anything missing skips with a reason, as every
    # learned component does.
    if (
        store is not None
        and typing is not None
        and embeddings_path is not None
        and embeddings_path.exists()
    ):
        from . import relations as relations_mod

        try:
            if store_embeddings is None:
                store_embeddings = read_store_embeddings(
                    embeddings_path, len(store.syllables)
                )
                if store_embeddings is None:
                    raise RuntimeError(
                        f"{embeddings_path} is stale against this store — re-run "
                        "`birdy-pipeline critic embed`"
                    )
            relations_doc = relations_mod.compute_relations(
                store, store_embeddings, typing, inventory
            )
            # The shipped copy is trimmed to the part the browser reads. The full document
            # is what the statistics below are taken from, so the finding is reported whole
            # even though the asset is not — and the trim is printed, never silent.
            shipped = relations_mod.shipped_relations(relations_doc)
            for _, mode_out in modes:
                relations_mod.write_relations(
                    mode_out / relations_mod.RELATIONS_NAME, shipped, per_species=None
                )
            n_shared = sum(
                len(p["sharedTypes"]) for p in relations_doc["speciesPairs"]
            )
            log(f"wrote {relations_mod.RELATIONS_NAME} "
                f"({'both maps' if len(modes) > 1 else str(modes[0][1])}): "
                f"{len(relations_doc['speciesPairs'])} species pairs computed, "
                f"{n_shared} shared-type candidate(s) under threshold "
                f"{relations_doc['sharedTypeThreshold']}")
            kept = shipped["retention"]
            log(f"  shipped {kept['pairsKept']} of {kept['pairsComputed']} pairs "
                f"({relations_mod.SHIPPED_PAIRS_PER_SPECIES} nearest partners per "
                f"species, which is every query the app makes) carrying "
                f"{kept['sharedTypesKept']} of {kept['sharedTypesComputed']} "
                f"shared-type candidates")
        except Exception as exc:  # analysis, not output: a build must not fail on it
            log(f"relations skipped: {exc}")
    else:
        log("relations skipped: needs the harvest store, its typing.json and "
            "embeddings.f32 (`critic embed`)")

    for mode, mode_out in modes:
        stats = map_stats[mode]
        log("")
        if len(modes) > 1:
            log(f"--- {'unknown' if mode == 'hdbscan' else 'known'} map ---")
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

        # The browser's match ramp, measured against the centroids this build just wrote
        # and folded into the manifest it reads. It is a property of the assets — where a
        # real field syllable scores against *these* centroids — and it moved 0.07-0.14
        # between v5 and v6 with the hand-tuned constants left behind, which is why it is
        # no longer allowed to be a constant. Analysis, not output: a build must not fail
        # on it, and a build with no field audio simply leaves the key out and lets the
        # app fall back.
        try:
            ramp = measure_match_ramp(mode_out, store_path)
            if ramp is None:
                log("match ramp: no harvest store, manifest keeps no matchRamp "
                    "(the app falls back to its constants)")
            else:
                manifest = galaxy.read_manifest(mode_out)
                manifest["matchRamp"] = ramp
                galaxy.write_manifest(mode_out, manifest)
                log(f"match ramp: {ramp['rule']} = {ramp['floor']:.3f}..{ramp['ceiling']:.3f} "
                    f"over {ramp['sampled']} field syllables "
                    f"(median {ramp['percentiles']['p50']:.3f})")
        except Exception as exc:
            log(f"match ramp skipped: {exc}")

        rc = verify(mode_out)
        if rc != 0:
            return rc
    return 0


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
                keep_audio=(
                    Path(args.keep_audio) if getattr(args, "keep_audio", None) else None
                ),
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


def cmd_sources_list(args: argparse.Namespace) -> int:
    """Which audio sources this machine can use right now, and why not for the rest."""
    from . import sources

    log(f"{'source':<18} {'available':<9} {'why not / what it would unlock'}")
    for name, ok, reason, summary in sources.availability_table():
        detail = summary if ok else f"skipped: {reason}"
        log(f"{name:<18} {'yes' if ok else 'no':<9} {detail}")
    log("\nan unfilled key is a skip, never an error; the keys live in pipeline/.env "
        "(see .env.example)")
    return 0


def cmd_sources_fetch(args: argparse.Namespace) -> int:
    """Fetch from one open source through the same decode -> describe -> delete loop."""
    from . import sources

    src = sources.SOURCES.get(args.source)
    if src is None:
        log(f"unknown source {args.source!r}; known: {', '.join(sorted(sources.SOURCES))}")
        return 2
    ok, reason = src.available()
    if not ok:
        # A missing key or package is a configuration fact, not a failure — the command
        # succeeds so a script can ask every source in turn and keep what answers.
        log(f"skip {args.source}: {reason}")
        return 0
    # The guard that watches the two silent store failures (see cmd_harvest).
    harvest.self_test(verbose=False)
    store = harvest.HarvestStore(
        Path(args.store), cap=args.cap, seed=args.seed,
        syllable_cap=getattr(args, "syllable_cap", harvest.DEFAULT_SYLLABLE_CAP),
    )
    t0 = time.time()
    # **A list of species, so one sweep serves all of them.** `inat-sounds` streams a single
    # 81 GB archive and re-downloads its index per call, so asking for one bird costs a whole
    # sweep to reach its first file — fifteen minutes, measured. The 1 160 species under
    # `learn`'s fitting floor need one pass, not 1 160 of them.
    species: Any = args.species
    if getattr(args, "species_file", None):
        names = [
            line.strip()
            for line in Path(args.species_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not names:
            log(f"{args.species_file} lists no species")
            return 2
        if args.species:
            log("--species and --species-file are two answers to one question; pass one")
            return 2
        species = names
        log(f"  {len(names)} species from {args.species_file}")

    fetch_kw: dict[str, Any] = {}
    if getattr(args, "per_species", None) is not None:
        # Only the sources whose archive order is biased (iNatSounds streams
        # taxonomically) accept a per-species cap; passing it elsewhere would be a
        # silent no-op, so it is wired exactly where it means something.
        fetch_kw["per_species"] = args.per_species
    if getattr(args, "keep_audio", None):
        # The owner's training-phase exception to the delete loop (AGENTS.md). Same
        # wiring rule: only adapters that implement it receive it.
        fetch_kw["keep_audio"] = Path(args.keep_audio)
    report = src.fetch(
        store,
        species=species,
        limit=args.limit,
        max_seconds=args.max_seconds,
        item=args.item,
        **fetch_kw,
    )
    store.save()
    log(harvest.format_report(report, store))
    log(f"\nstore written to {store.root} in {time.time() - t0:.1f}s "
        f"(attribution in {store.root / 'CREDITS.md'})")
    return 0


#: Descriptors a species needs before its centroid is allowed to stand for it in the
#: diverse pick. A centroid over a handful of syllables is mostly sampling noise, and
#: the whole premise of the pick is that a species' *position* means something.
DIVERSE_MIN_DESCRIPTORS = 20


def _diverse_species(
    strata: dict[str, Any],
    eligible: dict[str, int],
    n: int,
    seed: int = 0,
) -> tuple[list[str], dict[str, float]]:
    """The `n` species that best **represent** the store's acoustic spread.

    **Why this is not "the n most different species".** The obvious reading of "species
    with different vocals" is farthest-point sampling — repeatedly take whatever is
    least like everything picked so far. Measured on `out/harvest-gan` (2 991 species
    with at least `DIVERSE_MIN_DESCRIPTORS` descriptors, standardised 28-d space), that
    is a trap: it halves the worst-covered gap (12.05 -> 6.96) but makes the *average*
    distance from a corpus species to its nearest pick **worse** than simply taking the
    biggest species (4.98 vs 3.81), because it spends the whole budget on the rim of the
    space. A bench of a hundred outliers is a bench of a hundred edge cases, and on this
    corpus a good few of those are noise rather than birds.

    So the pick is k-medoid instead: cluster the species centroids into `n` groups and
    keep the most central real species of each. That is the selection whose objective
    *is* representativeness, and it beats both alternatives where it counts:

    | pick                | mean dist to nearest | worst-covered | median obs |
    |---------------------|----------------------|---------------|------------|
    | top-100 by count    | 3.813                | 12.052        | 271        |
    | 100 farthest-point  | 4.982                | 6.963         | -          |
    | 100 k-medoid (this) | **3.125**            | **9.122**     | 68         |

    The honest cost is in that last column: the diverse hundred holds 17 139
    observations against the biggest hundred's 63 055, so every type is fitted from
    fewer members. That is the right trade for a debug bench — the point is to meet
    every kind of voice the corpus contains before committing to a full run — and the
    wrong one for measuring fit quality, which wants depth.

    **The space is the 28-d descriptor, not the critic's 32-d embedding**, even though
    the embedding is the measurably better similarity space (docs/09 §9.7). `subset` is
    the fast step before anything has been trained: it must run on a bare store with no
    critic, no torch and no patches. A pick made in a space the command cannot always
    compute would be a pick that sometimes silently is not made.

    Ties inside a cluster go to the species with more data (a log-scaled nudge, so it
    breaks ties without dragging the choice away from the cluster's centre).

    Returns the chosen ids and the coverage figures, so the caller can report what the
    pick actually achieved rather than asserting that it worked.
    """
    import numpy as np
    from sklearn.cluster import KMeans

    ids = sorted(
        sid
        for sid, st in strata.items()
        if len(st.rows) >= DIVERSE_MIN_DESCRIPTORS and eligible.get(sid, 0) > 0
    )
    if not ids:
        return [], {}
    centres = np.stack([np.mean(np.stack(strata[sid].rows), axis=0) for sid in ids])
    counts = np.array([len(strata[sid].rows) for sid in ids], dtype=float)
    # Standardised, because the 28 descriptor dimensions are not in comparable units and
    # an unscaled distance would be dominated by whichever ones happen to run largest.
    centres = (centres - centres.mean(axis=0)) / np.maximum(centres.std(axis=0), 1e-9)
    if len(ids) <= n:
        return ids, {}

    km = KMeans(n_clusters=n, n_init=10, random_state=seed).fit(centres)
    chosen: list[int] = []
    for k in range(n):
        members = np.nonzero(km.labels_ == k)[0]
        if not len(members):
            continue
        cost = np.linalg.norm(
            centres[members] - km.cluster_centers_[k], axis=1
        ) - 0.15 * np.log1p(counts[members])
        chosen.append(int(members[int(np.argmin(cost))]))

    picked = centres[np.array(chosen)]
    nearest = np.linalg.norm(centres[:, None, :] - picked[None, :, :], axis=2).min(axis=1)
    spread = np.linalg.norm(picked[:, None, :] - picked[None, :, :], axis=2)
    upper = np.triu_indices(len(chosen), 1)
    return (
        sorted(ids[i] for i in chosen),
        {
            "candidates": float(len(ids)),
            "meanToNearest": float(nearest.mean()),
            "worstCovered": float(nearest.max()),
            "spread": float(spread[upper].mean()) if len(chosen) > 1 else 0.0,
        },
    )


def cmd_subset(args: argparse.Namespace) -> int:
    """Write a debug store holding the N biggest species, recordings whole.

    The debug cycle the user asked for: `subset --species 100` → `learn` → `build`
    on the subset proves the mechanics in minutes, and only then does the full run
    happen. The subset keeps each chosen species complete — every syllable, every
    recording's metadata and descriptor, the descriptor strata — because a partial
    species would test a store shape the full run never has. Stream statistics are
    the parent store's (they report on the harvest stream, not on this slice).
    """
    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations")
        return 2
    counts: dict[str, int] = {}
    for o in store.syllables:
        counts[o.species_id] = counts.get(o.species_id, 0) + 1
    if getattr(args, "diverse", False):
        chosen, stats = _diverse_species(
            store.strata, counts, args.species, seed=getattr(args, "seed", 0)
        )
        if not chosen:
            log(f"{store.root} has no species with at least {DIVERSE_MIN_DESCRIPTORS} "
                "descriptors and a syllable observation — nothing to pick from")
            return 2
        keep = set(chosen)
        if stats:
            log(f"diverse pick: {len(keep)} of {int(stats['candidates'])} eligible "
                f"species; a corpus species is {stats['meanToNearest']:.3f} from its "
                f"nearest pick on average (worst {stats['worstCovered']:.3f}), and the "
                f"picks sit {stats['spread']:.3f} apart in the standardised 28-d space")
        else:
            log(f"diverse pick: kept all {len(keep)} eligible species "
                f"(fewer than the {args.species} asked for)")
    else:
        keep = set(sorted(counts, key=lambda s: -counts[s])[: args.species])
    out = Path(args.out)
    if out.resolve() == Path(args.store).resolve():
        log("a subset cannot overwrite its source store")
        return 2

    sub = harvest.HarvestStore(out)
    sub.strata = {sid: store.strata[sid] for sid in keep if sid in store.strata}
    sub.syllables = [o for o in store.syllables if o.species_id in keep]
    sub.recordings = {
        rid: info for rid, info in store.recordings.items()
        if info.get("speciesId") in keep
    }
    sub.recording_descriptors = {
        rid: d for rid, d in store.recording_descriptors.items()
        if rid in sub.recordings
    }
    sub.stream_n = store.stream_n
    sub.stream_mean = store.stream_mean
    sub.stream_m2 = store.stream_m2
    sub.save()
    log(f"wrote {out}: {len(keep)} species, {len(sub.syllables)} syllables, "
        f"{sum(len(st.rows) for st in sub.strata.values())} descriptors "
        f"(of {len(counts)} / {len(store.syllables)} / {len(store)} in {store.root})")
    log(f"debug cycle: uv run birdy-pipeline learn --store {out} --jobs 8")
    log(f"         then uv run birdy-pipeline build --harvest-store {out} "
        f"--inventory <learned.json> --space embed")
    return 0


def cmd_grow(args: argparse.Namespace) -> int:
    """Add the harvest store's newest descriptors to the built galaxy, in place.

    The corpus stops arriving as a discontinuity: existing points keep their coordinates
    and the cloud gains marks around them. What it cannot do is discover a cluster — new
    audio joins the nearest existing knot — so the drift figures it prints are the signal
    for when a real rebuild is due.

    When the galaxy was built in the critic's embedding space (`build --space embed`),
    new audio has to be embedded before it can be placed — the frozen projection basis's
    landmarks are embedding vectors, so a 28-d descriptor has no meaning against them.
    That needs the critic; without it there is no honest placement and this refuses.
    """
    from datetime import datetime, timezone

    from . import grow

    out = Path(args.out)
    store_path = Path(args.harvest_store or DEFAULT_HARVEST_STORE)
    store = harvest.HarvestStore(store_path)
    points = json.loads((out / "points.json").read_text(encoding="utf-8"))
    total = int(points["n"])
    # **Count the field points, not all of them.** This compared the store's descriptor
    # count against the galaxy's *total* point count, and a mixed build's total includes
    # ~12000 synthetic renders — so `take` came out negative and `grow --only-new` reported
    # "nothing new to add" on every run, forever. The loop's third step was a no-op from the
    # day the harvest joined the corpus, which is why an hour of learning left the galaxy
    # at exactly the size it started.
    have = sum(1 for s in points.get("source", []) if s == "field") or 0

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    space = manifest.get("space", "descriptor")

    if space == "embed":
        # `getattr`: the control surface calls this with a hand-built Namespace that has
        # no `critic` attribute — its grow is the one Phase 3's ingest -> grow loop runs,
        # and an AttributeError there looked exactly like the refusal below.
        trained = load_critic(
            getattr(args, "critic", None)
            or (str(DEFAULT_CRITIC) if DEFAULT_CRITIC.exists() else None)
        )
        if trained is None:
            log(f"{out} was built in the critic's embedding space: its projection basis "
                "and cluster centroids are 32-d embedding vectors, and a new syllable "
                "can only join them through the critic that defines that space. Pass "
                "--critic (or train one) — there is no 28-d fallback that would place "
                "the point where it belongs.")
            return 2
        # The pool is exactly the set an embed build draws its field points from:
        # observations with a descriptor (the point's identity) *and* a mel patch (what
        # makes them embeddable), in store order, so a suffix is the newest.
        pool = [o for o in store.syllables if o.descriptor and o.mel_patch is not None]
        if not pool:
            log("the harvest store holds no embeddable syllable observations; nothing to add")
            return 1
        take = len(pool) - have if args.only_new else len(pool)
        if take <= 0:
            log(f"the galaxy holds {have} field points of {total} and the store has "
                f"{len(pool)} embeddable observations; nothing new to add")
            return 0
        fresh_obs = pool if not args.only_new else pool[-take:]
        typing_path = store_path / learn.TYPING_NAME
        type_of = {}
        if typing_path.exists():
            typing = json.loads(typing_path.read_text(encoding="utf-8"))
            type_of = {
                (e["speciesId"], e["recordingId"], int(e["order"])): str(e["typeId"])
                for e in typing.get("entries", [])
            }
        patches = np.stack([
            np.asarray(o.mel_patch, dtype=np.float32) for o in fresh_obs
        ])
        embedded = trained.embed(patches)
        fresh = galaxy.PointSet(
            x=np.asarray(embedded, dtype=np.float64),
            species_id=[o.species_id for o in fresh_obs],
            syllable_id=[
                type_of.get((o.species_id, o.recording_id, o.order), "")
                for o in fresh_obs
            ],
            song_id=[o.recording_id for o in fresh_obs],
            duration=[float(o.dur) for o in fresh_obs],
            source=[harvest.SOURCE] * len(fresh_obs),
            # The ingest-time verdict that decides which of these points may be
            # force-assigned to an existing knot and which must wait for a quorum of
            # their own kind (grow.py, docs/09 §9.2b use 2).
            novel=[bool(o.novel) for o in fresh_obs],
        )
        # The 28-d rows ride along only so a knot founded in this space can also ship
        # the fallback `vector` the browser's pre-embedding path reads.
        descriptors28 = np.stack([
            np.asarray(o.descriptor, dtype=np.float64) for o in fresh_obs
        ])
        log(f"embedded {len(fresh)} new syllables in the critic's space")
    else:
        field = store.to_point_set()
        if not len(field):
            log("the harvest store is empty; nothing to add")
            return 1

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
        # Window-level points carry no per-syllable novelty verdict — the flag lives on
        # syllable observations, and these are reservoir windows.
        descriptors28 = None
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # The newest fitted repertoire rides along, so a grown point that belongs to a syllable
    # or a species the shipped inventory has never seen arrives with a voice.
    inventory_path = Path(args.inventory)
    result = grow.extend_build(
        out, fresh, stamp, inventory_path=inventory_path, descriptors28=descriptors28
    )
    log(f"generation {result['generation']}: {result['points']} points")
    if result.get("founded"):
        log(f"{len(result['founded'])} new knot(s) founded from novel syllables: "
            "heard enough times to be a thing, still unlabelled — detecting that a "
            "sound is new is not knowing what it means")
    if result["drift"]["unmatched"] > 0.35:
        log("more than a third of the new audio matched no existing knot — "
            "the arrangement no longer describes its own contents; rebuild")
    return 0


def cmd_inverse(args: argparse.Namespace) -> int:
    """Train the amortised inverse of docs/09 §9.3 Part 2: mel patch -> syrinx parameters.

    The training data is generated here and thrown away: sample plausible parameter
    vectors from the fitted inventory's own marginals, render each through the same
    `syrinx.render_syllable` the app uses, measure it with the same `features.mel_patch`
    the critic consumes. No audio, no annotation, no licensing — and no confound, which is
    what separates this from every other learned component in the pipeline.
    """
    from . import inverse as inverse_mod

    inverse_mod.self_test(verbose=False)
    log("inverse self-test ok")
    inventory = load_inventory(Path(args.inventory))
    calibration = ensure_calibration(Path(args.calibration_dir))
    sampler = inverse_mod.EmpiricalSampler(inventory)
    log(f"sampling {args.pairs} pairs from {Path(args.inventory).name}'s marginals")
    data = inverse_mod.build_dataset(
        args.pairs, sampler, calibration=calibration, seed=args.seed, log=log
    )
    cfg = inverse_mod.InverseConfig(
        epochs=args.epochs, seed=args.seed, pairs=args.pairs, prefer_gpu=not args.cpu
    )
    model = inverse_mod.train(data, cfg, log=log)
    out = Path(args.out)
    model.save(out)
    r = model.report
    log(f"\nwrote {out}")
    log(f"  {r.epochs} epochs on {r.n_train} train / {r.n_val} val pairs, device {r.device}")
    log(f"  final validation loss {r.final_val_loss:.4f}; timbre {r.timbre_val_accuracy:.3f}, "
        f"hold {r.hold_val_accuracy:.3f} accurate")
    for name, mse in sorted(r.group_val_mse.items()):
        log(f"  {name:16} val MSE {mse:.4f}")
    log("\nThis is a starting point for the fit, not a fit: `learn --inverse "
        f"{out}` re-initialises each type's gesture axes from its own patch and lets the "
        "same coordinate descent polish. Judge it on docs/09 §9.3's gate — the "
        "resynthesis cosine of the types that ship — never on the validation loss above.")
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    """Fit syllables and syntax to the harvested observations, and check the model sings them."""
    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    inventory = load_inventory(Path(args.inventory))
    calibration = ensure_calibration(Path(args.calibration_dir))
    # The amortised inverse, when asked for. Imported here rather than at module scope
    # for the same reason the critic is: it pulls in torch, and a learn without it must
    # not need torch installed at all.
    inverse_encoder = None
    if getattr(args, "inverse", None):
        from . import inverse as inverse_mod

        inverse_encoder = inverse_mod.Inverse.load(Path(args.inverse), prefer_gpu=not args.cpu)
        if getattr(args, "inverse_two_start", False):
            log(f"inverse encoder: {args.inverse} on {inverse_encoder.device} — TWO-START: "
                "the descent runs from the cluster median AND from the encoder's proposal "
                "and the better objective wins, so this cannot fit worse than the shipped "
                "path by construction, and it costs two descents per type")
        else:
            log(f"inverse encoder: {args.inverse} on {inverse_encoder.device} — the gesture "
                "axes start from each type's own patch, and the descent still decides")
    # Cheap, and it checks the one property that would otherwise fail silently: that a fit
    # with no critic is bit-identical to the one that shipped before the critic existed.
    features.self_test(verbose=False)
    learn.self_test(verbose=False)
    respiration.self_test(verbose=False)
    twovoice.self_test(verbose=False)

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

    typing: list[dict[str, Any]] = []
    # Streaming progress + crash checkpoints. One line per fitted species lands in the
    # store's learn-progress.json as it finishes (the serve's status endpoint surfaces
    # it, so a long learn is watchable), and every 100 species the typing and the
    # document-so-far are checkpointed to disk — the fit's only copy used to be the
    # final write, so one crash in the last hour lost the hour.
    out = Path(args.out)
    typing_path = store.root / learn.TYPING_NAME
    progress_path = store.root / "learn-progress.json"
    partial_path = out.with_name(out.name + ".partial")
    streamed = {"done": 0}
    partial_species: list[dict[str, Any]] = []

    def _on_species(entry: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        streamed["done"] += 1
        partial_species.append(entry)
        payload = {
            "done": streamed["done"],
            "species": entry["id"],
            "common": entry.get("common", ""),
            "types": len(entry["syllables"]),
            "typingRows": len(typing),
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        tmp = progress_path.with_name(progress_path.name + ".tmp")
        tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        tmp.replace(progress_path)
        if streamed["done"] % 100 == 0:
            typing_path.write_text(
                json.dumps({"version": 1, "entries": typing}, indent=1) + "\n",
                encoding="utf-8",
            )
            partial_path.write_text(
                json.dumps({"version": document_version, "note": "partial fit in "
                            "progress — the final write replaces this",
                            "refs": {}, "banks": {}, "species": partial_species},
                           indent=1),
                encoding="utf-8",
            )

    # Inherit the ids the last fit used, so `L03` keeps naming the same sound. See
    # `learn.assign_ids`: renumbering was why a refitted bird sang something new and lit
    # a cluster that had been fitted to something else. Hoisted: the unlabelled pool's
    # `U*` candidates inherit from the same document below.
    prior = learn.previous_fit(out)
    document_version = int(inventory.get("version", 1))
    # Common names from the store's own recording metadata, behind the authored
    # inventory and the discovered registry (see learn.recording_names).
    discovered = list(harvest.load_discovered(DEFAULT_DISCOVERED))
    named = {sp["id"] for sp in inventory.get("species", [])} | {
        e["id"] for e in discovered if e.get("id")
    }
    discovered += learn.recording_names(store.recordings, named)
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
        use_respiration=args.respiration,
        use_two_voice=args.two_voice,
        inverse=inverse_encoder,
        inverse_two_start=getattr(args, "inverse_two_start", False),
        mel_weight=args.mel_weight,
        jobs=args.jobs,
        prior=prior,
        # Where a discovered bird's common name is. Without it every species that is not in
        # the authored inventory is called by its own id everywhere in the app.
        discovered=discovered,
        typing=typing,
        on_species=_on_species,
    )

    # --- label-free typing and syntax mining (phase 4) ---
    #
    # The per-species loop typed everything that carries a label. What arrived without
    # one (browser ingest stores it as `unlabelled`) is typed now, against the types the
    # loop just produced: inherit what matches a known type within the novelty
    # threshold, cluster the rest into `U*` candidates. It needs the critic to see with
    # and its novelty scorer to threshold with — both optional, every absence degrading
    # to a logged skip, as every learned component does (§9.4).
    novelty = None
    if trained is not None and args.critic:
        novelty_path = Path(args.critic).with_name(Path(args.critic).stem + "-novelty.json")
        if novelty_path.exists():
            from . import critic as critic_mod

            novelty = critic_mod.Novelty.load(novelty_path)
    unlabelled_embedder = embedder
    if (
        unlabelled_embedder is None
        and trained is not None
        and any(o.mel_patch is not None for o in store.syllables)
    ):
        # The pool's space is the critic's raw embedding regardless of how the labelled
        # species were clustered: the novelty threshold was calibrated there.
        unlabelled_embedder = learn.critic_embedder(trained)
    learn.fit_unlabelled(
        document,
        store.syllables,
        typing,
        embedder=unlabelled_embedder,
        novelty=novelty,
        seed=args.seed,
        previous=prior.get(learn.UNLABELLED_SPECIES),
    )
    learn.attach_chunks(document, store.syllables, typing)
    song_rows = learn.attach_song_types(document, store.syllables, typing)
    if not document["species"]:
        log("no species had enough observations to fit — harvest more recordings")
        return 2

    if args.learned_only:
        learn.write_learned_inventory(out, document)
    else:
        # The default keeps the documented calls and adds the fitted ones next to them,
        # so building from this file does not cost the app its citations.
        learn.write_learned_inventory(out, learn.merge_learned_inventory(inventory, document))
    # The fit is done: the partial checkpoint has no readers left.
    partial_path.unlink(missing_ok=True)

    # The typing belongs to the store, not to the inventory the fit produced: the build
    # keys the store's own observations by it, so it lives beside `syllables.jsonl`.
    # Same for the song typing one level up — same rows, keyed by bout.
    typing_path.write_text(
        json.dumps({"version": 1, "entries": typing}, indent=1) + "\n", encoding="utf-8"
    )
    log(f"wrote {typing_path}: {len(typing)} of {len(store.syllables)} stored "
        f"observations carry a learned type id")
    if song_rows:
        song_path = store.root / learn.SONG_TYPING_NAME
        song_path.write_text(
            json.dumps({"version": 1, "entries": song_rows}, indent=1) + "\n",
            encoding="utf-8",
        )
        log(f"wrote {song_path}: {len(song_rows)} bouts carry a song type id")

    total = sum(len(sp["syllables"]) for sp in document["species"])
    cosines = [
        s["learned"]["resynthesisCosine"]
        for sp in document["species"]
        for s in sp["syllables"]
        if s.get("learned", {}).get("resynthesisCosine")
    ]
    log("")
    log(f"wrote {out}: {len(document['species'])} species, {total} learned syllable types "
        f"({time.time() - t0:.1f}s)"
        + ("" if args.learned_only else ", alongside the documented inventory"))
    placed = [
        s["learned"]["nearestOwn"]
        for sp in document["species"]
        for s in sp["syllables"]
        # The unlabelled pool's `U*` candidates are never resynthesis-verified — there
        # is no species reference to judge them against — so they carry no placement
        # verdict and must not dilute the count.
        if "nearestOwn" in s.get("learned", {})
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
        # The pseudo-species of unlabelled arrivals has no sampled bout — its songs list
        # is empty on purpose (unlabelled_entry), so guard rather than assume one.
        bout = sp["songs"][0]["sequence"] if sp.get("songs") else []
        chunks = f", {len(grammar['chunks'])} chunks" if grammar.get("chunks") else ""
        songs = f", {len(grammar['songTypes'])} song types" if grammar.get("songTypes") else ""
        log(f"  {sp['id']:26} {len(sp['syllables'])} types, "
            f"{len(grammar.get('transitions', {}))} states{chunks}{songs}, "
            f"example bout {' '.join(bout) or '(none)'}")
    log("")
    log("next: uv run birdy-pipeline build --inventory " + str(out) +
        " --harvest-store " + str(store.root))
    return 0


def cmd_respfit(args: argparse.Namespace) -> int:
    """Fit the docs/15 synth blocks per species and gate them per type (respfit.py).

    Reads the learned inventory the parallel learn wrote and the store's typing.json,
    searches the respiration set per species and the second voice per screened type,
    and writes a new inventory in which a block ships on a type ONLY where it beat
    that type's current cosine by the margin. The input inventory is never modified
    in place unless `--out` points at it — and the caller backs it up first.
    """
    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    try:
        typing = respfit.load_typing(store.root)
    except RuntimeError as exc:
        log(str(exc))
        return 2
    inventory_path = Path(args.inventory)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    calibration = ensure_calibration(Path(args.calibration_dir))
    features.self_test(verbose=False)
    learn.self_test(verbose=False)
    respiration.self_test(verbose=False)
    twovoice.self_test(verbose=False)
    respfit.self_test(verbose=False)

    t0 = time.time()
    document, report = respfit.respfit_inventory(
        store.syllables,
        typing,
        inventory,
        calibration,
        recording_descriptors={
            rid: np.asarray(row, dtype=np.float64)
            for rid, row in store.recording_descriptors.items()
        },
        margin=args.margin,
        fit_respiration=not args.no_respiration,
        fit_two_voice=not args.no_two_voice,
        jobs=args.jobs,
    )
    out = (
        Path(args.out)
        if args.out
        else inventory_path.with_name(inventory_path.stem + ".respfit.json")
    )
    learn.write_learned_inventory(out, document)
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf-8"
        )

    g = report["global"]
    log("")
    log(f"wrote {out} ({time.time() - t0:.0f}s)")
    log(
        f"respfit verdict over {g['typesScored']} scored types: median cosine "
        f"{g['medianBefore']:.3f} -> {g['medianAfter']:.3f}, nearest own "
        f"{g['nearestBefore']} -> {g['nearestAfter']}, respiration shipped on "
        f"{g['respirationWon']} types, two-voice on {g['twoVoiceWon']} of "
        f"{g['twoVoiceScreened']} screened"
    )
    # The per-species table: one line per species where anything shipped, worst
    # median move first — the full per-type audit is in --report.
    moved = [
        (sid, s)
        for sid, s in report["species"].items()
        if s["respirationWon"] or s["twoVoiceWon"]
    ]
    moved.sort(key=lambda kv: -(kv[1]["respirationWon"] + kv[1]["twoVoiceWon"]))
    for sid, s in moved[:40]:
        resp = s["respiration"]
        obj = (
            f"obj {resp['seedScore']:.3f} -> {resp['bestScore']:.3f}"
            if resp
            else "respiration fit off"
        )
        log(
            f"  {sid:28} resp {s['respirationWon']}/{s['scored']} "
            f"({obj}), "
            f"two-voice {s['twoVoiceWon']}/{s['twoVoiceScreened']}, nearest "
            f"{s['nearestBefore']} -> {s['nearestAfter']}"
        )
    if len(moved) > 40:
        log(f"  ... and {len(moved) - 40} more species in the report")
    return 0


def cmd_docrefit(args: argparse.Namespace) -> int:
    """Re-fit the texture of the authored one-tone calls (docrefit.py; docs/16 §16.4).

    Reads the merged learned inventory and the store's typing.json, finds each
    documented pure-tone call's nearest learned type by pitch, and searches the
    noise x rough grids against that type's reference. A texture ships on a call ONLY
    where it beats the call's authored render by the margin; the call's contour,
    duration, function and citation never move. The input inventory is never modified
    in place unless `--out` points at it.
    """
    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    try:
        typing = respfit.load_typing(store.root)
    except RuntimeError as exc:
        log(str(exc))
        return 2
    inventory_path = Path(args.inventory)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    calibration = ensure_calibration(Path(args.calibration_dir))
    features.self_test(verbose=False)
    learn.self_test(verbose=False)
    docrefit.self_test(verbose=False)

    t0 = time.time()
    document, report = docrefit.docrefit_inventory(
        store.syllables,
        typing,
        inventory,
        calibration,
        recording_descriptors={
            rid: np.asarray(row, dtype=np.float64)
            for rid, row in store.recording_descriptors.items()
        },
        margin=args.margin,
        f0_cap=args.f0_cap,
    )
    out = (
        Path(args.out)
        if args.out
        else inventory_path.with_name(inventory_path.stem + ".docrefit.json")
    )
    learn.write_learned_inventory(out, document)
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf-8"
        )

    g = report["global"]
    log("")
    log(f"wrote {out} ({time.time() - t0:.0f}s)")
    log(
        f"docrefit verdict: {g['shipped']} of {g['callsScored']} scored one-tone "
        f"calls shipped a measured texture"
        + (
            f" (median gain {g['medianGainShipped']:.3f}, "
            f"median cosine after {g['medianAfterShipped']:.3f})"
            if g["shipped"]
            else ""
        )
    )
    shipped_species = [
        (sid, s) for sid, s in report["species"].items() if s["shipped"]
    ]
    for sid, s in sorted(shipped_species, key=lambda kv: -kv[1]["shipped"])[:40]:
        log(f"  {sid:28} {s['shipped']}/{s['scored']} calls re-fitted")
    if len(shipped_species) > 40:
        log(f"  ... and {len(shipped_species) - 40} more species in the report")
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
    "aug_channel_db": 0.0,
    "mixstyle_alpha": 0.0,
    "w_record": 0.0,
    "recordist_min_patches": 20,
}


def critic_default(name: str) -> Any:
    try:
        from .critic import CriticConfig

        return getattr(CriticConfig(), name)
    except ImportError:
        return _CRITIC_FALLBACK_DEFAULTS[name]


def _critic_provenance(
    critic_arg: str | None, embeddings_path: Path | None
) -> dict[str, Any] | None:
    """Which critic produced the embeddings, for the assets to record.

    Prefers the sidecar `embeddings.json` `critic embed` wrote (it carries the weights'
    hash, so an embedding file can be tied to the exact checkpoint that made it); falls
    back to the path and mtime of the critic the build itself used.
    """
    if embeddings_path is not None:
        sidecar = embeddings_path.with_suffix(".json")
        if sidecar.exists():
            try:
                blob = json.loads(sidecar.read_text(encoding="utf-8"))
                if blob.get("critic"):
                    return dict(blob["critic"])
            except ValueError:
                pass
    path = Path(critic_arg) if critic_arg else (DEFAULT_CRITIC if DEFAULT_CRITIC.exists() else None)
    if path is None or not path.exists():
        return None
    return {
        "path": str(path),
        "mtime": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(
            timespec="seconds"
        ),
    }


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
    real = critic_mod.real_patches(store.syllables, recording_meta=store.recordings)
    log(f"real side: {len(real)} patches over {len(real.names)} species, "
        f"{len(real.recording_names)} recordings")

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
        aug_channel_db=args.aug_channel_db,
        mixstyle_alpha=args.mixstyle_alpha,
        w_record=args.w_record,
        recordist_min_patches=args.recordist_min_patches,
        record_within_species=args.record_within_species,
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


def cmd_critic_embed(args: argparse.Namespace) -> int:
    """Embed every stored syllable once, so builds can cluster in the learned space.

    The expensive part of an embed-space galaxy is running the critic over the store;
    doing it here, to a file keyed by the store's own row order, means `build`,
    `spacemap` and `placement` all read the same embeddings instead of each re-running
    the network. The sidecar JSON records which checkpoint produced them, so a build can
    never silently mix embeddings from two critics.
    """
    try:
        # The probe, not the use: `write_store_embeddings` imports the module
        # itself. It runs here so a machine without torch reads the install line
        # instead of a traceback thrown halfway through loading the store.
        from . import critic  # noqa: F401
    except ImportError as exc:
        log(f"torch is not installed ({exc}). `uv sync --extra critic` and try again.")
        return 2

    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    trained = load_critic(args.critic, prefer_gpu=not args.cpu)
    if trained is None:
        return 2

    write_store_embeddings(
        store, trained, Path(args.critic), out=args.out, batch=args.batch, log=log
    )
    log("next: uv run birdy-pipeline build --harvest-store " + str(store.root) +
        " --space embed")
    return 0


def write_store_embeddings(
    store: harvest.HarvestStore,
    trained: Any,
    critic_path: Path,
    out: str | Path | None = None,
    batch: int = 256,
    log: Any = log,
) -> Path:
    """Run the critic over a store and write `embeddings.f32` + its sidecar.

    Split out of `cmd_critic_embed` so the Learn tab writes the same bytes by the same
    code (`server._fit`): a fit that leaves no embeddings behind is a fit whose next
    build silently drops to the descriptor space, or re-runs the network it just ran.
    """
    from . import critic as critic_mod

    t0 = time.time()
    embeddings = critic_mod.embed_store(store, trained, batch=batch, log=log)
    path = Path(out) if out else Path(store.root) / EMBEDDINGS_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(embeddings.astype("<f4", copy=False).ravel(order="C").tobytes())
    sidecar = {
        "n": int(embeddings.shape[0]),
        "dim": int(embeddings.shape[1]),
        "store": str(store.root),
        "order": "store.syllables row order — the same order patches.f16 is written in",
        "critic": {
            "path": str(critic_path),
            "mtime": datetime.fromtimestamp(
                critic_path.stat().st_mtime, timezone.utc
            ).isoformat(timespec="seconds"),
            "sha256": hashlib.sha256(critic_path.read_bytes()).hexdigest(),
        },
        "countNaN": int(np.isnan(embeddings[:, 0]).sum()),
        "writtenAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.with_suffix(".json").write_text(json.dumps(sidecar, indent=1), encoding="utf-8")
    log(f"wrote {path} ({embeddings.shape[0]} x {embeddings.shape[1]} float32, "
        f"{sidecar['countNaN']} NaN rows) + {path.with_suffix('.json')} "
        f"in {time.time() - t0:.1f}s")
    return path


def cmd_critic_groupings(args: argparse.Namespace) -> int:
    """The geometry battery on a critic's stored embeddings, without a build.

    The source-invariance verdict instrument (docs/14 §14.4's table, recomputed per
    retrain): does the embedding organise by species or by recording condition? A
    full build answers that as a side effect, but a recipe sweep needs the answer per
    candidate critic, and a build is a quarter of an hour of rendering that does not
    depend on the critic at all. This runs `geometry.analyse` directly on the store's
    `embeddings.f32`, so a sweep step costs the embedding pass and nothing else.
    """
    try:
        from . import geometry as geo
    except ImportError:
        from . import geometry as geo  # geometry has no optional deps; keep symmetry
    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    emb_path = (
        Path(args.embeddings) if args.embeddings else Path(args.store) / EMBEDDINGS_NAME
    )
    if not emb_path.exists():
        log(f"no embeddings at {emb_path} — run `birdy-pipeline critic embed "
            f"--store {args.store}` first")
        return 2
    emb = read_store_embeddings(emb_path, len(store.syllables), log=log)
    if emb is None:
        return 2

    kept = [i for i, o in enumerate(store.syllables) if o.descriptor]
    z = emb[kept]
    finite = np.all(np.isfinite(z), axis=1)
    if int((~finite).sum()):
        log(f"{int((~finite).sum())} of {len(kept)} observations have no embedding and "
            "are left out")
    kept = [i for i, ok in zip(kept, finite) if ok]
    z = z[finite]
    obs = [store.syllables[i] for i in kept]
    z = (z - z.mean(axis=0)) / np.maximum(z.std(axis=0), 1.0e-6)

    typing_path = Path(args.store) / learn.TYPING_NAME
    type_of: dict[tuple[str, str, int], str] = {}
    if typing_path.exists():
        typing = json.loads(typing_path.read_text(encoding="utf-8"))
        type_of = {
            (e["speciesId"], e["recordingId"], int(e["order"])): str(e["typeId"])
            for e in typing.get("entries", [])
        }
    species_id = [o.species_id for o in obs]
    recording_id = [o.recording_id for o in obs]
    syllable_id = [type_of.get((o.species_id, o.recording_id, o.order), "") for o in obs]
    groupings = geo.label_sets(
        species_id=species_id,
        syllable_id=syllable_id,
        recording_id=recording_id,
        source=[harvest.SOURCE] * len(obs),
        recordings=store.recordings,
    )
    blocks = geo.blocks_for(
        species_id, syllable_id, recording_id, [harvest.SOURCE] * len(obs)
    )
    relations = geo.analyse(
        {f"{z.shape[1]}-d critic embedding": (z, "cosine")},
        groupings,
        seed=args.seed,
        blocks=blocks,
    )
    log(geo.format_table(relations))
    log(f"  => {geo.summarise(relations)['headline']}")
    return 0


def cmd_critic_label_novel(args: argparse.Namespace) -> int:
    """Perch 2.0 second opinion for the syllables the novelty scorer flags.

    The store keeps no audio, so the only labellable targets are syllables whose
    recording is still in the owner-sanctioned iNat cache (AGENTS.md); everything
    else is counted and reported as unlabelable, never silently dropped. The output
    is metadata — `perch.py`'s module docstring carries the discipline, and the
    JSONL's `_meta` record carries the honesty label verbatim.
    """
    try:
        from . import perch as perch_mod
    except ImportError as exc:
        log(f"onnxruntime is not installed ({exc}). `uv sync --extra perch` and try again.")
        return 2

    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2

    flagged = np.array([bool(o.novel) for o in store.syllables])
    targets = flagged
    novelty_path = Path(args.critic).with_name(Path(args.critic).stem + "-novelty.json")
    embeddings_path = (
        Path(args.embeddings) if args.embeddings else Path(args.store) / EMBEDDINGS_NAME
    )
    if novelty_path.exists() and embeddings_path.exists():
        centroids, threshold = perch_mod.load_novelty_centroids(novelty_path)
        recomputed = perch_mod.novelty_mask(store, embeddings_path, centroids, threshold)
        # The stored flag is ingest-time evidence and wins where set; the recompute
        # covers rows harvested before the scorer existed (see perch.novelty_mask).
        targets = flagged | recomputed
        log(f"novelty targets: {int(flagged.sum())} flagged at ingest + "
            f"{int((recomputed & ~flagged).sum())} rederived from {novelty_path.name} "
            f"(threshold {threshold:.4f}) = {int(targets.sum())}")
    else:
        log(f"no {novelty_path.name} / {embeddings_path.name} pair — labelling only "
            f"the {int(flagged.sum())} syllables flagged at ingest")

    if not targets.any():
        log("nothing to label: no flagged syllables and no novelty scorer to derive them from")
        return 2

    model = perch_mod.ensure_model(Path(args.model_dir))
    out = Path(args.out) if args.out else Path(args.store) / "perch-labels.jsonl"
    t0 = time.time()
    counts = perch_mod.label_novel(
        store,
        Path(args.audio_cache),
        out,
        model,
        targets,
        limit=args.limit,
        batch=args.batch,
        keep_embeddings=args.keep_embeddings,
        log=log,
    )
    log(f"done in {time.time() - t0:.1f}s ({counts['labelled']} labels)")
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

    # --- render-free placement, in both spaces ---
    #
    # The table above places *resyntheses*; this places the stored field observations
    # themselves against per-species mean references — the galaxy's own geometry, with no
    # rendering involved, so it is cheap enough to run every time. It measures something
    # different from the headline number (how separable the species are in each space,
    # not how well the synthesiser lands in it) and says so rather than borrowing the
    # headline's framing. Each species reference includes the points being scored against
    # it; at hundreds of observations per species that moves nothing measurable.
    def place(rows: np.ndarray, species: list[str]) -> tuple[float, int]:
        """Share of rows whose nearest per-species mean reference is their own species."""
        unit = rows / np.maximum(np.linalg.norm(rows, axis=1, keepdims=True), 1e-12)
        names = sorted(set(species))
        refs = np.stack([unit[[i for i, s in enumerate(species) if s == n]].mean(axis=0)
                         for n in names])
        refs = refs / np.maximum(np.linalg.norm(refs, axis=1, keepdims=True), 1e-12)
        nearest = (unit @ refs.T).argmax(axis=1)
        own = np.asarray([names.index(s) for s in species])
        return float((nearest == own).mean()), len(names)

    obs = [
        (o.species_id, np.asarray(o.descriptor, dtype=float))
        for o in store.syllables
        if o.descriptor and o.species_id in references
    ]
    rows28 = np.stack([d for _, d in obs])
    if frame is not None:
        rows28 = features.standardise(rows28, frame[0], frame[1])
    species28 = [sid for sid, _ in obs]
    share28, n_species = place(rows28, species28)
    log("")
    log(f"render-free: {len(obs)} stored field syllables against per-species mean "
        f"references, {n_species} species (chance {1.0 / n_species:.1%})")
    log(f"  28-d descriptor space:   {share28:6.1%} nearest own species")
    emb_path = (
        Path(args.embeddings)
        if args.embeddings
        else Path(args.store) / EMBEDDINGS_NAME
    )
    if emb_path.exists():
        emb = read_store_embeddings(emb_path, len(store.syllables), log=log)
        if emb is None:
            return 2
        obs_idx = [
            i for i, o in enumerate(store.syllables)
            if o.descriptor and o.species_id in references
        ]
        rows32 = emb[obs_idx]
        finite = np.all(np.isfinite(rows32), axis=1)
        rows32 = rows32[finite]
        species32 = [store.syllables[i].species_id for i, m in zip(obs_idx, finite) if m]
        rows32 = (rows32 - rows32.mean(axis=0)) / np.maximum(rows32.std(axis=0), 1e-6)
        share32, _ = place(rows32, species32)
        log(f"  32-d embedding space:  {share32:6.1%} nearest own species "
            f"(the galaxy's geometry once built with --space embed)")
    else:
        log(f"  32-d embedding space:  not measured — no {emb_path.name}; run "
            f"`birdy-pipeline critic embed --store {args.store}` first")

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


def cmd_specbench(args: argparse.Namespace) -> int:
    """The spectral bench: correlate the resynthesis cosine with audible distortion.

    Renders fitted types and measures MCD and multi-resolution STFT error against the
    original audio they were fitted from — the only run in the pipeline that reads the
    owner-sanctioned iNat audio cache for anything but training (AGENTS.md). It writes
    nothing but the `--out` report; the cache is only read.
    """
    from . import specbench

    specbench.self_test(verbose=False)
    store = harvest.HarvestStore(Path(args.store))
    if not (store.root / learn.TYPING_NAME).exists():
        log(f"specbench needs the store's typing.json — run `learn` on {store.root} "
            "first")
        return 2
    inventory = load_inventory(Path(args.inventory))

    # The calibration table the renders were fitted with. Looked up, never built: a
    # bench run must not write beside a store it was pointed at. Without one the
    # renderer falls back to the analytic beta/amp mapping and the recomputed cosines
    # drift from the stored ones — said loudly rather than silently.
    calibration: Calibration | None = None
    cdir = Path(args.calibration_dir) if args.calibration_dir else store.root.parent
    cpath = cdir / CALIBRATION_NAME
    if cpath.exists():
        calibration = Calibration.from_dict(
            json.loads(cpath.read_text(encoding="utf-8"))
        )
        log(f"using {cpath}")
    else:
        log(f"NOTE: no {CALIBRATION_NAME} in {cdir}; rendering with the analytic "
            "fallbacks, so recomputed cosines will drift from the stored ones. Pass "
            "--calibration-dir to the table the fits were made with.")

    report = specbench.run_bench(
        store,
        inventory,
        Path(args.audio_cache),
        calibration,
        limit=args.limit,
        log=log,
        extra_caches=[Path(p) for p in (args.extra_audio_cache or [])],
        band_cap_hz=None if args.no_band_cap else args.band_cap_hz,
    )
    log(specbench.format_report(report))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        log(f"wrote {out}")
    return 0


def cmd_syntax(args: argparse.Namespace) -> int:
    """Run the P1 grammar bake-off of docs/18 on a store's typed bouts.

    Reads the store exactly as `learn` does — same observations, same typing.json,
    same bout rule — and changes nothing it reads: the verdict decides whether the
    shipped first-order grammar of `learn.learn_grammar` has a measurably better
    successor, it does not install one.
    """
    syntax_mod.self_test(verbose=False)
    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    typing = syntax_mod.load_typing(store.root)
    if not typing:
        log(f"{store.root} has no {learn.TYPING_NAME} — run `learn` first")
        return 2
    t0 = time.time()
    bouts = syntax_mod.species_bouts(store.syllables, typing)
    log(f"{sum(len(b) for b in bouts.values())} bouts of "
        f">= {syntax_mod.MIN_BOUT_TOKENS} tokens over {len(bouts)} species")
    if args.compare_backoff:
        report = syntax_mod.smoothing_comparison(
            bouts, alpha=args.alpha, min_bouts=args.min_bouts
        )
        print(syntax_mod.format_smoothing_report(report))
    else:
        ks = tuple(int(x) for x in args.ks.split(","))
        report = syntax_mod.bake_off(
            bouts, alpha=args.alpha, ks=ks, min_bouts=args.min_bouts,
            max_iter=args.max_iter,
        )
        print(syntax_mod.format_report(report))
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf-8"
        )
        log(f"wrote {args.json}")
    log(f"took {time.time() - t0:.1f}s")
    return 0


def cmd_songspace(args: argparse.Namespace) -> int:
    """Run the P2 song-space baseline of docs/18 on a store's typed bouts.

    Reads the store exactly as `learn` does — same observations, same typing.json,
    same bout rule — plus song-typing.json when learn wrote one, and changes
    nothing it reads: the verdict grades the hand-written kernel baseline the
    learned song encoder of a later stage must beat, it does not install one.
    """
    songspace_mod.self_test(verbose=False)
    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    if not (store.root / learn.TYPING_NAME).exists():
        log(f"{store.root} has no {learn.TYPING_NAME} — run `learn` first")
        return 2
    report = songspace_mod.evaluate(store, rhythm_weight=args.rhythm_weight)
    print(songspace_mod.format_report(report))
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf-8"
        )
        log(f"wrote {args.json}")
    return 0


def cmd_spacemap(args: argparse.Namespace) -> int:
    """Fit the browser's 28-d -> 32-d space map on a store and grade it honestly.

    The standalone version of what `build --space embed` folds into feature-space.json,
    for iterating on the map without rebuilding a galaxy. The split is by recording, the
    numbers are on recordings the map never fitted, and the nearest-centroid agreement
    here is against per-species centroids — the build replaces it with the agreement
    against the galaxy's own clusters, which is the number that ships.
    """
    from . import spacemap

    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    emb_path = (
        Path(args.embeddings) if args.embeddings else Path(args.store) / EMBEDDINGS_NAME
    )
    if not emb_path.exists():
        log(f"no embeddings at {emb_path} — run `birdy-pipeline critic embed "
            f"--store {args.store}` first")
        return 2

    emb = read_store_embeddings(emb_path, len(store.syllables), log=log)
    if emb is None:
        return 2
    kept = [i for i, o in enumerate(store.syllables) if o.descriptor]
    z = emb[kept]
    finite = np.all(np.isfinite(z), axis=1)
    if int((~finite).sum()):
        log(f"{int((~finite).sum())} of {len(kept)} observations have no embedding and "
            "are left out of the fit")
    z = z[finite]
    x = np.stack([
        np.asarray(store.syllables[i].descriptor, dtype=np.float64)
        for i, m in zip(kept, finite) if m
    ])
    recordings_of = [store.syllables[i].recording_id for i, m in zip(kept, finite) if m]
    species_of = [store.syllables[i].species_id for i, m in zip(kept, finite) if m]

    # The browser standardises its live descriptor against the *window* frame, so the
    # map is fitted on descriptors standardised the same way — here the store's own
    # window statistics; a build passes its shipped frame instead. The embedding moments
    # are over the embedded points themselves, as they are in the build.
    windows = store.to_point_set()
    x28 = features.standardise(x, windows.x.mean(axis=0), windows.x.std(axis=0))
    z32 = (z - z.mean(axis=0)) / np.maximum(z.std(axis=0), 1.0e-6)

    t0 = time.time()
    space_map = spacemap.fit_map(x28, z32, recordings_of, seed=args.seed, log=log)
    quality = dict(space_map.quality)

    # Species-level agreement, the standalone stand-in for the galaxy's own centroids.
    names = sorted(set(species_of))
    refs = np.stack([
        spacemap._unit_rows(z32[[i for i, s in enumerate(species_of) if s == n]]).mean(axis=0)
        for n in names
    ])
    quality["centroidAgreement"] = round(
        spacemap.centroid_agreement(space_map.eval_mapped, space_map.eval_true, refs), 4
    )
    quality["centroidAgreementDefinition"] = (
        "share of held-out syllables whose nearest per-species centroid is the same "
        "through the map as through the critic (standalone; a build measures this "
        "against the galaxy's own cluster centroids)"
    )

    deciles = quality["deciles"]
    log("")
    log(f"space map: {quality['pairs']} pairs, ridge lambda {quality['lambda']:g}, "
        f"graded on {quality['evalPairs']} syllables of {quality['evalRecordings']} "
        f"held-out recordings ({time.time() - t0:.1f}s)")
    log(f"  median cosine mapped-vs-true: {quality['medianCosine']:.3f} "
        f"(target >= {quality['target']})")
    log(f"  deciles: " + " ".join(f"{d:.3f}" for d in deciles))
    log(f"  nearest-centroid agreement (species centroids): "
        f"{quality['centroidAgreement']:.3f}")
    if quality["accepted"]:
        log("  accepted: the browser may match in the embedding space")
    else:
        log("  BELOW GATE: the map ships with accepted: false and the browser stays on "
            "the 28-d path. This is the honest answer, not a build failure — but the "
            "embedding-space activation stays off until it improves.")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "map": space_map.to_json(),
                    "mapQuality": quality,
                    "frame": {
                        "mean": [float(v) for v in windows.x.mean(axis=0)],
                        "std": [float(v) for v in windows.x.std(axis=0)],
                        "note": "the store's own window statistics; a build ships its "
                        "own frame and recomputes the map against it",
                    },
                    "embeddingMoments": {
                        "mean": [float(v) for v in z.mean(axis=0)],
                        "std": [float(v) for v in z.std(axis=0)],
                    },
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        log(f"wrote {out}")
    return 0


def cmd_relations(args: argparse.Namespace) -> int:
    """Cross-species relations from a store's typing and embeddings (relations.py).

    The standalone form of what `build` ships into the assets as `relations.json`:
    shared/convergent type candidates and the species similarity matrix, both in the
    critic's 32-d space. The three files it needs are the three the learning loop
    already writes — the store, its typing.json (`learn`) and its embeddings.f32
    (`critic embed`) — and each absence says which command produces it.
    """
    from . import relations as relations_mod

    store = harvest.HarvestStore(Path(args.store))
    if not store.syllables:
        log(f"{store.root} holds no syllable observations — run `harvest` first")
        return 2
    typing_path = Path(args.store) / learn.TYPING_NAME
    if not typing_path.exists():
        log(f"no {typing_path} — run `learn` first; relations are between types")
        return 2
    emb_path = (
        Path(args.embeddings) if args.embeddings else Path(args.store) / EMBEDDINGS_NAME
    )
    if not emb_path.exists():
        log(f"no embeddings at {emb_path} — run `birdy-pipeline critic embed "
            f"--store {args.store}` first; relations live in the critic's space")
        return 2
    relations_mod.self_test(verbose=False)

    t0 = time.time()
    typing = json.loads(typing_path.read_text(encoding="utf-8"))
    emb = read_store_embeddings(emb_path, len(store.syllables), log=log)
    if emb is None:
        return 2
    inventory = load_inventory(Path(args.inventory)) if args.inventory else None
    document = relations_mod.compute_relations(store, emb, typing, inventory)

    pairs = document["speciesPairs"]
    n_shared = sum(len(p["sharedTypes"]) for p in pairs)
    log(f"{len(pairs)} species pairs, {n_shared} shared-type candidate(s) under "
        f"threshold {document['sharedTypeThreshold']} ({time.time() - t0:.1f}s)")
    log("nearest species pairs:")
    for p in pairs[:12]:
        log(f"  {p['a']:26} {p['b']:26} {p['distance']:.3f} "
            f"(centroid {p['centroidDistance']:.3f}, 1-NN "
            f"{p['nearestNeighbourDistance'] if p['nearestNeighbourDistance'] is not None else 'n/a'}"
            f") shared {len(p['sharedTypes'])}")
    if args.out:
        # The complete document: this verb's output is the analysis, not a shipped asset,
        # so it is not trimmed to what a browser reads (see `shipped_relations`).
        relations_mod.write_relations(Path(args.out), document, per_species=None)
        log(f"wrote {args.out} (complete document, {len(pairs)} pairs — the build ships a "
            f"trimmed copy, see relations.shipped_relations)")
    return 0


def expand_targets(
    store: harvest.HarvestStore,
    discovered: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str]]:
    """Discovered species the store does not cover, ranked, each with its reason.

    Coverage is checked against both halves of the store — the descriptor strata and
    the syllable observations — because they are populated separately and either one
    alone can miss a species the other holds.

    Ranking: congeners of high-novelty species first. A genus whose collected members
    keep producing syllables the novelty scorer flags as unheard is a genus the corpus
    under-describes, so its uncollected members are the most promising place to look
    next. With no novelty flags at all the order falls back to the registry's own
    (most-recorded first, as discovered).
    """
    covered = set(store.strata) | {o.species_id for o in store.syllables}
    novelty: Counter[str] = Counter(o.species_id for o in store.syllables if o.novel)
    genus_novelty: Counter[str] = Counter()
    for species_id, n in novelty.items():
        genus_novelty[species_id.split("_")[0]] += n
    ranked: list[tuple[dict[str, Any], str, int]] = []
    for e in discovered:
        if e["id"] in covered:
            continue
        genus = (e.get("scientific", "").split() or [""])[0].lower()
        n = genus_novelty.get(genus, 0)
        reason = (
            f"congener of high-novelty {genus} ({n} flagged syllable(s))"
            if n
            else "no store coverage"
        )
        ranked.append((e, reason, n))
    ranked.sort(key=lambda t: (-t[2], -int(t[0].get("recordings", 0)), t[0]["id"]))
    return [(e, reason) for e, reason, _ in ranked]


def cmd_expand(
    args: argparse.Namespace, should_stop: Callable[[], bool] | None = None
) -> int:
    """Grow the corpus outward: harvest discovered species the store does not cover.

    Target selection is the only new logic (`expand_targets`); everything after it is
    the existing path run per target: harvest the species, re-embed the store, refit
    (id inheritance on, so the refit renames nothing), grow the galaxy. Bounded by
    --max-species and --max-recordings because xeno-canto is rate-limited; the client
    pauses between requests exactly as `harvest` does. `--dry-run` prints the ranked
    target list and touches nothing — no network, no writes.
    """
    store = harvest.HarvestStore(Path(args.store))
    discovered = harvest.load_discovered(Path(args.discovered))
    if not discovered:
        log(f"no discovered species in {args.discovered} — nothing to expand towards; "
            "run `harvest --discover` first")
        return 2
    ranked = expand_targets(store, discovered)
    if not ranked:
        log(f"all {len(discovered)} discovered species already have store coverage — "
            "nothing to expand towards")
        return 0
    chosen = ranked[: max(0, args.max_species)]
    log(f"{len(ranked)} discovered species without store coverage; {len(chosen)} "
        f"selected (--max-species {args.max_species}, --max-recordings "
        f"{args.max_recordings}):")
    for e, reason in chosen:
        log(f"  {e['id']:28} {e.get('common', '')[:30]:30} {reason}")
    if args.dry_run:
        log("dry run: nothing fetched, nothing written")
        return 0

    key = args.xc_key or os.environ.get("XC_API_KEY", "")
    try:
        client = harvest.XenoCanto(key, pause=args.pause)
    except RuntimeError as exc:
        log(str(exc))
        return 2

    critic_arg = args.critic or (str(DEFAULT_CRITIC) if DEFAULT_CRITIC.exists() else None)
    for e, _ in chosen:
        sid = e["id"]
        if should_stop and should_stop():
            log("stopping: asked to")
            break
        log(f"--- expand {sid}: harvesting ---")
        targets = harvest.species_queries(
            {"species": []}, quality=args.quality, extra=[e]
        )
        if not targets:
            log(f"  no xeno-canto query for {sid} "
                f"(scientific {e.get('scientific')!r}); skipped")
            continue
        report = harvest.harvest_xeno_canto(
            store, client, targets,
            per_species=args.max_recordings,
            should_stop=should_stop,
        )
        store.save()
        log(harvest.format_report(report, store))

        if critic_arg:
            log(f"--- expand {sid}: embedding the store ---")
            try:
                cmd_critic_embed(build_parser().parse_args(
                    ["critic", "embed", "--store", str(args.store),
                     "--critic", critic_arg]
                    + (["--cpu"] if args.cpu else [])
                ))
            except Exception as exc:
                log(f"  embed skipped: {exc}")

        log(f"--- expand {sid}: fitting ---")
        learn_argv = [
            "learn", "--store", str(args.store), "--out", str(args.learned),
            "--inventory", str(args.inventory),
            "--calibration-dir", str(args.calibration_dir),
            "--seed", str(args.seed),
        ]
        if critic_arg:
            learn_argv += ["--critic", critic_arg, "--embed-typing"]
        if args.cpu:
            learn_argv += ["--cpu"]
        code = cmd_learn(build_parser().parse_args(learn_argv))
        if code != 0:
            log(f"  fit exited {code}; not growing the galaxy for {sid}")
            continue

        log(f"--- expand {sid}: growing the galaxy ---")
        try:
            grow_argv = [
                "grow", "--out", str(args.out),
                "--harvest-store", str(args.store),
                "--inventory", str(args.learned),
            ]
            if critic_arg:
                grow_argv += ["--critic", critic_arg]
            cmd_grow(build_parser().parse_args(grow_argv))
        except Exception as exc:
            log(f"  grow skipped: {exc}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Local control surface for the Learn tab. Loopback only — see server.py."""
    from . import server as server_mod

    server_mod.self_test(verbose=False)
    # None means the flag was not given, and a defaulted store is a guess — the default
    # is out/harvest while the working store is out/harvest-gan, a confusion that has
    # already cost a galaxy (docs/11 §11.1). So the default announces itself and warns
    # about newer siblings; an explicit --store is a decision and behaves as before.
    defaulted = args.store is None
    store_path = DEFAULT_HARVEST_STORE if defaulted else Path(args.store)
    if defaulted:
        for line in server_mod.default_store_report(store_path):
            log(line)
    server_mod.serve(
        server_mod.Pipeline(
            store_path=store_path,
            inventory_path=Path(args.inventory),
            learned_path=Path(args.learned),
            out_path=Path(args.out),
            critic_path=Path(args.critic) if args.critic else None,
            critic_weight=args.critic_weight,
            embed_typing=args.embed_typing,
            inverse_path=Path(args.inverse) if args.inverse else None,
            inverse_two_start=not args.no_inverse_two_start,
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


# Where the browser's match ramp sits in the distribution of real field syllables.
#
# **These two percentiles are the rule; the two numbers in `features.ts` are only its
# last answer.** The constants were tuned by hand against a 2026-07 corpus and then went
# stale in silence: by v6 the whole distribution had moved up 0.07-0.14, which put the
# floor (0.62) below the *first* percentile — excluding nothing — and the ceiling (0.86)
# below the *median* real syllable, so more than half of all genuine birdsong pegged the
# ramp at full strength and "a partial match should look partial" had quietly stopped
# being true. Nothing caught it, because nothing re-measured it.
#
# So the ramp is a property of the assets and now ships with them. `matchRamp` in the
# manifest is written by every build, the app reads it, and the constants remain only as
# the fallback for an older asset set.
#
# **p5** keeps the floor's stated promise — it lets in about nineteen field syllables in
# twenty — and it is where the hand-tuned floor sat in the corpus it was tuned against
# (0.62 against that corpus's p5 of 0.605).
#
# **p90** is the ceiling: above it a match is unambiguous by the corpus's own account,
# and below it the response ramps. It has to sit well above the median or the ramp is
# saturated for the typical case, which is exactly the failure being fixed.
MATCH_RAMP_FLOOR_PCT = 5
MATCH_RAMP_CEILING_PCT = 90

#: Reported so a reader can see the shape either side of the two that are used.
MATCH_RAMP_PERCENTILES = (1, 5, 10, 25, 50, 75, 90, 95, 99)


def measure_match_ramp(
    out: Path, store_path: Path, sample: int = 2000, seed: int = 0
) -> dict | None:
    """Score real field syllables and the noise probes against the *shipped* centroids.

    Returns the manifest's `matchRamp` record, or None when there is no harvest store to
    measure against — a build with no field audio has nothing to set the ramp from, and
    an invented ramp is worse than the fallback.

    Runs against the finished asset directory rather than against the build's in-memory
    state on purpose: it is then the same code path whether it runs at the end of a build
    or by hand months later on the installed assets, and the two can never disagree.
    """
    store_path = Path(store_path)
    if not (store_path / "state.json").exists():
        return None

    centroids = json.loads((out / "centroids.json").read_text(encoding="utf-8"))
    space = json.loads((out / "feature-space.json").read_text(encoding="utf-8"))
    mean = np.asarray(space["mean"], dtype=float)
    std = np.maximum(np.asarray(space["std"], dtype=float), 1.0e-6)
    vectors = galaxy.centroid_vectors(out, centroids)["vector"]
    vectors = vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1.0e-12)

    rng = np.random.default_rng(seed)
    store = harvest.HarvestStore(store_path)
    rows = [np.asarray(o.descriptor, dtype=float) for o in store.syllables if o.descriptor]
    if not rows:
        return None
    chosen = rows if len(rows) <= sample else [
        rows[i] for i in rng.choice(len(rows), sample, replace=False)
    ]

    z = features.standardise(np.asarray(chosen, dtype=float), mean, std)
    z = z / np.maximum(np.linalg.norm(z, axis=1, keepdims=True), 1.0e-12)
    scores = np.max(z @ vectors.T, axis=1)

    pct = {f"p{q}": round(float(np.percentile(scores, q)), 4) for q in MATCH_RAMP_PERCENTILES}
    return {
        "floor": round(float(np.percentile(scores, MATCH_RAMP_FLOOR_PCT)), 4),
        "ceiling": round(float(np.percentile(scores, MATCH_RAMP_CEILING_PCT)), 4),
        "rule": f"floor = p{MATCH_RAMP_FLOOR_PCT}, ceiling = p{MATCH_RAMP_CEILING_PCT}",
        "percentiles": pct,
        "max": round(float(scores.max()), 4),
        "sampled": len(chosen),
        "population": len(rows),
        "store": str(store_path),
        "definition": (
            "best-centroid cosine over real harvested field syllables; the browser ramps "
            "activation strength between floor and ceiling with a smoothstep, so below "
            "the floor nothing lights and above the ceiling a match reads as certain"
        ),
    }


def cmd_quality_remeasure(args: argparse.Namespace) -> int:
    """Fill `snr`/`clipped` on the observations harvested before those fields existed.

    59 % of `out/harvest-gan` carries no `snr`, and `learn.quality_weight` reads that as
    neutral. It is not a sampling accident — 188 986 of the 199 993 unmeasured rows are
    the iNat sweep, and its audio is still in the owner-sanctioned cache, so the
    measurement was available on this disk the whole time. `quality.py` explains why the
    pass is exact rather than approximate, and why it fails closed.
    """
    # Before touching the corpus, prove this build still reproduces the arithmetic the
    # corpus was harvested with. The pass writes 188 986 rows; the check costs a second.
    quality.self_test(verbose=False)
    store_root = Path(args.store)
    try:
        report = quality.remeasure_store(
            store_root,
            Path(args.audio_cache),
            max_seconds=args.max_seconds,
            dry_run=args.dry_run,
            log=log,
        )
    except FileNotFoundError as exc:
        log(str(exc))
        return 2
    log(report.format(store_root))
    for rid, why in sorted(report.undecodable.items())[:10]:
        log(f"  undecodable {rid}: {why[:120]}")
    if report.drifted:
        # Not a warning to skim past: it means this build's segmentation is not the one
        # that harvested the store, so the pass is inapplicable rather than merely thin.
        return 1
    return 0


def cmd_thresholds(args: argparse.Namespace) -> int:
    """Re-measure the match ramp the browser uses to say "this is not birdsong".

    `app/src/lib/audio/features.ts` scales every activation by how well the best centroid
    matches, ramping between two constants. Those constants are only meaningful against
    the corpus that is actually shipped: a galaxy of synthetic renders and a galaxy that
    is two thirds field audio put birdsong and noise in different places. This prints
    where each sits now, so the ramp can be set from the measurement instead of from
    memory.

    `--write` puts the answer in the manifest, which is where the app now reads it from.
    Every build writes it too; this is the way to repair an asset set without a rebuild.
    """
    out = Path(args.out)
    centroids = json.loads((out / "centroids.json").read_text(encoding="utf-8"))
    space = json.loads((out / "feature-space.json").read_text(encoding="utf-8"))
    mean = np.asarray(space["mean"], dtype=float)
    std = np.maximum(np.asarray(space["std"], dtype=float), 1.0e-6)
    vectors = galaxy.centroid_vectors(out, centroids)["vector"]
    vectors = vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1.0e-12)

    def best_match(descriptor: np.ndarray) -> tuple[float, int]:
        z = features.standardise(descriptor, mean, std)
        z = z / max(float(np.linalg.norm(z)), 1.0e-12)
        scores = vectors @ z
        i = int(np.argmax(scores))
        return float(scores[i]), i

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
    probe_scores: list[float] = []
    for name, audio in probes.items():
        d = features.descriptor(syrinx.peak_normalise(audio), rate)
        if d is None:
            log(f"  {name:24} no descriptor")
            continue
        # Naming the winner is the difference between "the matcher is broken" and "one
        # cluster is a bin of wind and rain". Only the second has a fix.
        score, index = best_match(d)
        probe_scores.append(score)
        log(f"  {name:24} {score:.3f}  -> {name_of(index)}")

    # Real birds, from the harvested syllables: this is the case the ramp has to let in.
    store_path = Path(args.store)
    ramp = measure_match_ramp(out, store_path, sample=args.sample, seed=args.seed)
    if ramp is None:
        log(f"\nno harvest store at {store_path}: skipping the real-audio side")
        return 0

    log(f"\nreal field syllables (n={ramp['sampled']} of {ramp['population']}):")
    for q in MATCH_RAMP_PERCENTILES:
        mark = ""
        if q == MATCH_RAMP_FLOOR_PCT:
            mark = "  <- floor"
        elif q == MATCH_RAMP_CEILING_PCT:
            mark = "  <- ceiling"
        log(f"  p{q:<3} {ramp['percentiles'][f'p{q}']:.3f}{mark}")
    log(f"  max  {ramp['max']:.3f}")
    log(f"\nramp: {ramp['rule']} = {ramp['floor']:.3f} .. {ramp['ceiling']:.3f}")

    # What the ramp does to the typical syllable is the number the old constants got
    # wrong, so say it rather than leaving it to be inferred from the percentiles.
    def smoothstep(x: float) -> float:
        t = min(1.0, max(0.0, (x - ramp["floor"]) / max(ramp["ceiling"] - ramp["floor"], 1e-9)))
        return t * t * (3 - 2 * t)

    p50 = ramp["percentiles"]["p50"]
    log(f"  the median field syllable ({p50:.3f}) reads {smoothstep(p50) * 100:.0f} % strength")
    log(f"  the noise probes above would read "
        f"{', '.join(f'{smoothstep(s) * 100:.0f} %' for s in probe_scores)} "
        "before the tonality gate, which is what actually rejects them")

    if args.write:
        manifest = galaxy.read_manifest(out)
        manifest["matchRamp"] = ramp
        galaxy.write_manifest(out, manifest)
        log(f"\nwrote matchRamp to {out / 'manifest.json'}")
    else:
        log("\n--write puts this in the manifest, which is where the app reads it from.")
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
    # The three per-cluster float arrays live in `centroid-vectors.f32` since 2026-08-01
    # (64 % of centroids.json's bytes; galaxy.py says why). `centroid_vectors` reads either
    # layout, so this check covers old asset directories too.
    blocks = galaxy.centroid_vectors(out, centroids)
    lo_centroids = blocks.get("featuresLo", np.zeros((0, 0)))
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
    vectors = blocks.get("vector", np.zeros((0, 0)))
    if centroids["dims"] == features.DIM:
        # The descriptor-space build: `vector` is the centroid, as it always was.
        if vectors.shape != (centroids["k"], centroids["dims"]):
            problems.append(f"centroid vectors are {vectors.shape}, expected "
                            f"{(centroids['k'], centroids['dims'])}")
        elif not np.all(np.isfinite(vectors)):
            problems.append("centroids.json contains NaN/inf")
    else:
        # The embed-space build: the primary centroid is `vector32`, and `vector` is the
        # 28-d member centroid shipped for the browser's fallback path.
        v32 = blocks.get("vector32", np.zeros((0, 0)))
        if v32.shape != (centroids["k"], centroids["dims"]):
            problems.append(f"centroid vector32s are {v32.shape}, expected "
                            f"{(centroids['k'], centroids['dims'])}")
        elif not np.all(np.isfinite(v32)):
            problems.append("centroids.json vector32 contains NaN/inf")
        if vectors.size and vectors.shape != (centroids["k"], features.DIM):
            problems.append(f"fallback 28-d centroid vectors are {vectors.shape}, "
                            f"expected {(centroids['k'], features.DIM)}")
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
    emb = space.get("embedding")
    if emb is not None:
        dims32 = emb.get("dims")
        if len(emb.get("mean", [])) != dims32 or len(emb.get("std", [])) != dims32:
            problems.append(
                "feature-space.json embedding mean/std do not match embedding.dims"
            )
        elif not np.all(np.isfinite(emb["mean"] + emb["std"])):
            problems.append("feature-space.json embedding moments contain NaN/inf")
        space_map = emb.get("map")
        if space_map is not None:
            if space_map.get("kind") == "rff-ridge":
                # Weights live in the f32 sidecar: R (28 x D) | phase (D) | w (D x 32)
                # | b (32), row-major — check the file is exactly that long and finite.
                D = int(space_map.get("D", 0))
                want = features.DIM * D + D + D * dims32 + dims32
                f32_path = out / space_map.get("file", "")
                if not f32_path.exists():
                    problems.append(f"{f32_path.name} is missing for the rff-ridge map")
                else:
                    map_raw = np.frombuffer(f32_path.read_bytes(), dtype="<f4")
                    if map_raw.size != want:
                        problems.append(
                            f"{f32_path.name} holds {map_raw.size} floats, expected {want} "
                            f"for D={D}"
                        )
                    elif not np.all(np.isfinite(map_raw)):
                        problems.append(f"{f32_path.name} contains NaN/inf")
            else:
                w = np.asarray(space_map.get("w", []), dtype=np.float64)
                bias = np.asarray(space_map.get("b", []), dtype=np.float64)
                if w.shape != (features.DIM, dims32) or bias.shape != (dims32,):
                    problems.append(
                        f"feature-space.json embedding map is {w.shape}+{bias.shape}, "
                        f"expected ({features.DIM}, {dims32})+({dims32},)"
                    )
                elif not np.all(np.isfinite(w)) or not np.all(np.isfinite(bias)):
                    problems.append("feature-space.json embedding map contains NaN/inf")

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
        # The browser's match ramp. Absence is reported, not failed: a build with no
        # harvest store has no field syllables to set it from, and the app then falls
        # back to its constants. An *unusable* ramp is a failure, because the app divides
        # by `ceiling - floor` and an inverted pair inverts the whole matcher — lighting
        # the galaxy hardest on the sounds least like a bird, silently.
        ramp = man.get("matchRamp")
        if not ramp:
            log("  match ramp        absent — the app will use its fallback constants "
                "(re-run `thresholds --write` against a harvest store)")
        else:
            floor, ceiling = ramp.get("floor"), ramp.get("ceiling")
            if not isinstance(floor, (int, float)) or not isinstance(ceiling, (int, float)):
                problems.append("manifest.matchRamp has no numeric floor/ceiling")
            elif not ceiling > floor:
                problems.append(
                    f"manifest.matchRamp is inverted or degenerate: {floor} .. {ceiling}"
                )
            elif ceiling > 1.0 or floor < -1.0:
                problems.append(
                    f"manifest.matchRamp is outside cosine range: {floor} .. {ceiling}"
                )
            else:
                p50 = (ramp.get("percentiles") or {}).get("p50")
                median = f", median field syllable {p50:.3f}" if isinstance(p50, float) else ""
                log(f"  match ramp        {ramp.get('rule', '?')} = {floor:.3f}..{ceiling:.3f} "
                    f"over {ramp.get('sampled', '?')} field syllables{median}")
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
        choices=("synthetic", "local"),
        default="synthetic",
        help="`local` adds a directory of audio beside the rendered inventory. The "
             "inventory is always rendered unless --no-synthetic, because a galaxy "
             "without it can name nothing",
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
    b.add_argument(
        "--field-source",
        choices=("auto", "syllables", "windows"),
        default="auto",
        help="what a harvested field point is: one stored syllable observation carrying "
             "its learned type id (needs <store>/typing.json, written by `learn`), or "
             "one 0.6 s window. `auto` takes syllables when typing.json exists and "
             "windows otherwise. The standardisation frame in feature-space.json stays "
             "window-based either way, because the browser's live path analyses windows",
    )
    b.add_argument(
        "--space",
        choices=("auto", "descriptor", "embed"),
        default="auto",
        help="which similarity space the galaxy's projection, clusters and centroids "
             "are built in: the hand-designed 28-d descriptor, or the critic's learned "
             "32-d embedding (docs/09 phase 2 — the measurably better space). `auto` "
             "takes the embedding when <store>/embeddings.f32 exists (`critic embed`), "
             "typing.json is present and a critic can embed the rendered anchor, and "
             "the descriptor otherwise",
    )
    b.add_argument(
        "--critic",
        default=None,
        help="trained critic for --space embed (embeds the rendered inventory and any "
             "un-embedded observations; default: out/critic.pt when it exists)",
    )
    b.add_argument("--cpu", action="store_true",
                   help="run the critic on the CPU even where a GPU is available")
    b.add_argument("--audio-dir", default=None, help="corpus root for --source local")
    b.add_argument("--variants", type=int, default=24,
                   help="renders per learned syllable type, built from measured member "
                        "observations, and per hand-authored syllable, built by jitter "
                        "(default %(default)s)")
    b.add_argument("--member-anchor", action="store_true",
                   help="render the fitted median plus --member-variants measured "
                        "realisations for a learned type that HAS member observations. "
                        "**Off by default since 2026-08-01** (W5, docs/22 §22.6 + §22.8): "
                        "such a type already exists in the galaxy as the real syllables "
                        "typing.json assigned to it, and rendering it again made the "
                        "corpus half a duplicate of itself (measured on the pre-W5 "
                        "production build: 347 531 synthetic against 340 079 field) and "
                        "split every type into two seeds. "
                        "Rendering nothing takes seed demand 2.00 -> 1.00 per type and k "
                        "4 298 -> 2 155 on debug-100, for no measured change in "
                        "field-point retrieval (+0.02) — the case is the map's size, not "
                        "its accuracy. This flag buys back the rendered voice's own place "
                        "on the map, which is a claim about our synthesiser")
    b.add_argument("--member-variants", type=int, default=None, metavar="N",
                   help="renders per learned type that has member observations, "
                        "overriding --variants for those types only. Only has an effect "
                        "with --member-anchor, since without it such a type renders "
                        "nothing at all")
    b.add_argument("--song-variants", type=int, default=3, help="renders per song")
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--k", type=int, default=None, help="clusters (default: syllable types)")
    b.add_argument(
        "--clustering",
        choices=("kmeans", "hdbscan", "label", "both"),
        default="kmeans",
        help="kmeans fits exactly --k groups and puts every point in one of them; "
             "hdbscan discovers how many dense regions there are and leaves the rest "
             "unassigned, which is the only way a sound can come out as 'none of "
             "these'; label skips the geometry for the 96 %% of points that already "
             "carry a type and gives each type its own knot, running kmeans only over "
             "the points with no label (docs/22 §22.5 — the answer at production scale, "
             "where the pre-W5 corpus had kmeans wanting 27 862 clusters over 694 936 "
             "points and the vote losing every documented call. This is what the shipped "
             "production build uses: 387 287 points, k = 16 380, type coverage 100 %%). "
             "'both' renders the corpus once and writes the label map to <out>/known and "
             "the hdbscan map to <out>/unknown — the pair the known-vs-unknown comparison "
             "always wants, for one render, and the pair the app shows as a live toggle. "
             "The known side of 'both' is the label map because that is what ships and "
             "what the whitepaper measured; ask for kmeans by name to get it",
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
    b.add_argument("--type-split", action="store_true",
                   help="draw a type as two knots when its own sounds are two groups. "
                        "OFF by default and measured: on the 2026-08-03 A/B it split 58 "
                        "types and changed the torn count by zero, because 54 of the 58 "
                        "were already drawn as one place (see TYPE_SPLIT_SEPARATION)")
    b.add_argument("--type-split-separation", type=float,
                   default=galaxy.TYPE_SPLIT_SEPARATION,
                   help="effect size past which --type-split draws a type as two knots")
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
    b.add_argument("--dump-points", default=None, metavar="NPZ",
                   help="also write the standardised clustering matrix + labels to this "
                        ".npz, so cluster_plan iterations run on a fixed corpus instead "
                        "of re-rendering per idea")
    b.add_argument("--dump-spacemap-eval", default=None, metavar="NPZ",
                   help="also write the space map's held-out rows with their recording "
                        "ids, the fit-side descriptor cloud, and this galaxy's "
                        "centroids — the per-session quality analysis of docs/20 "
                        "(single-clustering builds only, like --dump-points)")
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
    h.add_argument("--cap", type=int, default=None,
                   help="descriptors the store may hold, over all runs (default: the "
                        "store's own saved cap, or 60000 for a fresh store)")
    # Exposed because it silently decides how much of the *learning* set survives, and it was
    # only reachable in Python. A harvest that grew `out/harvest-gan` past this evicted whole
    # recordings to stay under it; the eviction is now species-stratified (`add_syllables`), but
    # the ceiling is still a ceiling, and a corpus that wants 25 species at depth needs to be
    # told it may hold more than 40 000 syllables.
    h.add_argument("--syllable-cap", type=int, default=None,
                   help="syllable observations the store may hold, over all runs. These are "
                        "what `learn` fits and what carries the log-mel patches, so this is "
                        "the ceiling on the learning set (default: the store's own saved "
                        "cap, or 40000 for a fresh store)")
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
        "--keep-audio",
        default=None,
        metavar="DIR",
        help="keep each analysed recording here when its licence permits "
             "(harvest.audio_may_be_cached: no NoDerivatives, no unrecorded licence — "
             "90.3 %% of the production corpus passes). Local only: the audio still never "
             "reaches the browser or an asset set. Without this the loop is unchanged, "
             "fetch/describe/delete. The reason to keep it is that an external model "
             "(Perch, BirdNET) and any per-syllable re-measurement need the waveform, and "
             "docs/23 §23.6 could only run on the recordings whose audio still existed",
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

    src = sub.add_parser(
        "sources",
        help="multi-source audio fetching: open datasets alongside xeno-canto "
             "(sources.py; staged audio is decoded, described and deleted, as in harvest)",
    )
    src_sub = src.add_subparsers(dest="sources_command", required=True)
    sl = src_sub.add_parser(
        "list",
        help="which sources this machine can use right now, and why not for the rest",
    )
    sl.set_defaults(func=cmd_sources_list)
    sf = src_sub.add_parser(
        "fetch",
        help="fetch from one source into a store via the harvest's ingest loop",
    )
    sf.add_argument("--source", required=True,
                    help="zenodo | internet-archive | kaggle | huggingface | "
                         "inat-sounds | gbif | xeno-canto")
    sf.add_argument("--species", default=None,
                    help='"Genus species" (zenodo/internet-archive/inat-sounds/gbif), '
                         "an eBird folder code or prefix (kaggle), or a BirdSet "
                         "member-path species id (huggingface)")
    sf.add_argument("--species-file", default=None, metavar="FILE",
                    help="inat-sounds: a file of species, one per line, as ids or "
                         '"Genus species" (# comments allowed). One sweep serves all of '
                         "them — the archive is a single 81 GB stream and asking for one "
                         "bird at a time costs a whole sweep each")
    sf.add_argument("--limit", type=int, default=5,
                    help="recordings to fetch (default %(default)s; these are proofs and "
                         "production top-ups, not bulk harvests)")
    sf.add_argument("--per-species", type=int, default=None,
                    help="inat-sounds only: cap recordings per species, so a large "
                         "--limit is a balanced take instead of the archive's first "
                         "species in taxonomic order")
    sf.add_argument("--keep-audio", default=None, metavar="DIR",
                    help="inat-sounds only: cache the staged audio under DIR instead "
                         "of deleting it — the owner's training-phase exception to "
                         "the no-retained-audio rule (AGENTS.md). Local only, never "
                         "shipped, deleted when the phase ends")
    sf.add_argument("--item", default=None,
                    help="source-specific dataset: a Zenodo record id (default XCDC "
                         "15420487), an archive.org item (xccoverbl_2014 | "
                         "warblrb10k_public | ff1010bird), a BirdCLEF slug "
                         "(birdclef-2021..2025), or a BirdSet config (XCM | XCL)")
    sf.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    sf.add_argument("--cap", type=int, default=None,
                    help="descriptors the store may hold (default: the store's own "
                         "saved cap, or 60000 for a fresh store)")
    sf.add_argument("--syllable-cap", type=int, default=None,
                    help="syllable observations the store may hold (default: the "
                         "store's own saved cap, or 40000 for a fresh store)")
    sf.add_argument("--max-seconds", type=float, default=harvest.DEFAULT_MAX_SECONDS,
                    help="analyse at most this much of each recording")
    sf.add_argument("--seed", type=int, default=0)
    sf.set_defaults(func=cmd_sources_fetch)

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
    lrn.add_argument("--jobs", type=int, default=1,
                     help="worker processes for the per-species fits (default 1 = "
                          "serial). >1 forks a pool: the critic embeds once in the "
                          "parent, workers fit species independently — identical "
                          "results, all cores. Linux/fork only; ignored with a "
                          "realism term")
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
    lrn.add_argument("--inverse", default=None, metavar="PT",
                     help="re-initialise each type's gesture axes from its own mean mel "
                          "patch with the trained encoder of `birdy-pipeline inverse` "
                          "(docs/09 §9.3 Part 2) before the coordinate descent runs. The "
                          "descent still decides — it only moves on an improvement — so "
                          "this proposes a basin and cannot force a worse fit than it "
                          "found. The measured contour and duration are kept; only the "
                          "gesture axes the cluster median has no value for are taken "
                          "from the encoder. Off = bit-identical to the shipped fit. "
                          "Holds a torch model, so it fits serially, like --critic")
    lrn.add_argument("--inverse-two-start", action="store_true",
                     help="with --inverse, run the coordinate descent from BOTH the "
                          "cluster median and the encoder's proposal and keep whichever "
                          "scores better on the objective that already decides "
                          "(pre-registered in pipeline/analysis/inverse_gate.md). The "
                          "single-start encoder failed its gate on consistency, not "
                          "direction — the median rose but only 52.8 %% of types improved "
                          "— and taking the better of two starts cannot regress by "
                          "construction, because the median start is always one of the "
                          "candidates. Costs two descents per type. No effect without "
                          "--inverse")
    lrn.add_argument("--mel-weight", type=float, default=0.0, metavar="W",
                     help="give each type's mean member mel-path a share W of the "
                          "inversion's objective (docs/19 §19.4: the spectral target "
                          "that actually tracks audible distortion, Spearman -0.42 vs "
                          "the cosine's +0.10 against MCD). 0 = the pre-docs/19 "
                          "objective, bit-identical. 1.0 must not ship (the cosine "
                          "guardrail collapses); 0.5 is the measured candidate")
    lrn.add_argument("--respiration", action="store_true",
                     help="attach the default respiratory set of docs/15 §1 (Fainstein, "
                          "Goller & Mindlin 2025: air-sac pressure gesture replacing the "
                          "designed envelope, sqrt-pressure tract drive) to every fitted "
                          "type. Hand-set, one set per species, until the pre-registered "
                          "per-species fit exists; the reported cosine measures the "
                          "respiratory render, which is the bake-off comparison")
    lrn.add_argument("--two-voice", action="store_true",
                     help="attach the default second voice of docs/15 §5 (Laje & "
                          "Mindlin 2005: the type's own contour shifted by the Fig. 6 "
                          "ratio, Table I's trachea and reflection, coupled through "
                          "the shared tracheal pressure) to every fitted type. "
                          "Hand-set until the pre-registered per-species fit exists; "
                          "the reported cosine measures the two-voice render, which "
                          "is the bake-off comparison")
    lrn.add_argument("--cpu", action="store_true",
                     help="run the critic on the CPU even where a GPU is available")
    lrn.set_defaults(func=cmd_learn)

    rf = sub.add_parser(
        "respfit",
        help="the pre-registered per-species fit of the docs/15 synth blocks: one "
             "respiratory set per species (Table S2 ranges) and one second voice per "
             "screened type, shipped on a type ONLY where it beats that type's "
             "current resynthesis cosine by --margin (respfit.py's docstring is the "
             "pre-registration)",
    )
    rf.add_argument("--store", default=str(DEFAULT_HARVEST_STORE),
                    help="the store the parallel learn fitted (its typing.json is the "
                         "membership the fit is judged against)")
    rf.add_argument("--inventory", default=str(DEFAULT_LEARNED_INVENTORY),
                    help="the learned inventory the parallel learn wrote — the input "
                         "fit, never the authored inventory")
    rf.add_argument("--out", default=None,
                    help="where the gated inventory goes (default: <inventory "
                         "stem>.respfit.json beside the input; the input is never "
                         "modified unless this points at it)")
    rf.add_argument("--report", default=None,
                    help="write the full per-type audit (before/after cosines, what "
                         "shipped, the pre-registered numbers) to this JSON file")
    rf.add_argument("--jobs", type=int, default=1,
                    help="worker processes for the per-species fits (default 1 = "
                         "serial). >1 forks a pool: independent fits, identical "
                         "results, all cores. Linux/fork only")
    rf.add_argument("--margin", type=float, default=respfit.SHIP_MARGIN,
                    help="the honest gate: a fitted block ships on a type only if it "
                         "beats the type's current cosine by at least this much "
                         "(default %(default)s, pre-registered in respfit.py)")
    rf.add_argument("--no-respiration", action="store_true",
                    help="skip the respiratory fit (two-voice only)")
    rf.add_argument("--no-two-voice", action="store_true",
                    help="skip the two-voice fit (respiration only)")
    rf.add_argument("--calibration-dir", default=str(DEFAULT_OUT),
                    help="where syrinx-calibration.json lives")
    rf.set_defaults(func=cmd_respfit)

    dr = sub.add_parser(
        "docrefit",
        help="the pure-tone documented re-fit (docs/16 §16.4): give each authored "
             "one-tone call the noise/rough texture of its nearest learned type, "
             "shipped ONLY where the re-fit beats the authored render by --margin "
             "against that type's measured reference (docrefit.py's docstring is the "
             "pre-registration)",
    )
    dr.add_argument("--store", default=str(DEFAULT_HARVEST_STORE),
                    help="the store the learned types were fitted from (its "
                         "typing.json is the membership the references are built from)")
    dr.add_argument("--inventory", default=str(DEFAULT_LEARNED_INVENTORY),
                    help="the merged learned inventory (authored calls plus fitted "
                         "types); the input is never modified unless --out points at it")
    dr.add_argument("--out", default=None,
                    help="where the re-fitted inventory goes (default: <inventory "
                         "stem>.docrefit.json beside the input)")
    dr.add_argument("--report", default=None,
                    help="write the full per-call audit (matched type, match distance, "
                         "before/after cosines, what shipped) to this JSON file")
    dr.add_argument("--margin", type=float, default=respfit.SHIP_MARGIN,
                    help="the honest gate: a texture ships only if it beats the "
                         "authored render by at least this much (default %(default)s, "
                         "the same gate respfit uses)")
    dr.add_argument("--f0-cap", type=float, default=docrefit.F0_CAP_OCTAVES,
                    help="furthest pitch gap, in octaves, between a documented call "
                         "and the learned type it is re-fitted against "
                         "(default %(default)s)")
    dr.add_argument("--calibration-dir", default=str(DEFAULT_OUT),
                    help="where syrinx-calibration.json lives")
    dr.set_defaults(func=cmd_docrefit)

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
    crt.add_argument("--aug-channel-db", type=float,
                     default=critic_default("aug_channel_db"), metavar="DB",
                     help="source-invariance recipe: swing of the simulated recorder "
                          "frequency response added to each augmented view "
                          "(default %(default)s = off, the pre-recipe path)")
    crt.add_argument("--mixstyle-alpha", type=float,
                     default=critic_default("mixstyle_alpha"), metavar="A",
                     help="source-invariance recipe: Beta concentration for swapping "
                          "per-band statistics between same-species recordings "
                          "(default %(default)s = off)")
    crt.add_argument("--w-record", type=float, default=critic_default("w_record"),
                     help="source-invariance recipe: weight of the recordist-"
                          "adversarial head (default %(default)s = off; the term that "
                          "can eat species information, so it earns its weight in the "
                          "sweep)")
    crt.add_argument("--recordist-min-patches", type=int,
                     default=critic_default("recordist_min_patches"),
                     help="fewest training patches for a recordist to be an "
                          "adversarial class (default %(default)s)")
    crt.add_argument("--record-within-species", action="store_true",
                     default=critic_default("record_within_species"),
                     help="source-invariance follow-up (docs/17 §17.5): the "
                          "adversarial classes become recordings, and each patch's "
                          "softmax is masked to its own species's recordings — the "
                          "bird is given, so only the channel can pay the loss")
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

    cre = cr_sub.add_parser(
        "embed",
        help="embed every stored syllable once into <store>/embeddings.f32, so builds "
             "can cluster in the learned space (docs/09 phase 2)",
    )
    cre.add_argument("--store", default=str(DEFAULT_HARVEST_STORE),
                     help="harvest store holding the log-mel patches")
    cre.add_argument("--critic", default=str(DEFAULT_CRITIC))
    cre.add_argument("--out", default=None,
                     help="where to write the f32 matrix (default: <store>/%s); a "
                          "sidecar .json records the critic that produced it"
                     % EMBEDDINGS_NAME)
    cre.add_argument("--batch", type=int, default=512)
    cre.add_argument("--cpu", action="store_true",
                     help="embed on the CPU even with a GPU present")
    cre.set_defaults(func=cmd_critic_embed)

    crg = cr_sub.add_parser(
        "groupings",
        help="the geometry battery (species vs recordist vs source kNN lift) directly "
             "on the store's embeddings, without a build — the source-invariance "
             "verdict instrument for a retrain sweep",
    )
    crg.add_argument("--store", default=str(DEFAULT_HARVEST_STORE),
                     help="harvest store whose embeddings to test")
    crg.add_argument("--embeddings", default=None,
                     help="embeddings file (default: <store>/%s)" % EMBEDDINGS_NAME)
    crg.add_argument("--seed", type=int, default=0)
    crg.set_defaults(func=cmd_critic_groupings)

    crl = cr_sub.add_parser(
        "label-novel",
        help="Perch 2.0 second opinion for novelty-flagged syllables: labels land in "
             "<store>/perch-labels.jsonl as metadata, never as typing ground truth "
             "(docs/13 A1)",
    )
    crl.add_argument("--store", default=str(DEFAULT_HARVEST_STORE),
                     help="harvest store whose novelty-flagged syllables to label")
    crl.add_argument("--audio-cache",
                     default=str(REPO_ROOT / "pipeline" / "out" / "audio-cache"),
                     help="the owner-sanctioned iNat WAV cache (AGENTS.md); syllables "
                          "from any other source have no audio and are reported "
                          "unlabelable")
    crl.add_argument("--critic", default=str(DEFAULT_CRITIC),
                     help="used only to locate <stem>-novelty.json, whose centroids "
                          "and threshold rederive the novelty verdict for syllables "
                          "harvested before the scorer existed")
    crl.add_argument("--embeddings", default=None,
                     help="store embeddings for the novelty rederive (default: "
                          "<store>/%s)" % EMBEDDINGS_NAME)
    crl.add_argument("--out", default=None,
                     help="where to write the JSONL (default: <store>/perch-labels.jsonl)")
    crl.add_argument("--model-dir",
                     default=str(REPO_ROOT / "pipeline" / "out" / "perch"),
                     help="where the ONNX weights and class list are cached; the "
                          "409 MB download lands here on first use")
    crl.add_argument("--limit", type=int, default=None,
                     help="label at most this many syllables (smoke runs)")
    crl.add_argument("--batch", type=int, default=32)
    crl.add_argument("--keep-embeddings", action="store_true",
                     help="also write Perch's 1536-d embedding per syllable (off by "
                          "default; docs/13 A1's external cross-check of the critic "
                          "space, at ~10 KB of JSON per row)")
    crl.set_defaults(func=cmd_critic_label_novel)

    sm = sub.add_parser(
        "spacemap",
        help="fit and grade the browser's 28-d -> 32-d space map on a store, split by "
             "recording (docs/09 phase 2)",
    )
    sm.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    sm.add_argument("--embeddings", default=None,
                    help="embedding matrix (default: <store>/%s)" % EMBEDDINGS_NAME)
    sm.add_argument("--out", default=None,
                    help="also write the map and its quality gate as JSON here")
    sm.add_argument("--seed", type=int, default=0)
    sm.set_defaults(func=cmd_spacemap)

    rel = sub.add_parser(
        "relations",
        help="cross-species relations: shared/convergent syllable types and species "
             "similarity in the critic's embedding (relations.py, phase 4)",
    )
    rel.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    rel.add_argument("--embeddings", default=None,
                     help="embedding matrix (default: <store>/%s)" % EMBEDDINGS_NAME)
    rel.add_argument("--inventory", default=str(DEFAULT_LEARNED_INVENTORY),
                     help="consulted for common names only")
    rel.add_argument("--out", default=None,
                     help="where to write relations.json (default: print a summary only)")
    rel.set_defaults(func=cmd_relations)

    xp = sub.add_parser(
        "expand",
        help="grow the corpus outward: harvest discovered species the store does not "
             "cover, then embed, learn and grow (phase 4)",
    )
    xp.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    xp.add_argument("--discovered", default=str(DEFAULT_DISCOVERED),
                    help="the registry `harvest --discover` writes")
    xp.add_argument("--max-species", type=int, default=2,
                    help="how many uncovered species to collect per run "
                         "(default %(default)s)")
    xp.add_argument("--max-recordings", type=int, default=20,
                    help="recordings per target species; xeno-canto is rate-limited "
                         "(default %(default)s)")
    xp.add_argument("--quality", default="A", help="xeno-canto quality filter")
    xp.add_argument("--dry-run", action="store_true",
                    help="print the ranked target list and do nothing else — no "
                         "network, no writes")
    xp.add_argument("--out", default=str(DEFAULT_OUT), help="built assets to grow")
    xp.add_argument("--learned", default=str(DEFAULT_LEARNED_INVENTORY),
                    help="where the refit inventory is written")
    xp.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    xp.add_argument("--calibration-dir", default=str(DEFAULT_OUT),
                    help="where syrinx-calibration.json lives")
    xp.add_argument("--critic", default=None,
                    help="trained critic for the embed/learn steps (default: "
                         "out/critic.pt when it exists)")
    xp.add_argument("--xc-key", default=None,
                    help="xeno-canto v3 API key (or set XC_API_KEY)")
    xp.add_argument("--pause", type=float, default=harvest.XC_PAGE_PAUSE,
                    help="seconds between requests; the service rate-limits")
    xp.add_argument("--seed", type=int, default=0)
    xp.add_argument("--cpu", action="store_true",
                    help="run the critic on the CPU even where a GPU is available")
    xp.set_defaults(func=cmd_expand)

    pl = sub.add_parser(
        "placement",
        help="score a fitted inventory on docs/09's four numbers, including the one `learn` "
             "cannot report: whether a resynthesis lands nearest its own *species*",
    )
    pl.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    pl.add_argument("--inventory", default=str(DEFAULT_LEARNED_INVENTORY))
    pl.add_argument("--calibration-dir", default=str(DEFAULT_OUT))
    pl.add_argument("--embeddings", default=None,
                    help="embedding matrix for the render-free 32-d placement number "
                         "(default: <store>/%s when it exists)" % EMBEDDINGS_NAME)
    pl.add_argument("--per-species", action="store_true",
                    help="also break the placement down species by species")
    pl.set_defaults(func=cmd_placement)

    spb = sub.add_parser(
        "specbench",
        help="the spectral bench: render fitted types against their original cached "
             "audio and correlate the resynthesis cosine with channel-normalised MCD "
             "and multi-resolution STFT error — i.e. measure whether a cosine gain "
             "is an audible gain (specbench.py)",
    )
    spb.add_argument("--store", default=str(DEFAULT_HARVEST_STORE),
                     help="store with typing.json the inventory was learned from")
    spb.add_argument("--inventory", default=str(DEFAULT_LEARNED_INVENTORY),
                     help="learned inventory holding the fitted types")
    spb.add_argument("--audio-cache", default=str(REPO_ROOT / "pipeline" / "out" / "audio-cache"),
                     help="the owner-sanctioned iNat WAV cache (read only)")
    spb.add_argument("--extra-audio-cache", action="append", default=None,
                     metavar="DIR",
                     help="another read-only cache to resolve references from, repeatable. "
                          "Use it to reach the xeno-canto side of the corpus, whose audio "
                          "harvest streams and deletes: 1 033 fitted types (6.4 %%) have no "
                          "iNat member at all and are otherwise unbenchable. Mind the "
                          "format — that cache is lossy MP3 against the iNat cache's "
                          "lossless WAV, and every benched row records `audioFormat` so the "
                          "two are read as separate arms rather than averaged")
    spb.add_argument("--band-cap-hz", type=float, default=11025.0,
                     help="hold every row's comparison to this band, so rows from "
                          "caches with different sample rates are comparable at all "
                          "(default %(default)s Hz, the iNat cache's own Nyquist). "
                          "Without it a row is banded at its own file's Nyquist and "
                          "the caches sit an octave apart: wav-backed types read "
                          "median MCD 78.96 dB against mp3-backed 111.70, which is "
                          "mostly the band and not the fit. Rows reaching the cap "
                          "carry `atCap` and are the population to quote")
    spb.add_argument("--no-band-cap", action="store_true",
                     help="band each row at its own file's Nyquist instead, "
                          "reproducing every figure published before the cap existed. "
                          "NEVER average the arms of such a run")
    spb.add_argument("--limit", type=int, default=200,
                     help="how many fitted types to bench (default %(default)s)")
    spb.add_argument("--calibration-dir", default=None,
                     help="where syrinx-calibration.json lives (default: the store's "
                          "parent directory)")
    spb.add_argument("--out", default=None,
                     help="also write the full report (per-type rows + correlations) "
                          "as JSON here")
    spb.set_defaults(func=cmd_specbench)

    inv_p = sub.add_parser(
        "inverse",
        help="train the amortised inverse (mel patch -> syrinx parameters, docs/09 §9.3 "
             "Part 2). Its training data is generated and discarded: we own the forward "
             "model, so the pairs are free, perfectly labelled and unconfounded",
    )
    inv_p.add_argument("--inventory", default=str(DEFAULT_LEARNED_INVENTORY),
                       help="the fitted inventory whose marginals the sampler draws from "
                            "— a uniform box over 16 axes samples syllables no bird sings")
    inv_p.add_argument("--pairs", type=int, default=150_000,
                       help="render/patch pairs to train on (default %(default)s; ~810/s "
                            "single-core, so this is a few minutes)")
    inv_p.add_argument("--epochs", type=int, default=80)
    inv_p.add_argument("--seed", type=int, default=0)
    inv_p.add_argument("--cpu", action="store_true", help="train on the CPU")
    inv_p.add_argument("--calibration-dir", default=str(REPO_ROOT / "pipeline" / "out"),
                       help="where syrinx-calibration.json lives")
    inv_p.add_argument("--out", default=str(REPO_ROOT / "pipeline" / "out" / "inverse.pt"),
                       help="where to write the trained encoder")
    inv_p.set_defaults(func=cmd_inverse)

    sy = sub.add_parser(
        "syntax",
        help="the P1 grammar bake-off of docs/18: first-order (the shipped model) vs "
             "Jin-Kozhevnikov repeat-count vs a categorical HMM, scored by held-out "
             "bout log-likelihood on the store's typed bouts, with the win rule "
             "pre-registered in syntax.py",
    )
    sy.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    sy.add_argument("--alpha", type=float, default=syntax_mod.ALPHA,
                    help="add-alpha smoothing strength, backed off to the next lower "
                         "order (default %(default)s)")
    sy.add_argument("--ks", default=",".join(str(k) for k in syntax_mod.HMM_KS),
                    help="comma-separated HMM state counts to sweep, chosen on an inner "
                         "validation split (default %(default)s)")
    sy.add_argument("--min-bouts", type=int, default=syntax_mod.MIN_BOUTS_PER_SPECIES,
                    help="fewest bouts for a species to qualify (default %(default)s)")
    sy.add_argument("--max-iter", type=int, default=syntax_mod.HMM_MAX_ITER,
                    help="Baum-Welch iteration cap (default %(default)s)")
    sy.add_argument("--compare-backoff", action="store_true",
                    help="skip the three-model bake-off and instead run the smoothing "
                         "repair comparison: raw-unigram vs Kneser-Ney continuation-count "
                         "backoff for the first-order model's unseen contexts, with the "
                         "adoption gate pre-registered in syntax.py")
    sy.add_argument("--json", default=None,
                    help="also write the full machine-readable report here")
    sy.set_defaults(func=cmd_syntax)

    so = sub.add_parser(
        "songspace",
        help="the P2 song-level space of docs/18: whole bouts as points under a "
             "hand-written edit-plus-rhythm kernel, graded against bag-of-types "
             "and docs/12's song typing with geometry.py's kNN-lift + "
             "permutation-null battery, with the verdict pre-registered in "
             "songspace.py",
    )
    so.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    so.add_argument("--rhythm-weight", type=float,
                    default=songspace_mod.RHYTHM_WEIGHT,
                    help="price of one nat of log-gap difference at a matched "
                         "position; 0 is the rhythm-off ablation (default %(default)s)")
    so.add_argument("--json", default=None,
                    help="also write the full machine-readable report here")
    so.set_defaults(func=cmd_songspace)

    sb = sub.add_parser(
        "subset",
        help="write a debug store with the N biggest (or N most representative) species",
    )
    sb.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    sb.add_argument("--species", type=int, default=100,
                    help="how many species to keep (default %(default)s)")
    sb.add_argument("--diverse", action="store_true",
                    help="keep the N species that best represent the store's acoustic "
                         "spread (k-medoid over species centroids in the 28-d descriptor "
                         "space) instead of the N biggest. A bench that meets every kind "
                         "of voice the corpus holds; it carries less data per species, so "
                         "it is for proving mechanics, not for measuring fit quality")
    sb.add_argument("--seed", type=int, default=0,
                    help="seed for the diverse pick's clustering (default %(default)s)")
    sb.add_argument("--out", required=True, help="target store directory (never the source)")
    sb.set_defaults(func=cmd_subset)

    g = sub.add_parser(
        "grow",
        help="add the harvest store's newest audio to the built galaxy without rebuilding",
    )
    g.add_argument("--out", default=str(DEFAULT_OUT), help="built asset directory")
    g.add_argument("--harvest-store", default=None)
    g.add_argument(
        "--critic",
        default=None,
        help="critic that embeds new syllables when the galaxy was built in the "
             "embedding space (default: out/critic.pt when it exists). Required for an "
             "embed-space build: without it a new syllable cannot be placed at all",
    )
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
    s.add_argument("--store", default=None,
                   help=f"harvest store the Learn tab works on "
                        f"(default {DEFAULT_HARVEST_STORE}; starting on the default "
                        f"prints which store it is and warns when a sibling store in "
                        f"out/ has moved more recently)")
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
    # The amortised inverse, on the same "use it when it exists" footing as the critic. The
    # two-start it enables cannot fit worse than the median-only path by construction and
    # passed its gate at +0.0330 median cosine with nothing regressing
    # (pipeline/analysis/inverse_gate.md), so the Learn tab uses it when a model is on disk.
    # It costs roughly 5x the fit time, which is the reason for the off switch.
    s.add_argument("--inverse", default=str(DEFAULT_INVERSE),
                   help="trained inverse encoder every fit started from the Learn tab should "
                        "use, when it exists (default %(default)s)")
    s.add_argument("--no-inverse", dest="inverse", action="store_const", const=None,
                   help="ignore any trained inverse encoder; every fit starts from the "
                        "cluster median, which is bit-identical to the shipped path")
    s.add_argument("--no-inverse-two-start", action="store_true",
                   help="with an encoder present, start from its proposal ONLY instead of "
                        "descending from both starts and keeping the better. Cheaper and "
                        "measured worse: the single-start arm failed its gate at +0.0140 "
                        "against a +0.02 bar with 45 %% of types regressing")
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

    q = sub.add_parser(
        "quality",
        help="ingest-time quality of the observations a store already holds",
    )
    q_sub = q.add_subparsers(dest="quality_command", required=True)
    qr = q_sub.add_parser(
        "remeasure",
        help="fill snr/clipped on rows harvested before those fields existed, from the "
             "cached audio; rewrites syllables.jsonl line for line and touches nothing else",
    )
    qr.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    qr.add_argument("--audio-cache",
                    default=str(REPO_ROOT / "pipeline" / "out" / "audio-cache"),
                    help="the owner-sanctioned iNat WAV cache (AGENTS.md). Rows from any "
                         "other source have no audio and are reported unreachable, never "
                         "silently skipped")
    qr.add_argument("--max-seconds", type=float, default=harvest.DEFAULT_MAX_SECONDS,
                    help="the analysis window the store was harvested with. Changing it "
                         "changes the segmentation, so every row will read as drifted and "
                         "nothing will be written")
    qr.add_argument("--dry-run", action="store_true",
                    help="measure and report, write nothing")
    qr.set_defaults(func=cmd_quality_remeasure)

    th = sub.add_parser("thresholds", help="re-measure the browser's match ramp on the shipped assets")
    th.add_argument("--out", default=str(DEFAULT_OUT))
    th.add_argument("--store", default=str(DEFAULT_HARVEST_STORE))
    th.add_argument("--sample", type=int, default=2000, help="field syllables to score")
    th.add_argument("--seed", type=int, default=0)
    th.add_argument("--write", action="store_true",
                    help="write the measured ramp into the asset set's manifest.json")
    th.set_defaults(func=cmd_thresholds)
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
