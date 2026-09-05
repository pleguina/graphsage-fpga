#!/usr/bin/env python3
"""
Controlled software-only comparison of three quantization-scale policies for
the Cora root+neighbor GraphSAGE model (docs/tns_campaign_status.md OPEN
item, "true QAT-PO2 as a controlled additional experiment"):

  QAT           - standard QAT (model_qat_v2.py, unmodified), arbitrary
                  per-tensor symmetric scales, evaluated as-is.
  QAT -> PO2    - the SAME trained QAT weights/scales from the row above,
                  with every fake-quantizer's scale snapped to the nearest
                  power of two at *evaluation* time only (no retraining).
                  This is what the currently-deployed hardware actually
                  runs (generate_root_int8_po2.py's po2_shift()), but
                  evaluated here on the full Cora test set rather than the
                  8-node historical regression graph.
  True QAT-PO2  - a second model, trained from the same float-model
                  initialization and same hyperparameters, but with the
                  PO2 scale snap applied on *every* forward pass during QAT
                  fine-tuning itself (PO2 constraint present during
                  training, not just projected afterward).

This script does not touch the frozen model_qat_v2.py source. It
monkeypatches its fake-quantizer factory functions only for the duration of
constructing the "True QAT-PO2" model, and only within this process.

Scope: Cora only, root_weight=True, hidden=24 - this is the architecture
actually implemented in hardware (16->24->7, per
docs/tns_graphsage_full_campaign_plan.md). CiteSeer/PubMed/PPI are out of
scope for this pass: no reproducible multi-dataset training driver exists
in this repository (see docs/tns_campaign_status.md's tool_versions gap) -
extending this comparison to those datasets requires rebuilding that
driver, which is separate, larger follow-up work, not this controlled
experiment.

Usage:
  scaling_venv/bin/python3 campaigns/tns_final/scripts/true_qat_po2_experiment.py \
      --seeds 42 43 44 45 46 --epochs 200 --lr 0.0005 --float-epochs 200
"""
import argparse
import contextlib
import copy
import json
import os
import sys
from pathlib import Path

import torch
import torch.nn.functional as F

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLE_SRC = (
    REPO_ROOT
    / "hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/src"
)
DATA_DIR = (
    REPO_ROOT
    / "hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/data"
)
OUTPUT_DIR = REPO_ROOT / "campaigns/tns_final/results/true_qat_po2"

sys.path.insert(0, str(BUNDLE_SRC))

from torch_geometric.datasets import Planetoid  # noqa: E402
from torch_geometric.transforms import NormalizeFeatures  # noqa: E402

import model_qat_v2 as mqv2  # noqa: E402
from model_base import ReducedGraphSAGE  # noqa: E402
from model_qat_v2 import ReducedGraphSAGEQATv2, train_qat_v2  # noqa: E402
from torch.ao.quantization.fake_quantize import FakeQuantize  # noqa: E402
from torch.ao.quantization.observer import (  # noqa: E402
    MovingAverageMinMaxObserver,
    MovingAveragePerChannelMinMaxObserver,
)


def po2_round(scale: torch.Tensor) -> torch.Tensor:
    """Snap a (positive) scale tensor to the nearest power of two."""
    safe = torch.clamp(scale, min=1e-12)
    return torch.pow(2.0, torch.round(torch.log2(safe)))


class FakeQuantizePO2(FakeQuantize):
    """FakeQuantize whose *applied* scale is PO2-snapped on every forward.

    Observer statistics are collected identically to the base class (so
    calibration behaves the same); only the scale actually handed to the
    fake-quantize op is rounded to a power of two, both during QAT
    fine-tuning and at eval time. This is the "PO2 constraint present
    during training" case (category C), vs. model_qat_v2's own FakeQuantize
    which is category B (arbitrary scale throughout, projected to PO2 only
    at export).
    """

    def forward(self, X):
        if self.observer_enabled[0] == 1:
            self.activation_post_process(X.detach())
            _scale, _zero_point = self.calculate_qparams()
            _scale = _scale.to(self.scale.device)
            _zero_point = _zero_point.to(self.zero_point.device)
            if self.scale.shape != _scale.shape:
                self.scale.resize_(_scale.shape)
                self.zero_point.resize_(_zero_point.shape)
            self.scale.copy_(_scale)
            self.zero_point.copy_(_zero_point)

        if self.fake_quant_enabled[0] == 1:
            applied_scale = po2_round(self.scale)
            if self.is_per_channel:
                X = torch.fake_quantize_per_channel_affine(
                    X, applied_scale, self.zero_point, self.ch_axis,
                    self.quant_min, self.quant_max,
                )
            else:
                X = torch.fake_quantize_per_tensor_affine(
                    X, applied_scale, self.zero_point,
                    self.quant_min, self.quant_max,
                )
        return X


def make_activation_fake_quant_po2(num_bits: int = 8) -> FakeQuantizePO2:
    if num_bits <= 8:
        qmin, qmax = -(2 ** (num_bits - 1)), (2 ** (num_bits - 1)) - 1
    else:
        qmin, qmax = -128, 127
    return FakeQuantizePO2(
        observer=MovingAverageMinMaxObserver,
        quant_min=qmin, quant_max=qmax,
        dtype=torch.qint8, qscheme=torch.per_tensor_symmetric,
        reduce_range=False,
    )


def make_weight_fake_quant_po2(num_bits: int = 8, per_channel: bool = False) -> FakeQuantizePO2:
    if num_bits <= 8:
        qmin, qmax = -(2 ** (num_bits - 1)), (2 ** (num_bits - 1)) - 1
    else:
        qmin, qmax = -128, 127
    if per_channel:
        return FakeQuantizePO2(
            observer=MovingAveragePerChannelMinMaxObserver,
            quant_min=qmin, quant_max=qmax,
            dtype=torch.qint8, qscheme=torch.per_channel_symmetric,
            reduce_range=False, ch_axis=0,
        )
    return FakeQuantizePO2(
        observer=MovingAverageMinMaxObserver,
        quant_min=qmin, quant_max=qmax,
        dtype=torch.qint8, qscheme=torch.per_tensor_symmetric,
        reduce_range=False,
    )


@contextlib.contextmanager
def po2_fake_quant_patch():
    orig_act, orig_w = mqv2.make_activation_fake_quant, mqv2.make_weight_fake_quant
    mqv2.make_activation_fake_quant = make_activation_fake_quant_po2
    mqv2.make_weight_fake_quant = make_weight_fake_quant_po2
    try:
        yield
    finally:
        mqv2.make_activation_fake_quant = orig_act
        mqv2.make_weight_fake_quant = orig_w


def load_cora():
    dataset = Planetoid(root=str(DATA_DIR), name="Cora", transform=NormalizeFeatures())
    return dataset, dataset[0]


def train_float_model(dataset, data, seed, epochs, lr=0.01, dropout=0.5):
    torch.manual_seed(seed)
    model = ReducedGraphSAGE(
        in_channels=dataset.num_features, in_channels_reduced=16,
        hidden_channels=24, out_channels=dataset.num_classes,
        dropout=dropout, use_projection=True, root_weight=True,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)
    best_val_acc, best_state = 0.0, None
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
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return model


def eval_accuracy(model, data, mask):
    model.eval()
    with torch.no_grad():
        out = model(data.x, data.edge_index)
        pred = out.argmax(dim=1)
        return (pred[mask] == data.y[mask]).float().mean().item()


def eval_with_po2_projected_scale(qat_model, data, mask):
    """QAT -> PO2: reuse the trained QAT model's weights, snap every
    fake-quantizer's scale to PO2 for this eval pass only, then restore."""
    saved = []
    for module in qat_model.modules():
        if isinstance(module, FakeQuantize):
            saved.append((module, module.scale.clone()))
            module.scale.copy_(po2_round(module.scale))
    try:
        acc = eval_accuracy(qat_model, data, mask)
    finally:
        for module, original_scale in saved:
            module.scale.copy_(original_scale)
    return acc


def run_one_seed(dataset, data, seed, epochs, lr, calib_batches, float_epochs):
    print(f"\n{'='*70}\nSEED {seed}\n{'='*70}")

    float_model = train_float_model(dataset, data, seed, float_epochs)
    float_acc = eval_accuracy(float_model, data, data.test_mask)
    print(f"float test acc: {float_acc:.4f}")

    # ---- QAT (category B training path; arbitrary scale) ----
    torch.manual_seed(seed)
    qat_model = ReducedGraphSAGEQATv2(
        in_channels=dataset.num_features, in_channels_reduced=16,
        hidden_channels=24, out_channels=dataset.num_classes,
        dropout=0.5, use_projection=True, root_weight=True, num_bits=8,
    )
    qat_model.load_from_float_model(float_model)
    qat_model.calibrate(data, num_batches=calib_batches)
    qat_model = train_qat_v2(qat_model, data, epochs=epochs, lr=lr, verbose=False)
    qat_model.eval()
    qat_model.enable_fake_quant()
    qat_acc = eval_accuracy(qat_model, data, data.test_mask)
    qat_po2_acc = eval_with_po2_projected_scale(qat_model, data, data.test_mask)
    print(f"QAT test acc:          {qat_acc:.4f}")
    print(f"QAT -> PO2 test acc:   {qat_po2_acc:.4f}")

    # ---- True QAT-PO2 (category C training path; PO2 scale during training) ----
    torch.manual_seed(seed)
    with po2_fake_quant_patch():
        true_po2_model = ReducedGraphSAGEQATv2(
            in_channels=dataset.num_features, in_channels_reduced=16,
            hidden_channels=24, out_channels=dataset.num_classes,
            dropout=0.5, use_projection=True, root_weight=True, num_bits=8,
        )
        true_po2_model.load_from_float_model(float_model)
        true_po2_model.calibrate(data, num_batches=calib_batches)
        true_po2_model = train_qat_v2(true_po2_model, data, epochs=epochs, lr=lr, verbose=False)
    true_po2_model.eval()
    true_po2_model.enable_fake_quant()
    true_po2_acc = eval_accuracy(true_po2_model, data, data.test_mask)
    print(f"True QAT-PO2 test acc: {true_po2_acc:.4f}")

    return {
        "seed": seed,
        "float_acc": float_acc,
        "qat_acc": qat_acc,
        "qat_to_po2_acc": qat_po2_acc,
        "true_qat_po2_acc": true_po2_acc,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44, 45, 46])
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--lr", type=float, default=0.0005)
    parser.add_argument("--calib-batches", type=int, default=50)
    parser.add_argument("--float-epochs", type=int, default=200)
    args = parser.parse_args()

    dataset, data = load_cora()
    results = [
        run_one_seed(dataset, data, seed, args.epochs, args.lr, args.calib_batches, args.float_epochs)
        for seed in args.seeds
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "cora_root24_results.json").write_text(json.dumps(results, indent=2) + "\n")

    import statistics
    print(f"\n{'='*70}\nSUMMARY (Cora, root+neighbor, hidden=24, n={len(results)} seeds)\n{'='*70}")
    for key, label in [
        ("qat_acc", "QAT (arbitrary scale)"),
        ("qat_to_po2_acc", "QAT -> PO2 (post-hoc projection)"),
        ("true_qat_po2_acc", "True QAT-PO2 (PO2 during training)"),
    ]:
        values = [r[key] for r in results]
        mean = statistics.fmean(values)
        std = statistics.pstdev(values) if len(values) > 1 else 0.0
        print(f"{label:38s}: {mean:.4f} +/- {std:.4f}  ({[f'{v:.4f}' for v in values]})")

    csv_lines = ["variant,n_seeds,mean,std,values"]
    for key, label in [
        ("qat_acc", "QAT"),
        ("qat_to_po2_acc", "QAT_to_PO2"),
        ("true_qat_po2_acc", "True_QAT_PO2"),
    ]:
        values = [r[key] for r in results]
        mean = statistics.fmean(values)
        std = statistics.pstdev(values) if len(values) > 1 else 0.0
        csv_lines.append(f"{label},{len(values)},{mean:.4f},{std:.4f}," + ";".join(f"{v:.4f}" for v in values))
    (OUTPUT_DIR / "cora_root24_summary.csv").write_text("\n".join(csv_lines) + "\n")
    print(f"\nWrote {OUTPUT_DIR / 'cora_root24_results.json'}")
    print(f"Wrote {OUTPUT_DIR / 'cora_root24_summary.csv'}")


if __name__ == "__main__":
    main()
