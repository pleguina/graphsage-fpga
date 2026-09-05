#pragma once

#define ROOT_CONSTANTS_HEADER "../po2_qat_root_dynamic_const_weights/generated/root_graphsage_constants.h"
#include "../root_dynamic_const_weights/graphsage_root_dynamic_const_weights.h"

// Compile-time masks: bit OUT_FEATURE selects the corresponding branch/channel for DSP.
// Overridable at HLS compile time via -D so each sweep variant reuses this same source.
#ifndef L1_ROOT_DSP_MASK
#define L1_ROOT_DSP_MASK 0u
#endif
#ifndef L1_NEIGHBOR_DSP_MASK
#define L1_NEIGHBOR_DSP_MASK 0u
#endif
#ifndef L2_ROOT_DSP_MASK
#define L2_ROOT_DSP_MASK 0u
#endif
#ifndef L2_NEIGHBOR_DSP_MASK
#define L2_NEIGHBOR_DSP_MASK 0u
#endif
// F2: optional one-cycle registered combine for the channel accumulator,
// used to break a CARRY8-dominated reduction path before it fans out further.
#ifndef L1_NEIGHBOR_ACC_PIPELINE_MASK
#define L1_NEIGHBOR_ACC_PIPELINE_MASK 0u
#endif

template<bool USE_DSP, int OUT>
void l1_root_channel(
    const data_t root_input[ROOT_NUM_NODES][ROOT_IN_FEATURES],
    data_t output[ROOT_NUM_NODES]
) {
#pragma HLS INLINE off
L1_ROOT_CHANNEL_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
        acc_t root_acc = 0;
    L1_ROOT_CHANNEL_INPUT:
        for (int in_feature = 0; in_feature < ROOT_IN_FEATURES; ++in_feature) {
#pragma HLS UNROLL
            ap_int<16> root_product;
            if constexpr (USE_DSP) {
#if GS_DSP_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=root_product op=mul impl=dsp latency=GS_DSP_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=root_product op=mul impl=dsp
#endif
                root_product = root_input[node][in_feature] * ROOT_WEIGHTS1_ROOT[OUT][in_feature];
            } else {
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=root_product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=root_product op=mul impl=fabric
#endif
                root_product = root_input[node][in_feature] * ROOT_WEIGHTS1_ROOT[OUT][in_feature];
            }
            root_acc += root_product;
        }
        output[node] = root_int8_clamp(
            (scale_acc_t(root_acc) + (scale_acc_t(1) << (ROOT_LAYER1_ROOT_SHIFT - 1))) >> ROOT_LAYER1_ROOT_SHIFT);
    }
}

template<bool USE_DSP, int OUT, bool PIPELINE_ACC = false>
void l1_neighbor_channel(
    const data_t aggregate_input[ROOT_NUM_NODES][ROOT_IN_FEATURES],
    data_t output[ROOT_NUM_NODES]
) {
#pragma HLS INLINE off
L1_NEIGHBOR_CHANNEL_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
        acc_t neighbor_acc;
        if constexpr (PIPELINE_ACC) {
            acc_t partial_lo = ROOT_BIAS1[OUT];
            acc_t partial_hi = 0;
        L1_NEIGHBOR_CHANNEL_INPUT_LO:
            for (int in_feature = 0; in_feature < ROOT_IN_FEATURES / 2; ++in_feature) {
#pragma HLS UNROLL
                ap_int<16> neighbor_product;
                if constexpr (USE_DSP) {
#if GS_DSP_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=dsp latency=GS_DSP_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=dsp
#endif
                    neighbor_product = aggregate_input[node][in_feature] * ROOT_WEIGHTS1_NEIGHBOR[OUT][in_feature];
                } else {
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=fabric
#endif
                    neighbor_product = aggregate_input[node][in_feature] * ROOT_WEIGHTS1_NEIGHBOR[OUT][in_feature];
                }
                partial_lo += neighbor_product;
            }
        L1_NEIGHBOR_CHANNEL_INPUT_HI:
            for (int in_feature = ROOT_IN_FEATURES / 2; in_feature < ROOT_IN_FEATURES; ++in_feature) {
#pragma HLS UNROLL
                ap_int<16> neighbor_product;
                if constexpr (USE_DSP) {
#if GS_DSP_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=dsp latency=GS_DSP_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=dsp
#endif
                    neighbor_product = aggregate_input[node][in_feature] * ROOT_WEIGHTS1_NEIGHBOR[OUT][in_feature];
                } else {
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=fabric
#endif
                    neighbor_product = aggregate_input[node][in_feature] * ROOT_WEIGHTS1_NEIGHBOR[OUT][in_feature];
                }
                partial_hi += neighbor_product;
            }
            // Explicit one-cycle fabric add: forces an FF boundary between the two half-sums.
#pragma HLS BIND_OP variable=neighbor_acc op=add impl=fabric latency=1
            neighbor_acc = partial_lo + partial_hi;
        } else {
            neighbor_acc = ROOT_BIAS1[OUT];
        L1_NEIGHBOR_CHANNEL_INPUT:
            for (int in_feature = 0; in_feature < ROOT_IN_FEATURES; ++in_feature) {
#pragma HLS UNROLL
                ap_int<16> neighbor_product;
                if constexpr (USE_DSP) {
#if GS_DSP_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=dsp latency=GS_DSP_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=dsp
#endif
                    neighbor_product = aggregate_input[node][in_feature] * ROOT_WEIGHTS1_NEIGHBOR[OUT][in_feature];
                } else {
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=fabric
#endif
                    neighbor_product = aggregate_input[node][in_feature] * ROOT_WEIGHTS1_NEIGHBOR[OUT][in_feature];
                }
                neighbor_acc += neighbor_product;
            }
        }
        output[node] = root_int8_clamp(
            (scale_acc_t(neighbor_acc) + (scale_acc_t(1) << (ROOT_LAYER1_NEIGHBOR_SHIFT - 1))) >> ROOT_LAYER1_NEIGHBOR_SHIFT);
    }
}

template<bool USE_DSP, int OUT>
void l2_root_channel(
    const data_t aggregate_input[ROOT_NUM_NODES][ROOT_HIDDEN_FEATURES],
    const data_t root_input[ROOT_NUM_NODES][ROOT_HIDDEN_FEATURES],
    data_t output[ROOT_NUM_NODES]
) {
#pragma HLS INLINE off
L2_ROOT_CHANNEL_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
        acc_t root_acc = 0;
    L2_ROOT_CHANNEL_INPUT:
        for (int in_feature = 0; in_feature < ROOT_HIDDEN_FEATURES; ++in_feature) {
#pragma HLS UNROLL
            ap_int<16> root_product;
            if constexpr (USE_DSP) {
#if GS_DSP_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=root_product op=mul impl=dsp latency=GS_DSP_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=root_product op=mul impl=dsp
#endif
                root_product = root_input[node][in_feature] * ROOT_WEIGHTS2_ROOT[OUT][in_feature];
            } else {
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=root_product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=root_product op=mul impl=fabric
#endif
                root_product = root_input[node][in_feature] * ROOT_WEIGHTS2_ROOT[OUT][in_feature];
            }
            root_acc += root_product;
        }
        output[node] = root_int8_clamp(
            (scale_acc_t(root_acc) + (scale_acc_t(1) << (ROOT_LAYER2_ROOT_SHIFT - 1))) >> ROOT_LAYER2_ROOT_SHIFT);
    }
}

template<bool USE_DSP, int OUT>
void l2_neighbor_channel(
    const data_t aggregate_input[ROOT_NUM_NODES][ROOT_HIDDEN_FEATURES],
    data_t output[ROOT_NUM_NODES]
) {
#pragma HLS INLINE off
L2_NEIGHBOR_CHANNEL_NODE:
    for (int node = 0; node < ROOT_NUM_NODES; ++node) {
#pragma HLS UNROLL
        acc_t neighbor_acc = ROOT_BIAS2[OUT];
    L2_NEIGHBOR_CHANNEL_INPUT:
        for (int in_feature = 0; in_feature < ROOT_HIDDEN_FEATURES; ++in_feature) {
#pragma HLS UNROLL
            ap_int<16> neighbor_product;
            if constexpr (USE_DSP) {
#if GS_DSP_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=dsp latency=GS_DSP_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=dsp
#endif
                neighbor_product = aggregate_input[node][in_feature] * ROOT_WEIGHTS2_NEIGHBOR[OUT][in_feature];
            } else {
#if GS_FABRIC_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=fabric latency=GS_FABRIC_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=neighbor_product op=mul impl=fabric
#endif
                neighbor_product = aggregate_input[node][in_feature] * ROOT_WEIGHTS2_NEIGHBOR[OUT][in_feature];
            }
            neighbor_acc += neighbor_product;
        }
        output[node] = root_int8_clamp(
            (scale_acc_t(neighbor_acc) + (scale_acc_t(1) << (ROOT_LAYER2_NEIGHBOR_SHIFT - 1))) >> ROOT_LAYER2_NEIGHBOR_SHIFT);
    }
}

void graphsage_po2_qat_partitioned(
    const data_t input[ROOT_NUM_NODES][ROOT_IN_FEATURES],
    const edge_mask_t edge_masks[ROOT_NUM_NODES],
    data_t output[ROOT_NUM_NODES][ROOT_OUT_FEATURES]);