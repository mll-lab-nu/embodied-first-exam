#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in two fresh processes (the
# verdict), then a third that renders replay.mp4.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, docs/PROTOCOL.md §2.6).
# Harbor also mounts /logs/verifier into the agent's container: start from an empty directory, so nothing the agent
# left there (a planted reward, a symlink) can count. rm never follows symlinks.
rm -rf /logs/verifier/*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/PROTOCOL.md §2.10)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # the agent's files are untrusted input: no link out of /app/output, no FIFO or device (docs/PROTOCOL.md §2.6)
mkdir -p /logs/verifier
python /tests/grade.py --instance /tests/instance.json --traj /app/output/trajectory.npz 2> /logs/verifier/grade.log
