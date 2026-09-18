# robot_coding_bench

Can a coding agent be a roboticist? **robot_coding_bench** is a [Harbor](https://github.com/harbor-framework/harbor)
benchmark: each task drops an agent (Claude Code, Codex, …) into a container with a robot simulator and a
Python primitive API, and asks for **one replayable trajectory** that completes a manipulation goal in a
**frozen scene instance**. The verifier replays it open-loop in a fresh process. Scoring is binary and
bit-exact; there is no learned judge. Simulation substrate: [cap-x](https://github.com/capgym/cap-x)
(robosuite now; LIBERO-PRO and BEHAVIOR planned).

## Run it

```bash
uv tool install harbor            # https://docs.harborframework.com
export ANTHROPIC_API_KEY=…        # or OPENAI_API_KEY; see .env.example for subscription-login variants

# straight from this repo (private: use the SSH URL so your git credentials apply; verified with -a oracle)
harbor run --repo git@github.com:JamesKrW/robot_coding_bench.git -a claude-code -m anthropic/claude-fable-5-1 -k 3
harbor run --repo git@github.com:JamesKrW/robot_coding_bench.git -a codex       -m openai/gpt-6-astra          -k 3
# pin a release: --repo git@github.com:JamesKrW/robot_coding_bench.git@v0.1.0 ; subset: -i 'robosuite-cube-stack-*'
# or a local checkout / a subset
harbor run -p tasks -i 'robosuite-cube-stack-*' -a claude-code -m anthropic/claude-sonnet-5
harbor view jobs
```

Tasks pull the shared base image `ghcr.io/jameskrw/rcb-robosuite:<images/VERSION>`; no GPU is needed for
the `privileged` tier, so the default local Docker sandbox works (`-e modal` works too).
Once published to Harbor Hub the command becomes `harbor run -d robot-coding-bench/robot-coding-bench@0.1.0 …`.

## Repository structure

```
robot_coding_bench/
├── tasks/                     # one dir per (family, instance): <sim>-<family>-i<NN>/  + dataset.toml (allowlist)
│   └── robosuite-cube-stack-i00/{instruction.md, task.toml, README.md, environment/, tests/, solution/}
├── rcb/                       # shared tooling baked into the base images and importable as `rcb`
│   ├── traj.py                #   Session: frozen instance, recorder, deterministic replay, oracle
│   ├── grade.py               #   verifier entry point (writes /logs/verifier/reward.*)
│   ├── new_task.py            #   task generator (templates live here)
│   └── adapters/              #   simulator adapters: family registry per simulator
├── images/<name>/Dockerfile   # base images -> ghcr.io/jameskrw/rcb-<name>:<images/VERSION>
├── ci_checks/                 # static checks (bash check-*.sh <task-dir>; run_all.sh)
├── docs/                      # PROTOCOL.md (scoring), TAXONOMY.md (metadata vocab)
├── scripts/                   # install.sh (author setup), build_images.sh, push_images.sh
├── lite/  archive/            # easy / retired tasks (not shipped)
├── third_party/cap-x          # submodule: simulator + primitives (built into the images)
└── CONTRIBUTING.md  AGENTS.md
```

A task directory is deliberately thin: everything heavy (simulator, primitives, grader) lives in the base
image and `rcb/`, so adding an instance is a one-command change and adding a family is one registry entry.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version:

```bash
scripts/install.sh                                   # harbor + cap-x venv (host)
PYTHONPATH=. python -m rcb.new_task --family cube_stack --seed 7 --author "<you>"
bash ci_checks/run_all.sh tasks/robosuite-cube-stack-i07
harbor run -p tasks/robosuite-cube-stack-i07 -a oracle   # must be 1
harbor run -p tasks/robosuite-cube-stack-i07 -a nop      # must be 0
```

## Status

v0.1 (2026-09): 3 instances of robosuite `cube_stack`, privileged tier. Oracle and replay determinism
verified end-to-end through Harbor. Roadmap: the other 6 CaP-Bench robosuite families, LIBERO-PRO
(perturbation instances), BEHAVIOR (after replay-determinism study), `perception` tier, `policy` task type.
