# Contributing

Three kinds of contribution, in increasing effort. All go through a PR; CI runs `ci_checks/run_all.sh`.

## 1. A new instance of an existing family (minutes)

```bash
scripts/install.sh                     # once: harbor CLI + cap-x venv for making instances
PYTHONPATH=. python -m rcb.new_task --family cube_stack --seed 7 --author "Your Name"
bash ci_checks/run_all.sh tasks/robosuite-cube-stack-i07
harbor run -p tasks/robosuite-cube-stack-i07 -a oracle      # reward must be 1
harbor run -p tasks/robosuite-cube-stack-i07 -a nop         # reward must be 0
cd tasks && harbor add --scan . && cd ..                     # register in tasks/dataset.toml
```

Fill the `## Difficulty` section of the task `README.md` (why this layout is non-trivial: reach,
occlusion, grasp orientation, …). Then open the PR with the oracle job summary pasted in.

Rules:
- **Never regenerate `tests/instance.npz` of a shipped task.** The instance *is* the task; its sha256 is
  pinned in `task.toml` and checked by CI. Robosuite's robot init noise is unseeded, so the same seed
  yields a different instance.
- `environment/instance.npz` and `tests/instance.npz` are identical copies; the agent may modify its copy,
  the grader uses `/tests/`.
- Do not edit generated files by hand except `README.md`; re-run `rcb.new_task --render` after template changes.

## 2. A new family in an existing simulator (hours)

1. cap-x must already provide the exec env, low-level env, privileged API **and human-written oracle code**
   (`<ExecEnv>.oracle_code`). If not, add them to cap-x first (upstream PR or our submodule fork).
2. Add one entry to `rcb/adapters/capx_robosuite.py::TASKS` (`exec_env`, `low_level`, `apis`, `text`,
   `simulator`, `robot`, `image`).
3. Prove determinism on the host:
   `cd third_party/cap-x && PYTHONPATH=$PWD/../.. MUJOCO_GL=egl uv run --no-sync python -m rcb.traj selftest --task <family> --seed 0 --repeat 3`
   must print `"PASS": true` (oracle succeeds live; every replay succeeds; all state hashes equal).
   Paste the output in the PR.
4. Generate 3–5 instances (step 1) and check that the oracle passes on each.
5. Add the family to `docs/TAXONOMY.md`.

Watch for: primitives that read cached observables (must refresh after `set_state`), controller state that
is not in `qpos/qvel` (re-anchor goals), stochastic primitives (seed them from the Session), and success
predicates that depend on wall-clock or step counters.

## 3. A new simulator (days)

- `rcb/adapters/<sim>.py` with a `TASKS` registry and, if the state snapshot/restore differs, a `Session`
  subclass (see `rcb/traj.py` for the robosuite hooks: `_snapshot`, `_restore`, `_restore_wrapper_bookkeeping`,
  `_hooked_step`).
- `images/<sim>/Dockerfile`; bump `images/VERSION`; build with `scripts/build_images.sh`, push with
  `scripts/push_images.sh`. Every task Dockerfile must `FROM ghcr.io/<org>/rcb-<sim>:<VERSION>` (CI checks).
- GPU simulators: the local Docker sandbox rejects `[environment].gpus`; instead add a
  `environment/docker-compose.yaml` with an nvidia device reservation on `main` (see `docs/PROTOCOL.md`
  and the robot_osworld notes). Non-deterministic physics needs a different grader (majority-of-N).

## Instruction writing

Human-written. State the deliverable path, action layout, coordinate frame and quaternion order, and the
reset/self-check tools; withhold nothing the agent cannot infer from the primitives' docstrings. Never
reference `/tests/`. Keep it identical across instances of a family except the title.

## Repairs

A fix to a shipped task goes through a PR that explains which agent behaviour it closes and includes a
before/after trajectory or oracle run. Changing the instance file is a new task, not a repair.

## Releases

`images/VERSION` and the dataset version move together. Tag `vX.Y.Z` on `main`, push images, then
`harbor publish tasks/` (private by default; `harbor dataset share --org …` or `--public`).
