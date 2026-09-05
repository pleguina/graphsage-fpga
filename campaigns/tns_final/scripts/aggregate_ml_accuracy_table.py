#!/usr/bin/env python3
"""Aggregate existing per-seed results.json across datasets into Table I
(mean +/- std accuracy). Reads only already-computed training outputs; no
new training is launched.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
STUDY_ROOT = (
    REPO_ROOT
    / "transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls"
    / "hls/cora_graphsage_hls_test_bundle/build/cora_hls_bundle/build/po2_qat_study"
)
OUTPUT = REPO_ROOT / "campaigns/tns_final/paper_data/ml_accuracy_table.csv"

DATASETS = ("cora", "citeseer", "pubmed", "ppi")


def load_seed_results(dataset_dir: Path) -> list[dict]:
    rows = []
    for seed_dir in sorted(dataset_dir.glob("seed_*")):
        results_path = seed_dir / "results.json"
        if not results_path.exists():
            continue
        try:
            data = json.loads(results_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        data["seed_dir"] = seed_dir.name
        rows.append(data)
    return rows


def metric_key(rows: list[dict]) -> str:
    for row in rows:
        if "metric" in row:
            return row["metric"]
    return "NA"


def test_value(row: dict) -> float | None:
    metrics = row.get("metrics")
    if isinstance(metrics, dict) and "test" in metrics:
        return float(metrics["test"])
    for candidate in ("test_micro_f1", "test_acc", "test_accuracy"):
        if candidate in row:
            return float(row[candidate])
    return None


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["dataset,metric,n_seeds,mean,std,values"]
    for dataset in DATASETS:
        dataset_dir = STUDY_ROOT / dataset
        if not dataset_dir.exists():
            lines.append(f"{dataset},NA,0,NA,NA,NA")
            continue
        rows = load_seed_results(dataset_dir)
        if not rows:
            lines.append(f"{dataset},NA,0,NA,NA,NA")
            continue
        key = metric_key(rows)
        values = [v for row in rows if (v := test_value(row)) is not None]
        if not values:
            lines.append(f"{dataset},{key},0,NA,NA,NA")
            continue
        mean = statistics.fmean(values)
        std = statistics.pstdev(values) if len(values) > 1 else 0.0
        values_str = ";".join(f"{v:.4f}" for v in values)
        lines.append(f"{dataset},{key},{len(values)},{mean:.4f},{std:.4f},{values_str}")

    OUTPUT.write_text("\n".join(lines) + "\n")
    print(f"WROTE={OUTPUT}")
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
