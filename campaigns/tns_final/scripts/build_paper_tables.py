#!/usr/bin/env python3
"""Assemble paper_data/*.csv from the campaign config registries and the
existing/new run directories they point to (plan Section 21, Job 13).

Safe to run at any time: entries whose run directory does not exist yet
(new Vivado jobs still queued/running) are emitted with NA metric fields
rather than failing the whole table.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from report_parsers import collect_run_metrics, parse_hls_metrics

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_ROOT = REPO_ROOT / "campaigns/tns_final/configs"
OUTPUT_ROOT = REPO_ROOT / "campaigns/tns_final/paper_data"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"WROTE={path} rows={len(rows)}")


def build_architecture_ablation() -> None:
    config = load_json(CONFIG_ROOT / "architecture/ablation.json")
    rows = []
    for name, entry in config["variants"].items():
        row = {"variant": name, "label": entry["label"], "channelized": entry["channelized"],
               "selective_dsp": entry["selective_dsp"], "acc_cuts": entry["acc_cuts"],
               "physical_strategy": entry["physical_strategy"], "status": entry["status"]}
        run_dir = entry.get("run_dir")
        if run_dir and (REPO_ROOT / run_dir).exists():
            row.update(collect_run_metrics(REPO_ROOT, run_dir))
        rows.append(row)
    write_csv(OUTPUT_ROOT / "architecture_ablation.csv", rows)


def build_dsp_sweep() -> None:
    config = load_json(CONFIG_ROOT / "dsp_masks/dsp_sweep.json")
    rows = []
    for name, entry in config["variants"].items():
        row = {"variant": name, "hls_dsp_estimate": entry["hls_dsp"], "status": entry["status"],
               "masks": json.dumps(entry["masks"])}
        run_dir = entry.get("run_dir")
        if run_dir and (REPO_ROOT / run_dir).exists():
            row.update(collect_run_metrics(REPO_ROOT, run_dir))
        rows.append(row)
    write_csv(OUTPUT_ROOT / "dsp_sweep.csv", rows)


def build_pipeline_sweep() -> None:
    config = load_json(CONFIG_ROOT / "pipeline_masks/pipeline_sweep.json")
    rows = []
    for name, entry in config["variants"].items():
        row = {"variant": name, "label": entry["label"], "routed": entry["routed"],
               "pipeline_masks": json.dumps(entry["pipeline_masks"]), "status": entry["status"]}
        run_dir = entry.get("run_dir")
        if run_dir and (REPO_ROOT / run_dir).exists():
            row.update(collect_run_metrics(REPO_ROOT, run_dir))
        elif entry.get("hls_project"):
            project_dir = REPO_ROOT / entry["hls_project"]
            if project_dir.exists():
                row.update({f"hls_{k}": v for k, v in parse_hls_metrics(project_dir).items()})
        rows.append(row)
    write_csv(OUTPUT_ROOT / "pipeline_sweep.csv", rows)


def build_physical_robustness() -> None:
    config = load_json(CONFIG_ROOT / "physical_strategies/strategies.json")
    rows = []
    for name, entry in config["variants"].items():
        row = {"variant": name, "label": entry["label"], "place_directive": entry["place_directive"],
               "route_directive": entry["route_directive"], "use_retime": entry["use_retime"],
               "status": entry["status"]}
        run_dir = entry.get("run_dir")
        if run_dir and (REPO_ROOT / run_dir).exists():
            row.update(collect_run_metrics(REPO_ROOT, run_dir))
        rows.append(row)
    write_csv(OUTPUT_ROOT / "physical_robustness.csv", rows)


def build_clock_sweep() -> None:
    config = load_json(CONFIG_ROOT / "clock_sweep/periods.json")
    rows = []
    for period in config["periods_ns"]:
        run_dir = config["run_dirs"][f"{period:.2f}"]
        row = {"period_ns": period, "target_frequency_mhz": round(1000.0 / period, 1)}
        if (REPO_ROOT / run_dir).exists():
            row.update(collect_run_metrics(REPO_ROOT, run_dir))
        rows.append(row)
    write_csv(OUTPUT_ROOT / "clock_sweep.csv", rows)


def build_model_seeds() -> None:
    config = load_json(CONFIG_ROOT / "model_seeds/seeds.json")
    rows = []
    for name, entry in config["variants"].items():
        row = {"variant": name, "label": entry["label"], "model_seed": entry["model_seed"],
               "status": entry["status"]}
        run_dir = entry.get("run_dir")
        if run_dir and (REPO_ROOT / run_dir).exists():
            row.update(collect_run_metrics(REPO_ROOT, run_dir))
        rows.append(row)
    write_csv(OUTPUT_ROOT / "model_seeds.csv", rows)


def main() -> None:
    build_architecture_ablation()
    build_dsp_sweep()
    build_pipeline_sweep()
    build_physical_robustness()
    build_clock_sweep()
    build_model_seeds()


if __name__ == "__main__":
    main()
