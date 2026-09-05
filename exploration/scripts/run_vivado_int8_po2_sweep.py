#!/usr/bin/env python3

import argparse
import csv
import os
import re
import subprocess
from pathlib import Path


# =============================================================================
# Paths
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parents[2]

SWEEP_DIR = REPO_ROOT / "build" / "vivado_sweep"

VIVADO = Path(
    os.environ.get(
        "VIVADO_BIN",
        "/tools/Xilinx/Vivado/2024.1/bin/vivado",
    )
)

BASELINE_TCL = (
    REPO_ROOT
    / "hls"
    / "build_vivado_int8_po2_sweep_baseline.tcl"
)

STRATEGY_TCL = (
    REPO_ROOT
    / "hls"
    / "run_vivado_int8_po2_strategy.tcl"
)


# =============================================================================
# Vivado implementation strategies
# =============================================================================
#
# "baseline" is now the true Vivado Default placement strategy.
#
# ExtraNetDelay_high is preserved as an independent candidate instead of being
# used as the baseline.
#
# This means we compare:
#
#   Default
#   ExtraNetDelay_high
#   AltSpreadLogic_high
#   AltSpreadLogic_medium
#   SSI_SpreadLogic_high
#   SSI_BalanceSLLs
#   SSI_SpreadSLLs
#   SSI_BalanceSLRs
#   ExtraTimingOpt
#   ExtraPostPlacementOpt
#
# =============================================================================

STRATEGIES = {
    "baseline": "Default",
    "extra_net_delay_high": "ExtraNetDelay_high",
    "altspread_high": "AltSpreadLogic_high",
    "altspread_medium": "AltSpreadLogic_medium",
    "ssi_spread_high": "SSI_SpreadLogic_high",
    "ssi_balance_sll": "SSI_BalanceSLLs",
    "ssi_spread_sll": "SSI_SpreadSLLs",
    "ssi_balance_slr": "SSI_BalanceSLRs",
    "extra_timing": "ExtraTimingOpt",
    "extra_postplace": "ExtraPostPlacementOpt",
}


# =============================================================================
# Default routing strategy
# =============================================================================
#
# We deliberately do NOT use AggressiveExplore for the normal campaign.
#
# If later we find one or two promising candidates very close to timing
# closure, an AggressiveExplore run can be launched separately for those
# finalists.
#
# =============================================================================

DEFAULT_ROUTE_DIRECTIVE = "Default"


# =============================================================================
# CSV output columns
# =============================================================================

RESULT_COLUMNS = [
    "run_name",
    "place_directive",
    "route_directive",
    "tns_cleanup",
    "postroute_physopt",
    "clock_period_ns",
    "post_place_wns_ns",
    "post_place_tns_ns",
    "post_route_wns_before_physopt_ns",
    "post_route_tns_before_physopt_ns",
    "post_route_wns_after_physopt_ns",
    "post_route_tns_after_physopt_ns",
    "setup_failing_endpoints",
    "hold_wns_ns",
    "unrouted_nets",
    "partially_routed_nets",
    "lut",
    "ff",
    "dsp",
    "bram",
    "uram",
    "slr0_lut",
    "slr1_lut",
    "slr2_lut",
    "slr3_lut",
    "slr01_sll",
    "slr12_sll",
    "slr23_sll",
    "max_local_sll_percent",
    "congestion_level",
    "runtime_seconds",
    "status",
]


# =============================================================================
# Vivado launcher
# =============================================================================

def run_vivado(
    run_dir: Path,
    tcl: Path,
    env: dict[str, str],
) -> int:
    """
    Run Vivado in batch mode.

    Parameters
    ----------
    run_dir:
        Directory in which Vivado will execute.

    tcl:
        Tcl script to execute.

    env:
        Additional environment variables passed to the Tcl script.

    Returns
    -------
    int
        Vivado process return code.
    """

    run_dir.mkdir(parents=True, exist_ok=True)

    command = [
        str(VIVADO),
        "-mode",
        "batch",
        "-source",
        str(tcl),
        "-log",
        str(run_dir / "vivado.log"),
        "-journal",
        str(run_dir / "vivado.jou"),
    ]

    completed = subprocess.run(
        command,
        cwd=run_dir,
        env={
            **os.environ,
            **env,
        },
    )

    return completed.returncode


# =============================================================================
# Build common post-synthesis checkpoint
# =============================================================================

def build_baseline() -> None:
    """
    Build the common post-synthesis checkpoint.

    All placement strategies start from exactly this same checkpoint, which is
    important for making the implementation strategy comparison fair.
    """

    checkpoint = SWEEP_DIR / "baseline_post_synth.dcp"

    if checkpoint.exists():
        print(f"Baseline already exists: {checkpoint}")
        return

    return_code = run_vivado(
        SWEEP_DIR / "baseline_build",
        BASELINE_TCL,
        {},
    )

    if return_code != 0:
        raise SystemExit(
            f"Baseline synthesis failed with exit code {return_code}"
        )


# =============================================================================
# Run one implementation strategy
# =============================================================================

def run_strategy(
    name: str,
    screen_only: bool,
) -> None:
    """
    Run one placement strategy.

    screen_only=True
        The Tcl script should stop after placement and post-place reporting.

    screen_only=False
        The Tcl script continues through physical optimization and routing.

    Important
    ---------
    The SCREEN_ONLY behaviour must also be implemented correctly inside
    run_vivado_int8_po2_strategy.tcl.

    Python can request SCREEN_ONLY=1, but the Tcl script is ultimately
    responsible for stopping before expensive phys_opt_design / route_design.
    """

    run_name = (
        f"screen_{name}"
        if screen_only
        else f"route_{name}"
    )

    run_dir = SWEEP_DIR / run_name
    metadata = run_dir / "metadata.txt"

    if metadata.exists():
        print(f"Skipping completed run: {run_name}")
        return

    env = {
        "RUN_NAME": run_name,

        # Placement strategy being studied.
        "PLACE_DIRECTIVE": STRATEGIES[name],

        # Normal/default routing.
        #
        # Previously this was AggressiveExplore.
        "ROUTE_DIRECTIVE": DEFAULT_ROUTE_DIRECTIVE,

        # Screening should finish after placement.
        "SCREEN_ONLY": "1" if screen_only else "0",

        # Only relevant for routed candidates.
        "USE_TNS_CLEANUP": "1",

        # There is no reason for a screening run to perform a post-route
        # physical optimization because it should never reach route_design.
        "USE_POST_PHYS": "0" if screen_only else "1",
    }

    print()
    print("=" * 78)
    print(f"Run name        : {run_name}")
    print(f"Placement       : {STRATEGIES[name]}")
    print(f"Routing         : {DEFAULT_ROUTE_DIRECTIVE}")
    print(f"Screen only     : {screen_only}")
    print("=" * 78)
    print()

    return_code = run_vivado(
        run_dir,
        STRATEGY_TCL,
        env,
    )

    # Exit code 2 may be intentionally used by the Tcl flow for a valid
    # non-closing implementation, so preserve the original behaviour.
    if return_code not in (0, 2):
        raise SystemExit(
            f"Vivado run {run_name} failed "
            f"with exit code {return_code}"
        )


# =============================================================================
# Timing report parser
# =============================================================================

def parse_timing(path: Path) -> dict[str, str]:
    """
    Parse the timing summary table from a Vivado timing report.

    Extracted values:
        wns      Worst Negative Slack / Worst Setup Slack
        tns      Total Negative Slack
        failing  Number of failing setup endpoints
        whs      Worst Hold Slack
    """

    result = {
        "wns": "NA",
        "tns": "NA",
        "failing": "NA",
        "whs": "NA",
    }

    if not path.exists():
        return result

    text = path.read_text(errors="replace")

    match = re.search(
        r"^\s*(-?\d+\.\d+)\s+"
        r"(-?\d+\.\d+)\s+"
        r"(\d+)\s+"
        r"\d+\s+"
        r"(-?\d+\.\d+)\s+"
        r"(-?\d+\.\d+)",
        text,
        re.MULTILINE,
    )

    if match:
        result.update(
            wns=match.group(1),
            tns=match.group(2),
            failing=match.group(3),
            whs=match.group(4),
        )

    return result


# =============================================================================
# Metadata parser
# =============================================================================

def parse_metadata(path: Path) -> dict[str, str]:
    """
    Read key=value metadata generated by the Tcl implementation script.
    """

    if not path.exists():
        return {}

    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


# =============================================================================
# Utilization parser
# =============================================================================

def parse_utilization(path: Path) -> dict[str, str]:
    """
    Extract main FPGA resource utilization from a Vivado utilization report.
    """

    result = {
        key: "NA"
        for key in (
            "lut",
            "ff",
            "dsp",
            "bram",
            "uram",
        )
    }

    if not path.exists():
        return result

    text = path.read_text(errors="replace")

    patterns = {
        "lut": r"\| CLB LUTs\s+\|\s*(\d+)",
        "ff": r"\| CLB Registers\s+\|\s*(\d+)",
        "dsp": r"\| DSPs\s+\|\s*(\d+)",
        "bram": r"\| Block RAM Tile\s+\|\s*(\d+)",
        "uram": r"\| URAM\s+\|\s*(\d+)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text)

        if match:
            result[key] = match.group(1)

    return result


# =============================================================================
# Route status parser
# =============================================================================

def parse_route_status(path: Path) -> dict[str, str]:
    """
    Extract unrouted and partially routed net counts.
    """

    result = {
        "unrouted": "NA",
        "partial": "NA",
    }

    if not path.exists():
        return result

    text = path.read_text(errors="replace")

    labels = (
        ("unrouted", "Unrouted Nets"),
        ("partial", "Partially Routed Nets"),
    )

    for key, label in labels:
        match = re.search(
            rf"{label}\s*[:|]\s*(\d+)",
            text,
        )

        if match:
            result[key] = match.group(1)

    return result


# =============================================================================
# Collect campaign results
# =============================================================================

def collect_results() -> list[dict[str, str]]:
    """
    Collect all completed runs into build/vivado_sweep/results.csv.

    IMPORTANT CHANGE
    ----------------
    Screening results are now taken from:

        timing_post_place.rpt

    rather than:

        timing_post_place_physopt.rpt

    This means placement strategies are ranked based on their actual
    post-place result, before phys_opt_design modifies the solution.
    """

    rows: list[dict[str, str]] = []

    for metadata_path in sorted(
        SWEEP_DIR.glob("*/metadata.txt")
    ):
        run_dir = metadata_path.parent
        reports = run_dir / "reports"

        metadata = parse_metadata(metadata_path)

        # ---------------------------------------------------------------------
        # Pure post-place timing
        # ---------------------------------------------------------------------
        #
        # This is the number that should be used to compare placement
        # directives during screening.
        #
        post_place = parse_timing(
            reports / "timing_post_place.rpt"
        )

        # ---------------------------------------------------------------------
        # Post-route timing before optional post-route phys_opt
        # ---------------------------------------------------------------------

        before = parse_timing(
            reports / "timing_post_route_before_physopt.rpt"
        )

        # ---------------------------------------------------------------------
        # Final timing
        # ---------------------------------------------------------------------

        final = parse_timing(
            reports / "timing_final.rpt"
        )

        # ---------------------------------------------------------------------
        # Final utilization
        # ---------------------------------------------------------------------

        utilization = parse_utilization(
            reports / "utilization_final.rpt"
        )

        # ---------------------------------------------------------------------
        # Route status
        # ---------------------------------------------------------------------

        route_status = parse_route_status(
            reports / "route_status.rpt"
        )

        row = {
            column: "NA"
            for column in RESULT_COLUMNS
        }

        row.update(
            run_name=metadata.get(
                "run_name",
                run_dir.name,
            ),

            place_directive=metadata.get(
                "place_directive",
                "NA",
            ),

            route_directive=metadata.get(
                "route_directive",
                "NA",
            ),

            tns_cleanup=metadata.get(
                "tns_cleanup",
                "NA",
            ),

            postroute_physopt=metadata.get(
                "postroute_physopt",
                "NA",
            ),

            clock_period_ns=metadata.get(
                "clock_period_ns",
                "NA",
            ),

            # Pure post-placement QoR.
            post_place_wns_ns=post_place["wns"],
            post_place_tns_ns=post_place["tns"],

            # Routed QoR before post-route physical optimization.
            post_route_wns_before_physopt_ns=before["wns"],
            post_route_tns_before_physopt_ns=before["tns"],

            # Final QoR.
            post_route_wns_after_physopt_ns=final["wns"],
            post_route_tns_after_physopt_ns=final["tns"],

            setup_failing_endpoints=final["failing"],
            hold_wns_ns=final["whs"],

            unrouted_nets=route_status["unrouted"],
            partially_routed_nets=route_status["partial"],

            runtime_seconds=metadata.get(
                "runtime_seconds",
                "NA",
            ),

            status=metadata.get(
                "status",
                "NA",
            ),

            **utilization,
        )

        rows.append(row)

    output_path = SWEEP_DIR / "results.csv"

    with output_path.open(
        "w",
        newline="",
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=RESULT_COLUMNS,
        )

        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Collected {len(rows)} runs into "
        f"{output_path}"
    )

    return rows


# =============================================================================
# Rank screening candidates
# =============================================================================

def ranked_screen_names(limit: int) -> list[str]:
    """
    Rank screening runs by pure post-placement WNS.

    Higher WNS is better.

    Example:

        -0.30 ns > -0.70 ns > -1.50 ns

    The baseline is deliberately always included so that the routed campaign
    always contains a direct comparison against Vivado Default.
    """

    rows = collect_results()

    candidates: list[tuple[float, str]] = []

    for row in rows:
        run_name = row["run_name"]

        if not run_name.startswith("screen_"):
            continue

        try:
            wns = float(row["post_place_wns_ns"])
        except (ValueError, TypeError):
            continue

        name = run_name.removeprefix("screen_")

        candidates.append(
            (
                wns,
                name,
            )
        )

    # Higher WNS is better.
    candidates.sort(
        reverse=True,
        key=lambda item: item[0],
    )

    print()
    print("Screening ranking:")
    print("-" * 78)

    for position, (wns, name) in enumerate(
        candidates,
        start=1,
    ):
        print(
            f"{position:2d}. "
            f"{name:28s} "
            f"WNS = {wns:+.3f} ns"
        )

    print("-" * 78)
    print()

    # Always retain the true Default baseline.
    names = ["baseline"]

    names.extend(
        name
        for _, name in candidates
        if name != "baseline"
    )

    return names[:limit]


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Vivado placement-strategy sweep for "
            "GraphSAGE INT8 power-of-two implementation."
        )
    )

    parser.add_argument(
        "stage",
        choices=(
            "baseline",
            "screen",
            "route",
            "collect",
            "campaign",
        ),
        help=(
            "baseline: build common post-synthesis checkpoint; "
            "screen: run placement-only strategy sweep; "
            "route: route selected/top screening candidates; "
            "collect: regenerate results.csv; "
            "campaign: run screen followed by routing."
        ),
    )

    parser.add_argument(
        "--top",
        type=int,
        default=4,
        help=(
            "Number of screening candidates to send to "
            "the full routing stage. Default: 4."
        ),
    )

    parser.add_argument(
        "--runs",
        nargs="*",
        choices=tuple(STRATEGIES),
        help=(
            "Optional explicit list of strategies to run. "
            "If omitted, all strategies are used for screening "
            "or the top ranked strategies are used for routing."
        ),
    )

    parser.add_argument(
        "--no-collect",
        action="store_true",
        help=(
            "Do not regenerate results.csv automatically "
            "after the selected stage."
        ),
    )

    args = parser.parse_args()

    SWEEP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -------------------------------------------------------------------------
    # Common post-synthesis baseline
    # -------------------------------------------------------------------------

    if args.stage in (
        "baseline",
        "screen",
        "route",
        "campaign",
    ):
        build_baseline()

    # -------------------------------------------------------------------------
    # Placement screening
    # -------------------------------------------------------------------------

    if args.stage in (
        "screen",
        "campaign",
    ):
        screen_names = (
            args.runs
            if args.runs
            else list(STRATEGIES)
        )

        for name in screen_names:
            run_strategy(
                name,
                screen_only=True,
            )

        if not args.no_collect:
            collect_results()

    # -------------------------------------------------------------------------
    # Full routing of finalists
    # -------------------------------------------------------------------------

    if args.stage in (
        "route",
        "campaign",
    ):
        if args.runs:
            route_names = args.runs
        else:
            route_names = ranked_screen_names(
                args.top
            )

        print()
        print(
            "Candidates selected for full implementation:"
        )

        for name in route_names:
            print(
                f"  {name:28s} "
                f"({STRATEGIES[name]})"
            )

        print()

        for name in route_names:
            run_strategy(
                name,
                screen_only=False,
            )

        if not args.no_collect:
            collect_results()

    # -------------------------------------------------------------------------
    # Collection only
    # -------------------------------------------------------------------------

    if args.stage == "collect":
        collect_results()


if __name__ == "__main__":
    main()