# synth.tcl — auto-generated for graphsage_int8_po2. DO NOT EDIT BY HAND.

puts "=========================================="
puts "  C SYNTHESIS - graphsage_int8_po2"
puts "=========================================="
puts ""

# Absolute path to this module's HLS project directory
set project_dir "/home/pelayo/work/simple-gnn/build/hls/graphsage_int8_po2"
# FPGA part name
set part_name "xcvu13p-fsga2577-1-e"

puts "▶ Opening project: $project_dir"
open_project $project_dir

puts "▶ Opening solution: solution1"
open_solution "solution1"

puts "▶ Setting part: $part_name"
set_part $part_name

# User-provided synthesis options (often empty string)
set csynth_opts ""

puts ""
puts "=========================================="
puts "  STARTING C SYNTHESIS"
puts "=========================================="

if { $csynth_opts eq "" } {
    puts "▶ Command: csynth_design (default opts)"
    set status [catch {csynth_design} errMsg]
} else {
    puts "▶ Command: csynth_design $csynth_opts"
    set status [catch {eval csynth_design $csynth_opts} errMsg]
}
puts ""

if { $status != 0 } {
    puts "=========================================="
    puts "  ❌ SYNTHESIS FAILED"
    puts "=========================================="
    puts "Error: $errMsg"
    exit 1
} else {
    puts "=========================================="
    puts "  ✅ SYNTHESIS PASS"
    puts "=========================================="
    puts ""
    puts "Reports should be under:"
    puts "  $project_dir/solution1/syn/report/"
}

close_project
exit