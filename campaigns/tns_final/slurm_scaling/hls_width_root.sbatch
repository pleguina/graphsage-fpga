#!/usr/bin/env bash
#SBATCH --job-name=qat-width-root-hls
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=campaigns/tns_final/logs/hls_width_root_%j.out
#SBATCH --error=campaigns/tns_final/logs/hls_width_root_%j.err

set -euo pipefail
: "${WIDTH_TAG:?Missing WIDTH_TAG}"
: "${GS_HIDDEN_FEATURES:?Missing GS_HIDDEN_FEATURES}"
export WIDTH_TAG GS_HIDDEN_FEATURES
export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export HLS_ACTION=csynth

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
PACKAGE_ROOT="$ROOT/transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
SOURCE_DIR="$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/hls/root_dynamic_const_weights_${WIDTH_TAG}"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

cd "$ROOT"
mkdir -p slurm/logs campaigns/tns_final/logs "$PACKAGE_ROOT/build/hls/hls"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/cora_graphsage_hls_test_bundle"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/hls/cora_graphsage_hls_test_bundle"

echo "WIDTH_TAG=$WIDTH_TAG GS_HIDDEN_FEATURES=$GS_HIDDEN_FEATURES"
cd "$PACKAGE_ROOT"
"$VITIS_RUN_BIN" --mode hls --tcl "$SOURCE_DIR/run_hls_width.tcl"
