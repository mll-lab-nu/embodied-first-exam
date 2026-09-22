# robot_coding_bench

Can a coding agent be a roboticist? **robot_coding_bench** is a [Harbor](https://github.com/harbor-framework/harbor)
benchmark: each task drops an agent (Claude Code, Codex, …) into a container with a robot simulator and a
Python tool API and asks for a deliverable — in the current tasks, **one replayable trajectory** that completes
a manipulation goal in a **frozen scene instance**. The verifier replays it in a fresh process; scoring is
binary with numeric diagnostics, no learned judge.

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
    ├── tests/        test.sh, grade.py (verifier), rcb_traj.py, instance.npz (verifier's own copies)
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
New RoboTwin task: `scripts/robotwin_expert_sweep.py` (pick a seed the expert passes) then `scripts/robotwin_mk_task.py`.
Verified for all five: oracle 1, nop 0, replay bit-exact across processes.

## Status
v0.1 (2026-09): one robosuite example task + five RoboTwin 2.0 tasks (one easy, four hard: handover, articulated, multi-object, bimanual tool use). Next: more instances/families, LIBERO-PRO,
BEHAVIOR, `perception` tier, `policy` task type; then factor shared tooling into kits.
