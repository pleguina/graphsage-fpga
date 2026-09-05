/**
 * GraphSAGE Layer for FPGA - INT8 with POWER-OF-TWO SCALES
 *
 * ROUTED-OPTIMIZATION VARIANT:
 *   - Target top-level II = 2.
 *   - Reuses approximately half of the multiplier hardware across two cycles.
 *   - Aggregation multipliers remain in DSP48E2; linear multipliers remain in fabric.
 *   - Uses exact-width multiplication results before accumulation.
 *   - Uses compile-time PO2 shifts.
 *   - Uses a balanced 8-input aggregation reduction.
 *   - Adds one explicit pipelined cut at the first aggregation-adder level.
 *
 * IMPORTANT:
 *   The II=2 resource sharing is enforced with ALLOCATION limits. This is
 *   intentional: a PIPELINE directive on the top-level function causes HLS to
 *   unroll loops in the hierarchy below, so partial loop unrolling alone is not
 *   a reliable way to obtain sharing when the whole kernel is function-pipelined.
 */

#pragma once

#include <stdint.h>
#include <ap_int.h>

#ifndef __SYNTHESIS__
#include <cstdio>
#endif

// ============================================================================
// Optimized bit-width support
// ============================================================================
#ifdef USE_OPTIMIZED_BITWIDTHS
#include "auto_generated_bitwidths.h"
#endif

#ifdef DSE_CONFIG
#include "dse_config.h"
#endif

// ============================================================================
// Fixed network configuration
// ============================================================================
#ifdef DSE_CONFIG
#define NUM_NODES       DSE_NUM_NODES
#define IN_FEATURES     DSE_IN_FEATURES
#define HIDDEN_FEATURES DSE_HIDDEN_FEATURES
#define OUT_FEATURES    DSE_OUT_FEATURES
#else
#ifndef NUM_NODES
#define NUM_NODES 8
#endif
#ifndef IN_FEATURES
#define IN_FEATURES 16
#endif
#ifndef HIDDEN_FEATURES
#define HIDDEN_FEATURES 24
#endif
#ifndef OUT_FEATURES
#define OUT_FEATURES 7
#endif
#endif

#ifndef ADJ_BITS
#ifdef USE_OPTIMIZED_BITWIDTHS
#define ADJ_BITS OPT_ADJ_BITS
#else
#define ADJ_BITS 16
#endif
#endif

#ifndef ACC_BITS
#ifdef USE_OPTIMIZED_BITWIDTHS
#define ACC_BITS OPT_ACC_BITS
#else
#define ACC_BITS 22
#endif
#endif

// ============================================================================
// PO2 shifts
// ============================================================================
#ifndef EFF_SCALE1_SHIFT
#define EFF_SCALE1_SHIFT 7
#endif
#ifndef EFF_SCALE2_SHIFT
#define EFF_SCALE2_SHIFT 8
#endif
#ifndef BETA1_SHIFT
#define BETA1_SHIFT 17
#endif
#ifndef BETA2_SHIFT
#define BETA2_SHIFT 12
#endif

// ============================================================================
// II=2 / resource-sharing controls
// ============================================================================
#ifndef DSE_TOP_II
#define DSE_TOP_II 2
#endif

#ifndef DSE_BIND_AGG_MUL
#define DSE_BIND_AGG_MUL "dsp"
#endif

#ifndef DSE_BIND_LIN_MUL
#define DSE_BIND_LIN_MUL "fabric"
#endif

// The submitted 8->16/24 topology has:
//   AGG1: 8 nodes * 16 features * 8 neighbours = 1024 mul operations
//   AGG2: 8 nodes * 24 features * 8 neighbours = 1536 mul operations
// At II=2, half as many multiplier instances are sufficient in principle.
#ifndef DSE_AGG1_MUL_LIMIT
#define DSE_AGG1_MUL_LIMIT 512
#endif
#ifndef DSE_AGG2_MUL_LIMIT
#define DSE_AGG2_MUL_LIMIT 768
#endif

// Linear multipliers are in fabric in the paper configuration:
//   LIN1: 8 * 24 * 16 = 3072 -> 1536 instances at II=2
//   LIN2: 8 *  7 * 24 = 1344 ->  672 instances at II=2
// Sharing these too reduces local LUT density, not just DSP density.
#ifndef DSE_LIN1_MUL_LIMIT
#define DSE_LIN1_MUL_LIMIT 1536
#endif
#ifndef DSE_LIN2_MUL_LIMIT
#define DSE_LIN2_MUL_LIMIT 672
#endif

// DSP48 multiplier pipeline latency. The old generated RTL already used a
// two-stage multiplier in the critical family, so keep that physical intent.
#ifndef DSE_AGG_MUL_LATENCY
#define DSE_AGG_MUL_LATENCY 2
#endif

// First level of the 8-input aggregation reduction is explicitly pipelined.
// This is the intentional register cut added after post-route analysis.
#ifndef DSE_AGG_PAIR_ADD_LATENCY
#define DSE_AGG_PAIR_ADD_LATENCY 1
#endif

#ifndef DSE_LIN_MUL_LATENCY
#define DSE_LIN_MUL_LATENCY -1
#endif

// ============================================================================
// Types
// ============================================================================
typedef ap_int<8>        data_t;
typedef ap_int<8>        weight_t;
typedef ap_int<ADJ_BITS> adj_t;
typedef ap_int<ACC_BITS> acc_t;
typedef ap_int<ACC_BITS> bias_t;

// Exact mathematical multiplication widths. Products are explicitly cast to
// acc_t before accumulation, preserving the accumulator-domain behaviour.
typedef ap_int<ADJ_BITS + 8> agg_product_t;
typedef ap_int<16>           linear_product_t;

// ============================================================================
// Clamp
// ============================================================================
inline data_t int8_clamp(acc_t x) {
#pragma HLS INLINE
    if (x > 127)  return data_t(127);
    if (x < -128) return data_t(-128);
    return data_t(x);
}

// ============================================================================
// Balanced aggregation core
// ============================================================================
// The caller provides the ALLOCATION constraint. Keeping this function INLINE
// means the operation limit belongs to the AGG1/AGG2 stage wrapper, where the
// two layers can have different DSP budgets.
template<int N_NODES, int N_FEAT, int SHIFT_AMOUNT>
void aggregate_int8_po2_core(
    const adj_t  adj_matrix[N_NODES][N_NODES],
    const data_t features[N_NODES][N_FEAT],
    data_t       agg_out[N_NODES][N_FEAT]
) {
#pragma HLS INLINE

    static_assert(N_NODES == 8,
                  "This balanced aggregation implementation expects 8 nodes");

    const acc_t round_const = acc_t(1) << (SHIFT_AMOUNT - 1);

AGG_I:
    for (int i = 0; i < N_NODES; ++i) {
#pragma HLS UNROLL

    AGG_F:
        for (int f = 0; f < N_FEAT; ++f) {
#pragma HLS UNROLL

            agg_product_t products[8];
#pragma HLS ARRAY_PARTITION variable=products complete dim=1

        AGG_J:
            for (int j = 0; j < 8; ++j) {
#pragma HLS UNROLL
                agg_product_t prod;
#pragma HLS BIND_OP variable=prod op=mul impl=DSE_BIND_AGG_MUL latency=DSE_AGG_MUL_LATENCY
                prod = adj_matrix[i][j] * features[j][f];
                products[j] = prod;
            }

            // First balanced level. Each add has latency=1, deliberately
            // inserting a real register cut between DSP products and the
            // upper reduction levels.
            acc_t pair0;
            acc_t pair1;
            acc_t pair2;
            acc_t pair3;
#pragma HLS BIND_OP variable=pair0 op=add impl=fabric latency=DSE_AGG_PAIR_ADD_LATENCY
#pragma HLS BIND_OP variable=pair1 op=add impl=fabric latency=DSE_AGG_PAIR_ADD_LATENCY
#pragma HLS BIND_OP variable=pair2 op=add impl=fabric latency=DSE_AGG_PAIR_ADD_LATENCY
#pragma HLS BIND_OP variable=pair3 op=add impl=fabric latency=DSE_AGG_PAIR_ADD_LATENCY

            pair0 = acc_t(products[0]) + acc_t(products[1]);
            pair1 = acc_t(products[2]) + acc_t(products[3]);
            pair2 = acc_t(products[4]) + acc_t(products[5]);
            pair3 = acc_t(products[6]) + acc_t(products[7]);

            // Upper balanced reduction. Leave implementation/latency to HLS;
            // the long cone has already been cut at the pair-sum boundary.
            acc_t half0 = pair0 + pair1;
            acc_t half1 = pair2 + pair3;
            acc_t total = half0 + half1;

            acc_t rounded = total + round_const;
            acc_t result  = rounded >> SHIFT_AMOUNT;
            agg_out[i][f] = int8_clamp(result);

#ifndef __SYNTHESIS__
            if (i == 6 && f < 3) {
                std::printf(
                    "  AGG_PO2: node=%d feat=%d total=%d shift=%d result=%d out=%d\n",
                    i, f, (int)total, SHIFT_AMOUNT,
                    (int)result, (int)agg_out[i][f]);
            }
#endif
        }
    }
}

// Separate hierarchy blocks are intentional: they keep the independent
// AGG1/AGG2 allocation budgets local and give Vivado two physically meaningful
// aggregation regions instead of one monolithic multiplier pool.
template<int N_NODES, int N_FEAT, int SHIFT_AMOUNT>
void aggregate1_int8_po2(
    const adj_t  adj_matrix[N_NODES][N_NODES],
    const data_t features[N_NODES][N_FEAT],
    data_t       agg_out[N_NODES][N_FEAT]
) {
#pragma HLS INLINE off
#if DSE_AGG1_MUL_LIMIT > 0
#pragma HLS ALLOCATION operation instances=mul limit=DSE_AGG1_MUL_LIMIT
#endif
    aggregate_int8_po2_core<N_NODES, N_FEAT, SHIFT_AMOUNT>(
        adj_matrix, features, agg_out);
}

template<int N_NODES, int N_FEAT, int SHIFT_AMOUNT>
void aggregate2_int8_po2(
    const adj_t  adj_matrix[N_NODES][N_NODES],
    const data_t features[N_NODES][N_FEAT],
    data_t       agg_out[N_NODES][N_FEAT]
) {
#pragma HLS INLINE off
#if DSE_AGG2_MUL_LIMIT > 0
#pragma HLS ALLOCATION operation instances=mul limit=DSE_AGG2_MUL_LIMIT
#endif
    aggregate_int8_po2_core<N_NODES, N_FEAT, SHIFT_AMOUNT>(
        adj_matrix, features, agg_out);
}

// ============================================================================
// Linear core
// ============================================================================
template<int N_NODES, int IN_FEAT, int OUT_FEAT, int SHIFT_AMOUNT>
void linear_int8_po2_core(
    const data_t   features[N_NODES][IN_FEAT],
    const weight_t weights[OUT_FEAT][IN_FEAT],
    const bias_t   bias[OUT_FEAT],
    data_t         output[N_NODES][OUT_FEAT]
) {
#pragma HLS INLINE

    const acc_t round_const = acc_t(1) << (SHIFT_AMOUNT - 1);

LIN_N:
    for (int n = 0; n < N_NODES; ++n) {
#pragma HLS UNROLL

    LIN_O:
        for (int o = 0; o < OUT_FEAT; ++o) {
#pragma HLS UNROLL
            acc_t acc = bias[o];

        LIN_F:
            for (int f = 0; f < IN_FEAT; ++f) {
#pragma HLS UNROLL
                linear_product_t prod;
#if DSE_LIN_MUL_LATENCY >= 0
#pragma HLS BIND_OP variable=prod op=mul impl=DSE_BIND_LIN_MUL latency=DSE_LIN_MUL_LATENCY
#else
#pragma HLS BIND_OP variable=prod op=mul impl=DSE_BIND_LIN_MUL
#endif
                prod = features[n][f] * weights[o][f];
                acc += acc_t(prod);
            }

            acc_t rounded = acc + round_const;
            acc_t result  = rounded >> SHIFT_AMOUNT;
            output[n][o]  = int8_clamp(result);

#ifndef __SYNTHESIS__
            if (n == 6 && o < 3) {
                std::printf(
                    "  LIN_PO2: node=%d out=%d acc=%d shift=%d result=%d out=%d\n",
                    n, o, (int)acc, SHIFT_AMOUNT,
                    (int)result, (int)output[n][o]);
            }
#endif
        }
    }
}

template<int N_NODES, int IN_FEAT, int OUT_FEAT, int SHIFT_AMOUNT>
void linear1_int8_po2(
    const data_t   features[N_NODES][IN_FEAT],
    const weight_t weights[OUT_FEAT][IN_FEAT],
    const bias_t   bias[OUT_FEAT],
    data_t         output[N_NODES][OUT_FEAT]
) {
#pragma HLS INLINE off
#if DSE_LIN1_MUL_LIMIT > 0
#pragma HLS ALLOCATION operation instances=mul limit=DSE_LIN1_MUL_LIMIT
#endif
    linear_int8_po2_core<N_NODES, IN_FEAT, OUT_FEAT, SHIFT_AMOUNT>(
        features, weights, bias, output);
}

template<int N_NODES, int IN_FEAT, int OUT_FEAT, int SHIFT_AMOUNT>
void linear2_int8_po2(
    const data_t   features[N_NODES][IN_FEAT],
    const weight_t weights[OUT_FEAT][IN_FEAT],
    const bias_t   bias[OUT_FEAT],
    data_t         output[N_NODES][OUT_FEAT]
) {
#pragma HLS INLINE off
#if DSE_LIN2_MUL_LIMIT > 0
#pragma HLS ALLOCATION operation instances=mul limit=DSE_LIN2_MUL_LIMIT
#endif
    linear_int8_po2_core<N_NODES, IN_FEAT, OUT_FEAT, SHIFT_AMOUNT>(
        features, weights, bias, output);
}

// ============================================================================
// ReLU
// ============================================================================
template<int N_NODES, int N_FEAT>
void relu_int8(data_t data[N_NODES][N_FEAT]) {
#pragma HLS INLINE
RELU_N:
    for (int n = 0; n < N_NODES; ++n) {
#pragma HLS UNROLL
    RELU_F:
        for (int f = 0; f < N_FEAT; ++f) {
#pragma HLS UNROLL
            if (data[n][f] < 0)
                data[n][f] = 0;
        }
    }
}

// ============================================================================
// Full network
// ============================================================================
template<int N_NODES, int IN_FEAT, int HIDDEN_FEAT, int OUT_FEAT>
void graphsage_int8_po2_template(
    const adj_t    adj_matrix[N_NODES][N_NODES],
    const data_t   input[N_NODES][IN_FEAT],
    const weight_t weights1[HIDDEN_FEAT][IN_FEAT],
    const bias_t   bias1[HIDDEN_FEAT],
    const weight_t weights2[OUT_FEAT][HIDDEN_FEAT],
    const bias_t   bias2[OUT_FEAT],
    data_t         output[N_NODES][OUT_FEAT]
) {
#pragma HLS INLINE

    data_t agg1[N_NODES][IN_FEAT];
    data_t hidden[N_NODES][HIDDEN_FEAT];
    data_t agg2[N_NODES][HIDDEN_FEAT];

#pragma HLS ARRAY_PARTITION variable=agg1 complete dim=1
#pragma HLS ARRAY_PARTITION variable=agg1 complete dim=2
#pragma HLS ARRAY_PARTITION variable=hidden complete dim=1
#pragma HLS ARRAY_PARTITION variable=hidden complete dim=2
#pragma HLS ARRAY_PARTITION variable=agg2 complete dim=1
#pragma HLS ARRAY_PARTITION variable=agg2 complete dim=2

    aggregate1_int8_po2<N_NODES, IN_FEAT, BETA1_SHIFT>(
        adj_matrix, input, agg1);

    linear1_int8_po2<N_NODES, IN_FEAT, HIDDEN_FEAT, EFF_SCALE1_SHIFT>(
        agg1, weights1, bias1, hidden);

    relu_int8<N_NODES, HIDDEN_FEAT>(hidden);

    aggregate2_int8_po2<N_NODES, HIDDEN_FEAT, BETA2_SHIFT>(
        adj_matrix, hidden, agg2);

    linear2_int8_po2<N_NODES, HIDDEN_FEAT, OUT_FEAT, EFF_SCALE2_SHIFT>(
        agg2, weights2, bias2, output);
}

// ============================================================================
// Top-level declaration
// ============================================================================
void graphsage_int8_po2(
    const adj_t    adj_matrix[NUM_NODES][NUM_NODES],
    const data_t   input[NUM_NODES][IN_FEATURES],
    const weight_t weights1[HIDDEN_FEATURES][IN_FEATURES],
    const bias_t   bias1[HIDDEN_FEATURES],
    const weight_t weights2[OUT_FEATURES][HIDDEN_FEATURES],
    const bias_t   bias2[OUT_FEATURES],
    data_t         output[NUM_NODES][OUT_FEATURES]
);
