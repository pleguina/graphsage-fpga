"""
Generate PTQ test vectors for HLS validation using QUANTIZED forward pass.
Unlike generate_test_vectors.py which runs float model and quantizes output,
this does true quantized inference matching HLS PTQ implementation.

Options:
  --hw-round: Use hardware-style rounding (round half up) instead of Python's
              banker's rounding. This makes PTQ-float match INT8-only better.
"""

import torch
import numpy as np
import os
import sys
from pathlib import Path
import argparse

# Set random seed for reproducibility
torch.manual_seed(42)
np.random.seed(42)

# Get project root (parent of tests directory)
PROJECT_ROOT = Path(os.path.dirname(__file__)).parent.resolve()

# Add src to path
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from model_base import ReducedGraphSAGE
from quantization_ptq import quantize_tensor
from subgraph_extraction import extract_fixed_subgraph
from torch_geometric.datasets import Planetoid
from torch_geometric.transforms import NormalizeFeatures

# Global flag for rounding mode
USE_HW_ROUND = False


def hw_round(x):
    """Hardware-style rounding: round half up (for positive), round half away from zero."""
    if isinstance(x, (torch.Tensor, np.ndarray)):
        # Vectorized version
        if isinstance(x, torch.Tensor):
            return torch.where(x >= 0, 
                             torch.floor(x + 0.5), 
                             torch.ceil(x - 0.5))
        else:
            return np.where(x >= 0, 
                          np.floor(x + 0.5), 
                          np.ceil(x - 0.5))
    else:
        # Scalar version
        if x >= 0:
            return int(x + 0.5)
        else:
            return -int(-x + 0.5)


def smart_round(x):
    """Round using either Python round or HW round based on global flag."""
    if USE_HW_ROUND:
        return hw_round(x)
    else:
        if isinstance(x, torch.Tensor):
            return torch.round(x)
        elif isinstance(x, np.ndarray):
            return np.round(x)
        else:
            return round(x)


def quantized_aggregate(x_int8, adj_matrix, scale_in, scale_hidden):
    """Perform quantized aggregation like HLS"""
    # Dequantize to float
    x_float = x_int8.float() * scale_in
    
    # Aggregate in float using adjacency matrix
    adj_tensor = torch.from_numpy(adj_matrix).float()
    agg_float = torch.matmul(adj_tensor, x_float)
    
    # Quantize to hidden scale using appropriate rounding
    agg_int8 = smart_round(agg_float / scale_hidden).clamp(-128, 127).to(torch.int8)
    
    return agg_int8


def quantized_linear(x_int8, weight_int8, bias_int32, scale_in, scale_w, scale_out):
    """Perform quantized linear transformation like HLS"""
    # Compute in int32
    acc_int32 = torch.mm(x_int8.to(torch.int32), weight_int8.t().to(torch.int32)) + bias_int32
    
    # Requantize: acc_int32 * (scale_in * scale_w) / scale_out
    scale_factor = (scale_in * scale_w) / scale_out
    out_int8 = smart_round(acc_int32.float() * scale_factor).clamp(-128, 127).to(torch.int8)
    
    return out_int8


def save_matrix(matrix, filename):
    """Save matrix to text file."""
    np.savetxt(filename, matrix, fmt='%.6f')
    print(f"Saved {filename}")


def save_int_matrix(matrix, filename):
    """Save integer matrix to text file."""
    np.savetxt(filename, matrix, fmt='%d')
    print(f"Saved {filename}")


def generate_test_vectors_for_layer(model, subgraph_data, output_dir):
    """
    Generate test vectors for a single GraphSAGE layer.

    Args:
        model: Trained model
        subgraph_data: Subgraph data dictionary
        output_dir: Output directory for test vectors
    """
    os.makedirs(output_dir, exist_ok=True)

    # Get subgraph adjacency and features
    adj_matrix = subgraph_data['adj_matrix']
    features = subgraph_data['x']

    # Quantize input features
    features_tensor = torch.from_numpy(features).float()
    features_quant, scale_in, _ = quantize_tensor(features_tensor, num_bits=8)
    features_quant_np = features_quant.numpy()

    # Save adjacency matrix (float, already normalized)
    save_matrix(adj_matrix, f'{output_dir}/adj_matrix.txt')

    # Save quantized input features
    save_int_matrix(features_quant_np, f'{output_dir}/input_features.txt')

    # Get first layer weights and bias
    conv1 = model.conv1
    weights = conv1.lin_l.weight.data  # [out_features, in_features]
    bias = conv1.lin_l.bias.data if conv1.lin_l.bias is not None else torch.zeros(weights.shape[0])

    # Quantize weights
    weights_quant, scale_weight, _ = quantize_tensor(weights, num_bits=8)
    weights_quant_np = weights_quant.numpy()

    # Quantize bias (stored as int32)
    bias_quant = (bias / (scale_in * scale_weight)).to(torch.int32)
    bias_quant_np = bias_quant.numpy()

    # Save weights and bias
    save_int_matrix(weights_quant_np, f'{output_dir}/weights.txt')
    save_int_matrix(bias_quant_np, f'{output_dir}/bias.txt')

    # Generate reference output using PyTorch
    model.eval()
    with torch.no_grad():
        # Create edge_index from subgraph
        edge_index = torch.from_numpy(subgraph_data['edge_index']).long()

        # Run through first layer only
        x = torch.from_numpy(features).float()
        out = model.conv1(x, edge_index)
        out = torch.relu(out)

        # Quantize output
        out_quant, scale_out, _ = quantize_tensor(out, num_bits=8)
        out_quant_np = out_quant.numpy()

    # Save reference output
    save_int_matrix(out_quant_np, f'{output_dir}/output_reference.txt')

    # Save scale factors
    with open(f'{output_dir}/scales.txt', 'w') as f:
        f.write(f"scale_in: {scale_in}\n")
        f.write(f"scale_weight: {scale_weight}\n")
        f.write(f"scale_out: {scale_out}\n")

    print(f"\nTest vectors for single layer generated in {output_dir}/")
    print(f"  Input shape: {features_quant_np.shape}")
    print(f"  Weights shape: {weights_quant_np.shape}")
    print(f"  Output shape: {out_quant_np.shape}")


def generate_test_vectors_for_network(model, subgraph_data, output_dir):
    """
    Generate test vectors for full two-layer network.

    Args:
        model: Trained model
        subgraph_data: Subgraph data dictionary
        output_dir: Output directory for test vectors
    """
    os.makedirs(output_dir, exist_ok=True)

    # Get subgraph adjacency and features
    adj_matrix = subgraph_data['adj_matrix']
    features = subgraph_data['x']

    # Process through projection layer if it exists
    if hasattr(model, 'projection') and model.use_projection:
        features_tensor = torch.from_numpy(features).float()
        with torch.no_grad():
            features_tensor = model.projection(features_tensor)
            features_tensor = torch.relu(features_tensor)
        features = features_tensor.numpy()

    # Quantize input features
    features_tensor = torch.from_numpy(features).float()
    features_quant, scale_in, _ = quantize_tensor(features_tensor, num_bits=8)
    features_quant_np = features_quant.numpy()

    # Save adjacency matrix
    save_matrix(adj_matrix, f'{output_dir}/adj_matrix.txt')
    
    # Save edge_index for exact reproduction
    edge_index_np = subgraph_data['edge_index']
    save_int_matrix(edge_index_np.T, f'{output_dir}/edge_index.txt')

    # Save quantized input features
    save_int_matrix(features_quant_np, f'{output_dir}/network_input.txt')

    # Layer 1: Get weights and bias
    conv1 = model.conv1
    weights1 = conv1.lin_l.weight.data
    bias1 = conv1.lin_l.bias.data if conv1.lin_l.bias is not None else torch.zeros(weights1.shape[0])

    # Quantize layer 1
    # NOTE: Layer 1 linear operates on aggregated activations at scale_hidden
    # Aggregation: scale_in -> scale_hidden
    # Linear input is at scale_hidden, so bias must be in (scale_hidden * scale_w1) domain
    scale_hidden = 0.1
    weights1_quant, scale_w1, _ = quantize_tensor(weights1, num_bits=8)
    bias1_quant = (bias1 / (scale_hidden * scale_w1)).to(torch.int32)

    save_int_matrix(weights1_quant.numpy(), f'{output_dir}/weights_layer1.txt')
    save_int_matrix(bias1_quant.numpy(), f'{output_dir}/bias_layer1.txt')

    # Layer 2: Get weights and bias
    conv2 = model.conv2
    weights2 = conv2.lin_l.weight.data
    bias2 = conv2.lin_l.bias.data if conv2.lin_l.bias is not None else torch.zeros(weights2.shape[0])

    # Quantize layer 2
    # NOTE: Layer 2 linear also operates on scale_hidden activations
    # (Layer 2 aggregation: scale_hidden -> scale_hidden)
    weights2_quant, scale_w2, _ = quantize_tensor(weights2, num_bits=8)
    bias2_quant = (bias2 / (scale_hidden * scale_w2)).to(torch.int32)

    save_int_matrix(weights2_quant.numpy(), f'{output_dir}/weights_layer2.txt')
    save_int_matrix(bias2_quant.numpy(), f'{output_dir}/bias_layer2.txt')

    # QUANTIZED FORWARD PASS (matches HLS PTQ implementation)
    print("\n" + "="*60)
    print("Running QUANTIZED forward pass (HLS-style)...")
    print("="*60)
    
    # Layer 1
    print("\nLayer 1:")
    print(f"  Input (INT8) shape: {features_quant.shape}")
    agg1 = quantized_aggregate(features_quant, adj_matrix, scale_in, scale_hidden)
    print(f"  Aggregated (INT8) shape: {agg1.shape}")
    print(f"  Agg1 sample [0,:5]: {agg1[0,:5].tolist()}")
    
    hidden = quantized_linear(agg1, weights1_quant, bias1_quant, scale_hidden, scale_w1, scale_hidden)
    print(f"  After linear (INT8) shape: {hidden.shape}")
    
    # ReLU
    hidden = torch.clamp(hidden, min=0)
    print(f"  After ReLU sample [0,:5]: {hidden[0,:5].tolist()}")
    
    # Layer 2
    print("\nLayer 2:")
    scale_out = 0.1
    agg2 = quantized_aggregate(hidden, adj_matrix, scale_hidden, scale_out)
    print(f"  Aggregated (INT8) shape: {agg2.shape}")
    
    output_quant = quantized_linear(agg2, weights2_quant, bias2_quant, scale_out, scale_w2, scale_out)
    print(f"  Output (INT8) shape: {output_quant.shape}")
    print(f"  Output sample [0,:]: {output_quant[0,:].tolist()}")

    # Save quantized output as reference
    save_int_matrix(output_quant.numpy(), f'{output_dir}/network_output_reference.txt')

    # Save scale factors
    with open(f'{output_dir}/scales.txt', 'w') as f:
        f.write(f"scale_in: {scale_in}\n")
        f.write(f"scale_w1: {scale_w1}\n")
        f.write(f"scale_w2: {scale_w2}\n")
        f.write(f"scale_hidden: {scale_hidden}\n")
        f.write(f"scale_out: {scale_out}\n")

    print(f"\nTest vectors for network generated in {output_dir}/")
    print(f"  Input shape: {features_quant_np.shape}")
    print(f"  Layer 1 weights shape: {weights1_quant.shape}")
    print(f"  Layer 2 weights shape: {weights2_quant.shape}")
    print(f"  Output shape: {output_quant.shape}")


def main():
    global USE_HW_ROUND
    
    parser = argparse.ArgumentParser(description='Generate PTQ test vectors')
    parser.add_argument('--hw-round', action='store_true',
                       help='Use hardware-style rounding (round half up) instead of Python banker\'s rounding')
    parser.add_argument('--in-channels', type=int, default=16,
                       help='Input feature dimension after projection (default: 16)')
    parser.add_argument('--hidden-channels', type=int, default=24,
                       help='Hidden layer dimension (default: 24)')
    args = parser.parse_args()
    
    # Set global rounding mode
    USE_HW_ROUND = args.hw_round
    
    in_channels = args.in_channels
    hidden_channels = args.hidden_channels
    arch_key = f"{in_channels}x{hidden_channels}"
    
    rounding_mode = "HW-ROUND (round half up)" if USE_HW_ROUND else "Python round (banker's rounding)"
    
    print("="*60)
    print("Generating PTQ Test Vectors (Quantized Forward Pass)")
    print(f"Architecture: {in_channels} → {hidden_channels} → 7")
    print(f"Rounding mode: {rounding_mode}")
    print("="*60)

    # Load Cora dataset
    print("\nLoading Cora dataset...")
    dataset = Planetoid(root=str(PROJECT_ROOT / 'data'), name='Cora', transform=NormalizeFeatures())
    data = dataset[0]

    # Extract subgraph with fixed center node for reproducibility
    print("Extracting subgraph...")
    subgraph_data = extract_fixed_subgraph(data, num_nodes=8, center_node=0, num_hops=2)

    # Load trained reduced model
    print("Loading trained model...")
    model = ReducedGraphSAGE(
        in_channels=dataset.num_features,
        in_channels_reduced=in_channels,
        hidden_channels=hidden_channels,
        out_channels=dataset.num_classes,
        dropout=0.5,
        use_projection=True,
        root_weight=False  # HLS-compatible version
    )

    model_path = PROJECT_ROOT / 'build/models' / f'reduced_graphsage_no_root_{arch_key}_best.pth'
    try:
        checkpoint = torch.load(model_path)
        model.load_state_dict(checkpoint['model_state_dict'])
        print(f"✓ Loaded trained model: {model_path}")
    except Exception as e:
        print(f"Error: Could not load trained model: {e}")
        sys.exit(1)

    # Generate test vectors
    output_dir = PROJECT_ROOT / 'build/test_vectors_ptq_float'

    print("\n" + "="*60)
    print("Generating PTQ test vectors with quantized forward pass...")
    print("="*60)
    generate_test_vectors_for_network(model, subgraph_data, str(output_dir))

    print("\n" + "="*60)
    print("PTQ test vector generation complete!")
    print("="*60)
    print(f"\nPTQ test vectors saved to: {output_dir}/")
    print(f"Rounding mode used: {rounding_mode}")


if __name__ == '__main__':
    main()
