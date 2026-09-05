#!/usr/bin/env bash
#SBATCH --job-name=graphsage-19c-hls
#SBATCH --partition=momacpu
#SBATCH --nodelist=prometeo
#SBATCH --array=0-3
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=24:00:00
#SBATCH --output=slurm/logs/hls_19c_ladder_%A_%a.out
#SBATCH --error=slurm/logs/hls_19c_ladder_%A_%a.err

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

NAMES=(
    19c_a_balanced
    19c_b_register_cut
    19c_c_fold2
    19c_d_fold4
)

CFLAGS=(
    "-DDSE_PIPELINE_TOP=1 -DDSE_TOP_II=1 -DDSE_AGG_REGISTER_CUT=0 -DDSE_AGG_FEATURE_FOLD=1"
    "-DDSE_PIPELINE_TOP=1 -DDSE_TOP_II=1 -DDSE_AGG_REGISTER_CUT=1 -DDSE_AGG_FEATURE_FOLD=1"
    "-DDSE_PIPELINE_TOP=0 -DDSE_STAGE_DATAFLOW=1 -DDSE_AGG_REGISTER_CUT=1 -DDSE_AGG_FEATURE_FOLD=2 -DDSE_ALLOC_AGG_MUL_LIMIT=768"
    "-DDSE_PIPELINE_TOP=0 -DDSE_STAGE_DATAFLOW=1 -DDSE_AGG_REGISTER_CUT=1 -DDSE_AGG_FEATURE_FOLD=4 -DDSE_ALLOC_AGG_MUL_LIMIT=384"
)

export EXPERIMENT_NAME="${NAMES[$SLURM_ARRAY_TASK_ID]}"
export EXTRA_CFLAGS="${CFLAGS[$SLURM_ARRAY_TASK_ID]}"

cd "$ROOT"
mkdir -p slurm/logs build/experiments_19c
"$VITIS_RUN_BIN" --mode hls --tcl hls/build_graphsage_19c_ladder.tcl