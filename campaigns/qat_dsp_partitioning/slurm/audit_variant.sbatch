#!/usr/bin/env bash
#SBATCH --job-name=qat-dsp-audit
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=campaigns/qat_dsp_partitioning/logs/audit_variant_%j.out
#SBATCH --error=campaigns/qat_dsp_partitioning/logs/audit_variant_%j.err

set -euo pipefail
: "${VARIANT_NAME:?Missing VARIANT_NAME}"

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
RUN_DIR="$ROOT/build/vivado_sweep/qat_dsp_${VARIANT_NAME}_route_default"
CHECKPOINT="$RUN_DIR/final.dcp"
AUDIT_CSV="$RUN_DIR/reports/channel_criticality_paths.csv"
OUTPUT_JSON="$RUN_DIR/reports/channel_criticality_table.json"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

cd "$ROOT"
mkdir -p slurm/logs
if [[ ! -f "$CHECKPOINT" ]]; then
    echo "MISSING_CHECKPOINT=$CHECKPOINT"
    exit 1
fi

"$VIVADO_BIN" -mode batch -nolog -nojournal \
    -source campaigns/qat_dsp_partitioning/hls/audit_channel_criticality.tcl \
    -tclargs "$CHECKPOINT" "$AUDIT_CSV"
python3 campaigns/qat_dsp_partitioning/analysis/build_channel_criticality_table.py \
    --audit-csv "$AUDIT_CSV" \
    --output-json "$OUTPUT_JSON"