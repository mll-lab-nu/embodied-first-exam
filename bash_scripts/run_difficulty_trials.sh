#!/usr/bin/env bash
# Compatibility entry point; experiment logic lives in scripts/difficulty_eval.py.
set +x
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${TOPOGYM_EVAL_PYTHON:-$ROOT/.venv-gs121-nyx/bin/python}"
exec "$PY" "$ROOT/scripts/difficulty_eval.py" "$@"
