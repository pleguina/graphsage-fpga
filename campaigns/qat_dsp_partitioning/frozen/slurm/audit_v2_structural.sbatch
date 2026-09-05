#!/usr/bin/env bash
#SBATCH --job-name=qat-v2-structural
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=campaigns/qat_dsp_partitioning/logs/audit_v2_structural_%j.out
#SBATCH --error=campaigns/qat_dsp_partitioning/logs/audit_v2_structural_%j.err

set -euo pipefail
export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
RUN_DIR="$ROOT/build/vivado_sweep/qat_dsp_V2_route_default"
CHECKPOINT="$RUN_DIR/final.dcp"
AUDIT_CSV="$RUN_DIR/reports/structural_timing_paths.csv"
OUTPUT_JSON="$RUN_DIR/reports/structural_timing_table.json"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

cd "$ROOT"
mkdir -p slurm/logs
"$VIVADO_BIN" -mode batch -nolog -nojournal \
    -source campaigns/qat_dsp_partitioning/hls/audit_structural_timing.tcl \
    -tclargs "$CHECKPOINT" "$AUDIT_CSV"
python3 campaigns/qat_dsp_partitioning/analysis/build_structural_timing_table.py \
    "$AUDIT_CSV" "$OUTPUT_JSON"