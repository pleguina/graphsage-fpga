# ============================================================================
# GraphSAGE OOC timing constraints
# ============================================================================

# Primary algorithm clock
create_clock \
    -name ap_clk \
    -period 2.77 \
    [get_ports ap_clk]


# ============================================================================
# OOC clock source modelling
# ============================================================================
#
# KEEP THIS ONLY IF BUFGCE_X0Y192 represents the clock source expected
# in the final integrated design.
#
# set_property HD.CLK_SRC BUFGCE_X0Y192 [get_ports ap_clk]


# ============================================================================
# Reset
# ============================================================================
#
# Vitis HLS normally generates a synchronous reset unless reset_async
# has explicitly been configured.
#
# Therefore DO NOT false-path ap_rst by default.
#
# set_false_path -from [get_ports ap_rst]


# ============================================================================
# OOC interface timing budget
# ============================================================================

set data_inputs [get_ports -filter {
    DIRECTION == IN &&
    NAME != ap_clk &&
    NAME != ap_rst
}]

set_input_delay \
    -clock ap_clk \
    0.554 \
    $data_inputs

set_output_delay \
    -clock ap_clk \
    0.554 \
    [all_outputs]