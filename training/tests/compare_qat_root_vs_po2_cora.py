#!/usr/bin/env python3
"""Compare deployed PTQ/PO2 arithmetic and QAT checkpoints on Cora."""

import json
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
from model_qat_v2 import ReducedGraphSAGEQATv2

WEIGHTS_DIR = PROJECT_ROOT / "build" / "weights_ptq_float"
INT8_DIR = PROJECT_ROOT / "build" / "weights_ptq_int8"
PO2_DIR = PROJECT_ROOT / "build" / "test_vectors_ptq_int8_po2"
PTQ_VECTORS_DIR = PROJECT_ROOT / "build" / "test_vectors_ptq_float"
MODELS_DIR = PROJECT_ROOT / "build" / "models"


def clamp_int8(values):
    return torch.clamp(values, -128, 127).to(torch.int8)


def requantize_fixed(values, scale_fp, fractional_bits):
    rounded = values.to(torch.int64) * scale_fp + (1 << (fractional_bits - 1))
    return clamp_int8(rounded >> fractional_bits)


def requantize_po2(values, shift):
    if shift > 0:
        values = values.to(torch.int64) + (1 << (shift - 1))
        return clamp_int8(values >> shift)
    return clamp_int8(values.to(torch.int64) << (-shift))


def aggregate_sparse(features, edge_index, degree, coefficient_scale, requantize):
    source, target = edge_index
    coefficients = torch.round(coefficient_scale / degree[target]).to(torch.int32)
    messages = features[source].to(torch.int32) * coefficients.unsqueeze(1)
    accumulated = torch.zeros(
        features.shape, dtype=torch.int32, device=features.device
    )
    accumulated.index_add_(0, target, messages)
    return requantize(accumulated)


def linear_integer(features, weights, bias, requantize):
    accumulated = features.to(torch.int32) @ weights.to(torch.int32).t()
    accumulated += bias.to(torch.int32)
    return requantize(accumulated)


def run_integer_network(input_int8, edge_index, degree, parameters, po2):
    if po2:
        shifts = parameters["shifts"]
        aggregate1_scale = lambda values: requantize_po2(values, shifts["BETA1_SHIFT"])
        linear1_scale = lambda values: requantize_po2(values, shifts["EFF_SCALE1_SHIFT"])
        aggregate2_scale = lambda values: requantize_po2(values, shifts["BETA2_SHIFT"])
        linear2_scale = lambda values: requantize_po2(values, shifts["EFF_SCALE2_SHIFT"])
    else:
        fractional_bits = parameters["M"]
        scales = parameters["fixed_scales"]
        aggregate1_scale = lambda values: requantize_fixed(values, scales["beta1_fp"], fractional_bits)
        linear1_scale = lambda values: requantize_fixed(values, scales["eff_scale1_fp"], fractional_bits)
        aggregate2_scale = lambda values: requantize_fixed(values, scales["beta2_fp"], fractional_bits)
        linear2_scale = lambda values: requantize_fixed(values, scales["eff_scale2_fp"], fractional_bits)

    aggregate1 = aggregate_sparse(
        input_int8, edge_index, degree, parameters["K"], aggregate1_scale
    )
    hidden_pre_relu = linear_integer(
        aggregate1, parameters["weights1"], parameters["bias1"], linear1_scale
    )
    hidden = torch.clamp(hidden_pre_relu, min=0)
    aggregate2 = aggregate_sparse(
        hidden, edge_index, degree, parameters["K"], aggregate2_scale
    )
    output = linear_integer(
        aggregate2, parameters["weights2"], parameters["bias2"], linear2_scale
    )
    intermediates = {
        "input": input_int8,
        "aggregate1": aggregate1,
        "hidden_pre_relu": hidden_pre_relu,
        "hidden": hidden,
        "aggregate2": aggregate2,
        "output": output,
    }
    return output, intermediates


def run_packaged_po2_vector(parameters):
    input_int8 = torch.from_numpy(
        np.loadtxt(PTQ_VECTORS_DIR / "network_input.txt", dtype=np.int8)
    )
    adjacency = torch.from_numpy(
        np.loadtxt(INT8_DIR / "adj_matrix_int16.txt", dtype=np.int16)
    ).to(torch.int32)
    reference = torch.from_numpy(
        np.loadtxt(PO2_DIR / "network_output_int8_po2_reference.txt", dtype=np.int8)
    )

    def dense_aggregate(features, shift):
        accumulated = adjacency @ features.to(torch.int32)
        return requantize_po2(accumulated, shift)

    shifts = parameters["shifts"]
    aggregate1 = dense_aggregate(input_int8, shifts["BETA1_SHIFT"])
    hidden = linear_integer(
        aggregate1,
        parameters["weights1"],
        parameters["bias1"],
        lambda values: requantize_po2(values, shifts["EFF_SCALE1_SHIFT"]),
    )
    hidden = torch.clamp(hidden, min=0)
    aggregate2 = dense_aggregate(hidden, shifts["BETA2_SHIFT"])
    output = linear_integer(
        aggregate2,
        parameters["weights2"],
        parameters["bias2"],
        lambda values: requantize_po2(values, shifts["EFF_SCALE2_SHIFT"]),
    )
    max_error = int((output.to(torch.int16) - reference.to(torch.int16)).abs().max())
    if max_error != 0:
        raise RuntimeError(f"Packaged PO2 reference mismatch: {max_error} LSB")
    return max_error


def load_integer_parameters():
    int8_config = json.loads((INT8_DIR / "int8_params.json").read_text())
    po2_config = json.loads((PO2_DIR / "po2_config.json").read_text())
    return {
        "M": int8_config["fixed_point_config"]["M"],
        "K": int8_config["fixed_point_config"]["K"],
        "fixed_scales": int8_config["fixed_point_scales"],
        "shifts": po2_config["shifts"],
        "input_scale": int8_config["original_float_scales"]["scale_in"],
        "weights1": torch.from_numpy(
            np.loadtxt(WEIGHTS_DIR / "conv1_lin_l_weight.txt", dtype=np.int8).reshape(24, 16)
        ),
        "weights2": torch.from_numpy(
            np.loadtxt(WEIGHTS_DIR / "conv2_lin_l_weight.txt", dtype=np.int8).reshape(7, 24)
        ),
        "bias1": torch.from_numpy(
            np.loadtxt(INT8_DIR / "bias_layer1_int32.txt", dtype=np.int32)
        ),
        "bias2": torch.from_numpy(
            np.loadtxt(INT8_DIR / "bias_layer2_int32.txt", dtype=np.int32)
        ),
    }


def load_float_model(dataset, root_weight):
    model = ReducedGraphSAGE(
        dataset.num_features, 16, 24, dataset.num_classes,
        dropout=0.5, use_projection=True, root_weight=root_weight,
    )
    name = "reduced_graphsage_best.pth" if root_weight else "reduced_graphsage_no_root_best.pth"
    checkpoint = torch.load(MODELS_DIR / name, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model


def load_qat_model(dataset, root_weight):
    model = ReducedGraphSAGEQATv2(
        dataset.num_features, 16, 24, dataset.num_classes,
        dropout=0.5, use_projection=True, root_weight=root_weight, num_bits=8,
    )
    name = "qat_v2_root_best.pth" if root_weight else "qat_v2_best.pth"
    checkpoint = torch.load(MODELS_DIR / name, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    model.enable_fake_quant()
    return model


def accuracy(predictions, labels, mask):
    return float((predictions[mask] == labels[mask]).float().mean())


def saturation(intermediates):
    result = {}
    for name, values in intermediates.items():
        saturated = ((values == -128) | (values == 127)).sum().item()
        result[name] = 100.0 * saturated / values.numel()
    return result


def main():
    torch.manual_seed(42)
    np.random.seed(42)
    dataset = Planetoid(
        root=str(PROJECT_ROOT / "data"), name="Cora", transform=NormalizeFeatures()
    )
    data = dataset[0]
    parameters = load_integer_parameters()
    packaged_max_error = run_packaged_po2_vector(parameters)

    float_no_root = load_float_model(dataset, root_weight=False)
    float_root = load_float_model(dataset, root_weight=True)
    qat_no_root = load_qat_model(dataset, root_weight=False)
    qat_root = load_qat_model(dataset, root_weight=True)

    with torch.no_grad():
        float_no_root_output = float_no_root(data.x, data.edge_index)
        float_root_output = float_root(data.x, data.edge_index)
        qat_no_root_output = qat_no_root(data.x, data.edge_index)
        qat_root_output = qat_root(data.x, data.edge_index)
        projected = F.relu(float_no_root.projection(data.x))

    input_int8 = clamp_int8(torch.round(projected / parameters["input_scale"]))
    degree = torch.bincount(data.edge_index[1], minlength=data.num_nodes).clamp(min=1)
    ptq_output, ptq_intermediates = run_integer_network(
        input_int8, data.edge_index, degree, parameters, po2=False
    )
    po2_output, po2_intermediates = run_integer_network(
        input_int8, data.edge_index, degree, parameters, po2=True
    )

    predictions = {
        "Float no-root": float_no_root_output.argmax(dim=1),
        "PTQ INT8 no-root": ptq_output.argmax(dim=1),
        "PO2 HLS policy no-root": po2_output.argmax(dim=1),
        "QAT v2 no-root": qat_no_root_output.argmax(dim=1),
        "Float root": float_root_output.argmax(dim=1),
        "QAT v2 root": qat_root_output.argmax(dim=1),
    }
    accuracies = {
        name: accuracy(prediction, data.y, data.test_mask)
        for name, prediction in predictions.items()
    }
    po2_prediction = predictions["PO2 HLS policy no-root"]
    agreements = {
        name: accuracy(prediction, po2_prediction, data.test_mask)
        for name, prediction in predictions.items()
        if name != "PO2 HLS policy no-root"
    }

    report = {
        "dataset": {
            "name": "Cora",
            "nodes": data.num_nodes,
            "test_nodes": int(data.test_mask.sum()),
        },
        "packaged_po2_reference_max_error_lsb": packaged_max_error,
        "accuracies": accuracies,
        "agreement_with_po2": agreements,
        "saturation_percent": {
            "PTQ INT8 no-root": saturation(ptq_intermediates),
            "PO2 HLS policy no-root": saturation(po2_intermediates),
        },
        "po2_minus_qat_root_percentage_points": 100.0 * (
            accuracies["PO2 HLS policy no-root"] - accuracies["QAT v2 root"]
        ),
    }
    output_path = PROJECT_ROOT / "build" / "cora_po2_qat_comparison.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")

    print(f"Packaged PO2 reference check: {packaged_max_error} LSB")
    print(f"Cora test nodes: {int(data.test_mask.sum())}")
    for name, value in accuracies.items():
        print(f"{name:26s}: {100.0 * value:6.2f}%")
    print("\nAgreement with PO2 on Cora test nodes:")
    for name, value in agreements.items():
        print(f"{name:26s}: {100.0 * value:6.2f}%")
    print(f"\nPO2 - QAT root: {report['po2_minus_qat_root_percentage_points']:+.2f} pp")
    print(f"Report: {output_path}")


if __name__ == "__main__":
    main()