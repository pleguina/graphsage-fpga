#!/usr/bin/env bash
#SBATCH --job-name=tns-phys-strategy
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --array=0-1
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=campaigns/tns_final/logs/physical_strategy_%A_%a.out
#SBATCH --error=campaigns/tns_final/logs/physical_strategy_%A_%a.err

# Physical-strategy robustness sweep (plan Section 10, R2/R3).
# Reuses the frozen A4 RTL (qat_dsp_V2A1_allcut_post_synth.dcp) and only
# changes the Vivado placement directive, matching R1's retime policy.
set -euo pipefail

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
cd "$ROOT"
mkdir -p campaigns/tns_final/logs

declare -a TAGS=(altspread ssibalance)
declare -a PLACE_DIRECTIVES=(AltSpreadLogic_high SSI_BalanceSLRs)

IDX="${SLURM_ARRAY_TASK_ID}"
TAG="${TAGS[$IDX]}"
PLACE_DIRECTIVE="${PLACE_DIRECTIVES[$IDX]}"

export INPUT_CHECKPOINT="$ROOT/build/vivado_sweep/qat_dsp_V2A1_allcut_post_synth.dcp"
export RUN_NAME="qat_dsp_V2A1_allcut_${TAG}_retime_route"
export PLACE_DIRECTIVE
export ROUTE_DIRECTIVE=Default
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1
export POST_PLACE_PHYS_DIRECTIVE=""
export USE_RETIME=1

echo "PHYSICAL_STRATEGY_VARIANT=$TAG PLACE_DIRECTIVE=$PLACE_DIRECTIVE"

"$VIVADO_BIN" -mode batch \
    -source hls/run_vivado_int8_po2_strategy.tcl \
    -log "build/vivado_sweep/${RUN_NAME}_vivado.log" \
    -journal "build/vivado_sweep/${RUN_NAME}_vivado.jou"
