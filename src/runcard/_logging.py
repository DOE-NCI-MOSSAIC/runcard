"""Structured logging configuration built on structlog + stdlib integration.

Two renderers share one processor chain:

* The Hydra file handler writes JSON lines with every field, including the
  run context (SLURM variables, hostname) bound via contextvars.
* The console handler renders a compact human line: short timestamp, level,
  event, and only the fields passed explicitly on the log call.  Run
  context is hidden because it never changes within a run and is reported
  once at startup by :func:`runcard.diagnostics.log_diagnostics`.
"""

import logging
import os
from datetime import datetime
from typing import Any

import orjson
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars
from structlog.typing import EventDict, WrappedLogger

_SLURM_VARS = (
    "SLURM_JOB_ID",
    "SLURM_NODELIST",
    "SLURM_NNODES",
    "SLURM_NTASKS",
    "SLURM_CLUSTER_NAME",
)

#: Keys that runcard binds as run context.  Used by ``runcard logs`` to hide
#: them from human-readable output, where the marker below is unavailable.
RUN_CONTEXT_KEYS = frozenset(v.lower() for v in _SLURM_VARS) | {"hostname"}

#: Event names emitted by runcard itself rather than by the researcher's code.
#: ``run_finished`` and ``run_failed`` bracket every run; the other three are
#: the startup diagnostics.
RUNCARD_EVENTS = frozenset({"environment", "slurm", "packages", "run_finished", "run_failed"})

# Event-dict key holding the names of fields merged in from contextvars.
_RUN_CONTEXT_MARKER = "_run_context"

# Width reserved for the event name on the console.
_CONSOLE_EVENT_PAD = 24


def _orjson_dumps(obj, **_kw):
    """Orjson serializer that returns str (structlog expects str, orjson returns bytes)."""
    return orjson.dumps(obj, option=orjson.OPT_NON_STR_KEYS).decode()


# --- shared processors -------------------------------------------------------


def add_local_timestamp(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add an ISO-8601 timestamp in local time with UTC offset.

    Local time matches the clock researchers see and Hydra's run directory
    names; the offset (e.g. ``-04:00``) keeps the JSON file unambiguous.

    Args:
        logger: The wrapped logger (unused, structlog processor signature).
        method_name: The log method name, e.g. ``"info"`` (unused).
        event_dict: The event being processed.

    Returns:
        The same event dict with a ``timestamp`` key added.
    """
    event_dict["timestamp"] = datetime.now().astimezone().isoformat(timespec="microseconds")
    return event_dict


def merge_run_context(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Merge contextvars into the event, recording which keys came from context.

    Behaves like ``structlog.contextvars.merge_contextvars`` but leaves a
    marker so the console renderer can hide context-only keys while the
    JSON renderer keeps them.  Fields passed explicitly on the log call
    always win and are never hidden.

    Args:
        logger: The wrapped logger (unused, structlog processor signature).
        method_name: The log method name (unused).
        event_dict: The event being processed.

    Returns:
        The event dict with context values merged in and a private marker
        listing which keys came from context.
    """
    ctx = get_contextvars()
    merged = [k for k in ctx if k not in event_dict]
    for k in merged:
        event_dict[k] = ctx[k]
    event_dict[_RUN_CONTEXT_MARKER] = merged
    return event_dict


# --- console-only processors -------------------------------------------------


def _hide_run_context(logger, method_name, event_dict):
    """Drop fields that were merged from contextvars (console only)."""
    for k in event_dict.pop(_RUN_CONTEXT_MARKER, ()):
        event_dict.pop(k, None)
    return event_dict


def _short_timestamp(logger, method_name, event_dict):
    """Reduce an ISO-8601 timestamp to ``HH:MM:SS`` (console only)."""
    ts = event_dict.get("timestamp")
    if isinstance(ts, str) and len(ts) >= 19 and ts[10] == "T":
        event_dict["timestamp"] = ts[11:19]
    return event_dict


def _hide_root_logger(logger, method_name, event_dict):
    """Drop the ``[root]`` logger column; named loggers are still shown."""
    if event_dict.get("logger") == "root":
        del event_dict["logger"]
    return event_dict


# --- file-only processors ----------------------------------------------------


def _strip_run_context_marker(logger, method_name, event_dict):
    event_dict.pop(_RUN_CONTEXT_MARKER, None)
    return event_dict


# --- public configuration ----------------------------------------------------


def console_processors(*, colors: bool) -> list:
    """Processor chain that turns an event dict into one console line.

    Args:
        colors: Whether to emit ANSI colours (typically ``stdout.isatty()``).

    Returns:
        Processors ending in a ``structlog.dev.ConsoleRenderer``, suitable for
        a ``ProcessorFormatter`` or for ``render_console_line``.
    """
    return [
        _hide_run_context,
        _short_timestamp,
        _hide_root_logger,
        structlog.dev.ConsoleRenderer(colors=colors, pad_event_to=_CONSOLE_EVENT_PAD),
    ]


def render_console_line(event: dict, *, colors: bool) -> str:
    """Render one event dict as a console line.

    Used by ``runcard logs`` to show events read back from a JSON log in
    the same format they had on the console.

    Args:
        event: An event as written to the JSON log (``event``, ``level``,
            ``timestamp``, and any fields).
        colors: Whether to emit ANSI colours.

    Returns:
        A single line of text without a trailing newline.
    """
    *processors, renderer = console_processors(colors=colors)
    event = dict(event)
    for proc in processors:
        event = proc(None, "info", event)
    return str(renderer(None, "info", event))


def configure_structlog(*, cache_logger_on_first_use: bool = True) -> None:
    """Set up the structlog processor chain for stdlib integration.

    Called once at import time. Events pass through the shared processors
    here, then through ``logging`` handlers whose formatters apply the
    console or JSON renderer (see ``configure_handlers``).

    Args:
        cache_logger_on_first_use: Passed to ``structlog.configure``. Tests
            set it to ``False`` so reconfiguration takes effect.
    """
    structlog.configure(
        processors=[
            merge_run_context,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            add_local_timestamp,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=cache_logger_on_first_use,
    )


def configure_handlers() -> None:
    """Replace the formatters on Hydra's stdlib handlers.

    Hydra installs a ``StreamHandler`` (console) and a ``FileHandler`` (the
    run directory's ``.log``). This gives the file the JSON renderer and the
    console the human renderer. Called by ``@experiment`` after Hydra has
    initialised; safe to call again.

    Note:
        ``FileHandler`` is checked before ``StreamHandler`` because it is a
        subclass of it.
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.setFormatter(
                structlog.stdlib.ProcessorFormatter(
                    processors=[
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        _strip_run_context_marker,
                        # Render tracebacks into an "exception" string so
                        # log.exception() is preserved in the JSON file.
                        structlog.processors.format_exc_info,
                        structlog.processors.JSONRenderer(serializer=_orjson_dumps),
                    ],
                )
            )
        elif isinstance(handler, logging.StreamHandler):
            stream = getattr(handler, "stream", None)
            colors = hasattr(stream, "isatty") and stream.isatty()
            handler.setFormatter(
                structlog.stdlib.ProcessorFormatter(
                    processors=[
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        *console_processors(colors=colors),
                    ],
                )
            )


def bind_slurm_context() -> None:
    """Bind SLURM job variables to structlog contextvars.

    Reads ``SLURM_JOB_ID``, ``SLURM_NODELIST``, ``SLURM_NNODES``,
    ``SLURM_NTASKS`` and ``SLURM_CLUSTER_NAME`` and binds those that are set,
    lower-cased, so every JSON event carries them. Outside a job nothing is
    bound.
    """
    ctx = {}
    for var in _SLURM_VARS:
        value = os.environ.get(var)
        if value is not None:
            ctx[var.lower()] = value
    if ctx:
        bind_contextvars(**ctx)


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger, optionally with bound initial values.

    Args:
        name: Logger name, shown in brackets on the console (``[train]``).
            ``__name__`` is the usual choice; ``None`` gives the root logger,
            whose name is hidden.
        **initial_values: Fields to attach to every event from this logger.

    Returns:
        A bound logger. Call ``.info("event_name", key=value, ...)`` on it;
        ``.bind(**more)`` returns a child with extra fields.

    Example:
        ```python
        log = get_logger(__name__)
        run_log = log.bind(trial=7, seed=0)
        run_log.info("epoch_done", epoch=0, loss=0.5)
        ```
    """
    log = structlog.get_logger(name)
    if initial_values:
        log = log.bind(**initial_values)
    return log


# Configure structlog at import time so get_logger() works immediately.
configure_structlog()

__all__ = [
    "RUNCARD_EVENTS",
    "RUN_CONTEXT_KEYS",
    "add_local_timestamp",
    "bind_slurm_context",
    "clear_contextvars",
    "configure_handlers",
    "configure_structlog",
    "console_processors",
    "get_logger",
    "merge_run_context",
    "render_console_line",
]
