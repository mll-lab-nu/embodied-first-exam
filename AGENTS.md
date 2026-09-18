# AGENTS.md — map for coding agents working in this repo

Read `README.md` (what/why), `docs/PROTOCOL.md` (scoring), `CONTRIBUTING.md` (workflow) first.

## Where things are
- `rcb/traj.py` — `Session`: builds a cap-x env, freezes/restores an instance (qpos, qvel, time, warm-start;
  then controller re-anchor + observable refresh), records low-level actions by hooking `_do_robosuite_step`,
  replays them, runs the oracle. CLI: `make-instance | run-oracle | replay | selftest`.
- `rcb/grade.py` — verifier; the only thing `tests/test.sh` calls. Writes numeric-only `reward.json`.
- `rcb/new_task.py` — all task templates (instruction, task.toml, README, Dockerfile, test.sh, solve.sh).
  Edit templates here, then `--render` existing tasks; never hand-edit generated files (except README body).
- `rcb/adapters/capx_robosuite.py` — family registry. New family = one dict entry + selftest evidence.
- `images/robosuite/Dockerfile` — base image; `images/VERSION` pins the tag used by every task Dockerfile.
- `ci_checks/` — `bash ci_checks/run_all.sh [task dirs]`. Add a check as `check-<thing>.sh <task_dir>`
  printing `FAIL <task>: <reason>` and exiting 1; register it in `run_all.sh`.
- `tasks/dataset.toml` — allowlist manifest; regenerate with `cd tasks && harbor add --scan .`.

## Invariants to preserve
- One task == one frozen instance; `tests/instance.npz` sha256 is pinned in `task.toml`.
- Replay must be bit-exact across processes (`selftest` PASS) before a family ships.
- `instruction.md` never mentions `/tests/`; the agent's copy of the instance is `/app/instance.npz`.
- `reward.json` fields are numeric only (Harbor `VerifierOutputParseError` otherwise).
- cap-x prints import notices to stdout; parse its JSON from the last line.
- Local docker sandbox: no `[environment].gpus`; use compose device reservations if a GPU is needed.

## Local commands
```bash
bash ci_checks/run_all.sh
scripts/build_images.sh                                   # or sg docker -c "..." before re-login
harbor run -p tasks/<task> -a oracle -o jobs && harbor view jobs
cd third_party/cap-x && PYTHONPATH=$PWD/../.. MUJOCO_GL=egl uv run --no-sync python -m rcb.traj selftest --task cube_stack
```
