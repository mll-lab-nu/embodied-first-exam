# AGENTS.md — map for coding agents working in this repo

Read `README.md`, `docs/TWO_MODES.md` and `docs/PROTOCOL.md` first.

- Active tasks are self-contained Harbor task dirs in `limited_tasks/<benchmark>/` and `unlimited_tasks/<benchmark>/`
  (benchmarks: metaworldplus, robocasa, robocasa365, robocasa-gr1, vlabench). `suites/two-modes.json` is the registry;
  each mode/benchmark folder has its own `dataset.toml`.
- Run tasks only through `scripts/two_modes/run.py` (`list`, `smoke`, `run`); a plain `harbor run -p` skips the trusted
  network rules and the limited episode lifecycle.
- `ci_checks/run_all.sh [task dirs]`: contract checks plus `scripts/two_modes/check.py`. New check =
  `check-<thing>.sh <task_dir>`, registered in `run_all.sh`.
- A task's content is frozen by its registry fingerprints and dataset digest. Changing it is a new task version:
  refresh deliberately with `scripts/two_modes/check.py --freeze`, never to silence a failing check.
- Unlimited: no step or reset cap, 3600 s of agent time. Limited: one episode with its protocol step cap, no reset.
- `images/<sim>/`: simulator base images (not in a public registry; build locally, see README). No GPU needed.
