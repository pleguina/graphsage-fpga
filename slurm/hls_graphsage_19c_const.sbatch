#!/usr/bin/env bash
#SBATCH --job-name=graphsage-19c-const
#SBATCH --partition=momacpu
#SBATCH --nodelist=prometeo
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=slurm/logs/hls_19c_const_%j.out
#SBATCH --error=slurm/logs/hls_19c_const_%j.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

cd "$ROOT"
mkdir -p slurm/logs build/hls

"$VITIS_RUN_BIN" --mode hls --tcl hls/run_graphsage_19c_const.tcl