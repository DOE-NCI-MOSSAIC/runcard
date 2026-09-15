"""The ``runcard`` command-line application.

Built on Typer, so ``runcard --install-completion`` sets up tab completion
for bash, zsh, or fish, and ``--help`` output is formatted by Rich.

Commands:

* ``runcard check [OVERRIDES...]``: run a one-line experiment to verify
  the environment; extra arguments are Hydra overrides.
* ``runcard logs list|show|tail``: inspect structured logs from runs.
"""

from __future__ import annotations

import sys

import typer

from runcard import __version__
from runcard._experiment import experiment
from runcard._logging import get_logger
from runcard.cli.logs import logs_app

app = typer.Typer(
    name="runcard",
    help="Hydra configuration and structured logging for HPC experiments.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(logs_app, name="logs")

log = get_logger()


def _version(value: bool) -> None:
    if value:
        typer.echo(f"runcard {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show the version and exit.",
        callback=_version,
        is_eager=True,
    ),
) -> None:
    """Hydra configuration and structured logging for HPC experiments."""


@experiment("../conf/config.yaml")
def _check_experiment(cfg) -> None:
    log.info("greeting", message=cfg.app.greeting, version=__version__)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def check(ctx: typer.Context) -> None:
    """Run a one-line experiment to verify the environment.

    Logs the host, Python, package versions, and SLURM job, then one
    ``greeting`` event. Any extra arguments are passed to Hydra as overrides,
    for example [bold]runcard check app.greeting=Hi hydra.run.dir=runs/smoke[/bold]
    or [bold]runcard check --cfg job[/bold] to print the effective config.
    """
    sys.argv = ["runcard check", *ctx.args]
    _check_experiment()


def main() -> None:
    """Console-script entry point."""
    app()
