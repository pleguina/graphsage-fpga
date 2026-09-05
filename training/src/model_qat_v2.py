"""
QAT v2: Corrected Quantization-Aware Training for GNN Message Passing Layers.

Design principles:
1. Quantize at linear layer boundaries only (not around aggregation)
2. Aggregation uses INT32 accumulator (matching FPGA behavior)
3. Initialize from pre-trained float model
4. Freeze observers after calibration, then fine-tune

FPGA correspondence:
- INT8 features loaded from memory
- INT8 weights loaded from memory
- Aggregation accumulates in INT32 (no quantization mid-operation)
- Requantize to INT8 only after linear transform completes
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from typing import Optional, Union, Tuple
import torch.ao.quantization as tq
from torch.ao.quantization.fake_quantize import FakeQuantize
from torch.ao.quantization.observer import (
    MovingAverageMinMaxObserver,
    MovingAveragePerChannelMinMaxObserver,
)


def make_activation_fake_quant(num_bits: int = 8) -> FakeQuantize:
    """
    Symmetric per-tensor fake quantizer for activations.
    
    For bit widths <= 8, we use the actual range.
    For bit widths > 8, we use qint8 range (PyTorch limitation).
    """
    if num_bits <= 8:
        qmin = -(2 ** (num_bits - 1))
        qmax = (2 ** (num_bits - 1)) - 1
    else:
        # PyTorch FakeQuantize is limited to qint8 for >8 bits.
        # Simulate by using full qint8 range (~8-bit behavior).
        # True >8-bit requires a custom implementation.
        qmin = -128
        qmax = 127
    
    return FakeQuantize(
        observer=MovingAverageMinMaxObserver,
        quant_min=qmin,
        quant_max=qmax,
        dtype=torch.qint8,
        qscheme=torch.per_tensor_symmetric,
        reduce_range=False,
    )


def make_weight_fake_quant(num_bits: int = 8, per_channel: bool = False) -> FakeQuantize:
    """
    Symmetric fake quantizer for weights. Per-tensor by default for simpler HLS.
    
    For bit widths <= 8, we use the actual range.
    For bit widths > 8, we use qint8 range (PyTorch limitation).
    """
    if num_bits <= 8:
        qmin = -(2 ** (num_bits - 1))
        qmax = (2 ** (num_bits - 1)) - 1
    else:
        qmin = -128
        qmax = 127
    
    if per_channel:
        return FakeQuantize(
            observer=MovingAveragePerChannelMinMaxObserver,
            quant_min=qmin,
            quant_max=qmax,
            dtype=torch.qint8,
            qscheme=torch.per_channel_symmetric,
            reduce_range=False,
            ch_axis=0,
        )
    else:
        return FakeQuantize(
            observer=MovingAverageMinMaxObserver,
            quant_min=qmin,
            quant_max=qmax,
            dtype=torch.qint8,
            qscheme=torch.per_tensor_symmetric,
            reduce_range=False,
        )


class QuantLinear(nn.Module):
    """
    Quantized Linear layer with fake quantization for QAT.
    
    Quantization points:
    - Input activations (fake quant)
    - Weights (fake quant)
    - Output: NOT quantized here (let caller decide)
    
    This matches HLS where:
    - q_in (INT8) * q_w (INT8) -> INT32 accumulator
    - Bias added in INT32
    - Requantization happens AFTER all accumulation
    """
    
    def __init__(
        self,
        in_features: int,
        out_features: int,
        bias: bool = True,
        num_bits: int = 8,
    ):
        super().__init__()
        
        self.linear = nn.Linear(in_features, out_features, bias=bias)
        
        # Fake quantizers
        self.input_fake_quant = make_activation_fake_quant(num_bits)
        self.weight_fake_quant = make_weight_fake_quant(num_bits, per_channel=False)
        
    def forward(self, x: Tensor) -> Tensor:
        # Quantize input activations
        x_q = self.input_fake_quant(x)
        
        # Quantize weights
        w_q = self.weight_fake_quant(self.linear.weight)
        
        # Linear transform (simulates INT32 accumulation)
        # Bias stays in float during QAT; converted to INT32 at export
        out = F.linear(x_q, w_q, self.linear.bias)
        
        return out


class SAGEConvQATv2(nn.Module):
    """
    Corrected QAT-enabled GraphSAGE layer for message passing.
    
    Key insight: In hardware, the aggregation happens in an INT32 accumulator.
    We don't need separate quantization before/after aggregation!
    
    Data flow (matches HLS):
    ┌─────────────────────────────────────────────────────────────────┐
    │  x_in (FLOAT during training, INT8 at inference)               │
    │    │                                                            │
    │    ▼                                                            │
    │  ┌──────────────────────────────────────────────────────────┐  │
    │  │ AGGREGATION (mean over neighbors)                        │  │
    │  │ - In HLS: INT8 * INT16(adj) -> INT32 accumulator         │  │
    │  │ - In QAT: Keep in FLOAT (simulates INT32 accumulator)    │  │
    │  │ - Division by degree: INT32 / INT16 -> INT32             │  │
    │  └──────────────────────────────────────────────────────────┘  │
    │    │                                                            │
    │    ▼                                                            │
    │  h_agg (FLOAT, represents INT32 accumulator result)            │
    │    │                                                            │
    │    ▼                                                            │
    │  ┌──────────────────────────────────────────────────────────┐  │
    │  │ QUANTIZED LINEAR (the only place we fake-quantize!)      │  │
    │  │ - Input fake-quant: simulates INT8 storage of h_agg      │  │
    │  │ - Weight fake-quant: simulates INT8 weights              │  │
    │  │ - Accumulation in FLOAT (simulates INT32)                │  │
    │  └──────────────────────────────────────────────────────────┘  │
    │    │                                                            │
    │    ▼                                                            │
    │  out (FLOAT, will be quantized when stored or fed to next)     │
    └─────────────────────────────────────────────────────────────────┘
    
    Args:
        in_channels: Input feature dimension
        out_channels: Output feature dimension
        root_weight: If True, add W_r @ x_self (not HLS-compatible)
        bias: If True, add bias term
        num_bits: Quantization bit width (default 8)
    """
    
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        root_weight: bool = False,
        bias: bool = True,
        num_bits: int = 8,
    ):
        super().__init__()
        
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.root_weight = root_weight
        self.num_bits = num_bits
        
        # Single quantized linear for neighbor aggregation path
        self.lin_neighbor = QuantLinear(in_channels, out_channels, bias=bias, num_bits=num_bits)
        
        # Optional root (self) connection - typically disabled for HLS
        if root_weight:
            self.lin_root = QuantLinear(in_channels, out_channels, bias=False, num_bits=num_bits)
        else:
            self.lin_root = None
        
        # Output quantization (simulates storing result back to INT8 memory)
        self.output_fake_quant = make_activation_fake_quant(num_bits)
    
    def forward(self, x: Tensor, edge_index: Tensor) -> Tensor:
        """
        Forward pass with minimal quantization points.
        
        Args:
            x: Node features [num_nodes, in_channels]
            edge_index: Edge connectivity [2, num_edges]
            
        Returns:
            out: Transformed features [num_nodes, out_channels]
        """
        num_nodes = x.size(0)
        row, col = edge_index  # row = source, col = target
        
        # =====================================================================
        # STEP 1: Mean Aggregation (no quantization)
        # HLS: accumulates in INT32, no precision loss
        # =====================================================================
        
        # Compute node degrees for mean aggregation
        degree = torch.zeros(num_nodes, device=x.device, dtype=x.dtype)
        degree.scatter_add_(0, col, torch.ones_like(col, dtype=x.dtype))
        degree = degree.clamp(min=1.0)  # Avoid division by zero
        
        # Aggregate neighbor features (scatter_add simulates INT32 accumulator)
        h_agg = torch.zeros(num_nodes, self.in_channels, device=x.device, dtype=x.dtype)
        h_agg.scatter_add_(0, col.unsqueeze(1).expand(-1, self.in_channels), x[row])
        
        # Mean: divide by degree (in HLS: INT32 / INT16 -> INT32)
        h_agg = h_agg / degree.unsqueeze(1)
        
        # =====================================================================
        # STEP 2: Quantized Linear Transform
        # Quantization precision is determined here for HLS
        # =====================================================================
        
        out = self.lin_neighbor(h_agg)
        
        # Optional root contribution (disabled for HLS by default)
        if self.root_weight and self.lin_root is not None:
            out = out + self.lin_root(x)
        
        # =====================================================================
        # STEP 3: Output Quantization (models INT8 memory write)
        # =====================================================================
        
        out = self.output_fake_quant(out)
        
        return out


class ReducedGraphSAGEQATv2(nn.Module):
    """
    Corrected QAT model for GraphSAGE with minimal quantization points.
    
    Architecture:
    - QuantLinear projection (1433 -> 16)
    - ReLU
    - SAGEConvQATv2 (16 -> 24)
    - ReLU + Dropout
    - SAGEConvQATv2 (24 -> 7)
    
    Total quantization points: 6 (vs 9 in broken v1)
    - projection.input_fake_quant
    - projection.weight_fake_quant  
    - conv1.lin_neighbor.input_fake_quant
    - conv1.lin_neighbor.weight_fake_quant
    - conv1.output_fake_quant
    - conv2.lin_neighbor.input_fake_quant
    - conv2.lin_neighbor.weight_fake_quant
    - conv2.output_fake_quant
    
    Note: Aggregation stays in FLOAT (simulating INT32 accumulator)
    """
    
    def __init__(
        self,
        in_channels: int,
        in_channels_reduced: int,
        hidden_channels: int,
        out_channels: int,
        dropout: float = 0.5,
        use_projection: bool = True,
        root_weight: bool = False,
        num_bits: int = 8,
    ):
        super().__init__()
        
        self.use_projection = use_projection
        self.root_weight = root_weight
        self.dropout = dropout
        self.num_bits = num_bits
        
        # Projection layer (optional)
        if use_projection:
            self.projection = QuantLinear(in_channels, in_channels_reduced, bias=True, num_bits=num_bits)
            self.projection_output_quant = make_activation_fake_quant(num_bits)
            conv_in = in_channels_reduced
        else:
            self.projection = None
            self.projection_output_quant = None
            conv_in = in_channels
        
        # GraphSAGE layers
        self.conv1 = SAGEConvQATv2(conv_in, hidden_channels, root_weight=root_weight, num_bits=num_bits)
        self.conv2 = SAGEConvQATv2(hidden_channels, out_channels, root_weight=root_weight, num_bits=num_bits)
    
    def forward(self, x: Tensor, edge_index: Tensor) -> Tensor:
        # Projection
        if self.use_projection and self.projection is not None:
            x = self.projection(x)
            x = F.relu(x)
            x = self.projection_output_quant(x)
        
        # Conv1
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)
        
        # Conv2 (no ReLU after final layer)
        x = self.conv2(x, edge_index)
        
        return x
    
    def enable_fake_quant(self):
        """Enable fake quantization for all FakeQuantize modules."""
        for module in self.modules():
            if isinstance(module, FakeQuantize):
                module.enable_fake_quant()
    
    def disable_fake_quant(self):
        """Disable fake quantization (run in float mode)."""
        for module in self.modules():
            if isinstance(module, FakeQuantize):
                module.disable_fake_quant()
    
    def enable_observer(self):
        """Enable observers to collect statistics."""
        for module in self.modules():
            if isinstance(module, FakeQuantize):
                module.enable_observer()
    
    def disable_observer(self):
        """Disable observers (freeze quantization parameters)."""
        for module in self.modules():
            if isinstance(module, FakeQuantize):
                module.disable_observer()
    
    def load_from_float_model(self, float_model):
        """
        Initialize weights from a trained float model.
        This is CRUCIAL for QAT to work properly!
        
        Args:
            float_model: Trained ReducedGraphSAGE model
        """
        with torch.no_grad():
            # Copy projection weights
            if self.use_projection and hasattr(float_model, 'projection'):
                self.projection.linear.weight.copy_(float_model.projection.weight)
                self.projection.linear.bias.copy_(float_model.projection.bias)
            
            # Copy conv1 weights
            if hasattr(float_model.conv1, 'lin_l'):
                self.conv1.lin_neighbor.linear.weight.copy_(float_model.conv1.lin_l.weight)
                self.conv1.lin_neighbor.linear.bias.copy_(float_model.conv1.lin_l.bias)
            if self.root_weight and self.conv1.lin_root is not None:
                self.conv1.lin_root.linear.weight.copy_(float_model.conv1.lin_r.weight)
            
            # Copy conv2 weights
            if hasattr(float_model.conv2, 'lin_l'):
                self.conv2.lin_neighbor.linear.weight.copy_(float_model.conv2.lin_l.weight)
                self.conv2.lin_neighbor.linear.bias.copy_(float_model.conv2.lin_l.bias)
            if self.root_weight and self.conv2.lin_root is not None:
                self.conv2.lin_root.linear.weight.copy_(float_model.conv2.lin_r.weight)
        
        print("✓ Loaded weights from float model")
    
    def calibrate(self, data, num_batches: int = 50):
        """
        Calibrate quantization parameters using representative data.
        
        Run once before training, then freeze observers.
        
        Args:
            data: PyG data object with x and edge_index
            num_batches: Number of forward passes for calibration
        """
        self.eval()
        self.enable_observer()
        self.disable_fake_quant()  # Collect stats without quantization noise
        
        print(f"Calibrating with {num_batches} forward passes...")
        with torch.no_grad():
            for i in range(num_batches):
                _ = self(data.x, data.edge_index)
        
        self.disable_observer()  # Freeze observers
        self.enable_fake_quant()
        print("✓ Calibration complete, observers frozen")
    
    def print_quant_info(self):
        """Print quantization scales for debugging."""
        print("\nQuantization scales:")
        for name, module in self.named_modules():
            if isinstance(module, FakeQuantize):
                if module.scale is not None:
                    scale = module.scale.item() if module.scale.numel() == 1 else module.scale.mean().item()
                    print(f"  {name}: scale={scale:.6f}")


def train_qat_v2(
    qat_model,
    data,
    epochs: int = 100,
    lr: float = 0.001,
    weight_decay: float = 5e-4,
    verbose: bool = True,
):
    """
    Train QAT model with FROZEN observers (correct approach).
    
    Differences from v1:
    1. Observers are disabled during training
    2. Lower learning rate for fine-tuning
    3. Shorter training schedule (fine-tuning only, not from scratch)
    """
    qat_model.train()
    qat_model.enable_fake_quant()
    qat_model.disable_observer()  # Observers must stay frozen during training
    
    optimizer = torch.optim.Adam(qat_model.parameters(), lr=lr, weight_decay=weight_decay)
    
    best_val_acc = 0
    best_state = None
    
    for epoch in range(1, epochs + 1):
        # Training step
        qat_model.train()
        optimizer.zero_grad()
        
        out = qat_model(data.x, data.edge_index)
        loss = F.cross_entropy(out[data.train_mask], data.y[data.train_mask])
        
        loss.backward()
        
        # Gradient clipping to prevent weight collapse
        torch.nn.utils.clip_grad_norm_(qat_model.parameters(), max_norm=1.0)
        
        optimizer.step()
        
        # Evaluation
        if epoch % 10 == 0:
            qat_model.eval()
            with torch.no_grad():
                out = qat_model(data.x, data.edge_index)
                pred = out.argmax(dim=1)
                
                train_acc = (pred[data.train_mask] == data.y[data.train_mask]).float().mean()
                val_acc = (pred[data.val_mask] == data.y[data.val_mask]).float().mean()
                test_acc = (pred[data.test_mask] == data.y[data.test_mask]).float().mean()
            
            if verbose:
                print(f"Epoch {epoch:03d}: Loss={loss:.4f}, Train={train_acc:.4f}, Val={val_acc:.4f}, Test={test_acc:.4f}")
            
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_state = {k: v.clone() for k, v in qat_model.state_dict().items()}
    
    # Load best model
    if best_state is not None:
        qat_model.load_state_dict(best_state)
    
    return qat_model


if __name__ == "__main__":
    from torch_geometric.datasets import Planetoid
    from torch_geometric.transforms import NormalizeFeatures
    from model_base import ReducedGraphSAGE
    
    print("="*70)
    print("QAT v2: Corrected Implementation Test")
    print("="*70)
    
    # Load data
    dataset = Planetoid(root='../data', name='Cora', transform=NormalizeFeatures())
    data = dataset[0]
    
    # Load pre-trained float model
    print("\n1. Loading pre-trained float model...")
    float_model = ReducedGraphSAGE(
        in_channels=dataset.num_features,
        in_channels_reduced=16,
        hidden_channels=24,
        out_channels=dataset.num_classes,
        dropout=0.5,
        use_projection=True,
        root_weight=False
    )
    
    checkpoint = torch.load('../build/models/reduced_graphsage_no_root_best.pth', weights_only=False)
    float_model.load_state_dict(checkpoint['model_state_dict'])
    
    # Evaluate float model
    float_model.eval()
    with torch.no_grad():
        out = float_model(data.x, data.edge_index)
        pred = out.argmax(dim=1)
        float_acc = (pred == data.y).float().mean()
    print(f"   Float model accuracy: {float_acc*100:.2f}%")
    
    # Create QAT v2 model
    print("\n2. Creating QAT v2 model...")
    qat_model = ReducedGraphSAGEQATv2(
        in_channels=dataset.num_features,
        in_channels_reduced=16,
        hidden_channels=24,
        out_channels=dataset.num_classes,
        dropout=0.5,
        use_projection=True,
        root_weight=False,
        num_bits=8
    )
    
    # Initialize from float model (required for convergence)
    print("\n3. Initializing from float model...")
    qat_model.load_from_float_model(float_model)
    
    # Test accuracy before calibration
    qat_model.eval()
    qat_model.disable_fake_quant()
    with torch.no_grad():
        out = qat_model(data.x, data.edge_index)
        pred = out.argmax(dim=1)
        pre_calib_acc = (pred == data.y).float().mean()
    print(f"   Before calibration (float path): {pre_calib_acc*100:.2f}%")
    
    # Calibrate
    print("\n4. Calibrating quantization parameters...")
    qat_model.calibrate(data, num_batches=50)
    qat_model.print_quant_info()
    
    # Test accuracy after calibration
    qat_model.eval()
    qat_model.enable_fake_quant()
    with torch.no_grad():
        out = qat_model(data.x, data.edge_index)
        pred = out.argmax(dim=1)
        post_calib_acc = (pred == data.y).float().mean()
    print(f"\n   After calibration (quantized path): {post_calib_acc*100:.2f}%")
    
    # Fine-tune with QAT
    print("\n5. Fine-tuning with QAT (100 epochs)...")
    qat_model = train_qat_v2(qat_model, data, epochs=100, lr=0.001)
    
    # Final evaluation
    print("\n6. Final evaluation...")
    qat_model.eval()
    qat_model.enable_fake_quant()
    with torch.no_grad():
        out = qat_model(data.x, data.edge_index)
        pred = out.argmax(dim=1)
        final_acc = (pred == data.y).float().mean()
    
    print(f"\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)
    print(f"Float model accuracy:           {float_acc*100:.2f}%")
    print(f"QAT v2 (pre-calibration):       {pre_calib_acc*100:.2f}%")
    print(f"QAT v2 (post-calibration):      {post_calib_acc*100:.2f}%")
    print(f"QAT v2 (after fine-tuning):     {final_acc*100:.2f}%")
    print(f"Quantization gap:               {(float_acc - final_acc)*100:.2f}%")
    print("="*70)
