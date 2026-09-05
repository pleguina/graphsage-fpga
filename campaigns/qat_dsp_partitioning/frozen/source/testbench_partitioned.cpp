#include "graphsage_po2_qat_partitioned.h"

#include <iostream>

void graphsage_po2_qat_partitioned(
    const data_t input[ROOT_NUM_NODES][ROOT_IN_FEATURES],
    const edge_mask_t edge_masks[ROOT_NUM_NODES],
    data_t output[ROOT_NUM_NODES][ROOT_OUT_FEATURES]);

int main() {
    int differences = 0;
    for (int graph = 0; graph < ROOT_NUM_TEST_GRAPHS; ++graph) {
        data_t output[ROOT_NUM_NODES][ROOT_OUT_FEATURES] = {};
        graphsage_po2_qat_partitioned(
            ROOT_TEST_INPUTS[graph], ROOT_TEST_MASKS[graph], output);
        for (int node = 0; node < ROOT_NUM_NODES; ++node) {
            for (int feature = 0; feature < ROOT_OUT_FEATURES; ++feature) {
                const int actual = int(output[node][feature]);
                const int expected = int(ROOT_EXPECTED_OUTPUTS[graph][node][feature]);
                if (actual != expected) {
                    std::cerr << "Mismatch graph=" << graph
                              << " node=" << node
                              << " feature=" << feature
                              << " actual=" << actual
                              << " expected=" << expected << '\n';
                    ++differences;
                }
            }
        }
    }
    if (differences != 0) {
        std::cerr << "PARTITIONED_BIT_EXACT_FAILURE differences=" << differences << '\n';
        return 1;
    }
    std::cout << "PARTITIONED_BIT_EXACT_PASS graphs=" << ROOT_NUM_TEST_GRAPHS << '\n';
    return 0;
}