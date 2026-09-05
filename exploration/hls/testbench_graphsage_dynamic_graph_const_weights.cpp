#include "graphsage_layer_int8_po2_dynamic_graph_const_weights.h"

#include <fstream>
#include <iostream>

template<typename T, int ROWS, int COLS>
bool load_matrix(const char *path, T values[ROWS][COLS]) {
    std::ifstream stream(path);
    int value;
    for (int row = 0; row < ROWS; ++row) {
        for (int column = 0; column < COLS; ++column) {
            if (!(stream >> value)) return false;
            values[row][column] = value;
        }
    }
    return true;
}

void masks_to_adjacency(
    const edge_mask_t masks[NUM_NODES],
    adj_t adjacency[NUM_NODES][NUM_NODES]
) {
    for (int node = 0; node < NUM_NODES; ++node) {
        int degree = 0;
        for (int neighbor = 0; neighbor < NUM_NODES; ++neighbor) {
            degree += masks[node][neighbor] ? 1 : 0;
        }
        const int scale = degree == 0 ? 0 : (1 << K_BITS) / degree;
        for (int neighbor = 0; neighbor < NUM_NODES; ++neighbor) {
            adjacency[node][neighbor] = masks[node][neighbor] ? scale : 0;
        }
    }
}

void historical_masks(edge_mask_t masks[NUM_NODES]) {
    for (int node = 0; node < NUM_NODES; ++node) {
        masks[node] = 0;
        for (int neighbor = 0; neighbor < NUM_NODES; ++neighbor) {
            masks[node][neighbor] = CONST_ADJ[node][neighbor] != 0;
        }
    }
}

void build_test_masks(int test, edge_mask_t masks[NUM_NODES]) {
    for (int node = 0; node < NUM_NODES; ++node) masks[node] = 0;

    switch (test) {
    case 0:
        historical_masks(masks);
        break;
    case 1:
        for (int node = 0; node < NUM_NODES; ++node) {
            const int degree = node + 1;
            for (int offset = 0; offset < degree; ++offset) {
                masks[node][(node + offset + 1) % NUM_NODES] = 1;
            }
        }
        break;
    case 2:
        for (int node = 0; node < NUM_NODES; ++node) {
            masks[node][node] = 1;
            masks[node][(node + 3) % NUM_NODES] = 1;
            masks[node][(node + 5) % NUM_NODES] = 1;
        }
        break;
    case 3:
        for (int node = 0; node < NUM_NODES; ++node) masks[node] = 0xff;
        break;
    case 4:
        for (int node = 0; node < NUM_NODES; ++node) {
            masks[node][(node + 1) % NUM_NODES] = 1;
            masks[node][(node + 2) % NUM_NODES] = 1;
            masks[node][(node + 4) % NUM_NODES] = 1;
            masks[node][(node + 6) % NUM_NODES] = 1;
        }
        break;
    case 5:
        for (int node = 0; node < NUM_NODES; ++node) {
            masks[node][(node + 0) % NUM_NODES] = 1;
            masks[node][(node + 3) % NUM_NODES] = 1;
            masks[node][(node + 5) % NUM_NODES] = 1;
            masks[node][(node + 7) % NUM_NODES] = 1;
        }
        break;
    default:
        break;
    }
}

int compare_outputs(
    int test,
    const data_t actual[NUM_NODES][OUT_FEATURES],
    const data_t expected[NUM_NODES][OUT_FEATURES]
) {
    int differences = 0;
    for (int node = 0; node < NUM_NODES; ++node) {
        for (int feature = 0; feature < OUT_FEATURES; ++feature) {
            if (actual[node][feature] != expected[node][feature]) {
                std::cerr << "Mismatch test=" << test << " node=" << node
                          << " feature=" << feature
                          << " actual=" << actual[node][feature].to_int()
                          << " expected=" << expected[node][feature].to_int() << '\n';
                ++differences;
            }
        }
    }
    return differences;
}

int main() {
    data_t input[NUM_NODES][IN_FEATURES];
    data_t historical_expected[NUM_NODES][OUT_FEATURES];
    if (!load_matrix<data_t, NUM_NODES, IN_FEATURES>(
            "../../../../../../build/test_vectors_ptq_float/network_input.txt", input) ||
        !load_matrix<data_t, NUM_NODES, OUT_FEATURES>(
            "../../../../../../build/golden/graphsage_int8_po2_19c_output.txt",
            historical_expected)) {
        std::cerr << "Failed to load recovered historical vectors\n";
        return 2;
    }

    constexpr int NUM_TEST_GRAPHS = 7;
    int differences = 0;
    for (int test = 0; test < NUM_TEST_GRAPHS; ++test) {
        edge_mask_t masks[NUM_NODES];
        adj_t adjacency[NUM_NODES][NUM_NODES];
        data_t expected[NUM_NODES][OUT_FEATURES];
        data_t output[NUM_NODES][OUT_FEATURES];
        build_test_masks(test, masks);
        masks_to_adjacency(masks, adjacency);

        graphsage_int8_po2_template<
            NUM_NODES, IN_FEATURES, HIDDEN_FEATURES, OUT_FEATURES>(
            adjacency, input, CONST_WEIGHTS1, CONST_BIAS1,
            CONST_WEIGHTS2, CONST_BIAS2, expected);

        if (test == 0) {
            differences += compare_outputs(test, expected, historical_expected);
        }

        graphsage_dynamic_graph_const_weights(input, masks, output);
        differences += compare_outputs(test, output, expected);
    }

    if (differences != 0) {
        std::cerr << "DYNAMIC_GRAPH_BIT_EXACT_FAILURE differences="
                  << differences << '\n';
        return 1;
    }

    std::cout << "DYNAMIC_GRAPH_BIT_EXACT_PASS graphs=" << NUM_TEST_GRAPHS
              << " outputs=" << NUM_TEST_GRAPHS * NUM_NODES * OUT_FEATURES
              << " consecutive_topologies=yes\n";
    return 0;
}