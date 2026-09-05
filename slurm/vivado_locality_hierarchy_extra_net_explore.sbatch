#!/usr/bin/env bash
#SBATCH --job-name=graphsage-loc-hier
#SBATCH --partition=momacpu
#SBATCH --nodelist=prometeo
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=slurm/logs/locality_hierarchy_extra_net_explore_%j.out
#SBATCH --error=slurm/logs/locality_hierarchy_extra_net_explore_%j.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the extracted bundle root}"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

cd "$ROOT"
mkdir -p slurm/logs build/hls \
    build/vivado_sweep/locality_hierarchy_build \
    build/vivado_sweep/locality_hierarchy_extra_net_delay_high_explore

if [[ ! -x "$VITIS_RUN_BIN" ]]; then
    echo "Vitis executable is not available: $VITIS_RUN_BIN" >&2
    exit 1
fi
if [[ ! -x "$VIVADO_BIN" ]]; then
    echo "Vivado executable is not available: $VIVADO_BIN" >&2
    exit 1
fi

"$VITIS_RUN_BIN" \
    --mode hls \
    --tcl hls/build_graphsage_int8_po2_locality_hierarchy.tcl

"$VIVADO_BIN" -mode batch \
    -source hls/build_vivado_int8_po2_locality_hierarchy_checkpoint.tcl \
    -log build/vivado_sweep/locality_hierarchy_build/vivado.log \
    -journal build/vivado_sweep/locality_hierarchy_build/vivado.jou

export INPUT_CHECKPOINT="$ROOT/build/vivado_sweep/locality_hierarchy_post_synth.dcp"
export RUN_NAME=locality_hierarchy_extra_net_delay_high_explore
export PLACE_DIRECTIVE=ExtraNetDelay_high
export ROUTE_DIRECTIVE=Explore
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1

"$VIVADO_BIN" -mode batch \
    -source hls/run_vivado_int8_po2_strategy.tcl \
    -log build/vivado_sweep/locality_hierarchy_extra_net_delay_high_explore/vivado.log \
    -journal build/vivado_sweep/locality_hierarchy_extra_net_delay_high_explore/vivado.jou