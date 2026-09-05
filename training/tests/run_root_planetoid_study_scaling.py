#!/usr/bin/env python3
"""Train and compare default root-enabled GraphSAGE on Planetoid datasets."""

import argparse
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch_geometric.datasets import Planetoid
from torch_geometric.transforms import NormalizeFeatures

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from model_base import ReducedGraphSAGE
from model_qat_v2 import ReducedGraphSAGEQATv2, train_qat_v2


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def split_accuracy(output, data):
    prediction = output.argmax(dim=1)
    return {
        split: float((prediction[mask] == data.y[mask]).float().mean())
        for split, mask in (
            ("train", data.train_mask),
            ("validation", data.val_mask),
            ("test", data.test_mask),
        )
    }


def evaluate(model, data):
    model.eval()
    with torch.no_grad():
        return split_accuracy(model(data.x, data.edge_index), data)


def train_float(dataset, data, epochs, learning_rate, output_path, hidden_channels=24):
    model = ReducedGraphSAGE(
        dataset.num_features,
        in_channels_reduced=16,
        hidden_channels=hidden_channels,
        out_channels=dataset.num_classes,
        dropout=0.5,
        use_projection=True,
        root_weight=True,
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=5e-4)
    best_validation = -1.0
    best_state = None
    best_epoch = 0

    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()
        output = model(data.x, data.edge_index)
        loss = F.cross_entropy(output[data.train_mask], data.y[data.train_mask])
        loss.backward()
        optimizer.step()

        model.eval()
        with torch.no_grad():
            metrics = split_accuracy(model(data.x, data.edge_index), data)
        if metrics["validation"] > best_validation:
            best_validation = metrics["validation"]
            best_epoch = epoch
            best_state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}

    model.load_state_dict(best_state)
    metrics = evaluate(model, data)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "root_weight": True,
            "dataset": dataset.name,
            "best_epoch": best_epoch,
            "metrics": metrics,
        },
        output_path,
    )
    return model, metrics, best_epoch


def train_qat(dataset, data, float_model, epochs, learning_rate, calibration_passes, output_path, hidden_channels=24):
    model = ReducedGraphSAGEQATv2(
        dataset.num_features,
        in_channels_reduced=16,
        hidden_channels=hidden_channels,
        out_channels=dataset.num_classes,
        dropout=0.5,
        use_projection=True,
        root_weight=True,
        num_bits=8,
    )
    model.load_from_float_model(float_model)
    model.calibrate(data, num_batches=calibration_passes)
    model = train_qat_v2(model, data, epochs=epochs, lr=learning_rate, verbose=False)
    model.eval()
    model.enable_fake_quant()
    metrics = evaluate(model, data)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "root_weight": True,
            "dataset": dataset.name,
            "metrics": metrics,
        },
        output_path,
    )
    return model, metrics


def symmetric_quantize(tensor):
    max_abs = float(tensor.detach().abs().max())
    scale = max_abs / 127.0 if max_abs else 1.0
    quantized = torch.clamp(torch.round(tensor.detach() / scale), -128, 127).to(torch.int8)
    return quantized, scale


def fixed_requantize(values, factor, fractional_bits=24):
    factor_fixed = int(round(factor * (1 << fractional_bits)))
    rounded = values.to(torch.int64) * factor_fixed + (1 << (fractional_bits - 1))
    return torch.clamp(rounded >> fractional_bits, -128, 127).to(torch.int8)


def po2_shift(factor):
    if factor <= 0:
        raise ValueError(f"Scale factor must be positive, got {factor}")
    return -int(round(math.log2(factor)))


def po2_requantize(values, factor):
    shift = po2_shift(factor)
    values = values.to(torch.int64)
    if shift > 0:
        values = (values + (1 << (shift - 1))) >> shift
    elif shift < 0:
        values = values << (-shift)
    return torch.clamp(values, -128, 127).to(torch.int8)


def aggregate_integer(features, edge_index, degree, input_scale, output_scale, po2, adjacency_scale=4096):
    source, target = edge_index
    coefficients = torch.round(adjacency_scale / degree[target]).to(torch.int32)
    messages = features[source].to(torch.int32) * coefficients.unsqueeze(1)
    accumulated = torch.zeros(features.shape, dtype=torch.int32)
    accumulated.index_add_(0, target, messages)
    factor = input_scale / (adjacency_scale * output_scale)
    return po2_requantize(accumulated, factor) if po2 else fixed_requantize(accumulated, factor)


def root_linear_integer(
    aggregate,
    root_input,
    neighbor_weight,
    root_weight,
    bias,
    aggregate_scale,
    root_input_scale,
    neighbor_weight_scale,
    root_weight_scale,
    output_scale,
    po2,
):
    neighbor_bias = torch.round(bias / (aggregate_scale * neighbor_weight_scale)).to(torch.int32)
    neighbor_acc = aggregate.to(torch.int32) @ neighbor_weight.to(torch.int32).t() + neighbor_bias
    root_acc = root_input.to(torch.int32) @ root_weight.to(torch.int32).t()
    neighbor_factor = aggregate_scale * neighbor_weight_scale / output_scale
    root_factor = root_input_scale * root_weight_scale / output_scale
    requantize = po2_requantize if po2 else fixed_requantize
    neighbor_output = requantize(neighbor_acc, neighbor_factor).to(torch.int16)
    root_output = requantize(root_acc, root_factor).to(torch.int16)
    return torch.clamp(neighbor_output + root_output, -128, 127).to(torch.int8), {
        "neighbor_shift": po2_shift(neighbor_factor),
        "root_shift": po2_shift(root_factor),
    }


def calibrate_float_boundaries(model, data):
    model.eval()
    source, target = data.edge_index
    degree = torch.bincount(target, minlength=data.num_nodes).clamp(min=1).to(data.x.dtype)
    with torch.no_grad():
        projected = F.relu(model.projection(data.x))
        aggregate1 = torch.zeros_like(projected)
        aggregate1.index_add_(0, target, projected[source])
        aggregate1 /= degree.unsqueeze(1)
        hidden = F.relu(model.conv1(projected, data.edge_index))
        aggregate2 = torch.zeros_like(hidden)
        aggregate2.index_add_(0, target, hidden[source])
        aggregate2 /= degree.unsqueeze(1)
        output = model.conv2(hidden, data.edge_index)
    return projected, aggregate1, hidden, aggregate2, output, degree.to(torch.int64)


def run_root_integer(model, data, po2, return_tensors=False):
    projected, aggregate1_float, hidden_float, aggregate2_float, output_float, degree = calibrate_float_boundaries(model, data)
    input_int8, input_scale = symmetric_quantize(projected)
    aggregate1_scale = max(float(aggregate1_float.abs().max()) / 127.0, 1e-12)
    hidden_scale = max(float(hidden_float.abs().max()) / 127.0, 1e-12)
    aggregate2_scale = max(float(aggregate2_float.abs().max()) / 127.0, 1e-12)
    output_scale = max(float(output_float.abs().max()) / 127.0, 1e-12)

    neighbor1, neighbor1_scale = symmetric_quantize(model.conv1.lin_l.weight)
    root1, root1_scale = symmetric_quantize(model.conv1.lin_r.weight)
    neighbor2, neighbor2_scale = symmetric_quantize(model.conv2.lin_l.weight)
    root2, root2_scale = symmetric_quantize(model.conv2.lin_r.weight)

    aggregate1 = aggregate_integer(
        input_int8, data.edge_index, degree, input_scale, aggregate1_scale, po2
    )
    hidden_pre_relu, layer1_shifts = root_linear_integer(
        aggregate1,
        input_int8,
        neighbor1,
        root1,
        model.conv1.lin_l.bias,
        aggregate1_scale,
        input_scale,
        neighbor1_scale,
        root1_scale,
        hidden_scale,
        po2,
    )
    hidden = torch.clamp(hidden_pre_relu, min=0)
    aggregate2 = aggregate_integer(
        hidden, data.edge_index, degree, hidden_scale, aggregate2_scale, po2
    )
    output, layer2_shifts = root_linear_integer(
        aggregate2,
        hidden,
        neighbor2,
        root2,
        model.conv2.lin_l.bias,
        aggregate2_scale,
        hidden_scale,
        neighbor2_scale,
        root2_scale,
        output_scale,
        po2,
    )
    metrics = split_accuracy(output, data)
    tensors = {
        "input": input_int8,
        "aggregate1": aggregate1,
        "hidden": hidden,
        "aggregate2": aggregate2,
        "output": output,
    }
    saturation = {
        name: 100.0 * float(((values == -128) | (values == 127)).sum()) / values.numel()
        for name, values in tensors.items()
    }
    details = {
        "scales": {
            "input": input_scale,
            "aggregate1": aggregate1_scale,
            "hidden": hidden_scale,
            "aggregate2": aggregate2_scale,
            "output": output_scale,
        },
        "po2_shifts": {"layer1": layer1_shifts, "layer2": layer2_shifts} if po2 else None,
        "saturation_percent": saturation,
    }
    if return_tensors:
        details["tensors"] = tensors
    return metrics, details


def run_dataset(name, args):
    set_seed(args.seed)
    dataset = Planetoid(
        root=str(PROJECT_ROOT / "data"), name=name, transform=NormalizeFeatures()
    )
    data = dataset[0]
    output_dir = args.output_dir / name.lower() / f"seed_{args.seed}"
    output_dir.mkdir(parents=True, exist_ok=True)
    float_path = output_dir / "float_root.pth"
    qat_path = output_dir / "qat_root.pth"

    print(f"\n{'=' * 72}\n{name}: root_weight=True, seed={args.seed}\n{'=' * 72}")
    float_model, float_metrics, best_epoch = train_float(
        dataset, data, args.float_epochs, args.float_lr, float_path, hidden_channels=args.hidden
    )
    qat_model, qat_metrics = train_qat(
        dataset,
        data,
        float_model,
        args.qat_epochs,
        args.qat_lr,
        args.calibration_passes,
        qat_path,
        hidden_channels=args.hidden,
    )
    ptq_metrics, ptq_details = run_root_integer(float_model, data, po2=False)
    po2_metrics, po2_details = run_root_integer(float_model, data, po2=True)

    report = {
        "dataset": name,
        "seed": args.seed,
        "root_weight": True,
        "dimensions": {
            "nodes": data.num_nodes,
            "edges": data.num_edges,
            "features": dataset.num_features,
            "classes": dataset.num_classes,
            "train_nodes": int(data.train_mask.sum()),
            "validation_nodes": int(data.val_mask.sum()),
            "test_nodes": int(data.test_mask.sum()),
        },
        "training": {
            "float_best_epoch": best_epoch,
            "float_epochs": args.float_epochs,
            "qat_epochs": args.qat_epochs,
        },
        "metrics": {
            "float_root": float_metrics,
            "ptq_int8_root": ptq_metrics,
            "po2_root": po2_metrics,
            "qat_root": qat_metrics,
        },
        "details": {"ptq_int8_root": ptq_details, "po2_root": po2_details},
    }
    (output_dir / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(
        f"{name}: float={100 * float_metrics['test']:.2f}%  "
        f"PTQ={100 * ptq_metrics['test']:.2f}%  "
        f"PO2={100 * po2_metrics['test']:.2f}%  "
        f"QAT={100 * qat_metrics['test']:.2f}%"
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", default=["Cora", "CiteSeer", "PubMed"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hidden", type=int, default=24, help="Hidden width (plan Section 12 scaling study)")
    parser.add_argument("--float-epochs", type=int, default=200)
    parser.add_argument("--qat-epochs", type=int, default=200)
    parser.add_argument("--float-lr", type=float, default=0.01)
    parser.add_argument("--qat-lr", type=float, default=0.0005)
    parser.add_argument("--calibration-passes", type=int, default=50)
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "build" / "root_planetoid_study"
    )
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()

    for name in args.datasets:
        run_dataset(name, args)
    result_paths = sorted(args.output_dir.glob(f"*/seed_{args.seed}/results.json"))
    reports = [json.loads(path.read_text(encoding="ascii")) for path in result_paths]
    summary_path = args.output_dir / f"summary_seed_{args.seed}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(reports, indent=2) + "\n", encoding="ascii")
    print(f"\nSummary: {summary_path}")


if __name__ == "__main__":
    main()