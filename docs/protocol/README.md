# Embodied First Exam — Task Protocol v2.4

This is the task protocol of Embodied First Exam (EFE; [repository](https://github.com/mll-lab-nu/embodied-first-exam),
[site](https://www.embodied-first-exam.ai), [how to contribute](https://www.embodied-first-exam.ai/contribute/)). It is
the four documents in this folder: this README (the conventions a task follows, and the binding
invariants of Appendix H), [`standard_mode.md`](standard_mode.md) (the `eai-standard/2.x` wire format of the standard
modes), [`running.md`](running.md) (official-run configuration, seeds, retries, gateway, resource enforcement, results;
enforced by the runner and scheduler) and [`leakage.md`](leakage.md) (where answer keys survive and how they are
removed). Metadata values, names and run ids are in [`TAXONOMY.md`](../TAXONOMY.md); each benchmark's own choices in
`tasks/<benchmark>/README.md`.

**Recommended conventions, and eight invariants that bind.** Sections 1–7 describe how a task is usually built, so that
tasks from different benchmarks can be run, compared and reviewed the same way. They recommend; a task or a benchmark
may choose otherwise and says so where its readers look (its `task.toml`, its README, `tasks/<benchmark>/README.md`).
CI reports a departure from them as an advisory warning, never as a failure. **Appendix H is not a recommendation.** Its
eight invariants keep results honest (no reward without solving the task, one verdict for one deliverable, results
compared only with comparable results). They hold for every task and every run, no task value, declaration or
benchmark document can override them, and the required CI job `invariants` fails a pull request that breaks one, as
the runner refuses a run that would. The only setting Appendix H leaves to the task's author is the agent's network:
the allowlist unless the task declares open egress (H.6).

## 1. What a task is

A task is a self-contained Harbor task directory under `tasks/<benchmark>/` (one folder per benchmark); the benchmark adds as little as possible on top of
Harbor's format. Anything not described here (the simulator, how a scene is defined, the privileged tool API, how a
verifier decides internally) is the task's own business.

| Recommended | Notes |
|---|---|
| `task.toml`, `instruction.md`, `README.md`, `environment/Dockerfile`, `tests/test.sh` (executable), `tests/Dockerfile`; `solution/solve.sh` when `oracle` is `full` or `partial` | `ci_checks/check-task-structure.sh` |
| `[task].name = "embodied-first-exam/<folder>"`; `[metadata]` `task_type` (`trajectory` / `policy`), `simulator`, `robot` ([`TAXONOMY.md`](../TAXONOMY.md)), `family`, `instance_seed`, `expert_time_estimate_hours`, `oracle` (+ `oracle_evidence`), `protocol` (sidecar modes), the settings of §2 | `check-task-fields.sh`, `check-protocol.py` |
| The directory name `<base>-<mode>`, `<base>` = `<benchmark>-<family>-i<NN>` or the upstream name; no versions or durations in names | the mode is the whole suffix |
| All task code in the directory, or in a pinned image its Dockerfiles take it from (the benchmark's base image; a files-only image built from `embodied_first_exam/benchmarks/<benchmark>/`, `COPY --from=<image@digest>`); base images hold the simulator and its assets; nothing imports repository code at run time | a task's identity is its directory (H.8) |
| Every task is in the normal form `scripts/task_conventions.py` `normalize` writes (README layout, rendered sections, `DIGEST`) | `task_conventions.py --check` |
| Base images `ghcr.io/mll-lab-nu/efe:<name>-<images/<name>/VERSION>` (one public package, a tag per image), or `efe-private:<name>-<VERSION>` when `images/<name>/BUILD_ONLY` (one private package); every `FROM` / `image:` pinned to a tag or digest | `check-dockerfile.sh` |
| README in the standard layout (`# <dir>`, key table, Task, Difficulty, Reference solution, Verification, Resources, Details); no `results/` | rendered by `normalize` |
| A change to a published task, its scene included, is made in place: same name, a new DIGEST; the pull request says what changed and why (the README describes the current task, no history) | H.8 |

**What a contribution delivers.** Tasks only: task directories under `tasks/<benchmark>/`. No task-generation code
goes into the repository (generators, oracle searches, instance freezers, release builders stay with their authors), and
`scripts/` holds only what running the benchmark needs. Code several tasks of a benchmark share goes, preferably, into the
benchmark's image (`images/<name>/`), so the tasks get it from the image; else into
`embodied_first_exam/benchmarks/<benchmark>/` (the same folder name as `tasks/<benchmark>/`), from which a files-only
image is built (`scripts/files_image.py`, `images/<name>/FILES.json`) that the tasks' Dockerfiles copy from. A benchmark's
own choices are documented in `tasks/<benchmark>/README.md`.

## 2. Task-declared settings

Each task chooses these and declares them; CI checks that the declarations agree with
each other, not that they take a particular value. The defaults are what templates write when a task says nothing.
Every trial records its **effective configuration** (protocol version, mode, cutoff, reset budget, S, seed, network,
validated; `scripts/task_conventions.py` `effective_config`), and results are ranked only among trials with the same
configuration (`config_key`; running.md "Results").

| Setting | Declared in | Default |
|---|---|---|
| Modes offered (§3): any subset; a task without its privileged twin says why in its README Twin row | the task directories it ships | — |
| Cutoff: the agent's wall-clock time, decided by the task's author | `[agent] timeout_sec` (a whole number of seconds) | 3600 s; at most 14400 s; equal in a task's privileged and standard versions (H.7) |
| Reset budget N (standard modes) | the `sim` service's `RCB_RESET_BUDGET` default (`/spec.budget.reset`), the instruction | 0 in both standard and realtime (a task that grants resets declares its own N) |
| Agent-ended episode and its step limit (standard mode, optional, §3) | the `sim` service's `RCB_AGENT_END` and `RCB_STEP_LIMIT` (`/spec.success_signal`, `/spec.budget.steps`), the instruction's `## Episode end` (rendered by `normalize`) | off: the service ends the episode, no step limit |
| Slowdown S (realtime) | the `sim` service's `RCB_SLOWDOWN` default (`/spec.timing.slowdown`), the instruction (`S = <S>`) | S = 1 when the service's real-time factor is ≥ 3, else ⌈1.5 / RTF⌉ |
| Observation and action extensions | `/spec`, the instruction, the benchmark doc | the `eai-standard` core |
| Grading kind | the instruction, the frozen instance, `reward.json` (`replays`, `graded_by_live`) | privileged: one fresh replay, or up to `[metadata] replays` where the simulator does not replay bit-wise, any success counting (§4); standard modes: the live episode (H.4) |
| Seeds | `[metadata] instance_seed` (the default seed); `[metadata.seeds]` `allowed` (list, `{from, to}`, `"any"`), `oracle`, `build`, only where they differ from the defaults | the default seed only (`allowed` = `oracle` = [the default seed], `oracle` = [] without a reference solution; `build = "frozen"`) |
| Network | `[agent] network_mode` | `"allowlist"`; `"public"` (open) by the author's choice (H.6) |
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
  only hard budget (unless the task's episodes are agent-ended with a step limit, below). Graded by the live episode the
  sidecar ran (H.4).
- **realtime** (`-realtime`; `eai-standard/2.3`): standard mode on a clock that does not stop: once
  an episode starts the robot runs at 1/S of real speed whatever the agent does, holds its last targets while the agent
  thinks, and is driven by a program in the agent's own container. Resets as in standard: within the declared budget,
  0 unless the task grants its own (§2).
- **Agent-ended episodes** (optional; standard mode, `eai-standard/2.2` services; any task may opt in, standard_mode.md
  "Optional agent-ended episodes"). The service never tells the agent whether it has succeeded and a success does not
  end the episode; the agent ends it with `POST /finish`. A task may add a step limit, a number of its own control steps
  stated in its instruction. The episode ends at whichever comes first: `/finish`, the step limit, the agent's time
  limit (its cutoff, §2), its token budget (the run's, running.md "Official runs"), the agent's own exit, or the task's
  failure rule or a simulator error as without the feature. The verdict is the task's success rule on the state at that
  end, with the task's settle or hold window run from there; a success reached and undone is 0, a success the task
  latches as an event stays. The instruction states the three limits with their values (`## Episode end`, rendered by
  `normalize` from the task's step limit and the run's token budget; the time limit is `## Time limit`). `final.json`
  records `ended_by` (`finish`, `step_limit`, `session_end`: the time limit, the token budget or the agent's exit, which
  the runner's record tells apart; `failed`, `error`) and the counters (`steps_used`, `finish_time_s`).
- A benchmark with its own runtime may export tasks that keep it (`metadata.protocol` = its own, listed in
  `ci_checks/benchmarks/<bench>/exported.toml`); they are plain Harbor tasks, Appendix H applies to them unchanged, and their results
  are reported apart.

**Images per call (standard modes).** Every call that returns images has a per-call image budget,
`max_frames_per_call`, stated in the task (its `/spec` and its instruction). Tasks that bring their own runtime instead of
an eai-standard service (EO Match, RoboEngineer) are outside this rule. Each camera frame is one image, and a depth
frame one more: a service keeps depth as it is sent (uint16 millimetres or float16 metres), so it costs no more than an
RGB frame. The count is of the frames the service really captures, at the capture stride it uses (one frame every
`round(control rate / video_fps)` control steps, plus the call's first and last), not at the requested rate. It is
checked before the call runs: a call over the budget is refused with an error that says so and runs nothing. A call
whose length is known only while it runs (`ee_pose` rows, a chunk the service plans) stops
filming at the budget instead: the motion goes on, its last frame is always taken, and `meta["frames_skipped"]` counts the frames left out of the response (the trial's video still has them). `video` = `mp4` or `frames` changes what is
sent, not the budget. Building a response holds the captured frames plus one response body (the frames are written
once into it, a part the response drops is let go of first, and per-frame depth is compressed only while it
still fits), and the service's memory cap covers the largest
response the budget allows (§6). In realtime mode the pending watches and the answers not yet sent count
against one budget together: a watch that would exceed it, or that would make more than 8 watches and unsent answers
outstanding, is refused (429, nothing ran); a submit or an observation of the present (no watch) is never refused for its
images: past the budget its answer comes without its frames and `meta["frames_skipped"]` is set.

## 4. Grading and results

| Recommended | Notes |
|---|---|
| `/logs/verifier/reward.txt` `1` or `0`; `reward.json` numbers only: `success`, `replays`, `replays_succeeded` and `deterministic` (privileged trajectory tasks; with one replay nothing is compared and `deterministic` is 1), `live_success`, `graded_by_live` and `first_success` (standard modes: the trial's first episode ended in success, the no-reset performance; without a reset it is `success`; where the service keeps no first episode it is derived from `resets`, running.md "Results"), `infra_error`, `sim_error`, `grader_error`, `progress`, the resource fields, cost fields (`n_actions`, `sim_steps`) | the same names wherever the concept applies |
| Every graded trial leaves a playable video (`replay.mp4` in `/logs/verifier/` or the sim sidecar's collected directory) and the replayable trajectory it was graded on (privileged: the deliverable; standard: the sidecar's journal or `trajectory.npz`). The one expected exception: a privileged trial whose agent submitted no trajectory, or none that replays (`missing_trajectory`, `bad_trajectory`, no actions). By default a video is a post-hoc replay (rendered afterwards from the trajectory, `replay.mp4`). Where the simulator is not verified bit-wise replayable (the replay must reach the live final-state hash), the video must be a live recording instead (captured by the sim sidecar during the episode, `live.mp4`). Privileged videos are always post-hoc replays. Each benchmark declares which one its standard modes use, and every video, a published one included, is labelled with its source (`video_source`). The verdict is written before the video is rendered and never depends on it; the video's time bound covers the longest episode the cutoff allows. With resets, a service that keeps the first episode (the shared 2.1 sidecar service, standard_mode.md "Evidence and grading") also leaves its trajectory and video beside the graded ones (`trajectory.first.npz`, `replay.first.mp4`): evidence only | `check-video.py`; the runner flags a graded trial without a video and renders it from the trajectory (running.md "Recordings") |
| Privileged: success judged on the end state of one fresh replay of the deliverable (the default). A task whose simulator does not replay bit-wise declares a replay count N (`[metadata] replays`): its grader replays the deliverable up to N times, each in a fresh process, stopping at the first success, and the attempt succeeds if any replay succeeds (`replays`, `replays_succeeded`; `deterministic` is evidence only). Bit-wise determinism is checked when a task is built, not in every graded trial: its author makes sure that fresh replays of a positive example end on the same final-state hash on the hardware used for evaluation (the evidence goes in the pull request: CONTRIBUTING.md, REVIEWING.md). A scene build does not depend on the host (sorted listings, no wall clock); an instance rebuilt with another state hash gives no verdict (`instance_mismatch`, an infrastructure failure). Standard modes: success judged by the sidecar on the live episode, with the task's own rule (a settle or hold window it declares is run on the live simulator); `reward.json` says `graded_by_live = 1`, `replays = 0` | within H.4; `check-live-verdict.py` |
| An infrastructure failure is `infra_error = 1`: not a result, neither a success nor the agent's 0 (H.5) | `scripts/write_task_results.py` |
| A simulator error is a failure: an episode that ended in `error`, or in which the simulator raised an error on the agent's actions, scores 0 (`success = 0`, `sim_error = 1`) whatever it had reached before, and is the agent's result, not an infrastructure failure (unless the service records `infra_error = 1`: the agent had not acted yet) | `check-live-verdict.py` |
| `nop` scores 0; with `oracle = "full"` the oracle scores 1 on every seed in `seeds.oracle` (`/validate`); a task without an oracle gets a human review (a positive example, the predicate, `nop` 0, determinism; recorded in the PR) | the `validated` marker (§2) |
| Results report success with cost (tokens, money, turns, wall clock, simulation steps) per mode and per comparable configuration, and in the standard modes the first-attempt success (`first_success`, the no-reset performance) beside the graded result; run id `<harness>-<model>-<effort>`; not committed to the repository | running.md |
| The core set: the tasks listed in [`core_set.toml`](../core_set.toml), one entry per task (`task`, the task dir name without its mode suffix) with its `default_mode`. The headline statistics are computed on the core tasks in their default mode; the same tasks may be run in another mode (`--privileged` / `--standard` / `--realtime`), reported apart. Two sets run: `core` (`harbor run -d embodied-first-exam`) and `all`, every task dir (`harbor run -d embodied-first-exam@all`; `-p tasks/<benchmark>` narrows either to one benchmark). Each result records `set` (`core` / `excluded`) as a marker, never part of the configuration. Listing a task changes none of its files | `task_conventions.py core-set --check` |

## 5. Instructions and information

| Recommended | Notes |
|---|---|
| The instruction names the deliverable under `/app/output/` and never mentions `/tests/` | `check-instruction.sh` |
| It states every convention the agent cannot infer: frames, quaternion order, units, action layout, client usage, the reset budget and S; world-frame quantities are decided per benchmark and consistent within it | benchmark hooks `ci_checks/benchmarks/<bench>/advisory-*` |
| The success condition is written in terms the agent can observe in that mode: each object is named by its appearance and/or its starting place; an object's axis or point is described physically ("the keyboard's short edge", "the key's teeth end"), saying whether the condition already holds at the start; upstream identifiers (labels, function names, indices, asset metadata) may follow, only in brackets; thresholds stay exact and equal to the grader's. No benchmark is exempt | `check-instruction.sh` (standard modes: code-like terms with no physical description next to them) |
| It ends with three sections `normalize` renders: `## External material` (the honour rule: install packages and read what is installed, do not fetch a ready-made solution; the open-network paragraph for an open task), `## Resources` (the caps of the agent's own container, §6), `## Time limit` (the cutoff and what it means in the mode: running.md "The agent's time"); no second statement of the limit | `check-cutoffs.py`, `check-resources.py` |
| Everything a task needs at run time is in its image or directory; nothing tells the agent to download something | |
| A trial that fetched a solution is flagged and judged case by case by the maintainers; installing a general-purpose package never is | running.md |

## 6. Resources

Every resource number of a task is an upper bound (a cap) for **one container**; there are no minimums and no soft
limits. Each cap is written where Harbor or docker reads it:

| Container | Where | Keys |
|---|---|---|
| `main` (the agent's) | `task.toml` `[environment]` | `cpus` (a whole number), `memory_mb`, `storage_mb` (disk); `gpu_types` (RTX-class models) only for a task that needs ray-tracing cores; never `gpus` (Harbor's local docker refuses it) |
| `main`'s processes, and every other service | `environment/docker-compose.yaml` | `pids_limit` (main; it counts processes and threads); `cpus`, `mem_limit`, `pids_limit` (every other service); never `deploy.resources.limits` (docker refuses it beside `cpus` / `mem_limit`) |
| a service that holds a GPU | its compose service | the device reservation (`deploy.resources.reservations.devices`, `driver: nvidia`, `capabilities: [gpu]`, written by hand; a device whose capabilities name `gpu` counts as a GPU with or without the driver line; never `gpus:` or `runtime: nvidia`) and `x-gpu-memory-gb`, its GPU-memory cap in GiB, the one field of our own |
| the separate verifier | `task.toml` `[verifier.environment]`; `tests/docker-compose.yaml` | `cpus`, `memory_mb` (and `storage_mb`), set by hand. Harbor uses this table alone when it exists: a key it lacks is **no cap**. Without the table the verifier gets a copy of `[environment]` (`storage_mb` included). Its processes: `pids_limit` of `main` in `tests/docker-compose.yaml`, set by hand. A GPU service there gets `x-gpu-memory-gb` = main's value when main holds a GPU; otherwise the task writes that line itself (normalize keeps it) |

Other compose keys the task writes itself are settings, not caps from the rules: `shm_size` (the size of `/dev/shm`; docker
applies it, and what is stored there also counts against the container's memory cap), devices, volumes.

The values come from the rules in `scripts/task_resources.toml`; `python3 scripts/task_conventions.py <task dirs>`
(`normalize`, which creates `[environment]` when the task has none) writes them, and `ci_checks/check-resources.py`
checks that the declared caps are the applied ones: a cap the compose file sets itself (normalize keeps it) must equal
the rule's. A task no rule matches keeps the caps its own `[environment]` and compose file set; CI accepts them as long
as every container has its caps. A rule is a `[[cap]]` table:

- `match`: a regular expression searched in the task directory's name; the **last** rule that matches a task applies,
  whole (rules are never merged).
- one inline table per compose service, keyed by its name; the services must be exactly the task's compose services
  (`rcb_monitor` aside). `main` = { `cpus` (whole), `memory_gb`, `pids`, `disk_gb` }; every other service = { `cpus`,
  `memory_gb`, `pids` }; `gpu_memory_gb` on, and only on, a service that reserves a GPU. Memory, disk and GPU memory are
  in GiB; memory and disk a whole number of MiB (a multiple of 1/1024 GiB), since they are written in MiB.
- optional: `gpu_types` (written to `[environment]`) and `recommended_gpu`, each shown in the task README's
  `## Resources` (`gpu_types` as its `GPU:` line); `measured` (what the benchmark was measured to use) and
  `caps_measured` (the measured peaks the caps come from), kept in the rules file only.

How a rule's caps are chosen from measurements (the provenance in `caps_measured`). From the peaks seen: memory the
larger of 1.5 × the peak and the peak plus a margin (+2 GiB for main, +3 GiB for another service); GPU memory the larger
of 1.5 × the peak and the peak + 2 GiB, at least 16 GiB for Isaac Sim; CPU at least every reading, on hosts that applied
the cap and on hosts that did not, and a simulator that runs in real time keeps the CPU its slowdown was measured with;
processes and threads a power of two at least 2 × the peak thread count (4 × for Isaac Sim, whose thread count follows
the host's cores), at least 1024; disk at least 10 GiB. The peaks never raise a cap above the rule's earlier cap, for
any resource: such a cap stays where it was. A cap with no per-container measurement is kept at the earlier cap. From
the largest call the task allows: a simulator service that builds a response of frames in memory gets at least its
resident size + 1.2 × what building the largest legal response holds, in whole GiB, and 2 GiB more where that leaves no
margin over thin data. A cap may be set above what the peaks give only by (a) this largest-call rule, (b) kernel OOM
kills recorded at the earlier cap, or (c) an owner's decision, which may also set a cap below. `caps_measured` names
which one applies.

**Who enforces a cap.** The container's runtime first: Docker and Harbor apply what the host lets them (the table).
The resource monitor (the `rcb_monitor` sidecar) reads each container's own cgroup limits (`cpu.max`, `memory.max`,
`pids.max`, or their cgroup v1 equivalents) at every sample (every 5 s; disk once a minute). A cap the runtime holds at
the cap or below is the runtime's, and the monitor only records it. A cap whose limit is missing or higher than the cap
(disk and GPU memory always) is enforced by the monitor when the run-time switch `RCB_LIMITS_ENFORCE` is `1` (the
backstop), and only recorded when it is `0` (the default). The monitor acts on main and, in privileged mode, on the
services the agent drives, the way Docker would. Who enforced each cap of each container is in the record
(`enforced_by`, running.md "Resources"). A measurement is over a cap above cap × (1 + `RCB_LIMITS_TOLERANCE`, default
0.05: sampling noise). A count of processes and threads is over above the cap itself, in two samples in a row (one alone
can be a burst between samples). The benchmark's own services (a standard mode's simulator sidecar, RoboPaint's `scorer`)
are recorded only, in both settings.

The monitor never kills PID 1 of a container or what started with it. It kills a process only when that process still
has the start time it was measured with and is still in the trial's container (through a pidfd where the kernel has
them; elsewhere the check is made again right before each signal). What it cannot observe it records and never acts
on: a process whose GPU memory NVML does not report, NVML's process IDs when the monitor is not in the host's PID
namespace, or open files it cannot read. Neither setting changes the grade. A killed process ends like any process that dies, the trial may
fail for it, and the grader judges what the agent left. Going over a cap is recorded (`limits_violation_observed`,
running.md "Resources").

| Resource | Docker / Harbor on a cgroup v2 Docker host | Hosts where they do not | Monitor backstop (a cap the runtime does not hold, `RCB_LIMITS_ENFORCE=1`) |
|---|---|---|---|
| CPU (`cpus`) | a throttle (CFS quota) | rootless podman without a delegated cgroup: none | writes the cap as the container's own CPU quota where its cgroup can be written, and puts the old value back after. Else it duty-cycles the container's processes with `SIGSTOP` / `SIGCONT` (100 ms periods) while their demand is above the cap. It resumes only the processes it stopped: a process found stopped that it did not stop last is never signalled again. Never a kill |
| Memory (`memory_gb`) | the kernel's OOM killer, at the container's own cap | rootless podman without a delegated cgroup: none | kills the process with the largest PSS, one per sample, and only when the processes it may kill hold enough to cover the excess (none holding under 10 MiB). The next sample measures again |
| Processes and threads (`pids`) | a fork or a new thread fails at the cap | rootless podman without a delegated cgroup: none | kills the newest processes until the count is back at the cap, and only when the processes it may kill hold enough of the count to get there (not when the excess is PID 1's or unreaped zombies) |
| Disk (`disk_gb`, `storage_mb`) | a cloud backend may apply `storage_mb` | local Docker (overlay2 on ext4): none | at a disk measurement over the cap, kills the process that holds the most bytes open for writing in files under the measured paths, when those bytes cover the excess and are at least 10 MiB. No second kill until the disk has grown since the last one or has been under the cap again. Otherwise it records only |
| GPU memory (`x-gpu-memory-gb`) | none | every card without MIG: none (a card may be shared between trials) | kills the process holding the most GPU memory in that container, one per sample, when the processes it may kill can cover the excess |

The `SIGSTOP` fallback is visible to the agent. An interactive shell with job control reports a throttled child as a
stopped job (`Stopped`) and may stop waiting for it, so commands run under such a shell can end early or need `fg`.
The fallback is used only where the container's runtime does not hold its CPU and its cgroup cannot take a quota
(rootless runtimes; `cgroup: host` is read-only on most hosts). A stop the agent sends to a process while the monitor
holds it stopped cannot be told from the monitor's own, and is undone with it. A restarted monitor resumes every stopped
process of a throttled container that is not known to have been stopped by the agent. A container is its own cgroup when it has one: a process
of it in another mount namespace still counts in it. The fallback looks for new processes twice per period, so a short
process can run free for up to one period before it is stopped. The share never drops below the cap divided by the
container's CPUs, or 0.5 %, so no throttled process is held for more than 0.4 s. When the short processes alone use more
than the cap, the monitor holds what it can and records `throttle_insufficient`. Without a cgroup of its own (Quest
apptainer, rootless podman without delegation), the monitor counts a container's CPU from its processes, including the
children they have reaped. A process that ends between two samples counts only through its parent, so CPU use may be
under-recorded when the parent is outside the container or never waits.

On cgroup v1, Docker applies CPU, memory and processes through the v1 controllers; the monitor then measures memory
by PSS and reads no kernel OOM counters. It reads the runtime's limits from the container's directories (and their
parents that carry the container's id) where the v1 hierarchy is visible to it; where it is not, every cap is recorded as
the monitor's (`enforced_by`), and the kernel still applies the runtime's limits first. A runtime that refuses `pid: host` runs the monitor as a beacon (the clock in
`usage.json`, nothing measured or enforced; running.md "Without Docker"). The `x-gpu-memory-gb` of a recorded service and
of the verifier is a cap stated for the reader: nothing measures it. The agent reads its own container's caps in
`## Resources` (§5) and in `/run/rcb-limits/usage.json`. Placing trials, the switches, the record and the reward
fields: running.md "Resources".

## 7. Versions

This text is **v2.4** (2.4 made one fresh replay the default privileged grading, or up to N with any success where the simulator does not
replay bit-wise, bit-wise determinism being checked when the task is built rather than in every trial, §4; 2.3 renamed the third mode `standard-realtime` to `realtime`, its task directories
`<base>-realtime`, with no other change to the mode, and made its default reset budget 0 as in standard mode; 2.2 added
the optional agent-ended episodes of §3); like the wire protocol's, its minor versions otherwise
only add (a recommended field, an optional feature, evidence). A
result's `config.json` records `protocol_version`: `PROTOCOL_VERSION` in `scripts/task_conventions.py` of the checkout
that writes the result (`"legacy"` for a trial of another version of the task), one of the keys results are compared
by (`CONFIG_KEYS`, running.md "Results"). The wire protocol's versions:
`eai-standard/2.1` (the base: `/spec`, `/status`, `/observe`, `/submit`, RCB1 frames), 2.2 (depth, kinematics, per-call
bounds; shared layer `embodied_first_exam/standard/`), 2.3 (2.2 + realtime), 2.4 (2.3 + operation ids and deadlines; layer
`embodied_first_exam/standard/v2_4/`). Minor versions only add; `/spec.protocol` equals `metadata.protocol`. A protocol change is
an issue, then one pull request updating standard_mode.md, the reference implementation and an example task.
In this version a task declares its open egress only as `[agent] network_mode = "public"`, its reset budget and S only
in its `sim` service, and its default seed as `[metadata] instance_seed`; CI fails a task.toml with `[metadata] network`
(H.6), and a realtime task's with `[metadata]` `reset_budget` or `slowdown`, and warns on these and `mode`
elsewhere; `normalize` rewrites such a task into this form.

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
monitor, the one service exempt from these, has no network, runs its code from a pinned image and mounts its caps (`limits.json`) read-only, is the only writer of the
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
the README and `tasks/<benchmark>/README.md`. *CI:* `check-agent-pointers.py`, each benchmark's `ci_checks/benchmarks/<bench>/invariant-*`
hooks; images are reviewed when built ([leakage.md](leakage.md)).

**H.3 Standard trust boundary** (standard and realtime). The simulator, the scene, the frozen instance, the
seed and the success predicate run in the `sim` sidecar; the agent's image holds no simulator or simulation code
(`environment/Dockerfile` copies nothing from `sim/`, no `.` or wildcard). The agent reaches the service only through
the protocol's endpoints; every other path is 404 (no `/state`, no `/success`). The service exposes no object poses,
scene files, seed, success predicate or its parameters beyond what the instruction states, segmentation or object
contact forces, except telemetry the benchmark's doc declares field by field, which never gives an object's pose. The
agent's controller runs in the agent's own container; no agent code runs next to the simulator. *CI:*
`check-standard-agent-image.sh`, `check-verifier-isolation.sh` (topology, ports); the service's `/spec` checks; review.

**H.4 Trusted verdict.** The verdict comes only from a trusted source. Privileged: a replay, in a fresh process, of
the agent's deliverable from the frozen initial state, in the verifier. Standard and realtime: the sim
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

**H.5 Infrastructure rerun.** An attempt that failed for infrastructure reasons, with positive evidence of it (a model
API or account error, a usage limit, a host or launch that died, the verifier's `infra_error` / `grader_error`), is
void: it is moved aside, never counted, and the task may be rerun with the same instance, seed, and configuration,
clearing all agent and environment state, until an attempt gives a result. A graded failure (the agent's 0, its cutoff,
its token budget, its own end) is a result and is never rerun; nor is a success. (The rule is the runner's:
`scripts/retry_policy.py`, running.md.)
*CI:* `scripts/tests/test_retry_policy.py`, `scripts/tests/test_runner_results.py`.

**H.6 Egress.** During the agent phase the agent's container, and every service in its network namespace, reaches only
the allowlist `scripts/set_agent_egress.py` `HOSTS` (the model APIs and the package registries; `[agent] network_mode =
"allowlist"` with exactly those hosts, no step with a policy of its own; an official run narrows it further to the usage
gateway and the registries), unless the task's author declares open egress, `[agent] network_mode = "public"` (with no
host list). The runner applies what the task declares; open-network results are ranked apart.
The verifier has no network (`[verifier] network_mode = "no-network"` in every task, written by `normalize`; no service
of `tests/docker-compose.yaml` with a network setting other than `none`). *CI:* `check-verifier-isolation.sh`.

**H.7 Comparable twins.** Where a task ships both a privileged and a standard (or realtime) version, they
share one frozen instance (byte-identical copies), one success rule and the same seeds (`instance_seed`, and
`[metadata.seeds]` `allowed` and `build`), and the privileged and standard versions have the same cutoff (`same_cutoff_as` in the mode registry).
*CI:* `check-twins.py`, `check-instance-copies.sh`.
One success rule is not one length rule: where a privileged deliverable has an action or time limit its standard twin
does not, the suite's `tasks/<benchmark>/README.md` states both, and cross-mode comparisons of those twins are read
with that in mind.

**H.8 DIGEST.** `tasks/<benchmark>/<task>/DIGEST` is the digest Harbor publishes the task under (`sha256:<hex>` over the relative
path and content hash of `task.toml`, `instruction.md`, `README.md` and every file under `environment/`, `tests/`,
`solution/`), written last by `normalize` and equal to the digest of the task's current files. Results are attributed
to a task by its digest; a changed file is a changed task. *CI:* `check-dataset-manifest.sh`.
