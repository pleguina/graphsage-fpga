set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set run_dir [file join $repo_root build vivado_sweep graphsage_19c_const_extra_net_delay]
set checkpoint [file join $run_dir final.dcp]
set reports_dir [file join $run_dir reports]

if {![file exists $checkpoint]} {
    error "Missing final checkpoint: $checkpoint"
}

open_checkpoint $checkpoint
set data_pins [get_pins -hier -filter {REF_PIN_NAME == D}]
if {[llength $data_pins] == 0} {
    error "No register D pins found"
}

report_timing \
    -to $data_pins \
    -delay_type max \
    -max_paths 100 \
    -path_type full_clock_expanded \
    -file [file join $reports_dir timing_register_data_setup_final.rpt]

report_timing \
    -to $data_pins \
    -delay_type min \
    -max_paths 100 \
    -path_type full_clock_expanded \
    -file [file join $reports_dir timing_register_data_hold_final.rpt]

puts "REGISTER_DATA_SETUP_WNS=[get_property SLACK [lindex [get_timing_paths -to $data_pins -delay_type max -max_paths 1] 0]]"
puts "REGISTER_DATA_HOLD_WNS=[get_property SLACK [lindex [get_timing_paths -to $data_pins -delay_type min -max_paths 1] 0]]"
exit 0