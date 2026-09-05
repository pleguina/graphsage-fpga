foreach required_env {FORCE_MAX_FANOUT} {
    if {![info exists ::env($required_env)] || $::env($required_env) eq ""} {
        error "Missing required environment variable $required_env"
    }
}

set target_fanout $::env(FORCE_MAX_FANOUT)
if {![string is integer -strict $target_fanout] || $target_fanout < 2} {
    error "FORCE_MAX_FANOUT must be an integer greater than one"
}

set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set sweep_dir [file join $repo_root build vivado_sweep]
set source_checkpoint [file join $sweep_dir screen_ssi_spread_high post_place.dcp]
set run_name fanout_$target_fanout
set output_dir [file join $sweep_dir $run_name]
set reports_dir [file join $output_dir reports]
set start_time [clock seconds]

if {![file exists $source_checkpoint]} {
    error "Missing winning post-place checkpoint: $source_checkpoint"
}

file mkdir $output_dir
file mkdir $reports_dir

set vivado_threads [expr {
    [info exists ::env(SLURM_CPUS_PER_TASK)]
        ? $::env(SLURM_CPUS_PER_TASK)
        : 8
}]
set_param general.maxThreads $vivado_threads

proc internal_wns {} {
    set paths [get_timing_paths \
        -from [all_registers] \
        -to [all_registers] \
        -delay_type max \
        -max_paths 1 \
        -quiet]
    if {[llength $paths] == 0} {
        return "NA"
    }
    return [get_property SLACK [lindex $paths 0]]
}

proc sink_pins {net} {
    return [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == IN}]
}

proc dsp_sink_pins {net} {
    set result {}
    foreach pin [sink_pins $net] {
        set cell [get_cells -quiet -of_objects $pin]
        if {[llength $cell] == 0} {
            continue
        }
        set ref_name [get_property REF_NAME [lindex $cell 0]]
        if {[string match "DSP*" $ref_name]} {
            lappend result $pin
        }
    }
    return $result
}

proc critical_source_nets {} {
    set result {}
    foreach cell [get_cells -quiet -hier -regexp {.*trunc_ln269_.*reg.*}] {
        foreach pin [get_pins -quiet -of_objects $cell -filter {REF_PIN_NAME == Q}] {
            foreach net [get_nets -quiet -of_objects $pin] {
                if {[llength [dsp_sink_pins $net]] > 0} {
                    lappend result $net
                }
            }
        }
    }
    return [lsort -unique $result]
}

proc object_clock_regions {objects} {
    set regions {}
    foreach cell [get_cells -quiet -of_objects $objects] {
        foreach region [get_clock_regions -quiet -of_objects $cell] {
            lappend regions [get_property NAME $region]
        }
    }
    if {[llength $regions] == 0} {
        return "NA"
    }
    return [join [lsort -unique $regions] ","]
}

proc write_net_topology {path nets} {
    set output [open $path w]
    puts $output [join [list \
        net source source_loc source_clock_regions fanout dsp_sinks \
        sink_clock_regions] "\t"]
    foreach net [lsort -dictionary $nets] {
        set driver [lindex [get_pins -quiet -leaf -of_objects $net \
            -filter {DIRECTION == OUT}] 0]
        set driver_cell [get_cells -quiet -of_objects $driver]
        set source_loc "NA"
        if {[llength $driver_cell] > 0} {
            set source_loc [get_property LOC [lindex $driver_cell 0]]
            if {$source_loc eq ""} {
                set source_loc "UNPLACED"
            }
        }
        set sinks [sink_pins $net]
        set dsp_sinks [dsp_sink_pins $net]
        puts $output [join [list \
            $net \
            $driver \
            $source_loc \
            [object_clock_regions $driver] \
            [llength $sinks] \
            [llength $dsp_sinks] \
            [object_clock_regions $dsp_sinks]] "\t"]
    }
    close $output
}

proc report_internal_timing {reports_dir stage summary} {
    set wns [internal_wns]
    puts $summary "${stage}_internal_setup_wns_ns=$wns"
    puts "${stage}_INTERNAL_SETUP_WNS_NS=$wns"
    report_timing \
        -from [all_registers] \
        -to [all_registers] \
        -delay_type max \
        -max_paths 20 \
        -path_type full_clock_expanded \
        -file [file join $reports_dir internal_top20_${stage}.rpt]
}

puts "FORCE_MAX_FANOUT=$target_fanout"
puts "SOURCE_CHECKPOINT=$source_checkpoint"
puts "VIVADO_MAX_THREADS=$vivado_threads"

open_checkpoint $source_checkpoint
set summary [open [file join $reports_dir timing_stages.txt] w]
report_internal_timing $reports_dir post_place $summary

set source_nets [critical_source_nets]
if {[llength $source_nets] == 0} {
    error "No trunc_ln269 register nets with DSP sinks were found"
}
write_net_topology [file join $reports_dir topology_before.tsv] $source_nets

set selected_nets {}
foreach net $source_nets {
    if {[llength [sink_pins $net]] > $target_fanout} {
        lappend selected_nets $net
    }
}
if {[llength $selected_nets] == 0} {
    error "No critical nets exceed FORCE_MAX_FANOUT=$target_fanout"
}

puts "CRITICAL_SOURCE_NETS=[llength $source_nets]"
puts "SELECTED_REPLICATION_NETS=[llength $selected_nets]"
set_property FORCE_MAX_FANOUT $target_fanout $selected_nets
phys_opt_design -force_replication_on_nets $selected_nets

set replicated_nets [get_nets -quiet -hier -regexp {.*trunc_ln269_.*}]
write_net_topology [file join $reports_dir topology_after_replication.tsv] $replicated_nets
write_checkpoint -force [file join $output_dir post_replication.dcp]
report_internal_timing $reports_dir post_replication $summary

route_design -directive Default
write_checkpoint -force [file join $output_dir post_route.dcp]
report_internal_timing $reports_dir post_route $summary
report_route_status -file [file join $reports_dir route_status.rpt]
report_design_analysis -congestion -file [file join $reports_dir congestion.rpt]

phys_opt_design
write_checkpoint -force [file join $output_dir final.dcp]
report_internal_timing $reports_dir post_route_physopt $summary
report_utilization -file [file join $reports_dir utilization.rpt]
report_utilization -slr -file [file join $reports_dir utilization_slr.rpt]
close $summary

set metadata [open [file join $output_dir metadata.txt] w]
puts $metadata "run_name=$run_name"
puts $metadata "source_checkpoint=$source_checkpoint"
puts $metadata "force_max_fanout=$target_fanout"
puts $metadata "selected_replication_nets=[llength $selected_nets]"
puts $metadata "route_directive=Default"
puts $metadata "runtime_seconds=[expr {[clock seconds] - $start_time}]"
puts $metadata "status=implementation_complete"
close $metadata

puts "FANOUT_REPLICATION_COMPLETE=$target_fanout"
close_design
exit 0