#!/usr/bin/env bash
#SBATCH --job-name=qat-scaling-venv
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=campaigns/tns_final/logs/build_training_venv_%j.out
#SBATCH --error=campaigns/tns_final/logs/build_training_venv_%j.err

set -euo pipefail
ROOT="${SLURM_SUBMIT_DIR:?Submit from repository root}"
cd "$ROOT"
mkdir -p campaigns/tns_final/logs

PYTHON_BIN="/nfs/fanae/vivado/2025.2/lnx64/tools/vcxx/third-party/python-linux/user/3.10.10/bin/python3"
VENV_DIR="$ROOT/campaigns/tns_final/scaling_venv"

echo "HOST=$(hostname)"
"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch
python -m pip install torch_geometric
python -m pip install numpy

python - <<'EOF'
import torch, torch_geometric
print("torch", torch.__version__)
print("torch_geometric", torch_geometric.__version__)
from torch_geometric.datasets import Planetoid, PPI
from torch_geometric.transforms import NormalizeFeatures
print("PyG datasets import OK")
EOF
echo "VENV_BUILD_COMPLETE=1"
