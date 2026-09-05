#!/usr/bin/env bash
#SBATCH --job-name=qat-po2-low-dsp-vivado
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=96G
#SBATCH --time=04:00:00
#SBATCH --output=slurm/logs/vivado_updated_qat_po2_low_dsp_%j.out
#SBATCH --error=slurm/logs/vivado_updated_qat_po2_low_dsp_%j.err

set -euo pipefail

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
PACKAGE_ROOT="$ROOT/transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
HLS_REPORT="$PACKAGE_ROOT/build/hls/cora_po2_qat_root_dynamic_const_weights_2024_1/solution1/syn/report/graphsage_po2_qat_root_dynamic_const_weights_csynth.xml"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"
BUILD_DIR="$ROOT/build/vivado_sweep/updated_qat_po2_low_dsp_build"
RUN_DIR="$ROOT/build/vivado_sweep/updated_qat_po2_low_dsp_route_default"
CHECKPOINT="$ROOT/build/vivado_sweep/updated_qat_po2_low_dsp_post_synth.dcp"

cd "$ROOT"
mkdir -p slurm/logs "$BUILD_DIR" "$RUN_DIR"

if [[ ! -f "$HLS_REPORT" ]]; then
    echo "Missing HLS report: $HLS_REPORT" >&2
    exit 1
fi

DSP_COUNT="$(sed -n 's:.*<DSP>\([0-9][0-9]*\)</DSP>.*:\1:p' "$HLS_REPORT" | head -n 1)"
if [[ -z "$DSP_COUNT" || "$DSP_COUNT" -gt 512 ]]; then
    echo "Refusing Vivado run: HLS DSP count is ${DSP_COUNT:-unknown}, limit is 512" >&2
    exit 1
fi
echo "HLS_DSP_GATE_PASS=$DSP_COUNT"

"$VIVADO_BIN" -mode batch \
    -source hls/build_vivado_updated_qat_po2_low_dsp_checkpoint.tcl \
    -log "$BUILD_DIR/vivado.log" \
    -journal "$BUILD_DIR/vivado.jou"

export INPUT_CHECKPOINT="$CHECKPOINT"
export RUN_NAME=updated_qat_po2_low_dsp_route_default
export PLACE_DIRECTIVE=Default
export ROUTE_DIRECTIVE=Default
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1
export POST_PLACE_PHYS_DIRECTIVE=""

"$VIVADO_BIN" -mode batch \
    -source hls/run_vivado_int8_po2_strategy.tcl \
    -log "$RUN_DIR/vivado.log" \
    -journal "$RUN_DIR/vivado.jou"