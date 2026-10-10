#!/bin/bash
# Verifier (separate sandbox): clear earlier verdicts, then grade. grade.py writes /logs/verifier/reward.txt (1/0) and a
# numeric reward.json.
rm -rf /logs/verifier/*
trap 'p=$(command -v python3 || command -v python); "$p" /tests/rcb_limits.py verify' EXIT   # resource limits, after the grader (docs/PROTOCOL.md §2.10)
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
