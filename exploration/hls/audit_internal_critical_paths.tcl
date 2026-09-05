if {$argc != 2} {
    error "Usage: vivado -mode batch -source audit_internal_critical_paths.tcl -tclargs <checkpoint> <output.csv>"
}

set checkpoint [lindex $argv 0]
set output_csv [lindex $argv 1]

open_checkpoint $checkpoint
set paths [get_timing_paths -from [all_registers] -to [all_registers] \
    -delay_type max -max_paths 100]

file mkdir [file dirname $output_csv]
set output [open $output_csv w]
puts $output "rank,slack_ns,start_cell,start_ref,start_slr,end_cell,end_ref,end_slr,crosses_slr"

set rank 0
foreach path $paths {
    incr rank
    set start_pin [get_property STARTPOINT_PIN $path]
    set end_pin [get_property ENDPOINT_PIN $path]
    set start_cell [get_cells -quiet -of_objects $start_pin]
    set end_cell [get_cells -quiet -of_objects $end_pin]
    set start_slr [get_slrs -quiet -of_objects $start_cell]
    set end_slr [get_slrs -quiet -of_objects $end_cell]
    set start_ref [get_property -quiet REF_NAME $start_cell]
    set end_ref [get_property -quiet REF_NAME $end_cell]
    set crosses_slr [expr {$start_slr ne "" && $end_slr ne "" && $start_slr ne $end_slr}]
    puts $output [join [list \
        $rank \
        [get_property SLACK $path] \
        $start_cell \
        $start_ref \
        $start_slr \
        $end_cell \
        $end_ref \
        $end_slr \
        $crosses_slr] ","]
}

close $output
puts "CRITICAL_PATH_AUDIT=$output_csv"
puts "CRITICAL_PATH_COUNT=$rank"
exit 0