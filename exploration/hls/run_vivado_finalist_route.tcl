foreach required_env {FINALIST_NAME SOURCE_RUN} {
    if {![info exists ::env($required_env)] || $::env($required_env) eq ""} {
        error "Missing required environment variable $required_env"
    }
}

set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set sweep_dir [file join $repo_root build vivado_sweep]
set finalist_name $::env(FINALIST_NAME)
set source_run $::env(SOURCE_RUN)
set source_checkpoint [file join $sweep_dir $source_run post_place.dcp]
set output_dir [file join $sweep_dir route_$finalist_name]
set reports_dir [file join $output_dir reports]
set start_time [clock seconds]

if {![file exists $source_checkpoint]} {
    error "Missing screened post-place checkpoint: $source_checkpoint"
}

file mkdir $output_dir
file mkdir $reports_dir

set vivado_threads [expr {
    [info exists ::env(SLURM_CPUS_PER_TASK)]
        ? $::env(SLURM_CPUS_PER_TASK)
        : 8
}]
set_param general.maxThreads $vivado_threads

proc internal_wns {delay_type} {
    set paths [get_timing_paths \
        -from [all_registers] \
        -to [all_registers] \
        -delay_type $delay_type \
        -max_paths 1 \
        -quiet]
    if {[llength $paths] == 0} {
        return "NA"
    }
    return [get_property SLACK [lindex $paths 0]]
}

proc safe_property {object property_name} {
    if {$object eq "" || [llength $object] == 0} {
        return "NA"
    }
    if {[lsearch -exact [list_property $object] $property_name] < 0} {
        return "NA"
    }
    set value [get_property $property_name $object]
    if {$value eq ""} {
        return "NA"
    }
    return $value
}

proc object_slr {object} {
    if {$object eq "" || [llength $object] == 0} {
        return "NA"
    }
    set cell [get_cells -quiet -of_objects $object]
    if {[llength $cell] == 0} {
        set cell $object
    }
    set slr [get_slrs -quiet -of_objects $cell]
    if {[llength $slr] == 0} {
        return "NA"
    }
    return [get_property NAME [lindex $slr 0]]
}

proc path_cell_details {path} {
    set refs {}
    set names {}
    set max_fanout 0
    set dsp_involved 0
    set points {}
    if {[lsearch -exact [list_property $path] PATH] >= 0} {
        set points [get_property PATH $path]
    }
    foreach point $points {
        set pin [safe_property $point PIN]
        if {$pin eq "NA"} {
            continue
        }
        set cell [get_cells -quiet -of_objects $pin]
        if {[llength $cell] > 0} {
            set cell [lindex $cell 0]
            set cell_name [get_property NAME $cell]
            set ref_name [safe_property $cell REF_NAME]
            lappend names $cell_name
            lappend refs $ref_name
            if {[string match "DSP*" $ref_name]} {
                set dsp_involved 1
            }
        }
        foreach net [get_nets -quiet -of_objects $pin] {
            set fanout [llength [get_pins -quiet -leaf -of_objects $net]]
            if {$fanout > $max_fanout} {
                set max_fanout $fanout
            }
        }
    }
    return [list \
        [join [lsort -unique $refs] ","] \
        [join [lsort -unique $names] ","] \
        $max_fanout \
        $dsp_involved]
}

proc write_top_internal_diagnostics {reports_dir stage} {
    set paths [get_timing_paths \
        -from [all_registers] \
        -to [all_registers] \
        -delay_type max \
        -max_paths 20 \
        -quiet]

    report_timing \
        -from [all_registers] \
        -to [all_registers] \
        -delay_type max \
        -max_paths 20 \
        -path_type full_clock_expanded \
        -file [file join $reports_dir internal_top20_${stage}.rpt]

    set output [open [file join $reports_dir internal_top20_${stage}.tsv] w]
    puts $output [join [list \
        rank slack_ns startpoint endpoint source_slr destination_slr \
        logic_levels total_delay_ns cell_delay_ns net_delay_ns clock_skew_ns \
        max_fanout dsp_involved crosses_slr cell_types hls_cell_names] "\t"]

    set rank 0
    foreach path $paths {
        incr rank
        set startpoint [safe_property $path STARTPOINT_PIN]
        set endpoint [safe_property $path ENDPOINT_PIN]
        set source_slr [object_slr $startpoint]
        set destination_slr [object_slr $endpoint]
        set crosses_slr [expr {
            $source_slr ne "NA" &&
            $destination_slr ne "NA" &&
            $source_slr ne $destination_slr
        }]
        lassign [path_cell_details $path] cell_types cell_names max_fanout dsp_involved
        puts $output [join [list \
            $rank \
            [safe_property $path SLACK] \
            $startpoint \
            $endpoint \
            $source_slr \
            $destination_slr \
            [safe_property $path LOGIC_LEVELS] \
            [safe_property $path DATAPATH_DELAY] \
            [safe_property $path LOGIC_DELAY] \
            [safe_property $path NET_DELAY] \
            [safe_property $path SKEW] \
            $max_fanout \
            $dsp_involved \
            $crosses_slr \
            $cell_types \
            $cell_names] "\t"]
    }
    close $output
}

proc report_internal_stage {reports_dir stage include_diagnostics summary_file} {
    report_timing \
        -from [all_registers] \
        -to [all_registers] \
        -delay_type max \
        -max_paths 100 \
        -path_type full_clock_expanded \
        -file [file join $reports_dir timing_internal_setup_${stage}.rpt]
    report_timing \
        -from [all_registers] \
        -to [all_registers] \
        -delay_type min \
        -max_paths 100 \
        -path_type full_clock_expanded \
        -file [file join $reports_dir timing_internal_hold_${stage}.rpt]
    set setup_wns [internal_wns max]
    set hold_wns [internal_wns min]
    puts $summary_file "${stage}_internal_setup_wns_ns=$setup_wns"
    puts $summary_file "${stage}_internal_hold_wns_ns=$hold_wns"
    puts "${stage}_INTERNAL_SETUP_WNS_NS=$setup_wns"
    puts "${stage}_INTERNAL_HOLD_WNS_NS=$hold_wns"
    if {$include_diagnostics} {
        write_top_internal_diagnostics $reports_dir $stage
    }
}

puts "FINALIST_NAME=$finalist_name"
puts "SOURCE_CHECKPOINT=$source_checkpoint"
puts "ROUTE_DIRECTIVE=Default"
puts "VIVADO_MAX_THREADS=$vivado_threads"

open_checkpoint $source_checkpoint

set include_diagnostics [expr {$finalist_name eq "ssi_spread_high"}]
set summary [open [file join $reports_dir internal_timing_stages.txt] w]

report_internal_stage $reports_dir post_place $include_diagnostics $summary

phys_opt_design
write_checkpoint -force [file join $output_dir post_place_physopt.dcp]
report_internal_stage $reports_dir post_place_physopt $include_diagnostics $summary

route_design -directive Default
write_checkpoint -force [file join $output_dir post_route.dcp]
report_internal_stage $reports_dir post_route $include_diagnostics $summary
report_route_status -file [file join $reports_dir route_status_post_route.rpt]

phys_opt_design
write_checkpoint -force [file join $output_dir final.dcp]
report_internal_stage $reports_dir post_route_physopt $include_diagnostics $summary

report_timing_summary \
    -delay_type min_max \
    -max_paths 100 \
    -report_unconstrained \
    -check_timing_verbose \
    -file [file join $reports_dir timing_final.rpt]
report_route_status -file [file join $reports_dir route_status.rpt]
report_utilization -file [file join $reports_dir utilization_final.rpt]
report_utilization -slr -file [file join $reports_dir utilization_slr_final.rpt]
report_design_analysis -congestion -file [file join $reports_dir congestion_final.rpt]

close $summary

set metadata [open [file join $output_dir metadata.txt] w]
puts $metadata "run_name=route_$finalist_name"
puts $metadata "source_run=$source_run"
puts $metadata "route_directive=Default"
puts $metadata "postroute_physopt=1"
puts $metadata "clock_period_ns=2.77"
puts $metadata "runtime_seconds=[expr {[clock seconds] - $start_time}]"
puts $metadata "status=implementation_complete"
close $metadata

puts "FINALIST_IMPLEMENTATION_COMPLETE=$finalist_name"
close_design
exit 0