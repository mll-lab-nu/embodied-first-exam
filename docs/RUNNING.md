# Running evaluations

Operational notes for running batches and reading results. The contract is [PROTOCOL.md](PROTOCOL.md); the
standard-mode wire protocol is [LIMITED_MODE_PROTOCOL.md](LIMITED_MODE_PROTOCOL.md). Task directories end in `-privileged` or
`-standard`.

## Agent logs and timelines
Harbor keeps, per trial, `agent/codex.txt` (every message, command and output), `agent/trajectory.json` and the raw
Codex session (`agent/sessions/`). Run Codex with `--ak reasoning_summary=detailed` to also keep reasoning summaries
(otherwise reasoning is stored encrypted). `scripts/agent_timeline.py <trial_dir>` merges the agent's messages,
reasoning summaries, tool calls, images and token use with the robot service's log into one `analysis/timeline.md`.

## Recordings

- **Standard mode (RoboTwin):** the sim service records `live.mp4` (six views, frames only while physics runs and something moves,
  each stamped with the agent's call and wall/sim time; rendered from the deterministic trajectory at episode end, so it
  costs the agent nothing; `RCB_LIVE=realtime` captures during the episode instead), the exact actions of every call,
  and a crash-safe trajectory. Details: `docs/LIMITED_MODE_PROTOCOL.md` (Live recording). Protocol 2.1 also gives the
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
scripts/regrade_trials.sh exps/jobs/<job-priv>          # re-run the same grader for trials with a grader error / missing video
scripts/collect_batch_results.py exps/jobs <job-priv> <job-std> <out_dir>   # videos, rewards, cost, summary.md
scripts/make_two_mode_report_zh.py exps/jobs <job-priv> <job-std> <report_dir> [batch_plan.json]   # internal report (Chinese), GIF previews + mp4
```
`CODEX_FORCE_AUTH_JSON=1` uses a ChatGPT-subscription login (`codex login --device-auth`) instead of an API key.
Use an absolute `-o` (compose cp is noisy otherwise); 3 concurrent trials fit one RTX 4090 with headroom for the
separate verifiers. Results (per-task and batch reports) go to the results site and the Hugging Face dataset (PROTOCOL §5), not into the repository.

## Unattended batches (`scripts/run_agent_batch.sh`)
`scripts/run_agent_batch.sh <batch> <base> ...` runs one Harbor-native agent over `<base>-privileged` and `<base>-standard`
for each task base (a missing twin is skipped), one Harbor job per task and mode. Starting the same command again adds a
lane: every job is claimed by exactly one runner (`$JOBS/.claims/<job>`). The run id is derived as in TAXONOMY (D4) and
checked. Configuration is Harbor's own:

| what | how |
|---|---|
| agent, model, effort | `AGENT=codex` or `claude-code`, `MODEL`, `EFFORT` (`--ak reasoning_effort`), more options in `AK` |
| OpenRouter | Codex: `OPENAI_API_KEY=<OpenRouter key> OPENAI_BASE_URL=https://openrouter.ai/api/v1`; Claude Code: `ANTHROPIC_BASE_URL=https://openrouter.ai/api` with the key in `ANTHROPIC_API_KEY` |
| ChatGPT login (Codex) | `CODEX_FORCE_AUTH_JSON=1` (Harbor uploads `~/.codex/auth.json` into each trial) |
| Claude subscription | `CLAUDE_FORCE_OAUTH=1` and `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`) |
| Azure OpenAI, retries | a Codex `config.toml` passed as `AGENT_CONFIG` (`--ak config=<file>`): the Azure provider, and `request_max_retries` / `stream_max_retries` for transient upstream failures |
| credentials file | `ENV_FILE` (Harbor's `--env-file`); without it the variables come from the runner's environment |

Provider, service tier and other settings go in the results metadata, not in the run id. Use one key per batch with a
spending cap. After each job the runner scans the job for keys and redacts them, writes the per-task results for the
results site with `scripts/write_task_results.py --out` outside the repository (D3: `RESULTS`, default `../rcb_results`
next to the checkout, gets `<batch>/<task>/<run id>/`; `RESULTS=` skips it), updates `$JOBS/<batch>.summary.md`, and
stops its lane when a trial shows a model-account failure.

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

## Web search (off by default)
`scripts/run_agent_batch.sh` turns the harness's web search off unless `WEB_SEARCH=allowed`: Codex gets
`--ak web_search=disabled`, Claude Code `--ak disallowed_tools=WebSearch,WebFetch` (PROTOCOL §5). For a bare
`harbor run`, pass the same option yourself. Codex with ChatGPT login searches by default; an API key can still request
search directly, which the usage gateway's raw log shows (docs/LEAKAGE.md).

## Usage gateway (token usage per request, optional)
Off by default: the agent calls its API directly, as Harbor runs it. With `GATEWAY=1`, `scripts/run_agent_batch.sh` starts `scripts/usage_gateway/gateway.py` on the docker bridge (`GATEWAY_BIND`, 172.17.0.1)
and points the agent's base URL at it (`--ae ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL`; a copy of `AGENT_CONFIG` with its
provider `base_url`s rewritten and `supports_websockets = false`). The agent is still Harbor's own `codex` /
`claude-code` with its own credentials: the gateway forwards every request unchanged to the same API, never stores a key,
and refuses any host that is not a model API (`scripts/set_agent_egress.py` HOSTS), so it is no way around an egress
allowlist. Under an allowlist the runner adds `--allow-agent-host 172.17.0.1`.

Per trial, next to Harbor's `agent/` and `verifier/` (outside the agent's mounts):
```
<trial>/gateway/usage.jsonl     one line per request: time, duration, host, path, status, model, input / cached / output tokens
<trial>/gateway/totals.json     running totals, rewritten after every request
<trial>/gateway/raw/            every request and response body (GATEWAY_RAW=1, the default with the gateway on), gzipped JSON (headers without credentials)
```
Input counts what the model read (Anthropic: input + cache read + cache creation; OpenAI: `input_tokens`, cached
included); output includes reasoning: the same convention as Harbor's `n_input_tokens` / `n_output_tokens`, which the batch
summary shows side by side. They agree exactly when the agent ends by itself; when it is stopped at its time limit, the
gateway is higher by the requests the provider completed (and billed) after Harbor's cut-off or that the agent was killed
before logging (measured 2026-10-01 on 9 benchmarks: the difference is exactly those requests). Token budget: with the gateway on, a trial that reaches `TOKEN_BUDGET_IN` input or `TOKEN_BUDGET_OUT` output tokens
(default 100M / 10M; 0 = no limit) gets every further model request refused (HTTP 400, "token budget exceeded"), so
the agent stops; `totals.json` records `over_token_budget = 1`, the batch summary marks it, and `write_task_results.py`
counts it as failed (PROTOCOL §5). Tested 2026-10-02: Codex 0.159.2 ends its turn on the first refusal, without retrying.
Switches: `GATEWAY=1` (record usage and, by default, raw bodies), `GATEWAY_RAW=0` (usage only; raw bodies are private: they hold the
whole conversation). Known limits: no WebSocket (Codex's built-in provider falls back to HTTPS after a few refused
attempts); Codex request bodies are zstd-compressed and are stored as base64 unless `zstandard` is installed; OpenAI
reasoning arrives encrypted. Requests no trial can be matched to go to `<jobs>/.gateway/unattributed.jsonl`.
