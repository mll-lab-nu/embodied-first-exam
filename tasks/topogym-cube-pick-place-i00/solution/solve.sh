#!/bin/bash
# Oracle: run the human-written reference solution (kept in solution/, never in the agent image) and record it.
set -e
mkdir -p /app/output
python /opt/tools/rcb_topogym.py run-oracle --task cube_pick_place --instance /app/instance.json --code /solution/oracle_cube_pick_place.py --out /app/output/trajectory.npz
cp /solution/oracle_cube_pick_place.py /app/output/gen.py
