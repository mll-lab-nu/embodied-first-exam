#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
cd /tests
PYTHONPATH=/tests python /tests/casa_grade.py > /logs/verifier/grade.log 2>&1
