"""The ``@experiment`` decorator: Hydra config plus ORNL HPC diagnostics."""

import argparse
import functools
import inspect
import os
import platform as _platform
import re
import sys
from collections.abc import Callable, Sequence

import hydra
import structlog.contextvars
from omegaconf import DictConfig

from runcard._logging import bind_slurm_context, configure_handlers
from runcard.diagnostics import _CORE_PACKAGES, log_diagnostics

# Hydra 1.3 passes a LazyCompletionHelp object (which doesn't implement
# __contains__) as the ``help`` argument to argparse.  Python 3.14 added
# ``_check_help`` validation that calls ``'%' not in help_string``, which
# raises TypeError for non-string help objects.  Patch it out at import
# time so both ``uv run runcard`` and downstream scripts work on 3.14+.
if sys.version_info >= (3, 14) and hasattr(argparse.ArgumentParser, "_check_help"):
    argparse.ArgumentParser._check_help = lambda self, action: None  # type: ignore[assignment]

DEFAULT_CONFIG = "conf/config.yaml"

_YAML_SUFFIX = re.compile(r"\.ya?ml$")


def _split_config(config: str) -> tuple[str, str]:
    """Split ``"conf/config.yaml"`` into Hydra's ``("conf", "config")``."""
    directory, filename = os.path.split(config)
    name = _YAML_SUFFIX.sub("", filename)
    if not name:
        raise ValueError(f"config must name a YAML file, got {config!r}")
    return directory or ".", name


def experiment(
    config: str | Callable = DEFAULT_CONFIG,
    /,
    *,
    config_path: str | None = None,
    config_name: str | None = None,
    core_packages: Sequence[str] = _CORE_PACKAGES,
):
    """Turn a script's ``main(cfg)`` into a recorded experiment run.

    The decorated function receives its YAML config as ``cfg``, every value
    overridable from the command line.  Each run gets its own output
    directory holding the exact config, the overrides, and a JSON event log,
    and starts by logging the host, Python, package versions, and SLURM job.

    Usage::

        @experiment                          # conf/config.yaml next to the script
        @experiment("settings/train.yaml")   # any path relative to the script
        @experiment(config_path="conf", config_name="config")   # Hydra-style

    ``config`` is resolved relative to the file that defines the decorated
    function, so scripts behave the same wherever they are run from.
    """
    if callable(config):  # bare ``@experiment`` with no parentheses
        return experiment()(config)

    if config_path is None and config_name is None:
        config_path, config_name = _split_config(config)
    elif config_path is None or config_name is None:
        raise TypeError("config_path and config_name must be given together")
    elif config != DEFAULT_CONFIG:
        raise TypeError("pass either a config file or config_path/config_name, not both")

    def decorator(func):
        # Resolve config_path relative to the *researcher's* source file,
        # not runcard's.  Hydra's @hydra.main uses inspect.stack() to find
        # the caller's directory; wrapping it would make it resolve against
        # *this* file.  Passing an absolute path makes Hydra skip its own
        # stack-based resolution entirely.
        func_dir = os.path.dirname(os.path.abspath(inspect.getfile(func)))
        abs_config_path = os.path.join(func_dir, config_path)

        @hydra.main(version_base=None, config_path=abs_config_path, config_name=config_name)
        @functools.wraps(func)
        def wrapper(cfg: DictConfig):
            structlog.contextvars.clear_contextvars()
            configure_handlers()
            bind_slurm_context()
            structlog.contextvars.bind_contextvars(hostname=_platform.node())
            log_diagnostics(core_packages=core_packages)
            return func(cfg)

        return wrapper

    return decorator
