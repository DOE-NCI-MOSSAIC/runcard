# Quickstart example

A tiny experiment that fits a line to noisy data with gradient descent. The
science is deliberately trivial; the point is the shape of the script and
what you get for free from `@ornlkit_main`.

```
examples/quickstart/
├── train.py           # the experiment: ~60 lines, one decorator, one logger
├── conf/config.yaml   # every parameter, overridable from the command line
└── README.md
```

Run it from the repository root. Output lands in `outputs/<date>/<time>/`
under the current directory.

## Demo sequence

Each step introduces one idea. Run them in order.

**1. Run with defaults.** Three environment lines, then one line per epoch.

```bash
uv run python examples/quickstart/train.py
```

**2. Look at what was written.** The exact config, the overrides, and a JSON
log with one event per line.

```bash
ls -R outputs/$(date +%F) | head
cat outputs/$(date +%F)/*/.hydra/config.yaml
```

**3. Override a parameter.** No file edits.

```bash
uv run python examples/quickstart/train.py model.lr=0.9 model.epochs=10
```

**4. Make a typo.** Hydra refuses unknown keys.

```bash
uv run python examples/quickstart/train.py model.lrr=0.9
```

**5. Trigger a warning.** A learning rate that is too high makes the loss
grow, and the script logs `loss_increased` at warning level.

```bash
uv run python examples/quickstart/train.py model.lr=4.0
```

**6. Trigger an error.** The config has a `demo.fail_at_epoch` knob. The
traceback is printed on the console and stored in the JSON file.

```bash
uv run python examples/quickstart/train.py demo.fail_at_epoch=2
```

**7. Sweep.** Three runs, one per learning rate, under `multirun/`.

```bash
uv run python examples/quickstart/train.py -m model.lr=0.1,0.5,4.0
```

**8. Find runs afterwards.** Each run is listed with the overrides that
produced it.

```bash
uv run ornlkit logs list
uv run ornlkit logs list --roots multirun
```

**9. Read one run back.** Same format as the console. Filter by event or
level.

```bash
uv run ornlkit logs show outputs/<date>/<time>
uv run ornlkit logs show outputs/<date>/<time> --event epoch_done
uv run ornlkit logs show outputs/<date>/<time> --level error
```

**10. Analyse a sweep with Polars.** Loss per epoch, one column per run.

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

```
┌───────┬────────┬────────┬──────────┐
│ epoch ┆ 0      ┆ 1      ┆ 2        │
╞═══════╪════════╪════════╪══════════╡
│ 0     ┆ 1.9133 ┆ 1.0241 ┆ 5.788    │
│ 1     ┆ 1.6795 ┆ 0.5065 ┆ 15.6058  │
│ 2     ┆ 1.4755 ┆ 0.275  ┆ 42.3329  │
│ 3     ┆ 1.2977 ┆ 0.1714 ┆ 115.0924 │
│ 4     ┆ 1.1427 ┆ 0.1251 ┆ 313.1665 │
└───────┴────────┴────────┴──────────┘
```

Timestamps in the JSON file carry a UTC offset. To parse them, pass a
time zone: `pl.col("timestamp").str.to_datetime(time_zone="UTC")`.

## Adapting it

1. Copy this directory next to your own code.
2. Move your constants into `conf/config.yaml`.
3. Replace `print` with `log.info("what_happened", key=value)`.

Before the demo, clear old output so `logs list` shows only what you
create: `rm -rf outputs multirun`.
