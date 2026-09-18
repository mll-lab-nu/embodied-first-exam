#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in a fresh process.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/PROTOCOL.md).
cd /opt/cap-x
python /tests/grade.py --family cube_stack --instance /tests/instance.npz --traj /app/output/trajectory.npz --repeat 2 \
  2> /logs/verifier/grade.log
