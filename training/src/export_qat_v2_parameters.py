"""
Export QAT v2 Parameters for HLS

Extracts all quantization scales, INT8 weights, INT32 biases, and the four
fixed-point HLS scale factors from a trained ReducedGraphSAGEQATv2 checkpoint.

Outputs (build/weights_qat_v2/):
  weights_layer1_int8.txt   - INT8 conv1 weights  [24, 16]
  weights_layer2_int8.txt   - INT8 conv2 weights  [7,  24]
  bias_layer1_int32.txt     - INT32 conv1 biases  [24]
  bias_layer2_int32.txt     - INT32 conv2 biases  [7]
  adj_matrix_int16.txt      - INT16 mean-normalized adjacency [N, N]
  proj_weights_int8.txt     - INT8 projection weights [16, 1433]
  proj_bias_int32.txt       - INT32 projection biases [16]
  network_input_proj_int8.txt - INT8 projected input for subgraph [N, 16]
  qat_v2_params.json        - all scales and fixed-point parameters

Usage:
  cd src && python export_qat_v2_parameters.py
  cd src && python export_qat_v2_parameters.py --m-bits 20
"""

import argparse
import json
import os
import sys

import numpy as np
import torch
from torch_geometric.data import Data
from torch_geometric.datasets import Planetoid
from torch_geometric.transforms import NormalizeFeatures
torch.serialization.add_safe_globals([Data])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model_qat_v2 import ReducedGraphSAGEQATv2

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_ROOT, "build", "models")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "build", "weights_qat_v2")
QAT_V2_MODEL_PATH = os.path.join(MODELS_DIR, "qat_v2_best.pth")

NUM_NODES = 8    # subgraph size for HLS
CENTER_NODE = 6  # fixed so outputs are reproducible
NUM_HOPS = 2


def quantize_int8(tensor_float, scale):
    """Symmetric per-tensor INT8 quantization: round(x / scale), clipped to [-128, 127]."""
    q = np.round(tensor_float / scale).astype(np.int32)
    return np.clip(q, -128, 127).astype(np.int8)


def extract_subgraph(data, center_node, num_nodes, num_hops=2):
    """
    Return (adj_float [N,N], x_float [N,1433], node_indices [N]).

    Nodes are selected by BFS from center_node to guarantee that the chosen
    subgraph is connected (at least a spanning tree of edges exists).
    Sorting by index would yield nodes from across the graph with no edges.
    """
    from collections import deque

    # Build adjacency list (undirected view of PyG edge_index)
    adj_list = [[] for _ in range(data.num_nodes)]
    src_arr = data.edge_index[0].tolist()
    dst_arr = data.edge_index[1].tolist()
    for s, d in zip(src_arr, dst_arr):
        adj_list[s].append(d)

    # BFS — each node added is adjacent to at least one already-selected node
    visited = [center_node]
    seen = {center_node}
    queue = deque([center_node])
    while len(visited) < num_nodes and queue:
        node = queue.popleft()
        for nb in adj_list[node]:
            if nb not in seen:
                seen.add(nb)
                visited.append(nb)
                queue.append(nb)
                if len(visited) >= num_nodes:
                    break

    subset = torch.tensor(visited[:num_nodes], dtype=torch.long)
    n = len(subset)

    # Extract edges within the subset and relabel to [0, n-1]
    node_mask = torch.zeros(data.num_nodes, dtype=torch.bool)
    node_mask[subset] = True
    edge_mask = node_mask[data.edge_index[0]] & node_mask[data.edge_index[1]]
    edge_index = data.edge_index[:, edge_mask]

    mapping = torch.full((data.num_nodes,), -1, dtype=torch.long)
    mapping[subset] = torch.arange(n)
    edge_index = mapping[edge_index]

    adj = torch.zeros((n, n), dtype=torch.float32)
    adj[edge_index[1], edge_index[0]] = 1.0

    # Row-normalize: adj[i,j] = 1/degree_in[i] if edge j→i
    deg = adj.sum(dim=1)
    deg_inv = 1.0 / deg
    deg_inv[deg_inv == float("inf")] = 0.0
    adj = deg_inv.view(-1, 1) * adj

    x = data.x[subset].numpy()
    return adj.numpy(), x, subset.numpy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--m-bits", type=int, default=24,
                        help="Fixed-point fractional bits (default 24 for 0 LSB error)")
    args = parser.parse_args()

    M = args.m_bits
    K = 4096     # adjacency fixed-point scale = 2^12
    K_BITS = 12

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("QAT v2 PARAMETER EXPORT")
    print("=" * 70)
    print(f"  M (fractional bits) : {M}")
    print(f"  K (adj scale)       : {K}  (2^{K_BITS})")
    print(f"  Subgraph size       : {NUM_NODES} nodes, center={CENTER_NODE}")

    # ------------------------------------------------------------------ #
    # Load trained QAT v2 model
    # ------------------------------------------------------------------ #
    if not os.path.exists(QAT_V2_MODEL_PATH):
        print(f"\nERROR: checkpoint not found: {QAT_V2_MODEL_PATH}")
        print("Run:  cd src && python train_qat_v2.py")
        sys.exit(1)

    dataset = Planetoid(
        root=os.path.join(PROJECT_ROOT, "data"),
        name="Cora",
        transform=NormalizeFeatures(),
    )
    data = dataset[0]

    model = ReducedGraphSAGEQATv2(
        in_channels=dataset.num_features,
        in_channels_reduced=16,
        hidden_channels=24,
        out_channels=dataset.num_classes,
        dropout=0.5,
        use_projection=True,
        root_weight=False,
        num_bits=8,
    )
    ckpt = torch.load(QAT_V2_MODEL_PATH, weights_only=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    print(f"\nLoaded checkpoint: test_acc={ckpt.get('test_acc', '?'):.4f}")

    # ------------------------------------------------------------------ #
    # Extract quantization scales
    # ------------------------------------------------------------------ #
    def scale_of(fq):
        return fq.scale.detach().cpu().item()

    scale_proj_in  = scale_of(model.projection.input_fake_quant)
    scale_proj_w   = scale_of(model.projection.weight_fake_quant)
    scale_proj_out = scale_of(model.projection_output_quant)   # HLS kernel input scale

    scale_agg1  = scale_of(model.conv1.lin_neighbor.input_fake_quant)
    scale_w1    = scale_of(model.conv1.lin_neighbor.weight_fake_quant)
    scale_hidden = scale_of(model.conv1.output_fake_quant)

    scale_agg2  = scale_of(model.conv2.lin_neighbor.input_fake_quant)
    scale_w2    = scale_of(model.conv2.lin_neighbor.weight_fake_quant)
    scale_out   = scale_of(model.conv2.output_fake_quant)

    print("\nQuantization scales:")
    print(f"  Projection  in : {scale_proj_in:.8f}")
    print(f"  Projection  w  : {scale_proj_w:.8f}")
    print(f"  Projection  out: {scale_proj_out:.8f}  ← HLS kernel input scale")
    print(f"  Conv1  agg     : {scale_agg1:.8f}")
    print(f"  Conv1  w       : {scale_w1:.8f}")
    print(f"  Conv1  out     : {scale_hidden:.8f}")
    print(f"  Conv2  agg     : {scale_agg2:.8f}")
    print(f"  Conv2  w       : {scale_w2:.8f}")
    print(f"  Conv2  out     : {scale_out:.8f}")

    # ------------------------------------------------------------------ #
    # Quantize conv weights to INT8
    # ------------------------------------------------------------------ #
    w1_float = model.conv1.lin_neighbor.linear.weight.detach().cpu().numpy()  # [24, 16]
    w2_float = model.conv2.lin_neighbor.linear.weight.detach().cpu().numpy()  # [7,  24]

    weights1_int8 = quantize_int8(w1_float, scale_w1)
    weights2_int8 = quantize_int8(w2_float, scale_w2)

    print(f"\nINT8 weights:")
    print(f"  Layer 1: {weights1_int8.shape}  range=[{weights1_int8.min()}, {weights1_int8.max()}]")
    print(f"  Layer 2: {weights2_int8.shape}  range=[{weights2_int8.min()}, {weights2_int8.max()}]")

    # ------------------------------------------------------------------ #
    # Convert biases to INT32 accumulator domain
    #   bias_int32 = round(bias_float / (scale_agg * scale_w))
    # ------------------------------------------------------------------ #
    bias1_float = model.conv1.lin_neighbor.linear.bias.detach().cpu().numpy()  # [24]
    bias2_float = model.conv2.lin_neighbor.linear.bias.detach().cpu().numpy()  # [7]

    bias1_int32 = np.round(bias1_float / (scale_agg1 * scale_w1)).astype(np.int32)
    bias2_int32 = np.round(bias2_float / (scale_agg2 * scale_w2)).astype(np.int32)

    print(f"\nINT32 biases:")
    print(f"  Layer 1: {bias1_int32.shape}  range=[{bias1_int32.min()}, {bias1_int32.max()}]")
    print(f"  Layer 2: {bias2_int32.shape}  range=[{bias2_int32.min()}, {bias2_int32.max()}]")

    # ------------------------------------------------------------------ #
    # Fixed-point HLS scale parameters
    #
    #  beta_fp encodes: scale_in / (K * scale_agg_out)
    #  eff_scale_fp encodes: (scale_agg_in * scale_w) / scale_out
    # ------------------------------------------------------------------ #
    beta1 = scale_proj_out / (K * scale_agg1)
    beta2 = scale_hidden   / (K * scale_agg2)

    eff_scale1 = (scale_agg1 * scale_w1) / scale_hidden
    eff_scale2 = (scale_agg2 * scale_w2) / scale_out

    beta1_fp       = int(round(beta1       * (2 ** M)))
    beta2_fp       = int(round(beta2       * (2 ** M)))
    eff_scale1_fp  = int(round(eff_scale1  * (2 ** M)))
    eff_scale2_fp  = int(round(eff_scale2  * (2 ** M)))

    print(f"\nFixed-point HLS parameters (M={M}):")
    print(f"  beta1      = {beta1:.8f}  → beta1_fp      = {beta1_fp}")
    print(f"  beta2      = {beta2:.8f}  → beta2_fp      = {beta2_fp}")
    print(f"  eff_scale1 = {eff_scale1:.8f}  → eff_scale1_fp = {eff_scale1_fp}")
    print(f"  eff_scale2 = {eff_scale2:.8f}  → eff_scale2_fp = {eff_scale2_fp}")

    # ------------------------------------------------------------------ #
    # Extract subgraph and build adjacency matrix
    # ------------------------------------------------------------------ #
    print(f"\nExtracting {NUM_NODES}-node subgraph (center={CENTER_NODE}) ...")
    adj_float, x_raw, node_indices = extract_subgraph(data, CENTER_NODE, NUM_NODES, NUM_HOPS)
    n_actual = adj_float.shape[0]
    print(f"  Subgraph nodes: {n_actual}  (indices {node_indices})")

    # INT16 adjacency
    adj_int16 = np.round(adj_float * K).astype(np.int16)
    print(f"  Adj INT16 range: [{adj_int16.min()}, {adj_int16.max()}]")

    # ------------------------------------------------------------------ #
    # Apply projection offline to produce INT8 16-dim input for HLS
    # ------------------------------------------------------------------ #
    proj_w = model.projection.linear.weight.detach().cpu().numpy()  # [16, 1433]
    proj_b = model.projection.linear.bias.detach().cpu().numpy()    # [16]

    # Float projection
    proj_out_float = x_raw @ proj_w.T + proj_b    # [N, 16]
    proj_out_float = np.maximum(proj_out_float, 0.0)  # ReLU

    # Quantize projection output using scale_proj_out
    input_int8 = quantize_int8(proj_out_float, scale_proj_out)
    print(f"\nProjected INT8 input: {input_int8.shape}  range=[{input_int8.min()}, {input_int8.max()}]")

    # Also quantize projection weights (for completeness / future standalone use)
    scale_proj_in_val = scale_of(model.projection.input_fake_quant)
    proj_w_int8 = quantize_int8(proj_w, scale_proj_w)
    proj_bias_int32 = np.round(proj_b / (scale_proj_in_val * scale_proj_w)).astype(np.int32)

    # ------------------------------------------------------------------ #
    # Save all outputs
    # ------------------------------------------------------------------ #
    np.savetxt(os.path.join(OUTPUT_DIR, "weights_layer1_int8.txt"), weights1_int8, fmt="%d")
    np.savetxt(os.path.join(OUTPUT_DIR, "weights_layer2_int8.txt"), weights2_int8, fmt="%d")
    np.savetxt(os.path.join(OUTPUT_DIR, "bias_layer1_int32.txt"),   bias1_int32,   fmt="%d")
    np.savetxt(os.path.join(OUTPUT_DIR, "bias_layer2_int32.txt"),   bias2_int32,   fmt="%d")
    np.savetxt(os.path.join(OUTPUT_DIR, "adj_matrix_int16.txt"),    adj_int16,     fmt="%d")
    np.savetxt(os.path.join(OUTPUT_DIR, "network_input_proj_int8.txt"), input_int8, fmt="%d")
    np.savetxt(os.path.join(OUTPUT_DIR, "proj_weights_int8.txt"),   proj_w_int8,   fmt="%d")
    np.savetxt(os.path.join(OUTPUT_DIR, "proj_bias_int32.txt"),     proj_bias_int32, fmt="%d")

    params = {
        "fixed_point_config": {"M": M, "K": K, "K_BITS": K_BITS},
        "quantization_scales": {
            "scale_proj_in":  float(scale_proj_in),
            "scale_proj_w":   float(scale_proj_w),
            "scale_proj_out": float(scale_proj_out),
            "scale_agg1":     float(scale_agg1),
            "scale_w1":       float(scale_w1),
            "scale_hidden":   float(scale_hidden),
            "scale_agg2":     float(scale_agg2),
            "scale_w2":       float(scale_w2),
            "scale_out":      float(scale_out),
        },
        "float_scale_values": {
            "beta1": float(beta1), "beta2": float(beta2),
            "eff_scale1": float(eff_scale1), "eff_scale2": float(eff_scale2),
        },
        "fixed_point_scales": {
            "beta1_fp": beta1_fp, "beta2_fp": beta2_fp,
            "eff_scale1_fp": eff_scale1_fp, "eff_scale2_fp": eff_scale2_fp,
        },
        "subgraph": {
            "num_nodes": int(n_actual),
            "center_node": int(CENTER_NODE),
            "node_indices": node_indices.tolist(),
        },
        "architecture": {
            "in_features": 16, "hidden_features": 24, "out_features": 7,
        },
    }

    params_path = os.path.join(OUTPUT_DIR, "qat_v2_params.json")
    with open(params_path, "w") as f:
        json.dump(params, f, indent=2)

    print(f"\nSaved to {OUTPUT_DIR}/")
    for fname in [
        "weights_layer1_int8.txt", "weights_layer2_int8.txt",
        "bias_layer1_int32.txt", "bias_layer2_int32.txt",
        "adj_matrix_int16.txt", "network_input_proj_int8.txt",
        "proj_weights_int8.txt", "proj_bias_int32.txt",
        "qat_v2_params.json",
    ]:
        print(f"  ✓ {fname}")


if __name__ == "__main__":
    main()
