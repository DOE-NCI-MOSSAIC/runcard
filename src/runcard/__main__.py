"""Console entry point: ``runcard`` (smoke test) and ``runcard logs``.

Running ``runcard`` with no subcommand executes a minimal ``@experiment``
against the package's own ``conf/config.yaml``, which is useful for checking
an environment (``runcard app.greeting=Hi``). ``runcard logs ...`` is
delegated to ``runcard.cli.logs``.
"""

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
    """Dispatch to ``runcard logs`` or run the smoke-test experiment."""
    if len(sys.argv) > 1 and sys.argv[1] == "logs":
        from runcard.cli.logs import logs_main

        logs_main(sys.argv[2:])
    else:
        _hydra_main()


if __name__ == "__main__":
    main()
