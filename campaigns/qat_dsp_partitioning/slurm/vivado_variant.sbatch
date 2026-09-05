#!/usr/bin/env bash
#SBATCH --job-name=qat-dsp-vivado
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=campaigns/qat_dsp_partitioning/logs/vivado_variant_%j.out
#SBATCH --error=campaigns/qat_dsp_partitioning/logs/vivado_variant_%j.err

set -euo pipefail
: "${VARIANT_NAME:?Missing VARIANT_NAME}"
: "${L1_ROOT_MASK:=0}"
: "${L1_NEIGHBOR_MASK:=0}"
: "${L2_ROOT_MASK:=0}"
: "${L2_NEIGHBOR_MASK:=0}"
: "${AGGREGATION_MODE:=0}"
: "${L1_NEIGHBOR_ACC_PIPELINE_MASK:=0}"
: "${L1_ROOT_ACC_PIPELINE_MASK:=0}"
: "${L2_ROOT_ACC_PIPELINE_MASK:=0}"
: "${L2_NEIGHBOR_ACC_PIPELINE_MASK:=0}"

export VARIANT_NAME L1_ROOT_MASK L1_NEIGHBOR_MASK L2_ROOT_MASK L2_NEIGHBOR_MASK AGGREGATION_MODE L1_NEIGHBOR_ACC_PIPELINE_MASK L1_ROOT_ACC_PIPELINE_MASK L2_ROOT_ACC_PIPELINE_MASK L2_NEIGHBOR_ACC_PIPELINE_MASK
export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export XILINX_LOCAL_USER_DATA="${XILINX_LOCAL_USER_DATA:-${SLURM_TMPDIR:-/tmp/$USER}/xilinx_user_data}"

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
PACKAGE_ROOT="$ROOT/transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
HLS_PROJECT="$PACKAGE_ROOT/build/hls/cora_po2_qat_${VARIANT_NAME}_2024_1"
HLS_XML="$HLS_PROJECT/solution1/syn/report/graphsage_po2_qat_partitioned_csynth.xml"
RUN_NAME="qat_dsp_${VARIANT_NAME}_route_default"
OUTPUT_DIR="$ROOT/build/vivado_sweep/$RUN_NAME"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

cd "$ROOT"
mkdir -p slurm/logs "$XILINX_LOCAL_USER_DATA" "$OUTPUT_DIR"
DSP_COUNT="$(sed -n 's:.*<DSP>\([0-9][0-9]*\)</DSP>.*:\1:p' "$HLS_XML" | head -n 1)"
MAX_HLS_DSP="${MAX_HLS_DSP:-512}"
if [[ -z "$DSP_COUNT" ]]; then
    echo "MISSING_HLS_DSP_COUNT=$HLS_XML"
    exit 1
fi
if [[ "$DSP_COUNT" -gt "$MAX_HLS_DSP" ]]; then
    echo "VARIANT_DSP_GATE_WARNING=$DSP_COUNT limit=$MAX_HLS_DSP continuing=1"
else
    echo "VARIANT_DSP_GATE_PASS=$DSP_COUNT limit=$MAX_HLS_DSP"
fi

cat > "$OUTPUT_DIR/variant_manifest.txt" <<EOF
variant=$VARIANT_NAME
l1_root_mask=$L1_ROOT_MASK
l1_neighbor_mask=$L1_NEIGHBOR_MASK
l2_root_mask=$L2_ROOT_MASK
l2_neighbor_mask=$L2_NEIGHBOR_MASK
aggregation_mode=$AGGREGATION_MODE
l1_neighbor_acc_pipeline_mask=$L1_NEIGHBOR_ACC_PIPELINE_MASK
l1_root_acc_pipeline_mask=$L1_ROOT_ACC_PIPELINE_MASK
l2_root_acc_pipeline_mask=$L2_ROOT_ACC_PIPELINE_MASK
l2_neighbor_acc_pipeline_mask=$L2_NEIGHBOR_ACC_PIPELINE_MASK
gs_fabric_mul_latency=${GS_FABRIC_MUL_LATENCY:-unset}
gs_dsp_mul_latency=${GS_DSP_MUL_LATENCY:-unset}
hls_dsp=$DSP_COUNT
hls_project=$HLS_PROJECT
EOF

"$VIVADO_BIN" -mode batch -nolog -nojournal \
    -source campaigns/qat_dsp_partitioning/hls/build_variant_checkpoint.tcl
export INPUT_CHECKPOINT="$ROOT/build/vivado_sweep/qat_dsp_${VARIANT_NAME}_post_synth.dcp"
export RUN_NAME OUTPUT_DIR
export PLACE_DIRECTIVE=Default
export ROUTE_DIRECTIVE=Default
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1
export POST_PLACE_PHYS_DIRECTIVE=""
"$VIVADO_BIN" -mode batch -nolog -nojournal -source hls/run_vivado_int8_po2_strategy.tcl