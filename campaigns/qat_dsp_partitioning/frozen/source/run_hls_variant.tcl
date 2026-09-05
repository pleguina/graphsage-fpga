set script_dir [file dirname [file normalize [info script]]]
set bundle_root [file normalize [file join $script_dir .. ..]]
set repo_root [file normalize [file join $bundle_root .. .. .. ..]]

if {![info exists ::env(HLS_ACTION)]} { set ::env(HLS_ACTION) csynth }
set action $::env(HLS_ACTION)
if {$action ni {csim csynth cosim}} { error "HLS_ACTION must be csim, csynth, or cosim" }

if {![info exists ::env(VARIANT_NAME)] || $::env(VARIANT_NAME) eq ""} {
    error "Missing required environment variable VARIANT_NAME"
}
set variant $::env(VARIANT_NAME)

proc mask_define {name} {
    return [expr {[info exists ::env($name)] && $::env($name) ne "" ? $::env($name) : "0"}]
}
set l1_root_mask     [mask_define L1_ROOT_MASK]
set l1_neighbor_mask [mask_define L1_NEIGHBOR_MASK]
set l2_root_mask     [mask_define L2_ROOT_MASK]
set l2_neighbor_mask [mask_define L2_NEIGHBOR_MASK]
set aggregation_mode [mask_define AGGREGATION_MODE]
set l1_neighbor_acc_pipeline_mask [mask_define L1_NEIGHBOR_ACC_PIPELINE_MASK]

set project_dir [file join $repo_root build hls cora_po2_qat_${variant}_2024_1]
set source_dir [file join $repo_root build hls cora_graphsage_hls_test_bundle build cora_hls_bundle hls po2_qat_root_dynamic_const_weights_partitioned]
if {[file exists $project_dir]} { file delete -force $project_dir }

open_project -reset $project_dir
set_top graphsage_po2_qat_partitioned
set design_file [file join $source_dir graphsage_po2_qat_partitioned.cpp]
set defines "-DL1_ROOT_DSP_MASK=${l1_root_mask}u -DL1_NEIGHBOR_DSP_MASK=${l1_neighbor_mask}u -DL2_ROOT_DSP_MASK=${l2_root_mask}u -DL2_NEIGHBOR_DSP_MASK=${l2_neighbor_mask}u -DROOT_AGGREGATION_MODE=${aggregation_mode} -DL1_NEIGHBOR_ACC_PIPELINE_MASK=${l1_neighbor_acc_pipeline_mask}u"
add_files $design_file -cflags "-std=c++17 -I$source_dir $defines"
add_files -tb [file join $source_dir testbench_partitioned.cpp] -cflags "-std=c++17 -I$source_dir $defines"

open_solution -reset solution1 -flow_target vivado
set_part xcvu13p-fsga2577-1-e
create_clock -period 2.77 -name default
set_clock_uncertainty 1.0
config_op mul -impl dsp -latency 3
config_schedule -enable_dsp_full_reg
cd $project_dir

puts "VARIANT=$variant"
puts "L1_ROOT_MASK=$l1_root_mask"
puts "L1_NEIGHBOR_MASK=$l1_neighbor_mask"
puts "L2_ROOT_MASK=$l2_root_mask"
puts "L2_NEIGHBOR_MASK=$l2_neighbor_mask"
puts "AGGREGATION_MODE=$aggregation_mode"
puts "L1_NEIGHBOR_ACC_PIPELINE_MASK=$l1_neighbor_acc_pipeline_mask"

if {$action eq "csim"} { csim_design }
if {$action eq "csynth"} { csynth_design }
if {$action eq "cosim"} { cosim_design }
puts "QAT_VARIANT_HLS_COMPLETE=1"
close_project
exit 0
