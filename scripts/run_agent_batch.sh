#!/usr/bin/env bash
# Run one Harbor-native agent over tasks in both modes (<base>-privileged and <base>-standard), unattended; meant to be
# started in the background (inside `sg docker -c` if docker needs the group):
#   scripts/run_agent_batch.sh <batch-name> <base> [<base> ...]      # <base> = a task name without its -privileged / -standard
# Official runs use Harbor's native agents only (PROTOCOL D11): no adapter; the transparent usage gateway below only
# records and is off by default. Env (defaults):
#   AGENT        codex | claude-code (codex)        MODEL   the -m model (openai/gpt-6-luna)
#   EFFORT       reasoning effort, --ak reasoning_effort=<EFFORT> (xhigh); `default` passes none
#   AK           more agent options, e.g. "--ak reasoning_summary=detailed"
#   WEB_SEARCH   disabled (default) = the harness offers the model no web search: Codex --ak web_search=disabled,
#                Claude Code --ak disallowed_tools=WebSearch,WebFetch (PROTOCOL D11; the search runs at the model
#                provider, past any egress allowlist), and Codex none of the other tools that run there (a ChatGPT
#                login's connectors and apps, plugins, image generation: those features = false in a copy of
#                AGENT_CONFIG, scripts/codex_tools_off.py); "allowed" = leave the harness default (not for official runs)
#   AGENT_CONFIG a native config file, --ak config=<file>: Codex's config.toml (an Azure provider; retries with
#                request_max_retries / stream_max_retries) or Claude Code's settings
#   ENV_FILE     a .env file Harbor loads (--env-file); without it the credentials come from this environment
#   Credentials, as Harbor's agents read them (docs/protocol/running.md):
#     OpenRouter   codex: OPENAI_API_KEY=<openrouter key> OPENAI_BASE_URL=https://openrouter.ai/api/v1
#                  claude-code: ANTHROPIC_API_KEY=<openrouter key> ANTHROPIC_BASE_URL=https://openrouter.ai/api
#     ChatGPT login (codex)          CODEX_FORCE_AUTH_JSON=1 (Harbor uploads ~/.codex/auth.json into each trial)
#     Claude subscription            CLAUDE_FORCE_OAUTH=1 and CLAUDE_CODE_OAUTH_TOKEN (`claude setup-token`)
#     Azure OpenAI (codex)           AGENT_CONFIG=<config.toml with the Azure provider> and its key variable
#   MODES        "privileged standard"   K  attempts per task (1); add `standard-realtime` for <base>-standard-realtime where it exists
#   SEQ          1 = one trial at a time per runner (default): task by task, each mode in MODES order, one Harbor job per
#                task and mode ($JOBS/<batch>-<mode>-<task>/). Start the same command again to add a lane: every job is
#                claimed (mkdir $JOBS/.claims/<job>) by exactly one runner, so K runners run K trials at a time. A job that
#                already has its result.json (Harbor writes it when the job starts) is skipped; to rerun an interrupted
#                job, move its directory and its claim away first.
#                0 = one job per mode ($JOBS/<batch>-<mode>/), the modes side by side, N_P / N_S concurrent trials (2 / 2;
#                N_S also for standard-realtime)
#   WAIT_FOR     a file that must exist before a mode starts, e.g. "standard:<path>" (default: none)
#   JOBS         <repo>/jobs/agents     LABEL  the run's title for the results README
#   RUN_ID       the run id (PROTOCOL D4, docs/TAXONOMY.md): <harness>-<model>-<effort>, derived from AGENT / MODEL /
#                EFFORT, e.g. codex-gpt6_luna-xhigh. Provider, service tier and settings go in metadata, never in the id.
#   RESULTS      a directory OUTSIDE the repository: after each job scripts/write_task_results.py writes the per-task results
#                for the results site there, <RESULTS>/<batch>/<task>/<RUN_ID>/ (PROTOCOL D3: no results in the repository);
#                default <repo>/../rcb_results; "" = skip
#   HOST_CPUS    the host's CPU count (`nproc`): a task's CPU cap above it ([environment] / [verifier.environment] cpus,
#                a compose service's cpus) is clamped to it in the job's own copy of the task (below), as PROTOCOL §2.10
#                requires of a runner (docker refuses a larger cap); tasks/ keeps its values (scripts/clamp_cpus.py)
#   Every job runs from its own copy of its tasks ($JOBS/.tasks/<job>/, removed afterwards), every file's mtime derived
#   from its content (scripts/stamp_mtimes.py): Docker's BuildKit can otherwise build one task's image with another
#   task's equal-size, equal-mtime file (issue #258, docs/protocol/running.md "Building task images")
#   LOG_MIRROR / MEM_GUARD   1 (default) = start the agent-record mirror / the memory guard below if none runs; 0 = not
#   GATEWAY      0 (default) = the agent calls its API directly, as Harbor runs it; 1 = route the agent's model API
#                calls through scripts/usage_gateway/gateway.py, which forwards
#                them unchanged (the agent keeps its own credentials) and records each trial's tokens per request in
#                <trial>/gateway/ (usage.jsonl, totals.json). Before each job the runner checks that the gateway answers
#                (/_gateway/health) and restarts it on its port, or stops the lane; a job during which it died gets
#                <job>/gateway_down.json, and a trial whose last model calls failed at the gateway (upstream unreachable,
#                stream broken off, provider 5xx) is published as "not a result", never the agent's 0 (board 0121 M4)
#   GATEWAY_RAW  1 (default, takes effect with GATEWAY=1) = the gateway also keeps every request and response body
#                (<trial>/gateway/raw.jsonl.xz, deduplicated, see scripts/usage_gateway/rawlog.py; private: it holds the
#                whole conversation); 0 = token usage only
#                The gateway forwards model-API calls only (scripts/usage_gateway/api_paths.json) and answers anything
#                else at the provider 403 (account connectors, files, web tools; counted in totals.json refused_paths)
#   GATEWAY_EGRESS  gateway (default; takes effect with GATEWAY=1) = each job's copy of the task allows as egress only the gateway's address and the package registries (PyPI, apt), so the
#                agent's container reaches its provider through the gateway's model-API paths only. (Harbor's allowlist
#                names an address, not a port: every TCP service listening on that address of the host is reachable
#                from a trial, as it has been since the gateway exists. Bind host services to 127.0.0.1.)
#                (one exception: Codex with a ChatGPT login also keeps chatgpt.com, which its start-up lookup needs);
#                task = run tasks/ as it is (the task's allowlist: the model APIs' hosts stay reachable directly)
#   GATEWAY_BIND the docker bridge address the trial containers reach the host by (172.17.0.1)
#   GATEWAY_EXTRA_HOSTS  more model API host patterns the gateway forwards to, space-separated (e.g. "*.services.ai.azure.com");
#                a plain-HTTP base URL with a port (ANTHROPIC_BASE_URL / OPENAI_BASE_URL=http://<host>:<port>, a self-hosted
#                model server) is forwarded too, to exactly that <host>:<port>
#   GATEWAY_START_WAIT  seconds to wait for the gateway to come up (10); raise it on busy shared nodes
#   TOKEN_BUDGET_IN / TOKEN_BUDGET_OUT   per-trial token budget the gateway enforces (10000000000 / 10000000000, input
#                with cached input included; docs/protocol/running.md): past it every further model request is refused and the
#                trial counts as failed; 0 = no limit
# Runner-side tools (not task code): while trials run, the container rcb-log-mirror copies every trial's agent/ directory
# append-only into ${JOBS}_mirror/ (scripts/log_mirror.py; root-owned: neither the agent nor the host user can delete it),
# and scripts/mem_guard.py keeps 2 GiB of host memory available. After each job: a key scan with redaction
# (scripts/scan_secrets.py), the task results, the summary table $JOBS/<batch>.summary.md, and a lane stop on structured
# model-account failures (scripts/account_failure_check.py). Progress: $JOBS/<batch>.log; in a browser, every trial's
# state (pending / running / done) with scripts/live_board.py --jobs $JOBS.
set -u
R="$(cd "$(dirname "$0")/.." && pwd)"
[ $# -ge 2 ] || { sed -n 2,40p "$0"; exit 2; }
batch="$1"; shift; tasks=("$@")
AGENT="${AGENT:-codex}"; MODEL="${MODEL:-openai/gpt-6-luna}"; EFFORT="${EFFORT:-xhigh}"; AK="${AK:-}"
WEB_SEARCH="${WEB_SEARCH:-disabled}"
AGENT_CONFIG="${AGENT_CONFIG:-}"; ENV_FILE="${ENV_FILE:-}"
MODES="${MODES:-privileged standard}"; SEQ="${SEQ:-1}"; N_P="${N_P:-2}"; N_S="${N_S:-2}"; K="${K:-1}"; WAIT_FOR="${WAIT_FOR:-}"
JOBS="${JOBS:-$R/jobs/agents}"; RESULTS="${RESULTS-$(dirname "$R")/rcb_results}"; LABEL="${LABEL:-$AGENT + $MODEL ($EFFORT)}"
LOG_MIRROR="${LOG_MIRROR:-1}"; MEM_GUARD="${MEM_GUARD:-1}"
GATEWAY="${GATEWAY:-0}"; GATEWAY_RAW="${GATEWAY_RAW:-1}"; GATEWAY_BIND="${GATEWAY_BIND:-172.17.0.1}"; GATEWAY_START_WAIT="${GATEWAY_START_WAIT:-10}"
GATEWAY_EGRESS="${GATEWAY_EGRESS:-gateway}"
HOST_CPUS="${HOST_CPUS:-$(nproc)}"
[[ "$HOST_CPUS" =~ ^[1-9][0-9]*$ ]] || { echo "HOST_CPUS must be a positive integer (the host's CPU count)" >&2; exit 2; }
case "$GATEWAY_EGRESS" in gateway|task) ;; *) echo "GATEWAY_EGRESS must be gateway or task" >&2; exit 2 ;; esac
# absolute paths: with the gateway on, Harbor is started from the job's own copy of the task (run_job), not from the repository
abspath() { case "$1" in ""|/*) printf '%s' "$1" ;; *) printf '%s/%s' "$PWD" "$1" ;; esac; }
JOBS="$(abspath "$JOBS")"; ENV_FILE="$(abspath "$ENV_FILE")"; AGENT_CONFIG="$(abspath "$AGENT_CONFIG")"
[ -n "${RESULTS:-}" ] && RESULTS="$(abspath "$RESULTS")"
[ -n "${CODEX_AUTH_JSON_PATH:-}" ] && { CODEX_AUTH_JSON_PATH="$(abspath "$CODEX_AUTH_JSON_PATH")"; export CODEX_AUTH_JSON_PATH; }
TOKEN_BUDGET_IN="${TOKEN_BUDGET_IN:-10000000000}"; TOKEN_BUDGET_OUT="${TOKEN_BUDGET_OUT:-10000000000}"
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
# Codex's other provider-side tools go off with the web search (PROTOCOL D11). Under a ChatGPT login Codex hands the
# model the account's connectors and apps (mcp__codex_apps__*: GitHub fetch, a web search of their own, mail, drives),
# plugin installs and an image generator; they run at OpenAI, reached through chatgpt.com, so neither
# web_search=disabled nor an egress allowlist stops them. The run's config is a copy of AGENT_CONFIG (or an empty one)
# with those features = false; a config that turns one of them on is refused, never overridden silently.
# Harbor keeps the last --ak of a key: a config=... in AK would replace the one written here (and the gateway's copy)
case " $AK " in *[[:space:]]config=*) echo "AK must not carry config=...: name the file in AGENT_CONFIG" >&2; exit 2 ;; esac
if [ "$WEB_SEARCH" = disabled ] && [ "$AGENT" = codex ]; then
  mkdir -p "$JOBS/.agent-config" && cfg="$JOBS/.agent-config/config.toml.$$" \
    && python3 "$R/scripts/codex_tools_off.py" ${AGENT_CONFIG:+"$AGENT_CONFIG"} > "$cfg" && grep -q '^features\.apps = false$\|^apps = false$' "$cfg" \
    || { echo "no Codex config without provider-side tools could be written from AGENT_CONFIG=${AGENT_CONFIG:-(none)} (see above); WEB_SEARCH=disabled needs it" >&2; exit 2; }
  AGENT_CONFIG="$cfg"
fi
[ -n "$AGENT_CONFIG" ] && AGENT_ARGS+=(--ak "config=$AGENT_CONFIG")
# shellcheck disable=SC2206
AGENT_ARGS+=($AK)
# no harness web search unless asked for (PROTOCOL D11): it runs at the model provider, so no egress allowlist stops it
case "$WEB_SEARCH" in
  disabled) if [ "$AGENT" = codex ]; then AGENT_ARGS+=(--ak web_search=disabled)
            else AGENT_ARGS+=(--ak disallowed_tools=WebSearch,WebFetch); fi ;;
  allowed) ;;
  *) echo "WEB_SEARCH must be disabled or allowed" >&2; exit 2 ;;
esac
SCAN=(); [ -n "$ENV_FILE" ] && SCAN+=(--env-file "$ENV_FILE")
case "${CODEX_FORCE_AUTH_JSON:-}" in 1|true|TRUE|yes) SCAN+=(--codex-auth "${CODEX_AUTH_JSON_PATH:-$HOME/.codex/auth.json}") ;; esac
# Append, so a harbor already on PATH wins (a shared account's ~/.local/bin may hold another user's older harbor);
# hosts that keep harbor only in ~/.local/bin still find it.
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$PATH:$HOME/.local/bin" ;; esac
mkdir -p "$JOBS"
LOG="$JOBS/$batch.log"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
if [ -n "$ENV_FILE" ] && [ ! -f "$ENV_FILE" ]; then log "no env file $ENV_FILE"; exit 2; fi
log "runner $$: $AGENT $MODEL effort $EFFORT, run id $RUN_ID, modes $MODES, web search $WEB_SEARCH"
# the batch's plan, for scripts/live_board.py: every job this command runs, "pending" there until it starts
mkdir -p "$JOBS/.plan"
python3 - "$R" "$JOBS/.plan/$batch.json" "$batch" "$RUN_ID" "$SEQ" "$MODES" "${tasks[@]}" <<'PY'
import json, os, pathlib, sys
repo, out, batch, run_id, seq, modes, *tasks = sys.argv[1:]
name = lambda m, t: {"standard": f"{t}-standard", "limited": f"{t}-standard", "standard-realtime": f"{t}-standard-realtime"}.get(m, f"{t}-privileged")
jobs = [{"job": f"{batch}-{m}-{t}" if seq == "1" else f"{batch}-{m}", "task": name(m, t), "mode": m}
        for t in tasks for m in modes.split() if (pathlib.Path(repo) / "tasks" / name(m, t)).is_dir()]
tmp = pathlib.Path(f"{out}.{os.getpid()}")
tmp.write_text(json.dumps({"batch": batch, "run_id": run_id, "jobs": jobs}, indent=1))
tmp.replace(out)
PY

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

# job copies a killed runner left behind (run_job removes its own; never here on exit: Harbor may still be tearing a
# trial down from that directory, whose compose file and bind mounts it holds; a copy is at most 11 MB, and no job runs
# for a month)
[ -d "$JOBS/.tasks" ] && find "$JOBS/.tasks" -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} + 2>/dev/null

# transparent usage gateway (one per runner, stopped with it): the agent's base URL points at it, it forwards unchanged
if [ "$GATEWAY" = 1 ]; then
  mkdir -p "$JOBS/.gateway"; ready="$JOBS/.gateway/port.$$"; rm -f "$ready"
  # the upstream each base URL would have used: this environment, else the env file, else the API's default
  upstream() {  # <VAR> <default>
    local v="${!1:-}"
    [ -z "$v" ] && [ -n "$ENV_FILE" ] && v=$(sed -n "s/^[[:space:]]*\(export[[:space:]]\+\)\?$1=//p" "$ENV_FILE" | tail -1 | tr -d "\"'")
    printf '%s' "${v:-$2}"
  }
  gw_args=(--jobs "$JOBS" --bind "$GATEWAY_BIND" --ready-file "$ready" --budget-input "$TOKEN_BUDGET_IN" --budget-output "$TOKEN_BUDGET_OUT"); for h in ${GATEWAY_EXTRA_HOSTS:-}; do gw_args+=(--extra-host "$h"); done; [ "$GATEWAY_RAW" = 1 ] && gw_args+=(--raw)
  [ "$WEB_SEARCH" = allowed ] && gw_args+=(--server-tools record)   # not an official run: the provider-run tools are only recorded
  # a plain-HTTP base URL (a self-hosted model server, e.g. sglang): the gateway may forward to exactly that host:port
  [ "$AGENT" = claude-code ] && agent_up=$(upstream ANTHROPIC_BASE_URL https://api.anthropic.com) || agent_up=$(upstream OPENAI_BASE_URL https://api.openai.com/v1)
  [[ "$agent_up" =~ ^http://([A-Za-z0-9.-]+:[0-9]+)(/|$) ]] && gw_args+=(--http-host "${BASH_REMATCH[1]}")
  gw_start() {  # [port]: start the gateway (a restart: on the port the agent's base URLs already name); 0 = it listens
    rm -f "$ready"
    setsid python3 "$R/scripts/usage_gateway/gateway.py" "${gw_args[@]}" ${1:+--port "$1"} >>"$JOBS/.gateway/gateway.$$.err" 2>&1 </dev/null &
    gw_pid=$!
    local _; for _ in $(seq $((GATEWAY_START_WAIT * 5))); do [ -s "$ready" ] && return 0; kill -0 "$gw_pid" 2>/dev/null || return 1; sleep 0.2; done
    [ -s "$ready" ]
  }
  gw_alive() {  # the gateway process runs and answers its health check (board 0121 M4: it was started once, never checked)
    kill -0 "$gw_pid" 2>/dev/null && python3 -c 'import sys, urllib.request as u
u.build_opener(u.ProxyHandler({})).open(sys.argv[1], timeout=15).read()' "$GW/_gateway/health" 2>/dev/null
  }
  gw_pid=""; trap '[ -n "$gw_pid" ] && kill "$gw_pid" 2>/dev/null' EXIT
  gw_start
  [ -s "$ready" ] || { log "usage gateway did not start within ${GATEWAY_START_WAIT} s (see $JOBS/.gateway/gateway.$$.err); unset GATEWAY to run without it"; exit 2; }
  gw_port="$(cat "$ready")"; GW="http://$GATEWAY_BIND:$gw_port"
  gw_alive || { log "usage gateway $GW does not answer its health check (see $JOBS/.gateway/gateway.$$.err); not starting"; exit 2; }
  # https://host/path -> $GW/u/host/path; http://host:port/path -> $GW/h/host:port/path (`t`: one rewrite only)
  via_gw() { sed -E -e "s#^https://([^/]+)#$GW/u/\1#; t" -e "s#^http://([A-Za-z0-9.-]+:[0-9]+)#$GW/h/\1#" <<< "$1"; }
  if [ "$AGENT" = claude-code ]; then
    AGENT_ARGS+=(--ae "ANTHROPIC_BASE_URL=$(via_gw "$(upstream ANTHROPIC_BASE_URL https://api.anthropic.com)")")
  else
    case "${CODEX_FORCE_AUTH_JSON:-}" in
      1|true|TRUE|yes) AGENT_ARGS+=(--ae "OPENAI_BASE_URL=$(via_gw https://chatgpt.com/backend-api/codex)") ;;
      *) AGENT_ARGS+=(--ae "OPENAI_BASE_URL=$(via_gw "$(upstream OPENAI_BASE_URL https://api.openai.com/v1)")") ;;
    esac
  fi
  # a native config with its own provider URLs (Codex config.toml, Claude Code settings): a copy that points at the gateway
  if [ -n "$AGENT_CONFIG" ]; then
    cfg="$JOBS/.gateway/$(basename "$AGENT_CONFIG").$$"
    sed -E -e "s#^([[:space:]]*base_url[[:space:]]*=[[:space:]]*\")https://([^/\"]+)#\1$GW/u/\2#" \
           -e "s#(\"(ANTHROPIC|OPENAI)_BASE_URL\"[[:space:]]*:[[:space:]]*\")https://([^/\"]+)#\1$GW/u/\3#" "$AGENT_CONFIG" > "$cfg"
    # Codex reaches a provider by WebSocket first; the gateway speaks HTTPS only
    grep -q '^[[:space:]]*base_url[[:space:]]*=' "$cfg" && ! grep -q supports_websockets "$cfg" \
      && sed -i -E "s#^([[:space:]]*)(base_url[[:space:]]*=.*)#\1\2\n\1supports_websockets = false#" "$cfg"
    for i in "${!AGENT_ARGS[@]}"; do [ "${AGENT_ARGS[$i]}" = "config=$AGENT_CONFIG" ] && AGENT_ARGS[$i]="config=$cfg"; done
  fi
  # the egress allowlist must let the agent reach the gateway; with GATEWAY_EGRESS=gateway the list is the gateway's
  # address and the package registries (PyPI and the apt archives: installing packages is allowed, PROTOCOL §2.11), and
  # no model API's own host
  # (run_job: the job's own copy of the task; Harbor's --allow-agent-host can add a host to a task's list, not remove one)
  AGENT_ARGS+=(--allow-agent-host "$GATEWAY_BIND")
  GATEWAY_ONLY="$GATEWAY_BIND"
  # the tool that narrows a job's copy must work on this host before any job is claimed
  if [ "$GATEWAY_EGRESS" = gateway ]; then
    PACKAGE_HOSTS="$(python3 "$R/scripts/set_agent_egress.py" package-hosts 2>/dev/null)"
    GATEWAY_ONLY="$GATEWAY_BIND${PACKAGE_HOSTS:+,$PACKAGE_HOSTS}"      # PACKAGE_HOSTS may be empty: the gateway alone
    probe="$JOBS/.gateway/egress-probe.$$"; rm -rf "$probe"; [[ "$PACKAGE_HOSTS" =~ ^([A-Za-z0-9.-]+(,[A-Za-z0-9.-]+)*)?$ ]] \
      && mkdir -p "$probe/t" && printf '[agent]\ntimeout_sec = 1.0\n' > "$probe/t/task.toml" \
      && python3 "$R/scripts/set_agent_egress.py" only "$GATEWAY_ONLY" "$probe/t" >/dev/null \
      && grep -q "^allowed_hosts = \[\"${GATEWAY_ONLY//,/\", \"}\"\]\$" "$probe/t/task.toml" \
      || { log "scripts/set_agent_egress.py cannot write a gateway-only task copy on this host (python3: $(python3 -V 2>&1)); not starting"; rm -rf "$probe"; exit 2; }
    rm -rf "$probe"
  fi
  # The exception: Codex with a ChatGPT login. Before its first model call Codex 0.160.1 looks its account's workspace up
  # at chatgpt_base_url (GET /backend-api/wham/accounts/check), not at the model's base URL, and accepts only an HTTPS
  # origin there ("workspace backend must use an HTTPS origin"), which this plain-HTTP gateway is not. So chatgpt.com
  # itself stays reachable for such a run (that host alone: not *.chatgpt.com, auth.openai.com or api.openai.com), and
  # with it, directly, every path of that backend: the account's connectors are then off by the harness's configuration
  # only (docs/protocol/running.md). API-key and Claude Code runs have no such exception.
  case "$AGENT:${CODEX_FORCE_AUTH_JSON:-}" in codex:1|codex:true|codex:TRUE|codex:yes)
    GATEWAY_ONLY="$GATEWAY_ONLY,chatgpt.com"
    [ "$GATEWAY_EGRESS" = gateway ] && log "ChatGPT login: chatgpt.com stays directly reachable beside the gateway (Codex's workspace lookup needs it over HTTPS)" ;;
  esac
  log "usage gateway $GW (pid $gw_pid, raw bodies: $GATEWAY_RAW, token budget $TOKEN_BUDGET_IN in / $TOKEN_BUDGET_OUT out, agent egress: $GATEWAY_EGRESS); per-trial records in <trial>/gateway/"
fi

gateway_check() {  # before a job is claimed (GATEWAY=1): the gateway answers, else it is restarted on its port; 1 = it is
  # down for good and the lane stops (every trial would end as an infrastructure failure, board 0121 M4)
  [ "$GATEWAY" = 1 ] || return 0
  gw_alive && return 0
  log "usage gateway $GW (pid $gw_pid) does not answer; restarting it on port $gw_port"
  kill "$gw_pid" 2>/dev/null; sleep 1
  gw_start "$gw_port" && gw_alive && { log "usage gateway restarted (pid $gw_pid)"; return 0; }
  log "STOP lane $$: the usage gateway could not be restarted on port $gw_port (see $JOBS/.gateway/gateway.$$.err)"; return 1
}

gateway_after() {  # <job>: the gateway died during the job: its trials are infrastructure failures, not the agent's 0
  # (<job>/gateway_down.json, read by scripts/account_failure_check.py and write_task_results.py)
  [ "$GATEWAY" = 1 ] && [ -d "$JOBS/$1" ] || return 0
  gw_alive && return 0
  printf '{"gateway": "%s", "pid": "%s", "checked": "%s"}\n' "$GW" "$gw_pid" "$(date -u +%FT%TZ)" > "$JOBS/$1/gateway_down.json"
  log "$1: the usage gateway was down when the job ended: its trials are not results (gateway_down.json)"
}

wait_for() {  # <mode>: block until every WAIT_FOR file of this mode exists
  local w
  for w in $WAIT_FOR; do
    if [ "${w%%:*}" = "$1" ]; then
      log "$1 waits for ${w#*:}"
      until [ -e "${w#*:}" ]; do sleep 30; done
    fi
  done
}

finish_job() {  # <job>: the raw logs compacted; no key in any saved file (+redact); the task results (D3)
  [ -d "$JOBS/$1" ] || return 0
  [ "$GATEWAY" = 1 ] && [ "$GATEWAY_RAW" = 1 ] && python3 "$R/scripts/usage_gateway/rawlog.py" compact "$JOBS/$1" 2>&1 | sed "s/^/[$1] /" | tee -a "$LOG"
  python3 "$R/scripts/scan_secrets.py" "$JOBS/$1" "${SCAN[@]}" --redact 2>&1 | tail -3 | sed "s/^/[$1] /" | tee -a "$LOG"
  [ -n "$RESULTS" ] && python3 "$R/scripts/write_task_results.py" "$JOBS" "$1" "$RUN_ID" "$LABEL" --out "$RESULTS/$batch" 2>&1 | tail -3 | sed "s/^/[$1] /" | tee -a "$LOG"
}

summary() {  # one table per comparable configuration over every job of this batch, rewritten after each job (atomically: lanes share it)
  python3 - "$JOBS" "$batch" "$R" > "$JOBS/$batch.summary.md.$$" <<'PY'
import json, pathlib, sys, datetime as dt
from collections import defaultdict
jobs, batch, R = pathlib.Path(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3])
sys.path.insert(0, str(R / "scripts"))
import task_conventions as tc, write_task_results as wtr  # noqa: E402
from task_names import canonical  # noqa: E402
# docs/protocol/running.md "Results" (PROTOCOL v2.0): results are compared only within one configuration (task_conventions.config_key:
# protocol version, mode, cutoff, reset budget, S, network); validated and unvalidated tasks (task_conventions.validated_of)
# are ranked together, the unvalidated ones marked; a trial that is not a result (infrastructure, voided) never counts in a
# success rate. Tasks of the easy set (docs/easy_set.toml, task_conventions.set_of) are listed, marked, and left out of
# the headline rate (PROTOCOL §4).
HEAD = ("| task | success | result | reward fields | actions | agent wall s | input tok | cached | output tok | gateway in / out | cost $ | exception |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|")
f = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
groups = defaultdict(list)          # config key -> [(started, row, status, validated, easy)]
labels = {}
for trial in jobs.glob(f"{batch}-*/*__*"):
    if not trial.is_dir():
        continue
    r = json.loads((trial / "result.json").read_text()) if (trial / "result.json").exists() else {}
    rw = json.loads((trial / "verifier/reward.json").read_text()) if (trial / "verifier/reward.json").exists() else {}
    ar = r.get("agent_result") or {}; ex = (r.get("exception_info") or {}).get("exception_type") or ""
    ae = r.get("agent_execution") or {}
    gw = json.loads((trial / "gateway/totals.json").read_text()) if (trial / "gateway/totals.json").exists() else {}
    gw_cell = (f"{gw['input']} / {gw['output']}" + (" OVER BUDGET" if gw.get("over_token_budget") else "")) if gw else "-"
    # requests the gateway refused because they were not model-API calls (PROTOCOL §2.11): attempts, for a look; they
    # do not void the trial, and the harness's own start-up probes are not among them
    left = sum(gw.get(k, 0) for k in ("refused_paths", "refused_server_tools", "refused_bodies", "refused_hosts"))
    gw_cell += f" REFUSED {left}" if left else ""
    try:
        wall = round((f(ae["finished_at"]) - f(ae["started_at"])).total_seconds())
    except Exception:
        wall = ""
    task = canonical((r.get("task_name") or trial.name.split("__")[0]).split("/")[-1])
    if r and (R / "tasks" / task / "task.toml").is_file():
        status, why, _ = wtr.classify(trial, r, rw)
        cfg = wtr.trial_config(trial, task, r)
    else:
        status, why, cfg = ("not_a_result", "no result.json", {}) if not r else ("legacy", None, {"mode": task.rsplit("-", 1)[-1]})
    key = tc.config_key(cfg)
    labels[key] = tc.config_label(cfg)
    keys = {k: rw[k] for k in ("deterministic", "live_success", "replay_success", "instance_ok", "missing_trajectory", "grader_error",
                               "infra_error", "resumes") if k in rw}
    res = "not a result (voided" + (f": {why}" if why else "") + ")" if status == "not_a_result" else status
    val = cfg.get("validated") is True
    easy = (R / "tasks" / task / "task.toml").is_file() and tc.set_of(R / "tasks" / task) == "easy"
    groups[key].append((r.get("started_at") or "~", f"| {task}{'' if val else ' (unvalidated)'}{' (easy set)' if easy else ''} | {rw.get('success', '-')} | {res} | {json.dumps(keys)} | "
                        f"{rw.get('n_actions', '-')} | {wall} | {ar.get('n_input_tokens', '-')} | {ar.get('n_cache_tokens', '-')} | "
                        f"{ar.get('n_output_tokens', '-')} | {gw_cell} | {round(ar['cost_usd'], 4) if ar.get('cost_usd') is not None else '-'} | {ex} |",
                        status, val, easy))
print(f"# {batch}\n\nOne table per comparable configuration (docs/protocol/running.md \"Results\"); success rates count results only "
      "(a trial that is not a result is voided and never counted). Validated and unvalidated tasks are ranked together; "
      "tasks without a validated oracle (`oracle` not `full` and no `[metadata] validated = true`), and trials of a task "
      "version this checkout does not have, are marked (unvalidated). Tasks of the easy set (docs/easy_set.toml) are "
      "marked (easy set) and left out of the success rate (PROTOCOL §4).")
for k in sorted(groups, key=lambda k: tuple(map(str, k))):
    rows = groups[k]
    counted = [(s, v) for _, _, s, v, e in rows if s in ("success", "fail") and not e]
    easy_n = sum(1 for _, _, s, _, e in rows if s in ("success", "fail") and e)
    rate = f"{sum(s == 'success' for s, _ in counted)} / {len(counted)}" if counted else "-"
    cv = [s for s, v in counted if v]
    vrate = f" (validated tasks: {sum(s == 'success' for s in cv)} / {len(cv)})" if len(cv) != len(counted) else ""
    print(f"\n## {labels[k]}\n\nSuccess (results only): {rate}{vrate}; "
          f"{sum(s == 'not_a_result' for _, _, s, _, _ in rows)} voided"
          + (f"; {easy_n} result(s) of easy-set tasks not counted" if easy_n else "") + f".\n\n{HEAD}")
    for _, row, _, _, _ in sorted(rows):
        print(row)
PY
  mv -f "$JOBS/$batch.summary.md.$$" "$JOBS/$batch.summary.md"
}

stamp_task_dirs() {  # <root>: give every file of the job's task copies a mtime derived from its content (scripts/stamp_mtimes.py)
  # BuildKit keeps one shared snapshot per build-context NAME (Harbor's are always "environment" and "tests") and re-sends a file
  # only when its name, size, mode or mtime changed: a tree whose files share mtimes (git checkout, tar, cp -r, sed loops) can
  # build one task's image with ANOTHER task's equal-size file (issue #258). A content-derived mtime never matches another
  # content's. Always on the job's own copy: a checkout update during the trial cannot reset it before the verifier is built.
  python3 "$R/scripts/stamp_mtimes.py" --full "$1/tasks" >/dev/null
}

gateway_copy() {  # <dir> <harbor -i args...>: <dir>/tasks/<task> = the task with the gateway and the package registries as its only egress (PROTOCOL §2.11)
  local dir="$1" a; shift
  rm -rf "$dir" && mkdir -p "$dir/tasks" || return 1
  while [ $# -gt 0 ]; do
    a="$1"; shift
    if [ "$a" = -i ] && [ $# -gt 0 ]; then
      if [ "$(python3 "$R/scripts/set_agent_egress.py" network "$R/tasks/$1")" = open ]; then    # the task declares open egress (`[metadata] network = "open"`, PROTOCOL §2): the copy keeps it
        cp -a "$R/tasks/$1" "$dir/tasks/$1" || return 1; shift; continue
      fi
      cp -a "$R/tasks/$1" "$dir/tasks/$1" && python3 "$R/scripts/set_agent_egress.py" only "$GATEWAY_ONLY" "$dir/tasks/$1" >/dev/null || return 1
      grep -q "^allowed_hosts = \[\"${GATEWAY_ONLY//,/\", \"}\"\]\$" "$dir/tasks/$1/task.toml" || return 1     # fail closed
      shift
    fi
  done
}

plain_copy() {  # <dir> <harbor -i args...>: <dir>/tasks/<task> = the task as it is
  local dir="$1" a; shift
  rm -rf "$dir" && mkdir -p "$dir/tasks" || return 1
  while [ $# -gt 0 ]; do
    a="$1"; shift
    if [ "$a" = -i ] && [ $# -gt 0 ]; then cp -a "$R/tasks/$1" "$dir/tasks/$1" || return 1; shift; fi
  done
}

task_dirs() {  # <root> <harbor -i args...>: the task directories the -i arguments name under <root>/tasks
  local root="$1" a; shift
  while [ $# -gt 0 ]; do
    a="$1"; shift
    if [ "$a" = -i ] && [ $# -gt 0 ]; then printf '%s\n' "$root/tasks/$1"; shift; fi
  done
}

run_job() {  # <job> <concurrency> <harbor -i args...>
  local job="$1" n="$2"; shift 2
  local envf=(); [ -n "$ENV_FILE" ] && envf=(--env-file "$ENV_FILE")
  local root="$R" f dirs=()
  mapfile -t dirs < <(task_dirs "$R" "$@")
  # every job runs from its own copy of the task ($JOBS/.tasks/<job>/, removed afterwards), stamped (issue #258); PROTOCOL §2.10:
  # a CPU cap above the host's CPU count is clamped to it in that copy (docker refuses such a container: "range of CPUs is
  # from 0.01 to 8.00"), never in tasks/
  local clamp=0; python3 "$R/scripts/clamp_cpus.py" --cpus "$HOST_CPUS" --needs "${dirs[@]}" >/dev/null && clamp=1
  [[ "$job" =~ ^[A-Za-z0-9._-]+$ ]] || { log "FAILED $job: not a job name (letters, digits, . _ -); not started"; return 1; }
  root="$JOBS/.tasks/$job"
  if [ "$GATEWAY" = 1 ] && [ "$GATEWAY_EGRESS" = gateway ]; then
    gateway_copy "$root" "$@" || { log "FAILED $job: could not prepare its task copy (the gateway and the package registries as the only egress) ($root); not started"; rm -rf "$root"; return 1; }
  else
    plain_copy "$root" "$@" || { log "FAILED $job: could not prepare its task copy ($root); not started"; rm -rf "$root"; return 1; }
  fi
  for f in .env .env.local; do [ -e "$R/$f" ] && ln -s "$R/$f" "$root/$f"; done     # what Harbor would load from the repository
  if [ "$clamp" = 1 ]; then
    mapfile -t dirs < <(task_dirs "$root" "$@")
    python3 "$R/scripts/clamp_cpus.py" --cpus "$HOST_CPUS" "${dirs[@]}" | sed "s#^$root/tasks/#[$job] clamped #" | tee -a "$LOG" >/dev/null \
      && ! python3 "$R/scripts/clamp_cpus.py" --cpus "$HOST_CPUS" --needs "${dirs[@]}" >/dev/null \
      || { log "FAILED $job: could not clamp its CPU caps to the host's $HOST_CPUS ($root); not started"; rm -rf "$root"; return 1; }
  fi
  stamp_task_dirs "$root" || { log "FAILED $job: could not stamp its task copy (scripts/stamp_mtimes.py, $root); not started"; rm -rf "$root"; return 1; }
  log "start $job: $* (concurrency $n, attempts $K)"
  (cd "$root" && harbor run -p tasks "$@" "${AGENT_ARGS[@]}" "${envf[@]}" -n "$n" -k "$K" -y -o "$JOBS" --job-name "$job") > "$JOBS/$job.harbor.log" 2>&1
  log "done $job (harbor rc=$?)"
  rm -rf "$root"
  return 0
}

name() {  # <mode> <base> -> task dir name: <base>-privileged / <base>-standard / <base>-standard-realtime (PROTOCOL §2.2)
  case "$1" in
    standard|limited) echo "$2-standard" ;;
    standard-realtime) echo "$2-standard-realtime" ;;
    *) echo "$2-privileged" ;;
  esac
}

not_started=0
if [ "$SEQ" = 1 ]; then
  mkdir -p "$JOBS/.claims"
  for t in "${tasks[@]}"; do
    for m in $MODES; do
      job="$batch-$m-$t"
      if [ ! -d "$R/tasks/$(name "$m" "$t")" ]; then log "skip $job (no task dir $(name "$m" "$t"))"; continue; fi
      if [ -f "$JOBS/$job/result.json" ]; then log "skip $job (already has result.json)"; continue; fi
      mkdir "$JOBS/.claims/$job" 2>/dev/null || continue   # another lane of this batch took it
      wait_for "$m"
      gateway_check || { rmdir "$JOBS/.claims/$job" 2>/dev/null; break 2; }
      run_job "$job" 1 -i "$(name "$m" "$t")" || { rmdir "$JOBS/.claims/$job" 2>/dev/null; not_started=$((not_started + 1)); continue; }   # another lane or a later run may take it
      gateway_after "$job"; finish_job "$job"; summary
      # the model account is out of credits, rate-limited or logged out: every further job would fail within minutes. Only
      # structured evidence counts (Codex's rate_limits and last event, Claude Code's result event): scripts/account_failure_check.py
      why=$(python3 "$R/scripts/account_failure_check.py" "$JOBS/$job"/*__*/ 2>&1); rc=$?
      if [ $rc -eq 4 ]; then
        log "STOP lane $$: $job hit a model-account or config failure, or its model API was unreachable through the gateway ($(grep -m1 '"stop": true' <<< "$why" | cut -c1-300)); move its dir and claim aside to rerun it"; break 2
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
    n="$N_P"; case "$m" in standard|limited|standard-realtime) n="$N_S" ;; esac   # sidecar modes
    (wait_for "$m"; run_job "$batch-$m" "$n" "${inc[@]}") &
    pids+=($!)
  done
  wait "${pids[@]}"
  for m in $MODES; do gateway_after "$batch-$m"; finish_job "$batch-$m"; done
fi
[ -d "${JOBS}_mirror" ] && python3 "$R/scripts/scan_secrets.py" "${JOBS}_mirror" "${SCAN[@]}" 2>&1 | tail -2 | sed "s/^/[mirror] /" | tee -a "$LOG"
summary
log "summary: $JOBS/$batch.summary.md"
cat "$JOBS/$batch.summary.md" | tee -a "$LOG" >/dev/null
[ "$not_started" -gt 0 ] && log "WARNING: $not_started job(s) of batch $batch were NOT started (their task copy could not be prepared, see FAILED above)"
log "runner $$ of batch $batch finished (no unclaimed job left)"
