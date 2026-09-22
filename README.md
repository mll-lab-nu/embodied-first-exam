# robot_coding_bench

Can a coding agent be a roboticist? **robot_coding_bench** is a [Harbor](https://github.com/harbor-framework/harbor)
benchmark: each task drops an agent (Claude Code, Codex, …) into a container with a robot simulator and a
Python tool API and asks for a deliverable — in the current tasks, **one replayable trajectory** that completes
a manipulation goal in a **frozen scene instance**. The verifier replays it in a fresh process; scoring is
binary with numeric diagnostics, no learned judge.

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
Tasks `FROM` published base images (`ghcr.io/jameskrw/rcb-<sim>:<tag>`); the current tasks need no GPU, so
the default local Docker sandbox works (Modal too). Once on Harbor Hub: `harbor run -d robot-coding-bench/robot-coding-bench@0.1.0 …`.

To evaluate with DeepSeek V4.1 Flash through OpenRouter while retaining the Codex CLI harness, set
`OPENROUTER_API_KEY` in `.env` and run:

```bash
scripts/run_deepseek_openrouter.sh tasks/humanoidbench-loco-walk-i00 -k 3
RCB_MODEL=openrouter/<provider>/<model> scripts/run_deepseek_openrouter.sh <task>   # any OpenRouter model
```

The repository-local adapter preserves OpenRouter's nested model ID and maps the OpenRouter credential and endpoint
to the OpenAI-compatible interface expected by Codex.

## Layout

```
tasks/                          # Harbor tasks, one dir each, + dataset.toml (allowlist, digests)
├── robosuite-cube-stack-i00/   # the example: self-contained, hand-maintained
│   ├── instruction.md task.toml README.md
│   ├── environment/  Dockerfile (FROM base image), instance.npz (frozen scene), rcb_traj.py (agent tooling)
│   ├── tests/        test.sh, grade.py (verifier), rcb_traj.py, instance.npz (verifier's own copies)
│   └── solution/     solve.sh (oracle)
└── humanoidbench-*/            # 23 scored tasks + 1 fixture, all generated -- do not edit by hand
scripts/<sim>/                  # the generator: subset.toml (which tasks and why) + templates/ + shared/
images/<sim>/Dockerfile         # base images = simulator installs only; scripts/build_images.sh, push_images.sh
ci_checks/                      # contract checks: structure, fields, pinned FROM, instruction, tooling sync,
                                #   cross-task leaks, reward leaks, dataset manifest
docs/PROTOCOL.md TAXONOMY.md    # the contract and the metadata vocabulary
third_party/cap-x               # submodule used by images/robosuite
CONTRIBUTING.md AGENTS.md       # how to add a task; map for coding agents
```

### HumanoidBench tasks
23 scored tasks across nine capability classes (periodic gait, constrained gait, quasi-static
stabilisation, navigation, whole-body power, standing manipulation, in-hand precision, mobile
manipulation, long-horizon multi-subtask), 14 of them on the 19-DoF Unitree H1 and 9 on the 61-DoF
hand version. Which tasks and why: `local_docs/plan/06-task-selection.md`.

Two properties worth knowing before you read a task:

- **Doing nothing does not score.** Every task is selected on a measured floor — what holding the
  starting pose earns — and none of the scored tasks gives away more than 40% of its bar that way
  (`spoon` is the one documented exception at 58%). Two tasks score *negative* for a blank submission.
- **The agent does not see the reward function.** It is deleted from the base image and restored only
  inside the verifier, so the score still comes from upstream's exact expression — comparable with the
  paper and with FastTD3 — while the agent works from the task statement and the physical state. The
  agent phase is also off the network, because upstream is a public pinned commit. See
  [`docs/LEAKAGE.md`](docs/LEAKAGE.md) and `docs/PROTOCOL.md` §4.

## The example task (`robosuite-cube-stack-i00`)
Franka Panda in robosuite/MuJoCo via [cap-x](https://github.com/capgym/cap-x) primitives
(`get_object_pose`, `goto_pose`, `open/close_gripper`, …). `rcb_traj.py` gives the agent `Session`: reset to
the frozen state as often as it likes, record `(T, 9)` joint-target + gripper actions, self-check by replay,
save `/app/output/trajectory.npz`. `tests/grade.py` restores the same state in a fresh process, replays twice
and passes iff the stack predicate holds and both final-state hashes agree. Verified: oracle 1, nop 0.

## Status
v0.1 (2026-09): one robosuite example task plus **23 scored HumanoidBench tasks** (+1 CI fixture), all
verified end to end — `nop` scores 0, the oracle fixture scores 1, and the verifier's numbers are
bit-identical to the host's. Next: more instances per family (`i01`, `i02`) to separate "solved it" from
"memorised this scene", `g1` as a torque-control counterpart to the position-controlled H1, then
LIBERO-PRO / BEHAVIOR, the `perception` tier and the `policy` task type; then factor shared tooling
into kits.
