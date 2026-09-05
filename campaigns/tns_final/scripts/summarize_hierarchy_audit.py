#!/usr/bin/env python3
"""Post-process hierarchy_audit.tcl's raw CSV into the true top-level
(layer, branch, channel) unit summary (plan Section 16).

hierarchy_audit.tcl's raw output over-matches: any nested sub-cell whose
full hierarchical path contains the pattern substring (e.g. every
arithmetic macro instantiated *inside* a channel) is captured as its own
row, in addition to the channel's own top-level row. Since Vivado always
returns full hierarchical paths, a row is a genuine top-level channel unit
only if no other matched row is one of its ancestors (i.e. no other row's
path is a strict prefix of it, split on "/"). The top-level row's own
lut/ff/dsp fields already aggregate its whole subtree (hierarchy_audit.tcl
computes them from "^<cell>/.*"), so no re-aggregation is needed here.

Usage:
    summarize_hierarchy_audit.py <raw.csv> [<summary.csv>]
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

EXPECTED_COUNTS = {
    "l1_root_channel": 24,
    "l1_neighbor_channel": 24,
    "l2_root_channel": 7,
    "l2_neighbor_channel": 7,
}


def is_top_level(hier_cell: str, all_paths: set[str]) -> bool:
    parts = hier_cell.split("/")
    return not any("/".join(parts[:i]) in all_paths for i in range(1, len(parts)))


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Usage: summarize_hierarchy_audit.py <raw.csv> [<summary.csv>]")

    raw_path = Path(sys.argv[1])
    summary_path = Path(sys.argv[2]) if len(sys.argv) == 3 else raw_path.with_name(
        raw_path.stem + "_summary.csv"
    )

    with raw_path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    all_paths = {row["hier_cell"] for row in rows}
    top_level = [row for row in rows if is_top_level(row["hier_cell"], all_paths)]

    counts: dict[str, int] = {}
    for row in top_level:
        counts[row["pattern"]] = counts.get(row["pattern"], 0) + 1

    with summary_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["pattern", "hier_cell", "lut", "ff", "dsp", "slr", "bbox"])
        writer.writeheader()
        for row in top_level:
            writer.writerow(row)

    print(f"WROTE={summary_path} rows={len(top_level)}")
    total_expected = sum(EXPECTED_COUNTS.values())
    total_found = sum(counts.values())
    for pattern, expected in EXPECTED_COUNTS.items():
        found = counts.get(pattern, 0)
        flag = "OK" if found == expected else "MISMATCH"
        print(f"{pattern}: found={found} expected={expected} [{flag}]")
    print(f"TOTAL: found={total_found} expected={total_expected}")


if __name__ == "__main__":
    main()
