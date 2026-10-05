#!/usr/bin/env bash
# Helper-only workflow. Receiver download/website import is a separate process.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
P=python3
if [ -x "$R/.venv-agent-batch/bin/python" ]; then P="$R/.venv-agent-batch/bin/python"; fi
export PYTHONDONTWRITEBYTECODE=1
exec "$P" "$R/scripts/helper_batch.py" "$@"
