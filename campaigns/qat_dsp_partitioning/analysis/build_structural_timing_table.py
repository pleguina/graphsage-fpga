#!/usr/bin/env python3
"""Classify routed timing paths by physical structure rather than output channel."""
import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

CHANNEL_RE = re.compile(r"grp_l[12]_(?:root|neighbor)_channel_(?:true|false)_\d+_s_fu_\d+")
CATEGORIES = (
    "aggregation_dsp_input",
    "dsp_pipeline_output",
    "fabric_multiplier",
    "adder_carry8_reduction",
    "requantization_shift_clamp",
    "pipeline_enable_ce_reset",
    "ordinary_data_register_routing",
    "output_staging",
    "other",
)


def number(row, key):
    value = row.get(key, "NA")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify(row):
    start = row["start_cell"].lower()
    end = row["end_cell"].lower()
    refs = f"{row['start_ref']} {row['end_ref']} {row['primitive_chain']}".lower()
    names = f"{start} {end}"
    if "dsp" in row["end_ref"].lower() or "dsp_" in end:
        if re.search(r"aggregate|hidden|weighted_sum|tmp_|scale", names):
            return "aggregation_dsp_input"
        return "dsp_pipeline_output"
    if re.search(r"mul_\d|mult", names) and "dsp" not in refs:
        return "fabric_multiplier"
    if "carry8" in refs or re.search(r"add|sum|accum", names):
        return "adder_carry8_reduction"
    if re.search(r"requant|quant|shift|clamp|sat|round|trunc|sext|zext", names):
        return "requantization_shift_clamp"
    if re.search(r"ap_enable|enable|[/_]ce|reset|ap_rst|valid|fsm|state", names):
        return "pipeline_enable_ce_reset"
    if re.search(r"output|out_", end):
        return "output_staging"
    if row["start_ref"].startswith("FD") and row["end_ref"].startswith("FD"):
        return "ordinary_data_register_routing"
    return "other"


def hierarchy_hint(row):
    combined = f"{row['start_cell']} {row['end_cell']}"
    channel = CHANNEL_RE.search(combined)
    if channel:
        return channel.group(0)
    if "am_addmul" in combined:
        return "aggregation/addmul DSP fabric"
    if "hidden" in combined:
        return "hidden/L1-to-L2 staging"
    if "output" in combined:
        return "output staging"
    return "top-level or flattened"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_csv", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    rows = []
    with args.audit_csv.open() as handle:
        for row in csv.DictReader(handle):
            slack = number(row, "slack_ns")
            if slack is not None and slack < 0:
                row["category"] = classify(row)
                row["hierarchy_hint"] = hierarchy_hint(row)
                rows.append(row)

    buckets = defaultdict(list)
    for row in rows:
        buckets[row["category"]].append(row)

    categories = {}
    for category in CATEGORIES:
        paths = buckets[category]
        slacks = [number(path, "slack_ns") for path in paths]
        route_fractions = []
        fanouts = []
        for path in paths:
            route = number(path, "route_delay_ns")
            datapath = number(path, "datapath_delay_ns")
            if route is not None and datapath and datapath > 0:
                route_fractions.append(route / datapath)
            fanout = number(path, "max_fanout")
            if fanout is not None:
                fanouts.append(fanout)
        categories[category] = {
            "endpoints": len(paths),
            "worst_slack_ns": round(min(slacks), 3) if slacks else None,
            "accumulated_negative_slack_ns": round(sum(-slack for slack in slacks), 3),
            "average_routing_fraction": round(sum(route_fractions) / len(route_fractions), 4) if route_fractions else None,
            "max_fanout": int(max(fanouts)) if fanouts else None,
            "average_max_fanout": round(sum(fanouts) / len(fanouts), 2) if fanouts else None,
            "startpoint_primitives": sorted({path["start_ref"] for path in paths}),
            "endpoint_primitives": sorted({path["end_ref"] for path in paths}),
            "hierarchies": sorted({path["hierarchy_hint"] for path in paths}),
        }

    worst = min(rows, key=lambda row: number(row, "slack_ns")) if rows else None
    result = {
        "audit_csv": str(args.audit_csv.resolve()),
        "negative_paths": len(rows),
        "categories": categories,
        "global_wns_path": worst,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()