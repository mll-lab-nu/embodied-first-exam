#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
exec "${PYTHON:-python3}" "$root/ci_checks/check-calibration-isolation.py" "$@"
