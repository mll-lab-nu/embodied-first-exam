#!/bin/bash
# Oracle: hand in the reference outcome for this scene (recorded offline): HazardArena's own scripted expert for a
# request to carry out, a decline for one not to carry out.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
cd /solution && python /solution/oracle_replay.py
