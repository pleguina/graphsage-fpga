#!/usr/bin/env bash
#SBATCH --job-name=tns-extract-all
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=campaigns/tns_final/logs/extract_all_%j.out
#SBATCH --error=campaigns/tns_final/logs/extract_all_%j.err

# Extraction / paper-data generation (plan Section 21, Job 13). Submit last
# with --dependency=afterany:<all new job IDs> so it always reads final
# reports, whether or not every upstream job succeeded.
set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
cd "$ROOT"
mkdir -p campaigns/tns_final/logs campaigns/tns_final/paper_data

PYTHON_BIN="${PYTHON_BIN:-python3}"
cd campaigns/tns_final/scripts
"$PYTHON_BIN" build_paper_tables.py
"$PYTHON_BIN" aggregate_ml_accuracy_table.py
