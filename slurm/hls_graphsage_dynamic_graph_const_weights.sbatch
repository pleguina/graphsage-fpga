#!/usr/bin/env bash
#SBATCH --job-name=graphsage-dynamic-graph
#SBATCH --partition=batch
#SBATCH --nodelist=gae034
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=slurm/logs/hls_dynamic_graph_%j.out
#SBATCH --error=slurm/logs/hls_dynamic_graph_%j.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"
export HLS_ACTION="${HLS_ACTION:-csynth}"

cd "$ROOT"
mkdir -p slurm/logs build/hls

echo "HOST=$(hostname)"
echo "HLS_ACTION=$HLS_ACTION"
"$VITIS_RUN_BIN" --mode hls --tcl hls/run_graphsage_dynamic_graph_const_weights.tcl