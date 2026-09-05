"""Root-enabled PO2-QAT matching the dynamic HLS GraphSAGE arithmetic."""

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


ADJACENCY_SCALE = 4096


class RoundStraightThrough(torch.autograd.Function):
    @staticmethod
    def forward(ctx, values):
        return torch.round(values)

    @staticmethod
    def backward(ctx, gradient):
        return gradient


class ClampStraightThrough(torch.autograd.Function):
    @staticmethod
    def forward(ctx, values, minimum, maximum):
        return torch.clamp(values, minimum, maximum)

    @staticmethod
    def backward(ctx, gradient):
        return gradient, None, None


class FloorStraightThrough(torch.autograd.Function):
    @staticmethod
    def forward(ctx, values):
        return torch.floor(values)

    @staticmethod
    def backward(ctx, gradient):
        return gradient


def round_ste(values):
    return RoundStraightThrough.apply(values)


def clamp_ste(values, minimum=-128, maximum=127):
    return ClampStraightThrough.apply(values, minimum, maximum)


def quantize_ste(values, scale):
    return clamp_ste(round_ste(values / scale))


def po2_shift(factor):
    if factor <= 0:
        raise ValueError(f"Scale factor must be positive, got {factor}")
    return -int(round(math.log2(factor)))


def shift_round_ste(values, shift):
    if shift > 0:
        half = float(1 << (shift - 1))
        return FloorStraightThrough.apply((values + half) / float(1 << shift))
    if shift < 0:
        return values * float(1 << (-shift))
    return values


class PO2SAGEConvQAT(nn.Module):
    """One root-enabled SAGE layer with the same quantization order as HLS."""

    def __init__(
        self,
        in_channels,
        out_channels,
        input_scale,
        aggregate_scale,
        output_scale,
        neighbor_weight_scale,
        root_weight_scale,
    ):
        super().__init__()
        self.lin_neighbor = nn.Linear(in_channels, out_channels, bias=True)
        self.lin_root = nn.Linear(in_channels, out_channels, bias=False)
        self.register_buffer("input_scale", torch.tensor(float(input_scale)))
        self.register_buffer("aggregate_scale", torch.tensor(float(aggregate_scale)))
        self.register_buffer("output_scale", torch.tensor(float(output_scale)))
        self.register_buffer("neighbor_weight_scale", torch.tensor(float(neighbor_weight_scale)))
        self.register_buffer("root_weight_scale", torch.tensor(float(root_weight_scale)))
        self.aggregate_shift = po2_shift(input_scale / (ADJACENCY_SCALE * aggregate_scale))
        self.neighbor_shift = po2_shift(
            aggregate_scale * neighbor_weight_scale / output_scale
        )
        self.root_shift = po2_shift(input_scale * root_weight_scale / output_scale)

    def forward(self, input_values, edge_index):
        input_int = quantize_ste(input_values, self.input_scale)
        source, target = edge_index
        degree = torch.bincount(target, minlength=input_values.shape[0]).clamp(min=1)
        coefficients = torch.round(ADJACENCY_SCALE / degree[target]).to(input_values.dtype)
        messages = input_int[source] * coefficients.unsqueeze(1)
        aggregate_acc = torch.zeros_like(input_int)
        aggregate_acc.index_add_(0, target, messages)
        aggregate_int = clamp_ste(shift_round_ste(aggregate_acc, self.aggregate_shift))

        neighbor_weights = quantize_ste(
            self.lin_neighbor.weight, self.neighbor_weight_scale
        )
        root_weights = quantize_ste(self.lin_root.weight, self.root_weight_scale)
        bias_int = round_ste(
            self.lin_neighbor.bias
            / (self.aggregate_scale * self.neighbor_weight_scale)
        )
        neighbor_acc = F.linear(aggregate_int, neighbor_weights, bias_int)
        root_acc = F.linear(input_int, root_weights, None)
        neighbor_int = clamp_ste(shift_round_ste(neighbor_acc, self.neighbor_shift))
        root_int = clamp_ste(shift_round_ste(root_acc, self.root_shift))
        output_int = clamp_ste(neighbor_int + root_int)
        return output_int * self.output_scale

    def shifts(self):
        return {
            "aggregate": self.aggregate_shift,
            "neighbor": self.neighbor_shift,
            "root": self.root_shift,
        }


class ReducedGraphSAGEPO2QAT(nn.Module):
    """Projection plus two root-enabled PO2-QAT SAGE layers."""

    def __init__(self, in_channels, out_channels, scales, weight_scales, dropout=0.5, hidden_channels=24):
        super().__init__()
        self.projection = nn.Linear(in_channels, 16)
        self.conv1 = PO2SAGEConvQAT(
            16,
            hidden_channels,
            scales["input"],
            scales["aggregate1"],
            scales["hidden"],
            weight_scales["neighbor1"],
            weight_scales["root1"],
        )
        self.conv2 = PO2SAGEConvQAT(
            hidden_channels,
            out_channels,
            scales["hidden"],
            scales["aggregate2"],
            scales["output"],
            weight_scales["neighbor2"],
            weight_scales["root2"],
        )
        self.dropout = dropout

    def forward(self, features, edge_index):
        projected = F.relu(self.projection(features))
        hidden = F.relu(self.conv1(projected, edge_index))
        hidden = F.dropout(hidden, p=self.dropout, training=self.training)
        return self.conv2(hidden, edge_index)

    def load_from_float_model(self, float_model):
        with torch.no_grad():
            self.projection.weight.copy_(float_model.projection.weight)
            self.projection.bias.copy_(float_model.projection.bias)
            self.conv1.lin_neighbor.weight.copy_(float_model.conv1.lin_l.weight)
            self.conv1.lin_neighbor.bias.copy_(float_model.conv1.lin_l.bias)
            self.conv1.lin_root.weight.copy_(float_model.conv1.lin_r.weight)
            self.conv2.lin_neighbor.weight.copy_(float_model.conv2.lin_l.weight)
            self.conv2.lin_neighbor.bias.copy_(float_model.conv2.lin_l.bias)
            self.conv2.lin_root.weight.copy_(float_model.conv2.lin_r.weight)

    def shifts(self):
        return {"layer1": self.conv1.shifts(), "layer2": self.conv2.shifts()}
