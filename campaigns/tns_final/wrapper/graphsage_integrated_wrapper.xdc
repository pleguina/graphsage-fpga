# ============================================================================
# Section 15 integrated-wrapper timing constraints.
#
# Unlike hls/graphsage_int8_po2_ooc.xdc (OOC DSE flow, which budgets an
# artificial 0.554ns input/output delay on the accelerator's own boundary
# ports), this is a full non-OOC top-level implementation: clock input ->
# BUFG -> input registers -> accelerator -> output registers, all internal.
# There is no external I/O timing to assume, since every top-level data port
# is captured/driven by a register clocked by the same on-chip clock - so we
# constrain only the clock itself and let Vivado report true register-to-
# register (and register-to-IOB) timing rather than an assumed budget.
# ============================================================================

create_clock -name clk_in -period 2.77 [get_ports clk_in]

# No set_input_delay / set_output_delay: all top-level ports are registered
# at the wrapper boundary (see generate_wrapper.py), so IOB register timing
# is computed directly by Vivado rather than assumed.
