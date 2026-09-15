# runcard justfile — dev workflows
#
# Frontier submission recipes live in the runcard-frontier repository:
#   just -f ../runcard-frontier/justfile sync
#   just -f ../runcard-frontier/justfile submit account=ABC123

job_name := "runcard"

# List available recipes
default:
    @just --list

# Run pytest
test *args:
    uv run pytest {{ args }}

# Lint with ruff
lint:
    uv run ruff check .

# Format with ruff
fmt:
    uv run ruff format . && uv run ruff check --fix .

# Type-check with ty
typecheck:
    uv run ty check

# Run lint, typecheck, and tests
check: lint typecheck test

# Local run with unified output dir
run *hydra_args:
    #!/usr/bin/env bash
    set -euo pipefail
    timestamp=$(date +%Y%m%d-%H%M%S)
    run_dir="runs/{{ job_name }}/local-${timestamp}"
    mkdir -p "${run_dir}"
    uv run runcard hydra.run.dir="${run_dir}" {{ hydra_args }}

# Run the quickstart example
quickstart *hydra_args:
    uv run python examples/quickstart/train.py {{ hydra_args }}

# Remove all runs
clean-runs:
    rm -rf runs/

# Remove legacy output dirs (outputs/, multirun/, logs/)
clean-legacy:
    rm -rf outputs/ multirun/ logs/

# Remove all generated output
clean: clean-runs clean-legacy
