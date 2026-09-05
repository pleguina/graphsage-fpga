#!/usr/bin/env bash
#SBATCH --job-name=graphsage-paths
#SBATCH --partition=batch
#SBATCH --nodelist=gae034
#SBATCH --array=0-9
#SBATCH --cpus-per-task=1
#SBATCH --mem=12G
#SBATCH --time=04:00:00
#SBATCH --output=slurm/logs/path_classes_%A_%a.out
#SBATCH --error=slurm/logs/path_classes_%A_%a.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the extracted bundle root}"
RUNS=(
    screen_baseline
    screen_extra_net_delay_high
    screen_altspread_high
    screen_altspread_medium
    screen_ssi_spread_high
    screen_ssi_balance_sll
    screen_ssi_spread_sll
    screen_ssi_balance_slr
    screen_extra_timing
    screen_extra_postplace
)

cd "$ROOT"

if [[ -z "${VIVADO_BIN:-}" || ! -x "$VIVADO_BIN" ]]; then
    echo "Set VIVADO_BIN to the Vivado executable." >&2
    exit 1
fi

export RUN_NAME="${RUNS[$SLURM_ARRAY_TASK_ID]}"
"$VIVADO_BIN" \
    -mode batch \
    -source hls/report_vivado_post_place_path_classes.tcl \
    -log "build/vivado_sweep/$RUN_NAME/path_classes.log" \
    -journal "build/vivado_sweep/$RUN_NAME/path_classes.jou"