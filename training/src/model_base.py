"""
Base GraphSAGE model for CPU training on Cora dataset.
This implements the initial architecture as described in step 3.
"""

import torch
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv


class GraphSAGE(torch.nn.Module):
    """
    Base GraphSAGE model with 2 layers.

    Architecture:
    - SAGEConv(F_in, F_hidden)
    - ReLU
    - Dropout (only during training)
    - SAGEConv(F_hidden, F_out)
    """

    def __init__(self, in_channels, hidden_channels, out_channels, dropout=0.5):
        super(GraphSAGE, self).__init__()

        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, out_channels)
        self.dropout = dropout

    def forward(self, x, edge_index):
        # First layer
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)

        # Second layer
        x = self.conv2(x, edge_index)

        return x


class ReducedGraphSAGE(torch.nn.Module):
    """
    Reduced GraphSAGE model for FPGA implementation.
    Uses smaller feature dimensions suitable for hardware.

    Architecture:
    - Linear projection (optional, for feature reduction)
    - SAGEConv(F_in_reduced, F_hidden)
    - ReLU
    - Dropout (only during training)
    - SAGEConv(F_hidden, F_out)
    
    Args:
        root_weight: If True (default), uses W_l * h_agg + b_l + W_r * x_i
                     If False, uses W_l * h_agg + b_l (HLS-compatible, simpler)
    """

    def __init__(self, in_channels, in_channels_reduced, hidden_channels,
                 out_channels, dropout=0.5, use_projection=True, root_weight=True):
        super(ReducedGraphSAGE, self).__init__()

        self.use_projection = use_projection
        self.root_weight = root_weight

        if use_projection:
            self.projection = torch.nn.Linear(in_channels, in_channels_reduced)
            conv_in = in_channels_reduced
        else:
            conv_in = in_channels

        # SAGEConv with configurable root_weight for HLS compatibility
        self.conv1 = SAGEConv(conv_in, hidden_channels, 
                             aggr='mean', 
                             root_weight=root_weight,
                             normalize=False,
                             project=False)
        self.conv2 = SAGEConv(hidden_channels, out_channels,
                             aggr='mean',
                             root_weight=root_weight,
                             normalize=False,
                             project=False)
        self.dropout = dropout

    def forward(self, x, edge_index):
        # Optional projection for feature reduction
        if self.use_projection:
            x = self.projection(x)
            x = F.relu(x)

        # First SAGE layer
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)

        # Second SAGE layer
        x = self.conv2(x, edge_index)

        return x
