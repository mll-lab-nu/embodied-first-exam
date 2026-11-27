#!/bin/bash
# Verifier: grade every submitted checkpoint (/app/output/submissions/) and the final /app/output/solution/ against the
# frozen instance (the tests/ copy), each in a fresh simulator; the best one is the result. Writes
# /logs/verifier/reward.txt (1/0), reward.json (numbers only), results.json (every candidate), trajectory.npz and the video.
rm -rf /logs/verifier/* /logs/verifier/.[!.]*   # verdicts from an earlier run never survive (docs/protocol/tasks.md#grading)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (docs/protocol/resources.md)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (docs/protocol/invariants.md H.1)
mkdir -p /logs/verifier
chmod 700 /logs/verifier                        # the solution process (nobody) can neither read nor write the logs
python /tests/grade.py --instance /tests/instance.json --grader /tests/grader/fruit_delivery.py 2> /logs/verifier/grade.log
