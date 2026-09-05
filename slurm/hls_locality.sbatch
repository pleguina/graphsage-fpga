#!/usr/bin/env bash
#SBATCH --job-name=graphsage-hls-loc
#SBATCH --partition=momacpu
#SBATCH --nodelist=prometeo
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=slurm/logs/hls_locality_%j.out
#SBATCH --error=slurm/logs/hls_locality_%j.err

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the extracted bundle root}"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

cd "$ROOT"
mkdir -p slurm/logs build/hls

if [[ ! -x "$VITIS_RUN_BIN" ]]; then
    echo "Vitis executable is not available: $VITIS_RUN_BIN" >&2
    exit 1
fi

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

"$VITIS_RUN_BIN" \
    --mode hls \
    --tcl hls/build_graphsage_int8_po2_locality.tcl