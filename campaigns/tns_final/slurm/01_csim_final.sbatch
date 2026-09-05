#!/usr/bin/env bash
#SBATCH --job-name=tns-csim-final
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=campaigns/tns_final/logs/csim_final_%j.out
#SBATCH --error=campaigns/tns_final/logs/csim_final_%j.err

# Functional bit-exactness CSim for the final frozen architecture (plan
# Section 13), using the existing 256-graph reference corpus baked into
# root_graphsage_constants.h. This is smaller than the plan's 10k-graph
# target corpus (Section 18); expanding the corpus is a separate follow-up
# (see campaigns/tns_final/README.md).
set -euo pipefail

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export HLS_ACTION=csim
export VARIANT_NAME=V2A1_allcut
export L1_ROOT_MASK=0
export L1_NEIGHBOR_MASK=0x1004
export L2_ROOT_MASK=0
export L2_NEIGHBOR_MASK=0
export AGGREGATION_MODE=4
export L1_ROOT_ACC_PIPELINE_MASK=0xFFFFFF
export L1_NEIGHBOR_ACC_PIPELINE_MASK=0xFFFFFF
export L2_ROOT_ACC_PIPELINE_MASK=0x7F
export L2_NEIGHBOR_ACC_PIPELINE_MASK=0x7F

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
PACKAGE_ROOT="$ROOT/transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
SOURCE_DIR="$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/hls/po2_qat_root_dynamic_const_weights_partitioned"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

cd "$ROOT"
mkdir -p campaigns/tns_final/logs "$PACKAGE_ROOT/build/hls/hls"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/cora_graphsage_hls_test_bundle"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/hls/cora_graphsage_hls_test_bundle"

cd "$PACKAGE_ROOT"
"$VITIS_RUN_BIN" --mode hls --tcl "$SOURCE_DIR/run_hls_variant.tcl"
