# runcard logs

Inspect structured log files from Hydra runs. A *run* is a directory with a
`.hydra/` subdirectory; every command also accepts a `.log` file path
directly.

```
runcard logs list [--roots ROOT ...]
runcard logs show RUN [--event NAME] [--level LEVEL] [--json | -c]
runcard logs tail RUN [-n N] [--json | -c]
```

## `list`

Print every run directory under the given roots, newest last, with the
number of log files and the overrides recorded in `.hydra/overrides.yaml`.

`--roots ROOT ...`
:   Directories to search. Default: `outputs` and `runs`. Sweeps live under
    `multirun`, which is not searched unless you ask.

## `show`

Print the events from one run in the console format, with the run context
(hostname, SLURM variables) as a single header line.

`--event NAME`
:   Only events whose name is `NAME`.

`--level LEVEL`
:   Only events at `LEVEL` (`info`, `warning`, `error`, ...).

`--json`
:   Pretty-printed JSON, one event per block.

`-c`, `--compact`
:   One JSON object per line, for `jq` or Polars.

## `tail`

Like `show`, but only the last `N` events.

`-n N`
:   Number of events. Default: 10.

## Exit status

`show` and `tail` exit with status 1 when no log files are found. `list`
prints a message and exits 0 when no runs exist.
