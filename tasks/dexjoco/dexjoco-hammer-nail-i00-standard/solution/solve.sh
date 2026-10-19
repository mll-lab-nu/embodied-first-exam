#!/bin/bash
# Oracle (standard mode): streams the reference trajectory's rows (solution/oracle_trajectory.npz, one row per control
# step) as `ee_pose` chunks through the client. Uses no privileged information at run time (only the pre-recorded rows);
# the service's recorded trajectory is then exactly the privileged reference.
set -e
mkdir -p /app/output
cp /solution/oracle_stream.py /app/output/gen.py
python /solution/oracle_stream.py
