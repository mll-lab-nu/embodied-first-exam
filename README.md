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
Tasks `FROM` published base images (`ghcr.io/jameskrw/rcb-<sim>:<tag>`); the current tasks need no GPU, so
the default local Docker sandbox works (Modal too). Once on Harbor Hub: `harbor run -d robot-coding-bench/robot-coding-bench@0.1.0 …`.

## Layout

```
tasks/                          # Harbor tasks, one dir each, + dataset.toml (allowlist, digests)
└── robosuite-cube-stack-i00/   # the example: self-contained
    ├── instruction.md task.toml README.md
    ├── environment/  Dockerfile (FROM base image), instance.npz (frozen scene), rcb_traj.py (agent tooling)
    ├── tests/        test.sh, grade.py (verifier), rcb_traj.py, instance.npz (verifier's own copies)
    └── solution/     solve.sh (oracle)
images/<sim>/Dockerfile         # base images = simulator installs only; scripts/build_images.sh, push_images.sh
ci_checks/                      # contract checks: structure, fields, pinned FROM, instruction, dataset manifest
docs/PROTOCOL.md TAXONOMY.md    # the contract and the metadata vocabulary
third_party/cap-x               # submodule used by images/robosuite
CONTRIBUTING.md AGENTS.md       # how to add a task; map for coding agents
```

## The example task (`robosuite-cube-stack-i00`)
Franka Panda in robosuite/MuJoCo via [cap-x](https://github.com/capgym/cap-x) primitives
(`get_object_pose`, `goto_pose`, `open/close_gripper`, …). `rcb_traj.py` gives the agent `Session`: reset to
the frozen state as often as it likes, record `(T, 9)` joint-target + gripper actions, self-check by replay,
save `/app/output/trajectory.npz`. `tests/grade.py` restores the same state in a fresh process, replays twice
and passes iff the stack predicate holds and both final-state hashes agree. Verified: oracle 1, nop 0.

## Status
v0.1 (2026-09): one example task. Next: more instances/families (robosuite), LIBERO-PRO, BEHAVIOR,
`perception` tier, `policy` task type; then factor shared tooling into kits.
