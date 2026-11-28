# Reviewing pull requests

A guide for maintainers. The rules are the protocol ([protocol/README.md](protocol/README.md)). Contributors follow
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Order of work

0. **Overview.** Read the pull request's sticky overview comment, posted by the CI job `advisories`
   (`ci_checks/pr_overview.py`). It lists:
   - its "Advisories (not blocking)" findings;
   - the changed tasks;
   - the cutoffs it changes (old → new), and the cutoffs per benchmark and mode after it;
   - tasks whose modes have different cutoffs;
   - the scope of its static checks;
   - its labels (`new-task`, `task-fix`, `shared`, `cutoff-change`). Remove a wrong label by hand.
1. **Scope.** One benchmark per pull request. Shared files (protocol, taxonomy, CI, shared scripts, README) go in a
   separate pull request. Ask for a split otherwise. The deliverable is the tasks
   ([protocol/tasks.md](protocol/tasks.md#what-a-contribution-delivers)). Ask the author to remove task-generation code:
   generators, oracle searches, instance freezers, release builders. Shared code belongs in the benchmark's image
   (recommended) or in `embodied_first_exam/benchmarks/<benchmark>/`.
2. **Static checks.** The required job `invariants` (`ci_checks/run_invariants.sh`) must pass. Advisory findings are
   conventions: ask the author to fix them, or to say why the task departs.
3. **Shared files.** For many similar tasks, read the shared files once (`check-tooling-identity.sh` holds the copies
   identical within a benchmark), then the per-task differences.
4. **Sample tasks.** Read at least two tasks per mode the benchmark ships, in this order: `instruction.md` → `tests/`
   → `solution/` → `environment/` → `task.toml`.
5. **Runs.** Comment `/validate` on the pull request. It runs the oracle (where `oracle = "full"`) and `nop` on every
   task the pull request adds or changes, at its head commit, on the GPU runner (`.github/workflows/validate-task.yml`),
   and posts the results as a comment. It runs only on a dedicated runner with the `docker` label; the CI runners
   never get that label. Without that runner, run by hand: the oracle and `nop` on a sample (at least 2 per mode
   shipped). For a new simulator or family, also check determinism on the hardware used for evaluation: two fresh
   replays give the same hash. (Graded trials replay once, or up to `[metadata] replays` times where the hashes
   differ.)
6. **Adversarial trial.** For a new benchmark, run one agent trial instructed to make the verifier pass without
   solving the task. Any success blocks the merge until the verifier is fixed.
7. **Human review** for tasks whose `oracle` is not `full` ([below](#human-review-oracle-partial-or-none)).
8. **Approve** with a short summary of what was checked.

## Questions to ask

**The texts.**

- Could you write the verifier from the instruction alone? Is every convention the agent needs stated?
- Could the agent tell, from what it observes in its mode, whether each condition holds? Objects are named by
  appearance or starting place. Axes and points are described physically, with whether they already hold at the start.
  Upstream identifiers appear only in brackets after that. Thresholds equal the grader's. The advisory
  `check-instruction.sh` flags code-like terms in standard-mode texts.
- Does `instruction.md` have the five sections in order, with `## Limits` rendered by `normalize`
  ([protocol/tasks.md](protocol/tasks.md#instructionmd))? Is the README in the per-task layout
  ([protocol/tasks.md](protocol/tasks.md#readmemd))?

**Leakage.**

- Can the agent reach a solution, a pointer to one, or the success predicate (images, tooling, docs, network)? Check
  the image too: recorded episodes, demonstration files, a `source_url` or dataset name in instance metadata (H.2).
- Does the task work with the allowlist only (H.6, unless it declares open egress)? The oracle runs under it, and
  nothing is downloaded at run time.
- Is a solution one `pip install` away (a PyPI distribution with its experts or sources)? Then list it in
  [protocol/leakage.md](protocol/leakage.md), "Packages on PyPI".

**Grading.**

- Does the verifier depend on anything the agent controlled besides the declared artifacts?
- Is the predicate checked at the end of the replay (privileged) or of the live episode (standard and realtime)? Can it
  be true without doing the task?
- Standard and realtime modes (H.3, H.4):
  - only the protocol's endpoints (`/spec`, `/status`, `/observe`, `/submit`, `/finish`; `/kinematics` where served;
    `/reset` within a declared budget), with RCB1 responses;
  - the verdict from the sidecar's record of the live episode: `success` is the live episode's, with any settle or
    hold the task declares run on the live simulator; `graded_by_live = 1`; no grading replay;
  - the frozen start state checked when the episode begins;
  - the agent's processes stopped (a `main` collect hook) before the sidecar is signalled, and every later request
    refused;
  - the video recorded live, or rendered from the trajectory after the verdict.
- Agent-ended episodes ([protocol/eai-standard.md](protocol/eai-standard.md#agent-ended-episodes)):
  - Is `RCB_AGENT_END: "1"` in the `sim` service's environment (`ci_checks/check-agent-end.py`)?
  - Does nothing the agent sees depend on the task's success (no `done` or `reason = "success"`, no early end of a
    chunk, no progress field)?
  - Does `POST /finish` end the episode, and is the end state judged as the task says (its settle or hold window from
    there; events judged as they happened)?
  - Does `RCB_STEP_LIMIT`, where set, match the instruction?
  - Does the instruction's `## Limits` end with the Finish line?

**Runs and images.**

- Does the task run with Harbor's native agents, without custom adapters or runners, and without any gateway other than
  the recording-only usage gateway ([protocol/running.md](protocol/running.md#official-runs))?
- Are images pinned, published (or marked `BUILD_ONLY`), and shared with the other tasks of the same simulator?
- Do names end in their mode (`-privileged`, `-standard`, `-realtime`)? Are there no `results/` in task directories?

**Modes** ([protocol/tasks.md](protocol/tasks.md#modes), H.7).

- A benchmark may ship any subset of privileged, standard and realtime. A missing mode is not a reason to block, but
  the benchmark's README says which modes it ships and why the others are left out.
- Where a task is offered in several modes, do they share the frozen instance, success rule and seeds, and is the
  cutoff one number?
- A standard or realtime task without the same task in privileged mode: does it carry its own frozen instance, and
  does its benchmark's `readme.toml` say why (`no_twin`)? The task-structure check (`check-task-layout.py`) warns
  otherwise, so that a deleted or misnamed task does not pass silently.
- A new mode: does the pull request have everything [protocol/tasks.md](protocol/tasks.md#modes) lists? Is the runner
  side (runners, the results site) told the new suffix? A new mode is a protocol change the maintainers decide: one
  pull request of its own, shared files only, merged before the benchmark that uses it.

**Time.**

- Does every task set its own `[agent] timeout_sec` within the rules
  ([protocol/running.md](protocol/running.md#the-agents-time))? The pull request's overview lists the numbers.
- Does `instruction.md` end with the rendered `## Limits` (its Time line), and state the limit nowhere else?
- Does the benchmark's own text say what the cutoff costs here: simulator start-up, what the service's `time_left_s`
  counts from, a service that ends the episode itself?
- A pull request that changes the cutoff of existing tasks (label `cutoff-change`) is the author's decision. The
  maintainers step in only where official results must stay comparable. Its description states old → new and why. The
  tasks are normalized (their `DIGEST` files changed with them), and nothing else changed.

**Resources** ([protocol/resources.md](protocol/resources.md)). Every number is a cap for one container.

- Are the caps measured with a margin? What do `measured` and `caps_measured` in `scripts/task_resources.toml` cite,
  and do they say where there are no measurements?
- Would an honest agent and the oracle stay inside them? Any cap but CPU can kill a process. Count one simulator at the
  task's defaults on the largest card it runs on, the tooling's own replay checks, and the videos it is told to write.
  Otherwise, does the benchmark's README state the exception?
- Does `gpu_types` match the simulator (Isaac Sim and Omniverse need an RTX-class GPU)?
- Does a separate verifier need caps in `[verifier.environment]`? CI checks the rest.

## Human review (oracle `partial` or `none`)

Review per family (same scene template and predicate), at least two instances per family.

1. **Solvable.** A positive example (a successful model trial, an upstream policy or RL rollout, or a hand-built
   trajectory or state) that the verifier scores 1.
2. **Correct predicate.** The grader matches the instruction and cannot be satisfied trivially.
3. **Negative control.** `nop` scores 0. Ideally a wrong trajectory scores 0 too.
4. **Determinism.** Privileged: the positive example gives the same verdict in two fresh replays, or the task declares
   `[metadata] replays`. Standard and realtime: where the simulator replays bit for bit, the recorded trajectory
   reproduces the live end state (an audit, not the verdict).
5. **Record.** Post a review comment that lists the instances and evidence you checked. Check that the task's
   `[metadata] oracle_evidence` points at that review. Then approve and remove the `needs-human-review` label.

The reviewer is never the pull request's author. For a pull request by a code owner, another code owner reviews.
