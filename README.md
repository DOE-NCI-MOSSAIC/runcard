# runcard

Hydra configuration and structured logging for research experiments on ORNL
systems. A *run card*, in the event-generator sense, is the one file that
fully specifies a run. runcard makes your `conf/config.yaml` that file: every
value can be overridden from the command line, every run gets its own
directory holding the exact config and a JSON event log, and every run
starts by recording where it ran and ends by recording how it ended.

Two ways to use it:

- **In your code**: one decorator and one logger, two imports, nothing else
  in the script changes.
- **From the shell**: `runcard logs` answers "which runs do I have, how did
  they end, and what happened in this one" for any run directory runcard
  produced, yours or a colleague's.

## In your code

Add it to your own uv project:

```bash
uv add "runcard @ git+https://github.com/adanoelle/runcard.git"
```

Then write your experiment as a function of its config:

```python
from omegaconf import DictConfig

from runcard import experiment, get_logger

log = get_logger(__name__)


@experiment("conf/config.yaml")
def main(cfg: DictConfig) -> None:
    log.info("start", lr=cfg.model.lr, epochs=cfg.model.epochs)
    for epoch in range(cfg.model.epochs):
        ...
        log.info("epoch_done", epoch=epoch, loss=loss)


if __name__ == "__main__":
    main()
```

```yaml
# conf/config.yaml
model:
  lr: 0.001
  epochs: 3
```

`cfg.model.lr` reads `model: lr:` from the YAML. Every value can be changed
on the command line without editing the file, and a misspelled key is an
error rather than a silent default:

```bash
uv run python train.py                        # defaults
uv run python train.py model.lr=0.01          # override any value
uv run python train.py +model.dropout=0.1     # add a key not in the file
uv run python train.py -m model.lr=0.1,0.01   # sweep: one run per value
uv run python train.py --cfg job              # print the effective config
```

`log.info("epoch_done", epoch=i, loss=x)` replaces `print`. The same call
shows as one readable line on the console and is stored as one JSON object
in the run directory. Each run creates one directory:

```
outputs/<date>/<time>/
├── .hydra/
│   ├── config.yaml       # the exact config this run used
│   └── overrides.yaml    # what you typed on the command line
└── train.log             # every event as one JSON line, with host and SLURM context
```

The first three events of every run record the host, Python, package
versions, and SLURM job. The last one records whether the function returned
or raised, and how long it took. A run that behaves differently on Frontier
than on a laptop leaves evidence, and a crash is distinguishable from a job
that was killed.

The JSON log reads straight into Polars for analysis:

```python
import polars as pl

df = pl.read_ndjson("outputs/<date>/<time>/train.log")
df.filter(pl.col("event") == "epoch_done").select("epoch", "loss")
```

[examples/quickstart](examples/quickstart) is a complete, copyable experiment
with a ten-step README that introduces each idea once.

## From the shell

The `runcard` command works on any run directory the decorator produced. It
does not need to be run from the project that made the runs, so install it
once for your user and use it everywhere:

```bash
uv tool install "runcard @ git+https://github.com/adanoelle/runcard.git"
runcard --install-completion      # bash, zsh, or fish; then open a new shell
```

(Inside a project that depends on runcard, `uv run runcard ...` works too.)

**Find runs and see how they ended.** Status comes from the events the
decorator writes, not from what your script logged:

```
$ runcard logs list
Run                          Status             Duration  Overrides
outputs/2026-09-15/10-00-00  finished               3.2s  model.lr=0.1
outputs/2026-09-15/10-05-12  failed                 0.4s  demo.fail_at_epoch=2
outputs/2026-09-15/10-07-40  finished, 1 error      3.1s  model.lr=4.0
runs/myexp/1234567           running              12m 04s +model.dropout=0.1
```

**One screen per run.** When it ran, where, with what, how many warnings and
errors, how the numbers moved, and what the last thing logged was:

```
$ runcard logs summary outputs/2026-09-15/10-00-00
outputs/2026-09-15/10-00-00  finished
Started    2026-09-15 10:00:00-04:00    Duration  3.2s
Where      frontier01234 · python 3.12.13 · job 1234567 on 2 nodes
Overrides  model.lr=0.1 model.epochs=5
Events     12 · 1 warning · 0 errors
Progress   epoch_done ×5 · epoch 0 → 4 · loss 1.913 → 1.143
Last       done  final_loss=1.143 slope=1.39 true_slope=2.5
```

**Read the events back**, in the console format or as JSON, filtered by
event name or level:

```bash
runcard logs show outputs/2026-09-15/10-00-00
runcard logs show outputs/2026-09-15/10-00-00 --event epoch_done
runcard logs show outputs/2026-09-15/10-00-00 --level error
runcard logs tail outputs/2026-09-15/10-00-00 -n 5
runcard logs show outputs/2026-09-15/10-00-00 -c | jq '.loss'
```

**Check an environment** before submitting real work. This runs a one-line
experiment and prints the same startup record your scripts get; anything
after `check` is a Hydra override:

```bash
runcard check
runcard check hydra.run.dir=runs/smoke
```

Tab completion knows about your runs: the run argument completes to run
directories, `--event` completes to the event names actually in that run,
and `--level` to the levels. On a terminal, tables and JSON are colour
coded; when piped, every command prints plain text so it composes with
`grep`, `jq`, and scripts.

## On Frontier

Nothing in the script changes. Inside a job the startup events report the
SLURM job, every JSON line carries the job id, node list, and hostname, and
`runcard logs list` asks SLURM whether a run without an end marker is still
running.

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

Passing `"$@"` through means `sbatch job.sbatch model.lr=0.01` works and the
override is recorded with the run. Environment setup, the `.venv-frontier`
sync recipe, interactive submission, and the Apptainer container live in the
companion repository
[runcard-frontier](https://github.com/adanoelle/runcard-frontier).

## Documentation

The full documentation (tutorial, how-to guides, explanation, and API
reference generated from the docstrings) is in [docs/](docs/) and builds with
`just docs-serve`. The 30-minute walkthrough for researchers is in
[docs/presentation-notes.md](docs/presentation-notes.md).

## Development

```bash
uv sync
just check          # lint + typecheck + test
just quickstart     # run the example
just run            # local smoke test → runs/runcard/local-*/
just docs           # build the documentation site (strict)
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
│   └── cli/
│       ├── app.py         # runcard: check, logs, completion
│       └── logs.py        # runcard logs list | summary | show | tail
├── examples/quickstart/   # copyable experiment with a ten-step demo
├── docs/                  # documentation site source and presentation notes
├── talks/                 # presenterm deck
└── tests/
```
