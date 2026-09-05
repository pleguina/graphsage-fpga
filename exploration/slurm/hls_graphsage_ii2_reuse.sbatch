#!/usr/bin/env bash
#SBATCH --job-name=graphsage-hls-ii2-reuse
#SBATCH --partition=momacpu
#SBATCH --nodelist=prometeo
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=exploration/slurm/logs/hls_ii2_reuse_%j.out
#SBATCH --error=exploration/slurm/logs/hls_ii2_reuse_%j.err

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

cd "$ROOT"
mkdir -p exploration/slurm/logs build/hls

"$VITIS_RUN_BIN" --mode hls --tcl exploration/hls/build_graphsage_int8_po2_ii2_reuse.tcl