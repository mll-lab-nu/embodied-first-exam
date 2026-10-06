#!/bin/bash
# Oracle (standard mode): replays the privileged oracle's joint targets, one row per control step, as `joint_position` chunks
# through the client. Uses no privileged information at run time (only the pre-recorded targets).
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
