#!/usr/bin/env bash
#SBATCH --job-name=graphsage-screen
#SBATCH --partition=batch
#SBATCH --nodelist=gae034
#SBATCH --array=0-9%1
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=exploration/slurm/logs/screen_%A_%a.out
#SBATCH --error=exploration/slurm/logs/screen_%A_%a.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the extracted bundle root}"
STRATEGIES=(
    baseline
    extra_net_delay_high
    altspread_high
    altspread_medium
    ssi_spread_high
    ssi_balance_sll
    ssi_spread_sll
    ssi_balance_slr
    extra_timing
    extra_postplace
)

mkdir -p "$ROOT/exploration/slurm/logs"
cd "$ROOT"

if [[ -z "${VIVADO_BIN:-}" ]]; then
    VIVADO_BIN="$(command -v vivado || true)"
fi
if [[ -z "$VIVADO_BIN" || ! -x "$VIVADO_BIN" ]]; then
    echo "Set VIVADO_BIN to the Vivado executable." >&2
    exit 1
fi
export VIVADO_BIN

python3 exploration/scripts/run_vivado_int8_po2_sweep.py screen \
    --runs "${STRATEGIES[$SLURM_ARRAY_TASK_ID]}" --no-collect