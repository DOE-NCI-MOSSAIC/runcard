# Why a run card

Most experiment scripts start like this and stay like this:

```python
LR = 0.001
DATA = "/lustre/orion/proj/data.parquet"

print("starting...")
print(f"lr={LR}")
# ... three weeks later: which run had lr=0.01? which node did it crash on?
```

Three things go wrong.

**Parameters live in the code.**
:   Changing one means editing the file, and the value that produced a result
    is gone once you edit it again.

**Output is `print`.**
:   It goes to the SLURM log and nowhere else, mixed in with everything else,
    with no timestamp and no way to filter.

**Nothing records the environment.**
:   Which Python, which node, which package versions. When a job behaves
    differently on Frontier than on your laptop, you have no evidence.

## The run card

In event generators such as MadGraph and Pythia, the *run card* is the one
file that fully specifies a run, and sharing it is how someone else reproduces
your result. `runcard` gives every script that file. `conf/config.yaml` holds
every parameter; the decorator snapshots it into the run directory alongside
the overrides you typed; the JSON log is the receipt for what happened under
those parameters.

That framing puts the config first. The logging is there to make the record
complete, not the other way round.

## What the decorator does

`@experiment` wraps `hydra.main` and, on each run:

1. Parses the command line into overrides and creates a directory for this
   run.
2. Saves the effective config and the overrides under `.hydra/`.
3. Configures logging so the console gets one readable line per event and
   the run directory gets one JSON object per event.
4. Binds the hostname and any SLURM job variables so every JSON line carries
   them.
5. Logs three startup events: `environment`, `slurm`, and `packages`.

Then it calls your function with `cfg`. Nothing else in the script has to
change.
