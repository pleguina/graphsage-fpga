#!/usr/bin/env python3
"""
Extract quantitative no-bubble/back-to-back evidence from a Vitis HLS
C/RTL cosim log's "RTL Simulation : N / M [...] @ "<time>"" progress
lines (real RTL-simulator timestamps in ps, one per completed transaction).

For an ap_ctrl_none, PIPELINE II=1 design, these timestamps are the
ground truth for "one transaction retired per clock, no idle cycles" -
if consecutive completions are one clock period apart throughout (after
an initial pipeline-fill transient), that IS the RTL-level proof of
back-to-back streaming; a bubble would show up as an extra, unexplained
gap anywhere in the middle of the run.

Usage:
  python3 analyze_cosim_bubble_timing.py <cosim_log.out> [--clock-ns 2.77] [--num-transactions 1024]
"""
import argparse
import re
import statistics
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_path")
    parser.add_argument("--clock-ns", type=float, default=2.77)
    parser.add_argument("--num-transactions", type=int, default=1024)
    args = parser.parse_args()

    text = open(args.log_path).read()
    matches = re.findall(r'RTL Simulation : (\d+) / \d+ \[[\d.]+%\] @ "(\d+)"', text)
    if not matches:
        print("NO_TIMING_LINES_FOUND", file=sys.stderr)
        sys.exit(1)

    counts = [int(n) for n, _ in matches]
    times_ps = [int(t) for _, t in matches]
    print(f"completion events found: {len(times_ps)} (expected ~{args.num_transactions})")
    print(f"first count={counts[0]} last count={counts[-1]}")

    deltas = [times_ps[i + 1] - times_ps[i] for i in range(len(times_ps) - 1)]
    clock_ps = args.clock_ns * 1000.0

    # The first delta is the pipeline-fill transient (startup latency), not a
    # steady-state inter-transaction gap - separate it from the rest.
    startup_ps = deltas[0]
    steady_deltas = deltas[1:]

    mean_steady = statistics.fmean(steady_deltas)
    stdev_steady = statistics.pstdev(steady_deltas)
    max_steady = max(steady_deltas)
    min_steady = min(steady_deltas)

    print(f"\nstartup transient (first completion gap): {startup_ps} ps "
          f"({startup_ps / clock_ps:.2f} clock periods)")
    print(f"steady-state inter-completion deltas: n={len(steady_deltas)}")
    print(f"  mean = {mean_steady:.1f} ps  (clock period = {clock_ps:.1f} ps, "
          f"ratio = {mean_steady / clock_ps:.4f})")
    print(f"  stdev = {stdev_steady:.1f} ps")
    print(f"  min = {min_steady} ps, max = {max_steady} ps")

    # A real bubble/stall would show up as a steady-state delta well above
    # the log's own timestamp-rounding noise band (~1 clock period +/- the
    # sim's reporting granularity). Flag anything more than 1.5 clock
    # periods as suspicious.
    bubble_threshold_ps = clock_ps * 1.5
    suspicious = [(i, d) for i, d in enumerate(steady_deltas) if d > bubble_threshold_ps]
    print(f"\nsteady-state deltas exceeding 1.5x clock period ({bubble_threshold_ps:.0f} ps): "
          f"{len(suspicious)}")
    for i, d in suspicious[:20]:
        print(f"  after completion #{i + 2}: gap={d} ps ({d / clock_ps:.2f} clock periods)")

    ok = len(suspicious) == 0 and len(times_ps) >= args.num_transactions
    print(f"\nNO_BUBBLE_VERDICT={'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
