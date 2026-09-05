"""
Python Integer-Only PTQ Emulator

This script implements the EXACT same integer-only arithmetic
that will be used in the HLS implementation.

Purpose: Generate bit-exact reference outputs for HLS validation.

All operations use:
- INT8 for weights and activations
- INT16 for adjacency matrix
- INT32 for accumulators and intermediate values
- INT64 for multiplication results (before shift)
- No floating point in the forward pass
"""

import json
import numpy as np
from pathlib import Path

# ============================================================================
# Configuration
# ============================================================================

INT8_DIR = Path("../build/weights_ptq_int8")
PTQ_DIR = Path("../build/weights_ptq_float")
TEST_VECTORS_DIR = Path("../build/test_vectors_ptq_float")
OUTPUT_DIR = Path("../build/test_vectors_ptq_int8")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("="*80)
print("PYTHON INTEGER-ONLY PTQ EMULATOR")
print("="*80)

# ============================================================================
# Load integer parameters
# ============================================================================

print("\nLoading integer-only parameters...")

# Load configuration
with open(INT8_DIR / "int8_params.json", 'r') as f:
    params = json.load(f)

M = params['fixed_point_config']['M']
K = params['fixed_point_config']['K']
K_BITS = params['fixed_point_config']['K_BITS']

eff_scale1_fp = params['fixed_point_scales']['eff_scale1_fp']
eff_scale2_fp = params['fixed_point_scales']['eff_scale2_fp']
beta1_fp = params['fixed_point_scales']['beta1_fp']
beta2_fp = params['fixed_point_scales']['beta2_fp']

print(f"  M={M}, K={K} (2^{K_BITS})")
print(f"  eff_scale1_fp={eff_scale1_fp}")
print(f"  eff_scale2_fp={eff_scale2_fp}")
print(f"  beta1_fp={beta1_fp}")
print(f"  beta2_fp={beta2_fp}")

# Load INT8 weights
weights1_int8 = np.loadtxt(PTQ_DIR / "conv1_lin_l_weight.txt", dtype=np.int8).reshape(24, 16)
weights2_int8 = np.loadtxt(PTQ_DIR / "conv2_lin_l_weight.txt", dtype=np.int8).reshape(7, 24)

print(f"\nLoaded INT8 weights:")
print(f"  Layer 1: {weights1_int8.shape}")
print(f"  Layer 2: {weights2_int8.shape}")

# Load INT32 biases
bias1_int32 = np.loadtxt(INT8_DIR / "bias_layer1_int32.txt", dtype=np.int32)
bias2_int32 = np.loadtxt(INT8_DIR / "bias_layer2_int32.txt", dtype=np.int32)

print(f"\nLoaded INT32 biases:")
print(f"  Layer 1: {bias1_int32.shape}, range=[{bias1_int32.min()}, {bias1_int32.max()}]")
print(f"  Layer 2: {bias2_int32.shape}, range=[{bias2_int32.min()}, {bias2_int32.max()}]")

# Load INT16 adjacency
adj_matrix_int16 = np.loadtxt(INT8_DIR / "adj_matrix_int16.txt", dtype=np.int16)

print(f"\nLoaded INT16 adjacency:")
print(f"  Shape: {adj_matrix_int16.shape}")
print(f"  Range: [{adj_matrix_int16.min()}, {adj_matrix_int16.max()}]")
print(f"  Non-zero: {np.count_nonzero(adj_matrix_int16)}")

# Load INT8 test input
input_int8 = np.loadtxt(TEST_VECTORS_DIR / "network_input.txt", dtype=np.int8)

print(f"\nLoaded INT8 input:")
print(f"  Shape: {input_int8.shape}")

# ============================================================================
# Integer-only helper functions
# ============================================================================

def int8_clamp(x):
    """Clamp to INT8 range [-128, 127]"""
    return np.clip(x, -128, 127).astype(np.int8)

def aggregate_int_only(features_int8, adj_int16, beta_fp, M):
    """
    Integer-only aggregation
    
    features_int8: [N_NODES, N_FEAT] INT8
    adj_int16: [N_NODES, N_NODES] INT16 (scaled by K)
    beta_fp: INT32 (beta * 2^M)
    M: fractional bits
    
    Returns: [N_NODES, N_FEAT] INT8
    """
    N_NODES, N_FEAT = features_int8.shape
    agg_out = np.zeros((N_NODES, N_FEAT), dtype=np.int8)
    
    for i in range(N_NODES):
        for f in range(N_FEAT):
            # Accumulate: tmp = Σ A_fp[i,j] * q_j
            tmp = np.int32(0)
            for j in range(N_NODES):
                if adj_int16[i, j] != 0:
                    tmp += np.int32(adj_int16[i, j]) * np.int32(features_int8[j, f])
            
            # Scale: tmp_scaled = tmp * beta_fp (INT64)
            tmp_scaled = np.int64(tmp) * np.int64(beta_fp)
            
            # Round: add (1 << (M-1))
            tmp_rounded = tmp_scaled + (1 << (M - 1))
            
            # Shift: >> M
            q_agg_int = tmp_rounded >> M
            
            # Clamp to INT8
            agg_out[i, f] = int8_clamp(q_agg_int)
    
    return agg_out

def linear_int_only(features_int8, weights_int8, bias_int32, eff_scale_fp, M):
    """
    Integer-only linear transformation
    
    features_int8: [N_NODES, IN_FEAT] INT8
    weights_int8: [OUT_FEAT, IN_FEAT] INT8
    bias_int32: [OUT_FEAT] INT32 (in accumulator domain)
    eff_scale_fp: INT32 (eff_scale * 2^M)
    M: fractional bits
    
    Returns: [N_NODES, OUT_FEAT] INT8
    """
    N_NODES, IN_FEAT = features_int8.shape
    OUT_FEAT, _ = weights_int8.shape
    output = np.zeros((N_NODES, OUT_FEAT), dtype=np.int8)
    
    for n in range(N_NODES):
        for o in range(OUT_FEAT):
            # MAC: acc = Σ x_q[f] * w_q[o,f] + bias_int32[o]
            acc = np.int32(bias_int32[o])
            for f in range(IN_FEAT):
                acc += np.int32(features_int8[n, f]) * np.int32(weights_int8[o, f])
            
            # Requantize: tmp_scaled = acc * eff_scale_fp (INT64)
            tmp_scaled = np.int64(acc) * np.int64(eff_scale_fp)
            
            # Round: add (1 << (M-1))
            tmp_rounded = tmp_scaled + (1 << (M - 1))
            
            # Shift: >> M
            q_out_int = tmp_rounded >> M
            
            # Clamp to INT8
            output[n, o] = int8_clamp(q_out_int)
    
    return output

def relu_int8(x_int8):
    """ReLU for INT8 (symmetric quantization, zero_point=0)"""
    return np.maximum(x_int8, 0).astype(np.int8)

# ============================================================================
# Integer-only forward pass
# ============================================================================

print("\n" + "="*80)
print("INTEGER-ONLY FORWARD PASS")
print("="*80)

print("\nInput shape:", input_int8.shape)

# Layer 1: Aggregate
print("\n--- Layer 1 Aggregation ---")
agg1_int8 = aggregate_int_only(input_int8, adj_matrix_int16, beta1_fp, M)
print(f"  Aggregation output: {agg1_int8.shape}")
print(f"  Range: [{agg1_int8.min()}, {agg1_int8.max()}]")
print(f"  Node 6: {agg1_int8[6, :8]}")

# Layer 1: Linear
print("\n--- Layer 1 Linear ---")
hidden_int8 = linear_int_only(agg1_int8, weights1_int8, bias1_int32, eff_scale1_fp, M)
print(f"  Linear output: {hidden_int8.shape}")
print(f"  Range (before ReLU): [{hidden_int8.min()}, {hidden_int8.max()}]")
print(f"  Node 6 (before ReLU): {hidden_int8[6, :8]}")

# Layer 1: ReLU
print("\n--- Layer 1 ReLU ---")
hidden_int8 = relu_int8(hidden_int8)
print(f"  Range (after ReLU): [{hidden_int8.min()}, {hidden_int8.max()}]")
print(f"  Node 6 (after ReLU): {hidden_int8[6, :8]}")

# Layer 2: Aggregate
print("\n--- Layer 2 Aggregation ---")
agg2_int8 = aggregate_int_only(hidden_int8, adj_matrix_int16, beta2_fp, M)
print(f"  Aggregation output: {agg2_int8.shape}")
print(f"  Range: [{agg2_int8.min()}, {agg2_int8.max()}]")
print(f"  Node 6: {agg2_int8[6, :8]}")

# Layer 2: Linear (no ReLU)
print("\n--- Layer 2 Linear ---")
output_int8 = linear_int_only(agg2_int8, weights2_int8, bias2_int32, eff_scale2_fp, M)
print(f"  Final output: {output_int8.shape}")
print(f"  Range: [{output_int8.min()}, {output_int8.max()}]")
print(f"  Node 6: {output_int8[6]}")

# ============================================================================
# Save integer-only test vectors
# ============================================================================

print("\n" + "="*80)
print("SAVING INTEGER-ONLY TEST VECTORS")
print("="*80)

# Save all as text files for HLS testbench
np.savetxt(OUTPUT_DIR / "network_input_int8.txt", input_int8, fmt='%d')
np.savetxt(OUTPUT_DIR / "adj_matrix_int16.txt", adj_matrix_int16, fmt='%d')
np.savetxt(OUTPUT_DIR / "weights_layer1_int8.txt", weights1_int8, fmt='%d')
np.savetxt(OUTPUT_DIR / "weights_layer2_int8.txt", weights2_int8, fmt='%d')
np.savetxt(OUTPUT_DIR / "bias_layer1_int32.txt", bias1_int32, fmt='%d')
np.savetxt(OUTPUT_DIR / "bias_layer2_int32.txt", bias2_int32, fmt='%d')
np.savetxt(OUTPUT_DIR / "network_output_int8_reference.txt", output_int8, fmt='%d')

# Save intermediate values for debugging
np.savetxt(OUTPUT_DIR / "layer1_agg_int8.txt", agg1_int8, fmt='%d')
np.savetxt(OUTPUT_DIR / "layer1_hidden_int8.txt", hidden_int8, fmt='%d')
np.savetxt(OUTPUT_DIR / "layer2_agg_int8.txt", agg2_int8, fmt='%d')

# Save parameters
with open(OUTPUT_DIR / "int8_config.txt", 'w') as f:
    f.write(f"M: {M}\n")
    f.write(f"K: {K}\n")
    f.write(f"K_BITS: {K_BITS}\n")
    f.write(f"eff_scale1_fp: {eff_scale1_fp}\n")
    f.write(f"eff_scale2_fp: {eff_scale2_fp}\n")
    f.write(f"beta1_fp: {beta1_fp}\n")
    f.write(f"beta2_fp: {beta2_fp}\n")

print(f"\n✓ Saved test vectors to {OUTPUT_DIR}/")
print(f"  - network_input_int8.txt")
print(f"  - adj_matrix_int16.txt")
print(f"  - weights_layer*_int8.txt")
print(f"  - bias_layer*_int32.txt")
print(f"  - network_output_int8_reference.txt")
print(f"  - int8_config.txt")

# ============================================================================
# Compare with float PTQ reference
# ============================================================================

print("\n" + "="*80)
print("COMPARISON WITH FLOAT PTQ REFERENCE")
print("="*80)

# Load PTQ float reference
ptq_reference_int8 = np.loadtxt(TEST_VECTORS_DIR / "network_output_reference.txt", dtype=np.int8)

print(f"\nFloat PTQ reference: {ptq_reference_int8.shape}")
print(f"Integer-only output: {output_int8.shape}")

# Compare
diff = output_int8 - ptq_reference_int8
exact_match = np.sum(diff == 0)
total = diff.size

print(f"\nComparison:")
print(f"  Exact matches: {exact_match}/{total} ({100*exact_match/total:.1f}%)")
print(f"  Max error: {np.abs(diff).max()} LSB")

# Show differences
if exact_match < total:
    print(f"\nDifferences:")
    for i in range(output_int8.shape[0]):
        for j in range(output_int8.shape[1]):
            if diff[i, j] != 0:
                print(f"  [{i},{j}]: int_only={output_int8[i,j]:4d}, ptq_float={ptq_reference_int8[i,j]:4d}, diff={diff[i,j]:+d}")

print("\n" + "="*80)
print("Integer-only emulation complete!")
print("="*80)
