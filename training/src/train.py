"""
Training script for GraphSAGE models on Cora dataset.
Implements training for both base and reduced models.
"""

import torch
import torch.nn.functional as F
from torch_geometric.datasets import Planetoid
from torch_geometric.transforms import NormalizeFeatures
from torch_geometric.data import Data
import os
import sys
import json
import numpy as np

# Fix for PyTorch 2.6+ weights_only default change
torch.serialization.add_safe_globals([Data])

from model_base import GraphSAGE, ReducedGraphSAGE
from visualization import plot_training_curves
from config import get_config


def export_float_weights(model, output_dir='../build/weights_float', suffix=''):
    """
    Export float32 model weights to text files.
    This provides the starting point for integer quantization.
    
    Args:
        model: Trained PyTorch model
        output_dir: Directory to save weights
        suffix: Optional suffix for filenames
    """
    os.makedirs(output_dir, exist_ok=True)
    
    model.eval()
    
    print(f"\nExporting float weights to {output_dir}/")
    
    for name, param in model.named_parameters():
        if len(param.shape) == 0:  # Skip scalar parameters
            continue
        
        # Get weight as numpy array
        weight_np = param.data.cpu().numpy()
        
        # Create filename
        filename = name.replace('.', '_') + suffix + '.txt'
        
        # Save as text file
        np.savetxt(f'{output_dir}/{filename}', weight_np.flatten(), fmt='%.6f')
        
        # Save shape info
        with open(f'{output_dir}/{filename}.shape', 'w') as f:
            f.write(','.join(map(str, weight_np.shape)))
        
        print(f"  Exported {name}: shape={weight_np.shape}, range=[{weight_np.min():.6f}, {weight_np.max():.6f}]")
    
    print(f"✓ Float weights saved to {output_dir}/")
    return output_dir


def train(model, data, optimizer):
    """Train the model for one epoch."""
    model.train()
    optimizer.zero_grad()

    # Forward pass
    out = model(data.x, data.edge_index)

    # Compute loss only on training nodes
    loss = F.cross_entropy(out[data.train_mask], data.y[data.train_mask])

    # Backward pass
    loss.backward()
    optimizer.step()

    return loss.item()


def test(model, data):
    """Evaluate the model on train, val, and test sets."""
    model.eval()

    with torch.no_grad():
        out = model(data.x, data.edge_index)
        pred = out.argmax(dim=1)

        # Compute accuracy for each split
        train_correct = pred[data.train_mask] == data.y[data.train_mask]
        train_acc = int(train_correct.sum()) / int(data.train_mask.sum())

        val_correct = pred[data.val_mask] == data.y[data.val_mask]
        val_acc = int(val_correct.sum()) / int(data.val_mask.sum())

        test_correct = pred[data.test_mask] == data.y[data.test_mask]
        test_acc = int(test_correct.sum()) / int(data.test_mask.sum())

    return train_acc, val_acc, test_acc


def load_cora_dataset(root='../data'):
    """Load and prepare Cora dataset."""
    dataset = Planetoid(root=root, name='Cora', transform=NormalizeFeatures())
    data = dataset[0]

    print(f'Dataset: {dataset}')
    print(f'Number of graphs: {len(dataset)}')
    print(f'Number of features: {dataset.num_features}')
    print(f'Number of classes: {dataset.num_classes}')
    print(f'Number of nodes: {data.num_nodes}')
    print(f'Number of edges: {data.num_edges}')
    print(f'Average node degree: {data.num_edges / data.num_nodes:.2f}')
    print(f'Training nodes: {data.train_mask.sum()}')
    print(f'Validation nodes: {data.val_mask.sum()}')
    print(f'Test nodes: {data.test_mask.sum()}')

    return dataset, data


def train_base_model(epochs=None, lr=None, hidden_channels=None, dropout=None, use_config=True):
    """Train base GraphSAGE model on full Cora dataset."""
    # Load configuration
    if use_config:
        cfg = get_config()
        epochs = epochs or cfg.base_epochs
        lr = lr or cfg.base_lr
        hidden_channels = hidden_channels or cfg.base_hidden_channels
        dropout = dropout or cfg.base_dropout
    else:
        epochs = epochs or 200
        lr = lr or 0.01
        hidden_channels = hidden_channels or 64
        dropout = dropout or 0.5
    print("\n" + "="*60)
    print("Training Base GraphSAGE Model")
    print("="*60)

    # Load dataset
    dataset, data = load_cora_dataset()

    # Create model
    model = GraphSAGE(
        in_channels=dataset.num_features,
        hidden_channels=hidden_channels,
        out_channels=dataset.num_classes,
        dropout=dropout
    )

    print(f'\nModel architecture:\n{model}')
    print(f'Number of parameters: {sum(p.numel() for p in model.parameters())}')

    # Optimizer
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)

    # Training loop with history tracking
    history = {
        'train_loss': [],
        'train_acc': [],
        'val_acc': [],
        'test_acc': []
    }

    best_val_acc = 0
    for epoch in range(1, epochs + 1):
        loss = train(model, data, optimizer)
        train_acc, val_acc, test_acc = test(model, data)

        # Track history
        history['train_loss'].append(loss)
        history['train_acc'].append(train_acc)
        history['val_acc'].append(val_acc)
        history['test_acc'].append(test_acc)

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            # Save best model
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_acc': val_acc,
            }, '../build/models/base_graphsage_best.pth')

        if epoch % 10 == 0:
            print(f'Epoch: {epoch:03d}, Loss: {loss:.4f}, '
                  f'Train: {train_acc:.4f}, Val: {val_acc:.4f}, Test: {test_acc:.4f}')

    # Load best model and evaluate
    checkpoint = torch.load('../build/models/base_graphsage_best.pth')
    model.load_state_dict(checkpoint['model_state_dict'])
    train_acc, val_acc, test_acc = test(model, data)

    print(f'\nBest model performance:')
    print(f'Train Acc: {train_acc:.4f}, Val Acc: {val_acc:.4f}, Test Acc: {test_acc:.4f}')

    # Save training history
    os.makedirs('../outputs', exist_ok=True)
    with open('../build/base_model_history.json', 'w') as f:
        json.dump(history, f, indent=2)

    # Plot training curves
    plot_training_curves(history, save_path='../build/plots/base_model_training.png')

    return model, data, history


def train_reduced_model(epochs=None, lr=None, in_channels_reduced=None,
                       hidden_channels=None, dropout=None, root_weight=None,
                       use_config=True):
    """
    Train reduced GraphSAGE model for FPGA implementation.

    Args:
        epochs: Number of training epochs (default: from config)
        lr: Learning rate (default: from config)
        in_channels_reduced: Projected input dimension (default: from config)
        hidden_channels: Hidden layer dimension (default: from config)
        dropout: Dropout rate (default: from config)
        root_weight: If False, HLS-compatible (default: from config)
        use_config: If True, load defaults from config file
    """
    # Load configuration
    if use_config:
        cfg = get_config()
        epochs = epochs or cfg.reduced_epochs
        lr = lr or cfg.reduced_lr
        in_channels_reduced = in_channels_reduced or cfg.reduced_in_channels
        hidden_channels = hidden_channels or cfg.reduced_hidden_channels
        dropout = dropout or cfg.reduced_dropout
        root_weight = root_weight if root_weight is not None else cfg.reduced_root_weight
    else:
        # Fallback to hardcoded defaults
        epochs = epochs or 200
        lr = lr or 0.01
        in_channels_reduced = in_channels_reduced or 16
        hidden_channels = hidden_channels or 24
        dropout = dropout or 0.5
        root_weight = root_weight if root_weight is not None else True
    suffix = "" if root_weight else "_no_root"
    print("\n" + "="*60)
    print(f"Training Reduced GraphSAGE Model (FPGA-friendly{suffix})")
    print("="*60)
    if not root_weight:
        print("NOTE: Using root_weight=False for HLS compatibility")
        print("      Formula: out = W_l * h_agg + b_l")
    else:
        print("NOTE: Using root_weight=True (default PyG behavior)")
        print("      Formula: out = W_l * h_agg + b_l + W_r * x_i")

    # Load dataset
    dataset, data = load_cora_dataset()

    # Create reduced model
    model = ReducedGraphSAGE(
        in_channels=dataset.num_features,
        in_channels_reduced=in_channels_reduced,
        hidden_channels=hidden_channels,
        out_channels=dataset.num_classes,
        dropout=dropout,
        use_projection=True,
        root_weight=root_weight
    )

    print(f'\nModel architecture:\n{model}')
    print(f'Number of parameters: {sum(p.numel() for p in model.parameters())}')

    # Print configuration being used
    if use_config:
        print(f'\n📋 Using config: reduced_model')
        print(f'   Architecture: {in_channels_reduced} → {hidden_channels} → {dataset.num_classes}')
        print(f'   Learning rate: {lr}, Epochs: {epochs}')
        print(f'   Root weight: {root_weight}')

    # Optimizer
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)

    # Training loop with history tracking
    history = {
        'train_loss': [],
        'train_acc': [],
        'val_acc': [],
        'test_acc': []
    }

    best_val_acc = 0
    for epoch in range(1, epochs + 1):
        loss = train(model, data, optimizer)
        train_acc, val_acc, test_acc = test(model, data)

        # Track history
        history['train_loss'].append(loss)
        history['train_acc'].append(train_acc)
        history['val_acc'].append(val_acc)
        history['test_acc'].append(test_acc)

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            # Save best model
            model_path = f'../build/models/reduced_graphsage{suffix}_best.pth'
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_acc': val_acc,
                'root_weight': root_weight,
            }, model_path)

        if epoch % 10 == 0:
            print(f'Epoch: {epoch:03d}, Loss: {loss:.4f}, '
                  f'Train: {train_acc:.4f}, Val: {val_acc:.4f}, Test: {test_acc:.4f}')

    # Load best model and evaluate
    model_path = f'../build/models/reduced_graphsage{suffix}_best.pth'
    checkpoint = torch.load(model_path)
    model.load_state_dict(checkpoint['model_state_dict'])
    train_acc, val_acc, test_acc = test(model, data)

    print(f'\nBest model performance:')
    print(f'Train Acc: {train_acc:.4f}, Val Acc: {val_acc:.4f}, Test Acc: {test_acc:.4f}')

    # Save training history
    history_path = f'../build/reduced_model{suffix}_history.json'
    with open(history_path, 'w') as f:
        json.dump(history, f, indent=2)

    # Plot training curves
    plot_path = f'../build/plots/reduced_model{suffix}_training.png'
    plot_training_curves(history, save_path=plot_path)

    # Export float weights (for later quantization)
    if not root_weight:  # Only for HLS-compatible no-root model
        export_float_weights(model, output_dir='../build/weights_float', suffix=suffix)

    return model, data, history


if __name__ == '__main__':
    # Train base model
    base_model, data, base_history = train_base_model(epochs=200)

    # Train reduced model WITH root_weight (default PyG behavior)
    print("\n" + "="*60)
    print("Training Model WITH root_weight=True")
    print("="*60)
    reduced_model, data, reduced_history = train_reduced_model(epochs=200, root_weight=True)

    # Train reduced model WITHOUT root_weight (HLS-compatible)
    print("\n" + "="*60)
    print("Training Model WITHOUT root_weight (HLS-compatible)")
    print("="*60)
    reduced_model_no_root, data, reduced_history_no_root = train_reduced_model(epochs=200, root_weight=False)

    print("\n" + "="*60)
    print("Training Complete!")
    print("="*60)
    print("Saved models:")
    print("  - ../build/models/base_graphsage_best.pth")
    print("  - ../build/models/reduced_graphsage_best.pth (with root_weight)")
    print("  - ../build/models/reduced_graphsage_no_root_best.pth (HLS-compatible)")
    print("\nTraining plots:")
    print("  - ../build/plots/base_model_training.png")
    print("  - ../build/plots/reduced_model_training.png")
    print("  - ../build/plots/reduced_model_no_root_training.png")
    print("\nFor HLS implementation, use the '_no_root' model!")
