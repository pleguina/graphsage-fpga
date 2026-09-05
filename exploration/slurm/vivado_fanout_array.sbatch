#!/usr/bin/env bash
#SBATCH --job-name=graphsage-fanout
#SBATCH --partition=batch
#SBATCH --nodelist=gae034
#SBATCH --array=0-4%1
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=exploration/slurm/logs/fanout_%A_%a.out
#SBATCH --error=exploration/slurm/logs/fanout_%A_%a.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the extracted bundle root}"
FANOUT_TARGETS=(96 64 48 32 24)

cd "$ROOT"
mkdir -p exploration/slurm/logs

if [[ -z "${VIVADO_BIN:-}" || ! -x "$VIVADO_BIN" ]]; then
    echo "Set VIVADO_BIN to the Vivado executable." >&2
    exit 1
fi

export FORCE_MAX_FANOUT="${FANOUT_TARGETS[$SLURM_ARRAY_TASK_ID]}"
mkdir -p "build/vivado_sweep/fanout_${FORCE_MAX_FANOUT}"

"$VIVADO_BIN" \
    -mode batch \
    -source exploration/hls/run_vivado_fanout_replication.tcl \
    -log "build/vivado_sweep/fanout_${FORCE_MAX_FANOUT}/vivado.log" \
    -journal "build/vivado_sweep/fanout_${FORCE_MAX_FANOUT}/vivado.jou"