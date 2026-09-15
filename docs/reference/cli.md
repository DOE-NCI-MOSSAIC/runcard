# runcard (CLI)

```
runcard [-V | --version] [-h | --help]
runcard check [OVERRIDES...]
runcard logs list [--roots ROOT ...]
runcard logs summary RUN [--event NAME] [--json]
runcard logs show RUN [--event NAME] [--level LEVEL] [--json | -c]
runcard logs tail RUN [-n N] [--json | -c]
```

## Tab completion

One command installs completion for your shell (bash, zsh, or fish are
detected automatically):

```bash
runcard --install-completion
```

Then open a new shell. Completion is context-aware:

- `RUN` completes to run directories found under `outputs/`, `runs/`, and
  `multirun/`, falling back to ordinary directory completion elsewhere.
- `--event` completes to the event names actually present in the run you
  named.
- `--level` completes to the log levels.

`runcard --show-completion` prints the script instead of installing it, for
dotfiles managed by hand.

## `check`

Run a one-line experiment to verify the environment: the three startup
events and one `greeting`. Anything after `check` is passed to Hydra as an
override, so this doubles as a way to test overrides and output locations.

```bash
runcard check
runcard check app.greeting=Hi hydra.run.dir=runs/smoke
runcard check --cfg job          # print the effective config, run nothing
```

## `logs list`

Print every run directory under the given roots with its status, duration,
and the overrides recorded in `.hydra/overrides.yaml`. On a terminal this is
a table; when piped, one tab-separated line per run.

Status comes from the events `@experiment` writes at the end of every run,
so it does not depend on what your script logs:

| Status | Meaning |
|---|---|
| `finished` | The function returned. |
| `finished, N errors` | It returned, but `log.exception` or `log.error` was called N times. |
| `failed` | It raised; the traceback is in the log. |
| `running` | No end marker yet, and SLURM reports the job as running. |
| `running?` | No end marker, no SLURM answer, but the log changed in the last ten minutes. |
| `incomplete` | No end marker: the job was killed, or the run predates runcard's end events. |

Duration is the elapsed time reported by the end marker, or the span between
the first and last timestamps when there is none.

`--roots ROOT ...`
:   Directories to search. Default: `outputs` and `runs`. Sweeps live under
    `multirun`, which is not searched unless you ask.

## `logs summary`

One screen for a run: status, when it started and how long it took, where
it ran, the overrides, event counts by level, how the numeric fields of the
most frequent event moved from first to last, and the last event the script
logged. A failed run shows the exception's last line.

```
outputs/2026-09-15/10-00-00  finished
Started    2026-09-15 10:00:00-04:00    Duration  3.2s
Where      frontier01234 · python 3.12.13 · job 1234567 on 2 nodes
Overrides  model.lr=0.1 model.epochs=5
Events     12 · 1 warning · 0 errors
Progress   epoch_done ×5 · epoch 0 → 4 · loss 1.913 → 1.143
Last       done  final_loss=1.143 slope=1.39 true_slope=2.5
```

`--event NAME`
:   Report progress on `NAME` instead of the most frequent event.

`--json`
:   Emit the same information as a JSON object.

## `logs show`

Print the events from one run in the console format, with the run context
(hostname, SLURM variables) as a single header line. `RUN` is a directory
with a `.hydra/` subdirectory or a `.log` file.

`--event NAME`
:   Only events whose name is `NAME`.

`--level LEVEL`
:   Only events at `LEVEL` (`info`, `warning`, `error`, ...).

`--json`
:   Pretty-printed JSON, one event per block. Syntax-highlighted on a
    terminal, plain when piped.

`-c`, `--compact`
:   One JSON object per line, for `jq` or Polars.

## `logs tail`

Like `show`, but only the last `N` events.

`-n N`, `--lines N`
:   Number of events. Default: 10.

## Exit status

`show` and `tail` exit with status 1 when no log files are found. `list`
prints a message and exits 0 when no runs exist. Passing both `--json` and
`--compact` is a usage error.
