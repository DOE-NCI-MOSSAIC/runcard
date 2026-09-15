# runcard (CLI)

```
runcard [-V | --version] [-h | --help]
runcard check [OVERRIDES...]
runcard logs list [--roots ROOT ...]
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

Print every run directory under the given roots with the number of log
files and the overrides recorded in `.hydra/overrides.yaml`. On a terminal
this is a table; when piped, one plain line per run.

`--roots ROOT ...`
:   Directories to search. Default: `outputs` and `runs`. Sweeps live under
    `multirun`, which is not searched unless you ask.

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
