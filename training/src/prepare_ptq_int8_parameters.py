"""
Prepare Integer-Only PTQ Parameters for HLS

This script converts the existing PTQ parameters to integer-only format:
1. Convert biases from float to INT32 (accumulator domain)
2. Quantize adjacency matrix to INT16 fixed-point
3. Compute fixed-point scale factors (eff_scale_fp, beta_fp)

Input: build/weights_ptq_float/ (existing PTQ with float scales)
Output: build/weights_ptq_int8/ (integer-only parameters)

Usage:
  python prepare_ptq_int8_parameters.py          # Default M=20
  python prepare_ptq_int8_parameters.py --m24    # Use M=24 (recommended for exact match)
"""

import json
import numpy as np
import torch
import argparse
from pathlib import Path

# Get project root (parent of src directory)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ============================================================================
# Configuration
# ============================================================================

parser = argparse.ArgumentParser(description='Generate INT8-only PTQ parameters')
parser.add_argument('--m24', action='store_true', 
                    help='Use M=24 (exact match with PTQ-Float). Default is M=20. DEPRECATED: use --m-bits instead')
parser.add_argument('--m-bits', type=int, default=None,
                    help='Fixed-point fractional bits for data/weights (e.g., 16, 20, 24)')
parser.add_argument('--in-channels', type=int, default=16,
                    help='Input feature dimension after projection (default: 16)')
parser.add_argument('--hidden-channels', type=int, default=24,
                    help='Hidden layer dimension (default: 24)')
parser.add_argument('--output-dir', type=str, default=None,
                    help='Output directory for INT8 parameters (default: build/weights_ptq_int8)')
args = parser.parse_args()

# Architecture parameters
IN_CHANNELS = args.in_channels
HIDDEN_CHANNELS = args.hidden_channels
OUT_CHANNELS = 7  # Fixed for Cora

# Fixed-point precision parameters
# Determine M: priority is --m-bits, then --m24 flag, then default 20
if args.m_bits is not None:
    M = args.m_bits
elif args.m24:
    M = 24
else:
    M = 20
K = 4096  # Fixed-point scale for adjacency matrix (2^12)
K_BITS = 12  # log2(K)

# Paths (using absolute paths from PROJECT_ROOT)
FLOAT_WEIGHTS_DIR = PROJECT_ROOT / "build/weights_float"

# If output-dir is provided, use it for both reading PTQ and writing INT8 params
if args.output_dir:
    OUTPUT_DIR = Path(args.output_dir)
    QUANTIZED_DIR = OUTPUT_DIR  # Read PTQ from same location
else:
    # Legacy: read from shared PTQ float, write to shared INT8
    QUANTIZED_DIR = PROJECT_ROOT / "build/weights_ptq_float"
    OUTPUT_DIR = PROJECT_ROOT / "build/weights_ptq_int8"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("="*80)
print("INTEGER-ONLY PTQ PARAMETER GENERATION")
print("="*80)
print(f"\nConfiguration:")
print(f"  Architecture: {IN_CHANNELS} → {HIDDEN_CHANNELS} → {OUT_CHANNELS}")
print(f"  M (scale factor fractional bits): {M}")
print(f"  K (adjacency fixed-point scale):  {K} (2^{K_BITS})")
print(f"  Float weights dir: {FLOAT_WEIGHTS_DIR}")
print(f"  Quantized dir:     {QUANTIZED_DIR}")
print(f"  Output dir:        {OUTPUT_DIR}")

# ============================================================================
# Load existing PTQ parameters
# ============================================================================

print("\n" + "-"*80)
print("Step 1: Load existing PTQ parameters")
print("-"*80)

# Check if float weights exist
if not FLOAT_WEIGHTS_DIR.exists():
    print(f"\n❌ ERROR: Float weights directory not found: {FLOAT_WEIGHTS_DIR}")
    print(f"\nPlease run training first to generate float weights:")
    print(f"  cd ../src")
    print(f"  python3 train.py")
    print(f"\nThis will create the reduced_graphsage_no_root model and export float weights.")
    exit(1)

# Load quantization scales
with open(QUANTIZED_DIR / "quant_params.json", 'r') as f:
    quant_params = json.load(f)

scales = quant_params['scales']
zero_points = quant_params['zero_points']

print(f"\nLoaded scales:")
for name, scale in scales.items():
    print(f"  {name}: {scale}")

# Extract activation and weight scales
# Activation scales are inferred from the quantization scheme.
# In the current PTQ:
#   scale_in = 0.004860 (from test vectors)
#   scale_hidden = 0.1
#   scale_out = 0.1
#   scale_w1 = scales['conv1.lin_l.weight']
#   scale_w2 = scales['conv2.lin_l.weight']

# Load activation scales from test vectors metadata
# (These should have been saved during PTQ generation)
test_vectors_dir = PROJECT_ROOT / "build/test_vectors_ptq_float"
with open(test_vectors_dir / "scales.txt", 'r') as f:
    lines = f.readlines()
    
activation_scales = {}
for line in lines:
    if ':' in line:
        name, value = line.split(':')
        name = name.strip()
        value = float(value.strip())
        activation_scales[name] = value

scale_in = activation_scales['scale_in']
scale_hidden = activation_scales['scale_hidden']
scale_out = activation_scales['scale_out']
scale_w1 = activation_scales['scale_w1']  # Also get from scales.txt
scale_w2 = activation_scales['scale_w2']  # Also get from scales.txt

print(f"\nActivation scales:")
print(f"  scale_in:     {scale_in}")
print(f"  scale_hidden: {scale_hidden}")
print(f"  scale_out:    {scale_out}")

print(f"\nWeight scales:")
print(f"  scale_w1: {scale_w1}")
print(f"  scale_w2: {scale_w2}")

# ============================================================================
# Step 2: Convert biases to INT32 (accumulator domain)
# ============================================================================

print("\n" + "-"*80)
print("Step 2: Convert biases to INT32 accumulator domain")
print("-"*80)

# Load FLOAT biases from the original trained model
print(f"\nLoading float biases from {FLOAT_WEIGHTS_DIR}/")

def load_float_weight(filename):
    """Load a float weight file and reshape according to .shape file"""
    # Prefer the original float export. Files in QUANTIZED_DIR contain INT8
    # values and must not be interpreted as float biases.
    float_path = FLOAT_WEIGHTS_DIR / filename
    if float_path.exists():
        data = np.loadtxt(float_path, dtype=np.float32)
        shape_file = FLOAT_WEIGHTS_DIR / f"{filename}.shape"
        if shape_file.exists():
            with open(shape_file, 'r') as f:
                shape = tuple(map(int, f.read().strip().split(',')))
            return data.reshape(shape) if len(shape) > 1 else data
        return data

    # Per-architecture exports may keep float aliases without _no_root.
    alias_path = FLOAT_WEIGHTS_DIR / filename.replace('_no_root', '')
    if alias_path.exists():
        data = np.loadtxt(alias_path, dtype=np.float32)
        shape_file = FLOAT_WEIGHTS_DIR / f"{filename.replace('_no_root', '')}.shape"
        if shape_file.exists():
            with open(shape_file, 'r') as f:
                shape = tuple(map(int, f.read().strip().split(',')))
            return data.reshape(shape) if len(shape) > 1 else data
        return data

    raise FileNotFoundError(f"Could not find float parameter {filename} in {FLOAT_WEIGHTS_DIR}")

bias1_float = load_float_weight('conv1_lin_l_bias_no_root.txt')
bias2_float = load_float_weight('conv2_lin_l_bias_no_root.txt')

print(f"\nLoaded float biases:")
print(f"  Layer 1: shape={bias1_float.shape}, range=[{bias1_float.min():.6f}, {bias1_float.max():.6f}]")
print(f"  Layer 2: shape={bias2_float.shape}, range=[{bias2_float.min():.6f}, {bias2_float.max():.6f}]")

# Convert to accumulator domain
# b_int32 = round(b_float / (scale_act * scale_w))
# For layer 1: scale_act = scale_hidden (aggregation output scale)
# For layer 2: scale_act = scale_hidden

bias1_int32 = np.round(bias1_float / (scale_hidden * scale_w1)).astype(np.int32)
bias2_int32 = np.round(bias2_float / (scale_hidden * scale_w2)).astype(np.int32)

print(f"\nConverted to INT32:")
print(f"  Layer 1: shape={bias1_int32.shape}, range=[{bias1_int32.min()}, {bias1_int32.max()}]")
print(f"  Layer 2: shape={bias2_int32.shape}, range=[{bias2_int32.min()}, {bias2_int32.max()}]")

# Save INT32 biases
np.savetxt(OUTPUT_DIR / "bias_layer1_int32.txt", bias1_int32, fmt='%d')
np.savetxt(OUTPUT_DIR / "bias_layer2_int32.txt", bias2_int32, fmt='%d')

print(f"\n✓ Saved INT32 biases to {OUTPUT_DIR}")

# ============================================================================
# Step 3: Quantize adjacency matrix to INT16 fixed-point
# ============================================================================

print("\n" + "-"*80)
print("Step 3: Quantize adjacency matrix to INT16 fixed-point")
print("-"*80)

# Load float adjacency matrix
adj_matrix_float = np.loadtxt(test_vectors_dir / "adj_matrix.txt", dtype=np.float32)

print(f"\nLoaded adjacency matrix:")
print(f"  Shape: {adj_matrix_float.shape}")
print(f"  Float range: [{adj_matrix_float.min():.6f}, {adj_matrix_float.max():.6f}]")
print(f"  Non-zero entries: {np.count_nonzero(adj_matrix_float)}")

# Convert to fixed-point INT16
# A_fp[i][j] = round(A[i][j] * K)
adj_matrix_int16 = np.round(adj_matrix_float * K).astype(np.int16)

print(f"\nConverted to INT16 fixed-point (K={K}):")
print(f"  INT16 range: [{adj_matrix_int16.min()}, {adj_matrix_int16.max()}]")
print(f"  Non-zero entries: {np.count_nonzero(adj_matrix_int16)}")

# Verify reconstruction accuracy
adj_reconstructed = adj_matrix_int16.astype(np.float32) / K
max_error = np.abs(adj_matrix_float - adj_reconstructed).max()
print(f"  Max reconstruction error: {max_error:.8f}")

# Save INT16 adjacency
np.savetxt(OUTPUT_DIR / "adj_matrix_int16.txt", adj_matrix_int16, fmt='%d')

print(f"\n✓ Saved INT16 adjacency matrix to {OUTPUT_DIR}")

# ============================================================================
# Step 4: Compute fixed-point scale factors
# ============================================================================

print("\n" + "-"*80)
print("Step 4: Compute fixed-point scale factors")
print("-"*80)

# Layer 1 linear: eff_scale1 = (scale_hidden * scale_w1) / scale_hidden
eff_scale1 = (scale_hidden * scale_w1) / scale_hidden
eff_scale1_fp = int(round(eff_scale1 * (2 ** M)))

print(f"\nLayer 1 Linear:")
print(f"  eff_scale1 = (scale_hidden * scale_w1) / scale_hidden")
print(f"             = ({scale_hidden} * {scale_w1}) / {scale_hidden}")
print(f"             = {eff_scale1}")
print(f"  eff_scale1_fp = round({eff_scale1} * 2^{M}) = {eff_scale1_fp}")

# Layer 2 linear: eff_scale2 = (scale_hidden * scale_w2) / scale_out
eff_scale2 = (scale_hidden * scale_w2) / scale_out
eff_scale2_fp = int(round(eff_scale2 * (2 ** M)))

print(f"\nLayer 2 Linear:")
print(f"  eff_scale2 = (scale_hidden * scale_w2) / scale_out")
print(f"             = ({scale_hidden} * {scale_w2}) / {scale_out}")
print(f"             = {eff_scale2}")
print(f"  eff_scale2_fp = round({eff_scale2} * 2^{M}) = {eff_scale2_fp}")

# Aggregation 1 (input → hidden): beta1 = scale_in / (K * scale_hidden)
beta1 = scale_in / (K * scale_hidden)
beta1_fp = int(round(beta1 * (2 ** M)))

print(f"\nAggregation 1 (input → hidden):")
print(f"  beta1 = scale_in / (K * scale_hidden)")
print(f"        = {scale_in} / ({K} * {scale_hidden})")
print(f"        = {beta1}")
print(f"  beta1_fp = round({beta1} * 2^{M}) = {beta1_fp}")

# Aggregation 2 (hidden → hidden): beta2 = scale_hidden / (K * scale_hidden) = 1/K
beta2 = scale_hidden / (K * scale_hidden)
beta2_fp = int(round(beta2 * (2 ** M)))

print(f"\nAggregation 2 (hidden → hidden):")
print(f"  beta2 = scale_hidden / (K * scale_hidden)")
print(f"        = {scale_hidden} / ({K} * {scale_hidden})")
print(f"        = {beta2} = 1/K")
print(f"  beta2_fp = round({beta2} * 2^{M}) = {beta2_fp}")

# ============================================================================
# Step 5: Save all parameters to JSON
# ============================================================================

print("\n" + "-"*80)
print("Step 5: Save integer-only parameters")
print("-"*80)

int8_params = {
    "fixed_point_config": {
        "M": M,  # Fractional bits for scale factors
        "K": K,  # Adjacency fixed-point scale
        "K_BITS": K_BITS  # log2(K)
    },
    "original_float_scales": {
        "scale_in": float(scale_in),
        "scale_hidden": float(scale_hidden),
        "scale_out": float(scale_out),
        "scale_w1": float(scale_w1),
        "scale_w2": float(scale_w2)
    },
    "fixed_point_scales": {
        "eff_scale1_fp": int(eff_scale1_fp),
        "eff_scale2_fp": int(eff_scale2_fp),
        "beta1_fp": int(beta1_fp),
        "beta2_fp": int(beta2_fp)
    },
    "derived_float_values": {
        "eff_scale1": float(eff_scale1),
        "eff_scale2": float(eff_scale2),
        "beta1": float(beta1),
        "beta2": float(beta2)
    },
    "file_info": {
        "bias_layer1": "bias_layer1_int32.txt (INT32)",
        "bias_layer2": "bias_layer2_int32.txt (INT32)",
        "adj_matrix": "adj_matrix_int16.txt (INT16)",
        "weights": "Use existing INT8 weight files from weights_ptq_float/"
    }
}

with open(OUTPUT_DIR / "int8_params.json", 'w') as f:
    json.dump(int8_params, f, indent=2)

print(f"\n✓ Saved all parameters to {OUTPUT_DIR}/int8_params.json")

# ============================================================================
# Summary
# ============================================================================

print("\n" + "="*80)
print("SUMMARY")
print("="*80)

print(f"\nGenerated files in {OUTPUT_DIR}:")
print(f"  ✓ bias_layer1_int32.txt - Layer 1 bias (INT32 × {len(bias1_int32)})")
print(f"  ✓ bias_layer2_int32.txt - Layer 2 bias (INT32 × {len(bias2_int32)})")
print(f"  ✓ adj_matrix_int16.txt  - Adjacency matrix (INT16 {adj_matrix_int16.shape})")
print(f"  ✓ int8_params.json      - All integer-only parameters")

print(f"\nFixed-point parameters (M={M}, K={K}):")
print(f"  eff_scale1_fp = {eff_scale1_fp}")
print(f"  eff_scale2_fp = {eff_scale2_fp}")
print(f"  beta1_fp      = {beta1_fp}")
print(f"  beta2_fp      = {beta2_fp}")

print(f"\nNext steps:")
print(f"  1. Create Python integer emulator using these parameters")
print(f"  2. Generate integer-only test vectors (validate against PTQ)")
print(f"  3. Create integer-only HLS header")
print(f"  4. Implement integer-only HLS functions")
print(f"  5. Validate HLS vs Python integer emulator (bit-exact match)")

print(f"\nWorkflow summary:")
print(f"  Float model → PTQ (scales) → INT32 biases + INT16 adjacency + scale factors → Integer HLS")

print("\n" + "="*80)
