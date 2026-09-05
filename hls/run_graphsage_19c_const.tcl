set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]

if {![info exists ::env(CONST_MODE)]} {
    set ::env(CONST_MODE) adj
}
if {![info exists ::env(HLS_ACTION)]} {
    set ::env(HLS_ACTION) csim
}

set const_mode $::env(CONST_MODE)
set action $::env(HLS_ACTION)
if {$const_mode ni {adj params}} {
    error "CONST_MODE must be adj or params"
}
if {$action ni {csim csynth cosim}} {
    error "HLS_ACTION must be csim, csynth, or cosim"
}

set project_dir [file join $repo_root build hls graphsage_int8_po2_19c_const_${const_mode}]
set source_file [file join $script_dir graphsage_layer_int8_po2_19c_const.cpp]
set testbench_file [file join $script_dir testbench_graphsage_19c_const.cpp]
set top_function graphsage_int8_po2
set part_name xcvu13p-fsga2577-1-e
set clock_period 2.77
set mode_define [expr {$const_mode eq "params" ? "-DUSE_CONST_PARAMS=1" : "-DUSE_CONST_ADJ=1"}]
set cflags [join [list \
    -std=c++17 \
    -I$script_dir \
    $mode_define \
    -DDSE_TOP_II=1 \
    -DM_BITS=24 \
    -DK_BITS=12 \
    -DADJ_BITS=16 \
    -DACC_BITS=22 \
    -DBETA1_SHIFT=17 \
    -DBETA2_SHIFT=12 \
    -DEFF_SCALE1_SHIFT=6 \
    -DEFF_SCALE2_SHIFT=6] " "]

puts "HLS_PROJECT_DIR=$project_dir"
puts "HLS_CONST_MODE=$const_mode"
puts "HLS_ACTION=$action"
puts "HLS_PART=$part_name"
puts "HLS_CLOCK_PERIOD_NS=$clock_period"

open_project -reset $project_dir
set_top $top_function
add_files $source_file -cflags $cflags
add_files -tb $testbench_file -cflags $cflags

open_solution -reset solution1 -flow_target vivado
set_part $part_name
create_clock -period $clock_period -name default
set_clock_uncertainty 1.0
config_op mul -impl dsp -latency 3
config_schedule -enable_dsp_full_reg

if {$action eq "csim"} {
    csim_design -clean
} elseif {$action eq "csynth"} {
    csynth_design
} else {
    csynth_design
    cosim_design -rtl verilog -tool xsim
}

puts "HLS_CONST_FLOW_COMPLETE=1"
close_project
exit 0