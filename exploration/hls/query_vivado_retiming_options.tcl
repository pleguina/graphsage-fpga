create_project -in_memory -part xcvu13p-fsga2577-1-e
puts "SYNTH_DESIGN_HELP_BEGIN"
synth_design -help
puts "SYNTH_DESIGN_HELP_END"
puts "PHYS_OPT_DESIGN_HELP_BEGIN"
phys_opt_design -help
puts "PHYS_OPT_DESIGN_HELP_END"
exit 0
