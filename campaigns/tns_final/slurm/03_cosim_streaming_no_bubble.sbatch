#!/usr/bin/env bash
#SBATCH --job-name=tns-cosim-nobubble
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=03:00:00
#SBATCH --output=campaigns/tns_final/logs/cosim_streaming_no_bubble_%j.out
#SBATCH --error=campaigns/tns_final/logs/cosim_streaming_no_bubble_%j.err

# Explicit no-bubble II=1 RTL co-simulation (docs/tns_campaign_status.md
# OPEN item): 1024 back-to-back transactions, both edge_mask topology AND
# node features varying on every transaction (generate_streaming_no_bubble_
# corpus.py), run through HLS_ACTION=cosim (RTL-accurate C/RTL
# co-simulation, not csim) against the exact final V2A1_allcut
# architecture/masks. Bit-exactness is checked the same way as the
# existing 256/800-transaction tests; the NEW evidence this test adds is
# extracted afterward from the cosim log's own RTL-timestamped progress
# lines (see analyze_cosim_bubble_timing.py) - those timestamps are ground
# truth for "one transaction retired per clock, no idle cycles" for this
# ap_ctrl_none/PIPELINE II=1 design.
#
# Uses a fully self-contained copy of the HLS source directory
# (po2_qat_root_dynamic_const_weights_partitioned_streaming_no_bubble/,
# not the shared canonical one) with two fixes applied, matching the
# pre-existing po2_qat_root_dynamic_const_weights_partitioned_verify800/
# copy's own pattern (discovered after 03's first attempt failed with
# "C/RTL co-simulation cannot be started... Synthesis was not successful"):
#   1. source_dir in run_hls_variant.tcl repointed at this copy's own
#      directory (the base tcl hardcodes it back to the canonical dir
#      regardless of which copy invokes it - a plain directory copy alone
#      is not enough, as 02_csim_density_coverage.sbatch's shared-header
#      edit/restore approach had to work around).
#   2. the cosim action block extended to run csynth_design before
#      cosim_design - the base tcl only ever runs ONE action per
#      invocation, so a bare HLS_ACTION=cosim always fails on a freshly
#      -reset project with no RTL yet.
# This touches no shared state at all, unlike 02's approach - cleaner for
# a cosim run that needs a real RTL synthesis pass anyway.
set -euo pipefail

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export HLS_ACTION=cosim
export VARIANT_NAME=streaming_no_bubble_1024
export L1_ROOT_MASK=0
export L1_NEIGHBOR_MASK=0x1004
export L2_ROOT_MASK=0
export L2_NEIGHBOR_MASK=0
export AGGREGATION_MODE=4
export L1_ROOT_ACC_PIPELINE_MASK=0xFFFFFF
export L1_NEIGHBOR_ACC_PIPELINE_MASK=0xFFFFFF
export L2_ROOT_ACC_PIPELINE_MASK=0x7F
export L2_NEIGHBOR_ACC_PIPELINE_MASK=0x7F

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
PACKAGE_ROOT="$ROOT/transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
SOURCE_DIR="$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/hls/po2_qat_root_dynamic_const_weights_partitioned_streaming_no_bubble"
STREAMING_CORPUS="$ROOT/campaigns/qat_dsp_partitioning/frozen/source/root_graphsage_constants_streaming_no_bubble.h"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

cd "$ROOT"
mkdir -p campaigns/tns_final/logs "$PACKAGE_ROOT/build/hls/hls"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/cora_graphsage_hls_test_bundle"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/hls/cora_graphsage_hls_test_bundle"

if [[ ! -f "$STREAMING_CORPUS" ]]; then
    echo "MISSING_STREAMING_CORPUS=$STREAMING_CORPUS" >&2
    echo "Run: campaigns/tns_final/scaling_venv/bin/python3 campaigns/tns_final/scripts/generate_streaming_no_bubble_corpus.py" >&2
    exit 1
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "MISSING_SELF_CONTAINED_VARIANT_DIR=$SOURCE_DIR" >&2
    echo "This variant copy (with its source_dir/cosim-action fixes applied) must exist before submitting - see this script's header comment." >&2
    exit 1
fi

cd "$PACKAGE_ROOT"
"$VITIS_RUN_BIN" --mode hls --tcl "$SOURCE_DIR/run_hls_variant.tcl"
