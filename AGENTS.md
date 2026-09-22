# AGENTS.md — map for coding agents working in this repo

Read `README.md`, `docs/PROTOCOL.md` (the contract), `CONTRIBUTING.md` first.

- Tasks are self-contained Harbor task dirs under `tasks/`: there is no shared runtime package, so each
  one carries its own tooling (`environment/rcb_*.py`) and verifier (`tests/grade.py`).
- Those copies are generated, not hand-written. `scripts/<sim>/gen_tasks.py` renders a whole task dir from
  `scripts/<sim>/subset.toml` (which tasks and why) plus `templates/` and `shared/`; `check-tooling-sync.sh`
  fails the build if a copy drifts. **Edit the source and re-render — never a file under `tasks/`.**
  HumanoidBench works this way; `tasks/robosuite-cube-stack-i00/` predates it and is still hand-maintained.
- 🚩 **The scoring formula must never reach `environment/`.** HumanoidBench grades on a dense reward, and
  a dense reward is the answer key — `images/humanoidbench/scrub_oracles.py` deletes every `get_reward()`
  from the base image, `scripts/humanoidbench/rewards.json` keeps them, and `render` copies one family's
  entry into that task's `tests/` (which Harbor mounts only after the agent has finished). `grade.py`
  patches it back before scoring, so scores stay comparable with upstream.
  Consequences when working here: `Session.scored` is `False` and `step()` returns `None` for the reward
  inside the agent's container; `instruction.md` describes the scoring in prose and must not quote
  tolerance parameters or exact weights (the rule is written at the top of `subset.toml`);
  `ci_checks/check-no-reward-leak.sh` enforces both directions. Deleting it only works while the agent
  cannot fetch it back, so `task.toml` sets `[agent] network_mode = "allowlist"` with an empty list; the
  model API is opted into per run with `harbor run --allow-agent-host openrouter.ai`.
  **Before you hide anything from the agent, read `docs/LEAKAGE.md`** — it is the checklist of the places
  an answer key survives (dead code, constants, `__pycache__`, Docker layers, `.git`, the network), each
  entry written from one we actually shipped. Also `docs/PROTOCOL.md` §4, `local_docs/plan/07-open-questions.md` §1.
- Run anything that needs the simulator inside the image, not on the host:
  `sg docker -c "docker run --rm -v \$PWD:/repo -w /repo ghcr.io/jameskrw/rcb-humanoidbench:$(cat images/VERSION) ..."`.
  (`docker` without `sg` is permission-denied on this machine.)
- `images/<sim>/Dockerfile`: simulator base images, tagged from `images/VERSION`; `scripts/build_images.sh`.
- `ci_checks/run_all.sh [task dirs]`: contract checks. New check = `check-<thing>.sh <task_dir>`, registered in `run_all.sh`.
- `tasks/dataset.toml`: task manifest; refresh with `cd tasks && harbor add --scan .`.
- Local docker sandbox has no `[environment].gpus`; the current tasks don't need a GPU.
