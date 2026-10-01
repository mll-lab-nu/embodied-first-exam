#!/usr/bin/env bash
# Run one Harbor-native agent over tasks in both modes (<base>-privileged and <base>-standard), unattended; meant to be
# started in the background (inside `sg docker -c` if docker needs the group):
#   scripts/run_agent_batch.sh <batch-name> <base> [<base> ...]      # <base> = a task name without its -privileged / -standard
# Official runs use Harbor's native agents only (PROTOCOL D11): no gateway, no adapter. Env (defaults):
#   AGENT        codex | claude-code (codex)        MODEL   the -m model (openai/gpt-6-luna)
#   EFFORT       reasoning effort, --ak reasoning_effort=<EFFORT> (xhigh); `default` passes none
#   AK           more agent options, e.g. "--ak web_search=disabled --ak reasoning_summary=detailed"
#   AGENT_CONFIG a native config file, --ak config=<file>: Codex's config.toml (an Azure provider; retries with
#                request_max_retries / stream_max_retries) or Claude Code's settings
#   ENV_FILE     a .env file Harbor loads (--env-file); without it the credentials come from this environment
#   Credentials, as Harbor's agents read them (docs/RUNNING.md):
#     OpenRouter   codex: OPENAI_API_KEY=<openrouter key> OPENAI_BASE_URL=https://openrouter.ai/api/v1
#                  claude-code: ANTHROPIC_API_KEY=<openrouter key> ANTHROPIC_BASE_URL=https://openrouter.ai/api
#     ChatGPT login (codex)          CODEX_FORCE_AUTH_JSON=1 (Harbor uploads ~/.codex/auth.json into each trial)
#     Claude subscription            CLAUDE_FORCE_OAUTH=1 and CLAUDE_CODE_OAUTH_TOKEN (`claude setup-token`)
#     Azure OpenAI (codex)           AGENT_CONFIG=<config.toml with the Azure provider> and its key variable
#   MODES        "privileged standard"   K  attempts per task (1)
#   SEQ          1 = one trial at a time per runner (default): task by task, each mode in MODES order, one Harbor job per
#                task and mode ($JOBS/<batch>-<mode>-<task>/). Start the same command again to add a lane: every job is
#                claimed (mkdir $JOBS/.claims/<job>) by exactly one runner, so K runners run K trials at a time. A job that
#                already has its result.json (Harbor writes it when the job starts) is skipped; to rerun an interrupted
#                job, move its directory and its claim away first.
#                0 = one job per mode ($JOBS/<batch>-<mode>/), the modes side by side, N_P / N_S concurrent trials (2 / 2)
#   WAIT_FOR     a file that must exist before a mode starts, e.g. "standard:<path>" (default: none)
#   JOBS         <repo>/jobs/agents     LABEL  the run's title for the results README
#   RUN_ID       the run id (PROTOCOL D4, docs/TAXONOMY.md): <harness>-<model>-<effort>, derived from AGENT / MODEL /
#                EFFORT, e.g. codex-gpt6_luna-xhigh. Provider, service tier and settings go in metadata, never in the id.
#   RESULTS      a directory OUTSIDE the repository: after each job scripts/write_task_results.py writes the per-task results
#                for the results site there, <RESULTS>/<batch>/<task>/<RUN_ID>/ (PROTOCOL D3: no results in the repository);
#                default <repo>/../rcb_results; "" = skip
#   LOG_MIRROR / MEM_GUARD   1 (default) = start the agent-record mirror / the memory guard below if none runs; 0 = not
# Runner-side tools (not task code): while trials run, the container rcb-log-mirror copies every trial's agent/ directory
# append-only into ${JOBS}_mirror/ (scripts/log_mirror.py; root-owned: neither the agent nor the host user can delete it),
# and scripts/mem_guard.py keeps 2 GiB of host memory available. After each job: a key scan with redaction
# (scripts/scan_secrets.py), the task results, the summary table $JOBS/<batch>.summary.md, and a lane stop on structured
# model-account failures (scripts/account_failure_check.py). Progress: $JOBS/<batch>.log.
set -u
R="$(cd "$(dirname "$0")/.." && pwd)"
[ $# -ge 2 ] || { sed -n 2,40p "$0"; exit 2; }
batch="$1"; shift; tasks=("$@")
AGENT="${AGENT:-codex}"; MODEL="${MODEL:-openai/gpt-6-luna}"; EFFORT="${EFFORT:-xhigh}"; AK="${AK:-}"
AGENT_CONFIG="${AGENT_CONFIG:-}"; ENV_FILE="${ENV_FILE:-}"
MODES="${MODES:-privileged standard}"; SEQ="${SEQ:-1}"; N_P="${N_P:-2}"; N_S="${N_S:-2}"; K="${K:-1}"; WAIT_FOR="${WAIT_FOR:-}"
JOBS="${JOBS:-$R/jobs/agents}"; RESULTS="${RESULTS-$(dirname "$R")/rcb_results}"; LABEL="${LABEL:-$AGENT + $MODEL ($EFFORT)}"
LOG_MIRROR="${LOG_MIRROR:-1}"; MEM_GUARD="${MEM_GUARD:-1}"
case "$AGENT" in codex|claude-code) ;; *) echo "AGENT must be a Harbor native agent: codex or claude-code (PROTOCOL D11)" >&2; exit 2 ;; esac
# Run id (D4): harness = the agent name with - -> _; model = MODEL's last path segment, lower case, gpt-<n> joined
# (gpt-6-luna -> gpt6_luna), a leading claude- dropped (claude-fable-5-1 -> fable_5_1), every other
# character outside [a-z0-9] -> _; effort as given ("default" when the harness sets none).
if [ -z "${RUN_ID:-}" ]; then
  f() { tr 'A-Z' 'a-z' | sed -E 's/[^a-z0-9]+/_/g; s/^_+|_+$//g'; }
  harness=$(printf '%s' "$AGENT" | f)
  model=$(printf '%s' "${MODEL##*/}" | tr 'A-Z' 'a-z' | sed -E 's/^claude-//; s/^gpt-([0-9]+)/gpt\1/' | f)
  RUN_ID="$harness-$model-$(printf '%s' "$EFFORT" | f)"
fi
[[ "$RUN_ID" =~ ^[a-z0-9_]+-[a-z0-9_]+-(none|minimal|low|medium|high|xhigh|max|default)$ ]] || { echo "run id $RUN_ID is not <harness>-<model>-<effort>" >&2; exit 2; }
AGENT_ARGS=(-a "$AGENT" -m "$MODEL")
[ "$EFFORT" != default ] && AGENT_ARGS+=(--ak "reasoning_effort=$EFFORT")
[ -n "$AGENT_CONFIG" ] && AGENT_ARGS+=(--ak "config=$AGENT_CONFIG")
# shellcheck disable=SC2206
AGENT_ARGS+=($AK)
SCAN=(); [ -n "$ENV_FILE" ] && SCAN+=(--env-file "$ENV_FILE")
case "${CODEX_FORCE_AUTH_JSON:-}" in 1|true|TRUE|yes) SCAN+=(--codex-auth "${CODEX_AUTH_JSON_PATH:-$HOME/.codex/auth.json}") ;; esac
# Append, so a harbor already on PATH wins (a shared account's ~/.local/bin may hold another user's older harbor);
# hosts that keep harbor only in ~/.local/bin still find it.
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$PATH:$HOME/.local/bin" ;; esac
mkdir -p "$JOBS"
LOG="$JOBS/$batch.log"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
if [ -n "$ENV_FILE" ] && [ ! -f "$ENV_FILE" ]; then log "no env file $ENV_FILE"; exit 2; fi
log "runner $$: $AGENT $MODEL effort $EFFORT, run id $RUN_ID, modes $MODES"

# append-only mirror of every trial's agent/ directory, out of every trial container's reach
if [ "$LOG_MIRROR" = 1 ] && ! docker ps --format '{{.Names}}' | grep -qx rcb-log-mirror; then
  docker rm -f rcb-log-mirror >/dev/null 2>&1
  docker run -d --name rcb-log-mirror --restart unless-stopped --network none -v "$R/scripts:/s:ro" -v "$JOBS:/src:ro" \
    -v "${JOBS}_mirror:/mirror" python:3.12-slim python3 /s/log_mirror.py --src /src --mirror /mirror --interval 5 >/dev/null \
    && log "started rcb-log-mirror ($JOBS -> ${JOBS}_mirror)" || log "WARNING: could not start rcb-log-mirror"
fi

# host memory red line: scripts/mem_guard.py keeps 2 GiB available (the largest benchmark container is killed first)
pid="$(cat "$R/jobs/journal/mem_guard.pid" 2>/dev/null)"
if [ "$MEM_GUARD" = 1 ] && ! grep -qs mem_guard.py "/proc/${pid:-0}/cmdline"; then
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

finish_job() {  # <job>: no key in any saved file (+redact); the task results (D3)
  [ -d "$JOBS/$1" ] || return 0
  python3 "$R/scripts/scan_secrets.py" "$JOBS/$1" "${SCAN[@]}" --redact 2>&1 | tail -3 | sed "s/^/[$1] /" | tee -a "$LOG"
  [ -n "$RESULTS" ] && python3 "$R/scripts/write_task_results.py" "$JOBS" "$1" "$RUN_ID" "$LABEL" --out "$RESULTS/$batch" 2>&1 | tail -3 | sed "s/^/[$1] /" | tee -a "$LOG"
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
    mode = "standard" if task.endswith(("-standard", "-limited")) else "privileged"
    keys = {k: rw[k] for k in ("deterministic", "live_success", "replay_success", "instance_ok", "missing_trajectory", "grader_error",
                               "infra_error", "resumes") if k in rw}
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
  # build one task's image with ANOTHER task's equal-size file (instance.json, target.png, test.sh). A fresh ns mtime per task
  # dir makes every such file differ. git ignores mtimes.
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
  local envf=(); [ -n "$ENV_FILE" ] && envf=(--env-file "$ENV_FILE")
  stamp_task_dirs "$@"
  log "start $job: $* (concurrency $n, attempts $K)"
  (cd "$R" && harbor run -p tasks "$@" "${AGENT_ARGS[@]}" "${envf[@]}" -n "$n" -k "$K" -y -o "$JOBS" --job-name "$job") > "$JOBS/$job.harbor.log" 2>&1
  log "done $job (harbor rc=$?)"
}

name() {  # <mode> <base> -> task dir name: <base>-privileged / <base>-standard (PROTOCOL §2.2)
  case "$1" in
    standard|limited) echo "$2-standard" ;;
    *) echo "$2-privileged" ;;
  esac
}

if [ "$SEQ" = 1 ]; then
  mkdir -p "$JOBS/.claims"
  for t in "${tasks[@]}"; do
    for m in $MODES; do
      job="$batch-$m-$t"
      if [ ! -d "$R/tasks/$(name "$m" "$t")" ]; then log "skip $job (no task dir $(name "$m" "$t"))"; continue; fi
      if [ -f "$JOBS/$job/result.json" ]; then log "skip $job (already has result.json)"; continue; fi
      mkdir "$JOBS/.claims/$job" 2>/dev/null || continue   # another lane of this batch took it
      wait_for "$m"
      run_job "$job" 1 -i "$(name "$m" "$t")"
      finish_job "$job"; summary
      # the model account is out of credits, rate-limited or logged out: every further job would fail within minutes. Only
      # structured evidence counts (Codex's rate_limits and last event, Claude Code's result event): scripts/account_failure_check.py
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
    inc=(); for t in "${tasks[@]}"; do [ -d "$R/tasks/$(name "$m" "$t")" ] && inc+=(-i "$(name "$m" "$t")"); done
    [ ${#inc[@]} -eq 0 ] && continue
    n="$N_P"; case "$m" in standard|limited) n="$N_S" ;; esac
    (wait_for "$m"; run_job "$batch-$m" "$n" "${inc[@]}") &
    pids+=($!)
  done
  wait "${pids[@]}"
  for m in $MODES; do finish_job "$batch-$m"; done
fi
[ -d "${JOBS}_mirror" ] && python3 "$R/scripts/scan_secrets.py" "${JOBS}_mirror" "${SCAN[@]}" 2>&1 | tail -2 | sed "s/^/[mirror] /" | tee -a "$LOG"
summary
log "summary: $JOBS/$batch.summary.md"
cat "$JOBS/$batch.summary.md" | tee -a "$LOG" >/dev/null
log "runner $$ of batch $batch finished (no unclaimed job left)"
