"""Hydra configuration and structured logging for HPC experiments.

A *run card* is the one file that fully specifies a run. ``runcard`` turns a
script's ``conf/config.yaml`` into that file: every value can be overridden
from the command line, every run gets its own directory holding the exact
config and a JSON event log, and every run starts by recording where it ran,
under which Python, and with which package versions.

The public API is two names:

* ``experiment``: the decorator that wraps a script's ``main(cfg)``.
* ``get_logger``: a structlog logger for ``log.info("event", key=value)``.

Example:
    ```python
    from runcard import experiment, get_logger

    log = get_logger(__name__)


    @experiment("conf/config.yaml")
    def main(cfg):
        log.info("start", lr=cfg.model.lr)
    ```
"""

__version__ = "0.1.0"

from runcard._experiment import experiment
from runcard._logging import get_logger

__all__ = ["__version__", "get_logger", "experiment"]
