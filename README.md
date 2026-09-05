# GraphSAGE FPGA implementation campaign

Sources, build/run scripts, and result data for a two-layer SAGEConv
(GraphSAGE) accelerator implemented in HLS/Vivado, targeting an
`xcvu13p-fsga2577-1-e` device at a 2.77 ns implementation constraint
(360 MHz operating target).

This repository covers the physical-implementation and verification campaign
(architecture ablation, DSP/fabric multiplier mapping, accumulator pipeline
cuts, placement/routing strategy robustness, clock-period robustness,
hidden-width scaling, RTL/C-simulation verification, and the integrated
timing-closure wrapper) plus the model-training material needed to reproduce
the reported accuracy numbers (`training/`). The full training/quantization/
HLS-generation pipeline, developed independently, also has its own repository
at `github.com/INTREPID-hep/graphsage-cora`.

## Layout

```
training/
  src/                   model and quantization source (float, PTQ-INT8, QAT v2,
                         QAT->PO2, plus subgraph extraction and export scripts)
  tests/                 training/eval drivers, including run_po2_qat_study.py,
                         and standalone arithmetic/initialization unit tests
  data/Cora/             local Cora dataset cache; CiteSeer/PubMed/PPI are
                         fetched on demand by PyTorch Geometric
  configs/model_config.yaml
  results/po2_qat_study/            per-seed (42-51) results.json + trained
                                     po2_qat_root.pth for Cora/CiteSeer/PubMed/PPI
                                     -- this is the exact source of the accuracy
                                     numbers reported for the deployed QAT->PO2
                                     model
  results/po2_qat_multiseed_summary.json   paired per-seed statistics across
                                            the three tested quantization flows
campaigns/
  qat_dsp_partitioning/   DSP/fabric mapping and pipeline-cut source campaign
    frozen/               pinned source/config/result snapshot (A0-A5, V1-V4, V2A1*)
    hls/, slurm/, analysis/, logs/   the working tree it was pinned from
  tns_final/              final result-generation campaign
    configs/              JSON descriptors for each sweep (below)
    scripts/              Python analysis/aggregation (build *.csv from raw reports)
    slurm/, slurm_scaling/, slurm_seed_robustness/   job submission scripts
    logs/                 raw stdout/stderr of the jobs behind paper_data/*.csv
    paper_data/           final aggregated CSVs -- the numeric source for every
                           routed result reported for this campaign
    results/              per-run JSON/CSV artifacts and per-seed model checkpoints
    scaling/, scaling_smoke_test/   hidden-width scaling training runs
    wrapper/               integrated timing-closure wrapper (Verilog/XDC/Tcl)
hls/
  run_vivado_int8_po2_strategy.tcl   shared place-and-route driver used by every
                                     campaigns/ run (clock period, strategy,
                                     retiming, and reporting are all controlled
                                     through its environment variables)
  graphsage_int8_po2_ooc.xdc         shared out-of-context timing constraints
exploration/
  hls/, slurm/, scripts/, reports/   earlier, superseded design-space exploration
                                     (19c ladder, locality/locality-hierarchy,
                                     II=2 reuse, dynamic-graph constant weights,
                                     fanout replication, floorplanning). Kept for
                                     provenance; not required to reproduce the
                                     results under campaigns/.
```

## What each sweep is and where its data is

| Sweep | Config | Result CSV | Notes |
|---|---|---|---|
| Architecture ablation (A0-A5) | `campaigns/tns_final/configs/architecture/ablation.json` | `campaigns/tns_final/paper_data/architecture_ablation.csv` | A2 reuses the V2A1 DSP-sweep run; A5 reuses the A4 RTL under the tuned strategy. |
| DSP/fabric mapping (V1-V4, V2A1, Final) | `campaigns/tns_final/configs/dsp_masks/dsp_sweep.json` | `campaigns/tns_final/paper_data/dsp_sweep.csv` | |
| Accumulator pipeline cuts (P0-P5) | `campaigns/tns_final/configs/pipeline_masks/pipeline_sweep.json` | `campaigns/tns_final/paper_data/pipeline_sweep.csv` | P1/P2/P4 are HLS-only (not routed). |
| Placement/routing strategy robustness (R0-R3) | `campaigns/tns_final/configs/physical_strategies/strategies.json` | `campaigns/tns_final/paper_data/physical_robustness.csv` | All four share the same frozen A4 post-synthesis checkpoint; only the Vivado strategy changes. |
| Clock-period robustness | `campaigns/tns_final/configs/clock_sweep/periods.json` | `campaigns/tns_final/paper_data/clock_sweep.csv` | Same frozen RTL and final strategy; only `CLOCK_PERIOD_NS` changes. |
| Hidden-width scaling (H=16/24/32) | `campaigns/tns_final/slurm_scaling/` | `campaigns/tns_final/paper_data/scaling.csv` | Two independent series: common policy (`route_width_variant.sbatch`) and the A5 tuned strategy (`route_width_variant_a5strategy.sbatch`); do not merge them into one curve. |
| Model-seed routing robustness (S0-S2) | `campaigns/tns_final/configs/model_seeds/seeds.json` | `campaigns/tns_final/paper_data/model_seeds.csv` | |
| Critical-path attribution | -- | `campaigns/tns_final/paper_data/critical_path_categories.csv`, `critical_path_semantic_groups_A5.csv` | Built by `campaigns/tns_final/scripts/build_critical_path_categories.py`. |
| ML accuracy (QAT / QAT->PO2 / PO2-constrained QAT) | -- | `campaigns/tns_final/paper_data/ml_accuracy_table.csv` (sourced from `training/results/po2_qat_study/`), `campaigns/tns_final/results/true_qat_po2/` | `training/tests/run_po2_qat_study.py` generates the per-seed results; `campaigns/tns_final/scripts/aggregate_ml_accuracy_table.py` aggregates them; `true_qat_po2_experiment.py` is the separate controlled PO2-constrained-training comparison. |
| Verification (CSim/RTL cosim/streaming) | `campaigns/tns_final/slurm/01_csim_final.sbatch`, `02_cosim800_final_masks.sbatch`, `02_csim_density_coverage.sbatch`, `03_cosim_streaming_no_bubble.sbatch` | corresponding files in `campaigns/tns_final/logs/` | |
| Integrated wrapper | `campaigns/tns_final/wrapper/` | `campaigns/tns_final/logs/vivado_integrated_wrapper_*.out` | Independent build from the standalone core, with its own XDC/strategy. |

Every routed variant's masks/strategy/status is also recorded next to its raw
metadata as `metadata.txt` / `variant_manifest.txt` under
`campaigns/qat_dsp_partitioning/frozen/results/<variant>/`.

## Requirements to rerun

- Vitis HLS and Vivado 2025.2 (the frozen results were produced with build
  6295257 / 6299465 respectively); target device `xcvu13p-fsga2577-1-e`.
- Slurm for the `.sbatch` job scripts (or run the underlying Tcl/Python
  commands directly; each script documents its own invocation at the top).
- `XILINXD_LICENSE_FILE` / `LM_LICENSE_FILE` pointing at your own license
  server, and a compute host with the tools installed -- both are left as
  `<LICENSE_SERVER>` / `<COMPUTE_NODE>` placeholders in the scripts.
- Python 3.9+ with `numpy`/`torch`/`torch_geometric` for the scripts under
  `campaigns/tns_final/scripts/` and `exploration/scripts/`.

`build/`, `transfer/`, and `.Xil/` are intentionally not included (regenerable
tool output, tens of GB). Running the scripts recreates them locally,
including the symlinks under `campaigns/*/results/*` that point into them.

## License

MIT, see `LICENSE`.
