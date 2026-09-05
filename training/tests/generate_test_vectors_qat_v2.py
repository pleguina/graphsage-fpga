"""
QAT v2 Integer-Only Emulator and Test Vector Generator

Implements the exact same integer-only arithmetic that the HLS kernel uses,
giving bit-exact reference outputs for C-simulation verification.

Prerequisites:
  cd src && python train_qat_v2.py          # train and save checkpoint
  cd src && python export_qat_v2_parameters.py  # export INT8 weights + scales

Outputs (build/test_vectors_qat_v2/):
  network_input_int8.txt          - INT8 input to HLS kernel [N, 16]
  adj_matrix_int16.txt            - INT16 adjacency [N, N]
  weights_layer1_int8.txt         - INT8 weights layer 1 [24, 16]
  weights_layer2_int8.txt         - INT8 weights layer 2 [7, 24]
  bias_layer1_int32.txt           - INT32 biases layer 1 [24]
  bias_layer2_int32.txt           - INT32 biases layer 2 [7]
  network_output_int8_reference.txt - INT8 reference output [N, 7]
  layer1_agg_int8.txt             - intermediate: post-agg1 [N, 16]
  layer1_hidden_int8.txt          - intermediate: post-linear1+ReLU [N, 24]
  layer2_agg_int8.txt             - intermediate: post-agg2 [N, 24]
  int8_config.txt                 - M, K, scale parameters (text)
"""

import json
import sys
import os
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
WEIGHTS_DIR = PROJECT_ROOT / "build" / "weights_qat_v2"
OUTPUT_DIR = PROJECT_ROOT / "build" / "test_vectors_qat_v2"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 70)
print("QAT v2 INTEGER-ONLY EMULATOR")
print("=" * 70)

# ------------------------------------------------------------------ #
# Load parameters exported by export_qat_v2_parameters.py
# ------------------------------------------------------------------ #
params_path = WEIGHTS_DIR / "qat_v2_params.json"
if not params_path.exists():
    print(f"\nERROR: {params_path} not found.")
    print("Run:  cd src && python export_qat_v2_parameters.py")
    sys.exit(1)

with open(params_path) as f:
    params = json.load(f)

M       = params["fixed_point_config"]["M"]
K       = params["fixed_point_config"]["K"]
K_BITS  = params["fixed_point_config"]["K_BITS"]

beta1_fp      = params["fixed_point_scales"]["beta1_fp"]
beta2_fp      = params["fixed_point_scales"]["beta2_fp"]
eff_scale1_fp = params["fixed_point_scales"]["eff_scale1_fp"]
eff_scale2_fp = params["fixed_point_scales"]["eff_scale2_fp"]

print(f"\nFixed-point config: M={M}, K={K} (2^{K_BITS})")
print(f"  beta1_fp      = {beta1_fp}")
print(f"  beta2_fp      = {beta2_fp}")
print(f"  eff_scale1_fp = {eff_scale1_fp}")
print(f"  eff_scale2_fp = {eff_scale2_fp}")

# Load INT8 inputs and weights
input_int8    = np.loadtxt(WEIGHTS_DIR / "network_input_proj_int8.txt", dtype=np.int8)
adj_int16     = np.loadtxt(WEIGHTS_DIR / "adj_matrix_int16.txt",        dtype=np.int16)
weights1_int8 = np.loadtxt(WEIGHTS_DIR / "weights_layer1_int8.txt",     dtype=np.int8).reshape(24, 16)
weights2_int8 = np.loadtxt(WEIGHTS_DIR / "weights_layer2_int8.txt",     dtype=np.int8).reshape(7, 24)
bias1_int32   = np.loadtxt(WEIGHTS_DIR / "bias_layer1_int32.txt",       dtype=np.int32)
bias2_int32   = np.loadtxt(WEIGHTS_DIR / "bias_layer2_int32.txt",       dtype=np.int32)

print(f"\nLoaded inputs:")
print(f"  input_int8:    {input_int8.shape}")
print(f"  adj_int16:     {adj_int16.shape}  non-zero={np.count_nonzero(adj_int16)}")
print(f"  weights1_int8: {weights1_int8.shape}")
print(f"  weights2_int8: {weights2_int8.shape}")
print(f"  bias1_int32:   {bias1_int32.shape}  range=[{bias1_int32.min()}, {bias1_int32.max()}]")
print(f"  bias2_int32:   {bias2_int32.shape}  range=[{bias2_int32.min()}, {bias2_int32.max()}]")

# ------------------------------------------------------------------ #
# Integer-only helper functions  (identical to testbench C++ logic)
# ------------------------------------------------------------------ #

def int8_clamp(x):
    """Clamp to INT8 range [-128, 127]."""
    return np.clip(x, -128, 127).astype(np.int8)


def aggregate_int_only(features_int8, adj_int16, beta_fp, M):
    """
    Integer-only mean aggregation.

    Computes for each node i and feature f:
      tmp     = Σ_j  adj_int16[i,j] * features[j,f]       (INT32 accumulator)
      scaled  = tmp * beta_fp                               (INT64)
      result  = (scaled + 2^(M-1)) >> M                   (with rounding)
      q_out   = clamp(result, -128, 127)                   (INT8)

    beta_fp = round(scale_in / (K * scale_agg_out) * 2^M)
    adj_int16 encodes the mean-normalized adjacency scaled by K.
    """
    N, F = features_int8.shape
    agg_out = np.zeros((N, F), dtype=np.int8)
    round_const = np.int64(1) << (M - 1)

    for i in range(N):
        for f in range(F):
            tmp = np.int32(0)
            for j in range(N):
                if adj_int16[i, j] != 0:
                    tmp = np.int32(tmp + np.int32(adj_int16[i, j]) * np.int32(features_int8[j, f]))

            scaled  = np.int64(tmp) * np.int64(beta_fp)
            rounded = scaled + round_const
            result  = rounded >> M
            agg_out[i, f] = int8_clamp(result)

    return agg_out


def linear_int_only(features_int8, weights_int8, bias_int32, eff_scale_fp, M):
    """
    Integer-only linear transform + requantization.

    For each node n and output channel o:
      acc    = bias_int32[o] + Σ_f  features[n,f] * weights[o,f]  (INT32)
      scaled = acc * eff_scale_fp                                   (INT64)
      result = (scaled + 2^(M-1)) >> M                            (with rounding)
      q_out  = clamp(result, -128, 127)                            (INT8)

    eff_scale_fp = round((scale_agg * scale_w / scale_out) * 2^M)
    """
    N, IN_F = features_int8.shape
    OUT_F = weights_int8.shape[0]
    output = np.zeros((N, OUT_F), dtype=np.int8)
    round_const = np.int64(1) << (M - 1)

    for n in range(N):
        for o in range(OUT_F):
            acc = np.int32(bias_int32[o])
            for f in range(IN_F):
                acc = np.int32(acc + np.int32(features_int8[n, f]) * np.int32(weights_int8[o, f]))

            scaled  = np.int64(acc) * np.int64(eff_scale_fp)
            rounded = scaled + round_const
            result  = rounded >> M
            output[n, o] = int8_clamp(result)

    return output


def relu_int8(x):
    """In-place ReLU for symmetric INT8 (zero_point=0)."""
    return np.maximum(x, 0).astype(np.int8)


# ------------------------------------------------------------------ #
# Integer-only forward pass
# ------------------------------------------------------------------ #
print("\n" + "=" * 70)
print("INTEGER-ONLY FORWARD PASS")
print("=" * 70)

print(f"\nInput: {input_int8.shape}  node 0: {input_int8[0, :8]}")

# Layer 1 — Aggregation
print("\n--- Layer 1: Aggregation ---")
agg1_int8 = aggregate_int_only(input_int8, adj_int16, beta1_fp, M)
print(f"  Output: {agg1_int8.shape}  range=[{agg1_int8.min()}, {agg1_int8.max()}]")
print(f"  Node 0: {agg1_int8[0, :8]}")

# Layer 1 — Linear
print("\n--- Layer 1: Linear ---")
hidden_int8 = linear_int_only(agg1_int8, weights1_int8, bias1_int32, eff_scale1_fp, M)
print(f"  Output (before ReLU): {hidden_int8.shape}  range=[{hidden_int8.min()}, {hidden_int8.max()}]")

# Layer 1 — ReLU
hidden_int8 = relu_int8(hidden_int8)
print(f"  Output (after ReLU):  range=[{hidden_int8.min()}, {hidden_int8.max()}]")
print(f"  Node 0: {hidden_int8[0, :8]}")

# Layer 2 — Aggregation
print("\n--- Layer 2: Aggregation ---")
agg2_int8 = aggregate_int_only(hidden_int8, adj_int16, beta2_fp, M)
print(f"  Output: {agg2_int8.shape}  range=[{agg2_int8.min()}, {agg2_int8.max()}]")
print(f"  Node 0: {agg2_int8[0, :8]}")

# Layer 2 — Linear (no ReLU)
print("\n--- Layer 2: Linear ---")
output_int8 = linear_int_only(agg2_int8, weights2_int8, bias2_int32, eff_scale2_fp, M)
print(f"  Output: {output_int8.shape}  range=[{output_int8.min()}, {output_int8.max()}]")
print(f"  Node 0 logits: {output_int8[0]}")
print(f"  Node 0 pred:   class {output_int8[0].argmax()}")

# ------------------------------------------------------------------ #
# Save test vectors
# ------------------------------------------------------------------ #
print("\n" + "=" * 70)
print("SAVING TEST VECTORS")
print("=" * 70)

np.savetxt(OUTPUT_DIR / "network_input_int8.txt",           input_int8,    fmt="%d")
np.savetxt(OUTPUT_DIR / "adj_matrix_int16.txt",             adj_int16,     fmt="%d")
np.savetxt(OUTPUT_DIR / "weights_layer1_int8.txt",          weights1_int8, fmt="%d")
np.savetxt(OUTPUT_DIR / "weights_layer2_int8.txt",          weights2_int8, fmt="%d")
np.savetxt(OUTPUT_DIR / "bias_layer1_int32.txt",            bias1_int32,   fmt="%d")
np.savetxt(OUTPUT_DIR / "bias_layer2_int32.txt",            bias2_int32,   fmt="%d")
np.savetxt(OUTPUT_DIR / "network_output_int8_reference.txt", output_int8,  fmt="%d")
np.savetxt(OUTPUT_DIR / "layer1_agg_int8.txt",              agg1_int8,     fmt="%d")
np.savetxt(OUTPUT_DIR / "layer1_hidden_int8.txt",           hidden_int8,   fmt="%d")
np.savetxt(OUTPUT_DIR / "layer2_agg_int8.txt",              agg2_int8,     fmt="%d")

with open(OUTPUT_DIR / "int8_config.txt", "w") as f:
    f.write(f"M: {M}\n")
    f.write(f"K: {K}\n")
    f.write(f"K_BITS: {K_BITS}\n")
    f.write(f"beta1_fp: {beta1_fp}\n")
    f.write(f"beta2_fp: {beta2_fp}\n")
    f.write(f"eff_scale1_fp: {eff_scale1_fp}\n")
    f.write(f"eff_scale2_fp: {eff_scale2_fp}\n")
    for k, v in params["quantization_scales"].items():
        f.write(f"{k}: {v}\n")

print(f"\nSaved to {OUTPUT_DIR}/")
for fname in [
    "network_input_int8.txt", "adj_matrix_int16.txt",
    "weights_layer1_int8.txt", "weights_layer2_int8.txt",
    "bias_layer1_int32.txt", "bias_layer2_int32.txt",
    "network_output_int8_reference.txt",
    "layer1_agg_int8.txt", "layer1_hidden_int8.txt", "layer2_agg_int8.txt",
    "int8_config.txt",
]:
    print(f"  ✓ {fname}")

print("\n" + "=" * 70)
print("Integer-only emulation complete.")
print("=" * 70)
