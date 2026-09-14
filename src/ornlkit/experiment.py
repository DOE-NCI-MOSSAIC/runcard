"""Hydra-based experiment decorator with ORNL HPC diagnostics."""

import argparse
import functools
import inspect
import os
import platform as _platform
import sys
from collections.abc import Sequence

import hydra
import structlog.contextvars
from omegaconf import DictConfig

from ornlkit._logging import bind_slurm_context, configure_handlers
from ornlkit.diagnostics import _CORE_PACKAGES, log_diagnostics

# Hydra 1.3 passes a LazyCompletionHelp object (which doesn't implement
# __contains__) as the ``help`` argument to argparse.  Python 3.14 added
# ``_check_help`` validation that calls ``'%' not in help_string``, which
# raises TypeError for non-string help objects.  Patch it out at import
# time so both ``uv run ornlkit`` and downstream scripts work on 3.14+.
if sys.version_info >= (3, 14) and hasattr(argparse.ArgumentParser, "_check_help"):
    argparse.ArgumentParser._check_help = lambda self, action: None  # type: ignore[assignment]


def ornlkit_main(
    config_path: str = "conf",
    config_name: str = "config",
    core_packages: Sequence[str] = _CORE_PACKAGES,
):
    """Decorator: Hydra config + ORNL diagnostics for HPC experiment scripts."""

    def decorator(func):
        # Resolve config_path relative to the *researcher's* source file,
        # not ornlkit's.  Hydra's @hydra.main uses inspect.stack() to find
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
