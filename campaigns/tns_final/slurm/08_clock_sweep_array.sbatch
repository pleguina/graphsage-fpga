#!/usr/bin/env bash
#SBATCH --job-name=tns-clock-sweep
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --array=0-4
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=campaigns/tns_final/logs/clock_sweep_%A_%a.out
#SBATCH --error=campaigns/tns_final/logs/clock_sweep_%A_%a.err

# Routed clock-frequency sweep (plan Section 11). 2.77 ns already exists as
# A5/R1 (qat_dsp_V2A1_allcut_ssi_retime_route) and is intentionally excluded
# from this array. Same frozen A4 RTL, same final physical strategy.
set -euo pipefail

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
cd "$ROOT"
mkdir -p campaigns/tns_final/logs

declare -a TAGS=(clk300 clk290 clk280 clk272 clk267)
declare -a PERIODS=(3.00 2.90 2.80 2.72 2.67)

IDX="${SLURM_ARRAY_TASK_ID}"
TAG="${TAGS[$IDX]}"
PERIOD="${PERIODS[$IDX]}"

export INPUT_CHECKPOINT="$ROOT/build/vivado_sweep/qat_dsp_V2A1_allcut_post_synth.dcp"
export RUN_NAME="qat_dsp_V2A1_allcut_ssi_retime_route_${TAG}"
export PLACE_DIRECTIVE=SSI_SpreadLogic_high
export ROUTE_DIRECTIVE=Default
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1
export POST_PLACE_PHYS_DIRECTIVE=""
export USE_RETIME=1
export CLOCK_PERIOD_NS="$PERIOD"

echo "CLOCK_SWEEP_VARIANT=$TAG PERIOD_NS=$PERIOD"

"$VIVADO_BIN" -mode batch \
    -source hls/run_vivado_int8_po2_strategy.tcl \
    -log "build/vivado_sweep/${RUN_NAME}_vivado.log" \
    -journal "build/vivado_sweep/${RUN_NAME}_vivado.jou"
