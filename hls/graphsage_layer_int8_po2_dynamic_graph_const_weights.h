#pragma once

#include "graphsage_layer_int8_po2_19c_base.h"
#include "graphsage_layer_int8_po2_19c_constants.h"

typedef ap_uint<NUM_NODES> edge_mask_t;
typedef ap_uint<4> degree_t;
typedef ap_int<9> neighbor_pair_t;
typedef ap_int<10> neighbor_quad_t;
typedef ap_int<11> neighbor_sum_t;

inline degree_t edge_mask_popcount(edge_mask_t mask) {
#pragma HLS INLINE
    ap_uint<2> pair0 = mask[0] + mask[1];
    ap_uint<2> pair1 = mask[2] + mask[3];
    ap_uint<2> pair2 = mask[4] + mask[5];
    ap_uint<2> pair3 = mask[6] + mask[7];
    ap_uint<3> quad0 = pair0 + pair1;
    ap_uint<3> quad1 = pair2 + pair3;
    return degree_t(quad0 + quad1);
}

inline neighbor_sum_t select_and_sum_neighbors(
    const data_t features[NUM_NODES],
    edge_mask_t mask
) {
#pragma HLS INLINE
    const neighbor_pair_t pair0 =
        neighbor_pair_t(mask[0] ? features[0] : data_t(0)) +
        neighbor_pair_t(mask[1] ? features[1] : data_t(0));
    const neighbor_pair_t pair1 =
        neighbor_pair_t(mask[2] ? features[2] : data_t(0)) +
        neighbor_pair_t(mask[3] ? features[3] : data_t(0));
    const neighbor_pair_t pair2 =
        neighbor_pair_t(mask[4] ? features[4] : data_t(0)) +
        neighbor_pair_t(mask[5] ? features[5] : data_t(0));
    const neighbor_pair_t pair3 =
        neighbor_pair_t(mask[6] ? features[6] : data_t(0)) +
        neighbor_pair_t(mask[7] ? features[7] : data_t(0));
    const neighbor_quad_t quad0 = neighbor_quad_t(pair0) + neighbor_quad_t(pair1);
    const neighbor_quad_t quad1 = neighbor_quad_t(pair2) + neighbor_quad_t(pair3);
    return neighbor_sum_t(quad0) + neighbor_sum_t(quad1);
}

template<int SHIFT_AMOUNT>
inline data_t normalize_neighbor_sum(neighbor_sum_t neighbor_sum, degree_t degree) {
#pragma HLS INLINE
    acc_t weighted_sum = 0;

    switch (degree) {
    case 0:
        break;
    case 1:
        weighted_sum = acc_t(neighbor_sum) << 12;
        break;
    case 2:
        weighted_sum = acc_t(neighbor_sum) << 11;
        break;
    case 4:
        weighted_sum = acc_t(neighbor_sum) << 10;
        break;
    case 8:
        weighted_sum = acc_t(neighbor_sum) << 9;
        break;
    default: {
        ap_uint<11> degree_scale;
        switch (degree) {
        case 3: degree_scale = 1365; break;
        case 5: degree_scale = 819; break;
        case 6: degree_scale = 682; break;
        default: degree_scale = 585; break;
        }
        acc_t scaled_sum;
#pragma HLS BIND_OP variable=scaled_sum op=mul impl=dsp latency=3
        scaled_sum = acc_t(neighbor_sum) * degree_scale;
        weighted_sum = scaled_sum;
        break;
    }
    }

    const acc_t round_const = acc_t(1) << (SHIFT_AMOUNT - 1);
    return int8_clamp((weighted_sum + round_const) >> SHIFT_AMOUNT);
}

template<int N_FEAT, int SHIFT_AMOUNT>
void aggregate_dynamic_mean(
    const data_t features[NUM_NODES][N_FEAT],
    const edge_mask_t edge_masks[NUM_NODES],
    data_t agg_out[NUM_NODES][N_FEAT]
) {
#pragma HLS INLINE
    degree_t degrees[NUM_NODES];
#pragma HLS ARRAY_PARTITION variable=degrees complete

DEGREE_NODE:
    for (int node = 0; node < NUM_NODES; ++node) {
#pragma HLS UNROLL
        degrees[node] = edge_mask_popcount(edge_masks[node]);
    }

AGG_NODE:
    for (int node = 0; node < NUM_NODES; ++node) {
#pragma HLS UNROLL
    AGG_FEATURE:
        for (int feature = 0; feature < N_FEAT; ++feature) {
#pragma HLS UNROLL
            data_t feature_column[NUM_NODES];
#pragma HLS ARRAY_PARTITION variable=feature_column complete
        COPY_FEATURE_COLUMN:
            for (int neighbor = 0; neighbor < NUM_NODES; ++neighbor) {
#pragma HLS UNROLL
                feature_column[neighbor] = features[neighbor][feature];
            }

            const neighbor_sum_t neighbor_sum =
                select_and_sum_neighbors(feature_column, edge_masks[node]);
            agg_out[node][feature] =
                normalize_neighbor_sum<SHIFT_AMOUNT>(neighbor_sum, degrees[node]);
        }
    }
}

template<int N_NODES, int IN_FEAT, int HIDDEN_FEAT, int OUT_FEAT>
void graphsage_dynamic_graph_const_weights_template(
    const data_t input[N_NODES][IN_FEAT],
    const edge_mask_t edge_masks[N_NODES],
    data_t output[N_NODES][OUT_FEAT]
) {
    static_assert(N_NODES == NUM_NODES, "Dynamic graph masks require NUM_NODES nodes");
#pragma HLS ARRAY_PARTITION variable=CONST_WEIGHTS1 complete
#pragma HLS ARRAY_PARTITION variable=CONST_BIAS1 complete
#pragma HLS ARRAY_PARTITION variable=CONST_WEIGHTS2 complete
#pragma HLS ARRAY_PARTITION variable=CONST_BIAS2 complete

    data_t agg1[N_NODES][IN_FEAT];
    data_t hidden[N_NODES][HIDDEN_FEAT];
    data_t agg2[N_NODES][HIDDEN_FEAT];
#pragma HLS ARRAY_PARTITION variable=agg1 complete dim=1
#pragma HLS ARRAY_PARTITION variable=agg1 complete dim=2
#pragma HLS ARRAY_PARTITION variable=hidden complete dim=1
#pragma HLS ARRAY_PARTITION variable=hidden complete dim=2
#pragma HLS ARRAY_PARTITION variable=agg2 complete dim=1
#pragma HLS ARRAY_PARTITION variable=agg2 complete dim=2

    aggregate_dynamic_mean<IN_FEAT, BETA1_SHIFT>(input, edge_masks, agg1);
    linear_int8_po2<N_NODES, IN_FEAT, HIDDEN_FEAT>(
        agg1, CONST_WEIGHTS1, CONST_BIAS1, hidden, EFF_SCALE1_SHIFT);
    relu_int8<N_NODES, HIDDEN_FEAT>(hidden);
    aggregate_dynamic_mean<HIDDEN_FEAT, BETA2_SHIFT>(hidden, edge_masks, agg2);
    linear_int8_po2<N_NODES, HIDDEN_FEAT, OUT_FEAT>(
        agg2, CONST_WEIGHTS2, CONST_BIAS2, output, EFF_SCALE2_SHIFT);
}

void graphsage_dynamic_graph_const_weights(
    const data_t input[NUM_NODES][IN_FEATURES],
    const edge_mask_t edge_masks[NUM_NODES],
    data_t output[NUM_NODES][OUT_FEATURES]);