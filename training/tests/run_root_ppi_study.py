#!/usr/bin/env python3
"""Train and compare root-enabled GraphSAGE on the inductive PPI dataset."""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch_geometric.datasets import PPI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from model_base import ReducedGraphSAGE
from model_qat_v2 import ReducedGraphSAGEQATv2
from run_root_planetoid_study import (
    aggregate_integer,
    calibrate_float_boundaries,
    root_linear_integer,
    symmetric_quantize,
)


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def micro_f1_from_counts(true_positive, false_positive, false_negative):
    denominator = 2 * true_positive + false_positive + false_negative
    return 0.0 if denominator == 0 else 2.0 * true_positive / denominator


def update_f1_counts(logits, labels, counts):
    prediction = logits > 0
    target = labels > 0.5
    counts[0] += int((prediction & target).sum())
    counts[1] += int((prediction & ~target).sum())
    counts[2] += int((~prediction & target).sum())


def evaluate_float(model, graphs):
    model.eval()
    counts = [0, 0, 0]
    with torch.no_grad():
        for graph in graphs:
            update_f1_counts(model(graph.x, graph.edge_index), graph.y, counts)
    return micro_f1_from_counts(*counts)


def train_float(train_graphs, validation_graphs, features, labels, args, output_path):
    model = ReducedGraphSAGE(
        features, 16, 24, labels, dropout=0.5, use_projection=True, root_weight=True
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=args.float_lr, weight_decay=5e-4)
    best_validation = -1.0
    best_state = None
    best_epoch = 0

    for epoch in range(1, args.float_epochs + 1):
        model.train()
        for graph in train_graphs:
            optimizer.zero_grad()
            output = model(graph.x, graph.edge_index)
            loss = F.binary_cross_entropy_with_logits(output, graph.y)
            loss.backward()
            optimizer.step()
        validation = evaluate_float(model, validation_graphs)
        if validation > best_validation:
            best_validation = validation
            best_epoch = epoch
            best_state = {
                name: value.detach().cpu().clone() for name, value in model.state_dict().items()
            }

    model.load_state_dict(best_state)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "root_weight": True,
            "dataset": "PPI",
            "best_epoch": best_epoch,
            "validation_micro_f1": best_validation,
        },
        output_path,
    )
    return model, best_epoch


def calibrate_qat(model, train_graphs, passes):
    model.eval()
    model.enable_observer()
    model.disable_fake_quant()
    with torch.no_grad():
        for index in range(passes):
            graph = train_graphs[index % len(train_graphs)]
            model(graph.x, graph.edge_index)
    model.disable_observer()
    model.enable_fake_quant()


def train_qat(train_graphs, validation_graphs, float_model, features, labels, args, output_path):
    model = ReducedGraphSAGEQATv2(
        features,
        16,
        24,
        labels,
        dropout=0.5,
        use_projection=True,
        root_weight=True,
        num_bits=8,
    )
    model.load_from_float_model(float_model)
    calibrate_qat(model, train_graphs, args.calibration_passes)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.qat_lr, weight_decay=5e-4)
    best_validation = -1.0
    best_state = None
    best_epoch = 0

    for epoch in range(1, args.qat_epochs + 1):
        model.train()
        model.enable_fake_quant()
        model.disable_observer()
        for graph in train_graphs:
            optimizer.zero_grad()
            output = model(graph.x, graph.edge_index)
            loss = F.binary_cross_entropy_with_logits(output, graph.y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
        validation = evaluate_float(model, validation_graphs)
        if validation > best_validation:
            best_validation = validation
            best_epoch = epoch
            best_state = {
                name: value.detach().cpu().clone() for name, value in model.state_dict().items()
            }

    model.load_state_dict(best_state)
    model.eval()
    model.enable_fake_quant()
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "root_weight": True,
            "dataset": "PPI",
            "best_epoch": best_epoch,
            "validation_micro_f1": best_validation,
        },
        output_path,
    )
    return model, best_epoch


def collect_global_scales(model, calibration_graphs):
    maxima = {name: 0.0 for name in ("input", "aggregate1", "hidden", "aggregate2", "output")}
    for graph in calibration_graphs:
        tensors = calibrate_float_boundaries(model, graph)[:5]
        for name, tensor in zip(maxima, tensors):
            maxima[name] = max(maxima[name], float(tensor.abs().max()))
    return {name: max(value / 127.0, 1e-12) for name, value in maxima.items()}


def run_integer_graph(model, graph, scales, weights, po2):
    with torch.no_grad():
        projected = F.relu(model.projection(graph.x))
    input_int8 = torch.clamp(torch.round(projected / scales["input"]), -128, 127).to(torch.int8)
    degree = torch.bincount(graph.edge_index[1], minlength=graph.num_nodes).clamp(min=1)
    aggregate1 = aggregate_integer(
        input_int8,
        graph.edge_index,
        degree,
        scales["input"],
        scales["aggregate1"],
        po2,
    )
    hidden_pre_relu, _ = root_linear_integer(
        aggregate1,
        input_int8,
        weights["neighbor1"],
        weights["root1"],
        model.conv1.lin_l.bias,
        scales["aggregate1"],
        scales["input"],
        weights["neighbor1_scale"],
        weights["root1_scale"],
        scales["hidden"],
        po2,
    )
    hidden = torch.clamp(hidden_pre_relu, min=0)
    aggregate2 = aggregate_integer(
        hidden,
        graph.edge_index,
        degree,
        scales["hidden"],
        scales["aggregate2"],
        po2,
    )
    output, shifts = root_linear_integer(
        aggregate2,
        hidden,
        weights["neighbor2"],
        weights["root2"],
        model.conv2.lin_l.bias,
        scales["aggregate2"],
        scales["hidden"],
        weights["neighbor2_scale"],
        weights["root2_scale"],
        scales["output"],
        po2,
    )
    saturation = 100.0 * float(((output == -128) | (output == 127)).sum()) / output.numel()
    return output, shifts, saturation


def quantized_weights(model):
    neighbor1, neighbor1_scale = symmetric_quantize(model.conv1.lin_l.weight)
    root1, root1_scale = symmetric_quantize(model.conv1.lin_r.weight)
    neighbor2, neighbor2_scale = symmetric_quantize(model.conv2.lin_l.weight)
    root2, root2_scale = symmetric_quantize(model.conv2.lin_r.weight)
    return {
        "neighbor1": neighbor1,
        "neighbor1_scale": neighbor1_scale,
        "root1": root1,
        "root1_scale": root1_scale,
        "neighbor2": neighbor2,
        "neighbor2_scale": neighbor2_scale,
        "root2": root2,
        "root2_scale": root2_scale,
    }


def evaluate_integer(model, graphs, scales, weights, po2):
    counts = [0, 0, 0]
    peak_saturation = 0.0
    shifts = None
    for graph in graphs:
        output, shifts, saturation = run_integer_graph(model, graph, scales, weights, po2)
        update_f1_counts(output, graph.y, counts)
        peak_saturation = max(peak_saturation, saturation)
    return micro_f1_from_counts(*counts), peak_saturation, shifts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--float-epochs", type=int, default=200)
    parser.add_argument("--qat-epochs", type=int, default=200)
    parser.add_argument("--float-lr", type=float, default=0.005)
    parser.add_argument("--qat-lr", type=float, default=0.0005)
    parser.add_argument("--calibration-passes", type=int, default=50)
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "build" / "root_ppi_study"
    )
    args = parser.parse_args()
    set_seed(args.seed)
    output_dir = args.output_dir.resolve() / f"seed_{args.seed}"
    output_dir.mkdir(parents=True, exist_ok=True)

    train_dataset = PPI(root=str(PROJECT_ROOT / "data" / "PPI"), split="train")
    validation_dataset = PPI(root=str(PROJECT_ROOT / "data" / "PPI"), split="val")
    test_dataset = PPI(root=str(PROJECT_ROOT / "data" / "PPI"), split="test")
    train_graphs = list(train_dataset)
    validation_graphs = list(validation_dataset)
    test_graphs = list(test_dataset)

    float_model, float_best_epoch = train_float(
        train_graphs,
        validation_graphs,
        train_dataset.num_features,
        train_dataset.num_classes,
        args,
        output_dir / "float_root.pth",
    )
    qat_model, qat_best_epoch = train_qat(
        train_graphs,
        validation_graphs,
        float_model,
        train_dataset.num_features,
        train_dataset.num_classes,
        args,
        output_dir / "qat_root.pth",
    )

    float_f1 = evaluate_float(float_model, test_graphs)
    qat_f1 = evaluate_float(qat_model, test_graphs)
    scales = collect_global_scales(float_model, train_graphs)
    weights = quantized_weights(float_model)
    ptq_f1, ptq_saturation, _ = evaluate_integer(
        float_model, test_graphs, scales, weights, po2=False
    )
    po2_f1, po2_saturation, po2_shifts = evaluate_integer(
        float_model, test_graphs, scales, weights, po2=True
    )

    report = {
        "dataset": "PPI",
        "task": "inductive_multilabel_classification",
        "metric": "micro_f1",
        "seed": args.seed,
        "root_weight": True,
        "dimensions": {
            "features": train_dataset.num_features,
            "labels": train_dataset.num_classes,
            "train_graphs": len(train_graphs),
            "validation_graphs": len(validation_graphs),
            "test_graphs": len(test_graphs),
        },
        "training": {
            "float_epochs": args.float_epochs,
            "float_best_epoch": float_best_epoch,
            "qat_epochs": args.qat_epochs,
            "qat_best_epoch": qat_best_epoch,
        },
        "metrics": {
            "float_root": float_f1,
            "ptq_int8_root": ptq_f1,
            "po2_root": po2_f1,
            "qat_root": qat_f1,
        },
        "integer_details": {
            "calibration": "global maxima over training graphs only",
            "scales": scales,
            "po2_shifts_layer2": po2_shifts,
            "ptq_peak_output_saturation_percent": ptq_saturation,
            "po2_peak_output_saturation_percent": po2_saturation,
        },
    }
    (output_dir / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(
        f"PPI micro-F1: float={float_f1:.4f} PTQ={ptq_f1:.4f} "
        f"PO2={po2_f1:.4f} QAT={qat_f1:.4f}"
    )
    print(f"Report: {output_dir / 'results.json'}")


if __name__ == "__main__":
    main()