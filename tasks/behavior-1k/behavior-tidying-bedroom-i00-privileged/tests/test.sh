#!/bin/bash
# Verifier: replay /app/output/trajectory.npz from the frozen instance (the tests/ copy) in a fresh process.
# Writes /logs/verifier/reward.txt (1/0) and reward.json (numeric fields, see docs/protocol/README.md).
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md Appendix H.1)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (PROTOCOL §6)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (PROTOCOL H.1)
mkdir -p /logs/verifier
python /tests/grade.py --family tidying_bedroom --instance /tests/instance.json --traj /app/output/trajectory.npz --repeat 1 \
  2> /logs/verifier/grade.log
