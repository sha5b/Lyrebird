"""A small local control surface for harvest / learn / build.

Birdy's whole point is that the *running app* needs no backend: `adapter-static`,
precomputed assets, client-side features, client-side synthesis. That does not change.
This is a separate, optional, developer-facing process for driving the offline pipeline
from the interface instead of from a terminal — the app's Learn tab talks to it when it
is running and says how to start it when it is not. Ship the galaxy without it.

**It binds to the loopback interface and refuses to do anything else.** Every endpoint
here runs pipeline code — downloading, decoding and writing files — so exposing it on a
network would be handing out remote code execution. The bind address is not
configurable, and `--port` is the only knob.

Only one job runs at a time. Its stderr is captured into a ring buffer so the interface
can show the same progress the CLI prints, rather than a spinner and a guess.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import io
import json
import os
import tempfile
import threading
import time
import urllib.parse
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from . import harvest, learn
from .corpus import load_inventory

BIND_HOST = "127.0.0.1"  # not configurable, see the module docstring
DEFAULT_PORT = 8781
LOG_LINES = 400


class _Tee(io.TextIOBase):
    """Writes through to the real stderr and into the job log at the same time."""

    def __init__(self, sink: Callable[[str], None], passthrough: io.TextIOBase):
        self.sink = sink
        self.passthrough = passthrough
        self._partial = ""

    def write(self, text: str) -> int:
        self.passthrough.write(text)
        self._partial += text
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            self.sink(line)
        return len(text)

    def flush(self) -> None:
        self.passthrough.flush()


class Job:
    """One pipeline run. At most one exists at a time."""

    def __init__(self, name: str, detail: str):
        self.name = name
        self.detail = detail
        self.started = time.time()
        self.finished: float | None = None
        self.error: str | None = None
        self.log: deque[str] = deque(maxlen=LOG_LINES)
        self.cancelled = False
        #: Small structured outcome a job can leave for the interface — the ingest
        #: novelty counts are the one user so far. Anything bigger belongs in the log.
        self.result: dict[str, Any] | None = None

    def state(self) -> str:
        if self.finished is None:
            return "stopping" if self.cancelled else "running"
        return "failed" if self.error else ("stopped" if self.cancelled else "done")

    def stop(self) -> None:
        """Ask the job to end. It stops at its next checkpoint, not immediately."""
        self.cancelled = True
        self.log.append("stop requested — finishing the current step")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "detail": self.detail,
            "state": self.state(),
            "seconds": round((self.finished or time.time()) - self.started, 1),
            "error": self.error,
            "cancelled": self.cancelled,
            "log": list(self.log),
        }
        if self.result is not None:
            out["result"] = self.result
        return out


class Pipeline:
    """Holds the paths, the current job, and the lock that keeps runs serial."""

    def __init__(
        self,
        store_path: Path,
        inventory_path: Path,
        learned_path: Path,
        out_path: Path,
        critic_path: Path | None = None,
        #: 0, because the realism term measured *worse* at every weight tried — see the note
        #: on `cli.py`'s `--critic-weight`. The critic still earns its place through
        #: `embed_typing`, which is a different use of the same network.
        critic_weight: float = 0.0,
        #: **On by default whenever a critic is actually present.** The learned embedding beat
        #: the hand-written typing vector on every measure at once — species placement
        #: 26.6 % -> 32.9 %, own-type 63.0 % -> 63.9 %, F0 error 5.4 % -> 3.1 %, cosine held
        #: (docs/09 §9.7) — so making it opt-in would mean the interface defaulting to the
        #: worse of two things it has in front of it. `learn` on the command line stays
        #: explicit, because that is the surface where a measurement gets reproduced and the
        #: flag should be visible in the shell history; this is the surface where it should
        #: just do the better thing. `--no-embed-typing` turns it off.
        embed_typing: bool = True,
    ):
        self.store_path = Path(store_path)
        self.inventory_path = Path(inventory_path)
        self.discovered_path = Path(inventory_path).parent / harvest.DISCOVERED_NAME
        self.learned_path = Path(learned_path)
        self.out_path = Path(out_path)
        # The learned critic, if one has been trained. Loaded per fit rather than held open,
        # because `critic train` may have rewritten it since the server started — the whole
        # point of the alternation in docs/09 §9.3 step 6 is that the critic keeps changing.
        # None means every fit here uses the hand-written 28-d cosine, which is what happens
        # on a machine with no torch (§9.4) or before anything has been trained.
        self.critic_path = Path(critic_path) if critic_path else None
        self.critic_weight = float(critic_weight)
        self.embed_typing = bool(embed_typing)
        self.job: Job | None = None
        self._lock = threading.Lock()
        #: The novelty scorer cache: (critic mtime, centroids mtime, critic, scorer).
        #: Re-read when either file changes — `critic train` rewrites both, and a
        #: scorer held across a retrain would judge new audio against a network that
        #: no longer exists. False means "checked and absent": ingest then behaves
        #: exactly as it did before novelty flags, and says so once.
        self._novelty: tuple[float, float, Any, Any] | bool | None = None
        self._novelty_warned = False
        #: typing.json, cached by mtime — status polls every 1.5 s and the file is
        #: 5 MB at 40 k syllables, so parsing it per poll is not an option.
        self._typing_cache: tuple[float, dict[tuple[str, str, int], str]] | None = None

    # -- status --

    def status(self) -> dict[str, Any]:
        store: dict[str, Any] = {"exists": False}
        if (self.store_path / "state.json").exists():
            # **Without the syllables.** The interface polls this every 1.5 s and the only
            # thing it wanted from that file was a count, which `state.json` already carries.
            # Parsing 26 MB of JSONL (and now 13-57 MB of patches) per poll took a status call
            # to 1.3 s, which is over the 600 ms probe `vite-plugin-pipeline.ts` used to decide
            # whether a server is up — so on a large store the plugin could never see a
            # healthy server, concluded the port was free, and tried to spawn a second one
            # that then failed to bind. The Learn tab's "not running" panel was the visible
            # symptom and this was the cause.
            s = harvest.HarvestStore(self.store_path, load_syllables=False)
            rep = s.representativeness()
            store = {
                "exists": True,
                "path": str(self.store_path),
                "descriptors": len(s),
                "descriptorsSeen": s.stream_n,
                "syllables": s.syllable_count,
                "recordings": len(s.recordings),
                "species": sorted(s.strata),
                "cap": s.cap,
                "meanDrift": round(rep["meanDrift"], 4),
                "stdRatio": round(rep["stdRatio"], 4),
            }

        # Whether a learned critic is in play, so the Learn tab can say which objective the
        # numbers next to each syllable were produced under. Read from the sidecar JSON rather
        # than by loading the weights: this runs on every status poll, and importing torch to
        # answer a status request would be absurd.
        critic: dict[str, Any] = {"exists": False}
        if self.critic_path is not None:
            sidecar = self.critic_path.with_suffix(".json")
            critic = {
                "exists": self.critic_path.exists(),
                "path": str(self.critic_path),
                "weight": self.critic_weight,
                "embedTyping": self.embed_typing,
            }
            if sidecar.exists():
                try:
                    blob = json.loads(sidecar.read_text(encoding="utf-8"))
                    critic["report"] = blob.get("report", {})
                except (OSError, json.JSONDecodeError):
                    pass

        learned: dict[str, Any] = {"exists": False}
        if self.learned_path.exists():
            doc = json.loads(self.learned_path.read_text(encoding="utf-8"))
            cosines = [
                s["learned"]["resynthesisCosine"]
                for sp in doc.get("species", [])
                for s in sp.get("syllables", [])
                if s.get("learned", {}).get("resynthesisCosine")
            ]
            # The file may be merged (documented calls kept, fitted types appended) or
            # learned-only, so a species is only reported once it has fitted types, and
            # the bout is looked up by id rather than by position.
            learned = {
                "exists": True,
                "path": str(self.learned_path),
                "species": [
                    {
                        "id": sp["id"],
                        "common": sp.get("common", sp["id"]),
                        "types": sum(1 for s in sp.get("syllables", []) if s.get("learned")),
                        "states": len(sp.get("grammar", {}).get("transitions", {})),
                        "bout": next(
                            (s.get("sequence", []) for s in sp.get("songs", [])
                             if s.get("id") == "learned_bout"),
                            [],
                        ),
                    }
                    for sp in doc.get("species", [])
                    if any(s.get("learned") for s in sp.get("syllables", []))
                ],
                "medianCosine": round(sorted(cosines)[len(cosines) // 2], 4) if cosines else None,
                "worstCosine": round(min(cosines), 4) if cosines else None,
            }

        built: dict[str, Any] = {"exists": False}
        manifest = self.out_path / "manifest.json"
        if manifest.exists():
            m = json.loads(manifest.read_text(encoding="utf-8"))
            built = {
                "exists": True,
                "builtAt": m.get("builtAt"),
                "points": m.get("points"),
                "clusters": m.get("clusters"),
                "source": m.get("source"),
                "sourceMix": m.get("sourceMix", {}),
            }

        species = [
            {"id": sp["id"], "common": sp.get("common", sp["id"])}
            for sp in load_inventory(self.inventory_path).get("species", [])
        ]

        # **Discovered species, with how far each one has got.**
        #
        # A sweep changes what the pipeline collects and nothing in the interface said so: the
        # app reads the *build's* inventory copy, which cannot contain a bird that has no audio
        # yet, so fourteen new targets were invisible everywhere. That is the wrong kind of
        # silence — it is indistinguishable from the sweep not having run. Each one reports the
        # stage it has reached, because "discovered" and "singable" are several steps apart:
        # audio has to arrive, clear the observation floor, fit, and be rebuilt into the galaxy
        # before the bird has a voice at all.
        discovered: list[dict[str, Any]] = []
        if self.discovered_path.exists():
            # Only `strata` is read below, so this skips the syllables too — it was a second
            # full parse of the same 26 MB in the same request.
            store_obj = (
                harvest.HarvestStore(self.store_path, load_syllables=False)
                if (self.store_path / "state.json").exists()
                else None
            )
            fitted_ids = set()
            if self.learned_path.exists():
                try:
                    doc = json.loads(self.learned_path.read_text(encoding="utf-8"))
                    fitted_ids = {
                        sp["id"] for sp in doc.get("species", [])
                        if any(y.get("learned") for y in sp.get("syllables", []))
                    }
                except (OSError, ValueError):
                    pass
            for e in harvest.load_discovered(self.discovered_path):
                kept = len(store_obj.strata[e["id"]].rows) if (
                    store_obj and e["id"] in store_obj.strata
                ) else 0
                stage = "fitted" if e["id"] in fitted_ids else (
                    "collecting" if kept else "waiting for audio"
                )
                discovered.append({
                    "id": e["id"],
                    "common": e.get("common", e["id"]),
                    "scientific": e.get("scientific", ""),
                    "available": e.get("recordings", 0),
                    "descriptors": kept,
                    "stage": stage,
                })
        novel = (
            self._novel_summary() if (self.store_path / "state.json").exists()
            else {"novelCount": 0, "recentNovel": []}
        )
        return {
            "ok": True,
            "hasKey": bool(os.environ.get("XC_API_KEY")),
            "ffmpeg": harvest.have_ffmpeg(),
            "store": store,
            "learned": learned,
            "critic": critic,
            "built": built,
            "inventorySpecies": species,
            "discovered": discovered,
            # Syllables flagged as unlike every known type centroid (docs/09 §9.2b):
            # how many the store holds, and the most recent few so the interface can
            # say *whose* new sound it was.
            "novelCount": novel["novelCount"],
            "recentNovel": novel["recentNovel"],
            "job": self.job.to_dict() if self.job else None,
        }

    # -- running --

    def start(self, name: str, detail: str, fn: Callable[[Job], None]) -> dict[str, Any]:
        with self._lock:
            # `finished`, not the state: a job that has been asked to stop is still
            # holding the store until it reaches its next checkpoint.
            if self.job and self.job.finished is None:
                return {"ok": False, "error": f"{self.job.name} is still running"}
            job = Job(name, detail)
            self.job = job

        def run() -> None:
            tee = _Tee(job.log.append, harvest.sys.stderr)
            try:
                with contextlib.redirect_stderr(tee):
                    fn(job)
            except Exception as exc:  # surfaced to the interface, not swallowed
                job.error = f"{type(exc).__name__}: {exc}"
                job.log.append(f"FAILED: {job.error}")
            finally:
                job.finished = time.time()

        threading.Thread(target=run, daemon=True, name=f"birdy-{name}").start()
        return {"ok": True, "job": job.to_dict()}

    def stop(self) -> dict[str, Any]:
        job = self.job
        if not job or job.finished is not None:
            return {"ok": False, "error": "nothing is running"}
        job.stop()
        return {"ok": True, "job": job.to_dict()}

    def harvest(self, body: dict[str, Any]) -> dict[str, Any]:
        species = body.get("species") or None
        per_species = int(body.get("perSpecies", 10))
        quality = str(body.get("quality", "A"))
        # None = the store's own saved caps (harvest.HarvestStore resolves them);
        # defaulting to DEFAULT_CAP here would trim an enlarged store back on save.
        cap = body.get("cap")
        cap = None if cap is None else int(cap)
        max_seconds = float(body.get("maxSeconds", harvest.DEFAULT_MAX_SECONDS))
        from_dir = body.get("fromDir") or None
        dry_run = bool(body.get("dryRun"))

        def run(job: Job) -> None:
            store = harvest.HarvestStore(self.store_path, cap=cap)
            if from_dir:
                report = harvest.harvest_directory(
                    store, Path(from_dir), max_seconds=max_seconds, species_id=species,
                    should_stop=lambda: job.cancelled,
                )
            else:
                key = os.environ.get("XC_API_KEY", "")
                client = harvest.XenoCanto(key)
                # Discovered species are collected exactly like the authored ones — that is
                # the whole point of the registry, and a loop that ignored it would keep
                # harvesting twelve birds while the file said fifteen. Both are loaded here,
                # inside the job: this closure once referenced the *loop* route's
                # `inventory`/`registry` locals instead, and every hand harvest died on the
                # NameError before it fetched a thing.
                targets = harvest.species_queries(
                    load_inventory(self.inventory_path),
                    quality=quality,
                    extra=harvest.load_discovered(self.discovered_path),
                )
                if species:
                    targets = [t for t in targets if t[0] == species]
                report = harvest.harvest_xeno_canto(
                    store, client, targets, per_species=per_species,
                    max_seconds=max_seconds, dry_run=dry_run,
                    should_stop=lambda: job.cancelled,
                    max_length_seconds=float(
                        body.get("maxLength", harvest.DEFAULT_MAX_LENGTH_SECONDS)
                    ),
                    clean_only=bool(body.get("cleanOnly")),
                )
            if not dry_run:
                store.save()
                harvest.log(harvest.format_report(report, store))

        label = f"from {from_dir}" if from_dir else f"{species or 'all species'} x{per_species}"
        return self.start("harvest", label + (" (dry run)" if dry_run else ""), run)

    def _fit(self, job: Job, types: int, learned_only: bool = False, invert: bool = True) -> None:
        """Fit syllable types and syntax from the store. Shared by `learn` and `loop`."""
        store = harvest.HarvestStore(self.store_path)
        if not store.syllables:
            raise RuntimeError("no syllable observations yet — harvest first")
        from .cli import ensure_calibration

        inventory = load_inventory(self.inventory_path)

        # Re-read the critic on every fit: `critic train` alternates with `learn`, so the
        # right weights are whichever ones are on disk *now*. `load_critic` never raises —
        # a missing file or a missing torch logs a line and returns None.
        from .cli import learned_components, load_critic

        # `critic_path` defaults to `out/critic.pt` and is simply absent until something has
        # been trained, so this is the ordinary path rather than the exceptional one.
        quietly = self.critic_path is not None and not self.critic_path.exists()
        trained = None if quietly else load_critic(
            str(self.critic_path) if self.critic_path else None
        )
        realism, embedder = learned_components(
            trained, store.syllables, self.critic_weight, self.embed_typing
        )

        typing: list[dict[str, Any]] = []
        prior = learn.previous_fit(self.learned_path)
        document = learn.build_learned_inventory(
            store.syllables,
            inventory,
            ensure_calibration(self.out_path),
            descriptors={
                rid: harvest.np.asarray(row, dtype=float)
                for rid, row in store.recording_descriptors.items()
            },
            types=types,
            should_stop=lambda: job.cancelled,
            invert=invert,
            # So a refit keeps the ids the last one used. Without this every pass renamed
            # every learned syllable and the galaxy's labels stopped meaning anything.
            prior=prior,
            embedder=embedder,
            realism=realism,
            # Where a discovered bird's common name is; see `build_learned_inventory`.
            discovered=harvest.load_discovered(self.discovered_path),
            typing=typing,
        )
        # The label-free tail, identical to `cmd_learn`'s — this is the fit the ingested
        # (unlabelled) audio actually arrives through, so it must not drift from the
        # command-line one: same inheritance, same candidates, same chunks. The novelty
        # scorer is the one ingest already uses; with no scorer the pool is skipped with
        # a logged reason rather than typed at an invented threshold.
        scorer = self._novelty_scorer()
        unlabelled_embedder = embedder
        if (
            unlabelled_embedder is None
            and scorer is not None
            and any(o.mel_patch is not None for o in store.syllables)
        ):
            unlabelled_embedder = learn.critic_embedder(scorer[0])
        learn.fit_unlabelled(
            document,
            store.syllables,
            typing,
            embedder=unlabelled_embedder,
            novelty=scorer[1] if scorer else None,
            previous=prior.get(learn.UNLABELLED_SPECIES),
        )
        learn.attach_chunks(document, store.syllables, typing)
        song_rows = learn.attach_song_types(document, store.syllables, typing)
        if not document["species"]:
            raise RuntimeError("no species had enough observations to fit")
        learn.write_learned_inventory(
            self.learned_path,
            document if learned_only else learn.merge_learned_inventory(inventory, document),
        )
        harvest.log(f"wrote {self.learned_path}")
        # The same table `cmd_learn` writes: a fit from the Learn tab re-keys the store's
        # observations exactly like one from the terminal, and the build reads it either way.
        (self.store_path / learn.TYPING_NAME).write_text(
            json.dumps({"version": 1, "entries": typing}, indent=1) + "\n",
            encoding="utf-8",
        )
        if song_rows:
            (self.store_path / learn.SONG_TYPING_NAME).write_text(
                json.dumps({"version": 1, "entries": song_rows}, indent=1) + "\n",
                encoding="utf-8",
            )

    def learn(self, body: dict[str, Any]) -> dict[str, Any]:
        types = int(body.get("types", learn.DEFAULT_TYPES))
        learned_only = bool(body.get("learnedOnly"))

        def run(job: Job) -> None:
            self._fit(job, types, learned_only, invert=not bool(body.get("noInvert")))

        detail = f"{types} types per species"
        return self.start("learn", detail + (" (learned only)" if learned_only else ""), run)

    def ingest(self, audio: bytes, species_id: str, name: str) -> dict[str, Any]:
        """Fold one recording made in the browser into the store.

        It goes through `ingest_file`, the same function the harvester uses, so a
        recording captured at the desk and one downloaded from xeno-canto are analysed
        by identical code. Doing the segmentation in the browser instead would mean a
        second implementation of contract 8.2 to keep in step, and there are already two.
        """
        if not audio:
            return {"ok": False, "error": "no audio in the request"}

        def run(job: Job) -> None:
            store = harvest.HarvestStore(self.store_path)
            report = harvest.HarvestReport()
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / name
                path.write_bytes(audio)
                rid = f"local-{name}"
                harvest.ingest_file(store, path, species_id, rid, None, report)
                store.note_recording(
                    rid,
                    {
                        "speciesId": species_id,
                        "recordist": "recorded in the browser",
                        "licence": "yours",
                        "url": "",
                    },
                )
            # "This bird just sang something new", flagged while the observations are
            # still identifiable as the ones this recording added. Without this, a
            # genuinely unheard syllable is silently assigned to the nearest existing
            # knot at the next grow — the failure docs/09 §9.2b use 2 exists to end.
            # The flag is what `grow` reads to hold a point back from force-assignment.
            new_obs = [o for o in store.syllables if o.recording_id == rid]
            scorer = self._novelty_scorer()
            n_novel = 0
            if scorer is not None:
                trained, novelty = scorer
                embeddable = [o for o in new_obs if o.mel_patch is not None]
                if embeddable:
                    patches = harvest.np.stack(
                        [harvest.np.asarray(o.mel_patch, dtype=harvest.np.float32)
                         for o in embeddable]
                    )
                    flags = novelty.is_novel(trained.embed(patches))
                    for o, flag in zip(embeddable, flags):
                        o.novel = bool(flag)
                    n_novel = int(flags.sum())
                    if n_novel:
                        harvest.log(
                            f"{n_novel} of {len(new_obs)} syllables are unlike every "
                            "known type — flagged novel (still unlabelled: detecting "
                            "that a sound is new is not knowing what it means)"
                        )
            store.save()
            job.result = {"novel": n_novel, "total": len(new_obs)}
            harvest.log(harvest.format_report(report, store))

        return self.start("ingest", f"{name} as {species_id}", run)

    def _novelty_scorer(self) -> tuple[Any, Any] | None:
        """The critic plus its novelty centroids, or None when either is absent.

        `critic.pt` is auto-discovered exactly as `_fit` discovers it, and the
        centroids sit next to it under the name `cmd_critic` writes
        (`<stem>-novelty.json`). Loaded lazily on the first ingest that can use them
        and reloaded when either file's mtime moves — the alternation of docs/09 §9.3
        keeps retraining the critic, and a scorer held open across a retrain would
        measure distances in a space that no longer exists.

        With no scorer, ingest behaves exactly as it always did: every observation
        keeps `novel=False`. That is the honest default — an unmeasured syllable is
        not a known syllable, but flagging everything would be a false-positive rate
        of 100 %, and the detector's whole point is that the rate is chosen (§9.2b).
        """
        from .cli import DEFAULT_CRITIC, load_critic

        critic_path = self.critic_path
        if critic_path is None:
            critic_path = DEFAULT_CRITIC if DEFAULT_CRITIC.exists() else None
        novelty_path = (
            critic_path.with_name(critic_path.stem + "-novelty.json")
            if critic_path is not None
            else None
        )
        if (
            critic_path is None
            or not critic_path.exists()
            or novelty_path is None
            or not novelty_path.exists()
        ):
            self._warn_no_novelty(critic_path, novelty_path)
            return None
        key = (critic_path.stat().st_mtime, novelty_path.stat().st_mtime)
        if isinstance(self._novelty, tuple) and self._novelty[:2] == key:
            return self._novelty[2], self._novelty[3]
        try:
            from . import critic as critic_mod

            trained = load_critic(str(critic_path))
            scorer = critic_mod.Novelty.load(novelty_path) if trained is not None else None
        except Exception as exc:
            harvest.log(f"novelty scorer unusable ({exc}); ingest continues without it")
            trained, scorer = None, None
        if scorer is None:
            self._warn_no_novelty(critic_path, novelty_path)
            self._novelty = False
            return None
        self._novelty = (*key, trained, scorer)
        harvest.log(
            f"novelty scorer loaded (threshold {scorer.threshold:.4f} at a chosen "
            f"{scorer.report.target_false_positive:.0%} false-positive rate)"
        )
        return trained, scorer

    def _warn_no_novelty(self, critic_path: Any, novelty_path: Any) -> None:
        """Absence is worth one line, not one per ingest."""
        if self._novelty_warned:
            return
        self._novelty_warned = True
        missing = (
            f"no {novelty_path.name}"
            if critic_path is not None and Path(critic_path).exists()
            else "no trained critic"
        )
        harvest.log(
            f"{missing} — ingest cannot flag unheard syllables; everything is stored "
            "with novel=False, as before (`critic train` writes both files)"
        )

    def _type_of(self) -> dict[tuple[str, str, int], str]:
        """(speciesId, recordingId, order) -> typeId, from the store's typing.json.

        Cached by mtime: status is polled every 1.5 s and typing.json is 5 MB at
        40 k observations, so parsing it per poll would be the syllables.jsonl
        mistake again at a smaller scale.
        """
        path = self.store_path / learn.TYPING_NAME
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return {}
        if self._typing_cache and self._typing_cache[0] == mtime:
            return self._typing_cache[1]
        try:
            typing = json.loads(path.read_text(encoding="utf-8"))
            table = {
                (e["speciesId"], e["recordingId"], int(e["order"])): str(e["typeId"])
                for e in typing.get("entries", [])
            }
        except (OSError, ValueError, KeyError):
            table = {}
        self._typing_cache = (mtime, table)
        return table

    def _novel_summary(self) -> dict[str, Any]:
        """Store-wide novelty count and the most recent flagged syllables.

        Read by byte scan, not by parsing `syllables.jsonl`: the status endpoint's
        reason for existing is that that file costs over a second to parse at 26 MB,
        and it is polled every 1.5 s. `bytes.count` and a reverse search for the last
        few flagged lines are milliseconds on the same file, and — unlike a sidecar —
        can never disagree with the store, because they *are* the store.
        """
        out: dict[str, Any] = {"novelCount": 0, "recentNovel": []}
        path = self.store_path / "syllables.jsonl"
        try:
            raw = path.read_bytes()
        except OSError:
            return out
        needle = b'"novel": true'
        out["novelCount"] = raw.count(needle)
        recent: list[dict[str, Any]] = []
        end = len(raw)
        while len(recent) < 8:
            at = raw.rfind(needle, 0, end)
            if at < 0:
                break
            start = raw.rfind(b"\n", 0, at) + 1
            stop = raw.find(b"\n", at)
            end = start  # the next search looks before this line
            try:
                d = json.loads(raw[start : stop if stop >= 0 else len(raw)])
            except ValueError:
                continue
            recent.append(
                {
                    # `syllables.jsonl` is `asdict(SyllableObservation)`, so its keys
                    # are snake_case — reading camelCase here reported every flagged
                    # syllable as an anonymous one.
                    "speciesId": d.get("species_id", ""),
                    "recordingId": d.get("recording_id", ""),
                    "order": int(d.get("order", 0)),
                }
            )
        type_of = self._type_of() if recent else {}
        for entry in recent:
            entry["typeId"] = type_of.get(
                (entry["speciesId"], entry["recordingId"], entry["order"]), ""
            )
        out["recentNovel"] = recent
        return out

    def loop(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        Keep learning: harvest a little, fit what came in, grow the galaxy, repeat.

        The three steps were already here as three buttons, and pressing them in order
        forever is what learning from the wild actually is — there is no point at which
        a corpus of field recordings is finished. Running the cycle as one job rather
        than as three makes that the default rather than a discipline, and it puts the
        loop in the control process rather than in the browser, so closing the tab does
        not stop it.

        Each pass is deliberately small. A long harvest followed by one enormous rebuild
        is the discontinuity this was meant to remove; a few recordings at a time, folded
        in by `grow`, is a corpus that visibly accretes. The galaxy is only rebuilt when
        `drift` says the frame has stopped describing its own contents — which is the one
        thing extension cannot fix, because it never re-clusters.
        """
        per_pass = max(1, int(body.get("perSpecies", 2)))
        quality = str(body.get("quality", ">B"))
        types = int(body.get("types", learn.DEFAULT_TYPES))
        # None = the store's own saved caps (harvest.HarvestStore resolves them);
        # defaulting to DEFAULT_CAP here would trim an enlarged store back on save.
        cap = body.get("cap")
        cap = None if cap is None else int(cap)
        rebuild_at = float(body.get("rebuildAt", 0.35))
        passes = int(body.get("passes", 0))  # 0 = until stopped
        max_length = float(body.get("maxLength", harvest.DEFAULT_MAX_LENGTH_SECONDS))
        clean_only = bool(body.get("cleanOnly"))
        # Species to look for at the start of each pass. 0 keeps the loop to the birds it
        # already knows, which is what it did before this existed.
        discover = int(body.get("discover", 0))

        def run(job: Job) -> None:
            from .cli import cmd_grow

            done = 0
            while not job.cancelled and (passes <= 0 or done < passes):
                done += 1
                store = harvest.HarvestStore(self.store_path, cap=cap)
                key = os.environ.get("XC_API_KEY", "")
                inventory = load_inventory(self.inventory_path)
                registry = harvest.load_discovered(self.discovered_path)

                # **Learning now looks for birds as well as for calls.**
                #
                # Discovery was a separate command run by hand, so a loop left going for an hour
                # deepened twelve repertoires and never widened the corpus — which is not what
                # anyone means by "keep learning". The sweep asks xeno-canto what else it holds in
                # the genera already modelled, adds what it finds to the registry, and from that
                # moment the same pass harvests it: `species_queries` unions the registry in, and
                # the least-collected-first ordering puts a bird holding nothing at the front of
                # the queue rather than behind twelve that hold two thousand each.
                if discover > 0:
                    harvest.log(f"--- pass {done}: looking for new species ---")
                    try:
                        found = harvest.discover_species(
                            harvest.XenoCanto(key),
                            known={sp["id"] for sp in inventory.get("species", [])}
                            | {e["id"] for e in registry},
                            limit=discover,
                            genera=sorted(
                                {sp["scientific"].split()[0]
                                 for sp in inventory.get("species", [])
                                 if sp.get("scientific")}
                            ),
                            max_pages=int(body.get("discoverPages", 2)),
                        )
                        if found:
                            registry = [*registry, *found]
                            harvest.save_discovered(self.discovered_path, registry)
                            harvest.log(
                                f"  {len(found)} new species added; {len(registry)} discovered "
                                "in total"
                            )
                        else:
                            harvest.log("  nothing new in those genera")
                    except Exception as err:
                        harvest.log(f"discovery skipped: {err}")

                harvest.log(f"--- pass {done}: harvesting ---")
                # Discovered species are collected exactly like the authored ones — that is
                # the whole point of the registry, and a loop that ignored it would keep
                # harvesting twelve birds while the file said fifteen.
                targets = harvest.species_queries(
                    inventory, quality=quality, extra=registry
                )
                report = harvest.harvest_xeno_canto(
                    store, harvest.XenoCanto(key), targets, per_species=per_pass,
                    max_seconds=harvest.DEFAULT_MAX_SECONDS,
                    should_stop=lambda: job.cancelled,
                    max_length_seconds=max_length,
                    clean_only=clean_only,
                )
                store.save()
                harvest.log(harvest.format_report(report, store))
                if job.cancelled:
                    break

                harvest.log(f"--- pass {done}: fitting syllables and syntax ---")
                try:
                    self._fit(job, types, learned_only=False)
                except Exception as err:  # a thin pass is not a failed loop
                    harvest.log(f"fit skipped: {err}")
                if job.cancelled:
                    break

                harvest.log(f"--- pass {done}: growing the galaxy ---")
                # So the drift figure below can be told apart from the one a previous pass
                # left in the manifest: a grow that adds nothing writes no new entry.
                generation_before = self._generation()
                try:
                    argv = argparse.Namespace(
                        out=str(self.out_path),
                        harvest_store=str(self.store_path),
                        only_new=True,
                        inventory=str(self.learned_path),
                    )
                    cmd_grow(argv)
                except Exception as err:
                    harvest.log(f"grow skipped: {err}")

                # **The rebuild this docstring has always promised, which until now did not
                # exist.** `rebuild_at` was parsed, printed in the job's label and never read
                # again, so a loop left running for an hour accumulated fitted types that no
                # clustering had ever seen: `grow` assigns new audio to the nearest *existing*
                # knot and cannot create one, so a genuinely new call joined whatever it was
                # least unlike and the galaxy slowly stopped describing its own contents. The
                # drift figure is exactly the measurement of that, and it is already written
                # into the manifest by every grow, so the trigger costs one file read.
                # Two reasons to rebuild, and the second one is the one that fires in
                # practice. Drift says the *arrangement* has stopped describing its contents;
                # a fitted inventory newer than the galaxy says the *repertoire* has. Once
                # the harvest store is at its cap — which it reaches early and stays at — a
                # pass adds no points at all and only the second reason is ever true, so
                # triggering on drift alone would have meant never rebuilding again.
                reason = None
                unmatched = self._last_drift(grew_to=generation_before)
                if unmatched is not None and unmatched > rebuild_at:
                    reason = (
                        f"{unmatched:.0%} of the new audio matched no existing knot "
                        f"(over {rebuild_at:.0%})"
                    )
                else:
                    missing = self._unbuilt_types()
                    if missing:
                        reason = (
                            f"{len(missing)} fitted type(s) have no cluster to sit in "
                            f"({', '.join(missing[:3])}"
                            + (", …" if len(missing) > 3 else "")
                            + ")"
                        )
                if reason:
                    harvest.log(f"--- pass {done}: {reason} — rebuilding ---")
                    try:
                        self._rebuild(job)
                    except Exception as err:
                        harvest.log(f"rebuild skipped: {err}")
                else:
                    harvest.log(
                        f"  pass {done}: galaxy left as it is — "
                        f"drift {'n/a' if unmatched is None else f'{unmatched:.0%}'}, "
                        "inventory no newer than the build"
                    )

                # What the pass actually learned, as one line. A log that only says which
                # step is running tells you it is alive and nothing about whether it is
                # getting anywhere; these are the four numbers that move.
                after = harvest.HarvestStore(self.store_path)
                learned = self._learned_counts()
                harvest.log(
                    f"=== pass {done} learned: {len(after.recordings)} recordings, "
                    f"{len(after.syllables)} syllables, {learned['types']} fitted types "
                    f"across {learned['species']} species, galaxy {self._galaxy_size()} points"
                )

        detail = (
            f"{per_pass} per species per pass, rebuild past {rebuild_at:.0%} drift"
            + (f", +{discover} new species per pass" if discover else "")
        )
        return self.start("loop", detail, run)

    def _learned_counts(self) -> dict[str, int]:
        """Species fitted and types fitted, or zeros before anything has been."""
        try:
            doc = json.loads(self.learned_path.read_text(encoding="utf-8"))
        except Exception:
            return {"species": 0, "types": 0}
        species = doc.get("species", [])
        return {
            "species": len(species),
            "types": sum(
                sum(1 for y in sp.get("syllables", []) if str(y.get("id", "")).startswith("L"))
                for sp in species
            ),
        }

    def _galaxy_size(self) -> int:
        try:
            return int(json.loads((self.out_path / "manifest.json").read_text())["points"])
        except Exception:
            return 0

    def _manifest(self) -> dict[str, Any]:
        try:
            return json.loads((self.out_path / "manifest.json").read_text())
        except Exception:
            return {}

    def _generation(self) -> int:
        return int(self._manifest().get("generation", 0) or 0)

    def _last_drift(self, grew_to: int | None = None) -> float | None:
        """The share of the newest grown points that matched no existing knot.

        Read from the manifest rather than passed back from `cmd_grow`, because every grow
        already records it there and a return value would only be a second copy that could
        disagree with the first. `grew_to` is the generation counter from *before* the grow:
        if it has not moved, the newest entry belongs to some earlier pass and reporting it
        as this pass's drift would be a stale number dressed up as a fresh one.
        """
        manifest = self._manifest()
        if grew_to is not None and int(manifest.get("generation", 0) or 0) == grew_to:
            return None
        try:
            grown = manifest.get("grownBy") or []
            return float(grown[-1]["drift"]["unmatched"])
        except Exception:
            return None

    def _unbuilt_types(self) -> list[str]:
        """Fitted types the built galaxy has no cluster for — the honest reason to rebuild.

        **The trigger used to be the inventory's mtime, which is true every single pass.**
        `learn` refits from scratch each time and rewrites the file, so "newer than the galaxy"
        fired unconditionally and every pass ended in a full global rebuild: KMeans, the
        projection and the per-point space recomputed over the whole corpus, about 165 s at
        43 000 points, to absorb what was often the same repertoire with slightly nudged
        parameters.

        What actually requires a rebuild is a type the galaxy *cannot place*. `grow` assigns new
        audio to the nearest existing knot and cannot create one, so a genuinely new syllable —
        or a new species — has nowhere to go until the clustering runs again. A refit that only
        moved a contour a few hertz does not need that; the knot it belongs to already exists.

        This is only meaningful because ids are now stable across refits (`learn.assign_ids`).
        While they were renumbered every run, every type looked new every pass and this check
        would have been the mtime check with extra steps.
        """
        if not self.learned_path.exists():
            return []
        try:
            doc = json.loads(self.learned_path.read_text(encoding="utf-8"))
            centroids = json.loads((self.out_path / "centroids.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # No galaxy, or an unreadable one: rebuilding is the only way forward.
            return ["<no galaxy>"]
        placed = {
            (c.get("speciesId"), c.get("syllableId"))
            for c in centroids.get("items", [])
            if c.get("syllableId")
        }
        missing = [
            f"{sp['id']}/{y['id']}"
            for sp in doc.get("species", [])
            for y in sp.get("syllables", [])
            if (sp["id"], y["id"]) not in placed
        ]
        return missing

    def _rebuild(self, job: Job) -> None:
        """A full build from the fitted inventory, cancellable like any other step."""
        from .cli import build_parser, cmd_build
        from .corpus import Cancelled

        argv = [
            "build",
            "--source", "synthetic",
            "--out", str(self.out_path),
            "--no-compare-projections",
            "--inventory", str(self.learned_path),
        ]
        if (self.store_path / "state.json").exists():
            argv += ["--harvest-store", str(self.store_path)]
        try:
            code = cmd_build(build_parser().parse_args(argv), should_stop=lambda: job.cancelled)
        except Cancelled as stopped:
            harvest.log(str(stopped) + " — the assets on disk are the previous build")
            return
        if code != 0:
            raise RuntimeError(f"rebuild exited {code}")

    def grow(self, body: dict[str, Any]) -> dict[str, Any]:
        """Add the newest harvested audio to the built galaxy, leaving it in place."""

        def run(job: Job) -> None:
            from .cli import cmd_grow

            argv = argparse.Namespace(
                out=str(self.out_path),
                harvest_store=str(self.store_path),
                only_new=not bool(body.get("all")),
                inventory=str(self.learned_path),
            )
            cmd_grow(argv)

        return self.start("grow", "adding new audio to the galaxy", run)

    def expand(self, body: dict[str, Any]) -> dict[str, Any]:
        """Collect discovered species the store does not cover yet — the loop, widened.

        Orchestration only: the target list comes from `cli.expand_targets` and each
        target goes through the same harvest → embed → learn → grow path the
        command-line `expand` runs. A dry run lists the targets without touching the
        network.
        """
        max_species = int(body.get("maxSpecies", 2))
        max_recordings = int(body.get("maxRecordings", 20))
        dry_run = bool(body.get("dryRun"))

        def run(job: Job) -> None:
            from .cli import build_parser, cmd_expand

            argv = [
                "expand",
                "--store", str(self.store_path),
                "--discovered", str(self.discovered_path),
                "--max-species", str(max_species),
                "--max-recordings", str(max_recordings),
                "--out", str(self.out_path),
                "--learned", str(self.learned_path),
                "--inventory", str(self.inventory_path),
            ]
            if self.critic_path:
                argv += ["--critic", str(self.critic_path)]
            if dry_run:
                argv.append("--dry-run")
            code = cmd_expand(
                build_parser().parse_args(argv), should_stop=lambda: job.cancelled
            )
            if code != 0:
                raise RuntimeError(f"expand exited {code}")

        detail = f"up to {max_species} new species, {max_recordings} recordings each"
        return self.start("expand", detail + (" (dry run)" if dry_run else ""), run)

    def build(self, body: dict[str, Any]) -> dict[str, Any]:
        # Both default to on, because the corpus is one accumulating thing: the rendered
        # repertoire is the frame that names everything, and the harvest is what fills it in.
        # `useLearned=false` still exists for a documented-only galaxy, and it is a diagnostic.
        use_learned = bool(body.get("useLearned", True))
        include_harvest = bool(body.get("includeHarvest", True))
        source = str(body.get("source", "synthetic"))
        clustering = str(body.get("clustering", "kmeans"))
        min_cluster_size = int(body.get("minClusterSize", 25))

        def run(job: Job) -> None:
            from .cli import build_parser, cmd_build

            argv = ["build", "--source", source, "--out", str(self.out_path),
                    "--no-compare-projections",
                    "--clustering", clustering,
                    "--min-cluster-size", str(min_cluster_size)]
            if use_learned:
                argv += ["--inventory", str(self.learned_path)]
            else:
                argv += ["--inventory", str(self.inventory_path)]
            argv += ["--harvest-store", str(self.store_path)]
            if not include_harvest:
                argv += ["--no-harvest"]
            from .corpus import Cancelled

            args = build_parser().parse_args(argv)
            try:
                code = cmd_build(args, should_stop=lambda: job.cancelled)
            except Cancelled as stopped:
                harvest.log(str(stopped) + " — the assets on disk are the previous build")
                return
            if code != 0:
                raise RuntimeError(f"build exited {code}")

        parts = [source]
        if use_learned:
            parts.append("learned inventory")
        if include_harvest:
            parts.append("+ harvest")
        return self.start("build", " ".join(parts), run)


# --- HTTP ---------------------------------------------------------------------------


def make_handler(pipeline: Pipeline) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "birdy-pipeline"

        def log_message(self, *args: Any) -> None:  # quiet; the job log is what matters
            pass

        def _send(self, payload: dict[str, Any], code: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            # The app is served by Vite on another port during development, so the
            # browser treats this as cross-origin. Safe here only because the socket
            # is bound to loopback.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            try:
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # **A client that hung up is not an error, and printing it as one was the
                # actual damage.** The app polls this endpoint on every tab, so a reload, a
                # navigation or an aborted fetch routinely closes the socket while the
                # response is still going out — and the status payload is now the largest
                # thing here (the job log plus the discovered-species list), which widens
                # the window for it. Unhandled, `ThreadingHTTPServer` dumped a full
                # traceback to stderr, and stderr is teed into the job log the Learn tab
                # streams, so a harmless disconnect turned into ten lines of Python
                # internals in the middle of the harvest progress a reader was following.
                return

        def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
            self._send({"ok": True})

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/api/status"):
                self._send(pipeline.status())
            elif self.path.startswith("/api/job"):
                self._send({"ok": True, "job": pipeline.job.to_dict() if pipeline.job else None})
            else:
                self._send({"ok": False, "error": "unknown endpoint"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            if self.path.startswith("/api/ingest"):
                # raw audio bytes, with the metadata in the query string
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                result = pipeline.ingest(
                    self.rfile.read(length),
                    query.get("species", ["unlabelled"])[0],
                    query.get("name", ["recording.webm"])[0],
                )
                self._send(result, 200 if result.get("ok") else 409)
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send({"ok": False, "error": "body is not JSON"}, 400)
                return
            if self.path.startswith("/api/stop"):
                result = pipeline.stop()
                self._send(result, 200 if result.get("ok") else 409)
                return
            routes = {
                "/api/grow": pipeline.grow,
                "/api/loop": pipeline.loop,
                "/api/harvest": pipeline.harvest,
                "/api/learn": pipeline.learn,
                "/api/build": pipeline.build,
                "/api/expand": pipeline.expand,
            }
            for path, fn in routes.items():
                if self.path.startswith(path):
                    result = fn(body)
                    self._send(result, 200 if result.get("ok") else 409)
                    return
            self._send({"ok": False, "error": "unknown endpoint"}, 404)

    return Handler


def serve(pipeline: Pipeline, port: int = DEFAULT_PORT) -> None:
    class QuietServer(ThreadingHTTPServer):
        """Same server, silent about clients that hang up.

        The guard in `_send` covers the write side; this covers the read side and anything
        else socket-level, because `socketserver.handle_error` prints a traceback for every
        exception that escapes a handler — and stderr here is teed into the job log, so a
        dropped connection became ten lines of Python internals in the middle of the progress
        someone was reading. Anything that is not a connection error still prints.
        """

        def handle_error(self, request: Any, client_address: Any) -> None:
            import sys as _sys

            if isinstance(_sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
                return
            super().handle_error(request, client_address)

    try:
        server = QuietServer((BIND_HOST, port), make_handler(pipeline))
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        harvest.log(diagnose_port(port))
        raise SystemExit(2) from None

    harvest.log(f"birdy pipeline control on http://{BIND_HOST}:{port} (loopback only)")
    harvest.log("the app's Learn tab will pick this up automatically; ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        harvest.log("\nstopped")
    finally:
        server.server_close()


def probe(port: int, timeout: float = 2.0) -> str:
    """Classify whatever holds `port`: `free`, `healthy`, `silent`, or `foreign`.

    The distinction that matters is **`silent`**. A process can hold the listening socket
    without ever answering on it — suspended, wedged, or still importing numba — and from the
    outside that is not the same failure as nothing being there, even though both make a
    status request fail. The kernel completes the TCP handshake from the listen backlog, so
    `connect` succeeds and only the *reply* is missing.
    """
    import http.client

    try:
        conn = http.client.HTTPConnection(BIND_HOST, port, timeout=timeout)
        conn.connect()
    except (ConnectionRefusedError, OSError):
        return "free"
    try:
        conn.request("GET", "/api/status")
        body = json.loads(conn.getresponse().read().decode("utf-8"))
        return "healthy" if isinstance(body, dict) and "store" in body else "foreign"
    except (TimeoutError, OSError, ValueError, json.JSONDecodeError):
        # Connected, then nothing came back inside the timeout.
        return "silent"
    finally:
        conn.close()


def port_holder(port: int) -> str:
    """`pid command` of whatever is listening on `port`, or "" if it cannot be determined.

    Read from `/proc` rather than by shelling out to `ss` or `lsof`, so it works on a machine
    that has neither and cannot fail in a way that matters — this only ever decorates an
    error message.
    """
    try:
        wanted = f"{port:04X}"
        inodes: set[str] = set()
        for name in ("tcp", "tcp6"):
            path = Path("/proc/net") / name
            if not path.exists():
                continue
            for line in path.read_text().splitlines()[1:]:
                parts = line.split()
                # local_address is host:port in hex; state 0A is LISTEN
                if len(parts) > 9 and parts[1].endswith(":" + wanted) and parts[3] == "0A":
                    inodes.add(parts[9])
        if not inodes:
            return ""
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                for fd in (proc / "fd").iterdir():
                    target = os.readlink(fd)
                    if target.startswith("socket:[") and target[8:-1] in inodes:
                        cmd = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode()
                        state = ""
                        for row in (proc / "status").read_text().splitlines():
                            if row.startswith("State:"):
                                state = row.split(":", 1)[1].strip()
                                break
                        return f"pid {proc.name} [{state}] {cmd.strip()[:110]}"
            except (PermissionError, FileNotFoundError, OSError):
                continue
    except (OSError, ValueError):
        return ""
    return ""


def diagnose_port(port: int) -> str:
    """Turn "address already in use" into something with a next step in it.

    Worth the code because the bare `OSError` traceback is actively misleading here. The
    failure that produced this function: a `serve` started in the background by an editor
    session was left **suspended** (state `T`) when that session went away. It kept the
    listening socket, so every later `serve` died with EADDRINUSE, while the app's status
    probe timed out and the Learn tab showed its "not running" fallback — so the interface
    said the server was absent and the terminal said it was already there, both correctly,
    and neither said what to do.
    """
    state = probe(port)
    holder = port_holder(port)
    where = f"\n  holder: {holder}" if holder else ""

    if state == "healthy":
        return (
            f"a birdy pipeline server is already running on {BIND_HOST}:{port}, so this one "
            f"is not needed.{where}\n"
            f"  The app's Learn tab is already talking to it. Use `--port` to run a second "
            f"one on purpose."
        )
    if state == "silent":
        return (
            f"{BIND_HOST}:{port} is held by a process that accepts connections but never "
            f"answers.{where}\n"
            f"  That is why the Learn tab shows the pipeline as not running: its status "
            f"request connects and then times out.\n"
            f"  Most often this is a `serve` from an earlier session that was suspended or "
            f"wedged. A stopped process ignores SIGTERM, so:\n"
            f"      kill -CONT <pid> && kill <pid>      # or: kill -9 <pid>\n"
            f"  then start this again. `--port` runs elsewhere if you would rather leave it."
        )
    if state == "foreign":
        return (
            f"{BIND_HOST}:{port} is held by something that is not a birdy pipeline "
            f"server.{where}\n"
            f"  Use `--port` to pick another, or stop that process."
        )
    return (
        f"could not bind {BIND_HOST}:{port}, but nothing answers there either — the socket is "
        f"probably in TIME_WAIT from a server that just exited.{where}\n"
        f"  Wait a few seconds and try again, or use `--port`."
    )
