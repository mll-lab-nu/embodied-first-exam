# robot_coding_bench

Can a coding agent be a roboticist? **robot_coding_bench** is a [Harbor](https://github.com/harbor-framework/harbor)
benchmark: each task drops an agent (Claude Code, Codex, …) into a container with a robot simulator and a
Python tool API and asks for a deliverable — in the current tasks, **one replayable trajectory** that completes
a manipulation goal in a **frozen scene instance**. The verifier replays it in a fresh process **in its own
sandbox** (the agent's container, which the agent controls as root, is gone by then); scoring is binary with
numeric diagnostics, no learned judge.

The repo is deliberately minimal: it adds a thin **contract** ([docs/PROTOCOL.md](docs/PROTOCOL.md)) on top of
the plain Harbor task format, and every task is **self-contained**. Shared kits will be factored out once
several tasks exist; until then, copy the example.

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
Tasks `FROM` published base images (`ghcr.io/jameskrw/rcb-<sim>:<tag>`). The robosuite tasks need no GPU, so the
default local Docker sandbox works (Modal too); RoboTwin tasks need an NVIDIA GPU (CuRobo + Vulkan) and pass it
through with `environment/docker-compose.yaml` (nvidia-container-toolkit on the host). Once on Harbor Hub: `harbor run -d robot-coding-bench/robot-coding-bench@0.1.0 …`.

## Layout

```
tasks/                          # Harbor tasks, one dir each, + dataset.toml (allowlist, digests)
└── robosuite-cube-stack-i00/   # the example: self-contained
    ├── instruction.md task.toml README.md
    ├── environment/  Dockerfile (FROM base image), instance.npz (frozen scene), rcb_traj.py (agent tooling)
    ├── tests/        Dockerfile (separate verifier sandbox), test.sh, grade.py, rcb_traj.py, instance.npz (verifier's own copies)
    └── solution/     solve.sh (oracle)
└── robotwin_2_0_<task>/        # RoboTwin 2.0 (SAPIEN + CuRobo, ALOHA dual arm): same shape, + docker-compose.yaml (GPU);
                                #   stack_blocks_two, put_bottles_dustbin, open_microwave, place_can_basket, scan_object
images/<sim>/Dockerfile         # base images = simulator installs only; scripts/build_images.sh, push_images.sh
ci_checks/                      # contract checks: structure, fields, pinned FROM, instruction, dataset manifest
docs/PROTOCOL.md TAXONOMY.md    # the contract and the metadata vocabulary
third_party/cap-x, RoboTwin     # submodules used by images/robosuite and images/robotwin
CONTRIBUTING.md AGENTS.md       # how to add a task; map for coding agents
```

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
  Harbor has no run-time override, so this rewrites `task.toml`; re-scan the manifest afterwards.
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
v0.1 (2026-09): one robosuite example task + 22 RoboTwin 2.0 tasks in both modes. First batch (Codex + GPT-6 Luna, 21 tasks): unlimited 11/21, limited 1/21 — see `docs/results/`. Next: more instances/families, LIBERO-PRO,
BEHAVIOR, `perception` tier, `policy` task type; then factor shared tooling into kits.
