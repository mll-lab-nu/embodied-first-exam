#!/bin/bash
# Oracle (standard mode): submit the reference outcome through the client (the expert's recorded control steps, or a
# decline); the sim service records the episode, replays it and grades it.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
