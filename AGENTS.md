# AGENTS.md — map for coding agents working in this repo

Read `README.md`, `docs/PROTOCOL.md` (the contract), `CONTRIBUTING.md` first.

- Tasks are self-contained Harbor task dirs under `tasks/`: there is no shared runtime package, so each
  one carries its own tooling (`environment/rcb_*.py`) and verifier (`tests/grade.py`).
- Those copies are generated, not hand-written. `scripts/<sim>/gen_tasks.py` renders a whole task dir from
  `scripts/<sim>/subset.toml` (which tasks and why) plus `templates/` and `shared/`; `check-tooling-sync.sh`
  fails the build if a copy drifts, `check-generated-tasks.sh` if a task was not re-rendered. **Edit the
  source and re-render — never a file under `tasks/`.** HumanoidBench and KinDER work this way;
  `tasks/robosuite-cube-stack-i00/` predates it and is still hand-maintained.
- Limited mode (robot as a service, `docs/LIMITED_MODE_1_1.md`): every HumanoidBench and KinDER task has a
  `tasks/*-limited/` twin, rendered by the same generator from `templates/limited/`, `shared/limited/`,
  `scripts/limited/` (the service, verifier and client code every simulator shares) and, for HumanoidBench, the
  task's `[task.limited]` table (`gen_tasks.py measure-limited` checks and times its sim service; needs a GPU).
  The simulator, tooling and reward run in the `sim` sidecar from `environment/sim/` (compose volume, never
  COPYed into the agent image) -- the one place under `environment/` the formula may live; the checks know it
  from `mode = "limited"`. The agent-facing API is documented in `environment/rcb_client.py`'s docstring, the
  full reference; `instruction.md` points to it and keeps only task facts (task, rules, scoring prose, measured
  costs, actuator order). Anything that belongs to the robot or the run (reset budget, sensors, servo ranges,
  axes, joint positions, link masses, camera poses) is in `spec()`, not in the text.
- 🚩 **The scoring formula must never reach `environment/`.** HumanoidBench grades on a dense reward, and
  a dense reward is the answer key — `images/humanoidbench/scrub_oracles.py` deletes every `get_reward()`
  from the base image, `scripts/humanoidbench/rewards.json` keeps them, and `render` copies one family's
  entry into that task's `tests/`, which the verifier's own container is built from (`tests/Dockerfile`).
  `grade.py` patches it back before scoring, so scores stay comparable with upstream.
  Consequences when working here: `Session.scored` is `False` and `step()` returns `None` for the reward
  inside the agent's container; `instruction.md` describes the scoring in prose and must not quote
  tolerance parameters or exact weights (the rule is written at the top of `subset.toml`);
  `ci_checks/check-no-reward-leak.sh` enforces both directions. Deleting it only works while the agent
  cannot fetch it back, so `task.toml` allows the model-API hosts and nothing else (`[agent] network_mode =
  "allowlist"`, hosts in `subset.toml`), and the `harbor_agents/` adapters switch off the harness's own web
  tools, which the provider runs past that allowlist.
  **Before you hide anything from the agent, read `docs/LEAKAGE.md`** — it is the checklist of the places
  an answer key survives (dead code, constants, `__pycache__`, Docker layers, `.git`, the network), each
  entry written from one we actually shipped. Also `docs/PROTOCOL.md` §4.
- Run anything that needs the simulator inside the image, not on the host:
  `docker run --rm -v $PWD:/repo -w /repo ghcr.io/jameskrw/rcb-humanoidbench:$(cat images/VERSION) ...`.
- `images/<sim>/Dockerfile`: simulator base images, tagged from `images/VERSION`; `scripts/build_images.sh`.
- `ci_checks/run_all.sh [task dirs]`: contract checks. New check = `check-<thing>.sh <task_dir>`, registered in `run_all.sh`.
- `tasks/dataset.toml`: task manifest; refresh with `cd tasks && harbor add --scan .`.
- Local docker sandbox has no `[environment].gpus`; unlimited tasks don't need a GPU, limited ones reserve it on
  the sidecar in `environment/docker-compose.yaml` (images are rendered there).
