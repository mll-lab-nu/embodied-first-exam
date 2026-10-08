# Reviewing pull requests

Guide for maintainers. The contract is [PROTOCOL.md](PROTOCOL.md); contributors follow
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Order of work
1. **Scope.** One benchmark per pull request; shared files (protocol, taxonomy, CI, shared scripts, README) only in a
   separate pull request. Ask for a split otherwise.
2. **Static checks.** `bash ci_checks/run_all.sh` must pass. Read the protocol warnings: until the migration
   (PROTOCOL §7) new tasks may only carry the ones marked `legacy:`.
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
- Can the agent reach a solution, a pointer to one, or the success predicate (images, tooling, docs, network)?
- Does the verifier depend on anything the agent controlled besides the declared artifacts?
- Is the predicate checked at the end of the replay, and can it be true without doing the task?
- Standard mode: four endpoints only, RCB1 responses, no reset (unless the optional capability is declared and its
  results are reported separately), crash recovery, `success = replay_success ∧ deterministic`.
- Does the task run with Harbor's native agents, without custom adapters or runners, and without any gateway other than
  the recording-only usage gateway (PROTOCOL D11)?
- Are images pinned, published (or marked `BUILD_ONLY`), and shared with the other tasks of the same simulator?
- Names end in their mode, `-privileged` / `-standard` / `-standard-realtime`; README in the standard layout; no `results/` in task directories.

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
