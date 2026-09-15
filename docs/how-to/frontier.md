# Run on Frontier

Nothing in your script changes. Inside a job, the `slurm` startup line
becomes:

```
00:46:19 [info     ] slurm                    active=True cluster_name=frontier job_id=1234567 nnodes=2 nodelist=frontier[01234-01235] ntasks=16
```

and every JSON line carries `slurm_job_id`, `slurm_nodelist`, and
`hostname`. If you `srun` many ranks into one log, you can still tell them
apart.

## Minimal batch script

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

**One tree per experiment.**
:   SLURM stdout at `runs/myexp/<jobid>.log`, Hydra output at
    `runs/myexp/<jobid>/`. `runcard logs list` finds the latter.

**Pass `"$@"` through.**
:   Then `sbatch job.sbatch model.lr=0.01` works, and the override is recorded
    in `.hydra/overrides.yaml`.

## Environment setup

Building `.venv-frontier/` once on a login node, interactive submission with
`just`, and the Apptainer container are covered by the companion repository
[runcard-frontier](https://github.com/adanoelle/runcard-frontier). The short
version: its `sync` recipe creates the venv with the miniforge3 Python, and
compute nodes use it directly with no `uv` involved.
