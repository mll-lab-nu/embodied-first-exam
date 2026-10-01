#!/bin/bash
# Oracle: run the human-written reference solution (kept in solution/, never in the agent image) and record it.
set -e
mkdir -p /app/output
python /opt/tools/rcb_robowits.py run-oracle --task dominos --instance /app/instance.json --code /solution/oracle_dominos.py --out /app/output/trajectory.npz
cp /solution/oracle_dominos.py /app/output/gen.py
