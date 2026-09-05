#!/usr/bin/env bash
#SBATCH --job-name=qat-wrapper-vivado
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=campaigns/tns_final/logs/vivado_integrated_wrapper_%j.out
#SBATCH --error=campaigns/tns_final/logs/vivado_integrated_wrapper_%j.err

set -euo pipefail
export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export XILINX_LOCAL_USER_DATA="${XILINX_LOCAL_USER_DATA:-${SLURM_TMPDIR:-/tmp/$USER}/xilinx_user_data}"

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

cd "$ROOT"
mkdir -p campaigns/tns_final/logs "$XILINX_LOCAL_USER_DATA"
"$VIVADO_BIN" -mode batch -nolog -nojournal -source campaigns/tns_final/wrapper/build_integrated_wrapper.tcl
