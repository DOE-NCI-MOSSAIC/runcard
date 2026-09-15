# runcard

Hydra configuration and structured logging for research experiments on HPC
systems. One decorator turns a script's constants into a YAML file with
command-line overrides, gives every run its own directory, and records what
happened as readable console lines and a JSON event log.

A *run card*, in the event-generator sense, is the one file that fully
specifies a run. Your `conf/config.yaml` is that file. The decorator stamps
every run with it.

## The whole API

```python
from omegaconf import DictConfig

from runcard import experiment, get_logger

log = get_logger(__name__)


@experiment("conf/config.yaml")
def main(cfg: DictConfig) -> None:
    log.info("start", lr=cfg.model.lr, epochs=cfg.model.epochs)
    ...


if __name__ == "__main__":
    main()
```

```yaml
# conf/config.yaml
model:
  lr: 0.001
  epochs: 3
```

```bash
uv run python train.py                        # defaults
uv run python train.py model.lr=0.01          # override any value
uv run python train.py -m model.lr=0.1,0.01   # sweep
uv run runcard logs list                      # find runs afterwards
uv run runcard logs show outputs/<date>/<time> --event epoch_done
```

Every run leaves one directory behind:

```
outputs/<date>/<time>/
├── .hydra/
│   ├── config.yaml       # the exact config this run used
│   └── overrides.yaml    # what you typed on the command line
└── train.log             # every event as one JSON line, with host and SLURM context
```

## Install

Add it to your own uv project:

```bash
uv add "runcard @ git+https://github.com/adanoelle/runcard.git"
```

Tab completion for bash, zsh, or fish:

```bash
uv run runcard --install-completion
```

Then follow the [tutorial](tutorial.md): ten commands, each introducing one
idea, ending with a Polars one-liner that pivots a sweep's loss curves into a
table.

## What you get

**Config in one file.**
:   `cfg.model.lr` reads `model: lr:` from the YAML. Misspelled keys are
    refused instead of silently using the default.

**Events instead of prints.**
:   `log.info("epoch_done", epoch=i, loss=x)` shows as a readable line on the
    console and as a JSON object in the run directory. Same call, both outputs.

**Provenance for free.**
:   Config, overrides, package versions, hostname, and SLURM job id are stored
    with every run.

**`runcard logs`.**
:   `list` shows every run with the overrides that produced it; `show` and
    `tail` read a run back in the console format, filtered by event or level,
    or as JSON for `jq` and Polars.

## Where to go next

- [Tutorial](tutorial.md): run the quickstart and see each feature once.
- [How-to guides](how-to/overrides-and-sweeps.md): overrides, sweeps, reading
  logs, Frontier.
- [Explanation](explanation/why-run-cards.md): why the pieces are shaped the
  way they are.
- [Reference](reference/api.md): the API, generated from the docstrings.
