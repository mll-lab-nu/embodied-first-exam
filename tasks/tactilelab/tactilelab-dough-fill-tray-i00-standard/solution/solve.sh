#!/bin/bash
# Oracle (standard mode): streams the privileged twin's reference trajectory (solution/oracle_rows.npz, one row of the
# privileged format per control step) as `ee_pose` chunks through the client. Uses no privileged information at run time
# (only the pre-recorded rows); the service executes exactly those rows.
set -e
mkdir -p /app/output
cp /solution/oracle_client.py /app/output/gen.py
python /solution/oracle_client.py
