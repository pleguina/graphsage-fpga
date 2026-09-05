"""
Training script for QAT v2 GraphSAGE model.

Pipeline:
    1. Load or train the reduced float model (1433→16→24→7)
  2. Initialize ReducedGraphSAGEQATv2 from the float checkpoint
  3. Calibrate fake-quantizers (frozen observers, no weight update)
  4. Fine-tune with QAT (observers frozen, fake-quant active)
  5. Save the best checkpoint to build/models/qat_v2_best.pth

Usage:
  cd src && python train_qat_v2.py
    cd src && python train_qat_v2.py --root-weight
  cd src && python train_qat_v2.py --epochs 300 --lr 0.0003
"""

import argparse
import os
import sys

import torch
import torch.nn.functional as F
from torch_geometric.data import Data
from torch_geometric.datasets import Planetoid
from torch_geometric.transforms import NormalizeFeatures

torch.serialization.add_safe_globals([Data])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model_base import ReducedGraphSAGE
from model_qat_v2 import ReducedGraphSAGEQATv2, train_qat_v2

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_ROOT, "build", "models")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
def load_cora():
    dataset = Planetoid(root=DATA_DIR, name="Cora", transform=NormalizeFeatures())
    return dataset, dataset[0]


def train_float_model(dataset, data, model_path, root_weight=False,
                      epochs=200, lr=0.01, dropout=0.5):
    print("\n" + "=" * 60)
    print("Training Reduced Float GraphSAGE")
    print("=" * 60)

    model = ReducedGraphSAGE(
        in_channels=dataset.num_features,
        in_channels_reduced=16,
        hidden_channels=24,
        out_channels=dataset.num_classes,
        dropout=dropout,
        use_projection=True,
        root_weight=root_weight,
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)

    best_val_acc = 0.0
    best_state = None

    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()
        out = model(data.x, data.edge_index)
        loss = F.cross_entropy(out[data.train_mask], data.y[data.train_mask])
        loss.backward()
        optimizer.step()

        if epoch % 20 == 0 or epoch == epochs:
            model.eval()
            with torch.no_grad():
                out = model(data.x, data.edge_index)
                pred = out.argmax(dim=1)
                val_acc = (pred[data.val_mask] == data.y[data.val_mask]).float().mean().item()
                test_acc = (pred[data.test_mask] == data.y[data.test_mask]).float().mean().item()
            print(
                f"Epoch {epoch:03d}: loss={loss.item():.4f}  "
                f"val={val_acc:.4f}  test={test_acc:.4f}"
            )
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_state = {k: v.clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)

    model.eval()
    with torch.no_grad():
        out = model(data.x, data.edge_index)
        pred = out.argmax(dim=1)
        test_acc = (pred[data.test_mask] == data.y[data.test_mask]).float().mean().item()
    print(f"\nFloat model best test accuracy: {test_acc*100:.2f}%")

    os.makedirs(MODELS_DIR, exist_ok=True)
    torch.save(
        {"model_state_dict": model.state_dict(), "test_acc": test_acc},
        model_path,
    )
    print(f"Saved to {model_path}")

    return model


def main():
    parser = argparse.ArgumentParser(description="Train QAT v2 GraphSAGE")
    parser.add_argument("--epochs", type=int, default=200, help="QAT fine-tune epochs")
    parser.add_argument("--lr", type=float, default=0.0005, help="QAT learning rate")
    parser.add_argument("--calib-batches", type=int, default=50)
    parser.add_argument("--float-epochs", type=int, default=200,
                        help="Float training epochs (if no checkpoint)")
    parser.add_argument("--root-weight", action="store_true",
                        help="Train the root-enabled QAT model and save qat_v2_root_best.pth")
    args = parser.parse_args()

    float_model_name = "reduced_graphsage_best.pth" if args.root_weight else "reduced_graphsage_no_root_best.pth"
    qat_model_name = "qat_v2_root_best.pth" if args.root_weight else "qat_v2_best.pth"
    float_model_path = os.path.join(MODELS_DIR, float_model_name)
    qat_model_path = os.path.join(MODELS_DIR, qat_model_name)

    dataset, data = load_cora()

    # ------------------------------------------------------------------ #
    # Step 1: float model
    # ------------------------------------------------------------------ #
    float_model = ReducedGraphSAGE(
        in_channels=dataset.num_features,
        in_channels_reduced=16,
        hidden_channels=24,
        out_channels=dataset.num_classes,
        dropout=0.5,
        use_projection=True,
        root_weight=args.root_weight,
    )

    if os.path.exists(float_model_path):
        print(f"Loading float model from {float_model_path}")
        ckpt = torch.load(float_model_path, weights_only=False)
        float_model.load_state_dict(ckpt["model_state_dict"])
    else:
        float_model = train_float_model(
            dataset,
            data,
            float_model_path,
            root_weight=args.root_weight,
            epochs=args.float_epochs,
        )

    float_model.eval()
    with torch.no_grad():
        out = float_model(data.x, data.edge_index)
        pred = out.argmax(dim=1)
        float_acc = (pred[data.test_mask] == data.y[data.test_mask]).float().mean().item()
    print(f"Float model test accuracy: {float_acc*100:.2f}%")

    # ------------------------------------------------------------------ #
    # Step 2: create QAT v2 model and init from float weights
    # ------------------------------------------------------------------ #
    print("\n" + "=" * 60)
    print(f"QAT v2 Training (root_weight={args.root_weight})")
    print("=" * 60)

    qat_model = ReducedGraphSAGEQATv2(
        in_channels=dataset.num_features,
        in_channels_reduced=16,
        hidden_channels=24,
        out_channels=dataset.num_classes,
        dropout=0.5,
        use_projection=True,
        root_weight=args.root_weight,
        num_bits=8,
    )
    qat_model.load_from_float_model(float_model)

    # ------------------------------------------------------------------ #
    # Step 3: calibrate observers
    # ------------------------------------------------------------------ #
    qat_model.calibrate(data, num_batches=args.calib_batches)
    qat_model.print_quant_info()

    # ------------------------------------------------------------------ #
    # Step 4: QAT fine-tuning
    # ------------------------------------------------------------------ #
    print(f"\nFine-tuning for {args.epochs} epochs at lr={args.lr} ...")
    qat_model = train_qat_v2(qat_model, data, epochs=args.epochs, lr=args.lr)

    # ------------------------------------------------------------------ #
    # Step 5: evaluate and save
    # ------------------------------------------------------------------ #
    qat_model.eval()
    qat_model.enable_fake_quant()
    with torch.no_grad():
        out = qat_model(data.x, data.edge_index)
        pred = out.argmax(dim=1)
        qat_acc = (pred[data.test_mask] == data.y[data.test_mask]).float().mean().item()

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(f"Float model test accuracy : {float_acc*100:.2f}%")
    print(f"QAT v2 test accuracy      : {qat_acc*100:.2f}%")
    print(f"Quantization gap          : {(float_acc - qat_acc)*100:.2f}%")

    os.makedirs(MODELS_DIR, exist_ok=True)
    torch.save(
        {
            "model_state_dict": qat_model.state_dict(),
            "test_acc": qat_acc,
            "float_acc": float_acc,
            "root_weight": args.root_weight,
            "training_args": vars(args),
        },
        qat_model_path,
    )
    print(f"\nSaved QAT v2 model to {qat_model_path}")


if __name__ == "__main__":
    main()
