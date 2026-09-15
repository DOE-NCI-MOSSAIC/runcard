"""Diagnostic logging for verifying compute-job environments."""

import importlib.metadata
import os
import platform
import shutil
import sys
import time
from collections.abc import Sequence

from pydantic import BaseModel, Field

from runcard._logging import get_logger

log = get_logger()

_CORE_PACKAGES = ("polars", "pyarrow", "datafusion", "pydantic", "orjson", "rustworkx")

_SLURM_VARS = (
    "SLURM_JOB_ID",
    "SLURM_NODELIST",
    "SLURM_NNODES",
    "SLURM_NTASKS",
    "SLURM_CLUSTER_NAME",
)


class SlurmInfo(BaseModel):
    """SLURM job variables, ``None`` when running outside a job.

    Attributes:
        job_id: ``SLURM_JOB_ID``.
        nodelist: ``SLURM_NODELIST``, e.g. ``frontier[01234-01235]``.
        nnodes: ``SLURM_NNODES``.
        ntasks: ``SLURM_NTASKS``.
        cluster_name: ``SLURM_CLUSTER_NAME``.
    """

    job_id: str | None = None
    nodelist: str | None = None
    nnodes: str | None = None
    ntasks: str | None = None
    cluster_name: str | None = None


class DiagnosticsReport(BaseModel):
    """Snapshot of the environment a run started in.

    Attributes:
        hostname: Node the process is running on.
        platform: ``platform.platform()`` string.
        python_version: Interpreter version, e.g. ``3.12.13``.
        python_path: Path to the interpreter, which shows which venv is active.
        cwd: Working directory at startup.
        user: ``$USER``, or ``"unknown"``.
        slurm: SLURM job variables.
        uv_path: Location of ``uv`` if on ``PATH``.
        packages: Installed version per requested distribution, or
            ``"NOT FOUND"``.
        elapsed_seconds: Time taken to collect the report.
    """

    hostname: str
    platform: str
    python_version: str
    python_path: str
    cwd: str
    user: str
    slurm: SlurmInfo = Field(default_factory=SlurmInfo)
    uv_path: str | None = None
    packages: dict[str, str] = Field(default_factory=dict)
    elapsed_seconds: float = 0.0


def _get_package_version(name: str) -> str:
    """Return the installed version of *name*, or 'NOT FOUND'."""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "NOT FOUND"


def collect_diagnostics(
    core_packages: Sequence[str] = _CORE_PACKAGES,
) -> DiagnosticsReport:
    """Collect environment diagnostics without logging them.

    Args:
        core_packages: Distribution names to look up versions for.

    Returns:
        A ``DiagnosticsReport``; nothing is logged.
    """
    t0 = time.monotonic()

    slurm = SlurmInfo(
        job_id=os.environ.get("SLURM_JOB_ID"),
        nodelist=os.environ.get("SLURM_NODELIST"),
        nnodes=os.environ.get("SLURM_NNODES"),
        ntasks=os.environ.get("SLURM_NTASKS"),
        cluster_name=os.environ.get("SLURM_CLUSTER_NAME"),
    )

    packages = {pkg: _get_package_version(pkg) for pkg in core_packages}

    elapsed = time.monotonic() - t0

    return DiagnosticsReport(
        hostname=platform.node(),
        platform=platform.platform(),
        python_version=platform.python_version(),
        python_path=sys.executable,
        cwd=os.getcwd(),
        user=os.environ.get("USER", "unknown"),
        slurm=slurm,
        uv_path=shutil.which("uv"),
        packages=packages,
        elapsed_seconds=round(elapsed, 3),
    )


def log_diagnostics(
    core_packages: Sequence[str] = _CORE_PACKAGES,
) -> DiagnosticsReport:
    """Log environment information useful for verifying compute jobs.

    Emits three flat events, ``environment``, ``slurm`` and ``packages``, so
    each fits on one console line. ``@experiment`` calls this at startup.

    Args:
        core_packages: Distribution names to look up versions for.

    Returns:
        The ``DiagnosticsReport`` that was logged.
    """
    report = collect_diagnostics(core_packages=core_packages)

    # platform and uv_path stay on the report but are left off the log line:
    # they are long and rarely what a researcher needs to see at a glance.
    log.info(
        "environment",
        hostname=report.hostname,
        user=report.user,
        python_version=report.python_version,
        python_path=report.python_path,
        cwd=report.cwd,
    )
    slurm = report.slurm.model_dump(exclude_none=True)
    log.info("slurm", active=bool(slurm), **slurm)
    log.info("packages", **report.packages)

    return report
