#!/usr/bin/env bash
#SBATCH --job-name=graphsage-exp
#SBATCH --partition=momacpu
#SBATCH --nodelist=prometeo
#SBATCH --array=0-12%1
#SBATCH --cpus-per-task=32
#SBATCH --mem=48G
#SBATCH --time=24:00:00
#SBATCH --output=slurm/logs/experiment_%A_%a.out
#SBATCH --error=slurm/logs/experiment_%A_%a.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

NAMES=(
    exp1_hierarchy_floorplan
    exp2_regional_boundaries
    exp3a_agg1_fabric
    exp3b_agg2_fabric
    exp3c_agg1_agg2_fabric
    exp4_independent_agg1
    exp5_two_complete_domains
    exp6_four_domains_reduced
    exp7a_ii2_serial_agg
    exp7b_ii4_serial_agg
    exp7c_ii1_partial_unroll
    exp7d_ii2_partial_unroll
    exp7e_ii4_partial_unroll
)

CFLAGS=(
    ""
    "-DDSE_REGIONAL_BOUNDARIES=1"
    "-DDSE_BIND_AGG1_MUL=fabric"
    "-DDSE_BIND_AGG2_MUL=fabric"
    "-DDSE_BIND_AGG1_MUL=fabric -DDSE_BIND_AGG2_MUL=fabric"
    "-DDSE_INDEPENDENT_AGG1=1"
    "-DDSE_COMPUTE_DOMAINS=2"
    "-DDSE_COMPUTE_DOMAINS=4 -DDSE_UNROLL_NODES=2 -DDSE_UNROLL_FEATURES_AGG=4 -DDSE_UNROLL_FEATURES_LIN=4"
    "-DDSE_TOP_II=2 -DDSE_AGG_PIPELINE_II=2 -DDSE_LIN_PIPELINE_II=2 -DDSE_UNROLL_FEATURES_AGG=1"
    "-DDSE_TOP_II=4 -DDSE_AGG_PIPELINE_II=4 -DDSE_LIN_PIPELINE_II=4 -DDSE_UNROLL_FEATURES_AGG=1"
    "-DDSE_UNROLL_NODES=2 -DDSE_UNROLL_FEATURES_AGG=4 -DDSE_UNROLL_FEATURES_LIN=4"
    "-DDSE_TOP_II=2 -DDSE_AGG_PIPELINE_II=2 -DDSE_LIN_PIPELINE_II=2 -DDSE_UNROLL_NODES=2 -DDSE_UNROLL_FEATURES_AGG=1 -DDSE_UNROLL_FEATURES_LIN=4"
    "-DDSE_TOP_II=4 -DDSE_AGG_PIPELINE_II=4 -DDSE_LIN_PIPELINE_II=4 -DDSE_UNROLL_NODES=2 -DDSE_UNROLL_FEATURES_AGG=1 -DDSE_UNROLL_FEATURES_LIN=4"
)

export EXPERIMENT_NAME="${NAMES[$SLURM_ARRAY_TASK_ID]}"
export EXTRA_CFLAGS="${CFLAGS[$SLURM_ARRAY_TASK_ID]}"
EXPERIMENT_ROOT="$ROOT/build/experiments/$EXPERIMENT_NAME"
IMPLEMENT_DIR="$EXPERIMENT_ROOT/implementation"
HLS_REPORT="$EXPERIMENT_ROOT/hls/solution1/syn/report/csynth.rpt"

cd "$ROOT"
mkdir -p slurm/logs "$EXPERIMENT_ROOT" "$IMPLEMENT_DIR" \
    "$EXPERIMENT_ROOT/vivado_build"

printf 'experiment_name=%s\narray_job=%s\narray_task=%s\nextra_cflags=%s\n' \
    "$EXPERIMENT_NAME" "$SLURM_ARRAY_JOB_ID" "$SLURM_ARRAY_TASK_ID" \
    "$EXTRA_CFLAGS" > "$EXPERIMENT_ROOT/slurm_submission.txt"

if [[ "${VIVADO_ONLY:-0}" != "1" ]]; then
    if [[ ! -f "$HLS_REPORT" ]]; then
        "$VITIS_RUN_BIN" --mode hls --tcl hls/build_graphsage_experiment.tcl
    else
        echo "Reusing completed HLS report: $HLS_REPORT"
    fi
fi

if [[ "${HLS_ONLY:-0}" == "1" ]]; then
    echo "HLS_ONLY_COMPLETE=$EXPERIMENT_NAME"
    exit 0
fi

if [[ ! -f "$HLS_REPORT" ]]; then
    echo "Missing completed HLS report for Vivado stage: $HLS_REPORT" >&2
    exit 1
fi

export FLATTEN_HIERARCHY=none
"$VIVADO_BIN" -mode batch \
    -source hls/build_vivado_experiment_checkpoint.tcl \
    -log "$EXPERIMENT_ROOT/vivado_build/vivado.log" \
    -journal "$EXPERIMENT_ROOT/vivado_build/vivado.jou"

export INPUT_CHECKPOINT="$EXPERIMENT_ROOT/post_synth.dcp"
export RUN_NAME="../experiments/$EXPERIMENT_NAME/implementation"
export PLACE_DIRECTIVE=ExtraNetDelay_high
export ROUTE_DIRECTIVE=Explore
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1

if [[ "$EXPERIMENT_NAME" == "exp1_hierarchy_floorplan" ]]; then
    export PRE_PLACE_TCL="$ROOT/hls/floorplan_hierarchy_domains.tcl"
else
    unset PRE_PLACE_TCL || true
fi

"$VIVADO_BIN" -mode batch \
    -source hls/run_vivado_int8_po2_strategy.tcl \
    -log "$IMPLEMENT_DIR/vivado.log" \
    -journal "$IMPLEMENT_DIR/vivado.jou"