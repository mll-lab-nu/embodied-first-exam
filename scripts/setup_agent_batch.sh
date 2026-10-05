#!/usr/bin/env bash
# Optional maintainer entrypoint; run_agent_batch.sh performs this automatically.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$R/scripts/agent_batch_bootstrap.py"
