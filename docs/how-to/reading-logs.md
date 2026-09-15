# Read logs back

The JSON file in each run directory is for machines. `runcard logs` is for
you.

## Find runs

```bash
runcard logs list                       # every run under outputs/ and runs/
runcard logs list --roots multirun      # sweeps live under multirun/
```

```
Run                          Status     Duration  Overrides
outputs/2026-09-13/20-51-42  finished       3.2s  model.lr=0.01
outputs/2026-09-13/20-51-44  failed         0.4s  +model.dropout=0.1
```

Each run is listed with how it ended and the overrides that produced it.
That is usually enough to find the one you want. For one run at a glance:

```bash
runcard logs summary outputs/2026-09-13/20-51-42
```

## Read one run

```bash
runcard logs show outputs/2026-09-13/20-51-42
runcard logs show outputs/2026-09-13/20-51-42 --event epoch_done
runcard logs show outputs/2026-09-13/20-51-42 --level error
runcard logs tail outputs/2026-09-13/20-51-42 -n 5
```

Output is the same readable format as the console, with the run context
printed once as a header:

```
# hostname=frontier01234 slurm_job_id=1234567 slurm_nnodes=2 ...
20:51:44 [error    ] failed_step              [train] step=divide
Traceback (most recent call last):
  ...
ZeroDivisionError: division by zero
```

## Analyse with Polars

Add `--json` or `-c` to pipe into `jq`, or read the file straight into
Polars:

```python
import polars as pl

df = pl.read_ndjson("outputs/2026-09-13/20-51-42/train.log")
df.filter(pl.col("event") == "epoch_done").select("epoch", "loss")
```

Loss per epoch across a sweep, one column per run:

```python
import glob

import polars as pl

frames = []
for path in sorted(glob.glob("multirun/*/*/*/train.log")):
    run = path.split("/")[-2]
    frames.append(pl.read_ndjson(path).with_columns(run=pl.lit(run)))

df = pl.concat(frames, how="diagonal")
print(df.filter(pl.col("event") == "epoch_done").pivot(on="run", index="epoch", values="loss"))
```

!!! tip "Timestamps"
    Timestamps in the JSON file are local time with a UTC offset, e.g.
    `2026-09-13T20:51:42.123456-04:00`. Polars needs a hint to parse them:
    `pl.col("timestamp").str.to_datetime(time_zone="UTC")`.
