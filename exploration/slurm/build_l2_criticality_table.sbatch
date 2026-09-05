#!/usr/bin/env bash
#SBATCH --job-name=l2-criticality-table
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=exploration/slurm/logs/l2_criticality_table_%j.out
#SBATCH --error=exploration/slurm/logs/l2_criticality_table_%j.err

set -euo pipefail

export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-<LICENSE_SERVER>}"
export LM_LICENSE_FILE="${LM_LICENSE_FILE:-<LICENSE_SERVER>}"

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
cd "$ROOT"
mkdir -p exploration/slurm/logs

CHECKPOINT="$ROOT/build/vivado_sweep/updated_qat_partitioned_baseline_route_default/final.dcp"
AUDIT_CSV="$ROOT/build/vivado_sweep/updated_qat_partitioned_baseline_route_default/reports/l2_channel_criticality_paths.csv"
VIVADO_BIN="${VIVADO_BIN:-/nfs/fanae/vivado/2025.2/Vivado/bin/vivado}"

if [[ ! -f "$CHECKPOINT" ]]; then
    echo "MISSING_CHECKPOINT=$CHECKPOINT"
    exit 1
fi

"$VIVADO_BIN" -mode batch -nolog -nojournal \
    -source campaigns/qat_dsp_partitioning/exploration/hls/audit_channel_criticality.tcl \
    -tclargs "$CHECKPOINT" "$AUDIT_CSV"

python3 campaigns/qat_dsp_partitioning/analysis/build_channel_criticality_table.py
