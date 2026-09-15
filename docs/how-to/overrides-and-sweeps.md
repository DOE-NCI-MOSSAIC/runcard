# Override parameters and sweep

Hydra is the config framework underneath `@experiment`. You will use about
four features of it.

## Override any value on the command line

```bash
uv run python train.py model.lr=0.01
uv run python train.py model.lr=0.01 model.epochs=10 data.n_rows=50000
```

Dotted path into the YAML, equals sign, value. That is the whole syntax.

## Typos are caught

Hydra refuses keys that are not in the file:

```
Could not override 'model.lrr'.
To append to your config use +model.lrr=0.01
Key 'lrr' is not in struct
```

This is a feature. A misspelled parameter fails immediately instead of
silently running with the default.

## Add a key that is not in the file

Use a leading `+`:

```bash
uv run python train.py +model.dropout=0.1
```

## Print the effective config without running

```bash
uv run python train.py --cfg job
```

## Sweep

`-m` (multirun) with comma-separated values runs the script once per value,
each in its own directory under `multirun/`:

```bash
uv run python train.py -m model.lr=0.1,0.01,0.001
```

Combine two swept parameters and you get the cross product.

## Choose where output goes

```bash
uv run python train.py hydra.run.dir=runs/my-experiment/trial-7
```

The default is `outputs/<date>/<time>/`, which is fine to start with. Sweeps
default to `multirun/<date>/<time>/<n>/`; set `hydra.sweep.dir` to put them
somewhere `runcard logs list` searches by default.

!!! note "What Hydra does not do here"
    It does not change your working directory, so relative paths in your
    script behave normally. It does not touch your function's return value
    or arguments beyond `cfg`.
