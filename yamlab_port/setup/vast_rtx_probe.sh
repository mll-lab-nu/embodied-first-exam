#!/bin/bash
R=/workspace/yamlab_port; . $R/env.sh; cd $R
ls -la /dev/nvidia* /dev/dri 2>&1
for args in "" "--/renderer/multiGpu/enabled=false" "--/renderer/multiGpu/enabled=false --/rtx/verifyDriverVersion/enabled=false --/renderer/activeGpu=0"; do
  echo "=== PROBE args: [$args]"
  timeout 300 python vast_rtx_probe.py $args 2>&1 | grep -E "RTX_PROBE_OK|Crash detected|Error\]|Traceback|Error:" | grep -v MaterialX | head -8
done
echo PROBE_DONE
