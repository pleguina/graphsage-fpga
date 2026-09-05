#!/usr/bin/env python3
"""
Generate a deliberately-structured, small edge-density/topology coverage
corpus for the FINAL frozen partitioned architecture (A5/V2A1_allcut),
supplementing the existing 256-graph regression corpus.

Purpose (docs/tns_campaign_status.md OPEN item, "edge-density/topology
coverage at N=8"): demonstrate that edge_masks are genuinely runtime data
by holding node features FIXED and sweeping ONLY the adjacency pattern
across the complete |E|=0 -> |E|_max range, including canonical topologies
(empty, single-edge, ring, star, chain, checkerboard-bipartite, complete
with/without self, a single degree-1..8 sweep graph, an isolated+clique
mix, and three random-density steps). This is a functional-robustness
check, not a hardware-scaling study - resource/timing are architecturally
independent of |E| by construction (edge_mask is a runtime input port, not
a synthesis-time parameter); this corpus verifies *correctness* holds
across that whole topology range, using the real deployed weights.

Reuses the exact frozen weights/biases/shifts baked into
campaigns/qat_dsp_partitioning/frozen/source/root_graphsage_constants.h
(same array/shift names as generate_root_int8_po2.py's output - the
partitioned architecture uses the identical shift-per-branch scheme) so
the generated expected outputs are golden references for the SAME model
actually implemented in hardware, not a re-derivation from training.

Usage:
  python3 generate_edge_density_corpus.py
Writes:
  campaigns/qat_dsp_partitioning/frozen/source/root_graphsage_constants_density_coverage.h
"""
import re
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_HEADER = REPO_ROOT / "campaigns/qat_dsp_partitioning/frozen/source/root_graphsage_constants.h"
OUTPUT_HEADER = REPO_ROOT / "campaigns/qat_dsp_partitioning/frozen/source/root_graphsage_constants_density_coverage.h"

NUM_NODES = 8
IN_FEATURES = 16
HIDDEN_FEATURES = 24
OUT_FEATURES = 7
K = 4096  # degree-scale reciprocal base, matches root_degree_scale()/degree_scales()


def extract_array(text: str, name: str):
    """Extract a `static const|constexpr ... NAME[...] = { ... };` literal
    and eval it as nested Python lists (braces -> brackets)."""
    marker = re.search(rf"\b{re.escape(name)}\s*(\[[^=]*)?=\s*", text)
    if marker is None:
        raise ValueError(f"{name} not found")
    start = marker.end()
    # Balanced-brace scan from the first '{' after start.
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


def aggregate(features: np.ndarray, masks: list[int], shift: int) -> np.ndarray:
    out = np.zeros_like(features, dtype=np.int8)
    for node in range(NUM_NODES):
        mask = masks[node]
        selected = [features[n].astype(np.int64) for n in range(NUM_NODES) if mask & (1 << n)]
        neighbor_sum = np.sum(selected, axis=0, dtype=np.int64) if selected else np.zeros(features.shape[1], dtype=np.int64)
        degree = popcount8(mask)
        scale = degree_scale(degree)
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


def build_topology_corpus() -> list[dict]:
    """Each entry: name, masks (8 ints), description. Spans |E|=0..64."""
    graphs = []

    graphs.append(dict(name="EMPTY", masks=[0] * 8,
                        note="|E|=0, every node isolated"))

    m = [0] * 8
    m[1] = 1 << 0  # node1's only neighbor is node0
    graphs.append(dict(name="SINGLE_EDGE", masks=m,
                        note="|E|=1, one degree-1 node, seven degree-0 nodes"))

    graphs.append(dict(name="RING", masks=[1 << ((i - 1) % 8) for i in range(8)],
                        note="|E|=8, uniform degree-1 ring"))

    star = [0] * 8
    star[0] = 0xFE  # hub aggregates all 7 leaves
    for leaf in range(1, 8):
        star[leaf] = 1 << 0  # each leaf aggregates only the hub
    graphs.append(dict(name="STAR_HUB0", masks=star,
                        note="one degree-7 hub, seven degree-1 leaves"))

    chain = [0] * 8
    for i in range(1, 8):
        chain[i] = 1 << (i - 1)
    graphs.append(dict(name="CHAIN_WITH_ISOLATED_HEAD", masks=chain,
                        note="node0 degree-0, nodes1-7 form a degree-1 chain"))

    rng = np.random.default_rng(2026)
    for label, density in [("SPARSE_RANDOM", 0.25), ("MEDIUM_RANDOM", 0.5), ("DENSE_RANDOM", 0.75)]:
        masks = []
        for _ in range(8):
            bits = (rng.random(8) < density).astype(int)
            masks.append(int(sum(b << i for i, b in enumerate(bits))))
        graphs.append(dict(name=label, masks=masks, note=f"~{int(density*100)}% random density"))

    graphs.append(dict(name="COMPLETE_WITH_SELF", masks=[0xFF] * 8,
                        note="|E|=64 max, uniform degree-8 (includes self bit)"))

    graphs.append(dict(name="COMPLETE_NO_SELF", masks=[0xFF & ~(1 << i) for i in range(8)],
                        note="|E|=56, uniform degree-7, self bit excluded"))

    graphs.append(dict(name="DEGREE_SWEEP_1_TO_8", masks=[(1 << (i + 1)) - 1 for i in range(8)],
                        note="single graph exercising every degree 1..8 at once"))

    max_iso = [0] * 8
    max_iso[0] = 0xFF
    graphs.append(dict(name="MAX_DEGREE_WITH_ISOLATED_PEERS", masks=max_iso,
                        note="one degree-8 node among seven degree-0 nodes"))

    checker = [0xAA if i % 2 == 0 else 0x55 for i in range(8)]
    graphs.append(dict(name="CHECKERBOARD_BIPARTITE", masks=checker,
                        note="uniform degree-4, bipartite-like alternating pattern"))

    clique_iso = [0x00, 0x00, 0x00, 0x00, 0xE0, 0xD0, 0xB0, 0x70]
    graphs.append(dict(name="ISOLATED_QUAD_PLUS_CLIQUE_QUAD", masks=clique_iso,
                        note="4 isolated (degree-0) nodes + a 4-node degree-3 clique, same graph"))

    return graphs


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
    all_inputs = np.array(extract_array(text, "ROOT_TEST_INPUTS"), dtype=np.int64)
    fixed_input = all_inputs[0].astype(np.int8)  # hold node features fixed; vary only topology
    print(f"Reused frozen weights/shifts from {FROZEN_HEADER.name}; "
          f"fixed input = ROOT_TEST_INPUTS[0] (shape {fixed_input.shape})")

    topologies = build_topology_corpus()
    masks_all, expected_all, edge_counts, degree_lists = [], [], [], []
    for g in topologies:
        out = forward(fixed_input, g["masks"], params)
        masks_all.append(g["masks"])
        expected_all.append(out.tolist())
        degrees = [popcount8(m) for m in g["masks"]]
        degree_lists.append(degrees)
        edge_counts.append(sum(degrees))

    def fmt1d(values):
        return "{" + ", ".join(str(int(v)) for v in values) + "}"

    def fmt2d(values):
        return "{\n" + ",\n".join("    " + fmt1d(row) for row in values) + "\n}"

    def fmt3d(values):
        return "{\n" + ",\n".join("    " + fmt2d(m).replace("\n", "\n    ") for m in values) + "\n}"

    num_graphs = len(topologies)
    lines = [
        "#pragma once",
        "",
        "// Edge-density / topology coverage corpus (supplementary to the 256-graph",
        "// production regression corpus). Node features are held FIXED across every",
        "// graph (= ROOT_TEST_INPUTS[0] from the production corpus); only the",
        "// edge_mask topology varies, deliberately spanning |E|=0 (EMPTY) to",
        "// |E|=64 (COMPLETE_WITH_SELF), including explicit degree-0/1/max-degree",
        "// nodes and canonical topologies (ring, star, chain, bipartite, clique).",
        "// Golden outputs computed by campaigns/tns_final/scripts/",
        "// generate_edge_density_corpus.py using the SAME frozen weights/biases/",
        "// shifts as the production corpus (root_graphsage_constants.h) - this is",
        "// the actual deployed A5/V2A1_allcut model, not a re-derivation.",
        "//",
        "// Topology  |E|  per-node degrees  note",
    ]
    for g, ec, degs in zip(topologies, edge_counts, degree_lists):
        lines.append(f"// {g['name']:32s} {ec:3d}  {degs}  {g['note']}")
    lines += [
        "",
        f"static constexpr int ROOT_NUM_TEST_GRAPHS = {num_graphs};",
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
        f"static const data_t ROOT_TEST_INPUTS[ROOT_NUM_TEST_GRAPHS][ROOT_NUM_NODES][ROOT_IN_FEATURES] = "
        + fmt3d([fixed_input.tolist()] * num_graphs) + ";",
        f"static const edge_mask_t ROOT_TEST_MASKS[ROOT_NUM_TEST_GRAPHS][ROOT_NUM_NODES] = {fmt2d(masks_all)};",
        f"static const data_t ROOT_EXPECTED_OUTPUTS[ROOT_NUM_TEST_GRAPHS][ROOT_NUM_NODES][ROOT_OUT_FEATURES] = {fmt3d(expected_all)};",
        "",
    ]
    OUTPUT_HEADER.write_text("\n".join(lines))
    print(f"Wrote {OUTPUT_HEADER} ({num_graphs} graphs)")
    for g, ec, degs in zip(topologies, edge_counts, degree_lists):
        print(f"  {g['name']:32s} |E|={ec:3d} degrees={degs}")


if __name__ == "__main__":
    main()
