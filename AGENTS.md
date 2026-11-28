# AGENTS.md: a map for coding agents working in this repo

Read first: `README.md`, `docs/protocol/README.md` (the index of the protocol), `docs/protocol/invariants.md` (the
eight invariants H.1-H.8; no task value overrides them), `docs/protocol/tasks.md` (the task format) and
`CONTRIBUTING.md`.

## Where things are

| What | Where |
|---|---|
| Tasks | `tasks/<benchmark>/<task>/`, one folder per benchmark (`BENCHMARK_TABLE` in `scripts/task_conventions.py`) |
| Benchmark-level rules (templates, budgets, tooling, world frame) | `tasks/<benchmark>/README.md` |
| Code several tasks share | the benchmark's base image `images/<sim>/` (recommended), else `embodied_first_exam/benchmarks/<benchmark>/` |
| Service layers of the standard and realtime modes | `embodied_first_exam/standard/` ([its README](embodied_first_exam/standard/README.md)) |
| Wire protocol | `docs/protocol/eai-standard.md`, `docs/protocol/eai-standard.openapi.yaml` |
| Resource caps | `scripts/task_resources.toml` (rules), `docs/protocol/resources.md` |
| Runs and results | `docs/protocol/running.md`; hosts, images and the usage gateway: `docs/operations.md` |
| Metadata values, task names, run ids | `docs/TAXONOMY.md` |
| CI | `ci_checks/` |

## Modes and protocol

- Three modes: **privileged**, **standard** and **realtime**. Task directories end in `-privileged`, `-standard` or
  `-realtime` (`MODE_REGISTRY` in `scripts/task_conventions.py`).
- Standard and realtime tasks speak one wire protocol, `eai-standard/3.0`. What a service offers beyond the base is
  listed by the capabilities in its `/spec` (shared, realtime, operations, match).
- The rules that hold on every service (`EAI_STANDARD` in `scripts/task_conventions.py`):
  - `/observe` only reads (`last_s`; `seconds > 0` is a 400);
  - a hold chunk (`/submit` with `interpolate = "hold"` and `seconds`, no rows) lets time pass;
  - `/submit` replies carry `duration_s`;
  - the realtime clock starts at the first `/submit`;
  - the clients have `get_obs(last_s=)`, `hold()` and `finish()`.
- Every standard and realtime episode is agent-ended. The service never shows the success. `POST /finish` ends the
  episode, and the state it ends in is judged.
  - `normalize` writes `RCB_AGENT_END` and the instruction's Finish line. `ci_checks/check-agent-end.py` checks them.
  - The layers that implement it: `sidecar/rcb_service.py` (sidecar), `realtime/rcb_realtime.py` (realtime),
    `agent_end/rcb_agent_end.py` (shared, operations), all under `embodied_first_exam/standard/`.
- Every standard and realtime task also offers its service as the `efe-robot` MCP server, one tool per agent-facing
  endpoint.
  - Source: `embodied_first_exam/standard/mcp/`. `normalize` writes each task's `environment/efe_mcp/manifest.json`,
    the Dockerfile lines, the `[[environment.mcp_servers]]` entry and `### MCP tools` (`mcp/inject.py`).
  - `ci_checks/check-mcp-tools.py` checks it.
- The match extension (Embodied Olympics - Match): `embodied_first_exam/benchmarks/embodied-olympics-match/eai_std/`.
  `apply_eai_std.py` copies it unchanged into each match task's `environment/sim/eai_std/`
  (`ci_checks/benchmarks/embodied-olympics-match/invariant-eai-std.py`). The match's `core/` stays as exported.

## Tasks

- A pull request delivers tasks only. No task-generation code in the repository. `scripts/` holds only what running
  the benchmark needs.
- Every task is in the normal form of `scripts/task_conventions.py` (`normalize`): fields, protocol spelling,
  `test.sh`, graders, README, `## Limits`, `DIGEST`.
  - `python3 scripts/task_conventions.py --check tasks/<benchmark>/<task>` reports a task it would change.
  - After a hand edit: `python3 scripts/task_conventions.py tasks/<benchmark>/<task>`.
- Tasks are self-contained Harbor task directories. Nothing at run time imports repository code outside the task
  directory. No `results/` in task directories.
- Find a task directory with `task_dir(name)` or `iter_tasks()`, never by joining `tasks/` and a name.
- Reference tasks: `tasks/robotwin-2/robotwin_2_0_stack_blocks_two-privileged/` and
  `tasks/robotwin-2/robotwin_2_0_stack_blocks_two-standard/`.
- Every `instruction.md` has `## Task`, `## Goal`, `## Robot Interface`, `## Others` (optional) and `## Limits`, in
  this order (`V2_SECTIONS`). `normalize` renders `## Limits`: Time, Tokens, Network, Resources, the task's own
  lines, and the Finish line of a standard or realtime task.
- Every per-task `README.md` is rendered by `normalize`: Task, Success criteria, Resource requirements, Others
  (optional), License (`docs/protocol/tasks.md`).
- `tasks/<benchmark>/<task>/DIGEST` is the task's content digest (H.8), written last by `normalize`.
  `ci_checks/check-dataset-manifest.sh` recomputes it.
- The release manifest `tasks/dataset.toml` is generated (`scripts/dataset_manifest.py write`) and not committed. The
  task list (`TASKS.md`, `tasks.json`, `dataset.toml`) is pushed to the branch `task-list` after every merge
  (`.github/workflows/task-list.yml`; locally `scripts/dataset_manifest.py list --out DIR`).
- The agent's cutoff is each task's own `[agent] timeout_sec`, set by its author
  (`docs/protocol/running.md`, "The agent's time"). A benchmark's own text says "the time limit (Limits)", never a
  duration. Checks: `ci_checks/check-cutoffs.py` (advisory), `ci_checks/check-twins.py` (H.7: the same number across
  a task's modes).
- Seeds: `[metadata] instance_seed` is the default seed. `[metadata.seeds]` only where a task allows others.
  - Committed non-default instances live under the privileged task's `tests/seeds/<seed>/`, never under
    `environment/`.
  - `scripts/task_seed.py materialize` puts them in place. `ci_checks/check-seeds.py` checks them.
- Scene dynamics are each task's `[metadata] dynamics`. There is no central table.
- A task needs no download at run time: bake it into the image or the task directory. Nothing an agent can read
  (image, tooling, instance metadata) names or locates a solution.

## Shared code and images

- A benchmark's shared files reach its tasks through a files-only image (`scripts/files_image.py`,
  `images/<name>/FILES.json`). The tasks' Dockerfiles `COPY --from=<image@digest>` each file to the path a copy would
  have had. A sidecar is built from its own `environment/sim/Dockerfile`, which puts the directory and those files at
  `/srv`.
- The service layers ship from the files-only image `standard-files`: the shared layer (`rcb_limited.py`,
  `rcb_client.py`, `rcb1.py`, `run.sh`), the operations layer, the sidecar service `rcb_service.py`, the realtime
  layer, `live_video.py`, the agent-end layer and the MCP server. Tasks carry no copies.
  `ci_checks/check-tooling-identity.sh` checks the pins.
- Each benchmark adds only its adapter `server.py`, in `embodied_first_exam/benchmarks/<benchmark>/sim/` or in the
  task's `environment/sim/`. `embodied_first_exam/standard/toy_server.py` is the smallest adapter.
  `task_conventions.service_layer` says which tasks are on the shared layer.
- Crash recovery in the shared layer is an implementation detail; the protocol's rule is the runner's rerun (H.5).
  `python3 embodied_first_exam/standard/selftest.py` tests it on the CPU in about two minutes.
  `python3 embodied_first_exam/standard/operations/selftest.py` tests the operations layer in about 15 seconds.
- Base images: `images/<sim>/Dockerfile`, tagged `ghcr.io/mll-lab-nu/efe:<name>-<version>` (private:
  `efe-private:<name>-<version>`) from `images/<sim>/VERSION`. Build and push with `scripts/images.sh build|push`.
- MuJoCo tasks (`dextoolbench_*`, `mujoco_playground_*`) use `images/mujoco/`. Run `prepare_assets.sh` first.
- A local docker sandbox has no `[environment].gpus`. RoboTwin and MuJoCo tasks pass a GPU through with
  `environment/docker-compose.yaml` (service `main`, an nvidia device reservation; `sim` in standard mode). Copy it
  from `tasks/robotwin-2/robotwin_2_0_stack_blocks_two-privileged/`.

## Resources

- Every resource number is a cap for one container (`docs/protocol/resources.md`).
- Edit the `[[cap]]` rules of `scripts/task_resources.toml`, never a task's caps or its README's resource section:
  `normalize` writes both.
- The monitor sidecar (`images/monitor/rcb_monitor/`, in the pinned `ghcr.io/mll-lab-nu/efe:monitor-<version>`
  image) changes with a new image version only. `normalize` wires it into every task, which keeps only its
  `limits.json`. `ci_checks/check-monitor.py` runs its tests.
- A CPU cap above the host's CPU count is the runner's to clamp. The values in `scripts/task_resources.toml` stay.
- The `sanitize` line in every `tests/test.sh` removes links and special files from `/app/output` before the grader
  reads the agent's files.

## CI

- Two tiers.
  - `ci_checks/run_invariants.sh [task dirs]` is the required job `invariants`. It runs only the checks that enforce
    the invariants, and fails on any failure, error or incomplete run.
  - `ci_checks/run_all.sh [task dirs]` runs it, then every advisory check. `--tier advisory` alone: exit 3 means
    warnings only.
- A new per-task check is `check-<thing>.sh <task_dir>`, listed in `ci_checks/check-task.sh` under `INVARIANT_CHECKS`
  (it guards an invariant) or `ADVISORY_CHECKS`.
- A benchmark-specific check is that benchmark's hook `ci_checks/benchmarks/<bench>/invariant-*` or `advisory-*`.
  Shared `ci_checks/` names no benchmark.
- An invariant rule also gets a mutation in `ci_checks/check-ci-selftest.py`: a real task broken that way must fail
  the rule (`--tier invariants`).
- Run the checks from a checkout made with `umask 022` (`run_all.sh` sets it for itself).
- `ci_checks/check-unit-tests.sh --all` runs the service-layer tests that need numpy and requests (CI job
  `unit-tests`).
- Everything runs concurrently (`ci_checks/parallel.py`; `RCB_CI_JOBS` caps it).
- CI on a pull request runs `run_all.sh --changed`, scoped by `ci_checks/ci_scope.py`: one benchmark's own paths run
  its tasks, shared code runs the full suite. Pushes to main and the nightly run are the full suite.
- A benchmark's own paths come from `BENCHMARK_TABLE`. A `ci_scope.py` `UNITS` row only names an image directory of
  another name (`ci_scope.py --check`).

## Runs

- Run agents with Harbor's native agents only (`-a codex`, `-a claude-code`). No adapters, and no gateway that holds
  credentials or changes requests.
- The usage gateway (`scripts/usage_gateway/`, `GATEWAY=1` in `run_agent_batch.sh`; official runs use it) forwards
  model-API calls only (`api_paths.json`; anything else at a provider is a 403) and records token usage. With the
  package registries it is the agent container's only egress (`docs/operations.md`, "The usage gateway").
- No tool outside the container in official runs. The harness's web search is off (`run_agent_batch.sh` default
  `WEB_SEARCH=disabled`), as are account connectors, apps and plugins.
- A task's agent egress: H.6 and `docs/protocol/running.md`, "Network" (`[agent] network_mode`, `allowlist` or
  `public`). `normalize` renders it in the Network line of every instruction's `## Limits`.
- Unattended batches: `scripts/run_agent_batch.sh` (lanes with per-job claims, configured by environment variables;
  `docs/protocol/running.md`). Its runner-side tools (`log_mirror.py`, `mem_guard.py`, `scan_secrets.py`,
  `account_failure_check.py`) are not task code.
