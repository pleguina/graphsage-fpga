#include "graphsage_po2_qat_partitioned.h"

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

    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 0)) != 0, 0>(input, root_output1[0]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 1)) != 0, 1>(input, root_output1[1]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 2)) != 0, 2>(input, root_output1[2]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 3)) != 0, 3>(input, root_output1[3]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 4)) != 0, 4>(input, root_output1[4]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 5)) != 0, 5>(input, root_output1[5]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 6)) != 0, 6>(input, root_output1[6]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 7)) != 0, 7>(input, root_output1[7]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 8)) != 0, 8>(input, root_output1[8]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 9)) != 0, 9>(input, root_output1[9]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 10)) != 0, 10>(input, root_output1[10]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 11)) != 0, 11>(input, root_output1[11]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 12)) != 0, 12>(input, root_output1[12]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 13)) != 0, 13>(input, root_output1[13]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 14)) != 0, 14>(input, root_output1[14]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 15)) != 0, 15>(input, root_output1[15]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 16)) != 0, 16>(input, root_output1[16]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 17)) != 0, 17>(input, root_output1[17]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 18)) != 0, 18>(input, root_output1[18]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 19)) != 0, 19>(input, root_output1[19]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 20)) != 0, 20>(input, root_output1[20]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 21)) != 0, 21>(input, root_output1[21]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 22)) != 0, 22>(input, root_output1[22]);
    l1_root_channel<(L1_ROOT_DSP_MASK & (1u << 23)) != 0, 23>(input, root_output1[23]);

    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 0)) != 0, 0>(aggregate1, neighbor_output1[0]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 1)) != 0, 1>(aggregate1, neighbor_output1[1]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 2)) != 0, 2>(aggregate1, neighbor_output1[2]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 3)) != 0, 3>(aggregate1, neighbor_output1[3]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 4)) != 0, 4>(aggregate1, neighbor_output1[4]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 5)) != 0, 5>(aggregate1, neighbor_output1[5]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 6)) != 0, 6>(aggregate1, neighbor_output1[6]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 7)) != 0, 7>(aggregate1, neighbor_output1[7]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 8)) != 0, 8, (L1_NEIGHBOR_ACC_PIPELINE_MASK & (1u << 8)) != 0>(aggregate1, neighbor_output1[8]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 9)) != 0, 9>(aggregate1, neighbor_output1[9]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 10)) != 0, 10>(aggregate1, neighbor_output1[10]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 11)) != 0, 11>(aggregate1, neighbor_output1[11]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 12)) != 0, 12>(aggregate1, neighbor_output1[12]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 13)) != 0, 13>(aggregate1, neighbor_output1[13]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 14)) != 0, 14>(aggregate1, neighbor_output1[14]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 15)) != 0, 15>(aggregate1, neighbor_output1[15]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 16)) != 0, 16>(aggregate1, neighbor_output1[16]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 17)) != 0, 17>(aggregate1, neighbor_output1[17]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 18)) != 0, 18>(aggregate1, neighbor_output1[18]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 19)) != 0, 19>(aggregate1, neighbor_output1[19]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 20)) != 0, 20>(aggregate1, neighbor_output1[20]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 21)) != 0, 21>(aggregate1, neighbor_output1[21]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 22)) != 0, 22>(aggregate1, neighbor_output1[22]);
    l1_neighbor_channel<(L1_NEIGHBOR_DSP_MASK & (1u << 23)) != 0, 23>(aggregate1, neighbor_output1[23]);

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

    l2_root_channel<(L2_ROOT_DSP_MASK & (1u << 0)) != 0, 0>(aggregate2, hidden, root_output[0]);
    l2_root_channel<(L2_ROOT_DSP_MASK & (1u << 1)) != 0, 1>(aggregate2, hidden, root_output[1]);
    l2_root_channel<(L2_ROOT_DSP_MASK & (1u << 2)) != 0, 2>(aggregate2, hidden, root_output[2]);
    l2_root_channel<(L2_ROOT_DSP_MASK & (1u << 3)) != 0, 3>(aggregate2, hidden, root_output[3]);
    l2_root_channel<(L2_ROOT_DSP_MASK & (1u << 4)) != 0, 4>(aggregate2, hidden, root_output[4]);
    l2_root_channel<(L2_ROOT_DSP_MASK & (1u << 5)) != 0, 5>(aggregate2, hidden, root_output[5]);
    l2_root_channel<(L2_ROOT_DSP_MASK & (1u << 6)) != 0, 6>(aggregate2, hidden, root_output[6]);
    l2_neighbor_channel<(L2_NEIGHBOR_DSP_MASK & (1u << 0)) != 0, 0>(aggregate2, neighbor_output[0]);
    l2_neighbor_channel<(L2_NEIGHBOR_DSP_MASK & (1u << 1)) != 0, 1>(aggregate2, neighbor_output[1]);
    l2_neighbor_channel<(L2_NEIGHBOR_DSP_MASK & (1u << 2)) != 0, 2>(aggregate2, neighbor_output[2]);
    l2_neighbor_channel<(L2_NEIGHBOR_DSP_MASK & (1u << 3)) != 0, 3>(aggregate2, neighbor_output[3]);
    l2_neighbor_channel<(L2_NEIGHBOR_DSP_MASK & (1u << 4)) != 0, 4>(aggregate2, neighbor_output[4]);
    l2_neighbor_channel<(L2_NEIGHBOR_DSP_MASK & (1u << 5)) != 0, 5>(aggregate2, neighbor_output[5]);
    l2_neighbor_channel<(L2_NEIGHBOR_DSP_MASK & (1u << 6)) != 0, 6>(aggregate2, neighbor_output[6]);

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