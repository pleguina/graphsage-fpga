#!/usr/bin/env bash
#SBATCH --job-name=cora-root-dynamic
#SBATCH --partition=batch
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=exploration/slurm/logs/hls_cora_root_dynamic_%j.out
#SBATCH --error=exploration/slurm/logs/hls_cora_root_dynamic_%j.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"
PYTHON_BIN="${PYTHON_BIN:-/nfs/fanae/vivado/2025.2/lnx64/tools/vcxx/third-party/python-linux/user/3.10.10/bin/python3}"
export PYTHONPATH="/nfs/fanae/user/pleguina/.local/lib/python3.10/site-packages${PYTHONPATH:+:$PYTHONPATH}"
export HLS_ACTION="${HLS_ACTION:-csim}"
SOURCE_DIR="$ROOT/exploration/hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/exploration/hls/root_dynamic_const_weights"

cd "$ROOT"
mkdir -p exploration/slurm/logs build/hls
echo "HOST=$(hostname)"
echo "HLS_ACTION=$HLS_ACTION"
"$PYTHON_BIN" "$SOURCE_DIR/generate_root_int8_po2.py"
"$VITIS_RUN_BIN" --mode hls --tcl "$SOURCE_DIR/run_hls.tcl"