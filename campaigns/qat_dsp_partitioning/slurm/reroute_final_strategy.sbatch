#!/usr/bin/env bash
#SBATCH --job-name=qat-seed-final-route
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=campaigns/qat_dsp_partitioning/logs/reroute_final_%j.out
#SBATCH --error=campaigns/qat_dsp_partitioning/logs/reroute_final_%j.err

set -euo pipefail
: "${VARIANT_NAME:?Missing VARIANT_NAME}"

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export XILINX_LOCAL_USER_DATA="${XILINX_LOCAL_USER_DATA:-${SLURM_TMPDIR:-/tmp/$USER}/xilinx_user_data}"

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

# Reruns place+route on an EXISTING post-synthesis checkpoint using the same
# final validated physical strategy as A5 (SSI_SpreadLogic_high + retime).
# No HLS/synthesis is redone here.
export INPUT_CHECKPOINT="$ROOT/build/vivado_sweep/qat_dsp_${VARIANT_NAME}_post_synth.dcp"
export RUN_NAME="qat_dsp_${VARIANT_NAME}_ssi_retime_route"
export PLACE_DIRECTIVE=SSI_SpreadLogic_high
export ROUTE_DIRECTIVE=Default
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1
export POST_PLACE_PHYS_DIRECTIVE=""
export USE_RETIME=1

cd "$ROOT"
mkdir -p campaigns/qat_dsp_partitioning/logs "$XILINX_LOCAL_USER_DATA"
"$VIVADO_BIN" -mode batch -nolog -nojournal -source hls/run_vivado_int8_po2_strategy.tcl
