#include "graphsage_layer_int8_po2_ii2_reuse.h"

void graphsage_int8_po2(
    const adj_t    adj_matrix[NUM_NODES][NUM_NODES],
    const data_t   input[NUM_NODES][IN_FEATURES],
    const weight_t weights1[HIDDEN_FEATURES][IN_FEATURES],
    const bias_t   bias1[HIDDEN_FEATURES],
    const weight_t weights2[OUT_FEATURES][HIDDEN_FEATURES],
    const bias_t   bias2[OUT_FEATURES],
    data_t         output[NUM_NODES][OUT_FEATURES]
) {
#pragma HLS PIPELINE II=DSE_TOP_II

    // Preserve the fully distributed tensor interface of the submitted design.
#pragma HLS ARRAY_PARTITION variable=adj_matrix complete dim=1
#pragma HLS ARRAY_PARTITION variable=adj_matrix complete dim=2
#pragma HLS ARRAY_PARTITION variable=input complete dim=1
#pragma HLS ARRAY_PARTITION variable=input complete dim=2
#pragma HLS ARRAY_PARTITION variable=weights1 complete dim=1
#pragma HLS ARRAY_PARTITION variable=weights1 complete dim=2
#pragma HLS ARRAY_PARTITION variable=bias1 complete dim=1
#pragma HLS ARRAY_PARTITION variable=weights2 complete dim=1
#pragma HLS ARRAY_PARTITION variable=weights2 complete dim=2
#pragma HLS ARRAY_PARTITION variable=bias2 complete dim=1
#pragma HLS ARRAY_PARTITION variable=output complete dim=1
#pragma HLS ARRAY_PARTITION variable=output complete dim=2

    static_assert(NUM_NODES == 8,
                  "Default II=2 sharing limits are calculated for NUM_NODES=8");
    static_assert(IN_FEATURES == 16,
                  "Default II=2 sharing limits are calculated for IN_FEATURES=16");
    static_assert(HIDDEN_FEATURES == 24,
                  "Default II=2 sharing limits are calculated for HIDDEN_FEATURES=24");
    static_assert(OUT_FEATURES == 7,
                  "Default II=2 sharing limits are calculated for OUT_FEATURES=7");

    graphsage_int8_po2_template<
        NUM_NODES,
        IN_FEATURES,
        HIDDEN_FEATURES,
        OUT_FEATURES
    >(adj_matrix, input, weights1, bias1, weights2, bias2, output);
}
