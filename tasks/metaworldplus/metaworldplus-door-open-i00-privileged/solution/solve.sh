#!/bin/bash
# Oracle: replay Meta-World's scripted expert (recorded offline on this frozen instance) and hand it in.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
cd /solution && python /solution/oracle_replay.py
