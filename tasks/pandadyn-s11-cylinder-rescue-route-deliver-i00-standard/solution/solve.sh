#!/bin/bash
# Oracle (standard mode): spends the reset budget on short scouting episodes, then replays the privileged oracle's joint
# targets, one row per control step, as `joint_position` chunks through the client in the last (graded) episode. Uses no
# privileged information at run time (only the pre-recorded targets).
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
