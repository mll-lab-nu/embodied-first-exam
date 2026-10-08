# Contributing

Thank you for helping build Robot Coding Bench. Tasks follow the contract in [docs/PROTOCOL.md](docs/PROTOCOL.md);
this page explains how a contribution gets from an idea to `main`. Reviewers follow [docs/REVIEWING.md](docs/REVIEWING.md).

## Kinds of pull requests

| Kind | What it may change | Before you start |
|---|---|---|
| **New benchmark** | `tasks/<its tasks>`, `scripts/<bench>/`, `images/<sim>/`, `docs/benchmarks/<bench>.md`, `tasks/dataset.toml` | an approved [benchmark proposal](.github/ISSUE_TEMPLATE/benchmark-proposal.yml) |
| **Tasks for an existing benchmark** | the same, without `images/` | — |
| **Task fix** | the affected task directories and their generator | describe the agent behaviour it closes; include before/after runs |
| **Shared files / protocol** | `docs/PROTOCOL.md`, `docs/LIMITED_MODE_PROTOCOL.md`, `docs/TAXONOMY.md`, `ci_checks/`, `.github/`, shared `scripts/`, `README.md` | a [protocol-change issue](.github/ISSUE_TEMPLATE/protocol-change.yml) for protocol changes |

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

It also states the oracle source (§2.7 of the protocol), GPU and image size, whether the images can be published, and
the expected size of the pull request.

## Authoring a task
1. Copy the closest existing pair (`tasks/robotwin_2_0_stack_blocks_two-privileged/` and `-standard/`) or generate tasks
   with a script under `scripts/<bench>/`. Name them `<base>-privileged` / `<base>-standard` (and `<base>-realtime` for the realtime mode, PROTOCOL §2.2, §4b) and write
   the README in the standard layout (§2.1); there is no `results/` directory.
2. Fill in `task.toml` (PROTOCOL §2.3), `instruction.md` (§2.5, written by a human), the verifier under `tests/`
   (§2.6, separate sandbox) and `solution/` (§2.7).
3. Base images: `images/<sim>/Dockerfile`, versioned in `images/<sim>/VERSION`, built and pushed with
   `scripts/build_images.sh` / `scripts/push_images.sh`. Images that cannot be published carry `images/<sim>/BUILD_ONLY`
   and build instructions.
4. Run agents with Harbor's native agents only (`-a codex`, `-a claude-code`, …). No adapters, and no gateway that
   holds credentials or changes requests; the optional usage gateway that only records token usage is allowed (PROTOCOL D11).

## Before opening the pull request
```bash
bash ci_checks/run_all.sh tasks/<your tasks>      # must pass; only `legacy:` (image registry) warnings are accepted (§7)
python3 scripts/task_conventions.py --check tasks/<your tasks>     # README, task.toml, test.sh in the v1.0 layout
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
- Pin everything (`FROM` tags or digests, pip versions); no network access during verification.
- The agent is root in its container: assume it can modify anything under `/app` and `/opt`. Grading therefore runs in
  a separate sandbox, and only the declared artifacts cross over.
- No credentials, personal absolute paths, large binaries or agent results in the repository (results go to the results
  site and the Hugging Face dataset).
- New Python code should be formatted with `ruff format` (line length 120).
