set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set project_dir [file join $repo_root build hls graphsage_int8_po2_19c]
set source_file [file join $script_dir graphsage_layer_int8_po2.cpp]
set header_file [file join $script_dir graphsage_layer_int8_po2_19c.h]
set top_function graphsage_int8_po2
set part_name xcvu13p-fsga2577-1-e
set clock_period 2.77

foreach required_file [list $source_file $header_file] {
    if {![file exists $required_file]} {
        error "Missing HLS input: $required_file"
    }
}

file mkdir [file dirname $project_dir]

set cflags [join [list \
    -I$script_dir \
    -DGRAPHSAGE_19C=1 \
    -DDSE_TOP_II=1 \
    -DM_BITS=24 \
    -DBETA1_SHIFT=17 \
    -DBETA2_SHIFT=12 \
    -DEFF_SCALE1_SHIFT=6 \
    -DEFF_SCALE2_SHIFT=6] " "]

puts "HLS_PROJECT_DIR=$project_dir"
puts "HLS_TOP=$top_function"
puts "HLS_PART=$part_name"
puts "HLS_CLOCK_PERIOD_NS=$clock_period"
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
    error "HLS synthesis completed without expected report: $report_file"
}
if {[llength [glob -nocomplain [file join $rtl_dir *.v]]] == 0} {
    error "HLS synthesis completed without generated Verilog in $rtl_dir"
}

puts "HLS_REPORT=$report_file"
puts "HLS_RTL_DIR=$rtl_dir"
puts "HLS_19C_SYNTHESIS_COMPLETE=1"
close_project
exit 0