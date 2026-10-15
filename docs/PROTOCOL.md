# Robot Coding Bench — Task Protocol v1.2-rc

**Version: v1.2-rc** (2026-10-10). Changes in this version: the resource monitor sidecar, the docker caps and the
verifier's limits step are in every task (§2.10; #131, with the review fixes of the same day: an out-of-memory kill is
the agent's only at its container's own cap, a benchmark-owned service killed for memory is never the agent's 0, a CPU
cap above the host's CPU count is clamped by the runner); enforcement is off by default, and v1.2 becomes final when
the calibration batch has confirmed the limits. Also on 2026-10-10 and 2026-10-11 (owner decisions, board 0072): every task's
agent egress is the model APIs and the package registries, every instruction states the same honour rule about looking
solutions up (§2.11), and the usage gateway forwards model-API calls only (D11, §5). On 2026-10-11 (owner): §4.8's exception for
physics that does not replay bit for bit (such a task is standard only and graded by the live episode; RoboDojo's six). Also on 2026-10-11 (owner, board 0080): the agent's time cutoffs live in one table (until 2026-10-14: since then each task sets its own in `task.toml`, as in Terminal-Bench; owner, board 0120), and every instruction ends with its cutoff and the request not to cheat in one format (§2.12; 2026-10-12: at the end of the instruction, and the table takes exceptions per family and per task). On 2026-10-14 (owner, boards 0106 / 0112): scene dynamics (§2.15), and every standard-realtime task states its slowdown S and allows resets, 10 by default (§4b). On 2026-10-12 (owner): §3's and §4.8's exception for grading by one replay instead of two (RoboDojo). On 2026-10-14 (owner, board 0107 E6): a benchmark ships any subset of the three modes, a general rule that replaces the per-benchmark exceptions for a missing twin (§2.15; where privileged and standard both exist, their cutoffs stay equal), and new modes may be added by pull request, through one registry of modes (§2.16). On 2026-10-14 (owner, board 0107 E7): §4c, tasks a benchmark exports with its own service and grader (RoboOlympics' matches and skill tasks). Earlier versions, whose rules are all part of this text: v1.0
(2026-09-30: the two modes and their names), v1.1 (2026-10-08: the standard-realtime mode, §4b), v1.1.4 (compute
resources, §2.9), v1.1.5 (resource limits, §2.10).
The tasks in the repository follow it except for the open items in §7. The wire format of standard and
standard-realtime mode (`eai-standard/2.x`) is specified in [`STANDARD_MODE.md`](STANDARD_MODE.md).

> **Names.** v1.0 renamed the two modes (unlimited → **privileged**, limited → **standard**) and the standard-mode
> protocol (`rcb-limited/2.x` → **`eai-standard/2.x`**); task directories end in `-privileged` or `-standard`. Base images
> moved to `ghcr.io/mll-lab-nu/eai-<name>` on 2026-10-02 (§7). v1.1 added a third mode, **standard-realtime** (`-standard-realtime`): standard
> mode's robot as a service, on a clock that does not stop.

## 0. Conventions

| Level | Meaning |
|---|---|
| **MUST** / **MUST NOT** | Required / forbidden. A PR that violates it is not merged. |
| **SHOULD** | Recommended. Deviations are explained in the PR or the task README. |
| **MAY** | Optional; left to the task or benchmark. If adopted, it is implemented as specified here. |

Basis tags: **[CI]** enforced by `ci_checks/`; **[current]** what existing tasks already do (exceptions are named and
listed in §7); **[new]** introduced by v1.0 — required for new work, partly enforced by `ci_checks/check-protocol.py`,
and applied to existing tasks by the migration (§7).

**Principle.** The benchmark adds as little as possible on top of the Harbor task format. Anything not specified here
(which simulator, how a scene is defined, the shape of the privileged-mode tool API, how a verifier decides internally)
is the task's own business.

### 0.1 Terms

| Term | Meaning | Former name |
|---|---|---|
| **privileged mode** | Agent and simulator share a container; the agent may read privileged state, reset freely, call planning primitives. The deliverable is a trajectory. | unlimited |
| **standard mode** | Robot as a service: the simulator runs in a sidecar the agent cannot open; the agent only sends actions and receives images and proprioception through a client; no reset, unless the benchmark grants a reset budget (§4.5). | limited |
| **standard-realtime mode** | Standard mode on a clock that does not stop: once an episode starts, the robot runs in real time (divided by the slowdown S) whatever the agent does, holds its last targets while the agent thinks, and the agent drives it from a program of its own (§4b, `eai-standard/2.3`). | — (v1.1) |
| **`eai-standard/2.x`** | The standard-mode wire protocol (§4). | `rcb-limited/2.x` |
| **`eai-<name>`** | Base image (a simulator stack, usually one per benchmark) under `ghcr.io/mll-lab-nu/` (§2.4). | `rcb-<sim>` under several registries; `eai-<name>` under `embodied-agent-interface-v2-internal` until 2026-10-02 |

Unchanged: the task name prefix `robot-coding-bench/`, the client and tool file names (`rcb_client.py`, `rcb1.py`,
`rcb_traj.py`), the `RCB1` frame format and the `RCB_*` environment variables.

### 0.2 Design decisions

| # | Topic | Decision |
|---|---|---|
| D1 | Standard-mode protocol | Only `eai-standard/2.x`. Additive extensions are accepted through a protocol-change PR (2.2 is accepted once its services implement crash recovery). Reset is only an optional capability (`budget.reset = N`, default 0; results with N > 0 are reported separately). Documented per-benchmark exceptions (§4.5): HumanoidBench standard defaults to N = 50 (owner, 2026-10-07), MyoSuite standard to N = 10 (owner, 2026-10-09); BiGym2 and KinDER standard to N = 10 (owner, 2026-10-11); DexToolBench standard to N = 20 (owner, 2026-10-13); MuJoCo Playground's quadruped standard tasks to N = 10 (owner, 2026-10-14). The standard-realtime mode's `eai-standard/2.3` (§4b) is 2.2 plus the realtime capability. `eai-standard/2.4` (issue #89) is 2.3 plus the operations capability; standard tasks may use it. No step caps. The one other kind: tasks a benchmark exports with its own service, grader inside, on its own named protocol (§4c; owner, 2026-10-14: RoboOlympics), 2026-10-13); DexHand standard to N = 20 (owner, 2026-10-14); MuJoCo Playground's quadruped standard tasks to N = 10 (owner, 2026-10-14). The standard-realtime mode's `eai-standard/2.3` (§4b) is 2.2 plus the realtime capability. `eai-standard/2.4` (issue #89) is 2.3 plus the operations capability; standard tasks may use it. No step caps. |
| D2 | Tasks without an oracle | Allowed, with mandatory human review (§2.7). |
| D3 | Results | Not in the repository: agent results (per-task READMEs, videos, timelines, batch tables) are published on the results site and the Hugging Face dataset; a task directory has no `results/`. |
| D4 | Run id | `<harness>-<model>-<effort>`, model token with underscores (`codex-gpt6_luna-xhigh`); provider, tier and settings go in metadata. |
| D5 | Images | One registry (EAI organization), images named `eai-<name>` and versioned in `images/<name>/VERSION`; every image that may be redistributed is public, the rest are `BUILD_ONLY`. One image per **benchmark**, not per simulator: benchmarks on the same simulator may need different versions of it and of its dependencies (e.g. RoboCasa, RoboCasa365 and RoboCasa-GR1 on robosuite), so each may have its own image; an image is shared only where the dependency set is identical. |
| D6 | PR granularity | One benchmark per PR; changes to shared files go in a separate PR reviewed by a maintainer. |
| D7 | World-frame information in instructions | Decided per benchmark, consistent within it, documented in the benchmark's doc. |
| D8 | Agent time budget (the cutoff) | 3600 s by default, at most 14400 s; another number is justified in the pull request that sets it; one number within a benchmark and mode unless that pull request says why (§2.12), always the same in a task's privileged and standard versions (§2.15), and results are grouped by budget. No benchmark has an exception to the cap (§2.3). Each task sets its own, `[agent] timeout_sec` in its `task.toml` (its author, or its benchmark's generator; no central table), and every instruction states it in one format, in its last section (§2.12; owner, 2026-10-11, 2026-10-12 and 2026-10-14). |
| D9 | Shared code | Shared sources are copied into tasks by the generator; nothing at run time imports repository code outside the task directory. |
| D10 | Token budget | Per trial: **100M input tokens, 10M output tokens** by default; exceeding either fails the trial. |
| D11 | Harness | Official results use Harbor's native agents only; no agent adapters, and no gateway that holds credentials or changes requests. The usage gateway (`scripts/usage_gateway/`) is allowed: it forwards model-API requests unchanged, records token usage, and refuses what a trial may not have: a request past the token budget (§5) and, since 2026-10-10, every request that is not a model-API call (§2.11). No tool that runs outside the trial's container is offered to the model (§2.11): official runs turn the harness's web search off (Codex `web_search = "disabled"`, Claude Code `WebSearch` and `WebFetch` disallowed; `scripts/run_agent_batch.sh` `WEB_SEARCH=disabled`, the default) and start the harness without account connectors, apps, plugins, image generation and cloud agents (Codex: with the same switch the runner sets those features to false in the run's `config.toml`, `scripts/codex_tools_off.py`). These run at the model provider, so no egress allowlist stops them (2026-10-02: Codex with a ChatGPT login searched GitHub by default; 2026-10-10: the same login handed the model 238 account connector tools, and 21 trials called them) |
| D12 | Mode naming | `mode ∈ {privileged, standard, standard-realtime}` (the third mode since v1.1, #86; named `standard-realtime` since v1.1.1, owner 2026-10-08, #97: it is standard mode's robot as a service on a clock that does not stop); the `tier` field is removed; every task directory ends in its mode: `-privileged`, `-standard` or `-standard-realtime`. More modes may be added by pull request, through the registry of §2.16 (owner, 2026-10-14). |

## 1. Checklist (every task)

1. `task.toml`, `instruction.md`, `README.md`, `environment/Dockerfile`, `tests/test.sh` (executable), `tests/Dockerfile`. [CI] `solution/solve.sh` depending on the oracle level (§2.7). [new]
2. `[task].name = "robot-coding-bench/<folder>"`; required metadata present and valid (§2.3). [CI]
3. Top-level `artifacts` includes `"/app/output/"`; `[agent].timeout_sec` set, a whole number of seconds ≤ 14400 (§2.3), the same as its privileged twin's (§2.12, §2.15). [CI]
4. Every image reference pinned to a tag or digest, never `:latest`. [CI]
5. `[verifier] environment_mode = "separate"`; `tests/Dockerfile` copies `test.sh`. [CI]
6. `instruction.md` names the deliverable under `/app/output/` and never mentions `/tests/`. [CI]
7. Carries its content digest in `DIGEST` (§2.8). [CI]
8. The verifier writes `reward.txt` (1/0) and a numeric-only `reward.json` with at least `success` (and `deterministic` for trajectory tasks). [current]
9. Same verdict in a fresh process; the verifier does not need the network (standard-mode verifiers run with `no-network`). [current]
10. Reference solutions only under `solution/`; nothing the agent can reach contains or points to one. [current]
11. `nop` scores 0; with an oracle, the oracle scores 1; without one, human review (§2.7). [new]
12. A published task's `environment/` and `tests/` inputs never change; a change is a new task. [current]
13. The directory name ends in `-privileged`, `-standard` or `-standard-realtime`, matching `mode` (§2.2); no `results/` directory (D3). [CI]
14. `README.md` in the standard layout (§2.1). [CI] (sections and key rows; `scripts/task_conventions.py --check` for the rest)
15. Runs with Harbor's native agents; no custom runner or adapter, and no gateway beyond the usage gateway (D11). [new]
16. Standard-mode tasks also satisfy every MUST in §4; standard-realtime tasks every MUST in §4 and §4b.
17. `[metadata.resources]` states the minimum CPU cores, memory and GPU memory of the agent phase and the verifier
    phase, the GPU class and a recommended GPU; the README's `## Compute resources` shows the same values (§2.9). [CI] (v1.1.4)
18. `[metadata.resources.limits]` states the agent phase's limits (GPU memory, memory, processes, disk) and the whole
    trial's expected peak, `[metadata.resources.caps]` the docker caps per service; `instruction.md` has the
    `## Resource limits` paragraph rendered from them, just before the closing `## Time limit` (§2.10). [CI] (v1.1.5)
19. `[agent] network_mode = "allowlist"` with the one host list (the model APIs and the package registries; a
    benchmark with open egress by a documented exception, §2.11, sets no network policy and has its own paragraph);
    `instruction.md` states `## External material` just before `## Resource limits` (and `## Time limit` last, item 20); the task itself needs no download
    at run time (§2.11). [CI]
20. `instruction.md` ends with `## Time limit`, rendered from the task's `[agent] timeout_sec`, after `## External material` and
    `## Resource limits` ("You have N seconds to complete this task. Do not cheat by using online solutions or hints
    specific to this task.", then what the cutoff means in the task's mode), and states the limit nowhere else; a
    standard-mode `sim` service is told the same number (§2.12). [CI]
21. `[metadata.seeds]` names the default seed, the allowed seeds (each a frozen instance; another seed's instance only
    under `tests/seeds/<seed>/`) and the seeds the reference solution is for (§2.13). [CI]

## 2. Task contract

### 2.1 Layout and self-containment
| Item | Level | Basis |
|---|---|---|
| `task.toml`, `instruction.md`, `README.md`, `environment/Dockerfile`, `tests/test.sh` (executable), `tests/Dockerfile` | MUST | [CI] |
| `solution/solve.sh` (executable): required for `oracle = "full"` or `"partial"`; may be absent for `"none"` (no `exit 1` placeholders) | MUST / MAY | [new] (Harbor itself does not require it) |
| `environment/docker-compose.yaml` (GPU or sidecar) | MAY | [current] |
| All task code (agent tooling, verifier) lives in the task directory and is copied in by its Dockerfiles; base images contain the simulator and its assets only | MUST | [current] |
| At run time, importing repository code from outside the task directory (packages under `scripts/`, a package at the repository root, a `PYTHONPATH` into the repository). Pinned third-party pip packages are fine. | MUST NOT | [current] — a task's identity is its directory digest, and Harbor builds from the task directory alone |
| Shared sources under `scripts/<bench>/shared/`, copied into each task by the generator; copies byte-identical within a benchmark | MAY (if used, identical) | [new] |
| Generated tasks come with their generator (under `scripts/<bench>/` for new benchmarks; existing generators are in `scripts/`); re-running it reproduces the committed tasks (`git diff` is empty) | SHOULD | [current] / [new] |
| `README.md` in the standard layout: `# <directory name>`; a key table with Benchmark, Mode, Twin, Simulator / robot, Family / instance, Oracle, Agent time budget, Base image; then `## Task`, `## Difficulty`, `## Reference solution`, `## Verification`, `## Compute resources` (§2.9), and `## Details` for anything else (extra rows, notes, provenance). No results in the README | MUST | [CI] |

### 2.2 Naming
| Item | Level | Basis |
|---|---|---|
| Privileged tasks: `<base>-privileged`, where `<base>` is `<benchmark>-<family>-i<NN>` (`metaworldplus-<env>-i00`, `kinder-<family>-i00`, `humanoidbench-<category>-<task>-i00`) or an upstream name kept as is (`robotwin_2_0_<task>`, `dextoolbench_<cat>_<obj>_<task>`, `mujoco_playground_<env>`) | MUST | suffix [CI] |
| Standard tasks: `<base>-standard`, sharing the privileged twin's frozen instance and `instance_seed`, and its default and allowed seeds (§2.13), where the task has a twin (a task without one, §2.15, carries its own frozen instance in its sidecar) | MUST | suffix [CI]; shared instance [current] |
| Standard-realtime tasks: `<base>-standard-realtime`, sharing the privileged twin's frozen instance and `instance_seed`, and its default and allowed seeds (§2.13), where the task has a twin; its twin is `<base>-privileged` (which modes a benchmark ships: §2.15) | MAY (the mode) / MUST (the name) | suffix and instance [CI] [new] (v1.1) |
| Versions or durations in task names (`-v3-`, `-60min-`) | MUST NOT | [new] — versions are dataset digests |

### 2.3 `task.toml`
| Item | Level | Basis |
|---|---|---|
| `schema_version = "1.3"`; `[task].name = "robot-coding-bench/<folder>"` | MUST | [current]; name [CI] |
| `[task].description`, `authors`, `keywords` | SHOULD | [current] |
| `[metadata]`: `author_name`, `task_type ∈ {trajectory, policy}`, `simulator`, `robot`, `family`, `mode ∈ {privileged, standard, standard-realtime}`, `expert_time_estimate_hours` | MUST | [CI] |
| `tier` | MUST NOT | [CI] (`privileged` → `mode = "privileged"`, `perception` → `mode = "standard"`) |
| Standard tasks: `protocol = "eai-standard/2.1"`, `"eai-standard/2.2"` or `"eai-standard/2.4"`; standard-realtime tasks: `protocol = "eai-standard/2.3"`; privileged tasks: no `protocol` | MUST | [CI] |
| `oracle ∈ {full, partial, none}`; `oracle_evidence` when not `full` | MUST | [CI] |
| `simulator`, `robot` from the vocabularies in [`TAXONOMY.md`](TAXONOMY.md) (extend by PR) | MUST | [current]; CI check [new] |
| `instance_seed` (where present, equal to the default seed, §2.13); benchmark-specific fields registered in TAXONOMY | MAY | [current] |
| `[metadata.seeds]`: `default`, `allowed`, `oracle` (§2.13) | MUST | [CI] (2026-10-13) |
| `[metadata] dynamics ∈ {static, dynamic}` (§2.14), from `scripts/task_dynamics.toml` | MUST | [CI] (2026-10-14) |
| Top-level `artifacts` includes `"/app/output/"` | MUST | [CI] |
| `[agent].timeout_sec` set, a whole number of seconds ≤ 14400 (no exception, below); 3600 unless justified (one number within a benchmark and mode unless the pull request says why); set by the task's author or its benchmark's generator, the task's own and only statement of the number, from which `scripts/task_conventions.py` renders the rest (§2.12) | MUST / SHOULD / MUST | [CI] / [new] / [CI] |
| `[verifier].environment_mode = "separate"` | MUST | [CI] |
| `[verifier].timeout_sec`, `[environment]` `cpus` / `memory_mb` / `build_timeout_sec` | SHOULD | [current] |
| `[metadata.resources]`: the minimum compute (§2.9) | MUST | [CI] (v1.1.4) |
| `[metadata.resources.limits]` and `[metadata.resources.caps]`: the agent phase's resource limits and the docker caps (§2.10) | MUST | [CI] (v1.1.5) |
| `[environment].gpus` (unsupported by Harbor's local Docker sandbox; see §2.4) | MUST NOT | [current] |

**Agent budget cap.** `[agent].timeout_sec` is at most 14400 s in every task; no benchmark is excepted
(`ci_checks/check-task-fields.sh` and `ci_checks/check-cutoffs.py`, `scripts/task_conventions.py`
`CUTOFF_CAP`). An exception would be an owner decision, recorded here, in `docs/benchmarks/<bench>.md` and in both
checks; its budget would be uniform within the benchmark, in both modes, and its results compared only with results under the same budget (D8). A
standard sidecar's wall clock (`RCB_WALL_CLOCK_S`, `/spec.budget.wall_clock_s`) equals the task's cutoff, in every
benchmark (§2.12) [CI]. The token budget (D10) is unchanged. (RoboTangle's 21600 s exception, 2026-10-08, issue #87,
ended with its tasks on 2026-10-13: RoboARC replaced them at 10800 s, `docs/CUTOFFS.md`.)

### 2.4 Images, registry, GPU

A base image is defined by `images/<name>/Dockerfile` and tagged `<registry>/eai-<name>:<images/<name>/VERSION>`; `<name>` is
usually the benchmark (`eai-robocasa365`) or the simulator stack several benchmarks share (`eai-mujoco`). `scripts/build_images.sh` builds every image as
`ghcr.io/mll-lab-nu/eai-<name>` and `scripts/push_images.sh` pushes all but the `BUILD_ONLY` ones. Tasks reference it by tag:
`environment/Dockerfile` and `tests/Dockerfile` `FROM` it, and the standard-mode `sim` service uses it as `image:`.
Harbor builds the task images locally from the task directory on every run; only base images are pulled.

| Item | Level | Basis |
|---|---|---|
| Base images at `ghcr.io/mll-lab-nu/eai-<name>:<ver>`, anonymously pullable, unless `BUILD_ONLY` | MUST | [new] (registry: [CI]) |
| Versions in `images/<name>/VERSION`; the global `images/VERSION` is not changed (removed after migration) | MUST | [new] |
| Images that cannot be published (e.g. licensed simulators): `images/<name>/BUILD_ONLY` plus local build instructions (licences, data); never public, though maintainers may keep a private package for org members | MUST | [new] |
| Every `FROM` and `image:` pinned to a tag or `@sha256` digest | MUST | [CI] |
| Sidecars built with `build:` | MUST NOT | [new] |
| Dependencies pinned; no downloads during verification | MUST | no downloads: [current]; pinning: [new] (standard-mode client images and the MuJoCo image install unpinned pip packages today, §7) |
| Within a benchmark, one base image and one version: privileged `environment` and `tests`, and the standard `sim` service, use the same `eai-<name>:<ver>` | MUST | [new] |
| Different benchmarks on the same simulator (same `simulator` value) using different images or versions | MAY | [new] (D5; e.g. `robosuite` for RoboCasa, RoboCasa365 and RoboCasa-GR1) |
| Standard-mode agent containers and verifiers share one client base image pinned by digest | MUST | [new] |
| Merging different simulator stacks into one image only when their dependency versions are identical (frozen-instance hashes depend on them) | MUST | [new] |
| GPU: an NVIDIA device reservation (`count: 1`) in compose on `main` (privileged) or `sim` (standard); in `tests/docker-compose.yaml` too if replay needs it | MUST | [current] |
| `device_ids` pinning a specific GPU; fixed-name global volumes | MUST NOT | [new] |

### 2.5 `instruction.md`
| Item | Level | Basis |
|---|---|---|
| States the deliverable under `/app/output/` | MUST | [CI] |
| Mentions `/tests/` | MUST NOT | [CI] |
| States every convention the agent cannot infer: frames, quaternion order, units, action layout, tool or client usage | MUST | [current] |
| Ends with `## Time limit` (§2.12), the last thing the agent reads: the time limit in seconds and the request not to cheat, in the same words in every task, then what the cutoff means in the task's mode; `scripts/task_conventions.py` writes it from the task's `[agent] timeout_sec` and it is never edited by hand | MUST | [CI] (2026-10-11, at the end since 2026-10-12; before: SHOULD "states the time budget", in each benchmark's own words) |
| States the agent's time limit a second time as a duration ("your wall-clock budget is 90 min (5400 s)", "You have 60 minutes", "Time limit: one hour"). The task's own text says "the time limit (`## Time limit`)" | MUST NOT | [CI] (the wordings in use before 2026-10-11: `ci_checks/check-cutoffs.py` `OTHER_LIMIT`) |
| Says what the cutoff means for this benchmark where the mode's paragraph does not: a simulator's start-up cost, what the service's `time_left_s` counts from, a service that ends the episode on its own clock (RoboARC), a match that must be over in time; and tells the agent not to stop early where a first deliverable can be improved | SHOULD | [current] |
| Gives the success predicate's exact parameters | MAY | [current] |
| World-frame quantities (coordinates, table height): decided per benchmark, consistent within it, documented | MUST | [new] |
| Written by a human | SHOULD | [current] |
| Ends with three sections `scripts/task_conventions.py` writes, in this order: `## External material` (§2.11: the same words in every task), `## Resource limits`, rendered from `[metadata.resources.limits]` (§2.10), and `## Time limit` (§2.12) | MUST | [CI] (v1.1.5; 2026-10-10; 2026-10-12) |
| Tells the agent that it needs to download something, or that it may download anything but packages from the registries | MUST NOT | [new] (§2.11: packages install, nothing else is reachable) |

### 2.6 Verifier
| Item | Level | Basis |
|---|---|---|
| Runs in its own sandbox (separate mode) with only the declared artifacts | MUST | [CI] |
| `/logs/verifier/reward.txt` is `1` or `0` (partial progress goes to `reward.json` as `progress`); `/logs/verifier/reward.json` has numeric fields only | MUST | [current] |
| Same verdict in a fresh process on the same inputs | MUST | [current] |
| The verifier needs network access | MUST NOT | [current] |
| Standard-mode verifiers set `network_mode = "no-network"`; privileged-mode verifiers too | MUST / SHOULD | [current] / [new] |
| Verdict written before videos are rendered; videos never affect it | SHOULD | [current] |
| A human-viewable `replay.mp4` (`video_rendered = 1`) | SHOULD | [current] |
| `test.sh` first clears `/logs/verifier` (`rm -rf /logs/verifier/*`); named volumes crossing the trust boundary are named `*_trusted` | MUST | clearing [CI]; volume names [CI] |
| Before the grader, `test.sh` removes from `/app/output` what is not the agent's own regular file or directory: symbolic links that leave it or do not end at a regular file, FIFOs, devices (`python3 /tests/rcb_limits.py sanitize /app/output`, a generated line); a session log over 64 MiB is cut. The agent's files are collected as they are, links included, and a grader opens some by name (a log linked to `/dev/zero` left a trial without a verdict) | MUST | [CI] (v1.2-rc) |
| The agent's container mounts no `*_trusted` volume in any spelling (short, long, inline, `volumes_from`), binds no path of the task or the host (only a directory the runner names through an environment variable), and no service widens its container (`privileged`, `cap_add`, `devices`, the host's namespaces); a sidecar publishes no port; standard modes: the evidence artifacts and a collect hook are a sidecar's; an allowlist is the one of `scripts/set_agent_egress.py`. `ci_checks/check-ci-selftest.py` breaks real tasks in each of these ways and requires the checks to fail | MUST | [CI] (v1.2-rc) |

`reward.json` field names (use these whenever the concept applies; no synonyms):

| Field | Level | Meaning |
|---|---|---|
| `success` | MUST | 1 iff the deliverable completes the task |
| `deterministic` | MUST (trajectory tasks) | repeated verification agreed |
| `infra_error` | MUST (standard) / MAY | infrastructure failure, not the agent's |
| `sim_error` | SHOULD (standard) | the episode ended with a simulator error (`reason = "error"`, §4.6) |
| `grader_error`, `missing_trajectory` / `missing_log` | SHOULD | diagnosable failure modes |
| `resource_enforced`, `limits_violation_observed`, `peak_gpu_memory_gb`, `peak_memory_gb`, `peak_processes`, `peak_disk_gb`, `resource_monitor_missing`, `resource_emergency_kills`, `resource_oom_kills`, `resource_host_oom_kills`, `resource_service_oom_kills` | MUST (from v1.2) | the monitor's mode (`RCB_LIMITS_ENFORCE`), whether a limit was exceeded (`over_<metric> = 1` for each), the scope's peaks, a missing or unusable record, the processes the monitor killed to protect the host, and the kernel's out-of-memory kills in the record: in the scope at the container's own memory cap (the violation `over_oom`), in the scope by another OOM killer (the host's), in a benchmark-owned service (§2.10). Written by the verifier step in `tests/test.sh`'s exit trap: a verifier killed at its timeout leaves them out, and such a trial has no verdict anyway |
| `resource_limit_exceeded`, `success_before_limits` | MUST (from v1.2, enforcement on) | 1 iff an enforced limit was exceeded, then `success = 0`; the grader's verdict before it (§2.10). `success_before_limits` is also written whenever the resource step itself declares the trial not a result (`infra_error = 1` by the switch, an unusable record or a host OOM kill with enforcement on): it then sets `success = 0` and `reward.txt` 0, so that no `success = 1` stands beside `infra_error = 1` |
| `resource_service_oom`, `resource_host_oom` | MUST (from v1.2-rc, when it happens) | `resource_service_oom = 1` (both settings of the switch): the kernel OOM-killed a benchmark-owned service (the `sim` sidecar, RoboPaint's `scorer`) and the grader's verdict is not a success, then `infra_error = 1`; `resource_host_oom = 1` (enforcement on): a process in the scope was killed by an OOM killer that is not its container's own cap, then `infra_error = 1` (§2.10) |
| `resource_switch_error`, `resource_step_error` | MUST (from v1.2, when it happens) | `RCB_LIMITS_ENFORCE` was neither `0`/`1`/`true`/`false` (then `infra_error = 1`); the verifier's resource step itself failed (then `resource_monitor_missing = 1`, and `infra_error = 1` when enforcement was asked for) (§2.10) |
| `n_actions`, `sim_steps` (or `control_steps`), `video_rendered` | SHOULD | size of the deliverable, simulation cost, video present |
| `final_reward`, `progress`, `live_success`, `replay_success`, `live_video`, `live_frames`, `sim_startups`, `finalized`, `elapsed_s`, `agent_*` | MAY | when the concept exists |

### 2.7 Reference solutions, oracle, nop
| Item | Level | Basis |
|---|---|---|
| Reference solutions only under `solution/` (mounted for the oracle agent only) | MUST | [current] |
| A solution, or a pointer to one, anywhere the agent can reach (task image, base image, tooling, docs in the container). A pointer is anything that locates the solution of this task: a URL, a dataset or file name, a demonstration or episode id, the name of the upstream expert that produced the reference. Provenance is kept in `scripts/<bench>/` and the README, never in a file under `environment/` the agent reads | MUST NOT | [CI] for the task's own files (`ci_checks/check-agent-pointers.py`: hosts of code, data and video, `*_url` keys, dataset and demonstration file names, keys that name a demonstration or episode (`"demo": ...`, `episode_id`); text files and the string members of `.npz` archives, since 2026-10-14 (board 0105: DexJoCo's `instance.npz` named its demonstration)); [current] for images, reviewed when they are built. Upstream documentation inside a simulator image that names the benchmark's public datasets or checkpoints is not removed file by file: the allowlist of §2.11 makes them unreachable. Open (2026-10-10): RoboTangle's image; its tasks were removed on 2026-10-13, and RoboARC's image is built FROM it (docs/benchmarks/roboarc.md) |
| Upstream experts scrubbed from images (e.g. RoboTwin `play_once`) | MUST | [current] |
| Agent egress allowlisted in `task.toml` (the model APIs and, since 2026-10-11, the package registries), in every task (§2.11) | MUST | [CI] (2026-10-10; until then a SHOULD "when a solution is publicly downloadable", and RoboTwin, MuJoCo Playground's four Aloha / Panda pairs, RoboWits, RoboLab, BEHAVIOR-1K and RoboTangle were open) |
| `nop` scores 0 | MUST | [current] |
| `oracle = "full"`: the oracle scores 1 (on each seed in `seeds.oracle`, §2.13) | MUST | [current] |
| `oracle = "partial"` or `"none"`: `oracle_evidence` and **human review** | MUST | [new] |

**Human review** (any task whose `oracle` is not `full`): the PR is labelled `needs-human-review` and needs an approval
from a maintainer other than the author. Generated tasks are reviewed per family (same generator and predicate): at
least two instances per family, at least one with a positive example. The author provides a table *family → positive
example → nop result → predicate summary*. The reviewer checks:
1. **Solvable** — a positive example (a successful model trial, an upstream policy or RL rollout, or a hand-built
   trajectory or state) that the verifier scores 1.
2. **Correct predicate** — the grader matches the instruction and cannot be satisfied trivially (true at the initial
   state, or for any action).
3. **Negative control** — `nop` scores 0; ideally a wrong trajectory scores 0 too.
4. **Determinism** — the positive example replays to the same verdict twice in fresh processes.
5. **Record** — reviewer, date, instances and evidence in the review comment; the task README's Verification section
   says "no oracle; human review in PR #N".

### 2.8 Identity and immutability
| Item | Level | Basis |
|---|---|---|
| Carries the digest of its current files in `tasks/<task>/DIGEST` (one line `sha256:<hex>`, the digest Harbor publishes it under; written last by `scripts/task_conventions.py` `normalize`, so every generator and every normalize run refresh it; after a hand edit run `python3 scripts/task_conventions.py tasks/<task>`; `ci_checks/check-dataset-manifest.sh` recomputes it). The release manifest `tasks/dataset.toml` is generated from the DIGEST files (`scripts/dataset_manifest.py write`) and not committed, so pull requests that change different tasks share no file (2026-10-14, board 0117); the task list (`TASKS.md`, `tasks.json`, with the manifest) is generated after every merge to `main` and pushed to the branch `task-list`, and attached to a release (2026-10-14, board 0120) | MUST | [CI] |
| A published task's `environment/` and `tests/` inputs are immutable; a change is a new task. One line is not such an input: `RCB_WALL_CLOCK_S` of the `sim` service in `environment/docker-compose.yaml`, which mirrors the task's `[agent] timeout_sec` (§2.12) and is rewritten from it by `normalize`; it changes what the service reports, not the scene, the instance or the success rule. Nothing else under `environment/` or `tests/` follows the cutoff | MUST | [current]; the one line: [CI] (`ci_checks/check-cutoffs.py`) |
| Fixes to existing tasks add a Change Log entry to the task README with before/after runs | SHOULD | [new] |
| A change of a task's cutoff, or of the text `scripts/task_conventions.py` owns in every instruction (`## External material`, `## Resource limits`, `## Time limit`), changes the task in place: same name and instance, new digest. A cutoff change is recorded by its pull request (old -> new, who decided, why; §2.12) and the tasks' git history (until 2026-10-14: the cutoff table's `[[history]]`, kept in `docs/CUTOFFS.md`), which stand for the per-task Change Log entry; a change of the shared text in §7. Results under another cutoff are reported separately (D8) | MUST (the record) | [new] (2026-10-11; precedents: #155 RoboDojo 5400 → 3600 s, #150 / #151) |

### 2.9 Compute resources (v1.1.4)

Every task states the smallest allocation it runs on, so that a scheduler can pack trials onto machines and a
contributor knows what hardware a task needs. The values live in `task.toml` under `[metadata.resources]` (Harbor keeps
`[metadata]` free-form); the README's `## Compute resources` table is rendered from them by
`scripts/task_conventions.py`.

| Item | Level | Basis |
|---|---|---|
| `[metadata.resources]` with every field below (`recommended_gpu` may be left out when `gpu_required = false`) | MUST | [CI] |
| README `## Compute resources`, after `## Verification`, equal to what `scripts/task_conventions.py` renders from `[metadata.resources]` | MUST | [CI] |
| `gpu_required = true` exactly when `environment/docker-compose.yaml` reserves an NVIDIA GPU (§2.4); then `min_gpu_memory_gb > 0` and `gpu_class` is not `"none"`; with `gpu_required = false`, `min_gpu_memory_gb = 0` and `gpu_class = "none"` | MUST | [CI] |
| `verifier_min_gpu_memory_gb > 0` exactly when a GPU reaches the verifier phase (`tests/docker-compose.yaml`, or a `[[verifier.collect]]` hook on a GPU sidecar) | MUST | [CI] |
| A minimum never exceeds a cap that bounds the whole phase: `[environment]` `cpus` / `memory_mb` for a task without a sidecar, `[verifier.environment]` for a verifier without a collect hook | MUST | [CI] |
| Values derived from measured peaks as below; `measured` says from what (trials, hosts, dates), or `"author estimate"` until measured | SHOULD | [new] |
| Values uniform within a benchmark, or within a family where its families differ (e.g. particle simulation, two cameras) | SHOULD | [new] |

| Field | Type | Meaning |
|---|---|---|
| `min_cpus` | float | CPU cores the agent phase needs at once: every container of the trial (privileged: the agent's container with the simulator and its helpers; standard modes: the agent's container plus the `sim` sidecar(s)) |
| `min_memory_gb` | float | memory (GB) the agent phase needs at its peak, same scope |
| `min_gpu_memory_gb` | float | GPU memory (GB) the agent phase holds at its peak; 0 without a GPU |
| `gpu_required` | bool | the task does not start without an NVIDIA GPU |
| `gpu_class` | string | `"none"`; `"any"` (any CUDA GPU with EGL / Vulkan: MuJoCo, SAPIEN, ManiSkill, Genesis rendering); `"rtx"` (an RTX-class GPU with ray-tracing cores: Isaac Sim / Omniverse; data-centre cards without them, such as A100 or H100, do not run it) |
| `recommended_gpu` | string or list | a card the task is known to run well on, e.g. `"L40S 48GB"`, `"RTX 4090 24GB / L4 24GB"` |
| `verifier_min_cpus`, `verifier_min_memory_gb`, `verifier_min_gpu_memory_gb` | float | the same for the verifier phase, which runs after the agent phase: the verifier's container plus, in standard modes, the replay the collect hook runs in the sidecar |
| `measured` | string | provenance of the values |

**Minimum** means the smallest allocation on which one trial, alone on the machine, runs correctly: no out-of-memory
kill, no start-up watchdog or timeout caused by CPU starvation, the same verdict. It is not the `[environment]` cap
(an upper bound, often much larger), and not what makes a trial fast; an agent that starts extra simulator processes
needs more, and a scheduler adds its own margin. How to derive it:
- **memory**: the largest sum over the phase's containers of their cgroup `anon + shmem` (or `docker stats` usage, which
  also counts page cache and so overstates), × 1.2, rounded up to a whole GB;
- **GPU memory**: the largest sum over the phase's processes in `nvidia-smi`, × 1.15, rounded up to 0.5 GB. Isaac Sim
  sizes its pools to the card, so its value is the peak on the smallest card class the task ran on (24 GB);
- **CPU**: the sustained use (the 90th percentile of 30-second samples) summed over the containers, in cores, rounded up,
  and at least one core per simulator process plus one for the agent;
- over several trials (oracle or agent) where there are any; `measured` names them.

Values come from `scripts/task_resources.toml`: rules matched against the task directory name, applied in order (a later
rule overrides an earlier one's keys), written into `task.toml` by `scripts/task_conventions.py` (`normalize`, which
every generator runs). A task that no rule matches keeps the block its generator or author wrote. A new benchmark adds
its rule in its shared-files pull request (D6), or its generator writes the block itself. `ci_checks/check-resources.py`
checks the fields, the consistency rules above and the README.

### 2.10 Resource limits (v1.1.5; judged inside the trial from v1.2)

A trial must not take more than its share of the machine: an agent that starts extra simulators until the GPU runs out of
memory, fills the disk, or forks without end harms every other trial on the host. Every task therefore states **limits**,
the most the agent phase may use. They are part of the task contract and shown to the agent in `instruction.md`. When
enforcement is on, exceeding one is the agent's failure, graded like a wrong deliverable, not an infrastructure error.
They sit between the minimums of §2.9 (what a trial needs) and the docker caps (what the kernel allows). All sizes are
GiB (`memory_mb / 1024`, `nvidia-smi` MiB / 1024).

| Item | Level | Basis |
|---|---|---|
| `[metadata.resources.limits]` and `[metadata.resources.caps]` with every field below | MUST | [CI] (v1.1.5) |
| `scope = "trial"` in privileged mode, `"agent"` in standard and standard-realtime modes | MUST | [CI] |
| `instruction.md` has `## Resource limits`, equal to what `scripts/task_conventions.py` renders from the limits and `[environment].cpus`, after `## External material` and just before the closing `## Time limit` (§2.12; until 2026-10-12 it was the last section) | MUST | [CI] |
| Relations: memory `min ≤ limit` (scope trial) and GPU memory `min ≤ limit` (scope trial), `max_gpu_memory_gb > 0` only where the limited containers have a GPU; `trial_max_* ≥ min_*` and `≥` the limit (scope trial: equal, unless the task has a benchmark-owned, observe-only service); the scope's memory caps `≥ 1.2 × max_memory_gb` and `≥ max_memory_gb + 2`; `pids ≥ 8 × max_processes` for the services the limits bind; a cap for every compose service (cache helpers `rcb_*` aside); every declared cap is the cap docker applies: `caps.main.cpus = [environment].cpus`, `caps.main.memory_gb = [environment].memory_mb / 1024` (Harbor writes main's caps from `[environment]`), every other value equals the compose file's `cpus` / `mem_limit` / `pids_limit` of that service, and the relations are checked on those applied values; scope agent: `max_memory_gb ≤ [environment].memory_mb / 1024`; no cap below the task's own minimums: `min_cpus ≤` the CPU caps of all services together, and where the verifier phase runs in a sidecar (a collect hook replays there) `verifier_min_memory_gb ≤` the memory caps of those sidecars | MUST | [CI] |
| `measured` says what the values rest on; limits sit with a generous margin above measured peaks (e.g. `max(1.5 × peak, peak + 4 GiB)`), so that no past normal trial exceeds them; values without data say so | MUST / SHOULD | [new] |
| The oracle passes within the limits | MUST | from v1.2 (checked by the calibration batch) |
| Enforcement inside the Harbor trial (below): caps on every service, the monitor sidecar, the verifier's check, the switch | MUST | from v1.2 |
| Values uniform within a benchmark and mode (or family, where the minimums differ by family) | SHOULD | [new] |

`[metadata.resources.limits]`:

| Field | Type | Meaning |
|---|---|---|
| `scope` | string | whom the limits bind: `"trial"` = every container the agent drives (privileged: `main` and any service it starts or controls; the agent drives the simulators itself, so their use is the agent's). A service that is the benchmark's own and outside the agent's control (today RoboPaint's `scorer`; the list is `BENCHMARK_SERVICES` in `scripts/rcb_monitor/inject.py`) is observed and recorded only, like the monitor never part of the scope; `"agent"` = the agent's container (`main`) only (standard modes: the `sim` sidecar is the benchmark's service, outside the agent's control; it is recorded, never a failure) |
| `max_gpu_memory_gb` | float | GPU memory of the scope's processes, summed (NVML per process, compute and graphics; what a process reserves counts, e.g. JAX's preallocation); 0 = the scope has no GPU |
| `max_memory_gb` | float | memory of the scope's containers, summed (cgroup `anon + shmem`; without a cgroup, PSS) |
| `max_processes` | int | processes (thread groups, not threads) in the scope; a zombie counts in its parent's container, a process whose first thread has exited counts like any other |
| `max_disk_gb` | float | growth of the files under `disk_paths` in the agent's container since the baseline: the monitor's first complete measurement after it first saw the container, i.e. before the harness installs the agent, so that install (a few hundred MB under `/root`) counts and the limits leave room for it |
| `disk_paths`, `disk_exclude` | list of strings | absolute paths measured / skipped (today `["/app", "/tmp", "/root"]` / `[]`). Only these are measured: files written elsewhere in the container (`/opt`, `/var`, …) and other mounts are not counted; `/dev/shm` is memory (`shmem`) |
| `sustain_sec`, `window_sec` | float | a violation: above a limit for at least `sustain_sec` in total within any `window_sec` (60 / 120 s); disk: two measurements in a row; gaps in the record never count against the agent |
| `trial_max_gpu_memory_gb`, `trial_max_memory_gb` | float | expected peak of the whole trial, every container (sidecars and benchmark-owned services too), declared in both modes for schedulers; not a failure condition |
| `measured` | string | provenance of the limits |

`[metadata.resources.caps]`: one inline table per compose service, `{ cpus, memory_gb, pids }`, the docker caps
(`cpus`, `mem_limit`, `pids_limit`) the v1.2 compose files apply; `main`'s CPU and memory caps are Harbor's
`[environment]` values, so `scripts/task_conventions.py` sets `[environment].memory_mb = caps.main.memory_gb × 1024`
(v1.2: the kernel's cap sits above the limit, so that the monitor sees a violation before the OOM killer acts; a
scheduler sizes a trial by §2.9's minimums and `trial_max_*`, not by this cap). A service that sets a cap itself keeps
it, and the declared value is that one. CPU is never a limit, only a cap: it throttles and is stated in the paragraph.
An out-of-memory kill by the kernel in a container in scope, at that container's own memory cap, is a violation.

**A CPU cap above the host's CPU count means the host's count.** Docker refuses to create a container whose `cpus`
exceeds the machine's ("range of CPUs is from 0.01 to N"), so a task whose cap is 12 or 16 does not start on an
8-CPU host although its `min_cpus` is 6 or 8. A runner MUST therefore clamp every CPU cap (`[environment].cpus` and
each compose service's `cpus`) to the host's CPU count in the copy of the task it runs (`scripts/clamp_cpus.py`, which
`scripts/run_agent_batch.sh` applies to a job's own copy); the task's files keep their
values (a cap is not lowered for small hosts, and clamping does not change the task: a container can never use more
CPUs than the host has). A host that has `min_cpus` (§2.9) still gives the trial its minimum after clamping, because
`min_cpus` never exceeds the CPU caps of all services together [CI]. Memory and pids caps are never clamped.

**The switch.** `RCB_LIMITS_ENFORCE`, a run-time environment variable read by the monitor service (compose default
`${RCB_LIMITS_ENFORCE:-0}`, so turning it on does not change the task digest); `1` / `true` or `0` / `false`:
- `1` (hard): once the monitor confirms a violation, it kills the scope's processes (not the containers' PID 1) and the
  verifier fails the trial: `reward.txt` = 0, `success = 0`, `success_before_limits` = the grader's verdict,
  `resource_limit_exceeded = 1`; never retried.
- `0` (default): the monitor observes and records only, and kills nothing; the verifier reports the peaks and any
  violation (`limits_violation_observed = 1`, details in `/logs/verifier/resource_limits.json`) and does not change the
  verdict (`reward.txt`, `success`, `reward`); it sets `infra_error` in one case only, the same in both settings: a
  benchmark-owned service was killed for memory and the episode did not end in a success (below). A missing or unusable record is then only reported (`resource_monitor_missing = 1`), not an infrastructure
  error (owner: off means observe only), so a host whose runtime cannot run the monitor still produces results.
- any other value is an error, never a silent "off": the monitor kills nothing and records a fatal event, and the
  verifier reports `infra_error = 1`, `resource_switch_error = 1` (not a result; `success = 0`, the grader's verdict
  kept in `success_before_limits`).

The monitor writes the mode it ran in into its record; the verifier takes it from there (`resource_enforced`).

**What fails a trial** (enforcement on) is exactly: a limit exceeded for `sustain_sec` within `window_sec` (disk: two
measurements in a row), or a kernel out-of-memory kill in the scope at the container's own memory cap. Nothing else
does, and nothing another trial does on the same host or card can.

**Out-of-memory kills.** The kernel counts, per container (cgroup v2 `memory.events`), `oom_kill`: processes killed by
any OOM killer, and `oom`: times the container's memory reached its own cap. The monitor records every kill as an
`oom` event with its cause: `"cap"` when the container's own `oom` counter rose with the kill (or within 10 s before
it), else `"host"`: the host ran out of memory, or an enclosing cgroup did (a scheduler's job limit), which is other
trials' or the machine's doing. It reads the counters many times a second in a thread of its own, because a
container whose main process is killed is gone, and restarted with new counters, within milliseconds, and until the
record is sealed (the first collect hook): what happens to a sidecar in the hooks after it, its replays, is the
grader's to judge from the hook's own evidence. Then:
- a `cap` kill in the scope is the violation above (`over_oom = 1`, `resource_oom_kills`);
- a `host` kill in the scope is never a violation. With enforcement on the trial is not a result
  (`infra_error = 1`, `resource_host_oom = 1`, `success = 0` with the grader's verdict in `success_before_limits`); with
  enforcement off it is reported (`resource_host_oom_kills`) and the verdict stands;
- a kill in a **benchmark-owned service** (the `sim` sidecar of standard modes, RoboPaint's `scorer`; whatever the
  cause: its docker cap is the benchmark's own setting) is recorded (`resource_service_oom_kills`), never a failure.
  If the grader's verdict is not a success, the trial is not a result: `infra_error = 1`, `resource_service_oom = 1`,
  in both settings of the switch (the caps are applied in both). The service layers attribute a crash by whether a
  call was in progress, not by its cause, so a simulator killed at its cap inside three calls would otherwise end as
  the agent's `sim_crashed_on_call`. A success stands: the service recovered and the grader accepted the episode.
  Where the monitor did not run (no record), nothing is known and nothing changes.

**Host protection** (enforcement on only). Two immediate actions keep a runaway trial from harming the machine before
the sustained rule can act. Each is an `emergency_kill` event in the record, counted in `resource_emergency_kills`,
shown to the agent in `usage.json`, and **never a violation by itself**: the trial goes on and fails only by the rule
above. Both compare the trial's own use with its own declared values, never with the state of a card or host it shares.
- GPU memory of the scope above 1.5 × `max_gpu_memory_gb` at one sample: the monitor kills the scope's process that
  holds the most GPU memory (e.g. a JAX process that preallocated most of a large card; the agent can start it again
  with a smaller reservation). The paragraph says so.
- Where the container runtime applies no kernel memory cap (rootless podman without cgroups), the monitor stands in for
  it: when the scope's memory exceeds the sum of its declared memory caps, it kills the scope's largest process.

**Enforcement (required from v1.2).** Violations are judged by the Harbor trial itself, inside the task, so that every
harness that runs the task applies the same rule, not by a scheduler or resource pool outside it. A trial that a pool
kills to protect its host is an operations abort (`killed_by_pool`, infrastructure), not a graded result.
- docker caps on every compose service (`[metadata.resources.caps]`);
- a monitor sidecar `rcb_monitor`, provided by the task and outside the agent's container, samples GPU memory, memory,
  processes, disk and out-of-memory kills of the scope every few seconds into its own record (format `rcb-monitor/1`),
  which the agent can neither reach nor alter, and seals it in the first collect hook. It writes the current values to
  `/run/rcb-limits/usage.json` in the agent's container;
- the verifier recomputes violations from the raw samples with its own copy of the limits (`tests/`), writes the
  `reward.json` fields of §2.6 and `/logs/verifier/resource_limits.json`. A missing, unsealed, fatal or mostly empty
  record is reported as `resource_monitor_missing = 1`; with enforcement on it is also an infrastructure error
  (`infra_error = 1`, not a result), with enforcement off it changes nothing else.

What the record can and cannot say:
- gaps never count against the agent; more than 10 % of the agent phase unobserved makes the record unusable;
- disk: only a complete walk of `disk_paths` is a measurement and only such a walk sets the baseline (kept across a
  restart of the monitor). A walk that cannot finish (the container went away, or the tree is too large to read in
  5 minutes) is a gap (`disk_partial` event); its partial sum is a lower bound, which can show that the limit is
  exceeded but never that it is not;
- GPU memory: when NVML does not report the per-process memory of processes in scope (MIG, vGPU), the sample is marked
  `gpu_unmeasured`, never counted as a silent 0; more than 10 % such samples on a task with a GPU limit make the record
  unusable (the GPU limit was not measured).

v1.1.5 declared the limits and showed them to the agent; v1.2 judges them, and the paragraph says "from protocol v1.2
on". The values live in `scripts/task_resources.toml` (`[[limit]]` and `[[cap]]` rules, matched like
the minimums' `[[rule]]`s, with the derivation) and are written by `scripts/task_conventions.py`, which also renders the
paragraph and a line of the README's `## Compute resources`; `ci_checks/check-resources.py` checks them.

**Rendered paragraph** (RoboLab, privileged; standard modes say "Limits for your agent environment, your own container
only (the simulator in the `sim` service is the benchmark's and does not count)"):

> ## Resource limits
> Limits for the whole trial, all its processes together (every simulator you start included): at most **24 GiB of GPU
> memory**, **24 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU
> memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may
> be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process
> killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your
> container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on
> and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to
> protect the machine; that alone does not fail the trial. CPU is capped at 8 cores for your container; the cap only
> slows you down.

(The sentence about 1.5 times the GPU-memory limit is rendered only where the limits include GPU memory.)

### 2.11 External material and the network (2026-10-10, relaxed 2026-10-11 and 2026-10-14)
**Baseline and stricter task rules (owner, 2026-10-14).** The `## External material` words below are the baseline every
task carries. A task MAY add stricter requirements of its own on top of them, never looser ones: `[metadata.honour]
stricter = "..."` in its `task.toml`, which `normalize` renders right after the baseline as "Additional rules for this
task (stricter than the above): ...". Benchmark-level openings that predate this (the open-network RoboOlympics
families) stay as documented below.
An agent solves a task itself. It may install the packages it needs and read whatever is installed in its container; it should not look the task's solution up. This is
an honour rule (owner, 2026-10-11: "a soft constraint, a gentlemen's agreement"), backed by a network that reaches the
model API and the package registries and not GitHub, Hugging Face or the general web, where most of the benchmarks'
sources, demonstrations and trained policies are published (a few are on PyPI too: the table below). History: until 2026-10-10 six benchmarks left the agent's egress open and three instructions
stated a rule; trials downloaded upstream sources, a reference solution, a recorded demonstration, robot models and
pretrained policies, from their own shell or through tools of the model's account. #150 closed the egress to the model
APIs and forbade every download and install, with "a result obtained with external material is void"; the owner found
that too strict: installing a package or trying a tool is part of what a model can do. On 2026-10-14 (owner, board 0107
E4) reading the installed environment, the simulator's and the benchmark's own source included, became explicitly
allowed: the rule forbids only searching the web for, or downloading, a ready-made solution. What the image ships is
therefore fair game, which is why it must hold no answer (§2.7, [LEAKAGE.md](LEAKAGE.md)).

| Item | Level | Basis |
|---|---|---|
| The agent may install packages (pip, apt) and use them, and may read anything installed in its container, the simulator's and the benchmark's own source code included (since 2026-10-14; before, the benchmark's source was on the list below). It does not search the web for, or download, a ready-made solution to the task: published or reference solutions, recorded demonstrations, policies trained for the task | honour rule | stated in every instruction; not enforced beyond the network below |
| A trial that fetched a solution is flagged and the owner decides, case by case; there is no automatic rule that voids it. Installing a general-purpose package is never a violation, and neither is a tool call or request that was refused (an attempt: flagged for a look, nothing more) | MUST (how results are judged) | [new] |
| `[agent] network_mode = "allowlist"` in every task, `allowed_hosts` = `scripts/set_agent_egress.py` `HOSTS`, the same list in every task: the model APIs' hosts and the package registries (`PACKAGE_HOSTS`: PyPI and the Debian / Ubuntu apt archives the images' distributions use). GitHub, Hugging Face and the general web are not on it | MUST | [CI] |
| The list is the one switch: what agents reach changes by editing it there (and a run without any restriction is `set_agent_egress.py public` on a copy of the tasks, docs/RUNNING.md) | MUST | [new] |
| What the task itself needs at run time (assets, robot models, the tooling's packages, caches) is in its image or the task directory; a task that needs a download during the agent phase does not conform | MUST | [current] (of the six benchmarks switched on 2026-10-10, RoboTwin, the Playground pairs, RoboWits, BEHAVIOR-1K and RoboLab were run with the oracle under the allowlist, both modes, with the rewards and state hashes of their open-egress runs; RoboLab needed its image to hold the materials it used to fetch, `eai-robolab:0.1.2`; RoboTangle, whose image documents that it needs no network, was not run again before its next release) |
| Every `instruction.md` states the rule in the same words under `## External material`, just before `## Resource limits`; `scripts/task_conventions.py` (`EXTERNAL_TEXT`) writes it and it is never edited in a task | MUST | [CI] |
| The harness offers the model no tool that runs outside the container (web search and fetch, account connectors and apps, remote MCP servers, plugins, image generation, cloud agents): the runner's business, not a rule for the agent (D11). Web search is the direct way to ask for an answer, and connectors are the account owner's private data | MUST for official runs | [new] |
| A run through the usage gateway narrows the agent's egress to the gateway's address and the package registries, and the gateway forwards model-API calls only (§5) | MUST for official runs | [new] (`scripts/run_agent_batch.sh` `GATEWAY=1`) |

The paragraph in every `instruction.md`:

> ## External material
> You may install packages you need (pip, apt), and you may read anything installed in your container, the
> simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web
> for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or
> policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the
> package registries (PyPI, Debian / Ubuntu archives) only.

Packages on PyPI that carry a solution. A registry is not free of answers: some distributions ship a benchmark's
scripted experts, trained policies or task sources. Nothing blocks them (owner: what cannot be forbidden is let go); a
reviewer or a runner that sees one of these names in a trial's `pip install` (directly or as a dependency) looks at what
the trial did with it. Read from the archives' file lists on 2026-10-11, by name search of the index; a redistribution
under an unrelated name would be missed.

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
ManiGuard, DexJoCo, LabUtopia, AutoBio, VLABench, RoboDojo, RoboARC, RoboOlympics, BiGym, YAMLab, Panda Dynamic Scenes
(not published at all: its environment package is this repository's `images/pandadyn/`); Isaac Sim does not install from pypi.org.
ManiGuard, DexJoCo, VLABench, RoboDojo, RoboARC, RoboOlympics, RoboFunOlympics, BiGym, YAMLab, Panda Dynamic Scenes
(not published at all: its environment package is this repository's `images/pandadyn/`), DexHand (not published at all: its scenes and tooling are this repository's
`scripts/dexhand/` and `images/dexhand/`), AM-Bench; Isaac Sim does not install from pypi.org.

**Per-benchmark exceptions.** A benchmark's agents have open egress, and its instructions say so, only by owner
decision, recorded here, in `docs/benchmarks/<bench>.md` and in the three lists that implement it (the same directory
prefix in each): `ci_checks/check-verifier-isolation.sh` `OPEN_EGRESS` (the task sets no `[agent]` network policy:
Harbor's default, open), `scripts/task_conventions.py` `EXTERNAL_OPEN` (the benchmark's own `## External material`
paragraph) and `scripts/set_agent_egress.py` `OPEN_EGRESS` (`allowlist` leaves these tasks alone). Its results are
compared only with results under the same network setting. The exception covers the benchmark's tasks that set no
`[agent]` network policy; a task of it that declares the allowlist (RoboOlympics' exported tasks, §4c) is an allowlist
task in every respect: the CI check holds it to the one host list, its instruction has the common `## External
material` paragraph, `allowlist` maintains it and the runner narrows its copy to the gateway.
- **RoboOlympics** (owner, 2026-10-11, as RoboFunOlympics, renamed 2026-10-14; `roboolympics-<family>-i<NN>`, its single-humanoid sports families, not its exported tasks (§4c),
  [`benchmarks/roboolympics.md`](benchmarks/roboolympics.md)): the agent may search for, download and use public
  tools, robot models and pretrained controllers (a published Unitree G1 walking, jumping or whole-body policy), and
  is encouraged to: finding existing work and adapting it to the robot is part of what these tasks measure. The honour
  rule that remains is not to look up a ready-made solution to the task, such as the benchmark's reference solutions
  (reading the benchmark's installed source is allowed, as everywhere since 2026-10-14). Nothing an agent can reach
  in the task or its image holds a solution, as everywhere (§2.7). An official run still goes through the usage gateway
  for the model API, and the runner leaves the rest of the egress open for these tasks. With open egress the gateway
  is no longer the only road to a model provider (the provider key is in the agent's container): its token accounting
  and its budget (§5) bind only what the harness itself sends, so these runs' usage is reported as harness-reported,
  and a trial that called a model API directly is flagged in review.

Who reaches what in a trial (Harbor's egress control puts `main` and every compose service without its own network
setting in one network namespace; §2.6 forbids such a setting on any service but the monitor):

| | While the environment starts and the harness is installed | During the agent phase |
|---|---|---|
| The agent's container (`main`) | public (Harbor's baseline: the harness is installed from its registry) | the allowlist: the model APIs' hosts and the package registries; in a run through the usage gateway, the gateway's address and the package registries (and `chatgpt.com` for Codex with a ChatGPT login, below) |
| The `sim` sidecar (standard modes) and other services of the task | public; it needs nothing: images are complete | the same allowlist as `main` (one namespace): a service that restarts mid-episode starts with that network only |
| `rcb_monitor` | none | none |
| The verifier (its own sandbox, afterwards) | | `no-network` (§2.6: MUST in the standard modes, SHOULD in privileged mode) |

The model APIs' hosts also serve what a trial does not get (a ChatGPT login's account connectors, file and
conversation endpoints, the provider's web search), and the credentials of the run are in the container. So with the
gateway on, the runner starts each job from a copy of the task whose allowlist is the gateway's address and the package
registries (`scripts/set_agent_egress.py only <hosts>`; Harbor can add a host to a task's allowlist at run time, not take
one off), and the gateway forwards
only the requests listed per provider in `scripts/usage_gateway/api_paths.json` (responses, messages, token counting,
the model list), answers every other one 403 and records it (`<trial>/gateway/usage.jsonl`
`refused = "path_not_allowed"`, `totals.json` `refused_paths`). A model request's body is forwarded as it is or not at
all: it must be one JSON object the gateway can read, and every tool it declares must be of a type the agent runs
itself (`client_tool_types` in the same file); a request declaring any other type (the provider's: web search or
fetch, image generation, remote MCP, file search, a hosted shell or code interpreter), a provider-side search field or
content for the provider to fetch by URL is refused (`refused = "server_tool"`), an unreadable one too
(`"body_unreadable"`). A refusal is an attempt, recorded for a look: it does not void a trial, and a harness's own
start-up probe (Claude Code's `HEAD /api/hello`) is not counted. Without the gateway (`GATEWAY=0`, a
bare `harbor run`), the task's own allowlist applies and these hosts are reachable directly: not for official runs.
Open: Codex with a ChatGPT login needs `chatgpt.com` itself at start-up, over HTTPS (docs/RUNNING.md), so such a run
keeps that host beside the gateway, and its account connectors are off by the harness's configuration only; official
runs prefer API keys, which have none.

### 2.12 Time cutoff (2026-10-11; at the end of the instruction, 2026-10-12; each task's own, 2026-10-14)
Every task gives the agent a fixed wall-clock time, its **cutoff**, and tells the agent so in the last section of its
instruction, together with the request not to cheat, in one format in every task (owner, 2026-10-11, board 0080, issue
#156, after
Terminal-Bench's "You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific
to this task."). Until then each benchmark stated its budget in its own words and place ("60 minutes", "1 h", "90 min
(5400 s)", a paragraph of its own in RoboDojo since #155; RoboTwin's privileged instructions not at all), and the number
was a constant, a data value or a literal in each of 26 generators.

| Item | Level | Basis |
|---|---|---|
| Each task sets its own cutoff: `[agent] timeout_sec` in its `task.toml`, a whole number of seconds within D8's cap (§2.3), set by its author in the pull request that adds or changes the task and stated in that pull request's Contract; a generated benchmark keeps its number as a constant of its generator (`scripts/<bench>/`). There is no central table (owner, 2026-10-14, board 0120: as in Terminal-Bench, whose tasks set `[agent] timeout_sec` and whose CI checks the instruction's closing sentence against it). From 2026-10-11 to 2026-10-14 one table, `scripts/task_cutoffs.toml`, held every cutoff; its record is in `docs/CUTOFFS.md` | MUST | [CI] (`ci_checks/check-cutoffs.py`, per task) |
| A benchmark uses one number for all its tasks of a mode; a pull request that gives some tasks another number says why (its overview lists the numbers it sets) | SHOULD | [review] |
| `scripts/task_conventions.py` (`normalize`, which every generator ends with) writes from the task's number the `## Time limit` section of `instruction.md`, the README's `Agent time budget` row and, in the standard modes, the `sim` service's `RCB_WALL_CLOCK_S` (added to the service's environment where a task did not set it) | MUST | [CI] |
| `instruction.md` ends with `## Time limit`, equal to what `normalize` renders for the task's number and mode: after `## External material` and `## Resource limits`, nothing after it, so that it is the last thing the agent reads (owner, 2026-10-12: at the end, where Terminal-Bench has it; on 2026-10-11 the paragraphs stood under the title) | MUST | [CI] |
| Its first paragraph is the same sentence pair in every task: `You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.` Seconds only, the number as in `task.toml` | MUST | [CI] |
| Its second paragraph says what the cutoff means in the task's mode (below), the same words in every task of the mode | MUST | [CI] |
| The instruction states the agent's limit nowhere else as a duration; a benchmark's own text refers to "the time limit (`## Time limit`)" (§2.5), and nothing before the section contradicts it | MUST | [CI] (a heuristic: the wordings tasks used before 2026-10-11 and the obvious other shapes, "You have one hour", "The limit is 3600 seconds", "Finish within 60 minutes"; a reviewer still reads the text) |
| Nothing is added to the instruction on its way to the agent: Harbor passes `instruction.md` as it is, and official runs use no prompt template and no extra instruction | MUST for official runs | [current] (`scripts/run_agent_batch.sh` passes none) |
| "Do not cheat" is §2.11's honour rule, not a second rule: installing packages is allowed and is not cheating (the second paragraph says so and points to `## External material`, which keeps the substance: what counts as a solution, that trials are reviewed, what the network reaches); a trial that fetched a solution is flagged and decided by the owner (§2.11, §5) | MUST (how it is read) | [new] |
| What stops the agent is Harbor's agent timeout, `[agent] timeout_sec`, with no multiplier in official runs. Harbor counts it around the agent's run only (its trial's agent phase: `asyncio.wait_for(agent.run(...), timeout=...)`): after the environment has been built and started and after the agent's harness has been installed, each of which has a timeout of its own, not from the container's start. In the standard modes the `sim` service starts with the environment, so whatever start-up it has not finished by then is waited out inside the agent's time | MUST | [current] (Harbor 0.23; official runs pass only a multiplier for the harness's set-up) |
| At the cutoff the trial is graded as it stands: privileged, what is in `/app/output/` at that moment; standard modes, the episode as the `sim` service holds it (the collect hook ends and records it, §4.8). A timeout is a result, not an infrastructure error, and is not retried | MUST | [current] |
| The `sim` service's own clock (`RCB_WALL_CLOCK_S`: `/spec.budget.wall_clock_s`, `meta.time_left_s`) reports the same number and ends nothing. It counts from the agent's first request to the service (any endpoint; logged, so a restarted service keeps it), never from the service's start or the end of its scene build: the sidecar is up before the agent's phase begins, and a clock started then runs ahead of the harness's (STANDARD_MODE.md, "The agent's clock"). So `time_left_s` never runs out before the cutoff, and the instruction tells the agent to plan by it. A service that ends the episode on its own clock says so in the benchmark's own text and keeps the earlier closing sentence: today RoboARC's, which since its MuJoCo release (2026-10-13) counts from the first request like the others and still ends the episode at 0 (its instruction says so); it becomes report-only at RoboARC's next task update (`docs/benchmarks/roboarc.md`) | MUST | [CI] for the number and the service layers' tests (`check-unit-tests.sh`); [new] (2026-10-13, owner; before, RoboCasa's three benchmarks and twelve `eai-standard/2.2` services, LabUtopia among them, counted from the service's start) |
| Changing a cutoff: an owner decision. Its pull request sets the new `[agent] timeout_sec` in the tasks concerned (a generated benchmark: the generator's constant, then a render), in both twins, normalizes them and states old -> new, who decided and why (label `cutoff-change`, approved by the owner). The task changes in place and keeps its name (§2.8); the pull request and the tasks' git history are the record, there is no Change Log entry in each task's README (owner, 2026-10-12); results recorded under another cutoff are reported separately (D8) | MUST | [new] |
| A new benchmark needs its label in `scripts/task_conventions.py` `BENCHMARKS` (task-directory prefix -> name), in its shared-files pull request (D6); its cutoff is in its own tasks | MUST | [CI] |

**The section** (privileged mode, 3600 s; `scripts/task_conventions.py` `CUTOFF_HEADING`, `CUTOFF_SENTENCE`, `CUTOFF_NOTE`):

> ## Time limit
> You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
>
> This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Installing packages is not cheating (`## External material` above).

Standard and standard-realtime modes, second paragraph:

> This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Installing packages is not cheating (`## External material` above).

No benchmark keeps the earlier sentence today ("The service's `time_left_s` is its own count of this limit, from the service's start or from your first request, so it can differ from the time you really have left."): RoboARC's standard tasks did until its MuJoCo release (2026-10-13), whose service counts from the first request.

Seconds only, because the sentence is then the same in every task and the number is the one in `task.toml`; a second
unit is a second number to keep right. The sentence pair opens the section and the explanation follows it, because the
explanation refers to it; the two together are the end of every instruction. A heading of its own lets a benchmark's
text point to it from anywhere ("the time limit (`## Time limit`)") and keeps it apart from `## Resource limits`. Half
of the failed privileged trials recorded until 2026-10-11 ended at the cutoff, which is why the section also says what
is graded then.

**What follows a cutoff and what does not.** `normalize` rewrites everything that follows the task's number (above)
and its digest; [`CUTOFFS.md`](CUTOFFS.md) explains the rules and keeps the history of the table. A scheduler's
estimate of a trial's length reads `task.toml`. Not derived from the cutoff: the token budget (§5), the resource limits
(§2.10), reset budgets (§4.5), step caps, verifier timeouts. Collect-hook and verifier budgets that were sized for an
episode as long as the agent's time (RoboCasa's three benchmarks, RoboLab, YAMLab, DexJoCo, BEHAVIOR-1K) hold for any
shorter cutoff and are looked at when one is raised.

### 2.13 Seeds (2026-10-13)

The owner, 2026-10-13: "every task needs a default seed, but may also allow a change of seed, or name a list of seeds
it allows, so that the task's submitter verifies which seeds are reasonable"; "we do not want the agent to memorise
the answer: a reference solution can be the solution of one seed; from now on the answers are per seed"; "the seeds
can be a list, a range, or any seed"; official batches draw a seed from the allowed ones for each trial. A seed names
one instance of the task (its scene and start, replayed bit for bit as before); where an upstream has no seed of its
own, seed 0 names the task's one frozen instance.

| Item | Level | Basis |
|---|---|---|
| `[metadata.seeds]` in `task.toml`: `default` (an integer); `allowed`, the seeds a trial may run from, `default` among them: a list of distinct integers (`[0, 3, 7]`), a range with both ends included (`{ from = 0, to = 100 }`; TOML's `[0, 100]` would be the two seeds 0 and 100), or `"any"` (every seed; TOML has no null); `oracle` (the seeds the reference solution under `solution/` is for, a list of allowed seeds: not empty for `oracle = "full"` or `"partial"`, empty for `"none"`); `build`, `"frozen"` (the default: every seed in `allowed` is a committed instance) or `"runtime"` (the task builds a seed's instance itself; required for a range and for `"any"`, which cannot all be committed). A generator writes what it has; `scripts/task_conventions.py` completes the rest: `default` = `instance_seed` (0 without one), `allowed = [default]`, `oracle = [default]` or `[]` | MUST | [CI] (`ci_checks/check-seeds.py`) |
| `instance_seed`, where present, equals `default`; a standard or standard-realtime task has its privileged twin's `default`, `allowed` and `build` (where it has a twin, §2.15) | MUST | [CI] |
| The default seed's frozen instance is the task's instance, where §2.2 and §3 put it. With `build = "frozen"`, every other allowed seed's frozen instance is `tests/seeds/<seed>/instance.json` (or `.npz`, the same kind as the default's) of the task that holds the pair's instance (the privileged twin; a task without one: itself); `tests/seeds/` holds nothing else (a `"runtime"` task may commit some seeds' instances there too) | MUST | [CI] |
| `build = "runtime"`: given a file `seed` (the integer) next to its instance, the task's environment builds that seed's instance deterministically, and its verifier builds the same instance from its own copy of the file (never from anything the agent's container wrote) and grades on it; the same seed gives the same start hash in a fresh process. The benchmark's doc says how, and its generator's tests show it on a sample of seeds | MUST | [new] |
| Another seed's instance, or a `seeds` directory, anywhere under `environment/` (where the agent's image, or a sidecar's that the agent's container could share, is built from); in privileged mode the agent reads the instance of its own trial's seed only, as before | MUST NOT | [CI] |
| The runner chooses the seed, never the agent: `scripts/task_seed.py materialize <task> --seed <S> --out <dir>` writes a copy of the task whose instance copies are seed S's (a committed instance; else, for a `"runtime"` task, the file `seed` in each of those places) and whose `[metadata.seeds] default` says S, and refuses a seed that is not allowed; Harbor runs the copy. Results record the seed | MUST | [new] |
| Official batches draw a seed uniformly from `allowed` for each trial (owner, 2026-10-13; `"any"`: from 0 to 2^31 - 1); a run on the default seed only says so | SHOULD | [new] |
| The submitter allows only seeds they checked: the start is valid and the instruction holds for it (`nop` scores 0 on it; the oracle, a positive example or the human review of §2.7 covered it). For a range or `"any"`, they check the generator rather than each seed (its rule gives a valid start for every seed: say how in the benchmark's doc, and show it on a sample). A change of `allowed` is a new digest, recorded in the README's Change Log | MUST | [new] |
| Reference solutions are per seed: `solution/` may hold a different solution per seed (it reads the seed of the instance it runs on), and scores 1 on every seed in `seeds.oracle`; it need not on the other allowed seeds. The oracle check (§2.7) runs on each seed in `seeds.oracle` | MUST | [new] |
| Standard and standard-realtime modes: the seed and its instance stay in the service and the verifier, never in the agent's container (§4.5) | MUST | [current] |

Until a benchmark's generator writes more, every task allows its default seed only (`allowed = [default]`): the 2026-10-13
migration changed `task.toml` only (the instances, the instructions and the READMEs are unchanged).

### 2.14 Scene dynamics (2026-10-14, board 0106; merged with #188)

The owner, 2026-10-14: "every task runs in standard mode by default; a subset, the dynamic tasks, gets a
standard-realtime mode as well". A task is **dynamic** when something in its scene other than the robot can do work by
a force other than the robot's own and gravity ("非机器人力和重力原因下能够做功的"): a body that starts with a velocity
(a thrown, served, rolling or sliding object; a pendulum already swinging), an actuated or scripted body (a conveyor, a
motor-driven rail or turntable, a scripted push, a timer that moves a part), an opponent or another agent. Everything
else is **static**: the world waits while the agent thinks, and objects move only because the robot moves them or
gravity pulls them. Decided with it (board 0106, owner 2026-10-14):

- settling under gravity after reset, cloth / liquid / granular material the robot moves, a falling domino chain the
  robot started: static (gravity does the work);
- passive springs, joint stiffness and elastic material that only give back what the robot put in (a spring button, a
  self-closing latch, a springboard, an elastic rope): static;
- a world change applied once and instantly when the robot comes near (LIBERO-MAX's on-proximity relocations): static;
  a change on a clock, or a mechanism that keeps moving bodies after the robot started it (a venue that launches a
  ball at t = 2 s, a goalkeeper that moves after the kick, a timer dial that turns back by itself): dynamic;
- visual-only or state-only change (a faucet's water and a burner's flame drawn as a site, cooking and freezing
  states, an on/off flag): static;
- an episode horizon or step cap is not a force: static;
- a robot that must balance actively (a floating-base humanoid or legged robot, a hovering drone) does not make a task
  dynamic by itself (owner, 2026-10-14: HumanoidBench needs no realtime mode by this definition).

| Item | Level | Basis |
|---|---|---|
| `[metadata] dynamics ∈ {static, dynamic}` in `task.toml`, the value of the one table `scripts/task_dynamics.toml` for the task (its family's exception, else its benchmark's row; every entry gives its reason, `why`), written by `scripts/task_conventions.py` (`normalize`); never edited in a task, a template or a generator | MUST | [CI] (`ci_checks/check-dynamics.py`) |
| A new benchmark adds its row (and its families' exceptions) to the table in the pull request that adds its tasks | MUST | [CI] |
| The same family has the same value in every mode (the field describes the scene, not the mode) | MUST | [CI] (the table is keyed by family) |
| A `dynamic` task may have a `-standard-realtime` twin (§4b); a `static` one needs none | MAY | [new] (owner, 2026-10-14) |

### 2.15 Modes a benchmark ships (owner, 2026-10-14)

A benchmark may ship **any subset** of the three modes: privileged only, standard only, standard-realtime only, or any
combination, and a family within a benchmark may lack a mode its benchmark has (RoboDojo's six standard-only tasks,
§4.8). No owner decision is needed for the choice; what a benchmark leaves out is stated in its doc. This general rule
replaces the per-benchmark exceptions that allowed a missing twin before (RoboOlympics without privileged mode, §4b,
owner 2026-10-08; RoboDojo's six, §4.8, owner 2026-10-11); those benchmarks are unchanged and conform.

| Item | Level | Basis |
|---|---|---|
| The modes a benchmark ships are the modes it has tasks in (a standard task without a privileged twin is accepted when its benchmark has no privileged task, `task_conventions.bench_has_mode`) | MUST | [CI] (`ci_checks/check-instance-copies.sh`) |
| Where both exist for a task, its privileged and standard versions have **the same cutoff**: the same `[agent] timeout_sec` (owner, 2026-10-12) | MUST | [CI] (`ci_checks/check-cutoffs.py`, 2026-10-14) |
| Twins, where both modes exist for a family, share one frozen instance, success rule and seeds (§2.2, §2.13) | MUST | [CI] |
| A standard or standard-realtime task without a privileged twin carries its own frozen instance, if it has one, in its sidecar, and its verifier's copy (where it keeps one) is byte-identical; its README's Twin row says why there is none. In a benchmark with no privileged mode that is automatic; in a benchmark that has one, the task is listed with its reason in `scripts/task_conventions.py` `NO_TWIN` (a missing twin that is neither fails CI, so a deleted or misnamed twin is caught) | MUST | [CI] (`ci_checks/check-instance-copies.sh`) |
| A privileged task without a standard twin needs nothing more (its README's Twin row says "privileged only") | MAY | [current] |
| Results are reported per mode (§5); a benchmark's results state which modes it ships, and a mode it does not ship is "not offered", not a failure | SHOULD | [new] |

### 2.16 Adding a mode (owner, 2026-10-14)

The three modes (privileged §3, standard §4, standard-realtime §4b) are not a closed list: anyone may propose a new mode
by pull request. The modes live in one registry, `MODE_REGISTRY` in `scripts/task_conventions.py`; everything in the
repository that parses or branches on a mode reads it (`mode_of`, `base_of`, `twin_of`, the limits' scope, the twins'
equal cutoffs, the generated task list, and the checks under `ci_checks/`, which get it once per run from
`python3 scripts/task_conventions.py modes`). An entry gives the mode's name (= its directory suffix and `[metadata]
mode`), its column label, its PROTOCOL section, whether the simulator runs in a trusted `sim` sidecar, whom the resource
limits bind, the `protocol` values its tasks may declare, its twin mode (the task of the same base that holds the frozen
instance and seeds) and the mode whose cutoff it must equal, if any.

| A new-mode pull request contains | Level | Basis |
|---|---|---|
| A name, which is also the task-directory suffix (`<base>-<name>`) and the `[metadata] mode` value: lower case, words joined by `-`, not a suffix of another mode's name nor ending in one (`-standard-realtime` is recognised by its whole suffix, longest first), no version or duration (§2.2) | MUST | [CI] (`scripts/task_conventions.py` refuses a registry that breaks it; `ci_checks/check-task-fields.sh` checks every task's suffix and `mode`) |
| A PROTOCOL section of its own, like §3 / §4 / §4b, defining: what the agent gets (its container, the interface, privileged information or not, the wire protocol and its version if any); what is graded (the deliverable or the service's record, the success rule, replays and determinism); the time rule (what the cutoff counts, how a service reports it, §2.12) and the reset rule (none by default, §4.5); and the failure semantics, which failures are infrastructure (`infra_error`, never the agent's 0) and which are the agent's | MUST | [new] |
| Its `MODE_REGISTRY` entry, its `CUTOFF_NOTE` (the second paragraph of `## Time limit` for the mode; the module refuses a mode without one) and, where it has a protocol, its reference implementation (as §6 requires of a protocol change) | MUST | [CI] |
| CI support: the existing checks pass for its tasks through the registry; a rule specific to the mode is a new check (or a branch keyed on a registry field, never on a hard-coded mode name list), with a `ci_checks/check-ci-selftest.py` case that breaks a real task of the mode and must fail | MUST | [CI] |
| At least one benchmark using it: its tasks in the benchmark's own pull request (shared files first, as for a new benchmark), with the oracle and `nop` evidence of §2.7 in the new mode | MUST | [new] |
| `docs/TAXONOMY.md` (`mode`, and `protocol` if any), `docs/REVIEWING.md` if reviewers check something new, and the results: the new mode is reported separately from the others (§5) | MUST | [new] |
| The runner side (batch_eval_live and the results site) is told the new suffix in the same change; it reads the registry or follows it | SHOULD | [new] |

**Cutoffs of a new mode.** A task of the mode sets its own cutoff like any task (§2.12). Whether it must
equal another mode's number is the registry's `same_cutoff_as`, decided in the mode's pull request: standard has
`same_cutoff_as = "privileged"` (owner, 2026-10-12, CI-enforced), standard-realtime has none (today its numbers equal the
others everywhere). A new mode is free unless its pull request says otherwise.

## 3. Privileged mode (`mode = "privileged"`, `task_type = "trajectory"`)

| Item | Level | Basis |
|---|---|---|
| Deliverable `/app/output/trajectory.npz` (format defined by the task's instruction) | MUST | [current] |
| The generating script at `/app/output/gen.py` | SHOULD | [current] |
| Graded by open-loop replay from the frozen initial state in a fresh process | MUST | [current] |
| ≥ 2 replays with matching final-state hashes, reported as `deterministic` | SHOULD (the field is MUST) | [current] |
| Exception, one replay: a benchmark whose tasks are measured to replay bit for bit may be graded by ONE fresh-process replay, to save grading time (`success` = that replay's success). Nothing is compared then, and `reward.json` says so: `deterministic = 1` with `determinism_checked = 0` and `replays = 1`. The replay must start from the frozen state, shown by the recorded initial-state hash: a rebuilt instance that hashes differently gives no verdict (`instance_mismatch` with `infra_error`). The benchmark's doc states the rule, the measurement behind it and what it gives up (a trajectory whose outcome differs between fresh processes is no longer caught). RoboDojo, its 48 privileged tasks ([`benchmarks/robodojo.md`](benchmarks/robodojo.md)) | MAY, by owner decision | [new] (owner, 2026-10-12) |
| Success judged on the state at the end of the replay ("success at any step" needs a stated reason) | SHOULD | [current] |
| The frozen instance copied into both `environment/` and `tests/` with its expected initial-state hash, checked on rebuild | SHOULD | [current] |
| A hash check before moving to new hardware; a host that rebuilds a different state is graded `instance_mismatch` with `infra_error` (privileged: also when no trajectory was handed in; standard: the service's `reason`). A scene build must not depend on the host: no unsorted directory listing, no wall clock. RoboTwin's `place_a2b_left`, `place_a2b_right`, `place_object_scale` and `place_object_stand` drew their object from an unsorted `glob` (directory order) and never rebuilt off the reference workstation; since 2026-10-14 the tooling sorts it and their instances are re-frozen (board 0113) | SHOULD | [current] |
| Unlimited resets, privileged state, planning primitives, self-replay | MAY | [current] |
| Tool API shape | task-defined | [current] (recommended: `Session` with `reset` / `replay` / `status` / `save_trajectory`) |
| Self-reported cost (resets, simulation steps) in `agent_*` fields | SHOULD | [current] |
| `task_type = "policy"` | MAY | the first such tasks are standard-mode tasks of §4c (a skill as code, graded offline in the verifier) |

## 4. Standard mode (`mode = "standard"`): `eai-standard/2.x`

Wire details (endpoints, RCB1 frames, `meta`, error codes, crash recovery) are in
[`STANDARD_MODE.md`](STANDARD_MODE.md), one part per version. This section lists what is required.

### 4.0 Versions
| Version | Date | Content |
|---|---|---|
| eai-standard/2.1 | 2026-09-30 | the base (formerly `rcb-limited/2.1`): no reset; `/submit` action chunks, `/observe`; binary RCB1 responses; 82-column proprioception, optional depth noise; crash recovery. Served by the standard tasks of RoboTwin, DexToolBench, MuJoCo Playground (manipulation), KinDER, HumanoidBench, MetaWorld+, VLABench, the three RoboCasa benchmarks, LIBERO-MAX, BiGym 2.0, RoboOlympics, RoboFunOlympics, RoboSafeBench |
| eai-standard/2.2 | 2026-10-01 | additive extension (§6, [`STANDARD_MODE.md`](STANDARD_MODE.md) Part 2) with crash recovery; served by BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, MolmoSpaces, MyoSuite, DexJoCo, YAMLab, RoboDojo, ManiGuard, Panda Dynamic Scenes, DexHand and MuJoCo Playground's quadruped tasks (LabUtopia and AutoBio until their removal on 2026-10-14) |
| eai-standard/2.3 | 2026-10-08 | 2.2 + the realtime capability (§4b; [`STANDARD_MODE.md`](STANDARD_MODE.md) Part 3, "Standard-realtime mode"); every 2.2 addition stays a MAY. Served by standard-realtime tasks only (HumanoidBench, BiGym 2.0, MyoSuite, RoboOlympics, RoboSafeBench, Panda Dynamic Scenes, RoboCasa365, MuJoCo Playground); standard tasks stay on 2.1 / 2.2. Issue #86 |
| eai-standard/2.4 | 2026-10-08 | 2.3 + the operations capability ([`STANDARD_MODE.md`](STANDARD_MODE.md) Part 4): operation ids and request deadlines (408 / 409), `GET /operations/<id>`, a service-owned call watchdog, a physics-tick ledger, fsynced journals; every earlier addition, the realtime capability included, stays a MAY. Served by standard tasks (Robo, RoboARC; first RoboTangle); reference implementation `scripts/eai_standard/v2_4/`. Issue #89 |

Standard services report `eai-standard/2.1`, `eai-standard/2.2` or `eai-standard/2.4`, standard-realtime services `eai-standard/2.3`; the shipped clients
accept every 2.x version and the former `rcb-limited/2.x` spelling as well. No task declares a version before 2.1
(`rcb-limited/1.0`, with `/reset` and a single-action `/step`, is retired, §6; 2.0 had no measured proprioception).

**Core rules.** The simulator runs in a sidecar the agent cannot open; four endpoints; RCB1 binary responses; no
reset (unless the optional capability is enabled), no step limit, wall clock as the only hard budget; crash recovery
resumes the same episode; success is decided on a replay.

### 4.1 Topology
| Item | Level | Basis |
|---|---|---|
| Simulator in a compose sidecar named `sim`; no simulator or simulation code in the agent container | MUST | [current] |
| GPU reservation on `sim` only | MUST (if a GPU is needed) | [current] |
| `ports:` / `expose:` on the sidecar | MUST NOT | [current] |
| Service on `0.0.0.0:8000`; the client tries `http://sim:8000`, then `http://localhost:8000` | MUST | [current] |
| The socket opens only when the scene is ready; the client retries | SHOULD | [current] |
| `restart: on-failure:N`, N ≥ 3 | MUST | [current] |
| The agent image ships `rcb_client.py` (`Robot.spec / status / submit / get_obs`) and `rcb1.py` | MUST | [current] |
| The instruction documents client usage, action types and rules | MUST | [current] |

### 4.2 Endpoints
| Item | Level | Basis |
|---|---|---|
| `GET /spec`, `GET /status`, `POST /observe`, `POST /submit` | MUST | [current] |
| Everything else returns 404 (`/state`, `/success`, …), except endpoints a minor version adds (2.2: the stateless `POST /kinematics`); `/reset` exists only with the optional reset capability | MUST | [current] / [new] |
| `/spec` has `protocol`, `action_types` (each with `dim`, `layout`, units or limits, `semantics`), `cameras`, the proprioception layout, `budget` (`reset`, `wall_clock_s`) | MUST | [current] |
| `/spec` also has `task_text`, `max_chunk_s`, `max_watch_s`, `physics_hz` or `control_dt`, `on_service_error`, `max_frames_per_call` | SHOULD | [current] |
| `/status` has `calls`, `done`, `reason`, `elapsed_s` and a step counter | MUST | [current] |
| Step counters named `rows` and `sim_steps` (old names kept alongside) | SHOULD | [new] (next minor version) |

### 4.3 Encoding (RCB1)
| Item | Level | Basis |
|---|---|---|
| Responses are RCB1 frames: `"RCB1"`, 4-byte little-endian header length, header JSON, blobs | MUST | [current] |
| Images or video as base64 in JSON | MUST NOT | [current] |
| Part kinds `mp4`, `array` (C-order raw bytes, dtype and shape in the header), `jpeg`, `json`, `bytes` | MUST | [current] |
| `last/<cam>` in every response; `video/<cam>` / `frames/<cam>` on request | MUST | [current] |
| `proprio` part: one row per frame, columns as in `meta.proprio.layout` | MUST | [current] |
| Which proprioception columns | task-defined | [current] |
| `depth/<cam>`, depth noise, `meta.cameras`, `meta.task` | MAY | [current] |
| `meta` has `calls`, `sim_time_s`, `time_s`, `time_left_s`, `proprio{layout, now}`, `done`, `reason` and a step counter | MUST | [current] |
| Limits: requests ≤ 64 MB (413), ≤ 3000 frames per call (400), responses over 256 MB drop frames/depth and say so in `meta.degraded` | SHOULD | [current] |

### 4.4 Actions
| Item | Level | Basis |
|---|---|---|
| At least one action type, fully described in `/spec` | MUST | [current] |
| Which action types (`joint_position`, `ee_delta`, `ee_pose`, whole-body IK, …) | task- or benchmark-defined, consistent within a benchmark | [current] |
| `dt` a multiple of the physics or control step; otherwise 400, never rounded | MUST | [current] |
| Out-of-limit values clipped and reported in `clipped`, not rejected | MUST | [current] |
| `linear` / `hold` interpolation; chunks ≤ `max_chunk_s` | SHOULD | [current] |
| Planner-executed actions such as `ee_pose`, with frame, quaternion order and end-effector reference in `/spec` | MAY | [current] |
| Action dtype (float32 / float64) | task-defined, stated in `/spec` | [current] |

### 4.5 Budget and privileged information
| Item | Level | Basis |
|---|---|---|
| No reset by default: one trial is one episode (per-benchmark exceptions below) | MUST | [current] |
| Optional reset capability: `budget.reset = N` via `POST /reset`, default 0; results with N > 0 are reported separately, never ranked with N = 0 | MAY | [new] |
| No step limit; wall clock is the only hard budget; simulation steps are reported as cost | MUST | [current] |
| A technical episode cap stated in `spec.max_control_steps` | MAY | [current] |
| Exposing object poses, scene files, seeds, the success predicate, segmentation, object contact forces | MUST NOT | [current] |
| Contact or safety telemetry that a benchmark's task contract depends on, declared field by field in its benchmark document (below) | MAY | [new] (owner, 2026-10-10) |
| Robot proprioception, camera calibration, task text | MAY | [current] |

**Declared contact and safety telemetry** (owner decision, 2026-10-10). The MUST NOT on object contact forces has one
documented exception: a benchmark may publish contact or safety telemetry in standard mode when its task contract
depends on it (the agent is judged, or its success is held for review, on a reading it could not know otherwise), and
`docs/benchmarks/<bench>.md` declares exactly which fields are published and why. Nothing but the declared fields is
published; object poses, scene files, seeds, the success predicate and segmentation stay MUST NOT, and a reading that
gives an object's pose is not covered. Benchmarks that use it are listed here.
- **RoboARC** (standard tasks): `meta["safety"]` of every response: the forcing record (the largest force an arm
  or a part it holds pressed with, the drive load meanwhile, forcing events), the deepest task contact and
  held-finger contact with their review limits, the review events (with the names of the parts in contact), the lowest soft-body volume ratio and the worst cord
  attachment stretch, the table-guard stops and IK jumps
  ([`benchmarks/roboarc.md`](benchmarks/roboarc.md), "Safety readings in standard mode"). The benchmark's
  physical-validity policy holds a success with a deep contact for human review and ends an episode on a collapsed soft
  body, so the agent must be able to see the reading it is judged on.

**Per-benchmark reset defaults.** A benchmark's standard or standard-realtime tasks may default to a reset budget N > 0 only by owner
decision, recorded here and in `docs/benchmarks/<bench>.md`; the capability is the one above (`POST /reset`, only the
last episode graded, a success ends the trial: [`STANDARD_MODE.md`](STANDARD_MODE.md)), the budget stays an override (`RCB_RESET_BUDGET`), and that benchmark's
results must state the reset budget and are compared only with results under the same budget.
- **HumanoidBench** (owner, 2026-10-07; its standard-realtime tasks too, 2026-10-08): `budget.reset = 50`. The H1 falls within 1–3 s of robot time and the agent has
  no simulator to practise in, so a single episode is one blind attempt. `RCB_RESET_BUDGET=0` still runs one episode;
  HumanoidBench standard results recorded before 2026-10-07 ran with 0 and are reported separately
  ([`benchmarks/humanoidbench.md`](benchmarks/humanoidbench.md)).
- **RoboOlympics** (owner, 2026-10-12, as RoboFunOlympics; its single-robot sports families):
  `budget.reset = 50`, HumanoidBench's value for the same reason. A sport is attempts: a jump, a throw or a kick is over
  in a second or two and ends at the first foul or fall, and the agent has no simulator to practise in. `RCB_RESET_BUDGET=0`
  still runs one attempt ([`benchmarks/roboolympics.md`](benchmarks/roboolympics.md)).
- **MyoSuite** (owner, 2026-10-09; standard tasks; its standard-realtime twin has the mode's default, 10, too): `budget.reset = 10`. MyoSuite's own termination ends most episodes
  within a second or two of simulated time (a dropped object, an object off the reference motion), and the agent has no
  simulator to practise in, so a single episode is one blind attempt at muscle-level control. `RCB_RESET_BUDGET=0` still
  runs one episode; MyoSuite standard results recorded before 2026-10-09 ran with 0 (and saw the wrong `joint_effort`)
  and are reported separately ([`benchmarks/myosuite.md`](benchmarks/myosuite.md)).
- **BiGym2** and **KinDER** (owner, 2026-10-11; standard tasks): `budget.reset = 10`.
  The task's horizon (BiGym2: twice the longest human demonstration; KinDER: its 1000 control steps) bounds each
  episode, and with no reset the agent's practice and its graded attempt share it: of GPT-6 Astra's 16 standard runs,
  12 failed, 10 of them with the steps spent and 2 on an object on the floor, the hour mostly unused. Ten, as
  MyoSuite, not HumanoidBench's 50: an episode here is long. Steered call by call, one took Astra 6–50 min (median
  19), so ten resets leave the wall clock the only limit; a script that only replays actions ends one in about a minute
  (BiGym2 pick-box's 4400 steps in 75 s, KinDER sweep-simple's 1000 in 64 s, a reset about 1 s; RTX 4090,
  2026-10-10), so with 50 it could spend the hour on some 50 tries, and any success ends the trial.
  `RCB_RESET_BUDGET=0` still runs one episode; standard results recorded before this change ran with 0 and are
  reported separately ([`benchmarks/bigym2.md`](benchmarks/bigym2.md), [`benchmarks/kinder.md`](benchmarks/kinder.md)).
  BiGym2's standard-realtime tasks keep 0.
- **DexToolBench** (owner, 2026-10-13; standard tasks): `budget.reset = 20`. With one episode the first grasp decided
  the trial: all 21 of GPT-6 Astra's standard trials (2026-10-12) knocked the tool off the table at some point, the one
  success included, most of the hour went into picking it up from the floor, and the same task gave unrelated results
  from one run to the next (board 0098). A reset puts the robot, the tool and the goal sequence back to the frozen start
  (the service's `Session.reset()`; the same state hash, images and proprioception). The MuJoCo service
  (`images/mujoco/limited/server_mj.py`) implements the capability as above; its other tasks (MuJoCo Playground ALOHA,
  Panda) keep 0. `RCB_RESET_BUDGET=0` still runs one episode; DexToolBench standard results recorded before this change
  ran with 0 and are reported separately ([`benchmarks/dextoolbench.md`](benchmarks/dextoolbench.md)).
- **MuJoCo Playground, quadrupeds** (owner, 2026-10-14, board 0113; the nine `mujoco_playground_{go1,spot,barkour}_*`
  standard tasks): `budget.reset = 10`. A fall, a failed turn or a wrong first chunk used to end the trial. A reset
  restores the frozen start (`rcb_quadruped.Session.reset()`: the same state hash and proprioception). The quadrupeds'
  2.2 service (`scripts/mujoco-playground/shared/standard/server.py`) implements the capability as above, as MyoSuite's
  does (its instruction calls `POST /reset` through `Robot._post`). The ALOHA and Panda standard tasks keep 0.
  `RCB_RESET_BUDGET=0` still runs one episode; quadruped standard results recorded before this change ran with 0 and
  are reported separately ([`benchmarks/mujoco-playground.md`](benchmarks/mujoco-playground.md)).
- **DexHand** (owner, 2026-10-14, board 0109; standard tasks, from their first release): `budget.reset = 20`,
  DexToolBench's value. Every family ends an episode at the first failure (a dropped, slipped or knocked object, a bound
  exceeded), the essential families start with the object already in the hand, and the agent has no simulator to
  practise in, so with one episode the first slip decided the trial. A reset calls the family's `Session.reset()` (the
  same state hash as a fresh process). The DexHand 2.2 adapter (`scripts/dexhand/shared/standard/server.py`) implements
  the capability as MyoSuite's does. `RCB_RESET_BUDGET=0` still runs one episode
  ([`benchmarks/dexhand.md`](benchmarks/dexhand.md)).

### 4.6 Errors (no physics executed)
`400` invalid input (type, dimension, NaN/inf, `dt`/`seconds` invalid, chunk too long, frame limit, malformed body)
— MUST; `409` episode over — MUST; `413` body over 64 MB — SHOULD (the client refuses such a body before sending it);
`500` simulator error, and the episode ends with `reason = "error"` — MUST; the client raises `EpisodeOver` on 409 and
500. [current]

### 4.7 Episode and crash recovery
| Item | Level | Basis |
|---|---|---|
| The episode starts when the service is ready; the seed stays inside the service | MUST | [current] |
| End condition defined by the task and stated in the instruction and in `/spec` (`episode`) | MUST | [current] |
| The predicate is evaluated once more at episode end | MUST | [current] |
| Crash recovery: every executed step journaled, a checkpoint (step count, state hash) per completed call; after a restart the journal is replayed, the hash checked and the same episode continues — never a reset | MUST | [current] |
| At most 2 resumes (`RCB_MAX_RESUMES`); a third crash ends the episode with `sim_crashed_on_call` if every crash happened inside a call, else `sim_crashed` (`infra_error = 1`); a written verdict is never overwritten | SHOULD | [current] |
| Startup watchdog and back-off before rebuilding | SHOULD | [current] |
| Per-simulator resume rule: a simulator declared nondeterministic compares and records the hash, and a mismatch continues the same episode with `resume_state_mismatch` (unless the robot diverged grossly), as in [`STANDARD_MODE.md`](STANDARD_MODE.md) §13.1; the verdict still comes from fresh replays of the whole recorded trajectory (except for a task graded by the live episode under §4.8's exception) | MAY | [new] (2.2) |

### 4.8 Evidence and grading
| Item | Level | Basis |
|---|---|---|
| The sidecar writes `/data/episode.jsonl`, `/data/trajectory.npz` and `/data/final.json` (with `finalized`) | MUST | [current] |
| The replay's verdict (`replay_success`, `deterministic`) is in `final.json` before any video is rendered, and stands from then on: a video never decides, delays or voids a verdict (a service restarted while rendering loses only the video) | SHOULD | [new] (2026-10-10: the `rcb_service` family, the MuJoCo and MetaWorld+ services; [`STANDARD_MODE.md`](STANDARD_MODE.md)) |
| `/data/calls/NNNNNN/`, `replay.mp4`, `replay.last.png` | SHOULD | [current] |
| `artifacts` declares the evidence from `service = "sim"` and keeps `"/app/output/"` | MUST | [current] |
| `[[verifier.collect]]` waits for `server.pid`, sends SIGUSR1, waits for `finalized` | MUST | [current] |
| Needing a custom agent adapter to finish an episode | MUST NOT | [new] |
| A fresh replay decides: `success = replay_success ∧ deterministic` | MUST | [current] |
| `∧ live_success` when a live predicate exists | SHOULD | [current] |
| Exception, physics that does not replay bit for bit: a task measured not to (its frozen instance records it and why, e.g. `"determinism": "verdict"`; the benchmark's doc names the tasks and the measurement) is graded by the live episode the trusted service ran, `success = live_success`, read from the sim sidecar's own record of that episode (`final.json`; nothing the agent's container writes is read); the fresh replays still run and are reported (`replay_success`, `state_identical`, `deterministic`) but never decide, a replay without a result does not void the live verdict, and `reward.json` says `graded_by_live = 1`. A missing live record stays `infra_error`; an episode resumed after a crash (§4.7) is graded on its live state after the resume, so `reward.json` reports `resumes` and `resume_state_mismatch` and results state them. Such a task is standard-only: an open-loop trajectory of it cannot be graded reproducibly, so its family ships no privileged task (§2.15; `scripts/task_conventions.py` `NO_TWIN` lists these tasks with that reason). The verifier still grades `final.json` only, so §2.6's same verdict in a fresh process holds. RoboDojo: 6 tasks (two cloth, three liquid, `make_toast_random`) | MAY, by owner decision | [new] (owner, 2026-10-11) |
| Exception, one replay (the same decision as §3's): a benchmark whose tasks are measured to replay bit for bit may replay the recorded episode ONCE in a fresh process, and one successful replay is enough: `success = live_success ∧ replay_success` (the live predicate is then required, not SHOULD: it is what guards against a replay that succeeds where the episode did not, as the replay guards against a live success that does not repeat). `deterministic` is still measured, the replay's end state against the live episode's (= `state_identical`, `live_matches_replay`; `determinism_checked = 1`, `replays = 1`), and reported, but does not decide. A replay without a result, or one that did not start from the frozen state, stays `infra_error`. A task graded by the live episode (the exception above) records one replay instead of two. RoboDojo, its 54 standard tasks ([`benchmarks/robodojo.md`](benchmarks/robodojo.md)) | MAY, by owner decision | [new] (owner, 2026-10-12) |
| The verifier grades `final.json` only, without network access | MUST | [current] |

### 4.9 Live recording (sidecar only)
`live.mp4`, `live_timeline.jsonl`, `live_segments.jsonl`, `trajectory_live.f64`, `startups.jsonl` — SHOULD
(implemented for RoboTwin). If recorded: rendered from the replay by default, frames stamped with the call, never
affecting the verdict.

## 4b. Standard-realtime mode (`mode = "standard-realtime"`): `eai-standard/2.3`

Standard mode on a clock that does not stop (v1.1; owner, 2026-10-08; issue #86). Everything in §4 holds (sidecar
topology, endpoints, RCB1, actions, privileged information, crash recovery, evidence, replay grading) except where this
section says otherwise. Wire details: [`STANDARD_MODE.md`](STANDARD_MODE.md), "Standard-realtime mode". The time model
is the one proposed in #41 (the world runs at 1/S of real speed, a command takes effect at the next control step, all
agent latency counts, the agent's own program may act), on the 2.x endpoints and without its proxy (D11).

| Item | Level | Basis |
|---|---|---|
| `protocol = "eai-standard/2.3"`; `/spec.timing` with `realtime: true`, `slowdown`, `control_dt`, `wall_s_per_control_step`, `max_ahead_steps` | MUST | [CI] (protocol) [new] |
| An episode starts paused; its clock starts at its first `/submit` (or `/observe` with `seconds > 0`) and then runs one control step every `control_dt` × S s of wall time, whatever the agent does, until the episode ends; after a reset or a crash recovery the episode is paused again | MUST | [new] |
| `/submit` writes a plan of future targets from control step `at` (default: the next one) and answers at once; rows whose steps have run are dropped (`late_steps`); the last target is held when the plan runs out | MUST | [new] |
| Grading replays the targets the simulator **applied** at each control step (the journal), so the replay equals the live run whatever the timing; latency and jitter are recorded (`ticks.f64`; `max_lag_s`, `stalls`, `held_steps`, `late_steps` in `final.json`) and never decide the verdict | MUST | [new] |
| How well the clock was kept is evidence in `final.json`, and the grader repeats it in `reward.json` as numbers (a missing one is 0): `clock_s` (wall seconds the clock ran, over the trial), `max_lag_s` (the furthest a control step ran behind its time), `stalls` (the times the service, more than 0.5 s behind, dropped the debt instead of fast-forwarding the robot), `stalled_s` (the wall time dropped that way: the robot stood still while its clock should have run), `stalled_share` = `stalled_s` / `clock_s`, `held_steps`, `late_steps`, and what the requests cost: `requests_refused` (answered 4xx), `request_busy_s` (simulator-thread time spent on requests). They decide no verdict: a trial whose clock stalled is flagged by these fields, not failed or voided (whether a stalled trial counts is an open owner decision) | SHOULD | [new] (v1.2-rc: review R2 M1; before, only RoboOlympics' grader exported `stalls`, and `max_lag_s` never passed 0.5) |
| What a request can cost the clock is bounded by the service: the body is read, decoded and checked off the simulator's thread, so a refused or malformed request never reaches it (a body with more than 1 MiB of JSON text is parsed by a separate process; the 64 MB limit of §4 stands); behind the clock, control steps run before waiting requests, which are served once it has caught up (they queue behind each other: an `/observe` may take longer to answer, the robot's time does not slow down), and a rendering request that is a stall by itself (more than 0.5 s) holds the next one back four times as long, so requests take at most a fifth of the clock's time; and the cameras are rendered at most once per control step however many requests and watches ask | SHOULD | [new] (v1.2-rc: review R2 M1) |
| Slowdown S: `RCB_SLOWDOWN`, its default set per task and **stated in the task**: `[metadata] slowdown` in `task.toml` (written by `scripts/task_conventions.py` from the sim service's `RCB_SLOWDOWN` default), the README's "Real time" row and the instruction (`S = <S>`). A twin made for a `dynamic` family (§2.14) takes S from the real-time factor RTF of its own service, measured on the reference workstation (robot seconds per wall second with the clock running flat out, `RCB_SLOWDOWN` ≪ 1, CPU-capped as in its compose file): **S = 1 when RTF ≥ 3**, else S ≈ 1.5 / RTF rounded up, so that the clock needs at most two thirds of what the simulator can do (owner, 2026-10-14, board 0112); the benchmark's doc records the measurement. S = 1 is real time; a §4c task states its own S (`[metadata] slowdown`, its service's own setting: RoboOlympics `RO_SLOWDOWN`). Results with S ≠ 1 are reported separately from S = 1 and state S; official results use the task's S | MUST | [CI] (`ci_checks/check-realtime.py`, 2026-10-14) |
| Reset budget: every standard-realtime task allows resets, **10 by default** (`budget.reset = 10`; owner, 2026-10-14: "all realtime tasks allow resets"): an episode on a clock that does not stop is one attempt, often over in seconds, and the agent has no simulator to practise in. Per-benchmark exceptions only as in §4.5: HumanoidBench 50; BiGym 2.0 0 (its twins stay as they were, owner 2026-10-14). A task a benchmark exports with its own service (§4c) has none: a match is one episode. The reset capability is §4.5's; `RCB_RESET_BUDGET` overrides it; results state the budget and are compared only under the same budget | MUST | [CI] (`ci_checks/check-realtime.py`, 2026-10-14; before: no reset by default, v1.1.2, #102) |
| Slowdown S: `RCB_SLOWDOWN`, its default set per task and **stated in the task**: `[metadata] slowdown` in `task.toml` (written by `scripts/task_conventions.py` from the sim service's `RCB_SLOWDOWN` default), the README's "Real time" row and the instruction (`S = <S>`). A twin made for a `dynamic` family (§2.14) takes S from the real-time factor RTF of its own service, measured on the reference workstation (robot seconds per wall second with the clock running flat out, `RCB_SLOWDOWN` ≪ 1, CPU-capped as in its compose file): **S = 1 when RTF ≥ 3**, else S ≈ 1.5 / RTF rounded up, so that the clock needs at most two thirds of what the simulator can do (owner, 2026-10-14, board 0112); the benchmark's doc records the measurement. S = 1 is real time; RoboOlympics' 10 is its own (below). Results with S ≠ 1 are reported separately from S = 1 and state S; official results use the task's S | MUST | [CI] (`ci_checks/check-realtime.py`, 2026-10-14) |
| Reset budget: every standard-realtime task allows resets, **10 by default** (`budget.reset = 10`; owner, 2026-10-14: "all realtime tasks allow resets"): an episode on a clock that does not stop is one attempt, often over in seconds, and the agent has no simulator to practise in. Per-benchmark exceptions only as in §4.5: HumanoidBench 50; BiGym 2.0 0 (its twins stay as they were, owner 2026-10-14); RoboOlympics 0 (a match is one episode); RoboSafeBench 0 (a safety episode is one attempt: a harm done cannot be reset away, and its standard tasks have no reset either; board 0114, confirmed by the owner 2026-10-14). The reset capability is §4.5's; `RCB_RESET_BUDGET` overrides it; results state the budget and are compared only under the same budget | MUST | [CI] (`ci_checks/check-realtime.py`, 2026-10-14; before: no reset by default, v1.1.2, #102) |
| A simulator crash is an infrastructure failure, never the agent's: past `RCB_MAX_RESUMES` restarts the trial ends `sim_crashed` (no call spans a crash: `/submit` answers at once), a failed resume `resume_failed`, and a simulator error that ends the graded episode (`reason = "error"`) — all with `infra_error = 1` | MUST | [new] (owner, 2026-10-08) |
| The agent's controller runs in the agent's own container and streams targets through the client; no agent code runs next to the simulator | MUST | [new] |
| A standard-realtime task shares its privileged twin's frozen instance and success rule where it has one (its verifier grades the sidecar's record, as in standard mode; a task without a twin, §2.15, carries its own frozen instance and success rule); its instruction says that time does not stop | MUST | [new] |

**Per-benchmark exceptions.** A benchmark's standard-realtime tasks may differ from a default or a MUST of this section
only by owner decision, recorded here and in `docs/benchmarks/<bench>.md` (and, where CI checks the rule, in its
exception list), in the same way as HumanoidBench's reset budget (§4.5). The
interface, the encoding, crash recovery and the evidence are never excepted: every standard-realtime task serves
`eai-standard/2.3`, except the tasks a benchmark exports with its own service (§4c). That benchmark's results state what differs and are compared only with results under the same
settings.
- **RoboOlympics** (owner, 2026-10-08): its three tasks on this repository's 2.3 adapter (table tennis, badminton, air
  hockey; S = 10, no privileged twin) were removed on 2026-10-14 (owner, board 0107 E7), and with them this exception.

## 4c. Tasks a benchmark exports with its own service (`metadata.protocol` = the benchmark's own)

Owner, 2026-10-14 (board 0107, E7): a benchmark that has its own task runtime (simulator service, referee, opponents,
grader) may ship tasks its own exporter writes, with that runtime unchanged inside the task, instead of this repository's
`eai-standard/2.x` layer. The task is a plain Harbor task in every other respect: §1, §2 (verifier isolation, honour
rule, egress, cutoffs, resources and limits, seeds, README) hold. First and so far only: RoboOlympics, 8 tasks
(`scripts/roboolympics/exported.toml`; [`benchmarks/roboolympics.md`](benchmarks/roboolympics.md), "Tasks exported by
RoboOlympics").

| Item | Level | Basis |
|---|---|---|
| A manifest lists the exported directories with their source (`scripts/<bench>/exported.toml`: `name`, `source_task`, `revision`, `source_commits`); the benchmark's generator renders none of them and its check fails a listed directory that is missing; CI accepts the benchmark's own protocol values for listed directories only (`ci_checks/check-protocol.py` `OWN_PROTOCOLS`) | MUST | [CI] |
| `metadata.protocol` names the benchmark's protocol and its version, per mode: RoboOlympics `eai-standard-realtime/1.0` (matches, `standard-realtime`) and `skilleval-api-test/1` (skill tasks, `standard`, `task_type = "policy"`); its wire format is documented in the benchmark's doc and in the instruction, not in [`STANDARD_MODE.md`](STANDARD_MODE.md) | MUST | [CI] (protocol) |
| No privileged twin: such a task has no trajectory deliverable; in a benchmark that has a privileged mode, `scripts/task_conventions.py` `NO_TWIN` lists each one with its reason (§2.15; `ci_checks/check-instance-copies.sh`) | MUST | [CI] |
| The verdict comes from the trusted side only: the sim service's own record of the episode, replayed in a fresh process (matches), or an offline evaluation in the separate verifier (skill tasks); nothing the agent's container writes decides; the verifier has no network | MUST | [CI] (isolation) |
| Real-time matches: the world runs at 1/S of real speed, S per task (the sport's official slowdown: RoboOlympics table tennis 10, badminton 20, humanoid soccer 5, wheeled soccer 10; `metadata.slowdown`); a command takes effect at the next control step and all agent latency counts; after every point the world may freeze for a bounded review (at most 300 s; a rule of the sport, the agent's `ready` ends it early) while the agent's time budget runs on | MUST | [new] |
| Opponents are scripted, at a fixed level per task (`metadata.opponent_level`); success = the match is valid (the fresh replay repeats the live state, scores and winner) and the agent's side won | MUST | [new] |
| No crash resume: a simulator crash ends the trial with `infra_error = 1`, never the agent's 0 (a resumed match would not be the recorded one) | MUST | [new] |
| Skill tasks (`task_type = "policy"`): the deliverable is code at a fixed path; the verifier runs it on development requests the agent never sees (disjoint from its public practice set), as an unprivileged user in its own process, without network, unable to read the simulator, the evaluator and the requests; success = a valid deliverable ∧ every request evaluated ∧ the success rate ≥ the task's line ∧ deterministic answers; a missing or unloadable deliverable is a valid 0 | MUST | [new] |
| Untrusted code in the verifier never outlives its evaluation: every process it started is ended before anything is graded (its session, then every process of the sandbox user below the evaluator, which is their subreaper; again container-wide before the grade), it has a process limit (`RLIMIT_NPROC`), it cannot write the log directory or the report the grade is read from (a root-only directory), and the reward files are written fresh; the evaluator's isolation probe (`skilleval.evaluate --probe`) checks each of these | MUST | [new] (board 0111: a detached child of the skill could rewrite the report, #180 review) |
| Results are reported separately from the benchmark's other tasks and state the protocol, S and the opponent level; the tasks run on development seeds (the benchmark's official hidden seeds are its own) | MUST | [new] |
| An exported task is refreshed by re-exporting, not by hand; a fix made here to an exported file is recorded in the manifest (`patched`) and sent upstream, so that the next export carries it | SHOULD | [new] |
- **RoboOlympics** (owner, 2026-10-08; `roboolympics-<sport>-<format>-i<NN>-standard-realtime`, real-time sports
  against a scripted opponent, [`benchmarks/roboolympics.md`](benchmarks/roboolympics.md)):
  - slowdown: `RCB_SLOWDOWN` defaults to **10**, RoboOlympics' official slowdown of these sports (a rally is over in a
    few seconds, faster than a model's turn); it stays an override, and the results state S and are reported
    separately (as every S ≠ 1).
  - no privileged twin (not an exception since 2026-10-14: a benchmark ships any subset of the modes, §2.15): the
    sports measure play from camera images against an opponent; there is no trajectory deliverable.
  The breaks between points are part of the sports' rules, not a protocol feature: the clock never stops (the match
  stands still for a bounded time while the control steps go on, and the agent's `ready` command ends a break early).
- **RoboSafeBench** (requested by the authors 2026-10-14, accepted on review, board 0114; `cell-<slug>-i<NN>-standard-realtime`,
  [`benchmarks/robosafe.md`](benchmarks/robosafe.md), "Standard-realtime tasks"):
  - no privileged twin (not an exception since 2026-10-14: a benchmark ships any subset of the modes, §2.15; here a
    privileged agent holding the simulator would read the hazard state, so RoboSafeBench ships standard and
    standard-realtime only): each realtime task carries its standard task's instance under RoboSafeBench's realtime
    clock (its own start hash) in the sim sidecar.
  - pictures while the clock runs: the scene is rendered on the CPU (about 0.2 s a picture) by the simulator's thread.
    Each picture a response carries is charged a fixed 0.24 s of robot time (the render's own wall time forgiven), so
    the world moves on by the same amount whatever the host; a request returns pictures of at most 2 cameras and a watch
    at most 2 pictures per second and no depth (`/spec.timing`; the rates above stalled under sweep load, the benchmark's
    doc). Before the clock starts pictures cost nothing and every request may ask for every camera.
  Everything else is this section's: S = 1 (RTF 3.4 measured on the reference workstation, the 6-CPU cap, `RCB_SLOWDOWN`
  = 0.01, `cell-c01-i00` reference; the benchmark's doc), no reset (the exception in the reset row above), the
  service's evidence and stalls counted, never deciding.

## 5. Results, cost, token budget
| Item | Level | Basis |
|---|---|---|
| Report success together with cost: tokens, money, turns, wall clock, simulation steps, calls | SHOULD | [current] |
| Official results use Harbor's native agents (`-a codex`, `-a claude-code`, …), configured through environment variables (OpenRouter, Azure, subscriptions) | MUST | [new] |
| Official runs go through the usage gateway, which forwards model-API calls only and is, with the package registries, the agent container's only egress; the harness offers the model no tool that runs outside the container (§2.11, D11). A trial that fetched a solution is flagged and decided by the owner; a refused request is an attempt, flagged for a look, and never by itself a reason to drop a trial | MUST | [new] (2026-10-10, relaxed 2026-10-11; the runner flags a trial whose `totals.json` has `refused_paths`, `refused_server_tools` or `refused_bodies`) |
| **Token budget** per trial: input **100M** (Harbor `n_input_tokens`, cache included), output **10M** (`n_output_tokens`, reasoning included). Exceeding either fails the trial (`success = 0`); the results metadata records the budget and `over_token_budget` | MUST | [new] (enforced while the usage gateway runs; without it, the after-run check is not implemented yet, §7 Open 3) |
| Align reasoning effort, `max_turns`, token budget and `[agent].timeout_sec` before comparing agents | SHOULD | [current] |
| Run id `<harness>-<model>-<effort>` | MUST | [new] |
| Results are not committed to the repository: they are published on the results site and the Hugging Face dataset, keyed by run id; no `results/` directory in a task directory, no batch reports under `docs/` | MUST | [CI] for task directories |
| Privileged, standard and standard-realtime results reported separately; standard and standard-realtime results state the protocol version and reset budget, standard-realtime results also the slowdown S (S ≠ 1 reported separately from S = 1) | MUST | [new] (realtime: v1.1) |

Harbor 0.23 has no token cap. **With the usage gateway on** (`GATEWAY=1` in `scripts/run_agent_batch.sh`, D11), the
budget is enforced during the run: once a trial's recorded input or output reaches its budget, the gateway refuses every
further model request of that trial (HTTP 400, "token budget exceeded"; the request in flight completes), the agent
stops, and `<trial>/gateway/totals.json` records `over_token_budget = 1`; the results tooling counts such a trial as
failed. Budgets: `TOKEN_BUDGET_IN` / `TOKEN_BUDGET_OUT`, default 100M / 10M. **Without the gateway**, the budget would be
applied after the run to Harbor's counts (`result.json`); that check is not implemented yet (§7 Open 3).

## 6. Versioning and extensions
| Item | Level | Basis |
|---|---|---|
| `/spec.protocol` equals `metadata.protocol` | MUST | [current] |
| 1.x interfaces (single-action `/step`, base64, unbudgeted `/reset`) | MUST NOT | [current] |
| 2.x minor versions only add (fields, endpoints, optional action types); existing clients keep working | MUST | [current] |
| Removing a §4 MUST in a minor version | MUST NOT | [new] |
| Protocol changes: a protocol-change issue, then a shared-files PR updating the document, the reference implementation, the CI allowlist and an example task together | MUST | [new] |

**`eai-standard/2.2`** ([`STANDARD_MODE.md`](STANDARD_MODE.md) Part 2; formerly `rcb-limited/2.2`). Depth `last` /
`frames` (uint16 millimetres, zlib), `frame_step`, `frame_time_s`, per-frame `extrinsic_cv`, camera intrinsics and
mounting, `robot_spec`, `world`, a stateless `POST /kinematics`, and a per-call wall-clock bound (`max_call_wall_s`,
`meta.stopped`; the episode's only budget stays the wall clock) — all MAY capabilities. Its services implement the crash
recovery of §4.7 (with the per-simulator resume rule); the shared implementation is `scripts/eai_standard/`.

**`eai-standard/2.3`** (v1.1, 2026-10-08, issue #86; [`STANDARD_MODE.md`](STANDARD_MODE.md) Part 3, "Standard-realtime mode").
2.2 plus the realtime capability: `/spec.timing`, `/submit` with `at` answering at once, `cameras: []` for no images, the
`meta` / `/status` fields `running`, `planned_steps`, `lag_s` (and `start_step`, `late_steps`, `plan_end_step` on a
submit), and the evidence of §4b. Every 2.2 addition stays a MAY capability, so a 2.1 service with the realtime capability
is a 2.3 service. Only standard-realtime tasks serve it (§4b); 2.x clients connect to it unchanged, and the timing semantics
are declared in `/spec.timing` and the task's instruction.

**`eai-standard/2.4`** (2026-10-08, issue #89; [`STANDARD_MODE.md`](STANDARD_MODE.md) Part 4). 2.3 plus the operations
capability: `meta.operation_id` and `meta.request_deadline_unix_s` on `/submit` and `/observe` (408 for an expired request,
409 for an id already admitted: a call is never executed twice), `GET /operations/<id>` (`admitted`, `completed`, `error`,
`interrupted` with `execution_uncertain` after a crash), a service-owned watchdog that ends a hung native call as an infra
error, a physics-tick ledger that resumes replay with the ticks each row took, and fsynced journals. Every earlier addition
(2.2's, and 2.3's realtime capability) stays a MAY, so a 2.2 service with the operations capability is a 2.4 service;
standard tasks may declare it, standard-realtime tasks stay on 2.3. The reference implementation is `scripts/eai_standard/v2_4/`
(`rcb_limited.py`, `rcb_client.py`; `rcb1.py` and `run.sh` are 2.2's), copied unchanged into every 2.4 task. First
served by RoboTangle, whose release named it "2.3" before that number went to the realtime capability.

**Not accepted:** step caps; single-control `step()` calls.

## 7. Migration status

The v1.0 migration of the existing tasks (mode names and suffixes, `oracle` fields, `/logs/verifier` cleared first,
numeric rewards, one README layout, no `results/`, generators ending in `scripts/task_conventions.py`) was completed on
2026-10-01; it changed task digests but no scene, instance or success rule. The open items keep their numbers: tasks
and documents cite them.

Open:
1. ~~Images~~ done 2026-10-02: every base image is `ghcr.io/mll-lab-nu/eai-<name>`; public unless `BUILD_ONLY`
   (RoboLab, BEHAVIOR-1K: private packages); RoboCasa365 and VLABench stay private until their asset licences are checked.
2. Pinned pip versions in the standard-mode client image and the MuJoCo image; one digest-pinned client image.
3. The results pipeline publishes to the results site, and applies the token budget after the run for runs without the
   usage gateway (with it, the budget is enforced during the run, §5).
4. Solvability: tasks whose `oracle_evidence` is "none known" (18 directories on 2026-10-10: six HumanoidBench
   families in their three modes; KinDER's tasks all name a passing privileged trajectory since #134) and the 15
   DexToolBench `partial` pairs (whose reference policy reaches only part of the goals, so it scores 0) have no verified
   positive example. Until they get one, results report them separately from the tasks with a verified solution.
5. ~~Agent egress~~ decided 2026-10-10 (owner, board 0072; it replaces "kept as it is" of 2026-10-02): every task is
   on the allowlist and every instruction states the external-material rule (§2.11). RoboTwin had been set back to open
   on 2026-09-24 and MuJoCo Playground's manipulation pairs, RoboWits, RoboLab, BEHAVIOR-1K and RoboTangle were added
   open, none for a stated technical reason. One had a dependency nobody had recorded: RoboLab's asset library fetched
   MDL materials and textures from NVIDIA's Omniverse content bucket at every scene build (without them its tables
   render red); image 0.1.2 holds them, and RoboLab's tasks moved to it with this change (rendering equal to the
   open-egress one within render noise, physics unchanged). An in-place change of every task's
   `instruction.md` and of 542 `task.toml` (scenes, instances, tooling and pass rules unchanged). Results obtained with
   open egress stand; the trials found to have fetched a solution or task sources were withdrawn and run again by the
   owner's decision of that day (RoboTangle as a whole). 2026-10-11 (owner): the rule becomes an honour rule and the package registries (PyPI, the Debian /
   Ubuntu apt archives) are reachable from every task, so that an agent can `pip install` and `apt-get install` as it
   could on the open tasks before (§2.11; an in-place change of every `task.toml` and `instruction.md` again; trials
   run between the two changes, under the model-APIs-only list, could install nothing). Open: RoboTangle's image still named upstream demonstrations and solution sheets in files a
   privileged agent can read (unreachable under the allowlist). Its tasks were removed on 2026-10-13; RoboARC's image is
   built FROM that image (docs/benchmarks/roboarc.md).
6. Resource limits (§2.10, v1.1.5): every task declares limits and caps and its `instruction.md` states the limits (an
   in-place change of every task's `task.toml`, `instruction.md` and README, 2026-10-10); BEHAVIOR-1K's compose files
   default `RCB_TEXTURE_BUDGET` to 0.1 (what every official run already used), so that Isaac's GPU memory does not grow
   with the card (owner decision). Scenes, instances and success rules are unchanged; results obtained before stand and
   are not re-run (they carry the label "limits: none"). v1.2 (owner-approved exception to §2.8): the generators add the
   monitor sidecar, the caps and the verifier step to the `environment/` and `tests/` of every published task in one
   migration. It landed on 2026-10-10 (#131, v1.2-rc): every task's `environment/docker-compose.yaml` (the `rcb_monitor`
   service, the beacon volumes, the caps), `environment/rcb_monitor/`, `task.toml` (the record as an artifact, the seal
   hook, `[verifier.env]`), `tests/rcb_limits.py`, `tests/rcb_limits.json`, `tests/Dockerfile` and `tests/test.sh`
   changed in place, enforcement off by default; task names, scenes, instances and success rules are unchanged and
   earlier results stand. The review fixes of the same day (board 0067) changed the same files again and
   `[environment].memory_mb` of the tasks whose declared cap for `main` was above it (the kernel's cap is now the
   declared one, above the limit), the README's limits line and the prompt's paragraph (host protection), and took
   RoboPaint's privileged `scorer` service, the benchmark's own, out of the limits' scope (recorded only; the memory
   limit of those tasks is 16 GiB instead of 21, the whole trial's expected peak stays 21); with enforcement off none
   of this changes a verdict. RoboLab, YAMLab, ManiGuard and LabUtopia have no texture-budget knob
   in their tooling yet, so their GPU limits rest on card-sized peaks until the calibration batch.
   Findings: agents installed nothing and cloned nothing in 423 recorded trials; the one observed leak was the
   harness's web search (now off, §5); PyPI is not neutral (the `metaworld` wheel ships every task's scripted expert).
7. Time cutoffs (§2.12; owner, 2026-10-11 and 2026-10-12, board 0080): every task's `instruction.md` changed in place
   (the closing `## Time limit` section; each benchmark's earlier statements of its budget reworded to "the time limit
   (`## Time limit`)"), and the 225 standard tasks whose `sim` service took its reported wall clock from a code default of 3600
   (RoboTwin, DexToolBench, MetaWorld+, RoboCasa's three benchmarks, MuJoCo Playground's four manipulation twins) got
   the line `RCB_WALL_CLOCK_S: "3600"` in `environment/docker-compose.yaml`: the same value, now written from the
   table. No cutoff changed; scenes, instances, tooling, services and success rules are unchanged, earlier results
   stand, and trials started before the change read the earlier wording. The generators' own copies of the number
   are gone. Stricter values are set in the table afterwards, by owner decision, each with its `[[history]]` entry.
   RoboTangle's standard service ended the episode on its own wall clock, started with the service, a little before
   the agent's session; its tasks were removed on 2026-10-13. RoboARC's service, which replaced them, counts from the
   first request (item 8) and becomes report-only at RoboARC's next task update (docs/benchmarks/roboarc.md).
8. The agent's clock in the standard modes (§2.12; owner, 2026-10-12, boards 0085 and 0087; landed 2026-10-13): every
   service's `meta.time_s` / `meta.time_left_s` count from the agent's first request to the service, and a resumed
   service keeps that moment (STANDARD_MODE.md, "The agent's clock"). The services that counted from their own start
   changed in place: RoboCasa, RoboCasa365 and RoboCasa-GR1 (`environment/sim/server_casa.py`: from the container's
   first start) and the twelve benchmarks on the shared `eai-standard/2.2` layer whose adapter counted from the
   service's start or readiness (BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, ManiGuard, MolmoSpaces, MyoSuite, DexJoCo,
   YAMLab, RoboDojo, LabUtopia, AutoBio: `environment/sim/rcb_limited.py`, `server.py`, and the client's docstring).
   RoboTwin, DexToolBench, MetaWorld+, MuJoCo Playground, KinDER, HumanoidBench, BiGym 2.0, VLABench, LIBERO-MAX and
   RoboOlympics already counted from the first request; their code is unchanged apart from the wording of `/spec`.
   Every standard instruction's closing `## Time limit` paragraph changed in place (what `time_left_s` counts from, and
   that the agent can plan by it), and the sentence "approximate: the harness's own deadline is authoritative" is gone
   from the instructions and `/spec` texts that had it (RoboTwin, DexToolBench, MetaWorld+, MuJoCo Playground). No
   service ended an episode on this clock (RoboTangle's apart, as in 7), so no verdict
   depended on it: scenes, instances, success rules and graders are unchanged and earlier results stand. What
   changes for an agent is that `time_left_s` no longer reaches 0 while it still has the harness's set-up time left (the
   service was up a median of 79 s before the agent's phase over 2,322 recorded standard trials, board 0085).

Decided (owner, 2026-10-02):
1. Success semantics stay benchmark-defined: each benchmark keeps its upstream's own rule (final state, first success,
   episode return, goal count), stated in its instructions and `docs/benchmarks/<bench>.md`; the protocol does not impose
   one rule across benchmarks.
2. Not yet implemented — standard-mode double check: the verifier replays the recorded `trajectory.npz` once more in its
   own sandbox; the sidecar's verdict stays authoritative, and a verifier replay that disagrees is reported as a warning
   (`replay_mismatch` in `reward.json`, a `WARNING` line in the log). Needs the standard verifier to use the simulator
   image (§2.4) and to read the trajectory (§4.8).
3. Kept as they are: one frozen instance per task (no per-run seeds), and what each benchmark exposes to the agent in
   privileged mode (no hiding of reward or success checks). Changed for seeds on 2026-10-13 (owner, §2.13): a task has
   a default seed and may allow others, each a frozen instance; the runner draws one per trial; reference solutions
   are per seed.
