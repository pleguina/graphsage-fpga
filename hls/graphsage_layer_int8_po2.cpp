/**
 * GraphSAGE Layer - INT8 with Power-of-Two Scales
 * Implementation file with HLS pragmas
 * 
 * Key optimizations:
 *   - NO scale multipliers (just bit-shifts)
 *   - Reduced critical path
 *   - Lower DSP usage than arbitrary-scale INT8
 */

#ifdef GRAPHSAGE_19C
#include "graphsage_layer_int8_po2_19c.h"
#elif defined(GRAPHSAGE_INTERNAL_LOCALITY_HIERARCHY)
#include "graphsage_layer_int8_po2_locality_hierarchy.h"
#elif defined(GRAPHSAGE_INTERNAL_LOCALITY)
#include "graphsage_layer_int8_po2_locality.h"
#else
#include "graphsage_layer_int8_po2.h"
#endif

/**
 * Top-level synthesis wrapper
 * 
 * Note: No scale_fp parameters needed! Shift amounts are compile-time constants.
 * 
 * IMPORTANT: No top-level PIPELINE pragma! 
 * Pipeline/unroll directives in template functions control parallelism.
 * Top-level pipelining would force complete unrolling of all loops.
 */
void graphsage_int8_po2(
    const adj_t    adj_matrix[NUM_NODES][NUM_NODES],
    const data_t   input[NUM_NODES][IN_FEATURES],
    const weight_t weights1[HIDDEN_FEATURES][IN_FEATURES],
    const bias_t   bias1[HIDDEN_FEATURES],
    const weight_t weights2[OUT_FEATURES][HIDDEN_FEATURES],
    const bias_t   bias2[OUT_FEATURES],
    data_t         output[NUM_NODES][OUT_FEATURES]
) {
    // NOTE: Top-level PIPELINE pragma removed to allow parametrized unrolling
    // Individual loops inside template have their own PIPELINE/UNROLL directives
#if DSE_PIPELINE_TOP
    #pragma HLS PIPELINE II=DSE_TOP_II
#endif
    // ========== HLS Interface Pragmas ==========
    #pragma HLS INTERFACE mode=ap_none port=adj_matrix
    #pragma HLS INTERFACE mode=ap_none port=input
    #pragma HLS INTERFACE mode=ap_none port=weights1
    #pragma HLS INTERFACE mode=ap_none port=bias1
    #pragma HLS INTERFACE mode=ap_none port=weights2
    #pragma HLS INTERFACE mode=ap_none port=bias2
    #pragma HLS INTERFACE mode=ap_none port=output
    #pragma HLS INTERFACE mode=ap_ctrl_hs port=return
    
    // ========== Array Partitioning ==========
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
    
    // Call template with compile-time shift amounts
    graphsage_int8_po2_template<NUM_NODES, IN_FEATURES, HIDDEN_FEATURES, OUT_FEATURES>(
        adj_matrix,
        input,
        weights1,
        bias1,
        weights2,
        bias2,
        output
    );
}
