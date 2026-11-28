#!/bin/bash
# Verifier: replay /app/output/trajectory.npz once, in a fresh process, from the frozen instance (the tests/ copy).
# Writes /logs/verifier/reward.txt (1/0), reward.json (numbers only) and replay.mp4 (docs/protocol/tasks.md#grading).
rm -rf /logs/verifier/*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (docs/protocol/resources.md)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (docs/protocol/invariants.md H.1)
mkdir -p /logs/verifier
python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz 2> /logs/verifier/grade.log
