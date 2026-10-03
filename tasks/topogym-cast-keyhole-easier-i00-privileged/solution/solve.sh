#!/bin/bash
# Oracle: run the human-written reference solution (kept in solution/, never in the agent image) and record it.
set -e
mkdir -p /app/output
python /opt/tools/rcb_topogym.py run-oracle --task cast_keyhole --instance /app/instance.json --code /solution/oracle_cast_keyhole.py --out /app/output/trajectory.npz
cp /solution/oracle_cast_keyhole.py /app/output/gen.py
