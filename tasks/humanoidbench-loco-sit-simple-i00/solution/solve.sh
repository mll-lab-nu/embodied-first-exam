#!/bin/bash
# Oracle: run the reference solution (kept in solution/, never in the agent image) and record it.
set -e
mkdir -p /app/output
python /opt/tools/rcb_hb.py run-oracle --task sit_simple --instance /app/instance.npz --code /solution/oracle_sit_simple.py --out /app/output/trajectory.npz
cp /solution/oracle_sit_simple.py /app/output/gen.py
