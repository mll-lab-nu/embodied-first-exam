# Robot Coding Bench — Task Protocol v1.2-rc

**Version: v1.2-rc** (2026-10-10). Changes in this version: the resource monitor sidecar, the docker caps and the
verifier's limits step are in every task (§2.10; #131, with the review fixes of the same day: an out-of-memory kill is
the agent's only at its container's own cap, a benchmark-owned service killed for memory is never the agent's 0, a CPU
cap above the host's CPU count is clamped by the runner); enforcement is off by default, and v1.2 becomes final when
the calibration batch has confirmed the limits. Also on 2026-10-10 (owner decision, board 0072): every task's agent
egress is the model APIs only, every instruction states the external-material rule in the same words (§2.11), and the
usage gateway forwards model-API calls only (D11, §5). Earlier versions, whose rules are all part of this text: v1.0
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
| D1 | Standard-mode protocol | Only `eai-standard/2.x`. Additive extensions are accepted through a protocol-change PR (2.2 is accepted once its services implement crash recovery). Reset is only an optional capability (`budget.reset = N`, default 0; results with N > 0 are reported separately). Documented per-benchmark exceptions (§4.5): HumanoidBench standard defaults to N = 50 (owner, 2026-10-07), MyoSuite standard to N = 10 (owner, 2026-10-09). The standard-realtime mode's `eai-standard/2.3` (§4b) is 2.2 plus the realtime capability. `eai-standard/2.4` (issue #89) is 2.3 plus the operations capability; standard tasks may use it. No step caps. |
| D2 | Tasks without an oracle | Allowed, with mandatory human review (§2.7). |
| D3 | Results | Not in the repository: agent results (per-task READMEs, videos, timelines, batch tables) are published on the results site and the Hugging Face dataset; a task directory has no `results/`. |
| D4 | Run id | `<harness>-<model>-<effort>`, model token with underscores (`codex-gpt6_luna-xhigh`); provider, tier and settings go in metadata. |
| D5 | Images | One registry (EAI organization), images named `eai-<name>` and versioned in `images/<name>/VERSION`; every image that may be redistributed is public, the rest are `BUILD_ONLY`. One image per **benchmark**, not per simulator: benchmarks on the same simulator may need different versions of it and of its dependencies (e.g. RoboCasa, RoboCasa365 and RoboCasa-GR1 on robosuite), so each may have its own image; an image is shared only where the dependency set is identical. |
| D6 | PR granularity | One benchmark per PR; changes to shared files go in a separate PR reviewed by a maintainer. |
| D7 | World-frame information in instructions | Decided per benchmark, consistent within it, documented in the benchmark's doc. |
| D8 | Agent time budget | 3600 s by default, at most 14400 s; longer budgets are justified, uniform within a benchmark, and results are grouped by budget. Documented per-benchmark exceptions to the cap (§2.3): RoboTangle 21600 s (owner, 2026-10-08). |
| D9 | Shared code | Shared sources are copied into tasks by the generator; nothing at run time imports repository code outside the task directory. |
| D10 | Token budget | Per trial: **100M input tokens, 10M output tokens** by default; exceeding either fails the trial. |
| D11 | Harness | Official results use Harbor's native agents only; no agent adapters, and no gateway that holds credentials or changes requests. The usage gateway (`scripts/usage_gateway/`) is allowed: it forwards model-API requests unchanged, records token usage, and refuses what a trial may not have: a request past the token budget (§5) and, since 2026-10-10, every request that is not a model-API call (§2.11). No tool that runs outside the trial's container is offered to the model (§2.11): official runs turn the harness's web search off (Codex `web_search = "disabled"`, Claude Code `WebSearch` and `WebFetch` disallowed; `scripts/run_agent_batch.sh` `WEB_SEARCH=disabled`, the default) and start the harness without account connectors, apps, plugins, image generation and cloud agents. These run at the model provider, so no egress allowlist stops them (2026-10-02: Codex with a ChatGPT login searched GitHub by default; 2026-10-10: the same login handed the model 238 account connector tools, and 21 trials called them) |
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
15. Runs with Harbor's native agents; no custom runner or adapter, and no gateway beyond the usage gateway (D11). [new]
16. Standard-mode tasks also satisfy every MUST in §4; standard-realtime tasks every MUST in §4 and §4b.
17. `[metadata.resources]` states the minimum CPU cores, memory and GPU memory of the agent phase and the verifier
    phase, the GPU class and a recommended GPU; the README's `## Compute resources` shows the same values (§2.9). [CI] (v1.1.4)
18. `[metadata.resources.limits]` states the agent phase's limits (GPU memory, memory, processes, disk) and the whole
    trial's expected peak, `[metadata.resources.caps]` the docker caps per service; `instruction.md` ends with the
    `## Resource limits` paragraph rendered from them (§2.10). [CI] (v1.1.5)
19. `[agent] network_mode = "allowlist"` with the model APIs' hosts; `instruction.md` states `## External material`
    just before `## Resource limits`; the agent needs no download at run time (§2.11). [CI]

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
| `[metadata.resources]`: the minimum compute (§2.9) | MUST | [CI] (v1.1.4) |
| `[metadata.resources.limits]` and `[metadata.resources.caps]`: the agent phase's resource limits and the docker caps (§2.10) | MUST | [CI] (v1.1.5) |
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
| States the time budget and tells the agent to save a deliverable early and not to stop early | SHOULD | [new] |
| Gives the success predicate's exact parameters | MAY | [current] |
| World-frame quantities (coordinates, table height): decided per benchmark, consistent within it, documented | MUST | [new] |
| Written by a human | SHOULD | [current] |
| Ends with `## External material` (§2.11: the same words in every task) and `## Resource limits`, rendered from `[metadata.resources.limits]` (§2.10); `scripts/task_conventions.py` writes both | MUST | [CI] (v1.1.5; 2026-10-10) |
| Tells the agent that it may install or download something | MUST NOT | [new] (§2.11: under the allowlist it cannot) |

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
| A solution, or a pointer to one, anywhere the agent can reach (task image, base image, tooling, docs in the container). A pointer is anything that locates the solution of this task: a URL, a dataset or file name, a demonstration or episode id, the name of the upstream expert that produced the reference. Provenance is kept in `scripts/<bench>/` and the README, never in a file under `environment/` the agent reads | MUST NOT | [CI] for the task's own files (`ci_checks/check-agent-pointers.py`: hosts of code, data and video, `*_url` keys, dataset and demonstration file names); [current] for images, reviewed when they are built. Upstream documentation inside a simulator image that names the benchmark's public datasets or checkpoints is not removed file by file: the allowlist of §2.11 makes them unreachable. Open (2026-10-10): RoboTangle's image (docs/benchmarks/robotangle.md) |
| Upstream experts scrubbed from images (e.g. RoboTwin `play_once`) | MUST | [current] |
| Agent egress allowlisted in `task.toml` (the model APIs only), in every task (§2.11) | MUST | [CI] (2026-10-10; until then a SHOULD "when a solution is publicly downloadable", and RoboTwin, MuJoCo Playground's four Aloha / Panda pairs, RoboWits, RoboLab, BEHAVIOR-1K and RoboTangle were open) |
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
| Listed in `tasks/dataset.toml` with the digest of its current files (re-run `cd tasks && harbor add --scan .` after any change; `ci_checks/check-dataset-manifest.sh` recomputes every digest) | MUST | [CI] |
| A published task's `environment/` and `tests/` inputs are immutable; a change is a new task | MUST | [current] |
| Fixes to existing tasks add a Change Log entry to the task README with before/after runs | SHOULD | [new] |

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
| `instruction.md` ends with `## Resource limits`, equal to what `scripts/task_conventions.py` renders from the limits and `[environment].cpus` | MUST | [CI] |
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
each compose service's `cpus`) to the host's CPU count in the copy of the task it runs; the task's files keep their
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

### 2.11 External material and the network (2026-10-10)
An agent solves a task with what is in its container and with the task interface its `instruction.md` documents, and
with nothing else (owner decision, board 0072). Before, only three benchmarks' instructions said so, six benchmarks
left the agent's egress open, and trials downloaded upstream sources, a reference solution, a recorded demonstration,
robot models and pretrained policies, from their own shell or through tools of the model's account.

| Item | Level | Basis |
|---|---|---|
| The agent uses only what is in its container and the documented task interface (the tooling, the standard-mode client and its service). It downloads and installs nothing: no source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages | MUST | [new] (stated in every instruction; the allowlist below) |
| No tool that runs outside the container is used: web search and fetch, browsing, account connectors and apps, remote MCP servers, plugins, image generation, cloud agents. The runner does not offer them (D11) | MUST NOT | [new] |
| `[agent] network_mode = "allowlist"` in every task, `allowed_hosts` = the model APIs' hosts (`scripts/set_agent_egress.py` `HOSTS`, the same list in every task) | MUST | [CI] |
| What the agent's container needs at run time (assets, robot models, packages, caches) is in its image or the task directory; a task that needs a download during the agent phase does not conform | MUST | [current] (of the six benchmarks switched on 2026-10-10, RoboTwin, the Playground pairs, RoboWits, BEHAVIOR-1K and RoboLab were run with the oracle under the allowlist, both modes, with the rewards and state hashes of their open-egress runs; RoboLab needed its image to hold the materials it used to fetch, `eai-robolab:0.1.2`; RoboTangle, whose image documents that it needs no network, was not run again before its next release) |
| Every `instruction.md` states the rule in the same words under `## External material`, just before `## Resource limits`; `scripts/task_conventions.py` (`EXTERNAL_TEXT`) writes it and it is never edited in a task | MUST | [CI] |
| A run through the usage gateway narrows the agent's egress to the gateway's address, and the gateway forwards model-API calls only (§5) | MUST for official runs | [new] (`scripts/run_agent_batch.sh` `GATEWAY=1`) |
| A result obtained with external material is void: the trial is withdrawn and run again. It is neither a success nor a failure of the task | MUST | [new] |

The paragraph in every `instruction.md`:

> ## External material
> Use only what is in your container and the task interface described above. Do not download or install anything: no
> source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages. Do not use
> web search, browsing, account connectors or any other tool that runs outside your container. Network access is
> limited to your model's API. A result obtained with external material is void.

Who reaches what in a trial (Harbor's egress control puts `main` and every compose service without its own network
setting in one network namespace; §2.6 forbids such a setting on any service but the monitor):

| | While the environment starts and the harness is installed | During the agent phase |
|---|---|---|
| The agent's container (`main`) | public (Harbor's baseline: the harness is installed from its registry) | the allowlist: the model APIs' hosts; in a run through the usage gateway, the gateway's address only (and `chatgpt.com` for Codex with a ChatGPT login, below) |
| The `sim` sidecar (standard modes) and other services of the task | public; it needs nothing: images are complete | the same allowlist as `main` (one namespace): a service that restarts mid-episode starts without the network |
| `rcb_monitor` | none | none |
| The verifier (its own sandbox, afterwards) | | `no-network` (§2.6: MUST in the standard modes, SHOULD in privileged mode) |

The model APIs' hosts also serve what a trial must not reach (a ChatGPT login's account connectors, file and
conversation endpoints), and the credentials of the run are in the container. So with the gateway on, the runner
starts each job from a copy of the task whose allowlist is the gateway's address alone (`scripts/set_agent_egress.py
only <address>`; Harbor can add a host to a task's allowlist at run time, not take one off), and the gateway forwards
only the requests listed per provider in `scripts/usage_gateway/api_paths.json` (responses, messages, token counting,
the model list), answers every other one 403 and records it (`<trial>/gateway/usage.jsonl`
`refused = "path_not_allowed"`, `totals.json` `refused_paths`). A model request's body is forwarded as it is or not at
all: it must be one JSON object the gateway can read, and every tool it declares must be of a type the agent runs
itself (`client_tool_types` in the same file); a request declaring any other type (the provider's: web search or
fetch, image generation, remote MCP, file search, a hosted shell or code interpreter), a provider-side search field or
content for the provider to fetch by URL is refused (`refused = "server_tool"`), an unreadable one too
(`"body_unreadable"`). Without the gateway (`GATEWAY=0`, a
bare `harbor run`), the task's own allowlist applies and these hosts are reachable directly: not for official runs.
Open: Codex with a ChatGPT login needs `chatgpt.com` itself at start-up, over HTTPS (docs/RUNNING.md), so such a run
keeps that host beside the gateway, and its account connectors are off by the harness's configuration only; official
runs prefer API keys, which have none.

## 3. Privileged mode (`mode = "privileged"`, `task_type = "trajectory"`)

| Item | Level | Basis |
|---|---|---|
| Deliverable `/app/output/trajectory.npz` (format defined by the task's instruction) | MUST | [current] |
| The generating script at `/app/output/gen.py` | SHOULD | [current] |
| Graded by open-loop replay from the frozen initial state in a fresh process | MUST | [current] |
| ≥ 2 replays with matching final-state hashes, reported as `deterministic` | SHOULD (the field is MUST) | [current] |
| Success judged on the state at the end of the replay ("success at any step" needs a stated reason) | SHOULD | [current] |
| The frozen instance copied into both `environment/` and `tests/` with its expected initial-state hash, checked on rebuild | SHOULD | [current] |
| A hash check before moving to new hardware. Reference hardware is an RTX 4090: `place_a2b_left`, `place_a2b_right`, `place_object_scale` and `place_object_stand` rebuild to a different state on an L40S, and grading there reports `instance_mismatch` with `infra_error` (privileged: also when no trajectory was handed in; standard: the service's `reason`) | SHOULD | [current] |
| Unlimited resets, privileged state, planning primitives, self-replay | MAY | [current] |
| Tool API shape | task-defined | [current] (recommended: `Session` with `reset` / `replay` / `status` / `save_trajectory`) |
| Self-reported cost (resets, simulation steps) in `agent_*` fields | SHOULD | [current] |
| `task_type = "policy"` | MAY | rules defined with the first such task |

## 4. Standard mode (`mode = "standard"`): `eai-standard/2.x`

Wire details (endpoints, RCB1 frames, `meta`, error codes, crash recovery) are in
[`STANDARD_MODE.md`](STANDARD_MODE.md), one part per version. This section lists what is required.

### 4.0 Versions
| Version | Date | Content |
|---|---|---|
| eai-standard/2.1 | 2026-09-30 | the base (formerly `rcb-limited/2.1`): no reset; `/submit` action chunks, `/observe`; binary RCB1 responses; 82-column proprioception, optional depth noise; crash recovery. Served by the standard tasks of RoboTwin, DexToolBench, MuJoCo Playground (manipulation), KinDER, HumanoidBench, MetaWorld+, VLABench, the three RoboCasa benchmarks, LIBERO-MAX and BiGym 2.0 |
| eai-standard/2.2 | 2026-10-01 | additive extension (§6, [`STANDARD_MODE.md`](STANDARD_MODE.md) Part 2) with crash recovery; served by BEHAVIOR-1K, RoboLab, RoboWits, RoboPaint, MolmoSpaces, MyoSuite, DexJoCo, YAMLab, RoboDojo, LabUtopia, AutoBio, ManiGuard and MuJoCo Playground's quadruped tasks |
| eai-standard/2.3 | 2026-10-08 | 2.2 + the realtime capability (§4b; [`STANDARD_MODE.md`](STANDARD_MODE.md) Part 3, "Standard-realtime mode"); every 2.2 addition stays a MAY. Served by standard-realtime tasks only (HumanoidBench, RoboOlympics, BiGym 2.0); standard tasks stay on 2.1 / 2.2. Issue #86 |
| eai-standard/2.4 | 2026-10-08 | 2.3 + the operations capability ([`STANDARD_MODE.md`](STANDARD_MODE.md) Part 4): operation ids and request deadlines (408 / 409), `GET /operations/<id>`, a service-owned call watchdog, a physics-tick ledger, fsynced journals; every earlier addition, the realtime capability included, stays a MAY. Served by standard tasks (RoboTangle); reference implementation `scripts/eai_standard/v2_4/`. Issue #89 |

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
- **RoboTangle** (standard tasks): `meta["safety"]` of every response: the forcing record (the largest force an arm
  or a part it holds pressed with, the drive load meanwhile, forcing events), the deepest task contact and
  held-finger contact with their review limits, the review events (with the names of the parts in contact), the lowest soft-body volume ratio and the worst cord
  attachment stretch, the table-guard stops and IK jumps
  ([`benchmarks/robotangle.md`](benchmarks/robotangle.md), "Safety readings in standard mode"). The benchmark's
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
- **MyoSuite** (owner, 2026-10-09; standard tasks): `budget.reset = 10`. MyoSuite's own termination ends most episodes
  within a second or two of simulated time (a dropped object, an object off the reference motion), and the agent has no
  simulator to practise in, so a single episode is one blind attempt at muscle-level control. `RCB_RESET_BUDGET=0` still
  runs one episode; MyoSuite standard results recorded before 2026-10-09 ran with 0 (and saw the wrong `joint_effort`)
  and are reported separately ([`benchmarks/myosuite.md`](benchmarks/myosuite.md)).

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
| Per-simulator resume rule: a simulator declared nondeterministic compares and records the hash, and a mismatch continues the same episode with `resume_state_mismatch` (unless the robot diverged grossly), as in [`STANDARD_MODE.md`](STANDARD_MODE.md) §13.1; the verdict still comes from fresh replays of the whole recorded trajectory | MAY | [new] (2.2) |

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
| Slowdown S: `RCB_SLOWDOWN`, default **1** (real time; per-benchmark exceptions below: RoboOlympics 10). Results with S ≠ 1 are reported separately from S = 1 and state S; official results use S = 1, or the benchmark's documented S | MUST | [new] |
| Reset budget: **no reset by default** (`budget.reset = 0`), as in standard mode; per-benchmark exceptions only as in §4.5 (HumanoidBench: 50; MyoSuite has no standard-realtime tasks). The reset capability is §4.5's; `RCB_RESET_BUDGET` overrides it; results state the budget and are compared only under the same budget | MUST | [new] (v1.1.2, #102: v1.1 and v1.1.1 wrongly made HumanoidBench's 50 the mode's default) |
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
| Official runs go through the usage gateway, which forwards model-API calls only and is the agent container's only egress; the harness offers the model no tool that runs outside the container (§2.11, D11). A trial with a call of such a tool, or with material fetched from outside, is void | MUST | [new] (2026-10-10; the runner flags a trial whose `totals.json` has `refused_paths` or `server_tool_requests`) |
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
   open egress stand unless the trial fetched external material (those are withdrawn and run again; RoboTangle is run
   again as a whole); an agent could `pip install` there (plotting and image libraries were the common ones), which
   it no longer can. Open: RoboTangle's image still names upstream demonstrations and solution sheets in files a
   privileged agent can read (unreachable under the allowlist; docs/benchmarks/robotangle.md, Network policy: a
   requirement for its next release).
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
