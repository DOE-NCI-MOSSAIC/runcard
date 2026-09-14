# ornlkit

Portable data engineering toolkit for ORNL Frontier.

Python project managed with [UV](https://docs.astral.sh/uv/) and built on
Rust-backed libraries for performance: Polars, PyArrow, DataFusion, Pydantic,
orjson, and rustworkx. Linting and type checking via
[Ruff](https://docs.astral.sh/ruff/) and [ty](https://docs.astral.sh/ty/).

## Project structure

```
ornlkit/
├── flake.nix                 # Nix dev shell and container image
├── pyproject.toml             # Python project and tool configuration
├── rust-toolchain.toml        # Rust toolchain pinning
├── containers/
│   └── frontier.def           # Apptainer definition for Frontier
├── jobs/
│   └── hello.sbatch           # Frontier smoke-test batch script
├── examples/
│   └── quickstart/            # Minimal experiment to copy from (see its README)
├── src/ornlkit/               # Python package source
└── tests/                     # Test suite
```

## Local development

Requires [Nix](https://nixos.org/) with flakes enabled.

```bash
nix develop
uv sync
just check              # lint + typecheck + test
just run                # local smoke test → runs/ornlkit/local-*/
just run app.greeting="Hi"  # with Hydra overrides
```

## Usage on Frontier

There are two ways to run ornlkit on Frontier: directly with UV and the system
Python, or inside an Apptainer container.

### UV + system Python

Install UV to your project space (one time):

```bash
curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_INSTALL_DIR=/ccs/proj/<project_id>/$USER/.local/bin sh
export PATH="/ccs/proj/<project_id>/$USER/.local/bin:$PATH"
```

Clone, sync, and run:

```bash
module load miniforge3/23.11.0-0
cd /ccs/proj/<project_id>/$USER
git clone <repo-url> ornlkit && cd ornlkit
uv sync
uv run python3 your_script.py
```

Batch script:

```bash
#!/bin/bash
#SBATCH -A <project_id>
#SBATCH -N 1
#SBATCH -t 00:30:00

module load miniforge3/23.11.0-0
export PATH="/ccs/proj/<project_id>/$USER/.local/bin:$PATH"
cd /ccs/proj/<project_id>/$USER/ornlkit

uv run python3 your_script.py
```

### Apptainer container

Build on your local machine:

```bash
# Option 1: from the Nix flake
nix build .#frontier-image
apptainer build frontier.sif docker-archive://result

# Option 2: from the definition file (also works on Frontier login nodes)
apptainer build frontier.sif containers/frontier.def
```

Transfer and run:

```bash
scp frontier.sif <user>@frontier.olcf.ornl.gov:/ccs/proj/<project_id>/$USER/
```

```bash
# Interactive
apptainer shell /ccs/proj/<project_id>/$USER/frontier.sif

# With GPU and MPI
module load apptainer-enable-gpu apptainer-enable-mpi
srun -N 1 -n 8 --gpus-per-task=1 \
    apptainer exec /ccs/proj/<project_id>/$USER/frontier.sif python3 your_script.py
```

Batch script:

```bash
#!/bin/bash
#SBATCH -A <project_id>
#SBATCH -N 2
#SBATCH -t 01:00:00

module load apptainer-enable-gpu
module load apptainer-enable-mpi

IMG=/ccs/proj/<project_id>/$USER/frontier.sif

srun -N 2 -n 16 --gpus-per-task=1 \
    apptainer exec "$IMG" python3 your_script.py
```

## Smoke test

Submit a smoke-test job on Frontier using the justfile:

```bash
just submit account=ABC123
just submit account=ABC123 nodes=2 time=00:30:00 app.greeting="Hi"
just jobs                    # check job status
just last-log                # view most recent log
```

Output goes to a unified `runs/` directory:

```
runs/ornlkit/
  {jobid}.log                # SLURM stdout/stderr
  {jobid}/                   # Hydra output dir
    .hydra/config.yaml
    main.log
```

You can also run locally to preview the output:

```bash
just run                     # → runs/ornlkit/local-YYYYMMDD-HHMMSS/
```

For manual submission without the justfile, see `jobs/hello.sbatch`.

## Reference

See [OLCF.md](OLCF.md) for additional guidance on storage locations, NVMe
performance optimization, Rust installation, and common pitfalls.
