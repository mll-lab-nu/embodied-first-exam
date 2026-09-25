# Answer-key leakage

Tasks are built from public research repositories, and those usually ship the thing that grades the task:
a reward function, a success predicate, a trained policy, a demonstration set.

> **Removing an answer key from what we ship is not the same as the agent being unable to get it.**
> The first is a set we control. The second is everything the container can reach.

## 1. Where it survives

| Place | Why it is still readable | Check |
|---|---|---|
| Dead code | unreachable ≠ unreadable | scan the whole package, not the import graph |
| Constants the grader read | a constant whose only reader was the grader still describes it | no module-level name may be write-only afterwards |
| Attributes set at construction | weights in `__init__` are not "functions with a matching name" | enumerate instance attributes at runtime |
| Helpers the grader called | not named like the grader, so the name match keeps them: HumanoidBench maze's `update_move_direction` returns the checkpoint bonus (still in the 0.1.5 image) | list what every removed method calls |
| Compiled bytecode | `*.pyc` built before the removal keeps the old code | clear caches *before* removing, assert after |
| Earlier Docker layers | a layer is an immutable tarball; a later `rm` does not unwrite it | download and remove in the **same `RUN`**; verify with `docker save` |
| `.git` | `git show` reconstructs every file ever committed | delete it in that same `RUN` |
| The network | upstream is public and pinned, one `curl` away | `[agent] network_mode = "allowlist"`, never `public` |
| The model API | the harness's web search runs on the provider, reached through the one allowed host: codex's default live `web_search` and Claude Code's `WebSearch`, both executed by OpenRouter | the `harbor_agents/` adapters switch them off; to audit a harness, point it at a local fake API and read the request's `tools` |
| The model's memory | the benchmark's source is public, so it is in pretraining data: Opus 5.5 recalled H1's 19 actuator ranges exactly and the sit reward's seat-height band, with no tool | nothing in the harness removes it; report it with the result |
| Package metadata | `*.egg-info/SOURCES.txt` lists files you deleted | generate metadata after the removal |
| Sibling tasks | one task's `tests/` must not carry another's answer | ship one task's answer per task |

Layers and `.git` are invisible from inside the container — overlayfs shows the agent only the merged
view. They leak to whoever pulls the image, which for a public benchmark is the same people.

**Read the agent's transcript.** Two of these rows came from watching one go looking: `grep -rn` over the
package, `cat` on the likely file, then `import dis, marshal` against the bytecode caches.

## 2. Deciding what to remove

A name match (`*reward*`, `*success*`, `*solve*`) **proposes candidates**; it never decides. Deleting on a
name alone removes things the environment needs and keeps everything named something else. Settle each
candidate with a rule a script can evaluate, so the removal rediscovers itself on every build instead of
following a hand-written list that rots.

**A. Falls through to a safe base.** Delete an override when the language guarantees a harmless
replacement — removing a subclass method when the base returns a neutral value. Correctness comes from the
language, not our judgement, so over-matching is cheap. Assert it: the package must still import and run,
and the same actions must give the same observations and terminations as with the grader restored — upstream
sometimes advances task state inside it (HumanoidBench: a stirring target's phase, the current checkpoint).

**B. Dead *because of* the removal.** Delete a definition when **both** hold: something we removed read it,
**and** nothing that remains reads it. Without the first you delete upstream's own unused code and
anything reached in a way your analysis does not model; without the second you keep constants that exist
only to parameterise the grader. Search the whole package — another module may import the name.

**C. Kept only by a surviving reader.** When one container mixes grading data with operational data — a
dict of weights that also holds a control flag — keep exactly the entries surviving code still reads.

Two properties make it auditable:

- **Idempotence.** Running the removal again must be a no-op, which turns "did we miss anything?" into a
  build-time assertion that also fixes the problem if it fires.
- **One source of truth.** Whatever the image loses, the verifier needs back. Derive that list by running
  the real removal against a copy and diffing — never by re-deriving the rule in a second script.

**Third-party dependencies are out of reach, and that is usually fine.** A grader copied from a library
leaves the library's version installed — `dm_control/suite/` carries the very pattern HumanoidBench's
rewards were written from. Removing it raises the bar but cannot close the channel, because the pattern is
public and in the model's training data. Judge by what leaks: a *convention* is acceptable, a *parameter*
is not.

**What stays:** termination conditions (one rollout reveals them — that is dynamics), observations, the
pass mark, the scene layout, and constants surviving code reads. These *describe* the task; the grader
*scores* it. When in doubt: would the task statement name it anyway?

## 3. Giving it back to the verifier

Harbor copies `tests/` in only after the agent finishes, which is what makes a shared container safe.

| Stage | What it does |
|---|---|
| build | remove, then assert nothing survived and the package still runs |
| once, offline | lift what was removed into a committed data file, by diffing against a real removal |
| render | copy **one task's** entry into that task's `tests/` |
| verify | restore, then assert the restore worked — a failed restore is a grader error, never a 0 |
| CI | `tests/` has it, `environment/` does not, `instruction.md` quotes no parameters, `[agent]` is off the network |

Restore code against the **defining module's own namespace** so it closes over what it did upstream. Agent
tooling should report that scoring is unavailable rather than return a zero.

*Worked example:* HumanoidBench's grader is a dense reward — `images/humanoidbench/scrub_oracles.py`
(remove), `scripts/humanoidbench/extract_rewards.py` (diff), `shared/rcb_rewards.py` (restore),
`ci_checks/check-no-reward-leak.sh` (enforce).

## 4. The task statement is then the only account

- **Say** which quantities are judged and how they combine, the order of magnitude of a target, what ends
  the episode.
- **Do not say** tolerance parameters, exact weights, the reward's per-step scale, or what any particular
  policy scores. What the pass mark *requires* is fine.

The test: *an engineer reading only this should be able to build a reasonable objective and optimise it,
and should not be able to skip the robot and solve for the number.* If a task proves unsolvable because
the statement is too vague, fix the statement — do not give the grader back.
