#!/usr/bin/env bash
# Submit one (layer, branch, channel) HLS+Vivado+audit variant for the TNS
# campaign, reusing the qat_dsp_partitioning Slurm scripts (same HLS project
# family, same physical flow) so results stay directly comparable to
# V1/V2/V3/V4/V2A1/V2A1_allcut. Unlike submit_variant.sh (which only forwards
# the four DSP masks + aggregation mode), this wrapper also forwards the
# accumulator pipeline masks and optional multiplier latencies needed for the
# architecture-ablation (A3) and pipeline-sweep (P1-P4) campaigns.
#
# Usage:
#   submit_ablation_variant.sh <VARIANT_NAME> \
#       <L1_ROOT_MASK> <L1_NEIGHBOR_MASK> <L2_ROOT_MASK> <L2_NEIGHBOR_MASK> \
#       <AGGREGATION_MODE> \
#       <L1_ROOT_ACC_PIPELINE_MASK> <L1_NEIGHBOR_ACC_PIPELINE_MASK> \
#       <L2_ROOT_ACC_PIPELINE_MASK> <L2_NEIGHBOR_ACC_PIPELINE_MASK> \
#       [route=1|0]
#
# route=0 submits HLS synthesis only (for HLS-only pipeline-sweep entries).
# route=1 (default) chains HLS -> Vivado route -> channel-criticality audit.
set -euo pipefail

if [[ $# -lt 10 || $# -gt 11 ]]; then
    echo "Usage: $0 <variant> <l1-root-mask> <l1-neighbor-mask> <l2-root-mask> <l2-neighbor-mask> <agg-mode> <l1-root-acc-pipeline-mask> <l1-neighbor-acc-pipeline-mask> <l2-root-acc-pipeline-mask> <l2-neighbor-acc-pipeline-mask> [route=1|0]" >&2
    exit 64
fi

VARIANT_NAME="$1"
L1_ROOT_MASK="$2"
L1_NEIGHBOR_MASK="$3"
L2_ROOT_MASK="$4"
L2_NEIGHBOR_MASK="$5"
AGGREGATION_MODE="$6"
L1_ROOT_ACC_PIPELINE_MASK="$7"
L1_NEIGHBOR_ACC_PIPELINE_MASK="$8"
L2_ROOT_ACC_PIPELINE_MASK="$9"
L2_NEIGHBOR_ACC_PIPELINE_MASK="${10}"
ROUTE="${11:-1}"

if [[ ! "$VARIANT_NAME" =~ ^[A-Za-z0-9_-]+$ ]]; then
    echo "Invalid variant name: $VARIANT_NAME" >&2
    exit 64
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
QAT_SLURM="$REPO_ROOT/campaigns/qat_dsp_partitioning/slurm"

EXPORTS="ALL,VARIANT_NAME=$VARIANT_NAME,L1_ROOT_MASK=$L1_ROOT_MASK,L1_NEIGHBOR_MASK=$L1_NEIGHBOR_MASK,L2_ROOT_MASK=$L2_ROOT_MASK,L2_NEIGHBOR_MASK=$L2_NEIGHBOR_MASK,AGGREGATION_MODE=$AGGREGATION_MODE,L1_ROOT_ACC_PIPELINE_MASK=$L1_ROOT_ACC_PIPELINE_MASK,L1_NEIGHBOR_ACC_PIPELINE_MASK=$L1_NEIGHBOR_ACC_PIPELINE_MASK,L2_ROOT_ACC_PIPELINE_MASK=$L2_ROOT_ACC_PIPELINE_MASK,L2_NEIGHBOR_ACC_PIPELINE_MASK=$L2_NEIGHBOR_ACC_PIPELINE_MASK"

cd "$REPO_ROOT"
HLS_JOB="$(sbatch --parsable --export="$EXPORTS" "$QAT_SLURM/hls_variant.sbatch")"
echo "VARIANT=$VARIANT_NAME HLS_JOB=$HLS_JOB"

if [[ "$ROUTE" == "1" ]]; then
    VIVADO_JOB="$(sbatch --parsable --dependency="afterok:$HLS_JOB" --export="$EXPORTS" "$QAT_SLURM/vivado_variant.sbatch")"
    AUDIT_JOB="$(sbatch --parsable --dependency="afterany:$VIVADO_JOB" --export="ALL,VARIANT_NAME=$VARIANT_NAME" "$QAT_SLURM/audit_variant.sbatch")"
    echo "VARIANT=$VARIANT_NAME VIVADO_JOB=$VIVADO_JOB AUDIT_JOB=$AUDIT_JOB"
fi
