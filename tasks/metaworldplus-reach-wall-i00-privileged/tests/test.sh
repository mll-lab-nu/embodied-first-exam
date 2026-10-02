#!/bin/bash
# Verifier (separate sandbox): clear earlier verdicts, then grade. grade.py writes /logs/verifier/reward.txt (1/0) and a
# numeric reward.json.
rm -rf /logs/verifier/*
mkdir -p /logs/verifier
python /tests/grade.py 2> /logs/verifier/grade.log
