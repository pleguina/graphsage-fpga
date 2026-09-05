# Plan Section 15: minimal integrated wrapper (clock -> BUFG -> input regs ->
# accelerator -> output regs). Built out-of-context (like every other run in
# this campaign): the ~1500-bit-wide interface (128x8 input + 8x8 edge_masks
# + 51x8 output) has no realistic single-package pinout, so a real top-level
# (non-OOC) implementation fails at IO placement ("IO Clock Placer failed",
# unplaced edge_masks IBUFs) trying to bind every bit to a physical pin.
# OOC still place&routes the whole wrapper netlist as one unit, so it reports
# genuine registered-boundary timing (not an assumed I/O delay budget) without
# requiring a real pinout.
#
# Strategy history: originally reused SSI_SpreadLogic_high+retime (the A5
# accelerator's R1 strategy from the R0-R3 physical-robustness sweep). With
# the wrapper's extra registered boundary added, that strategy still failed
# (job 1369176, 2026-08-29: SETUP_WNS=-0.02ns even after fixing the missing
# post-placement phys_opt_design pass). Switched to AltSpreadLogic_high+retime
# (R2 in the same sweep) for job 1369177 as an empirical retry with a
# different placement heuristic -- NOT because its standalone WNS
# (+0.035ns vs R1's +0.007ns) predicts it will do better here. Vivado's
# timing-driven P&R is a threshold-satisfying optimizer: once a path's
# slack crosses zero it stops getting priority, so a "met" run's specific
# positive WNS reflects where the tool stopped, not true margin -- R1 and
# R2 were both simply timing_met in the R0-R3 sweep, and that WNS gap is
# not evidence either one would survive the wrapper's extra delay better.
# Judge this retry only by whether it passes or fails, not by the WNS it
# lands on if it passes.
set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir .. .. ..]]

set accel_rtl_dir [file join $repo_root transfer cora_graphsage_dynamic_root_hls_updated build cora_graphsage_dynamic_root_hls build hls cora_po2_qat_V2A1_allcut_2024_1 solution1 syn verilog]
set wrapper_v [file join $script_dir graphsage_integrated_wrapper.v]
set xdc_file [file join $script_dir graphsage_integrated_wrapper.xdc]
set output_dir [file join $repo_root build vivado_sweep integrated_wrapper]
set reports_dir [file join $output_dir reports]

file mkdir $output_dir
file mkdir $reports_dir

set vivado_threads [expr {[info exists ::env(SLURM_CPUS_PER_TASK)] ? $::env(SLURM_CPUS_PER_TASK) : 4}]
set_param general.maxThreads $vivado_threads

set accel_files [glob -nocomplain [file join $accel_rtl_dir *.v]]
if {[llength $accel_files] == 0} {
    error "No accelerator RTL found in $accel_rtl_dir - run the V2A1_allcut HLS csynth job first"
}
if {![file exists $wrapper_v]} {
    error "Missing generated wrapper RTL: $wrapper_v - run generate_wrapper.py first"
}

read_verilog $accel_files
read_verilog $wrapper_v
read_xdc $xdc_file

synth_design -top graphsage_integrated_wrapper -part xcvu13p-fsga2577-1-e -mode out_of_context
if {[llength [get_clocks -quiet clk_in]] != 1} { error "Expected exactly one clk_in timing clock after synthesis" }
write_checkpoint -force [file join $output_dir post_synth.dcp]
report_utilization -file [file join $reports_dir utilization_post_synth.rpt]

opt_design -directive Explore
place_design -directive AltSpreadLogic_high
report_utilization -file [file join $reports_dir utilization_post_place.rpt]
write_checkpoint -force [file join $output_dir post_place.dcp]

# Post-placement phys_opt_design (default directive, matching
# hls/run_vivado_int8_po2_strategy.tcl POST_PLACE_PHYS_DIRECTIVE="") --
# the earlier version of this script skipped straight from placement to
# routing and omitted this pass, which is why it missed timing by 8ps
# (WNS=-0.008ns) while the OOC accelerator alone, built with the full
# strategy including this step, closed at +0.007ns.
phys_opt_design
write_checkpoint -force [file join $output_dir post_place_physopt.dcp]

route_design -directive Default -tns_cleanup
phys_opt_design -retime
write_checkpoint -force [file join $output_dir final.dcp]

report_timing_summary -delay_type min_max -max_paths 100 -file [file join $reports_dir timing_final.rpt]
report_utilization -file [file join $reports_dir utilization_final.rpt]
report_route_status -file [file join $reports_dir route_status.rpt]
report_drc -file [file join $reports_dir drc_final.rpt]
report_timing -delay_type max -max_paths 100 -file [file join $reports_dir worst_setup_paths.rpt]

set setup_paths [get_timing_paths -delay_type max -max_paths 1 -quiet]
set hold_paths [get_timing_paths -delay_type min -max_paths 1 -quiet]
set setup_wns [expr {[llength $setup_paths] ? [get_property SLACK [lindex $setup_paths 0]] : "NA"}]
set hold_wns [expr {[llength $hold_paths] ? [get_property SLACK [lindex $hold_paths 0]] : "NA"}]
set metadata [open [file join $output_dir metadata.txt] w]
puts $metadata "run_name=integrated_wrapper"
puts $metadata "top=graphsage_integrated_wrapper"
puts $metadata "clock_period_ns=2.77"
puts $metadata "place_directive=AltSpreadLogic_high"
puts $metadata "route_directive=Default"
puts $metadata "setup_wns_ns=$setup_wns"
puts $metadata "hold_wns_ns=$hold_wns"
close $metadata

puts "INTEGRATED_WRAPPER_SETUP_WNS=$setup_wns"
puts "INTEGRATED_WRAPPER_HOLD_WNS=$hold_wns"
puts "INTEGRATED_WRAPPER_COMPLETE=1"
exit 0
