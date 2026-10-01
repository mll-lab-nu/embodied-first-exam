#!/bin/bash
# Oracle (standard mode): the privileged oracle's recorded actions (solution/sit_simple_actions.npy) sent through the
# client, one row per control step. No privileged information at run time: only the recorded actions.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
