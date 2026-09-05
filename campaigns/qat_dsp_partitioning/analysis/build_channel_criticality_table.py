#!/usr/bin/env python3
"""Build the (layer, branch, channel) criticality table for the instrumented QAT-PO2 design.

For each (layer, branch, output_channel) group this computes:
  - N: number of distinct violated endpoints found in the audited path sample
  - T: accumulated negative slack (sum of max(0, -slack) over those endpoints)
  - W: worst (most negative) slack in the group
    - dsp_analytical: analytical DSP increment estimate for moving this group to DSP.
        HLS folds weights 0 and +-1, while BIND_OP impl=dsp forces every other product
        to DSP, including larger powers of two. The fully unrolled node loop replicates
        each remaining product for all eight nodes.
        Exact values must still be confirmed with a per-group HLS csynth run.
    - ranking_tns_per_dsp = T / dsp_analytical (pressure efficiency)
    - ranking_wns_per_dsp = max(0, -W) / dsp_analytical (worst-path efficiency)
    - contains_global_wns: whether the group owns the worst path in the audit sample
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AUDIT_CSV = ROOT / "build/vivado_sweep/updated_qat_partitioned_baseline_route_default/reports/l2_channel_criticality_paths.csv"
CONSTANTS_HEADER = (
    ROOT
    / "transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
    / "hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/hls"
    / "po2_qat_root_dynamic_const_weights/generated/root_graphsage_constants.h"
)
OUTPUT_JSON = ROOT / "build/vivado_sweep/l1_l2_channel_criticality_table.json"

CELL_RE = re.compile(r"grp_l(1|2)_(root|neighbor)_channel_false_(\d+)_s_fu_\d+")
ROOT_NUM_NODES = 8

CATEGORY_PATTERNS = (
    (
        "aggregation_dsp_input",
        re.compile(r"DSP48|DSP_[A-Z_]+_DATA|am_addmul|aggregate|aggregation", re.IGNORECASE),
    ),
    (
        "control_enable",
        re.compile(r"(^|[/_])(ap_)?(ce|en|enable|control|ctrl|fsm|state)([/_]|$)|icmp|select_ln", re.IGNORECASE),
    ),
    (
        "adder_saturation_quantization",
        re.compile(r"add|sum|accum|sat|quant|requant|round|trunc|clip|sext|zext", re.IGNORECASE),
    ),
    (
        "pipeline_registers",
        re.compile(r"pp\d+_iter|pipeline|pipe|pair\d*_|tmp_reg|scale(?:_\d+)?_reg", re.IGNORECASE),
    ),
)


def classify(cell_path):
    if not cell_path:
        return None
    match = CELL_RE.search(cell_path)
    if not match:
        return None
    layer, branch, channel = int(match.group(1)), match.group(2), int(match.group(3))
    return layer, branch, channel


def classify_unassigned(start_cell, end_cell):
    path_text = f"{start_cell}/{end_cell}"
    for category, pattern in CATEGORY_PATTERNS:
        if pattern.search(path_text):
            return category
    return "unknown"


def parse_weight_matrix(text, name):
    match = re.search(rf"{name}\[[^;]*?\]\s*=\s*\{{(.*?)\}};", text, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find {name} in constants header")
    rows = re.findall(r"\{([^{}]*)\}", match.group(1))
    matrix = []
    for row in rows:
        values = [int(v.strip()) for v in row.split(",") if v.strip() != ""]
        matrix.append(values)
    return matrix


def analytical_dsp_for_row(row):
    return ROOT_NUM_NODES * sum(abs(int(weight)) > 1 for weight in row)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-csv", type=Path, default=AUDIT_CSV)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    return parser.parse_args()


def main():
    args = parse_args()
    audit_csv = args.audit_csv.resolve()
    output_json = args.output_json.resolve()

    if not audit_csv.exists():
        print(f"AUDIT_CSV_MISSING={audit_csv}")
        sys.exit(1)

    header_text = CONSTANTS_HEADER.read_text(errors="replace")
    matrices = {
        (1, "neighbor"): parse_weight_matrix(header_text, "ROOT_WEIGHTS1_NEIGHBOR"),
        (1, "root"): parse_weight_matrix(header_text, "ROOT_WEIGHTS1_ROOT"),
        (2, "neighbor"): parse_weight_matrix(header_text, "ROOT_WEIGHTS2_NEIGHBOR"),
        (2, "root"): parse_weight_matrix(header_text, "ROOT_WEIGHTS2_ROOT"),
    }

    groups = {}
    seen_endpoints = {}
    unclassified_paths = []
    total_rows = 0
    global_wns = None
    global_wns_owner = None

    with audit_csv.open() as handle:
        for row in csv.DictReader(handle):
            total_rows += 1
            slack = float(row["slack_ns"])
            if slack >= 0:
                continue
            start_cell = row["start_cell"]
            end_cell = row["end_cell"]
            classified = classify(end_cell)
            if global_wns is None or slack < global_wns:
                global_wns = slack
                global_wns_owner = classified
            if classified is None:
                category = classify_unassigned(start_cell, end_cell)
                unclassified_paths.append({
                    "slack": slack,
                    "start_cell": start_cell,
                    "end_cell": end_cell,
                    "category": category,
                })
                continue
            key = classified
            # Endpoint-unique aggregation: keep the worst slack seen per endpoint,
            # since a single physical endpoint can appear more than once in the sample.
            prior = seen_endpoints.get((key, end_cell))
            if prior is None or slack < prior:
                seen_endpoints[(key, end_cell)] = slack

    for (key, _end_cell), slack in seen_endpoints.items():
        group = groups.setdefault(key, {"count": 0, "tns": 0.0, "worst": 0.0})
        group["count"] += 1
        group["tns"] += -slack
        group["worst"] = min(group["worst"], slack)

    table = []
    for (layer, branch, channel), stats in groups.items():
        matrix = matrices[(layer, branch)]
        dsp_analytical = analytical_dsp_for_row(matrix[channel])
        ranking_tns = stats["tns"] / dsp_analytical if dsp_analytical > 0 else float("inf")
        ranking_wns = max(0.0, -stats["worst"]) / dsp_analytical if dsp_analytical > 0 else float("inf")
        table.append({
            "layer": layer,
            "branch": branch,
            "channel": channel,
            "endpoints": stats["count"],
            "worst_slack_ns": round(stats["worst"], 3),
            "accumulated_negative_slack_ns": round(stats["tns"], 3),
            "dsp_analytical": dsp_analytical,
            "ranking_tns_per_dsp": round(ranking_tns, 4),
            "ranking_wns_per_dsp": round(ranking_wns, 4),
            "contains_global_wns": (layer, branch, channel) == global_wns_owner,
        })

    table.sort(key=lambda entry: entry["ranking_tns_per_dsp"], reverse=True)

    category_stats = {
        category: {"paths": 0, "unique_end_cells": 0, "accumulated_negative_slack_ns": 0.0, "worst_slack_ns": 0.0, "examples": []}
        for category, _pattern in CATEGORY_PATTERNS
    }
    category_stats["unknown"] = {
        "paths": 0,
        "unique_end_cells": 0,
        "accumulated_negative_slack_ns": 0.0,
        "worst_slack_ns": 0.0,
        "examples": [],
    }
    category_end_cells = {category: set() for category in category_stats}
    for path in unclassified_paths:
        stats = category_stats[path["category"]]
        stats["paths"] += 1
        category_end_cells[path["category"]].add(path["end_cell"])
        stats["accumulated_negative_slack_ns"] += -path["slack"]
        stats["worst_slack_ns"] = min(stats["worst_slack_ns"], path["slack"])
        if len(stats["examples"]) < 5:
            stats["examples"].append({
                "slack_ns": path["slack"],
                "start_cell": path["start_cell"],
                "end_cell": path["end_cell"],
            })
    for category, stats in category_stats.items():
        stats["unique_end_cells"] = len(category_end_cells[category])
        stats["accumulated_negative_slack_ns"] = round(stats["accumulated_negative_slack_ns"], 3)
        stats["worst_slack_ns"] = round(stats["worst_slack_ns"], 3)

    result = {
        "audit_csv": str(audit_csv),
        "total_paths_in_sample": total_rows,
        "global_sample_wns_ns": round(global_wns, 3) if global_wns is not None else None,
        "global_sample_wns_owner": (
            {"layer": global_wns_owner[0], "branch": global_wns_owner[1], "channel": global_wns_owner[2]}
            if global_wns_owner is not None else None
        ),
        "unclassified_paths": len(unclassified_paths),
        "unclassified_categories": category_stats,
        "groups": table,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")

    print(f"{'layer':<7}{'branch':<9}{'ch':>3}{'endpoints':>11}{'worst_ns':>11}{'TNS_ns':>11}{'dsp_est':>9}{'TNS/DSP':>11}{'WNS/DSP':>11}{'global':>8}")
    for entry in table:
        print(
            f"{entry['layer']:<7}{entry['branch']:<9}{entry['channel']:>3}{entry['endpoints']:>11}"
            f"{entry['worst_slack_ns']:>11.3f}{entry['accumulated_negative_slack_ns']:>11.3f}"
            f"{entry['dsp_analytical']:>9}{entry['ranking_tns_per_dsp']:>11.4f}"
            f"{entry['ranking_wns_per_dsp']:>11.4f}{str(entry['contains_global_wns']):>8}"
        )
    print(f"GLOBAL_SAMPLE_WNS_NS={result['global_sample_wns_ns']}")
    print(f"GLOBAL_SAMPLE_WNS_OWNER={result['global_sample_wns_owner']}")
    for category, stats in category_stats.items():
        print(
            f"UNCLASSIFIED_CATEGORY={category} paths={stats['paths']} "
            f"unique_end_cells={stats['unique_end_cells']} "
            f"tns_ns={stats['accumulated_negative_slack_ns']:.3f} "
            f"worst_ns={stats['worst_slack_ns']:.3f}"
        )
    print(f"UNCLASSIFIED_PATHS={len(unclassified_paths)}/{total_rows}")
    print(f"CHANNEL_CRITICALITY_TABLE={output_json}")


if __name__ == "__main__":
    main()
