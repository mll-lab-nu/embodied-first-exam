# Answer-key leakage

Part of the task protocol ([README](README.md)): where answer keys survive in what a task ships, and how they
are removed.

Tasks are built from public research repositories, and those usually ship the thing that grades the task:
a reward function, a success predicate, a trained policy, a demonstration set.

> **Removing an answer key from what we ship is not the same as the agent being unable to get it.**
> The first is a set we control. The second is everything the container can reach.

The honour rule allows the agent to read anything installed in its container, the simulator's and the benchmark's
own source included (PROTOCOL §5); it forbids only searching the web for, or
downloading, a ready-made solution. Reading the image is therefore not a violation in any trial: whatever the image
ships is fair game, and the only protection of the answer is that the image does not hold it. Everything below is
about making that true.

## 1. Where it survives

| Place | Why it is still readable | Check |
|---|---|---|
| Dead code | unreachable ≠ unreadable | scan the whole package, not the import graph |
| Constants the grader read | a constant whose only reader was the grader still describes it; so does a comment on one that stays (`# Horizontal speeds above which move reward is 1.`) | no module-level name may be write-only afterwards; no comment may mention the reward |
| Attributes set at construction | weights in `__init__` are not "functions with a matching name", and a snapshot of the object keeps them: e.g. a HumanoidBench frozen instance that carried its reward weights | enumerate instance attributes at runtime; leave them out of anything saved from one |
| Class attributes | a class body's `_move_speed = _WALK_SPEED` keeps the module constant alive once `get_reward`, its only reader, is gone: HumanoidBench's `_WALK_SPEED = 1` and `_RUN_SPEED = 5` (the move term's bound and margin for walk, stair, hurdle) are still in the 0.1.6 image | **open**: extend the scrub's dead-name rule to class bodies, restore the attributes in `rcb_rewards`, and build a new image |
| Values the kept methods compute for the expert | a scrub that keeps `load_actors` because it builds the scene also keeps what it computes only for the removed expert: RoboTwin's `load_actors` sets the expert's target and waypoint poses (`adjust_bottle.left_target_pose`, …) and `dump_bin_bigbin.pour_actions`, the whole pouring motion as a ready-made action list | `images/robotwin/scrub_oracles.py` removes every attribute a kept method sets that no kept method reads (`LEAKS`), with the locals and comments that only feed it, keeps the random draws so the scene is unchanged, and fails the build on a new pose-like one; the oracles rebuild the scene with upstream's `load_actors` |
| Helpers the grader called | not named like the grader, so the name match keeps them: HumanoidBench maze's `update_move_direction` returned the checkpoint bonus, truck's `upon_table` held the table test | list what every removed method calls; delete what nothing else calls, keep only the effect of what the tooling still calls |
| Compiled bytecode | `*.pyc` built before the removal keeps the old code | clear caches *before* removing, assert after |
| Earlier Docker layers | a layer is an immutable tarball; a later `rm` does not unwrite it | download and remove in the **same `RUN`**; verify with `docker save` |
| `.git` | `git show` reconstructs every file ever committed | delete it in that same `RUN` |
| The network | upstream is public and pinned, one `curl` away | `[agent] network_mode = "allowlist"`: the model-API hosts and the package registries (PyPI, the Debian / Ubuntu apt archives; `scripts/set_agent_egress.py`), unless the task declares open network (PROTOCOL H.6, [CI]). The registries are not where solutions are published, with exceptions: some PyPI distributions ship a benchmark's scripted experts, trained policies or task sources (§5 below; nothing blocks them, a trial that installs one is looked at). On an open network a pointer inside the image (a `source_url`) leads the agent straight to the upstream solution |
| Instance metadata and upstream docs | a frozen instance that records where it came from (a `source_url`, a demonstration file, the expert's module) hands the agent the address of its solution: YAMLab's `instance.json` the recording its oracle replays, DexJoCo's `instance.npz` (`meta`) the demonstration whose actions are the reference, RoboLab's image shipped a recorded successful episode of one task; upstream READMEs name the public demonstration datasets and checkpoints | keep provenance in `scripts/<bench>/` and the README, never in a file under `environment/` the agent reads ([CI] `check-agent-pointers.py`); grep a new image for `https?://`, `*.hdf5` and recorded episodes before publishing it; the allowlist covers what an upstream checkout's documentation still names |
| The model API | tools that run at the provider, reached through an allowed model-API host: Codex's `web_search` and Claude Code's `WebSearch`; under a ChatGPT login also the account's connectors and apps (web open and search, GitHub, mail, drives), image generation and plugins | **closed**: the runner turns them off (running.md "No tool outside the container"; Codex calls connectors from its `exec` tool as `tools.mcp__codex_apps__*`, so grep the transcript for that name); and with the usage gateway on, the gateway is the container's only egress and forwards model-API calls only (running.md "Usage gateway") |
| The model-API key | Harbor's native agents put it in the agent's container. Codex: `OPENAI_API_KEY` in its environment and in `/tmp/codex-secrets/auth.json` (linked from `$CODEX_HOME/auth.json`), removed only after the run; Claude Code: `ANTHROPIC_API_KEY` (or its OAuth token) in its environment. With the model API allowed, the agent can spend it on any model, a search-enabled one included, which undoes the row above | **narrowed**: with the usage gateway on, the container reaches its provider only through the gateway's model-API paths (no connector, file or conversation endpoint, whatever the agent runs with the key or the login), and a model request is forwarded only if every tool it declares is one the agent runs itself (a web search, image generation or remote MCP tool, or an unreadable body, is refused). Still open: the key can be spent on another model of the same provider (a gateway that holds the key is ruled out: running.md "Official runs"): one key per batch with a spending cap (running.md "Unattended batches"), and read the transcript for direct API calls |
| The model's memory | the benchmark's source is public, so it is in pretraining data: Opus 5.5 recalled H1's 19 actuator ranges exactly and the sit reward's seat-height band, with no tool | nothing in the harness removes it; report it with the result |
| Package metadata | `*.egg-info/SOURCES.txt` lists files you deleted | generate metadata after the removal |
| Sibling tasks | one task's `tests/` must not carry another's answer | ship one task's answer per task |

Layers and `.git` are invisible from inside the container — overlayfs shows the agent only the merged
view. They leak to whoever pulls the image, which for a public benchmark is the same people.

**Read the agent's transcript.** Two of these rows came from watching one go looking: `grep -rn` over the
package, `cat` on the likely file, then `import dis, marshal` against the bytecode caches.

**Audit a harness** by pointing it at a local fake API and reading the tools of its first request (Codex sends them
in an `additional_tools` input item, not in `tools`); the tool set follows the model. Where the key goes: Harbor's
`agents/installed/codex.py` (`run()`) and `claude_code.py` (`_resolve_auth_env()`). Two channels an egress allowlist
cannot close: under a ChatGPT login Codex searches through `chatgpt.com/backend-api/codex/alpha/search`, the same host
as its model calls (off with `web_search=disabled`); and with an API key a request that carries
`tools: [{"type": "web_search"}]` (or `web_search_preview`) is served with real searches. The usage gateway refuses
both (`usage.jsonl` `refused`: `server_tool`, `path_not_allowed`), and its raw log shows the tool list of every request.

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

## 5. Packages on PyPI that carry a solution

The agent may install packages (PROTOCOL §5), and a registry is not free of answers: some distributions ship a
benchmark's scripted experts, trained policies or task sources. Nothing blocks them (what cannot be forbidden is let
go); a reviewer or a runner that sees one of these names in a trial's `pip install` (directly or as a dependency) looks
at what the trial did with it. Found from the archives' file lists, by name search of the index; a redistribution
under an unrelated name would be missed. A new benchmark whose solution is one `pip install` away adds its row here.

| Benchmark | Distribution | What it ships |
|---|---|---|
| RoboTwin 2.0 | `rlinf-robotwin-runtime` | the upstream task files with `play_once` (the reference solution the image scrubs) and `check_success`, 51 tasks |
| MetaWorld+ | `metaworld` | the scripted policy of every environment (the reference solutions), the environments and their assets |
| MyoSuite | `myosuite` (2.x), `myo-sim`, `robohive` | trained baseline policies of key-turn, obj-hold, pen-twirl, pose and reach (2.12: `agents/baslines_NPG`), every environment's source and models |
| MuJoCo Playground | `playground` (0.0.4: a trained Go1 joystick policy; every version: the task sources), `envpool` + `envpool-assets*` (the environments compiled, Menagerie's robot meshes) | the Go1 reference; a local copy of the hidden simulator in standard mode |
| MolmoSpaces | `molmo-spaces` | the planner policies the image stubs (`policy/solvers`), the tasks' `judge_success` |
| RoboPaint | `kanjivg` | ordered stroke paths of the kaishu characters (a Japanese textbook typeface, not the exemplars' glyphs) |
| KinDER | `kindergarden` | the upstream package: environments, models, goal checks (standard mode; the privileged image already has it) |
| BEHAVIOR-1K | `bddl` | every activity's formal initial and goal conditions |
| RoboCasa, RoboCasa365, RoboCasa-GR1 | `praxis-robocasa`, `rlinf-robocasa365`, `rpent-robocasa365`, `praxis-robocasa-gr1` | task sources with `_check_success`; no kitchen assets |
| LIBERO-MAX | `libero`, `hf-libero`, `rlinf-libero`, `rpent-libero`, `praxis-libero`, `libero-infinity`, `rlinf-liberopro`, `rpent-liberopro`, `rlinf-liberoplus` | LIBERO's goal definitions and initial states; no meshes, no demonstrations, not LIBERO-MAX's events |

Not on PyPI under any name found: RoboTwin's own package, DexToolBench / SimToolReal, HumanoidBench, RoboWits, RoboLab,
ManiGuard, DexJoCo, VLABench, RoboDojo, RoboARC, RoboOlympics, BiGym,
YAMLab, Panda Dynamic Scenes (not published at all: its environment package is this repository's `images/pandadyn/`),
DexHand (not published at all: its scenes and tooling are this repository's `scripts/dexhand/` and `images/dexhand/`),
AM-Bench, iSpatialGym (GitHub and Hugging Face only), IKEA MuJoCo (not published at all: its scenes are this repository's
`images/ikea-mujoco/scenes/` with meshes on a private dataset); Isaac Sim does not install from pypi.org.
