"""
Subgraph extraction for FPGA implementation.
Extracts a fixed subgraph with specified number of nodes for hardware implementation.
"""

import torch
import numpy as np
from torch_geometric.datasets import Planetoid
from torch_geometric.transforms import NormalizeFeatures
from torch_geometric.utils import k_hop_subgraph
import json


def extract_fixed_subgraph(data, num_nodes=32, center_node=None, num_hops=2):
    """
    Extract a fixed subgraph with specified number of nodes.

    Args:
        data: PyG Data object
        num_nodes: Number of nodes to include in subgraph
        center_node: Central node for extraction (if None, choose randomly)
        num_hops: Number of hops for neighborhood extraction

    Returns:
        subgraph_data: Dictionary containing subgraph information
    """
    if center_node is None:
        # Choose a node from training set
        train_nodes = data.train_mask.nonzero(as_tuple=True)[0]
        center_node = train_nodes[torch.randint(len(train_nodes), (1,))].item()

    # Extract k-hop neighborhood
    subset, edge_index, mapping, edge_mask = k_hop_subgraph(
        node_idx=center_node,
        num_hops=num_hops,
        edge_index=data.edge_index,
        relabel_nodes=True,
        num_nodes=data.num_nodes
    )

    # Limit to desired number of nodes
    if len(subset) > num_nodes:
        subset = subset[:num_nodes]
        # Re-extract edges for the limited subset
        node_mask = torch.zeros(data.num_nodes, dtype=torch.bool)
        node_mask[subset] = True

        # Filter edges
        edge_mask = node_mask[data.edge_index[0]] & node_mask[data.edge_index[1]]
        edge_index = data.edge_index[:, edge_mask]

        # Relabel nodes to be contiguous
        mapping = torch.full((data.num_nodes,), -1, dtype=torch.long)
        mapping[subset] = torch.arange(len(subset))
        edge_index = mapping[edge_index]

    # Extract node features and labels
    x_subgraph = data.x[subset]
    y_subgraph = data.y[subset]

    # Create adjacency matrix (dense format for FPGA)
    num_nodes_actual = len(subset)
    adj_matrix = torch.zeros((num_nodes_actual, num_nodes_actual), dtype=torch.float32)
    adj_matrix[edge_index[1], edge_index[0]] = 1.0

    # Normalize adjacency matrix for SAGEConv mean aggregation
    # SAGEConv with aggr='mean' does NOT add self-loops automatically.
    # It divides by the number of incoming neighbors.
    # Row-normalize: adj[i,j] = 1/degree(i) if there's an edge j->i
    deg = adj_matrix.sum(dim=1)  # Incoming degree per node
    deg_inv = 1.0 / deg
    deg_inv[deg_inv == float('inf')] = 0  # Handle isolated nodes
    adj_matrix = deg_inv.view(-1, 1) * adj_matrix  # Row-normalize

    subgraph_data = {
        'subset_indices': subset.numpy(),
        'num_nodes': num_nodes_actual,
        'edge_index': edge_index.numpy(),
        'adj_matrix': adj_matrix.numpy(),
        'x': x_subgraph.numpy(),
        'y': y_subgraph.numpy(),
        'center_node': center_node,
        'original_num_features': data.x.shape[1]
    }

    return subgraph_data


def save_subgraph(subgraph_data, output_dir='./outputs'):
    """Save subgraph data to files for FPGA implementation."""
    import os
    os.makedirs(output_dir, exist_ok=True)

    # Save adjacency matrix
    np.savetxt(f'{output_dir}/adj_matrix.txt', subgraph_data['adj_matrix'], fmt='%.6f')

    # Save node features
    np.savetxt(f'{output_dir}/node_features.txt', subgraph_data['x'], fmt='%.6f')

    # Save labels
    np.savetxt(f'{output_dir}/labels.txt', subgraph_data['y'], fmt='%d')

    # Save metadata
    metadata = {
        'num_nodes': int(subgraph_data['num_nodes']),
        'num_features': int(subgraph_data['original_num_features']),
        'center_node': int(subgraph_data['center_node']),
        'num_edges': int(subgraph_data['edge_index'].shape[1])
    }

    with open(f'{output_dir}/subgraph_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"Subgraph saved to {output_dir}/")
    print(f"  - Nodes: {metadata['num_nodes']}")
    print(f"  - Features: {metadata['num_features']}")
    print(f"  - Edges: {metadata['num_edges']}")

    return metadata


if __name__ == '__main__':
    # Load Cora dataset
    dataset = Planetoid(root='./data', name='Cora', transform=NormalizeFeatures())
    data = dataset[0]

    print("Extracting fixed subgraph for FPGA implementation...")

    # Extract subgraph with 32 nodes
    subgraph_data = extract_fixed_subgraph(data, num_nodes=32, num_hops=2)

    # Save to files
    metadata = save_subgraph(subgraph_data, output_dir='../build/subgraph')

    print("\nSubgraph extraction complete!")
