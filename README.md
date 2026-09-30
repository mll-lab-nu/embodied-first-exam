# robot_coding_bench

Can a coding agent be a roboticist? **robot_coding_bench** is a [Harbor](https://github.com/harbor-framework/harbor)
benchmark: each task drops an agent (Claude Code, Codex, …) into a container with a robot simulator and a
Python tool API and asks for a deliverable — in the current tasks, **one replayable trajectory** that completes
a manipulation goal in a **frozen scene instance**. The verifier replays it in a fresh process **in its own
sandbox** (the agent's container, which the agent controls as root, is gone by then); scoring is binary with
numeric diagnostics, no learned judge.

The repo is deliberately minimal: it adds a thin **contract** ([docs/PROTOCOL.md](docs/PROTOCOL.md)) on top of
the plain Harbor task format, and every task is **self-contained** — no shared runtime package, so each task
dir carries its own tooling and verifier. For HumanoidBench those copies are *generated* from one manifest
(`scripts/humanoidbench/`) and CI rejects any that drift; `tasks/robosuite-cube-stack-i00/` predates that and
is still hand-maintained.

## Run

```bash
uv tool install harbor
export ANTHROPIC_API_KEY=…   # or OPENAI_API_KEY; subscription-login variants in .env.example

harbor run --repo git@github.com:JamesKrW/robot_coding_bench.git -a claude-code -m anthropic/claude-fable-5-1 -k 3
harbor run --repo git@github.com:JamesKrW/robot_coding_bench.git -a codex       -m openai/gpt-6-astra          -k 3
# local checkout / subset / pinned release
harbor run -p tasks -i 'robosuite-*' -a claude-code -m anthropic/claude-sonnet-5
harbor run --repo git@github.com:JamesKrW/robot_coding_bench.git@v0.1.0 -a oracle
harbor view jobs
```
Tasks `FROM` published base images (`ghcr.io/jameskrw/rcb-<sim>:<tag>`). The robosuite, HumanoidBench and KinDER
unlimited tasks need no GPU, so the default local Docker sandbox works (Modal too); RoboTwin tasks need an NVIDIA GPU
(CuRobo + Vulkan) and pass it through with `environment/docker-compose.yaml` (nvidia-container-toolkit on the host).
HumanoidBench's and KinDER's limited tasks reserve one for their simulator sidecar; run at most 8 of them at once on
one GPU (`-n 8`, counting other runs' trials on it). Each instruction quotes a step's cost measured alone; on an RTX
4090 it grew about 15% with 8 trials stepping at once, 30% with 10 and 14–26× with 12.
Once on Harbor Hub: `harbor run -d robot-coding-bench/robot-coding-bench@0.1.0 …`.

Through OpenRouter (`OPENROUTER_API_KEY` in `.env`), with the Codex or the Claude Code harness:

```bash
scripts/run_deepseek_openrouter.sh tasks/humanoidbench-loco-walk-i00 -k 3                 # Codex, DeepSeek V4.1 Flash
RCB_MODEL=openrouter/<provider>/<model> scripts/run_deepseek_openrouter.sh <task>   # Codex, any OpenRouter model
PYTHONPATH=. harbor run -p <task> -a harbor_agents.claude_code_openrouter:ClaudeCodeOpenRouter \
  -m openrouter/anthropic/claude-opus-5.5 --env-file .env --allow-agent-host openrouter.ai        # Claude Code
```

The adapters in `harbor_agents/` map the OpenRouter key, endpoint and nested model ID to what each harness
expects, and switch off the harness's own web tools: the provider runs those, past the task's network
allowlist (`docs/LEAKAGE.md`). In limited mode they also end the trial when the agent's session ends
(`docs/LIMITED_MODE_1_1.md`). `--ak` (`--agent-kwarg`) passes an agent option, e.g. `--ak web_search=live` or
`--ak reasoning_effort=medium`. The standard configs and their commands are in `results/<benchmark>/README.md`.

After a run, in either mode, `python3 scripts/results/build.py --add jobs/<job>` appends its line to
`results/<benchmark>/runs.csv`, measures the trial (the bill, every tool call and image; in limited mode every episode
replayed, scored and rendered) and writes the results pages to `jobs/results/<benchmark>/` -- an overview, one page
per task, one per run. Each run's analysis is written by hand or by an agent, from `scripts/results/digest.py`'s one-page
view of the trial, as `scripts/results/NOTES_GUIDE.md` says.

## Layout

```
tasks/                          # Harbor tasks, one dir each, + dataset.toml (allowlist, digests)
├── robosuite-cube-stack-i00/   # the example: self-contained, hand-maintained
│   ├── instruction.md task.toml README.md
│   ├── environment/  Dockerfile (FROM base image), instance.npz (frozen scene), rcb_traj.py (agent tooling)
│   ├── tests/        Dockerfile (separate verifier sandbox), test.sh, grade.py, rcb_traj.py, instance.npz (verifier's own copies)
│   └── solution/     solve.sh (oracle)
├── robotwin_2_0_<task>[-limited]/ # RoboTwin 2.0 (SAPIEN + CuRobo, ALOHA dual arm): same shape, + docker-compose.yaml (GPU)
├── humanoidbench-*-i00/        # 23 scored tasks + 1 fixture, all generated -- do not edit by hand
├── humanoidbench-*-i00-limited/ # the limited-mode twin of each (docs/LIMITED_MODE_1_1.md), also generated
└── kinder-*-i00[-limited]/     # 10 scored KinDER tasks + 1 fixture, both modes (docs/benchmarks/kinder.md), generated
scripts/<sim>/                  # the generator: subset.toml (which tasks and why) + templates/ + shared/;
                                #   replay.py re-plays a limited run's episodes for the results pages
scripts/limited/                # the simulator-agnostic half of limited mode: sim service, verifier, client code
scripts/results/                # the results pages: build.py (+ common, data, calls, charts, pages), collect.py (one trial, measured),
                                #   digest.py + NOTES_GUIDE.md (a run's analysis); benches/<benchmark>.py: what differs per benchmark
results/<benchmark>/            # what agents scored: README.md (standard configs, table per model and mode) + runs.csv (one line per trial)
images/<sim>/Dockerfile         # base images = simulator installs only; scripts/build_images.sh, push_images.sh
ci_checks/                      # contract checks: structure, fields, pinned FROM, instruction, verifier isolation,
                                #   tooling sync, cross-task leaks, reward leaks, generated tasks, dataset manifest
docs/                           # PROTOCOL (the contract), TAXONOMY (metadata vocabulary), LEAKAGE (where answer
                                #   keys survive), LIMITED_MODE_1_1 (robot as a service), benchmarks/ (one short page each),
                                #   results/ (RoboTwin batch reports)
harbor_agents/                  # Harbor adapters for running Codex / Claude Code through OpenRouter
third_party/cap-x, RoboTwin     # submodules used by images/robosuite and images/robotwin
CONTRIBUTING.md AGENTS.md       # how to add a task; map for coding agents
```

### HumanoidBench tasks
23 scored tasks across nine capability classes (periodic gait, constrained gait, quasi-static
stabilisation, navigation, whole-body power, standing manipulation, in-hand precision, mobile
manipulation, long-horizon multi-subtask), 14 of them on the 19-DoF Unitree H1 and 9 on the 61-DoF
hand version. Which tasks and why: [`docs/benchmarks/humanoidbench.md`](docs/benchmarks/humanoidbench.md), and in
full `scripts/humanoidbench/subset.toml`.

Two properties worth knowing before you read a task:

- **Doing nothing does not score.** Every task is selected on a measured floor — what holding the
  starting pose earns — and none of the scored tasks gives away more than 40% of its bar that way
  (`spoon` is the one documented exception at 58%). Two tasks score *negative* for a blank submission.
- **The agent does not see the reward function.** It is deleted from the base image and restored only
  inside the verifier, which runs in its own container, so the score still comes from upstream's exact
  expression — comparable with the paper and with FastTD3 — while the agent works from the task statement
  and the physical state. The agent reaches the model APIs and nothing else, because upstream is a public
  pinned commit. See [`docs/LEAKAGE.md`](docs/LEAKAGE.md) and `docs/PROTOCOL.md` §4.

## The example task (`robosuite-cube-stack-i00`)
Franka Panda in robosuite/MuJoCo via [cap-x](https://github.com/capgym/cap-x) primitives
(`get_object_pose`, `goto_pose`, `open/close_gripper`, …). `rcb_traj.py` gives the agent `Session`: reset to
the frozen state as often as it likes, record `(T, 9)` joint-target + gripper actions, self-check by replay,
save `/app/output/trajectory.npz`. `tests/grade.py` restores the same state in a fresh process, replays twice
and passes iff the stack predicate holds and both final-state hashes agree. Verified: oracle 1, nop 0.

## RoboTwin 2.0 tasks (`robotwin_2_0_<task>`)
RoboTwin's task envs (`/opt/RoboTwin/envs/<task>.py`) keep their scene definition and `check_success`; the expert
`play_once` is scrubbed from the image. The agent drives RoboTwin's own primitives (`env.grasp_actor`,
`env.place_actor`, `env.move`, …); `rcb_traj.py` hooks every `scene.step()` and records the (T, 34) drive-target
rows, which the verifier replays from the scene rebuilt from the RoboTwin seed (initial-state hash checked).
22 tasks (`tasks/dataset.toml`), each with a `-limited` twin. New task: `scripts/robotwin_expert_sweep.py` (pick a seed the
expert passes) → `scripts/robotwin_mk_task.py` → `scripts/robotwin_mk_limited.py` (run inside the image; needs numpy).

## Two evaluation modes
| | **unlimited** (`robotwin_2_0_<task>`) | **limited** (`robotwin_2_0_<task>-limited`, "robot as a service") |
|---|---|---|
| simulator | in the agent's container | in a `sim` sidecar container the agent cannot open (GPU reserved there) |
| reset | unlimited | none — one trial is one episode |
| what the agent sees | object poses, `check_success` source, RoboTwin primitives | RGB from 4 cameras (+ calibration) and proprioception only |
| actions | primitives / low-level step | RoboTwin's native `take_action`: `qpos` (14) or `ee` (16), through a small HTTP client |
| deliverable | the (T, 34) trajectory the agent saves | the same (T, 34) trajectory, recorded by the service |
| verifier | separate container, two fresh replays + six-view video | separate container over the service's own record (already replay-checked) |
Design, protocol and results: `docs/LIMITED_MODE.md`, `docs/LIMITED_MODE_PROTOCOL.md` (`rcb-limited/2.0`: `submit` chunks of low-level actions, `observe` frames or a watch window, binary RCB1 responses; design in `docs/LIMITED_MODE_V2_DESIGN.zh.md`), `docs/LIMITED_MODE.zh.md`;
v2 design (two operations `submit` / `get_obs`, low-level action chunks, videos returned as binary): `docs/LIMITED_MODE_V2_DESIGN.zh.md`.

## Anti-cheat design (what an agent can and cannot touch)
- **Verifier isolation.** Every task grades in its own container (`[verifier] environment_mode = "separate"`,
  `tests/Dockerfile`); the agent's container is stopped first and only `/app/output/` is copied over. Measured: a
  cheating oracle that patched `check_success` and handed in a do-nothing trajectory scored 1 under Harbor's default
  shared verifier and 0 under the separate sandbox. `ci_checks/check-verifier-isolation.sh` enforces it, plus pinned
  `tests/Dockerfile` and sidecar images.
- **Oracle scrub.** `images/robotwin/scrub_oracles.py` removes every expert method from the 50 task classes (and
  `code_gen/`) in the agent image; reference solutions live only in `solution/`, which Harbor mounts for the oracle agent only.
- **Limited-mode evidence.** The sidecar records the episode, replays it for success and determinism, renders the video
  and writes `final.json`; the agent never holds the simulator. A collect hook signals the service by PID after the
  agent container is gone (never `pkill -f`, which kills the hook's own shell).
- **Agent egress is a per-run switch, default open.** The scrubbed solutions are public upstream, so a run that must
  rule out "the agent fetched the answer" runs `scripts/set_agent_egress.py allowlist` (model-API hosts only; verified
  to keep Codex/ChatGPT login, Claude Code and OpenRouter working while GitHub/PyPI are blocked), and `public` to revert.
  Harbor has no run-time override, so this rewrites `task.toml`; re-scan the manifest afterwards. HumanoidBench and
  KinDER tasks are always model-APIs-only: their generators write the allowlist (`docs/PROTOCOL.md` §4).
- **Self-reported cost.** In unlimited mode the tooling appends every session/reset/record/replay to
  `/app/output/rcb_session_log.jsonl`; the verifier reports it as `agent_*` cost fields flagged `agent_cost_self_reported`
  (the agent owns that file). In limited mode the equivalent log is the sidecar's and is evidence.

## Running a two-mode batch
```bash
harbor run -p tasks -i robotwin_2_0_<t1> -i robotwin_2_0_<t2> -a codex -m openai/gpt-6-luna -n 3 -o $PWD/exps/jobs --job-name <job-u>
harbor run -p tasks -i robotwin_2_0_<t1>-limited ... -a codex -m openai/gpt-6-luna -n 3 -o $PWD/exps/jobs --job-name <job-l>
scripts/regrade_trials.sh exps/jobs/<job-u>            # re-run the same grader for trials with a grader error / missing video
scripts/collect_batch_results.py exps/jobs <job-u> <job-l> <out_dir>   # videos, rewards, cost, summary.md
scripts/make_two_mode_report_zh.py exps/jobs <job-u> <job-l> <report_dir> [batch_plan.json]   # 中文报告，GIF 预览 + mp4
```
`CODEX_FORCE_AUTH_JSON=1` uses a ChatGPT-subscription login (`codex login --device-auth`) instead of an API key.
Use an absolute `-o` (compose cp is noisy otherwise); 3 concurrent trials fit one RTX 4090 with headroom for the
separate verifiers. Results so far: `docs/results/`; each RoboTwin task also carries `results/<agent-slug>/README.md` (replay video, last frame, reward fields, cost, failure analysis) written by `scripts/write_task_results.py`.

## Status
v0.1 (2026-09): one robosuite example task, 22 RoboTwin 2.0 tasks, 23 scored HumanoidBench tasks (+1 CI fixture)
and 10 scored KinDER tasks (+1 fixture), each in both modes. HumanoidBench and KinDER are verified end to end — `nop`
scores 0, the oracle fixture scores 1, and the verifier's numbers are bit-identical to the host's. Results: RoboTwin's
first batch (Codex + GPT-6 Luna, 21 tasks: unlimited 11/21, limited 1/21) in `docs/results/`; HumanoidBench's and
KinDER's runs in `results/<benchmark>/`. Next: more instances per family (`i01`, `i02`) to separate "solved it" from
"memorised this scene", LIBERO-PRO, BEHAVIOR, the `perception` tier and the `policy` task type; then factor shared
tooling into kits.
