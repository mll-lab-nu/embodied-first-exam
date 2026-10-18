#!/bin/bash
# Verifier: replay /app/output/trajectory.npz twice from the frozen instance (tests/, with its goal) in fresh processes.
rm -rf /logs/verifier/*   # verdicts from an earlier run never survive (docs/protocol/README.md Appendix H.1)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
