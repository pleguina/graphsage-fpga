if {![info exists ::env(EXPERIMENT_NAME)] || $::env(EXPERIMENT_NAME) eq ""} {
    error "Missing required environment variable EXPERIMENT_NAME"
}

set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set experiment_name $::env(EXPERIMENT_NAME)
set experiment_root [file join $repo_root build experiments_19c $experiment_name]
set rtl_dir [file join $experiment_root hls solution1 syn verilog]
set xdc_file [file join $script_dir graphsage_int8_po2_ooc.xdc]
set output_dir [file join $experiment_root vivado_build]
set output_checkpoint [file join $experiment_root post_synth.dcp]
set clock_period 2.77

set rtl_files [glob -nocomplain [file join $rtl_dir *.v]]
if {[llength $rtl_files] == 0} {
    error "No HLS RTL found in $rtl_dir"
}

file mkdir $output_dir
set vivado_threads [expr {
    [info exists ::env(SLURM_CPUS_PER_TASK)]
        ? $::env(SLURM_CPUS_PER_TASK)
        : 4
}]
set_param general.maxThreads $vivado_threads

puts "EXPERIMENT_NAME=$experiment_name"
puts "RTL_FILES=[llength $rtl_files]"
puts "OUTPUT_CHECKPOINT=$output_checkpoint"

read_verilog $rtl_files
read_xdc $xdc_file
synth_design \
    -top graphsage_int8_po2 \
    -part xcvu13p-fsga2577-1-e \
    -mode out_of_context \
    -flatten_hierarchy rebuilt \
    -retiming

if {[llength [get_clocks -quiet ap_clk]] != 1} {
    error "Expected exactly one ap_clk timing clock after synthesis"
}

write_checkpoint -force $output_checkpoint
report_timing_summary -delay_type min_max -max_paths 100 \
    -file [file join $output_dir timing_post_synth.rpt]
report_utilization -file [file join $output_dir utilization_post_synth.rpt]

puts "VIVADO_19C_LADDER_CHECKPOINT_COMPLETE=$experiment_name"
exit 0