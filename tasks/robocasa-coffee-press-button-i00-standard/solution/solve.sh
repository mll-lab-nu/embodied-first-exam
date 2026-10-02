#!/bin/bash
# Oracle (standard mode): submit the recorded reference actions through the client; the sim service records and grades.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
