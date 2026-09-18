#!/bin/bash
# Oracle: record cap-x's human-written reference code for cube_stack into a trajectory.
set -e
mkdir -p /app/output
cd /opt/cap-x
python /opt/tools/rcb_traj.py run-oracle --task cube_stack --instance /app/instance.npz --out /app/output/trajectory.npz
cp /opt/tools/rcb_traj.py /app/output/gen.py
