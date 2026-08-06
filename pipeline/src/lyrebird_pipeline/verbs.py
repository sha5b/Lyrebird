"""The verbs the control surface may run, declared once.

**Why a registry rather than sixteen routes.**

`lyrebird-pipeline` has twenty-two subcommands and the Learn tab drove eight of them. The
other fourteen are where most of this project's measurements live — `placement`,
`specbench`, `spacemap`, `syntax`, `songspace`, `relations`, `critic groupings` — and
every one of them was reachable only from a terminal. So the interface could print a
resynthesis cosine and could not print whether that cosine meant anything audible, which
is the number `specbench` exists to produce.

Two ways to fix that. Sixteen endpoints with sixteen hand-written forms is sixteen places
for the interface to fall behind the flags it drives, and this codebase has been bitten
by exactly that: a probe looking for a `<select>` that had become a combobox reported six
vacuous passes for weeks. So one declaration per verb drives all three of the argv, the
form, and the result table. A flag that moves takes its control with it, and a verb that
is not declared here cannot be run at all.

**And the declaration is what makes the route safe.** `server.py` answers with
`Access-Control-Allow-Origin: *`, because the app is served by Vite on another port in
development — which means any page open in this browser can post to this socket. A route
that accepted a command line would hand every website a shell on this machine, and the
loopback bind would not help, because the request comes *from* the browser on this
machine. Every parameter here is coerced to its declared type and clamped to its declared
range, every path in an argv comes from the server's own configuration rather than from
the request, and anything undeclared is refused.

**Every report flag is supplied by the server, not by the caller.** Seven of these verbs
write a JSON report and all seven make it optional (`--report`, `--json`, `--out`), so the
ordinary way to run them leaves no measurement on disk. The tab always passes the flag,
into `out/reports/<verb>.json`. A measurement you have to remember to ask for is one that
does not exist most of the time.

**What is deliberately not here.** `build`, `harvest`, `learn`, `grow`, `expand` and
`loop` keep their own hand-written routes: they are the page's main actions rather than
measurements, they take far more arguments, and their forms already exist. `serve` cannot
run inside itself, and `demo` writes a wav nobody can hear from here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Rows a report table may send. `Job.result`'s own note says anything big belongs in the
#: log, and the reason is size: `specbench`'s report is 4.5 MB over 1 200 types, and the
#: Learn page re-reads these after every job. Longer reports are cut, say so, and name the
#: file that holds the rest.
MAX_ROWS = 40

#: Columns a generic table may draw. Past about seven the row stops being readable at this
#: font size and the eye cannot find the one number it came for.
MAX_COLS = 7

#: Where a verb's report goes. `out/` rather than `analysis/`, because `analysis/` is
#: hand-run one-off scripts kept for their published figures and this directory is
#: rewritten every time a button is pressed.
REPORTS_DIRNAME = "reports"

#: Report fields that are prose rather than data. They carry a report's own statement of
#: what it measured — worth showing as a headline, never as a table column.
PROSE_KEYS = ("definition", "note", "question", "warning", "rule", "verdict")


# --- the declaration ---------------------------------------------------------------


@dataclass(frozen=True)
class Param:
    """One control, and one argv flag.

    `kind` decides both how the value is coerced here and which control the page draws.
    `bool` is an argparse `store_true`: the flag's presence is the value, so a false one
    is emitted as nothing at all rather than as `--flag false`, which would set it.
    """

    name: str
    flag: str
    kind: str  # int | float | bool | choice | text
    default: Any
    label: str
    gloss: str
    lo: float | None = None
    hi: float | None = None
    step: float | None = None
    choices: tuple[tuple[str, str], ...] = ()
    #: Folded into a drawer on the page. The test is whether a reader would change it to
    #: ask a different question (primary) or only to reproduce one published run.
    advanced: bool = False
    #: A regex a `text` value must match end to end. Required for every text parameter:
    #: this is the one kind whose value reaches an argv as itself, so its shape is
    #: declared rather than assumed. See `coerce`.
    pattern: str | None = None
    #: Emitted even when it equals the default, because argparse marks it `required`.
    #: Eliding defaults keeps the job log readable, and for exactly one parameter here it
    #: would instead produce a run that cannot start: `sources fetch --source`.
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "default": self.default,
            "gloss": self.gloss,
            "advanced": self.advanced,
        }
        for key, value in (("lo", self.lo), ("hi", self.hi), ("step", self.step)):
            if value is not None:
                out[key] = value
        if self.choices:
            out["choices"] = [{"value": v, "label": lbl} for v, lbl in self.choices]
        return out


@dataclass(frozen=True)
class Need:
    """A precondition checked on disk, so a disabled button can say why it is disabled.

    Phrased as what IS required rather than what is missing, because the page prints it
    both ways round and only the positive form survives being negated.
    """

    what: str
    check: Callable[["Ctx"], bool]


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: str = "text"  # text | num | pct | chip
    digits: int | None = None
    width: str | None = None
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"key": self.key, "label": self.label, "kind": self.kind}
        if self.digits is not None:
            out["digits"] = self.digits
        if self.width:
            out["width"] = self.width
        if self.title:
            out["title"] = self.title
        return out


@dataclass(frozen=True)
class Ctx:
    """The paths the control process was started with.

    Every path in every argv comes from here. That is the other half of what keeps
    `/api/run` safe: a hostile page can choose which declared verb runs and its in-range
    parameters, and cannot choose what it reads or writes.
    """

    store: Path
    out: Path
    learned: Path
    inventory: Path
    critic: Path | None
    #: `pipeline/`, which is where `analysis/` and `out/` live.
    pipeline_root: Path

    @property
    def pipeline_out(self) -> Path:
        return self.pipeline_root / "out"

    @property
    def reports(self) -> Path:
        return self.pipeline_out / REPORTS_DIRNAME

    def report_for(self, verb_id: str) -> Path:
        return self.reports / f"{verb_id}.json"

    def rel(self, path: Path) -> str:
        """A path as the reader sees it in the repo, for printing on the page."""
        try:
            return str(path.relative_to(self.pipeline_root.parent))
        except ValueError:
            return str(path)


@dataclass(frozen=True)
class Verb:
    id: str
    argv: tuple[str, ...]
    title: str
    group: str
    #: One line, present tense, naming the question it answers — not a description of what
    #: it does. The page has room for one sentence, and "what would I learn by pressing
    #: this" is the one worth spending it on.
    measures: str
    #: What it overwrites, in words. Empty means it writes nothing but its own report,
    #: which is the distinction this page most needs to draw.
    writes: str = ""
    cost: str = ""
    params: tuple[Param, ...] = ()
    needs: tuple[Need, ...] = ()
    #: Whether it rewrites a file inside the harvest store. Those files are keyed by row
    #: index against each other and against the shipped assets — row `i` is the same
    #: syllable in all of them — so a verb that rewrites one while an analysis is in
    #: flight breaks that alignment with no error anywhere.
    mutates_store: bool = False
    #: Whether it writes the report at `report_at`. The flag itself is added by `paths`,
    #: because which flag carries it differs per verb (`--report`, `--json`, `--out`).
    has_report: bool = False
    #: Where that report is, when it is not this verb's slot under `out/reports`. Two verbs
    #: already wrote a JSON sidecar next to the model they train — `out/critic.json` and
    #: `out/inverse.json` — long before this registry existed. Pointing at those is better
    #: than adding a second report flag that would write the same numbers twice under a
    #: different name.
    report_at: Callable[["Ctx"], Path] | None = None
    #: Server-supplied flags: the paths, and the report destination. Takes the coerced
    #: parameters because a couple of verbs name their output after one.
    paths: Callable[["Ctx", dict[str, Any]], list[str]] = field(
        default=lambda _ctx, _p: []
    )


# --- coercion ----------------------------------------------------------------------


class Refused(ValueError):
    """A parameter the registry does not declare, or one that cannot be coerced."""


def coerce(param: Param, value: Any) -> Any:
    """One parameter, coerced to its declared type and clamped to its declared range.

    Numbers are clamped rather than rejected: a slider that sends 201 against a declared
    ceiling of 200 is an interface rounding error, and refusing it would surface as a job
    that will not start with nothing on screen to say why. A value that is not a number at
    all is refused, because that is not a rounding error.
    """
    if param.kind == "bool":
        return bool(value)
    if param.kind in ("int", "float"):
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise Refused(f"{param.name} takes a number, not {value!r}") from exc
        # NaN fails every comparison, so it would slide past both clamps untouched.
        if number != number or number in (float("inf"), float("-inf")):
            raise Refused(f"{param.name} takes a finite number, not {value!r}")
        if param.lo is not None:
            number = max(param.lo, number)
        if param.hi is not None:
            number = min(param.hi, number)
        return int(round(number)) if param.kind == "int" else number
    if param.kind == "choice":
        allowed = {v for v, _ in param.choices}
        text = str(value)
        if text not in allowed:
            raise Refused(f"{param.name} must be one of {sorted(allowed)}, not {text!r}")
        return text
    if param.kind == "text":
        text = str(value)
        # The only kind whose value reaches an argv as itself, so the shape is declared
        # per parameter rather than guessed at here. No pattern means no text allowed.
        if not param.pattern:
            raise Refused(f"{param.name} declares no shape, so no value is accepted")
        # A parameter whose default is blank is an optional one, and blank is how the page
        # says "not this time". It matches no pattern by design, so it is admitted here and
        # then dropped by `build_argv` for being the default — the flag never reaches the
        # command line at all, which is what the CLI's own `None` default means.
        if text == "" and param.default == "":
            return ""
        if len(text) > 64 or not re.fullmatch(param.pattern, text):
            raise Refused(f"{param.name} is not of the form {param.pattern}")
        return text
    raise Refused(f"{param.name} has an unknown kind {param.kind!r}")


def coerce_all(verb: Verb, params: dict[str, Any]) -> dict[str, Any]:
    """Every declared parameter, coerced, with the defaults filled in.

    Undeclared keys are refused rather than dropped. A dropped key is a control that
    appears to work and does nothing — the failure this registry exists to prevent — so a
    form that has fallen behind says so on the first press instead of on the tenth reading
    of a number that never changed.
    """
    declared = {p.name: p for p in verb.params}
    unknown = sorted(set(params) - set(declared))
    if unknown:
        raise Refused(
            f"{verb.id} does not take {', '.join(unknown)} — it takes "
            f"{', '.join(sorted(declared)) or 'no parameters'}"
        )
    return {
        name: coerce(param, params[name]) if name in params else param.default
        for name, param in declared.items()
    }


def build_argv(verb: Verb, ctx: Ctx, params: dict[str, Any]) -> list[str]:
    """The full argv for one run: subcommand, the server's paths, then the parameters."""
    values = coerce_all(verb, params)
    argv = [*verb.argv, *verb.paths(ctx, values)]
    for param in verb.params:
        value = values[param.name]
        if param.kind == "bool":
            if value:
                argv.append(param.flag)
            continue
        if value == param.default and not param.required:
            # Defaults stay off the command line, so the log records what was chosen
            # rather than the whole surface. The parser applies the same value either way —
            # unless it marked the argument required, in which case omitting it is a run
            # that refuses to start.
            continue
        argv += [param.flag, str(value)]
    return argv


def unmet(verb: Verb, ctx: Ctx) -> list[dict[str, Any]]:
    """Every precondition with its verdict, in declaration order."""
    out = []
    for need in verb.needs:
        try:
            ok = bool(need.check(ctx))
        except Exception:
            # A precondition that cannot be evaluated is not met. Raising here would take
            # the whole registry down over one missing directory.
            ok = False
        out.append({"ok": ok, "what": need.what})
    return out


# --- turning a report into a table -------------------------------------------------
#
# Two shapes cover every report this pipeline writes, and both are in the tree to check
# against rather than guessed at: `out/respfit-gan-report.json` and
# `analysis/specbench_capped_n1200.json` are row reports (a list of per-type dicts under
# `records` / `types`), and `analysis/v10_unknown_join.json` is a figure report (nested
# blocks of scalars). So the reducer prefers rows and falls back to figures.
#
# Generic rather than sixteen hand-written column specs, and that is the conservative
# choice, not the lazy one: a hand-written spec naming a field that has since been renamed
# draws a column of blanks, which reads as "measured, and zero". Reading the keys off the
# data cannot do that.

ROW_KEYS = (
    "records", "types", "rows", "speciesPairs", "items", "sweep", "arms",
    # `geometry.summarise`'s own manifest form, which `critic groupings` writes
    # verbatim rather than reshaping.
    "relations",
    # `verify`'s per-check list.
    "checks",
)


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _is_share(key: str, values: list[Any]) -> bool:
    """Whether a column of numbers is a share, and should print as a percentage.

    Named *and* ranged: a field called `share` holding 0.79 is a share, and one called
    `cosine` holding 0.79 is not. Printing a cosine as `79%` would be inventing a unit,
    which is the specific error the chorus counts made when `synthesized 2851` and
    `synthesized 2 %` appeared under one word.
    """
    if not re.search(r"share|fraction|rate|pct|percent", key, re.I):
        return False
    numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return bool(numbers) and all(0.0 <= float(v) <= 1.0 for v in numbers)


def _column_for(key: str, values: list[Any]) -> Column:
    numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    label = re.sub(r"(?<!^)(?=[A-Z])", " ", key).lower()
    if len(numbers) >= max(1, len(values) // 2):
        if _is_share(key, values):
            return Column(key, label, "pct", digits=1, title=key)
        # Integers keep their separators; fitted figures get three places, which is what
        # every published number in this project is quoted to.
        digits = None if all(float(v).is_integer() for v in numbers) else 3
        return Column(key, label, "num", digits=digits, title=key)
    return Column(key, label, "text", title=key)


def _rows_table(rows: list[dict[str, Any]]) -> tuple[list[Column], list[dict[str, Any]], int]:
    """A list of per-row dicts as a table, columns read off the data."""
    keys: list[str] = []
    for row in rows[: MAX_ROWS * 4]:
        for key in row:
            if key not in keys and key not in PROSE_KEYS and _scalar(row.get(key)):
                keys.append(key)
    # Text columns first — the row's identity is what you scan down — then the numbers.
    sample = {k: [r.get(k) for r in rows[:MAX_ROWS]] for k in keys}
    columns = [_column_for(k, sample[k]) for k in keys]
    columns.sort(key=lambda c: 0 if c.kind == "text" else 1)
    columns = columns[:MAX_COLS]
    shown = [{c.key: r.get(c.key) for c in columns} for r in rows[:MAX_ROWS]]
    return columns, shown, len(rows)


def _figures_table(blob: dict[str, Any]) -> tuple[list[Column], list[dict[str, Any]], int]:
    """A report with no row list as one figure per row: where it came from, and the value.

    Nested one level, because every figure report here groups its numbers (`global`,
    `agreement`, `mapQuality`) and the group is half of what the figure means.
    """
    rows: list[dict[str, Any]] = []
    for key, value in blob.items():
        if key in PROSE_KEYS:
            continue
        if _scalar(value):
            rows.append({"figure": key, "value": value, "of": ""})
        elif isinstance(value, dict):
            for inner, number in value.items():
                if inner in PROSE_KEYS or not _scalar(number):
                    continue
                rows.append({"figure": inner, "value": number, "of": key})
    columns = [
        Column("figure", "figure", "text", width="minmax(7rem, 1.4fr)"),
        Column("of", "block", "chip", width="minmax(4rem, 0.7fr)"),
        Column("value", "value", "num", digits=None, width="6rem"),
    ]
    # `value` holds every figure in the report, so one shared column cannot be given a
    # digit count — a count of species and a cosine are both in it. Each cell prints as
    # it is stored, which is what the report itself chose.
    return columns, rows[:MAX_ROWS], len(rows)


def _headline(blob: dict[str, Any]) -> str | None:
    """The report's own statement of what it measured, if it carries one."""
    for key in PROSE_KEYS:
        value = blob.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in blob.values():
        if isinstance(value, dict):
            for key in PROSE_KEYS:
                inner = value.get(key)
                if isinstance(inner, str) and inner.strip():
                    return inner.strip()
    return None


def table_of(blob: Any) -> tuple[list[Column], list[dict[str, Any]], int, str | None]:
    if not isinstance(blob, dict):
        if isinstance(blob, list) and blob and isinstance(blob[0], dict):
            columns, rows, total = _rows_table(blob)
            return columns, rows, total, None
        raise Refused("this report is not an object or a list of rows")
    for key in ROW_KEYS:
        value = blob.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            columns, rows, total = _rows_table(value)
            return columns, rows, total, _headline(blob)
    columns, rows, total = _figures_table(blob)
    return columns, rows, total, _headline(blob)


def read_report(verb: Verb, ctx: Ctx) -> dict[str, Any]:
    """One verb's report as a bounded table, or an honest absence.

    Read from disk on every request rather than remembered from a job, so a measurement
    taken last week is on screen the moment the page opens. A process that only showed
    what it had itself run would draw an empty table over a report sitting on disk, and
    empty reads as "never measured".
    """
    out: dict[str, Any] = {"verb": verb.id, "exists": False, "path": None}
    if not verb.has_report:
        return out
    path = verb.report_at(ctx) if verb.report_at else ctx.report_for(verb.id)
    out["path"] = ctx.rel(path)
    if not path.exists():
        return out
    out["exists"] = True
    try:
        out["ranAt"] = (
            datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            .isoformat(timespec="seconds")
        )
    except OSError:
        out["ranAt"] = None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        columns, rows, total, headline = table_of(blob)
    except Exception as exc:  # noqa: BLE001 - one bad report must not blank the others
        # Worth saying out loud: the alternative is an empty table, which cannot be told
        # apart from a verb that has never run.
        out["headline"] = f"{path.name} is on disk but this build cannot read it ({exc})"
        return out
    out["headline"] = headline
    out["table"] = {
        "columns": [c.to_dict() for c in columns],
        "rows": rows,
        "path": ctx.rel(path),
    }
    if total > len(rows):
        out["table"]["truncated"] = {"shown": len(rows), "total": total}
    return out


def to_dict(verb: Verb, ctx: Ctx) -> dict[str, Any]:
    return {
        "id": verb.id,
        "command": " ".join(verb.argv),
        "title": verb.title,
        "group": verb.group,
        "measures": verb.measures,
        "writes": verb.writes,
        "cost": verb.cost,
        "mutatesStore": verb.mutates_store,
        "params": [p.to_dict() for p in verb.params],
        "needs": unmet(verb, ctx),
        "report": ctx.rel(ctx.report_for(verb.id)) if verb.has_report else None,
    }


# --- preconditions -----------------------------------------------------------------


def _has_torch(_ctx: Ctx) -> bool:
    from importlib.util import find_spec

    return find_spec("torch") is not None


def _has_onnx(_ctx: Ctx) -> bool:
    from importlib.util import find_spec

    return find_spec("onnxruntime") is not None


NEED_TORCH = Need("torch installed (uv sync --extra critic)", _has_torch)
NEED_ONNX = Need("onnxruntime installed (uv sync --extra perch)", _has_onnx)
NEED_STORE = Need(
    "a harvest store with syllables", lambda c: (c.store / "state.json").exists()
)
NEED_TYPING = Need(
    "typing.json in the store — run Fit syllables first",
    lambda c: (c.store / "typing.json").exists(),
)
NEED_EMBEDDINGS = Need(
    "embeddings.f32 in the store — run Embed the store first",
    lambda c: (c.store / "embeddings.f32").exists(),
)
NEED_CRITIC = Need(
    "a trained critic", lambda c: c.critic is not None and c.critic.exists()
)
NEED_LEARNED = Need("a fitted inventory", lambda c: c.learned.exists())
NEED_BUILT = Need(
    "a built galaxy", lambda c: (c.out / "manifest.json").exists()
)
NEED_AUDIO_CACHE = Need(
    "the sanctioned audio cache (out/audio-cache)",
    lambda c: (c.pipeline_out / "audio-cache").is_dir(),
)


# --- shared path builders ----------------------------------------------------------


def _store(ctx: Ctx, _p: dict[str, Any]) -> list[str]:
    return ["--store", str(ctx.store)]


def _store_report(verb_id: str, flag: str = "--json") -> Callable[[Ctx, dict], list[str]]:
    def build(ctx: Ctx, _p: dict[str, Any]) -> list[str]:
        return ["--store", str(ctx.store), flag, str(ctx.report_for(verb_id))]

    return build


# --- the registry ------------------------------------------------------------------
#
# Four groups, and the axis is what a press *changes* rather than what it is about. That
# is the only distinction on this page a reader cannot undo by pressing something else,
# so it is the one the layout should carry.

VERBS: tuple[Verb, ...] = (
    # --- train: writes a model under pipeline/out, never an asset -------------------
    Verb(
        id="critic-train",
        argv=("critic", "train"),
        title="Train the critic",
        group="train",
        measures=(
            "Whether a network can tell this pipeline's renders from real recordings — "
            "and, when it can, gives the fit a better idea of what a syllable type is."
        ),
        writes="out/critic.pt and out/critic-novelty.json. No asset changes.",
        cost="minutes on a GPU, longer on the CPU",
        has_report=True,
        # `cmd_critic` already writes its training report beside the weights, and has since
        # before this registry existed. Reading that is better than adding a second flag
        # that would write the same AUC and accuracies again under another name.
        report_at=lambda c: c.pipeline_out / "critic.json",
        needs=(NEED_TORCH, NEED_STORE, NEED_LEARNED),
        params=(
            Param("epochs", "--epochs", "int", 60, "Epochs", "Passes over the patches.",
                  lo=1, hi=400, step=1),
            Param("holdoutSpecies", "--holdout-species", "float", 0.25, "Species held out",
                  "Share of species kept out of training entirely, so the realism AUC is "
                  "measured on birds the network has never seen.",
                  lo=0.0, hi=0.6, step=0.05),
            Param("cpu", "--cpu", "bool", False, "On the CPU",
                  "Train on the CPU even where a GPU is available."),
            Param("batch", "--batch", "int", 256, "Batch", "Minibatch size.",
                  lo=16, hi=1024, step=16, advanced=True),
            Param("lr", "--lr", "float", 0.002, "Learning rate", "Adam step size.",
                  lo=0.00001, hi=0.05, step=0.0001, advanced=True),
            Param("falsePositive", "--false-positive", "float", 0.05,
                  "Novelty false positives",
                  "The false-positive rate the unheard-syllable threshold is calibrated "
                  "to. It is chosen, not discovered.",
                  lo=0.01, hi=0.25, step=0.01, advanced=True),
            Param("seed", "--seed", "int", 0, "Seed", "RNG seed.",
                  lo=0, hi=9999, step=1, advanced=True),
        ),
        paths=lambda c, _p: [
            "--store", str(c.store), "--inventory", str(c.learned),
            "--calibration-dir", str(c.out),
        ],
    ),
    Verb(
        id="critic-embed",
        argv=("critic", "embed"),
        title="Embed the store",
        group="train",
        measures=(
            "Nothing on its own — it writes the 32-d vector for every stored syllable, "
            "which is the space the better galaxy, the relations and the unheard-syllable "
            "detector are all built in."
        ),
        writes=(
            "embeddings.f32 and embeddings.json inside the harvest store, replacing any "
            "previous ones."
        ),
        cost="one forward pass over every stored syllable",
        mutates_store=True,
        has_report=True,
        # The sidecar `write_store_embeddings` already writes beside the matrix. It is
        # provenance rather than a measurement — how many rows, which critic, its sha256 —
        # and that is exactly the question worth being able to answer from here: whether the
        # store's embeddings are the ones the critic on disk would produce.
        report_at=lambda c: c.store / "embeddings.json",
        needs=(NEED_TORCH, NEED_STORE, NEED_CRITIC),
        params=(
            Param("cpu", "--cpu", "bool", False, "On the CPU",
                  "Embed on the CPU even where a GPU is available."),
            Param("batch", "--batch", "int", 512, "Batch", "Embedding batch size.",
                  lo=32, hi=2048, step=32, advanced=True),
        ),
        paths=lambda c, _p: [
            "--store", str(c.store),
            *(["--critic", str(c.critic)] if c.critic else []),
        ],
    ),
    Verb(
        id="inverse",
        argv=("inverse",),
        title="Train the inverse encoder",
        group="train",
        measures=(
            "Whether a network can read a mel patch back into syrinx parameters. The fit "
            "then starts its search from that guess as well as from the cluster median, "
            "and keeps whichever lands better."
        ),
        writes="out/inverse.pt. No asset changes.",
        cost="about 3–4 minutes to generate 150 000 pairs, then training",
        has_report=True,
        # Same as the critic: `inverse.json` is written next to the encoder and carries the
        # config and the validation report already.
        report_at=lambda c: c.pipeline_out / "inverse.json",
        needs=(NEED_TORCH,),
        params=(
            Param("pairs", "--pairs", "int", 150000, "Training pairs",
                  "Render/patch pairs generated and thrown away. They are free: we own "
                  "the forward model, so every pair is perfectly labelled.",
                  lo=1000, hi=400000, step=1000),
            Param("epochs", "--epochs", "int", 80, "Epochs", "Passes over the pairs.",
                  lo=1, hi=400, step=1),
            Param("cpu", "--cpu", "bool", False, "On the CPU",
                  "Train on the CPU even where a GPU is available."),
            Param("seed", "--seed", "int", 0, "Seed", "RNG seed.",
                  lo=0, hi=9999, step=1, advanced=True),
        ),
        paths=lambda c, _p: [
            "--inventory", str(c.learned),
            "--calibration-dir", str(c.pipeline_out),
            "--out", str(c.pipeline_out / "inverse.pt"),
        ],
    ),
    # --- improve: writes a candidate inventory beside the fitted one ----------------
    Verb(
        id="respfit",
        argv=("respfit",),
        title="Fit breathing and the second voice",
        group="improve",
        measures=(
            "Whether giving each type an air-sac pressure gesture, or a second voice, "
            "beats its current resynthesis — and ships the change only on the types where "
            "it does, by a pre-registered margin."
        ),
        writes=(
            "a new inventory beside the fitted one (…​.respfit.json). The shipped "
            "inventory is untouched, and nothing sings differently until you build from it."
        ),
        cost="the slowest of these — a grid search per type, per species",
        has_report=True,
        needs=(NEED_STORE, NEED_TYPING, NEED_LEARNED),
        params=(
            Param("jobs", "--jobs", "int", 1, "Worker processes",
                  "Forks a pool over species. Identical results, all cores; Linux only.",
                  lo=1, hi=32, step=1),
            Param("margin", "--margin", "float", 0.02, "Ship margin",
                  "How much better a candidate must be before it ships. Pre-registered "
                  "in respfit.py — lowering it is changing the gate after seeing the data.",
                  lo=0.0, hi=0.2, step=0.005),
            Param("noRespiration", "--no-respiration", "bool", False, "Skip breathing",
                  "Leave the respiratory arm out and fit the second voice only.",
                  advanced=True),
            Param("noTwoVoice", "--no-two-voice", "bool", False, "Skip the second voice",
                  "Leave the two-voice arm out and fit breathing only.", advanced=True),
        ),
        paths=lambda c, _p: [
            "--store", str(c.store), "--inventory", str(c.learned),
            "--calibration-dir", str(c.out),
            "--report", str(c.report_for("respfit")),
        ],
    ),
    Verb(
        id="docrefit",
        argv=("docrefit",),
        title="Give documented calls a real texture",
        group="improve",
        measures=(
            "Whether an authored pure-tone call sounds more like the recording once it "
            "borrows the noise and roughness of its nearest learned type — shipped only "
            "where it beats the authored render."
        ),
        writes=(
            "a new inventory beside the fitted one (…​.docrefit.json). The shipped "
            "inventory is untouched."
        ),
        cost="faster than the breathing fit — the authored calls only",
        has_report=True,
        needs=(NEED_STORE, NEED_TYPING, NEED_LEARNED),
        params=(
            Param("margin", "--margin", "float", 0.02, "Ship margin",
                  "How much better the re-fit must be than the authored render.",
                  lo=0.0, hi=0.2, step=0.005),
            Param("f0Cap", "--f0-cap", "float", 0.5, "Pitch gap cap",
                  "Furthest, in octaves, a learned type may be from the call it lends its "
                  "texture to.",
                  lo=0.1, hi=2.0, step=0.1, advanced=True),
        ),
        paths=lambda c, _p: [
            "--store", str(c.store), "--inventory", str(c.learned),
            "--calibration-dir", str(c.out),
            "--report", str(c.report_for("docrefit")),
        ],
    ),
    # --- measure: writes a report and nothing else ----------------------------------
    Verb(
        id="placement",
        argv=("placement",),
        title="Score the fit",
        group="measure",
        measures=(
            "Whether a fitted syllable's resynthesis lands nearest its own species and its "
            "own type — the guardrail the median cosine cannot give you, because a tidy "
            "clustering and a correct one are different things."
        ),
        writes="",
        cost="renders every learned type once, so it scales with the inventory",
        has_report=True,
        needs=(NEED_STORE, NEED_LEARNED),
        params=(
            Param("perSpecies", "--per-species", "bool", False, "Break down by species",
                  "Also report the two placement figures species by species."),
        ),
        paths=lambda c, _p: [
            "--store", str(c.store), "--inventory", str(c.learned),
            "--calibration-dir", str(c.out),
            "--json", str(c.report_for("placement")),
        ],
    ),
    Verb(
        id="specbench",
        argv=("specbench",),
        title="Is a cosine gain an audible gain",
        group="measure",
        measures=(
            "Whether the resynthesis cosine this project quotes tracks audible distortion "
            "at all. It correlates the cosine against MCD and spectral error on cached "
            "audio; docs/19 measured that correlation at about 0.1, which is the reason "
            "the cosine is never called fidelity."
        ),
        writes="",
        cost="renders and decodes one recording per benched type",
        has_report=True,
        needs=(NEED_STORE, NEED_TYPING, NEED_LEARNED, NEED_AUDIO_CACHE),
        params=(
            Param("limit", "--limit", "int", 200, "Types benched",
                  "How many fitted types to bench. The full inventory is thousands.",
                  lo=10, hi=4000, step=10),
            Param("bandCapHz", "--band-cap-hz", "float", 11025.0, "Band cap",
                  "Hold every row's comparison to this band, so a 48 kHz recording and a "
                  "22 kHz one are scored over the same spectrum.",
                  lo=4000.0, hi=24000.0, step=1025.0, advanced=True),
            Param("noBandCap", "--no-band-cap", "bool", False, "No band cap",
                  "Band each row at its own Nyquist instead. Reproduces the older figures "
                  "and makes rows of different sample rates incomparable.",
                  advanced=True),
        ),
        paths=lambda c, _p: [
            "--store", str(c.store), "--inventory", str(c.learned),
            "--audio-cache", str(c.pipeline_out / "audio-cache"),
            "--calibration-dir", str(c.out),
            "--out", str(c.report_for("specbench")),
        ],
    ),
    Verb(
        id="spacemap",
        argv=("spacemap",),
        title="Grade the browser's space map",
        group="measure",
        measures=(
            "Whether the 28-d → 32-d map the browser uses to place a live sound actually "
            "reproduces the critic's own embedding, graded on recordings held out of the "
            "fit. It reports accepted or not, and a below-gate map is the honest answer "
            "rather than a failure."
        ),
        writes="",
        cost="a ridge fit — fast, and no galaxy is rebuilt",
        has_report=True,
        needs=(NEED_STORE, NEED_EMBEDDINGS),
        params=(
            Param("seed", "--seed", "int", 0, "Split seed",
                  "Seed for the recording-level split.", lo=0, hi=9999, step=1),
        ),
        paths=_store_report("spacemap", "--out"),
    ),
    Verb(
        id="relations",
        argv=("relations",),
        title="Which birds share a call",
        group="measure",
        measures=(
            "Which species hold syllable types close enough together to be called shared, "
            "and how far apart any two repertoires are in the critic's space."
        ),
        writes=(
            "its own report only. The galaxy's shipped relations.json is a trimmed, "
            "separate asset that a build writes; this does not touch it."
        ),
        cost="minutes",
        has_report=True,
        needs=(NEED_STORE, NEED_TYPING, NEED_EMBEDDINGS),
        params=(),
        paths=lambda c, _p: [
            "--store", str(c.store), "--inventory", str(c.learned),
            "--out", str(c.report_for("relations")),
        ],
    ),
    Verb(
        id="syntax",
        argv=("syntax",),
        title="Which grammar predicts a bout",
        group="measure",
        measures=(
            "Whether the shipped first-order grammar beats a repeat-count model and a "
            "hidden Markov model at predicting held-out bouts. The win rule is "
            "pre-registered in syntax.py, and a win here installs nothing."
        ),
        writes="",
        cost="a Baum-Welch sweep over every qualifying species",
        has_report=True,
        needs=(NEED_STORE, NEED_TYPING),
        params=(
            Param("ks", "--ks", "text", "4,8,16", "HMM states",
                  "State counts to sweep, comma separated.",
                  pattern=r"[0-9]{1,3}(,[0-9]{1,3}){0,5}"),
            Param("minBouts", "--min-bouts", "int", 20, "Fewest bouts",
                  "How many bouts a species needs before it is scored at all.",
                  lo=2, hi=200, step=1),
            Param("compareBackoff", "--compare-backoff", "bool", False,
                  "Compare smoothing instead",
                  "Run the smoothing-repair comparison rather than the bake-off. It writes "
                  "a differently shaped report.",
                  advanced=True),
            Param("alpha", "--alpha", "float", 0.1, "Smoothing",
                  "Add-alpha strength on the transition counts.",
                  lo=0.0, hi=2.0, step=0.05, advanced=True),
        ),
        paths=_store_report("syntax", "--json"),
    ),
    Verb(
        id="songspace",
        argv=("songspace",),
        title="Do whole songs form a space",
        group="measure",
        measures=(
            "Whether whole bouts, compared by edit distance and rhythm, cluster by species "
            "better than a bag of syllable types does — against a permutation null."
        ),
        writes="",
        cost="quadratic in the number of bouts, and the heaviest of these",
        has_report=True,
        needs=(NEED_STORE, NEED_TYPING),
        params=(
            Param("rhythmWeight", "--rhythm-weight", "float", 1.0, "Rhythm weight",
                  "What one nat of log-gap difference costs against one edit. 0 ablates "
                  "rhythm entirely, which is the comparison worth making.",
                  lo=0.0, hi=4.0, step=0.1),
        ),
        paths=_store_report("songspace", "--json"),
    ),
    Verb(
        id="critic-groupings",
        argv=("critic", "groupings"),
        title="Does the embedding group anything",
        group="measure",
        measures=(
            "Whether the critic's embedding separates species and types better than "
            "chance, against a permutation null — answered from the embeddings alone, "
            "without rendering or rebuilding a galaxy."
        ),
        writes="",
        cost="the embedding pass and nothing else",
        has_report=True,
        needs=(NEED_STORE, NEED_EMBEDDINGS),
        params=(
            Param("seed", "--seed", "int", 0, "Null seed",
                  "Seed for the permutation null.", lo=0, hi=9999, step=1),
        ),
        paths=_store_report("critic-groupings", "--json"),
    ),
    # --- check: reads the shipped assets, and two of them can rewrite one -----------
    Verb(
        id="verify",
        argv=("verify",),
        title="Check the shipped assets",
        group="check",
        measures=(
            "Whether the assets the app loads are internally consistent: the manifest "
            "against the files, the points against their positions, the centroids against "
            "their clusters. It is the check a build ends with."
        ),
        writes="",
        cost="seconds",
        has_report=True,
        needs=(NEED_BUILT,),
        params=(),
        paths=lambda c, _p: [
            "--out", str(c.out), "--json", str(c.report_for("verify")),
        ],
    ),
    Verb(
        id="thresholds",
        argv=("thresholds",),
        title="Measure the match ramp",
        group="check",
        measures=(
            "How close a real field syllable actually lands to the nearest shipped knot, "
            "as a percentile ramp — which is what decides when the app says a live sound "
            "matches something and when it says it matches nothing."
        ),
        writes=(
            "nothing, unless you tick Write it in — which replaces matchRamp inside the "
            "shipped manifest.json."
        ),
        cost="seconds",
        has_report=True,
        needs=(NEED_BUILT,),
        params=(
            Param("write", "--write", "bool", False, "Write it in",
                  "Write the measured ramp into the shipped manifest.json. Without this "
                  "the measurement is reported and nothing changes."),
            Param("sample", "--sample", "int", 2000, "Syllables scored",
                  "How many field syllables to score against the shipped centroids.",
                  lo=100, hi=20000, step=100),
            Param("seed", "--seed", "int", 0, "Seed", "Sampling seed.",
                  lo=0, hi=9999, step=1, advanced=True),
        ),
        paths=lambda c, _p: [
            "--out", str(c.out), "--store", str(c.store),
            "--json", str(c.report_for("thresholds")),
        ],
    ),
    Verb(
        id="calibrate",
        argv=("calibrate",),
        title="Re-measure the pitch table",
        group="check",
        measures=(
            "The relation between the syrinx model's tension parameter and the pitch it "
            "actually produces, swept and tabulated, with the share of steps that came out "
            "monotonic."
        ),
        writes=(
            "the shipped syrinx-calibration.json. Deterministic — a re-run on the same "
            "code produces the same table."
        ),
        cost="tens of seconds",
        params=(
            Param("betaMin", "--beta-min", "float", 0.15, "Tension floor",
                  "The clamp on the tension parameter. Lowering it unlocks sub-kHz pitches "
                  "and leaves the shipped contract — the browser then has to read the "
                  "clamp from the table.",
                  lo=-0.45, hi=1.0, step=0.05, advanced=True),
        ),
        paths=lambda c, _p: ["--out", str(c.out)],
    ),
    Verb(
        id="quality-remeasure",
        argv=("quality", "remeasure"),
        title="Re-measure the stored recordings",
        group="check",
        measures=(
            "Whether this build's segmentation still reproduces the numbers the store was "
            "harvested with, and fills in the quality fields that are missing. A drifted "
            "row means the arithmetic has moved since the harvest."
        ),
        writes=(
            "syllables.jsonl inside the harvest store, rewritten line for line — via a "
            "temporary file, so an interrupt leaves the original intact. Tick Dry run to "
            "measure and write nothing."
        ),
        cost="two passes over the store plus one decode per recording — a long run",
        mutates_store=True,
        needs=(NEED_STORE, NEED_AUDIO_CACHE),
        params=(
            Param("dryRun", "--dry-run", "bool", True, "Dry run",
                  "Measure and report, writing nothing. On by default here, because the "
                  "alternative rewrites the production store."),
        ),
        paths=lambda c, _p: [
            "--store", str(c.store),
            "--audio-cache", str(c.pipeline_out / "audio-cache"),
        ],
    ),
    # --- corpus: changes what the pipeline holds ------------------------------------
    Verb(
        id="sources-list",
        argv=("sources", "list"),
        title="Which audio sources are reachable",
        group="corpus",
        measures=(
            "Which of the open datasets and archives this machine can actually fetch from, "
            "and for each one it cannot, why. An unfilled key is a skip, never an error."
        ),
        writes="",
        cost="instant, and no network",
        params=(),
    ),
    Verb(
        id="sources-fetch",
        argv=("sources", "fetch"),
        title="Fetch from an open dataset",
        group="corpus",
        measures=(
            "Nothing — it collects. Recordings are staged, described and deleted, and only "
            "the measurements enter the store."
        ),
        writes=(
            "the harvest store: new rows in syllables.jsonl, patches.f16, descriptors.f32 "
            "and state.json, with eviction once the caps are reached. It does not rewrite "
            "embeddings.f32, so the store's embeddings are stale afterwards until you run "
            "Embed the store again."
        ),
        cost="network-bound; inat-sounds streams an 81 GB archive and costs a quarter hour",
        mutates_store=True,
        needs=(NEED_STORE,),
        params=(
            Param("source", "--source", "choice", "zenodo", "Source",
                  "Which archive to fetch from.",
                  choices=(
                      ("zenodo", "Zenodo"),
                      ("internet-archive", "Internet Archive"),
                      ("kaggle", "Kaggle"),
                      ("huggingface", "Hugging Face"),
                      ("inat-sounds", "iNaturalist sounds"),
                      ("gbif", "GBIF"),
                      ("xeno-canto", "xeno-canto"),
                  ), required=True),
            Param("limit", "--limit", "int", 5, "Recordings",
                  "How many recordings to fetch.", lo=1, hi=500, step=1),
            Param("species", "--species", "text", "", "One species",
                  "A species id, or blank for the source's own selection.",
                  pattern=r"[a-z][a-z0-9_]{2,48}"),
            Param("maxSeconds", "--max-seconds", "float", 90.0, "Analysed per recording",
                  "How much of each recording is analysed.",
                  lo=15.0, hi=300.0, step=15.0, advanced=True),
        ),
        paths=lambda c, _p: ["--store", str(c.store)],
    ),
    Verb(
        id="subset",
        argv=("subset",),
        title="Cut a small store to work against",
        group="corpus",
        measures=(
            "Nothing — it copies a slice of the corpus into its own store, so the whole "
            "cycle can be proved in minutes instead of hours. The source store is never "
            "written to."
        ),
        writes="a new store under out/, named after what you type. Never the source.",
        cost="minutes at most",
        has_report=True,
        needs=(NEED_STORE,),
        params=(
            Param("name", "--out", "text", "small", "Call it",
                  "The new store's name. It lands at out/store-<name>, so it cannot "
                  "overwrite the one it is cut from.",
                  pattern=r"[a-z0-9][a-z0-9-]{0,30}"),
            Param("species", "--species", "int", 100, "Species kept",
                  "How many species the subset holds.", lo=2, hi=2000, step=1),
            Param("diverse", "--diverse", "bool", False, "Spread them out",
                  "Pick species that cover the corpus rather than the biggest ones."),
        ),
        # `--out` is the one path a caller names, so it is built here from the slug rather
        # than passed through: `store-` prefixed and confined to `out/`, which is what
        # makes it impossible to aim at the source store or at a shipped asset.
        paths=lambda c, p: [
            "--store", str(c.store),
            "--out", str(c.pipeline_out / f"store-{p.get('name') or 'small'}"),
            "--json", str(c.report_for("subset")),
        ],
    ),
    Verb(
        id="critic-label-novel",
        argv=("critic", "label-novel"),
        title="Ask Perch what the unheard ones are",
        group="corpus",
        measures=(
            "What an outside classifier calls the syllables our own detector flagged as "
            "unlike everything known. The labels are metadata and never typing ground "
            "truth — another model's guess is not an identification."
        ),
        writes=(
            "perch-labels.jsonl inside the store, and caches Perch's weights under "
            "out/perch on first use — a 409 MB download."
        ),
        cost="a 409 MB download the first time, then inference over the flagged syllables",
        mutates_store=True,
        needs=(NEED_ONNX, NEED_STORE, NEED_EMBEDDINGS),
        params=(
            Param("limit", "--limit", "int", 50, "How many",
                  "Label at most this many flagged syllables.",
                  lo=1, hi=5000, step=10),
            Param("keepEmbeddings", "--keep-embeddings", "bool", False,
                  "Keep Perch's vectors",
                  "Also store Perch's own 1536-d vector per row, at about 10 KB each.",
                  advanced=True),
        ),
        paths=lambda c, _p: [
            "--store", str(c.store),
            "--audio-cache", str(c.pipeline_out / "audio-cache"),
            *(["--critic", str(c.critic)] if c.critic else []),
            "--model-dir", str(c.pipeline_out / "perch"),
        ],
    ),
)

BY_ID: dict[str, Verb] = {v.id: v for v in VERBS}

#: The order the page draws the groups in, and a line for each saying what a press in it
#: changes. Ordered by how far a press reaches: a measurement changes nothing, a check can
#: rewrite one asset field, a corpus verb changes what everything downstream is fitted to.
GROUPS: tuple[tuple[str, str, str], ...] = (
    ("measure", "Measure", "Runs a measurement and writes a report. Changes nothing else."),
    ("train", "Train", "Writes a model under out/. Nothing sings differently until you fit again."),
    ("improve", "Improve the voices",
     "Writes a candidate inventory beside the fitted one. Nothing sings differently until "
     "you build from it."),
    ("check", "Check what shipped",
     "Reads the assets the app is loading. Two of these can rewrite one, and say so."),
    ("corpus", "Change the corpus",
     "Changes what the pipeline holds, which is what everything downstream is fitted to."),
)


def self_test(verbose: bool = True) -> None:
    """Prove the registry is coherent and that coercion actually refuses things.

    Cheap, and it checks the properties that would otherwise fail silently: a verb whose
    `paths` raises, a text parameter with no declared shape, a duplicate id, and — the one
    that matters — that an undeclared parameter is refused rather than dropped.
    """
    ctx = Ctx(
        store=Path("/tmp/store"),
        out=Path("/tmp/out"),
        learned=Path("/tmp/learned.json"),
        inventory=Path("/tmp/inventory.json"),
        critic=Path("/tmp/critic.pt"),
        pipeline_root=Path("/tmp/pipeline"),
    )
    assert len(BY_ID) == len(VERBS), "two verbs share an id"
    known_groups = {g for g, _, _ in GROUPS}
    for verb in VERBS:
        assert verb.group in known_groups, f"{verb.id} is in no drawn group: {verb.group}"
        assert verb.measures, f"{verb.id} does not say what it measures"
        names = [p.name for p in verb.params]
        assert len(names) == len(set(names)), f"{verb.id} declares a parameter twice"
        for param in verb.params:
            assert param.kind in ("int", "float", "bool", "choice", "text"), param.kind
            if param.kind == "text":
                assert param.pattern, f"{verb.id}.{param.name} declares no shape"
                if param.default:
                    assert re.fullmatch(param.pattern, str(param.default)), (
                        f"{verb.id}.{param.name}'s own default does not match its shape"
                    )
            if param.kind == "choice":
                assert param.choices, f"{verb.id}.{param.name} offers no choices"
                assert param.default in {v for v, _ in param.choices}
        # The defaults must build an argv, which is what the page's first press sends.
        argv = build_argv(verb, ctx, {})
        assert argv[: len(verb.argv)] == list(verb.argv), verb.id
        # A default-valued parameter is left off the command line — except a `store_true`
        # whose default is on, which has to be emitted to *hold* it on. `quality
        # remeasure`'s dry run is the one of those, and it defaults on precisely because
        # the alternative rewrites the production store.
        for param in verb.params:
            if (param.kind == "bool" and param.default) or param.required:
                assert param.flag in argv, (
                    f"{verb.id} dropped {param.flag}, which must always be passed"
                )
                continue
            assert param.flag not in argv or param.flag in verb.paths(ctx, {}), (
                f"{verb.id} put {param.flag} on the line at its default value"
            )
        unmet(verb, ctx)  # every check must be callable without raising

    # Refusal, which is the property the whole registry rests on.
    verb = BY_ID["specbench"]
    for bad in ({"nope": 1}, {"limit": "banana"}, {"limit": float("nan")}):
        try:
            build_argv(verb, ctx, bad)  # type: ignore[arg-type]
        except Refused:
            pass
        else:  # pragma: no cover - a failure here is the security property gone
            raise AssertionError(f"specbench accepted {bad!r}")
    # Clamping, in both directions.
    assert coerce(next(p for p in verb.params if p.name == "limit"), 99999) == 4000
    assert coerce(next(p for p in verb.params if p.name == "limit"), -5) == 10
    # A text parameter's shape, and that a flag-like value cannot pass through it.
    ks = next(p for p in BY_ID["syntax"].params if p.name == "ks")
    assert coerce(ks, "4,8") == "4,8"
    for bad_text in ("--out", "4;rm -rf /", "4,8,", ""):
        try:
            coerce(ks, bad_text)
        except Refused:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"syntax --ks accepted {bad_text!r}")
    # A bool never reaches the line as a word, in either state.
    dry = BY_ID["quality-remeasure"]
    assert "--dry-run" not in build_argv(dry, ctx, {"dryRun": False})
    assert "--dry-run" in build_argv(dry, ctx, {"dryRun": True})
    # The subset slug cannot escape out/, which is the one caller-named path here.
    sub = build_argv(BY_ID["subset"], ctx, {"name": "tiny"})
    assert str(ctx.pipeline_out / "store-tiny") in sub, sub

    # Both report shapes reduce to a table. These are the two archetypes in the tree:
    # a row report (`out/respfit-gan-report.json`) and a figure report
    # (`analysis/v10_unknown_join.json`).
    columns, rows, total, _ = table_of(
        {"records": [{"speciesId": "a", "before": 0.5, "after": 0.7} for _ in range(60)]}
    )
    assert total == 60 and len(rows) == MAX_ROWS, (total, len(rows))
    assert columns[0].kind == "text" and any(c.kind == "num" for c in columns)
    columns, rows, _, headline = table_of(
        {"agreement": {"adjustedRand": 0.0001, "definition": "what it means"},
         "unassignedShare": 0.7953}
    )
    assert headline == "what it means"
    assert {r["figure"] for r in rows} == {"adjustedRand", "unassignedShare"}
    # A named share prints as a percentage and a cosine does not, which is the distinction
    # that stops a unit being invented.
    assert _column_for("noiseShare", [0.79]).kind == "pct"
    assert _column_for("cosine", [0.79]).kind == "num"

    # --- the check the whole registry rests on: every argv it builds must parse --------
    #
    # This is the one that would otherwise rot. A flag renamed in `cli.py` leaves this
    # file describing a command line that no longer exists, and the symptom is a job that
    # exits 2 with argparse's usage text in the log — long after the form has been drawn,
    # the tooltip written and the number quoted. Parsing is cheap and it runs nothing, so
    # both ends of every verb's range are checked: all defaults, and every parameter moved
    # off its default so each declared flag actually reaches the parser.
    #
    # `cli` is imported here rather than at module scope because it pulls in the whole
    # pipeline and `verbs` is imported by the server at startup.
    import contextlib
    import io

    from .cli import build_parser

    parser = build_parser()
    for verb in VERBS:
        moved: dict[str, Any] = {}
        for param in verb.params:
            if param.kind == "bool":
                moved[param.name] = not param.default
            elif param.kind == "int":
                moved[param.name] = int((param.lo or 0) + 1)
            elif param.kind == "float":
                moved[param.name] = float(param.lo or 0) + 0.01
            elif param.kind == "choice":
                moved[param.name] = param.choices[-1][0]
            elif param.kind == "text":
                moved[param.name] = param.default or "aaa"
        for label, params in (("defaults", {}), ("every flag set", moved)):
            argv = build_argv(verb, ctx, params)
            try:
                # argparse writes to stderr and exits rather than raising, and this runs
                # inside a server start.
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    parsed = parser.parse_args(argv)
            except SystemExit as exit_code:
                raise AssertionError(
                    f"{verb.id} ({label}) builds an argv the CLI refuses: "
                    f"{' '.join(argv)} — {err.getvalue().strip()}"
                ) from exit_code
            assert hasattr(parsed, "func"), f"{verb.id} ({label}) binds no command"

    if verbose:
        print(
            f"verbs self-test: {len(VERBS)} verbs in {len(GROUPS)} groups, "
            f"{2 * len(VERBS)} argvs parse, coercion refuses"
        )
