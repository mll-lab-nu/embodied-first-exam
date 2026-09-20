#!/usr/bin/env bash
# Evaluate a task with DeepSeek V4.1 Flash through OpenRouter and the Codex CLI harness.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASK="${1:-tasks/libero-pick-alphabet-soup-basket-i00}"
if [ "$#" -gt 0 ]; then shift; fi

cd "$ROOT"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" exec harbor run \
  -p "$TASK" \
  -a harbor_agents.codex_openrouter:CodexOpenRouter \
  -m openrouter/deepseek/deepseek-v4.1-flash \
  --env-file "$ROOT/.env" \
  --allow-agent-host openrouter.ai \
  "$@"
