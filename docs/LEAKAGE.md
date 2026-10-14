# Answer-key leakage

Tasks are built from public research repositories, and those usually ship the thing that grades the task:
a reward function, a success predicate, a trained policy, a demonstration set.

> **Removing an answer key from what we ship is not the same as the agent being unable to get it.**
> The first is a set we control. The second is everything the container can reach.

## 1. Where it survives

| Place | Why it is still readable | Check |
|---|---|---|
| Dead code | unreachable ≠ unreadable | scan the whole package, not the import graph |
| Constants the grader read | a constant whose only reader was the grader still describes it; so does a comment on one that stays (`# Horizontal speeds above which move reward is 1.`) | no module-level name may be write-only afterwards; no comment may mention the reward |
| Attributes set at construction | weights in `__init__` are not "functions with a matching name", and a snapshot of the object keeps them: HumanoidBench push's frozen instance carried its reward weights until 2026-09-29 | enumerate instance attributes at runtime; leave them out of anything saved from one |
| Class attributes | a class body's `_move_speed = _WALK_SPEED` keeps the module constant alive once `get_reward`, its only reader, is gone: HumanoidBench's `_WALK_SPEED = 1` and `_RUN_SPEED = 5` (the move term's bound and margin for walk, stair, hurdle) are still in the 0.1.6 image | **open**: extend the scrub's dead-name rule to class bodies, restore the attributes in `rcb_rewards`, and build a new image |
| Values the kept methods compute for the expert | a scrub that keeps `load_actors` because it builds the scene also keeps what it computes only for the removed expert: RoboTwin's `load_actors` set the expert's target and waypoint poses (`adjust_bottle.left_target_pose`, `stack_bowls_three.quat_of_target_pose`, …) and `dump_bin_bigbin.pour_actions`, the whole pouring motion as a ready-made action list, and the instruction listed them as scene objects (27 attributes in 18 tasks; images up to `eai-robotwin` 0.1.1) | **closed** 2026-10-13 (board 0100, `eai-robotwin` 0.1.2): `images/robotwin/scrub_oracles.py` removes every attribute a kept method sets that no kept method reads (`LEAKS`), with the locals and comments that only feed it, keeps the random draws so the scene is unchanged, and fails the build on a new pose-like one; the oracles rebuild the scene with upstream's `load_actors` |
| Helpers the grader called | not named like the grader, so the name match keeps them: HumanoidBench maze's `update_move_direction` returned the checkpoint bonus, truck's `upon_table` held the table test (both until the 0.1.6 image) | list what every removed method calls; delete what nothing else calls, keep only the effect of what the tooling still calls |
| Compiled bytecode | `*.pyc` built before the removal keeps the old code | clear caches *before* removing, assert after |
| Earlier Docker layers | a layer is an immutable tarball; a later `rm` does not unwrite it | download and remove in the **same `RUN`**; verify with `docker save` |
| `.git` | `git show` reconstructs every file ever committed | delete it in that same `RUN` |
| The network | upstream is public and pinned, one `curl` away | `[agent] network_mode = "allowlist"` of the model-API hosts (`scripts/set_agent_egress.py`) in **every task** since 2026-10-10 (PROTOCOL §2.11, [CI]); since 2026-10-11 the list also has the package registries (PyPI, the Debian / Ubuntu apt archives), which are not where solutions are published, with exceptions: some PyPI distributions ship a benchmark's scripted experts, trained policies or task sources (the table in PROTOCOL §2.11; nothing blocks them, a trial that installs one is looked at). Until then six benchmarks were open, and trials fetched upstream task sources with their reference solution, a recorded demonstration and robot models from their own shell (board 0072); a pointer inside the image (a `source_url`) is what led one of them there |
| Instance metadata and upstream docs | a frozen instance that records where it came from (a `source_url`, a demonstration file, the expert's module) hands the agent the address of its solution: RoboTangle's `reference_scene.json` named the upstream demonstration, YAMLab's `instance.json` the recording its oracle replays, DexJoCo's `instance.npz` (`meta`) the demonstration whose actions are the reference, RoboLab's image shipped a recorded successful episode of one task; upstream READMEs name the public demonstration datasets and checkpoints | keep provenance in `scripts/<bench>/` and the README, never in a file under `environment/` the agent reads ([CI] `check-agent-pointers.py`); grep a new image for `https?://`, `*.hdf5` and recorded episodes before publishing it; the allowlist covers what an upstream checkout's documentation still names |
| The model API | tools that run at the provider, reached through an allowed model-API host: Codex's `web_search` and Claude Code's `WebSearch`; under a ChatGPT login also the account's connectors and apps (238 tools on 2026-10-10: web open and search, GitHub, mail, drives), image generation and plugins | **closed**: `scripts/run_agent_batch.sh` passes Codex `--ak web_search=disabled` and Claude Code `--ak disallowed_tools=WebSearch,WebFetch` unless `WEB_SEARCH=allowed` (since 2026-10-02; before that it was open unless a run's own agent config turned it off, audit below); the runner starts Codex without connectors, apps, plugins and image generation (the same switch: those features set to false in the run's `config.toml` by `scripts/codex_tools_off.py`; 2026-10-10, after 21 trials had called connectors: Codex 0.160 calls them from its `exec` tool as `tools.mcp__codex_apps__*`, so grep the transcript for that name); and with the usage gateway on, the gateway is the container's only egress and forwards model-API calls only (PROTOCOL §2.11) |
| The model-API key | Harbor's native agents put it in the agent's container. Codex: `OPENAI_API_KEY` in its environment and in `/tmp/codex-secrets/auth.json` (linked from `$CODEX_HOME/auth.json`), removed only after the run; Claude Code: `ANTHROPIC_API_KEY` (or its OAuth token) in its environment. With the model API allowed, the agent can spend it on any model, a search-enabled one included, which undoes the row above | **narrowed 2026-10-10**: with the usage gateway on, the container reaches its provider only through the gateway's model-API paths (no connector, file or conversation endpoint, whatever the agent runs with the key or the login), and a model request is forwarded only if every tool it declares is one the agent runs itself (a web search, image generation or remote MCP tool, or an unreadable body, is refused). Still open: the key can be spent on another model of the same provider (a gateway that holds the key is ruled out by D11): one key per batch with a spending cap (`docs/RUNNING.md`), and read the transcript for direct API calls |
| The model's memory | the benchmark's source is public, so it is in pretraining data: Opus 5.5 recalled H1's 19 actuator ranges exactly and the sit reward's seat-height band, with no tool | nothing in the harness removes it; report it with the result |
| Package metadata | `*.egg-info/SOURCES.txt` lists files you deleted | generate metadata after the removal |
| Sibling tasks | one task's `tests/` must not carry another's answer | ship one task's answer per task |

Layers and `.git` are invisible from inside the container — overlayfs shows the agent only the merged
view. They leak to whoever pulls the image, which for a public benchmark is the same people.

**Read the agent's transcript.** Two of these rows came from watching one go looking: `grep -rn` over the
package, `cat` on the likely file, then `import dis, marshal` against the bytecode caches.

**Audit a harness** by pointing it at a local fake API and reading the tools of its first request (Codex 0.159
sends them in an `additional_tools` input item, not in `tools`). 2026-10-01, Codex 0.159.2 with the configs'
OpenRouter provider: the tool set follows the model. `gpt-5` and `gpt-5.5` get a `web_search` tool by default and
with `cached` or `live`, none with `disabled`; `gpt-6-luna` gets none in any mode. Where the key goes: Harbor 0.23.0,
`agents/installed/codex.py` (`run()`) and `claude_code.py` (`_resolve_auth_env()`).

2026-10-02, real calls, Codex 0.159.2 and `gpt-6-luna`, asked to find RoboTwin's `play_once` on GitHub:
- **ChatGPT login** (`chatgpt.com/backend-api/codex`): by default Codex searched twice (its client calls
  `/backend-api/codex/alpha/search` on `chatgpt.com`, the same host as the model calls, so an egress allowlist cannot
  separate them) and quoted `play_once`; with `-c web_search=disabled` it had no search and made no such call.
- **Azure API key** (a custom Responses provider): Codex offered no search in either setting. But a request that
  carries `tools: [{"type": "web_search"}]` (or `web_search_preview`) is served with real searches, so an agent
  holding the key can still search by writing its own request. The usage gateway's raw log (`GATEWAY=1`, raw bodies on by default)
  shows the tool list of every request: flag any `web_search` tool or `alpha/search` path. Since 2026-10-10 the gateway
  refuses both (`usage.jsonl` `refused`: `server_tool`, `path_not_allowed`).

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

The verifier runs in a container of its own, built from `tests/` (`[verifier] environment_mode = "separate"`):
the agent's container, where it was root, is gone by then, and only the declared deliverable crosses over. In
standard mode the `sim` sidecar scores the episode, from `environment/sim/`, which the agent's image never copies.

| Stage | What it does |
|---|---|
| build | remove, then assert nothing survived and the package still runs |
| once, offline | lift what was removed into a committed data file, by diffing against a real removal |
| render | copy **one task's** entry into that task's `tests/` (standard: `environment/sim/`) |
| verify | restore, then assert the restore worked — a failed restore is a grader error, never a 0 |
| CI | the scoring side has it, the agent's side does not, `instruction.md` quotes no parameters, `[agent]` is on an allowlist |

Restore code against the **defining module's own namespace** so it closes over what it did upstream. Agent
tooling should report that scoring is unavailable rather than return a zero.

*Worked example:* HumanoidBench's grader is a dense reward — `images/humanoidbench/scrub_oracles.py`
(remove), `scripts/humanoidbench/extract_rewards.py` (diff), `scripts/humanoidbench/shared/rcb_rewards.py` (restore),
`scripts/humanoidbench/gen_tasks.py check` (enforce; CI runs it through `ci_checks/check-generated-tasks.sh`). For
every standard task, `ci_checks/check-standard-agent-image.sh` keeps `environment/sim/` out of the agent's image.

## 4. The task statement is then the only account

- **Say** which quantities are judged and how they combine, the order of magnitude of a target, what ends
  the episode.
- **Do not say** tolerance parameters, exact weights, the reward's per-step scale, or what any particular
  policy scores. What the pass mark *requires* is fine.

The test: *an engineer reading only this should be able to build a reasonable objective and optimise it,
and should not be able to skip the robot and solve for the number.* If a task proves unsolvable because
the statement is too vague, fix the statement — do not give the grader back.
