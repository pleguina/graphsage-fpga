#!/usr/bin/env python3
"""Generate paper-ready LaTeX tables (plan Section 25) from
campaigns/tns_final/paper_data/*.csv and a small set of verified constants.

Requires \\usepackage{booktabs} in the paper preamble.

Only tables fully supported by data already collected in this campaign are
produced. Not generated (data does not exist or cannot be attributed with
confidence):
  Table III  - HLS DSE across Float/PTQ/PO2/QAT-PO2: three old csynth
               snapshots exist under transfer/.../validation/*.xml but their
               naming does not reliably map to these four categories -
               mislabeling them would be worse than omitting the table.
  Table VI   - model-seed physical robustness: deliberately skipped (plan
               Section 9), per-seed weight-export path unconfirmed.
  Table VII  - verification: case counts / mismatch counts for the
               Python-vs-integer-reference and CSim-vs-RTL stages were not
               found as structured artifacts in this campaign; RTL cosim and
               back-to-back II=1 (Sections 13.3/13.4) were never run.
  Table VIII - related work: requires literature values, out of scope for a
               data-extraction script.

Produces, into campaigns/tns_final/tables/:
  table1_model_accuracy.tex
  table2_nominal_config.tex
  table4_architecture_ablation.tex
  table5_dsp_pipeline_sequence.tex
"""
from __future__ import annotations

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "campaigns/tns_final/paper_data"
TABLES_DIR = REPO_ROOT / "campaigns/tns_final/tables"


def read_csv(name: str) -> list[dict]:
    with (DATA_DIR / name).open(newline="") as fh:
        return list(csv.DictReader(fh))


def write(name: str, tex: str) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    path = TABLES_DIR / name
    path.write_text(tex)
    print(f"WROTE={path}")


DATASET_LABELS = {"cora": "Cora", "citeseer": "CiteSeer", "pubmed": "PubMed", "ppi": "PPI"}


def table1_model_accuracy() -> None:
    rows = {r["dataset"]: r for r in read_csv("ml_accuracy_table.csv")}
    order = ["cora", "citeseer", "pubmed", "ppi"]
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Model accuracy (mean $\pm$ std over 10 seeds). Float / INT8 PTQ / "
        r"PO2 PTQ baselines were not separately measured in this campaign\footnotemark[1].}",
        r"\label{tab:model-accuracy}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Dataset & Float & INT8 PTQ & PO2 PTQ & QAT-PO2 \\",
        r"\midrule",
    ]
    for key in order:
        r = rows[key]
        metric = "micro-F1" if r["metric"] == "micro_f1" else "acc."
        qat = f"{float(r['mean']):.3f} $\\pm$ {float(r['std']):.3f}"
        lines.append(f"{DATASET_LABELS[key]} ({metric}) & --- & --- & --- & {qat} \\\\")
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\footnotetext[1]{Only the frozen QAT-PO2 configuration used in the final "
        r"hardware implementation was evaluated across all ten training seeds.}",
        r"\end{table}",
    ]
    write("table1_model_accuracy.tex", "\n".join(lines) + "\n")


def table2_nominal_config() -> None:
    rows = [
        ("Nodes $N$", "8"),
        ("Input features", "16"),
        ("Hidden features", "24"),
        ("Output features", "7"),
        ("Activation / weight precision", "INT8 (\\texttt{ap\\_int<8>})"),
        ("Accumulator / bias precision", "22-bit (\\texttt{ap\\_int<22>})"),
        ("Clock target", "2.77\\,ns (361\\,MHz)"),
        ("Device", "xcvu13p-fsga2577-1-e"),
        ("Runtime topology", "Adjacency / edge mask (runtime input)"),
        ("Compile-time model", "Trained weights and biases (frozen constants)"),
        ("Initiation interval (II)", "1"),
    ]
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Nominal hardware/model configuration.}",
        r"\label{tab:nominal-config}",
        r"\begin{tabular}{ll}",
        r"\toprule",
        r"Parameter & Value \\",
        r"\midrule",
    ]
    for k, v in rows:
        lines.append(f"{k} & {v} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    write("table2_nominal_config.tex", "\n".join(lines) + "\n")


def table4_architecture_ablation() -> None:
    rows = read_csv("architecture_ablation.csv")
    by_variant = {r["variant"]: r for r in rows}
    order = ["A0", "A1", "A2", "A3", "A4", "A5"]
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Architecture ablation, routed results.}",
        r"\label{tab:architecture-ablation}",
        r"\begin{tabular}{lllccrrrrl}",
        r"\toprule",
        r"Variant & Channelized & Selective DSP & Acc.\ cuts & DSP & LUT & FF & "
        r"WNS [ns] & TNS [ns] & Status \\",
        r"\midrule",
    ]
    for v in order:
        r = by_variant[v]
        chan = "yes" if r["channelized"] == "True" else "no"
        sdsp = "yes" if r["selective_dsp"] == "True" else "no"
        cuts = "yes" if r["acc_cuts"] == "True" else "no"
        status = "met" if r["status"] == "timing_met" else "failed"
        lines.append(
            f"{v} & {chan} & {sdsp} & {cuts} & {int(float(r['util_dsp']))} & "
            f"{int(float(r['util_lut'])):,} & {int(float(r['util_ff'])):,} & "
            f"{float(r['timing_wns_ns']):.3f} & {float(r['timing_tns_ns']):.3f} & {status} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table*}"]
    write("table4_architecture_ablation.tex", "\n".join(lines) + "\n")


def _dominant_categories() -> dict[str, str]:
    """Dominant critical-path category per DSP-sweep variant, from the top-100
    worst setup endpoints (plan Section 8; see build_critical_path_categories.py).
    Ranked by accumulated negative slack; when that is zero everywhere (a
    checkpoint that closes timing, e.g. Final) falls back to endpoint count.
    """
    rows = read_csv("critical_path_categories.csv")
    by_checkpoint: dict[str, list[dict]] = {}
    for r in rows:
        by_checkpoint.setdefault(r["checkpoint"], []).append(r)

    checkpoint_for_variant = {
        "V1": "V1", "V2": "V2", "V3": "V3", "V4": "V4",
        "V2A1": "A2_selective_dsp", "Final": "A5_final",
    }
    result = {}
    for variant, checkpoint in checkpoint_for_variant.items():
        recs = by_checkpoint.get(checkpoint, [])
        if not recs:
            result[variant] = "---"
            continue
        total_pressure = sum(float(r["accumulated_negative_slack_ns"]) for r in recs)
        if total_pressure > 0:
            top = max(recs, key=lambda r: float(r["accumulated_negative_slack_ns"]))
            result[variant] = top["category"]
        else:
            top = max(recs, key=lambda r: int(r["endpoint_count"]))
            result[variant] = f"{top['category']} (by count, timing met)"
    return result


def table5_dsp_pipeline_sequence() -> None:
    rows = read_csv("dsp_sweep.csv")
    by_variant = {r["variant"]: r for r in rows}
    dominant = _dominant_categories()
    order = ["V1", "V2", "V3", "V4", "V2A1", "Final"]
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Guided physical optimization sequence. Dominant critical-path "
        r"category is the top category by accumulated negative slack among the "
        r"worst 100 routed setup endpoints (plan Section 8); see "
        r"\texttt{paper\_data/critical\_path\_categories.csv} for the full "
        r"per-category breakdown and Figure~5 for the migration across stages.}",
        r"\label{tab:dsp-pipeline-sequence}",
        r"\begin{tabular}{lrrrrrll}",
        r"\toprule",
        r"Variant & DSP & LUT & FF & WNS [ns] & TNS [ns] & Status & Dominant category \\",
        r"\midrule",
    ]
    for v in order:
        r = by_variant[v]
        status = "met" if r["status"] == "timing_met" else "failed"
        dom = dominant.get(v, "---").replace("_", "\\_")
        lines.append(
            f"{v} & {int(float(r['util_dsp']))} & {int(float(r['util_lut'])):,} & "
            f"{int(float(r['util_ff'])):,} & {float(r['timing_wns_ns']):.3f} & "
            f"{float(r['timing_tns_ns']):.3f} & {status} & {dom} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table*}"]
    write("table5_dsp_pipeline_sequence.tex", "\n".join(lines) + "\n")


def main() -> None:
    table1_model_accuracy()
    table2_nominal_config()
    table4_architecture_ablation()
    table5_dsp_pipeline_sequence()


if __name__ == "__main__":
    main()
