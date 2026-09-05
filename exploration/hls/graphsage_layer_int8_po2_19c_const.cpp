#include "graphsage_layer_int8_po2_19c_const.h"

#if defined(USE_CONST_PARAMS)
void graphsage_int8_po2(
    const data_t input[NUM_NODES][IN_FEATURES],
    data_t output[NUM_NODES][OUT_FEATURES]
) {
#pragma HLS PIPELINE II=1
#pragma HLS INTERFACE mode=ap_none port=input register
#pragma HLS INTERFACE mode=ap_none port=output register
#pragma HLS INTERFACE mode=ap_ctrl_none port=return
#pragma HLS ARRAY_PARTITION variable=input complete dim=1
#pragma HLS ARRAY_PARTITION variable=input complete dim=2
#pragma HLS ARRAY_PARTITION variable=output complete dim=1
#pragma HLS ARRAY_PARTITION variable=output complete dim=2

    data_t registered_input[NUM_NODES][IN_FEATURES];
    data_t registered_output[NUM_NODES][OUT_FEATURES];
#pragma HLS ARRAY_PARTITION variable=registered_input complete dim=1
#pragma HLS ARRAY_PARTITION variable=registered_input complete dim=2
#pragma HLS ARRAY_PARTITION variable=registered_output complete dim=1
#pragma HLS ARRAY_PARTITION variable=registered_output complete dim=2

REGISTER_INPUT_NODES:
    for (int node = 0; node < NUM_NODES; ++node) {
#pragma HLS UNROLL
    REGISTER_INPUT_FEATURES:
        for (int feature = 0; feature < IN_FEATURES; ++feature) {
#pragma HLS UNROLL
            registered_input[node][feature] = input[node][feature];
        }
    }

    graphsage_int8_po2_const_template<
        NUM_NODES, IN_FEATURES, HIDDEN_FEATURES, OUT_FEATURES>(
        registered_input, registered_output);

REGISTER_OUTPUT_NODES:
    for (int node = 0; node < NUM_NODES; ++node) {
#pragma HLS UNROLL
    REGISTER_OUTPUT_FEATURES:
        for (int feature = 0; feature < OUT_FEATURES; ++feature) {
#pragma HLS UNROLL
            output[node][feature] = registered_output[node][feature];
        }
    }
}
#elif defined(USE_CONST_ADJ)
void graphsage_int8_po2(
    const data_t input[NUM_NODES][IN_FEATURES],
    const weight_t weights1[HIDDEN_FEATURES][IN_FEATURES],
    const bias_t bias1[HIDDEN_FEATURES],
    const weight_t weights2[OUT_FEATURES][HIDDEN_FEATURES],
    const bias_t bias2[OUT_FEATURES],
    data_t output[NUM_NODES][OUT_FEATURES]
) {
#pragma HLS PIPELINE II=1
#pragma HLS INTERFACE mode=ap_none port=input register
#pragma HLS INTERFACE mode=ap_none port=weights1
#pragma HLS INTERFACE mode=ap_none port=bias1
#pragma HLS INTERFACE mode=ap_none port=weights2
#pragma HLS INTERFACE mode=ap_none port=bias2
#pragma HLS INTERFACE mode=ap_none port=output register
#pragma HLS INTERFACE mode=ap_ctrl_hs port=return
#pragma HLS ARRAY_PARTITION variable=input complete dim=1
#pragma HLS ARRAY_PARTITION variable=input complete dim=2
#pragma HLS ARRAY_PARTITION variable=weights1 complete dim=1
#pragma HLS ARRAY_PARTITION variable=weights1 complete dim=2
#pragma HLS ARRAY_PARTITION variable=bias1 complete
#pragma HLS ARRAY_PARTITION variable=weights2 complete dim=1
#pragma HLS ARRAY_PARTITION variable=weights2 complete dim=2
#pragma HLS ARRAY_PARTITION variable=bias2 complete
#pragma HLS ARRAY_PARTITION variable=output complete dim=1
#pragma HLS ARRAY_PARTITION variable=output complete dim=2

    graphsage_int8_po2_const_adj_template<
        NUM_NODES, IN_FEATURES, HIDDEN_FEATURES, OUT_FEATURES>(
        input, weights1, bias1, weights2, bias2, output);
}
#else
void graphsage_int8_po2(
    const adj_t adj_matrix[NUM_NODES][NUM_NODES],
    const data_t input[NUM_NODES][IN_FEATURES],
    const weight_t weights1[HIDDEN_FEATURES][IN_FEATURES],
    const bias_t bias1[HIDDEN_FEATURES],
    const weight_t weights2[OUT_FEATURES][HIDDEN_FEATURES],
    const bias_t bias2[OUT_FEATURES],
    data_t output[NUM_NODES][OUT_FEATURES]
) {
#pragma HLS PIPELINE II=1
#pragma HLS INTERFACE mode=ap_none port=adj_matrix
#pragma HLS INTERFACE mode=ap_none port=input
#pragma HLS INTERFACE mode=ap_none port=weights1
#pragma HLS INTERFACE mode=ap_none port=bias1
#pragma HLS INTERFACE mode=ap_none port=weights2
#pragma HLS INTERFACE mode=ap_none port=bias2
#pragma HLS INTERFACE mode=ap_none port=output
#pragma HLS INTERFACE mode=ap_ctrl_hs port=return
#pragma HLS ARRAY_PARTITION variable=adj_matrix complete
#pragma HLS ARRAY_PARTITION variable=input complete
#pragma HLS ARRAY_PARTITION variable=weights1 complete
#pragma HLS ARRAY_PARTITION variable=bias1 complete
#pragma HLS ARRAY_PARTITION variable=weights2 complete
#pragma HLS ARRAY_PARTITION variable=bias2 complete
#pragma HLS ARRAY_PARTITION variable=output complete

    graphsage_int8_po2_template<
        NUM_NODES, IN_FEATURES, HIDDEN_FEATURES, OUT_FEATURES>(
        adj_matrix, input, weights1, bias1, weights2, bias2, output);
}
#endif