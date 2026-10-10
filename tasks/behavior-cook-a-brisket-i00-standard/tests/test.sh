#!/bin/bash
# Verifier (separate sandbox): grades the sim sidecar's own record, uploaded by Harbor from the sidecar's /out.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/PROTOCOL.md §2.6)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/PROTOCOL.md §2.10)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
