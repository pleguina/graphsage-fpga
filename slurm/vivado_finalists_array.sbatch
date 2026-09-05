#!/usr/bin/env bash
#SBATCH --job-name=graphsage-final
#SBATCH --partition=batch
#SBATCH --nodelist=gae034
#SBATCH --array=0-3%1
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=slurm/logs/finalist_%A_%a.out
#SBATCH --error=slurm/logs/finalist_%A_%a.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the extracted bundle root}"
FINALISTS=(
    ssi_spread_high
    ssi_spread_sll
    extra_net_delay_high
    baseline
)

cd "$ROOT"
mkdir -p slurm/logs

if [[ -z "${VIVADO_BIN:-}" || ! -x "$VIVADO_BIN" ]]; then
    echo "Set VIVADO_BIN to the Vivado executable." >&2
    exit 1
fi

export FINALIST_NAME="${FINALISTS[$SLURM_ARRAY_TASK_ID]}"
export SOURCE_RUN="screen_${FINALIST_NAME}"
mkdir -p "build/vivado_sweep/route_${FINALIST_NAME}"

"$VIVADO_BIN" \
    -mode batch \
    -source hls/run_vivado_finalist_route.tcl \
    -log "build/vivado_sweep/route_${FINALIST_NAME}/vivado.log" \
    -journal "build/vivado_sweep/route_${FINALIST_NAME}/vivado.jou"