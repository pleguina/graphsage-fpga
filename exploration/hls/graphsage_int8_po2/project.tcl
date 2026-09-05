#-------------------------------------------------------------
# project.tcl — auto-generated for graphsage_int8_po2. DO NOT EDIT BY HAND.
#-------------------------------------------------------------

# ---------- core project variables --------------------------
# Absolute path to the HLS project dir for this module
set project_dir   "/home/pelayo/work/simple-gnn/build/hls/graphsage_int8_po2"

# Logical metadata (not strictly required by Vitis, but useful)
set project_name  "graphsage_int8_po2"
set top_function  "graphsage_int8_po2"
set part_name     "xcvu13p-fsga2577-1-e"
set clock_period  2.0

set description   "Streaming HLS Module"
set display_name  "graphsage_int8_po2"
set vendor        "GNN"
set version       "1.0"

puts "=========================================="
puts "  PROJECT SETUP - graphsage_int8_po2"
puts "=========================================="
puts "▶ project_dir   = $project_dir"
puts "▶ top_function  = $top_function"
puts "▶ part_name     = $part_name"
puts "▶ clock_period  = $clock_period"
puts ""

# ---------- (re)create project ------------------------------
open_project -reset $project_dir
set_top $top_function

# ---------- solution / timing / device ----------------------
open_solution -reset "solution1" -flow_target vivado
set_part     $part_name
create_clock -period $clock_period -name default

# ---------- sources / testbench -----------------------------
# These filenames are intentionally kept RELATIVE (../../src/...)
# so that Vitis HLS copies them into the out-of-context project
# instead of baking absolute /home/... paths.
set src_files { "/home/pelayo/work/simple-gnn/hls/graphsage_layer_int8_po2.cpp" "/home/pelayo/work/simple-gnn/hls/graphsage_layer_int8_po2.h"  }
set tb_files  { "/home/pelayo/work/simple-gnn/hls/testbench_int8_po2.cpp"  }

# ---------- include directories -----------------------------
# We build cflags as a Tcl list - each flag is a separate element.
# This avoids quote-escaping issues entirely.
set cflags [list \
  -I/home/pelayo/work/simple-gnn/hls \
  -DM_BITS=24 \
  -DBETA1_SHIFT=17 \
  -DBETA2_SHIFT=12 \
  -DEFF_SCALE1_SHIFT=6 \
  -DEFF_SCALE2_SHIFT=6 \
]

puts "▶ Adding source files..."
foreach file $src_files {
    puts "   + $file"
    add_files $file -cflags $cflags
}

puts "▶ Adding testbench files..."
foreach file $tb_files {
    puts "   + $file (TB)"
    add_files $file -cflags $cflags -tb
}

puts ""
puts "✅ project.tcl setup complete for graphsage_int8_po2"
puts "   Project dir: $project_dir"
puts "   Solution   : solution1"
puts ""

close_project
exit