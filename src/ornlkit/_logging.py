"""Structured logging configuration built on structlog + stdlib integration."""

import logging
import os

import orjson
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

_SLURM_VARS = (
    "SLURM_JOB_ID",
    "SLURM_NODELIST",
    "SLURM_NNODES",
    "SLURM_NTASKS",
    "SLURM_CLUSTER_NAME",
)


def _orjson_dumps(obj, **_kw):
    """orjson serializer that returns str (structlog expects str, orjson returns bytes)."""
    return orjson.dumps(obj, option=orjson.OPT_NON_STR_KEYS).decode()


def configure_structlog(*, cache_logger_on_first_use: bool = True) -> None:
    """Set up the structlog processor chain for stdlib integration."""
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=cache_logger_on_first_use,
    )


def configure_handlers() -> None:
    """Patch Hydra's stdlib handlers with structlog ProcessorFormatter.

    Called after Hydra init to replace handler formatters.
    FileHandler check must come before StreamHandler (it's a subclass).
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.setFormatter(
                structlog.stdlib.ProcessorFormatter(
                    processors=[
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
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
                        structlog.dev.ConsoleRenderer(colors=colors),
                    ],
                )
            )


def bind_slurm_context() -> None:
    """Bind SLURM environment variables to structlog contextvars."""
    ctx = {}
    for var in _SLURM_VARS:
        value = os.environ.get(var)
        if value is not None:
            ctx[var.lower()] = value
    if ctx:
        bind_contextvars(**ctx)


def get_logger(name=None, **initial_values):
    """Return a structlog logger, optionally with bound initial values."""
    log = structlog.get_logger(name)
    if initial_values:
        log = log.bind(**initial_values)
    return log


# Configure structlog at import time so get_logger() works immediately.
configure_structlog()

__all__ = [
    "bind_slurm_context",
    "clear_contextvars",
    "configure_handlers",
    "configure_structlog",
    "get_logger",
]
