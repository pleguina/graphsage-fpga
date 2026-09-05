#!/usr/bin/env python3
"""Generate paper-ready figures (plan Section 24) from campaigns/tns_final/paper_data/*.csv.

Only figures fully supported by data already collected in this campaign are
produced. Not generated (data does not exist yet):
  Figure 1/2/3 - schematic diagrams, not data plots (draw by hand/vector tool)
  Figure 9 - scalability: needs the hidden-width scaling campaign (Section 12),
             not launched
  Figure 10 - optional channel-placement scatter, skipped

Produces, into campaigns/tns_final/plots/:
  fig4_wns_vs_dsp.pdf         - Figure 4
  fig5_bottleneck_migration.pdf - Figure 5 (now generated - see
                                 build_critical_path_categories.py for the
                                 underlying critical-path classification)
  fig5b_routing_fraction.pdf  - Section 8.5 routing-fraction distribution
  fig6a_ablation_wns.pdf      - Figure 6 (WNS panel)
  fig6b_ablation_resources.pdf- Figure 6 (DSP/LUT/FF panel, small multiples)
  fig7_pipeline_tradeoff.pdf  - Figure 7
  fig8_clock_sweep.pdf        - Figure 8
  figR_physical_robustness.pdf- Section 10 required plot (WNS by strategy)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from critical_path_report import parse_worst_setup_paths

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "campaigns/tns_final/paper_data"
PLOTS_DIR = REPO_ROOT / "campaigns/tns_final/plots"

# Categorical palette (dataviz skill reference palette, light mode).
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
GREEN = "#008300"   # status: timing_met
RED = "#e34948"     # status: timing_failed
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#d8d7d2"

plt.rcParams.update({
    "font.size": 8,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "svg.fonttype": "none",
})


VIOLET = "#4a3aa7"
YELLOW = "#eda100"
MAGENTA = "#e87ba4"

CATEGORY_COLORS = {
    "CLOCK_SKEW": VIOLET,
    "FABRIC_MULTIPLIER": BLUE,
    "DSP_INPUT": ORANGE,
    "DSP_PIPELINE": "#f2a373",  # lighter orange
    "CARRY_REDUCTION": AQUA,
    "AGGREGATION": YELLOW,
    "HIGH_FANOUT_CONTROL": MAGENTA,
    "REQUANTIZATION_CLAMP": GREEN,
    "MEMORY": RED,
    "REGISTER_ROUTING": MUTED,
    "OTHER": "#c3c2b7",
    "UNCLASSIFIED": "#8a8a86",
}


def read_csv(name: str) -> list[dict]:
    with (DATA_DIR / name).open(newline="") as fh:
        return list(csv.DictReader(fh))


def status_color(status: str) -> str:
    return GREEN if status == "timing_met" else RED


def save(fig, name: str) -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(PLOTS_DIR / f"{name}.{ext}", bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"WROTE={PLOTS_DIR / name}.pdf")


def fig4_wns_vs_dsp() -> None:
    rows = read_csv("dsp_sweep.csv")
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    for row in rows:
        dsp = float(row["util_dsp"])
        wns = float(row["timing_wns_ns"])
        color = status_color(row["status"])
        ax.scatter(dsp, wns, color=color, s=28, zorder=3, edgecolor="white", linewidth=0.5)
        ax.annotate(row["variant"], (dsp, wns), textcoords="offset points",
                    xytext=(4, 3), fontsize=6.5, color=MUTED)
    ax.axhline(0.0, color=INK, linewidth=0.8, linestyle="--", zorder=1)
    ax.set_xlabel("Routed DSP usage")
    ax.set_ylabel("Worst negative slack [ns]")
    handles = [
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=GREEN, label="timing met"),
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=RED, label="timing failed"),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=6.5, loc="lower right")
    fig.tight_layout()
    save(fig, "fig4_wns_vs_dsp")


FIG5_STAGES = [
    ("Initial", "A1_initial"),
    ("Selective-DSP", "A2_selective_dsp"),
    ("Post-pipeline-cut", "A4_post_pipeline_cut"),
    ("Final", "A5_final"),
]


def fig5_bottleneck_migration() -> None:
    rows = read_csv("critical_path_categories.csv")
    by_checkpoint: dict[str, dict[str, float]] = {}
    for r in rows:
        by_checkpoint.setdefault(r["checkpoint"], {})[r["category"]] = float(r["accumulated_negative_slack_ns"])

    # "Initial" (~175 ns, all clock skew) dwarfs the other three stages
    # (<=5.6 ns) by >30x, so a single linear axis would flatten them to
    # invisible slivers. Two panels, same category colors, different scales.
    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(7.0, 2.8),
                                             gridspec_kw={"width_ratios": [1, 2.4]})

    stage_checkpoints = [key for _, key in FIG5_STAGES]
    all_categories = sorted(
        {cat for k in stage_checkpoints for cat in by_checkpoint.get(k, {})},
        key=lambda c: c != "CLOCK_SKEW",
    )

    def stacked_bar(ax, stage_names, stage_keys):
        bottoms = [0.0] * len(stage_keys)
        for cat in all_categories:
            heights = [by_checkpoint.get(k, {}).get(cat, 0.0) for k in stage_keys]
            if sum(heights) == 0:
                continue
            ax.bar(stage_names, heights, bottom=bottoms, color=CATEGORY_COLORS.get(cat, "#999999"),
                   width=0.6, zorder=3, label=cat)
            bottoms = [b + h for b, h in zip(bottoms, heights)]

    stacked_bar(ax_left, ["Initial"], ["A1_initial"])
    ax_left.set_ylabel("Accumulated negative slack [ns]\n(top-100 setup endpoints)")
    ax_left.set_title("Initial", fontsize=8)

    right_names = ["Selective-\nDSP", "Post-pipeline-\ncut", "Final"]
    right_keys = ["A2_selective_dsp", "A4_post_pipeline_cut", "A5_final"]
    stacked_bar(ax_right, right_names, right_keys)
    ax_right.set_title("Selective-DSP -> Post-pipeline-cut -> Final", fontsize=8)
    ax_right.annotate("0 ns\n(timing met)", (2, 0.05), ha="center", fontsize=6.5, color=MUTED)

    handles = [plt.Rectangle((0, 0), 1, 1, color=CATEGORY_COLORS.get(c, "#999999"), label=c)
               for c in all_categories]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=6, frameon=False,
               bbox_to_anchor=(0.5, -0.16))
    fig.text(0.5, -0.30,
              "Categories from the worst-100 routed setup endpoints per checkpoint "
              "(see critical_path_categories.csv); not the full-design TNS.",
              ha="center", fontsize=6, color=MUTED)
    fig.tight_layout()
    save(fig, "fig5_bottleneck_migration")


def fig5b_routing_fraction() -> None:
    variants = [
        ("Selective-DSP", "build/vivado_sweep/qat_dsp_V2A1_route_default"),
        ("Post-pipeline-cut", "build/vivado_sweep/qat_dsp_V2A1_allcut_route_default"),
        ("Final", "build/vivado_sweep/qat_dsp_V2A1_allcut_ssi_retime_route"),
    ]
    data = []
    labels = []
    for label, run_dir in variants:
        report = REPO_ROOT / run_dir / "reports/worst_setup_paths.rpt"
        records = parse_worst_setup_paths(report)
        fractions = [r.route_delay_ns / r.data_path_delay_ns for r in records
                     if r.data_path_delay_ns and r.data_path_delay_ns > 0 and r.category != "CLOCK_SKEW"]
        data.append(fractions)
        labels.append(label)

    fig, ax = plt.subplots(figsize=(3.6, 2.6))
    bp = ax.boxplot(data, labels=labels, patch_artist=True, widths=0.5,
                     medianprops={"color": INK, "linewidth": 1.2},
                     whiskerprops={"color": MUTED}, capprops={"color": MUTED},
                     flierprops={"markersize": 3, "markeredgecolor": MUTED})
    for patch in bp["boxes"]:
        patch.set_facecolor(BLUE)
        patch.set_alpha(0.55)
        patch.set_edgecolor(MUTED)
    ax.set_ylabel("Routing fraction of data-path delay\n(route delay / data path delay)")
    ax.tick_params(axis="x", labelsize=7)
    fig.tight_layout()
    save(fig, "fig5b_routing_fraction")


def fig6_architecture_ablation() -> None:
    rows = read_csv("architecture_ablation.csv")
    order = ["A0", "A1", "A2", "A3", "A4", "A5"]
    rows_by_variant = {r["variant"]: r for r in rows}
    variants = [v for v in order if v in rows_by_variant]

    # Panel A: WNS bar, colored by pass/fail.
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    wns = [float(rows_by_variant[v]["timing_wns_ns"]) for v in variants]
    colors = [status_color(rows_by_variant[v]["status"]) for v in variants]
    ax.bar(variants, wns, color=colors, width=0.6, zorder=3)
    ax.axhline(0.0, color=INK, linewidth=0.8, zorder=2)
    ax.set_ylabel("Worst negative slack [ns]")
    ax.set_xlabel("Architecture variant")
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=GREEN, label="timing met"),
        plt.Rectangle((0, 0), 1, 1, color=RED, label="timing failed"),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=6.5, loc="lower right")
    fig.tight_layout()
    save(fig, "fig6a_ablation_wns")

    # Panel B: DSP / LUT / FF as small multiples (no dual axis).
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.2), sharex=True)
    metrics = [("util_dsp", "DSP", BLUE), ("util_lut", "LUT", ORANGE), ("util_ff", "FF", AQUA)]
    for ax, (key, label, color) in zip(axes, metrics):
        values = [float(rows_by_variant[v][key]) for v in variants]
        ax.bar(variants, values, color=color, width=0.6, zorder=3)
        ax.set_title(label, fontsize=8)
        ax.tick_params(axis="x", labelsize=7)
    axes[0].set_ylabel("Utilization (count)")
    fig.tight_layout()
    save(fig, "fig6b_ablation_resources")


def _hls_latency_lookup() -> dict:
    """Best-case latency (cycles) for each pipeline variant, from HLS csynth reports.

    P0 and P5 reuse the A2 / A4 HLS projects respectively (plan Section 7.1:
    "P0 and P5 already exist as A2 (V2A1) and A4 (V2A1_allcut)"); P5's own
    csynth report is not preserved on disk (no solution1/syn/report under its
    HLS project directory), so its latency is left unmeasured rather than
    guessed.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report_parsers import parse_hls_metrics

    base = "transfer/cora_graphsage_dynamic_root_hls_updated/build/cora_graphsage_dynamic_root_hls/build/hls"
    projects = {
        "P0": f"{base}/cora_po2_qat_V2A1_2024_1",
        "P1": f"{base}/cora_po2_qat_P1_2024_1",
        "P2": f"{base}/cora_po2_qat_P2_2024_1",
        "P3": f"{base}/cora_po2_qat_P3_2024_1",
        "P4": f"{base}/cora_po2_qat_P4_2024_1",
        "P5": f"{base}/cora_po2_qat_V2A1_allcut_2024_1",
    }
    out = {}
    for variant, rel in projects.items():
        m = parse_hls_metrics(REPO_ROOT / rel)
        out[variant] = m
    return out


def fig7_pipeline_tradeoff() -> None:
    rows = read_csv("pipeline_sweep.csv")
    rows_by_variant = {r["variant"]: r for r in rows}
    hls = _hls_latency_lookup()

    baseline = int(hls["P0"]["latency_best_cycles"])
    order = ["P0", "P1", "P2", "P3", "P4", "P5"]

    # Group variants that land on the exact same (added-latency, HLS-only)
    # point so labels don't overlap.
    hls_only_by_x: dict[int, list[str]] = {}
    routed_points = []
    for v in order:
        r = rows_by_variant[v]
        lat = hls[v]["latency_best_cycles"]
        if lat == "NA":
            continue
        added = int(lat) - baseline
        ii = hls[v]["ii_cycles"]
        routed = r["routed"] == "True"
        if routed and r.get("timing_wns_ns") not in (None, "", "NA"):
            routed_points.append((v, added, float(r["timing_wns_ns"]), r["status"], ii))
        else:
            hls_only_by_x.setdefault(added, []).append((v, ii))

    fig, ax = plt.subplots(figsize=(3.8, 3.1))
    for v, added, y, status, ii in routed_points:
        color = status_color(status)
        ax.scatter(added, y, color=color, marker="o", s=30, zorder=3,
                   edgecolor="white", linewidth=0.5)
        label = f"{v} (II={ii})" if ii != "NA" else v
        ax.annotate(label, (added, y), textcoords="offset points",
                    xytext=(5, 3), fontsize=6.5, color=MUTED)

    for added, entries in hls_only_by_x.items():
        ax.scatter(added, 0.0, facecolors="none", edgecolors=MUTED,
                   marker="^", s=30, zorder=3)
        label = "/".join(v for v, _ in entries) + f" (HLS-only, II={entries[0][1]})"
        ax.annotate(label, (added, 0.0), textcoords="offset points",
                    xytext=(5, -11), fontsize=6.5, color=MUTED)

    ax.axhline(0.0, color=INK, linewidth=0.8, linestyle="--", zorder=1)
    ax.set_xlabel("Added latency vs. no-cut baseline [cycles]")
    ax.set_ylabel("Worst negative slack [ns]\n(routed points only)")
    fig.tight_layout(rect=(0, 0.14, 1, 1))
    note = ("P5 HLS latency not independently synthesized; its routed WNS\n"
            "is reported in Table V, not plotted here.")
    fig.text(0.02, 0.02, note, fontsize=6, color=MUTED)
    save(fig, "fig7_pipeline_tradeoff")


def fig8_clock_sweep() -> None:
    rows = read_csv("clock_sweep.csv")
    rows.sort(key=lambda r: float(r["target_frequency_mhz"]))
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    freqs = [float(r["target_frequency_mhz"]) for r in rows]
    wns = [float(r["timing_wns_ns"]) for r in rows]
    colors = [status_color(r["status"]) for r in rows]
    ax.plot(freqs, wns, color=MUTED, linewidth=1.2, zorder=2)
    ax.scatter(freqs, wns, color=colors, s=30, zorder=3, edgecolor="white", linewidth=0.5)
    ax.axhline(0.0, color=INK, linewidth=0.8, linestyle="--", zorder=1)
    ax.axvline(361.0, color=BLUE, linewidth=1.0, linestyle=":", zorder=1)
    ax.annotate("361 MHz target", (361.0, max(wns)), textcoords="offset points",
                xytext=(4, 0), fontsize=6.5, color=BLUE)
    ax.set_xlabel("Target clock frequency [MHz]")
    ax.set_ylabel("Routed WNS [ns]")
    fig.tight_layout()
    save(fig, "fig8_clock_sweep")


def figR_physical_robustness() -> None:
    rows = read_csv("physical_robustness.csv")
    order = ["R0", "R1", "R2", "R3"]
    rows_by_variant = {r["variant"]: r for r in rows}
    variants = [v for v in order if v in rows_by_variant]
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    wns = [float(rows_by_variant[v]["timing_wns_ns"]) for v in variants]
    colors = [status_color(rows_by_variant[v]["status"]) for v in variants]
    ax.scatter(variants, wns, color=colors, s=45, zorder=3, edgecolor="white", linewidth=0.6)
    ax.axhline(0.0, color=INK, linewidth=0.8, linestyle="--", zorder=1)
    ax.set_ylabel("Routed WNS [ns]")
    ax.set_xlabel("Physical implementation strategy")
    handles = [
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=GREEN, label="timing met"),
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=RED, label="timing failed"),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=6.5, loc="lower right")
    fig.tight_layout()
    save(fig, "figR_physical_robustness")


def main() -> None:
    fig4_wns_vs_dsp()
    fig5_bottleneck_migration()
    fig5b_routing_fraction()
    fig6_architecture_ablation()
    fig7_pipeline_tradeoff()
    fig8_clock_sweep()
    figR_physical_robustness()


if __name__ == "__main__":
    main()
