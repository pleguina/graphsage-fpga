#!/usr/bin/env bash
#SBATCH --job-name=collect-root-po2
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --output=exploration/slurm/logs/collect_updated_root_vivado_%j.out
#SBATCH --error=exploration/slurm/logs/collect_updated_root_vivado_%j.err

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:?Submit this job from the repository root}"
cd "$ROOT"
python3 exploration/scripts/collect_updated_root_vivado_results.py