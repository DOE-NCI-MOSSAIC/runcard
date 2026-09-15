# runcard

Hydra configuration and structured logging for research experiments on ORNL
HPC systems. One decorator turns a script's constants into a YAML file with
command-line overrides, gives every run its own directory, and records what
happened as readable console lines and a JSON event log.

## Example

```python
from omegaconf import DictConfig
from runcard import get_logger, experiment

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

Each run creates one directory, tracking provenance:

```
outputs/<date>/<time>/
├── .hydra/
│   ├── config.yaml       # the exact config this run used
│   └── overrides.yaml    # what you typed on the command line
└── train.log             # every event as one JSON line, with host and SLURM context
```

The first three console lines of every run report the host, Python, package
versions, and SLURM job, so a run that behaves differently on Frontier than on
a laptop leaves evidence.

## Install

Add it to your own uv project:

```bash
uv add "runcard @ git+https://github.com/adanoelle/runcard.git"
```

Tab completion for bash, zsh, or fish:

```bash
uv run runcard --install-completion
```

Then copy [examples/quickstart](examples/quickstart) next to your code and
follow its README: ten commands, each introducing one idea, ending with a
Polars one-liner that pivots a sweep's loss curves into a table.

## What you get

- **Config in one file.** `cfg.model.lr` reads `model: lr:` from the YAML.
  Misspelled keys are refused instead of silently using the default.
- **Events instead of prints.** `log.info("epoch_done", epoch=i, loss=x)`
  shows as a readable line on the console and as a JSON object in the run
  directory. Same call, both outputs.
- **Provenance for free.** Config, overrides, package versions, hostname, and
  SLURM job id are stored with every run.
- **`runcard logs`.** `list` shows every run with the overrides that produced
  it; `show` and `tail` read a run back in the console format, filtered by
  event or level, or as JSON for `jq` and Polars.

The 30-minute walkthrough for researchers is in
[docs/presentation-notes.md](docs/presentation-notes.md).

## On Frontier

Nothing in the script changes. Inside a job the startup lines report the SLURM
job, and every JSON line carries the job id, node list, and hostname.

Minimal batch script:

```bash
#!/bin/bash
#SBATCH -A <project_id>
#SBATCH -J myexp
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o runs/myexp/%j.log

module load miniforge3/23.11.0-0
export TMPDIR=/tmp

run_dir="runs/myexp/${SLURM_JOB_ID}"
mkdir -p "$run_dir"
.venv-frontier/bin/python3 train.py hydra.run.dir="$run_dir" "$@"
```

Environment setup, the `.venv-frontier` sync recipe, interactive submission,
and the Apptainer container live in the companion repository
[runcard-frontier](https://github.com/adanoelle/runcard-frontier).

## Development

```bash
uv sync
just check          # lint + typecheck + test
just quickstart     # run the example
just run            # local smoke test → runs/runcard/local-*/
```

A Nix dev shell with Python, uv, and just is provided (`nix develop`); it is
optional.

## Layout

```
runcard/
├── src/runcard/
│   ├── _experiment.py     # @experiment
│   ├── _logging.py        # structlog configuration, console and JSON renderers
│   ├── diagnostics.py     # environment / SLURM / package report at startup
│   └── cli/logs.py        # runcard logs list | show | tail
├── examples/quickstart/   # copyable experiment with a ten-step demo
├── docs/                  # presentation notes
├── talks/                 # presenterm deck
└── tests/
```
