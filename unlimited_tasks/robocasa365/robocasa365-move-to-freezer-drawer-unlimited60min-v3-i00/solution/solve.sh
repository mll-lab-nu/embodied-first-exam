#!/bin/bash
set -euo pipefail
if [ ! -f /solution/oracle.npz ]; then
  echo "Reference trajectory has not passed author validation; see validation/status.json" >&2
  exit 1
fi
python /solution/solve.py
