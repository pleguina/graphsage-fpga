#pragma once

#include "graphsage_layer_int8_po2_19c_base.h"
#include "graphsage_layer_int8_po2_19c_constants.h"

static constexpr int CONST_ADJ_ROW_VALUE[NUM_NODES] = {
    1365, 1365, 4096, 4096, 1365, 1024, 2048, 1365,
};

static constexpr int CONST_ADJ_ROW_LOG2[NUM_NODES] = {
    -1, -1, 12, 12, -1, 10, 11, -1,
};

template<int ROW, int N_FEAT, int SHIFT_AMOUNT>
void aggregate_const_row(
    const data_t features[NUM_NODES][N_FEAT],
    data_t agg_out[NUM_NODES][N_FEAT]
) {
#pragma HLS INLINE

ROW_FEATURE:
    for (int feature = 0; feature < N_FEAT; ++feature) {
#pragma HLS UNROLL
        acc_t neighbor_sum = 0;

        if constexpr (CONST_ADJ[ROW][0] != 0) neighbor_sum += features[0][feature];
        if constexpr (CONST_ADJ[ROW][1] != 0) neighbor_sum += features[1][feature];
        if constexpr (CONST_ADJ[ROW][2] != 0) neighbor_sum += features[2][feature];
        if constexpr (CONST_ADJ[ROW][3] != 0) neighbor_sum += features[3][feature];
        if constexpr (CONST_ADJ[ROW][4] != 0) neighbor_sum += features[4][feature];
        if constexpr (CONST_ADJ[ROW][5] != 0) neighbor_sum += features[5][feature];
        if constexpr (CONST_ADJ[ROW][6] != 0) neighbor_sum += features[6][feature];
        if constexpr (CONST_ADJ[ROW][7] != 0) neighbor_sum += features[7][feature];

        acc_t result;
        if constexpr (CONST_ADJ_ROW_LOG2[ROW] >= 0) {
            constexpr int effective_shift = SHIFT_AMOUNT - CONST_ADJ_ROW_LOG2[ROW];
            static_assert(effective_shift >= 0, "Adjacency shift exceeds PO2 rescale shift");
            if constexpr (effective_shift == 0) {
                result = neighbor_sum;
            } else {
                const acc_t round_const = acc_t(1) << (effective_shift - 1);
                result = (neighbor_sum + round_const) >> effective_shift;
            }
        } else {
            const acc_t weighted_sum = neighbor_sum * CONST_ADJ_ROW_VALUE[ROW];
            const acc_t round_const = acc_t(1) << (SHIFT_AMOUNT - 1);
            result = (weighted_sum + round_const) >> SHIFT_AMOUNT;
        }

        agg_out[ROW][feature] = int8_clamp(result);

#ifndef __SYNTHESIS__
        if (ROW == 6 && feature < 3) {
            printf("  AGG_CONST: node=%d feat=%d sum=%d result=%d out=%d\n",
                   ROW, feature, (int)neighbor_sum, (int)result,
                   (int)agg_out[ROW][feature]);
        }
#endif
    }
}

template<int N_FEAT, int SHIFT_AMOUNT>
void aggregate_int8_po2_const(
    const data_t features[NUM_NODES][N_FEAT],
    data_t agg_out[NUM_NODES][N_FEAT]
) {
#pragma HLS INLINE
    aggregate_const_row<0, N_FEAT, SHIFT_AMOUNT>(features, agg_out);
    aggregate_const_row<1, N_FEAT, SHIFT_AMOUNT>(features, agg_out);
    aggregate_const_row<2, N_FEAT, SHIFT_AMOUNT>(features, agg_out);
    aggregate_const_row<3, N_FEAT, SHIFT_AMOUNT>(features, agg_out);
    aggregate_const_row<4, N_FEAT, SHIFT_AMOUNT>(features, agg_out);
    aggregate_const_row<5, N_FEAT, SHIFT_AMOUNT>(features, agg_out);
    aggregate_const_row<6, N_FEAT, SHIFT_AMOUNT>(features, agg_out);
    aggregate_const_row<7, N_FEAT, SHIFT_AMOUNT>(features, agg_out);
}

template<int N_NODES, int IN_FEAT, int HIDDEN_FEAT, int OUT_FEAT>
void graphsage_int8_po2_const_adj_template(
    const data_t input[N_NODES][IN_FEAT],
    const weight_t weights1[HIDDEN_FEAT][IN_FEAT],
    const bias_t bias1[HIDDEN_FEAT],
    const weight_t weights2[OUT_FEAT][HIDDEN_FEAT],
    const bias_t bias2[OUT_FEAT],
    data_t output[N_NODES][OUT_FEAT]
) {
    static_assert(N_NODES == NUM_NODES, "Constant adjacency is fixed to NUM_NODES");

    data_t agg1[N_NODES][IN_FEAT];
    data_t hidden[N_NODES][HIDDEN_FEAT];
    data_t agg2[N_NODES][HIDDEN_FEAT];
#pragma HLS ARRAY_PARTITION variable=agg1 complete
#pragma HLS ARRAY_PARTITION variable=hidden complete
#pragma HLS ARRAY_PARTITION variable=agg2 complete

#ifndef __SYNTHESIS__
    printf("\n=== INT8-PO2 CONST: LAYER 1 AGGREGATION (shift=%d) ===\n", BETA1_SHIFT);
#endif
    aggregate_int8_po2_const<IN_FEAT, BETA1_SHIFT>(input, agg1);
    linear_int8_po2<N_NODES, IN_FEAT, HIDDEN_FEAT>(
        agg1, weights1, bias1, hidden, EFF_SCALE1_SHIFT);
    relu_int8<N_NODES, HIDDEN_FEAT>(hidden);

#ifndef __SYNTHESIS__
    printf("\n=== INT8-PO2 CONST: LAYER 2 AGGREGATION (shift=%d) ===\n", BETA2_SHIFT);
#endif
    aggregate_int8_po2_const<HIDDEN_FEAT, BETA2_SHIFT>(hidden, agg2);
    linear_int8_po2<N_NODES, HIDDEN_FEAT, OUT_FEAT>(
        agg2, weights2, bias2, output, EFF_SCALE2_SHIFT);
}

template<int N_NODES, int IN_FEAT, int HIDDEN_FEAT, int OUT_FEAT>
void graphsage_int8_po2_const_template(
    const data_t input[N_NODES][IN_FEAT],
    data_t output[N_NODES][OUT_FEAT]
) {
#pragma HLS ARRAY_PARTITION variable=CONST_WEIGHTS1 complete
#pragma HLS ARRAY_PARTITION variable=CONST_BIAS1 complete
#pragma HLS ARRAY_PARTITION variable=CONST_WEIGHTS2 complete
#pragma HLS ARRAY_PARTITION variable=CONST_BIAS2 complete

    graphsage_int8_po2_const_adj_template<N_NODES, IN_FEAT, HIDDEN_FEAT, OUT_FEAT>(
        input, CONST_WEIGHTS1, CONST_BIAS1, CONST_WEIGHTS2, CONST_BIAS2, output);
}