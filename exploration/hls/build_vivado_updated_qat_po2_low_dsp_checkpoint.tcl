set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set package_root [file join $repo_root transfer cora_graphsage_dynamic_root_hls_updated build cora_graphsage_dynamic_root_hls]
set rtl_dir [file join $package_root build hls cora_po2_qat_root_dynamic_const_weights_2024_1 solution1 syn verilog]
set xdc_file [file join $script_dir graphsage_int8_po2_ooc.xdc]
set output_dir [file join $repo_root build vivado_sweep updated_qat_po2_low_dsp_build]
set output_checkpoint [file join $repo_root build vivado_sweep updated_qat_po2_low_dsp_post_synth.dcp]

set top_function graphsage_po2_qat_root_dynamic_const_weights
set part_name xcvu13p-fsga2577-1-e
set clock_period 2.77
set rtl_files [glob -nocomplain [file join $rtl_dir *.v]]

if {[llength $rtl_files] == 0} {
    error "No updated QAT-PO2 root HLS RTL found in $rtl_dir"
}
if {![file exists $xdc_file]} {
    error "Missing OOC constraints: $xdc_file"
}

file mkdir $output_dir
set vivado_threads [expr {
    [info exists ::env(SLURM_CPUS_PER_TASK)] ? $::env(SLURM_CPUS_PER_TASK) : 4
}]
set_param general.maxThreads $vivado_threads

puts "UPDATED_QAT_PO2_LOW_DSP_RTL_DIR=$rtl_dir"
puts "UPDATED_QAT_PO2_LOW_DSP_RTL_FILES=[llength $rtl_files]"
puts "UPDATED_QAT_PO2_LOW_DSP_OUTPUT_CHECKPOINT=$output_checkpoint"

read_verilog $rtl_files
read_xdc $xdc_file

synth_design \
    -top $top_function \
    -part $part_name \
    -mode out_of_context \
    -flatten_hierarchy rebuilt

if {[llength [get_clocks -quiet ap_clk]] != 1} {
    error "Expected exactly one ap_clk timing clock after synthesis"
}

write_checkpoint -force $output_checkpoint
report_timing_summary -delay_type min_max -max_paths 100 \
    -file [file join $output_dir timing_post_synth.rpt]
report_utilization -hierarchical -hierarchical_depth 3 \
    -file [file join $output_dir utilization_hierarchical_post_synth.rpt]
report_utilization \
    -file [file join $output_dir utilization_post_synth.rpt]

puts "UPDATED_QAT_PO2_LOW_DSP_CHECKPOINT_COMPLETE=1"
exit 0