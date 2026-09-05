#!/usr/bin/env bash
#SBATCH --job-name=root-low-dsp-hls
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=exploration/slurm/logs/hls_updated_root_low_dsp_%j.out
#SBATCH --error=exploration/slurm/logs/hls_updated_root_low_dsp_%j.err

set -euo pipefail

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"

REPO_ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
PACKAGE_ROOT="$REPO_ROOT/transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
SOURCE_DIR="$PACKAGE_ROOT/exploration/hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/exploration/hls/root_dynamic_const_weights"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"
export HLS_ACTION="${HLS_ACTION:-csynth}"

cd "$REPO_ROOT"
mkdir -p exploration/slurm/logs
echo "HOST=$(hostname)"
echo "PACKAGE_ROOT=$PACKAGE_ROOT"
echo "HLS_ACTION=$HLS_ACTION"

cd "$PACKAGE_ROOT"
mkdir -p build/exploration/hls/hls
ln -sfn "$PACKAGE_ROOT/exploration/hls/cora_graphsage_hls_test_bundle" \
    build/exploration/hls/cora_graphsage_hls_test_bundle
ln -sfn "$PACKAGE_ROOT/exploration/hls/cora_graphsage_hls_test_bundle" \
    build/exploration/hls/exploration/hls/cora_graphsage_hls_test_bundle
"$VITIS_RUN_BIN" --mode hls --tcl "$SOURCE_DIR/run_hls.tcl"