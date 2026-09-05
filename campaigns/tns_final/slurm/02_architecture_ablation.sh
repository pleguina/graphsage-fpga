#!/usr/bin/env bash
# Submits the one missing architecture-ablation entry (A3: channelized +
# accumulator cuts, all-fabric multiplier policy, common Default/Default
# physical flow). A0/A1/A2/A4/A5 already exist and are reused via symlinks
# in campaigns/tns_final/results/ablation/.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

./scripts/submit_ablation_variant.sh \
    A3 \
    0 0 0 0 \
    4 \
    0xFFFFFF 0xFFFFFF 0x7F 0x7F \
    1
