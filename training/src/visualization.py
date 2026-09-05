"""
Visualization utilities for model analysis and comparison.
Generates plots for training curves, model efficiency, quantization effects, etc.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import numpy as np
import json
import os
from pathlib import Path

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['font.size'] = 10


def _smart_rotate_labels(ax, names, threshold=6):
    """
    Smart rotation for x-axis labels based on number of items and label lengths.
    Prevents label overlap on bar charts.
    """
    max_len = max(len(name) for name in names) if names else 0
    num_labels = len(names)
    
    if num_labels > 10 or max_len > 12:
        rotation = 45
        ha = 'right'
    elif num_labels > threshold or max_len > 8:
        rotation = 30
        ha = 'right'
    else:
        rotation = 0
        ha = 'center'
    
    ax.set_xticklabels(names, rotation=rotation, ha=ha)
    return rotation


def _smart_annotate_scatter(ax, names, x_vals, y_vals, colors=None):
    """
    Smart annotation for scatter plots that avoids label overlap.
    Uses adjustText library if available, otherwise manual offsets.
    """
    # Calculate data range for offset scaling
    x_range = max(x_vals) - min(x_vals) if len(x_vals) > 1 else 1
    y_range = max(y_vals) - min(y_vals) if len(y_vals) > 1 else 1
    
    # Create annotations with alternating offsets to reduce overlap
    offsets = [
        (8, 8), (-8, 8), (8, -12), (-8, -12),
        (12, 0), (-12, 0), (0, 12), (0, -12),
        (10, 5), (-10, 5), (10, -5), (-10, -5)
    ]
    
    annotations = []
    for i, (name, x, y) in enumerate(zip(names, x_vals, y_vals)):
        offset = offsets[i % len(offsets)]
        ann = ax.annotate(
            name, (x, y),
            xytext=offset,
            textcoords='offset points',
            fontsize=8,
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7, edgecolor='gray'),
            arrowprops=dict(arrowstyle='-', color='gray', alpha=0.5) if len(names) > 6 else None
        )
        annotations.append(ann)
    
    return annotations


def plot_training_curves(history, save_path='../build/plots/training_curves.png'):
    """
    Plot training and validation curves.

    Args:
        history: Dictionary with keys 'train_loss', 'train_acc', 'val_acc', 'test_acc'
        save_path: Path to save the plot
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    epochs = range(1, len(history['train_loss']) + 1)

    # Loss plot
    axes[0].plot(epochs, history['train_loss'], 'b-', label='Training Loss', linewidth=2)
    axes[0].set_xlabel('Epoch')
    axes[0].set_ylabel('Loss')
    axes[0].set_title('Training Loss over Epochs')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # Accuracy plot
    axes[1].plot(epochs, history['train_acc'], 'b-', label='Train Accuracy', linewidth=2)
    axes[1].plot(epochs, history['val_acc'], 'r-', label='Validation Accuracy', linewidth=2)
    axes[1].plot(epochs, history['test_acc'], 'g-', label='Test Accuracy', linewidth=2)
    axes[1].set_xlabel('Epoch')
    axes[1].set_ylabel('Accuracy')
    axes[1].set_title('Accuracy over Epochs')
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Saved training curves to {save_path}")
    plt.close()


def plot_model_comparison(model_stats, save_path='../build/plots/model_comparison.png'):
    """
    Compare different model variants (base, reduced, pruned, quantized).

    Args:
        model_stats: List of dicts with keys 'name', 'accuracy', 'parameters', 'memory_mb'
        save_path: Path to save the plot
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # Adaptive figure size based on number of models
    num_models = len(model_stats)
    fig_width = max(16, 12 + num_models * 0.5)
    fig_height = max(5, 4 + num_models * 0.1)
    fig, axes = plt.subplots(1, 3, figsize=(fig_width, fig_height))

    names = [stat['name'] for stat in model_stats]
    accuracies = [stat['accuracy'] for stat in model_stats]
    parameters = [stat['parameters'] / 1e3 for stat in model_stats]  # Convert to K
    memory = [stat['memory_mb'] for stat in model_stats]

    colors = sns.color_palette("husl", len(names))

    # Accuracy comparison
    bars1 = axes[0].bar(range(len(names)), accuracies, color=colors, alpha=0.7, edgecolor='black')
    axes[0].set_ylabel('Test Accuracy')
    axes[0].set_title('Model Accuracy Comparison')
    axes[0].set_ylim([0, 1.0])
    axes[0].grid(True, alpha=0.3, axis='y')
    axes[0].set_xticks(range(len(names)))

    # Add value labels on bars (smaller font for many models)
    label_fontsize = max(6, 9 - num_models // 4)
    for bar, acc in zip(bars1, accuracies):
        height = bar.get_height()
        axes[0].text(bar.get_x() + bar.get_width()/2., height,
                    f'{acc:.3f}', ha='center', va='bottom', fontsize=label_fontsize)

    # Parameters comparison
    bars2 = axes[1].bar(range(len(names)), parameters, color=colors, alpha=0.7, edgecolor='black')
    axes[1].set_ylabel('Parameters (K)')
    axes[1].set_title('Model Size (Parameters)')
    axes[1].grid(True, alpha=0.3, axis='y')
    axes[1].set_xticks(range(len(names)))

    for bar, param in zip(bars2, parameters):
        height = bar.get_height()
        axes[1].text(bar.get_x() + bar.get_width()/2., height,
                    f'{param:.1f}K', ha='center', va='bottom', fontsize=label_fontsize)

    # Memory comparison
    bars3 = axes[2].bar(range(len(names)), memory, color=colors, alpha=0.7, edgecolor='black')
    axes[2].set_ylabel('Memory (MB)')
    axes[2].set_title('Model Memory Footprint')
    axes[2].grid(True, alpha=0.3, axis='y')
    axes[2].set_xticks(range(len(names)))

    for bar, mem in zip(bars3, memory):
        height = bar.get_height()
        axes[2].text(bar.get_x() + bar.get_width()/2., height,
                    f'{mem:.3f}', ha='center', va='bottom', fontsize=label_fontsize)

    # Smart label rotation for all axes
    for ax in axes:
        _smart_rotate_labels(ax, names)

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Saved model comparison to {save_path}")
    plt.close()


def plot_efficiency_analysis(model_stats, save_path='../build/plots/efficiency_analysis.png'):
    """
    Plot efficiency metrics: accuracy vs parameters and accuracy vs memory.

    Args:
        model_stats: List of dicts with keys 'name', 'accuracy', 'parameters', 'memory_mb'
        save_path: Path to save the plot
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # Adaptive figure size
    num_models = len(model_stats)
    fig_width = max(14, 12 + num_models * 0.3)
    fig, axes = plt.subplots(1, 2, figsize=(fig_width, 7))

    names = [stat['name'] for stat in model_stats]
    accuracies = [stat['accuracy'] * 100 for stat in model_stats]  # Convert to percentage
    parameters = [stat['parameters'] / 1e3 for stat in model_stats]
    memory = [stat['memory_mb'] for stat in model_stats]

    colors = sns.color_palette("husl", len(names))

    # Accuracy vs Parameters
    axes[0].scatter(parameters, accuracies, s=200, c=colors, alpha=0.7, edgecolors='black', linewidths=2)
    _smart_annotate_scatter(axes[0], names, parameters, accuracies, colors)
    axes[0].set_xlabel('Model Parameters (K)')
    axes[0].set_ylabel('Test Accuracy (%)')
    axes[0].set_title('Accuracy vs Model Size\n(Higher & Left is Better)')
    axes[0].grid(True, alpha=0.3)

    # Accuracy vs Memory
    axes[1].scatter(memory, accuracies, s=200, c=colors, alpha=0.7, edgecolors='black', linewidths=2)
    _smart_annotate_scatter(axes[1], names, memory, accuracies, colors)
    axes[1].set_xlabel('Memory Footprint (MB)')
    axes[1].set_ylabel('Test Accuracy (%)')
    axes[1].set_title('Accuracy vs Memory Usage\n(Higher & Left is Better)')
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Saved efficiency analysis to {save_path}")
    plt.close()


def plot_quantization_error(original_weights, quantized_weights, layer_name,
                           save_path='../build/plots/quantization_error.png'):
    """
    Analyze quantization error for weights.

    Args:
        original_weights: Original float weights (numpy array)
        quantized_weights: Quantized weights (numpy array)
        layer_name: Name of the layer
        save_path: Path to save the plot
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # Compute errors
    errors = original_weights.flatten() - quantized_weights.flatten()

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Original weights distribution
    axes[0, 0].hist(original_weights.flatten(), bins=50, color='blue', alpha=0.7, edgecolor='black')
    axes[0, 0].set_xlabel('Weight Value')
    axes[0, 0].set_ylabel('Frequency')
    axes[0, 0].set_title(f'{layer_name} - Original Weights Distribution')
    axes[0, 0].grid(True, alpha=0.3)

    # Quantized weights distribution
    axes[0, 1].hist(quantized_weights.flatten(), bins=50, color='red', alpha=0.7, edgecolor='black')
    axes[0, 1].set_xlabel('Weight Value')
    axes[0, 1].set_ylabel('Frequency')
    axes[0, 1].set_title(f'{layer_name} - Quantized Weights Distribution')
    axes[0, 1].grid(True, alpha=0.3)

    # Error distribution
    axes[1, 0].hist(errors, bins=50, color='green', alpha=0.7, edgecolor='black')
    axes[1, 0].set_xlabel('Quantization Error')
    axes[1, 0].set_ylabel('Frequency')
    axes[1, 0].set_title(f'{layer_name} - Quantization Error Distribution')
    axes[1, 0].axvline(0, color='red', linestyle='--', linewidth=2)
    axes[1, 0].grid(True, alpha=0.3)

    # Error statistics
    stats_text = f'Mean Error: {np.mean(errors):.6f}\n'
    stats_text += f'Std Error: {np.std(errors):.6f}\n'
    stats_text += f'Max Error: {np.max(np.abs(errors)):.6f}\n'
    stats_text += f'RMSE: {np.sqrt(np.mean(errors**2)):.6f}'

    axes[1, 1].text(0.1, 0.5, stats_text, transform=axes[1, 1].transAxes,
                   fontsize=14, verticalalignment='center',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    axes[1, 1].axis('off')
    axes[1, 1].set_title(f'{layer_name} - Error Statistics')

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Saved quantization error analysis to {save_path}")
    plt.close()


def plot_pruning_effect(original_channels, pruned_channels, layer_names,
                       save_path='../build/plots/pruning_effect.png'):
    """
    Visualize the effect of pruning on each layer.

    Args:
        original_channels: List of original channel counts
        pruned_channels: List of pruned channel counts
        layer_names: List of layer names
        save_path: Path to save the plot
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 6))

    x = np.arange(len(layer_names))
    width = 0.35

    bars1 = ax.bar(x - width/2, original_channels, width, label='Original',
                  color='blue', alpha=0.7, edgecolor='black')
    bars2 = ax.bar(x + width/2, pruned_channels, width, label='After Pruning',
                  color='red', alpha=0.7, edgecolor='black')

    ax.set_xlabel('Layer')
    ax.set_ylabel('Number of Channels')
    ax.set_title('Effect of Structured Pruning on Layer Channels')
    ax.set_xticks(x)
    ax.set_xticklabels(layer_names)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Add value labels and pruning percentage
    for i, (bar1, bar2) in enumerate(zip(bars1, bars2)):
        height1 = bar1.get_height()
        height2 = bar2.get_height()

        ax.text(bar1.get_x() + bar1.get_width()/2., height1,
               f'{int(height1)}', ha='center', va='bottom', fontsize=9)
        ax.text(bar2.get_x() + bar2.get_width()/2., height2,
               f'{int(height2)}', ha='center', va='bottom', fontsize=9)

        # Pruning percentage
        prune_pct = (1 - height2/height1) * 100
        ax.text(i, max(height1, height2) * 1.1,
               f'-{prune_pct:.1f}%', ha='center', fontsize=9,
               color='red', fontweight='bold')

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Saved pruning effect plot to {save_path}")
    plt.close()


def plot_accuracy_degradation(base_acc, model_accs, model_names,
                              save_path='../build/plots/accuracy_degradation.png'):
    """
    Show accuracy degradation from optimizations.

    Args:
        base_acc: Base model accuracy (float)
        model_accs: List of accuracies for other models
        model_names: List of model names
        save_path: Path to save the plot
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # Adaptive figure size
    num_models = len(model_names) + 1
    fig_width = max(10, 8 + num_models * 0.5)
    fig, ax = plt.subplots(figsize=(fig_width, 6))

    all_names = ['Base'] + model_names
    all_accs = [base_acc] + model_accs
    degradations = [0] + [(base_acc - acc) * 100 for acc in model_accs]

    colors = ['green'] + ['orange' if d < 5 else 'red' for d in degradations[1:]]

    x_pos = range(len(all_names))
    bars = ax.bar(x_pos, [a * 100 for a in all_accs], color=colors,
                  alpha=0.7, edgecolor='black', linewidth=2)

    ax.set_ylabel('Test Accuracy (%)')
    ax.set_title('Accuracy Comparison: Impact of Optimizations')
    ax.set_ylim([0, 100])
    ax.grid(True, alpha=0.3, axis='y')
    ax.axhline(y=base_acc * 100, color='blue', linestyle='--', linewidth=2, label='Base Model')
    ax.set_xticks(x_pos)

    # Adaptive font size based on number of models
    label_fontsize = max(6, 9 - num_models // 4)
    
    # Add value labels
    for i, (bar, acc, deg) in enumerate(zip(bars, all_accs, degradations)):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{acc*100:.1f}%', ha='center', va='bottom', fontsize=label_fontsize, fontweight='bold')

        if i > 0:  # Skip base model
            ax.text(bar.get_x() + bar.get_width()/2., height - 5,
                   f'({deg:+.1f}%)', ha='center', va='top', fontsize=label_fontsize-1, color='darkred')

    ax.legend()
    ax.set_xticks(range(len(all_names)))
    _smart_rotate_labels(ax, all_names)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Saved accuracy degradation plot to {save_path}")
    plt.close()


def plot_resource_utilization(model_stats, save_path='../build/plots/resource_utilization.png'):
    """
    Stacked bar chart showing resource breakdown.

    Args:
        model_stats: List of dicts with resource information
        save_path: Path to save the plot
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 6))

    names = [stat['name'] for stat in model_stats]

    # Normalized parameters by layer type
    layer_params = []
    for stat in model_stats:
        layers = stat.get('layer_breakdown', {'conv': 0, 'linear': 0, 'other': 0})
        layer_params.append([layers.get('conv', 0), layers.get('linear', 0), layers.get('other', 0)])

    layer_params = np.array(layer_params).T / 1e3  # Convert to K

    colors = ['#ff9999', '#66b3ff', '#99ff99']
    labels = ['Conv Layers', 'Linear Layers', 'Other']

    bottom = np.zeros(len(names))
    for i, (params, color, label) in enumerate(zip(layer_params, colors, labels)):
        bars = ax.bar(names, params, bottom=bottom, label=label,
                     color=color, alpha=0.8, edgecolor='black')
        bottom += params

        # Add labels
        for j, (bar, p) in enumerate(zip(bars, params)):
            if p > 0:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2.,
                       bottom[j] - height/2,
                       f'{p:.1f}K', ha='center', va='center', fontsize=8)

    ax.set_ylabel('Parameters (K)')
    ax.set_title('Model Resource Breakdown by Layer Type')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    ax.set_xticks(range(len(names)))
    _smart_rotate_labels(ax, names)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Saved resource utilization plot to {save_path}")
    plt.close()


def generate_summary_report(model_stats, save_path='../build/plots/summary_report.png'):
    """
    Generate a comprehensive summary figure with multiple subplots.

    Args:
        model_stats: List of model statistics
        save_path: Path to save the plot
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # Adaptive figure size based on number of models - MUCH BIGGER
    num_models = len(model_stats)
    fig_width = max(20, 16 + num_models * 0.6)
    fig_height = max(18, 14 + num_models * 0.4)
    
    fig = plt.figure(figsize=(fig_width, fig_height))
    # Increased spacing between subplots
    gs = fig.add_gridspec(3, 3, hspace=0.5, wspace=0.4, 
                          height_ratios=[1, 1.2, 1],
                          top=0.93, bottom=0.05, left=0.06, right=0.98)

    names = [stat['name'] for stat in model_stats]
    accuracies = [stat['accuracy'] * 100 for stat in model_stats]
    parameters = [stat['parameters'] / 1e3 for stat in model_stats]
    memory = [stat['memory_mb'] for stat in model_stats]
    colors = sns.color_palette("husl", len(names))
    
    # Adaptive font size
    label_fontsize = max(7, 10 - num_models // 4)

    # Accuracy comparison
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.bar(range(len(names)), accuracies, color=colors, alpha=0.7, edgecolor='black')
    ax1.set_ylabel('Accuracy (%)')
    ax1.set_title('Test Accuracy')
    ax1.set_xticks(range(len(names)))
    _smart_rotate_labels(ax1, names)
    ax1.grid(True, alpha=0.3, axis='y')

    # Parameters comparison
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.bar(range(len(names)), parameters, color=colors, alpha=0.7, edgecolor='black')
    ax2.set_ylabel('Parameters (K)')
    ax2.set_title('Model Size')
    ax2.set_xticks(range(len(names)))
    _smart_rotate_labels(ax2, names)
    ax2.grid(True, alpha=0.3, axis='y')

    # Memory comparison
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.bar(range(len(names)), memory, color=colors, alpha=0.7, edgecolor='black')
    ax3.set_ylabel('Memory (MB)')
    ax3.set_title('Memory Footprint')
    ax3.set_xticks(range(len(names)))
    _smart_rotate_labels(ax3, names)
    ax3.grid(True, alpha=0.3, axis='y')

    # Efficiency: Accuracy vs Parameters
    ax4 = fig.add_subplot(gs[1, :2])
    ax4.scatter(parameters, accuracies, s=300, c=colors, alpha=0.7, edgecolors='black', linewidths=2)
    _smart_annotate_scatter(ax4, names, parameters, accuracies, colors)
    ax4.set_xlabel('Parameters (K)')
    ax4.set_ylabel('Accuracy (%)')
    ax4.set_title('Model Efficiency: Accuracy vs Size')
    ax4.grid(True, alpha=0.3)

    # Summary table - adaptive column width
    ax5 = fig.add_subplot(gs[1, 2])
    ax5.axis('tight')
    ax5.axis('off')

    # Truncate names for table if too long
    max_name_len = min(12, max(8, 16 - num_models // 2))
    table_data = []
    for stat in model_stats:
        reduction = (1 - stat['parameters'] / model_stats[0]['parameters']) * 100
        name_display = stat['name'][:max_name_len] + ('...' if len(stat['name']) > max_name_len else '')
        table_data.append([
            name_display,
            f"{stat['accuracy']*100:.1f}%",
            f"{stat['parameters']/1e3:.1f}K",
            f"{reduction:.0f}%"
        ])

    table = ax5.table(cellText=table_data,
                     colLabels=['Model', 'Acc', 'Params', 'Red.'],
                     cellLoc='center',
                     loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(max(7, 10 - num_models // 3))
    table.scale(1.1, 1.8 + num_models * 0.08)
    ax5.set_title('Summary Statistics', pad=30, fontsize=11)

    # Speedup / Compression ratio (horizontal bar chart - handles many models well)
    ax6 = fig.add_subplot(gs[2, :])
    base_params = model_stats[0]['parameters']
    compression_ratios = [base_params / stat['parameters'] for stat in model_stats]

    y_pos = range(len(names))
    bars = ax6.barh(y_pos, compression_ratios, color=colors, alpha=0.7, edgecolor='black', height=0.7)
    ax6.set_yticks(y_pos)
    ax6.set_yticklabels(names, fontsize=label_fontsize + 1)
    ax6.set_xlabel('Compression Ratio (vs Base Model)', fontsize=11)
    ax6.set_title('Model Compression Achieved', fontsize=12, pad=15)
    ax6.axvline(x=1.0, color='red', linestyle='--', linewidth=2, label='Base Model')
    ax6.grid(True, alpha=0.3, axis='x')
    ax6.legend(loc='lower right', fontsize=10)

    for bar, ratio in zip(bars, compression_ratios):
        width = bar.get_width()
        ax6.text(width + 0.08, bar.get_y() + bar.get_height()/2.,
                f'{ratio:.2f}x', ha='left', va='center', fontsize=label_fontsize + 1, fontweight='bold')

    fig.suptitle('GraphSAGE Model Optimization Summary', fontsize=18, fontweight='bold', y=0.97)

    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"Saved summary report to {save_path}")
    plt.close()


def save_stats_json(model_stats, save_path='../build/plots/model_stats.json'):
    """Save model statistics to JSON file."""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with open(save_path, 'w') as f:
        json.dump(model_stats, f, indent=2)

    print(f"Saved model statistics to {save_path}")
