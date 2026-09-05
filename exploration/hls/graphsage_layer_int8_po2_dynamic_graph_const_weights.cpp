#include "graphsage_layer_int8_po2_dynamic_graph_const_weights.h"

void graphsage_dynamic_graph_const_weights(
    const data_t input[NUM_NODES][IN_FEATURES],
    const edge_mask_t edge_masks[NUM_NODES],
    data_t output[NUM_NODES][OUT_FEATURES]
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

    data_t registered_input[NUM_NODES][IN_FEATURES];
    edge_mask_t registered_masks[NUM_NODES];
    data_t registered_output[NUM_NODES][OUT_FEATURES];
#pragma HLS ARRAY_PARTITION variable=registered_input complete dim=1
#pragma HLS ARRAY_PARTITION variable=registered_input complete dim=2
#pragma HLS ARRAY_PARTITION variable=registered_masks complete
#pragma HLS ARRAY_PARTITION variable=registered_output complete dim=1
#pragma HLS ARRAY_PARTITION variable=registered_output complete dim=2

REGISTER_INPUT_NODE:
    for (int node = 0; node < NUM_NODES; ++node) {
#pragma HLS UNROLL
        registered_masks[node] = edge_masks[node];
    REGISTER_INPUT_FEATURE:
        for (int feature = 0; feature < IN_FEATURES; ++feature) {
#pragma HLS UNROLL
            registered_input[node][feature] = input[node][feature];
        }
    }

    graphsage_dynamic_graph_const_weights_template<
        NUM_NODES, IN_FEATURES, HIDDEN_FEATURES, OUT_FEATURES>(
        registered_input, registered_masks, registered_output);

REGISTER_OUTPUT_NODE:
    for (int node = 0; node < NUM_NODES; ++node) {
#pragma HLS UNROLL
    REGISTER_OUTPUT_FEATURE:
        for (int feature = 0; feature < OUT_FEATURES; ++feature) {
#pragma HLS UNROLL
            output[node][feature] = registered_output[node][feature];
        }
    }
}