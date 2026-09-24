# AGENTS.md — map for coding agents working in this repo

Read `README.md`, `docs/PROTOCOL.md` (the contract), `CONTRIBUTING.md` first.

- Tasks are self-contained Harbor task dirs under `tasks/`. To keep maximum flexibility there is currently
  no shared Python package: the example `tasks/robosuite-cube-stack-i00/` carries its own tooling
  (`environment/rcb_traj.py`) and verifier (`tests/grade.py`, `tests/rcb_traj.py`). To add a task, copy it.
- `images/<sim>/Dockerfile`: simulator base images, tagged from `images/VERSION`; `scripts/build_images.sh`.
- `ci_checks/run_all.sh [task dirs]`: contract checks (incl. verifier isolation: `[verifier] environment_mode = "separate"` + `tests/Dockerfile`). New check = `check-<thing>.sh <task_dir>`, registered in `run_all.sh`.
- `tasks/dataset.toml`: task manifest; refresh with `cd tasks && harbor add --scan .`.
- Local docker sandbox has no `[environment].gpus`. robosuite tasks don't need a GPU; RoboTwin tasks pass one through
  with `environment/docker-compose.yaml` (service `main`, nvidia device reservation) — copy it from
  `tasks/robotwin_2_0_stack_blocks_two/`.
