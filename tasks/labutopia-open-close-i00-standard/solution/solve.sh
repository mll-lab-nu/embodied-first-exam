#!/bin/bash
# Oracle (standard mode): streams the reference trajectory's joint targets (solution/oracle.npz, one row per 1/60 s
# control step) as `joint_position_velocity` chunks through the client. Uses no privileged information at run time (only
# the pre-recorded rows); the service's recorded trajectory is then exactly the privileged reference.
set -e
mkdir -p /app/output
cp /solution/oracle_stream.py /app/output/gen.py
python /solution/oracle_stream.py
