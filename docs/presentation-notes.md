# ornlkit for your experiments — presentation notes

Speaker notes for introducing ornlkit to researchers who have not used Hydra or
Python logging before. Each `##` section is one slide or one live demo step.
Text in _Say:_ blocks is the talking point; code blocks are what to show.
Everything here was run against the current `main` and reflects real output.

Suggested length: 30 minutes, with the live demo taking half of it.

---

## 1. The problem (2 min)

_Say:_ Most experiment scripts start like this and stay like this.

```python
LR = 0.001
DATA = "/lustre/orion/proj/data.parquet"

print("starting...")
print(f"lr={LR}")
# ... three weeks later: which run had lr=0.01? which node did it crash on?
```

Three things go wrong:

- **Parameters live in the code.** Changing one means editing the file, and the
  value that produced a result is gone once you edit it again.
- **Output is `print`.** It goes to the SLURM log and nowhere else, mixed in
  with everything else, with no timestamp and no way to filter.
- **Nothing records the environment.** Which Python, which node, which package
  versions. When a job behaves differently on Frontier than on your laptop, you
  have no evidence.

ornlkit fixes all three with one decorator. You do not need to learn Hydra or
structlog to benefit. You need to learn about six things, and they are on the
next slides.

---

## 2. The whole API on one slide (3 min)

_Say:_ This is the complete surface area a researcher touches.

```python
from ornlkit._logging import get_logger
from ornlkit.experiment import ornlkit_main

log = get_logger(__name__)

@ornlkit_main(config_path="conf", config_name="config")
def main(cfg):
    log.info("start", lr=cfg.model.lr)
    ...

if __name__ == "__main__":
    main()
```

and a YAML file next to the script:

```yaml
# conf/config.yaml
data:
  path: /lustre/orion/proj/data.parquet
  n_rows: 1000
model:
  lr: 0.001
  epochs: 3
```

Two ideas:

1. **`cfg` is your YAML file as an object.** `cfg.model.lr` reads `model: lr:`
   from the file. Any value can be overridden from the command line without
   touching the file.
2. **`log.info("event_name", key=value, ...)` replaces `print`.** The first
   argument names what happened. Everything else is data attached to it.

The decorator does the rest: parses the command line, creates a directory for
this run, snapshots the config, configures logging, and logs the environment.

---

## 3. Live demo: first run (5 min)

_Say:_ Let's run it. No arguments yet. The script is `examples/quickstart/train.py`
in the repo; its README lists the full demo sequence.

```bash
uv run python examples/quickstart/train.py
```

```
20:51:42 [info     ] environment              cwd=/ccs/proj/abc123/ada/myexp hostname=frontier01234 python_path=/ccs/proj/abc123/ada/myexp/.venv-frontier/bin/python3 python_version=3.12.13 user=ada
20:51:42 [info     ] slurm                    active=False
20:51:42 [info     ] packages                 datafusion=54.0.0 orjson=3.11.9 polars=1.43.2 pyarrow=25.0.1 pydantic=2.13.4 rustworkx=0.18.1
20:51:42 [info     ] start                    [train] lr=0.001 n_rows=1000 path=/lustre/orion/proj/data.parquet
20:51:42 [info     ] epoch_done               [train] epoch=0 loss=1.0
20:51:42 [info     ] epoch_done               [train] epoch=1 loss=0.5
20:51:42 [info     ] epoch_done               [train] epoch=2 loss=0.333
```

Point at the pieces of one line, left to right:

- `20:51:42` — local time. The JSON file has the full timestamp with UTC
  offset.
- `[info     ]` — level. `warning` and `error` stand out in colour.
- `epoch_done` — the event name you passed.
- `[train]` — which logger, if you named it. Handy once a project has several
  modules.
- `epoch=1 loss=0.5` — the data. Always `key=value`, sorted, greppable.

The first three lines are free. Every run tells you where it ran, under what
Python, and with which package versions. When a job misbehaves on Frontier, this
is the first thing to compare.

Then show what appeared on disk:

```
outputs/2026-09-13/20-51-42/
├── .hydra/
│   ├── config.yaml       # the exact config this run used
│   ├── overrides.yaml    # what you typed on the command line
│   └── hydra.yaml
└── train.log             # every event as one JSON line
```

_Say:_ One directory per run, created for you. The config that produced the
result is saved with the result. You can never lose track of which parameters a
run used.

---

## 4. Hydra: change parameters without editing code (5 min)

_Say:_ Hydra is a config framework. You will use about four features of it.

**Override any value on the command line:**

```bash
uv run python train.py model.lr=0.01
uv run python train.py model.lr=0.01 model.epochs=10 data.n_rows=50000
```

Dotted path into the YAML, equals sign, value. That is the whole syntax.

**Typos are caught.** Hydra refuses keys that are not in the file:

```
Could not override 'model.lrr'.
To append to your config use +model.lrr=0.01
Key 'lrr' is not in struct
```

This is a feature. A misspelled parameter fails immediately instead of silently
running with the default.

**Add a key that is not in the file** with a leading `+`:

```bash
uv run python train.py +model.dropout=0.1
```

**Print the effective config** without running anything:

```bash
uv run python train.py --cfg job
```

**Sweep** with `-m` (multirun) and comma-separated values:

```bash
uv run python train.py -m model.lr=0.1,0.01,0.001
```

That runs the script three times, one per value, each in its own directory under
`multirun/`. Combine two swept parameters and you get the cross product.

**Choose where output goes:**

```bash
uv run python train.py hydra.run.dir=runs/my-experiment/trial-7
```

The default is `outputs/<date>/<time>/`, which is fine to start with.

Things Hydra does _not_ do here, on purpose:

- It does not change your working directory. Relative paths in your script
  behave normally.
- It does not touch your function's return value or arguments beyond `cfg`.

---

## 5. Logging: what to write and how (5 min)

_Say:_ Structured logging has one rule. Put data in fields, not in the message
string.

```python
# Do this
log.info("epoch_done", epoch=epoch, loss=loss, elapsed_s=dt)

# Not this
log.info(f"Epoch {epoch} done, loss {loss:.3f} in {dt}s")
```

Both look similar on the console. The first one is also a JSON object you can
filter, plot, and compare across runs. The second one is a string you will be
parsing with regexes in six months.

**Naming events.** Use a short `snake_case` phrase that says what happened:
`start`, `data_loaded`, `epoch_done`, `checkpoint_saved`, `failed_step`. Reuse
the same name every time the same thing happens. That is what makes
`--event epoch_done` useful later.

**Levels.** Four you will use:

| Call                 | When                                                        |
| -------------------- | ----------------------------------------------------------- |
| `log.debug(...)`     | Detail you want only when investigating. Hidden by default. |
| `log.info(...)`      | Normal progress. The default level.                         |
| `log.warning(...)`   | Something odd that did not stop the run.                    |
| `log.exception(...)` | Inside an `except` block. Attaches the traceback.           |

**Errors.** Call `log.exception` inside the `except`, and the traceback goes to
the console and into the JSON file:

```python
try:
    result = step(batch)
except Exception:
    log.exception("failed_step", step=i, batch_size=len(batch))
    raise
```

**Bind values you would otherwise repeat:**

```python
log = get_logger(__name__)
run_log = log.bind(trial=trial_id, seed=seed)
run_log.info("start")          # trial=... seed=... appear automatically
run_log.info("epoch_done", epoch=0)
```

**Where each thing goes.** Two destinations, configured for you:

| Destination                   | Format                      | Contains                                                      |
| ----------------------------- | --------------------------- | ------------------------------------------------------------- |
| Console / SLURM `.log`        | one readable line per event | what you passed on the call                                   |
| `<script>.log` in the run dir | one JSON object per line    | everything, plus hostname and SLURM job context on every line |

The console hides the SLURM job id and hostname on every line because they never
change within a run. They are printed once at startup and stored on every JSON
line, where a script reading many runs at once needs them.

`print` still works and still shows on the console, but it is not in the JSON
file and has no timestamp. Use it for nothing you will want later.

---

## 6. Live demo: reading logs afterwards (4 min)

_Say:_ The JSON file is for machines. `ornlkit logs` is for you.

```bash
ornlkit logs list                       # every run under outputs/ and runs/
ornlkit logs list --roots multirun      # sweeps live under multirun/
```

```
outputs/2026-09-13/20-51-42  (1 log file(s)) - model.lr=0.01
outputs/2026-09-13/20-51-44  (1 log file(s)) - +model.dropout=0.1
```

Each run is listed with the overrides that produced it. That is usually enough
to find the one you want.

```bash
ornlkit logs show outputs/2026-09-13/20-51-42
ornlkit logs show outputs/2026-09-13/20-51-42 --event epoch_done
ornlkit logs show outputs/2026-09-13/20-51-42 --level error
ornlkit logs tail outputs/2026-09-13/20-51-42 -n 5
```

Output is the same readable format as the console, with the run context printed
once as a header:

```
# hostname=frontier01234 slurm_job_id=1234567 slurm_nnodes=2 ...
20:51:44 [error    ] failed_step              [train] step=divide
Traceback (most recent call last):
  ...
ZeroDivisionError: division by zero
```

For analysis, add `--json` or `-c` and pipe into `jq`, or read the file straight
into Polars:

```python
import polars as pl
df = pl.read_ndjson("outputs/2026-09-13/20-51-42/train.log")
df.filter(pl.col("event") == "epoch_done").select("epoch", "loss")
```

_Say:_ This is the payoff of structured logging. Loss curves across a sweep are
a one-liner, not a parsing project.

---

## 7. Running on Frontier (4 min)

_Say:_ Nothing in your script changes. The decorator notices SLURM.

Inside a job, the `slurm` startup line becomes:

```
00:46:19 [info     ] slurm                    active=True cluster_name=frontier job_id=1234567 nnodes=2 nodelist=frontier[01234-01235] ntasks=16
```

and every JSON line carries `slurm_job_id`, `slurm_nodelist`, and `hostname`. If
you `srun` many ranks into one log, you can still tell them apart.

Minimal batch script (a fuller smoke-test version lives in the ornlkit-frontier repository):

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

Two conventions worth copying:

- **One tree per experiment.** SLURM stdout at `runs/myexp/<jobid>.log`, Hydra
  output at `runs/myexp/<jobid>/`. `ornlkit logs list` finds the latter.
- **Pass `"$@"` through.** Then `sbatch job.sbatch model.lr=0.01` works, and the
  override is recorded in `.hydra/overrides.yaml`.

Setup is covered in the ornlkit-frontier repository. The short version: its `sync` recipe
builds `.venv-frontier/` once on a login node, and compute nodes use it directly
with no `uv` involved.

---

## 8. Pitfalls to mention (2 min)

- **Timestamps are local time with an offset** in the JSON file, e.g.
  `2026-09-13T20:51:42.123456-04:00`. Polars needs a hint to parse them:
  `pl.col("timestamp").str.to_datetime(time_zone="UTC")`.
- **`debug` is hidden by default.** If your debug lines do not appear, that is
  why. Lower the level with `hydra.verbose=true` on the command line, or keep to
  `info` for anything you might want.
- **Keep values flat.** `log.info("stats", mean=m, std=s)` reads well.
  `log.info("stats", stats={"mean": m, "std": s})` works but prints a dict
  literal on the console. Nested data belongs in the JSON file only if you will
  read it back programmatically.
- **Do not log huge things.** An array or DataFrame passed as a field is
  serialised in full into the JSON file on every call.
- **`multirun/` is not searched by default.** Use
  `ornlkit logs list --roots multirun`, or set `hydra.sweep.dir` to put sweeps
  under `runs/`.
- **Config keys are strict.** `model.lr` must exist in the YAML to be
  overridden. Use `+model.lr` to add one. This trips everyone exactly once.

---

## 9. Closing: what to do next (1 min)

_Say:_ Three steps to try this on your own script this week.

1. Copy the `train.py` and `conf/config.yaml` skeleton from slide 2. Move your
   hard-coded constants into the YAML.
2. Replace every `print` with `log.info("what_happened", key=value)`.
3. Run it twice with different overrides, then run `ornlkit logs list`.

If those three steps take more than an hour, that is a bug in ornlkit. Tell me.

---

## Appendix: demo checklist

The demo lives in `examples/quickstart/`. Its README lists ten commands in
the order they appear in these notes.

Before the talk:

- [ ] `uv run python examples/quickstart/train.py` works on the machine you
      will present from.
- [ ] Terminal at 100+ columns and a large font. The `environment` line is the
      longest and wraps at 80.
- [ ] `rm -rf outputs multirun` so `logs list` shows only what the demo
      creates.
- [ ] One pre-run Frontier job with its `runs/myexp/<jobid>/` directory copied
      locally, for the `slurm active=True` slide if the queue is slow.

Demo order: run once, show the tree, override, typo, warning (`model.lr=4.0`),
error (`demo.fail_at_epoch=2`), `--cfg job`, sweep, `logs list`,
`logs show --event`, `logs show --level error`, Polars pivot.
