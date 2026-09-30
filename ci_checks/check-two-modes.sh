#!/usr/bin/env bash
# The registry check needs the Python environment Harbor is installed in (HARBOR_PYTHON, or the one behind `harbor`).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
harbor_python="${HARBOR_PYTHON:-}"
if [ -z "$harbor_python" ] && command -v harbor >/dev/null; then
  harbor_python="$(dirname "$(readlink -f "$(command -v harbor)")")/python"
fi
[ -x "$harbor_python" ] || { echo "FAIL two-modes: set HARBOR_PYTHON to the Python that has harbor installed"; exit 1; }
cd "$root/scripts/two_modes" && "$harbor_python" check.py
