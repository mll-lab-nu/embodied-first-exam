#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in a fresh process.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/protocol/tasks.md#grading).
mkdir -p /logs/verifier
rm -rf /logs/verifier/*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (docs/protocol/resources.md)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (docs/protocol/invariants.md H.1)
python /tests/grade.py --family walk --instance /tests/instance.npz --traj /app/output/trajectory.npz \
  2> /logs/verifier/grade.log
