if {$argc != 2} {
    error "Usage: vivado -mode batch -source audit_structural_timing.tcl -tclargs <checkpoint> <output.csv>"
}

proc path_property {path property} {
    set value [get_property -quiet $property $path]
    return [expr {$value eq "" ? "NA" : $value}]
}

proc cell_property {cell property} {
    set value [get_property -quiet $property $cell]
    return [expr {$value eq "" ? "NA" : $value}]
}

proc csv_clean {value} {
    return [string map [list "," ";" "\n" " " "\r" " "] $value]
}

set checkpoint [lindex $argv 0]
set output_csv [lindex $argv 1]
open_checkpoint $checkpoint

set paths [get_timing_paths \
    -from [all_registers] \
    -to [all_registers] \
    -delay_type max \
    -max_paths 1000 \
    -unique_pins \
    -nworst 1]

file mkdir [file dirname $output_csv]
set output [open $output_csv w]
puts $output "rank,slack_ns,datapath_delay_ns,logic_delay_ns,route_delay_ns,logic_levels,skew_ns,start_cell,start_ref,start_hierarchy,start_slr,start_loc,end_cell,end_ref,end_hierarchy,end_slr,end_loc,max_fanout,average_fanout,primitive_chain"

set rank 0
foreach path $paths {
    incr rank
    set start_pin [get_property STARTPOINT_PIN $path]
    set end_pin [get_property ENDPOINT_PIN $path]
    set start_cell [get_cells -quiet -of_objects $start_pin]
    set end_cell [get_cells -quiet -of_objects $end_pin]
    set path_cells [get_cells -quiet -of_objects [get_pins -quiet -of_objects $path]]
    set path_nets [get_nets -quiet -of_objects [get_pins -quiet -of_objects $path]]

    set primitive_chain {}
    foreach cell $path_cells {
        set ref_name [cell_property $cell REF_NAME]
        if {$ref_name ni $primitive_chain} {
            lappend primitive_chain $ref_name
        }
    }

    set fanout_sum 0.0
    set fanout_count 0
    set max_fanout 0
    foreach net $path_nets {
        set fanout [get_property -quiet FLAT_PIN_COUNT $net]
        if {$fanout eq ""} {
            set fanout [llength [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == IN}]]
        } else {
            set fanout [expr {max(0, $fanout - 1)}]
        }
        set fanout_sum [expr {$fanout_sum + $fanout}]
        incr fanout_count
        if {$fanout > $max_fanout} { set max_fanout $fanout }
    }
    set average_fanout [expr {$fanout_count > 0 ? $fanout_sum / $fanout_count : 0.0}]

    set fields [list \
        $rank \
        [path_property $path SLACK] \
        [path_property $path DATAPATH_DELAY] \
        [path_property $path DATAPATH_LOGIC_DELAY] \
        [path_property $path DATAPATH_NET_DELAY] \
        [path_property $path LOGIC_LEVELS] \
        [path_property $path SKEW] \
        $start_cell \
        [cell_property $start_cell REF_NAME] \
        [cell_property $start_cell PARENT] \
        [expr {[get_slrs -quiet -of_objects $start_cell] eq "" ? "NA" : [get_slrs -quiet -of_objects $start_cell]}] \
        [cell_property $start_cell LOC] \
        $end_cell \
        [cell_property $end_cell REF_NAME] \
        [cell_property $end_cell PARENT] \
        [expr {[get_slrs -quiet -of_objects $end_cell] eq "" ? "NA" : [get_slrs -quiet -of_objects $end_cell]}] \
        [cell_property $end_cell LOC] \
        $max_fanout \
        $average_fanout \
        [join $primitive_chain ">"]]
    puts $output [join [lmap field $fields {csv_clean $field}] ","]
}

close $output
puts "STRUCTURAL_TIMING_AUDIT=$output_csv"
puts "STRUCTURAL_TIMING_AUDIT_COUNT=$rank"
exit 0