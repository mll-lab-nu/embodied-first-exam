#!/bin/bash
# Oracle: run the human-written reference solution (kept in solution/, never in the agent image) and record it.
set -e
mkdir -p /app/output
cd /opt/cap-x
python /opt/tools/rcb_traj.py run-oracle --task cube_stack --instance /app/instance.npz --code /solution/oracle_cube_stack.py --out /app/output/trajectory.npz
cp /solution/oracle_cube_stack.py /app/output/gen.py
