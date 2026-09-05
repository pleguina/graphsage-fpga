#pragma once

#include <ap_int.h>

// GS_NUM_NODES is fixed at 8: the aggregator's popcount/reduction tree below
// is hand-unrolled for exactly 8 neighbors (mask[0..7], features[0..7]) and
// the degree normalizer only covers degrees 1-8. Changing this macro alone
// does NOT generalize the datapath; it exists for naming/documentation only.
#ifndef GS_NUM_NODES
#define GS_NUM_NODES 8
#endif
#ifndef GS_IN_FEATURES
#define GS_IN_FEATURES 16
#endif
#ifndef GS_HIDDEN_FEATURES
#define GS_HIDDEN_FEATURES 24
#endif
#ifndef GS_OUT_FEATURES
#define GS_OUT_FEATURES 7
#endif

static constexpr int ROOT_NUM_NODES = GS_NUM_NODES;
static constexpr int ROOT_IN_FEATURES = GS_IN_FEATURES;
static constexpr int ROOT_HIDDEN_FEATURES = GS_HIDDEN_FEATURES;
static constexpr int ROOT_OUT_FEATURES = GS_OUT_FEATURES;

typedef ap_int<8> data_t;
typedef ap_int<8> weight_t;
typedef ap_int<32> bias_t;
typedef ap_int<32> acc_t;
typedef ap_int<48> scale_acc_t;
typedef ap_uint<ROOT_NUM_NODES> edge_mask_t;
typedef ap_uint<4> degree_t;
typedef ap_int<11> neighbor_sum_t;

// Named aggregation-path architectures (see root_dynamic_mean below).
#define GS_AGG_MONOLITHIC_DSP 0
#define GS_AGG_SPLIT_DSP       1
#define GS_AGG_DECODED         2
#define GS_AGG_SPLIT_DECODED   3
#define GS_AGG_PIPELINED_DSP   4

// Final frozen architecture (V2-A1): monolithic aggregation with a one-cycle
// registered add ahead of the DSP normalizer. Callers that need a different
// mode (sweeps, ablations) override this via -DROOT_AGGREGATION_MODE=<mode>.
#ifndef ROOT_AGGREGATION_MODE
#define ROOT_AGGREGATION_MODE GS_AGG_PIPELINED_DSP
#endif

// BIND_OP latencies for the aggregation path's final add and DSP normalizer,
// overridable independently of ROOT_AGGREGATION_MODE for reproducibility.
#ifndef GS_AGG_ADD_LATENCY
#define GS_AGG_ADD_LATENCY 1
#endif
#ifndef GS_AGG_DSP_LATENCY
#define GS_AGG_DSP_LATENCY 4
#endif

// Generic latency for every other fabric/DSP multiplier BIND_OP in the
// design (channel MACs, decoded-product normalizer). -1 means "no explicit
// latency", i.e. the unchanged HLS-scheduled behavior that produced every
// frozen V1-V4/V2/V2-A1/F2 result; override with a non-negative integer via
// -D to force a specific pipeline latency.
#ifndef GS_FABRIC_MUL_LATENCY
#define GS_FABRIC_MUL_LATENCY -1
#endif
#ifndef GS_DSP_MUL_LATENCY
#define GS_DSP_MUL_LATENCY -1
#endif

#ifndef ROOT_CONSTANTS_HEADER
#define ROOT_CONSTANTS_HEADER "generated/root_graphsage_constants.h"
#endif
#include ROOT_CONSTANTS_HEADER

inline data_t root_int8_clamp(scale_acc_t value) {
#pragma HLS INLINE
    if (value > 127) return data_t(127);
    if (value < -128) return data_t(-128);
    return data_t(value);
}

inline degree_t root_popcount(edge_mask_t mask) {
#pragma HLS INLINE
    ap_uint<2> pair0 = mask[0] + mask[1];
    ap_uint<2> pair1 = mask[2] + mask[3];
    ap_uint<2> pair2 = mask[4] + mask[5];
    ap_uint<2> pair3 = mask[6] + mask[7];
    ap_uint<3> quad0 = pair0 + pair1;
    ap_uint<3> quad1 = pair2 + pair3;
    return degree_t(quad0 + quad1);
}

inline ap_uint<13> root_degree_scale(degree_t degree) {
#pragma HLS INLINE
    switch (degree) {
    case 1: return 4096;
    case 2: return 2048;
    case 3: return 1365;
    case 4: return 1024;
    case 5: return 819;
    case 6: return 683;
    case 7: return 585;
    case 8: return 512;
    default: return 0;
    }
}

template<int N_FEAT>
void root_dynamic_reduce(
    const data_t features[ROOT_NUM_NODES][N_FEAT],
    const edge_mask_t masks[ROOT_NUM_NODES],
    neighbor_sum_t sums[ROOT_NUM_NODES][N_FEAT],
    degree_t degrees[ROOT_NUM_NODES]
) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
#pragma HLS ARRAY_PARTITION variable=sums complete
#pragma HLS ARRAY_PARTITION variable=degrees complete
ROOT_REDUCE_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
        degrees[node] = root_popcount(masks[node]);
    ROOT_REDUCE_FEATURE:
        for (int feature = 0; feature < N_FEAT; ++feature) {
#pragma HLS UNROLL
            const ap_int<9> pair0 = ap_int<9>(masks[node][0] ? features[0][feature] : data_t(0)) +
                                    ap_int<9>(masks[node][1] ? features[1][feature] : data_t(0));
            const ap_int<9> pair1 = ap_int<9>(masks[node][2] ? features[2][feature] : data_t(0)) +
                                    ap_int<9>(masks[node][3] ? features[3][feature] : data_t(0));
            const ap_int<9> pair2 = ap_int<9>(masks[node][4] ? features[4][feature] : data_t(0)) +
                                    ap_int<9>(masks[node][5] ? features[5][feature] : data_t(0));
            const ap_int<9> pair3 = ap_int<9>(masks[node][6] ? features[6][feature] : data_t(0)) +
                                    ap_int<9>(masks[node][7] ? features[7][feature] : data_t(0));
            const ap_int<10> half0 = ap_int<10>(pair0) + pair1;
            const ap_int<10> half1 = ap_int<10>(pair2) + pair3;
            neighbor_sum_t sum;
            // Explicit one-cycle fabric add: forces a real FF boundary before the DSP input.
#pragma HLS BIND_OP variable=sum op=add impl=fabric latency=GS_AGG_ADD_LATENCY
            sum = neighbor_sum_t(half0) + neighbor_sum_t(half1);
            sums[node][feature] = sum;
        }
    }
}

inline acc_t root_degree_decoded_product(neighbor_sum_t sum, degree_t degree) {
#pragma HLS INLINE
    switch (degree) {
    case 1: {
        acc_t product;
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=product op=mul impl=fabric
#endif
        product = acc_t(sum) * 4096;
        return product;
    }
    case 2: {
        acc_t product;
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=product op=mul impl=fabric
#endif
        product = acc_t(sum) * 2048;
        return product;
    }
    case 3: {
        acc_t product;
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=product op=mul impl=fabric
#endif
        product = acc_t(sum) * 1365;
        return product;
    }
    case 4: {
        acc_t product;
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=product op=mul impl=fabric
#endif
        product = acc_t(sum) * 1024;
        return product;
    }
    case 5: {
        acc_t product;
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=product op=mul impl=fabric
#endif
        product = acc_t(sum) * 819;
        return product;
    }
    case 6: {
        acc_t product;
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=product op=mul impl=fabric
#endif
        product = acc_t(sum) * 683;
        return product;
    }
    case 7: {
        acc_t product;
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=product op=mul impl=fabric
#endif
        product = acc_t(sum) * 585;
        return product;
    }
    case 8: {
        acc_t product;
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=product op=mul impl=fabric
#endif
        product = acc_t(sum) * 512;
        return product;
    }
    default: return 0;
    }
}

template<int N_FEAT, int SHIFT, bool DECODED>
void root_dynamic_normalize(
    const neighbor_sum_t sums[ROOT_NUM_NODES][N_FEAT],
    const degree_t degrees[ROOT_NUM_NODES],
    data_t output[ROOT_NUM_NODES][N_FEAT]
) {
#pragma HLS INLINE off
#pragma HLS PIPELINE II=1
#pragma HLS ARRAY_PARTITION variable=sums complete
#pragma HLS ARRAY_PARTITION variable=degrees complete
ROOT_NORMALIZE_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
    ROOT_NORMALIZE_FEATURE:
        for (int feature = 0; feature < N_FEAT; ++feature) {
#pragma HLS UNROLL
            acc_t weighted_sum;
            if constexpr (DECODED) {
                weighted_sum = root_degree_decoded_product(sums[node][feature], degrees[node]);
            } else {
                const ap_uint<13> scale = root_degree_scale(degrees[node]);
#pragma HLS BIND_OP variable=weighted_sum op=mul impl=dsp latency=GS_AGG_DSP_LATENCY
                weighted_sum = acc_t(sums[node][feature]) * scale;
            }
            output[node][feature] = root_int8_clamp(
                (scale_acc_t(weighted_sum) + (scale_acc_t(1) << (SHIFT - 1))) >> SHIFT);
        }
    }
}

template<int N_FEAT, int SHIFT>
void root_dynamic_mean(
    const data_t features[ROOT_NUM_NODES][N_FEAT],
    const edge_mask_t masks[ROOT_NUM_NODES],
    data_t output[ROOT_NUM_NODES][N_FEAT]
) {
#if ROOT_AGGREGATION_MODE == 1 || ROOT_AGGREGATION_MODE == 3
#pragma HLS INLINE off
    neighbor_sum_t sums[ROOT_NUM_NODES][N_FEAT];
    degree_t degrees[ROOT_NUM_NODES];
#pragma HLS ARRAY_PARTITION variable=sums complete
#pragma HLS ARRAY_PARTITION variable=degrees complete
    root_dynamic_reduce<N_FEAT>(features, masks, sums, degrees);
    root_dynamic_normalize<N_FEAT, SHIFT, ROOT_AGGREGATION_MODE == 3>(sums, degrees, output);
#else
#pragma HLS INLINE
ROOT_AGG_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
        const degree_t degree = root_popcount(masks[node]);
        const ap_uint<13> scale = root_degree_scale(degree);
    ROOT_AGG_FEATURE:
        for (int feature = 0; feature < N_FEAT; ++feature) {
#pragma HLS UNROLL
            const ap_int<9> pair0 = ap_int<9>(masks[node][0] ? features[0][feature] : data_t(0)) +
                                            ap_int<9>(masks[node][1] ? features[1][feature] : data_t(0));
            const ap_int<9> pair1 = ap_int<9>(masks[node][2] ? features[2][feature] : data_t(0)) +
                                            ap_int<9>(masks[node][3] ? features[3][feature] : data_t(0));
            const ap_int<9> pair2 = ap_int<9>(masks[node][4] ? features[4][feature] : data_t(0)) +
                                            ap_int<9>(masks[node][5] ? features[5][feature] : data_t(0));
            const ap_int<9> pair3 = ap_int<9>(masks[node][6] ? features[6][feature] : data_t(0)) +
                                            ap_int<9>(masks[node][7] ? features[7][feature] : data_t(0));
            const ap_int<10> half0 = ap_int<10>(pair0) + pair1;
            const ap_int<10> half1 = ap_int<10>(pair2) + pair3;
#if ROOT_AGGREGATION_MODE == 4
            neighbor_sum_t sum;
            // V2-A1: one-cycle fabric add, still a single monolithic function (no split, no DATAFLOW).
#pragma HLS BIND_OP variable=sum op=add impl=fabric latency=GS_AGG_ADD_LATENCY
            sum = neighbor_sum_t(half0) + neighbor_sum_t(half1);
#else
            const neighbor_sum_t sum = neighbor_sum_t(half0) + neighbor_sum_t(half1);
#endif
            acc_t weighted_sum;
#if ROOT_AGGREGATION_MODE == 2
            weighted_sum = root_degree_decoded_product(sum, degree);
#else
#pragma HLS BIND_OP variable=weighted_sum op=mul impl=dsp latency=GS_AGG_DSP_LATENCY
            weighted_sum = acc_t(sum) * scale;
#endif
            output[node][feature] = root_int8_clamp(
                (scale_acc_t(weighted_sum) + (scale_acc_t(1) << (SHIFT - 1))) >> SHIFT);
        }
    }
#endif
}

template<int IN_FEAT, int OUT_FEAT, int NEIGHBOR_SHIFT, int ROOT_SHIFT>
void root_dual_linear(
    const data_t aggregate_input[ROOT_NUM_NODES][IN_FEAT],
    const data_t root_input[ROOT_NUM_NODES][IN_FEAT],
    const weight_t neighbor_weights[OUT_FEAT][IN_FEAT],
    const weight_t root_weights[OUT_FEAT][IN_FEAT],
    const bias_t bias[OUT_FEAT],
    data_t output[ROOT_NUM_NODES][OUT_FEAT]
) {
#pragma HLS INLINE
ROOT_LINEAR_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
    ROOT_LINEAR_OUTPUT:
        for (int out_feature = 0; out_feature < OUT_FEAT; ++out_feature) {
#pragma HLS UNROLL
            acc_t neighbor_acc = bias[out_feature];
            acc_t root_acc = 0;
        ROOT_LINEAR_INPUT:
            for (int in_feature = 0; in_feature < IN_FEAT; ++in_feature) {
#pragma HLS UNROLL
                ap_int<16> neighbor_product;
                ap_int<16> root_product;
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#pragma HLS BIND_OP variable=root_product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=fabric
#pragma HLS BIND_OP variable=root_product op=mul impl=fabric
#endif
                neighbor_product = aggregate_input[node][in_feature] * neighbor_weights[out_feature][in_feature];
                root_product = root_input[node][in_feature] * root_weights[out_feature][in_feature];
                neighbor_acc += neighbor_product;
                root_acc += root_product;
            }
            const data_t neighbor_output = root_int8_clamp(
                (scale_acc_t(neighbor_acc) + (scale_acc_t(1) << (NEIGHBOR_SHIFT - 1))) >> NEIGHBOR_SHIFT);
            const data_t root_output = root_int8_clamp(
                (scale_acc_t(root_acc) + (scale_acc_t(1) << (ROOT_SHIFT - 1))) >> ROOT_SHIFT);
            output[node][out_feature] = root_int8_clamp(
                scale_acc_t(neighbor_output) + scale_acc_t(root_output));
        }
    }
}

template<int IN_FEAT, int OUT_FEAT, int NEIGHBOR_SHIFT, int ROOT_SHIFT>
void root_dual_linear_dsp(
    const data_t aggregate_input[ROOT_NUM_NODES][IN_FEAT],
    const data_t root_input[ROOT_NUM_NODES][IN_FEAT],
    const weight_t neighbor_weights[OUT_FEAT][IN_FEAT],
    const weight_t root_weights[OUT_FEAT][IN_FEAT],
    const bias_t bias[OUT_FEAT],
    data_t output[ROOT_NUM_NODES][OUT_FEAT]
) {
#pragma HLS INLINE
ROOT_DSP_LINEAR_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
    ROOT_DSP_LINEAR_OUTPUT:
        for (int out_feature = 0; out_feature < OUT_FEAT; ++out_feature) {
#pragma HLS UNROLL
            acc_t neighbor_acc = bias[out_feature];
            acc_t root_acc = 0;
        ROOT_DSP_LINEAR_INPUT:
            for (int in_feature = 0; in_feature < IN_FEAT; ++in_feature) {
#pragma HLS UNROLL
                ap_int<16> neighbor_product;
                ap_int<16> root_product;
#if GS_DSP_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=dsp latency=GS_DSP_MUL_LATENCY
#pragma HLS BIND_OP variable=root_product op=mul impl=dsp latency=GS_DSP_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=dsp
#pragma HLS BIND_OP variable=root_product op=mul impl=dsp
#endif
                neighbor_product = aggregate_input[node][in_feature] * neighbor_weights[out_feature][in_feature];
                root_product = root_input[node][in_feature] * root_weights[out_feature][in_feature];
                neighbor_acc += neighbor_product;
                root_acc += root_product;
            }
            const data_t neighbor_output = root_int8_clamp(
                (scale_acc_t(neighbor_acc) + (scale_acc_t(1) << (NEIGHBOR_SHIFT - 1))) >> NEIGHBOR_SHIFT);
            const data_t root_output = root_int8_clamp(
                (scale_acc_t(root_acc) + (scale_acc_t(1) << (ROOT_SHIFT - 1))) >> ROOT_SHIFT);
            output[node][out_feature] = root_int8_clamp(
                scale_acc_t(neighbor_output) + scale_acc_t(root_output));
        }
    }
}

void graphsage_root_dynamic_const_weights(
    const data_t input[ROOT_NUM_NODES][ROOT_IN_FEATURES],
    const edge_mask_t edge_masks[ROOT_NUM_NODES],
    data_t output[ROOT_NUM_NODES][ROOT_OUT_FEATURES]);