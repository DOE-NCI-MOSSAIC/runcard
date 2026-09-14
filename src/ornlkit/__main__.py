"""Allow running with `python -m ornlkit` or `uv run ornlkit`."""

import sys

from omegaconf import DictConfig

from ornlkit import __version__
from ornlkit._logging import get_logger
from ornlkit.experiment import ornlkit_main

log = get_logger()


@ornlkit_main(config_path="conf", config_name="config")
def _hydra_main(cfg: DictConfig) -> None:
    log.info("greeting", message=cfg.app.greeting, version=__version__)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "logs":
        from ornlkit.cli.logs import logs_main

        logs_main(sys.argv[2:])
    else:
        _hydra_main()


if __name__ == "__main__":
    main()
