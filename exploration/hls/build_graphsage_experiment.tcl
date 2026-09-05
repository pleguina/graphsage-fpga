foreach required_env {EXPERIMENT_NAME} {
    if {![info exists ::env($required_env)] || $::env($required_env) eq ""} {
        error "Missing required environment variable $required_env"
    }
}

set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set experiment_name $::env(EXPERIMENT_NAME)
set experiment_root [file join $repo_root build experiments $experiment_name]
set project_dir [file join $experiment_root hls]
set source_file [file join $script_dir graphsage_layer_int8_po2.cpp]
set header_file [file join $script_dir graphsage_layer_int8_po2_locality_hierarchy.h]
set top_function graphsage_int8_po2
set part_name xcvu13p-fsga2577-1-e
set clock_period 2.0

foreach required_file [list $source_file $header_file] {
    if {![file exists $required_file]} {
        error "Missing HLS input: $required_file"
    }
}

set base_cflags [list \
    -I$script_dir \
    -DGRAPHSAGE_INTERNAL_LOCALITY_HIERARCHY=1 \
    -DDSE_ENABLE_INTERNAL_LOCALITY=1 \
    -DDSE_LOCALITY_LIN1_GROUPS=4 \
    -DDSE_LOCALITY_AGG2_GROUPS=4 \
    -DM_BITS=24 \
    -DBETA1_SHIFT=17 \
    -DBETA2_SHIFT=12 \
    -DEFF_SCALE1_SHIFT=6 \
    -DEFF_SCALE2_SHIFT=6]

set extra_cflags [expr {
    [info exists ::env(EXTRA_CFLAGS)] ? $::env(EXTRA_CFLAGS) : ""
}]
set cflags "[join $base_cflags { }] $extra_cflags"

file mkdir $experiment_root
puts "EXPERIMENT_NAME=$experiment_name"
puts "HLS_PROJECT_DIR=$project_dir"
puts "HLS_CFLAGS=$cflags"

open_project -reset $project_dir
set_top $top_function
add_files $source_file -cflags $cflags
add_files $header_file -cflags $cflags

open_solution -reset solution1 -flow_target vivado
set_part $part_name
create_clock -period $clock_period -name default
csynth_design

set report_file [file join $project_dir solution1 syn report csynth.rpt]
set rtl_dir [file join $project_dir solution1 syn verilog]
if {![file exists $report_file]} {
    error "Missing HLS report: $report_file"
}
if {[llength [glob -nocomplain [file join $rtl_dir *.v]]] == 0} {
    error "Missing generated Verilog: $rtl_dir"
}

set manifest [open [file join $experiment_root configuration.txt] w]
puts $manifest "experiment_name=$experiment_name"
puts $manifest "hls_cflags=$cflags"
puts $manifest "hls_clock_period_ns=$clock_period"
close $manifest

puts "HLS_EXPERIMENT_COMPLETE=$experiment_name"
close_project
exit 0