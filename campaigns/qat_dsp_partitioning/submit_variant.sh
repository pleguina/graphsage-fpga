#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 5 || $# -gt 6 ]]; then
    echo "Usage: $0 <variant> <l1-root-mask> <l1-neighbor-mask> <l2-root-mask> <l2-neighbor-mask> [aggregation-mode]" >&2
    exit 64
fi

VARIANT_NAME="$1"
L1_ROOT_MASK="$2"
L1_NEIGHBOR_MASK="$3"
L2_ROOT_MASK="$4"
L2_NEIGHBOR_MASK="$5"
AGGREGATION_MODE="${6:-0}"

if [[ ! "$VARIANT_NAME" =~ ^[A-Za-z0-9_-]+$ ]]; then
    echo "Invalid variant name: $VARIANT_NAME" >&2
    exit 64
fi

EXPORTS="ALL,VARIANT_NAME=$VARIANT_NAME,L1_ROOT_MASK=$L1_ROOT_MASK,L1_NEIGHBOR_MASK=$L1_NEIGHBOR_MASK,L2_ROOT_MASK=$L2_ROOT_MASK,L2_NEIGHBOR_MASK=$L2_NEIGHBOR_MASK,AGGREGATION_MODE=$AGGREGATION_MODE"
CAMPAIGN_DIR="campaigns/qat_dsp_partitioning"
HLS_JOB="$(sbatch --parsable --export="$EXPORTS" "$CAMPAIGN_DIR/slurm/hls_variant.sbatch")"
VIVADO_JOB="$(sbatch --parsable --dependency="afterok:$HLS_JOB" --export="$EXPORTS" "$CAMPAIGN_DIR/slurm/vivado_variant.sbatch")"
AUDIT_JOB="$(sbatch --parsable --dependency="afterany:$VIVADO_JOB" --export="ALL,VARIANT_NAME=$VARIANT_NAME" "$CAMPAIGN_DIR/slurm/audit_variant.sbatch")"

echo "VARIANT=$VARIANT_NAME"
echo "HLS_JOB=$HLS_JOB"
echo "VIVADO_JOB=$VIVADO_JOB"
echo "AUDIT_JOB=$AUDIT_JOB"