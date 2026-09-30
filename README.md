# robot_coding_bench: limited and unlimited tasks

Harbor tasks in which a coding agent controls a simulated robot on a frozen scene instance and is graded by the
native success predicate of the simulator's own benchmark. Five pinned benchmarks, each instance in two modes:

- **unlimited**: full privileged state, unlimited resets and exploration, 60 minutes of agent time; the last trajectory
  submitted before the deadline is graded.
- **limited**: RGB, camera calibration and the robot's own state only; one continuous episode with no reset, in a
  private simulator sidecar that records every action; the sealed episode is graded.

This branch holds the current task versions (`60min-v3`), their registry and settings, and the tooling to check,
smoke-test and evaluate them. Historical task versions, experiment outputs and reports are not included.

## Layout

| Path | Contents |
|---|---|
| `unlimited_tasks/<benchmark>/<family>-unlimited60min-v3-iNN/` | self-contained Harbor task (environment, verifier, oracle) |
| `limited_tasks/<benchmark>/<family>-limited60min-v3-iNN/` | self-contained Harbor task; the scene and simulator live in `environment/server/` (sim sidecar) |
| `<mode>_tasks/<benchmark>/dataset.toml` | Harbor dataset manifest per mode and benchmark |
| `suites/two-modes.json` | registry: source instance, seed, instance SHA-256, and per mode the path, task ID, readiness (`blocked_reason`), checksum, package digest and file fingerprints |
| `suites/two-modes-{limited,unlimited}.json` | per-mode task lists; `suites/task-path-aliases.json` maps older task IDs/paths to these |
| `scripts/two_modes/` | `run.py` (the only supported runner), `check.py` (registry/config check), `lifecycle.py` (isolation and limited episode control) |
| `scripts/vlabench/codex_subscription/` | Harbor agent: Codex CLI with ChatGPT-subscription login only |
| `images/`, `scripts/build_images.sh`, `scripts/robot24/build.py`, `scripts/vlabench/build_local.sh` | pinned simulator base images |
| `ci_checks/` | static contract checks (`run_all.sh`) |
| `docs/TWO_MODES.md`, `docs/PROTOCOL.md`, `docs/prompts/metaworldplus_codex_luna_high_two_modes.md` | protocol and mode definitions |
| `docs/validation/two-modes-v3/` | reorganization report, configuration check and smoke evidence |
| `archive/`, `staging/vlabench/` | only the reference trajectories that the limited-mode oracle smoke replays |

## Tasks

| Benchmark | Families | Instance IDs | Unlimited runnable | Limited runnable | Not runnable (unlimited / limited) |
|---|---:|---:|---:|---:|---:|
| MetaWorld+ (Meta-World 3.1.1, v3) | 50 | 70 | 70 | 69 | 0 / 1 |
| RoboCasa 0.2 | 30 | 30 | 30 | 30 | 0 / 0 |
| RoboCasa365 1.0.1 | 256 | 263 | 263 | 263 | 0 / 0 |
| RoboCasa-GR1 0.2 | 24 | 33 | 33 | 33 | 0 / 0 |
| VLABench | 96 | 104 | 91 | 91 | 13 / 13 |
| **Total** | | **500** | **487** | **486** | |

Not-runnable records stay in the registry and in the denominator (`blocked_reason` says why): 13 VLABench tasks have
no frozen instance at the pinned commit, and MetaWorld+ `sweep` limited has a goal that cannot be determined from the
allowed observations. VLABench's 104 IDs are 96 native tasks plus 8 historical visual aliases that share a physical
instance with their privileged twin, so they are not independent samples. 41 runnable VLABench tasks have no validated
reference trajectory, so their solvability has not been demonstrated.

## Settings

| | Unlimited | Limited |
|---|---|---|
| Observation | full privileged state | RGB, camera calibration, robot proprioception; no object/goal state, reward or success predicate |
| Reset | any number, same instance | none: one continuous episode |
| Steps | no per-trajectory or cumulative cap | MetaWorld+ 500, VLABench 4000, RoboCasa series 3000 (kitchen navigation 1200) controls |
| Agent time | 3600 s (independent watchdog stops the agent) | 3600 s |
| Graded input | last trajectory submitted before the deadline | the sim-sealed server-side episode, including failed actions |
| Grading | two independent replays | online record and two fresh replays must succeed with identical final state |
| Verifier | same container after restart; 7500 s total, 3600 s per replay | separate container, no network; 1900–2000 s |
| Network | agent reaches only the subscription egress proxy (and `sim` in limited); public internet, host gateway and Docker DNS are blocked and probed before every trial | same |
| Container | `cap_drop: ALL`, no-new-privileges, no volumes, internal network | same; the agent container holds no simulator, instance or reference |

Native success predicates, robots, physics and frozen instances are unchanged from the source benchmarks.
Agent-container resources (from `task.toml`):

| Benchmark | Unlimited | Limited (agent container; simulator runs in the sidecar) |
|---|---|---|
| MetaWorld+ | 2 CPU; 8 GB (40 tasks) or 4 GB (30 tasks) | 2 CPU, 4 GB |
| RoboCasa 0.2 | 2 CPU, 8 GB (kitchen navigation 4 CPU, 16 GB) | 1 CPU, 2 GB |
| RoboCasa365 | 2 CPU, 8 GB | 1 CPU, 2 GB |
| RoboCasa-GR1 | 2 CPU, 8 GB | 1 CPU, 2 GB |
| VLABench | 2 CPU, 8 GB (16 tasks: 4 CPU) | 2 CPU, 4 GB |

The model configuration is fixed in `scripts/two_modes/run.py`: Harbor agent `codex_subscription.agent:SubscriptionCodex`,
`openai/gpt-6-luna`, reasoning effort `high`, web search disabled, ChatGPT login only (no API-key fallback), one attempt,
no retry.

## Requirements

- Linux with Docker and Docker Compose; no GPU.
- Harbor 0.23.0: `uv tool install harbor==0.23.0`. The scripts must run with Harbor's Python:
  `export HARBOR_PYTHON="$(dirname "$(readlink -f "$(command -v harbor)")")/python"`.
- For model runs: the standalone Codex CLI on `PATH` and a ChatGPT login (`codex login`, which writes `~/.codex/auth.json`).
- The simulator base images, built locally (they are not available from a public registry):

| Image | Used by | Build |
|---|---|---|
| `ghcr.io/jameskrw/rcb-metaworldplus:0.1.0` | MetaWorld+ | `python3 scripts/robot24/build.py metaworldplus` |
| `ghcr.io/jameskrw/rcb-robocasa365:0.1.0` | RoboCasa365 | `python3 scripts/robot24/build.py robocasa365` |
| `ghcr.io/jameskrw/rcb-robocasa-gr1:0.1.1` | RoboCasa-GR1 | `python3 scripts/robot24/build.py robocasa-gr1` |
| `ghcr.io/jameskrw/rcb-robocasa:0.1.0`, `:0.1.1` | RoboCasa 0.2 | `bash images/robocasa/build.sh` (after the GR1 image) |
| `ghcr.io/jameskrw/rcb-vlabench:0.1.1` | VLABench | `docker build -f images/vlabench/Dockerfile -t ghcr.io/jameskrw/rcb-vlabench:0.1.1 .`, or `bash scripts/vlabench/build_local.sh <vlabench-assets checkout>` |

`build.py` clones the pinned upstream sources and downloads hash-checked assets (tens of GB). The kitchen-navigation
tasks build their own image from public sources, and the public `python:*-slim-bookworm` images are pulled on demand.

## Check (no simulation)

```bash
export HARBOR_PYTHON="$(dirname "$(readlink -f "$(command -v harbor)")")/python"
bash ci_checks/run_all.sh                         # per-task contract checks + scripts/two_modes/check.py
"$HARBOR_PYTHON" scripts/two_modes/run.py list --benchmark robocasa365   # registry rows, including not-runnable ones
```

`check.py` verifies task IDs, frozen instance bytes, network/isolation settings, the absence of budgets in unlimited
runtimes, the limited verifier separation, file fingerprints and dataset digests.

## Smoke test (oracle and nop, no model)

```bash
# the benchmark's representative instance, both modes, oracle and nop
"$HARBOR_PYTHON" scripts/two_modes/run.py smoke --benchmark metaworldplus \
  --output "jobs/smoke-$(date -u +%Y%m%dT%H%M%SZ)"
# a specific instance (source slug or mode directory name)
"$HARBOR_PYTHON" scripts/two_modes/run.py smoke --benchmark robocasa365 \
  --task robocasa365-close-cabinet-privileged-i00 --output "jobs/smoke-$(date -u +%Y%m%dT%H%M%SZ)"
```

A pass is oracle success 1 with deterministic replay and nop success 0. The oracle cannot pass for the 41 VLABench tasks
without a reference, and the limited oracle smoke of the 8 VLABench visual aliases finds no reference at their source path.

## Evaluation (Codex + ChatGPT subscription)

Always use the runner: a plain `harbor run -p ...` installs neither the network rules nor the limited episode
start/stop/seal lifecycle.

```bash
export HARBOR_PYTHON="$(dirname "$(readlink -f "$(command -v harbor)")")/python"
export CODEX_FORCE_AUTH_JSON=1   # required: lets the Codex agent inject ~/.codex/auth.json into the trial
# optional: the runner uses whichever `codex` is on PATH; put a specific standalone release first to pin it, e.g.
# export PATH="$HOME/.codex/packages/standalone/releases/0.158.0-x86_64-unknown-linux-musl/bin:$PATH"

# one task, one mode
"$HARBOR_PYTHON" scripts/two_modes/run.py run --benchmark robocasa365 --mode unlimited \
  --task robocasa365-close-cabinet-unlimited60min-v3-i00 --output "jobs/codex-$(date -u +%Y%m%dT%H%M%SZ)"

# one benchmark and mode, 4 tasks at a time, each in its own output directory
OUT="jobs/codex-metaworldplus-unlimited-$(date -u +%Y%m%dT%H%M%SZ)"
"$HARBOR_PYTHON" scripts/two_modes/run.py list --benchmark metaworldplus | python3 -c '
import json, sys
for r in json.load(sys.stdin):
    m = r["modes"]["unlimited"]
    if not m["blocked_reason"]:
        print(m["path"].split("/")[-1])' |
  xargs -P 4 -I{} "$HARBOR_PYTHON" scripts/two_modes/run.py run --benchmark metaworldplus \
    --mode unlimited --task {} --output "$OUT/{}"
```

- `run` requires `--task`; without `--mode` it runs the task's limited and then unlimited version. One attempt, no
  retry; it refuses to overwrite an existing attempt, so give every run a new output directory.
- Results per run: `<output>/summary.json`; `<output>/<task>-codex-lifecycle.json` (status `success`,
  `task_failure`, `timeout` or `infrastructure_failure`; reward; agent seconds; isolation probe results); the Harbor
  trial in `<output>/<task>-codex/<trial>/` (agent logs, `verifier/reward.json`).
- Timeouts, subscription/API failures, simulator or grading failures and ordinary task failures are recorded separately;
  not-runnable tasks remain in the denominator.

## Known caveats

- The base images exist only where they were built; build them on each machine (see Requirements).
- The runner does not pin the Codex CLI version; record `codex --version` with every run.
- Resources are not uniform within MetaWorld+ and VLABench unlimited (see Settings), which matters under a
  wall-clock budget.
- Unlimited mode runs the privileged runtime in the agent's own container as root; its counters are audit records,
  not tamper-proof. Limited mode keeps the simulator and its record in a separate sidecar.
- Configuration of every task is checked; dynamically, representative instances of every benchmark, controller type
  and mode passed oracle/nop smoke (`docs/validation/two-modes-v3/`), not every instance.
