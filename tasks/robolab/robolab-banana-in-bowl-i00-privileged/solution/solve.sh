#!/bin/bash
# Oracle: run the human-written reference solution (kept in solution/, never in the agent image) and record it.
set -e
mkdir -p /app/output
python /opt/tools/rcb_robolab.py run-oracle --task banana_in_bowl --instance /app/instance.json --code /solution/oracle_banana_in_bowl.py --out /app/output/trajectory.npz
cp /solution/oracle_banana_in_bowl.py /app/output/gen.py
