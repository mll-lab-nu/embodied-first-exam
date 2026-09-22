#!/usr/bin/env bash
# Evaluate a task through OpenRouter while keeping Harbor's native Codex CLI harness.
#
#   scripts/run_deepseek_openrouter.sh                                   # default task, default model
#   scripts/run_deepseek_openrouter.sh tasks/humanoidbench-loco-walk-i00 -k 3
#   RCB_MODEL=openrouter/qwen/qwen3-max scripts/run_deepseek_openrouter.sh tasks/... 
#
# Any OpenRouter model works; the adapter in harbor_agents/codex_openrouter.py exists because Harbor's
# Codex adapter keeps only the last slash-delimited component of a model id, which would turn
# `openrouter/deepseek/deepseek-v4.1-flash` into `deepseek-v4.1-flash` and lose the provider.
# Needs OPENROUTER_API_KEY in .env.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASK="${1:-tasks/humanoidbench-loco-sit-simple-i00}"
MODEL="${RCB_MODEL:-openrouter/deepseek/deepseek-v4.1-flash}"
if [ "$#" -gt 0 ]; then shift; fi

cd "$ROOT"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" exec harbor run \
  -p "$TASK" \
  -a harbor_agents.codex_openrouter:CodexOpenRouter \
  -m "$MODEL" \
  --env-file "$ROOT/.env" \
  --allow-agent-host openrouter.ai \
  "$@"
