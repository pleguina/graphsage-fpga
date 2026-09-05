#!/usr/bin/env bash
#SBATCH --job-name=graphsage-19c-route
#SBATCH --partition=momacpu
#SBATCH --nodelist=prometeo
#SBATCH --array=0-3%1
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=exploration/slurm/logs/vivado_19c_ladder_%A_%a.out
#SBATCH --error=exploration/slurm/logs/vivado_19c_ladder_%A_%a.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

NAMES=(
    19c_a_balanced
    19c_b_register_cut
    19c_c_fold2
    19c_d_fold4
)

export EXPERIMENT_NAME="${NAMES[$SLURM_ARRAY_TASK_ID]}"
EXPERIMENT_ROOT="$ROOT/build/experiments_19c/$EXPERIMENT_NAME"
HLS_REPORT="$EXPERIMENT_ROOT/exploration/hls/solution1/syn/report/csynth.rpt"
BUILD_DIR="$EXPERIMENT_ROOT/vivado_build"
RUN_DIR="$EXPERIMENT_ROOT/implementation"

cd "$ROOT"
mkdir -p exploration/slurm/logs "$BUILD_DIR" "$RUN_DIR"

if [[ ! -s "$HLS_REPORT" ]]; then
    echo "Missing completed HLS report: $HLS_REPORT" >&2
    exit 1
fi

"$VIVADO_BIN" -mode batch \
    -source exploration/hls/build_vivado_19c_ladder_checkpoint.tcl \
    -log "$BUILD_DIR/vivado.log" \
    -journal "$BUILD_DIR/vivado.jou"

export INPUT_CHECKPOINT="$EXPERIMENT_ROOT/post_synth.dcp"
export RUN_NAME="../experiments_19c/$EXPERIMENT_NAME/implementation"
export PLACE_DIRECTIVE=ExtraNetDelay_high
export POST_PLACE_PHYS_DIRECTIVE=AddRetime
export ROUTE_DIRECTIVE=Explore
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=0

"$VIVADO_BIN" -mode batch \
    -source exploration/hls/run_vivado_int8_po2_strategy.tcl \
    -log "$RUN_DIR/vivado.log" \
    -journal "$RUN_DIR/vivado.jou"