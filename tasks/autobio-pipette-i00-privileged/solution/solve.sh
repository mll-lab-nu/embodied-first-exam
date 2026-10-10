#!/bin/bash
# Oracle (privileged): replay the reference trajectory frozen at generation time (solution/oracle.npz: the position
# targets AutoBio's own scripted expert sent from the frozen instance; scripts/autobio/README.md), check it and save it
# as the deliverable.
set -e
mkdir -p /app/output
cp /solution/oracle_replay.py /app/output/gen.py
python /solution/oracle_replay.py
