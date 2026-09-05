#!/usr/bin/env bash
# Submits the pipeline-cut sweep entries missing from the existing campaign
# (plan Section 7). P0 = A2/V2A1 and P5 = A4/V2A1_allcut already exist and
# are reused via symlinks in campaigns/tns_final/results/pipeline_sweep/.
# Fixed DSP policy for every entry: L1_NEIGHBOR_MASK=0x1004, AGGREGATION_MODE=4.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# P1: L1 root cuts only (HLS-only, per plan Section 7.1).
./scripts/submit_ablation_variant.sh \
    P1 0 0x1004 0 0 4 0xFFFFFF 0 0 0 0

# P2: L1 neighbor cuts only (HLS-only).
./scripts/submit_ablation_variant.sh \
    P2 0 0x1004 0 0 4 0 0xFFFFFF 0 0 0

# P3: all L1 cuts, no L2 cuts (routed).
./scripts/submit_ablation_variant.sh \
    P3 0 0x1004 0 0 4 0xFFFFFF 0xFFFFFF 0 0 1

# P4: all L2 cuts only (HLS-only).
./scripts/submit_ablation_variant.sh \
    P4 0 0x1004 0 0 4 0 0 0x7F 0x7F 0
