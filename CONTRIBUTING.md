# Contributing a task

A task is a plain Harbor task directory that follows [docs/PROTOCOL.md](docs/PROTOCOL.md). Start by copying
the example and changing what you need.

## Steps
1. `cp -r tasks/robosuite-cube-stack-i00 tasks/<simulator>-<family>-i<NN>` (or `harbor task init` for a
   blank one). Slug rules: `docs/TAXONOMY.md`.
2. Edit `task.toml`: `[task].name = "robot-coding-bench/<folder>"`, metadata fields, timeouts.
3. `environment/`: a `Dockerfile` that `FROM`s a **pinned** registry image and `COPY`s everything the agent
   needs (scene definition, tooling). Need a new simulator? Add `images/<sim>/Dockerfile`, build with
   `scripts/build_images.sh`, push with `scripts/push_images.sh`, bump `images/VERSION`.
4. `instruction.md`: human-written; states the deliverable under `/app/output/`, the action layout, frames,
   quaternion order, and the tools; never mentions `/tests/`.
5. `tests/test.sh` + your verifier: fresh-process verification, `reward.txt` 1/0, numeric-only `reward.json`
   with the field names from PROTOCOL §3. Keep the verifier's inputs (scene copy, tooling) under `tests/`, add a
   `tests/Dockerfile` that bakes them into `/tests/` on top of the same base image (+ `tests/docker-compose.yaml` if
   replay needs the GPU), and set `[verifier] environment_mode = "separate"` in `task.toml` — the verifier must not
   run in the agent's container (PROTOCOL §4). Agent egress stays Harbor-default (public); `scripts/set_agent_egress.py`
   flips all tasks to model-APIs-only for runs where fetching the public reference solutions must be ruled out.
6. `solution/solve.sh`: a human-written oracle that scores 1. Keep the reference code itself in `solution/` too;
   never bake it into `environment/` or a base image, and make sure agent-visible tooling does not reference it.
7. `README.md`: fill **Difficulty**, **Reference solution**, **Verification**.
   Agent runs go under `results/<agent-slug>/` inside the task directory (`README.md` with result, cost, the verifier's
   `replay.mp4` / `replay.last.png` and an analysis; `scripts/write_task_results.py` writes them from a Harbor job).
   Adding results changes the task digest in `dataset.toml`; re-scan.
8. Check and run:
   ```bash
   bash ci_checks/run_all.sh tasks/<your-task>
   harbor run -p tasks/<your-task> -a oracle      # must be 1
   harbor run -p tasks/<your-task> -a nop         # must be 0
   cd tasks && harbor add --scan . && cd ..       # register in dataset.toml
   ```
9. Open a PR with the oracle job summary (and, ideally, one strong-model run and why it failed).

## Rules
- A shipped task's `environment/` and `tests/` inputs are immutable; changing the scene is a new task.
- Determinism is on you: `selftest`-style evidence (live run == replay, repeated) is required for a new
  simulator or family. For MuJoCo see the example's `_snapshot/_restore/_restore_wrapper_bookkeeping`.
- Pin everything (`FROM` tag, pip versions). No network fetches at verification time.
- Agents run as root inside their container; assume they can edit anything under `/app` and `/opt`, including the
  simulator and the task's success predicate. That is why the verifier runs in a separate sandbox built from
  `tests/Dockerfile`; only the declared artifacts cross over.

## Repairs
Fix PRs explain which agent behaviour the change closes and include before/after runs. Pass rates alone are
not evidence.
