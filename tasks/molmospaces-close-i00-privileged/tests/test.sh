#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in two fresh processes (the
# verdict), then a third that renders replay.mp4.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, docs/PROTOCOL.md §2.6).
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent
# left there (a planted reward, a symlink) can count. rm never follows symlinks.
rm -rf /logs/verifier/*
mkdir -p /logs/verifier
python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz 2> /logs/verifier/grade.log
