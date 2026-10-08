# Robot Coding Bench — Task Protocol v1.1.2

Status: **final** (2026-09-30; v1.0.1 2026-10-01: both modes carry a suffix, no results in the repository, standard
task README; **v1.1 2026-10-08: a third mode (§4b), served by `eai-standard/2.3`; protocol-change issue #86; v1.1.1 2026-10-08: the third mode is named
`standard-realtime`, issue #97; v1.1.2 2026-10-08: the standard-realtime mode's default reset budget is 0, as in standard
mode, and HumanoidBench's 50 is a per-benchmark exception, issue #102**).
The tasks in the repository follow it except for the open items in §7. The wire format of standard mode is specified in
[`LIMITED_MODE_PROTOCOL.md`](LIMITED_MODE_PROTOCOL.md) (`eai-standard/2.1`, and the standard-realtime mode's `eai-standard/2.3`);
its 2.2 extension in [`STANDARD_MODE_2_2.md`](STANDARD_MODE_2_2.md), and the 2.4 operations capability in
[`STANDARD_MODE_2_4.md`](STANDARD_MODE_2_4.md) (2026-10-08, issue #89).

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
listed in §7); **[new]** introduced by v1.0 — required for new work, partly enforced by `ci_checks/check-protocol-v1.py`,
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
| D1 | Standard-mode protocol | Only `eai-standard/2.x`. Additive extensions are accepted through a protocol-change PR (2.2 is accepted once its services implement crash recovery). Reset is only an optional capability (`budget.reset = N`, default 0; results with N > 0 are reported separately). Documented per-benchmark exception (owner, 2026-10-07): HumanoidBench standard defaults to N = 50 (§4.5). The standard-realtime mode's `eai-standard/2.3` (§4b) is 2.2 plus the realtime capability. `eai-standard/2.4` (issue #89) is 2.3 plus the operations capability; standard tasks may use it. No step caps. |
| D2 | Tasks without an oracle | Allowed, with mandatory human review (§2.7). |
| D3 | Results | Not in the repository: agent results (per-task READMEs, videos, timelines, batch tables) are published on the results site and the Hugging Face dataset; a task directory has no `results/`. |
| D4 | Run id | `<harness>-<model>-<effort>`, model token with underscores (`codex-gpt6_luna-xhigh`); provider, tier and settings go in metadata. |
| D5 | Images | One registry (EAI organization), images named `eai-<name>` and versioned in `images/<name>/VERSION`; every image that may be redistributed is public, the rest are `BUILD_ONLY`. One image per **benchmark**, not per simulator: benchmarks on the same simulator may need different versions of it and of its dependencies (e.g. RoboCasa, RoboCasa365 and RoboCasa-GR1 on robosuite), so each may have its own image; an image is shared only where the dependency set is identical. |
| D6 | PR granularity | One benchmark per PR; changes to shared files go in a separate PR reviewed by a maintainer. |
| D7 | World-frame information in instructions | Decided per benchmark, consistent within it, documented in the benchmark's doc. |
| D8 | Agent time budget | 3600 s by default, at most 14400 s; longer budgets are justified, uniform within a benchmark, and results are grouped by budget. Documented per-benchmark exceptions to the cap (§2.3): RoboTangle 21600 s (owner, 2026-10-08). |
| D9 | Shared code | Shared sources are copied into tasks by the generator; nothing at run time imports repository code outside the task directory. |
| D10 | Token budget | Per trial: **100M input tokens, 10M output tokens** by default; exceeding either fails the trial. |
| D11 | Harness | Official results use Harbor's native agents only; no agent adapters, and no gateway that holds credentials or changes requests. A transparent usage gateway that forwards requests unchanged and only records token usage (`scripts/usage_gateway/`) is allowed. |
| The harness's web search is off in official runs: Codex `web_search = "disabled"` (Harbor `--ak web_search=disabled`), Claude Code `WebSearch` and `WebFetch` disallowed (`--ak disallowed_tools=WebSearch,WebFetch`). The search runs at the model provider, so no egress allowlist stops it; `scripts/run_agent_batch.sh` sets both by default (`WEB_SEARCH=disabled`) | MUST | [new] (2026-10-02: tested with Codex 0.159.2 and gpt-6-luna — with ChatGPT login the default searches GitHub and quotes upstream experts, `disabled` stops it; with an Azure API key Codex offers no search, but the API runs one for a request that carries the `web_search` tool, which only the usage gateway's raw log can reveal) |
| D12 | Mode naming | `mode ∈ {privileged, standard, standard-realtime}` (the third mode since v1.1, #86; named `standard-realtime` since v1.1.1, owner 2026-10-08, #97: it is standard mode's robot as a service on a clock that does not stop); the `tier` field is removed; every task directory ends in its mode: `-privileged`, `-standard` or `-standard-realtime`. |

## 1. Checklist (every task)

1. `task.toml`, `instruction.md`, `README.md`, `environment/Dockerfile`, `tests/test.sh` (executable), `tests/Dockerfile`. [CI] `solution/solve.sh` depending on the oracle level (§2.7). [new]
2. `[task].name = "robot-coding-bench/<folder>"`; required metadata present and valid (§2.3). [CI]
3. Top-level `artifacts` includes `"/app/output/"`; `[agent].timeout_sec` set and ≤ 14400, or ≤ the benchmark's documented exception (§2.3). [CI]
4. Every image reference pinned to a tag or digest, never `:latest`. [CI]
5. `[verifier] environment_mode = "separate"`; `tests/Dockerfile` copies `test.sh`. [CI]
6. `instruction.md` names the deliverable under `/app/output/` and never mentions `/tests/`. [CI]
7. Listed in `tasks/dataset.toml`. [CI]
8. The verifier writes `reward.txt` (1/0) and a numeric-only `reward.json` with at least `success` (and `deterministic` for trajectory tasks). [current]
9. Same verdict in a fresh process; the verifier does not need the network (standard-mode verifiers run with `no-network`). [current]
10. Reference solutions only under `solution/`; nothing the agent can reach contains or points to one. [current]
11. `nop` scores 0; with an oracle, the oracle scores 1; without one, human review (§2.7). [new]
12. A published task's `environment/` and `tests/` inputs never change; a change is a new task. [current]
13. The directory name ends in `-privileged`, `-standard` or `-standard-realtime`, matching `mode` (§2.2); no `results/` directory (D3). [CI]
14. `README.md` in the standard layout (§2.1). [CI] (sections and key rows; `scripts/task_conventions.py --check` for the rest)
15. Runs with Harbor's native agents; no custom runner or adapter, and no gateway beyond the recording-only usage gateway (D11). [new]
16. Standard-mode tasks also satisfy every MUST in §4; standard-realtime tasks every MUST in §4 and §4b.

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
| `README.md` in the standard layout: `# <directory name>`; a key table with Benchmark, Mode, Twin, Simulator / robot, Family / instance, Oracle, Agent time budget, Base image; then `## Task`, `## Difficulty`, `## Reference solution`, `## Verification`, and `## Details` for anything else (extra rows, notes, provenance). No results in the README | MUST | [CI] |

### 2.2 Naming
| Item | Level | Basis |
|---|---|---|
| Privileged tasks: `<base>-privileged`, where `<base>` is `<benchmark>-<family>-i<NN>` (`metaworldplus-<env>-i00`, `kinder-<family>-i00`, `humanoidbench-<category>-<task>-i00`) or an upstream name kept as is (`robotwin_2_0_<task>`, `dextoolbench_<cat>_<obj>_<task>`, `mujoco_playground_<env>`) | MUST | suffix [CI] |
| Standard tasks: `<base>-standard`, sharing the privileged twin's frozen instance and `instance_seed` | MUST | suffix [CI]; shared instance [current] |
| Standard-realtime tasks: `<base>-standard-realtime`, sharing the privileged twin's frozen instance and `instance_seed`; its twin is `<base>-privileged` (a benchmark that has standard-realtime tasks usually has `<base>-standard` too) | MAY (the mode) / MUST (the name) | suffix and instance [CI] [new] (v1.1) |
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
| `instance_seed`; benchmark-specific fields registered in TAXONOMY | MAY | [current] |
| Top-level `artifacts` includes `"/app/output/"` | MUST | [CI] |
| `[agent].timeout_sec` set, ≤ 14400 (per-benchmark exceptions below); 3600 unless justified (uniform within a benchmark) | MUST / SHOULD | [CI] / [new] |
| `[verifier].environment_mode = "separate"` | MUST | [CI] |
| `[verifier].timeout_sec`, `[environment]` `cpus` / `memory_mb` / `build_timeout_sec` | SHOULD | [current] |
| `[environment].gpus` (unsupported by Harbor's local Docker sandbox; see §2.4) | MUST NOT | [current] |

**Per-benchmark agent budget exceptions.** A benchmark's tasks may set `[agent].timeout_sec` above 14400 s only by owner
decision. The decision is recorded here, in `docs/benchmarks/<bench>.md`, and in the exception table of
`ci_checks/check-task-fields.sh`. The budget is uniform within the benchmark, in both modes. A standard sidecar's wall
clock (`RCB_WALL_CLOCK_S`, `/spec.budget.wall_clock_s`) equals it. That benchmark's results state the budget and are
compared only with results under the same budget (D8). The token budget (D10) is unchanged.
- **RoboTangle** (owner, 2026-10-08; issue #87): 21600 s (6 h) for every task. The topological puzzles are much
  harder than typical robotics tasks (reference executions take 2–185 min of simulated work), and the benchmark's
  owner sets the budget to probe the capability ceiling. Simulator speed-ups add interaction within it; they never
  shorten it (`docs/benchmarks/robotangle.md`, added with the tasks in #81).

### 2.4 Images, registry, GPU

A base image is defined by `images/<name>/Dockerfile` and tagged `<registry>/eai-<name>:<images/<name>/VERSION>`; `<name>` is
usually the benchmark (`eai-robocasa365`) or the simulator stack several benchmarks share (`eai-mujoco`). `scripts/build_images.sh` builds every image as
`ghcr.io/mll-lab-nu/eai-<name>` and `scripts/push_images.sh` pushes all but the `BUILD_ONLY` ones. Tasks reference it by tag:
`environment/Dockerfile` and `tests/Dockerfile` `FROM` it, and the standard-mode `sim` service uses it as `image:`.
Harbor builds the task images locally from the task directory on every run; only base images are pulled.

| Item | Level | Basis |
|---|---|---|
| Base images at `ghcr.io/mll-lab-nu/eai-<name>:<ver>`, anonymously pullable, unless `BUILD_ONLY` | MUST | [new] (registry: `legacy:` warning in CI) |
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
| States the time budget and tells the agent to save a deliverable early and not to stop early | SHOULD | [new] |
| Gives the success predicate's exact parameters | MAY | [current] |
| World-frame quantities (coordinates, table height): decided per benchmark, consistent within it, documented | MUST | [new] |
| Written by a human | SHOULD | [current] |

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
| `test.sh` first clears `/logs/verifier` (`rm -rf /logs/verifier/*`); named volumes crossing the trust boundary are named `*_trusted` | MUST | clearing [CI]; volume names [new] |

`reward.json` field names (use these whenever the concept applies; no synonyms):

| Field | Level | Meaning |
|---|---|---|
| `success` | MUST | 1 iff the deliverable completes the task |
| `deterministic` | MUST (trajectory tasks) | repeated verification agreed |
| `infra_error` | MUST (standard) / MAY | infrastructure failure, not the agent's |
| `sim_error` | SHOULD (standard) | the episode ended with a simulator error (`reason = "error"`, §4.6) |
| `grader_error`, `missing_trajectory` / `missing_log` | SHOULD | diagnosable failure modes |
| `n_actions`, `sim_steps` (or `control_steps`), `video_rendered` | SHOULD | size of the deliverable, simulation cost, video present |
| `final_reward`, `progress`, `live_success`, `replay_success`, `live_video`, `live_frames`, `sim_startups`, `finalized`, `elapsed_s`, `agent_*` | MAY | when the concept exists |

### 2.7 Reference solutions, oracle, nop
| Item | Level | Basis |
|---|---|---|
| Reference solutions only under `solution/` (mounted for the oracle agent only) | MUST | [current] |
| A solution, or a pointer to one, anywhere the agent can reach (task image, base image, tooling, docs in the container) | MUST NOT | [current] |
| Upstream experts scrubbed from images (e.g. RoboTwin `play_once`) | MUST | [current] |
| Agent egress allowlisted in `task.toml` when a solution is publicly downloadable | SHOULD | [current] for DexToolBench, KinDER, HumanoidBench, MetaWorld+, RoboPaint, VLABench, RoboCasa, RoboCasa365, RoboCasa-GR1, MolmoSpaces, MyoSuite and DexJoCo; RoboTwin, MuJoCo Playground, RoboWits, RoboLab, BEHAVIOR-1K and RoboTangle are open by default and switched per run with `scripts/set_agent_egress.py` (allowlist contents under review, §7) |
| `nop` scores 0 | MUST | [current] |
| `oracle = "full"`: the oracle scores 1 | MUST | [current] |
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
| Listed in `tasks/dataset.toml` (re-run `harbor add --scan` after any change) | MUST | [CI] |
| A published task's `environment/` and `tests/` inputs are immutable; a change is a new task | MUST | [current] |
| Fixes to existing tasks add a Change Log entry to the task README with before/after runs | SHOULD | [new] |

## 3. Privileged mode (`mode = "privileged"`, `task_type = "trajectory"`)

| Item | Level | Basis |
|---|---|---|
| Deliverable `/app/output/trajectory.npz` (format defined by the task's instruction) | MUST | [current] |
| The generating script at `/app/output/gen.py` | SHOULD | [current] |
| Graded by open-loop replay from the frozen initial state in a fresh process | MUST | [current] |
| ≥ 2 replays with matching final-state hashes, reported as `deterministic` | SHOULD (the field is MUST) | [current] |
| Success judged on the state at the end of the replay ("success at any step" needs a stated reason) | SHOULD | [current] |
| The frozen instance copied into both `environment/` and `tests/` with its expected initial-state hash, checked on rebuild | SHOULD | [current] |
| A hash check before moving to new hardware. Reference hardware is an RTX 4090: `place_a2b_left`, `place_a2b_right`, `place_object_scale` and `place_object_stand` rebuild to a different state on an L40S, and grading there reports `grader_error` | SHOULD | [current] |
| Unlimited resets, privileged state, planning primitives, self-replay | MAY | [current] |
| Tool API shape | task-defined | [current] (recommended: `Session` with `reset` / `replay` / `status` / `save_trajectory`) |
| Self-reported cost (resets, simulation steps) in `agent_*` fields | SHOULD | [current] |
| `task_type = "policy"` | MAY | rules defined with the first such task |

## 4. Standard mode (`mode = "standard"`): `eai-standard/2.x`

Wire details (endpoints, RCB1 frames, `meta`, error codes, crash recovery) are in
[`LIMITED_MODE_PROTOCOL.md`](LIMITED_MODE_PROTOCOL.md) (2.1), [`STANDARD_MODE_2_2.md`](STANDARD_MODE_2_2.md) (2.2) and
[`STANDARD_MODE_2_4.md`](STANDARD_MODE_2_4.md) (2.4). This section lists what is required.

### 4.0 Versions
| Version | Date | Content |
|---|---|---|
| rcb-limited/1.0 (retired) | 2026-09-22 | `POST /reset` with a budget, `POST /step` one action, base64 images |
| rcb-limited/2.0 | 2026-09-24 | no reset; `/submit` action chunks, `/observe`; binary RCB1 responses |
| rcb-limited/2.1 | 2026-09-27 | 82-column proprioception, optional depth noise; crash recovery added 2026-09-29 (no version bump) |
| **eai-standard/2.1** | 2026-09-30 | rename only; identical to rcb-limited/2.1 including crash recovery. **Current.** |
| eai-standard/2.2 | 2026-10-01 | additive extension (§6, [`STANDARD_MODE_2_2.md`](STANDARD_MODE_2_2.md)) with crash recovery; served by BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, MolmoSpaces, MyoSuite and DexJoCo |
| eai-standard/2.3 | 2026-10-08 | 2.2 + the realtime capability (§4b; [`LIMITED_MODE_PROTOCOL.md`](LIMITED_MODE_PROTOCOL.md), "Standard-realtime mode"); every 2.2 addition stays a MAY. Served by standard-realtime tasks only (HumanoidBench); standard tasks stay on 2.1 / 2.2. Issue #86 |
| eai-standard/2.4 | 2026-10-08 | 2.3 + the operations capability ([`STANDARD_MODE_2_4.md`](STANDARD_MODE_2_4.md)): operation ids and request deadlines (408 / 409), `GET /operations/<id>`, a service-owned call watchdog, a physics-tick ledger, fsynced journals; every earlier addition, the realtime capability included, stays a MAY. Served by standard tasks (RoboTangle); reference implementation `scripts/eai_standard/v2_4/`. Issue #89 |

Standard services report `eai-standard/2.1`, `eai-standard/2.2` or `eai-standard/2.4`, standard-realtime services `eai-standard/2.3`; the shipped clients
accept every 2.x version and the former `rcb-limited/2.x` spelling as well.

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
| Robot proprioception, camera calibration, task text | MAY | [current] |

**Per-benchmark reset defaults.** A benchmark's standard or standard-realtime tasks may default to a reset budget N > 0 only by owner
decision, recorded here and in `docs/benchmarks/<bench>.md`; the capability is the one above (`POST /reset`, only the
last episode graded, a success ends the trial: [`LIMITED_MODE_PROTOCOL.md`](LIMITED_MODE_PROTOCOL.md)), the budget stays an override (`RCB_RESET_BUDGET`), and that benchmark's
results must state the reset budget and are compared only with results under the same budget.
- **HumanoidBench** (owner, 2026-10-07; its standard-realtime tasks too, 2026-10-08): `budget.reset = 50`. The H1 falls within 1–3 s of robot time and the agent has
  no simulator to practise in, so a single episode is one blind attempt. `RCB_RESET_BUDGET=0` still runs one episode;
  HumanoidBench standard results recorded before 2026-10-07 ran with 0 and are reported separately
  ([`benchmarks/humanoidbench.md`](benchmarks/humanoidbench.md)).

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
| Per-simulator resume rule: a simulator declared nondeterministic compares and records the hash, and a mismatch continues the same episode with `resume_state_mismatch` (unless the robot diverged grossly), as in [`STANDARD_MODE_2_2.md`](STANDARD_MODE_2_2.md) §13.1; the verdict still comes from fresh replays of the whole recorded trajectory | MAY | [new] (2.2) |

### 4.8 Evidence and grading
| Item | Level | Basis |
|---|---|---|
| The sidecar writes `/data/episode.jsonl`, `/data/trajectory.npz` and `/data/final.json` (with `finalized`) | MUST | [current] |
| `/data/calls/NNNNNN/`, `replay.mp4`, `replay.last.png` | SHOULD | [current] |
| `artifacts` declares the evidence from `service = "sim"` and keeps `"/app/output/"` | MUST | [current] |
| `[[verifier.collect]]` waits for `server.pid`, sends SIGUSR1, waits for `finalized` | MUST | [current] |
| Needing a custom agent adapter to finish an episode | MUST NOT | [new] |
| A fresh replay decides: `success = replay_success ∧ deterministic` | MUST | [current] |
| `∧ live_success` when a live predicate exists | SHOULD | [current] |
| The verifier grades `final.json` only, without network access | MUST | [current] |

### 4.9 Live recording (sidecar only)
`live.mp4`, `live_timeline.jsonl`, `live_segments.jsonl`, `trajectory_live.f64`, `startups.jsonl` — SHOULD
(implemented for RoboTwin). If recorded: rendered from the replay by default, frames stamped with the call, never
affecting the verdict.

## 4b. Standard-realtime mode (`mode = "standard-realtime"`): `eai-standard/2.3`

Standard mode on a clock that does not stop (v1.1; owner, 2026-10-08; issue #86). Everything in §4 holds (sidecar
topology, endpoints, RCB1, actions, privileged information, crash recovery, evidence, replay grading) except where this
section says otherwise. Wire details: [`LIMITED_MODE_PROTOCOL.md`](LIMITED_MODE_PROTOCOL.md), "Standard-realtime mode". The time model
is the one proposed in #41 (the world runs at 1/S of real speed, a command takes effect at the next control step, all
agent latency counts, the agent's own program may act), on the 2.x endpoints and without its proxy (D11).

| Item | Level | Basis |
|---|---|---|
| `protocol = "eai-standard/2.3"`; `/spec.timing` with `realtime: true`, `slowdown`, `control_dt`, `wall_s_per_control_step`, `max_ahead_steps` | MUST | [CI] (protocol) [new] |
| An episode starts paused; its clock starts at its first `/submit` (or `/observe` with `seconds > 0`) and then runs one control step every `control_dt` × S s of wall time, whatever the agent does, until the episode ends; after a reset or a crash recovery the episode is paused again | MUST | [new] |
| `/submit` writes a plan of future targets from control step `at` (default: the next one) and answers at once; rows whose steps have run are dropped (`late_steps`); the last target is held when the plan runs out | MUST | [new] |
| Grading replays the targets the simulator **applied** at each control step (the journal), so the replay equals the live run whatever the timing; latency and jitter are recorded (`ticks.f64`; `max_lag_s`, `stalls`, `held_steps`, `late_steps` in `final.json`) and never decide the verdict | MUST | [new] |
| Slowdown S: `RCB_SLOWDOWN`, default **1** (real time; per-benchmark exceptions below: RoboOlympics 10). Results with S ≠ 1 are reported separately from S = 1 and state S; official results use S = 1, or the benchmark's documented S | MUST | [new] |
| Reset budget: **no reset by default** (`budget.reset = 0`), as in standard mode; per-benchmark exceptions only as in §4.5 (HumanoidBench: 50). The reset capability is §4.5's; `RCB_RESET_BUDGET` overrides it; results state the budget and are compared only under the same budget | MUST | [new] (v1.1.2, #102: v1.1 and v1.1.1 wrongly made HumanoidBench's 50 the mode's default) |
| A simulator crash is an infrastructure failure, never the agent's: past `RCB_MAX_RESUMES` restarts the trial ends `sim_crashed` (no call spans a crash: `/submit` answers at once), a failed resume `resume_failed`, and a simulator error that ends the graded episode (`reason = "error"`) — all with `infra_error = 1` | MUST | [new] (owner, 2026-10-08) |
| The agent's controller runs in the agent's own container and streams targets through the client; no agent code runs next to the simulator | MUST | [new] |
| A standard-realtime task shares its privileged twin's frozen instance and success rule (its verifier grades the sidecar's record, as in standard mode; a benchmark without a privileged mode only by the exception below); its instruction says that time does not stop | MUST | [new] |

**Per-benchmark exceptions.** A benchmark's standard-realtime tasks may differ from a default or a MUST of this section
only by owner decision, recorded here and in `docs/benchmarks/<bench>.md` (and, where CI checks the rule, in its
exception list), in the same way as HumanoidBench's reset budget (§4.5) and RoboTangle's agent budget (§2.3). The
interface, the encoding, crash recovery and the evidence are never excepted: every standard-realtime task serves
`eai-standard/2.3`. That benchmark's results state what differs and are compared only with results under the same
settings.
- **RoboOlympics** (owner, 2026-10-08; `roboolympics-<sport>-<format>-i<NN>-standard-realtime`, real-time sports
  against a scripted opponent, [`benchmarks/roboolympics.md`](benchmarks/roboolympics.md)):
  - slowdown: `RCB_SLOWDOWN` defaults to **10**, RoboOlympics' official slowdown of these sports (a rally is over in a
    few seconds, faster than a model's turn); it stays an override, and the results state S and are reported
    separately (as every S ≠ 1).
  - no privileged twin: the sports measure play from camera images against an opponent; there is no trajectory
    deliverable. `ci_checks/check-instance-copies.sh` and `scripts/task_conventions.py` (`NO_TWIN`) exempt exactly
    these tasks.
  The breaks between points are part of the sports' rules, not a protocol feature: the clock never stops (the match
  stands still for a bounded time while the control steps go on, and the agent's `ready` command ends a break early).

## 5. Results, cost, token budget
| Item | Level | Basis |
|---|---|---|
| Report success together with cost: tokens, money, turns, wall clock, simulation steps, calls | SHOULD | [current] |
| Official results use Harbor's native agents (`-a codex`, `-a claude-code`, …), configured through environment variables (OpenRouter, Azure, subscriptions) | MUST | [new] |
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

**`eai-standard/2.2`** ([`STANDARD_MODE_2_2.md`](STANDARD_MODE_2_2.md); formerly `rcb-limited/2.2`). Depth `last` /
`frames` (uint16 millimetres, zlib), `frame_step`, `frame_time_s`, per-frame `extrinsic_cv`, camera intrinsics and
mounting, `robot_spec`, `world`, a stateless `POST /kinematics`, and a per-call wall-clock bound (`max_call_wall_s`,
`meta.stopped`; the episode's only budget stays the wall clock) — all MAY capabilities. Its services implement the crash
recovery of §4.7 (with the per-simulator resume rule); the shared implementation is `scripts/eai_standard/`.

**`eai-standard/2.3`** (v1.1, 2026-10-08, issue #86; [`LIMITED_MODE_PROTOCOL.md`](LIMITED_MODE_PROTOCOL.md), "Standard-realtime mode").
2.2 plus the realtime capability: `/spec.timing`, `/submit` with `at` answering at once, `cameras: []` for no images, the
`meta` / `/status` fields `running`, `planned_steps`, `lag_s` (and `start_step`, `late_steps`, `plan_end_step` on a
submit), and the evidence of §4b. Every 2.2 addition stays a MAY capability, so a 2.1 service with the realtime capability
is a 2.3 service. Only standard-realtime tasks serve it (§4b); 2.x clients connect to it unchanged, and the timing semantics
are declared in `/spec.timing` and the task's instruction.

**`eai-standard/2.4`** (2026-10-08, issue #89; [`STANDARD_MODE_2_4.md`](STANDARD_MODE_2_4.md)). 2.3 plus the operations
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

Done (2026-10-01):
1. Modes and names: every task ends in `-privileged` or `-standard`; `mode` set, `tier` removed;
   `rcb-limited/2.1` → `eai-standard/2.1` in `task.toml`, the services' `/spec` and the instructions; `rcb_client.py`
   accepts both spellings.
2. `oracle` / `oracle_evidence` on every task (DexToolBench: full on 6, partial on 15; KinDER: full on 1, none on 10;
   HumanoidBench: full on 1, none on 23 — the non-full ones need human review).
3. `/logs/verifier` cleared at the start of every `tests/test.sh`.
4. `reward.txt` is `success` (1/0) for DexToolBench and the MuJoCo standard tasks, with `progress` in `reward.json`; the
   MuJoCo standard grader writes no string fields.
5. The MuJoCo privileged tasks use the same image tag as their standard twins (`rcb-mujoco:0.1.2`: same physics and state
   hashes as 0.1.1, plus GPU EGL rendering).
6. No `results/` in any task and no batch reports under `docs/` (results live on the results site); every task README in
   the standard layout.
7. Services: a 500 ends the episode (`reason = "error"`), bodies over 64 MB get 413, RoboTwin's `/spec` states the end
   condition (`episode`).
8. CI: every rule of `check-protocol-v1.py` except the image registry (`legacy:`) fails a PR; `static-checks` also runs
   `scripts/task_conventions.py --check` and the KinDER and HumanoidBench `gen_tasks.py check`.
9. Generators (`scripts/robotwin_mk_*.py`, `dtb_mk_task.py`, `mj_mk_limited.py`, `scripts/{kinder,humanoidbench}/gen_tasks.py`)
   emit the v1.0 names and finish with `scripts/task_conventions.py` (`normalize`), which applies the conventions above
   (fields, protocol spelling, test.sh, graders, README layout, no `results/`); `--check` reports a task it would change.
   Results tooling writes outside the repository (`write_task_results.py --out`).

These edits change task digests but not scenes, instances or success rules; no separate re-run was made for them.

Open:
1. ~~Images~~ done 2026-10-02: every base image is `ghcr.io/mll-lab-nu/eai-<name>`; public unless `BUILD_ONLY`
   (RoboLab, BEHAVIOR-1K: private packages); RoboCasa365 and VLABench stay private until their asset licences are checked.
2. Pinned pip versions in the standard-mode client image and the MuJoCo image; one digest-pinned client image.
3. The results pipeline publishes to the results site, and applies the token budget after the run for runs without the
   usage gateway (with it, the budget is enforced during the run, §5).
4. Solvability: tasks whose `oracle_evidence` is "none known" (38 privileged/standard directories) and the 15
   DexToolBench `partial` pairs (whose reference policy reaches only part of the goals, so it scores 0) have no verified
   positive example. Until they get one, results report them separately from the tasks with a verified solution.
5. Agent egress (owner, 2026-10-02: kept as it is): the per-benchmark settings stay; the harness's web search is off (§5).
   Findings: agents installed nothing and cloned nothing in 423 recorded trials; the one observed leak was the
   harness's web search (now off, §5); PyPI is not neutral (the `metaworld` wheel ships every task's scripted expert).

Decided (owner, 2026-10-02):
1. Success semantics stay benchmark-defined: each benchmark keeps its upstream's own rule (final state, first success,
   episode return, goal count), stated in its instructions and `docs/benchmarks/<bench>.md`; the protocol does not impose
   one rule across benchmarks.
2. Not yet implemented — standard-mode double check: the verifier replays the recorded `trajectory.npz` once more in its
   own sandbox; the sidecar's verdict stays authoritative, and a verifier replay that disagrees is reported as a warning
   (`replay_mismatch` in `reward.json`, a `WARNING` line in the log). Needs the standard verifier to use the simulator
   image (§2.4) and to read the trajectory (§4.8).
3. Kept as they are: one frozen instance per task (no per-run seeds), and what each benchmark exposes to the agent in
   privileged mode (no hiding of reward or success checks).
