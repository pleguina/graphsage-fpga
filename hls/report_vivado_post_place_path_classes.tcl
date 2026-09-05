foreach required_env {RUN_NAME} {
    if {![info exists ::env($required_env)] || $::env($required_env) eq ""} {
        error "Missing required environment variable $required_env"
    }
}

set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set run_dir [file join $repo_root build vivado_sweep $::env(RUN_NAME)]
set checkpoint [file join $run_dir post_place.dcp]
set reports_dir [file join $run_dir reports]

if {![file exists $checkpoint]} {
    error "Missing post-place checkpoint: $checkpoint"
}

file mkdir $reports_dir
set vivado_threads [expr {[info exists ::env(SLURM_CPUS_PER_TASK)] ? $::env(SLURM_CPUS_PER_TASK) : 8}]
set_param general.maxThreads $vivado_threads

proc path_wns {from_objects to_objects delay_type} {
    if {[llength $from_objects] == 0 || [llength $to_objects] == 0} {
        return "NA"
    }

    set paths [get_timing_paths \
        -from $from_objects \
        -to $to_objects \
        -delay_type $delay_type \
        -max_paths 100 \
        -quiet]

    if {[llength $paths] == 0} {
        return "NA"
    }

    return [get_property SLACK [lindex $paths 0]]
}

proc write_path_report {path from_objects to_objects delay_type} {
    if {[llength $from_objects] == 0 || [llength $to_objects] == 0} {
        set output [open $path w]
        puts $output "No objects found for this path class."
        close $output
        return
    }

    report_timing \
        -from $from_objects \
        -to $to_objects \
        -delay_type $delay_type \
        -max_paths 100 \
        -path_type full_clock_expanded \
        -file $path
}

open_checkpoint $checkpoint

set registers [all_registers]
set inputs [all_inputs]
set outputs [all_outputs]

write_path_report [file join $reports_dir timing_internal_setup.rpt] $registers $registers max
write_path_report [file join $reports_dir timing_internal_hold.rpt] $registers $registers min
file copy -force \
    [file join $reports_dir timing_internal_setup.rpt] \
    [file join $reports_dir timing_reg_to_reg_setup.rpt]
file copy -force \
    [file join $reports_dir timing_internal_hold.rpt] \
    [file join $reports_dir timing_reg_to_reg_hold.rpt]

write_path_report [file join $reports_dir timing_reg_to_output_setup.rpt] $registers $outputs max
write_path_report [file join $reports_dir timing_reg_to_output_hold.rpt] $registers $outputs min
write_path_report [file join $reports_dir timing_input_to_reg_setup.rpt] $inputs $registers max
write_path_report [file join $reports_dir timing_input_to_reg_hold.rpt] $inputs $registers min

set summary [open [file join $reports_dir timing_path_class_wns.txt] w]
foreach {name from_objects to_objects} [list \
    internal $registers $registers \
    reg_to_output $registers $outputs \
    input_to_reg $inputs $registers] {
    set setup_wns [path_wns $from_objects $to_objects max]
    set hold_wns [path_wns $from_objects $to_objects min]
    puts $summary "${name}_setup_wns_ns=$setup_wns"
    puts $summary "${name}_hold_wns_ns=$hold_wns"
    puts "[string toupper $name]_SETUP_WNS_NS=$setup_wns"
    puts "[string toupper $name]_HOLD_WNS_NS=$hold_wns"
}
close $summary

puts "PATH_CLASS_REPORTS_COMPLETE=$::env(RUN_NAME)"
close_design
exit 0