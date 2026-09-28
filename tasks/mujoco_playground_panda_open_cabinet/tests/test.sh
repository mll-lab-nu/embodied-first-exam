#!/bin/bash
# Verifier (separate sandbox): replay /app/output/trajectory.npz from the frozen start state (tests/ copies of the
# tooling and instance) and write /logs/verifier/reward.txt (1/0) + reward.json.
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
