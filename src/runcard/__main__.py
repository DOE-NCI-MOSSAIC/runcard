"""Allow running with `python -m runcard` or `uv run runcard`."""

import sys

from omegaconf import DictConfig

from runcard import __version__
from runcard._experiment import experiment
from runcard._logging import get_logger

log = get_logger()


@experiment("conf/config.yaml")
def _hydra_main(cfg: DictConfig) -> None:
    log.info("greeting", message=cfg.app.greeting, version=__version__)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "logs":
        from runcard.cli.logs import logs_main

        logs_main(sys.argv[2:])
    else:
        _hydra_main()


if __name__ == "__main__":
    main()
