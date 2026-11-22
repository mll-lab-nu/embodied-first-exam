#!/bin/bash
# Oracle (standard mode): streams the reference trajectory's joint targets (solution/oracle.npy, one row per control step)
# as `joint_position` chunks through the client. Uses no privileged information at run time (only the pre-recorded
# targets); the service's recorded trajectory is then exactly the privileged reference.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
