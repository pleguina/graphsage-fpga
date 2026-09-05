#!/usr/bin/env python3
"""Check PO2-QAT forward against an independent integer reference."""

import sys
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from model_po2_qat import PO2SAGEConvQAT, shift_round_ste


def rounded_shift(values, shift):
    values = values.to(torch.int64)
    if shift > 0:
        return (values + (1 << (shift - 1))) >> shift
    if shift < 0:
        return values << (-shift)
    return values


def main():
    tie_values = torch.tensor([-6.0, -2.0, 2.0, 6.0], requires_grad=True)
    tie_actual = shift_round_ste(tie_values, 2)
    tie_expected = torch.tensor([-1.0, 0.0, 1.0, 2.0])
    assert torch.equal(tie_actual, tie_expected)
    tie_actual.sum().backward()
    assert torch.equal(tie_values.grad, torch.full_like(tie_values, 0.25))

    torch.manual_seed(7)
    layer = PO2SAGEConvQAT(4, 3, 0.125, 0.125, 0.25, 0.0625, 0.03125)
    with torch.no_grad():
        layer.lin_neighbor.weight.copy_(torch.randn(3, 4) * 0.2)
        layer.lin_neighbor.bias.copy_(torch.randn(3) * 0.1)
        layer.lin_root.weight.copy_(torch.randn(3, 4) * 0.2)
    features = torch.randn(5, 4)
    edge_index = torch.tensor(
        [[0, 1, 2, 3, 4, 0, 2], [1, 2, 3, 4, 0, 2, 2]], dtype=torch.long
    )
    layer.eval()
    actual = torch.round(layer(features, edge_index) / layer.output_scale).to(torch.int8)

    input_int = torch.clamp(torch.round(features / layer.input_scale), -128, 127).to(torch.int8)
    source, target = edge_index
    degree = torch.bincount(target, minlength=features.shape[0]).clamp(min=1)
    coefficients = torch.round(4096 / degree[target]).to(torch.int32)
    aggregate_acc = torch.zeros_like(input_int, dtype=torch.int32)
    aggregate_acc.index_add_(
        0, target, input_int[source].to(torch.int32) * coefficients.unsqueeze(1)
    )
    aggregate_int = torch.clamp(
        rounded_shift(aggregate_acc, layer.aggregate_shift), -128, 127
    ).to(torch.int8)
    neighbor_weight = torch.clamp(
        torch.round(layer.lin_neighbor.weight / layer.neighbor_weight_scale), -128, 127
    ).to(torch.int8)
    root_weight = torch.clamp(
        torch.round(layer.lin_root.weight / layer.root_weight_scale), -128, 127
    ).to(torch.int8)
    bias = torch.round(
        layer.lin_neighbor.bias / (layer.aggregate_scale * layer.neighbor_weight_scale)
    ).to(torch.int32)
    neighbor_acc = aggregate_int.to(torch.int32) @ neighbor_weight.to(torch.int32).t() + bias
    root_acc = input_int.to(torch.int32) @ root_weight.to(torch.int32).t()
    neighbor = torch.clamp(
        rounded_shift(neighbor_acc, layer.neighbor_shift), -128, 127
    ).to(torch.int16)
    root = torch.clamp(rounded_shift(root_acc, layer.root_shift), -128, 127).to(torch.int16)
    expected = torch.clamp(neighbor + root, -128, 127).to(torch.int8)

    assert torch.equal(actual, expected), (actual, expected)
    loss = layer(features.requires_grad_(), edge_index).square().mean()
    loss.backward()
    assert features.grad is not None and torch.isfinite(features.grad).all()
    assert layer.lin_neighbor.weight.grad is not None
    assert layer.lin_root.weight.grad is not None
    print("PO2_QAT_ARITHMETIC_PASS values=15 gradients=finite")


if __name__ == "__main__":
    main()