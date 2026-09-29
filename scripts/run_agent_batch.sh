#!/usr/bin/env bash
# Run one agent over tasks in both modes (each task + its -limited twin), unattended; meant to be started in the
# background (run it inside `sg docker -c` if docker needs the group):
#   scripts/run_agent_batch.sh <batch-name> <task> [<task> ...]
# Env (defaults):
#   AGENT     harbor_agents.codex_openrouter:CodexOpenRouter      MODEL  openrouter/openai/gpt-6-luna
#   AK        "--ak reasoning_effort=medium --ak provider_only=openai/flex"
#   ENV_FILE  <repo>/../.env (holds OPENROUTER_API_KEY; only Harbor and scan_secrets.py read it)
#   SCAN_ARGS extra scan_secrets.py arguments, e.g. "--env-file ../.env --var OPENROUTER_API_KEY --codex-auth ~/.codex/auth.json"
#             Codex on the user's ChatGPT login instead of OpenRouter: AGENT=codex MODEL=openai/gpt-6-luna
#             AK="--ak reasoning_effort=medium --ak web_search=disabled", ENV_FILE = a file holding only
#             CODEX_FORCE_AUTH_JSON=1 (Harbor then uploads ~/.codex/auth.json into each trial), SCAN_ARGS as above
#   MODES     "unlimited limited"   K  attempts per task (1)
#   SEQ       1 = one trial at a time per runner (default): task by task, each mode in MODES order, one Harbor job per task
#             and mode ($JOBS/<batch>-<mode>-<task>/). Start the same command again to add a lane: every job is claimed
#             (mkdir $JOBS/.claims/<job>) by exactly one runner, so K runners run K trials at a time. A job that already
#             has its result.json (Harbor writes it when the job starts) is skipped; to rerun an interrupted job, move its
#             directory and its claim away first.
#             0 = one job per mode ($JOBS/<batch>-<mode>/), the modes side by side, N_U / N_L concurrent trials (2 / 2)
#   WAIT_FOR  a file that must exist before a mode starts, e.g. "limited:<path>" (default: none)
#   JOBS      <repo>/jobs/agents     RESULTS  <repo>/jobs/results     LABEL  the run's title
#   SLUG      the run ID, also the per-agent results folder: <harness>-<model>-<effort>[-<tag>], by default derived from
#             AGENT / MODEL / AK (e.g. codex-gpt6_luna-xhigh); TAG adds -<tag> (only to tell two runs of one triple apart)
# The full record of every trial stays in its Harbor job dir under $JOBS (agent/ = the harness stream, its
# sessions, the model gateway's log of every raw exchange with usage and billed cost; artifacts/; verifier/). While
# trials run, the container rcb-log-mirror copies every agent/ directory append-only into ${JOBS}_mirror/ (root-owned:
# neither the agent nor the host user can delete it), and scripts/mem_guard.py keeps 2 GiB of host memory available.
# After each job: key scan (+redact), per-task results (scripts/write_task_results.py) in $RESULTS/<batch>/<task>/<SLUG>/
# (never in tasks/: run results are published on the site and the HF dataset, not committed), and the summary table
# $JOBS/<batch>.summary.md. Progress: $JOBS/<batch>.log.
set -u
R="$(cd "$(dirname "$0")/.." && pwd)"
[ $# -ge 2 ] || { sed -n 2,30p "$0"; exit 2; }
batch="$1"; shift; tasks=("$@")
AGENT="${AGENT:-harbor_agents.codex_openrouter:CodexOpenRouter}"; MODEL="${MODEL:-openrouter/openai/gpt-6-luna}"
AK="${AK:---ak reasoning_effort=medium --ak provider_only=openai/flex}"; ENV_FILE="${ENV_FILE:-$(dirname "$R")/.env}"
MODES="${MODES:-unlimited limited}"; SEQ="${SEQ:-1}"; SCAN_ARGS="${SCAN_ARGS:-}"; N_U="${N_U:-2}"; N_L="${N_L:-2}"; K="${K:-1}"; WAIT_FOR="${WAIT_FOR:-}"
JOBS="${JOBS:-$R/jobs/agents}"; RESULTS="${RESULTS:-$R/jobs/results}"; LABEL="${LABEL:-Codex CLI + GPT-6 Luna (OpenRouter, openai/flex)}"
# The run ID convention of the site and the HF dataset (user 2026-09-28): <harness>-<model>-<effort>[-<tag>], fields
# [a-z0-9_]+. harness: codex for every Codex agent; model: MODEL's last path segment, lowercased, a leading
# <letters>-<digits> joined (gpt-6 -> gpt6), every other - or . -> _; effort: AK's reasoning_effort, else "default";
# tag: TAG, when set. An explicit SLUG overrides it.
if [ -z "${SLUG:-}" ]; then
  f() { tr 'A-Z' 'a-z' | sed -E 's/[^a-z0-9_]/_/g'; }
  harness=$(printf '%s' "${AGENT##*[.:]}" | f); case "$harness" in *codex*) harness=codex ;; esac
  model=$(printf '%s' "${MODEL##*/}" | tr 'A-Z' 'a-z' | sed -E 's/^([a-z]+)-([0-9]+)/\1\2/' | f)
  effort=$(printf '%s' "$AK" | grep -o 'reasoning_effort=[A-Za-z]*' | tail -1 | cut -d= -f2 | f)
  SLUG="$harness-$model-${effort:-default}${TAG:+-$(printf '%s' "$TAG" | f)}"
fi
# Append, so a harbor already on PATH wins (lab, 2026-09-26: the shared account's ~/.local/bin has another
# user's harbor 0.1.44, which lacks -i); hosts that keep harbor only in ~/.local/bin still find it.
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$PATH:$HOME/.local/bin" ;; esac
mkdir -p "$JOBS"
LOG="$JOBS/$batch.log"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
[ -f "$ENV_FILE" ] || { log "no env file $ENV_FILE"; exit 2; }

# append-only mirror of every trial's agent/ directory, out of every trial container's reach
if ! docker ps --format '{{.Names}}' | grep -qx rcb-log-mirror; then
  docker rm -f rcb-log-mirror >/dev/null 2>&1
  docker run -d --name rcb-log-mirror --restart unless-stopped --network none -v "$R/scripts:/s:ro" -v "$JOBS:/src:ro" \
    -v "${JOBS}_mirror:/mirror" python:3.12-slim python3 /s/log_mirror.py --src /src --mirror /mirror --interval 5 >/dev/null \
    && log "started rcb-log-mirror ($JOBS -> ${JOBS}_mirror)" || log "WARNING: could not start rcb-log-mirror"
fi

# host memory red line: scripts/mem_guard.py keeps 2 GiB available (the largest benchmark container is killed first)
pid="$(cat "$R/jobs/journal/mem_guard.pid" 2>/dev/null)"
if ! grep -qs mem_guard.py "/proc/${pid:-0}/cmdline"; then
  setsid nohup python3 "$R/scripts/mem_guard.py" >/dev/null 2>&1 </dev/null &
  log "started mem_guard (2 GiB red line; log jobs/journal/mem_guard.log)"
fi

wait_for() {  # <mode>: block until every WAIT_FOR file of this mode exists
  local w
  for w in $WAIT_FOR; do
    if [ "${w%%:*}" = "$1" ]; then
      log "$1 waits for ${w#*:}"
      until [ -e "${w#*:}" ]; do sleep 30; done
    fi
  done
}

finish_job() {  # <job>: no key in any saved file (+redact); per-task results in Kangrui's format
  [ -d "$JOBS/$1" ] || return 0
  python3 "$R/scripts/scan_secrets.py" "$JOBS/$1" --env-file "$ENV_FILE" $SCAN_ARGS --redact 2>&1 | tail -3 | sed "s/^/[$1] /" | tee -a "$LOG"
  python3 "$R/scripts/write_task_results.py" "$JOBS" "$1" "$SLUG" "$LABEL" --out "$RESULTS/$batch" 2>&1 | tail -3 | sed "s/^/[$1] /" | tee -a "$LOG"
}

summary() {  # one table over every job of this batch, rewritten after each job (atomically: lanes share it)
  python3 - "$JOBS" "$batch" > "$JOBS/$batch.summary.md.$$" <<'PY'
import json, pathlib, sys, datetime as dt
jobs, batch = pathlib.Path(sys.argv[1]), sys.argv[2]
print(f"# {batch}\n\n| task | mode | success | reward fields | actions | agent wall s | input tok | cached | output tok | cost $ | exception |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
f = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
rows = []
for trial in jobs.glob(f"{batch}-*/*__*"):
    if not trial.is_dir():
        continue
    r = json.loads((trial / "result.json").read_text()) if (trial / "result.json").exists() else {}
    rw = json.loads((trial / "verifier/reward.json").read_text()) if (trial / "verifier/reward.json").exists() else {}
    ar = r.get("agent_result") or {}; ex = (r.get("exception_info") or {}).get("exception_type") or ""
    ae = r.get("agent_execution") or {}
    try:
        wall = round((f(ae["finished_at"]) - f(ae["started_at"])).total_seconds())
    except Exception:
        wall = ""
    task = (r.get("task_name") or trial.name.split("__")[0]).split("/")[-1]
    mode = "limited" if task.endswith("-limited") else "unlimited"
    keys = {k: rw[k] for k in ("deterministic", "live_success", "replay_success", "instance_ok", "missing_trajectory", "grader_error") if k in rw}
    rows.append((r.get("started_at") or "~", f"| {task} | {mode} | {rw.get('success', '-')} | {json.dumps(keys)} | "
                 f"{rw.get('n_actions', '-')} | {wall} | {ar.get('n_input_tokens', '-')} | {ar.get('n_cache_tokens', '-')} | "
                 f"{ar.get('n_output_tokens', '-')} | {round(ar['cost_usd'], 4) if ar.get('cost_usd') is not None else '-'} | {ex} |"))
for _, row in sorted(rows):
    print(row)
PY
  mv -f "$JOBS/$batch.summary.md.$$" "$JOBS/$batch.summary.md"
}

stamp_task_dirs() {  # <harbor -i args...>: give every file of each task dir about to be built its own fresh nanosecond mtime
  # BuildKit keeps one shared snapshot per build-context NAME (Harbor's are always "environment" and "tests") and re-sends a file
  # only when its name, size, mode or mtime changed; copies with whole-second mtimes (tar, rsync of a tar copy) can therefore
  # build one task's image with ANOTHER task's equal-size file (instance.json, target.png, test.sh). Found by agent V on ws3,
  # 2026-09-28 (validate/NOTES.md 04:52). A fresh ns mtime per task dir makes every such file differ. git ignores mtimes.
  local a ts
  while [ $# -gt 0 ]; do
    a="$1"; shift
    if [ "$a" = -i ] && [ $# -gt 0 ]; then
      ts="$(date +%s.%N)"
      [ -d "$R/tasks/$1" ] && find "$R/tasks/$1" -exec touch -h -m -d "@$ts" {} +
      shift
    fi
  done
}

run_job() {  # <job> <concurrency> <harbor -i args...>
  local job="$1" n="$2"; shift 2
  stamp_task_dirs "$@"
  log "start $job: $* (concurrency $n, attempts $K)"
  (cd "$R" && PYTHONPATH="$R" harbor run -p tasks "$@" -a "$AGENT" -m "$MODEL" --env-file "$ENV_FILE" $AK \
     -n "$n" -k "$K" -y -o "$JOBS" --job-name "$job") > "$JOBS/$job.harbor.log" 2>&1
  log "done $job (harbor rc=$?)"
}

name() { if [ "$1" = limited ]; then echo "$2-limited"; else echo "$2"; fi; }  # <mode> <task> -> task dir name

if [ "$SEQ" = 1 ]; then
  mkdir -p "$JOBS/.claims"
  for t in "${tasks[@]}"; do
    for m in $MODES; do
      job="$batch-$m-$t"
      if [ -f "$JOBS/$job/result.json" ]; then log "skip $job (already has result.json)"; continue; fi
      mkdir "$JOBS/.claims/$job" 2>/dev/null || continue   # another lane of this batch took it
      wait_for "$m"
      run_job "$job" 1 -i "$(name "$m" "$t")"
      finish_job "$job"; summary
      # the model account is out of credits, rate-limited or logged out: every further job would fail within minutes. Only
      # structured evidence counts (gateway HTTP statuses, Codex's rate_limits, Codex's last event): scripts/account_failure_check.py
      why=$(python3 "$R/scripts/account_failure_check.py" "$JOBS/$job"/*__*/ 2>&1); rc=$?
      if [ $rc -eq 4 ]; then
        log "STOP lane $$: $job hit a model-account or config failure ($(grep -m1 '"stop": true' <<< "$why" | cut -c1-300)); move its dir and claim aside to rerun it"; break 2
      elif [ $rc -ne 0 ]; then
        log "account check of $job failed (rc $rc): $(tail -1 <<< "$why" | cut -c1-200)"
      fi
    done
  done
else
  pids=()
  for m in $MODES; do
    inc=(); for t in "${tasks[@]}"; do inc+=(-i "$(name "$m" "$t")"); done
    n="$N_U"; [ "$m" = limited ] && n="$N_L"
    (wait_for "$m"; run_job "$batch-$m" "$n" "${inc[@]}") &
    pids+=($!)
  done
  wait "${pids[@]}"
  for m in $MODES; do finish_job "$batch-$m"; done
fi
[ -d "${JOBS}_mirror" ] && python3 "$R/scripts/scan_secrets.py" "${JOBS}_mirror" --env-file "$ENV_FILE" $SCAN_ARGS 2>&1 | tail -2 | sed "s/^/[mirror] /" | tee -a "$LOG"
summary
log "summary: $JOBS/$batch.summary.md"
cat "$JOBS/$batch.summary.md" | tee -a "$LOG" >/dev/null
log "runner $$ of batch $batch finished (no unclaimed job left)"
