#!/bin/bash
# Oracle (limited mode): the unlimited oracle's recorded targets, submitted through the client.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
