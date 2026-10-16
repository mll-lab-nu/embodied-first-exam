# Contributing

Thank you for helping build Robot Coding Bench. Tasks follow the contract in [docs/PROTOCOL.md](docs/PROTOCOL.md);
this page explains how a contribution gets from an idea to `main`. Reviewers follow [docs/REVIEWING.md](docs/REVIEWING.md).

## Kinds of pull requests

| Kind | What it may change | Before you start |
|---|---|---|
| **New benchmark** | `tasks/<its tasks>`, `scripts/<bench>/`, `images/<sim>/`, `docs/benchmarks/<bench>.md` | an approved [benchmark proposal](.github/ISSUE_TEMPLATE/benchmark-proposal.yml) |
| **Tasks for an existing benchmark** | the same, without `images/` | — |
| **Task fix** | the affected task directories and their generator | describe the agent behaviour it closes; include before/after runs |
| **Shared files / protocol** | `docs/PROTOCOL.md`, `docs/STANDARD_MODE.md`, `docs/TAXONOMY.md`, `ci_checks/`, `.github/`, shared `scripts/`, `README.md` | a [protocol-change issue](.github/ISSUE_TEMPLATE/protocol-change.yml) for protocol changes |

One benchmark per pull request. A pull request that adds tasks **and** changes shared files is split before review.

## Proposal (new benchmarks)
Open a benchmark-proposal issue first. A good proposal shows that the tasks are:
- **verifiable** by a program, in a fresh process, without a learned judge;
- **solvable** — a positive example the verifier scores 1: an oracle, an upstream expert or policy, a successful
  model trial, or a hand-built trajectory (tasks without one are human-reviewed and marked unvalidated, PROTOCOL §2, §4);
- **difficult** for today's coding agents, for a reason that matters for robotics;
- **reproducible** — bit-exact replay of a frozen scene instance, and the hardware it was checked on;
- **isolatable** — the verifier can recompute the result in its own sandbox from the declared artifacts;
- **scrubbable** — upstream reference solutions can be removed from everything the agent can reach.

It also states the oracle source (PROTOCOL §4), the minimum compute per trial (CPU cores, memory, GPU memory
and GPU class, §6), image size, whether the images can be published, and
the expected size of the pull request.

## Authoring a task
1. Copy the closest existing pair (`tasks/robotwin_2_0_stack_blocks_two-privileged/` and `-standard/`) or generate tasks
   with a script under `scripts/<bench>/`. Name them `<base>-privileged` / `<base>-standard` (and `<base>-standard-realtime` for the standard-realtime mode, PROTOCOL §1, §3) and write
   the README in the standard layout (§1); there is no `results/` directory.
2. Fill in `task.toml` (PROTOCOL §1, §2: declare its settings, `dynamics` and `network` included), `instruction.md`
   (§5, written by a human), the verifier under `tests/` (Appendix H.1, separate sandbox) and `solution/` (H.2).
   The agent's time cutoff (PROTOCOL §2) is the task's own `[agent] timeout_sec`, which you set in this pull
   request (a generator: a constant in your `scripts/<bench>/`) and state in its Contract: a whole number of seconds,
   3600 unless you justify another number, at most 14400, the same for a task's privileged and standard versions,
   and one number for all your benchmark's tasks of a mode unless you say why. There is no central table. `normalize`
   writes from it the standard modes' `RCB_WALL_CLOCK_S` and the README row, and ends `instruction.md` with the
   `## Time limit` section, after `## External material` and `## Resource limits` ("You have N seconds to complete this
   task. Do not cheat by using online solutions or hints specific to this task.", then what the cutoff means in the
   mode). Your own text never repeats the limit as a duration: say "the time limit (`## Time limit`)", and add what is
   particular to your benchmark (a simulator's start-up cost). Your service's `time_s` / `time_left_s` count from the
   agent's first request to it, never from the service's start, and a resumed service keeps that moment
   (STANDARD_MODE.md, "The agent's clock": the shared layers do it for you; a test must show it).
3. State the minimum compute (PROTOCOL §6): CPU cores, memory and GPU memory of the agent phase and the verifier
   phase, the GPU class and a recommended GPU, derived from measured peaks (oracle or agent trials; `docker stats` /
   cgroup `memory.stat` and `nvidia-smi` while they run). Add a rule to `scripts/task_resources.toml` (or have the
   generator write `[metadata.resources]`); `scripts/task_conventions.py` writes it into `task.toml` and renders the
   README's `## Compute resources`.
   Add the resource limits and caps too (PROTOCOL §6, RUNNING.md "Resources"): a `[[limit]]` and a `[[cap]]` rule in the same file (scope
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
   holds credentials or changes requests; the optional usage gateway that only records token usage is allowed (RUNNING.md "Official runs").

## Before opening the pull request
```bash
bash ci_checks/run_invariants.sh tasks/<your tasks>   # must pass (the required CI job `invariants`)
bash ci_checks/run_all.sh tasks/<your tasks>      # both tiers: fix the advisory findings or say why the task departs
bash ci_checks/run_all.sh --changed               # what CI runs on your pull request (scope: ci_checks/ci_scope.py)
python3 scripts/task_conventions.py --check tasks/<your tasks>     # README, task.toml, test.sh in the standard layout
python3 ci_checks/check-resources.py tasks/<your tasks>             # [metadata.resources] + limits + README / instruction (§2.9, §2.10)
python3 ci_checks/check-cutoffs.py tasks/<your tasks>               # the time cutoff: task.toml = instruction = README = sim service, twins equal, cap (§2.12)
python3 scripts/<bench>/gen_tasks.py check        # generated tasks (e.g. scripts/kinder/): tasks/ is what render writes
#   older generators: re-run them (scripts/robotwin_mk_task.py, robotwin_mk_limited.py, dtb_mk_task.py, mj_mk_limited.py)
#   and check that `git diff --exit-code tasks/` is empty
python3 scripts/stamp_mtimes.py tasks             # before any image build from the checkout (below)
harbor run -p tasks/<task> -a oracle               # on a sample: >= 2 tasks per mode
harbor run -p tasks/<task> -a nop                  # must score 0
python3 scripts/task_conventions.py tasks/<your tasks>    # after a hand edit: normalize, which also refreshes each DIGEST
```
Never build a task image (a `harbor run`, a `docker build` of `environment/` or `tests/`) from a tree you have not
stamped with `scripts/stamp_mtimes.py`: Docker's BuildKit reuses another build's same-name context file when its size and
mtime match, and a checkout gives many files one mtime, so a task can silently run or be graded with another task's file
(issue #258, RUNNING.md "Building task images"). Tools that build images run from a stamped copy
(`stamp_mtimes.py stage`); a new one does the same.

For a new simulator or family, also replay the oracle (or a positive example) twice in fresh processes and include
the matching state hashes.

## Tasks without an oracle
Allowed (`oracle = "partial"` or `"none"` with `oracle_evidence`), but they need **human review**: the pull request is
labelled `needs-human-review` and is merged only after a maintainer other than the author approves it. Provide, per
family, a positive example the verifier scores 1, the `nop` result and a short description of the success predicate.
The checklist is in PROTOCOL §4.

## Review and merge
1. Static checks run on every pull request (`.github/workflows/static-checks.yml`), on what the pull request can
   affect (`ci_checks/ci_scope.py`, from the diff against `main`): when it changes only one benchmark's own paths (its
   `tasks/<prefix>*`, `scripts/<bench>/`, `images/<bench>/`, `docs/benchmarks/<bench>.md`; plus the benchmarks that
   share code with it), the per-task checks (incl. each task's `DIGEST`) and `task_conventions.py --check` on that
   benchmark's tasks, its generator's check and its unit tests (and `check-cutoffs.py` on its tasks); the cheap repo-level checks (resources,
   protocol, ...) always run on every task. Anything shared -- `ci_checks/`, `.github/`, the shared `scripts/` modules and tables
   (`task_conventions.py`, `task_resources.toml`, `eai_standard/`,
   `rcb_monitor/`, ...), `images/monitor/`, `images/VERSION`, `docs/PROTOCOL.md` and the other protocol documents, or a
   path the scope table does not know -- runs the full suite, as does every push to `main`, the nightly run and a manual
   run (`workflow_dispatch`). The CI mutation self-test (`check-ci-selftest.py`) runs with the full suite.
   The checks are in two tiers (PROTOCOL v2.0): the job **`invariants`** (`ci_checks/run_invariants.sh`: the checks
   that enforce PROTOCOL Appendix H) is the only one that blocks a merge, and it fails on any failure, error or
   incomplete run; the job **`advisories`** (`ci_checks/run_all.sh --tier advisory`) reports every other finding as a
   warning (annotations, the job summary). Locally, `bash ci_checks/run_all.sh` runs both: exit 0 clean, 1 an invariant
   failed, 3 advisory findings only.
2. A sticky overview comment (posted by the job `advisories`, `ci_checks/pr_overview.py`) lists the tasks the pull
   request adds or changes, the cutoffs it changes, the scope of its checks and the advisory findings ("Advisories (not
   blocking)": fix them or say why the task departs), and labels it (`new-task`, `task-fix`, `shared`,
   `cutoff-change`). A maintainer reviews the files and comments `/validate` to run the oracle (where `oracle = "full"`)
   and `nop` on the changed tasks (`.github/workflows/validate-task.yml`, on the GPU runner; the results come back as a
   comment; not working yet: it needs a dedicated runner with the `docker` label, which is not attached -- until then the
   reviewer runs oracle and `nop` by hand), and, for new benchmarks, runs an adversarial ("cheat") trial and a model trial.
3. Merge requires: the required check `invariants` passing (branch protection), a maintainer approval (CODEOWNERS for shared files), human review where required,
   and a branch up to date with `main`.
4. After merge, the task list is regenerated by `.github/workflows/task-list.yml` and pushed to the branch `task-list`
   (`TASKS.md`, `tasks.json`, `dataset.toml`; nothing in `main` lists the tasks); maintainers publish base images and
   update the results site. A release (tag `v<semver>`) gets the same files as assets (`.github/workflows/release.yml`).

## Rules that apply to every contribution
- A published task's `environment/` and `tests/` inputs are immutable; changing the scene makes a new task.
- To change a time cutoff (the task author's decision; owner involvement only where official results must stay
  comparable), set the new `[agent] timeout_sec` in the tasks concerned (a generated
  benchmark: its generator's constant, then regenerate), in both twins, run `python3 scripts/task_conventions.py` on them
  and say old -> new and why in the pull request ([docs/CUTOFFS.md](docs/CUTOFFS.md)). The task keeps its name and gets
  a new digest; results under the earlier cutoff are ranked separately (PROTOCOL §2, H.8).
- Pin everything (`FROM` tags or digests, pip versions); no network access during verification.
- The agent's egress is the model APIs and the package registries (PyPI, the Debian / Ubuntu apt archives) by default
  (`[agent] network_mode = "allowlist"` with the hosts of `scripts/set_agent_egress.py`; PROTOCOL Appendix H.6); a task
  whose author chooses open egress declares `[metadata] network = "open"` and writes its own `## External material`
  paragraph, and its results are ranked apart. Bake
  what the task itself needs at run time into the image or the task directory (an agent may install packages; a task
  must not depend on it). `normalize` writes the `## External material` paragraph, an honour rule, into
  `instruction.md`. If a distribution on PyPI ships your benchmark's solutions or task sources, add it to the table in
  [docs/LEAKAGE.md](docs/LEAKAGE.md) ("Packages on PyPI"). Keep provenance (source repository, dataset, demonstration
  file, expert module) out of every file under `environment/` that the agent reads, and look through a new image for
  recorded episodes and links to them (`ci_checks/check-agent-pointers.py` covers the task's own files only).
- The agent is root in its container: assume it can modify anything under `/app` and `/opt`. Grading therefore runs in
  a separate sandbox, and only the declared artifacts cross over (PROTOCOL Appendix H.1). A benchmark-specific check
  goes into the benchmark's own `scripts/<bench>/ci/` as an `invariant-*` hook (it guards Appendix H: blocking) or an
  `advisory-*` hook (a convention: a warning); shared `ci_checks/` names no benchmark.
- No credentials, personal absolute paths, large binaries or agent results in the repository (results go to the results
  site and the Hugging Face dataset).
- New Python code should be formatted with `ruff format` (line length 120).
