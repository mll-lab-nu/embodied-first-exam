#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
/usr/local/bin/python -I /tests/grade.py
