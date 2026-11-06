#!/bin/bash
# Verifier: replay /app/output/trajectory.npz once from the frozen instance (tests/, with its goal) in a fresh process.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md Appendix H.1)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resources, after the grader (PROTOCOL §6)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # untrusted agent files (PROTOCOL H.1)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
