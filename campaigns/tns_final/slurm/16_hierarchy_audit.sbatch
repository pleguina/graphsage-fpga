#!/usr/bin/env bash
#SBATCH --job-name=tns-hierarchy-audit
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=campaigns/tns_final/logs/hierarchy_audit_%j.out
#SBATCH --error=campaigns/tns_final/logs/hierarchy_audit_%j.err

# Hierarchy / physical-exposure validation (plan Section 16): counts how
# many of the 62 expected (layer, branch, channel) units are identifiable
# hierarchical cells in the final routed checkpoint.
set -euo pipefail

VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"
ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
cd "$ROOT"
mkdir -p campaigns/tns_final/logs campaigns/tns_final/results/ablation

CHECKPOINT="$ROOT/build/vivado_sweep/qat_dsp_V2A1_allcut_ssi_retime_route/final.dcp"
OUTPUT_CSV="$ROOT/campaigns/tns_final/results/ablation/hierarchy_audit_A5.csv"

if [[ ! -f "$CHECKPOINT" ]]; then
    echo "MISSING_CHECKPOINT=$CHECKPOINT"
    exit 1
fi

"$VIVADO_BIN" -mode batch -nolog -nojournal \
    -source campaigns/tns_final/scripts/hierarchy_audit.tcl \
    -tclargs "$CHECKPOINT" "$OUTPUT_CSV"
