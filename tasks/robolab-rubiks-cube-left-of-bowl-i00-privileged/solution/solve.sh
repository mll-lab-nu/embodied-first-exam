#!/bin/bash
# Oracle: run the human-written reference solution (kept in solution/, never in the agent image) and record it.
set -e
mkdir -p /app/output
python /opt/tools/rcb_robolab.py run-oracle --task rubiks_cube_left_of_bowl --instance /app/instance.json --code /solution/oracle_rubiks_cube_left_of_bowl.py --out /app/output/trajectory.npz
cp /solution/oracle_rubiks_cube_left_of_bowl.py /app/output/gen.py
