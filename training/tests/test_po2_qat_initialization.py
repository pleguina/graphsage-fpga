#!/usr/bin/env python3
"""Verify untrained PO2-QAT reproduces the existing PO2 integer emulator."""

import sys
from pathlib import Path

import torch
from torch_geometric.datasets import PPI, Planetoid
from torch_geometric.transforms import NormalizeFeatures

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from model_po2_qat import ReducedGraphSAGEPO2QAT
from run_po2_qat_study import activation_scales, load_float_model, weight_scales
from run_root_planetoid_study import run_root_integer
from run_root_ppi_study import quantized_weights, run_integer_graph


def study_root(direct_name, bundled_name):
    direct = PROJECT_ROOT / "build" / direct_name
    return direct if direct.exists() else PROJECT_ROOT / "build" / "root_studies" / bundled_name


def check_planetoid(name):
    dataset = Planetoid(
        root=str(PROJECT_ROOT / "data"), name=name, transform=NormalizeFeatures()
    )
    data = dataset[0]
    model = load_float_model(
        study_root("root_planetoid_study", "planetoid") / name.lower() / "seed_42" / "float_root.pth",
        dataset.num_features,
        dataset.num_classes,
    )
    scales = activation_scales(model, [data])
    po2_qat = ReducedGraphSAGEPO2QAT(dataset.num_features, dataset.num_classes, scales, weight_scales(model))
    po2_qat.load_from_float_model(model)
    po2_qat.eval()
    with torch.no_grad():
        actual = torch.round(po2_qat(data.x, data.edge_index) / scales["output"]).to(torch.int8)
    _, details = run_root_integer(model, data, po2=True, return_tensors=True)
    expected = details["tensors"]["output"]
    assert torch.equal(actual, expected)
    return actual.numel()


def check_ppi():
    train_graphs = list(PPI(root=str(PROJECT_ROOT / "data" / "PPI"), split="train"))
    test_graph = PPI(root=str(PROJECT_ROOT / "data" / "PPI"), split="test")[0]
    model = load_float_model(
        study_root("root_ppi_study", "ppi") / "seed_42" / "float_root.pth",
        train_graphs[0].num_features,
        train_graphs[0].y.shape[1],
    )
    scales = activation_scales(model, train_graphs)
    po2_qat = ReducedGraphSAGEPO2QAT(
        train_graphs[0].num_features, train_graphs[0].y.shape[1], scales, weight_scales(model)
    )
    po2_qat.load_from_float_model(model)
    po2_qat.eval()
    with torch.no_grad():
        actual = torch.round(po2_qat(test_graph.x, test_graph.edge_index) / scales["output"]).to(torch.int8)
    expected, _, _ = run_integer_graph(
        model, test_graph, scales, quantized_weights(model), po2=True
    )
    assert torch.equal(actual, expected)
    return actual.numel()


def main():
    planetoid_values = {
        name.lower(): check_planetoid(name)
        for name in ("Cora", "CiteSeer", "PubMed")
    }
    ppi_values = check_ppi()
    print(
        "PO2_QAT_INITIALIZATION_PASS "
        + " ".join(f"{name}_values={values}" for name, values in planetoid_values.items())
        + " "
        f"ppi_values={ppi_values}"
    )


if __name__ == "__main__":
    main()