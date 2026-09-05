proc constrain_hierarchy_domain {pblock_name slr patterns} {
    set cells {}
    foreach pattern $patterns {
        set cells [concat $cells [get_cells -hierarchical -quiet -filter "NAME =~ $pattern"]]
    }
    set cells [lsort -unique $cells]
    if {[llength $cells] == 0} {
        error "No cells matched $pblock_name patterns: $patterns"
    }

    foreach root $cells {
        set_property KEEP_HIERARCHY true $root
    }

    create_pblock $pblock_name
    add_cells_to_pblock [get_pblocks $pblock_name] $cells
    resize_pblock [get_pblocks $pblock_name] -add $slr
    set_property IS_SOFT false [get_pblocks $pblock_name]
    puts "PBLOCK=$pblock_name SLR=$slr ROOTS=[llength $cells]"
}

constrain_hierarchy_domain pb_domain0 SLR0 [list \
    *grp_linear1_local_group_0_6_* \
    *grp_aggregate2_local_group_0_2_*]
constrain_hierarchy_domain pb_domain1 SLR1 [list \
    *grp_linear1_local_group_6_6_* \
    *grp_aggregate2_local_group_2_2_*]
constrain_hierarchy_domain pb_domain2 SLR2 [list \
    *grp_aggregate_int8_po2_replicated_* \
    *grp_linear1_local_group_12_6_* \
    *grp_aggregate2_local_group_4_2_*]
constrain_hierarchy_domain pb_domain3 SLR3 [list \
    *grp_linear1_local_group_18_6_* \
    *grp_aggregate2_local_group_6_2_*]