#!/bin/bash
# Oracle (standard mode): the privileged-mode oracle's recorded targets, submitted through the client.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
