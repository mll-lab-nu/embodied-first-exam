#!/bin/bash
# Oracle: run the human-written reference solution (kept in solution/, never in the agent image) and record it. It needs
# the task-level primitives (navigation, grasp, place_inside, ...) of the tooling it was written with, frozen in
# solution/rcb_behavior_ref.py; the agent's tooling has only thin ones. The copy runs next to the robot config it loads.
set -e
mkdir -p /app/output /tmp/rcb_ref
cp /solution/rcb_behavior_ref.py /tmp/rcb_ref/rcb_behavior.py
cp /opt/tools/r1pro_primitives_eval.yaml /tmp/rcb_ref/
python /tmp/rcb_ref/rcb_behavior.py run-oracle --task putting_shoes_on_rack --instance /app/instance.json --code /solution/oracle_putting_shoes_on_rack.py --out /app/output/trajectory.npz
cp /solution/oracle_putting_shoes_on_rack.py /app/output/gen.py
