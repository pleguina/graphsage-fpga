set checkpoint [file normalize $::env(ANALYSIS_CHECKPOINT)]
set output_dir [file normalize $::env(ANALYSIS_OUTPUT_DIR)]
file mkdir $output_dir

set vivado_threads [expr {
    [info exists ::env(SLURM_CPUS_PER_TASK)]
        ? $::env(SLURM_CPUS_PER_TASK)
        : 8
}]
set_param general.maxThreads $vivado_threads

proc object_slr {cell} {
    set sites [get_sites -quiet -of_objects $cell]
    if {[llength $sites] == 0} {
        return "UNPLACED"
    }
    set slrs [get_slrs -quiet -of_objects $sites]
    return [expr {[llength $slrs] ? [lindex $slrs 0] : "NO_SLR"}]
}

proc object_pblock {cell} {
    set pblocks [get_pblocks -quiet -of_objects $cell]
    return [expr {[llength $pblocks] ? [join $pblocks ","] : "UNASSIGNED"}]
}

proc hierarchy_members {pblock} {
    set members {}
    foreach root [get_cells -quiet -of_objects $pblock] {
        lappend members $root
        set members [concat $members [get_cells -quiet -hierarchical \
            -filter "NAME =~ $root/*"]]
    }
    return [lsort -unique $members]
}

if {![file exists $checkpoint]} {
    error "Missing analysis checkpoint: $checkpoint"
}

puts "ANALYSIS_CHECKPOINT=$checkpoint"
puts "ANALYSIS_OUTPUT_DIR=$output_dir"
puts "VIVADO_MAX_THREADS=$vivado_threads"
open_checkpoint $checkpoint

report_timing_summary -delay_type min_max -max_paths 200 \
    -file [file join $output_dir timing_summary.rpt]
report_timing -from [all_registers] -to [all_registers] -delay_type max \
    -max_paths 200 -nworst 200 -path_type full_clock_expanded \
    -file [file join $output_dir timing_internal_top200.rpt]
report_utilization -slr -file [file join $output_dir utilization_slr.rpt]
foreach pblock [get_pblocks] {
    report_utilization -pblocks $pblock \
        -file [file join $output_dir utilization_${pblock}.rpt]
}
report_design_analysis -congestion \
    -file [file join $output_dir congestion.rpt]

set pblock_report [open [file join $output_dir pblock_membership.tsv] w]
puts $pblock_report "pblock\tgrid\tis_soft\troots\tleaf_cells\tregisters\tdsps\tluts"
foreach pblock [lsort [get_pblocks]] {
    set roots [get_cells -quiet -of_objects $pblock]
    set members [hierarchy_members $pblock]
    set leaf_cells [filter $members {IS_PRIMITIVE == 1}]
    set registers [filter $leaf_cells {IS_SEQUENTIAL == 1}]
    set dsps [filter $leaf_cells {REF_NAME == DSP48E2}]
    set luts [filter $leaf_cells {REF_NAME =~ LUT*}]
    puts $pblock_report [join [list \
        $pblock \
        [get_property GRID_RANGES $pblock] \
        [get_property IS_SOFT $pblock] \
        [llength $roots] \
        [llength $leaf_cells] \
        [llength $registers] \
        [llength $dsps] \
        [llength $luts]] "\t"]
}
close $pblock_report

set hidden_report [open [file join $output_dir hidden_register_distribution.tsv] w]
puts $hidden_report "slr\tpblock\tregisters"
array set hidden_counts {}
set hidden_registers [get_cells -quiet -hierarchical -regexp {.*hidden_(local|regional)_[0-9]+_reg.*}]
foreach cell $hidden_registers {
    set key "[object_slr $cell]|[object_pblock $cell]"
    if {![info exists hidden_counts($key)]} {
        set hidden_counts($key) 0
    }
    incr hidden_counts($key)
}
foreach key [lsort [array names hidden_counts]] {
    lassign [split $key |] slr pblock
    puts $hidden_report "$slr\t$pblock\t$hidden_counts($key)"
}
close $hidden_report

set path_report [open [file join $output_dir critical_paths.tsv] w]
puts $path_report "rank\tslack_ns\tdatapath_ns\tlogic_levels\tsource\tsource_loc\tsource_slr\tsource_pblock\tdestination\tdestination_loc\tdestination_slr\tdestination_pblock"
array set crossing_counts {}
set paths [get_timing_paths -from [all_registers] -to [all_registers] \
    -delay_type max -max_paths 200 -nworst 200]
set rank 0
foreach path $paths {
    incr rank
    set source_pin [get_property STARTPOINT_PIN $path]
    set destination_pin [get_property ENDPOINT_PIN $path]
    set source [lindex [get_cells -quiet -of_objects $source_pin] 0]
    set destination [lindex [get_cells -quiet -of_objects $destination_pin] 0]
    set source_slr [object_slr $source]
    set destination_slr [object_slr $destination]
    set crossing "$source_slr->$destination_slr"
    if {![info exists crossing_counts($crossing)]} {
        set crossing_counts($crossing) 0
    }
    incr crossing_counts($crossing)
    puts $path_report [join [list \
        $rank \
        [get_property SLACK $path] \
        [get_property DATAPATH_DELAY $path] \
        [get_property LOGIC_LEVELS $path] \
        $source \
        [get_property LOC $source] \
        $source_slr \
        [object_pblock $source] \
        $destination \
        [get_property LOC $destination] \
        $destination_slr \
        [object_pblock $destination]] "\t"]
}
close $path_report

set crossing_report [open [file join $output_dir critical_crossings.tsv] w]
puts $crossing_report "crossing\tpaths_in_top200"
foreach crossing [lsort [array names crossing_counts]] {
    puts $crossing_report "$crossing\t$crossing_counts($crossing)"
}
close $crossing_report

puts "PBLOCKS=[llength [get_pblocks]]"
puts "HIDDEN_REGISTERS=[llength $hidden_registers]"
puts "CRITICAL_PATHS=[llength $paths]"
puts "FLOORPLAN_ANALYSIS_COMPLETE"
close_design
exit 0