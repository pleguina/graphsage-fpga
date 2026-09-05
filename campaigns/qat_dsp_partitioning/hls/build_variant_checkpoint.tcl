set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir .. .. ..]]

if {![info exists ::env(VARIANT_NAME)] || $::env(VARIANT_NAME) eq ""} {
    error "Missing required environment variable VARIANT_NAME"
}

set variant $::env(VARIANT_NAME)
set package_root [file join $repo_root transfer cora_graphsage_dynamic_root_hls_updated build cora_graphsage_dynamic_root_hls]
set rtl_dir [file join $package_root build hls cora_po2_qat_${variant}_2024_1 solution1 syn verilog]
set xdc_file [file join $repo_root hls graphsage_int8_po2_ooc.xdc]
set output_dir [file join $repo_root build vivado_sweep qat_dsp_${variant}_build]
set output_checkpoint [file join $repo_root build vivado_sweep qat_dsp_${variant}_post_synth.dcp]
set rtl_files [glob -nocomplain [file join $rtl_dir *.v]]

if {[llength $rtl_files] == 0} { error "No variant HLS RTL found in $rtl_dir" }
if {![file exists $xdc_file]} { error "Missing OOC constraints: $xdc_file" }

file mkdir $output_dir
set vivado_threads [expr {[info exists ::env(SLURM_CPUS_PER_TASK)] ? $::env(SLURM_CPUS_PER_TASK) : 4}]
set_param general.maxThreads $vivado_threads

read_verilog $rtl_files
read_xdc $xdc_file
synth_design -top graphsage_po2_qat_partitioned -part xcvu13p-fsga2577-1-e -mode out_of_context -flatten_hierarchy rebuilt
if {[llength [get_clocks -quiet ap_clk]] != 1} { error "Expected exactly one ap_clk timing clock" }

write_checkpoint -force $output_checkpoint
report_timing_summary -delay_type min_max -max_paths 100 -file [file join $output_dir timing_post_synth.rpt]
report_utilization -hierarchical -hierarchical_depth 3 -file [file join $output_dir utilization_hierarchical_post_synth.rpt]
report_utilization -file [file join $output_dir utilization_post_synth.rpt]
puts "QAT_DSP_VARIANT_CHECKPOINT=$output_checkpoint"
exit 0