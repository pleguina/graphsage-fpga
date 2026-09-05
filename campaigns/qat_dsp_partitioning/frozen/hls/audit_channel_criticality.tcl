if {$argc != 2} {
    error "Usage: vivado -mode batch -source audit_channel_criticality.tcl -tclargs <checkpoint> <output.csv>"
}

set checkpoint [lindex $argv 0]
set output_csv [lindex $argv 1]

open_checkpoint $checkpoint

# Unique-per-endpoint worst paths give a much larger, non-redundant sample
# than a plain -max_paths N query, which repeats the same endpoint.
set paths [get_timing_paths \
    -from [all_registers] \
    -to [all_registers] \
    -delay_type max \
    -max_paths 1000 \
    -unique_pins \
    -nworst 1]

file mkdir [file dirname $output_csv]
set output [open $output_csv w]
puts $output "rank,slack_ns,start_cell,end_cell"

set rank 0
foreach path $paths {
    incr rank
    set start_pin [get_property STARTPOINT_PIN $path]
    set end_pin [get_property ENDPOINT_PIN $path]
    set start_cell [get_cells -quiet -of_objects $start_pin]
    set end_cell [get_cells -quiet -of_objects $end_pin]
    puts $output [join [list \
        $rank \
        [get_property SLACK $path] \
        $start_cell \
        $end_cell] ","]
}

close $output
puts "L2_CHANNEL_AUDIT=$output_csv"
puts "L2_CHANNEL_AUDIT_COUNT=$rank"
exit 0
