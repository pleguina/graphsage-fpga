#!/usr/bin/env python3
"""Compare PO2-QAT with existing root-enabled multiseed baselines."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def paired_summary(values, reference):
    values = np.asarray(values, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    delta = values - reference
    margin = stats.t.ppf(0.975, len(delta) - 1) * stats.sem(delta)
    return {
        "mean": float(values.mean()),
        "sample_std": float(values.std(ddof=1)),
        "mean_paired_delta": float(delta.mean()),
        "paired_delta_95_percent_ci": [
            float(delta.mean() - margin),
            float(delta.mean() + margin),
        ],
        "paired_t_test_two_sided_p_value": float(stats.ttest_rel(values, reference).pvalue),
        "wins": int((delta > 1e-12).sum()),
        "ties": int((np.abs(delta) <= 1e-12).sum()),
        "losses": int((delta < -1e-12).sum()),
        "values_by_seed": values.tolist(),
    }


def load_baseline(summary, dataset, variant):
    return summary[dataset]["variants"][variant]["values_by_seed"]


def load_po2_qat(root, dataset, seeds):
    values = []
    for seed in seeds:
        report = json.loads(
            (root / dataset.lower() / f"seed_{seed}" / "results.json").read_text(
                encoding="ascii"
            )
        )
        key = "test"
        values.append(report["metrics"][key])
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=list(range(42, 52)))
    parser.add_argument(
        "--baseline", type=Path, default=PROJECT_ROOT / "build" / "root_multiseed_summary.json"
    )
    parser.add_argument(
        "--po2-qat-root", type=Path, default=PROJECT_ROOT / "build" / "po2_qat_study"
    )
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "build" / "po2_qat_multiseed_summary.json"
    )
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="ascii"))
    result = {}

    for dataset in ("Cora", "CiteSeer", "PubMed", "PPI"):
        po2_qat = load_po2_qat(args.po2_qat_root, dataset, args.seeds)
        variants = {}
        for name, baseline_key in (
            ("float_root", "float_root"),
            ("ptq_int8_root", "ptq_int8_root"),
            ("po2_ptq_root", "po2_root"),
            ("qat_root", "qat_root"),
        ):
            values = load_baseline(baseline, dataset, baseline_key)
            variants[name] = {
                "mean": float(np.mean(values)),
                "sample_std": float(np.std(values, ddof=1)),
                "values_by_seed": values,
            }
        variants["po2_qat_root_vs_float"] = paired_summary(
            po2_qat, variants["float_root"]["values_by_seed"]
        )
        variants["po2_qat_root_vs_po2_ptq"] = paired_summary(
            po2_qat, variants["po2_ptq_root"]["values_by_seed"]
        )
        variants["po2_qat_root_vs_qat"] = paired_summary(
            po2_qat, variants["qat_root"]["values_by_seed"]
        )
        result[dataset] = {
            "metric": baseline[dataset]["metric"],
            "seeds": args.seeds,
            "variants": variants,
        }

    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    for dataset, dataset_result in result.items():
        print(f"\n{dataset} ({dataset_result['metric']}, n={len(args.seeds)})")
        for variant in ("float_root", "ptq_int8_root", "po2_ptq_root", "qat_root"):
            entry = dataset_result["variants"][variant]
            print(f"  {variant:18s} {entry['mean']:.4f} +/- {entry['sample_std']:.4f}")
        po2_qat = dataset_result["variants"]["po2_qat_root_vs_float"]
        print(f"  {'po2_qat_root':18s} {po2_qat['mean']:.4f} +/- {po2_qat['sample_std']:.4f}")
        for comparison in ("po2_qat_root_vs_float", "po2_qat_root_vs_po2_ptq", "po2_qat_root_vs_qat"):
            entry = dataset_result["variants"][comparison]
            print(
                f"    {comparison}: delta={entry['mean_paired_delta']:+.4f} "
                f"CI=[{entry['paired_delta_95_percent_ci'][0]:+.4f},"
                f"{entry['paired_delta_95_percent_ci'][1]:+.4f}] "
                f"W/T/L={entry['wins']}/{entry['ties']}/{entry['losses']}"
            )
    print(f"\nSummary: {args.output}")


if __name__ == "__main__":
    main()