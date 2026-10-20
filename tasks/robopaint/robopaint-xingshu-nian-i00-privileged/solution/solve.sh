#!/bin/bash
# Oracle: replay the reference plan frozen at generation time (solution/oracle_qpos.npy; how it was made: the task README's Reference solution) and record it.
set -e
mkdir -p /app/output
RCB_SOLUTION_DIR=/solution python /opt/tools/rcb_brush.py run-oracle --instance /app/instance.json \
  --code /solution/oracle_paint.py --out /app/output/trajectory.npz
cp /solution/oracle_paint.py /app/output/gen.py
