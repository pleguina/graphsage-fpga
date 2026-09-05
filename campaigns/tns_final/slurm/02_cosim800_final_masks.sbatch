#!/usr/bin/env bash
#SBATCH --job-name=tns-cosim800-final
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=04:00:00
#SBATCH --output=campaigns/tns_final/logs/cosim800_final_masks_%j.out
#SBATCH --error=campaigns/tns_final/logs/cosim800_final_masks_%j.err

# Closes the gap flagged in the 2026-08-29 verification audit (tns_verification.md
# Section 7): the existing 800-transaction RTL cosim PASS (verify800_cosim_fixed)
# was never confirmed to use the same DSP/pipeline masks as the final frozen
# V2A1_allcut architecture. This reruns the same 800-graph corpus
# (po2_qat_root_dynamic_const_weights_partitioned_verify800, which pulls its
# 800 test vectors from root_dynamic_const_weights_verify800/generated/) with
# the exact final masks from paper_data/architecture_ablation.csv row A5 /
# campaigns/tns_final/slurm/01_csim_final.sbatch, run through full RTL cosim.
set -euo pipefail

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export HLS_ACTION=cosim
export VARIANT_NAME=V2A1_allcut_verify800_finalmasks
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
SOURCE_DIR="$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/hls/po2_qat_root_dynamic_const_weights_partitioned_verify800"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

cd "$ROOT"
mkdir -p campaigns/tns_final/logs "$PACKAGE_ROOT/build/hls/hls"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/cora_graphsage_hls_test_bundle"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/hls/cora_graphsage_hls_test_bundle"

cd "$PACKAGE_ROOT"
"$VITIS_RUN_BIN" --mode hls --tcl "$SOURCE_DIR/run_hls_variant.tcl"
