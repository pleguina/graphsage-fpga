#!/usr/bin/env python3
"""Train root-enabled PO2-QAT from existing float checkpoints."""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch_geometric.datasets import PPI, Planetoid
from torch_geometric.transforms import NormalizeFeatures

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from model_base import ReducedGraphSAGE
from model_po2_qat import ReducedGraphSAGEPO2QAT


def default_study_root(direct_name, bundled_name):
    direct = PROJECT_ROOT / "build" / direct_name
    return direct if direct.exists() else PROJECT_ROOT / "build" / "root_studies" / bundled_name


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def tensor_scale(values):
    maximum = float(values.detach().abs().max())
    return max(maximum / 127.0, 1e-12)


def weight_scales(model):
    return {
        "neighbor1": tensor_scale(model.conv1.lin_l.weight),
        "root1": tensor_scale(model.conv1.lin_r.weight),
        "neighbor2": tensor_scale(model.conv2.lin_l.weight),
        "root2": tensor_scale(model.conv2.lin_r.weight),
    }


def float_boundaries(model, graph):
    source, target = graph.edge_index
    degree = torch.bincount(target, minlength=graph.num_nodes).clamp(min=1).to(graph.x.dtype)
    with torch.no_grad():
        projected = F.relu(model.projection(graph.x))
        aggregate1 = torch.zeros_like(projected)
        aggregate1.index_add_(0, target, projected[source])
        aggregate1 /= degree.unsqueeze(1)
        hidden = F.relu(model.conv1(projected, graph.edge_index))
        aggregate2 = torch.zeros_like(hidden)
        aggregate2.index_add_(0, target, hidden[source])
        aggregate2 /= degree.unsqueeze(1)
        output = model.conv2(hidden, graph.edge_index)
    return {
        "input": projected,
        "aggregate1": aggregate1,
        "hidden": hidden,
        "aggregate2": aggregate2,
        "output": output,
    }


def activation_scales(model, graphs):
    maxima = {name: 0.0 for name in ("input", "aggregate1", "hidden", "aggregate2", "output")}
    model.eval()
    for graph in graphs:
        for name, values in float_boundaries(model, graph).items():
            maxima[name] = max(maxima[name], float(values.abs().max()))
    return {name: max(value / 127.0, 1e-12) for name, value in maxima.items()}


def load_float_model(checkpoint_path, in_channels, out_channels):
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if checkpoint.get("root_weight") is not True:
        raise ValueError(f"Checkpoint is not root-enabled: {checkpoint_path}")
    model = ReducedGraphSAGE(
        in_channels,
        16,
        24,
        out_channels,
        dropout=0.5,
        use_projection=True,
        root_weight=True,
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model


def split_accuracy(model, data):
    model.eval()
    with torch.no_grad():
        prediction = model(data.x, data.edge_index).argmax(dim=1)
    return {
        name: float((prediction[mask] == data.y[mask]).float().mean())
        for name, mask in (
            ("train", data.train_mask),
            ("validation", data.val_mask),
            ("test", data.test_mask),
        )
    }


def micro_f1(model, graphs):
    model.eval()
    true_positive = false_positive = false_negative = 0
    with torch.no_grad():
        for graph in graphs:
            prediction = model(graph.x, graph.edge_index) > 0
            target = graph.y > 0.5
            true_positive += int((prediction & target).sum())
            false_positive += int((prediction & ~target).sum())
            false_negative += int((~prediction & target).sum())
    denominator = 2 * true_positive + false_positive + false_negative
    return 0.0 if denominator == 0 else 2.0 * true_positive / denominator


def save_checkpoint(path, model, dataset, seed, scales, weights, best_epoch, metrics):
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "dataset": dataset,
            "seed": seed,
            "root_weight": True,
            "normalize": False,
            "project": False,
            "quantization": "PO2-QAT INT8",
            "activation_scales": scales,
            "weight_scales": weights,
            "po2_shifts": model.shifts(),
            "best_epoch": best_epoch,
            "metrics": metrics,
        },
        path,
    )


def run_planetoid(name, args):
    set_seed(args.seed)
    dataset = Planetoid(
        root=str(PROJECT_ROOT / "data"), name=name, transform=NormalizeFeatures()
    )
    data = dataset[0]
    float_path = args.planetoid_root / name.lower() / f"seed_{args.seed}" / "float_root.pth"
    float_model = load_float_model(float_path, dataset.num_features, dataset.num_classes)
    scales = activation_scales(float_model, [data])
    weights = weight_scales(float_model)
    model = ReducedGraphSAGEPO2QAT(dataset.num_features, dataset.num_classes, scales, weights)
    model.load_from_float_model(float_model)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate, weight_decay=5e-4)
    best_validation = -1.0
    best_state = None
    best_epoch = 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        optimizer.zero_grad()
        output = model(data.x, data.edge_index)
        loss = F.cross_entropy(output[data.train_mask], data.y[data.train_mask])
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        metrics = split_accuracy(model, data)
        if metrics["validation"] > best_validation:
            best_validation = metrics["validation"]
            best_epoch = epoch
            best_state = {
                name: value.detach().cpu().clone() for name, value in model.state_dict().items()
            }

    model.load_state_dict(best_state)
    metrics = split_accuracy(model, data)
    output_dir = args.output_dir / name.lower() / f"seed_{args.seed}"
    output_dir.mkdir(parents=True, exist_ok=True)
    save_checkpoint(
        output_dir / "po2_qat_root.pth",
        model,
        name,
        args.seed,
        scales,
        weights,
        best_epoch,
        metrics,
    )
    report = {
        "dataset": name,
        "metric": "accuracy",
        "seed": args.seed,
        "root_weight": True,
        "normalize": False,
        "project": False,
        "epochs": args.epochs,
        "best_epoch": best_epoch,
        "metrics": metrics,
        "activation_scales": scales,
        "weight_scales": weights,
        "po2_shifts": model.shifts(),
    }
    (output_dir / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(f"{name} seed={args.seed} PO2-QAT test={100 * metrics['test']:.2f}%")


def run_ppi(args):
    set_seed(args.seed)
    train_graphs = list(PPI(root=str(PROJECT_ROOT / "data" / "PPI"), split="train"))
    validation_graphs = list(PPI(root=str(PROJECT_ROOT / "data" / "PPI"), split="val"))
    test_graphs = list(PPI(root=str(PROJECT_ROOT / "data" / "PPI"), split="test"))
    float_path = args.ppi_root / f"seed_{args.seed}" / "float_root.pth"
    float_model = load_float_model(float_path, train_graphs[0].num_features, train_graphs[0].y.shape[1])
    scales = activation_scales(float_model, train_graphs)
    weights = weight_scales(float_model)
    model = ReducedGraphSAGEPO2QAT(
        train_graphs[0].num_features, train_graphs[0].y.shape[1], scales, weights
    )
    model.load_from_float_model(float_model)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate, weight_decay=5e-4)
    best_validation = -1.0
    best_state = None
    best_epoch = 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        for graph in train_graphs:
            optimizer.zero_grad()
            output = model(graph.x, graph.edge_index)
            loss = F.binary_cross_entropy_with_logits(output, graph.y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
        validation = micro_f1(model, validation_graphs)
        if validation > best_validation:
            best_validation = validation
            best_epoch = epoch
            best_state = {
                name: value.detach().cpu().clone() for name, value in model.state_dict().items()
            }

    model.load_state_dict(best_state)
    metrics = {
        "validation": micro_f1(model, validation_graphs),
        "test": micro_f1(model, test_graphs),
    }
    output_dir = args.output_dir / "ppi" / f"seed_{args.seed}"
    output_dir.mkdir(parents=True, exist_ok=True)
    save_checkpoint(
        output_dir / "po2_qat_root.pth",
        model,
        "PPI",
        args.seed,
        scales,
        weights,
        best_epoch,
        metrics,
    )
    report = {
        "dataset": "PPI",
        "metric": "micro_f1",
        "seed": args.seed,
        "root_weight": True,
        "normalize": False,
        "project": False,
        "epochs": args.epochs,
        "best_epoch": best_epoch,
        "metrics": metrics,
        "activation_scales": scales,
        "weight_scales": weights,
        "po2_shifts": model.shifts(),
    }
    (output_dir / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(f"PPI seed={args.seed} PO2-QAT test={metrics['test']:.4f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", default=["Cora", "CiteSeer", "PubMed", "PPI"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--learning-rate", type=float, default=0.0005)
    parser.add_argument(
        "--planetoid-root", type=Path, default=default_study_root("root_planetoid_study", "planetoid")
    )
    parser.add_argument(
        "--ppi-root", type=Path, default=default_study_root("root_ppi_study", "ppi")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "build" / "po2_qat_study"
    )
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    for name in args.datasets:
        if name == "PPI":
            run_ppi(args)
        else:
            run_planetoid(name, args)


if __name__ == "__main__":
    main()