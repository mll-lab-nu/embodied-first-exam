# Running evaluations

How runs are configured and what makes a run official. The invariants in [invariants.md](invariants.md) bind every
run. The sections "Official runs" to "Results" are the runner's rules. A runner's scheduler checks them at every
launch and retry, and refuses a launch that breaks one.

`scripts/run_agent_batch.sh` applies most of the rules by default. A batch of it is an official run only with
`GATEWAY=1` (the default is 0) and a seed drawn for each trial. By default it runs the task's default seed
([Seeds](#seeds)).

How to set up a host (podman, base images, building task images, the usage gateway) is in
[../operations.md](../operations.md).

## Official runs

A result is official only when its run had all of these:

- **Harbor's native agents** (`-a codex`, `-a claude-code`, ...), configured through environment variables. No agent
  adapter, and no gateway that holds credentials or changes requests.
- **The usage gateway** (`GATEWAY=1`, [../operations.md](../operations.md#the-usage-gateway)). It forwards model-API
  calls only. With the package registries, it is the agent container's only egress. A task that declares open egress
  keeps it ([Network](#network)). The runner flags a trial whose `totals.json` has `refused_paths`,
  `refused_server_tools` or `refused_bodies` for a look.
- **No tool outside the container.** The harness's web search, account connectors, apps, plugins, image generation
  and cloud agents are off ([No tool outside the container](#no-tool-outside-the-container)).
- **A token budget per trial.** The defaults are 10B input tokens (Harbor `n_input_tokens`; cached input counts in
  full) and 10B output tokens (reasoning included): `TOKEN_BUDGET_IN` and `TOKEN_BUDGET_OUT`. The budget is set so high
  that it almost never binds. With the gateway, going over either one stops the agent and fails the trial
  (`over_token_budget = 1`). The first refusal also writes `budget_stop` into `totals.json`, and the runner labels the
  trial `TokenBudgetExceeded`, not a harness or network error. A standard or realtime task is instead graded on the
  state its session ended in ([eai-standard.md](eai-standard.md#agent-ended-episodes)). A batch run with another
  budget records it in its results' metadata.
- **The task's own cutoff**, with no multiplier (`--timeout-multiplier`, `--agent-timeout-multiplier`, an agent
  `override_timeout_sec`).
- **Nothing added to the instruction**: no prompt template and no extra instruction, in `AK` or elsewhere.
- **The runner's seed, the task's network, and reruns only after an infrastructure failure** (the next three
  sections).
- **The effective configuration recorded with the result** ([Results](#results)).

## Seeds

The seed is the runner's, never the agent's.

- A task's default seed is `[metadata] instance_seed`: the task directory as committed.
- The seeds a runner may draw from are `[metadata.seeds] allowed`: a list, a range `{ from = A, to = B }` or `"any"`.
  Without the table, the default seed is the only one. `oracle` names the seeds the reference solution is for
  ([tasks.md](tasks.md#seeds)).
- An official batch draws one seed uniformly per trial. A run on the default seed only is not official, and records
  `default-only`.
- The verifier grades the drawn seed's instance from its own copy (with `build = "runtime"`: from its own seed file).

To run another allowed seed, or one drawn from the allowed list, let the runner write a copy and run that:

```bash
python3 scripts/task_seed.py list tasks/<benchmark>/<task>                      # {'default': 0, 'allowed': [0, ...], 'oracle': [...]}
python3 scripts/task_seed.py materialize tasks/<benchmark>/<task> --seed draw --out /tmp/run1   # prints the copy and the seed
harbor run -p /tmp/run1/<task> -a <agent> ...
```

The agent never chooses or sees the list. Another seed's instance lives under the privileged task's `tests/seeds/`,
with the seed's other files and text (`seed.toml`). The copy carries only the drawn one.

`scripts/run_agent_batch.sh` runs each job on the task's default seed (`default-only`), from a stamped copy of the
task as it is. With the gateway, the copy's egress is the gateway. With a CPU cap above the host's count
(`HOST_CPUS`), the copy has that cap clamped ([resources.md](resources.md#running-with-caps)). For an official batch,
draw each trial's seed with `task_seed.py materialize --seed draw` and run the copies.

## Network

The default is the allowlist (H.6). Whether a task has open network is its author's decision, declared in Harbor's own
field, `[agent] network_mode = "public"`. The runner applies the declaration:

- an allowlist task's copy is narrowed to the gateway and the package registries
  (`scripts/set_agent_egress.py only`);
- an open task's copy is left open. The gateway still records its usage.

`python3 scripts/set_agent_egress.py network <task>` prints the declaration. `network` is part of the recorded
configuration, so open-network results are never ranked with allowlist ones.

**The allowlist.** Every task's `[agent]` allowlist is one list, `HOSTS` in `scripts/set_agent_egress.py`: the model
APIs and the package registries.

- PyPI: pypi.org, files.pythonhosted.org.
- apt: deb.debian.org, security.debian.org, archive.ubuntu.com, security.ubuntu.com, snapshot.ubuntu.com.

So `pip install` (or `uv pip install` in the images without pip) and `apt-get update && apt-get install` work in
every agent container, in every mode, with and without the usage gateway (Debian 12 and 13, Ubuntu 22.04 images).
GitHub, raw.githubusercontent.com, Hugging Face and the general web do not answer. The network keeps the places where
solutions are published out of reach. In the Ubuntu images built on NVIDIA's CUDA base, `apt-get update` warns about
NVIDIA's own repository (developer.download.nvidia.com is not on the list) and goes on.

Before it applies an allowlist, Harbor checks the host kernel once per job by running a small alpine image. It gives
the pull and the run 30 s, and a slower pull reads as "allowlist unsupported" for the whole job. On docker and podman,
this repository's `harbor run` (`scripts/efe.py`) pulls that image first when it is missing.

**Changing it.** The list is the one switch.

- To add a host for every task, add it to `HOSTS` (and to `PACKAGE_HOSTS` if a run through the gateway should reach
  it directly). Then run `python3 scripts/set_agent_egress.py allowlist` and
  `python3 scripts/task_conventions.py tasks/*/*/` (normalize refreshes each `DIGEST`).
- For a run with no restriction at all, run a copy of the tasks, since CI keeps the list in `tasks/`:
  `cp -a tasks /some/dir/tasks && python3 scripts/set_agent_egress.py public /some/dir/tasks/*/*/`, then
  `harbor run -p /some/dir/tasks/<benchmark> ...`. With `scripts/run_agent_batch.sh`, use a copy of the repository
  with that `tasks/`. The copies say `network_mode = "public"`, so the runner keeps each job's copy open,
  `set_agent_egress.py allowlist` skips them, and their results record `network` = open. The instructions' Network
  line does not hold for such a run: `LIMITS_NETWORK` in `scripts/task_conventions.py` is the text every allowlist
  task carries.

## Infrastructure failures: rerun

The rule is H.5. This is how the runner applies it.

- An infrastructure failure is what `scripts/write_task_results.py` publishes as "not a result":
  - the verifier's `infra_error` or `grader_error`;
  - no `reward.json`;
  - a Harbor exception other than the agent's cutoff;
  - a model-account or usage-gateway failure (`scripts/account_failure_check.py`).
- It needs positive evidence. A trial is not voided because it scored 0. The agent's own end, its cutoff and its
  token budget are results and are never rerun.
- The void attempt's directory is moved aside (e.g. into `_superseded/`) and never counted. The rerun starts from a
  new environment with the first attempt's recorded configuration. A rerun that fails for infrastructure too is
  voided the same way and may be rerun again. Until an attempt gives a result, the task × run id is reported as an
  infrastructure failure. A launch that never started a trial is no attempt.
- The rule has one implementation, `scripts/retry_policy.py` (`decide`, `check_attempts`), tested by the required CI
  job. A runner's scheduler uses it. `write_task_results.py` keeps every attempt of a task × run id in
  `attempts.json`. It flags a sequence that breaks the rule (`attempts_over_cap`: an attempt after a result, or a
  rerun with another configuration).
- In-trial crash recovery (a sidecar that replays its journal and resumes the episode) is the service layers'
  implementation, not a rule. A crash it cannot recover is an infrastructure failure, unless every crash was the
  agent's (below).

**Standard and realtime modes.** The live record is the verdict (H.4). An infrastructure failure is one where that
record gives no verdict on the agent:

- `final.json` is missing, unreadable or not finalized (`finalized`: the verdict is on disk, written before any video);
- the sidecar gave up after crashes that were not all inside the agent's calls (`sim_crashed`);
- it could not restore the episode after a crash (`resume_failed`, whatever crashed);
- it ended a native call still unfinished 60 s past the service's own per-call cap, `max_call_wall_s`
  (`call_watchdog`, operations capability; never counted from the request's deadline);
- the scene did not start from the frozen instance, at the start or after a reset (`instance_mismatch`).

Only what the service itself records as `infra_error = 1` (or a missing, unreadable or unfinalized record) is one. A
grader never infers it from missing fields.

What the agent's commands caused stays a result. A rerun would be a free second attempt. These are results:

- crashes all inside its calls (`sim_crashed_on_call`);
- a simulator error its actions raised (realtime: a simulator error or crash after the agent's first command,
  [eai-standard.md](eai-standard.md#realtime));
- the cutoff, no actions, a failed settle or hold;
- a crash or error while the service runs a settle or hold window on the agent's final state (it counts as one inside
  the agent's last call).

The video is never an infrastructure failure: a render that fails or runs out of time loses only the video. A resume
that continued from a state that does not match its checkpoint exactly (`approx` resume class,
`resume_state_mismatch = 1`) keeps its live verdict and is flagged for audit.

## Results

Results are not committed. They are published on the [results site](https://www.embodied-first-exam.ai) and the
Hugging Face dataset, keyed by run id `<harness>-<model>-<effort>` (the model token with underscores:
`codex-gpt6_luna-xhigh`; [../TAXONOMY.md](../TAXONOMY.md#run-ids)). Provider, tier and settings go in the metadata.

`scripts/write_task_results.py` writes three files per task and run id:

- `README.md`;
- `config.json`, the trial's effective configuration: `protocol_version`, `mode`, `cutoff_s`, `reset_budget`,
  `slowdown`, `seed`, `network`, `validated`, `set`, `oracle`, `service_protocol`, `digest`, the result, whether it
  counts, and the first-attempt result `first_success`. In the standard and realtime modes `first_success` is
  `reward.json`'s. Where the verifier does not write it, it is the graded success if no reset was made, else 0. A
  trial whose digest is neither the task's `DIGEST` nor that of the runner's copy keeps only what its name says, and
  its other fields are `"legacy"`;
- `attempts.json`.

**Rankings.** The batch summary and the results site compare trials only within one comparable configuration
(`task_conventions.config_key`: protocol version, mode, cutoff, reset budget, slowdown, network).

- They report success together with cost: tokens, money, turns, wall clock, simulation steps.
- They align reasoning effort, `max_turns` and the token budget before comparing agents.
- Validated and unvalidated tasks (`validated_of`: `[metadata] validated`, else `oracle = "full"`) are ranked
  together. Totals count every core task. The flag is shown as a marker and may be used as a filter.

**The core set.** The main table and every headline number (success rates, rankings, totals) count the core set
only: every mode directory of the tasks listed in [`core_set.toml`](../core_set.toml) (`task_conventions.core_tasks()`;
`set_of`: `core` for every mode of a listed task, else `excluded`). Task directories the list leaves out stay in the
repository under their names and are not evaluated by official runs. Results they already have are kept and shown
marked. The batch summary marks them in their configuration's table and leaves them out of its rate. `set` in
`config.json` is the value when the result was written; a report derives it from `docs/core_set.toml` at the commit
it publishes.

## The agent's time

Every task gives the agent a fixed wall-clock time, its cutoff: Harbor's `[agent] timeout_sec` in the task's own
`task.toml`. The task's author sets it in the pull request that adds or changes the task
([tasks.md](tasks.md#tasktoml)):

- 3600 s unless the pull request justifies another number;
- at most 14400 s (`CUTOFF_CAP`);
- the same for the same task in privileged mode (H.7);
- one number for a benchmark's tasks of a mode, unless the pull request says why.

`ci_checks/check-cutoffs.py` checks per task that the number is a whole number of seconds within the cap. It also
checks that the same number is stated by the Time line of the instruction's `## Limits`, by the README's time-limit
row and, in the standard and realtime modes, by the sim service's `RCB_WALL_CLOCK_S`. Nothing else in the instruction
states the limit as a duration.

**What the agent is told.** `normalize` ends every `instruction.md` with `## Limits`. Its Time line gives the task's
number and what the cutoff means in the mode (`LIMITS_TIME` in `scripts/task_conventions.py`):

- it is wall-clock time from the start of the session;
- at the cutoff the agent is stopped, and only `/app/output/` (privileged) or the episode as it stands (standard and
  realtime; with resets, the last one) is graded;
- `/run/rcb-limits/usage.json` gives `time_left_s` and `deadline_utc`;
- long waits in tool calls count.

A benchmark's own text about its time says "the time limit (Limits)", never a number.

**When the clock runs.** Harbor counts the cutoff around the agent's run only
(`asyncio.wait_for(agent.run(...), timeout=...)`). The environment is built and started and the harness installed
before it, each under a timeout of its own. A `sim` service starts with the environment, and what it has not finished
starting by then is waited out inside the agent's time. The service's own clock (`/spec.budget.wall_clock_s`,
`meta.time_left_s`) counts the same number from the agent's first request to the service, kept through a restart, so
it never runs out before Harbor's ([eai-standard.md](eai-standard.md#the-agents-clock)). It only reports, except that
RoboARC's service ends the episode when its count reaches 0 (`tasks/roboarc/README.md`). At the cutoff Harbor stops
the agent (`AgentTimeoutError`), collects the artifacts and runs the verifier. The trial is graded as it stands: a
result, not an infrastructure failure, never run again.

Official runs pass no multiplier and add nothing to the instruction, so `## Limits` is the last thing the agent reads.
`--agent-setup-timeout-multiplier` (for slow harness installs) is fine: set-up is not the agent's time.

**Changing a cutoff** is the author's decision.

1. Set the new `[agent] timeout_sec` in every mode of the task.
2. Run `python3 scripts/task_conventions.py tasks/<benchmark>/<task> ...`. It rewrites `## Limits`, the README row,
   `RCB_WALL_CLOCK_S` and `DIGEST`.
3. State old → new and why in the pull request (label `cutoff-change`).

The task changes in place and keeps its name. Results under another cutoff are a different configuration
(`config_key`). The cutoff does not set the token budget, the resource caps, reset budgets, step caps or verifier
timeouts. When raising it, check the collect-hook and verifier budgets sized for an episode as long as the agent's
time: RoboCasa, RoboCasa365 and RoboCasa-GR1 `COLLECT_TIMEOUT_S`; RoboLab, YAMLab, DexJoCo and BEHAVIOR-1K in their
`tasks/<benchmark>/README.md`; and for Embodied Olympics - Match's exported matches, a match's wall time at its
slowdown plus the reviews between points.

## Resources

Every resource number is a cap for one container. Where each is written, how the caps are chosen, who enforces them
and what a trial records: [resources.md](resources.md). How a run sets the switches and places trials:
[resources.md](resources.md#running-with-caps).

## Agent logs and timelines

Harbor keeps, per trial, `agent/codex.txt` (every message, command and output), `agent/trajectory.json` and the raw
Codex session (`agent/sessions/`). Run Codex with `--ak reasoning_summary=detailed` to also keep reasoning summaries.
Otherwise reasoning is stored encrypted.

## Recordings

- **Every trial has a video** ([tasks.md](tasks.md#grading)). The runner flags a finished, graded trial without a
  playable `*.mp4` in `verifier/`, `artifacts/data/` or `artifacts/out/` (`no_video`, with the reason it can read).
  The exception is a privileged trial whose agent submitted no trajectory that replays.
- **A missed video** (the render ran out of its time bound, crashed, or the task rendered none) is rendered afterwards
  from the recorded trajectory in the task's own image. That happens only where a post-hoc replay is allowed, on the
  same host class when the replay is only reproducible there. It is kept only when the replay reaches the recorded
  final state, and `replay.regenerated.json` next to it says how. The grade is never touched, and the agent is never
  rerun for a video.
- **Standard and realtime modes.** No replay grades the episode (H.4). The video is a post-hoc replay by default, and
  a live recording where the benchmark's simulator is not verified bit-wise replayable. Either way the verdict is on
  disk first (`final.json` `finalized`; `video_pending` while the video is made), and `final.json` says
  `video_source` (`live` or `render`). Published videos follow the same rule and keep the label.
- **The first episode (with resets).** Only benchmarks on the sidecar service (`rcb_service.py`) graded by the shared
  grader (`embodied_first_exam/standard/sidecar/grade.py`) keep the first episode (`trajectory.first.npz`,
  `replay.first.mp4`) and how it ended. `first_success` is the graded success when `resets` = 0. After a reset it is
  the first episode's own end judgement, or null when that is not on record. A task whose sidecar runs a service of
  its own reports `resets` only: its `first_success` is the graded success when `resets` = 0, else 0, and the first
  episode is not kept.
- **RoboTwin 2.0, standard mode.** The sim service records `live.mp4`: six views, frames only while physics runs and
  something moves, each stamped with the agent's call and wall and sim time. It is rendered from the trajectory after
  the verdict, in the same pass as `replay.mp4`, so it costs the agent nothing. `RCB_LIVE=realtime` captures during
  the episode instead. The service also records the exact actions of every call and a crash-safe trajectory.
- **Privileged mode.** The agent owns the simulator, so nothing it produces is evidence. `rcb_traj.Session` still
  dumps every rollout's per-step drive targets to `/app/output/rcb_trace/` (`RCB_AGENT_TRACE_DIR`, capped at 300
  files / 400 MB). After writing the verdict, the verifier reconstructs videos of the agent's last six rollouts into
  `agent_sessions/`, with an `index.json` of all of them (`agent_traces`, `agent_trace_steps`, `agent_trace_videos`
  in `reward.json`). These are self-reported: an agent that teleports objects through `exec_code` will not replay
  faithfully.

## Running a batch by hand

```bash
python3 scripts/stamp_mtimes.py tasks                   # first (../operations.md, "Building task images")
harbor run -p tasks/robotwin-2 -i robotwin_2_0_<t1>-privileged -i robotwin_2_0_<t2>-privileged -a codex -m openai/gpt-6-astra -n 3 -o $PWD/exps/jobs --job-name <job-priv>
harbor run -p tasks/robotwin-2 -i robotwin_2_0_<t1>-standard ... -a codex -m openai/gpt-6-astra -n 3 -o $PWD/exps/jobs --job-name <job-std>
harbor trial regrade --help                             # re-run the verifier of a recorded trial (a grader error, a missing video)
python3 scripts/write_task_results.py exps/jobs <job> <run-id> "<agent label>" --out <dir outside the repository>
```

- `CODEX_FORCE_AUTH_JSON=1` uses a ChatGPT-subscription login (`codex login --device-auth`) instead of an API key.
- Use an absolute `-o`; compose cp is noisy otherwise.
- 3 concurrent trials fit one RTX 4090 with headroom for the separate verifiers.
- Results go to the results site and the Hugging Face dataset ([Results](#results)), not into the repository.

## Unattended batches

`scripts/run_agent_batch.sh <batch> <base> ...` runs one Harbor-native agent over `<base>-privileged` and
`<base>-standard` for each task base, one Harbor job per task and mode. `MODES="privileged standard realtime"` adds
`<base>-realtime`. A mode the base does not have is skipped.

- Starting the same command again adds a lane. Every job is claimed by exactly one runner (`$JOBS/.claims/<job>`).
- The run id is derived as in [../TAXONOMY.md](../TAXONOMY.md#run-ids), and checked.
- Each batch's plan (every job, pending until it starts) is `$JOBS/.plan/<batch>.json`, written when the runner
  starts.

Configuration is Harbor's own:

| What | How |
|---|---|
| agent, model, effort | `AGENT=codex` or `claude-code`, `MODEL`, `EFFORT` (`--ak reasoning_effort`), more options in `AK` |
| OpenRouter (Codex) | `OPENAI_API_KEY=<OpenRouter key> OPENAI_BASE_URL=https://openrouter.ai/api/v1`. For long runs, declare OpenRouter as a provider of its own in the `AGENT_CONFIG` file (`model_provider = "openrouter"`, its `base_url`, `env_key = "OPENAI_API_KEY"`, `wire_api = "responses"`, `supports_websockets = false`). As "OpenAI", Codex compacts a full context through an endpoint OpenRouter does not serve, and the run stops ("Error running remote compact task"). |
| OpenRouter (Claude Code) | `ANTHROPIC_BASE_URL=https://openrouter.ai/api` with the key in `ANTHROPIC_API_KEY` |
| ChatGPT login (Codex) | `CODEX_FORCE_AUTH_JSON=1` (Harbor uploads `~/.codex/auth.json` into each trial) |
| Claude subscription | `CLAUDE_FORCE_OAUTH=1` and `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`) |
| Azure OpenAI, retries | a Codex `config.toml` passed as `AGENT_CONFIG` (`--ak config=<file>`): the Azure provider, and `request_max_retries` / `stream_max_retries` for transient upstream failures |
| credentials file | `ENV_FILE` (Harbor's `--env-file`); without it the variables come from the runner's environment |

Provider, service tier and other settings go in the results metadata, not in the run id. Use one key per batch, with a
spending cap.

After each job the runner:

- scans the job for keys and redacts them;
- writes the per-task results with `scripts/write_task_results.py --out`, outside the repository (`RESULTS`, default
  `../rcb_results` next to the checkout, gets `<batch>/<task>/<run id>/`; `RESULTS=` skips it);
- updates `$JOBS/<batch>.summary.md`;
- stops its lane when a trial shows a model-account failure.

**Runner-side tools.** They run on the host, never in a task.

- `scripts/log_mirror.py`, in the `rcb-log-mirror` container: an append-only copy of every trial's `agent/` record
  that neither the agent nor the host user can delete.
- `scripts/mem_guard.py`: keeps 2 GiB of host memory available by killing the largest benchmark container first.
- `scripts/scan_secrets.py`: the key scan. It loads secrets inside its own process and never prints them.
- `scripts/account_failure_check.py`: structured evidence only (Codex's rate limits and last event, Claude Code's
  result event).

`LOG_MIRROR=0` and `MEM_GUARD=0` skip starting the first two.

## No tool outside the container

`scripts/run_agent_batch.sh` turns the harness's web search off unless `WEB_SEARCH=allowed`. Codex gets
`--ak web_search=disabled`, and Claude Code gets `--ak disallowed_tools=WebSearch,WebFetch`. For a bare `harbor run`,
pass the same option yourself.

Codex with a ChatGPT login searches by default. It also hands the model the account's connectors, apps, plugins and
an image generator unless its config turns them off: `features.apps = false`, `features.plugins = false`,
`features.image_generation = false` and `apps._default.enabled = false`, before any table of the config. Claude Code
under a full claude.ai login loads the account's connectors (`disableClaudeAiConnectors`).

An official run starts the harness without them.

- For Codex, the runner passes `--ak config=` a copy of `AGENT_CONFIG` (or a config of its own when there is none) in
  which `scripts/codex_tools_off.py` has set those features to false (`$JOBS/.agent-config/`).
- It refuses an `AGENT_CONFIG` that turns one of them on, and an `AK` that carries its own `config=` (Harbor would keep
  the last one). A config that already sets them to false is accepted.
- For a bare `harbor run`: `--ak config=<the output of scripts/codex_tools_off.py [your config.toml]>`.
- Claude Code's settings stay the caller's (`AGENT_CONFIG`).

An API key can still request a search directly. The usage gateway refuses such a request, and every path that is not a
model call ([../operations.md](../operations.md#the-usage-gateway), [leakage.md](leakage.md)).
