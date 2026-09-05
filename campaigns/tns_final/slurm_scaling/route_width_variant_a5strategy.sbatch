#!/usr/bin/env bash
#SBATCH --job-name=tns-width-route-a5
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=campaigns/tns_final/logs/route_width_variant_a5strategy_%j.out
#SBATCH --error=campaigns/tns_final/logs/route_width_variant_a5strategy_%j.err

# Second, explicitly separate scaling series (docs/tns_campaign_status.md
# OPEN item 3): re-routes an existing H=24/H=32 scaling point under A5's
# validated final strategy (physical_robustness.csv row R1:
# PLACE_DIRECTIVE=SSI_SpreadLogic_high, ROUTE_DIRECTIVE=Default,
# USE_RETIME=1) instead of route_width_variant.sbatch's A3-equivalent
# common policy (Default/Default, no retime).
#
# This is NOT a rerun/fix of the common-policy series in
# paper_data/scaling.csv - it is a second data point answering "does a
# stronger physical strategy recover the widths that miss under the common
# policy," and must be reported as a separate series, never blended into
# the same WNS-vs-width curve as the common-policy run.
#
# Reuses the post-synthesis checkpoint already produced by
# route_width_variant.sbatch's build_variant_checkpoint.tcl step for the
# same WIDTH, so it must be run after that job has produced
# build/vivado_sweep/qat_dsp_h${WIDTH}_scaling_post_synth.dcp.
#
# Usage: sbatch --export=ALL,WIDTH=24 route_width_variant_a5strategy.sbatch

set -euo pipefail
: "${WIDTH:?Missing WIDTH (e.g. 24 or 32)}"

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export XILINX_LOCAL_USER_DATA="${SLURM_TMPDIR:-/tmp/$USER}/xilinx_user_data_${SLURM_JOB_ID}"

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

VARIANT_NAME="h${WIDTH}_scaling"
INPUT_CHECKPOINT="$ROOT/build/vivado_sweep/qat_dsp_${VARIANT_NAME}_post_synth.dcp"
RUN_NAME="qat_dsp_${VARIANT_NAME}_route_ssi_retime"
OUTPUT_DIR="$ROOT/build/vivado_sweep/$RUN_NAME"

cd "$ROOT"
mkdir -p campaigns/tns_final/logs "$XILINX_LOCAL_USER_DATA" "$OUTPUT_DIR"

if [[ ! -f "$INPUT_CHECKPOINT" ]]; then
    echo "MISSING_POST_SYNTH_CHECKPOINT=$INPUT_CHECKPOINT" >&2
    echo "Run route_width_variant.sbatch (WIDTH=$WIDTH) first - it produces this checkpoint before its own Default/Default route." >&2
    exit 1
fi

cat > "$OUTPUT_DIR/variant_manifest.txt" <<EOF
variant=$VARIANT_NAME
width=$WIDTH
l1_root_mask=0
l1_neighbor_mask=0
l2_root_mask=0
l2_neighbor_mask=0
aggregation_mode=4
physical_strategy=A5-equivalent (SSI_SpreadLogic_high + retime), second series - see docs/tns_campaign_status.md OPEN item 3
input_checkpoint=$INPUT_CHECKPOINT
EOF

export INPUT_CHECKPOINT RUN_NAME OUTPUT_DIR
export PLACE_DIRECTIVE=SSI_SpreadLogic_high
export ROUTE_DIRECTIVE=Default
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1
export POST_PLACE_PHYS_DIRECTIVE=""
export USE_RETIME=1
"$VIVADO_BIN" -mode batch -nolog -nojournal -source hls/run_vivado_int8_po2_strategy.tcl
