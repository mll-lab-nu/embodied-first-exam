#!/bin/bash
# Oracle (privileged mode): replay the recorded reference actions (solution/sit_simple_actions.npy, found by CEM-MPC:
# solution/cem_mpc.py) through the tooling, which records them as the trajectory.
set -e
mkdir -p /app/output
python /opt/tools/rcb_hb.py run-oracle --task sit_simple --instance /app/instance.npz --code /solution/oracle_sit_simple.py \
  --out /app/output/trajectory.npz
cp /solution/oracle_sit_simple.py /app/output/gen.py
