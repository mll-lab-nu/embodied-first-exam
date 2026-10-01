#!/bin/bash
# Oracle: replay VLABench's expert controls (recorded offline on this frozen instance) and hand them in.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
cd /solution && python /solution/oracle_replay.py
