# Running evaluations

Part of the task protocol ([README](README.md); its Appendix H binds every run): how runs are configured, and what
makes a run official. The sections "Official runs" to "Results" below are the runner's rules:
`scripts/run_agent_batch.sh` applies them by default, and the evaluation pool's scheduler (its run policy, called from
the dispatcher's launch and retry paths) refuses a launch that breaks one.

## Official runs
A result is official only when its run had all of these:
- **Harbor's native agents** (`-a codex`, `-a claude-code`, ...), configured through environment variables; no agent
  adapter, no gateway that holds credentials or changes requests.
- **The usage gateway** (`GATEWAY=1`, below): it forwards model-API calls only and is, with the package registries, the
  agent container's only egress; a task that declares open egress keeps it (Network). The runner flags a trial whose
  `totals.json` has `refused_paths`, `refused_server_tools` or `refused_bodies` for a look.
- **No tool outside the container**: the harness's web search, account connectors, apps, plugins, image generation and
  cloud agents off (`WEB_SEARCH=disabled`, `scripts/codex_tools_off.py`; below).
- **Token budget** per trial: 10B input tokens (Harbor `n_input_tokens`: cached input counts in full) and 10B output
  (reasoning included) by default (`TOKEN_BUDGET_IN` / `TOKEN_BUDGET_OUT`), set so high that it almost never binds; with the gateway, exceeding either stops the agent and
  fails the trial (`over_token_budget = 1`; the first refusal also writes `budget_stop` into `totals.json`, which the runner
  labels `TokenBudgetExceeded`, not a harness or network error). A batch run with another budget records it in its results' metadata.
- **The task's own cutoff**, no multiplier (`--timeout-multiplier`, `--agent-timeout-multiplier`, an agent
  `override_timeout_sec`), and **nothing added to the instruction** (no prompt template, no extra instruction, in `AK` or elsewhere).
- **The runner's seed, the task's network, at most one infrastructure retry** (the next three sections), and the
  effective configuration recorded with the result (Results).

## Seeds: the runner chooses
The seed is the runner's, never the agent's: it is one of the task's `[metadata.seeds] allowed` (a list, `{from, to}`,
`"any"`), official batches draw one uniformly per trial, and a run on the default seed only records `default-only`.
The verifier grades the drawn seed's instance from its own copy (`build = "runtime"`: from its own seed file). How to
run a seed: "Seeds (which frozen instance a trial runs from)" below.

## Network: what the task declares
The default is the allowlist (PROTOCOL Appendix H.6); whether a task has open network is its author's decision,
declared as `[metadata] network = "open"`. The runner applies the declaration: an allowlist task's copy is narrowed to
the gateway and the package registries (`scripts/set_agent_egress.py only`), an open task's copy is left open (the
gateway still records its usage). `python3 scripts/set_agent_egress.py network <task>` prints the declaration.
`network` is part of the recorded configuration, so open-network results are never ranked with allowlist ones.

## Infrastructure failures: one full retry
The rule is PROTOCOL Appendix H.5; how the runner applies it:
- An infrastructure failure is what `scripts/write_task_results.py` publishes as "not a result": the verifier's
  `infra_error` / `grader_error`, no `reward.json`, a Harbor exception other than the agent's cutoff, a model-account or
  usage-gateway failure (`scripts/account_failure_check.py`). The agent's own end, its cutoff and its token budget are
  results and are never retried.
- The voided attempt's directory is moved aside (in the evaluation pool: `_superseded/`) and never counted; the retry starts
  from a new environment with the first attempt's recorded configuration. A failed retry keeps the default handling
  (it stays an infrastructure failure, reported as such). A launch that never started a trial is no attempt.
- One implementation of the rule, `scripts/retry_policy.py` (`decide`, `check_attempts`), tested by the required CI
  job; the evaluation pool's scheduler uses it. `write_task_results.py` keeps every attempt of a task x run id in
  `attempts.json` and flags a sequence that breaks the rule (`attempts_over_cap`).
- In-trial crash recovery (a sidecar that replays its journal and resumes the episode, standard_mode.md) is the shared
  layers' implementation, not a rule; a crash it cannot recover is an infrastructure failure, unless every crash was
  the agent's (below).
- Standard modes (graded by the live episode, PROTOCOL H.4): an infrastructure failure is one where the live record
  gives no verdict on the agent: no, an unreadable or an unfinalized `final.json` (`finalized`: the verdict is on
  disk, written before any video); the sidecar gave up after crashes that were not all inside the agent's calls
  (`sim_crashed`), could not restore the episode after a crash (`resume_failed`, whatever crashed) or ended a native
  call that hung past its deadline (`call_watchdog`); the scene did not start from the frozen instance, at the start or
  after a reset (`instance_mismatch`). Only what the service itself records as `infra_error = 1` (or a missing,
  unreadable or unfinalized record) is one; a grader never infers it from missing fields. What the agent's commands
  caused stays a result, never an infrastructure failure (a retry would be a free second attempt): crashes all inside
  its calls (`sim_crashed_on_call`), a simulator error its actions raised where the task counts that as the agent's
  (standard-realtime: a simulator error or crash after the agent's first command, standard_mode.md Part 3), the cutoff, no actions, a failed settle or hold, and a crash or error while the service
  runs a settle or hold window on the agent's final state (it counts as one inside the agent's last call). The video is
  never one: a render that fails or runs out of time loses only the video. A resume that continued from a state that
  does not match its checkpoint exactly (`approx` resume class, `resume_state_mismatch = 1`) keeps its live verdict
  and is flagged for audit.

## Results
Results are not committed (published on the [results site](https://www.embodied-first-exam.ai) and the Hugging Face dataset, keyed by run id
`<harness>-<model>-<effort>`, the model token with underscores: `codex-gpt6_luna-xhigh`; provider, tier and settings go
in the metadata). `scripts/write_task_results.py` writes, per task and run id, `README.md`, `config.json` (the trial's
effective configuration: `protocol_version`, `mode`, `cutoff_s`, `reset_budget`, `slowdown`, `seed`, `network`,
`validated`, `set`, `oracle`, `service_protocol`, `digest`, the result and whether it counts; a result dir from before v2.0
gets its fields from the task at that digest, else `"legacy"`) and `attempts.json`. Rankings (the batch summary,
the results site) compare trials only within one comparable configuration (`task_conventions.config_key`: protocol
version, mode, cutoff, reset budget, S, network), report success together with cost (tokens, money, turns, wall clock,
simulation steps), and align reasoning effort, `max_turns` and the token budget before comparing agents. Validated and
unvalidated tasks (`validated_of`: `[metadata] validated`, else `oracle = "full"`) are ranked together: totals count
every core task, the flag is shown as a marker and may be used as a filter. The main table and every headline number
(success rates, rankings, totals) count core only: the tasks of [`core_set.toml`](../core_set.toml), each in its
`default_mode` (`task_conventions.core_tasks()`); a run of the core tasks in another mode is reported apart (`set_of`:
`core` for every mode of a listed task, else `excluded`). Task dirs the list leaves out stay in the repository under
their names and are not evaluated by official runs; results they already have are kept and shown marked (the batch
summary marks them in their configuration's table and leaves them out of its rate). `set` in `config.json` is the
value when the result was written; a report derives it from `docs/core_set.toml` at the commit it publishes.

A standard-mode result recorded while a grading replay still decided is re-read from its own `final.json` (the live
episode's success, where that record applied the task's whole rule); the recorded verdict stays beside it, and a trial
without such a live verdict, started off the frozen instance (`instance_mismatch`) or re-graded under a stricter rule
keeps the recorded one (benchmark docs name their fields where they differ).

## Resources: limits and their enforcement
Each task declares its minimum compute, `[metadata.resources]`, its limits `[metadata.resources.limits]` and the docker
caps `[metadata.resources.caps]` (PROTOCOL §6; values from `scripts/task_resources.toml`, written by `normalize`,
checked by `ci_checks/check-resources.py`).
- **Minimum** = the smallest allocation on which one trial, alone on the machine, runs correctly. Derivation: memory,
  the largest sum over the phase's containers of cgroup `anon + shmem` × 1.2, rounded up to a GB; GPU memory, the largest
  `nvidia-smi` sum × 1.15, rounded up to 0.5 GB; CPU, the 90th percentile of 30-second samples, rounded up, at least
  one core per simulator process plus one for the agent. Limits sit with a margin above measured peaks (e.g.
  `max(1.5 × peak, peak + 4 GiB)`); the oracle passes within them.
- **Scope**: `trial` (privileged: every container the agent drives) or `agent` (standard modes: the agent's container;
  the `sim` sidecar is recorded, never a failure). Limits: `max_gpu_memory_gb` (NVML per process, summed),
  `max_memory_gb` (cgroup `anon + shmem`), `max_processes`, `max_disk_gb` (growth under `disk_paths`), a violation =
  above a limit for `sustain_sec` (60 s) within any `window_sec` (120 s), disk two measurements in a row; gaps never
  count against the agent. CPU is only a cap. A CPU cap above the host's count means the host's count: the runner
  clamps it in its copy (`scripts/clamp_cpus.py`); memory and pids caps are never clamped.
- **Monitor**: the `rcb_monitor` sidecar samples every few seconds into its own record (`rcb-monitor/1`), sealed in the
  first collect hook, and shows current values in `/run/rcb-limits/usage.json`, with the agent's clock (`elapsed_s`,
  `time_left_s`, `deadline_utc`: `[agent] timeout_sec` from the environment's start, so never more than the agent has);
  the verifier recomputes violations from the raw samples with its own copy of the limits. A missing, unsealed or mostly
  empty record (> 10 % of the agent phase unobserved) is `resource_monitor_missing = 1`. A runner whose container runtime
  cannot run the monitor (no `pid: host`) runs the same service as `monitor.py beacon` (no pid / cgroup host, no record):
  `usage.json` then has the clock and `"measured": false`.
- **Session log**: the monitor copies the agent's `/app/output/rcb_session_log.jsonl` append-only into its record
  (`session_log/`); before the grader, the verifier step gives the grader that copy when the agent's file was removed or
  rewritten (`session_log_tampered`, `session_log_from_monitor` in `reward.json`). The log feeds cost fields only.
- **The switch** `RCB_LIMITS_ENFORCE` (compose default 0, so it does not change the digest): `1` — a confirmed violation
  kills the scope's processes and fails the trial (`reward 0`, `success_before_limits`, `resource_limit_exceeded = 1`),
  never retried; `0` — observe and record only (`limits_violation_observed`, `/logs/verifier/resource_limits.json`);
  any other value — nothing is killed, `infra_error = 1`, `resource_switch_error = 1`. Official runs so far: 0.
- **Out-of-memory kills**: a kill at a container's own cap in the scope is a violation (`over_oom`); a host OOM kill is
  never one (enforcement on: `infra_error = 1`, `resource_host_oom`); a benchmark-owned service killed for memory in an
  episode that did not succeed is `infra_error = 1` (`resource_service_oom`) in both settings. Host protection
  (enforcement on): GPU memory above 1.5 × its limit kills the process holding the most; never a violation by itself.
  A trial a pool kills to protect its host is an operations abort (`killed_by_pool`), not a graded result.

## Agent logs and timelines
Harbor keeps, per trial, `agent/codex.txt` (every message, command and output), `agent/trajectory.json` and the raw
Codex session (`agent/sessions/`). Run Codex with `--ak reasoning_summary=detailed` to also keep reasoning summaries
(otherwise reasoning is stored encrypted).

## Recordings

- **Every trial has a video** (PROTOCOL §4): a finished, graded trial without a playable `*.mp4` in `verifier/`,
  `artifacts/data/` or `artifacts/out/` is flagged by the runner (`no_video`, with the reason it can read), unless it
  is a privileged trial whose agent submitted no trajectory that replays. A video a trial missed (the render ran out of
  its time bound, crashed, or the task rendered none) is rendered afterwards from the recorded trajectory in the
  task's own image, on the same host class when the replay is only reproducible there, and kept only when the replay
  reaches the recorded final state; `replay.regenerated.json` next to it says how. The grade is never touched, and
  the agent is never rerun for a video.
- **Standard modes:** no replay grades the episode (PROTOCOL H.4), so the video is what the sidecar recorded during the
  live episode where that is cheap, or one render of the recorded trajectory after the verdict (each benchmark's doc
  says which, and what it costs). Either way the verdict is on disk first (`final.json` `finalized`; `video_pending`
  while the render runs) and `final.json` says `video_source` (`live` / `render`).
- **Standard mode (RoboTwin):** the sim service records `live.mp4` (six views, frames only while physics runs and something moves,
  each stamped with the agent's call and wall/sim time; rendered from the trajectory after the verdict, in the same pass
  as `replay.mp4`, so it costs the agent nothing; `RCB_LIVE=realtime` captures during the episode instead), the exact actions of every call,
  and a crash-safe trajectory. Details: `standard_mode.md` (Live recording). Protocol 2.1 also gives the
  agent measured proprioception (encoders, gripper opening, TCP pose, drive effort) and optional depth noise.
- **Privileged mode:** the agent owns the simulator, so nothing it produces is evidence. `rcb_traj.Session` still dumps every
  rollout's per-step drive targets to `/app/output/rcb_trace/` (`RCB_AGENT_TRACE_DIR`, capped at 300 files / 400 MB),
  and the verifier, after writing the verdict, reconstructs videos of the agent's last six rollouts into
  `agent_sessions/` with an `index.json` of all of them (`agent_traces`, `agent_trace_steps`, `agent_trace_videos`
  in reward.json). Self-reported: an agent that teleports objects through `exec_code` will not replay faithfully.

## Building task images: stamp first
Docker's BuildKit keeps one synced copy of a build context per context directory name and client (Harbor's contexts are
always `environment/` and `tests/`) and re-sends a file only when its path, size, mode or mtime changed. A task built
from a tree whose files share mtimes (a git checkout, `git archive`, tar, `cp -r`, a sed loop) can therefore get another
task's equal-size file in its image, silently, with `--no-cache` too (issue #258; rootless podman builds are not
affected). **Never build a task image from a tree without stamping it:** `scripts/stamp_mtimes.py` gives every file a
mtime derived from its content, so different files never share one (content, modes and DIGEST unchanged; git ignores
mtimes). `scripts/run_agent_batch.sh`, `/validate` and `scripts/task_seed.py materialize` build from stamped copies; `harbor run` with this repository's set flags (`-d embodied-first-exam`, `--core`, `--all`, a mode flag, `--benchmark`) stamps the task dirs it runs in place. For a bare `harbor run -p` or `harbor trial regrade`:
```bash
c=$(python3 scripts/stamp_mtimes.py stage tasks/<benchmark>/<task> "$(mktemp -d)") && harbor run -p "$c" -a oracle ...   # a stamped copy
python3 scripts/stamp_mtimes.py tasks           # or stamp the checkout in place (again after every pull: --check tells)
```

## Without Docker: rootless podman (e.g. a Slurm cluster)
Harbor runs the tasks on podman with `-e podman`, through podman's Docker-compatible API and the docker-compose plugin.
Tested with the oracle on cgroup v1 and v2 nodes without root, `/etc/subuid` entries or a user systemd session. Run
everything inside an allocation on the compute node, with `HOME`, `XDG_RUNTIME_DIR`, `XDG_CONFIG_HOME` and `TMPDIR` on
node-local scratch (podman's storage does not work on most network file systems):

1. podman: the cluster's, or a static build (github.com/mgoltzsche/podman-static; 5.8.x on cgroup v1, which 6.x refuses),
   and the docker-compose v2 binary in `~/.docker/cli-plugins/docker-compose`.
2. `~/.config/containers/containers.conf`, for a static build unpacked into `$P`:
   ```toml
   [engine]
   helper_binaries_dir = ["$P/usr/local/lib/podman"]
   conmon_path = ["$P/usr/local/lib/podman/conmon"]
   cgroup_manager = "cgroupfs"        # no user systemd session
   events_logger = "file"
   [engine.runtimes]
   crun = ["$P/usr/local/bin/crun"]
   [network]
   firewall_driver = "none"           # only on a node without iptables
   ```
   plus `policy.json` (the build's `etc/containers/policy.json`) and, without `/etc/subuid` entries, `storage.conf` with
   `[storage.options.overlay] ignore_chown_errors = "true"`. Harbor's egress sidecar is built `FROM` a short image name,
   which podman's enforcing short-name mode refuses without a terminal; this repository's `harbor run` pulls it (and the
   allowlist probe's alpine) by its full `docker.io/` name first, so `registries.conf` needs no change.
3. Without a user systemd session netavark cannot start aardvark-dns through `systemd-run`; a `systemd-run` early on
   `PATH` that drops its options and execs the command works.
4. Start the API and run:
   ```bash
   podman system service --time=0 &
   export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock
   harbor run -e podman -d embodied-first-exam@all -p tasks/<benchmark>/<task> -a oracle -y -o $PWD/jobs
   ```
5. GPU tasks: podman ignores compose's `driver: nvidia` device request, and the task's processes then find no driver
   (`Found no NVIDIA driver`, `libnvidia-ml.so.1: cannot open shared object file`). Generate a CDI spec for the
   allocation's GPUs (`nvidia-ctk cdi generate --output=<dir>/nvidia.yaml`, and `cdi_spec_dirs = ["<dir>"]` under
   `[engine]`). `harbor run -e podman` with this repository's set flags (`-d embodied-first-exam`, as above) then runs
   each GPU task from a stamped copy whose compose files (`environment/` and `tests/`) ask for the CDI device
   `nvidia.com/gpu=all` instead (`EFE_PODMAN_GPUS` names another, e.g. `nvidia.com/gpu=0` on a node with several GPUs
   for RoboARC, whose renderer needs exactly one), and removes the copies after the job. For a bare `harbor run -p`,
   make that copy yourself:
   ```bash
   c=$(python3 scripts/stamp_mtimes.py stage tasks/<benchmark>/<task> "$(mktemp -d)")
   find "$c" -name docker-compose.yaml -exec sed -i -e 's/- driver: nvidia/- driver: cdi/' \
     -e 's/^\( *\)count: 1$/\1device_ids: ["nvidia.com\/gpu=all"]/' {} +
   python3 scripts/stamp_mtimes.py "$c"
   harbor run -e podman -p "$c" -a oracle -y -o $PWD/jobs
   ```
6. The `rcb_monitor` sidecar can stay "Stopping" after a trial under rootless podman on cgroup v2; stop its container
   (or the `monitor.py` process) by hand. On cgroup v1 the resource caps are not applied (`RCB_LIMITS_ENFORCE` stays 0).
7. On cgroup v2 the containers' CPU caps need the `cpu` controller delegated to your user: when
   `/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers` lacks `cpu` (systemd
   delegates only `memory pids` by default on some distributions), every container fails to start with
   ``crun: controller `cpu` is not available``. An administrator enables it (systemd `Delegate=cpu cpuset io memory
   pids` for `user@.service`); a user cannot.

## Running a two-mode batch (privileged + standard)
```bash
python3 scripts/stamp_mtimes.py tasks                   # first ("Building task images" above)
harbor run -p tasks/robotwin-2 -i robotwin_2_0_<t1>-privileged -i robotwin_2_0_<t2>-privileged -a codex -m openai/gpt-6-astra -n 3 -o $PWD/exps/jobs --job-name <job-priv>
harbor run -p tasks/robotwin-2 -i robotwin_2_0_<t1>-standard ... -a codex -m openai/gpt-6-astra -n 3 -o $PWD/exps/jobs --job-name <job-std>
harbor trial regrade --help                             # re-run the verifier of a recorded trial (a grader error, a missing video)
python3 scripts/write_task_results.py exps/jobs <job> <run-id> "<agent label>" --out <dir outside the repository>   # per-task results (README, video, cost)
```
`CODEX_FORCE_AUTH_JSON=1` uses a ChatGPT-subscription login (`codex login --device-auth`) instead of an API key.
Use an absolute `-o` (compose cp is noisy otherwise); 3 concurrent trials fit one RTX 4090 with headroom for the
separate verifiers. Results (per-task and batch reports) go to the results site and the Hugging Face dataset (Results above), not into the repository.

## Unattended batches (`scripts/run_agent_batch.sh`)
`scripts/run_agent_batch.sh <batch> <base> ...` runs one Harbor-native agent over `<base>-privileged` and `<base>-standard`
(and `<base>-standard-realtime` with `MODES="privileged standard standard-realtime"`) for each task base (a missing twin is skipped), one Harbor job per task and mode. Starting the same command again adds a
lane: every job is claimed by exactly one runner (`$JOBS/.claims/<job>`). The run id is derived as in TAXONOMY "Run ids" and
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
results site with `scripts/write_task_results.py --out` outside the repository (`RESULTS`, default `../rcb_results`
next to the checkout, gets `<batch>/<task>/<run id>/`; `RESULTS=` skips it), updates `$JOBS/<batch>.summary.md`, and
stops its lane when a trial shows a model-account failure.

Each batch's plan (every job, pending until it starts) is `$JOBS/.plan/<batch>.json`, which the runner writes when
it starts.

Runner-side tools (they run on the host, never in a task): `scripts/log_mirror.py` (in the `rcb-log-mirror` container: an
append-only copy of every trial's `agent/` record that neither the agent nor the host user can delete),
`scripts/mem_guard.py` (keeps 2 GiB of host memory available by killing the largest benchmark container first),
`scripts/scan_secrets.py` (the key scan; it loads secrets inside its own process and never prints them),
`scripts/account_failure_check.py` (structured evidence only: Codex's rate limits and last event, Claude Code's result
event). `LOG_MIRROR=0` / `MEM_GUARD=0` skip starting the first two.

## Seeds (which frozen instance a trial runs from)

Every task names its seeds in `task.toml` (`[metadata.seeds]`: `default`, `allowed`, `oracle`; PROTOCOL §2). Each
seed is an instance (`allowed`: a list, a range `{ from = A, to = B }` or `"any"`); the default one is the task
directory as committed. To run another allowed seed, or one
drawn from the allowed list (official batches draw one per trial), let the runner
write a copy and run that:

```bash
python3 scripts/task_seed.py list tasks/<benchmark>/<task>                      # {'default': 0, 'allowed': [0, ...], 'oracle': [...]}
python3 scripts/task_seed.py materialize tasks/<benchmark>/<task> --seed draw --out /tmp/run1   # prints the copy and the seed
harbor run -p /tmp/run1/<task> -a <agent> ...
```

The agent never chooses or sees the list: another seed's instance lives under the privileged task's `tests/seeds/`,
and the copy carries only the drawn one. Every task allows its default seed only today, so
`scripts/run_agent_batch.sh` runs each job from a stamped copy of the task as it is (with the gateway, the copy's
egress is the gateway; with a CPU cap above the host's count, `HOST_CPUS`, the copy has that cap clamped, Resources
above); it materializes a seed per trial once a benchmark allows more than one.

## The agent's time (the cutoff)
Every task gives the agent a fixed wall-clock time, its cutoff: Harbor's `[agent] timeout_sec` in the task's own
`task.toml`, set by the task's author in the pull request that adds or changes the task  `ci_checks/check-cutoffs.py` checks per task: a whole number
of seconds, at most 14400 (`CUTOFF_CAP`), 3600 unless the pull request justifies another; the instruction's closing
`## Time limit`, the README's `Agent time budget` row and, in the standard modes, the sim service's `RCB_WALL_CLOCK_S`
state the same number; nothing else in the instruction states the limit as a duration. A task's privileged and
standard versions have the same cutoff (H.7, the mode registry's `same_cutoff_as`). A benchmark uses one number for all its tasks of a mode unless the pull
request says why.

**What the agent is told.** `normalize` ends every `instruction.md` with `## Time limit`: "You have N seconds to
complete this task. Do not cheat by using online solutions or hints specific to this task.", then what the cutoff means
in the mode (`CUTOFF_NOTE` in `scripts/task_conventions.py`: wall-clock time from the start of the session; at the cutoff
the agent is stopped and only `/app/output/` (privileged) or the episode as it stands (standard modes) is graded;
`/run/rcb-limits/usage.json` gives `time_left_s` and `deadline_utc`; long waits in tool calls count). A benchmark's own
text about its time says "the time limit (`## Time limit`)", never a number.

**When the clock runs.** Harbor counts the cutoff around the agent's run only (`asyncio.wait_for(agent.run(...),
timeout=...)`): after the environment has been built and started and the harness installed, each under a timeout of its
own. A standard-mode `sim` service starts with the environment; what it has not finished starting by then is waited out
inside the agent's time. The service's own clock (`/spec.budget.wall_clock_s`, `meta.time_left_s`) counts the same
number from the agent's first request to the service (kept through a restart) and never runs out before Harbor's; it only
reports, except that RoboARC's service ends the episode when its count reaches 0 (tasks/roboarc/README.md). At the cutoff Harbor stops the agent (`AgentTimeoutError`), collects the artifacts and runs the verifier, so
the trial is graded as it stands: a result, not an infrastructure failure, never run again.

**Official runs** pass no multiplier and add nothing to the instruction (Official runs above), so `## Time limit` is the
last thing the agent reads. `--agent-setup-timeout-multiplier` (slow harness
installs) is fine: set-up is not the agent's time.

**Changing a cutoff** (the author's decision): set the new `[agent] timeout_sec` in both twins, run `python3 scripts/task_conventions.py tasks/<benchmark>/<task> ...` (it rewrites the closing section, the
README row, `RCB_WALL_CLOCK_S` and `DIGEST`), and state old -> new and why in the change (label `cutoff-change`). The task
changes in place and keeps its name; results under another cutoff are a different configuration (`config_key`). Not
derived from the cutoff: the token budget, the resource limits, reset budgets, step caps, verifier timeouts. When
raising one, look at collect-hook and verifier budgets sized for an episode as long as the agent's time (RoboCasa,
RoboCasa365 and RoboCasa-GR1 `COLLECT_TIMEOUT_S`; RoboLab, YAMLab, DexJoCo, BEHAVIOR-1K: their `tasks/<benchmark>/README.md`
pages) and, for Embodied Olympics - Match's exported matches, a match's wall time at its slowdown plus the reviews between points.

## Base images
Every base image is a tag of one of two packages (PROTOCOL §1): `ghcr.io/mll-lab-nu/efe:<name>-<images/<name>/VERSION>` (public), or `ghcr.io/mll-lab-nu/efe-private:<name>-<VERSION>` for an image with `images/<name>/BUILD_ONLY` (org members only): `scripts/build_images.sh`
builds them all, `scripts/push_images.sh` pushes all but the `BUILD_ONLY` ones (needs `docker login ghcr.io` with a token
that has `write:packages`). A new image is a new tag of `efe`, which is public, so nothing needs an admin's visibility
change (a new package would start private, and the API cannot change that). An image with `images/<name>/BUILD_ONLY` (Isaac Sim inside: RoboLab, BEHAVIOR-1K) is never
public: every host builds it (the marker file says how, and what licences and data it needs), and maintainers may keep
a private package for org members.
A files-only image (`images/<name>/FILES.json`) is no docker build: `scripts/files_image.py build <name>` writes it byte
for byte from the repository, so it has the digest the task Dockerfiles pin (`COPY --from=<tag>@sha256:…`), and loads it;
`files_image.py push` pushes those same bytes (`docker push` would recompress the layer). A private one built locally
serves the tasks unchanged on Docker's containerd image store (Docker Engine 29's and Docker Desktop's default); the
classic store resolves a digest only for a pulled image.

## What an agent's container reaches
Every task's `[agent]` allowlist is one list, `HOSTS` in `scripts/set_agent_egress.py`: the model APIs and the package
registries (PyPI: pypi.org, files.pythonhosted.org; apt: deb.debian.org, security.debian.org, archive.ubuntu.com,
security.ubuntu.com, snapshot.ubuntu.com). So `pip install` (or `uv pip install` in the images without pip) and
`apt-get update && apt-get install` work in every agent container, in both modes; GitHub, raw.githubusercontent.com,
Hugging Face and the general web do not answer (PROTOCOL §5, Appendix H.6: the honour rule is the instruction's; the network keeps the
places where solutions are published out of reach). Both installs work with and without the
usage gateway (Debian 12 and 13, Ubuntu 22.04 images).
In the Ubuntu images built on NVIDIA's CUDA base, `apt-get update` warns about NVIDIA's own repository
(developer.download.nvidia.com is not on the list) and goes on; the Ubuntu archives answer.
Before it applies an allowlist, Harbor checks the host kernel once per job by running a small alpine image, and gives
the pull and run 30 s: a slower pull reads as "allowlist unsupported" for the whole job. On docker and podman this
repository's `harbor run` (`scripts/efe.py`) pulls that image first when it is missing.

The list is the one switch.
- Another host for every task: add it to `HOSTS` (to `PACKAGE_HOSTS` too if a run through the gateway should reach it
  directly), update the generators' copies of the list, `python3 scripts/set_agent_egress.py allowlist`,
  `python3 scripts/task_conventions.py tasks/*/*/` (normalize refreshes each DIGEST).
- A run with no restriction at all (the agent may reach anything): run a copy of the tasks, since CI keeps the list
  in `tasks/`:
  `cp -a tasks /some/dir/tasks && python3 scripts/set_agent_egress.py public /some/dir/tasks/*/*/`, then
  `harbor run -p /some/dir/tasks/<benchmark> ...` (with `scripts/run_agent_batch.sh`: a copy of the repository with that `tasks/`,
  and `GATEWAY_EGRESS=task`, or the runner narrows each job's copy again). The instructions' last sentence about the
  network is then no longer true: change `EXTERNAL_TEXT` in `scripts/task_conventions.py` if that becomes the default.

## No tool outside the container (web search off by default)
`scripts/run_agent_batch.sh` turns the harness's web search off unless `WEB_SEARCH=allowed`: Codex gets
`--ak web_search=disabled`, Claude Code `--ak disallowed_tools=WebSearch,WebFetch` (Official runs above). For a bare
`harbor run`, pass the same option yourself. Codex with ChatGPT login searches by default, and it hands the model the
account's connectors, apps, plugins and an image generator unless its config turns them off (`features.apps = false`,
`features.plugins = false`, `features.image_generation = false`, `apps._default.enabled = false`, before any table of
the config); Claude Code under a full claude.ai login loads the account's connectors (`disableClaudeAiConnectors`). An
official run starts the harness without them. For Codex the runner does it with the same switch: it passes
`--ak config=` a copy of `AGENT_CONFIG` (or a config of its own when there is none) in which
`scripts/codex_tools_off.py` has set those features to false (`$JOBS/.agent-config/`), and refuses an `AGENT_CONFIG`
that turns one of them on, and an `AK` that carries its own `config=` (Harbor would keep the last one). A config that
already sets them to false, as a scheduler's own may, is accepted. For a bare `harbor run`:
`--ak config=<the output of scripts/codex_tools_off.py [your config.toml]>`. Claude Code's settings stay the
caller's (`AGENT_CONFIG`). An API key can still request a search directly; the usage gateway
refuses such a request and every path that is not a model call (below, leakage.md).

## Usage gateway (token usage per request, optional)
Off by default: the agent calls its API directly, as Harbor runs it. With `GATEWAY=1`, `scripts/run_agent_batch.sh` starts `scripts/usage_gateway/gateway.py` on the docker bridge (`GATEWAY_BIND`, 172.17.0.1)
and points the agent's base URL at it (`--ae ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL`; a copy of `AGENT_CONFIG` with its
provider `base_url`s rewritten and `supports_websockets = false`). The agent is still Harbor's own `codex` /
`claude-code` with its own credentials: the gateway forwards model requests unchanged to the same API, never stores a key,
and refuses any host that is not a model API (`scripts/set_agent_egress.py` HOSTS), so it is no way around an egress
allowlist.

**Model-API calls only, and the only way out (Official runs above).** The gateway forwards the requests listed per provider
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
`body_unreadable`, with method and path, never a body) and counted in `totals.json` (`refused_paths`, `refused_hosts`,
`refused_server_tools`, `refused_bodies`); the batch summary shows `REFUSED n` in the gateway column. A refusal is an
attempt: the trial is one to look at, and that is all (an attempt does not void a trial, and nothing
tells the agent that trying is forbidden). What a harness sends by itself at start-up without being a model call
(`harness_probes` in `api_paths.json`: Claude Code's `HEAD /api/hello`, in every trial) is refused but neither recorded
nor counted. To add a provider, a path or a client tool type (a new harness
version that declares another one is refused until it is listed), edit `api_paths.json` (default deny; a host without a
provider there gets nothing forwarded).
The model APIs' hosts also serve all of that directly, so with the gateway on each job runs from its own copy of the
task (`$JOBS/.tasks/<job>/`, removed afterwards) whose egress allowlist is the gateway's address and the package
registries (`scripts/set_agent_egress.py only <GATEWAY_BIND>,<PACKAGE_HOSTS>`; Harbor's `--allow-agent-host` can add a
host, not remove one). `GATEWAY_EGRESS=task` keeps the task's own allowlist (the hosts reachable directly; not for
official runs).
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
which have no connectors, and keep the evaluation accounts' connectors disconnected. A Codex API key, a Claude
subscription token and a self-hosted endpoint work with the gateway and the package registries as the only addresses.
The runner waits `GATEWAY_START_WAIT` seconds (10) for the gateway to come up; raise it on busy shared nodes.
Before each job it checks that the gateway still runs and answers `/_gateway/health`; a dead gateway is restarted on its
port (the agents' base URLs keep working), and the lane stops if that fails. A job during which the gateway died gets
`<job>/gateway_down.json`. A model call that fails on the way is recorded as `upstream_failure` in `usage.jsonl` (the
upstream unreachable: the gateway answers 502; the provider's stream broken off; a provider 5xx), counted in
`totals.json` (`upstream_failures`; `failures_in_a_row` up to the latest call). A trial that ends on such failures, or
whose job has `gateway_down.json`, is an infrastructure failure: `write_task_results.py` publishes it as "not a result",
never the agent's 0, and three or more failed calls in a row at its end stop the lane like an account failure
(`scripts/account_failure_check.py`).

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
before logging. Token budget: with the gateway on, a trial that reaches `TOKEN_BUDGET_IN` input or `TOKEN_BUDGET_OUT` output tokens
(default 10B / 10B; 0 = no limit) gets every further model request refused (HTTP 400, "token budget exceeded"), so
the agent stops; `totals.json` records `over_token_budget = 1` and, from the first refused request, `budget_stop`
(`limit` input|output, `first_refused_at` / `last_refused_at`, the input / cached / output counts at the stop, `refused`):
a runner records such a trial as `TokenBudgetExceeded` (not the harness's own exception, which reads as a network or API
error: Codex `NetworkConnectionError` / `NonZeroAgentExitCodeError`, Claude Code `UnknownApiError`), the batch summary marks it, and `write_task_results.py`
counts it as failed (Official runs above). Codex ends its turn on the first refusal, without retrying.
The raw log stores each conversation item once and a request as references to the items it resends, like Codex's and
Claude Code's own session files, and is lossless: `scripts/usage_gateway/rawlog.py cat <trial>/gateway` prints every
request and response in full. The gateway appends to `raw.jsonl.gz` while the trial runs; after each job the runner
compacts it to `raw.jsonl.xz`.
Switches: `GATEWAY=1` (record usage and, by default, raw bodies), `GATEWAY_RAW=0` (usage only; raw bodies are private: they hold the
whole conversation). Known limits: no WebSocket (Codex's built-in provider falls back to HTTPS after a few refused
attempts); Codex's zstd-compressed request bodies are stored as base64, and so not deduplicated, on a runner host
that has neither the `zstandard` module nor the `zstd` program; OpenAI reasoning arrives encrypted. Requests no trial can be matched to go to `<jobs>/.gateway/unattributed.jsonl`.
