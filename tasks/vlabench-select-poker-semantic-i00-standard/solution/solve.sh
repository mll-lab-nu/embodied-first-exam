#!/bin/bash
# Oracle (standard mode): submit the recorded expert control steps through the client; the sim service records the
# episode, replays it and grades it.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
