#!/bin/bash
# Oracle: record cap-x's human-written reference code into a trajectory.
set -e
mkdir -p /app/output
cd /opt/cap-x
python -m rcb.traj run-oracle --task cube_stack --instance /app/instance.npz --out /app/output/trajectory.npz
cp /opt/rcb/rcb/traj.py /app/output/gen.py
