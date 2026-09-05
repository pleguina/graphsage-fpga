#!/usr/bin/env python3
"""Parse Vivado `report_timing -max_paths 100` text reports
(reports/worst_setup_paths.rpt, present for every routed run directory in
this campaign) into structured path records, and classify each path into a
stable category for plan Section 8 (critical-path attribution).

Categories (plan Section 8.2's list, plus one addition):
  DSP_INPUT           - path crosses from fabric into a DSP48E2 port (or vice
                         versa), e.g. a scale/quantization register feeding
                         DSP_A_B_DATA_INST / DSP_PREADD_DATA_INST
  DSP_PIPELINE        - path stays between two DSP-internal pipeline stages
  FABRIC_MULTIPLIER   - path is inside an HLS `mul_*` shift-add multiplier
                         implemented in CARRY8/LUT fabric (no DSP48E2)
  CARRY_REDUCTION     - generic addition/accumulation chain (add_ln*, acc_*)
                         not already tagged as GraphSAGE aggregation
  AGGREGATION         - GraphSAGE neighbor-sum / root-reduce / normalize path
                         (aggregate*, root_dynamic_reduce/mean/normalize)
  REQUANTIZATION_CLAMP- combine/clamp/relu/saturate/requantize path
  HIGH_FANOUT_CONTROL - ap_enable/ap_ready/ap_done/ap_start or edge_masks
                         (runtime adjacency broadcast) driving many endpoints
  MEMORY              - BRAM/URAM/FIFO path
  REGISTER_ROUTING    - zero logic levels, no functional-block name match
                         (pure placement/routing hop between generic FFs)
  OTHER               - has logic but matches no functional-block pattern
  UNCLASSIFIED        - source/destination could not be parsed
  CLOCK_SKEW          - NOT in the plan's original list. Added because the
                         A0/A1 "unoptimized baseline" checkpoints turn out to
                         fail timing almost entirely due to ~3.85ns of
                         source/destination clock-tree skew (Source Clock
                         Delay - Destination Clock Delay), not logic or
                         routing delay (their Data Path Delay is ~0.1ns).
                         Bucketing these as REGISTER_ROUTING or OTHER would
                         misattribute the actual physical cause, so they get
                         their own category. See build_critical_path_categories.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

CLOCK_SKEW_THRESHOLD_NS = 0.3  # normal skew observed in this campaign is ~0.01ns

GROUP_RE = re.compile(r"grp_l(?P<layer>[12])_(?P<branch>root|neighbor)_channel_\w+?_(?P<channel>\d+)_")

DSP_TOKEN_RE = re.compile(r"DSP48|DSP_A_B_DATA_INST|DSP_PREADD_DATA_INST|DSP_M_DATA|DSP_ALU_DATA|DSP_C_DATA|am_addmul|ama_addmuladd|_psdsp|weighted_sum")
CONTROL_RE = re.compile(r"\bap_enable_reg|\bap_ready\b|\bap_done\b|\bap_start\b|\bap_ce\b|edge_masks")
FABRIC_MUL_RE = re.compile(
    r"\bmul_\d+\w*_\d+\w*_\d+_|half[01]_\d|pair\d?_\d+_reg|partial_(hi|lo)|"
    r"_product_\d|root_product|input_\d+_\d+_\d+_data_reg"
)
AGGREGATION_RE = re.compile(r"aggregate|root_dynamic_reduce|root_dynamic_mean|root_dynamic_normalize|neighbor_sum")
REQUANT_RE = re.compile(r"combine|clamp|relu|saturate|requant|shift_res")
CARRY_REDUCTION_RE = re.compile(r"add_ln|\bacc_\d|_acc_reg")
MEMORY_RE = re.compile(r"bram|uram|fifo|_mem_", re.IGNORECASE)


@dataclass
class PathRecord:
    rank: int
    slack_ns: float
    violated: bool
    source: str
    destination: str
    data_path_delay_ns: float | None
    logic_delay_ns: float | None
    logic_pct: float | None
    route_delay_ns: float | None
    route_pct: float | None
    logic_levels: int | None
    src_clock_delay_ns: float | None
    dst_clock_delay_ns: float | None
    category: str = field(init=False, default="UNCLASSIFIED")
    layer: str | None = field(init=False, default=None)
    branch: str | None = field(init=False, default=None)
    channel: str | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.category = classify(self)
        for text in (self.destination, self.source):
            m = GROUP_RE.search(text)
            if m:
                self.layer, self.branch, self.channel = f"L{m.group('layer')}", m.group("branch"), m.group("channel")
                break


def classify(p: "PathRecord") -> str:
    if not p.source or not p.destination:
        return "UNCLASSIFIED"
    text = f"{p.source} {p.destination}"

    if p.src_clock_delay_ns is not None and p.dst_clock_delay_ns is not None:
        if abs(p.src_clock_delay_ns - p.dst_clock_delay_ns) > CLOCK_SKEW_THRESHOLD_NS:
            return "CLOCK_SKEW"

    if DSP_TOKEN_RE.search(text):
        src_dsp = bool(DSP_TOKEN_RE.search(p.source))
        dst_dsp = bool(DSP_TOKEN_RE.search(p.destination))
        return "DSP_PIPELINE" if (src_dsp and dst_dsp) else "DSP_INPUT"
    if CONTROL_RE.search(text):
        return "HIGH_FANOUT_CONTROL"
    if FABRIC_MUL_RE.search(text):
        return "FABRIC_MULTIPLIER"
    if AGGREGATION_RE.search(text):
        return "AGGREGATION"
    if REQUANT_RE.search(text):
        return "REQUANTIZATION_CLAMP"
    if CARRY_REDUCTION_RE.search(text):
        return "CARRY_REDUCTION"
    if MEMORY_RE.search(text):
        return "MEMORY"
    if p.logic_levels == 0:
        return "REGISTER_ROUTING"
    return "OTHER"


_FLOAT = r"(-?\d+\.\d+)"


def parse_worst_setup_paths(report_path: Path) -> list[PathRecord]:
    text = report_path.read_text(errors="replace")
    chunks = text.split("Slack (")[1:]
    records = []
    for rank, chunk in enumerate(chunks, start=1):
        violated = chunk.startswith("VIOLATED")
        slack_hdr = re.search(rf"^\w+\)\s*:\s*{_FLOAT}ns", chunk)
        source = re.search(r"Source:\s+(\S+)", chunk)
        destination = re.search(r"Destination:\s+(\S+)", chunk)
        dpd = re.search(rf"Data Path Delay:\s+{_FLOAT}ns\s+\(logic\s+{_FLOAT}ns\s+\(([\d.]+)%\)\s+route\s+{_FLOAT}ns\s+\(([\d.]+)%\)\)", chunk)
        levels = re.search(r"Logic Levels:\s+(\d+)", chunk)
        dcd = re.search(rf"Destination Clock Delay \(DCD\):\s+{_FLOAT}ns", chunk)
        scd = re.search(rf"Source Clock Delay\s+\(SCD\):\s+{_FLOAT}ns", chunk)

        # Slack line may report "arrival time" fallback if header regex misses (rare formatting edge).
        slack_ns = float(slack_hdr.group(1)) if slack_hdr else float(re.search(rf"slack\s+{_FLOAT}", chunk).group(1))

        records.append(PathRecord(
            rank=rank,
            slack_ns=slack_ns,
            violated=violated,
            source=source.group(1) if source else "",
            destination=destination.group(1) if destination else "",
            data_path_delay_ns=float(dpd.group(1)) if dpd else None,
            logic_delay_ns=float(dpd.group(2)) if dpd else None,
            logic_pct=float(dpd.group(3)) if dpd else None,
            route_delay_ns=float(dpd.group(4)) if dpd else None,
            route_pct=float(dpd.group(5)) if dpd else None,
            logic_levels=int(levels.group(1)) if levels else None,
            src_clock_delay_ns=float(scd.group(1)) if scd else None,
            dst_clock_delay_ns=float(dcd.group(1)) if dcd else None,
        ))
    return records
