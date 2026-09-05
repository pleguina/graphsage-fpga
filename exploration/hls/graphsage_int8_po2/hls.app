<AutoPilot:project xmlns:AutoPilot="com.autoesl.autopilot.project" top="graphsage_int8_po2" name="graphsage_int8_po2" ideType="classic" projectType="C/C++">
    <files>
        <file name="../../../hls/graphsage_layer_int8_po2.h" sc="0" tb="false" cflags="-I/home/pelayo/work/simple-gnn/hls -DM_BITS=24 -DBETA1_SHIFT=17 -DBETA2_SHIFT=12 -DEFF_SCALE1_SHIFT=6 -DEFF_SCALE2_SHIFT=6" csimflags="" blackbox="false"/>
        <file name="../../../hls/graphsage_layer_int8_po2.cpp" sc="0" tb="false" cflags="-I/home/pelayo/work/simple-gnn/hls -DM_BITS=24 -DBETA1_SHIFT=17 -DBETA2_SHIFT=12 -DEFF_SCALE1_SHIFT=6 -DEFF_SCALE2_SHIFT=6" csimflags="" blackbox="false"/>
        <file name="../../../../hls/testbench_int8_po2.cpp" sc="0" tb="1" cflags="-I/home/pelayo/work/simple-gnn/hls -DM_BITS=24 -DBETA1_SHIFT=17 -DBETA2_SHIFT=12 -DEFF_SCALE1_SHIFT=6 -DEFF_SCALE2_SHIFT=6 -Wno-unknown-pragmas" csimflags="" blackbox="false"/>
    </files>
    <Simulation argv="">
        <SimFlow name="csim" setup="false" optimizeCompile="false" clean="true" ldflags="" mflags=""/>
    </Simulation>
    <solutions>
        <solution name="solution1" status=""/>
    </solutions>
</AutoPilot:project>

