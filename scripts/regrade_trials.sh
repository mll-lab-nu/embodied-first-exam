#!/usr/bin/env bash
# v15 only; records a new verdict without overwriting the original trial.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
exec "${TOPOGYM_PYTHON:-$R/.venv-gs121-nyx/bin/python}" "$R/scripts/regrade_trials.py" "$@"
