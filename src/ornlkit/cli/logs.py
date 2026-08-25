"""``ornlkit logs`` subcommand — inspect structured log files from Hydra runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import orjson

_DEFAULT_ROOTS = ("outputs", "runs")


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
    """Format a single event for display."""
    if compact:
        return json.dumps(event, default=str)
    return json.dumps(event, indent=2, default=str)


def _cmd_list(args: argparse.Namespace) -> None:
    dirs = _find_run_dirs(args.roots)
    if not dirs:
        print("No Hydra run directories found.")
        return
    for d in dirs:
        log_count = len(list(d.glob("*.log")))
        # Read overrides if available
        overrides_file = d / ".hydra" / "overrides.yaml"
        overrides = ""
        if overrides_file.exists():
            overrides = " " + overrides_file.read_text().strip()
        print(f"{d}  ({log_count} log file(s)){overrides}")


def _cmd_show(args: argparse.Namespace) -> None:
    run = Path(args.run)
    log_files = _find_log_files(run)
    if not log_files:
        print(f"No log files found in {run}", file=sys.stderr)
        sys.exit(1)
    for lf in log_files:
        events = _read_jsonl_events(lf)
        for ev in events:
            if args.event and ev.get("event") != args.event:
                continue
            if args.level and ev.get("level", "").upper() != args.level.upper():
                continue
            print(_format_event(ev, compact=args.compact))


def _cmd_tail(args: argparse.Namespace) -> None:
    run = Path(args.run)
    log_files = _find_log_files(run)
    if not log_files:
        print(f"No log files found in {run}", file=sys.stderr)
        sys.exit(1)
    all_events: list[dict] = []
    for lf in log_files:
        all_events.extend(_read_jsonl_events(lf))
    for ev in all_events[-args.n :]:
        print(_format_event(ev, compact=True))


def logs_main(argv: list[str] | None = None) -> None:
    """Entry point for ``ornlkit logs``."""
    parser = argparse.ArgumentParser(prog="ornlkit logs", description="Inspect structured logs")
    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="List Hydra run directories")
    p_list.add_argument("--roots", nargs="+", help="Root directories to search")

    # show
    p_show = sub.add_parser("show", help="Show log events from a run")
    p_show.add_argument("run", help="Run directory or log file path")
    p_show.add_argument("--event", help="Filter by event name")
    p_show.add_argument("--level", help="Filter by log level")
    p_show.add_argument("-c", "--compact", action="store_true", help="Compact one-line format")

    # tail
    p_tail = sub.add_parser("tail", help="Show last N events from a run")
    p_tail.add_argument("run", help="Run directory or log file path")
    p_tail.add_argument("-n", type=int, default=10, help="Number of events (default: 10)")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    {"list": _cmd_list, "show": _cmd_show, "tail": _cmd_tail}[args.command](args)
