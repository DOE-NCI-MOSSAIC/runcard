# Logging: what to write and where it goes

Structured logging has one rule. Put data in fields, not in the message
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

## Naming events

Use a short `snake_case` phrase that says what happened: `start`,
`data_loaded`, `epoch_done`, `checkpoint_saved`, `failed_step`. Reuse the same
name every time the same thing happens. That is what makes
`--event epoch_done` useful later.

## Levels

| Call                 | When                                                        |
| -------------------- | ----------------------------------------------------------- |
| `log.debug(...)`     | Detail you want only when investigating. Hidden by default. |
| `log.info(...)`      | Normal progress. The default level.                         |
| `log.warning(...)`   | Something odd that did not stop the run.                    |
| `log.exception(...)` | Inside an `except` block. Attaches the traceback.           |

Call `log.exception` inside the `except`, and the traceback goes to the
console and into the JSON file:

```python
try:
    result = step(batch)
except Exception:
    log.exception("failed_step", step=i, batch_size=len(batch))
    raise
```

## Bind values you would otherwise repeat

```python
log = get_logger(__name__)
run_log = log.bind(trial=trial_id, seed=seed)
run_log.info("start")          # trial=... seed=... appear automatically
run_log.info("epoch_done", epoch=0)
```

## Where each thing goes

Two destinations, configured for you:

| Destination                   | Format                      | Contains                                                      |
| ----------------------------- | --------------------------- | ------------------------------------------------------------- |
| Console / SLURM `.log`        | one readable line per event | what you passed on the call                                   |
| `<script>.log` in the run dir | one JSON object per line    | everything, plus hostname and SLURM job context on every line |

The console hides the SLURM job id and hostname on every line because they
never change within a run. They are printed once at startup and stored on
every JSON line, where a script reading many runs at once needs them.

`print` still works and still shows on the console, but it is not in the JSON
file and has no timestamp. Use it for nothing you will want later.

## Pitfalls

**Timestamps are local time with an offset**
:   e.g. `2026-09-13T20:51:42.123456-04:00`. Polars needs a hint to parse
    them: `pl.col("timestamp").str.to_datetime(time_zone="UTC")`.

**`debug` is hidden by default.**
:   If your debug lines do not appear, that is why. Lower the level with
    `hydra.verbose=true` on the command line, or keep to `info` for anything
    you might want.

**Keep values flat.**
:   `log.info("stats", mean=m, std=s)` reads well.
    `log.info("stats", stats={"mean": m, "std": s})` works but prints a dict
    literal on the console. Nested data belongs in the JSON file only if you
    will read it back programmatically.

**Do not log huge things.**
:   An array or DataFrame passed as a field is serialised in full into the
    JSON file on every call.

**`multirun/` is not searched by default.**
:   Use `runcard logs list --roots multirun`, or set `hydra.sweep.dir` to put
    sweeps under `runs/`.

**Config keys are strict.**
:   `model.lr` must exist in the YAML to be overridden. Use `+model.lr` to
    add one. This trips everyone exactly once.
