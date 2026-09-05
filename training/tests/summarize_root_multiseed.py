#!/usr/bin/env python3
"""Aggregate root-enabled Planetoid and PPI results across seeds."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("float_root", "ptq_int8_root", "po2_root", "qat_root")


def summarize(values, float_values):
    array = np.asarray(values, dtype=np.float64)
    delta = array - np.asarray(float_values, dtype=np.float64)
    tolerance = 1e-12
    if np.all(np.abs(delta) <= tolerance):
        confidence_interval = [0.0, 0.0]
        paired_p_value = 1.0
    else:
        standard_error = stats.sem(delta)
        margin = stats.t.ppf(0.975, len(delta) - 1) * standard_error
        confidence_interval = [float(delta.mean() - margin), float(delta.mean() + margin)]
        paired_p_value = float(stats.ttest_rel(array, float_values).pvalue)
    return {
        "mean": float(array.mean()),
        "sample_std": float(array.std(ddof=1)),
        "mean_paired_delta_vs_float": float(delta.mean()),
        "paired_delta_95_percent_ci": confidence_interval,
        "paired_t_test_two_sided_p_value": paired_p_value,
        "wins_vs_float": int((delta > tolerance).sum()),
        "ties_vs_float": int((np.abs(delta) <= tolerance).sum()),
        "losses_vs_float": int((delta < -tolerance).sum()),
        "values_by_seed": [float(value) for value in array],
    }


def load_planetoid(root, dataset, seeds):
    reports = []
    for seed in seeds:
        path = root / dataset.lower() / f"seed_{seed}" / "results.json"
        reports.append(json.loads(path.read_text(encoding="ascii")))
    values = {
        variant: [report["metrics"][variant]["test"] for report in reports]
        for variant in VARIANTS
    }
    return {
        "metric": "accuracy",
        "seeds": seeds,
        "variants": {
            variant: summarize(variant_values, values["float_root"])
            for variant, variant_values in values.items()
        },
    }


def load_ppi(root, seeds):
    reports = []
    for seed in seeds:
        path = root / f"seed_{seed}" / "results.json"
        reports.append(json.loads(path.read_text(encoding="ascii")))
    values = {
        variant: [report["metrics"][variant] for report in reports] for variant in VARIANTS
    }
    summary = {
        "metric": "micro_f1",
        "seeds": seeds,
        "variants": {
            variant: summarize(variant_values, values["float_root"])
            for variant, variant_values in values.items()
        },
    }
    summary["po2_peak_saturation_percent_by_seed"] = [
        report["integer_details"]["po2_peak_output_saturation_percent"] for report in reports
    ]
    summary["po2_layer2_shifts_by_seed"] = [
        report["integer_details"]["po2_shifts_layer2"] for report in reports
    ]
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(42, 52)))
    parser.add_argument(
        "--planetoid-root",
        type=Path,
        default=PROJECT_ROOT / "build" / "root_planetoid_study",
    )
    parser.add_argument(
        "--ppi-root", type=Path, default=PROJECT_ROOT / "build" / "root_ppi_study"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "build" / "root_multiseed_summary.json",
    )
    args = parser.parse_args()

    result = {
        dataset: load_planetoid(args.planetoid_root, dataset, args.seeds)
        for dataset in ("Cora", "CiteSeer", "PubMed")
    }
    result["PPI"] = load_ppi(args.ppi_root, args.seeds)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")

    for dataset, dataset_summary in result.items():
        print(f"\n{dataset} ({dataset_summary['metric']}, n={len(args.seeds)})")
        for variant in VARIANTS:
            stats = dataset_summary["variants"][variant]
            print(
                f"  {variant:14s} {stats['mean']:.4f} +/- {stats['sample_std']:.4f}  "
                f"delta={stats['mean_paired_delta_vs_float']:+.4f}  "
                f"CI=[{stats['paired_delta_95_percent_ci'][0]:+.4f}, "
                f"{stats['paired_delta_95_percent_ci'][1]:+.4f}]  "
                f"p={stats['paired_t_test_two_sided_p_value']:.4f}  "
                f"W/T/L={stats['wins_vs_float']}/{stats['ties_vs_float']}/"
                f"{stats['losses_vs_float']}"
            )
    print(f"\nSummary: {args.output}")


if __name__ == "__main__":
    main()