#!/bin/bash
# Oracle (standard mode): submit the validated authoring trajectory's rows (solution/trajectory.npz), one row per
# 50 Hz control, as `joint_position` chunks through the same client an agent has. No privileged information is used.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
