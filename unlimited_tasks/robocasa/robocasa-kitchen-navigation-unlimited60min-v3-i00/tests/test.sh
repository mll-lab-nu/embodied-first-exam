#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
cd /tests
python grade.py
