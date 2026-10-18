#!/bin/bash
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md §2.6)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/protocol/README.md §2.10)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # the agent's files are untrusted input: no link out of /app/output, no FIFO or device (docs/protocol/README.md §2.6)
mkdir -p /logs/verifier
python /tests/grade.py
