#!/usr/bin/env bash
#SBATCH --job-name=graphsage-collect
#SBATCH --partition=batch
#SBATCH --nodelist=gae034
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --output=slurm/logs/collect_%j.out
#SBATCH --error=slurm/logs/collect_%j.err

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the extracted bundle root}"
mkdir -p "$ROOT/slurm/logs"
cd "$ROOT"
python3 scripts/run_vivado_int8_po2_sweep.py collect