# AGENTS.md — map for coding agents working in this repo

Read `README.md`, `docs/PROTOCOL.md` (the contract), `CONTRIBUTING.md` first.

- Tasks are self-contained Harbor task dirs under `tasks/`; there is **no shared Python package**. The
  example `tasks/robosuite-cube-stack-i00/` carries its own tooling (`environment/rcb_traj.py`) and verifier
  (`tests/grade.py`, `tests/rcb_traj.py`). To add a task, copy it.
- `images/<sim>/Dockerfile` = simulator base images (infrastructure only, no benchmark code). Tag from
  `images/VERSION`. Build: `scripts/build_images.sh` (falls back to `sg docker -c` before re-login).
- `ci_checks/run_all.sh [task dirs]` runs the contract checks; add one as `check-<thing>.sh <task_dir>` printing
  `FAIL <task>: <reason>`, exit 1, and register it in `run_all.sh`.
- `tasks/dataset.toml` is the allowlist manifest (digest per task): `cd tasks && harbor add --scan .`.

Invariants: deliverable under `/app/output/`; `reward.json` numeric only; verifier inputs under `/tests/` and
never named in `instruction.md`; pinned `FROM`; oracle 1 / nop 0; fresh-process determinism.

Known gotchas: cap-x prints import notices to stdout before JSON (parse the last line); the local Docker
sandbox rejects `[environment].gpus` (use a compose device reservation on `main` if a GPU is needed);
cap-x's curobo needs `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NVIDIA_CUROBO` when built without git metadata.
