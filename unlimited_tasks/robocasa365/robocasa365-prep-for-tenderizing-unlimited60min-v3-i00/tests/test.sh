#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
cd /tests
python -I /tests/casa_grade.py
