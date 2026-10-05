#!/usr/bin/env bash
# Receiver only: HF download and offline acceptance, no GPU/model or helper execution.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
P="${TOPOGYM_RECEIVER_PYTHON:-python3}"
if [ -z "${TOPOGYM_RECEIVER_PYTHON:-}" ] && [ -x "$R/.venv-agent-batch/bin/python" ]; then P="$R/.venv-agent-batch/bin/python"; fi
export PYTHONDONTWRITEBYTECODE=1
exec "$P" "$R/scripts/import_helper_results.py" "$@"
