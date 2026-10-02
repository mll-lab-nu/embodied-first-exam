#!/bin/bash
# Oracle: replay the reference trajectory (recorded offline on this frozen instance) and hand it in.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
cd /solution && python /solution/oracle_replay.py
