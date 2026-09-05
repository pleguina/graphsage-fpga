#include "graphsage_layer_int8_po2_19c_const.h"

#include <fstream>
#include <iostream>

#if defined(USE_CONST_PARAMS)
void graphsage_int8_po2(
    const data_t input[NUM_NODES][IN_FEATURES],
    data_t output[NUM_NODES][OUT_FEATURES]);
#elif defined(USE_CONST_ADJ)
void graphsage_int8_po2(
    const data_t input[NUM_NODES][IN_FEATURES],
    const weight_t weights1[HIDDEN_FEATURES][IN_FEATURES],
    const bias_t bias1[HIDDEN_FEATURES],
    const weight_t weights2[OUT_FEATURES][HIDDEN_FEATURES],
    const bias_t bias2[OUT_FEATURES],
    data_t output[NUM_NODES][OUT_FEATURES]);
#endif

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

template<typename T, int SIZE>
bool load_vector(const char *path, T values[SIZE]) {
    std::ifstream stream(path);
    int value;
    for (int index = 0; index < SIZE; ++index) {
        if (!(stream >> value)) return false;
        values[index] = value;
    }
    return true;
}

int main() {
    const char *root = "../../../../../../build";
    data_t input[NUM_NODES][IN_FEATURES];
    weight_t weights1[HIDDEN_FEATURES][IN_FEATURES];
    bias_t bias1[HIDDEN_FEATURES];
    weight_t weights2[OUT_FEATURES][HIDDEN_FEATURES];
    bias_t bias2[OUT_FEATURES];
    data_t expected[NUM_NODES][OUT_FEATURES];
    data_t output[NUM_NODES][OUT_FEATURES];

    if (!load_matrix<data_t, NUM_NODES, IN_FEATURES>(
            "../../../../../../build/test_vectors_ptq_float/network_input.txt", input) ||
        !load_matrix<weight_t, HIDDEN_FEATURES, IN_FEATURES>(
            "../../../../../../build/test_vectors_ptq_float/weights_layer1.txt", weights1) ||
        !load_vector<bias_t, HIDDEN_FEATURES>(
            "../../../../../../build/weights_ptq_int8/bias_layer1_int32.txt", bias1) ||
        !load_matrix<weight_t, OUT_FEATURES, HIDDEN_FEATURES>(
            "../../../../../../build/test_vectors_ptq_float/weights_layer2.txt", weights2) ||
        !load_vector<bias_t, OUT_FEATURES>(
            "../../../../../../build/weights_ptq_int8/bias_layer2_int32.txt", bias2) ||
        !load_matrix<data_t, NUM_NODES, OUT_FEATURES>(
            "../../../../../../build/golden/graphsage_int8_po2_19c_output.txt", expected)) {
        std::cerr << "Failed to load recovered test vectors under " << root << '\n';
        return 2;
    }

#if defined(USE_CONST_PARAMS)
    graphsage_int8_po2(input, output);
    const char *output_path = "../../../../../../build/golden/graphsage_const_params_output.txt";
#else
    graphsage_int8_po2(input, weights1, bias1, weights2, bias2, output);
    const char *output_path = "../../../../../../build/golden/graphsage_const_adj_output.txt";
#endif

    std::ofstream output_stream(output_path);
    int differences = 0;
    for (int node = 0; node < NUM_NODES; ++node) {
        for (int feature = 0; feature < OUT_FEATURES; ++feature) {
            const int actual = output[node][feature].to_int();
            const int golden = expected[node][feature].to_int();
            output_stream << actual << (feature + 1 == OUT_FEATURES ? '\n' : ' ');
            if (actual != golden) {
                std::cerr << "Mismatch node=" << node << " feature=" << feature
                          << " actual=" << actual << " golden=" << golden << '\n';
                ++differences;
            }
        }
    }

    if (differences != 0) {
        std::cerr << "BIT_EXACT_FAILURE differences=" << differences << '\n';
        return 1;
    }

    std::cout << "BIT_EXACT_PASS outputs=56 output_file=" << output_path << '\n';
    return 0;
}