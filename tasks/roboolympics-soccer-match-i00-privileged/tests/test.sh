#!/bin/bash
set -eu
mkdir -p /logs/verifier
rm -rf /logs/verifier/* /logs/verifier/.[!.]*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/protocol/README.md §2.10)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # the agent's files are untrusted input: no link out of /app/output, no FIFO or device (docs/protocol/README.md §2.6)
chmod 755 /logs/verifier
python /tests/grade.py > /logs/verifier/grade.log 2>&1
