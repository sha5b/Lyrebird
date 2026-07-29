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

    def state(self) -> str:
        if self.finished is None:
            return "stopping" if self.cancelled else "running"
        return "failed" if self.error else ("stopped" if self.cancelled else "done")

    def stop(self) -> None:
        """Ask the job to end. It stops at its next checkpoint, not immediately."""
        self.cancelled = True
        self.log.append("stop requested — finishing the current step")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "detail": self.detail,
            "state": self.state(),
            "seconds": round((self.finished or time.time()) - self.started, 1),
            "error": self.error,
            "cancelled": self.cancelled,
            "log": list(self.log),
        }


class Pipeline:
    """Holds the paths, the current job, and the lock that keeps runs serial."""

    def __init__(self, store_path: Path, inventory_path: Path, learned_path: Path, out_path: Path):
        self.store_path = Path(store_path)
        self.inventory_path = Path(inventory_path)
        self.discovered_path = Path(inventory_path).parent / harvest.DISCOVERED_NAME
        self.learned_path = Path(learned_path)
        self.out_path = Path(out_path)
        self.job: Job | None = None
        self._lock = threading.Lock()

    # -- status --

    def status(self) -> dict[str, Any]:
        store: dict[str, Any] = {"exists": False}
        if (self.store_path / "state.json").exists():
            s = harvest.HarvestStore(self.store_path)
            rep = s.representativeness()
            store = {
                "exists": True,
                "path": str(self.store_path),
                "descriptors": len(s),
                "descriptorsSeen": s.stream_n,
                "syllables": len(s.syllables),
                "recordings": len(s.recordings),
                "species": sorted(s.strata),
                "cap": s.cap,
                "meanDrift": round(rep["meanDrift"], 4),
                "stdRatio": round(rep["stdRatio"], 4),
            }

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
            store_obj = (
                harvest.HarvestStore(self.store_path)
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
        return {
            "ok": True,
            "hasKey": bool(os.environ.get("XC_API_KEY")),
            "ffmpeg": harvest.have_ffmpeg(),
            "store": store,
            "learned": learned,
            "built": built,
            "inventorySpecies": species,
            "discovered": discovered,
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
        cap = int(body.get("cap", harvest.DEFAULT_CAP))
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
                # harvesting twelve birds while the file said fifteen.
                targets = harvest.species_queries(
                    inventory, quality=quality, extra=registry
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
            prior=learn.previous_fit(self.learned_path),
        )
        if not document["species"]:
            raise RuntimeError("no species had enough observations to fit")
        learn.write_learned_inventory(
            self.learned_path,
            document if learned_only else learn.merge_learned_inventory(inventory, document),
        )
        harvest.log(f"wrote {self.learned_path}")

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
            store.save()
            harvest.log(harvest.format_report(report, store))

        return self.start("ingest", f"{name} as {species_id}", run)

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
        cap = int(body.get("cap", harvest.DEFAULT_CAP))
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

    server = QuietServer((BIND_HOST, port), make_handler(pipeline))
    harvest.log(f"birdy pipeline control on http://{BIND_HOST}:{port} (loopback only)")
    harvest.log("the app's Learn tab will pick this up automatically; ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        harvest.log("\nstopped")
    finally:
        server.server_close()
