#!/usr/bin/env bash
#SBATCH --job-name=graphsage-loc-xnet
#SBATCH --partition=momacpu
#SBATCH --nodelist=prometeo
#SBATCH --cpus-per-task=32
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=exploration/slurm/logs/locality_extra_net_explore_%j.out
#SBATCH --error=exploration/slurm/logs/locality_extra_net_explore_%j.err

set -euo pipefail

export XILINXD_LICENSE_FILE=<LICENSE_SERVER>
export LM_LICENSE_FILE=<LICENSE_SERVER>

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the extracted bundle root}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

cd "$ROOT"
mkdir -p exploration/slurm/logs build/vivado_sweep/locality_build \
    build/vivado_sweep/locality_extra_net_delay_high_explore

if [[ ! -x "$VIVADO_BIN" ]]; then
    echo "Vivado executable is not available: $VIVADO_BIN" >&2
    exit 1
fi

LOCALITY_DCP="$ROOT/build/vivado_sweep/locality_post_synth.dcp"

if [[ ! -f "$LOCALITY_DCP" ]]; then
    "$VIVADO_BIN" -mode batch \
        -source exploration/hls/build_vivado_int8_po2_locality_checkpoint.tcl \
        -log build/vivado_sweep/locality_build/vivado.log \
        -journal build/vivado_sweep/locality_build/vivado.jou
fi

export INPUT_CHECKPOINT="$LOCALITY_DCP"
export RUN_NAME=locality_extra_net_delay_high_explore
export PLACE_DIRECTIVE=ExtraNetDelay_high
export ROUTE_DIRECTIVE=Explore
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1

"$VIVADO_BIN" -mode batch \
    -source exploration/hls/run_vivado_int8_po2_strategy.tcl \
    -log build/vivado_sweep/locality_extra_net_delay_high_explore/vivado.log \
    -journal build/vivado_sweep/locality_extra_net_delay_high_explore/vivado.jou