# Contributing

Thank you for helping build Embodied First Exam ([site](https://www.embodied-first-exam.ai),
[Discord](https://discord.gg/AhC6utNyfk)). Tasks follow the protocol in [docs/protocol/](docs/protocol/README.md).
This page explains how a contribution gets from an idea to `main`. Reviewers follow
[docs/REVIEWING.md](docs/REVIEWING.md). Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).
Report security problems privately ([SECURITY.md](SECURITY.md)).

Only the repository's collaborators can open pull requests. To contribute a benchmark or a task fix from outside, open
an issue, or propose it as the [contribute page](https://www.embodied-first-exam.ai/contribute/) describes. A
maintainer brings it in.

## Kinds of pull requests

| Kind | What it may change | Before you start |
|---|---|---|
| **New benchmark** | `tasks/<benchmark>/<its tasks>`, `images/<sim>/`, `tasks/<benchmark>/README.md` (and, if needed, `embodied_first_exam/benchmarks/<benchmark>/`, `ci_checks/benchmarks/<benchmark>/`) | an approved [benchmark proposal](.github/ISSUE_TEMPLATE/benchmark-proposal.yml) |
| **Tasks for an existing benchmark** | the same, without `images/` | — |
| **Task fix** | the affected task directories | describe the agent behaviour it closes; include before and after runs |
| **Shared files / protocol** | `docs/protocol/`, `docs/TAXONOMY.md`, `ci_checks/`, `.github/`, shared `scripts/`, `README.md` | a [protocol-change issue](.github/ISSUE_TEMPLATE/protocol-change.yml) for protocol changes |

- One benchmark per pull request. A pull request that adds tasks **and** changes shared files is split before review.
- A pull request delivers tasks only: task directories under `tasks/<benchmark>/`
  ([docs/protocol/tasks.md](docs/protocol/tasks.md#what-a-contribution-delivers)).
- Scripts that build or generate tasks (generators, oracle searches, instance freezers, release builders) stay outside
  this repository.
- Code several tasks share goes in the benchmark's image (`images/<sim>/`, recommended), or in
  `embodied_first_exam/benchmarks/<benchmark>/`.

## Proposal (new benchmarks)

Open a benchmark-proposal issue first, or e-mail the proposal to embodiedfirstexam@gmail.com as the
[contribute page](https://www.embodied-first-exam.ai/contribute/) describes. A good proposal shows that the tasks are:

- **verifiable** by a program, in a fresh process, without a learned judge;
- **solvable**: a positive example that the verifier (in the standard modes: the sidecar) scores 1. That is an oracle,
  an upstream expert or policy, a successful model trial, or a hand-built trajectory. Tasks without one are
  human-reviewed and marked unvalidated ([docs/REVIEWING.md](docs/REVIEWING.md#human-review-oracle-partial-or-none));
- **difficult** for today's coding agents, for a reason that matters for robotics;
- **reproducible**: a frozen scene instance. A privileged trajectory replays bit for bit (say on which hardware), or
  the task declares `[metadata] replays`. A standard episode's recorded trajectory reproduces it for the video and
  audits where the simulator replays bit for bit; otherwise the video is recorded live;
- **isolatable**: the result is computed by a party the agent cannot reach. In privileged mode that is the verifier,
  in its own sandbox, from the declared artifacts. In the standard modes it is the sim sidecar, on the live episode,
  after the agent's container stops (H.4);
- **scrubbable**: upstream reference solutions can be removed from everything the agent can reach.

It also states:

- the oracle source;
- the caps of each container of a trial: CPU cores, memory, processes, GPU memory, and GPU type (RTX-class, any or
  none; [docs/protocol/resources.md](docs/protocol/resources.md));
- the image size, and whether the images can be published;
- the expected size of the pull request.

A new benchmark's shared-files change adds its row to `scripts/task_conventions.py` `BENCHMARK_TABLE` (task-directory
prefix, label, folder). It adds a row to `ci_checks/ci_scope.py` `UNITS` only for image directories of other names.
Every benchmark has its own prefix (`task_conventions.py benchmarks --check`, `ci_scope.py --check`).

## Authoring a task

The task format (directory layout, `task.toml`, `instruction.md`, `README.md`, seeds, grading) is
[docs/protocol/tasks.md](docs/protocol/tasks.md).

1. **Start from an existing task.** Copy the closest one
   (`tasks/robotwin-2/robotwin_2_0_stack_blocks_two-privileged/` and `-standard/`), or generate tasks with your own
   tooling, kept outside this repository. Name them `<base>-privileged`, `<base>-standard` and `<base>-realtime`.
   There is no `results/` directory.
2. **Write the files.** `task.toml` (among its settings `[metadata] dynamics` and `[agent] network_mode`),
   `instruction.md` (written by a human), the verifier under `tests/` (H.1: a separate sandbox) and `solution/` (H.2).
   `normalize` renders the README and the instruction's `## Limits`. A privileged task's `task.toml`, with the fields
   you write (`normalize` adds the resource monitor's artifact and hook, `[verifier] network_mode` and main's caps):

   ```toml
   schema_version = "1.3"
   artifacts = ["/app/output/"]          # must include "/app/output/" (the task-structure check)

   [task]
   name = "embodied-first-exam/mybench-pick-cube-i00-privileged"   # embodied-first-exam/<directory name>

   [metadata]
   task_type = "trajectory"              # or "policy"
   simulator = "mujoco"                  # simulator and robot: docs/TAXONOMY.md
   robot = "franka-panda"
   family = "pick_cube"
   dynamics = "static"                   # or "dynamic" (docs/TAXONOMY.md "Dynamics")
   oracle = "full"                       # "partial" / "none" also need oracle_evidence = "..."
   instance_seed = 0                     # the default seed; [metadata.seeds] only for other seeds
   expert_time_estimate_hours = 0.5      # a standard task adds protocol = "eai-standard/3.0"

   [verifier]
   timeout_sec = 1800
   environment_mode = "separate"         # H.1

   [agent]
   timeout_sec = 3600                    # the agent's cutoff
   network_mode = "allowlist"            # or "public": open egress, the author's choice, with no host list
   ```

   - On the allowlist, `python3 scripts/set_agent_egress.py allowlist <task dirs>` writes `[agent] allowed_hosts`.
     `check-verifier-isolation.sh` requires exactly its list.
   - The cutoff, `[agent] timeout_sec`, is yours to set in this pull request, within the rules of
     [docs/protocol/running.md](docs/protocol/running.md#the-agents-time). That section also says what `normalize`
     renders from it and how the clock runs.
   - Your own text never repeats the limit as a duration. Say "the time limit (Limits)", and add what is particular to
     your benchmark (a simulator's start-up cost).
   - Your service's `time_s` and `time_left_s` count from the agent's first request to it, never from the service's
     start, and a resumed service keeps that moment
     ([docs/protocol/eai-standard.md](docs/protocol/eai-standard.md#the-agents-clock)). The shared layers do it for
     you; a test must show it.
3. **State the caps of every container.** Each number is an upper bound for one container, never a minimum. The rule
   format and where each cap ends up are in [docs/protocol/resources.md](docs/protocol/resources.md). Add a `[[cap]]`
   rule to `scripts/task_resources.toml`. For a standard task with a `sim` sidecar that holds the GPU:

   ```toml
   [[cap]]
   match = "^mybench-.*-standard$"          # a regular expression on the task directory's name; the last match wins
                                            # (`-standard$` does not match `-realtime` tasks: give them a rule too)
   main = { cpus = 4, memory_gb = 3, pids = 1024, disk_gb = 10 }      # the agent's container (cpus: a whole number)
   sim = { cpus = 4, memory_gb = 5, pids = 1024, gpu_memory_gb = 4 }   # gpu_memory_gb: only on the service that holds the GPU
   recommended_gpu = "any 8 GB+ NVIDIA GPU (RTX 4090 / L4)"
   measured = "oracle trials on an RTX 4090: sim 1.9 GiB, 1.2 GiB of GPU memory; agent's container 0.1 GiB"
   caps_measured = "memory: the sim service 1.9 GiB -> max(1.5 x peak, peak + 3), rounded up: 5 GiB; the agent's container 0.1 GiB -> peak + 2, rounded up: 3 GiB; GPU memory (the sim service): 1.2 GiB -> max(1.5 x peak, peak + 2), rounded up: 4 GiB; processes and disk: no thread count measured, the minimums (1024, 10 GiB)"
   ```

   For the same task in privileged mode, where the agent's own container runs the simulator and holds the GPU:

   ```toml
   [[cap]]
   match = "^mybench-.*-privileged$"
   main = { cpus = 8, memory_gb = 10, pids = 1024, disk_gb = 10, gpu_memory_gb = 4 }
   gpu_types = ["L40S", "L4", "RTX 4090"]   # only if the task needs ray-tracing cores (RTX-class models); else leave it out
   caps_measured = "the agent's container: memory 6.2 GiB -> max(1.5 x peak, peak + 2), rounded up: 10 GiB; GPU memory 1.3 GiB -> max(1.5 x peak, peak + 2), rounded up: 4 GiB; 300 threads -> 1024 (2 x peak, at least 1024); disk: the minimum (10 GiB)"
   ```

   - One table per compose service; the names must be the compose file's. Set `gpu_types` only when the task needs an
     RTX-class GPU.
   - The GPU itself is a device reservation you write in the compose file (`deploy.resources.reservations.devices`,
     `driver: nvidia`, `capabilities: [gpu]`). Caps go in `cpus`, `mem_limit` and `pids_limit`, never in
     `deploy.resources.limits`.
   - A separate verifier's caps are the `cpus` and `memory_mb` you set in `[verifier.environment]`.
   - Measure the oracle, and agent trials if you can (`docker stats` or cgroup `memory.peak`, `nvidia-smi`). Set the
     caps as [resources.md](docs/protocol/resources.md#how-a-rules-caps-are-chosen) says: the peaks with a margin, and
     the largest call the task allows.
   - Make sure the oracle stays inside them, unless the benchmark's README states an exception: a process over any cap
     but CPU can be killed.
   - Then run `scripts/task_conventions.py` on the tasks. `check-resources.py` checks the result.
4. **Base images.** `images/<sim>/Dockerfile`, versioned in `images/<sim>/VERSION`, built and pushed with
   `scripts/images.sh build` and `scripts/images.sh push` ([docs/operations.md](docs/operations.md#base-images)).
   - Images that cannot be published carry `images/<sim>/BUILD_ONLY` and build instructions.
   - A task on a private image builds it itself when the runner cannot pull it. Its Dockerfile starts with the recipe
     between `# >>> images/<sim>/Dockerfile` and `# <<< images/<sim>/Dockerfile`: the recipe's first
     `FROM ... AS <sim>-base`, then the task's own stage `FROM <sim>-base`. `normalize` writes the current recipe
     there.
   - Its compose service names the private image in `build.cache_from`. For main: `build:` with `cache_from` only. For
     a sidecar: `build:` with `context` and `dockerfile` inside `environment/`, and `cache_from`.
   - The recipe needs no build context. Every file it takes comes from a public files-only image
     (`COPY --from=<image@digest>`) or a public URL (`ADD --checksum`). A URL into this repository names a commit that a
     tag keeps reachable, since main is squashed and GitHub drops unreachable commits. System packages come from a
     dated snapshot (e.g. snapshot.debian.org).
   - The private image is that recipe built with BuildKit's inline cache (`scripts/images.sh build` adds it to every
     `BUILD_ONLY` image). A runner that can pull it takes its layers. Any other runner builds the same layers from
     public sources.
5. **Agents.** Run agents with Harbor's native agents only (`-a codex`, `-a claude-code`, …). No adapters, and no
   gateway that holds credentials or changes requests. The usage gateway, which only records token usage, is allowed
   ([docs/protocol/running.md](docs/protocol/running.md#official-runs)).

## Before opening the pull request

```bash
bash ci_checks/run_invariants.sh tasks/<benchmark>/<your tasks>   # must pass (the required CI job `invariants`)
bash ci_checks/run_all.sh tasks/<benchmark>/<your tasks>      # both tiers: fix the advisory findings or say why the task departs
bash ci_checks/run_all.sh --changed               # what CI runs on your pull request (scope: ci_checks/ci_scope.py)
python3 scripts/task_conventions.py --check tasks/<benchmark>/<your tasks>     # every task in the normal form
python3 ci_checks/check-resources.py tasks/<benchmark>/<your tasks>             # the caps of every container, README and instruction
python3 ci_checks/check-cutoffs.py tasks/<benchmark>/<your tasks>               # the cutoff: task.toml = instruction = README = sim service, within the cap
python3 ci_checks/check-twins.py tasks/<benchmark>/<your tasks>                 # the same cutoff and seeds across a task's modes (H.7)
python3 scripts/stamp_mtimes.py tasks             # before any image build from the checkout (below)
harbor run -p tasks/<benchmark>/<task> -a oracle               # on a sample: >= 2 tasks per mode
harbor run -p tasks/<benchmark>/<task> -a nop                  # must score 0
python3 scripts/task_conventions.py tasks/<benchmark>/<your tasks>    # after a hand edit: normalize, which also refreshes each DIGEST
```

**Stamp before you build.** Never build a task image (a `harbor run`, a `docker build` of `environment/` or `tests/`)
from a tree you have not stamped with `scripts/stamp_mtimes.py`. Docker's BuildKit reuses another build's same-name
context file when its size and mtime match, and a checkout gives many files one mtime. A task can then silently run or
be graded with another task's file ([docs/operations.md](docs/operations.md#building-task-images-stamp-first)). Tools
that build images run from a stamped copy (`stamp_mtimes.py stage`); a new one does the same.

**Determinism.** For a new simulator or family, also replay the oracle (or a positive example) twice in fresh
processes, and include the matching state hashes. Where fresh replays end in different states, the task declares
`[metadata] replays = 3`, and its grader stops at the first successful replay.

## Tasks without an oracle

Tasks with `oracle = "partial"` or `"none"` (with `oracle_evidence`) are allowed, but they need **human review**. The
pull request is labelled `needs-human-review` and is merged only after a maintainer other than the author approves it.
Provide, per family, a positive example the verifier scores 1, the `nop` result and a short description of the success
predicate. The checklist is in [docs/REVIEWING.md](docs/REVIEWING.md#human-review-oracle-partial-or-none).

## Review and merge

1. **Static checks** run on every pull request (`.github/workflows/static-checks.yml`), on what the pull request can
   affect (`ci_checks/ci_scope.py`, from the diff against `main`).
   - A pull request that changes only one benchmark's own paths (its `tasks/<benchmark>/`, `images/<bench>/`,
     `ci_checks/benchmarks/<benchmark>/`, plus the benchmarks that share code with it) runs the per-task checks
     (including each task's `DIGEST`), `task_conventions.py --check` and `check-cutoffs.py` on that benchmark's tasks.
   - The cheap repo-level checks (resources, protocol, ...) always run on every task.
   - Anything shared runs the full suite: `ci_checks/`, `.github/`, the shared `scripts/` modules and tables
     (`task_conventions.py`, `task_resources.toml`, ...), `embodied_first_exam/standard/`, `images/monitor/`, the
     protocol documents (`docs/protocol/`), or a path the scope table does not know. So do every push to `main`, the
     nightly run and a manual run (`workflow_dispatch`). The CI mutation self-test (`check-ci-selftest.py`) runs with
     the full suite.
   - The checks are in two tiers. The job **`invariants`** (`ci_checks/run_invariants.sh`: the checks that enforce
     the invariants) is the only one that blocks a merge. It fails on any failure, error or incomplete run. The job
     **`advisories`** (`ci_checks/run_all.sh --tier advisory`) reports every other finding as a warning (annotations,
     the job summary). Locally, `bash ci_checks/run_all.sh` runs both: exit 0 clean, 1 an invariant failed, 3
     advisory findings only.
2. **The overview.** A sticky overview comment (posted by the job `advisories`, `ci_checks/pr_overview.py`) lists the
   tasks the pull request adds or changes, the cutoffs it changes, the scope of its checks and the advisory findings
   ("Advisories (not blocking)": fix them or say why the task departs). It labels the pull request (`new-task`,
   `task-fix`, `shared`, `cutoff-change`).
3. **Runs.** A maintainer reviews the files and comments `/validate` to run the oracle (where `oracle = "full"`) and
   `nop` on the changed tasks (`.github/workflows/validate-task.yml`, on the GPU runner; the results come back as a
   comment). `/validate` needs a dedicated runner with the `docker` label; without one, the reviewer runs the oracle
   and `nop` by hand. For a new benchmark, the maintainer also runs an adversarial ("cheat") trial and a model trial.
4. **Merge** requires the required check `invariants` passing (branch protection), a maintainer approval (CODEOWNERS
   for shared files), human review where required, and a branch up to date with `main`.
5. **After merge**, `.github/workflows/task-list.yml` regenerates the task list and pushes it to the branch
   `task-list` (`TASKS.md`, `tasks.json`, `dataset.toml`; nothing in `main` lists the tasks). Maintainers publish base
   images and update the results site. A release (tag `v<semver>`) gets the same files as assets
   (`.github/workflows/release.yml`).

## Rules that apply to every contribution

- **Changing a published task.** It may be changed in place, its scene included. It keeps its name and gets a new
  `DIGEST` (H.8), and results are attributed by digest. Say what changed and why in the pull request. The README
  describes the task as it is.
- **Changing a cutoff** is the task author's decision. The maintainers step in only where official results must stay
  comparable. Set the new `[agent] timeout_sec` in every mode of the task, run `python3 scripts/task_conventions.py`
  on them, and say old → new and why in the pull request
  ([docs/protocol/running.md](docs/protocol/running.md#the-agents-time)). The task keeps its name and gets a new
  digest. Results under the earlier cutoff are ranked separately.
- **A sidecar's directory** (`environment/sim/`, `environment/scorer/`, served at `/srv`) holds only what is the
  task's own: its frozen instance, per-task grader data, files no other task has.
  - Files it shares with other tasks come from a pinned files-only image: the benchmark's `images/<folder>-files/`
    (sources under `embodied_first_exam/benchmarks/<folder>/`; the same image serves its agent and verifier images),
    or `images/standard-files/` for the service layers ([docs/operations.md](docs/operations.md#files-only-images)).
  - A benchmark may also have files images that hold only data (goal pictures, build inputs), and one per further
    simulator image it runs on, as RoboARC's IKEA suite does.
  - The sidecar is built from its directory (`build: context: sim`). Its `Dockerfile` runs `COPY . /srv/`, then
    `COPY --from=<image@digest>` of those files at their paths under `/srv`. `.dockerignore` keeps the two build files
    out.
  - A private evaluator's own data (hidden plants, case banks) and files that may not be redistributed stay in the
    task directory.
- **Pin everything**: `FROM` tags or digests, pip versions. No network access during verification.
- **The agent's egress** ([H.6](docs/protocol/invariants.md#h6-egress),
  [docs/protocol/running.md](docs/protocol/running.md#network)) is the allowlist by default. A task whose author
  chooses open egress declares `[agent] network_mode = "public"`. `normalize` writes the Network line of `## Limits`.
  - Bake what the task itself needs at run time into the image or the task directory. An agent may install packages;
    a task must not depend on it.
  - If a distribution on PyPI ships your benchmark's solutions or task sources, add it to the table in
    [docs/protocol/leakage.md](docs/protocol/leakage.md) ("Packages on PyPI").
  - Keep provenance (source repository, dataset, demonstration file, expert module) out of every file under
    `environment/` that the agent reads. Look through a new image for recorded episodes and links to them
    (`ci_checks/check-agent-pointers.py` covers the task's own files only).
- **The agent is root in its container.** Assume it can modify anything under `/app` and `/opt`. Grading therefore
  runs in a separate sandbox, and only the declared artifacts cross over (H.1).
- **Benchmark-specific checks** go into the benchmark's own `ci_checks/benchmarks/<bench>/`: an `invariant-*` hook
  (it guards an invariant: blocking) or an `advisory-*` hook (a convention: a warning). Shared `ci_checks/` names no
  benchmark.
- **Nothing private in the repository**: no credentials, personal absolute paths, large binaries or agent results.
  Results go to the results site and the Hugging Face dataset.
- **Formatting.** Format new Python code with `ruff format` (line length 120).
