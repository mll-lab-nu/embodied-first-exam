# Contributing

Thank you for helping build Robot Coding Bench. Tasks follow the contract in [docs/PROTOCOL.md](docs/PROTOCOL.md);
this page explains how a contribution gets from an idea to `main`. Reviewers follow [docs/REVIEWING.md](docs/REVIEWING.md).

## Kinds of pull requests

| Kind | What it may change | Before you start |
|---|---|---|
| **New benchmark** | `tasks/<its tasks>`, `scripts/<bench>/`, `images/<sim>/`, `docs/benchmarks/<bench>.md`, `tasks/dataset.toml`, its row in `scripts/task_cutoffs.toml` | an approved [benchmark proposal](.github/ISSUE_TEMPLATE/benchmark-proposal.yml) |
| **Tasks for an existing benchmark** | the same, without `images/` | — |
| **Task fix** | the affected task directories and their generator | describe the agent behaviour it closes; include before/after runs |
| **Shared files / protocol** | `docs/PROTOCOL.md`, `docs/STANDARD_MODE.md`, `docs/TAXONOMY.md`, `ci_checks/`, `.github/`, shared `scripts/`, `README.md` | a [protocol-change issue](.github/ISSUE_TEMPLATE/protocol-change.yml) for protocol changes |

One benchmark per pull request. A pull request that adds tasks **and** changes shared files is split before review.

## Proposal (new benchmarks)
Open a benchmark-proposal issue first. A good proposal shows that the tasks are:
- **verifiable** by a program, in a fresh process, without a learned judge;
- **solvable** — a positive example the verifier scores 1: an oracle, an upstream expert or policy, a successful
  model trial, or a hand-built trajectory (tasks without one are human-reviewed and reported separately, PROTOCOL §7);
- **difficult** for today's coding agents, for a reason that matters for robotics;
- **reproducible** — bit-exact replay of a frozen scene instance, and the hardware it was checked on;
- **isolatable** — the verifier can recompute the result in its own sandbox from the declared artifacts;
- **scrubbable** — upstream reference solutions can be removed from everything the agent can reach.

It also states the oracle source (§2.7 of the protocol), the minimum compute per trial (CPU cores, memory, GPU memory
and GPU class, §2.9), image size, whether the images can be published, and
the expected size of the pull request.

## Authoring a task
1. Copy the closest existing pair (`tasks/robotwin_2_0_stack_blocks_two-privileged/` and `-standard/`) or generate tasks
   with a script under `scripts/<bench>/`. Name them `<base>-privileged` / `<base>-standard` (and `<base>-standard-realtime` for the standard-realtime mode, PROTOCOL §2.2, §4b) and write
   the README in the standard layout (§2.1); there is no `results/` directory.
2. Fill in `task.toml` (PROTOCOL §2.3), `instruction.md` (§2.5, written by a human), the verifier under `tests/`
   (§2.6, separate sandbox) and `solution/` (§2.7).
   The agent's time cutoff (PROTOCOL §2.12) is not written in the task: add your benchmark's row to
   `scripts/task_cutoffs.toml` (seconds per mode; 3600 unless you justify more, D8), named by the benchmark's label in
   `scripts/task_conventions.py` `BENCHMARKS` (task-directory prefix -> name: a new benchmark adds it in its
   shared-files pull request), with a `[[history]]` entry (`from_sec = 0`). The row goes in the pull request that adds
   the benchmark's first tasks: a row without tasks fails CI, and so do tasks without a row. `normalize` writes the number into
   `[agent] timeout_sec` and the standard modes' `RCB_WALL_CLOCK_S`, and ends `instruction.md` with the `## Time limit`
   section, after `## External material` and `## Resource limits` ("You have N seconds to complete this task. Do not
   cheat by using online solutions or hints specific to this task.", then what the cutoff means in the mode). Your own
   text never repeats the limit as a duration: say "the time limit (`## Time limit`)", and add what is particular to
   your benchmark (a simulator's start-up cost, what your service's `time_left_s` counts from). A family or a single
   task that needs another number than its benchmark gets an exception in the same table (owner decision).
3. State the minimum compute (PROTOCOL §2.9): CPU cores, memory and GPU memory of the agent phase and the verifier
   phase, the GPU class and a recommended GPU, derived from measured peaks (oracle or agent trials; `docker stats` /
   cgroup `memory.stat` and `nvidia-smi` while they run). Add a rule to `scripts/task_resources.toml` (or have the
   generator write `[metadata.resources]`); `scripts/task_conventions.py` writes it into `task.toml` and renders the
   README's `## Compute resources`.
   Add the resource limits and caps too (PROTOCOL §2.10): a `[[limit]]` and a `[[cap]]` rule in the same file (scope
   `trial` for privileged tasks, `agent` for standard ones; GPU memory, memory, processes, disk in GiB, the whole trial's
   expected peak, `measured`; docker caps per compose service). `normalize` writes `[metadata.resources.limits]` /
   `.caps` and writes the `## Resource limits` paragraph the agent reads into `instruction.md` (just before the closing
   `## Time limit`). With enforcement on
   (`RCB_LIMITS_ENFORCE=1`, v1.2) exceeding a limit fails the trial, so set them a generous margin above measured peaks
   (e.g. `max(1.5 x peak, peak + 4 GiB)`) and make sure the oracle stays inside them. The caps are the ones docker
   applies: `normalize` sets `[environment].memory_mb` from `caps.main.memory_gb` and writes the other services' caps
   into the compose file; a cap your compose file sets itself must be the declared value (`check-resources.py`).
4. Base images: `images/<sim>/Dockerfile`, versioned in `images/<sim>/VERSION`, built and pushed with
   `scripts/build_images.sh` / `scripts/push_images.sh`. Images that cannot be published carry `images/<sim>/BUILD_ONLY`
   and build instructions.
5. Run agents with Harbor's native agents only (`-a codex`, `-a claude-code`, …). No adapters, and no gateway that
   holds credentials or changes requests; the optional usage gateway that only records token usage is allowed (PROTOCOL D11).

## Before opening the pull request
```bash
bash ci_checks/run_all.sh tasks/<your tasks>      # must pass
python3 scripts/task_conventions.py --check tasks/<your tasks>     # README, task.toml, test.sh in the standard layout
python3 ci_checks/check-resources.py tasks/<your tasks>             # [metadata.resources] + limits + README / instruction (§2.9, §2.10)
python3 ci_checks/check-cutoffs.py tasks/<your tasks>               # the time cutoff: table = task.toml = instruction = sim service (§2.12)
python3 scripts/<bench>/gen_tasks.py check        # generated tasks (e.g. scripts/kinder/): tasks/ is what render writes
#   older generators: re-run them (scripts/robotwin_mk_task.py, robotwin_mk_limited.py, dtb_mk_task.py, mj_mk_limited.py)
#   and check that `git diff --exit-code tasks/` is empty
harbor run -p tasks/<task> -a oracle               # on a sample: >= 2 tasks per mode
harbor run -p tasks/<task> -a nop                  # must score 0
cd tasks && harbor add --scan . && cd ..           # refresh tasks/dataset.toml
```
For a new simulator or family, also replay the oracle (or a positive example) twice in fresh processes and include
the matching state hashes.

## Tasks without an oracle
Allowed (`oracle = "partial"` or `"none"` with `oracle_evidence`), but they need **human review**: the pull request is
labelled `needs-human-review` and is merged only after a maintainer other than the author approves it. Provide, per
family, a positive example the verifier scores 1, the `nop` result and a short description of the success predicate.
The checklist is in PROTOCOL §2.7.

## Review and merge
1. Static checks run on every pull request (`.github/workflows/static-checks.yml`).
2. A maintainer reviews the files, runs the oracle and `nop` on a sample, and, for new benchmarks, an adversarial
   ("cheat") trial and a model trial.
3. Merge requires: checks passing, a maintainer approval (CODEOWNERS for shared files), human review where required,
   and a branch up to date with `main`.
4. After merge, maintainers publish base images and update the task list and results site.

## Rules that apply to every contribution
- A published task's `environment/` and `tests/` inputs are immutable; changing the scene makes a new task.
- To change a time cutoff (an owner decision), edit the number in `scripts/task_cutoffs.toml` (the benchmark's row, or an
  exception for one family or one task), add its `[[history]]` entry there (required: CI and `apply` refuse a changed
  number without one), run `python3 scripts/task_cutoffs.py apply` and commit what it changed
  ([docs/CUTOFFS.md](docs/CUTOFFS.md)); never edit the number in a task, a template or a generator. The task keeps its
  name; results under the earlier cutoff are reported separately (PROTOCOL §2.8, §2.12).
- Pin everything (`FROM` tags or digests, pip versions); no network access during verification.
- The agent's egress is the model APIs and the package registries (PyPI, the Debian / Ubuntu apt archives), in every
  task (`[agent] network_mode = "allowlist"` with the hosts of `scripts/set_agent_egress.py`; PROTOCOL §2.11): bake
  what the task itself needs at run time into the image or the task directory (an agent may install packages; a task
  must not depend on it). `normalize` writes the `## External material` paragraph, an honour rule, into
  `instruction.md`. If a distribution on PyPI ships your benchmark's solutions or task sources, add it to the table in
  PROTOCOL §2.11. Keep provenance (source repository, dataset, demonstration
  file, expert module) out of every file under `environment/` that the agent reads, and look through a new image for
  recorded episodes and links to them (`ci_checks/check-agent-pointers.py` covers the task's own files only).
- The agent is root in its container: assume it can modify anything under `/app` and `/opt`. Grading therefore runs in
  a separate sandbox, and only the declared artifacts cross over.
- No credentials, personal absolute paths, large binaries or agent results in the repository (results go to the results
  site and the Hugging Face dataset).
- New Python code should be formatted with `ruff format` (line length 120).
