#!/bin/bash
# Verifier: replay /app/output/trajectory.npz twice from the frozen instance (tests/, with its goal) in fresh processes.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/PROTOCOL.md Appendix H.1)
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/PROTOCOL.md §2.10)
p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py sanitize /app/output || true   # the agent's files are untrusted input: no link out of /app/output, no FIFO or device (docs/PROTOCOL.md §2.6)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
