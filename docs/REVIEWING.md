# Reviewing pull requests

Guide for maintainers. The contract is [PROTOCOL.md](PROTOCOL.md); contributors follow
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Order of work
1. **Scope.** One benchmark per pull request; shared files (protocol, taxonomy, CI, shared scripts, README) only in a
   separate pull request. Ask for a split otherwise.
2. **Static checks.** `bash ci_checks/run_all.sh` must pass.
3. **Generator.** For generated tasks, read the generator and the shared sources, not 500 copies. Re-run it and check
   that `git diff tasks/` is empty.
4. **Sample tasks.** Read at least two tasks per mode in this order: `instruction.md` → `tests/` → `solution/` →
   `environment/` → `task.toml`.
5. **Runs.** Oracle and `nop` on a sample (≥ 2 per mode); for a new simulator or family, a determinism check (two
   fresh replays, same hash) on the hardware used for evaluation.
6. **Adversarial trial.** For new benchmarks, one agent trial instructed to make the verifier pass without solving the
   task. Any success blocks the merge until the verifier is fixed.
7. **Human review** for tasks whose `oracle` is not `full` (below).
8. **Approve** with a short summary of what was checked.

## Questions to ask
- Could you write the verifier from the instruction alone? Is every convention the agent needs stated?
- Can the agent reach a solution, a pointer to one, or the success predicate (images, tooling, docs, network)? In the
  image too: recorded episodes, demonstration files, a `source_url` or dataset name in instance metadata (PROTOCOL
  §2.7). Does the task work with the allowlist only (§2.11: oracle run under it, nothing downloaded at run time)? Is a
  solution of it one `pip install` away (a PyPI distribution with its experts or sources: list it in §2.11)?
- Does the verifier depend on anything the agent controlled besides the declared artifacts?
- Is the predicate checked at the end of the replay, and can it be true without doing the task?
- Standard mode: four endpoints only, RCB1 responses, no reset (unless the optional capability is declared and its
  results are reported separately), crash recovery, `success = replay_success ∧ deterministic`.
- Does the task run with Harbor's native agents, without custom adapters or runners, and without any gateway other than
  the recording-only usage gateway (PROTOCOL D11)?
- Are images pinned, published (or marked `BUILD_ONLY`), and shared with the other tasks of the same simulator?
- Names end in their mode, `-privileged` / `-standard` / `-standard-realtime`; README in the standard layout; no `results/` in task directories.
- Compute resources (PROTOCOL §2.9): are the minimums measured (what does `measured` cite?) rather than copied from the
  `[environment]` caps? Does `gpu_class` match the simulator (Isaac Sim / Omniverse: `rtx`)? Would the oracle run on a
  machine with exactly these values?
- Resource limits (PROTOCOL §2.10): would an honest agent stay inside them (one simulator at the task's defaults on the
  largest card it runs on, the tooling's own replay checks, videos it is told to write)? Is the scope `trial` in
  privileged mode and `agent` in standard modes, and does `instruction.md` end with the rendered paragraph? Does
  `measured` cite real peaks (and say where there are none)? Do the caps leave the margin of §2.10 above the limits?

## Human review (oracle `partial` or `none`)
Review per family (same generator and predicate), at least two instances per family:
1. **Solvable** — a positive example (successful model trial, upstream policy or RL rollout, or a hand-built
   trajectory or state) that the verifier scores 1.
2. **Correct predicate** — the grader matches the instruction and cannot be satisfied trivially.
3. **Negative control** — `nop` scores 0; ideally a wrong trajectory scores 0 too.
4. **Determinism** — the positive example gives the same verdict in two fresh replays.
5. **Record** — post a review comment listing the instances and evidence you checked, check that the task README's
   Verification section says "no oracle; human review in PR #N", then approve and remove the `needs-human-review` label.

The reviewer is never the pull request's author. For pull requests by a code owner, another code owner reviews.
