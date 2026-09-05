# ============================================================================
# Hierarchy / physical-exposure audit (plan Section 16).
#
# Enumerates the 62 expected (layer, branch, channel) semantic units inside a
# routed graphsage_po2_qat_partitioned checkpoint and reports per-unit
# LUT/FF/DSP counts plus SLR membership, so the paper can state how many of
# the 62 expected channel units are present as identifiable hierarchical
# cells in the synthesized netlist.
#
# Usage:
#   vivado -mode batch -source hierarchy_audit.tcl -tclargs <checkpoint> <output.csv>
# ============================================================================

if {[llength $argv] != 2} {
    error "Usage: hierarchy_audit.tcl <checkpoint.dcp> <output.csv>"
}
set checkpoint [lindex $argv 0]
set output_csv [lindex $argv 1]

if {![file exists $checkpoint]} {
    error "Missing checkpoint: $checkpoint"
}

open_checkpoint $checkpoint

set patterns {
    l1_root_channel
    l1_neighbor_channel
    l2_root_channel
    l2_neighbor_channel
}

set fh [open $output_csv w]
puts $fh "pattern,hier_cell,lut,ff,dsp,slr,bbox"

# Pass 1: collect every hierarchical cell whose full path contains a pattern
# substring. This over-matches (it also catches arithmetic macros nested
# *inside* each channel, since their full path includes the channel's name),
# so pass 2 keeps only cells with no matched ancestor, i.e. the genuine
# top-level (layer, branch, channel) units.
set matches {}
set all_paths [dict create]
foreach pattern $patterns {
    foreach cell [get_cells -hierarchical -regexp -filter "IS_PRIMITIVE == 0" ".*${pattern}.*"] {
        lappend matches [list $pattern $cell]
        dict set all_paths $cell 1
    }
}

set total_units 0
foreach entry $matches {
    lassign $entry pattern cell

    set is_top_level 1
    set parts [split $cell "/"]
    for {set i 1} {$i < [llength $parts]} {incr i} {
        if {[dict exists $all_paths [join [lrange $parts 0 [expr {$i - 1}]] "/"]]} {
            set is_top_level 0
            break
        }
    }
    if {!$is_top_level} {
        continue
    }

    # Top-level match: leaf counts already aggregate the whole subtree.
    set leaf_cells [get_cells -hierarchical -regexp -filter "IS_PRIMITIVE == 1" "^${cell}/.*"]
    set lut_count 0
    set ff_count 0
    set dsp_count 0
    foreach leaf $leaf_cells {
        set ref [get_property REF_NAME $leaf]
        if {[string match "LUT*" $ref] || [string match "*LUT6*" $ref]} { incr lut_count }
        if {[string match "FD*" $ref]} { incr ff_count }
        if {[string match "DSP*" $ref]} { incr dsp_count }
    }
    set slrs [lsort -unique [get_property -quiet SLR_NAME [get_sites -quiet -of_objects $leaf_cells]]]
    set bbox [get_property -quiet BBOX [get_pblocks -quiet -of_objects $cell]]
    puts $fh "$pattern,$cell,$lut_count,$ff_count,$dsp_count,\"$slrs\",\"$bbox\""
    incr total_units
}
close $fh

puts "============================================================"
puts "HIERARCHY_AUDIT_TOTAL_UNITS=$total_units"
puts "HIERARCHY_AUDIT_EXPECTED_UNITS=62"
puts "============================================================"
exit 0
