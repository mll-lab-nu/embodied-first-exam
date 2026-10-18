#!/bin/bash
# Verifier (separate sandbox): clear earlier verdicts, then grade. grade.py writes /logs/verifier/reward.txt (1/0) and a
# numeric reward.json.
rm -rf /logs/verifier/*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/protocol/README.md §2.10)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # the agent's files are untrusted input: no link out of /app/output, no FIFO or device (docs/protocol/README.md §2.6)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
