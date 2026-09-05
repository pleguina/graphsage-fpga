#!/usr/bin/env bash
#SBATCH --job-name=tns-width-pipeline
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=campaigns/tns_final/logs/width_pipeline_%j.out
#SBATCH --error=campaigns/tns_final/logs/width_pipeline_%j.err

# Hidden-width scaling study (plan Section 12/20): trains a fresh QAT-PO2
# model at hidden width WIDTH, exports it to HLS constants, generates the
# channelized partitioned source for that width, and runs HLS csynth.
# Mirrors the existing H=8 proof-of-concept
# (po2_qat_root_dynamic_const_weights_partitioned_h8/, produced ad hoc in
# an earlier session) but as a reusable, parametrized pipeline.
#
# Physical policy held fixed across widths per the plan's "do not
# hand-optimize each width" rule: all-fabric multipliers (DSP masks=0,
# matching the A3 ablation baseline), full pipelining on every channel.
set -euo pipefail
: "${WIDTH:?Missing WIDTH (e.g. 16 or 32)}"

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
# Job-unique Xilinx scratch dir: without this, two vitis-run jobs landing on
# the same node concurrently silently cross-contaminate each other's HLS
# results (observed 2026-08-30: two widths produced byte-identical, wrong
# csynth reports when run at the same time without this).
export XILINX_LOCAL_USER_DATA="${SLURM_TMPDIR:-/tmp/$USER}/xilinx_user_data_${SLURM_JOB_ID}"

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
PACKAGE_ROOT="$ROOT/transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
P="$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle"
TESTS="$P/tests"
SCALING_OUT="$ROOT/campaigns/tns_final/scaling"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

cd "$ROOT"
mkdir -p campaigns/tns_final/logs "$SCALING_OUT" "$XILINX_LOCAL_USER_DATA"

echo "=== [1/5] Training float+QAT at hidden=$WIDTH ==="
source campaigns/tns_final/scaling_venv/bin/activate
python3 "$TESTS/run_root_planetoid_study_scaling.py" \
    --hidden "$WIDTH" --datasets Cora --seed 42 \
    --output-dir "$SCALING_OUT/root_planetoid_h${WIDTH}"

echo "=== [2/5] PO2-QAT projection at hidden=$WIDTH ==="
python3 "$TESTS/run_po2_qat_study_scaling.py" \
    --hidden "$WIDTH" --datasets Cora --seed 42 \
    --planetoid-root "$SCALING_OUT/root_planetoid_h${WIDTH}" \
    --output-dir "$SCALING_OUT/po2_qat_h${WIDTH}"

echo "=== [3/5] Exporting HLS constants (self-validated against PyTorch model) ==="
CONST_DIR="$P/hls/root_dynamic_const_weights_h${WIDTH}"
mkdir -p "$CONST_DIR"
# NOTE: graphsage_root_dynamic_const_weights.h has a hardcoded ABSOLUTE
# #include of its sibling generated/root_graphsage_constants.h (not a
# relative path) - a naive cp would silently keep pointing at h8's old
# constants, causing this width's csynth to read out-of-bounds past an
# 8-wide array. Rewrite that one line to point at this width's own dir.
sed "s|root_dynamic_const_weights_h8/generated|root_dynamic_const_weights_h${WIDTH}/generated|" \
    "$P/hls/root_dynamic_const_weights_h8/graphsage_root_dynamic_const_weights.h" \
    > "$CONST_DIR/graphsage_root_dynamic_const_weights.h"
python3 "$P/hls/root_dynamic_const_weights/generate_verification_corpus.py" \
    --checkpoint "$SCALING_OUT/po2_qat_h${WIDTH}/cora/seed_42/po2_qat_root.pth" \
    --generated-root "$CONST_DIR/generated" \
    --test-events 256

echo "=== [4/5] Generating partitioned channel source for hidden=$WIDTH ==="
PART_DIR="$P/hls/po2_qat_root_dynamic_const_weights_partitioned_h${WIDTH}"
mkdir -p "$PART_DIR"
cp "$P/hls/po2_qat_root_dynamic_const_weights_partitioned_verify10k/testbench_partitioned.cpp" "$PART_DIR/"
sed "s|root_dynamic_const_weights_h8|root_dynamic_const_weights_h${WIDTH}|" \
    "$P/hls/po2_qat_root_dynamic_const_weights_partitioned_h8/graphsage_po2_qat_partitioned.h" \
    > "$PART_DIR/graphsage_po2_qat_partitioned.h"
python3 "$ROOT/campaigns/tns_final/scripts/generate_partitioned_cpp.py" \
    --hidden-features "$WIDTH" \
    --output "$PART_DIR/graphsage_po2_qat_partitioned.cpp"
sed "s|po2_qat_root_dynamic_const_weights_partitioned_h8|po2_qat_root_dynamic_const_weights_partitioned_h${WIDTH}|" \
    "$P/hls/po2_qat_root_dynamic_const_weights_partitioned_h8/run_hls_variant.tcl" \
    > "$PART_DIR/run_hls_variant.tcl"
deactivate

echo "=== [5/5] HLS csynth for hidden=$WIDTH ==="
PIPELINE_MASK_L1=$(( (1 << WIDTH) - 1 ))
export HLS_ACTION=csynth
export VARIANT_NAME="h${WIDTH}_scaling"
export GS_HIDDEN_FEATURES="$WIDTH"
export L1_ROOT_MASK=0
export L1_NEIGHBOR_MASK=0
export L2_ROOT_MASK=0
export L2_NEIGHBOR_MASK=0
export AGGREGATION_MODE=4
export L1_ROOT_ACC_PIPELINE_MASK=$PIPELINE_MASK_L1
export L1_NEIGHBOR_ACC_PIPELINE_MASK=$PIPELINE_MASK_L1
export L2_ROOT_ACC_PIPELINE_MASK=0x7F
export L2_NEIGHBOR_ACC_PIPELINE_MASK=0x7F

mkdir -p "$PACKAGE_ROOT/build/hls/hls"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/cora_graphsage_hls_test_bundle"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/hls/cora_graphsage_hls_test_bundle"

cd "$PACKAGE_ROOT"
"$VITIS_RUN_BIN" --mode hls --tcl "$PART_DIR/run_hls_variant.tcl"
