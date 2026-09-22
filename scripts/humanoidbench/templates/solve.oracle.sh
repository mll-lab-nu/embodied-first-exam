#!/bin/bash
# Oracle: run the reference solution (kept in solution/, never in the agent image) and record it.
set -e
mkdir -p /app/output
python /opt/tools/rcb_hb.py run-oracle --task {{family}} --instance /app/instance.npz --code /solution/{{oracle_file}} --out /app/output/trajectory.npz
cp /solution/{{oracle_file}} /app/output/gen.py
