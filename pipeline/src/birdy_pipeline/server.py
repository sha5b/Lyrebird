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

import contextlib
import io
import json
import os
import tempfile
import threading
import time
import urllib.parse
from collections import deque
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
            return "running"
        return "failed" if self.error else "done"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "detail": self.detail,
            "state": self.state(),
            "seconds": round((self.finished or time.time()) - self.started, 1),
            "error": self.error,
            "log": list(self.log),
        }


class Pipeline:
    """Holds the paths, the current job, and the lock that keeps runs serial."""

    def __init__(self, store_path: Path, inventory_path: Path, learned_path: Path, out_path: Path):
        self.store_path = Path(store_path)
        self.inventory_path = Path(inventory_path)
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
        return {
            "ok": True,
            "hasKey": bool(os.environ.get("XC_API_KEY")),
            "ffmpeg": harvest.have_ffmpeg(),
            "store": store,
            "learned": learned,
            "built": built,
            "inventorySpecies": species,
            "job": self.job.to_dict() if self.job else None,
        }

    # -- running --

    def start(self, name: str, detail: str, fn: Callable[[Job], None]) -> dict[str, Any]:
        with self._lock:
            if self.job and self.job.state() == "running":
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
                    store, Path(from_dir), max_seconds=max_seconds, species_id=species
                )
            else:
                key = os.environ.get("XC_API_KEY", "")
                client = harvest.XenoCanto(key)
                targets = harvest.species_queries(
                    load_inventory(self.inventory_path), quality=quality
                )
                if species:
                    targets = [t for t in targets if t[0] == species]
                report = harvest.harvest_xeno_canto(
                    store, client, targets, per_species=per_species,
                    max_seconds=max_seconds, dry_run=dry_run,
                )
            if not dry_run:
                store.save()
                harvest.log(harvest.format_report(report, store))

        label = f"from {from_dir}" if from_dir else f"{species or 'all species'} x{per_species}"
        return self.start("harvest", label + (" (dry run)" if dry_run else ""), run)

    def learn(self, body: dict[str, Any]) -> dict[str, Any]:
        types = int(body.get("types", learn.DEFAULT_TYPES))
        learned_only = bool(body.get("learnedOnly"))

        def run(job: Job) -> None:
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
            )
            if not document["species"]:
                raise RuntimeError("no species had enough observations to fit")
            learn.write_learned_inventory(
                self.learned_path,
                document if learned_only else learn.merge_learned_inventory(inventory, document),
            )
            harvest.log(f"wrote {self.learned_path}")

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

    def build(self, body: dict[str, Any]) -> dict[str, Any]:
        use_learned = bool(body.get("useLearned"))
        include_harvest = bool(body.get("includeHarvest", True))
        source = str(body.get("source", "synthetic"))

        def run(job: Job) -> None:
            from .cli import build_parser, cmd_build

            argv = ["build", "--source", source, "--out", str(self.out_path),
                    "--no-compare-projections"]
            if use_learned:
                argv += ["--inventory", str(self.learned_path)]
            else:
                argv += ["--inventory", str(self.inventory_path)]
            if include_harvest and (self.store_path / "state.json").exists():
                argv += ["--harvest-store", str(self.store_path)]
            args = build_parser().parse_args(argv)
            code = cmd_build(args)
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
            self.end_headers()
            self.wfile.write(body)

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
            routes = {
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
    server = ThreadingHTTPServer((BIND_HOST, port), make_handler(pipeline))
    harvest.log(f"birdy pipeline control on http://{BIND_HOST}:{port} (loopback only)")
    harvest.log("the app's Learn tab will pick this up automatically; ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        harvest.log("\nstopped")
    finally:
        server.server_close()
