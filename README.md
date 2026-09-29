# TopoGym

**TopoGym** is a Genesis-based simulator and a [Harbor](https://github.com/harbor-framework/harbor)
benchmark for robotic topology manipulation. A coding agent controls a robot in a **frozen scene instance**
and produces one replayable trajectory. Tasks include assembling interlocking puzzles, freeing trapped
objects, threading ropes, untying knots and flattening cloth. Physics runs on **Genesis 1.2.1 / CUDA**;
RGB observations use **Nyx + compact_lab**.

The Harbor layer follows **robot_coding_bench** (`dev/qineng@fa59c1a6`): self-contained tasks, unlimited
and limited evaluation modes, and a verifier in its own sandbox. Scores are binary, with numeric
diagnostics and replay videos. There are **28 Harbor tasks: 13 manipulation families plus a cube
example, each in two modes**. See the [protocol](docs/rcb/PROTOCOL.md),
[task manifest](tasks/dataset.toml) and [中文 CLI 手册与验收记录](docs/rcb/README.md).

## Run

The host needs an NVIDIA GPU, a compatible driver, Docker with Compose, and NVIDIA Container Toolkit
with the `nvidia` runtime available. Containers need CUDA and Vulkan for physics and Nyx rendering.
Start with **one concurrent trial**: observed GPU memory use is roughly 2–3 GB for rigid tasks and up
to 10 GB for FEM tasks, with headroom needed for other GPU work. Run commands from the repository root.

```bash
git clone git@github.com:LUIGIVAMPER/topogym.git
cd topogym

# Once per host; uv must already be installed. Reuse this venv if it exists.
uv venv --python 3.12 .venv-harbor
uv pip install --python .venv-harbor/bin/python 'harbor==0.23.0'
source .venv-harbor/bin/activate

scripts/build_images.sh topogym
nvidia-smi
```

**Build the base image locally**: `ghcr.io/luigivamper/rcb-topogym:0.1.0` is not currently published.
`scripts/push_images.sh` disables publication pending confirmation of Nyx redistribution terms.
Rebuild after changing simulator code; task containers use the source copied into the image at build
time. Use the local-checkout workflow; `harbor run --repo` has not been validated for TopoGym.
Keep the venv active for helper scripts and CI, which also need Python 3.11+.

Choose credentials using [.env.example](.env.example) or the [full CLI guide](docs/rcb/README.md).
For an OpenAI API-key run:

```bash
# Set OPENAI_API_KEY in this shell, or in a local .env passed with --env-file .env.
unset CODEX_FORCE_AUTH_JSON CODEX_AUTH_JSON_PATH

harbor run -p "$PWD/tasks/topogym-cast-coil-i00" \
  -a codex -m openai/gpt-6-luna --ak version=0.157.0 --ak reasoning_effort=max \
  -n 1 -k 1 -o "$PWD/jobs" --job-name "coil-u-$(date +%Y%m%d-%H%M%S)"

# Limited twin: the robot is exposed through a service, with no reset.
harbor run -p "$PWD/tasks/topogym-cast-coil-i00-limited" \
  -a codex -m openai/gpt-6-luna --ak version=0.157.0 --ak reasoning_effort=max \
  -n 1 -k 1 -o "$PWD/jobs" --job-name "coil-l-$(date +%Y%m%d-%H%M%S)"

harbor view "$PWD/jobs"
```

`-n` controls concurrent trials; `-k` controls attempts per task. Use absolute task/output paths and
a new job name per run. Each task currently gives the agent **5,400 seconds**; builds, agent setup,
artifact collection and verification take additional time.

### Codex with a ChatGPT subscription

The existing Cast Coil tutorial uses **GPT-6 Luna / Max** through Harbor's standard `codex` agent.
Install the host Codex CLI if needed, then create a file-based ChatGPT login cache for Harbor.
Device-code login must be enabled for the account or workspace; see the official
[Codex authentication guide](https://learn.chatgpt.com/docs/auth).

```bash
# First login only; skip login if a working file-based ChatGPT login already exists.
codex -c 'cli_auth_credentials_store="file"' login --device-auth
codex -c 'cli_auth_credentials_store="file"' login status

unset OPENAI_API_KEY OPENAI_BASE_URL OPENROUTER_API_KEY
export CODEX_FORCE_AUTH_JSON=1
export CODEX_AUTH_JSON_PATH="${CODEX_HOME:-$HOME/.codex}/auth.json"

COIL_JOB="coil-luna-max-$(date +%Y%m%d-%H%M%S)"
harbor run -p "$PWD/tasks/topogym-cast-coil-i00" \
  -a codex -m openai/gpt-6-luna \
  --ak version=0.157.0 --ak reasoning_effort=max \
  --ak config='{"forced_login_method":"chatgpt"}' \
  -n 1 -k 1 -o "$PWD/jobs" --job-name "$COIL_JOB"

python -m json.tool "$PWD/jobs/$COIL_JOB"/*/verifier/reward.json
```

For limited mode, use `topogym-cast-coil-i00-limited` and a new job name. Harbor injects the selected
login cache; `forced_login_method=chatgpt` restricts Codex to ChatGPT authentication
([configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)).
The `openai/` model prefix does not select the authentication method.

### Short rollout → replay check

After subscription login, this runs the same unlimited Cast Coil task with an additional instruction:
render one frame, execute **8 hold actions**, save `gen.py` and `trajectory.npz`, then exit for
independent verification. It checks the pipeline; holding still is expected to score **0**.

```bash
COIL_JOB="coil-smoke-$(date +%Y%m%d-%H%M%S)"
harbor run -p "$PWD/tasks/topogym-cast-coil-i00" \
  -a codex -m openai/gpt-6-luna \
  --ak version=0.157.0 --ak reasoning_effort=max \
  --ak config='{"forced_login_method":"chatgpt"}' \
  --extra-instruction-path "$PWD/docs/rcb/cast_coil_smoke.instruction.md" \
  --agent-timeout-multiplier 0.1 --verifier-timeout-multiplier 0.035 \
  -n 1 -k 1 -o "$PWD/jobs" --job-name "$COIL_JOB"

python -m json.tool "$PWD/jobs/$COIL_JOB"/*/verifier/reward.json
harbor view "$PWD/jobs"
```

Expected evidence: no trial exception, `verifier_environment_mode="separate"`, the submitted trajectory,
`n_actions=8`, `sim_steps=8`, `grader_error=0`, `video_rendered=1`, and a nonempty `verifier/replay.mp4`.
A zero score alone does not establish that replay ran. Agent/verifier limits are 540/598.5 seconds;
setup is additional. This command has been checked as Harbor configuration, but has not yet been run
with a real model and does not cover the limited service.

Harbor's `claude-code` agent and the vendored `harbor_agents.codex_chatgpt:CodexChatGPT` /
`harbor_agents.codex_openrouter:CodexOpenRouter` adapters are also available. Custom adapters need
`PYTHONPATH="$PWD"`; provider-specific credentials and examples are in the [CLI guide](docs/rcb/README.md).

## Layout

```text
tasks/                              # 28 self-contained Harbor tasks + dataset.toml
├── topogym-<family>-i00/            # unlimited: agent controls the simulator
│   ├── instruction.md task.toml README.md
│   ├── environment/                # Dockerfile, GPU compose, instance.json, rcb_topogym.py
│   ├── tests/                      # separate verifier image, grade.py, own instance/tooling
│   └── solution/                   # oracle, when implemented
└── topogym-<family>-i00-limited/     # same instance, robot as a service
    ├── environment/                # Python client + GPU sim/ sidecar
    ├── tests/                      # separate grader over the sidecar's evidence
    └── solution/
images/topogym/                     # simulator image, solution scrub, source fingerprint
harbor_agents/                     # ChatGPT / OpenRouter model gateways
scripts/                           # image build, task generation, batches, results
ci_checks/                         # structure, verifier isolation, tooling, manifest
docs/rcb/                          # CLI guide, protocol, limited protocol, taxonomy
topogym/                           # simulator: config, Env, world, robot, tasks, sensors
assets/                            # robot models and authored task assets
tests/                             # simulator contracts, unit and real runtime tests
solvability_proof/ demos/            # proof catalogs and recorded demonstrations
jobs/ runs/ task_rollouts/          # local execution evidence (gitignored)
legacy/                            # archived implementations; outside active runtime
```

## The example task (`topogym-cube-pick-place-i00`)

A Franka Panda with a Robotiq 2F-85 gripper lifts a cube, holds it, puts it back, opens the gripper,
withdraws and lets the cube settle. Assisted grasping (`contact_weld_v1`) is enabled for this instance.
`from rcb_topogym import Session` exposes reset, recording, replay and thin motion primitives.
The agent saves a `(T, 8)` joint-target-plus-gripper trajectory in `/app/output/trajectory.npz`.
The separate verifier replays it twice and records a video.

For an infrastructure check without model credentials, run the tasks sequentially:

```bash
CHECK_JOB="cube-check-$(date +%Y%m%d-%H%M%S)"
harbor run -p "$PWD/tasks" -i 'topogym-cube-pick-place-i00*' \
  -a oracle -n 1 -k 1 -o "$PWD/jobs" --job-name "$CHECK_JOB-oracle"
harbor run -p "$PWD/tasks" -i 'topogym-cube-pick-place-i00*' \
  -a nop -n 1 -k 1 -o "$PWD/jobs" --job-name "$CHECK_JOB-nop"
```

Expected: oracle **1**, nop **0** in each mode. Earlier acceptance runs achieved these scores;
the full two-mode matrix has not been rerun after later shared-tooling and history changes.
The other 13 families do **not** yet have Harbor oracles; their `solution/solve.sh` exits with an
error. Use a model agent for them.

## TopoGym tasks (`topogym-<family>-i00`)

The 13 manipulation families are `blanket-flatten`, `buzz-wire-3d`, `cast-coil`, `cast-keyhole`,
`fiber-bundling`, `hedgehog-in-cage`, `horseshoe-ring`, `interlocked-claws`, `knot-untying`,
`lock-picking`, `orbits`, `rope-threading` and `slotted-post-ring`. Each task README specifies its
robot, variation, seed, grasping mode and success predicate. A Harbor task fixes one instance;
the simulator's broader variation catalog is separate.

Tooling records one row of joint targets and gripper widths per control step: `(T, 8)` for Panda/Robotiq,
`(T, 14)` for ALOHA. Instances are frozen in `instance.json`; task digests are in `tasks/dataset.toml`.
GPU state hashes and initial-state agreement are diagnostics, not pass conditions. Unlimited success
requires both graded replays to succeed; limited success requires the live episode and its replay.

## Two evaluation modes

| | **unlimited** (`topogym-<family>-i00`) | **limited** (`topogym-<family>-i00-limited`) |
|---|---|---|
| Simulator | In the agent container | In a GPU `sim` sidecar the agent cannot open |
| Reset | Return to the frozen initial state as often as needed | None; one trial is one episode |
| Observations | Object state, predicate source, robot state, RGB/depth | RGB, optional depth, calibration and proprioception |
| Actions | `Session` primitives or low-level `step` | `submit` chunks of `joint_position` or `ee_pose`; stateless FK/IK |
| Deliverable | Agent saves `trajectory.npz` and `gen.py` | Service records the trajectory and episode evidence |
| Verification | Separate sandbox; two graded replays, then a video replay | Sidecar checks live/replay success and renders; separate grader reads its evidence |

The limited client uses **`rcb-limited/2.2`**: `get_obs`, `submit`, `fk` and `ik`.
See the [limited protocol](docs/rcb/LIMITED_MODE_PROTOCOL.md).

## Anti-cheat design (what an agent can and cannot touch)

- **Verifier isolation.** Every task sets `environment_mode="separate"`. The agent container stops
  before verification; the verifier has its own tooling and frozen instance.
- **Solution scrub.** Image builds remove planning code, agent experiments and reference motions.
  Harbor mounts `solution/` only for the oracle agent.
- **Limited evidence.** The sidecar owns the episode record. After the agent stops, the collect hook
  signals it to finalize, replay and render; the agent cannot supply the grading record.
- **Network access.** Egress is public by default. For model-API-only access, run
  `scripts/set_agent_egress.py allowlist`, then `(cd tasks && harbor add --scan .)` to refresh digests.
  Use `public` and rescan to restore public access.
- **Cost accounting.** Unlimited session logs are agent-controlled and labeled self-reported;
  limited logs are service-owned. Harbor also records agent wall time and token usage.

## Running a two-mode batch

After configuring credentials, run the two jobs sequentially:

```bash
BATCH="topogym-$(date +%Y%m%d-%H%M%S)"
harbor run -p "$PWD/tasks" \
  -i topogym-cast-coil-i00 -i topogym-horseshoe-ring-i00 \
  -a codex -m openai/gpt-6-luna --ak version=0.157.0 --ak reasoning_effort=max \
  -n 1 -k 1 -o "$PWD/jobs" --job-name "$BATCH-u"
harbor run -p "$PWD/tasks" \
  -i topogym-cast-coil-i00-limited -i topogym-horseshoe-ring-i00-limited \
  -a codex -m openai/gpt-6-luna --ak version=0.157.0 --ak reasoning_effort=max \
  -n 1 -k 1 -o "$PWD/jobs" --job-name "$BATCH-l"

python scripts/collect_batch_results.py "$PWD/jobs" "$BATCH-u" "$BATCH-l" "$PWD/jobs/results/$BATCH"
python scripts/make_two_mode_report_zh.py "$PWD/jobs" "$BATCH-u" "$BATCH-l" "$PWD/jobs/reports/$BATCH"
harbor view "$PWD/jobs"
```

Use `-i 'topogym-*-i00'` for all unlimited tasks or `-i 'topogym-*-i00-limited'` for all limited tasks.
With the subscription setup above, keep its auth variables and add
`--ak config='{"forced_login_method":"chatgpt"}'` to each Codex run. Report GIF generation needs
`ffmpeg` on the host. `scripts/regrade_trials.sh jobs/<job>` reruns failed grading or missing-video
cases and uses the GPU again.

For unattended batches, [scripts/run_agent_batch.sh](scripts/run_agent_batch.sh) runs each task and its
limited twin sequentially by default (`SEQ=1`). Set `AGENT`, `MODEL`, `AK` and `ENV_FILE` explicitly;
its default agent is the OpenRouter adapter. It starts a log-mirror container and memory guard that
remain running after the batch. Output naming and details are in the [CLI guide](docs/rcb/README.md).

## Results

Each trial lives under `jobs/<job>/<task-prefix>__<suffix>/`:

| Path | Contents |
|---|---|
| `result.json` | Harbor timings, tokens, exceptions and verifier environment mode |
| `agent/` | Model conversation, executed commands and adapter logs |
| `verifier/reward.txt`, `reward.json` | Binary score and numeric diagnostics |
| `verifier/replay.mp4`, `replay.last.png` | Replay video and final frame |
| `artifacts/app/output/` | Unlimited trajectory, generation script and session log |
| `artifacts/data/` | Limited service's `final.json`, episode log, trajectory and video |

Check `exception_info`, `grader_error`, `missing_trajectory`, `bad_trajectory` and `wrong_family`
alongside `success`. A completed unsuccessful replay differs from an authentication, simulator or
grading failure. `jobs/`, `runs/` and `task_rollouts/` are gitignored; a fresh clone does not contain
local acceptance jobs.

## Status

As of **2026-09-29**, all 28 tasks are generated and the Harbor layer has passed static contract checks.
Recorded acceptance includes cube oracle **1** / nop **0** in both modes, 203 limited-protocol checks,
and a `knot_untying` limited nop run that starts, finalizes and grades under segment history. A later
cube unlimited regrade also passed after the history changes. See the dated
[acceptance record](docs/rcb/README.md#7-验收记录) for the exact scope and remaining work.

**Real-model rollouts, the Luna smoke command, non-cube Harbor oracles and a full final-version
two-mode rerun remain unvalidated.** Simulator lifecycle checks and standalone solvability proofs do
not establish a benchmark success rate. FEM tasks remain substantially slower than rigid tasks.

For simulator development, start with the [module map](docs/develop/modules/README.md),
[tests and Nyx setup](tests/README.md), [current progress](docs/progress/current_zh.md),
[solvability proofs](solvability_proof/README.md), [demo catalog](demos/README.md) and
[development rules](AGENTS.md). The management `Env` is separate from episode-bound interaction
handles; Harbor's unlimited `Session` supplies its own reset wrapper. Default
`history_storage="segment"` checkpoints the initial state and segment boundaries; use `"memory"`
when full per-tick rewind is required.

Publishing this checkout to GitHub `main` according to `.gitignore`:
[Git 操作指令](docs/maintenance/publish_main_zh.md).
