# OLCF Quickstart

This guide covers how to use ornlkit on OLCF systems (Frontier, Andes).

## Prerequisites

- OLCF account and project allocation
- Project directory at `/ccs/proj/<project_id>/<user_id>`

## Option A: UV + System Python (no container)

The lightest-weight approach. Works for pure Python workloads that don't need
custom system-level dependencies.

```bash
# 1. Install UV to your project space (one-time setup)
curl -LsSf https://astral.sh/uv/install.sh | env CARGO_HOME=/ccs/proj/<project_id>/$USER/.cargo UV_INSTALL_DIR=/ccs/proj/<project_id>/$USER/.local/bin sh

# Add to your PATH in ~/.bashrc (but NOT via conda init)
export PATH="/ccs/proj/<project_id>/$USER/.local/bin:$PATH"

# 2. Load the system Python
#    Frontier:
module load miniforge3/23.11.0-0
#    Andes:
module load miniforge3/24.11.3-2

# 3. Clone and sync
cd /ccs/proj/<project_id>/$USER
git clone <repo-url> ornlkit
cd ornlkit
uv sync

# 4. Run
uv run pytest
uv run python3 your_script.py
```

### In a batch script

Run `just sync` on the login node first to create `.venv-frontier/` with
miniforge3 Python. Then use the venv directly in batch scripts — no uv needed on
compute nodes:

```bash
#!/bin/bash
#SBATCH -A <project_id>
#SBATCH -J ornlkit-job
#SBATCH -N 1
#SBATCH -t 00:30:00

module load miniforge3/23.11.0-0
export TMPDIR="/tmp"

cd /ccs/proj/<project_id>/$USER/ornlkit
.venv-frontier/bin/python3 your_script.py
```

## Option B: Apptainer Container (built locally)

Use this when you need a fully reproducible environment or custom system-level
dependencies. Build on your local machine where Nix is available, then transfer.

### Build with Nix

```bash
# On your local machine
nix build .#frontier-image
apptainer build frontier.sif docker-archive://result
```

### Build with Apptainer directly

```bash
# On your local machine (or on Frontier itself)
apptainer build frontier.sif containers/frontier.def
```

### Transfer to Frontier

```bash
scp frontier.sif <user>@frontier.olcf.ornl.gov:/ccs/proj/<project_id>/$USER/
```

### Run on Frontier

```bash
# Interactive shell
apptainer shell /ccs/proj/<project_id>/$USER/frontier.sif

# Run a script
apptainer exec /ccs/proj/<project_id>/$USER/frontier.sif python3 your_script.py

# With GPU + MPI support
module load apptainer-enable-gpu apptainer-enable-mpi
srun -N 1 -n 8 --gpus-per-task=1 \
    apptainer exec /ccs/proj/<project_id>/$USER/frontier.sif python3 your_script.py
```

### In a batch script

```bash
#!/bin/bash
#SBATCH -A <project_id>
#SBATCH -J ornlkit-container
#SBATCH -N 2
#SBATCH -t 01:00:00

module load apptainer-enable-gpu
module load apptainer-enable-mpi

IMG=/ccs/proj/<project_id>/$USER/frontier.sif

srun -N 2 -n 16 --gpus-per-task=1 \
    apptainer exec "$IMG" python3 your_script.py
```

## Option C: Build the container on Frontier

If you can't build locally, Apptainer is available directly on Frontier. The
`.def` file does not require Nix.

```bash
cd /ccs/proj/<project_id>/$USER/ornlkit
apptainer build frontier.sif containers/frontier.def
```

Note: this will pull packages from the internet during build, so run it on a
login node (not a compute node).

## Tips

### Storage locations

| Path                            | Use for                               | Notes                                     |
| ------------------------------- | ------------------------------------- | ----------------------------------------- |
| `/ccs/proj/<project_id>/$USER/` | Environments, containers, shared data | NFS, no purge, visible to project members |
| `$MEMBERWORK/<project_id>/`     | Job scratch data                      | Lustre, purged after 90 days              |
| `/mnt/bb/$USER/` (Frontier)     | NVMe burst buffer                     | Fast local storage during jobs            |

### Performance: large environments

For jobs that import many Python packages, copying the container to NVMe can
significantly reduce startup time:

```bash
#!/bin/bash
#SBATCH ...
sbcast --send-libs /ccs/proj/<project_id>/$USER/frontier.sif /mnt/bb/$USER/frontier.sif
srun apptainer exec /mnt/bb/$USER/frontier.sif python3 your_script.py
```

### Avoiding common pitfalls

- **Do not** run `conda init` — it hardcodes paths and breaks multi-system use
- **Do not** install into the base conda environment
- **Do not** load the miniforge3 module twice in one session
- **Do** use `python3` explicitly (bare `python` is not available)
- **Do** clean caches regularly to avoid quota issues:
  ```bash
  pip cache purge
  conda clean -a
  uv cache clean
  ```
- **Do** use unbuffered output for logging: `python3 -u your_script.py`

### Rust on OLCF

Rust is not provided via modules. Two options:

1. **User-space rustup** (redirect to project storage):

   ```bash
   export RUSTUP_HOME=/ccs/proj/<project_id>/$USER/.rustup
   export CARGO_HOME=/ccs/proj/<project_id>/$USER/.cargo
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```

2. **Inside a container** — the Apptainer image already includes the Rust
   toolchain.
