# Reviewing pull requests

Guide for maintainers. The contract is [protocol/README.md](protocol/README.md); contributors follow
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Order of work
0. **Overview.** Read the pull request's sticky overview comment (posted by the CI job `advisories`,
   `ci_checks/pr_overview.py`): its "Advisories (not blocking)" findings, the changed tasks, the cutoffs it changes (old -> new) and the cutoffs per benchmark and
   mode after it, twins with different cutoffs, the scope of its static checks, and its labels (`new-task`, `task-fix`,
   `shared`, `cutoff-change`; a wrong label is removed by hand).
1. **Scope.** One benchmark per pull request; shared files (protocol, taxonomy, CI, shared scripts, README) only in a
   separate pull request. Ask for a split otherwise. The deliverable is the tasks (PROTOCOL §1, "What a contribution
   delivers"): ask the author to remove task-generation code (generators, oracle searches, instance freezers, release
   builders); shared code belongs in the benchmark's image (recommended) or `embodied_first_exam/benchmarks/<benchmark>/`.
2. **Static checks.** The required job `invariants` (`ci_checks/run_invariants.sh`, PROTOCOL Appendix H) must pass;
   advisory findings are conventions: ask the author to fix them or to say why the task departs.
3. **Shared files.** For many similar tasks, read the shared files once (`check-tooling-identity.sh` holds the copies
   identical within a benchmark), then the per-task differences.
4. **Sample tasks.** Read at least two tasks per mode the benchmark ships in this order: `instruction.md` → `tests/` → `solution/` →
   `environment/` → `task.toml`.
5. **Runs.** Comment `/validate` on the pull request: the oracle (where `oracle = "full"`) and `nop` on every task it adds
   or changes, at its head commit, on the GPU runner (`.github/workflows/validate-task.yml`; the results come back as a
   comment; not working yet: it needs a dedicated runner with the `docker` label, which is not attached, and the CI
   runners must never get that label). By hand (the only runtime check until then): oracle and `nop` on a sample (≥ 2 per mode shipped); for a new simulator or family, a determinism check (two
   fresh replays, same hash) on the hardware used for evaluation.
6. **Adversarial trial.** For new benchmarks, one agent trial instructed to make the verifier pass without solving the
   task. Any success blocks the merge until the verifier is fixed.
7. **Human review** for tasks whose `oracle` is not `full` (below).
8. **Approve** with a short summary of what was checked.

## Questions to ask
- Could you write the verifier from the instruction alone? Is every convention the agent needs stated?
- Can the agent reach a solution, a pointer to one, or the success predicate (images, tooling, docs, network)? In the
  image too: recorded episodes, demonstration files, a `source_url` or dataset name in instance metadata (PROTOCOL
  Appendix H.2). Does the task work with the allowlist only (H.6, unless it declares open egress: oracle run under it, nothing downloaded at run time)? Is a
  solution of it one `pip install` away (a PyPI distribution with its experts or sources: list it in [protocol/leakage.md](protocol/leakage.md), "Packages on PyPI")?
- Does the verifier depend on anything the agent controlled besides the declared artifacts?
- Is the predicate checked at the end of the replay (privileged) or of the live episode (standard), and can it be true
  without doing the task?
- Standard mode (Appendix H.3, H.4): four endpoints only, RCB1 responses, resets within the declared budget, the
  verdict from the sidecar's record of the live episode (`success` = the live episode's, with any settle or hold the
  task declares run on the live simulator; `graded_by_live = 1`; no grading replay), the frozen start state checked
  when the episode begins, the agent's processes stopped (a `main` collect hook) before the sidecar is signalled and
  every later request refused, the video recorded live or rendered from the trajectory after the verdict.
- Does the task run with Harbor's native agents, without custom adapters or runners, and without any gateway other than
  the recording-only usage gateway (protocol/running.md "Official runs")?
- Are images pinned, published (or marked `BUILD_ONLY`), and shared with the other tasks of the same simulator?
- Names end in their mode, `-privileged` / `-standard` / `-standard-realtime`; README in the standard layout; no `results/` in task directories.
- Modes (PROTOCOL §3, Appendix H.7): a benchmark may ship any subset of privileged, standard and standard-realtime; a missing
  mode is not a reason to block, but the benchmark's doc says which modes it ships and why the others are left out.
  Where a family has twins, do they share the frozen instance, success rule and seeds, and is the cutoff of privileged
  and standard one number? A standard or standard-realtime task without a twin: does it carry its own frozen instance,
  and does its README's Twin row say why (`— (none: <reason>)`; the advisory check `check-task-structure.sh` warns
  otherwise: a deleted or misnamed twin must not pass silently)?
- A new mode (PROTOCOL §3): does the pull request have everything §3 lists: the name / suffix and `mode` value,
  its own PROTOCOL section (what the agent gets, what is graded, the time and reset rules, which failures are
  infrastructure and which the agent's), the `MODE_REGISTRY` entry and `CUTOFF_NOTE`, CI support keyed on the registry
  (no new hard-coded list of mode names anywhere) with a self-test case, at least one benchmark using it, the TAXONOMY
  entry, and a stated cutoff relation (`same_cutoff_as`, or free)? Is the runner side (batch_eval_live, the results
  site) told the new suffix? A new mode is an owner-visible protocol change: one pull request of its own, shared files
  only, merged before the benchmark that uses it.
- Time cutoff (PROTOCOL §2): does every task set its own `[agent] timeout_sec` , 3600 s unless the pull request justifies another number, at most 14400 s, the same for a task's
  privileged and standard versions and, unless the pull request says why, for all the benchmark's tasks of a mode (the
  pull request's overview lists the numbers)? Does `instruction.md` end with the rendered `## Time limit` section and
  state the limit nowhere else? Does the benchmark's own text say what the cutoff costs here (simulator start-up, what
  the service's `time_left_s` counts from, a service that ends the episode itself)? A pull request that changes the
  cutoff of existing tasks (label `cutoff-change`): the author's decision (the owner steps in only where official
  results must stay comparable), old -> new and why in its description, the tasks normalized (their `DIGEST` files changed with them), nothing else changed.
- Compute resources (PROTOCOL §6): are the minimums measured (what does `measured` cite?) rather than copied from the
  `[environment]` caps? Does `gpu_class` match the simulator (Isaac Sim / Omniverse: `rtx`)? Would the oracle run on a
  machine with exactly these values?
- Resource limits (PROTOCOL §6, protocol/running.md "Resources"): would an honest agent stay inside them (one simulator at the task's defaults on the
  largest card it runs on, the tooling's own replay checks, videos it is told to write)? Is the scope `trial` in
  privileged mode and `agent` in standard modes, and does `instruction.md` have the rendered paragraph just before the closing `## Time limit`? Does
  `measured` cite real peaks (and say where there are none)? Do the caps leave the margin protocol/running.md "Resources" names above the limits?

## Human review (oracle `partial` or `none`)
Review per family (same scene template and predicate), at least two instances per family:
1. **Solvable** — a positive example (successful model trial, upstream policy or RL rollout, or a hand-built
   trajectory or state) that the verifier scores 1.
2. **Correct predicate** — the grader matches the instruction and cannot be satisfied trivially.
3. **Negative control** — `nop` scores 0; ideally a wrong trajectory scores 0 too.
4. **Determinism** — privileged: the positive example gives the same verdict in two fresh replays; standard: its
   recorded trajectory reproduces the live end state where the simulator replays bit for bit (an audit, not the verdict).
5. **Record** — post a review comment listing the instances and evidence you checked, check that the task README's
   Verification section says "no oracle; human review in PR #N", then approve and remove the `needs-human-review` label.

The reviewer is never the pull request's author. For pull requests by a code owner, another code owner reviews.
