#!/usr/bin/env python3
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
OUTPUT = ROOT / "build/vivado_sweep/updated_root_po2_comparison.json"

VARIANTS = {
    "baseline_po2_ptq": {
        "hls": PACKAGE / "build/hls/cora_root_dynamic_const_weights_2024_1/solution1/syn/report/graphsage_root_dynamic_const_weights_csynth.xml",
        "run": ROOT / "build/vivado_sweep/updated_root_low_dsp_route_default",
    },
    "qat_po2": {
        "hls": PACKAGE / "build/hls/cora_po2_qat_root_dynamic_const_weights_2024_1/solution1/syn/report/graphsage_po2_qat_root_dynamic_const_weights_csynth.xml",
        "run": ROOT / "build/vivado_sweep/updated_qat_po2_low_dsp_route_default",
    },
}


def metadata(path):
    if not path.exists():
        return {}
    return {
        key: value
        for line in path.read_text(errors="replace").splitlines()
        if "=" in line
        for key, value in [line.split("=", 1)]
    }


def first_text(root, tag):
    node = root.find(f".//{tag}")
    return node.text if node is not None else None


def hls_metrics(path):
    if not path.exists():
        return {"available": False}
    root = ET.parse(path).getroot()
    return {
        "available": True,
        "latency_cycles": first_text(root, "Worst-caseLatency"),
        "ii": first_text(root, "Interval-min"),
        "estimated_period_ns": first_text(root, "EstimatedClockPeriod"),
        "dsp": first_text(root, "DSP"),
        "ff": first_text(root, "FF"),
        "lut": first_text(root, "LUT"),
        "bram_18k": first_text(root, "BRAM_18K"),
    }


def timing_metrics(path):
    if not path.exists():
        return {"available": False}
    text = path.read_text(errors="replace")
    match = re.search(
        r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+\d+\s+"
        r"(-?\d+\.\d+)\s+(-?\d+\.\d+)",
        text,
        re.MULTILINE,
    )
    if not match:
        return {"available": True, "parsed": False}
    return {
        "available": True,
        "parsed": True,
        "wns_ns": match.group(1),
        "tns_ns": match.group(2),
        "failing_endpoints": match.group(3),
        "whs_ns": match.group(4),
    }


def worst_path_slack(path):
    if not path.exists():
        return {"available": False}
    text = path.read_text(errors="replace")
    match = re.search(r"Slack \((?:VIOLATED|MET)\)\s*:\s*(-?\d+\.\d+)ns", text)
    return {
        "available": True,
        "slack_ns": match.group(1) if match else None,
    }


def utilization(path):
    if not path.exists():
        return {"available": False}
    text = path.read_text(errors="replace")
    patterns = {
        "lut": r"\| CLB LUTs\s+\|\s*(\d+)",
        "ff": r"\| CLB Registers\s+\|\s*(\d+)",
        "dsp": r"\| DSPs\s+\|\s*(\d+)",
        "bram_tiles": r"\| Block RAM Tile\s+\|\s*(\d+)",
        "uram": r"\| URAM\s+\|\s*(\d+)",
    }
    result = {"available": True}
    for name, pattern in patterns.items():
        match = re.search(pattern, text)
        result[name] = match.group(1) if match else None
    return result


def route_status(path):
    if not path.exists():
        return {"available": False}
    text = path.read_text(errors="replace")
    result = {"available": True}
    match = re.search(r"# of fully routed nets\.*\s*:\s*(\d+)", text, re.IGNORECASE)
    result["fully_routed_nets"] = match.group(1) if match else None
    match = re.search(r"# of nets with routing errors\.*\s*:\s*(\d+)", text, re.IGNORECASE)
    result["nets_with_routing_errors"] = match.group(1) if match else None
    return result


def slr_metrics(path):
    if not path.exists():
        return {"available": False}
    text = path.read_text(errors="replace")
    match = re.search(r"\| Total SLLs Used\s*\|\s*(\d+)", text)
    return {
        "available": True,
        "total_slls_used": match.group(1) if match else None,
    }


def collect_variant(paths):
    reports = paths["run"] / "reports"
    return {
        "hls": hls_metrics(paths["hls"]),
        "vivado_metadata": metadata(paths["run"] / "metadata.txt"),
        "timing_final": timing_metrics(reports / "timing_final.rpt"),
        "internal_setup": worst_path_slack(reports / "timing_internal_setup_final.rpt"),
        "internal_hold": worst_path_slack(reports / "timing_internal_hold_final.rpt"),
        "utilization_final": utilization(reports / "utilization_final.rpt"),
        "route_status": route_status(reports / "route_status.rpt"),
        "slr": slr_metrics(reports / "utilization_slr_final.rpt"),
        "final_checkpoint": (paths["run"] / "final.dcp").exists(),
    }


def main():
    result = {name: collect_variant(paths) for name, paths in VARIANTS.items()}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    print(f"UPDATED_ROOT_COMPARISON={OUTPUT}")


if __name__ == "__main__":
    main()