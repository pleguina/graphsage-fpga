set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set sweep_dir [file join $repo_root build vivado_sweep]


# =============================================================================
# Required environment variables
# =============================================================================

foreach required_env {RUN_NAME PLACE_DIRECTIVE} {
    if {![info exists ::env($required_env)] || $::env($required_env) eq ""} {
        error "Missing required environment variable $required_env"
    }
}


# =============================================================================
# Configuration
# =============================================================================

set run_name $::env(RUN_NAME)
set place_directive $::env(PLACE_DIRECTIVE)

# CLOCK_PERIOD_NS is optional and defaults to the historical 2.77 ns target,
# so every existing run/variant is unaffected unless a clock sweep opts in.
set clock_period [expr {
    [info exists ::env(CLOCK_PERIOD_NS)]
        ? $::env(CLOCK_PERIOD_NS)
        : 2.77
}]
set xdc_file [file join $script_dir graphsage_int8_po2_ooc.xdc]

set input_checkpoint [expr {
    [info exists ::env(INPUT_CHECKPOINT)]
        ? [file normalize $::env(INPUT_CHECKPOINT)]
        : [file join $sweep_dir baseline_post_synth.dcp]
}]

# Normal Vivado routing is now the default.
# AggressiveExplore is deliberately NOT used by default.
set route_directive [expr {
    [info exists ::env(ROUTE_DIRECTIVE)]
        ? $::env(ROUTE_DIRECTIVE)
        : "Default"
}]

set screen_only [expr {
    [info exists ::env(SCREEN_ONLY)]
        ? $::env(SCREEN_ONLY)
        : 1
}]

set use_tns_cleanup [expr {
    [info exists ::env(USE_TNS_CLEANUP)]
        ? $::env(USE_TNS_CLEANUP)
        : 1
}]

set use_post_phys [expr {
    [info exists ::env(USE_POST_PHYS)]
        ? $::env(USE_POST_PHYS)
        : 1
}]

set post_place_phys_directive [expr {
    [info exists ::env(POST_PLACE_PHYS_DIRECTIVE)]
        ? $::env(POST_PLACE_PHYS_DIRECTIVE)
        : ""
}]

# Opt-in register retiming on post-route phys_opt_design (off by default so
# every existing run/variant is unaffected).
set use_retime [expr {
    [info exists ::env(USE_RETIME)]
        ? $::env(USE_RETIME)
        : 0
}]

set output_dir [file join $sweep_dir $run_name]
set reports_dir [file join $output_dir reports]
set start_time [clock seconds]


# =============================================================================
# Output directories
# =============================================================================

file mkdir $output_dir
file mkdir $reports_dir


# =============================================================================
# Vivado thread configuration
# =============================================================================

set vivado_threads [expr {
    [info exists ::env(SLURM_CPUS_PER_TASK)]
        ? $::env(SLURM_CPUS_PER_TASK)
        : 4
}]

set_param general.maxThreads $vivado_threads


# =============================================================================
# Print configuration clearly into vivado.log
# =============================================================================

puts "============================================================"
puts "RUN_NAME=$run_name"
puts "INPUT_CHECKPOINT=$input_checkpoint"
puts "PLACE_DIRECTIVE=$place_directive"
puts "ROUTE_DIRECTIVE=$route_directive"
puts "SCREEN_ONLY=$screen_only"
puts "USE_TNS_CLEANUP=$use_tns_cleanup"
puts "USE_POST_PHYS=$use_post_phys"
puts "POST_PLACE_PHYS_DIRECTIVE=$post_place_phys_directive"
puts "VIVADO_MAX_THREADS=$vivado_threads"
puts "============================================================"


# =============================================================================
# Helper: return worst timing slack
# =============================================================================

proc timing_slack {delay_type} {

    set paths [
        get_timing_paths \
            -delay_type $delay_type \
            -max_paths 1 \
            -quiet
    ]

    if {[llength $paths] == 0} {
        return "NA"
    }

    return [get_property SLACK [lindex $paths 0]]
}

proc report_internal_timing {reports_dir stage} {
    set registers [all_registers]

    report_timing \
        -from $registers \
        -to $registers \
        -delay_type max \
        -max_paths 100 \
        -path_type full_clock_expanded \
        -file [file join $reports_dir timing_internal_setup_${stage}.rpt]

    report_timing \
        -from $registers \
        -to $registers \
        -delay_type min \
        -max_paths 100 \
        -path_type full_clock_expanded \
        -file [file join $reports_dir timing_internal_hold_${stage}.rpt]
}


# =============================================================================
# Helper: write metadata.txt
# =============================================================================

proc write_metadata {
    path
    status
    run_name
    place_directive
    route_directive
    screen_only
    use_tns_cleanup
    use_post_phys
    post_place_phys_directive
    start_time
    clock_period_ns
} {

    set metadata [open $path w]

    puts $metadata "run_name=$run_name"
    puts $metadata "place_directive=$place_directive"
    puts $metadata "route_directive=$route_directive"
    puts $metadata "screen_only=$screen_only"
    puts $metadata "tns_cleanup=$use_tns_cleanup"
    puts $metadata "postroute_physopt=$use_post_phys"
    puts $metadata "post_place_phys_directive=$post_place_phys_directive"

    puts $metadata "clock_period_ns=$clock_period_ns"

    puts $metadata \
        "post_stage_setup_wns_ns=[timing_slack max]"

    puts $metadata \
        "post_stage_hold_wns_ns=[timing_slack min]"

    puts $metadata \
        "runtime_seconds=[expr {[clock seconds] - $start_time}]"

    puts $metadata "status=$status"

    close $metadata
}


# =============================================================================
# Load post-synthesis checkpoint
# =============================================================================

if {![file exists $input_checkpoint]} {
    error "Missing input checkpoint: $input_checkpoint"
}

open_checkpoint $input_checkpoint

if {[llength [get_clocks -quiet ap_clk]] == 0} {
    puts "LOADING_MISSING_TIMING_CONSTRAINTS=$xdc_file"
    read_xdc $xdc_file
}

if {[llength [get_clocks -quiet ap_clk]] != 1} {
    error "Expected exactly one ap_clk timing clock after loading $input_checkpoint"
}

# Re-target the OOC clock period when CLOCK_PERIOD_NS overrides the default.
# Redefining ap_clk with the same 2.77 ns default is a no-op, so unmodified
# callers get byte-identical constraints.
if {[info exists ::env(CLOCK_PERIOD_NS)]} {
    puts "OVERRIDING_CLOCK_PERIOD_NS=$clock_period"
    create_clock -name ap_clk -period $clock_period [get_ports ap_clk]
}


# =============================================================================
# Basic clock/interface information
# =============================================================================

report_property \
    [get_ports ap_clk] \
    -file [
        file join \
            $reports_dir \
            ap_clk_properties.rpt
    ]


# =============================================================================
# Logic optimization
# =============================================================================

opt_design -directive Explore

if {[info exists ::env(PRE_PLACE_TCL)] && $::env(PRE_PLACE_TCL) ne ""} {
    set pre_place_tcl [file normalize $::env(PRE_PLACE_TCL)]
    if {![file exists $pre_place_tcl]} {
        error "Missing PRE_PLACE_TCL hook: $pre_place_tcl"
    }
    puts "SOURCING_PRE_PLACE_TCL=$pre_place_tcl"
    source $pre_place_tcl
}

write_checkpoint \
    -force \
    [
        file join \
            $output_dir \
            post_opt.dcp
    ]


# =============================================================================
# Placement
#
# PLACE_DIRECTIVE comes from Python.
#
# Examples:
#
#   Default
#   ExtraNetDelay_high
#   AltSpreadLogic_high
#   SSI_BalanceSLLs
#   SSI_BalanceSLRs
#   ...
#
# =============================================================================

puts "============================================================"
puts "STARTING_PLACEMENT=$place_directive"
puts "============================================================"

place_design \
    -directive $place_directive \
    -timing_summary


# =============================================================================
# Save pure post-placement checkpoint
# =============================================================================

write_checkpoint \
    -force \
    [
        file join \
            $output_dir \
            post_place.dcp
    ]


# =============================================================================
# Pure post-placement reports
#
# THESE are the reports used for strategy screening.
# No phys_opt_design has been executed yet.
# =============================================================================

report_timing_summary \
    -delay_type min_max \
    -max_paths 100 \
    -file [
        file join \
            $reports_dir \
            timing_post_place.rpt
    ]

        report_internal_timing $reports_dir post_place


report_design_analysis \
    -congestion \
    -file [
        file join \
            $reports_dir \
            congestion_post_place.rpt
    ]


report_utilization \
    -slr \
    -file [
        file join \
            $reports_dir \
            utilization_slr_post_place.rpt
    ]


report_high_fanout_nets \
    -file [
        file join \
            $reports_dir \
            high_fanout_post_place.rpt
    ]


# =============================================================================
# SCREENING STOPS HERE
#
# This is extremely important.
#
# If SCREEN_ONLY=1:
#
#     NO phys_opt_design
#     NO route_design
#     NO AggressiveExplore
#
# The run ends immediately after placement reports.
# =============================================================================

if {$screen_only} {

    puts "============================================================"
    puts "SCREEN_ONLY=1"
    puts "STOPPING_AFTER_PLACEMENT"
    puts "PLACEMENT_SCREEN_COMPLETE=$run_name"
    puts "============================================================"

    write_metadata \
        [file join $output_dir metadata.txt] \
        "placement_complete" \
        $run_name \
        $place_directive \
        $route_directive \
        $screen_only \
        $use_tns_cleanup \
        $use_post_phys \
        $post_place_phys_directive \
        $start_time \
        $clock_period

    exit 0
}


# =============================================================================
# FULL IMPLEMENTATION BEGINS HERE
#
# Only shortlisted candidates should reach this section.
# =============================================================================


# =============================================================================
# Post-placement physical optimization
#
# IMPORTANT:
#
# OLD:
#
#   phys_opt_design -directive AggressiveExplore
#
# NEW:
#
#   phys_opt_design
#
# This uses Vivado's normal/default phys-opt behaviour.
# =============================================================================

puts "============================================================"
puts "STARTING_POST_PLACE_PHYS_OPT=$post_place_phys_directive"
puts "============================================================"

if {$post_place_phys_directive eq ""} {
    phys_opt_design
} else {
    phys_opt_design -directive $post_place_phys_directive
}


# =============================================================================
# Save post-placement-physopt checkpoint
# =============================================================================

write_checkpoint \
    -force \
    [
        file join \
            $output_dir \
            post_place_physopt.dcp
    ]


# =============================================================================
# Reports after normal/default post-placement physopt
# =============================================================================

report_timing_summary \
    -delay_type min_max \
    -max_paths 100 \
    -file [
        file join \
            $reports_dir \
            timing_post_place_physopt.rpt
    ]


report_design_analysis \
    -congestion \
    -file [
        file join \
            $reports_dir \
            congestion_post_place_physopt.rpt
    ]


report_utilization \
    -slr \
    -file [
        file join \
            $reports_dir \
            utilization_slr_post_place_physopt.rpt
    ]


# =============================================================================
# Routing
#
# route_directive should normally be "Default".
# =============================================================================

puts "============================================================"
puts "STARTING_ROUTING=$route_directive"
puts "TNS_CLEANUP=$use_tns_cleanup"
puts "============================================================"

if {$use_tns_cleanup} {

    route_design \
        -directive $route_directive \
        -tns_cleanup

} else {

    route_design \
        -directive $route_directive
}


# =============================================================================
# Save routed design BEFORE optional post-route physopt
# =============================================================================

write_checkpoint \
    -force \
    [
        file join \
            $output_dir \
            post_route_before_physopt.dcp
    ]


# =============================================================================
# Timing before post-route physopt
# =============================================================================

report_timing_summary \
    -delay_type min_max \
    -max_paths 100 \
    -file [
        file join \
            $reports_dir \
            timing_post_route_before_physopt.rpt
    ]


report_route_status \
    -file [
        file join \
            $reports_dir \
            route_status_before_physopt.rpt
    ]


# =============================================================================
# Optional POST-ROUTE physical optimization
#
# Again, use default phys_opt_design.
#
# OLD:
#
#   phys_opt_design -directive AggressiveExplore
#
# NEW:
#
#   phys_opt_design
#
# =============================================================================

if {$use_post_phys} {

    puts "============================================================"
    puts "STARTING_DEFAULT_POST_ROUTE_PHYS_OPT"
    puts "USE_RETIME=$use_retime"
    puts "============================================================"

    if {$use_retime} {
        phys_opt_design -retime
    } else {
        phys_opt_design
    }
}


# =============================================================================
# Final checkpoint
# =============================================================================

write_checkpoint \
    -force \
    [
        file join \
            $output_dir \
            final.dcp
    ]


# =============================================================================
# Final timing reports
# =============================================================================

report_timing_summary \
    -delay_type min_max \
    -max_paths 100 \
    -report_unconstrained \
    -check_timing_verbose \
    -file [
        file join \
            $reports_dir \
            timing_final.rpt
    ]

        report_internal_timing $reports_dir final


report_timing \
    -delay_type max \
    -max_paths 100 \
    -file [
        file join \
            $reports_dir \
            worst_setup_paths.rpt
    ]


# =============================================================================
# Final routing report
# =============================================================================

report_route_status \
    -file [
        file join \
            $reports_dir \
            route_status.rpt
    ]


# =============================================================================
# Congestion
# =============================================================================

report_design_analysis \
    -congestion \
    -file [
        file join \
            $reports_dir \
            congestion_final.rpt
    ]


# =============================================================================
# Complexity
# =============================================================================

report_design_analysis \
    -complexity \
    -hierarchical_depth 4 \
    -file [
        file join \
            $reports_dir \
            complexity_final.rpt
    ]


# =============================================================================
# Utilization
# =============================================================================

report_utilization \
    -file [
        file join \
            $reports_dir \
            utilization_final.rpt
    ]


report_utilization \
    -hierarchical \
    -file [
        file join \
            $reports_dir \
            utilization_hier_final.rpt
    ]


report_utilization \
    -slr \
    -file [
        file join \
            $reports_dir \
            utilization_slr_final.rpt
    ]


# =============================================================================
# Fanout
# =============================================================================

report_high_fanout_nets \
    -file [
        file join \
            $reports_dir \
            high_fanout_final.rpt
    ]


# =============================================================================
# Methodology
# =============================================================================

report_methodology \
    -file [
        file join \
            $reports_dir \
            methodology_final.rpt
    ]


# =============================================================================
# QoR suggestions
# =============================================================================

report_qor_suggestions \
    -file [
        file join \
            $reports_dir \
            qor_suggestions_final.rpt
    ]


# =============================================================================
# Clock reports
# =============================================================================

report_clocks \
    -file [
        file join \
            $reports_dir \
            clocks_final.rpt
    ]


report_clock_utilization \
    -file [
        file join \
            $reports_dir \
            clock_utilization_final.rpt
    ]


# =============================================================================
# Final DRC
# =============================================================================

report_drc \
    -file [
        file join \
            $reports_dir \
            drc_final.rpt
    ]


# =============================================================================
# Determine whether timing closed
# =============================================================================

set setup_wns [timing_slack max]

set timing_met [
    expr {
        $setup_wns ne "NA"
        && $setup_wns >= 0.0
    }
]


# =============================================================================
# Final metadata
# =============================================================================

write_metadata \
    [file join $output_dir metadata.txt] \
    [expr {
        $timing_met
            ? "timing_met"
            : "timing_failed"
    }] \
    $run_name \
    $place_directive \
    $route_directive \
    $screen_only \
    $use_tns_cleanup \
    $use_post_phys \
    $post_place_phys_directive \
    $start_time \
    $clock_period


# =============================================================================
# Final console output
# =============================================================================

puts "============================================================"
puts "RUN_COMPLETE=$run_name"
puts "SETUP_WNS_NS=$setup_wns"
puts "TIMING_MET=$timing_met"
puts "============================================================"


# Exit 0 when timing closes.
# Exit 2 when implementation finishes correctly but timing fails.
exit [expr {$timing_met ? 0 : 2}]