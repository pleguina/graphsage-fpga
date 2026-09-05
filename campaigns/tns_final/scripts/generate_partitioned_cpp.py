#!/usr/bin/env python3
"""Emit graphsage_po2_qat_partitioned.cpp for an arbitrary L1 (hidden) channel count.

The channel-level template functions (l1_root_channel, l1_neighbor_channel,
l2_root_channel, l2_neighbor_channel) in graphsage_po2_qat_partitioned.h are
already generic in ROOT_HIDDEN_FEATURES/ROOT_IN_FEATURES/ROOT_OUT_FEATURES.
Only the .cpp's per-channel call list is hand-unrolled for the nominal
HIDDEN_FEATURES=24 config. This script regenerates that call list for a
different hidden width so hidden-width scaling (campaign plan Section 12)
does not require hand-editing the unrolled instantiation list.

L2 (root/neighbor) channel count is left at the nominal OUT_FEATURES=7,
since scaling only varies HIDDEN_FEATURES per the campaign plan.
"""
import argparse

L2_OUT_FEATURES = 7

HEADER = """#include "graphsage_po2_qat_partitioned.h"

void graphsage_po2_qat_partitioned(
    const data_t input[ROOT_NUM_NODES][ROOT_IN_FEATURES],
    const edge_mask_t edge_masks[ROOT_NUM_NODES],
    data_t output[ROOT_NUM_NODES][ROOT_OUT_FEATURES]
) {
#pragma HLS PIPELINE II=1
#pragma HLS INTERFACE mode=ap_none port=input register
#pragma HLS INTERFACE mode=ap_none port=edge_masks register
#pragma HLS INTERFACE mode=ap_none port=output register
#pragma HLS INTERFACE mode=ap_ctrl_none port=return
#pragma HLS ARRAY_PARTITION variable=input complete dim=1
#pragma HLS ARRAY_PARTITION variable=input complete dim=2
#pragma HLS ARRAY_PARTITION variable=edge_masks complete
#pragma HLS ARRAY_PARTITION variable=output complete dim=1
#pragma HLS ARRAY_PARTITION variable=output complete dim=2
#pragma HLS ARRAY_PARTITION variable=ROOT_WEIGHTS1_NEIGHBOR complete
#pragma HLS ARRAY_PARTITION variable=ROOT_WEIGHTS1_ROOT complete
#pragma HLS ARRAY_PARTITION variable=ROOT_BIAS1 complete
#pragma HLS ARRAY_PARTITION variable=ROOT_WEIGHTS2_NEIGHBOR complete
#pragma HLS ARRAY_PARTITION variable=ROOT_WEIGHTS2_ROOT complete
#pragma HLS ARRAY_PARTITION variable=ROOT_BIAS2 complete

    data_t aggregate1[ROOT_NUM_NODES][ROOT_IN_FEATURES];
    data_t hidden[ROOT_NUM_NODES][ROOT_HIDDEN_FEATURES];
    data_t aggregate2[ROOT_NUM_NODES][ROOT_HIDDEN_FEATURES];
    data_t root_output1[ROOT_HIDDEN_FEATURES][ROOT_NUM_NODES];
    data_t neighbor_output1[ROOT_HIDDEN_FEATURES][ROOT_NUM_NODES];
    data_t root_output[ROOT_OUT_FEATURES][ROOT_NUM_NODES];
    data_t neighbor_output[ROOT_OUT_FEATURES][ROOT_NUM_NODES];
#pragma HLS ARRAY_PARTITION variable=aggregate1 complete dim=1
#pragma HLS ARRAY_PARTITION variable=aggregate1 complete dim=2
#pragma HLS ARRAY_PARTITION variable=hidden complete dim=1
#pragma HLS ARRAY_PARTITION variable=hidden complete dim=2
#pragma HLS ARRAY_PARTITION variable=aggregate2 complete dim=1
#pragma HLS ARRAY_PARTITION variable=aggregate2 complete dim=2
#pragma HLS ARRAY_PARTITION variable=root_output1 complete dim=1
#pragma HLS ARRAY_PARTITION variable=root_output1 complete dim=2
#pragma HLS ARRAY_PARTITION variable=neighbor_output1 complete dim=1
#pragma HLS ARRAY_PARTITION variable=neighbor_output1 complete dim=2
#pragma HLS ARRAY_PARTITION variable=root_output complete dim=2
#pragma HLS ARRAY_PARTITION variable=root_output complete dim=1
#pragma HLS ARRAY_PARTITION variable=neighbor_output complete dim=2
#pragma HLS ARRAY_PARTITION variable=neighbor_output complete dim=1

    root_dynamic_mean<ROOT_IN_FEATURES, ROOT_AGGREGATE1_SHIFT>(input, edge_masks, aggregate1);

"""

MIDDLE = """
PARTITIONED_L1_COMBINE_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
    PARTITIONED_L1_COMBINE_FEATURE:
        for (int feature = 0; feature < ROOT_HIDDEN_FEATURES; ++feature) {
#pragma HLS UNROLL
            hidden[node][feature] = root_int8_clamp(
                scale_acc_t(root_output1[feature][node]) + scale_acc_t(neighbor_output1[feature][node]));
        }
    }

PARTITIONED_RELU_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
    PARTITIONED_RELU_FEATURE:
        for (int feature = 0; feature < ROOT_HIDDEN_FEATURES; ++feature) {
#pragma HLS UNROLL
            if (hidden[node][feature] < 0) hidden[node][feature] = 0;
        }
    }

    root_dynamic_mean<ROOT_HIDDEN_FEATURES, ROOT_AGGREGATE2_SHIFT>(hidden, edge_masks, aggregate2);

"""

FOOTER = """
PARTITIONED_OUTPUT_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
    PARTITIONED_OUTPUT_FEATURE:
        for (int out_feature = 0; out_feature < ROOT_OUT_FEATURES; ++out_feature) {
#pragma HLS UNROLL
            output[node][out_feature] = root_int8_clamp(
                scale_acc_t(root_output[out_feature][node]) + scale_acc_t(neighbor_output[out_feature][node]));
        }
    }
}
"""


def l1_root_calls(n):
    return "\n".join(
        f"    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << {i})) != 0, {i}, "
        f"(L1_ROOT_ACC_PIPELINE_MASK & (1u << {i})) != 0>(input, root_output1[{i}]);"
        for i in range(n)
    )


def l1_neighbor_calls(n):
    return "\n".join(
        f"    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << {i})) != 0, {i}, "
        f"(L1_NEIGHBOR_ACC_PIPELINE_MASK & (1u << {i})) != 0>(aggregate1, neighbor_output1[{i}]);"
        for i in range(n)
    )


def l2_root_calls(n):
    return "\n".join(
        f"    l2_root_channel<(L2_ROOT_DSP_MASK & (1u << {i})) != 0, {i}, "
        f"(L2_ROOT_ACC_PIPELINE_MASK & (1u << {i})) != 0>(aggregate2, hidden, root_output[{i}]);"
        for i in range(n)
    )


def l2_neighbor_calls(n):
    return "\n".join(
        f"    l2_neighbor_channel<(L2_NEIGHBOR_DSP_MASK & (1u << {i})) != 0, {i}, "
        f"(L2_NEIGHBOR_ACC_PIPELINE_MASK & (1u << {i})) != 0>(aggregate2, neighbor_output[{i}]);"
        for i in range(n)
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hidden-features", type=int, required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    body = (
        HEADER
        + l1_root_calls(args.hidden_features)
        + "\n\n"
        + l1_neighbor_calls(args.hidden_features)
        + "\n"
        + MIDDLE
        + l2_root_calls(L2_OUT_FEATURES)
        + "\n"
        + l2_neighbor_calls(L2_OUT_FEATURES)
        + "\n"
        + FOOTER
    )
    with open(args.output, "w") as f:
        f.write(body)
    print(f"Wrote {args.output} with {args.hidden_features} L1 channels, {L2_OUT_FEATURES} L2 channels")


if __name__ == "__main__":
    main()
