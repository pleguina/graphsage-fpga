"""
Quantization utilities for FPGA implementation.
Implements INT8 quantization for weights and activations.
"""

import torch
import numpy as np
import json
from pathlib import Path
from model_base import ReducedGraphSAGE
from config import get_config

# Get project root (parent of src directory)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()


class QuantizationParams:
    """Store quantization parameters (scale and zero_point)."""

    def __init__(self):
        self.scales = {}
        self.zero_points = {}

    def add_param(self, name, scale, zero_point):
        self.scales[name] = float(scale)
        self.zero_points[name] = int(zero_point)

    def save(self, filepath):
        data = {
            'scales': self.scales,
            'zero_points': self.zero_points
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)


def quantize_tensor(tensor, num_bits=8, symmetric=True, power_of_two_scale=False):
    """
    Quantize a tensor to int representation.

    Args:
        tensor: Input tensor to quantize
        num_bits: Number of bits for quantization (default 8 for int8)
        symmetric: Use symmetric quantization (zero_point=0)
        power_of_two_scale: If True, round scale to nearest power of 2.
                           This enables bit-shift instead of multiply in HLS!
                           Uses ceil(log2) to avoid clipping.

    Returns:
        quantized: Quantized tensor (int representation)
        scale: Quantization scale (power-of-two if power_of_two_scale=True)
        zero_point: Quantization zero point
    
    Hardware Implications:
        - power_of_two_scale=False: Requires multiplier for dequantization
        - power_of_two_scale=True:  Only needs bit-shift (saves DSP resources!)
          
        Example with scale=0.015625 (= 2^-6):
          dequant = int8_val >> 6  (just a bit shift!)
    """
    import math
    
    if symmetric:
        # Symmetric quantization: zero_point = 0
        max_val = max(abs(tensor.min().item()), abs(tensor.max().item()))
        qmax = 2 ** (num_bits - 1) - 1  # 127 for int8, 7 for int4, etc.
        
        if max_val == 0:
            scale = 1.0
        else:
            scale = max_val / qmax
            
            if power_of_two_scale:
                # Round to power of two (use ceil to avoid clipping)
                log2_scale = math.log2(scale)
                scale = 2 ** math.ceil(log2_scale)
        
        zero_point = 0
    else:
        # Asymmetric quantization
        min_val = tensor.min().item()
        max_val = tensor.max().item()
        qmin = -(2 ** (num_bits - 1))  # -128 for int8
        qmax = 2 ** (num_bits - 1) - 1  # 127 for int8
        scale = (max_val - min_val) / (qmax - qmin) if max_val != min_val else 1.0
        
        if power_of_two_scale:
            log2_scale = math.log2(scale) if scale > 0 else 0
            scale = 2 ** math.ceil(log2_scale)
        
        zero_point = qmin - int(min_val / scale)

    # Quantize
    qmin = -(2 ** (num_bits - 1))
    qmax = 2 ** (num_bits - 1) - 1
    
    quantized = torch.clamp(
        torch.round(tensor / scale) + zero_point,
        qmin,
        qmax
    )

    # Choose appropriate dtype
    if num_bits <= 8:
        quantized = quantized.to(torch.int8)
    else:
        quantized = quantized.to(torch.int16)

    return quantized, scale, zero_point


def dequantize_tensor(quantized, scale, zero_point):
    """Dequantize a tensor back to float representation."""
    return (quantized.to(torch.float32) - zero_point) * scale


def quantize_model_weights(model, num_bits=8):
    """
    Quantize all weights in the model.

    Args:
        model: PyTorch model to quantize
        num_bits: Number of bits for quantization

    Returns:
        quantized_weights: Dictionary of quantized weights
        quant_params: Quantization parameters
    """
    quantized_weights = {}
    quant_params = QuantizationParams()

    model.eval()

    for name, param in model.named_parameters():
        if len(param.shape) == 0:  # Skip scalar parameters
            continue

        # Quantize weight
        quantized, scale, zero_point = quantize_tensor(
            param.data, num_bits=num_bits, symmetric=True
        )

        quantized_weights[name] = quantized.numpy()
        quant_params.add_param(name, scale, zero_point)

        print(f"Quantized {name}: shape={param.shape}, scale={scale:.6f}")

    return quantized_weights, quant_params


def save_quantized_weights(quantized_weights, quant_params, output_dir='../build/quantized'):
    """Save quantized weights and parameters to files."""
    import os
    os.makedirs(output_dir, exist_ok=True)

    # Save each weight as separate file
    for name, weight in quantized_weights.items():
        # Replace dots with underscores for filename
        filename = name.replace('.', '_') + '.txt'
        np.savetxt(f'{output_dir}/{filename}', weight.flatten(), fmt='%d')

        # Also save shape info
        with open(f'{output_dir}/{filename}.shape', 'w') as f:
            f.write(','.join(map(str, weight.shape)))

    # Save quantization parameters
    quant_params.save(f'{output_dir}/quant_params.json')

    print(f"\nQuantized weights saved to {output_dir}/")


def export_weights_as_c_header(quantized_weights, quant_params, header_file='../build/hls/weights.h', model_dims=None):
    """Export quantized weights as C/C++ header file for HLS."""
    import os
    os.makedirs(os.path.dirname(header_file), exist_ok=True)

    with open(header_file, 'w') as f:
        f.write("// Auto-generated quantized weights for FPGA implementation\n")
        f.write("#ifndef WEIGHTS_H\n")
        f.write("#define WEIGHTS_H\n\n")
        f.write("#include <stdint.h>\n\n")

        # Write model dimensions if provided
        if model_dims:
            f.write("// Model architecture dimensions\n")
            f.write(f"#define MODEL_IN_FEATURES {model_dims['in_features']}\n")
            f.write(f"#define MODEL_HIDDEN_FEATURES {model_dims['hidden_features']}\n")
            f.write(f"#define MODEL_OUT_FEATURES {model_dims['out_features']}\n")
            if 'num_nodes' in model_dims:
                f.write(f"#define MODEL_NUM_NODES {model_dims['num_nodes']}\n")
            f.write("\n")

        for name, weight in quantized_weights.items():
            # Create valid C identifier
            c_name = name.replace('.', '_').upper()

            # Write array
            f.write(f"// {name}\n")
            f.write(f"const int8_t {c_name}[{weight.size}] = {{\n")

            # Write values (16 per line)
            flat_weight = weight.flatten()
            for i in range(0, len(flat_weight), 16):
                chunk = flat_weight[i:i+16]
                f.write("    " + ", ".join(f"{int(x):4d}" for x in chunk))
                if i + 16 < len(flat_weight):
                    f.write(",")
                f.write("\n")

            f.write("};\n\n")

            # Write shape constants
            if len(weight.shape) == 2:
                f.write(f"const int {c_name}_ROWS = {weight.shape[0]};\n")
                f.write(f"const int {c_name}_COLS = {weight.shape[1]};\n\n")

        # Write scales as float constants
        f.write("// Quantization scales\n")
        for name, scale in quant_params.scales.items():
            c_name = name.replace('.', '_').upper()
            f.write(f"const float {c_name}_SCALE = {scale}f;\n")

        f.write("\n#endif // WEIGHTS_H\n")

    print(f"\nC header file saved to {header_file}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Quantize GraphSAGE model')
    parser.add_argument('--use-root-weight', action='store_true', 
                       help='Use model with root_weight=True (default is False for HLS)')
    parser.add_argument('--in-channels', type=int, default=16,
                       help='Input feature dimension after projection (default: 16)')
    parser.add_argument('--hidden-channels', type=int, default=24,
                       help='Hidden layer dimension (default: 24)')
    parser.add_argument('--output-dir', type=str, default=None,
                       help='Output directory for quantized weights (default: build/weights_ptq_float[_with_root])')
    args = parser.parse_args()
    
    root_weight = args.use_root_weight
    in_channels = args.in_channels
    hidden_channels = args.hidden_channels
    arch_key = f"{in_channels}x{hidden_channels}"
    
    suffix = "" if root_weight else "_no_root"
    model_path = PROJECT_ROOT / 'build/models' / f'reduced_graphsage{suffix}_{arch_key}_best.pth'
    
    print(f"Using model: {model_path}")
    print(f"Architecture: {in_channels} → {hidden_channels} → 7")
    print(f"root_weight = {root_weight}")
    if not root_weight:
        print("NOTE: This is the HLS-compatible version (simpler formula)")
    
    # Load configuration (for num_features only)
    cfg = get_config()

    # Load reduced model with specified architecture
    model = ReducedGraphSAGE(
        in_channels=cfg.num_features,
        in_channels_reduced=in_channels,
        hidden_channels=hidden_channels,
        out_channels=cfg.num_classes,
        dropout=cfg.reduced_dropout,
        use_projection=True,
        root_weight=root_weight
    )

    print(f"📋 Architecture: {in_channels} → {hidden_channels} → {cfg.num_classes}")

    # Load trained weights
    try:
        checkpoint = torch.load(model_path)
        model.load_state_dict(checkpoint['model_state_dict'])
        print(f"Loaded trained model from {model_path}")
    except Exception as e:
        print(f"Warning: Could not load trained model: {e}")
        print("Using random weights.")

    # Quantize model
    print("\nQuantizing model to INT8...")
    quantized_weights, quant_params = quantize_model_weights(model, num_bits=8)

    # Save quantized weights with new naming convention
    # Determine output directory
    if args.output_dir:
        output_dir = args.output_dir
    elif root_weight:
        output_dir = str(PROJECT_ROOT / 'build/weights_ptq_float_with_root')
    else:
        output_dir = str(PROJECT_ROOT / 'build/weights_ptq_float')
    save_quantized_weights(quantized_weights, quant_params, output_dir=output_dir)

    # Prepare model dimensions
    model_dims = {
        'in_features': in_channels,
        'hidden_features': hidden_channels,
        'out_features': 7,
        'num_nodes': 32
    }

    # Export as C header with dimensions
    header_path = str(PROJECT_ROOT / 'build/hls' / f'weights{suffix}.h')
    export_weights_as_c_header(quantized_weights, quant_params, 
                               header_file=header_path, model_dims=model_dims)

    print("\nQuantization complete!")
    print(f"Output directory: {output_dir}")
    print(f"C header: {header_path}")
