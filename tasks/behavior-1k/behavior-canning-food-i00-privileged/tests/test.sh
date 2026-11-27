#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) up to 3 times, each in a fresh
# process, stopping at the first success (task.toml [metadata] replays, docs/protocol/tasks.md#grading).
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/protocol/README.md).
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/invariants.md H.1)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (docs/protocol/resources.md)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (docs/protocol/invariants.md H.1)
mkdir -p /logs/verifier
python /tests/grade.py --family canning_food --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 3 \
  2> /logs/verifier/grade.log
