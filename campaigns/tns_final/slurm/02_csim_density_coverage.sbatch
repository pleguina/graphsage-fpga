#!/usr/bin/env bash
#SBATCH --job-name=tns-csim-density
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=campaigns/tns_final/logs/csim_density_coverage_%j.out
#SBATCH --error=campaigns/tns_final/logs/csim_density_coverage_%j.err

# Edge-density/topology coverage CSim (docs/tns_campaign_status.md OPEN
# item): runs the SAME final V2A1_allcut architecture/masks as
# 01_csim_final.sbatch, but against the 14-graph structured corpus from
# campaigns/tns_final/scripts/generate_edge_density_corpus.py (node
# features held fixed, edge_mask topology swept from |E|=0 to |E|=64,
# including explicit degree-0/1/max-degree nodes and canonical topologies).
#
# run_hls_variant.tcl hardcodes its source_dir back to the ONE canonical
# "po2_qat_root_dynamic_const_weights_partitioned" directory regardless of
# which copy of the tcl script is invoked (confirmed by reading it) - so
# there is no way to point it at an alternate corpus via a sibling
# directory copy. Instead this script temporarily repoints that directory's
# graphsage_po2_qat_partitioned.h at the density-coverage header via an
# absolute-path ROOT_CONSTANTS_HEADER override, runs csim under a UNIQUE
# VARIANT_NAME (so it builds an isolated project, not the production one),
# then restores the original file. The restore runs under `trap` so it
# fires even on failure/interruption - this shared file must never be left
# in the swapped state.
set -euo pipefail

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"
export HLS_ACTION=csim
export VARIANT_NAME=density_coverage
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
SOURCE_DIR="$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/hls/po2_qat_root_dynamic_const_weights_partitioned"
HEADER="$SOURCE_DIR/graphsage_po2_qat_partitioned.h"
DENSITY_CORPUS="$ROOT/campaigns/qat_dsp_partitioning/frozen/source/root_graphsage_constants_density_coverage.h"
VITIS_RUN_BIN="${VITIS_RUN_BIN:-/nfs/fanae/vivado/2025.2/Vitis/bin/vitis-run}"

cd "$ROOT"
mkdir -p campaigns/tns_final/logs "$PACKAGE_ROOT/build/hls/hls"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/cora_graphsage_hls_test_bundle"
ln -sfn "$PACKAGE_ROOT/hls/cora_graphsage_hls_test_bundle" "$PACKAGE_ROOT/build/hls/hls/cora_graphsage_hls_test_bundle"

if [[ ! -f "$DENSITY_CORPUS" ]]; then
    echo "MISSING_DENSITY_CORPUS=$DENSITY_CORPUS" >&2
    echo "Run: campaigns/tns_final/scaling_venv/bin/python3 campaigns/tns_final/scripts/generate_edge_density_corpus.py" >&2
    exit 1
fi

cp "$HEADER" "${HEADER}.orig_backup"
restore_header() {
    mv "${HEADER}.orig_backup" "$HEADER"
    echo "RESTORED_ORIGINAL_HEADER=$HEADER"
}
trap restore_header EXIT

sed -i "s|^#define ROOT_CONSTANTS_HEADER .*|#define ROOT_CONSTANTS_HEADER \"$DENSITY_CORPUS\"|" "$HEADER"
echo "SWAPPED_HEADER_TO=$DENSITY_CORPUS"
grep -n "ROOT_CONSTANTS_HEADER" "$HEADER"

cd "$PACKAGE_ROOT"
"$VITIS_RUN_BIN" --mode hls --tcl "$SOURCE_DIR/run_hls_variant.tcl"
