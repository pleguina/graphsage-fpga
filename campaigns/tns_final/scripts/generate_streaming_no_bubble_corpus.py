#!/usr/bin/env python3
"""
Generate the 1024-transaction back-to-back streaming corpus for the
explicit no-bubble II=1 RTL co-simulation test
(docs/tns_campaign_status.md OPEN item: "explicit no-bubble II=1 test").

Unlike the 14-graph edge-density/topology corpus (which holds features
fixed to isolate the topology variable), THIS corpus deliberately varies
BOTH the edge-mask topology and the node features on every single
transaction, cycling through the same 14 canonical topologies (empty,
chain, ring, star, bipartite, clique, degree sweep, complete, random
sparse/medium/dense, ...) combined with 1024 distinct feature draws from
the real production corpus's own diverse input pool. Consecutive
transactions always use a different topology (index i and i+1 always land
on different entries of the 14-item list) and, because gcd(14, 256) != the
period of the combined (topology, feature) pairing, the pairing does not
repeat at all within the first 1024 transactions - i.e. E_t != E_{t+1}
essentially always, and X_t changes every cycle too. This is the input
side of the "root/neighbor misalignment" and "graph changes every cycle"
checks: if the design internally cached or misaligned any per-node state
across transactions, this input pattern would expose it immediately.

Golden outputs reuse the exact frozen production weights/biases/shifts
(same technique as generate_edge_density_corpus.py) so this checks the
literal deployed A5/V2A1_allcut model, not a re-derivation.

The actual "no idle cycle between inputs, fixed 50-cycle latency, one
output per clock thereafter" claim is verified separately, from the
RTL-timestamped "RTL Simulation : N / 1024 [...] @ "<time>"" progress
lines Vitis HLS's cosim engine prints for this ap_ctrl_none/PIPELINE II=1
design - see campaigns/tns_final/scripts/analyze_cosim_bubble_timing.py.

Usage:
  python3 generate_streaming_no_bubble_corpus.py
Writes:
  campaigns/qat_dsp_partitioning/frozen/source/root_graphsage_constants_streaming_no_bubble.h
"""
import re
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_HEADER = REPO_ROOT / "campaigns/qat_dsp_partitioning/frozen/source/root_graphsage_constants.h"
OUTPUT_HEADER = REPO_ROOT / "campaigns/qat_dsp_partitioning/frozen/source/root_graphsage_constants_streaming_no_bubble.h"

NUM_NODES = 8
NUM_TRANSACTIONS = 1024
K = 4096


def extract_array(text: str, name: str):
    marker = re.search(rf"\b{re.escape(name)}\s*(\[[^=]*)?=\s*", text)
    if marker is None:
        raise ValueError(f"{name} not found")
    start = marker.end()
    brace_start = text.index("{", start)
    depth = 0
    i = brace_start
    while True:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    literal = text[brace_start:i + 1].replace("{", "[").replace("}", "]")
    return eval(literal)  # noqa: S307 - trusted, our own generated numeric header


def extract_scalar(text: str, name: str) -> int:
    m = re.search(rf"\b{re.escape(name)}\s*=\s*(-?\d+)\s*;", text)
    if m is None:
        raise ValueError(f"{name} not found")
    return int(m.group(1))


def degree_scale(degree: int) -> int:
    return 0 if degree == 0 else int(np.rint(K / degree))


def round_shift(values: np.ndarray, shift: int) -> np.ndarray:
    values = values.astype(np.int64)
    if shift == 0:
        return values
    if shift < 0:
        return values << (-shift)
    return (values + (1 << (shift - 1))) >> shift


def popcount8(mask: int) -> int:
    return bin(mask & 0xFF).count("1")


def aggregate(features: np.ndarray, masks: list, shift: int) -> np.ndarray:
    out = np.zeros_like(features, dtype=np.int8)
    for node in range(NUM_NODES):
        mask = masks[node]
        selected = [features[n].astype(np.int64) for n in range(NUM_NODES) if mask & (1 << n)]
        neighbor_sum = np.sum(selected, axis=0, dtype=np.int64) if selected else np.zeros(features.shape[1], dtype=np.int64)
        scale = degree_scale(popcount8(mask))
        out[node] = np.clip(round_shift(neighbor_sum * scale, shift), -128, 127).astype(np.int8)
    return out


def dual_linear(agg_in, root_in, w_neighbor, w_root, bias, shift_neighbor, shift_root):
    neighbor_acc = agg_in.astype(np.int64) @ w_neighbor.astype(np.int64).T
    neighbor_acc += bias.astype(np.int64)
    root_acc = root_in.astype(np.int64) @ w_root.astype(np.int64).T
    neighbor_out = np.clip(round_shift(neighbor_acc, shift_neighbor), -128, 127).astype(np.int16)
    root_out = np.clip(round_shift(root_acc, shift_root), -128, 127).astype(np.int16)
    return np.clip(neighbor_out + root_out, -128, 127).astype(np.int8)


def forward(input_int8, masks, p):
    agg1 = aggregate(input_int8, masks, p["agg1_shift"])
    hidden = dual_linear(agg1, input_int8, p["w1_neighbor"], p["w1_root"], p["b1"],
                          p["layer1_neighbor_shift"], p["layer1_root_shift"])
    hidden = np.maximum(hidden, 0).astype(np.int8)
    agg2 = aggregate(hidden, masks, p["agg2_shift"])
    output = dual_linear(agg2, hidden, p["w2_neighbor"], p["w2_root"], p["b2"],
                          p["layer2_neighbor_shift"], p["layer2_root_shift"])
    return output


def build_topology_bank():
    """Same 14 canonical topologies as generate_edge_density_corpus.py."""
    banks = []
    banks.append(("EMPTY", [0] * 8))

    m = [0] * 8
    m[1] = 1 << 0
    banks.append(("SINGLE_EDGE", m))

    banks.append(("RING", [1 << ((i - 1) % 8) for i in range(8)]))

    star = [0] * 8
    star[0] = 0xFE
    for leaf in range(1, 8):
        star[leaf] = 1 << 0
    banks.append(("STAR_HUB0", star))

    chain = [0] * 8
    for i in range(1, 8):
        chain[i] = 1 << (i - 1)
    banks.append(("CHAIN_WITH_ISOLATED_HEAD", chain))

    rng = np.random.default_rng(2026)
    for label, density in [("SPARSE_RANDOM", 0.25), ("MEDIUM_RANDOM", 0.5), ("DENSE_RANDOM", 0.75)]:
        masks = []
        for _ in range(8):
            bits = (rng.random(8) < density).astype(int)
            masks.append(int(sum(b << i for i, b in enumerate(bits))))
        banks.append((label, masks))

    banks.append(("COMPLETE_WITH_SELF", [0xFF] * 8))
    banks.append(("COMPLETE_NO_SELF", [0xFF & ~(1 << i) for i in range(8)]))
    banks.append(("DEGREE_SWEEP_1_TO_8", [(1 << (i + 1)) - 1 for i in range(8)]))

    max_iso = [0] * 8
    max_iso[0] = 0xFF
    banks.append(("MAX_DEGREE_WITH_ISOLATED_PEERS", max_iso))

    banks.append(("CHECKERBOARD_BIPARTITE", [0xAA if i % 2 == 0 else 0x55 for i in range(8)]))
    banks.append(("ISOLATED_QUAD_PLUS_CLIQUE_QUAD", [0x00, 0x00, 0x00, 0x00, 0xE0, 0xD0, 0xB0, 0x70]))

    assert len(banks) == 14
    return banks


def main():
    text = FROZEN_HEADER.read_text()
    params = {
        "agg1_shift": extract_scalar(text, "ROOT_AGGREGATE1_SHIFT"),
        "agg2_shift": extract_scalar(text, "ROOT_AGGREGATE2_SHIFT"),
        "layer1_neighbor_shift": extract_scalar(text, "ROOT_LAYER1_NEIGHBOR_SHIFT"),
        "layer1_root_shift": extract_scalar(text, "ROOT_LAYER1_ROOT_SHIFT"),
        "layer2_neighbor_shift": extract_scalar(text, "ROOT_LAYER2_NEIGHBOR_SHIFT"),
        "layer2_root_shift": extract_scalar(text, "ROOT_LAYER2_ROOT_SHIFT"),
        "w1_neighbor": np.array(extract_array(text, "ROOT_WEIGHTS1_NEIGHBOR"), dtype=np.int64),
        "w1_root": np.array(extract_array(text, "ROOT_WEIGHTS1_ROOT"), dtype=np.int64),
        "b1": np.array(extract_array(text, "ROOT_BIAS1"), dtype=np.int64),
        "w2_neighbor": np.array(extract_array(text, "ROOT_WEIGHTS2_NEIGHBOR"), dtype=np.int64),
        "w2_root": np.array(extract_array(text, "ROOT_WEIGHTS2_ROOT"), dtype=np.int64),
        "b2": np.array(extract_array(text, "ROOT_BIAS2"), dtype=np.int64),
    }
    feature_pool = np.array(extract_array(text, "ROOT_TEST_INPUTS"), dtype=np.int64)  # [256, 8, 16]
    num_feature_sets = feature_pool.shape[0]
    topology_bank = build_topology_bank()
    num_topologies = len(topology_bank)

    masks_all, expected_all, inputs_all, labels = [], [], [], []
    for t in range(NUM_TRANSACTIONS):
        topo_name, masks = topology_bank[t % num_topologies]
        features = feature_pool[t % num_feature_sets].astype(np.int8)
        out = forward(features, masks, params)
        masks_all.append(masks)
        inputs_all.append(features.tolist())
        expected_all.append(out.tolist())
        labels.append(topo_name)

    # Sanity: consecutive transactions must use a different topology every time.
    same_topology_repeats = sum(1 for t in range(1, NUM_TRANSACTIONS) if labels[t] == labels[t - 1])
    assert same_topology_repeats == 0, f"{same_topology_repeats} consecutive repeats found"
    print(f"Verified: topology changes on all {NUM_TRANSACTIONS - 1} consecutive transaction pairs.")

    def fmt1d(values):
        return "{" + ", ".join(str(int(v)) for v in values) + "}"

    def fmt2d(values):
        return "{\n" + ",\n".join("    " + fmt1d(row) for row in values) + "\n}"

    def fmt3d(values):
        return "{\n" + ",\n".join("    " + fmt2d(m).replace("\n", "\n    ") for m in values) + "\n}"

    lines = [
        "#pragma once",
        "",
        "// 1024-transaction back-to-back streaming corpus for the explicit",
        "// no-bubble II=1 RTL co-simulation test. Both edge_mask topology AND",
        "// node features vary on every transaction (cycling through the 14",
        "// canonical topologies from the edge-density corpus combined with the",
        "// production corpus's 256 distinct feature sets); consecutive",
        "// transactions never repeat the same topology. Golden outputs use the",
        "// same frozen production weights/biases/shifts as the deployed model.",
        "// Generated by campaigns/tns_final/scripts/",
        "// generate_streaming_no_bubble_corpus.py.",
        "",
        f"static constexpr int ROOT_NUM_TEST_GRAPHS = {NUM_TRANSACTIONS};",
        f"static constexpr int ROOT_AGGREGATE1_SHIFT = {params['agg1_shift']};",
        f"static constexpr int ROOT_AGGREGATE2_SHIFT = {params['agg2_shift']};",
        f"static constexpr int ROOT_LAYER1_NEIGHBOR_SHIFT = {params['layer1_neighbor_shift']};",
        f"static constexpr int ROOT_LAYER1_ROOT_SHIFT = {params['layer1_root_shift']};",
        f"static constexpr int ROOT_LAYER2_NEIGHBOR_SHIFT = {params['layer2_neighbor_shift']};",
        f"static constexpr int ROOT_LAYER2_ROOT_SHIFT = {params['layer2_root_shift']};",
        "",
        f"static const weight_t ROOT_WEIGHTS1_NEIGHBOR[ROOT_HIDDEN_FEATURES][ROOT_IN_FEATURES] = {fmt2d(params['w1_neighbor'].tolist())};",
        f"static const weight_t ROOT_WEIGHTS1_ROOT[ROOT_HIDDEN_FEATURES][ROOT_IN_FEATURES] = {fmt2d(params['w1_root'].tolist())};",
        f"static const bias_t ROOT_BIAS1[ROOT_HIDDEN_FEATURES] = {fmt1d(params['b1'].tolist())};",
        f"static const weight_t ROOT_WEIGHTS2_NEIGHBOR[ROOT_OUT_FEATURES][ROOT_HIDDEN_FEATURES] = {fmt2d(params['w2_neighbor'].tolist())};",
        f"static const weight_t ROOT_WEIGHTS2_ROOT[ROOT_OUT_FEATURES][ROOT_HIDDEN_FEATURES] = {fmt2d(params['w2_root'].tolist())};",
        f"static const bias_t ROOT_BIAS2[ROOT_OUT_FEATURES] = {fmt1d(params['b2'].tolist())};",
        "",
        f"static const data_t ROOT_TEST_INPUTS[ROOT_NUM_TEST_GRAPHS][ROOT_NUM_NODES][ROOT_IN_FEATURES] = {fmt3d(inputs_all)};",
        f"static const edge_mask_t ROOT_TEST_MASKS[ROOT_NUM_TEST_GRAPHS][ROOT_NUM_NODES] = {fmt2d(masks_all)};",
        f"static const data_t ROOT_EXPECTED_OUTPUTS[ROOT_NUM_TEST_GRAPHS][ROOT_NUM_NODES][ROOT_OUT_FEATURES] = {fmt3d(expected_all)};",
        "",
    ]
    OUTPUT_HEADER.write_text("\n".join(lines))
    print(f"Wrote {OUTPUT_HEADER} ({NUM_TRANSACTIONS} transactions, {num_topologies} topologies x {num_feature_sets} feature sets)")


if __name__ == "__main__":
    main()
