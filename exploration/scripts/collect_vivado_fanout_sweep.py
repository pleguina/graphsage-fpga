#!/usr/bin/env python3

import csv
from pathlib import Path
from typing import Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
SWEEP_DIR = ROOT / "build" / "vivado_sweep"
TARGETS = (96, 64, 48, 32, 24)


def read_key_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def topology_metrics(path: Path) -> Tuple[Optional[int], int, int, int]:
    if not path.exists():
        return None, 0, 0, 0

    fanouts = []
    source_cells = set()
    source_regions = set()
    sink_regions = set()
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if int(row["dsp_sinks"]) == 0:
                continue
            fanouts.append(int(row["fanout"]))
            source_cells.add(row["source"].rsplit("/", 1)[0])
            source_regions.update(row["source_clock_regions"].split(","))
            sink_regions.update(row["sink_clock_regions"].split(","))

    source_regions.discard("NA")
    sink_regions.discard("NA")
    return (
        max(fanouts) if fanouts else None,
        len(source_cells),
        len(source_regions),
        len(sink_regions),
    )


rows = []
for target in TARGETS:
    run_dir = SWEEP_DIR / f"fanout_{target}"
    metadata = read_key_values(run_dir / "metadata.txt")
    timing = read_key_values(run_dir / "reports" / "timing_stages.txt")
    max_fanout, sources, source_regions, sink_regions = topology_metrics(
        run_dir / "reports" / "topology_after_replication.tsv"
    )
    rows.append(
        {
            "target": target,
            "status": metadata.get("status", "incomplete"),
            "selected_nets": metadata.get("selected_replication_nets", "NA"),
            "actual_max_dsp_fanout": max_fanout if max_fanout is not None else "NA",
            "dsp_source_cells": sources,
            "source_clock_regions": source_regions,
            "sink_clock_regions": sink_regions,
            "post_place_wns_ns": timing.get("post_place_internal_setup_wns_ns", "NA"),
            "post_replication_wns_ns": timing.get(
                "post_replication_internal_setup_wns_ns", "NA"
            ),
            "post_route_wns_ns": timing.get("post_route_internal_setup_wns_ns", "NA"),
            "post_route_physopt_wns_ns": timing.get(
                "post_route_physopt_internal_setup_wns_ns", "NA"
            ),
            "runtime_seconds": metadata.get("runtime_seconds", "NA"),
        }
    )

completed = [row for row in rows if row["status"] == "implementation_complete"]
completed.sort(key=lambda row: float(row["post_route_physopt_wns_ns"]), reverse=True)
incomplete = [row for row in rows if row["status"] != "implementation_complete"]
ranked = completed + incomplete

output_path = SWEEP_DIR / "fanout_sweep_results.csv"
with output_path.open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(ranked)

print(f"Wrote {output_path}")
print(
    "target status actual_max_fanout post_replication_wns "
    "post_route_wns post_route_physopt_wns"
)
for row in ranked:
    print(
        row["target"],
        row["status"],
        row["actual_max_dsp_fanout"],
        row["post_replication_wns_ns"],
        row["post_route_wns_ns"],
        row["post_route_physopt_wns_ns"],
    )