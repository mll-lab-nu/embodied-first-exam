# Robot Coding Bench — Task Protocol v1.2-rc

**A set of recommended conventions.** This protocol describes how a task is usually built so that tasks from different
benchmarks can be run, compared and reviewed the same way. It recommends; it does not forbid. A task or a benchmark may
deviate, and says so where its readers look: its `task.toml`, its README and `docs/benchmarks/<bench>.md`. What CI
checks today is marked **[CI]**; those checks stay as they are until the owner decides otherwise, and a task that
deviates from a checked convention adapts the check in the same pull request through a value the task declares, never
through a per-benchmark list in `ci_checks/`.

The protocol keeps general conventions only. A benchmark's own settings, the reasons for them and the decisions
behind them are in its doc (`docs/benchmarks/<bench>.md`); the dated record of how this text came about is in
[`PROTOCOL_HISTORY.md`](PROTOCOL_HISTORY.md). The wire format of the standard modes (`eai-standard/2.x`) is in
[`STANDARD_MODE.md`](STANDARD_MODE.md). Section numbers are stable: tasks and documents cite them.

Versions: v1.0 (2026-09-30: the two modes and their names), v1.1 (2026-10-08: the standard-realtime mode, §4b),
v1.1.4 (compute resources, §2.9), v1.1.5 (resource limits, §2.10), v1.2-rc (2026-10-10: the limits judged inside the
trial; final when the calibration batch has confirmed them); 2026-10-14: the protocol made lean and recommended
(conventions, not mandates; each task declares its own settings, §0).

## 0. Conventions

| Level | Meaning |
|---|---|
| **Default** | What a task does unless it declares otherwise. A deviation is stated in the task's README or its benchmark's doc and explained in the pull request. |
| **Recommended** | Good practice; reviewers ask about it. |
| **Optional** | Left to the task or benchmark; if adopted, done as described here. |
| **Avoid** | Not done by default; a task that does it says why. |

Basis tags: **[CI]** checked by `ci_checks/`; **[current]** what existing tasks do; **[new]** introduced since v1.0.

**Principle.** The benchmark adds as little as possible on top of the Harbor task format. Anything not described here
(which simulator, how a scene is defined, the shape of the privileged-mode tool API, how a verifier decides
internally) is the task's own business.

**Each task chooses its own settings.** The settings below are the task's (or its benchmark generator's) to choose;
the task declares them, and CI checks that the declarations agree with each other, not that they take a particular
value. The defaults are what the templates and generators write when a task says nothing else.

| Setting | Where the task declares it | Default |
|---|---|---|
| Modes offered (privileged, standard, standard-realtime, or any subset; §2.15) | the task directories it ships; the README's Twin row; the benchmark's doc | — |
| Time limit / cutoff (§2.12) | `[agent] timeout_sec` in `task.toml` (a generator: its own constant) | 3600 s; at most 14400 s; equal in a task's privileged and standard versions |
| Reset budget, standard modes (§4.5, §4b) | the `sim` service's `RCB_RESET_BUDGET` default in `environment/docker-compose.yaml` (served as `/spec.budget.reset`), the instruction, and `[metadata] reset_budget` where the task keeps it | standard 0; standard-realtime 10 |
| Realtime slowdown S (§4b) | the `sim` service's `RCB_SLOWDOWN` default, `[metadata] slowdown`, the instruction (`S = <S>`) | from the measured real-time factor (§4b) |
| Observation and action extras (§4.3–§4.5) | `/spec`, the instruction, the benchmark's doc (action types, depth, declared telemetry) | the §4 core |
| Grading variant (§3, §4.8) | the instruction, the frozen instance, the benchmark's doc | two fresh replays |
| Seeds (§2.13) | `[metadata.seeds]` | the default seed only |
| Network (§2.11) | `[agent] network_mode` | the one allowlist |
| Stricter honour rules (§2.11) | `[metadata.honour] stricter` | none |

### 0.1 Terms

| Term | Meaning | Former name |
|---|---|---|
| **privileged mode** | Agent and simulator share a container; the agent may read privileged state, reset freely, call planning primitives. The deliverable is a trajectory. | unlimited |
| **standard mode** | Robot as a service: the simulator runs in a sidecar the agent cannot open; the agent sends actions and receives images and proprioception through a client; resets only as the task's budget allows (§4.5). | limited |
| **standard-realtime mode** | Standard mode on a clock that does not stop: once an episode starts the robot runs in real time (divided by the slowdown S) whatever the agent does, holds its last targets while the agent thinks, and the agent drives it from a program of its own (§4b, `eai-standard/2.3`). | — (v1.1) |
| **`eai-standard/2.x`** | The standard-mode wire protocol (§4). | `rcb-limited/2.x` |
| **`eai-<name>`** | Base image (a simulator stack, usually one per benchmark) under `ghcr.io/mll-lab-nu/` (§2.4). | `rcb-<sim>` |

Unchanged from before v1.0: the task name prefix `robot-coding-bench/`, the client and tool file names
(`rcb_client.py`, `rcb1.py`, `rcb_traj.py`), the `RCB1` frame format and the `RCB_*` environment variables.

### 0.2 Design decisions

| # | Topic | Decision |
|---|---|---|
| D1 | Standard-mode protocol | `eai-standard/2.x`; additive extensions through a protocol-change pull request (§6). Reset is an optional capability whose budget each task declares (§4.5); results with a budget N > 0 are reported separately from N = 0. `eai-standard/2.3` is 2.2 plus the realtime capability (§4b), `eai-standard/2.4` 2.3 plus the operations capability. No step caps. Tasks a benchmark exports with its own service use its own protocol (§4c). |
| D2 | Tasks without an oracle | Allowed, with human review (§2.7). |
| D3 | Results | Not in the repository: published on the results site and the Hugging Face dataset; a task directory has no `results/`. |
| D4 | Run id | `<harness>-<model>-<effort>`, model token with underscores (`codex-gpt6_luna-xhigh`); provider, tier and settings go in metadata. |
| D5 | Images | One registry, images named `eai-<name>` and versioned in `images/<name>/VERSION`; every image that may be redistributed is public, the rest `BUILD_ONLY`. One image per benchmark, shared only where the dependency set is identical. |
| D6 | PR granularity | One benchmark per PR; changes to shared files in a separate PR reviewed by a maintainer. |
| D7 | World-frame information in instructions | Decided per benchmark, consistent within it, documented in the benchmark's doc. |
| D8 | Agent time budget (the cutoff) | Each task's own `[agent] timeout_sec`: 3600 s by default, at most 14400 s, another number justified in the pull request that sets it; the same in a task's privileged and standard versions; results grouped by budget (§2.12). |
| D9 | Shared code | Shared sources are copied into tasks by the generator; nothing at run time imports repository code outside the task directory. |
| D10 | Token budget | Per trial: 100M input tokens, 10M output tokens by default; exceeding either fails the trial (§5). |
| D11 | Harness | Official results use Harbor's native agents; no agent adapters, and no gateway that holds credentials or changes requests. The usage gateway (`scripts/usage_gateway/`) forwards model-API requests unchanged, records token usage and refuses what a trial may not have (past the token budget, anything that is not a model-API call). Official runs offer the model no tool that runs outside the trial's container: the harness's web search, account connectors, apps, plugins, image generation and cloud agents are off (`scripts/run_agent_batch.sh` `WEB_SEARCH=disabled`, `scripts/codex_tools_off.py`). |
| D12 | Mode naming | `mode ∈` the registry of §2.16 (today `privileged`, `standard`, `standard-realtime`); every task directory ends in its mode (`-privileged`, `-standard`, `-standard-realtime`). |

## 1. Checklist (every task)

By default a task has:

1. `task.toml`, `instruction.md`, `README.md`, `environment/Dockerfile`, `tests/test.sh` (executable), `tests/Dockerfile`; `solution/solve.sh` depending on the oracle level (§2.7). [CI]
2. `[task].name = "robot-coding-bench/<folder>"` and the metadata of §2.3. [CI]
3. Top-level `artifacts` with `"/app/output/"`; `[agent].timeout_sec`, a whole number of seconds ≤ 14400, the same as its privileged twin's (§2.12). [CI]
4. Every image reference pinned to a tag or digest, never `:latest`. [CI]
5. `[verifier] environment_mode = "separate"`; `tests/Dockerfile` copies `test.sh`. [CI]
6. An `instruction.md` that names the deliverable under `/app/output/` and never mentions `/tests/`. [CI]
7. Its content digest in `DIGEST` (§2.8). [CI]
8. A verifier that writes `reward.txt` (1/0) and a numeric-only `reward.json` with at least `success` (and `deterministic` for trajectory tasks). [current]
9. The same verdict in a fresh process, without network. [current]
10. Reference solutions only under `solution/`; nothing the agent can reach contains or points to one. [current]
11. `nop` scoring 0; with an oracle, the oracle scoring 1; without one, human review (§2.7).
12. Immutable `environment/` and `tests/` inputs once published; a change is a new task (§2.8). [current]
13. A directory name ending in its mode (§2.2); no `results/` (D3). [CI]
14. A README in the standard layout (§2.1). [CI]
15. Harbor's native agents only (D11).
16. In the standard modes, the conventions of §4 (and §4b for standard-realtime).
17. `[metadata.resources]` and the README's `## Compute resources` (§2.9). [CI]
18. `[metadata.resources.limits]` / `.caps` and the instruction's `## Resource limits` (§2.10). [CI]
19. `[agent] network_mode = "allowlist"` with the one host list, and the instruction's `## External material`; no download at run time (§2.11). [CI]
20. An instruction that ends with `## Time limit`, rendered from `[agent] timeout_sec` (§2.12). [CI]
21. `[metadata.seeds]` (§2.13). [CI]

## 2. Task contract

### 2.1 Layout and self-containment
| Item | Level | Basis |
|---|---|---|
| `task.toml`, `instruction.md`, `README.md`, `environment/Dockerfile`, `tests/test.sh` (executable), `tests/Dockerfile` | Default | [CI] |
| `solution/solve.sh` (executable) for `oracle = "full"` or `"partial"`; absent for `"none"` (no `exit 1` placeholders) | Default | [CI] |
| `environment/docker-compose.yaml` (GPU or sidecar) | Optional | [current] |
| All task code (agent tooling, verifier) in the task directory, copied in by its Dockerfiles; base images hold the simulator and its assets only | Default | [current] |
| Importing repository code from outside the task directory at run time (`scripts/` packages, a `PYTHONPATH` into the repository); pinned third-party packages are fine | Avoid | [current] (a task's identity is its directory digest; Harbor builds from the task directory alone) |
| Shared sources under `scripts/<bench>/shared/`, copied into each task by the generator, byte-identical within a benchmark | Optional | [CI] (`check-tooling-identity.sh`) |
| Generated tasks come with their generator (`scripts/<bench>/`); re-running it reproduces the committed tasks | Recommended | [CI] (`check-generated-tasks.sh`) |
| `README.md` layout: `# <directory name>`; a key table (Benchmark, Mode, Twin, Simulator / robot, Family / instance, Oracle, Agent time budget, Base image); `## Task`, `## Difficulty`, `## Reference solution`, `## Verification`, `## Compute resources` (§2.9), `## Details`. No results | Default | [CI] |

### 2.2 Naming
| Item | Level | Basis |
|---|---|---|
| Privileged tasks: `<base>-privileged`, `<base>` = `<benchmark>-<family>-i<NN>` or an upstream name kept as is | Default | suffix [CI] |
| Standard and standard-realtime tasks: `<base>-standard` / `<base>-standard-realtime`, sharing the privileged twin's frozen instance, `instance_seed` and seeds (§2.13) where there is a twin (without one, §2.15, the task carries its own instance in its sidecar) | Default | suffix and instance [CI] |
| Versions or durations in task names (`-v3-`, `-60min-`) | Avoid | [new] (versions are digests) |

### 2.3 `task.toml`
| Item | Level | Basis |
|---|---|---|
| `schema_version = "1.3"`; `[task].name = "robot-coding-bench/<folder>"` | Default | name [CI] |
| `[task].description`, `authors`, `keywords` | Recommended | [current] |
| `[metadata]`: `author_name`, `task_type ∈ {trajectory, policy}`, `simulator`, `robot`, `family`, `mode` (§2.16), `expert_time_estimate_hours` | Default | [CI] |
| `tier` (replaced by `mode`) | Avoid | [CI] |
| `protocol`: one of the values the mode's registry entry lists (standard 2.1 / 2.2 / 2.4, standard-realtime 2.3; privileged none), or the benchmark's own protocol for an exported task (§4c) | Default | [CI] |
| `oracle ∈ {full, partial, none}`; `oracle_evidence` when not `full` | Default | [CI] |
| `simulator`, `robot` from the vocabularies in [`TAXONOMY.md`](TAXONOMY.md) (extend by PR); benchmark-specific fields registered there | Default | [current] |
| `instance_seed` (equal to the default seed, §2.13); `[metadata.seeds]` | Default | [CI] |
| `[metadata] dynamics ∈ {static, dynamic}` (§2.14) | Default | [CI] |
| `[agent].timeout_sec` (§2.12) | Default | [CI] |
| `[verifier].environment_mode = "separate"` | Default | [CI] |
| `[verifier].timeout_sec`, `[environment]` `cpus` / `memory_mb` / `build_timeout_sec` | Recommended | [current] |
| `[metadata.resources]`, `.limits`, `.caps` (§2.9, §2.10) | Default | [CI] |
| `[environment].gpus` (Harbor's local Docker sandbox ignores it; §2.4) | Avoid | [current] |

**Agent budget cap.** `[agent].timeout_sec` is at most 14400 s (`ci_checks/check-task-fields.sh`,
`ci_checks/check-cutoffs.py`, `scripts/task_conventions.py` `CUTOFF_CAP`). A standard sidecar's wall clock
(`RCB_WALL_CLOCK_S`, `/spec.budget.wall_clock_s`) equals the task's cutoff [CI]. The token budget (D10) is separate.

### 2.4 Images, registry, GPU

A base image is defined by `images/<name>/Dockerfile` and tagged `ghcr.io/mll-lab-nu/eai-<name>:<images/<name>/VERSION>`;
`scripts/build_images.sh` builds every image, `scripts/push_images.sh` pushes all but the `BUILD_ONLY` ones. Tasks
reference it by tag: `environment/Dockerfile` and `tests/Dockerfile` `FROM` it, and a standard-mode `sim` service uses
it as `image:`. Harbor builds the task images locally from the task directory; only base images are pulled.

| Item | Level | Basis |
|---|---|---|
| Base images at `ghcr.io/mll-lab-nu/eai-<name>:<ver>`, anonymously pullable, unless `BUILD_ONLY` | Default | registry [CI] |
| Images that cannot be published (licensed simulators): `images/<name>/BUILD_ONLY` plus local build instructions | Default | [new] |
| Every `FROM` and `image:` pinned to a tag or `@sha256` digest | Default | [CI] |
| Sidecars built with `build:` | Avoid | [new] |
| Dependencies pinned; no downloads during verification | Default | [current] (open: §7 item 2) |
| Within a benchmark, one base image version across privileged `environment`, `tests` and the standard `sim` service | Default | [new] |
| Different benchmarks on the same simulator using different images or versions | Optional | [new] (D5) |
| Merging simulator stacks into one image only when their dependency versions are identical (instance hashes depend on them) | Default | [new] |
| GPU: an NVIDIA device reservation (`count: 1`) in compose on `main` (privileged) or `sim` (standard); in `tests/docker-compose.yaml` too if replay needs it | Default | [current] |
| `device_ids` pinning a specific GPU; fixed-name global volumes | Avoid | [new] |

### 2.5 `instruction.md`
| Item | Level | Basis |
|---|---|---|
| States the deliverable under `/app/output/`; does not mention `/tests/` | Default | [CI] |
| States every convention the agent cannot infer: frames, quaternion order, units, action layout, tool or client usage, the reset budget and S where they apply | Default | [current] |
| Ends with three sections `scripts/task_conventions.py` writes, in this order: `## External material` (§2.11), `## Resource limits` (§2.10), `## Time limit` (§2.12); never edited by hand | Default | [CI] |
| States the agent's time limit a second time as a duration; the task's own text says "the time limit (`## Time limit`)" | Avoid | [CI] (`check-cutoffs.py` `OTHER_LIMIT`) |
| Says what the cutoff means where the mode's paragraph does not (a simulator's start-up cost, a service that ends the episode on its own clock, a match that must be over in time) and asks the agent not to stop early where a deliverable can be improved | Recommended | [current] |
| Gives the success predicate's exact parameters | Optional | [current] |
| World-frame quantities: decided per benchmark, consistent within it, documented (D7) | Default | [new] |
| Tells the agent it needs to download something | Avoid | (§2.11) |

### 2.6 Verifier
| Item | Level | Basis |
|---|---|---|
| Runs in its own sandbox (separate mode) with only the declared artifacts | Default | [CI] |
| `/logs/verifier/reward.txt` is `1` or `0` (partial progress in `reward.json` as `progress`); `reward.json` has numeric fields only | Default | [current] |
| Same verdict in a fresh process on the same inputs; no network (`network_mode = "no-network"`, in the standard modes and recommended in privileged mode) | Default | [current] |
| Verdict written before videos are rendered; videos never affect it; a human-viewable `replay.mp4` | Recommended | [current] |
| `test.sh` first clears `/logs/verifier`; named volumes crossing the trust boundary are named `*_trusted` | Default | [CI] |
| Before the grader, `test.sh` removes from `/app/output` what is not the agent's own regular file or directory (links that leave it, FIFOs, devices: `python3 /tests/rcb_limits.py sanitize /app/output`); a session log over 64 MiB is cut | Default | [CI] |
| The agent's container mounts no `*_trusted` volume in any spelling, binds no host path (only a directory the runner names through an environment variable), and no service widens its container (`privileged`, `cap_add`, `devices`, host namespaces); a sidecar publishes no port; in the standard modes the evidence artifacts and the collect hook are a sidecar's; an allowlist is the one of `scripts/set_agent_egress.py`. `ci_checks/check-ci-selftest.py` breaks real tasks in each of these ways and requires the checks to fail | Default | [CI] |

`reward.json` field names (use these whenever the concept applies; no synonyms):

| Field | Level | Meaning |
|---|---|---|
| `success` | Default | 1 iff the deliverable completes the task |
| `deterministic` | Default (trajectory tasks) | repeated verification agreed |
| `infra_error` | Default (standard) / Optional | infrastructure failure, not the agent's |
| `sim_error` | Recommended (standard) | the episode ended with a simulator error (`reason = "error"`, §4.6) |
| `grader_error`, `missing_trajectory` / `missing_log` | Recommended | diagnosable failure modes |
| `resource_enforced`, `limits_violation_observed`, `peak_gpu_memory_gb`, `peak_memory_gb`, `peak_processes`, `peak_disk_gb`, `resource_monitor_missing`, `resource_emergency_kills`, `resource_oom_kills`, `resource_host_oom_kills`, `resource_service_oom_kills` | Default (v1.2) | the monitor's mode (`RCB_LIMITS_ENFORCE`), whether a limit was exceeded (`over_<metric> = 1` each), the scope's peaks, a missing or unusable record, the monitor's protective kills, and the kernel's OOM kills: at the container's own cap (the violation `over_oom`), by another OOM killer (the host's), in a benchmark-owned service (§2.10). Written by the verifier step in `tests/test.sh`'s exit trap |
| `resource_limit_exceeded`, `success_before_limits` | Default (v1.2, enforcement on) | 1 iff an enforced limit was exceeded, then `success = 0`; the grader's verdict before it. `success_before_limits` is also written whenever the resource step declares the trial not a result (`infra_error = 1`), which then sets `success = 0` and `reward.txt` 0 |
| `resource_service_oom`, `resource_host_oom` | Default (when it happens) | a benchmark-owned service was OOM-killed and the verdict is not a success (both settings), or a process in scope was killed by an OOM killer that is not its container's cap (enforcement on): then `infra_error = 1` (§2.10) |
| `resource_switch_error`, `resource_step_error` | Default (when it happens) | `RCB_LIMITS_ENFORCE` was not `0`/`1`/`true`/`false` (then `infra_error = 1`); the resource step itself failed (then `resource_monitor_missing = 1`, and `infra_error = 1` with enforcement asked for) |
| `n_actions`, `sim_steps` (or `control_steps`), `video_rendered` | Recommended | size of the deliverable, simulation cost, video present |
| `final_reward`, `progress`, `live_success`, `replay_success`, `live_video`, `live_frames`, `sim_startups`, `finalized`, `elapsed_s`, `agent_*` | Optional | when the concept exists |

### 2.7 Reference solutions, oracle, nop
| Item | Level | Basis |
|---|---|---|
| Reference solutions only under `solution/` (mounted for the oracle agent only) | Default | [current] |
| A solution, or a pointer to one, anywhere the agent can reach (task image, base image, tooling, docs in the container). A pointer locates the solution of this task: a URL, a dataset or file name, a demonstration or episode id, the upstream expert's name. Provenance lives in `scripts/<bench>/` and the README, never in a file under `environment/` | Avoid | [CI] for the task's own files, text and `.npz` string members (`check-agent-pointers.py`); [current] for images, reviewed when built ([LEAKAGE.md](LEAKAGE.md)) |
| Upstream experts scrubbed from images | Default | [current] |
| `nop` scores 0 | Default | [current] |
| `oracle = "full"`: the oracle scores 1 on each seed in `seeds.oracle` (§2.13) | Default | [current] |
| `oracle = "partial"` or `"none"`: `oracle_evidence` and human review | Default | [new] |

**Human review** (any task whose `oracle` is not `full`): the PR is labelled `needs-human-review` and approved by a
maintainer other than the author. Generated tasks are reviewed per family (same generator and predicate): at least two
instances per family, one with a positive example. The author provides a table *family → positive example → nop
result → predicate summary*. The reviewer checks:
1. **Solvable** — a positive example (a successful model trial, an upstream policy or RL rollout, or a hand-built
   trajectory or state) that the verifier scores 1.
2. **Correct predicate** — the grader matches the instruction and cannot be satisfied trivially.
3. **Negative control** — `nop` scores 0; ideally a wrong trajectory scores 0 too.
4. **Determinism** — the positive example replays to the same verdict twice in fresh processes.
5. **Record** — reviewer, date, instances and evidence in the review comment; the README's Verification section says
   "no oracle; human review in PR #N".

### 2.8 Identity and immutability
| Item | Level | Basis |
|---|---|---|
| The digest of the task's files in `tasks/<task>/DIGEST` (`sha256:<hex>`, the digest Harbor publishes it under), written last by `scripts/task_conventions.py` `normalize`; after a hand edit run `python3 scripts/task_conventions.py tasks/<task>`. The release manifest `tasks/dataset.toml` and the task list are generated from the DIGEST files after every merge (`scripts/dataset_manifest.py`, branch `task-list`), not committed | Default | [CI] (`check-dataset-manifest.sh`) |
| A published task's `environment/` and `tests/` inputs do not change; a change is a new task. One line is exempt: the `sim` service's `RCB_WALL_CLOCK_S`, which mirrors `[agent] timeout_sec` and is rewritten by `normalize` | Default | [current]; the line [CI] |
| Fixes to existing tasks add a Change Log entry to the task README with before/after runs | Recommended | [new] |
| A change of a task's cutoff, or of the text `normalize` owns in every instruction, changes the task in place (same name and instance, new digest); its pull request records old -> new and why. Results under another cutoff are reported separately (D8) | Default | [new] |

### 2.9 Compute resources (v1.1.4)

Every task states the smallest allocation it runs on, so that a scheduler can pack trials and a contributor knows what
hardware a task needs. The values live in `task.toml` under `[metadata.resources]`; the README's `## Compute
resources` table is rendered from them by `scripts/task_conventions.py`.

| Item | Level | Basis |
|---|---|---|
| `[metadata.resources]` with every field below (`recommended_gpu` may be left out when `gpu_required = false`) | Default | [CI] |
| README `## Compute resources`, after `## Verification`, equal to what `task_conventions.py` renders | Default | [CI] |
| `gpu_required = true` exactly when the compose file reserves an NVIDIA GPU; then `min_gpu_memory_gb > 0` and `gpu_class` is not `"none"`; otherwise `min_gpu_memory_gb = 0` and `gpu_class = "none"` | Default | [CI] |
| `verifier_min_gpu_memory_gb > 0` exactly when a GPU reaches the verifier phase (`tests/docker-compose.yaml`, or a collect hook on a GPU sidecar) | Default | [CI] |
| A minimum never exceeds a cap that bounds the whole phase (`[environment]` for a task without a sidecar, `[verifier.environment]` for a verifier without a collect hook) | Default | [CI] |
| Values derived from measured peaks as below; `measured` says from what, or `"author estimate"` | Recommended | [new] |
| Values uniform within a benchmark, or within a family where families differ | Recommended | [new] |

| Field | Type | Meaning |
|---|---|---|
| `min_cpus` | float | CPU cores the agent phase needs at once, over every container of the trial |
| `min_memory_gb` | float | memory (GB) the agent phase needs at its peak, same scope |
| `min_gpu_memory_gb` | float | GPU memory (GB) the agent phase holds at its peak; 0 without a GPU |
| `gpu_required` | bool | the task does not start without an NVIDIA GPU |
| `gpu_class` | string | `"none"`; `"any"` (any CUDA GPU with EGL / Vulkan); `"rtx"` (an RTX-class GPU with ray-tracing cores: Isaac Sim / Omniverse; A100 / H100 do not run it) |
| `recommended_gpu` | string or list | a card the task is known to run well on |
| `verifier_min_cpus`, `verifier_min_memory_gb`, `verifier_min_gpu_memory_gb` | float | the same for the verifier phase (the verifier's container plus, in standard modes, the replay in the sidecar) |
| `measured` | string | provenance of the values |

**Minimum** means the smallest allocation on which one trial, alone on the machine, runs correctly (no OOM kill, no
start-up timeout from CPU starvation, the same verdict); not the `[environment]` cap and not what makes a trial fast.
Derivation: **memory**, the largest sum over the phase's containers of cgroup `anon + shmem`, × 1.2, rounded up to a
GB; **GPU memory**, the largest sum in `nvidia-smi`, × 1.15, rounded up to 0.5 GB (Isaac Sim sizes its pools to the
card: the peak on the smallest card class it ran on); **CPU**, the 90th percentile of 30-second samples summed over the
containers, rounded up, at least one core per simulator process plus one for the agent; over several trials where there
are any.

Values come from `scripts/task_resources.toml` (rules matched against the directory name, later rules override
earlier keys), written into `task.toml` by `normalize`. A task no rule matches keeps the block its generator or
author wrote. `ci_checks/check-resources.py` checks the fields, the relations and the README.

### 2.10 Resource limits (v1.1.5; judged inside the trial from v1.2)

A trial should not take more than its share of the machine. Every task therefore states **limits**, the most the agent
phase may use, shown to the agent in `instruction.md`. When enforcement is on, exceeding one is the agent's failure,
graded like a wrong deliverable. They sit between the minimums of §2.9 and the docker caps. All sizes are GiB.

| Item | Level | Basis |
|---|---|---|
| `[metadata.resources.limits]` and `[metadata.resources.caps]` with every field below | Default | [CI] |
| `scope = "trial"` in privileged mode, `"agent"` in the standard modes (the mode registry's field, §2.16) | Default | [CI] |
| `instruction.md` has `## Resource limits`, equal to what `task_conventions.py` renders, after `## External material` and before `## Time limit` | Default | [CI] |
| Relations: memory and GPU memory `min ≤ limit` (scope trial); `max_gpu_memory_gb > 0` only where the limited containers have a GPU; `trial_max_* ≥ min_*` and `≥` the limit (scope trial: equal, unless a benchmark-owned observe-only service exists); the scope's memory caps `≥ 1.2 × max_memory_gb` and `≥ max_memory_gb + 2`; `pids ≥ 8 × max_processes` for the bound services; a cap for every compose service (`rcb_*` helpers aside); every declared cap is the applied one (`caps.main` = `[environment]`, others = the compose file's `cpus` / `mem_limit` / `pids_limit`); scope agent: `max_memory_gb ≤ [environment].memory_mb / 1024`; `min_cpus ≤` the CPU caps of all services together; `verifier_min_memory_gb ≤` the memory caps of the sidecars a collect hook replays in | Default | [CI] |
| `measured` says what the values rest on; limits sit with a generous margin above measured peaks (e.g. `max(1.5 × peak, peak + 4 GiB)`) | Recommended | [new] |
| The oracle passes within the limits | Default | from v1.2 (the calibration batch) |
| Enforcement inside the Harbor trial (below) | Default | from v1.2 |
| Values uniform within a benchmark and mode (or family) | Recommended | [new] |

`[metadata.resources.limits]`:

| Field | Type | Meaning |
|---|---|---|
| `scope` | string | `"trial"` = every container the agent drives (privileged: `main` and any service it starts or controls). A service that is the benchmark's own and outside the agent's control (`BENCHMARK_SERVICES` in `scripts/rcb_monitor/inject.py`) is observed and recorded only; `"agent"` = the agent's container only (standard modes: the `sim` sidecar is recorded, never a failure) |
| `max_gpu_memory_gb` | float | GPU memory of the scope's processes, summed (NVML per process; what a process reserves counts); 0 = no GPU |
| `max_memory_gb` | float | memory of the scope's containers, summed (cgroup `anon + shmem`; without a cgroup, PSS) |
| `max_processes` | int | processes (thread groups) in the scope |
| `max_disk_gb` | float | growth of the files under `disk_paths` in the agent's container since the monitor's first complete measurement (before the harness is installed, so its install counts) |
| `disk_paths`, `disk_exclude` | list of strings | absolute paths measured / skipped (today `["/app", "/tmp", "/root"]` / `[]`); `/dev/shm` is memory |
| `sustain_sec`, `window_sec` | float | a violation: above a limit for at least `sustain_sec` in total within any `window_sec` (60 / 120 s); disk: two measurements in a row; gaps never count against the agent |
| `trial_max_gpu_memory_gb`, `trial_max_memory_gb` | float | expected peak of the whole trial, every container, for schedulers; not a failure condition |
| `measured` | string | provenance of the limits |

`[metadata.resources.caps]`: one inline table per compose service, `{ cpus, memory_gb, pids }`, the docker caps the
compose files apply; `main`'s CPU and memory caps are Harbor's `[environment]` values, so `normalize` sets
`[environment].memory_mb = caps.main.memory_gb × 1024` (the kernel's cap sits above the limit, so that the monitor sees
a violation before the OOM killer acts). CPU is never a limit, only a cap. An OOM kill by the kernel in a container in
scope, at that container's own cap, is a violation.

**A CPU cap above the host's CPU count means the host's count.** Docker refuses a container whose `cpus` exceeds the
machine's, so a runner clamps every CPU cap to the host's CPU count in the copy of the task it runs
(`scripts/clamp_cpus.py`, applied by `scripts/run_agent_batch.sh`); the task's files keep their values. Memory and pids
caps are never clamped.

**The switch.** `RCB_LIMITS_ENFORCE`, a run-time environment variable read by the monitor (compose default
`${RCB_LIMITS_ENFORCE:-0}`, so turning it on does not change the digest):
- `1` / `true` (hard): once the monitor confirms a violation, it kills the scope's processes and the verifier fails the
  trial: `reward.txt` = 0, `success = 0`, `success_before_limits` = the grader's verdict, `resource_limit_exceeded = 1`;
  never retried.
- `0` / `false` (default): observe and record only; the verifier reports peaks and violations
  (`limits_violation_observed`, `/logs/verifier/resource_limits.json`) and does not change the verdict, except that a
  benchmark-owned service killed for memory in an episode that did not succeed is `infra_error` (below). A missing
  record is only reported (`resource_monitor_missing = 1`).
- any other value: the monitor kills nothing and records a fatal event; the verifier reports `infra_error = 1`,
  `resource_switch_error = 1`.

**What fails a trial** (enforcement on) is exactly: a limit exceeded for `sustain_sec` within `window_sec` (disk: two
measurements in a row), or a kernel OOM kill in the scope at the container's own cap. Nothing another trial does on the
same host can.

**Out-of-memory kills.** The monitor reads each container's cgroup v2 `memory.events` (`oom_kill`, `oom`) in a thread
of its own, many times a second, until the record is sealed (the first collect hook), and records each kill with its
cause: `"cap"` when the container's own `oom` counter rose with it (or within 10 s before), else `"host"`. Then:
- a `cap` kill in the scope is the violation above (`over_oom = 1`, `resource_oom_kills`);
- a `host` kill in the scope is never a violation: with enforcement on the trial is not a result (`infra_error = 1`,
  `resource_host_oom = 1`), with it off it is reported and the verdict stands;
- a kill in a **benchmark-owned service** (a `sim` sidecar, a scorer) is recorded, never a failure; if the verdict is not
  a success, the trial is not a result (`infra_error = 1`, `resource_service_oom = 1`) in both settings. A success
  stands.

**Host protection** (enforcement on only), each an `emergency_kill` event, counted in `resource_emergency_kills`, shown
in `usage.json`, and never a violation by itself: GPU memory of the scope above 1.5 × `max_gpu_memory_gb` at one sample
kills the scope's process holding the most GPU memory; where the runtime applies no kernel memory cap, memory above the
sum of the declared caps kills the scope's largest process.

**Enforcement (v1.2).** Violations are judged by the Harbor trial itself, so every harness applies the same rule; a
trial a pool kills to protect its host is an operations abort (`killed_by_pool`), not a graded result.
- docker caps on every compose service;
- a monitor sidecar `rcb_monitor`, outside the agent's container, samples GPU memory, memory, processes, disk and OOM
  kills every few seconds into its own record (`rcb-monitor/1`), seals it in the first collect hook, and writes the
  current values to `/run/rcb-limits/usage.json` in the agent's container;
- the verifier recomputes violations from the raw samples with its own copy of the limits (`tests/`). A missing,
  unsealed, fatal or mostly empty record is `resource_monitor_missing = 1` (with enforcement on also `infra_error = 1`).

What the record can say: gaps never count against the agent, and more than 10 % of the agent phase unobserved makes
the record unusable; a disk walk that cannot finish is a gap whose partial sum is a lower bound; GPU samples NVML cannot
attribute per process (MIG, vGPU) are `gpu_unmeasured`, never a silent 0, and more than 10 % of them on a task with a
GPU limit make the record unusable.

The values live in `scripts/task_resources.toml` (`[[limit]]` and `[[cap]]` rules) and are written by `normalize`,
which also renders the paragraph and a README line; `ci_checks/check-resources.py` checks them.

**Rendered paragraph** (privileged; the standard modes say "Limits for your agent environment, your own container only
(the simulator in the `sim` service is the benchmark's and does not count)"):

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

### 2.11 External material and the network

An agent solves a task itself. It may install the packages it needs and read whatever is installed in its container,
the simulator's and the benchmark's own source included; it does not search the web for, or download, a ready-made
solution to the task. This is an honour rule, backed by a network that reaches the model APIs and the package
registries and not GitHub, Hugging Face or the general web. What an image ships is therefore fair game, which is why it
should hold no answer (§2.7, [LEAKAGE.md](LEAKAGE.md), which also lists the PyPI distributions known to carry a
benchmark's solutions).

| Item | Level | Basis |
|---|---|---|
| The agent may install packages (pip, apt) and read anything installed in its container; it does not search for or download a ready-made solution (published or reference solutions, recorded demonstrations, policies trained for the task) | honour rule | stated in every instruction |
| A trial that fetched a solution is flagged and the owner decides case by case; installing a general-purpose package is never a violation, and a refused request is an attempt, flagged for a look | Default (how results are judged) | [new] |
| `[agent] network_mode = "allowlist"`, `allowed_hosts` = `scripts/set_agent_egress.py` `HOSTS`: the model APIs' hosts and the package registries (`PACKAGE_HOSTS`) | Default | [CI] |
| The list is the one switch (a run without restriction: `set_agent_egress.py public` on a copy of the tasks, docs/RUNNING.md) | Default | [new] |
| What the task needs at run time (assets, robot models, packages, caches) is in its image or the task directory | Default | [current] |
| Every `instruction.md` states the rule in the same words under `## External material` (`task_conventions.py` `EXTERNAL_TEXT`) | Default | [CI] |
| A task may add stricter rules of its own, never looser ones: `[metadata.honour] stricter = "..."`, rendered after the baseline as "Additional rules for this task (stricter than the above): ..." | Optional | [CI] |
| The harness offers the model no tool that runs outside the container (D11) | Default for official runs | [new] |
| A run through the usage gateway narrows the agent's egress to the gateway and the package registries; the gateway forwards model-API calls only (§5) | Default for official runs | [new] |

The paragraph in every `instruction.md`:

> ## External material
> You may install packages you need (pip, apt), and you may read anything installed in your container, the
> simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web
> for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or
> policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the
> package registries (PyPI, Debian / Ubuntu archives) only.

**Open egress.** A benchmark may choose open egress for its tasks when finding and adapting public work is part of
what they measure; its doc says why, its tasks set no `[agent]` network policy (Harbor's default, open) and carry the
benchmark's own `## External material` paragraph, and its results are compared only with results under the same
network setting. Today the choice is implemented by three lists keyed by directory prefix, which agree:
`ci_checks/check-verifier-isolation.sh` `OPEN_EGRESS`, `scripts/task_conventions.py` `EXTERNAL_OPEN` and
`scripts/set_agent_egress.py` `OPEN_EGRESS`. A task of such a benchmark that declares the allowlist is an allowlist task
in every respect.

Who reaches what in a trial (Harbor's egress control puts `main` and every compose service without its own network
setting in one network namespace; §2.6 keeps such a setting off every service but the monitor):

| | While the environment starts and the harness is installed | During the agent phase |
|---|---|---|
| The agent's container (`main`) | public (the harness is installed from its registry) | the allowlist; through the usage gateway, the gateway's address and the package registries (and `chatgpt.com` for Codex with a ChatGPT login) |
| The `sim` sidecar and other services | public; it needs nothing | the same as `main` (one namespace) |
| `rcb_monitor` | none | none |
| The verifier (its own sandbox, afterwards) | | `no-network` |

With the gateway on, the runner starts each job from a copy of the task whose allowlist is the gateway's address and
the package registries (`scripts/set_agent_egress.py only <hosts>`), and the gateway forwards only the requests listed
per provider in `scripts/usage_gateway/api_paths.json`, answers every other one 403 and records it
(`<trial>/gateway/usage.jsonl`, `totals.json` `refused_paths`). A model request is forwarded as it is or not at all: it
must be one JSON object, every tool it declares must be of a type the agent runs itself (`client_tool_types`); a request
declaring a provider-side tool, search field or fetch-by-URL content is refused (`server_tool`), an unreadable one too
(`body_unreadable`). A refusal is an attempt, recorded for a look; a harness's start-up probe is not counted. Without
the gateway (a bare `harbor run`), the task's own allowlist applies: not for official runs.

### 2.12 Time cutoff

Every task gives the agent a fixed wall-clock time, its **cutoff**, and says so in the last section of its instruction
together with the request not to cheat, in one format in every task (after Terminal-Bench).

| Item | Level | Basis |
|---|---|---|
| Each task sets its own cutoff: `[agent] timeout_sec`, a whole number of seconds within D8's cap, set by its author (a generated benchmark: a constant of its generator) and stated in the pull request. No central table | Default | [CI] (`check-cutoffs.py`, per task) |
| One number for all of a benchmark's tasks of a mode, or the pull request says why | Recommended | [review] |
| `normalize` writes from the number the `## Time limit` section, the README's `Agent time budget` row and, in the standard modes, the `sim` service's `RCB_WALL_CLOCK_S` | Default | [CI] |
| `instruction.md` ends with `## Time limit`, equal to what `normalize` renders for the number and mode, nothing after it | Default | [CI] |
| Its first paragraph is the same in every task: `You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.` (seconds only, the number as in `task.toml`); its second says what the cutoff means in the mode, the same words in every task of the mode (`CUTOFF_NOTE`) | Default | [CI] |
| The instruction states the limit nowhere else as a duration (§2.5) | Default | [CI] (a heuristic; a reviewer still reads the text) |
| Nothing is added to the instruction on its way to the agent (no prompt template, no extra instruction in official runs) | Default for official runs | [current] |
| "Do not cheat" is §2.11's honour rule, not a second rule; installing packages is not cheating | Default (how it is read) | [new] |
| What stops the agent is Harbor's agent timeout, `[agent] timeout_sec`, no multiplier in official runs; Harbor counts it around the agent's run only (after the environment is up and the harness installed). In the standard modes the `sim` service's start-up not finished by then is waited out inside the agent's time | Default | [current] |
| At the cutoff the trial is graded as it stands: privileged, what is in `/app/output/`; standard modes, the episode as the `sim` service holds it. A timeout is a result, not an infrastructure error | Default | [current] |
| The `sim` service's clock (`RCB_WALL_CLOCK_S`: `/spec.budget.wall_clock_s`, `meta.time_left_s`) reports the same number, counts from the agent's first request to the service (logged, kept over a restart) and ends nothing ([`STANDARD_MODE.md`](STANDARD_MODE.md), "The agent's clock"). A service that ends the episode on its own clock says so in the benchmark's own text | Default | [CI] for the number; the service layers' tests |
| Changing a cutoff: its pull request sets the new `[agent] timeout_sec` (or the generator's constant, then a render) in both twins, normalizes and states old -> new, who decided and why (label `cutoff-change`). The task changes in place (§2.8); results under another cutoff are reported separately (D8) | Default | [new] |
| A new benchmark adds its label to `scripts/task_conventions.py` `BENCHMARKS` (directory prefix -> name) in its shared-files pull request (D6) | Default | [CI] |

**The section** (privileged mode, 3600 s; `scripts/task_conventions.py` `CUTOFF_HEADING`, `CUTOFF_SENTENCE`, `CUTOFF_NOTE`):

> ## Time limit
> You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
>
> This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Installing packages is not cheating (`## External material` above).

Standard and standard-realtime modes, second paragraph:

> This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Installing packages is not cheating (`## External material` above).

Not derived from the cutoff: the token budget (§5), the resource limits (§2.10), reset budgets (§4.5), step caps,
verifier timeouts. Collect-hook and verifier budgets sized for an episode as long as the agent's time are looked at when
a cutoff is raised. [`CUTOFFS.md`](CUTOFFS.md) explains the rules and keeps the history of the numbers.

### 2.13 Seeds

A task has a default seed and may allow others; each seed names one instance of the task (its scene and start,
replayed bit for bit); where an upstream has no seed, seed 0 names the task's one frozen instance.

| Item | Level | Basis |
|---|---|---|
| `[metadata.seeds]`: `default` (an integer); `allowed`, the seeds a trial may run from, `default` among them: a list (`[0, 3, 7]`), a range with both ends included (`{ from = 0, to = 100 }`), or `"any"`; `oracle`, the seeds the reference solution is for (not empty for `full` / `partial`, empty for `none`); `build`, `"frozen"` (default: every allowed seed is a committed instance) or `"runtime"` (the task builds a seed's instance itself; needed for a range and `"any"`). `normalize` completes what a generator leaves out (`default` = `instance_seed` or 0, `allowed = [default]`, `oracle = [default]` or `[]`) | Default | [CI] (`check-seeds.py`) |
| `instance_seed`, where present, equals `default`; a standard or standard-realtime task has its privileged twin's `default`, `allowed` and `build` (where it has a twin) | Default | [CI] |
| With `build = "frozen"`, every other allowed seed's instance is `tests/seeds/<seed>/instance.json` (or `.npz`) of the task that holds the pair's instance; `tests/seeds/` holds nothing else | Default | [CI] |
| `build = "runtime"`: given a file `seed`, the environment builds that seed's instance deterministically and the verifier builds the same one from its own copy; the benchmark's doc says how and its generator's tests show it on a sample | Default | [new] |
| Another seed's instance, or a `seeds` directory, under `environment/` | Avoid | [CI] |
| The runner chooses the seed, never the agent: `scripts/task_seed.py materialize <task> --seed <S> --out <dir>`; results record the seed | Default | [new] |
| Official batches draw a seed uniformly from `allowed` per trial; a run on the default seed only says so | Recommended | [new] |
| The submitter allows only seeds they checked (`nop` 0, the oracle or review covered them; for a range or `"any"`, the generator's rule); a change of `allowed` is a new digest with a Change Log entry | Default | [new] |
| Reference solutions are per seed and score 1 on every seed in `seeds.oracle` | Default | [new] |
| In the standard modes the seed and its instance stay in the service and the verifier (§4.5) | Default | [current] |

### 2.14 Scene dynamics

A task is **dynamic** when something in its scene other than the robot can do work by a force other than the robot's
own and gravity: a body that starts with a velocity, an actuated or scripted body (a conveyor, a scripted push, a timer
that moves a part), an opponent or another agent. Everything else is **static**: the world waits while the agent
thinks. Static, by this definition: settling under gravity, material the robot moves, a chain the robot started;
passive springs and elastic material that give back what the robot put in; a world change applied once and instantly
when the robot comes near; visual-only or state-only change; an episode horizon; a robot that must balance actively.
Dynamic: a change on a clock, or a mechanism that keeps moving bodies after the robot started it.

| Item | Level | Basis |
|---|---|---|
| `[metadata] dynamics ∈ {static, dynamic}`, the value of `scripts/task_dynamics.toml` for the task (its family's exception, else its benchmark's row, each with its `why`), written by `normalize` | Default | [CI] (`check-dynamics.py`) |
| A new benchmark adds its row (and its families' exceptions) in the pull request that adds its tasks | Default | [CI] |
| The same family has the same value in every mode | Default | [CI] |
| A `dynamic` task may have a `-standard-realtime` twin (§4b); a `static` one needs none | Optional | [new] |

### 2.15 Modes a benchmark ships

A benchmark ships any subset of the modes, and a family within it may lack a mode the benchmark has; what it leaves
out, and why, is stated in its doc.

| Item | Level | Basis |
|---|---|---|
| The modes a benchmark ships are the modes it has tasks in (a standard task without a privileged twin is accepted when its benchmark has no privileged task, `task_conventions.bench_has_mode`) | Default | [CI] (`check-instance-copies.sh`) |
| Where both exist, a task's privileged and standard versions have the same `[agent] timeout_sec` | Default | [CI] (`check-cutoffs.py`) |
| Twins share one frozen instance, success rule and seeds (§2.2, §2.13) | Default | [CI] |
| A standard or standard-realtime task without a privileged twin carries its own frozen instance in its sidecar (the verifier's copy byte-identical); its README's Twin row says why. In a benchmark that has a privileged mode, the task is listed with its reason in `scripts/task_conventions.py` `NO_TWIN` | Default | [CI] (`check-instance-copies.sh`) |
| A privileged task without a standard twin (README: "privileged only") | Optional | [current] |
| Results are reported per mode; a mode a benchmark does not ship is "not offered", not a failure | Recommended | [new] |

### 2.16 Adding a mode

The modes are not a closed list: anyone may propose a new one by pull request. They live in one registry,
`MODE_REGISTRY` in `scripts/task_conventions.py`; everything that parses or branches on a mode reads it (`mode_of`,
`base_of`, `twin_of`, the limits' scope, the twins' equal cutoffs, the task list, and the checks, which get it from
`python3 scripts/task_conventions.py modes`). An entry gives the mode's name (= directory suffix and `[metadata] mode`),
its column label, its PROTOCOL section, whether the simulator runs in a trusted `sim` sidecar, whom the limits bind, the
`protocol` values its tasks may declare, its twin mode, and the mode whose cutoff it equals (`same_cutoff_as`, if any:
standard has `"privileged"`).

| A new-mode pull request contains | Level | Basis |
|---|---|---|
| A name (lower case, words joined by `-`, not a suffix of another mode's name nor ending in one, no version or duration) | Default | [CI] |
| A PROTOCOL section of its own defining what the agent gets, what is graded, the time and reset rules, and which failures are infrastructure (`infra_error`) and which the agent's | Default | [new] |
| Its `MODE_REGISTRY` entry, its `CUTOFF_NOTE` and, where it has a protocol, a reference implementation (§6) | Default | [CI] |
| CI support through the registry; a mode-specific rule is a new check keyed on a registry field, with a `check-ci-selftest.py` case | Default | [CI] |
| At least one benchmark using it, with the oracle and `nop` evidence of §2.7 | Default | [new] |
| `docs/TAXONOMY.md`, `docs/REVIEWING.md` where reviewers check something new; results reported separately (§5) | Default | [new] |
| The runner side (batch_eval_live, the results site) told the new suffix in the same change | Recommended | [new] |

## 3. Privileged mode (`mode = "privileged"`, `task_type = "trajectory"`)

| Item | Level | Basis |
|---|---|---|
| Deliverable `/app/output/trajectory.npz` (format defined by the task's instruction) | Default | [current] |
| The generating script at `/app/output/gen.py` | Recommended | [current] |
| Graded by open-loop replay from the frozen initial state in a fresh process | Default | [current] |
| ≥ 2 replays with matching final-state hashes, reported as `deterministic` | Recommended (the field: Default) | [current] |
| One replay instead: a benchmark whose tasks are measured to replay bit for bit may grade by one fresh-process replay (`deterministic = 1`, `determinism_checked = 0`, `replays = 1`), starting from the frozen state shown by the recorded initial-state hash (a mismatch: `instance_mismatch` with `infra_error`); its doc states the rule, the measurement and what it gives up | Optional | [new] |
| Success judged on the state at the end of the replay ("success at any step" needs a stated reason) | Recommended | [current] |
| The frozen instance copied into both `environment/` and `tests/` with its expected initial-state hash, checked on rebuild | Recommended | [current] |
| A host that rebuilds a different state is graded `instance_mismatch` with `infra_error`; a scene build does not depend on the host (no unsorted directory listing, no wall clock) | Recommended | [current] |
| Unlimited resets, privileged state, planning primitives, self-replay | Optional | [current] |
| Tool API shape | task-defined | [current] (recommended: `Session` with `reset` / `replay` / `status` / `save_trajectory`) |
| Self-reported cost (resets, simulation steps) in `agent_*` fields | Recommended | [current] |
| `task_type = "policy"` (a skill as code, graded offline in the verifier, §4c) | Optional | [new] |

## 4. Standard mode (`mode = "standard"`): `eai-standard/2.x`

Wire details (endpoints, RCB1 frames, `meta`, error codes, crash recovery) are in
[`STANDARD_MODE.md`](STANDARD_MODE.md), one part per version. This section lists the conventions.

### 4.0 Versions
| Version | Date | Content |
|---|---|---|
| eai-standard/2.1 | 2026-09-30 | the base: `/submit` action chunks, `/observe`; binary RCB1 responses; 82-column proprioception, optional depth noise; crash recovery |
| eai-standard/2.2 | 2026-10-01 | additive extension ([`STANDARD_MODE.md`](STANDARD_MODE.md) Part 2) with crash recovery; shared layer `scripts/eai_standard/` |
| eai-standard/2.3 | 2026-10-08 | 2.2 + the realtime capability (§4b; Part 3); served by standard-realtime tasks |
| eai-standard/2.4 | 2026-10-08 | 2.3 + the operations capability (Part 4): operation ids and request deadlines (408 / 409), `GET /operations/<id>`, a service-owned call watchdog, a physics-tick ledger, fsynced journals; standard tasks may use it; reference implementation `scripts/eai_standard/v2_4/` |

Which benchmarks serve which version: their docs and `[metadata] protocol`. Standard services report 2.1, 2.2 or 2.4,
standard-realtime services 2.3; the shipped clients accept every 2.x version and the former `rcb-limited/2.x`
spelling. No task declares a version before 2.1.

**Core rules.** The simulator runs in a sidecar the agent cannot open; four endpoints; RCB1 binary responses; resets
only as the task's budget allows; no step limit, the wall clock the only hard budget; crash recovery resumes the same
episode; success is decided on a replay.

### 4.1 Topology
| Item | Level | Basis |
|---|---|---|
| Simulator in a compose sidecar named `sim`; no simulator or simulation code in the agent container | Default | [current] |
| GPU reservation on `sim` only (if a GPU is needed) | Default | [current] |
| `ports:` / `expose:` on the sidecar | Avoid | [current] |
| Service on `0.0.0.0:8000`; the client tries `http://sim:8000`, then `http://localhost:8000` | Default | [current] |
| The socket opens only when the scene is ready; the client retries | Recommended | [current] |
| `restart: on-failure:N`, N ≥ 3 | Default | [current] |
| The agent image ships `rcb_client.py` (`Robot.spec / status / submit / get_obs`) and `rcb1.py` | Default | [current] |
| The instruction documents client usage, action types and rules | Default | [current] |

### 4.2 Endpoints
| Item | Level | Basis |
|---|---|---|
| `GET /spec`, `GET /status`, `POST /observe`, `POST /submit` | Default | [current] |
| Everything else returns 404, except endpoints a minor version adds (2.2: `POST /kinematics`); `/reset` exists only with a reset budget | Default | [current] |
| `/spec` has `protocol`, `action_types` (each with `dim`, `layout`, units or limits, `semantics`), `cameras`, the proprioception layout, `budget` (`reset`, `wall_clock_s`) | Default | [current] |
| `/spec` also has `task_text`, `max_chunk_s`, `max_watch_s`, `physics_hz` or `control_dt`, `on_service_error`, `max_frames_per_call` | Recommended | [current] |
| `/status` has `calls`, `done`, `reason`, `elapsed_s` and a step counter | Default | [current] |
| Step counters named `rows` and `sim_steps` (old names kept alongside) | Recommended | [new] |

### 4.3 Encoding (RCB1)
| Item | Level | Basis |
|---|---|---|
| Responses are RCB1 frames: `"RCB1"`, 4-byte little-endian header length, header JSON, blobs | Default | [current] |
| Images or video as base64 in JSON | Avoid | [current] |
| Part kinds `mp4`, `array` (C-order raw bytes, dtype and shape in the header), `jpeg`, `json`, `bytes` | Default | [current] |
| `last/<cam>` in every response; `video/<cam>` / `frames/<cam>` on request | Default | [current] |
| `proprio` part: one row per frame, columns as in `meta.proprio.layout`; which columns is task-defined | Default | [current] |
| `depth/<cam>`, depth noise, `meta.cameras`, `meta.task` | Optional | [current] |
| `meta` has `calls`, `sim_time_s`, `time_s`, `time_left_s`, `proprio{layout, now}`, `done`, `reason` and a step counter | Default | [current] |
| Limits: requests ≤ 64 MB (413), ≤ 3000 frames per call (400), responses over 256 MB drop frames/depth and say so in `meta.degraded` | Recommended | [current] |

### 4.4 Actions
| Item | Level | Basis |
|---|---|---|
| At least one action type, fully described in `/spec` | Default | [current] |
| Which action types (`joint_position`, `ee_delta`, `ee_pose`, whole-body IK, …) | task- or benchmark-defined, consistent within a benchmark | [current] |
| `dt` a multiple of the physics or control step; otherwise 400, never rounded | Default | [current] |
| Out-of-limit values clipped and reported in `clipped`, not rejected | Default | [current] |
| `linear` / `hold` interpolation; chunks ≤ `max_chunk_s` | Recommended | [current] |
| Planner-executed actions such as `ee_pose`, with frame, quaternion order and end-effector reference in `/spec` | Optional | [current] |
| Action dtype (float32 / float64) | task-defined, stated in `/spec` | [current] |

### 4.5 Budget and privileged information
| Item | Level | Basis |
|---|---|---|
| Reset budget: each task declares its own N (`budget.reset`; the `sim` service's `RCB_RESET_BUDGET` default, which stays a run-time override; the instruction states it). Template default: 0 in standard mode (one trial is one episode), 10 in standard-realtime (§4b). A benchmark's doc gives its number and why | Default | [CI] for the realtime declaration (`check-realtime.py`) |
| The capability: `POST /reset` within the budget, only the last episode graded, a success ends the trial ([`STANDARD_MODE.md`](STANDARD_MODE.md)); results state N, and results with N > 0 are never ranked with N = 0 | Default | [new] |
| No step limit; the wall clock is the only hard budget; simulation steps are reported as cost | Default | [current] |
| A technical episode cap stated in `spec.max_control_steps` | Optional | [current] |
| Exposing object poses, scene files, seeds, the success predicate, segmentation, object contact forces | Avoid | [current] |
| Contact or safety telemetry that the task contract depends on (the agent is judged, or a success held for review, on a reading it could not know otherwise), declared field by field in the benchmark's doc; nothing else is published, and a reading that gives an object's pose is not covered | Optional | [new] |
| Robot proprioception, camera calibration, task text | Optional | [current] |

### 4.6 Errors (no physics executed)
`400` invalid input (type, dimension, NaN/inf, `dt`/`seconds` invalid, chunk too long, frame limit, malformed body);
`409` episode over; `413` body over 64 MB (recommended; the client refuses such a body before sending it); `500`
simulator error, and the episode ends with `reason = "error"`; the client raises `EpisodeOver` on 409 and 500. [current]

### 4.7 Episode and crash recovery
| Item | Level | Basis |
|---|---|---|
| The episode starts when the service is ready; the seed stays inside the service | Default | [current] |
| End condition defined by the task and stated in the instruction and in `/spec` (`episode`) | Default | [current] |
| The predicate is evaluated once more at episode end | Default | [current] |
| Crash recovery: every executed step journaled, a checkpoint (step count, state hash) per completed call; after a restart the journal is replayed, the hash checked and the same episode continues — never a reset | Default | [current] |
| At most 2 resumes (`RCB_MAX_RESUMES`); a third crash ends the episode `sim_crashed_on_call` if every crash happened inside a call, else `sim_crashed` (`infra_error = 1`); a written verdict is never overwritten | Recommended | [current] |
| Startup watchdog and back-off before rebuilding | Recommended | [current] |
| Per-simulator resume rule: a simulator declared nondeterministic records the hash, and a mismatch continues the episode with `resume_state_mismatch` ([`STANDARD_MODE.md`](STANDARD_MODE.md) §13.1); the verdict still comes from fresh replays (except under §4.8's live grading) | Optional | [new] (2.2) |

### 4.8 Evidence and grading
| Item | Level | Basis |
|---|---|---|
| The sidecar writes `/data/episode.jsonl`, `/data/trajectory.npz` and `/data/final.json` (with `finalized`) | Default | [current] |
| The replay's verdict (`replay_success`, `deterministic`) is in `final.json` before any video is rendered and stands from then on | Recommended | [new] |
| `/data/calls/NNNNNN/`, `replay.mp4`, `replay.last.png` | Recommended | [current] |
| `artifacts` declares the evidence from `service = "sim"` and keeps `"/app/output/"` | Default | [current] |
| `[[verifier.collect]]` waits for `server.pid`, sends SIGUSR1, waits for `finalized` | Default | [current] |
| Needing a custom agent adapter to finish an episode | Avoid | [new] |
| A fresh replay decides: `success = replay_success ∧ deterministic`; `∧ live_success` when a live predicate exists (recommended) | Default | [current] |
| Live grading, for physics that does not replay bit for bit: a task measured not to (its frozen instance records it, e.g. `"determinism": "verdict"`; the benchmark's doc names the tasks and the measurement) is graded by the live episode the trusted service ran, `success = live_success` from the sidecar's `final.json`; the fresh replays still run and are reported but never decide; `reward.json` says `graded_by_live = 1` and reports `resumes` and `resume_state_mismatch`. Such a task ships no privileged twin (`NO_TWIN`, §2.15) | Optional | [new] |
| One replay: a benchmark whose tasks are measured to replay bit for bit may replay the episode once, `success = live_success ∧ replay_success` (the live predicate then required); `deterministic` is still measured against the live end state (`state_identical`, `determinism_checked = 1`, `replays = 1`) and reported. A replay without a result, or not from the frozen state, is `infra_error` | Optional | [new] |
| The verifier grades `final.json` only, without network access | Default | [current] |

### 4.9 Live recording (sidecar only)
`live.mp4`, `live_timeline.jsonl`, `live_segments.jsonl`, `trajectory_live.f64`, `startups.jsonl` — recommended. If
recorded: rendered from the replay by default, frames stamped with the call, never affecting the verdict.

## 4b. Standard-realtime mode (`mode = "standard-realtime"`): `eai-standard/2.3`

Standard mode on a clock that does not stop. Everything in §4 holds (sidecar topology, endpoints, RCB1, actions,
privileged information, crash recovery, evidence, replay grading) except where this section says otherwise. Wire
details: [`STANDARD_MODE.md`](STANDARD_MODE.md) Part 3. The time model: the world runs at 1/S of real speed, a command
takes effect at the next control step, all agent latency counts, the agent's own program may act.

| Item | Level | Basis |
|---|---|---|
| `protocol = "eai-standard/2.3"`; `/spec.timing` with `realtime: true`, `slowdown`, `control_dt`, `wall_s_per_control_step`, `max_ahead_steps` | Default | [CI] (protocol) |
| An episode starts paused; its clock starts at its first `/submit` (or `/observe` with `seconds > 0`) and then runs one control step every `control_dt` × S s of wall time, whatever the agent does; after a reset or a crash recovery the episode is paused again | Default | [new] |
| `/submit` writes a plan of future targets from control step `at` (default: the next one) and answers at once; rows whose steps have run are dropped (`late_steps`); the last target is held when the plan runs out | Default | [new] |
| Grading replays the targets the simulator **applied** at each control step (the journal), so the replay equals the live run whatever the timing; latency and jitter are recorded (`ticks.f64`) and never decide | Default | [new] |
| Clock evidence in `final.json`, repeated in `reward.json` as numbers (a missing one is 0): `clock_s`, `max_lag_s`, `stalls` (times the service, more than 0.5 s behind, dropped the debt), `stalled_s`, `stalled_share`, `held_steps`, `late_steps`, `requests_refused`, `request_busy_s`. They flag a trial, never decide it | Recommended | [new] |
| Requests are bounded in what they cost the clock: bodies are read and checked off the simulator's thread (over 1 MiB of JSON in a separate process); behind the clock, control steps run before waiting requests; a rendering request that stalls by itself holds the next one back four times as long; cameras are rendered at most once per control step | Recommended | [new] |
| **Slowdown S**: each task declares it: the `sim` service's `RCB_SLOWDOWN` default (a run-time override), `[metadata] slowdown` (written by `normalize` from it), the README's "Real time" row and the instruction (`S = <S>`, or "in real time" for S = 1). Recommended value for a `dynamic` family's twin (§2.14), from the real-time factor RTF of its own service measured on the reference workstation (robot seconds per wall second with the clock flat out, `RCB_SLOWDOWN` ≪ 1, CPU-capped as in its compose file): **S = 1 when RTF ≥ 3**, else S ≈ 1.5 / RTF rounded up; the benchmark's doc records the measurement. Results with S ≠ 1 are reported separately and state S; official results use the task's S | Default | [CI] (`check-realtime.py`) |
| **Reset budget**: each task declares it (§4.5): the `sim` service's `RCB_RESET_BUDGET` default, `[metadata] reset_budget` where the task keeps it, and the instruction (its number, or "no reset" for 0; or a pointer to `spec()["budget"]["reset"]`). Template default **10**: an episode on a running clock is one attempt, often over in seconds, and the agent has no simulator to practise in. A benchmark that chooses another number says why in its doc | Default | [CI] (`check-realtime.py`: declared and consistent) |
| A simulator crash is an infrastructure failure, never the agent's: past `RCB_MAX_RESUMES` restarts the trial ends `sim_crashed`, a failed resume `resume_failed`, a simulator error that ends the graded episode `reason = "error"` — all with `infra_error = 1` | Default | [new] |
| The agent's controller runs in the agent's own container and streams targets through the client; no agent code runs next to the simulator | Default | [new] |
| A standard-realtime task shares its privileged twin's frozen instance and success rule where it has one (a task without a twin carries its own, §2.15); its instruction says that time does not stop | Default | [new] |

A benchmark's realtime tasks may add their own rules on top of these (a picture cost while the clock runs, rate limits
on watches, breaks between points in a sport); the benchmark's doc states them and its results are compared only with
results under the same settings. The interface, the encoding, crash recovery and the evidence stay §4's.

## 4c. Tasks a benchmark exports with its own service (`metadata.protocol` = the benchmark's own)

A benchmark that has its own task runtime (simulator service, referee, opponents, grader) may ship tasks its own
exporter writes, with that runtime unchanged inside the task, instead of this repository's `eai-standard/2.x` layer.
The task is a plain Harbor task in every other respect: §1 and §2 (verifier isolation, honour rule, egress, cutoffs,
resources and limits, seeds, README) apply. Which benchmarks do this, their protocols, slowdowns and opponents: their
docs.

| Item | Level | Basis |
|---|---|---|
| A manifest lists the exported directories with their source (`scripts/<bench>/exported.toml`: `name`, `source_task`, `revision`, `source_commits`) and the protocol each mode serves (`[protocols]`); the benchmark's generator renders none of them and fails a listed directory that is missing; CI accepts a manifest's protocol only for the directories it lists (`check-protocol.py`) | Default | [CI] |
| `metadata.protocol` names the benchmark's protocol and its version; its wire format is documented in the benchmark's doc and in the instruction, not in [`STANDARD_MODE.md`](STANDARD_MODE.md) | Default | [CI] (protocol) |
| No privileged twin (no trajectory deliverable); in a benchmark that has a privileged mode, `NO_TWIN` lists each one (§2.15) | Default | [CI] |
| The verdict comes from the trusted side only: the service's own record replayed in a fresh process, or an offline evaluation in the separate verifier; nothing the agent's container writes decides; the verifier has no network | Default | [CI] (isolation) |
| Real-time tasks state S (`[metadata] slowdown`, the service's own setting) and their reset budget as in §4b; a service without a reset capability declares none (no reset), and its instruction offers none | Default | [CI] (`check-realtime.py`) |
| Scripted opponents at a fixed level per task (`metadata.opponent_level`); success = the match is valid (the fresh replay repeats the live record) and the agent's side won | Default (for matches) | [new] |
| No crash resume where a resumed episode would not be the recorded one: a simulator crash ends the trial with `infra_error = 1` | Default | [new] |
| Tasks whose deliverable is code (`task_type = "policy"`): the verifier runs it on requests the agent never sees, as an unprivileged user in its own process, without network, unable to read the simulator, the evaluator and the requests; a missing or unloadable deliverable is a valid 0 | Default | [new] |
| Untrusted code in the verifier never outlives its evaluation: every process it started is ended before anything is graded, it has a process limit, it cannot write the log directory or the report the grade is read from, and the reward files are written fresh; the evaluator's isolation probe checks each of these | Default | [new] |
| Results reported separately from the benchmark's other tasks, stating the protocol, S and the opponent level | Default | [new] |
| An exported task is refreshed by re-exporting; a fix made here to an exported file is recorded in the manifest (`patched`) and sent upstream | Recommended | [new] |

## 5. Results, cost, token budget
| Item | Level | Basis |
|---|---|---|
| Report success together with cost: tokens, money, turns, wall clock, simulation steps, calls | Recommended | [current] |
| Official results use Harbor's native agents (`-a codex`, `-a claude-code`, …), configured through environment variables | Default | [new] |
| Official runs go through the usage gateway, which forwards model-API calls only and is, with the package registries, the agent container's only egress; the harness offers the model no tool that runs outside the container (§2.11, D11). The runner flags a trial whose `totals.json` has `refused_paths`, `refused_server_tools` or `refused_bodies` | Default | [new] |
| **Token budget** per trial: input 100M (Harbor `n_input_tokens`, cache included), output 10M (`n_output_tokens`, reasoning included); exceeding either fails the trial; the results metadata records the budget and `over_token_budget` | Default | [new] (enforced while the gateway runs; otherwise open, §7 item 3) |
| Align reasoning effort, `max_turns`, token budget and `[agent].timeout_sec` before comparing agents | Recommended | [current] |
| Run id `<harness>-<model>-<effort>` | Default | [new] |
| Results are not committed: published on the results site and the Hugging Face dataset, keyed by run id | Default | [CI] for task directories |
| Results reported per mode; the standard modes state the protocol version and reset budget, standard-realtime also S | Default | [new] |

With the usage gateway on (`GATEWAY=1` in `scripts/run_agent_batch.sh`), once a trial's recorded input or output
reaches its budget the gateway refuses every further model request of that trial (HTTP 400, "token budget exceeded"),
the agent stops, and `<trial>/gateway/totals.json` records `over_token_budget = 1`. Budgets: `TOKEN_BUDGET_IN` /
`TOKEN_BUDGET_OUT`, default 100M / 10M. Without the gateway the budget would be applied after the run to Harbor's
counts; not implemented yet (§7 item 3).

## 6. Versioning and extensions
| Item | Level | Basis |
|---|---|---|
| `/spec.protocol` equals `metadata.protocol` | Default | [current] |
| 1.x interfaces (single-action `/step`, base64, unbudgeted `/reset`) | Avoid | [current] |
| 2.x minor versions only add (fields, endpoints, optional action types); existing clients keep working, and nothing §4 makes the default is removed | Default | [current] |
| Protocol changes: a protocol-change issue, then a shared-files PR updating the document, the reference implementation, the CI allowlist and an example task together | Default | [new] |

**`eai-standard/2.2`** ([`STANDARD_MODE.md`](STANDARD_MODE.md) Part 2). Depth `last` / `frames` (uint16 millimetres,
zlib), `frame_step`, `frame_time_s`, per-frame `extrinsic_cv`, camera intrinsics and mounting, `robot_spec`, `world`, a
stateless `POST /kinematics`, and a per-call wall-clock bound (`max_call_wall_s`, `meta.stopped`) — all optional
capabilities. Its services implement §4.7's crash recovery; the shared implementation is `scripts/eai_standard/`.

**`eai-standard/2.3`** (Part 3). 2.2 plus the realtime capability: `/spec.timing`, `/submit` with `at` answering at
once, `cameras: []` for no images, the `meta` / `/status` fields `running`, `planned_steps`, `lag_s` (and `start_step`,
`late_steps`, `plan_end_step` on a submit), and the evidence of §4b. Every 2.2 addition stays optional. Only
standard-realtime tasks serve it; 2.x clients connect to it unchanged.

**`eai-standard/2.4`** (Part 4). 2.3 plus the operations capability: `meta.operation_id` and
`meta.request_deadline_unix_s` on `/submit` and `/observe` (408 for an expired request, 409 for an id already admitted:
a call is never executed twice), `GET /operations/<id>`, a service-owned watchdog that ends a hung native call as an
infra error, a physics-tick ledger that resumes replay with the ticks each row took, and fsynced journals. Every earlier
addition stays optional; standard tasks may declare it, standard-realtime tasks stay on 2.3. The reference
implementation is `scripts/eai_standard/v2_4/` (`rcb_limited.py`, `rcb_client.py`; `rcb1.py` and `run.sh` are 2.2's),
copied unchanged into every 2.4 task.

**Not accepted:** step caps; single-control `step()` calls.

## 7. Migration status

The v1.0 migration (mode names and suffixes, `oracle` fields, `/logs/verifier` cleared first, numeric rewards, one
README layout, no `results/`, generators ending in `normalize`) was completed on 2026-10-01. The items keep their
numbers, because tasks and documents cite them; the record of each finished item (what changed in place, when, why) is
in [`PROTOCOL_HISTORY.md`](PROTOCOL_HISTORY.md).

Open:
1. ~~Images~~ done (2026-10-02): every base image is `ghcr.io/mll-lab-nu/eai-<name>`, public unless `BUILD_ONLY`.
2. Pinned pip versions in the standard-mode client image and the MuJoCo image; one digest-pinned client image.
3. The results pipeline publishes to the results site, and applies the token budget after the run for runs without the
   usage gateway (with it, the budget is enforced during the run, §5).
4. Solvability: tasks whose `oracle_evidence` is "none known" and the DexToolBench `partial` pairs have no verified
   positive example; until they get one, results report them separately from the tasks with a verified solution.
5. ~~Agent egress~~ done (2026-10-10 / 2026-10-11): every task on the allowlist with the honour rule (§2.11).
6. ~~Resource limits~~ done (2026-10-10, v1.2-rc): limits, caps, the monitor and the verifier step in every task,
   enforcement off by default (§2.10).
7. ~~Time cutoffs~~ done (2026-10-11 / 2026-10-12): the closing `## Time limit` in every instruction (§2.12).
8. ~~The agent's clock~~ done (2026-10-13): every standard service counts `time_left_s` from the agent's first request.

Decided (2026-10-02):
1. Success semantics stay benchmark-defined: each benchmark keeps its upstream's own rule (final state, first success,
   episode return, goal count), stated in its instructions and `docs/benchmarks/<bench>.md`.
2. Not yet implemented — standard-mode double check: the verifier replays the recorded `trajectory.npz` once more in its
   own sandbox; the sidecar's verdict stays authoritative, and a disagreement is a warning (`replay_mismatch`).
3. What each benchmark exposes to the agent in privileged mode is its own (no hiding of reward or success checks).
   Seeds: §2.13.
