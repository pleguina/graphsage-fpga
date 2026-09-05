#!/usr/bin/env bash
#SBATCH --job-name=qat-partitioned-baseline-vivado
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=slurm/logs/vivado_updated_qat_partitioned_baseline_%j.out
#SBATCH --error=slurm/logs/vivado_updated_qat_partitioned_baseline_%j.err

set -euo pipefail
export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export XILINX_LOCAL_USER_DATA="${XILINX_LOCAL_USER_DATA:-${SLURM_TMPDIR:-/tmp/$USER}/xilinx_user_data}"
mkdir -p "$XILINX_LOCAL_USER_DATA"
ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
cd "$ROOT"
mkdir -p slurm/logs
PACKAGE_ROOT="$ROOT/transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
HLS_XML="$PACKAGE_ROOT/build/hls/cora_po2_qat_partitioned_2024_1/solution1/syn/report/graphsage_po2_qat_partitioned_csynth.xml"
DSP_COUNT="$(sed -n 's:.*<DSP>\([0-9][0-9]*\)</DSP>.*:\1:p' "$HLS_XML" | head -n 1)"
if [[ -z "$DSP_COUNT" || "$DSP_COUNT" -gt 512 ]]; then
    echo "INSTRUMENTED_DSP_GATE_FAIL=$DSP_COUNT"
    exit 1
fi
echo "INSTRUMENTED_DSP_GATE_PASS=$DSP_COUNT"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"
"$VIVADO_BIN" -mode batch -nolog -nojournal -source hls/build_vivado_updated_qat_partitioned_baseline_checkpoint.tcl
export INPUT_CHECKPOINT="$ROOT/build/vivado_sweep/updated_qat_partitioned_baseline_post_synth.dcp"
export RUN_NAME=updated_qat_partitioned_baseline_route_default
export OUTPUT_DIR="$ROOT/build/vivado_sweep/updated_qat_partitioned_baseline_route_default"
export PLACE_DIRECTIVE=Default
export ROUTE_DIRECTIVE=Default
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1
export POST_PLACE_PHYS_DIRECTIVE=""
"$VIVADO_BIN" -mode batch -nolog -nojournal -source hls/run_vivado_int8_po2_strategy.tcl