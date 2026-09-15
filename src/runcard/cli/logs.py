"""The ``runcard logs`` subcommand: inspect structured logs from Hydra runs.

Three commands, all operating on a run directory (identified by its
``.hydra/`` subdirectory) or directly on a ``.log`` file:

* ``list``: every run under ``outputs/`` and ``runs/``, with its overrides.
* ``show``: events from one run, filtered by ``--event`` or ``--level``.
* ``tail``: the last *N* events from one run.

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
import sys
from pathlib import Path

import orjson
import typer
from rich.console import Console
from rich.table import Table

from runcard._logging import RUN_CONTEXT_KEYS, render_console_line

_DEFAULT_ROOTS = ("outputs", "runs")
_COMPLETION_ROOTS = (*_DEFAULT_ROOTS, "multirun")
_LEVELS = ("debug", "info", "warning", "error", "critical")

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
    """Return the overrides recorded for a run, or ``""``."""
    overrides_file = run / ".hydra" / "overrides.yaml"
    if not overrides_file.exists():
        return ""
    return " ".join(overrides_file.read_text().split())


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
    """List run directories with the overrides that produced them."""
    dirs = _find_run_dirs(roots)
    if not dirs:
        typer.echo("No run directories found.")
        return
    if not sys.stdout.isatty():
        for d in dirs:
            log_count = len(list(d.glob("*.log")))
            overrides = _overrides(d)
            typer.echo(f"{d}  ({log_count} log file(s)){' ' + overrides if overrides else ''}")
        return
    table = Table(box=None, pad_edge=False, header_style="bold")
    table.add_column("Run", style="cyan", no_wrap=True)
    table.add_column("Logs", justify="right", style="dim")
    table.add_column("Overrides", style="yellow")
    for d in dirs:
        table.add_row(str(d), str(len(list(d.glob("*.log")))), _overrides(d))
    Console().print(table)


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
