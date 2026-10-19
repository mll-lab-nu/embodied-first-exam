#!/bin/bash
# Oracle (standard mode): streams the reference trajectory's muscle commands (solution/oracle.npy, one row per control
# step) as `muscle` chunks through the client. Uses no privileged information at run time (only the pre-recorded rows);
# the service's recorded trajectory is then exactly the privileged reference.
set -e
mkdir -p /app/output
cp /solution/oracle_stream.py /app/output/gen.py
python /solution/oracle_stream.py
