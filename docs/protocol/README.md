# Robot Coding Bench — Task Protocol v2.0

The protocol is the four documents in this folder: this README (the conventions a task follows, and the binding
invariants of Appendix H), [`standard_mode.md`](standard_mode.md) (the `eai-standard/2.x` wire format of the standard
modes), [`running.md`](running.md) (official-run configuration, seeds, retries, gateway, resource enforcement, results;
enforced by the runner and scheduler) and [`leakage.md`](leakage.md) (where answer keys survive and how they are
removed). Metadata values, names and run ids are in [`TAXONOMY.md`](../TAXONOMY.md); each benchmark's own choices in
`docs/benchmarks/<bench>.md`.

**Recommended conventions, and eight invariants that bind.** Sections 1–7 describe how a task is usually built, so that
tasks from different benchmarks can be run, compared and reviewed the same way. They recommend; a task or a benchmark
may choose otherwise and says so where its readers look (its `task.toml`, its README, `docs/benchmarks/<bench>.md`).
CI reports a departure from them as an advisory warning, never as a failure. **Appendix H is not a recommendation.** Its
eight invariants keep results honest (no reward without solving the task, one verdict for one deliverable, results
compared only with comparable results). They hold for every task and every run, no task value, declaration or
benchmark document can override them, and the required CI job `invariants` fails a pull request that breaks one, as
the runner refuses a run that would. The only setting Appendix H leaves to the task's author is the agent's network:
the allowlist unless the task declares open egress (H.6).

Older tasks and code cite v1 section numbers (§2.10); the table at the end maps them.

## 1. What a task is

A task is a self-contained Harbor task directory under `tasks/<benchmark>/` (one folder per benchmark); the benchmark adds as little as possible on top of
Harbor's format. Anything not described here (the simulator, how a scene is defined, the privileged tool API, how a
verifier decides internally) is the task's own business.

| Recommended | Notes |
|---|---|
| `task.toml`, `instruction.md`, `README.md`, `environment/Dockerfile`, `tests/test.sh` (executable), `tests/Dockerfile`; `solution/solve.sh` when `oracle` is `full` or `partial` | `ci_checks/check-task-structure.sh` |
| `[task].name = "robot-coding-bench/<folder>"`; `[metadata]` `author_name`, `task_type` (`trajectory` / `policy`), `simulator`, `robot` ([`TAXONOMY.md`](../TAXONOMY.md)), `family`, `mode`, `expert_time_estimate_hours`, `oracle` (+ `oracle_evidence`), `protocol` (sidecar modes), the settings of §2 | `check-task-fields.sh`, `check-protocol.py` |
| The directory name `<base>-<mode>`, `<base>` = `<benchmark>-<family>-i<NN>` or the upstream name; no versions or durations in names | the mode is the whole suffix |
| All task code in the directory, copied in by its Dockerfiles; base images hold the simulator and its assets; nothing imports repository code at run time | a task's identity is its directory (H.8) |
| Every task is in the normal form `scripts/task_conventions.py` `normalize` writes (README layout, rendered sections, `DIGEST`) | `task_conventions.py --check` |
| Base images `ghcr.io/mll-lab-nu/efe:<name>-<images/<name>/VERSION>` (one public package, a tag per image), or `efe-private:<name>-<VERSION>` when `images/<name>/BUILD_ONLY` (one private package); every `FROM` / `image:` pinned to a tag or digest | `check-dockerfile.sh` |
| README in the standard layout (`# <dir>`, key table, Task, Difficulty, Reference solution, Verification, Compute resources, Details); no `results/` | rendered by `normalize` |
| A change to a published task, its scene included, is made in place: same name, a new DIGEST, a README Change Log entry | H.8 |

**What a contribution delivers.** The deliverable is the tasks only: task directories under `tasks/<benchmark>/`. No
task-generation code goes into the repository (generators, oracle searches, instance freezers, release builders stay
with their authors). What several tasks of a benchmark share may go in `embodied_first_exam/benchmarks/<benchmark>/`;
the recommended place is the benchmark's image (its `images/<name>/` Dockerfile and build), so the tasks get it from the
image.

## 2. Task-declared settings

Each task (or its benchmark's generator) chooses these and declares them; CI checks that the declarations agree with
each other, not that they take a particular value. The defaults are what templates write when a task says nothing.
Every trial records its **effective configuration** (protocol version, mode, cutoff, reset budget, S, seed, network,
validated; `scripts/task_conventions.py` `effective_config`), and results are ranked only among trials with the same
configuration (`config_key`; running.md "Results").

| Setting | Declared in | Default |
|---|---|---|
| Modes offered (§3): any subset; a task without its privileged twin says why in its README Twin row | the task directories it ships | — |
| Cutoff: the agent's wall-clock time, decided by the task's author | `[agent] timeout_sec` (a whole number of seconds) | 3600 s; at most 14400 s; equal in a task's privileged and standard versions (H.7) |
| Reset budget N (standard modes) | the `sim` service's `RCB_RESET_BUDGET` default (`/spec.budget.reset`), the instruction, `[metadata] reset_budget` | standard 0; standard-realtime 10 |
| Slowdown S (standard-realtime) | `RCB_SLOWDOWN` default, `[metadata] slowdown`, the instruction (`S = <S>`) | S = 1 when the service's real-time factor is ≥ 3, else ⌈1.5 / RTF⌉ |
| Observation and action extensions | `/spec`, the instruction, the benchmark doc | the `eai-standard` core |
| Grading kind | the instruction, the frozen instance, `reward.json` (`replays`, `graded_by_live`) | privileged: two fresh replays, or one by the task's choice; standard modes: the live episode (H.4) |
| Seeds | `[metadata.seeds]` `default`, `allowed` (list, `{from, to}`, `"any"`), `oracle`, `build` | the default seed only |
| Network | `[metadata] network` | `"allowlist"`; `"open"` by the author's choice (H.6) |
| Scene dynamics | `[metadata] dynamics` (`dynamic`: something other than the robot does work by a force other than the robot's and gravity; TAXONOMY.md "Dynamics") | none: declared by every task |
| Validated | `[metadata] validated`, else `oracle = "full"` | a recorded marker, not part of the configuration: validated and unvalidated tasks are ranked together |
| Stricter honour rules | `[metadata.honour] stricter` | none (never looser rules) |

## 3. Modes

The modes live in one registry, `MODE_REGISTRY` in `scripts/task_conventions.py`; a new mode is one entry there plus a
section here, by pull request (name, what the agent gets, what is graded, time and reset rules, which failures are
infrastructure, a reference implementation, one benchmark using it, CI support through the registry).

- **privileged** (`-privileged`): agent and simulator share a container; the agent may read
  privileged state, reset freely and plan; the deliverable is a trajectory (`/app/output/trajectory.npz`) or code
  (`task_type = "policy"`), graded offline in the verifier.
- **standard** (`-standard`; `eai-standard/2.1`, `2.2`, `2.4`): robot as a service. The simulator runs
  in a `sim` sidecar the agent cannot open; the agent sends actions and receives images and proprioception through the
  shipped client (`rcb_client.py`, `rcb1.py`); resets within the declared budget; no step caps, the wall clock is the
  only hard budget. Graded by the live episode the sidecar ran (H.4).
- **standard-realtime** (`-standard-realtime`; `eai-standard/2.3`): standard mode on a clock that does not stop: once
  an episode starts the robot runs at 1/S of real speed whatever the agent does, holds its last targets while the agent
  thinks, and is driven by a program in the agent's own container.
- A benchmark with its own runtime may export tasks that keep it (`metadata.protocol` = its own, listed in
  `ci_checks/benchmarks/<bench>/exported.toml`); they are plain Harbor tasks, Appendix H applies to them unchanged, and their results
  are reported apart.

## 4. Grading and results

| Recommended | Notes |
|---|---|
| `/logs/verifier/reward.txt` `1` or `0`; `reward.json` numbers only: `success`, `deterministic` (privileged trajectory tasks), `live_success` and `graded_by_live` (standard modes), `infra_error`, `sim_error`, `grader_error`, `progress`, the resource fields, cost fields (`n_actions`, `sim_steps`) | the same names wherever the concept applies |
| Every graded trial leaves a playable video (`replay.mp4` in `/logs/verifier/` or the sim sidecar's collected directory) and the replayable trajectory it was graded on (privileged: the deliverable; standard: the sidecar's journal or `trajectory.npz`). The one expected exception: a privileged trial whose agent submitted no trajectory, or none that replays (`missing_trajectory`, `bad_trajectory`, no actions). Standard modes: recorded by the sidecar during the live episode where that is cheap (or where the simulator does not replay bit for bit), else rendered from the trajectory in one pass after the verdict (`live.mp4` / `replay.mp4`). The verdict is written before the video is rendered and never depends on it; the video's time bound covers the longest episode the cutoff allows | `check-video.py`; the runner flags a graded trial without a video and renders it from the trajectory (running.md "Recordings") |
| Privileged: success judged on the end state of the replay; ≥ 2 replays with matching final-state hashes (`deterministic`), or one by the task's declared choice. A scene build does not depend on the host (sorted listings, no wall clock); an instance rebuilt with another state hash gives no verdict (`instance_mismatch`, an infrastructure failure). Standard modes: success judged by the sidecar on the live episode, with the task's own rule (a settle or hold window it declares is run on the live simulator); `reward.json` says `graded_by_live = 1`, `replays = 0` | within H.4; `check-live-verdict.py` |
| An infrastructure failure is `infra_error = 1`: not a result, neither a success nor the agent's 0 (H.5) | `scripts/write_task_results.py` |
| `nop` scores 0; with `oracle = "full"` the oracle scores 1 on every seed in `seeds.oracle` (`/validate`); a task without an oracle gets a human review (a positive example, the predicate, `nop` 0, determinism; recorded in the PR) | the `validated` marker (§2) |
| Results report success with cost (tokens, money, turns, wall clock, simulation steps) per mode and per comparable configuration; run id `<harness>-<model>-<effort>`; not committed to the repository | running.md |
| The core set: the tasks listed in [`core_set.toml`](../core_set.toml), one entry per task (`task`, the task dir name without its mode suffix) with its `default_mode`. The headline statistics are computed on the core tasks in their default mode; the same tasks may be run in another mode (`harbor run --core --privileged` / `--standard` / `--standard-realtime`), reported apart. Each result records `set` (`core` / `excluded`) as a marker, never part of the configuration. Listing a task changes none of its files | `task_conventions.py core-set --check` |

## 5. Instructions and information

| Recommended | Notes |
|---|---|
| The instruction names the deliverable under `/app/output/` and never mentions `/tests/` | `check-instruction.sh` |
| It states every convention the agent cannot infer: frames, quaternion order, units, action layout, client usage, the reset budget and S; world-frame quantities are decided per benchmark and consistent within it | benchmark hooks `ci_checks/benchmarks/<bench>/advisory-*` |
| It ends with three sections `normalize` renders: `## External material` (the honour rule: install packages and read what is installed, do not fetch a ready-made solution; the open-network paragraph for an open task), `## Resource limits`, `## Time limit` (the cutoff and what it means in the mode: running.md "The agent's time"); no second statement of the limit | `check-cutoffs.py`, `check-resources.py` |
| Everything a task needs at run time is in its image or directory; nothing tells the agent to download something | |
| A trial that fetched a solution is flagged and judged case by case by the owner; installing a general-purpose package never is | running.md |

## 6. Resources

Each task states the smallest allocation it runs on (`[metadata.resources]`: `min_cpus`, `min_memory_gb`,
`min_gpu_memory_gb`, `gpu_required`, `gpu_class`, the verifier's minimums, `measured`) and the most its agent phase may
use (`[metadata.resources.limits]`, shown in `## Resource limits`), with the docker caps every compose service applies
(`[metadata.resources.caps]`). Values come from measured peaks with a margin (`scripts/task_resources.toml`, written by
`normalize`). A monitor sidecar records usage; whether a limit is enforced is the runner's switch (`RCB_LIMITS_ENFORCE`,
off by default). Derivation, enforcement and the reward fields: running.md "Resources".

## 7. Versions

This text is **v2.0**. The wire protocol's versions:
`eai-standard/2.1` (the base: `/spec`, `/status`, `/observe`, `/submit`, RCB1 frames), 2.2 (depth, kinematics, per-call
bounds; shared layer `embodied_first_exam/standard/`), 2.3 (2.2 + realtime), 2.4 (2.3 + operation ids and deadlines; layer
`embodied_first_exam/standard/v2_4/`). Minor versions only add; `/spec.protocol` equals `metadata.protocol`. A protocol change is
an issue, then one pull request updating standard_mode.md, the reference implementation and an example task.

## Appendix H. Invariants (binding)

Each holds for every task in every mode, including tasks a benchmark exports with its own runtime. CI: the required
job `invariants` (`ci_checks/run_invariants.sh`) runs exactly the checks named here and fails on any failure, error or
incomplete run; `ci_checks/check-ci-selftest.py --tier invariants` breaks real tasks in each way and requires the
checks to fail. What CI cannot see (images, endpoints, the runner) is the reviewer's and the runner's to hold.

**H.1 Verifier isolation.** The verifier runs in a sandbox of its own (`[verifier] environment_mode = "separate"`, an
image built from `tests/`, `tests/Dockerfile` shipping `test.sh`) that receives only the declared artifacts (standard
modes: it transcribes the sidecar's verdict, H.4). `tests/test.sh` first empties `/logs/verifier`, and removes from `/app/output` whatever is not the agent's
own regular file or directory (links out of it, FIFOs, devices) before anything reads the agent's files; reward files
are written fresh. No writable volume crosses the trust boundary: a named volume mounted by a trusted container (the
verifier, a sidecar) is `*_trusted` and never mounted by the agent's container; the agent's container binds no task
file, host path or socket (only a directory the runner names as a whole `${RCB_*}` variable); no service widens its
container (`privileged`, `cap_add`, `devices`, host namespaces, `volumes_from`, OOM settings), takes files by another road
(`secrets`, `configs`, `env_file`, `build`, `include`) or sets its own network; sidecars publish no port. The resource
monitor, the one service exempt from these, has no network, runs its code from a pinned image and mounts its limits read-only, is the only writer of the
beacons (read-only everywhere else) and seals its record in the first sidecar collect hook. Code a verifier runs for
the agent (a `policy` deliverable) runs as an unprivileged user in its own process, without network, unable to read the
simulator, the evaluator or the requests, under a process limit; every process it started ends before anything is
graded, and it cannot write the logs or the report the grade is read from. A new benchmark merges only after one
adversarial trial (an agent told to obtain reward without solving the task) scored 0 on its tasks.
*CI:* `check-verifier-isolation.sh`, `check-monitor.py --tier invariants`, the benchmarks' `invariant-*` hooks (a skill sandbox's test); review.

**H.2 No answer in reach.** Reference solutions exist only under `solution/`, mounted for the oracle agent only.
Nothing the agent's container can read (the task's `environment/` files, the task and base images, the tooling, the
frozen instance, installed documentation) contains a solution of the task or a pointer to one: a URL, a dataset or
file name, a demonstration or episode id, the name of the upstream expert or policy for this task. Upstream experts,
recorded demonstrations and policies trained for the task are scrubbed from images; provenance lives in
the README and `docs/benchmarks/<bench>.md`. *CI:* `check-agent-pointers.py`, each benchmark's `ci_checks/benchmarks/<bench>/invariant-*`
hooks; images are reviewed when built ([leakage.md](leakage.md)).

**H.3 Standard trust boundary** (standard and standard-realtime). The simulator, the scene, the frozen instance, the
seed and the success predicate run in the `sim` sidecar; the agent's image holds no simulator or simulation code
(`environment/Dockerfile` copies nothing from `sim/`, no `.` or wildcard). The agent reaches the service only through
the protocol's endpoints; every other path is 404 (no `/state`, no `/success`). The service exposes no object poses,
scene files, seed, success predicate or its parameters beyond what the instruction states, segmentation or object
contact forces, except telemetry the benchmark's doc declares field by field, which never gives an object's pose. The
agent's controller runs in the agent's own container; no agent code runs next to the simulator. *CI:*
`check-standard-agent-image.sh`, `check-verifier-isolation.sh` (topology, ports); the service's `/spec` checks; review.

**H.4 Trusted verdict.** The verdict comes only from a trusted source. Privileged: a replay, in a fresh process, of
the agent's deliverable from the frozen initial state, in the verifier. Standard and standard-realtime: the sim
sidecar's record of the live episode (`final.json`, its `success`), judged by the service on the episode it ran, from a
frozen initial state it checked when the episode began (and after every reset), and the verifier transcribes the
record; no replay decides it, and nothing the verifier renders afterwards (a video) does. What keeps that record
trusted: the agent cannot write the sidecar's state (its volumes are `*_trusted`, it publishes no port); the evidence is
collected only from the sidecar; when the agent's time is up the collect hooks stop every process the agent left
running (`kill -9 -1` in its container; only the resource monitor's seal comes first) before the sidecar is signalled,
and from that signal on the service refuses every request that would run the simulator (a settle or hold window
included), so the sidecar finalizes an episode the agent can no longer change; the
sidecar keeps the episode's journal or trajectory as the deliverable. Nothing the agent's container writes
decides, except the privileged deliverable that is replayed; the verifier uses no network; a verdict once written in
a trial is never rewritten (a later re-grade keeps the original beside it). The frozen instance the verifier or the
sidecar grades against and the one the trial ran from are byte-identical copies.
*CI:* `check-verifier-isolation.sh` (evidence and collect hook from a sidecar), `check-instance-copies.sh`.

**H.5 Infrastructure retry.** Infrastructure failures allow at most one full retry with the same instance, seed, and
configuration, clearing all agent and environment state. If that retry also fails, follow the default failure-handling
behavior; no further retries. Normal task failures do not qualify. (At most two runs of a task under one run id; the
voided attempt is moved aside and never counted. The rule is the runner's: `scripts/retry_policy.py`, running.md.)
*CI:* `scripts/tests/test_retry_policy.py`, `scripts/tests/test_runner_results.py`.

**H.6 Egress.** During the agent phase the agent's container, and every service in its network namespace, reaches only
the allowlist `scripts/set_agent_egress.py` `HOSTS` (the model APIs and the package registries; `[agent] network_mode =
"allowlist"` with exactly those hosts, no step with a policy of its own; an official run narrows it further to the usage
gateway and the registries), unless the task's author declares open egress, `[metadata] network = "open"` (then
`[agent]` sets no other policy). The runner applies what the task declares; open-network results are ranked apart.
The verifier has no network (`[verifier] network_mode = "no-network"` in every task, written by `normalize`; no service
of `tests/docker-compose.yaml` with a network setting other than `none`). *CI:* `check-verifier-isolation.sh`.

**H.7 Comparable twins.** Where a task ships both a privileged and a standard (or standard-realtime) version, they
share one frozen instance (byte-identical copies), one success rule and the same seeds (`default`, `allowed`,
`build`), and the privileged and standard versions have the same cutoff (`same_cutoff_as` in the mode registry).
*CI:* `check-twins.py`, `check-instance-copies.sh`.

**H.8 DIGEST.** `tasks/<benchmark>/<task>/DIGEST` is the digest Harbor publishes the task under (`sha256:<hex>` over the relative
path and content hash of `task.toml`, `instruction.md`, `README.md` and every file under `environment/`, `tests/`,
`solution/`), written last by `normalize` and equal to the digest of the task's current files. Results are attributed
to a task by its digest; a changed file is a changed task. *CI:* `check-dataset-manifest.sh`.

## v1 section numbers (cited by older tasks and code)

| v1 | Now |
|---|---|
| §0, D1–D12 | §2 (settings), §3 (modes), §7; D3/D4 §4; D5 §1; D8 §2, H.7; D10/D11 running.md |
| §1 checklist, §2.1–2.5 | §1, §5 |
| §2.6 verifier | H.1 (isolation), §4 (fields) |
| §2.7 solutions, oracle, nop | H.2, §4 |
| §2.8 identity | H.8, §1 |
| §2.9, §2.10 resources and limits | §6, running.md "Resources" |
| §2.11 external material, network | §5, H.6, running.md "Network" |
| §2.12 cutoff | §2, §5, running.md "The agent's time" |
| §2.13 seeds | §2, running.md "Seeds" |
| §2.14 dynamics, §2.15 modes shipped, §2.16 adding a mode | §2 (TAXONOMY.md "Dynamics"), §3, H.7 |
| §3 privileged; §4, §4.1–4.9 standard; §4b realtime; §4c exported | §3, H.3, H.4, §4; wire details standard_mode.md |
| §4.7 crash recovery | H.5 (retry); in-trial resume is an implementation detail of the shared layers (standard_mode.md) |
| §5 results, token budget; §6 versioning; §7 migration | §4, running.md; §7; the migration is complete (no rule) |
