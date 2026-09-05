#!/usr/bin/env python3
"""Critical-path attribution campaign (plan Section 8), built entirely from
reports/worst_setup_paths.rpt (Vivado `report_timing -max_paths 100`), which
exists for every routed run directory in this campaign - no new Vivado runs
needed.

Caveat carried through every output: these are the worst 100 setup endpoints
per checkpoint, not all failing endpoints. Section 8's category-pressure sums
are therefore a proxy for the true TNS (see timing_tns_ns in
architecture_ablation.csv / dsp_sweep.csv for the full-design TNS), not an
exact accounting of it.

Writes:
  paper_data/critical_path_categories.csv        - per (checkpoint, category)
      endpoint_count, worst_slack_ns, accumulated_negative_slack_ns,
      mean_routing_fraction. Covers every checkpoint with a
      worst_setup_paths.rpt (A0, A1, V1-V4, A2/A3/A4, A5), not just the four
      used in Figure 5.
  paper_data/critical_path_semantic_groups_A5.csv - Section 8.3 semantic
      grouping (layer, branch, channel) for the Final (A5) checkpoint,
      ranked by accumulated negative slack.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from critical_path_report import parse_worst_setup_paths

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "campaigns/tns_final/paper_data"

# checkpoint label -> run_dir (relative to REPO_ROOT), taken from the same
# run_dir values already present in paper_data/{architecture_ablation,dsp_sweep}.csv
CHECKPOINTS = {
    "A0":          "build/vivado_sweep/updated_qat_po2_low_dsp_route_default",
    "A1_initial":  "build/vivado_sweep/updated_qat_partitioned_baseline_route_default",
    "V1":          "build/vivado_sweep/qat_dsp_V1_route_default",
    "V2":          "build/vivado_sweep/qat_dsp_V2_route_default",
    "V3":          "build/vivado_sweep/qat_dsp_V3_route_default",
    "V4":          "build/vivado_sweep/qat_dsp_V4_route_default",
    "A2_selective_dsp": "build/vivado_sweep/qat_dsp_V2A1_route_default",
    "A3":          "build/vivado_sweep/qat_dsp_A3_route_default",
    "A4_post_pipeline_cut": "build/vivado_sweep/qat_dsp_V2A1_allcut_route_default",
    "A5_final":    "build/vivado_sweep/qat_dsp_V2A1_allcut_ssi_retime_route",
}

# The four stages plan Section 24 / Figure 5 actually asks for.
FIGURE5_STAGES = {
    "Initial": "A1_initial",
    "Selective-DSP": "A2_selective_dsp",
    "Post-pipeline-cut": "A4_post_pipeline_cut",
    "Final": "A5_final",
}


def build_category_table() -> None:
    rows = []
    for checkpoint, run_dir in CHECKPOINTS.items():
        report = REPO_ROOT / run_dir / "reports" / "worst_setup_paths.rpt"
        if not report.exists():
            continue
        records = parse_worst_setup_paths(report)
        by_cat: dict[str, list] = {}
        for r in records:
            by_cat.setdefault(r.category, []).append(r)
        for category, recs in by_cat.items():
            pressure = sum(max(0.0, -r.slack_ns) for r in recs)
            worst = min(r.slack_ns for r in recs)
            frac_candidates = [
                r.route_delay_ns / r.data_path_delay_ns
                for r in recs
                if r.data_path_delay_ns and r.data_path_delay_ns > 0 and category != "CLOCK_SKEW"
            ]
            mean_frac = sum(frac_candidates) / len(frac_candidates) if frac_candidates else ""
            rows.append({
                "checkpoint": checkpoint,
                "run_dir": run_dir,
                "category": category,
                "endpoint_count": len(recs),
                "worst_slack_ns": round(worst, 4),
                "accumulated_negative_slack_ns": round(pressure, 4),
                "mean_routing_fraction": round(mean_frac, 4) if mean_frac != "" else "",
            })

    out = DATA_DIR / "critical_path_categories.csv"
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "checkpoint", "run_dir", "category", "endpoint_count",
            "worst_slack_ns", "accumulated_negative_slack_ns", "mean_routing_fraction",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"WROTE={out} rows={len(rows)}")


def build_semantic_groups_final() -> None:
    run_dir = CHECKPOINTS["A5_final"]
    report = REPO_ROOT / run_dir / "reports" / "worst_setup_paths.rpt"
    records = parse_worst_setup_paths(report)

    groups: dict[tuple, list] = {}
    for r in records:
        if r.layer is None:
            continue
        key = (r.layer, r.branch, r.channel)
        groups.setdefault(key, []).append(r)

    rows = []
    for (layer, branch, channel), recs in sorted(
        groups.items(), key=lambda kv: -sum(max(0.0, -r.slack_ns) for r in kv[1])
    ):
        pressure = sum(max(0.0, -r.slack_ns) for r in recs)
        worst = min(r.slack_ns for r in recs)
        rows.append({
            "layer": layer, "branch": branch, "channel": channel,
            "endpoint_count": len(recs),
            "worst_slack_ns": round(worst, 4),
            "accumulated_negative_slack_ns": round(pressure, 4),
        })

    out = DATA_DIR / "critical_path_semantic_groups_A5.csv"
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "layer", "branch", "channel", "endpoint_count",
            "worst_slack_ns", "accumulated_negative_slack_ns",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"WROTE={out} rows={len(rows)}")
    if rows:
        print("Top 5 (layer, branch, channel) groups in A5 top-100 setup endpoints "
              "(note: A5 is timing_met, so this ranks the least-slack-margin groups, "
              "not failing groups):")
        for row in rows[:5]:
            print(" ", row)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    build_category_table()
    build_semantic_groups_final()


if __name__ == "__main__":
    main()
