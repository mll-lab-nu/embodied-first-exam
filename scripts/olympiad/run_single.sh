#!/bin/bash
# Run one configuration of a single-player Olympiad task (default tasks/tabletennis-match-wallclock-program-standard).
#   run_single.sh [--task NAME] --agent opus|fable|astra|luna|oracle|nop --level L [--slowdown S] [--seed N] [--tag TAG]
# (--slowdown for real-time sports; precision sports have none and take --level 1 when they have no levels)
# Table tennis' seed defaults to the level's first official seed (L1 101, L2 202, L3 303, L4 404); other sports need
# --seed. Players:
#   opus   Claude Code 2.1.284, claude-opus-5-5, on the Claude subscription token in .env
#   fable  Claude Code 2.1.284, claude-fable-5-1, on the same subscription
#   astra  Codex 0.158.0, gpt-6-astra, reasoning effort medium, on Azure with failover over gpt-6-astra/-2/-3
#          (one Astra match per key at a time)
#   luna   Codex 0.158.0, openai/gpt-6-luna, reasoning effort medium, on OpenRouter
# The sim's metering proxy holds the credentials and strips the provider prefix for Azure.
# Job: jobs/<tag>-<agent>-L<L>-x<S>-s<seed>-<UTC time>; prints the job and its reward.json.
set -euo pipefail
task=tabletennis-match-wallclock-program-standard agent= level= slowdown= seed= tag=tt
while [ $# -gt 0 ]; do
  case $1 in
    --task) task=$2; shift 2;; --agent) agent=$2; shift 2;; --level) level=$2; shift 2;; --slowdown) slowdown=$2; shift 2;;
    --seed) seed=$2; shift 2;; --tag) tag=$2; shift 2;; *) echo "unknown argument $1" >&2; exit 2;;
  esac
done
[ -n "$agent" ] && [ -n "$level" ] || { sed -n 2,3p "$0" >&2; exit 2; }
if [ -z "$seed" ]; then
  case $task in tabletennis-*) seed=$((level * 101));; *) echo "--seed is required for $task" >&2; exit 2;; esac
fi
repo=$(cd "$(dirname "$0")/../.." && pwd)
cd "$repo"
export PYTHONPATH=$repo     # harbor_agents/ (the metering adapters)
# Harbor with multi-seat support (docs/benchmarks/olympiad.md):
#   uv tool install git+https://github.com/CHIGUI0/harbor@3fc74678123a2eb1845938b099e9d7856f2c6f6d
HARBOR=${HARBOR:-harbor}
export RCB_LEVEL=$level RCB_SEED=$seed
[ -z "$slowdown" ] || export RCB_SLOWDOWN=$slowdown     # real-time sports only
sport=${task%%-*}
task=tasks/$task
[ -d "$task" ] || { echo "no task $task" >&2; exit 2; }
job=$tag-$sport-$agent-L$level${slowdown:+-x$slowdown}-s$seed-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p jobs
# The task has one Harbor seat (A, service `main`): the agent is installed with internet, then plays offline.
# With a second Claude subscription configured (CLAUDE_CODE_OAUTH_TOKEN_2 in .env, and .env.acct2), Opus runs on it by
# default and Fable on the first (the second account has no Fable allowance).
if [ -z "${OPUS_ACCOUNT:-}" ] && [ -f .env.acct2 ] && grep -q '^CLAUDE_CODE_OAUTH_TOKEN_2=.' .env 2>/dev/null; then OPUS_ACCOUNT=2; fi
claude() {   # claude <model> <account 1|2>: account 2 runs from .env.acct2 (.env with CLAUDE_CODE_OAUTH_TOKEN_2's token)
  envf=.env; [ "$2" = 2 ] && envf=.env.acct2
  RCB_PLAYER_MODE=model RCB_RENDER_VIDEO=${RCB_RENDER_VIDEO:-1} $HARBOR run -p $task \
    --seat A=harbor_agents.claude_think:ClaudeThink@anthropic/$1 --seat-kwarg A:version=2.1.284 \
    --env-file $envf -k 1 -n 1 -r 0 -o jobs --job-name $job
}
codex() {   # codex <route azure|openrouter> <openrouter-style model>
  RCB_PLAYER_MODE=model THINK_OPENAI_ROUTE=$1 RCB_RENDER_VIDEO=${RCB_RENDER_VIDEO:-1} \
    AZURE_DEPLOYMENTS=${AZURE_DEPLOYMENTS:-gpt-6-astra,gpt-6-astra-2,gpt-6-astra-3} $HARBOR run -p $task \
    --seat A=harbor_agents.codex_openrouter:CodexOpenRouter@$2 \
    --seat-kwarg A:version=0.158.0 --seat-kwarg A:reasoning_effort=medium \
    --env-file .env -k 1 -n 1 -r 0 -o jobs --job-name $job
}
case $agent in
  opus)  claude claude-opus-5-5 ${OPUS_ACCOUNT:-1} ;;
  fable) claude claude-fable-5-1 ${FABLE_ACCOUNT:-1} ;;
  astra) codex azure openrouter/openai/gpt-6-astra ;;
  luna)  codex openrouter openrouter/openai/gpt-6-luna ;;
  oracle|nop)
    RCB_PLAYER_MODE=oracle RCB_RENDER_VIDEO=${RCB_RENDER_VIDEO:-0} $HARBOR run -p $task --seat A=$agent \
      -k 1 -n 1 -r 0 -o jobs --job-name $job ;;
  *) echo "agent must be opus, fable, astra, luna, oracle or nop" >&2; exit 2;;
esac > jobs/$job.log 2>&1
r=$(ls jobs/$job/*/verifier/reward.json 2>/dev/null | head -1 || true)
echo "$job: $( [ -n "$r" ] && python3 -c "import json,sys;print(json.load(open(sys.argv[1])))" "$r" || echo NO-REWARD)"
