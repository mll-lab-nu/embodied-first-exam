# The task format

A task is a self-contained Harbor task directory under `tasks/<benchmark>/`, one folder per benchmark. The benchmark
adds as little as possible on top of Harbor's format. Anything this document does not describe is the task's own
business: the simulator, how a scene is defined, the privileged tool API, how a verifier decides internally.

Most rules here are conventions. CI reports a departure as an advisory warning. The rules marked **(H.n)** come from
the invariants in [invariants.md](invariants.md) and bind. The table at the end lists the check for every rule.

## Normal form

Every task is in the normal form that `scripts/task_conventions.py` (`normalize`) writes. `normalize` renders the
generated parts: the README, the `## Limits` section of the instruction, the caps, the resource monitor's wiring, the
MCP server entry, `[verifier] network_mode` and, last, `DIGEST`.

```bash
python3 scripts/task_conventions.py tasks/<benchmark>/<task>          # normalize after a hand edit
python3 scripts/task_conventions.py --check tasks/<benchmark>/<task>  # report what normalize would change
```

Edit a generated part at its source (the task's own fields, `scripts/task_resources.toml`,
`tasks/<benchmark>/readme.toml`), never in the task.

## What a contribution delivers

- Task directories under `tasks/<benchmark>/`, nothing else.
- No task-generation code goes into the repository. Generators, oracle searches, instance freezers and release
  builders stay with their authors. `scripts/` holds only what running the benchmark needs.
- Code several tasks of a benchmark share goes, preferably, into the benchmark's base image (`images/<name>/`), so the
  tasks get it from the image.
- Otherwise it goes into `embodied_first_exam/benchmarks/<benchmark>/`, the same folder name as `tasks/<benchmark>/`.
  A files-only image is built from it (`scripts/files_image.py`, `images/<name>/FILES.json`). The tasks' Dockerfiles
  copy from that image by digest.
- A benchmark's own choices are documented in `tasks/<benchmark>/README.md`.

## Directory layout

```
tasks/<benchmark>/<task>/
  task.toml               Harbor's task file, with the fields below
  instruction.md          what the agent reads
  README.md               for people; rendered, never given to the agent
  DIGEST                  the task's content digest (H.8)
  environment/
    Dockerfile            the agent's image
    docker-compose.yaml   services, caps, GPU reservations (standard modes: the sim service)
    sim/                  standard modes: the sim service's build context (its own Dockerfile)
    efe_mcp/              standard modes: the MCP server's manifest
  tests/
    Dockerfile            the verifier's image (H.1)
    test.sh               executable; the verifier's entry point
    seeds/<seed>/         committed instances of seeds other than the default
  solution/
    solve.sh              executable; required unless oracle = "none"
```

- **Name.** The directory is `<base>-<mode>`. The mode is the whole suffix: `-privileged`, `-standard` or
  `-realtime`. `<base>` is `<benchmark>-<family>-i<NN>` or the upstream task name. Names carry no versions or
  durations. The naming rules per benchmark are in [TAXONOMY.md](../TAXONOMY.md#task-names).
- **Self-contained.** All task code is in the directory, or in a pinned image its Dockerfiles take it from: the
  benchmark's base image, or a files-only image (`COPY --from=<image@digest>`). Nothing imports repository code at
  run time. A task's identity is its directory (H.8).
- **Base images.** `ghcr.io/mll-lab-nu/efe:<name>-<version>`, with the version from `images/<name>/VERSION`. An image
  that may not be redistributed carries `images/<name>/BUILD_ONLY` and is tagged
  `ghcr.io/mll-lab-nu/efe-private:<name>-<version>`. Every `FROM` and `image:` is pinned to a tag or a digest. See
  [operations.md](../operations.md#base-images).
- **No results.** A task directory has no `results/`. Results go to the results site.
- **Shared files of a sidecar.** A sidecar's directory (`environment/sim/`, `environment/scorer/`, served at `/srv`)
  holds only what is the task's own: its frozen instance, per-task grader data, files no other task has. Shared files
  come from a pinned files-only image: the benchmark's `images/<folder>-files/`, or `images/standard-files/` for the
  service layers, the shipped clients, the MCP server and the shared grader.
- **Changes in place.** A change to a published task, its scene included, is made in place. The task keeps its name
  and gets a new `DIGEST` (H.8). The pull request says what changed and why. The README describes the task as it is
  now.

## Modes

The modes live in one registry, `MODE_REGISTRY` in `scripts/task_conventions.py`. A benchmark may ship any subset of
them. Each task is independent: it has its own instruction, README and grading.

| Mode | What the agent gets | What is graded |
|---|---|---|
| privileged | The simulator in its own container: privileged state, free resets, planning tools. | A deliverable under `/app/output/`: a trajectory (`trajectory.npz`) or code (`task_type = "policy"`), replayed by the separate verifier. |
| standard | A robot service in a `sim` sidecar it cannot open, reached through the shipped client or the MCP tools. The world stands still between calls. | The live episode the service ran, judged by the service (H.4). |
| realtime | The same service on a clock that does not stop once the episode has started. The robot runs at 1/S of real speed and holds its last targets while the agent thinks. | The live episode, as in standard mode. |

- The wire protocol of the standard modes is `eai-standard/3.0` ([eai-standard.md](eai-standard.md)).
- Every standard and realtime episode is agent-ended. The service never shows the success. The agent ends the
  episode with `POST /finish`, and the state it ends in is judged
  ([eai-standard.md](eai-standard.md#agent-ended-episodes)).
- Every standard and realtime task offers its service two ways: the shipped HTTP client and the MCP server
  `efe-robot`. Three kinds of task keep only their own interface: roboEngineer, the `matchlow` matches, and a match
  exported without the match extension.
- A benchmark with its own runtime may export tasks that keep it. Their `[metadata] protocol` names that runtime, and
  they are listed in `ci_checks/benchmarks/<bench>/exported.toml`. They are plain Harbor tasks, the invariants apply
  to them unchanged, and their results are reported apart.
- **Adding a mode** is a protocol change in a pull request of its own, merged before the benchmark that uses it. It
  contains: the name (the directory suffix); its definition in these documents (what the agent gets, what is graded,
  the time and reset rules, which failures are infrastructure); the `MODE_REGISTRY` entry and its `LIMITS_TIME`; CI
  support keyed on the registry, with a self-test case; one benchmark using it; the [TAXONOMY.md](../TAXONOMY.md)
  entry; and its cutoff relation (`same_cutoff_as`, or free).

## `task.toml`

The fields a task writes. `normalize` adds the rest (the monitor's artifact and collect hook, `[verifier]
network_mode`, the caps, the MCP server entry).

| Field | Meaning | Default and rules |
|---|---|---|
| `schema_version` | Harbor's schema | `"1.3"` |
| `artifacts` | What Harbor collects | must include `"/app/output/"`; standard modes add the sim service's records |
| `[task] name` | The task's name | `"embodied-first-exam/<directory name>"` |
| `[metadata] task_type` | The deliverable | `trajectory` or `policy` |
| `[metadata] simulator`, `robot` | What it runs on | values in [TAXONOMY.md](../TAXONOMY.md) |
| `[metadata] family` | The scene and goal, shared by its instances | a free-form slug |
| `[metadata] dynamics` | Whether something in the scene moves on its own | `static` or `dynamic`; every task declares it ([TAXONOMY.md](../TAXONOMY.md#dynamics)) |
| `[metadata] protocol` | The wire protocol | standard and realtime only: `eai-standard/3.0`, or an exported runtime's own id |
| `[metadata] oracle` | How far the reference solution gets | `full`, `partial` or `none` |
| `[metadata] oracle_evidence` | Where the evidence of solvability is | required unless `oracle = "full"` |
| `[metadata] instance_seed` | The default seed: the instance as committed | every task has one ([Seeds](#seeds)) |
| `[metadata.seeds]` | Other seeds: `allowed`, `oracle`, `build` | only where they differ from the defaults ([Seeds](#seeds)) |
| `[metadata] expert_time_estimate_hours` | How long an expert would need | a number |
| `[metadata] replays` | Fresh replays a privileged grader may run | privileged only; default 1 ([Grading](#grading)) |
| `[metadata] validated` | Whether the task is validated | default: `oracle = "full"`; a marker, not part of the configuration |
| `[metadata.honour] stricter` | Rules stricter than the defaults | rendered into the Network line; never looser |
| `[agent] timeout_sec` | The agent's cutoff, in whole seconds | 3600 unless the pull request justifies another; at most 14400 |
| `[agent] network_mode` | The agent's egress (H.6) | `"allowlist"`; `"public"` for open egress, the author's choice |
| `[agent] allowed_hosts` | The allowlist | exactly `scripts/set_agent_egress.py` `HOSTS` (`set_agent_egress.py allowlist` writes it) |
| `[verifier] environment_mode` | The verifier's sandbox (H.1) | `"separate"` |
| `[verifier] timeout_sec` | The verifier's time | the task's choice |
| `[environment]`, `[verifier.environment]` | Caps of `main` and of the separate verifier | [resources.md](resources.md) |

Benchmark-specific `[metadata]` fields are listed in [TAXONOMY.md](../TAXONOMY.md).

**Settings that live elsewhere.** A task states each setting once, where the code reads it:

| Setting | Where | Default |
|---|---|---|
| Mode | the directory suffix | — |
| Reset budget N | the `sim` service's `RCB_RESET_BUDGET` default; served as `/spec.budget.reset` | 0 |
| Step limit | the `sim` service's `RCB_STEP_LIMIT` | none: the service's own step cap |
| Slowdown S (realtime) | the `sim` service's `RCB_SLOWDOWN` default; served as `/spec.timing.slowdown` | 1 when the service's real-time factor is at least 3, else ⌈1.5 / RTF⌉ |
| Agent-ended episodes | the `sim` service's `RCB_AGENT_END: "1"` (written by `normalize`) | required in the standard modes |
| The service's clock | the `sim` service's `RCB_WALL_CLOCK_S` (written by `normalize` from the cutoff) | equals `[agent] timeout_sec` |

CI fails a `task.toml` with `[metadata] network`, and warns on `[metadata]` `mode`, `reset_budget`, `slowdown` or
`tier`: each copies a setting that lives elsewhere.

**The effective configuration.** Every trial records its effective configuration: protocol version, mode, cutoff,
reset budget, S, seed, network and the `validated` marker (`effective_config` in `scripts/task_conventions.py`).
Results are ranked only among trials with the same configuration key (`config_key`;
[running.md](running.md#results)).

## `instruction.md`

The instruction is what the agent reads. A human writes it. It has a `# ` title line and then exactly these sections,
in this order, and nothing else at the top level (`V2_SECTIONS`):

| Section | What goes in it |
|---|---|
| `## Task` | The request, in a sentence or a few. |
| `## Goal` | The success condition, the agent-end paragraph (standard modes), the deliverable (privileged) and the rules. |
| `## Robot Interface` | The robot and its scene, the mode line, the Finish line (standard modes), the client or session API, actions and observations. `###` sub-sections are allowed. |
| `## Others` | Optional. Anything the agent needs that fits no other section. Left out when empty. |
| `## Limits` | Rendered by `normalize`. Never edited by hand. |

**Goal.**
- The success condition is written in terms the agent can observe in that mode. Name each object by its appearance
  or its starting place. Describe an axis or point physically ("the keyboard's short edge", "the key's teeth end"),
  and say whether the condition already holds at the start. Upstream identifiers (labels, function names, indices,
  asset metadata) may follow, only in brackets.
- Keep it minimal: no grader code and few thresholds. A threshold that is stated equals the grader's.
- In the standard modes, the Success sentence is followed by one short paragraph:
  "When you are done, send `/finish` to end the episode and get it graded." It is followed by "Only the state at that
  point counts." for a goal judged on its end state. For a goal that counts some steps as they happen and judges the
  rest at the end, it is followed by "Everything else is judged on the state at that point." instead.
- Rules: the **No cheating.** rule comes first. It is the same text in every task (`NO_CHEATING`).
- A privileged instruction names the deliverable under `/app/output/`. A standard-mode instruction has no deliverable.
- The instruction never mentions `/tests/`.

**Robot Interface.**
- The mode line says how the agent reaches the robot (`V2_MODE_LINE`).
- In the standard modes, the Finish line is its own paragraph after the mode line:

  > `POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

  A task without the MCP tools drops "MCP tool `finish`" (`ROBOT_FINISH`).
- It states every convention the agent cannot infer: frames, quaternion order, units, action layout, client usage.
  Whether world-frame quantities are given is decided per benchmark and kept consistent within it.
- In the standard modes, `normalize` adds a `### MCP tools` sub-section after `### Client`.

**Limits.** `normalize` renders these lines, in this order:
- Time: the cutoff and what it means in the mode (`LIMITS_TIME`). It is the only place that states the limit as a
  duration. A benchmark's own text says "the time limit (Limits)".
- Tokens.
- Network: what can be reached, read and installed (`LIMITS_NETWORK`; the open-network text for an open task).
- Resources: the caps of the agent's own container ([resources.md](resources.md)).
- The task's own lines: Resets, Steps and the like. A task without a Resets line gets its mode's default.
- Finish (standard modes): what is graded if the agent never sends `/finish` (`LIMITS_FINISH`). For example: "if you
  never send `/finish`, the episode is graded when your session ends."

**Everything at hand.** Everything a task needs at run time is in its image or directory. Nothing tells the agent to
download something.

## `README.md`

Every task directory has a `README.md` for people who read or review the task. It is not given to the agent: no image
is built with it and no container mounts it. It describes that one task and nothing else, so a reader needs no other
task to understand it.

Nobody writes it by hand. `normalize` renders it from three sources: the task's `instruction.md`, its `task.toml`
(and its compose file, for the realtime slowdown), and the benchmark's data file `tasks/<benchmark>/readme.toml`. To
change the wording, edit the source and run `normalize`. `--check` fails when the committed README differs from the
rendered one, or when `readme.toml` lacks something the README needs. A missing piece is never filled with a
placeholder.

### Layout

```
# <title>

| | |
|---|---|
| Task ID | ... |
| Benchmark | ... |
| Robot | ... |
| Mode | ... |
| Opponent | ...            (match tasks only) |
| Instance | ... |
| Time limit | ... |
| Reference solution | ... |

## Task
## Success criteria
## Resource requirements
## Others                     (optional)
## License
```

The headings appear in exactly this order. `## Others` is the only optional section, and it is left out when it has
no text. No other heading is allowed, nor any `###` sub-heading outside `## Task` (whose body is the instruction's,
verbatim, its own sub-headings included).

### Title and key table

| Row | What it says | Source |
|---|---|---|
| (title) | The instruction's `# ` line, verbatim | `instruction.md` |
| Task ID | The task directory name, in backticks | the directory |
| Benchmark | The upstream benchmark's name (linked when a URL is given), its citation, and the pinned upstream repository and short commit: ``Name (Authors, year), upstream `owner/repo@abc1234` `` | `readme.toml` `[benchmark]` `name`, `url`, `citation`, `repo`, `commit` |
| Robot | The robot's display name | `[metadata] robot`, looked up in `readme.toml` `[robots]` |
| Mode | `privileged`, `standard`, or `realtime, slowdown <S>` | the directory suffix; S is the `RCB_SLOWDOWN` default |
| Opponent | The opponent's level; match tasks only | `readme.toml` `opponent` |
| Instance | `` `<family>`, seed <n> `` | `[metadata] family`, `instance_seed` |
| Time limit | The agent's time limit in words (`30 min`, `1 h`, `1 h 30 min`) | `[agent] timeout_sec` |
| Reference solution | `Included` (`oracle = "full"` and `solution/solve.sh`), `Pipeline check only` (`oracle = "partial"` and `solution/solve.sh`), or `None` | `[metadata] oracle`, `solution/` |

### Sections

| Section | What goes in it | Source |
|---|---|---|
| `## Task` | The instruction's `## Task` body, verbatim | `instruction.md` |
| `## Success criteria` | The exact pass condition or conditions, in plain English; thresholds may be given. The failure terminations, and which episode or file is graded: in privileged mode the delivered trajectory, replayed open-loop; in the standard modes the live episode (with resets, the last of up to N episodes) and what ends it. For a match, the forfeits (`no_show`, `ready_timeout`, the session ending first). | `readme.toml`: the family's (or task's) `success` text, then the mode's `[modes.<mode>] success` text |
| `## Resource requirements` | The caps of each container (main, sim, verifier) and the GPU line | `[environment]`, the compose files and `scripts/task_resources.toml` |
| `## Others` | Optional. Anything the reader needs that fits no other section. | `readme.toml` `others`: for the whole benchmark in `[benchmark]`, overridable per family or per task |
| `## License` | The upstream benchmark's name and license, with a link (NC and NC-SA terms flagged), and the asset licenses where relevant (from `images/<image>/NOTICE`) | `readme.toml` `[license] text` |

### `readme.toml`

One data file per benchmark, at `tasks/<benchmark>/readme.toml`. Unknown tables and keys are errors.

- `[benchmark]`: `name`, `citation`, `repo`, `commit` (all required); `url` and `others` (optional).
- `[license]`: `text`.
- `[robots]`: one display name for each `[metadata] robot` value.
- `[modes.<mode>]`: `success`, the text that follows the family text in every task of that mode (what is graded, and
  how). Each mode the benchmark ships needs one.
- `[families."<family>"]`: `success` (all modes), with optional per-mode replacements `privileged`, `standard` and
  `realtime`. Optional keys: `vars` (values for `{vars[...]}`), `opponent`, `others`, and `no_twin` (why a standard or
  realtime task has no privileged-mode task).
- `[tasks."<task dir or base name>"]`: the same keys, for a task a family text cannot cover. The most specific entry
  wins: the task directory, then the base name, then the family.
- Texts may use placeholders: `{task}` `{base}` `{mode}` `{family}` `{env}` `{seed}` `{timeout}` `{timeout_s}`
  `{resets}` `{slowdown}` `{md[<metadata key>]}` `{vars[<key>]}`. Write a literal brace as `{{` or `}}`. An unknown
  placeholder fails the render.
- Next to each success text, a `#` comment cites the code the condition comes from: the grader (`tests/grade.py`),
  the sim service, or the upstream success function.

### What a per-task README must not contain

- The name of any other task directory or another task's base name, the same task in another mode included.
- A protocol version.
- Rows or sections outside the layout: no difficulty, baselines, verification prose, image notes or history.
- Any description of how the reference solution, or any other strategy, solves the task. Success criteria say what
  counts as success, never how to reach it.

## The benchmark README

Facts that every task of a benchmark shares belong in `tasks/<benchmark>/README.md`: the upstream, the license,
changes from upstream such as physics and asset fixes, the observation and action interface, and the grading method.
It may name task directories. Its sections, in this order:

```
## Overview
## Upstream and license
## Changes from upstream
## Interface
## Grading
## Tasks
## Others        (optional)
```

`## Others` is left out when it has no text.

## Seeds

- The default seed is `[metadata] instance_seed`: the instance as committed.
- `[metadata.seeds]` lists other seeds, only where they differ from the defaults:
  - `allowed`: the seeds a runner may draw from. A list, a range `{ from = A, to = B }` or `"any"`. Default: the
    default seed alone.
  - `oracle`: the seeds the reference solution is for. Default: the default seed with a reference solution, else none.
  - `build`: `"frozen"` (default) or `"runtime"`. With `"frozen"`, every allowed seed other than the default has its
    frozen instance committed under `tests/seeds/<seed>/`. A range or `"any"` needs `"runtime"`: the task builds each
    seed's instance itself.
- A committed seed's directory holds the instance files, the seed's other files at their paths (a per-seed
  `solution/`, for example) and a `seed.toml` of text replacements (pinned hashes, the scene's description). It is
  never under `environment/`. `scripts/task_seed.py materialize` puts them in place in a copy of the task.
- Provide as many seeds as you can. At least three are recommended. A task with fewer still passes.
- How a runner draws a seed: [running.md](running.md#seeds).

## Grading

**The verifier.** `tests/test.sh` runs in the verifier's own sandbox (H.1). It writes `/logs/verifier/reward.txt`
(`1` or `0`) and `/logs/verifier/reward.json` (numbers only). The same field names are used wherever the concept
applies:

| Field | Meaning |
|---|---|
| `success` | The verdict |
| `replays`, `replays_succeeded`, `deterministic` | Privileged trajectory tasks: the fresh replays run and how many succeeded |
| `live_success`, `graded_by_live` | Standard modes: how the live episode ended; `graded_by_live = 1` |
| `first_success` | Standard modes: the first episode's own result, the no-reset performance |
| `infra_error`, `sim_error`, `grader_error` | Why there is no verdict, or why the agent's actions failed |
| `progress`, `n_actions`, `sim_steps` | Progress and cost fields |
| resource fields | [running.md](resources.md#the-record) |

**Privileged mode.**
- Success is judged on the end state of one fresh replay of the deliverable.
- A task whose simulator does not replay bit-wise declares a replay count N (`[metadata] replays`). Its grader replays
  the deliverable up to N times, each in a fresh process, and stops at the first success. The attempt succeeds if any
  replay succeeds. `deterministic` is evidence only.
- Determinism is checked when a task is built, not in every trial. The author makes sure that fresh replays of a
  positive example end on the same final-state hash on the evaluation hardware, and puts the evidence in the pull
  request.
- A scene build does not depend on the host (sorted listings, no wall clock). An instance rebuilt with another state
  hash gives no verdict: `instance_mismatch`, an infrastructure failure.

**Standard modes.** The sidecar judges the live episode with the task's own rule. A settle or hold window the task
declares runs on the live simulator. `reward.json` says `graded_by_live = 1` and `replays = 0` (H.4).

**Failures.**
- An infrastructure failure is `infra_error = 1`. It is not a result: neither a success nor the agent's 0 (H.5).
- A simulator error is the agent's failure. An episode that ended in `error`, or in which the simulator raised an
  error on the agent's actions, scores 0 (`success = 0`, `sim_error = 1`), whatever it had reached before. It is an
  infrastructure failure only when the service records `infra_error = 1` (the agent had not acted yet).

**Videos.**
- Every graded trial leaves a playable video and the replayable trajectory it was graded on. The one exception is a
  privileged trial whose agent submitted no trajectory, or none that replays.
- By default the video is a post-hoc replay, rendered afterwards from the trajectory (`replay.mp4`).
- Where the simulator is not verified bit-wise replayable, the standard modes record the video live in the sim sidecar
  (`live.mp4`). Privileged videos are always replays. Each benchmark states which kind its standard modes use, and
  every video is labelled with its source (`video_source`).
- The verdict is written before the video is rendered and never depends on it.
- With resets, the shared sidecar grader also keeps the first episode's trajectory and video
  (`trajectory.first.npz`, `replay.first.mp4`), as evidence only.

**Oracle and validation.**
- `nop` scores 0.
- With `oracle = "full"`, the oracle scores 1 on every seed in `seeds.oracle` (`/validate`).
- A task without a full oracle gets a human review: a positive example, the predicate, `nop` 0 and determinism,
  recorded in the pull request ([REVIEWING.md](../REVIEWING.md#human-review-oracle-partial-or-none)).

## `DIGEST`

`DIGEST` is the task's content digest (H.8). `normalize` writes it last. After any hand edit, run `normalize` on the
task. Results are attributed by digest, so a changed file is a changed task, under the same name.

## Checks

`bash ci_checks/run_all.sh <task dirs>` runs every check below. `ci_checks/run_invariants.sh` runs the invariant
ones alone. "The task-structure check" is `ci_checks/check-task-layout.py`, the shared per-task check of files,
names, the README's layout and `task.toml` fields.

| Rule | Tier | Enforced by |
|---|---|---|
| The required files exist; `tests/test.sh` and `solution/solve.sh` are executable; `solve.sh` exists unless `oracle = "none"`; no `results/` | advisory | the task-structure check |
| `[task] name` matches the directory; the directory ends in a mode; the required `[metadata]` fields; `dynamics` declared; `/app/output/` in `artifacts`; no copied settings | advisory | the task-structure check |
| The task is in normal form: rendered README, `## Limits`, caps, monitor, MCP entry | advisory | `scripts/task_conventions.py --check` |
| The README's headings and key-table rows in order, title from the instruction; a standard or realtime task without a privileged-mode task says why (`no_twin`) | advisory | the task-structure check |
| No other task's name in a README; `readme.toml` has no stale entries; the benchmark README's sections in order | advisory | `ci_checks/check-readmes.py` |
| No image copies or mounts a README | advisory | `ci_checks/check-dockerfile.sh` |
| Pinned `FROM` / `image:`; images from the one registry | advisory | `ci_checks/check-dockerfile.sh`, `ci_checks/check-protocol.py` |
| The `protocol` value per mode; oracle fields; `replays` only in privileged mode | advisory | `ci_checks/check-protocol.py` |
| The instruction never mentions `/tests/`; a privileged one names its deliverable; standard-mode prose names no bare code-like term | advisory | `ci_checks/check-instruction.sh` |
| The cutoff is a whole number of seconds, at most 14400; the Time line, the README's Time limit row and `RCB_WALL_CLOCK_S` agree | advisory | `ci_checks/check-cutoffs.py` |
| The caps match the rules; the Resources line and the README section are rendered from them | advisory | `ci_checks/check-resources.py` |
| Seeds: the declared seeds and their committed instances agree | advisory | `ci_checks/check-seeds.py` |
| Realtime: S and the reset budget declared in the sim service | advisory | `ci_checks/check-realtime.py` |
| Every standard and realtime task has the MCP tools | advisory | `ci_checks/check-mcp-tools.py` |
| The Goal says how an agent-ended episode is judged | advisory | `ci_checks/check-agent-end.py --tier advisory` |
| Every task renders a video | advisory | `ci_checks/check-video.py` |
| The standard graders transcribe the live verdict | advisory | `ci_checks/check-live-verdict.py` |
| Verifier isolation, egress, sidecar topology (H.1, H.3, H.4, H.6) | invariant | `ci_checks/check-verifier-isolation.sh` |
| No pointer to a solution in the agent's reach (H.2) | invariant | `ci_checks/check-agent-pointers.py`, benchmark `invariant-*` hooks |
| No simulator in the agent's image (H.3) | invariant | `ci_checks/check-standard-agent-image.sh` |
| `RCB_AGENT_END: "1"` and the Finish line in every standard and realtime task (H.3) | invariant | `ci_checks/check-agent-end.py --tier invariants` |
| One protocol id, `eai-standard/3.0`, in every tracked file (H.3) | invariant | `ci_checks/check-protocol-strings.py` |
| Byte-identical instance copies (H.4, H.7) | invariant | `ci_checks/check-instance-copies.sh` |
| The same instance, seeds and cutoff across modes (H.7) | invariant | `ci_checks/check-twins.py` |
| `DIGEST` equals the task's digest (H.8) | invariant | `ci_checks/check-dataset-manifest.sh` |
| Each rule above catches a real task broken that way | both | `ci_checks/check-ci-selftest.py` |

A benchmark-specific check is that benchmark's hook, `ci_checks/benchmarks/<bench>/invariant-*` (it guards an
invariant: blocking) or `advisory-*` (a convention: a warning). Shared `ci_checks/` names no benchmark.
