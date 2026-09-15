"""The ``runcard logs`` subcommand: inspect structured logs from Hydra runs.

Three commands, all operating on a run directory (identified by its
``.hydra/`` subdirectory) or directly on a ``.log`` file:

* ``list``: every run under ``outputs/`` and ``runs/``, with status,
  duration and overrides.
* ``summary``: one screen per run: how it ended, where it ran, event counts,
  and how its most frequent event's numeric fields moved.
* ``show``: events from one run, filtered by ``--event`` or ``--level``.
* ``tail``: the last *N* events from one run.

Status comes from the ``run_finished`` / ``run_failed`` events that
``@experiment`` writes, so it does not depend on what the script logged. A
run with neither is *running* (SLURM says so, or the log changed in the last
few minutes) or *incomplete*.

Output defaults to the console format; ``--json`` and ``--compact`` emit JSON
for ``jq`` or Polars. On a terminal, ``list`` renders a table and JSON is
syntax-highlighted; when piped, output is plain text.

Tab completion (``runcard --install-completion``) offers run directories for
``RUN``, the event names found in that run for ``--event``, and log levels
for ``--level``.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import orjson
import typer
from rich.console import Console
from rich.table import Table

from runcard._logging import RUN_CONTEXT_KEYS, RUNCARD_EVENTS, render_console_line

_DEFAULT_ROOTS = ("outputs", "runs")
_COMPLETION_ROOTS = (*_DEFAULT_ROOTS, "multirun")
_LEVELS = ("debug", "info", "warning", "error", "critical")
_TAIL_BYTES = 64 * 1024
_RUNNING_IF_MODIFIED_WITHIN_S = 10 * 60

logs_app = typer.Typer(help="Inspect structured logs from runs.", no_args_is_help=True)


def _find_run_dirs(roots: list[str] | None = None) -> list[Path]:
    """Find Hydra run directories (identified by a ``.hydra/`` subdirectory)."""
    search_roots = [Path(r) for r in roots] if roots else [Path(r) for r in _DEFAULT_ROOTS]
    dirs: list[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, _ in os.walk(root):
            if ".hydra" in dirnames:
                dirs.append(Path(dirpath))
                dirnames.clear()  # don't descend further
    dirs.sort()
    return dirs


def _overrides(run: Path) -> str:
    """Return the overrides recorded for a run as one line, or ``""``.

    Hydra writes ``.hydra/overrides.yaml`` as a YAML list (``- key=value``
    per line, or ``[]``); the list markers are stripped.
    """
    overrides_file = run / ".hydra" / "overrides.yaml"
    if not overrides_file.exists():
        return ""
    items = []
    for line in overrides_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if line and line != "[]":
            items.append(line)
    return " ".join(items)


def _read_jsonl_events(path: Path) -> list[dict]:
    """Read events from a JSONL file, wrapping non-JSON lines for compatibility."""
    events: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                events.append(orjson.loads(line))
            except (orjson.JSONDecodeError, ValueError):
                events.append({"raw": line})
    return events


def _find_log_files(run: Path) -> list[Path]:
    """Find .log files in a run directory."""
    if run.is_file():
        return [run]
    return sorted(run.glob("*.log"))


def _format_event(event: dict, *, compact: bool = False) -> str:
    """Format a single event as JSON (pretty by default, one line if *compact*)."""
    if compact:
        return json.dumps(event, default=str)
    return json.dumps(event, indent=2, default=str)


def _run_context(events: list[dict]) -> dict:
    """Return the run context (SLURM vars, hostname) from the first event carrying it."""
    for ev in events:
        ctx = {k: ev[k] for k in sorted(RUN_CONTEXT_KEYS) if k in ev}
        if ctx:
            return ctx
    return {}


def _format_human(event: dict, *, colors: bool) -> str:
    """Format a single event as a console line, hiding run-context keys."""
    if "event" not in event:
        return event.get("raw", json.dumps(event, default=str))
    event = {k: v for k, v in event.items() if k not in RUN_CONTEXT_KEYS}
    return render_console_line(event, colors=colors)


def _print_events(events: list[dict], *, fmt: str) -> None:
    """Print events in the requested format: ``human``, ``json`` or ``compact``."""
    if fmt == "human":
        colors = sys.stdout.isatty()
        ctx = _run_context(events)
        if ctx:
            line = "# " + " ".join(f"{k}={v}" for k, v in ctx.items())
            print(f"\x1b[2m{line}\x1b[0m" if colors else line)
        for ev in events:
            print(_format_human(ev, colors=colors))
    elif fmt == "json" and sys.stdout.isatty():
        console = Console()
        for ev in events:
            console.print_json(json.dumps(ev, default=str))
    else:
        for ev in events:
            print(_format_event(ev, compact=fmt == "compact"))


# --- analysis ---------------------------------------------------------------


def _read_tail_events(path: Path, nbytes: int = _TAIL_BYTES) -> list[dict]:
    """Parse the events in the last *nbytes* of a JSONL file without reading it all."""
    size = path.stat().st_size
    with open(path, "rb") as f:
        if size > nbytes:
            f.seek(size - nbytes)
            f.readline()  # drop the partial first line
        chunk = f.read().decode(errors="replace")
    events: list[dict] = []
    for line in chunk.splitlines():
        if not line:
            continue
        try:
            events.append(orjson.loads(line))
        except (orjson.JSONDecodeError, ValueError):
            pass
    return events


def _first_event(path: Path) -> dict | None:
    with open(path) as f:
        for line in f:
            try:
                return orjson.loads(line)
            except (orjson.JSONDecodeError, ValueError):
                continue
    return None


def _parse_ts(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, sec = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _slurm_states(job_ids: list[str]) -> dict[str, str]:
    """Ask ``sacct`` for the state of each job id; empty when sacct is unavailable."""
    if not job_ids or shutil.which("sacct") is None:
        return {}
    try:
        out = subprocess.run(
            ["sacct", "-X", "-n", "-P", "-o", "JobID,State", "-j", ",".join(job_ids)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    states: dict[str, str] = {}
    for line in out.splitlines():
        job, _, state = line.partition("|")
        if job and state:
            states[job.strip()] = state.strip().split()[0]
    return states


def _status(
    first: dict | None,
    tail: list[dict],
    log_path: Path | None,
    slurm_states: dict[str, str] | None = None,
) -> str:
    """Classify a run: finished, finished with N errors, failed, running, or incomplete."""
    names = [ev.get("event") for ev in tail]
    if "run_failed" in names:
        return "failed"
    if "run_finished" in names:
        errors = sum(1 for ev in tail if str(ev.get("level", "")).lower() in ("error", "critical"))
        return f"finished, {errors} error{'s' if errors != 1 else ''}" if errors else "finished"
    job_id = None
    for ev in (first, *tail):
        if ev and ev.get("slurm_job_id"):
            job_id = str(ev["slurm_job_id"])
            break
    if job_id and slurm_states and job_id in slurm_states:
        state = slurm_states[job_id]
        if state in ("RUNNING", "PENDING", "COMPLETING"):
            return "running"
        return "incomplete"
    if log_path is not None:
        try:
            if time.time() - log_path.stat().st_mtime < _RUNNING_IF_MODIFIED_WITHIN_S:
                return "running?"
        except OSError:
            pass
    return "incomplete"


def _numeric_fields(ev: dict) -> dict[str, float]:
    return {
        k: v
        for k, v in ev.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in RUN_CONTEXT_KEYS
    }


_HIDDEN_FIELDS = frozenset({"event", "level", "timestamp", "logger", "exception"})


def _display_fields(ev: dict) -> dict:
    """Numeric and short string fields of an event, for a one-line rendering."""
    out: dict = {}
    for k, v in ev.items():
        if k in _HIDDEN_FIELDS or k in RUN_CONTEXT_KEYS:
            continue
        if isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str):
            first = v.splitlines()[0] if v else ""
            out[k] = first if len(first) <= 60 else first[:57] + "..."
    return out


def _progress(events: list[dict], event_name: str | None) -> dict | None:
    """Most frequent researcher event (or *event_name*) with first->last of its numeric fields."""
    own = [ev for ev in events if ev.get("event") not in RUNCARD_EVENTS and "event" in ev]
    if event_name is None:
        counts = Counter(ev["event"] for ev in own)
        if not counts:
            return None
        event_name = counts.most_common(1)[0][0]
    hits = [ev for ev in own if ev["event"] == event_name]
    if not hits:
        return None
    first, last = _numeric_fields(hits[0]), _numeric_fields(hits[-1])
    return {
        "event": event_name,
        "count": len(hits),
        "fields": {k: [first[k], last[k]] for k in first if k in last},
    }


def _summarize(run: Path, progress_event: str | None = None) -> dict:
    """Build the summary of one run as a plain dict (the source for every output format)."""
    log_files = _find_log_files(run)
    events: list[dict] = []
    for lf in log_files:
        events.extend(_read_jsonl_events(lf))
    ctx = _run_context(events)
    env = next((ev for ev in events if ev.get("event") == "environment"), {})
    stamps = [t for t in (_parse_ts(ev.get("timestamp")) for ev in events) if t]
    started, ended = (stamps[0], stamps[-1]) if stamps else (None, None)
    levels = Counter(str(ev.get("level", "")).lower() for ev in events)
    ended_ev = next(
        (ev for ev in events if ev.get("event") in ("run_finished", "run_failed")), None
    )
    own = [ev for ev in events if ev.get("event") not in RUNCARD_EVENTS and "event" in ev]
    last = own[-1] if own else None
    failure = None
    if ended_ev and ended_ev.get("event") == "run_failed":
        exc = str(ended_ev.get("exception", "")).strip().splitlines()
        failure = exc[-1] if exc else str(ended_ev.get("reason", "unknown"))
    duration = ended_ev.get("elapsed_s") if ended_ev else None
    if duration is None and started and ended:
        duration = (ended - started).total_seconds()
    return {
        "run": str(run),
        "status": _status(
            events[0] if events else None,
            events,
            log_files[-1] if log_files else None,
            _slurm_states([ctx["slurm_job_id"]]) if ctx.get("slurm_job_id") else {},
        ),
        "started": started.isoformat(timespec="seconds") if started else None,
        "ended": ended.isoformat(timespec="seconds") if ended else None,
        "duration_s": round(duration, 3) if duration is not None else None,
        "hostname": ctx.get("hostname") or env.get("hostname"),
        "python_version": env.get("python_version"),
        "slurm": {k[len("slurm_") :]: v for k, v in ctx.items() if k.startswith("slurm_")},
        "overrides": _overrides(run) if run.is_dir() else "",
        "events": {
            "total": len(events),
            "warnings": levels.get("warning", 0),
            "errors": levels.get("error", 0) + levels.get("critical", 0),
        },
        "progress": _progress(events, progress_event),
        "last": {"event": last["event"], "fields": _display_fields(last)} if last else None,
        "failure": failure,
    }


def _fmt_num(v) -> str:
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def _summary_lines(summary: dict) -> list[tuple[str, str]]:
    """The summary as (label, text) rows shared by the terminal and plain renderers."""
    rows: list[tuple[str, str]] = []
    started = summary["started"] or "--"
    rows.append(
        (
            "Started",
            f"{started.replace('T', ' ')}    Duration  {_fmt_duration(summary['duration_s'])}",
        )
    )
    where = [summary["hostname"] or "?"]
    if summary["python_version"]:
        where.append(f"python {summary['python_version']}")
    slurm = summary["slurm"]
    if slurm.get("job_id"):
        nodes = (
            f" on {slurm['nnodes']} node{'s' if slurm['nnodes'] != '1' else ''}"
            if slurm.get("nnodes")
            else ""
        )
        where.append(f"job {slurm['job_id']}{nodes}")
    else:
        where.append("no SLURM job")
    rows.append(("Where", " · ".join(where)))
    rows.append(("Overrides", summary["overrides"] or "(none)"))
    ev = summary["events"]
    warnings = f"{ev['warnings']} warning{'s' if ev['warnings'] != 1 else ''}"
    errors = f"{ev['errors']} error{'s' if ev['errors'] != 1 else ''}"
    rows.append(("Events", f"{ev['total']} · {warnings} · {errors}"))
    prog = summary["progress"]
    if prog:
        moves = " · ".join(
            f"{k} {_fmt_num(a)} → {_fmt_num(b)}" for k, (a, b) in prog["fields"].items()
        )
        rows.append(
            ("Progress", f"{prog['event']} ×{prog['count']}" + (f" · {moves}" if moves else ""))
        )
    last = summary["last"]
    if last:
        fields = " ".join(f"{k}={_fmt_num(v)}" for k, v in last["fields"].items())
        rows.append(("Last", f"{last['event']}  {fields}".rstrip()))
    if summary["failure"]:
        rows.append(("Failure", summary["failure"]))
    return rows


def _status_style(status: str) -> str:
    if status.startswith("finished,"):
        return "yellow"
    return {"finished": "green", "failed": "red", "running": "cyan", "running?": "cyan"}.get(
        status, "dim"
    )


# --- completion -------------------------------------------------------------


def _run_candidates(incomplete: str) -> list[str]:
    """Run directories under the usual roots whose path starts with *incomplete*."""
    return [
        str(d) for d in _find_run_dirs(list(_COMPLETION_ROOTS)) if str(d).startswith(incomplete)
    ]


def _event_candidates(run: str | None, incomplete: str) -> list[str]:
    """Distinct event names in *run*, in first-seen order, starting with *incomplete*."""
    if not run:
        return []
    seen: dict[str, None] = {}
    for lf in _find_log_files(Path(run)):
        try:
            events = _read_jsonl_events(lf)
        except OSError:
            continue
        for ev in events:
            name = ev.get("event")
            if isinstance(name, str) and name.startswith(incomplete):
                seen.setdefault(name, None)
    return list(seen)


def _path_fallback(incomplete: str, *, dirs_only: bool = False) -> list[str]:
    """Directories (and ``.log`` files) matching *incomplete*, for paths outside the roots."""
    matches = glob.glob(incomplete + "*")
    return sorted(p for p in matches if os.path.isdir(p) or (not dirs_only and p.endswith(".log")))


def _complete_run(ctx: typer.Context, args: list[str], incomplete: str) -> list[str]:
    return _run_candidates(incomplete) or _path_fallback(incomplete)


def _complete_event(ctx: typer.Context, args: list[str], incomplete: str) -> list[str]:
    # While completing `--event <TAB>` the parser has not bound RUN yet; it sits
    # in ctx.args as a leftover positional.
    run = ctx.params.get("run") or next((a for a in ctx.args if not a.startswith("-")), None)
    return _event_candidates(run, incomplete)


def _complete_level(ctx: typer.Context, args: list[str], incomplete: str) -> list[str]:
    return [lv for lv in _LEVELS if lv.startswith(incomplete)]


def _complete_dir(ctx: typer.Context, args: list[str], incomplete: str) -> list[str]:
    return _path_fallback(incomplete, dirs_only=True)


# --- commands ---------------------------------------------------------------

_RUN_ARG = typer.Argument(
    ...,
    help="Run directory (one with a .hydra/ subdirectory) or a .log file.",
    autocompletion=_complete_run,
)
_JSON_OPT = typer.Option(False, "--json", help="Pretty-printed JSON, one event per block.")
_COMPACT_OPT = typer.Option(False, "--compact", "-c", help="Compact JSON, one event per line.")


def _output_format(json_: bool, compact: bool) -> str:
    if json_ and compact:
        raise typer.BadParameter("--json and --compact are mutually exclusive")
    if compact:
        return "compact"
    if json_:
        return "json"
    return "human"


def _load_events(run: str) -> list[dict]:
    """Read every event from a run directory or log file, or exit 1 if there are none."""
    log_files = _find_log_files(Path(run))
    if not log_files:
        typer.echo(f"No log files found in {run}", err=True)
        raise typer.Exit(code=1)
    events: list[dict] = []
    for lf in log_files:
        events.extend(_read_jsonl_events(lf))
    return events


@logs_app.command("list")
def list_runs(
    roots: list[str] | None = typer.Option(
        None,
        "--roots",
        help="Root directories to search (default: outputs, runs).",
        autocompletion=_complete_dir,
    ),
) -> None:
    """List run directories with status, duration, and the overrides that produced them.

    When piped, prints one tab-separated line per run: path, status, duration,
    overrides.
    """
    dirs = _find_run_dirs(roots)
    if not dirs:
        typer.echo("No run directories found.")
        return
    rows = [_list_row(d) for d in dirs]
    job_ids = [r["job_id"] for r in rows if r["job_id"]]
    states = _slurm_states(job_ids)
    for r in rows:
        r["status"] = _status(r["first"], r["tail"], r["log"], states)
    if not sys.stdout.isatty():
        for r in rows:
            typer.echo(
                "\t".join([r["run"], r["status"], _fmt_duration(r["duration"]), r["overrides"]])
            )
        return
    table = Table(box=None, pad_edge=False, header_style="bold")
    table.add_column("Run", style="cyan", no_wrap=True)
    table.add_column("Status")
    table.add_column("Duration", justify="right", style="dim")
    table.add_column("Overrides", style="yellow")
    for r in rows:
        table.add_row(
            r["run"],
            f"[{_status_style(r['status'])}]{r['status']}[/]",
            _fmt_duration(r["duration"]),
            r["overrides"],
        )
    Console().print(table)


def _list_row(run: Path) -> dict:
    """Cheap per-run facts for ``list``: reads the first line and the tail of the newest log."""
    log_files = _find_log_files(run)
    first = tail = None
    if log_files:
        first = _first_event(log_files[0])
        tail = _read_tail_events(log_files[-1])
    tail = tail or []
    duration = None
    ended_ev = next((ev for ev in tail if ev.get("event") in ("run_finished", "run_failed")), None)
    if ended_ev and isinstance(ended_ev.get("elapsed_s"), (int, float)):
        duration = float(ended_ev["elapsed_s"])
    else:
        t0 = _parse_ts(first.get("timestamp")) if first else None
        t1 = _parse_ts(tail[-1].get("timestamp")) if tail else None
        if t0 and t1:
            duration = (t1 - t0).total_seconds()
    job_id = None
    for ev in (first, *tail):
        if ev and ev.get("slurm_job_id"):
            job_id = str(ev["slurm_job_id"])
            break
    return {
        "run": str(run),
        "first": first,
        "tail": tail,
        "log": log_files[-1] if log_files else None,
        "duration": duration,
        "job_id": job_id,
        "overrides": _overrides(run),
    }


@logs_app.command("summary")
def summary(
    run: str = _RUN_ARG,
    event: str | None = typer.Option(
        None,
        "--event",
        help="Event to report progress on (default: the most frequent one).",
        autocompletion=_complete_event,
    ),
    json_: bool = typer.Option(False, "--json", help="Emit the summary as JSON."),
) -> None:
    """Summarise one run: how it ended, where it ran, event counts, and progress."""
    path = Path(run)
    if not _find_log_files(path):
        typer.echo(f"No log files found in {run}", err=True)
        raise typer.Exit(code=1)
    data = _summarize(path, event)
    if json_:
        typer.echo(json.dumps(data, indent=2, default=str))
        return
    rows = _summary_lines(data)
    if not sys.stdout.isatty():
        typer.echo(f"{data['run']}  {data['status']}")
        for label, text in rows:
            typer.echo(f"{label}: {text}")
        return
    console = Console()
    console.print(
        f"[bold cyan]{data['run']}[/]  [{_status_style(data['status'])}]{data['status']}[/]"
    )
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", no_wrap=True)
    grid.add_column()
    for label, text in rows:
        grid.add_row(label, text)
    console.print(grid)


@logs_app.command("show")
def show(
    run: str = _RUN_ARG,
    event: str | None = typer.Option(
        None, "--event", help="Only events with this name.", autocompletion=_complete_event
    ),
    level: str | None = typer.Option(
        None, "--level", help="Only events at this level.", autocompletion=_complete_level
    ),
    json_: bool = _JSON_OPT,
    compact: bool = _COMPACT_OPT,
) -> None:
    """Show the events from a run, optionally filtered by event name or level."""
    events = [
        ev
        for ev in _load_events(run)
        if (event is None or ev.get("event") == event)
        and (level is None or ev.get("level", "").upper() == level.upper())
    ]
    _print_events(events, fmt=_output_format(json_, compact))


@logs_app.command("tail")
def tail(
    run: str = _RUN_ARG,
    n: int = typer.Option(10, "-n", "--lines", min=1, help="Number of events."),
    json_: bool = _JSON_OPT,
    compact: bool = _COMPACT_OPT,
) -> None:
    """Show the last N events from a run."""
    events = _load_events(run)
    _print_events(events[-n:], fmt=_output_format(json_, compact))


def logs_main(argv: list[str] | None = None) -> None:
    """Run ``runcard logs`` standalone.

    Args:
        argv: Arguments after ``logs``; ``None`` reads ``sys.argv[1:]``.
    """
    logs_app(args=argv, prog_name="runcard logs")
