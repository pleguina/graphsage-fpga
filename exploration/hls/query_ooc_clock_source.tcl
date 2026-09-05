set script_dir [file dirname [file normalize [info script]]]
set repo_root [file normalize [file join $script_dir ..]]
set checkpoint [file join \
    $repo_root build vivado_sweep route_ssi_spread_high final.dcp]

if {![file exists $checkpoint]} {
    error "Missing implemented checkpoint: $checkpoint"
}

open_checkpoint $checkpoint

set site [get_sites BUFGCE_X0Y192]
puts "SITE=[get_property NAME $site]"
puts "SITE_TYPE=[get_property SITE_TYPE $site]"
puts "SITE_CLOCK_REGION=[get_property NAME \
    [get_clock_regions -of_objects $site]]"
puts "SITE_SLR=[get_property NAME [get_slrs -of_objects $site]]"
puts "SITE_X=[get_property RPM_X $site]"
puts "SITE_Y=[get_property RPM_Y $site]"

foreach target_site {SLICE_X134Y490 DSP48E2_X4Y247} {
    set object [get_sites $target_site]
    puts [join [list \
        "TARGET=$target_site" \
        "TYPE=[get_property SITE_TYPE $object]" \
        "CLOCK_REGION=[get_property NAME \
            [get_clock_regions -of_objects $object]]" \
        "SLR=[get_property NAME [get_slrs -of_objects $object]]" \
        "RPM_X=[get_property RPM_X $object]" \
        "RPM_Y=[get_property RPM_Y $object]"] " "]
}

puts "HD_CLK_SRC=[get_property HD.CLK_SRC [get_ports ap_clk]]"

close_design
exit 0