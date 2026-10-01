#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in a fresh process.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/PROTOCOL.md §2.6).
mkdir -p /logs/verifier
rm -rf /logs/verifier/*
python /tests/grade.py --family truck --instance /tests/instance.npz --traj /app/output/trajectory.npz --repeat 2 \
  2> /logs/verifier/grade.log
