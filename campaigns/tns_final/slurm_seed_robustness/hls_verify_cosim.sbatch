#!/usr/bin/env bash
#SBATCH --job-name=qat-verify-cosim
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=08:00:00
#SBATCH --output=campaigns/tns_final/logs/hls_seed_variant_%j.out
#SBATCH --error=campaigns/tns_final/logs/hls_seed_variant_%j.err

set -euo pipefail
: "${SEED_TAG:?Missing SEED_TAG}"
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

export SEED_TAG VARIANT_NAME L1_ROOT_MASK L1_NEIGHBOR_MASK L2_ROOT_MASK L2_NEIGHBOR_MASK AGGREGATION_MODE L1_NEIGHBOR_ACC_PIPELINE_MASK L1_ROOT_ACC_PIPELINE_MASK L2_ROOT_ACC_PIPELINE_MASK L2_NEIGHBOR_ACC_PIPELINE_MASK
# GS_FABRIC_MUL_LATENCY / GS_DSP_MUL_LATENCY are intentionally NOT defaulted:
# unset means "no explicit latency" (header default -1, unchanged behavior).
export GS_FABRIC_MUL_LATENCY GS_DSP_MUL_LATENCY
export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export HLS_ACTION=cosim

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
PACKAGE_ROOT="$ROOT/transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
SOURCE_DIR="$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/hls/po2_qat_root_dynamic_const_weights_partitioned_${SEED_TAG}"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

cd "$ROOT"
mkdir -p slurm/logs "$PACKAGE_ROOT/build/hls/hls"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/cora_graphsage_hls_test_bundle"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/hls/cora_graphsage_hls_test_bundle"

printf 'VARIANT=%s L1_ROOT=%s L1_NEIGHBOR=%s L2_ROOT=%s L2_NEIGHBOR=%s AGGREGATION_MODE=%s ACC_PIPELINE=%s FABRIC_MUL_LAT=%s DSP_MUL_LAT=%s\n' \
    "$VARIANT_NAME" "$L1_ROOT_MASK" "$L1_NEIGHBOR_MASK" "$L2_ROOT_MASK" "$L2_NEIGHBOR_MASK" "$AGGREGATION_MODE" "$L1_NEIGHBOR_ACC_PIPELINE_MASK" "${GS_FABRIC_MUL_LATENCY:-unset}" "${GS_DSP_MUL_LATENCY:-unset}"
cd "$PACKAGE_ROOT"
"$VITIS_RUN_BIN" --mode hls --tcl "$SOURCE_DIR/run_hls_variant.tcl"