#!/bin/bash
set -eu
mkdir -p /logs/verifier
rm -rf /logs/verifier/* /logs/verifier/.[!.]*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (PROTOCOL §6)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (PROTOCOL H.1)
chmod 755 /logs/verifier
python /tests/grade.py > /logs/verifier/grade.log 2>&1
