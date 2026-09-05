#!/usr/bin/env bash
#SBATCH --job-name=graphsage-const-data-timing
#SBATCH --partition=momacpu
#SBATCH --nodelist=prometeo
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=slurm/logs/vivado_19c_const_data_%j.out
#SBATCH --error=slurm/logs/vivado_19c_const_data_%j.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

cd "$ROOT"
mkdir -p slurm/logs

"$VIVADO_BIN" -mode batch \
    -source hls/report_graphsage_19c_const_data_paths.tcl \
    -log build/vivado_sweep/graphsage_19c_const_extra_net_delay/data_paths.log \
    -journal build/vivado_sweep/graphsage_19c_const_extra_net_delay/data_paths.jou