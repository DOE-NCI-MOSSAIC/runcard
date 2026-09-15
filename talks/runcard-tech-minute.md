---
title: runcard
sub_title: support infrastructure for experiments
author: Ada Young
event: tech minute
date: 2026-09-14
---

<!-- speaker_note: Run from the repo root with present talks/runcard-tech-minute.md. Ctrl+E runs the live blocks in the real terminal, any key returns to the slide. Before the talk, rm -rf outputs multirun, and run uv sync so runcard is current. The live blocks create four runs in order (default, lr=0.9, one that logs an error, one that crashes) and the later slides pick the first and the last of those automatically. -->

How most experiment scripts look
===

```python {1-3|5-7|9-10} +line_numbers
LR = 0.001
EPOCHS = 3
DATA = "/lustre/orion/proj/data.parquet"

print("starting...")
print(f"lr={LR}")
print("epoch 0 loss", loss)

# ...
```

<!-- pause -->

# Some weeks later:

which run had lr=0.01? which node did it crash on?
<!-- pause -->

- parameters live in the code, so the value that made a result is <span class="hl">gone once you edit it</span>
<!-- pause -->
- output is `print`, mixed into the SLURM log with no timestamp
<!-- pause -->
- every run writes to the same place, so <span class="hl">run two overwrites run one</span>

runcard: Experiment Tracking and Logging
===

# Two main objectives:

<!-- pause -->
- Sets up experiment configuration & tracking (Meta's Hydra)
<!-- pause -->
- Sets up structured logging (structlog)
<!-- pause -->
- Answers "which runs, how did they end, what happened" from the shell

<!-- pause -->

All with minimal surface area so that you do not have to add boilerplate.

The Entire API
===

<!-- column_layout: [5, 3] -->

<!-- column: 0 -->

```python {1|3|5-7|8}
from runcard import experiment, get_logger

log = get_logger("train")


@experiment("conf/config.yaml")
def main(cfg):
    log.info("start", lr=cfg.model.lr)
    ...


if __name__ == "__main__":
    main()
```

<!-- pause -->

<!-- column: 1 -->

```yaml
# conf/config.yaml
data:
  n_rows: 10000
  seed: 0
model:
  lr: 0.5
  epochs: 5
```

<!-- pause -->

## Two ideas

- `cfg` is the YAML, as an object
- `log.info(...)` replaces `print`

Event name first, then data.

<!-- reset_layout -->

Run it
===

```bash +exec +acquire_terminal
/// cd "$(git rev-parse --show-toplevel)"
uv run python examples/quickstart/train.py
/// read -rsn1 -p $'\n[any key returns to the slides]'
```

<!-- pause -->

# Structured Logging

```text
21:15:47 [info   ] environment  hostname=frontier01234 python=3.12.13
21:15:47 [info   ] slurm        active=False
21:15:47 [info   ] packages     polars=1.43.2 pyarrow=25.0.1
21:15:47 [info   ] start        [train] epochs=5 lr=0.5 n_rows=10000 seed=0
21:15:47 [info   ] epoch_done   [train] epoch=0 loss=1.0241 slope=0.8328
21:15:47 [info   ] epoch_done   [train] epoch=1 loss=0.5065 slope=1.3898
21:15:47 [info   ] run_finished elapsed_s=0.012
```

<!-- pause -->

- first three lines are automatic: <span class="hl">where it ran, which Python, which packages</span>
<!-- pause -->
- then `time` `level` `event` `logger` and sorted `key=value` data
<!-- pause -->
- the last line is automatic too: <span class="hl">returned, or raised, and how long it took</span>

What is saved to disk
===

```text
outputs/2026-09-13/21-15-47/
├── .hydra/
│   ├── config.yaml       the exact config this run used
│   ├── overrides.yaml    what you typed on the command line
│   └── hydra.yaml
└── train.log             every event, one JSON object per line
```

<!-- pause -->

# train.log

```json
{"epoch":1,"loss":0.5065,"slope":1.3898,"event":"epoch_done",
 "hostname":"frontier01234","slurm_job_id":"1234567",
 "level":"info","timestamp":"2026-09-13T21:15:47.9-04:00"}
```

<!-- pause -->

# Outputs

> One directory per run, created for you.
> The config that produced a result is saved next to the result.
> <span class="hl">Nothing is ever overwritten.</span>

Change parameters without editing code
===

What if you wanted to run a quick experiment without needing to update some configuration file?
<!-- pause -->

```bash +exec +acquire_terminal
/// cd "$(git rev-parse --show-toplevel)"
uv run python examples/quickstart/train.py model.lr=0.9 model.epochs=3
/// read -rsn1 -p $'\n[any key returns to the slides]'
```



<!-- pause -->

Typos are refused instead of silently running with the default:

```bash +exec +acquire_terminal
/// cd "$(git rev-parse --show-toplevel)"
uv run python examples/quickstart/train.py model.lrr=0.9
/// read -rsn1 -p $'\n[any key returns to the slides]'
```

<!-- pause -->

| Want to                      | Type                         |
| ---------------------------- | ---------------------------- |
| add a key not in the YAML    | `+model.dropout=0.1`         |
| print the effective config   | `--cfg job`                  |
| sweep, one run dir per value | `-m model.lr=0.1,0.5,4.0`    |
| pick the output dir yourself | `hydra.run.dir=runs/trial-7` |

Logging: data in fields, not in strings
===

```python {1-2|4-5} +line_numbers
# do this
log.info("epoch_done", epoch=epoch, loss=loss)

# not this
log.info(f"Epoch {epoch} done, loss {loss:.3f}")
```

Both look the same on the console. Only the first one is a JSON object
you can filter, plot, and compare across runs.

<!-- pause -->

```python
log.warning("loss_increased", epoch=epoch, lr=cfg.model.lr)

try:
    result = step(batch)
except Exception:
    log.exception("failed_step", step=i)  # traceback goes to the file
    raise
```

<span class="dim">Levels: debug (hidden by default), info, warning, exception.</span>

How a run ends is recorded too
===

A script that logs an error and carries on:

```bash +exec +acquire_terminal
/// cd "$(git rev-parse --show-toplevel)"
uv run python examples/quickstart/train.py demo.fail_at_epoch=1
/// read -rsn1 -p $'\n[any key returns to the slides]'
```

<!-- pause -->

A script that crashes (no rows, so the mean is `None`):

```bash +exec +acquire_terminal
/// cd "$(git rev-parse --show-toplevel)"
uv run python examples/quickstart/train.py data.n_rows=0
/// read -rsn1 -p $'\n[any key returns to the slides]'
```

<!-- pause -->

- the decorator writes `run_finished` or `run_failed` (with the traceback)
<!-- pause -->
- so <span class="hl">a crash, a killed job, and a running job no longer look the same</span>

Find runs afterwards
===

```bash +exec +acquire_terminal
/// cd "$(git rev-parse --show-toplevel)"
uv run runcard logs list
/// read -rsn1 -p $'\n[any key returns to the slides]'
```

```text
Run                          Status             Duration  Overrides
outputs/2026-09-13/21-15-47  finished               0.1s
outputs/2026-09-13/21-15-48  finished               0.1s  model.lr=0.9
outputs/2026-09-13/21-15-49  finished, 1 error      0.1s  demo.fail_at_epoch=1
outputs/2026-09-13/21-15-50  failed                 0.0s  data.n_rows=0
```

<span class="dim">Status comes from the events the decorator writes, not from your script.</span>

<!-- pause -->

## One screen for a run: how it ended, where, how the numbers moved

```bash +exec +acquire_terminal
/// cd "$(git rev-parse --show-toplevel)"
/// last=$(uv run runcard logs list | grep '^outputs' | tail -1 | cut -f1)
uv run runcard logs summary "$last"    # the run that crashed
/// read -rsn1 -p $'\n[any key returns to the slides]'
```

Read one run
===

```bash +exec +acquire_terminal
/// cd "$(git rev-parse --show-toplevel)"
/// first=$(uv run runcard logs list | grep '^outputs' | head -1 | cut -f1)
uv run runcard logs show "$first" --event epoch_done
/// read -rsn1 -p $'\n[any key returns to the slides]'
```

<!-- pause -->

```bash +exec +acquire_terminal
/// cd "$(git rev-parse --show-toplevel)"
/// last=$(uv run runcard logs list | grep '^outputs' | tail -1 | cut -f1)
uv run runcard logs show "$last" --level error
/// read -rsn1 -p $'\n[any key returns to the slides]'
```

<!-- pause -->

| Want to                          | Type                          |
| -------------------------------- | ----------------------------- |
| the last five events             | `runcard logs tail RUN -n 5`  |
| JSON for `jq`                    | `runcard logs show RUN -c`    |
| tab-complete runs and events     | `runcard --install-completion`|

<!-- pause -->

# Or skip the CLI and read the file with Polars:

```python
df = pl.read_ndjson("outputs/<date>/<time>/train.log")
df.filter(pl.col("event") == "epoch_done").select("epoch", "loss")
```

<span class="hl">Loss curves across a sweep are a one-liner.</span>

On Frontier nothing changes
===

The decorator notices SLURM. Inside a job the startup line becomes:

```text
00:46:19 [info   ] slurm  active=True cluster_name=frontier job_id=1234567
                            nnodes=2 nodelist=frontier[01234-01235]
```

and every JSON line carries `slurm_job_id`, `slurm_nodelist`, `hostname`.

<!-- pause -->

```bash {9-11} +line_numbers
#!/bin/bash
#SBATCH -A <project_id>
#SBATCH -N 1
#SBATCH -t 00:30:00
#SBATCH -o runs/myexp/%j.log

module load miniforge3/23.11.0-0

run_dir="runs/myexp/${SLURM_JOB_ID}"

.venv-frontier/bin/python3 train.py \
    hydra.run.dir="$run_dir" "$@"
```

- one tree per experiment: `runs/myexp/<jobid>.log` and `runs/myexp/<jobid>/`
- pass `"$@"` through, so `sbatch job.sbatch model.lr=0.01` just works
- `runcard logs list` asks SLURM whether an unfinished run is still going

Try it on your script
===

1. Copy `examples/quickstart/` next to your code.
   Move your constants into `conf/config.yaml`.
2. Replace every `print` with `log.info("what_happened", key=value)`.
3. Run it twice with different overrides, then `runcard logs list`
   and `runcard logs summary <run>`.

<span class="dim">Repo: runcard. Longer notes: runcard/docs/presentation-notes.md</span>
