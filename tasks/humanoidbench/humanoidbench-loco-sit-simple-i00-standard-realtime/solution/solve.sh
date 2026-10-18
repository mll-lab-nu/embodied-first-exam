#!/bin/bash
# Oracle (standard-realtime mode): the privileged oracle's recorded actions (solution/sit_simple_actions.npy) streamed
# through the client into the episode's plan, one row per control step. No privileged information at run time: only
# the recorded actions.
set -e
mkdir -p /app/output
cp /solution/oracle_stream.py /app/output/gen.py
python /solution/oracle_stream.py
