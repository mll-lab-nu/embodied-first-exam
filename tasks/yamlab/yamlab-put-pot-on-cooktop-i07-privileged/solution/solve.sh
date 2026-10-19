#!/bin/bash
# Oracle: replay the reference actions (solution/oracle_actions.npy: a 1 s ramp from the home pose to the first action of
# YAMLab's teleoperation demonstration of this instance, then that demonstration's recorded actions) through the agent's
# own tooling, and save the trajectory. The actions live in solution/ only (never in the agent image).
set -e
mkdir -p /app/output
cp /solution/oracle.py /app/output/gen.py
python /solution/oracle.py
