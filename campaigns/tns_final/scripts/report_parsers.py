#!/usr/bin/env python3
"""Shared parsers for HLS csynth.xml and Vivado post-route reports.

Used by build_paper_tables.py to assemble the architecture-ablation,
DSP-sweep, pipeline-sweep, physical-robustness, and clock-sweep CSVs from
existing report files, without re-deriving numbers by hand.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def find_csynth_xml(hls_project_dir: Path) -> Path | None:
    matches = sorted((hls_project_dir / "solution1" / "syn" / "report").glob("*_csynth.xml"))
    return matches[0] if matches else None


def parse_hls_metrics(hls_project_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {key: "NA" for key in (
        "target_period_ns", "estimated_period_ns", "latency_best_cycles",
        "latency_worst_cycles", "ii_cycles", "dsp", "ff", "lut", "bram_18k", "uram",
    )}
    xml_path = find_csynth_xml(hls_project_dir)
    if xml_path is None or not xml_path.exists():
        return result
    root = ET.parse(xml_path).getroot()

    def text(path: str) -> str | None:
        node = root.find(path)
        return node.text if node is not None else None

    result["target_period_ns"] = text("UserAssignments/TargetClockPeriod") or "NA"
    result["estimated_period_ns"] = text("PerformanceEstimates/SummaryOfTimingAnalysis/EstimatedClockPeriod") or "NA"
    result["latency_best_cycles"] = text("PerformanceEstimates/SummaryOfOverallLatency/Best-caseLatency") or "NA"
    result["latency_worst_cycles"] = text("PerformanceEstimates/SummaryOfOverallLatency/Worst-caseLatency") or "NA"
    result["ii_cycles"] = text("PerformanceEstimates/SummaryOfOverallLatency/PipelineInitiationInterval") or "NA"
    for key, tag in (("dsp", "DSP"), ("ff", "FF"), ("lut", "LUT"), ("bram_18k", "BRAM_18K"), ("uram", "URAM")):
        result[key] = text(f"AreaEstimates/Resources/{tag}") or "NA"
    return result


def _read(path: Path) -> str:
    return path.read_text(errors="replace") if path.exists() else ""


def parse_timing_summary(report_path: Path) -> dict[str, Any]:
    result = {key: "NA" for key in ("wns_ns", "tns_ns", "setup_failing", "whs_ns", "ths_ns", "hold_failing")}
    text = _read(report_path)
    match = re.search(
        r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)",
        text, re.MULTILINE,
    )
    if match:
        result.update(
            wns_ns=match.group(1), tns_ns=match.group(2), setup_failing=match.group(3),
            whs_ns=match.group(4), ths_ns=match.group(5), hold_failing=match.group(6),
        )
    else:
        # Fallback: "Setup : N Failing Endpoints, Worst Slack X ns" lines.
        setup = re.search(r"Setup\s*:\s*(\d+)\s+Failing Endpoints,\s*Worst Slack\s*(-?\d+\.\d+)ns", text)
        hold = re.search(r"Hold\s*:\s*(\d+)\s+Failing Endpoints,\s*Worst Slack\s*(-?\d+\.\d+)ns", text)
        if setup:
            result["setup_failing"], result["wns_ns"] = setup.group(1), setup.group(2)
        if hold:
            result["hold_failing"], result["whs_ns"] = hold.group(1), hold.group(2)
    return result


def parse_utilization(report_path: Path) -> dict[str, Any]:
    result = {key: "NA" for key in ("lut", "ff", "dsp", "bram", "uram", "carry8")}
    text = _read(report_path)
    patterns = {
        "lut": r"\|\s*CLB LUTs\s*\|\s*(\d+)",
        "ff": r"\|\s*CLB Registers\s*\|\s*(\d+)",
        "dsp": r"\|\s*DSPs\s*\|\s*(\d+)",
        "bram": r"\|\s*Block RAM Tile\s*\|\s*(\d+)",
        "uram": r"\|\s*URAM\s*\|\s*(\d+)",
        "carry8": r"\|\s*CARRY8\s*\|\s*(\d+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            result[key] = match.group(1)
    return result


def parse_route_status(report_path: Path) -> dict[str, Any]:
    result = {key: "NA" for key in ("routing_errors", "unrouted_nets")}
    text = _read(report_path)
    errors = re.search(r"#\s*of nets with routing errors\.+\s*:\s*(\d+)", text)
    unrouted = re.search(r"#\s*of nets not needing routing\.+\s*:\s*(\d+)", text)
    if errors:
        result["routing_errors"] = errors.group(1)
    if unrouted:
        result["unrouted_nets"] = unrouted.group(1)
    return result


def parse_metadata(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def collect_run_metrics(repo_root: Path, run_dir: str) -> dict[str, Any]:
    """Collect the standard post-route metric bundle for one routed run directory."""
    run_path = repo_root / run_dir
    reports = run_path / "reports"
    metrics: dict[str, Any] = {"run_dir": run_dir}
    metrics.update(parse_metadata(run_path / "metadata.txt"))
    metrics.update({f"timing_{k}": v for k, v in parse_timing_summary(reports / "timing_final.rpt").items()})
    metrics.update({f"util_{k}": v for k, v in parse_utilization(reports / "utilization_final.rpt").items()})
    metrics.update({f"route_{k}": v for k, v in parse_route_status(reports / "route_status.rpt").items()})
    return metrics
