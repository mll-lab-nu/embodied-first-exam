#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/output
cp /solution/gen.py /app/output/gen.py
PYTHONPATH=/app python /app/output/gen.py
