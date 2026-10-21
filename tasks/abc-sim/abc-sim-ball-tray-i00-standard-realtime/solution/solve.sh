#!/bin/bash
# Reference solution (standard-realtime): plan the privileged twin's reference rows into the episode from step 0.
set -e
mkdir -p /app/output
cp /solution/oracle_plan.py /app/output/gen.py
python /solution/oracle_plan.py
