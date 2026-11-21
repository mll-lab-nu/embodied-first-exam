#!/bin/bash
# Oracle (standard mode): submits the standard reference's control steps (solution/oracle_actions.npz: the privileged
# reference slowed down to the joint-speed rule) through the client, one control step per row (hold), as float64.
# Uses no privileged information at run time (only the pre-recorded rows).
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
