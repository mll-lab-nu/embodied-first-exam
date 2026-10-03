#!/bin/bash
# Run one configuration of a two-player Olympiad task (default tasks/tabletennis-duel-wallclock-program-standard).
#   run_duel.sh [--task NAME] --a opus|fable|astra|luna|oracle --b opus|fable|astra|luna|oracle [--slowdown S] [--seed N] [--first A|B] [--tag TAG]
# Players as in run_single.sh: opus and fable (Claude Code 2.1.284, subscription), astra (Codex 0.158.0, medium, Azure
# with failover; its route is set for its seat only) and luna (Codex 0.158.0, medium, OpenRouter).
# Job: jobs/<tag>-duel-x<S>-s<seed>-<a>A-<b>B-<UTC time>.
set -euo pipefail
task=tabletennis-duel-wallclock-program-standard a= b= slowdown= seed=1 first=A tag=tt
while [ $# -gt 0 ]; do
  case $1 in
    --task) task=$2; shift 2;; --a) a=$2; shift 2;; --b) b=$2; shift 2;; --slowdown) slowdown=$2; shift 2;; --seed) seed=$2; shift 2;;
    --first) first=$2; shift 2;; --tag) tag=$2; shift 2;; *) echo "unknown argument $1" >&2; exit 2;;
  esac
done
[ -n "$a" ] && [ -n "$b" ] || { sed -n 2,3p "$0" >&2; exit 2; }
repo=$(cd "$(dirname "$0")/../.." && pwd)
cd "$repo"
export PYTHONPATH=$repo     # harbor_agents/ (the metering adapters)
# Harbor with multi-seat support (docs/benchmarks/olympiad.md):
#   uv tool install git+https://github.com/CHIGUI0/harbor@3fc74678123a2eb1845938b099e9d7856f2c6f6d
HARBOR=${HARBOR:-harbor}
export DUEL_SEED=$seed FIRST_RECEIVER=$first FIRST_PLAYER=$first THINK_OPENAI_ROUTE=azure
[ -z "$slowdown" ] || export RCB_SLOWDOWN=$slowdown     # real-time sports only
export AZURE_DEPLOYMENTS=${AZURE_DEPLOYMENTS:-gpt-6-astra,gpt-6-astra-2,gpt-6-astra-3} RCB_RENDER_VIDEO=${RCB_RENDER_VIDEO:-1}
seat() {   # seat <A|B> <agent>: the harbor --seat/--seat-kwarg arguments
  case $2 in
    opus)   echo "--seat $1=harbor_agents.claude_think:ClaudeThink@anthropic/claude-opus-5-5 --seat-kwarg $1:version=2.1.284";;
    fable)  echo "--seat $1=harbor_agents.claude_think:ClaudeThink@anthropic/claude-fable-5-1 --seat-kwarg $1:version=2.1.284";;
    astra)  echo "--seat $1=harbor_agents.codex_openrouter:CodexOpenRouter@openrouter/openai/gpt-6-astra --seat-kwarg $1:version=0.158.0 --seat-kwarg $1:reasoning_effort=medium";;
    luna)   echo "--seat $1=harbor_agents.codex_openrouter:CodexOpenRouter@openrouter/openai/gpt-6-luna --seat-kwarg $1:version=0.158.0 --seat-kwarg $1:reasoning_effort=medium";;
    oracle) echo "--seat $1=oracle";;
    *) echo "agent must be opus, fable, astra, luna or oracle" >&2; exit 2;;
  esac
}
route() { [ "$1" = astra ] && echo azure || echo openrouter; }   # each seat's route for OpenAI-style (Codex) calls
export THINK_OPENAI_ROUTE_A=$(route $a) THINK_OPENAI_ROUTE_B=$(route $b)
# With a second Claude subscription configured (CLAUDE_CODE_OAUTH_TOKEN_2 in .env, and .env.acct2), Opus runs on it by
# default and Fable on the first (the second account has no Fable allowance).
if [ -z "${OPUS_ACCOUNT:-}" ] && [ -f .env.acct2 ] && grep -q '^CLAUDE_CODE_OAUTH_TOKEN_2=.' .env 2>/dev/null; then OPUS_ACCOUNT=2; fi
# Claude subscription per seat: OPUS_ACCOUNT / FABLE_ACCOUNT (1 = CLAUDE_CODE_OAUTH_TOKEN, 2 = CLAUDE_CODE_OAUTH_TOKEN_2)
account() { case $1 in opus) echo ${OPUS_ACCOUNT:-1};; fable) echo ${FABLE_ACCOUNT:-1};; *) echo 1;; esac; }
export CLAUDE_ACCOUNT_A=$(account $a) CLAUDE_ACCOUNT_B=$(account $b)
mode() { [ "$1" = oracle ] && echo oracle || echo model; }
export PLAYER_MODE_A=$(mode $a) PLAYER_MODE_B=$(mode $b)
job=$tag-${task%%-*}-duel${slowdown:+-x$slowdown}-s$seed-${a}A-${b}B-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p jobs
# shellcheck disable=SC2046
[ -d tasks/$task ] || { echo "no task tasks/$task" >&2; exit 2; }
$HARBOR run -p tasks/$task $(seat A $a) $(seat B $b) \
  --env-file .env -n 1 -k 1 -r 0 -o jobs --job-name $job > jobs/$job.log 2>&1
r=$(ls jobs/$job/*/verifier/reward.json 2>/dev/null | head -1 || true)
echo "$job: $( [ -n "$r" ] && python3 -c "import json,sys;print(json.load(open(sys.argv[1])))" "$r" || echo NO-REWARD)"
