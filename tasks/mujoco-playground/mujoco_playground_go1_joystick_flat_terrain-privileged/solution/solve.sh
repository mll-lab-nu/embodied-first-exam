#!/bin/bash
# Oracle (privileged): write the reference trajectory frozen at generation time (solution/oracle.npy; how it was made:
# scripts/mujoco-playground/oracle.py) as the deliverable.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
