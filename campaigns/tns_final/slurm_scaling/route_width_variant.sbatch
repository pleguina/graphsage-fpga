#!/usr/bin/env bash
#SBATCH --job-name=tns-width-route
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=campaigns/tns_final/logs/route_width_variant_%j.out
#SBATCH --error=campaigns/tns_final/logs/route_width_variant_%j.err

# Vivado place+route for one hidden-width scaling point (plan Section 12/20).
# Consumes the HLS RTL already produced by full_width_pipeline.sbatch
# (VARIANT_NAME=h${WIDTH}_scaling, DSP masks=0, i.e. the same all-fabric
# multiplier policy as the A3 architecture-ablation baseline) and reuses the
# exact two-stage flow qat_dsp_partitioning uses for every other variant:
#   1. build_variant_checkpoint.tcl  - out-of-context synth -> post_synth.dcp
#   2. run_vivado_int8_po2_strategy.tcl - place -> phys_opt -> route
#
# Physical strategy is held fixed across widths at A3's "common" policy
# (PLACE_DIRECTIVE=Default, ROUTE_DIRECTIVE=Default, no retime) per the
# plan's "do not hand-optimize each width" rule - this is NOT A5's
# SSI_SpreadLogic_high+retime strategy, deliberately, so DSP=0 scaling
# points stay comparable to A3 rather than to the final tuned design.
#
# Usage: sbatch --export=ALL,WIDTH=16 route_width_variant.sbatch
# H=24 has no HLS output yet as of 2026-08-30 - submit its HLS job first
# (sbatch --export=ALL,WIDTH=24 full_width_pipeline.sbatch) and chain this
# script with --dependency=afterok:<that job id>.

set -euo pipefail
: "${WIDTH:?Missing WIDTH (e.g. 16, 24, or 32)}"

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export XILINX_LOCAL_USER_DATA="${SLURM_TMPDIR:-/tmp/$USER}/xilinx_user_data_${SLURM_JOB_ID}"

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

VARIANT_NAME="h${WIDTH}_scaling"
PACKAGE_ROOT="$ROOT/transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
HLS_PROJECT="$PACKAGE_ROOT/build/hls/cora_po2_qat_${VARIANT_NAME}_2024_1"
HLS_XML="$HLS_PROJECT/solution1/syn/report/graphsage_po2_qat_partitioned_csynth.xml"
RUN_NAME="qat_dsp_${VARIANT_NAME}_route_default"
OUTPUT_DIR="$ROOT/build/vivado_sweep/$RUN_NAME"

cd "$ROOT"
mkdir -p campaigns/tns_final/logs "$XILINX_LOCAL_USER_DATA" "$OUTPUT_DIR"

if [[ ! -f "$HLS_XML" ]]; then
    echo "MISSING_HLS_CSYNTH_REPORT=$HLS_XML"
    echo "Run: sbatch --export=ALL,WIDTH=$WIDTH full_width_pipeline.sbatch first" >&2
    exit 1
fi

DSP_COUNT="$(sed -n 's:.*<DSP>\([0-9][0-9]*\)</DSP>.*:\1:p' "$HLS_XML" | head -n 1)"
MAX_HLS_DSP="${MAX_HLS_DSP:-512}"
if [[ -z "$DSP_COUNT" ]]; then
    echo "MISSING_HLS_DSP_COUNT=$HLS_XML"
    exit 1
fi
if [[ "$DSP_COUNT" -gt "$MAX_HLS_DSP" ]]; then
    echo "VARIANT_DSP_GATE_WARNING=$DSP_COUNT limit=$MAX_HLS_DSP continuing=1"
else
    echo "VARIANT_DSP_GATE_PASS=$DSP_COUNT limit=$MAX_HLS_DSP"
fi

cat > "$OUTPUT_DIR/variant_manifest.txt" <<EOF
variant=$VARIANT_NAME
width=$WIDTH
l1_root_mask=0
l1_neighbor_mask=0
l2_root_mask=0
l2_neighbor_mask=0
aggregation_mode=4
physical_strategy=common (A3-equivalent: Default/Default, no retime)
hls_dsp=$DSP_COUNT
hls_project=$HLS_PROJECT
EOF

export VARIANT_NAME
"$VIVADO_BIN" -mode batch -nolog -nojournal \
    -source campaigns/qat_dsp_partitioning/hls/build_variant_checkpoint.tcl

export INPUT_CHECKPOINT="$ROOT/build/vivado_sweep/qat_dsp_${VARIANT_NAME}_post_synth.dcp"
export RUN_NAME OUTPUT_DIR
export PLACE_DIRECTIVE=Default
export ROUTE_DIRECTIVE=Default
export SCREEN_ONLY=0
export USE_TNS_CLEANUP=1
export USE_POST_PHYS=1
export POST_PLACE_PHYS_DIRECTIVE=""
export USE_RETIME=0
"$VIVADO_BIN" -mode batch -nolog -nojournal -source hls/run_vivado_int8_po2_strategy.tcl
