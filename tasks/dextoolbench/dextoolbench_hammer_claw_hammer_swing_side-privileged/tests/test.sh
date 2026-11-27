#!/bin/bash
# Verifier (separate sandbox): replay /app/output/trajectory.npz from the frozen start state (tests/ copies of the
# tooling and instance) and write /logs/verifier/reward.txt (success, 1/0; progress in reward.json) + reward.json.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/invariants.md H.1)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (docs/protocol/resources.md)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (docs/protocol/invariants.md H.1)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
