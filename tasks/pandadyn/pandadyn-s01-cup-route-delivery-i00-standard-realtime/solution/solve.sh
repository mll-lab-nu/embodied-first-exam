#!/bin/bash
# Oracle (standard-realtime mode): plans the privileged oracle's joint targets, one row per control step, into the episode
# from step 0 through the realtime client. Uses no privileged information at run time (only the pre-recorded targets).
set -e
mkdir -p /app/output
cp /solution/oracle_plan.py /app/output/gen.py
python /solution/oracle_plan.py
