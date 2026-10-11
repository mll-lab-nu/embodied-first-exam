# Running evaluations

Operational notes for running batches and reading results. The contract is [PROTOCOL.md](PROTOCOL.md); the
standard-mode wire protocol is [STANDARD_MODE.md](STANDARD_MODE.md). Task directories end in `-privileged`,
`-standard` or `-standard-realtime` (PROTOCOL §4b: standard-realtime results state the reset budget and the slowdown `RCB_SLOWDOWN`, default
1; results with another slowdown are reported separately).

## Agent logs and timelines
Harbor keeps, per trial, `agent/codex.txt` (every message, command and output), `agent/trajectory.json` and the raw
Codex session (`agent/sessions/`). Run Codex with `--ak reasoning_summary=detailed` to also keep reasoning summaries
(otherwise reasoning is stored encrypted). `scripts/agent_timeline.py <trial_dir>` merges the agent's messages,
reasoning summaries, tool calls, images and token use with the robot service's log into one `analysis/timeline.md`.

## Recordings

- **Standard mode (RoboTwin):** the sim service records `live.mp4` (six views, frames only while physics runs and something moves,
  each stamped with the agent's call and wall/sim time; rendered from the deterministic trajectory at episode end, so it
  costs the agent nothing; `RCB_LIVE=realtime` captures during the episode instead), the exact actions of every call,
  and a crash-safe trajectory. Details: `docs/STANDARD_MODE.md` (Live recording). Protocol 2.1 also gives the
  agent measured proprioception (encoders, gripper opening, TCP pose, drive effort) and optional depth noise.
- **Privileged mode:** the agent owns the simulator, so nothing it produces is evidence. `rcb_traj.Session` still dumps every
  rollout's per-step drive targets to `/app/output/rcb_trace/` (`RCB_AGENT_TRACE_DIR`, capped at 300 files / 400 MB),
  and the verifier, after writing the verdict, reconstructs videos of the agent's last six rollouts into
  `agent_sessions/` with an `index.json` of all of them (`agent_traces`, `agent_trace_steps`, `agent_trace_videos`
  in reward.json). Self-reported: an agent that teleports objects through `exec_code` will not replay faithfully.

## Running a two-mode batch (privileged + standard)
```bash
harbor run -p tasks -i robotwin_2_0_<t1>-privileged -i robotwin_2_0_<t2>-privileged -a codex -m openai/gpt-6-luna -n 3 -o $PWD/exps/jobs --job-name <job-priv>
harbor run -p tasks -i robotwin_2_0_<t1>-standard ... -a codex -m openai/gpt-6-luna -n 3 -o $PWD/exps/jobs --job-name <job-std>
harbor trial regrade --help                             # re-run the verifier of a recorded trial (a grader error, a missing video)
scripts/write_task_results.py exps/jobs <job> <run-id> "<agent label>" --out <dir outside the repository>   # per-task results (README, video, cost)
```
`CODEX_FORCE_AUTH_JSON=1` uses a ChatGPT-subscription login (`codex login --device-auth`) instead of an API key.
Use an absolute `-o` (compose cp is noisy otherwise); 3 concurrent trials fit one RTX 4090 with headroom for the
separate verifiers. Results (per-task and batch reports) go to the results site and the Hugging Face dataset (PROTOCOL §5), not into the repository.

## Unattended batches (`scripts/run_agent_batch.sh`)
`scripts/run_agent_batch.sh <batch> <base> ...` runs one Harbor-native agent over `<base>-privileged` and `<base>-standard`
(and `<base>-standard-realtime` with `MODES="privileged standard standard-realtime"`) for each task base (a missing twin is skipped), one Harbor job per task and mode. Starting the same command again adds a
lane: every job is claimed by exactly one runner (`$JOBS/.claims/<job>`). The run id is derived as in TAXONOMY (D4) and
checked. Configuration is Harbor's own:

| what | how |
|---|---|
| agent, model, effort | `AGENT=codex` or `claude-code`, `MODEL`, `EFFORT` (`--ak reasoning_effort`), more options in `AK` |
| OpenRouter | Codex: `OPENAI_API_KEY=<OpenRouter key> OPENAI_BASE_URL=https://openrouter.ai/api/v1`; for long runs declare OpenRouter as a provider of its own in the `AGENT_CONFIG` file (`model_provider = "openrouter"`, its `base_url`, `env_key = "OPENAI_API_KEY"`, `wire_api = "responses"`, `supports_websockets = false`): as "OpenAI", Codex compacts a full context through an endpoint OpenRouter does not serve and the run stops ("Error running remote compact task"). Claude Code: `ANTHROPIC_BASE_URL=https://openrouter.ai/api` with the key in `ANTHROPIC_API_KEY` |
| ChatGPT login (Codex) | `CODEX_FORCE_AUTH_JSON=1` (Harbor uploads `~/.codex/auth.json` into each trial) |
| Claude subscription | `CLAUDE_FORCE_OAUTH=1` and `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`) |
| Azure OpenAI, retries | a Codex `config.toml` passed as `AGENT_CONFIG` (`--ak config=<file>`): the Azure provider, and `request_max_retries` / `stream_max_retries` for transient upstream failures |
| credentials file | `ENV_FILE` (Harbor's `--env-file`); without it the variables come from the runner's environment |

Provider, service tier and other settings go in the results metadata, not in the run id. Use one key per batch with a
spending cap. After each job the runner scans the job for keys and redacts them, writes the per-task results for the
results site with `scripts/write_task_results.py --out` outside the repository (D3: `RESULTS`, default `../rcb_results`
next to the checkout, gets `<batch>/<task>/<run id>/`; `RESULTS=` skips it), updates `$JOBS/<batch>.summary.md`, and
stops its lane when a trial shows a model-account failure.

To watch a batch live: `scripts/live_board.py --jobs <JOBS>` (repeatable; stdlib only) serves a page on 127.0.0.1 that
refreshes every 5 s. It shows every trial as pending, setup, running (agent time against the task's limit), verifying,
success or failed, with live tokens when the usage gateway runs, the reward, the videos and the tail of the agent's
output. Pending trials come from `$JOBS/.plan/<batch>.json`, which the runner writes when it starts. Reach the page from
another machine with `ssh -N -L 8765:127.0.0.1:<port> <host>`; it shows the agent's output, so keep it off public
addresses. It has no login (every user of a shared host can open it) and serves a running trial's files before the
runner's secret scan has redacted them.

Runner-side tools (they run on the host, never in a task): `scripts/log_mirror.py` (in the `rcb-log-mirror` container: an
append-only copy of every trial's `agent/` record that neither the agent nor the host user can delete),
`scripts/mem_guard.py` (keeps 2 GiB of host memory available by killing the largest benchmark container first),
`scripts/scan_secrets.py` (the key scan; it loads secrets inside its own process and never prints them),
`scripts/account_failure_check.py` (structured evidence only: Codex's rate limits and last event, Claude Code's result
event). `LOG_MIRROR=0` / `MEM_GUARD=0` skip starting the first two.

## Base images
Every base image is `ghcr.io/mll-lab-nu/eai-<name>:<images/<name>/VERSION>` (PROTOCOL §2.4, D5): `scripts/build_images.sh`
builds them all, `scripts/push_images.sh` pushes all but the `BUILD_ONLY` ones (needs `docker login ghcr.io` with a token
that has `write:packages`). New packages in the org start private; an org admin makes them public in the package
settings (the API cannot). An image with `images/<name>/BUILD_ONLY` (Isaac Sim inside: RoboLab, BEHAVIOR-1K) is never
public: every host builds it (the marker file says how, and what licences and data it needs), and maintainers may keep
a private package for org members. Before 2026-10-02 the images were `rcb-<sim>` (several registries) or `eai-<name>`
under `embodied-agent-interface-v2-internal`; a host with an old tag can `docker tag` it to the new name.

## No tool outside the container (web search off by default)
`scripts/run_agent_batch.sh` turns the harness's web search off unless `WEB_SEARCH=allowed`: Codex gets
`--ak web_search=disabled`, Claude Code `--ak disallowed_tools=WebSearch,WebFetch` (PROTOCOL D11, §2.11). For a bare
`harbor run`, pass the same option yourself. Codex with ChatGPT login searches by default, and it hands the model the
account's connectors, apps, plugins and an image generator unless its config turns them off (`features.apps = false`,
`features.plugins = false`, `features.image_generation = false`, `apps._default.enabled = false`, before any table of
the config); Claude Code under a full claude.ai login loads the account's connectors (`disableClaudeAiConnectors`). An
official run starts the harness without them. An API key can still request a search directly; the usage gateway
refuses such a request and every path that is not a model call (below, docs/LEAKAGE.md).

## Usage gateway (token usage per request, optional)
Off by default: the agent calls its API directly, as Harbor runs it. With `GATEWAY=1`, `scripts/run_agent_batch.sh` starts `scripts/usage_gateway/gateway.py` on the docker bridge (`GATEWAY_BIND`, 172.17.0.1)
and points the agent's base URL at it (`--ae ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL`; a copy of `AGENT_CONFIG` with its
provider `base_url`s rewritten and `supports_websockets = false`). The agent is still Harbor's own `codex` /
`claude-code` with its own credentials: the gateway forwards model requests unchanged to the same API, never stores a key,
and refuses any host that is not a model API (`scripts/set_agent_egress.py` HOSTS), so it is no way around an egress
allowlist.

**Model-API calls only, and the only way out (PROTOCOL §2.11).** The gateway forwards the requests listed per provider
in `scripts/usage_gateway/api_paths.json` (responses, messages, token counting, the model list; chat completions only
to a self-hosted upstream: no official run used them, and at the providers that API serves models that search the web
without any tool declaration) and answers anything else 403 without forwarding it: connectors and apps,
plugins, files, conversations, web search. A model request is forwarded as it is or not at all: its body must be one
JSON object the gateway can read (one Content-Length of at most 256 MiB, at most one Content-Encoding), and every tool
it declares (top-level `tools`, and the `tools` of an `input` item, where Codex declares its own) must be one the agent
runs itself (`client_tool_types` in the same file: no type, `function`, `custom`, `namespace`, which is all Codex and
Claude Code declared in the recorded runs). Any other tool type is the provider's (web search or fetch, image
generation, remote MCP, file search, a hosted shell or code interpreter) and the request is refused, as is one with a
provider-side search, MCP or stored-prompt field (`provider_side_fields`), an OpenRouter `:online` model, or an image,
document or file given as an http(s) address for the provider to fetch (`data:` URLs are fine). What the gateway does
not judge: which model a request names (a provider's model that searches by itself on a forwarded path would pass;
give a run a key that can call only its model). Codex compresses its
ChatGPT-login requests with zstd: the gateway reads them with the `zstandard` module or the `zstd` program; a host with
neither forwards such a body unchecked, marks it `body_unchecked` and says so in the gateway's start-up log. Refusals
are in `<trial>/gateway/usage.jsonl` (`refused`: `path_not_allowed`, `host_not_allowed`, `server_tool` or
`body_unreadable`, with method and path, never a body) and counted in `totals.json` (`refused_paths`,
`refused_server_tools`, `refused_bodies`); the batch summary shows `REFUSED n` in the gateway column. A trial with one
tried to leave the model API and is to be looked at. To add a provider, a path or a client tool type (a new harness
version that declares another one is refused until it is listed), edit `api_paths.json` (default deny; a host without a
provider there gets nothing forwarded).
The model APIs' hosts also serve all of that directly, so with the gateway on each job runs from its own copy of the
task (`$JOBS/.tasks/<job>/`, removed afterwards) whose egress allowlist is the gateway's address alone
(`scripts/set_agent_egress.py only <GATEWAY_BIND>`; Harbor's `--allow-agent-host` can add a host, not remove one).
`GATEWAY_EGRESS=task` keeps the task's own allowlist (the hosts reachable directly; not for official runs).
Harbor's allowlist names addresses, not ports: every TCP service that listens on the gateway's address (the docker
bridge) of the runner host is reachable from a trial, as it has been since the gateway exists; bind the host's other
services to 127.0.0.1 or firewall the bridge.
One exception, Codex with a ChatGPT login: before its first model call Codex 0.160.1 asks
`chatgpt.com/backend-api/wham/accounts/check` for the account's workspace, at `chatgpt_base_url` and not at the model's
base URL, and it accepts only an HTTPS origin there, which the plain-HTTP gateway is not (through the gateway the lookup
succeeds and Codex then stops with "workspace backend must use an HTTPS origin"; without it, "workspace routing
discovery failed"). Such a run keeps `chatgpt.com` (that one host) on the copy's allowlist beside the gateway, so that
backend's other paths stay reachable directly and the account's connectors are off by the harness's configuration
alone. Closing it needs a gateway that speaks HTTPS with a certificate the harness trusts; until then prefer API keys,
which have no connectors, and keep the evaluation accounts' connectors disconnected. Measured 2026-10-10 on a pool host
(one short trial each, a container probing its own reach): a Codex API key, a Claude subscription token and a
self-hosted endpoint work with the gateway as the only address, and `chatgpt.com`, `api.openai.com`,
`api.anthropic.com`, `auth.openai.com`, GitHub and PyPI fail from the container; a ChatGPT login works with the
exception, with `chatgpt.com` answering directly and the other hosts failing.
The runner waits `GATEWAY_START_WAIT` seconds (10) for the gateway to come up; raise it on busy shared nodes.

Per trial, next to Harbor's `agent/` and `verifier/` (outside the agent's mounts):
```
<trial>/gateway/usage.jsonl     one line per request: time, duration, host, path, status, model, input / cached / output tokens
<trial>/gateway/totals.json     running totals, rewritten after every request
<trial>/gateway/raw.jsonl.xz    every request and response body (GATEWAY_RAW=1, the default with the gateway on; headers without credentials)
```
Input counts what the model read (Anthropic: input + cache read + cache creation; OpenAI: `input_tokens`, cached
included); output includes reasoning: the same convention as Harbor's `n_input_tokens` / `n_output_tokens`, which the batch
summary shows side by side. They agree exactly when the agent ends by itself; when it is stopped at its time limit, the
gateway is higher by the requests the provider completed (and billed) after Harbor's cut-off or that the agent was killed
before logging (measured 2026-10-01 on 9 benchmarks: the difference is exactly those requests). Token budget: with the gateway on, a trial that reaches `TOKEN_BUDGET_IN` input or `TOKEN_BUDGET_OUT` output tokens
(default 100M / 10M; 0 = no limit) gets every further model request refused (HTTP 400, "token budget exceeded"), so
the agent stops; `totals.json` records `over_token_budget = 1`, the batch summary marks it, and `write_task_results.py`
counts it as failed (PROTOCOL §5). Tested 2026-10-02: Codex 0.159.2 ends its turn on the first refusal, without retrying.
The raw log stores each conversation item once and a request as references to the items it resends, like Codex's and
Claude Code's own session files, and is lossless: `scripts/usage_gateway/rawlog.py cat <trial>/gateway` prints every
request and response in full. The gateway appends to `raw.jsonl.gz` while the trial runs; after each job the runner
compacts it to `raw.jsonl.xz` (one 1,994-request trial: 5.9 GB as one gzip file per request, the format before
2026-10-02, 32 MB now; `rawlog.py pack --delete <dir>` converts such `raw/` directories).
Switches: `GATEWAY=1` (record usage and, by default, raw bodies), `GATEWAY_RAW=0` (usage only; raw bodies are private: they hold the
whole conversation). Known limits: no WebSocket (Codex's built-in provider falls back to HTTPS after a few refused
attempts); Codex's zstd-compressed request bodies are stored as base64, and so not deduplicated, on a runner host
that has neither the `zstandard` module nor the `zstd` program; OpenAI reasoning arrives encrypted. Requests no trial can be matched to go to `<jobs>/.gateway/unattributed.jsonl`.
