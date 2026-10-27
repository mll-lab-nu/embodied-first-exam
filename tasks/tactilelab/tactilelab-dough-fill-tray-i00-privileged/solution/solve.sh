#!/bin/bash
# Oracle: the scripted demonstration policy (kept in solution/, never in the agent image) recorded through the Session.
# The policy code and the task's full config (with its expert blocks) are laid over the package first.
set -e
mkdir -p /app/output
cp -r /solution/oracle_pkg/tactilelab_tasks/. /opt/tactilelab/tactilelab_tasks/
python /opt/tools/rcb_tactilelab.py run-oracle --task dough_fill_tray --instance /app/instance.json --code /solution/oracle_dough_fill_tray.py --out /app/output/trajectory.npz
cp /solution/oracle_dough_fill_tray.py /app/output/gen.py
