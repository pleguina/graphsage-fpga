#!/usr/bin/env bash
#SBATCH --job-name=graphsage-const-freerun
#SBATCH --partition=momacpu
#SBATCH --nodelist=prometeo
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=slurm/logs/vivado_19c_const_freerun_%j.out
#SBATCH --error=slurm/logs/vivado_19c_const_freerun_%j.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"
BUILD_NAME=graphsage_19c_const_freerun_build
CHECKPOINT_NAME=graphsage_19c_const_freerun_post_synth.dcp
RUN_NAME=graphsage_19c_const_freerun_extra_net_delay
BUILD_DIR="$ROOT/build/vivado_sweep/$BUILD_NAME"
RUN_DIR="$ROOT/build/vivado_sweep/$RUN_NAME"
CHECKPOINT="$ROOT/build/vivado_sweep/$CHECKPOINT_NAME"

cd "$ROOT"
mkdir -p slurm/logs "$BUILD_DIR" "$RUN_DIR"

export CONST_BUILD_NAME="$BUILD_NAME"
export CONST_CHECKPOINT_NAME="$CHECKPOINT_NAME"

"$VIVADO_BIN" -mode batch \
    -source hls/build_vivado_graphsage_19c_const_checkpoint.tcl \
    -log "$BUILD_DIR/vivado.log" \
    -journal "$BUILD_DIR/vivado.jou"

export INPUT_CHECKPOINT="$CHECKPOINT"
export RUN_NAME
export PLACE_DIRECTIVE=ExtraNetDelay_high
export POST_PLACE_PHYS_DIRECTIVE=AddRetime
export ROUTE_DIRECTIVE=Explore
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=0

"$VIVADO_BIN" -mode batch \
    -source hls/run_vivado_int8_po2_strategy.tcl \
    -log "$RUN_DIR/vivado.log" \
    -journal "$RUN_DIR/vivado.jou"