"""
Python Integer-Only PTQ-PO2 Emulator

This script implements the EXACT same integer-only arithmetic with POWER-OF-TWO scales
that will be used in the HLS PO2 implementation.

Purpose: Generate bit-exact reference outputs for HLS PO2 validation.

Key differences from regular INT8:
- Scale multiplications replaced with bit-shifts
- Uses nearest power-of-2 approximation of scale factors
- Should match HLS PO2 implementation exactly (0 LSB error expected)

All operations use:
- INT8 for weights and activations
- INT16 for adjacency matrix
- INT32 for accumulators and intermediate values
- Bit-shifts instead of scale multiplications
- No floating point in the forward pass
"""

import json
import numpy as np
import math
from pathlib import Path

# ============================================================================
# Configuration
# ============================================================================

INT8_DIR = Path("../build/weights_ptq_int8")
PTQ_DIR = Path("../build/weights_ptq_float")
TEST_VECTORS_DIR = Path("../build/test_vectors_ptq_float")
OUTPUT_DIR = Path("../build/test_vectors_ptq_int8_po2")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("="*80)
print("PYTHON INTEGER-ONLY PTQ-PO2 EMULATOR (Power-of-Two Scales)")
print("="*80)

# ============================================================================
# Load integer parameters and compute PO2 shifts
# ============================================================================

print("\nLoading integer-only parameters...")

# Load configuration
with open(INT8_DIR / "int8_params.json", 'r') as f:
    params = json.load(f)

M = params['fixed_point_config']['M']
K = params['fixed_point_config']['K']
K_BITS = params['fixed_point_config']['K_BITS']

# Original arbitrary-precision scales
eff_scale1_fp_orig = params['fixed_point_scales']['eff_scale1_fp']
eff_scale2_fp_orig = params['fixed_point_scales']['eff_scale2_fp']
beta1_fp_orig = params['fixed_point_scales']['beta1_fp']
beta2_fp_orig = params['fixed_point_scales']['beta2_fp']

print(f"  M={M}, K={K} (2^{K_BITS})")
print(f"\nOriginal (arbitrary) scales:")
print(f"  eff_scale1_fp = {eff_scale1_fp_orig}")
print(f"  eff_scale2_fp = {eff_scale2_fp_orig}")
print(f"  beta1_fp = {beta1_fp_orig}")
print(f"  beta2_fp = {beta2_fp_orig}")

# ============================================================================
# Compute Power-of-Two Approximations
# ============================================================================

def compute_po2_shift(scale_fp, M):
    """
    Convert a fixed-point scale to nearest power-of-2 shift.
    
    Args:
        scale_fp: Fixed-point scale value (scale * 2^M)
        M: Number of fractional bits
    
    Returns:
        shift: Shift amount for bit-shift operation
        po2_value: The power-of-2 approximation of scale_fp
    """
    if scale_fp <= 0:
        return M, 1
    
    log2_val = math.log2(scale_fp)
    po2_exponent = round(log2_val)
    shift = M - po2_exponent
    po2_value = 2 ** po2_exponent
    
    return shift, po2_value

# Compute PO2 shifts
BETA1_SHIFT, beta1_po2 = compute_po2_shift(beta1_fp_orig, M)
BETA2_SHIFT, beta2_po2 = compute_po2_shift(beta2_fp_orig, M)
EFF_SCALE1_SHIFT, eff_scale1_po2 = compute_po2_shift(eff_scale1_fp_orig, M)
EFF_SCALE2_SHIFT, eff_scale2_po2 = compute_po2_shift(eff_scale2_fp_orig, M)

print(f"\nPower-of-Two Approximations:")
print(f"  beta1:      {beta1_fp_orig:8} → 2^{M-BETA1_SHIFT:2} = {beta1_po2:8} (shift={BETA1_SHIFT}, error={(abs(beta1_fp_orig-beta1_po2)/beta1_fp_orig*100):.2f}%)")
print(f"  beta2:      {beta2_fp_orig:8} → 2^{M-BETA2_SHIFT:2} = {beta2_po2:8} (shift={BETA2_SHIFT}, error={(abs(beta2_fp_orig-beta2_po2)/beta2_fp_orig*100):.2f}%)")
print(f"  eff_scale1: {eff_scale1_fp_orig:8} → 2^{M-EFF_SCALE1_SHIFT:2} = {eff_scale1_po2:8} (shift={EFF_SCALE1_SHIFT}, error={(abs(eff_scale1_fp_orig-eff_scale1_po2)/eff_scale1_fp_orig*100):.2f}%)")
print(f"  eff_scale2: {eff_scale2_fp_orig:8} → 2^{M-EFF_SCALE2_SHIFT:2} = {eff_scale2_po2:8} (shift={EFF_SCALE2_SHIFT}, error={(abs(eff_scale2_fp_orig-eff_scale2_po2)/eff_scale2_fp_orig*100):.2f}%)")

# Save PO2 configuration
po2_config = {
    'M_BITS': M,
    'K_BITS': K_BITS,
    'K': K,
    'shifts': {
        'BETA1_SHIFT': BETA1_SHIFT,
        'BETA2_SHIFT': BETA2_SHIFT,
        'EFF_SCALE1_SHIFT': EFF_SCALE1_SHIFT,
        'EFF_SCALE2_SHIFT': EFF_SCALE2_SHIFT
    },
    'po2_values': {
        'beta1_po2': int(beta1_po2),
        'beta2_po2': int(beta2_po2),
        'eff_scale1_po2': int(eff_scale1_po2),
        'eff_scale2_po2': int(eff_scale2_po2)
    },
    'original_values': {
        'beta1_fp': int(beta1_fp_orig),
        'beta2_fp': int(beta2_fp_orig),
        'eff_scale1_fp': int(eff_scale1_fp_orig),
        'eff_scale2_fp': int(eff_scale2_fp_orig)
    }
}

with open(OUTPUT_DIR / "po2_config.json", 'w') as f:
    json.dump(po2_config, f, indent=2)

print(f"\n✓ Saved PO2 configuration to {OUTPUT_DIR / 'po2_config.json'}")

# ============================================================================
# Load data
# ============================================================================

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
# Integer-only PO2 helper functions
# ============================================================================

def int8_clamp(x):
    """Clamp to INT8 range [-128, 127]"""
    return np.clip(x, -128, 127).astype(np.int8)

def aggregate_int_po2(features_int8, adj_int16, shift, M):
    """
    Integer-only aggregation with PO2 bit-shift scaling
    
    features_int8: [N_NODES, N_FEAT] INT8
    adj_int16: [N_NODES, N_NODES] INT16 (scaled by K)
    shift: Shift amount (replaces scale multiplication)
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
            
            # PO2 rescale: bit-shift with rounding
            if shift > 0:
                round_const = 1 << (shift - 1)
                tmp_rounded = tmp + round_const
                q_agg_int = tmp_rounded >> shift
            else:
                q_agg_int = tmp << (-shift)
            
            # Clamp to INT8
            agg_out[i, f] = int8_clamp(q_agg_int)
    
    return agg_out

def linear_int_po2(features_int8, weights_int8, bias_int32, shift, M):
    """
    Integer-only linear transformation with PO2 bit-shift scaling
    
    features_int8: [N_NODES, IN_FEAT] INT8
    weights_int8: [OUT_FEAT, IN_FEAT] INT8
    bias_int32: [OUT_FEAT] INT32 (in accumulator domain)
    shift: Shift amount (replaces scale multiplication)
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
            
            # PO2 rescale: bit-shift with rounding
            if shift > 0:
                round_const = 1 << (shift - 1)
                tmp_rounded = acc + round_const
                q_out_int = tmp_rounded >> shift
            else:
                q_out_int = acc << (-shift)
            
            # Clamp to INT8
            output[n, o] = int8_clamp(q_out_int)
    
    return output

def relu_int8(x_int8):
    """ReLU for INT8 (symmetric quantization, zero_point=0)"""
    return np.maximum(x_int8, 0).astype(np.int8)

# ============================================================================
# Integer-only PO2 forward pass
# ============================================================================

print("\n" + "="*80)
print("INTEGER-ONLY PO2 FORWARD PASS")
print("="*80)

print("\nInput shape:", input_int8.shape)

# Layer 1: Aggregate
print("\n--- Layer 1 Aggregation (PO2) ---")
print(f"  Using shift={BETA1_SHIFT} (replaces beta1_fp={beta1_fp_orig} → {beta1_po2})")
agg1_int8 = aggregate_int_po2(input_int8, adj_matrix_int16, BETA1_SHIFT, M)
print(f"  Aggregation output: {agg1_int8.shape}")
print(f"  Range: [{agg1_int8.min()}, {agg1_int8.max()}]")
print(f"  Node 6: {agg1_int8[6, :8]}")

# Layer 1: Linear
print("\n--- Layer 1 Linear (PO2) ---")
print(f"  Using shift={EFF_SCALE1_SHIFT} (replaces eff_scale1_fp={eff_scale1_fp_orig} → {eff_scale1_po2})")
hidden_int8 = linear_int_po2(agg1_int8, weights1_int8, bias1_int32, EFF_SCALE1_SHIFT, M)
print(f"  Linear output: {hidden_int8.shape}")
print(f"  Range (before ReLU): [{hidden_int8.min()}, {hidden_int8.max()}]")
print(f"  Node 6 (before ReLU): {hidden_int8[6, :8]}")

# Layer 1: ReLU
print("\n--- Layer 1 ReLU ---")
hidden_int8 = relu_int8(hidden_int8)
print(f"  After ReLU: range=[{hidden_int8.min()}, {hidden_int8.max()}]")
print(f"  Node 6: {hidden_int8[6, :8]}")

# Layer 2: Aggregate
print("\n--- Layer 2 Aggregation (PO2) ---")
print(f"  Using shift={BETA2_SHIFT} (replaces beta2_fp={beta2_fp_orig} → {beta2_po2})")
agg2_int8 = aggregate_int_po2(hidden_int8, adj_matrix_int16, BETA2_SHIFT, M)
print(f"  Aggregation output: {agg2_int8.shape}")
print(f"  Range: [{agg2_int8.min()}, {agg2_int8.max()}]")
print(f"  Node 6: {agg2_int8[6, :8]}")

# Layer 2: Linear
print("\n--- Layer 2 Linear (PO2) ---")
print(f"  Using shift={EFF_SCALE2_SHIFT} (replaces eff_scale2_fp={eff_scale2_fp_orig} → {eff_scale2_po2})")
output_int8 = linear_int_po2(agg2_int8, weights2_int8, bias2_int32, EFF_SCALE2_SHIFT, M)
print(f"  Final output: {output_int8.shape}")
print(f"  Range: [{output_int8.min()}, {output_int8.max()}]")
print(f"  Node 6: {output_int8[6]}")

# ============================================================================
# Compute predictions
# ============================================================================

print("\n" + "="*80)
print("PREDICTIONS")
print("="*80)

predictions = np.argmax(output_int8, axis=1)
print(f"\nPredicted classes: {predictions}")
print(f"Output logits (node 6): {output_int8[6]}")

# ============================================================================
# Save test vectors
# ============================================================================

print("\n" + "="*80)
print("SAVING TEST VECTORS")
print("="*80)

# Save PO2 reference output
np.savetxt(OUTPUT_DIR / "network_output_int8_po2_reference.txt", output_int8, fmt='%d')
print(f"✓ Saved: {OUTPUT_DIR / 'network_output_int8_po2_reference.txt'}")

# Save intermediate outputs for debugging
np.savetxt(OUTPUT_DIR / "agg1_int8_po2.txt", agg1_int8, fmt='%d')
np.savetxt(OUTPUT_DIR / "hidden_int8_po2.txt", hidden_int8, fmt='%d')
np.savetxt(OUTPUT_DIR / "agg2_int8_po2.txt", agg2_int8, fmt='%d')
print(f"✓ Saved intermediate outputs")

# ============================================================================
# Compare against regular INT8
# ============================================================================

print("\n" + "="*80)
print("COMPARISON: PO2 vs Regular INT8")
print("="*80)

# Load regular INT8 reference
int8_ref = np.loadtxt(Path("../build/test_vectors_ptq_int8/network_output_int8_reference.txt"), dtype=np.int8)

diff = output_int8.astype(np.int32) - int8_ref.astype(np.int32)
max_error = np.abs(diff).max()
mean_error = np.abs(diff).mean()
total_diffs = np.count_nonzero(diff)

print(f"\nError metrics (PO2 vs Regular INT8):")
print(f"  Max error: {max_error} LSB")
print(f"  Mean error: {mean_error:.2f} LSB")
print(f"  Total differences: {total_diffs}/{diff.size}")

print(f"\nSample comparison (node 6):")
print(f"  PO2:         {output_int8[6]}")
print(f"  Regular INT8: {int8_ref[6]}")
print(f"  Difference:   {diff[6]}")

# Check if predictions match
po2_pred = np.argmax(output_int8, axis=1)
int8_pred = np.argmax(int8_ref, axis=1)
pred_match = np.sum(po2_pred == int8_pred)

print(f"\nPrediction agreement:")
print(f"  Matching predictions: {pred_match}/{len(po2_pred)} ({pred_match/len(po2_pred)*100:.1f}%)")
print(f"  PO2 predictions:  {po2_pred}")
print(f"  INT8 predictions: {int8_pred}")

print("\n" + "="*80)
print("✅ PO2 TEST VECTOR GENERATION COMPLETE")
print("="*80)
print(f"\nGenerated files in {OUTPUT_DIR}:")
print("  - network_output_int8_po2_reference.txt (for HLS validation)")
print("  - po2_config.json (shift values and configuration)")
print("  - agg1_int8_po2.txt, hidden_int8_po2.txt, agg2_int8_po2.txt (debug)")
