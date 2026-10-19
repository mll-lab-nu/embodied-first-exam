#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in two fresh processes and judge
# each run with Embodied Safety Exam's verdict. Writes /logs/verifier/reward.txt (1/0) and reward.json (numbers).
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent left
# there can count. rm never follows symlinks.
rm -rf /logs/verifier/*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/protocol/README.md §2.10)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # the agent's files are untrusted input: no link out of /app/output, no FIFO or device (docs/protocol/README.md §2.6)
mkdir -p /logs/verifier
cd /tmp && python /tests/grade.py 2> /logs/verifier/grade.log
