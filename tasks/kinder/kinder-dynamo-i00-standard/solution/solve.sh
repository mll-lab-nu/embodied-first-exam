#!/bin/bash
# Oracle (standard mode): the privileged oracle's moves, recorded in the odometry frame, streamed through the client.
# No privileged information at run time: only the recorded moves.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
