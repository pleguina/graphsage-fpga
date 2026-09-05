#!/usr/bin/env bash
#SBATCH --job-name=graphsage-route
#SBATCH --partition=batch
#SBATCH --nodelist=gae034
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=36:00:00
#SBATCH --output=slurm/logs/route_%A_%a.out
#SBATCH --error=slurm/logs/route_%A_%a.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the extracted bundle root}"
mkdir -p "$ROOT/slurm/logs"
cd "$ROOT"

if [[ -z "${VIVADO_BIN:-}" ]]; then
    VIVADO_BIN="$(command -v vivado || true)"
fi
if [[ -z "$VIVADO_BIN" || ! -x "$VIVADO_BIN" ]]; then
    echo "Set VIVADO_BIN to the Vivado executable." >&2
    exit 1
fi
if [[ -z "${SWEEP_RUN:-}" ]]; then
    echo "Submit with SWEEP_RUN set to one strategy name." >&2
    exit 1
fi
export VIVADO_BIN

python3 scripts/run_vivado_int8_po2_sweep.py route \
    --runs "$SWEEP_RUN" --no-collect