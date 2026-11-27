# Resources

Every resource number of a task is an upper bound, a cap, for **one container**. There are no minimums and no soft
limits. Memory, disk and GPU memory are in GiB in the rules. They are written in MiB where Harbor reads them, so each
is a whole number of MiB.

## Where each cap is written

| Container | Where | Keys |
|---|---|---|
| `main` (the agent's) | `task.toml` `[environment]` | `cpus` (a whole number), `memory_mb`, `storage_mb` (disk); `gpu_types` (RTX-class models) only for a task that needs ray-tracing cores. Never `gpus`: Harbor's local docker refuses it. |
| `main`'s processes, and every other service | `environment/docker-compose.yaml` | `pids_limit` for main (it counts processes and threads); `cpus`, `mem_limit`, `pids_limit` for every other service. Never `deploy.resources.limits`: docker refuses it beside `cpus` / `mem_limit`. |
| a service that holds a GPU | its compose service | The device reservation, written by hand: `deploy.resources.reservations.devices` with `driver: nvidia` and `capabilities: [gpu]`. Never `gpus:` or `runtime: nvidia`. A device whose capabilities name `gpu` counts as a GPU with or without the driver line. `x-gpu-memory-gb` is its GPU-memory cap in GiB, the one field of our own. |
| the separate verifier | `task.toml` `[verifier.environment]`; `tests/docker-compose.yaml` | `cpus`, `memory_mb` (and `storage_mb`), set by hand. |

**The verifier's caps.** Harbor uses `[verifier.environment]` alone when it exists, so a key it lacks is **no cap**.
Without the table, the verifier gets a copy of `[environment]`, `storage_mb` included. Its process cap is `pids_limit`
of `main` in `tests/docker-compose.yaml`, set by hand. A GPU service there gets `x-gpu-memory-gb` equal to main's when
main holds a GPU. Otherwise the task writes that line itself, and `normalize` keeps it.

**Settings that are not caps.** Other compose keys a task writes itself are settings: `shm_size` (the size of
`/dev/shm`; what is stored there also counts against the container's memory cap), devices, volumes.

## The rules file

The caps come from the rules in `scripts/task_resources.toml`. `python3 scripts/task_conventions.py <task dirs>`
(`normalize`) writes them, and creates `[environment]` when a task has none. `ci_checks/check-resources.py` checks
that the declared caps are the applied ones. A cap the compose file sets itself must equal the rule's.

A task that no rule matches keeps the caps its own `[environment]` and compose file set. CI accepts them as long as
every container has its caps.

A rule is a `[[cap]]` table:

- `match`: a regular expression searched in the task directory's name. The **last** rule that matches a task applies,
  whole. Rules are never merged.
- One inline table per compose service, keyed by its name. The services must be exactly the task's compose services
  (`rcb_monitor` aside).
  - `main = { cpus, memory_gb, pids, disk_gb }`; `cpus` is a whole number.
  - Every other service: `{ cpus, memory_gb, pids }`.
  - `gpu_memory_gb` on, and only on, a service that reserves a GPU.
- Optional:
  - `gpu_types` (written to `[environment]`) and `recommended_gpu`, both shown in the task README;
  - `measured` (what the benchmark was measured to use) and `caps_measured` (the measured peaks the caps come from),
    kept in the rules file only.

```toml
[[cap]]
match = "^mybench-.*-standard$"          # the last match wins; `-standard$` does not match `-realtime` tasks
main = { cpus = 4, memory_gb = 3, pids = 1024, disk_gb = 10 }
sim = { cpus = 4, memory_gb = 5, pids = 1024, gpu_memory_gb = 4 }
recommended_gpu = "any 8 GB+ NVIDIA GPU (RTX 4090 / L4)"
measured = "oracle trials on an RTX 4090: sim 1.9 GiB, 1.2 GiB of GPU memory; agent's container 0.1 GiB"
caps_measured = "memory: sim 1.9 GiB -> max(1.5 x peak, peak + 3) = 5 GiB; main 0.1 GiB -> peak + 2 = 3 GiB; GPU memory 1.2 GiB -> 4 GiB; processes and disk: the minimums"
```

## How a rule's caps are chosen

From the peaks seen in measured runs:

- **Memory:** the larger of 1.5 × the peak and the peak plus a margin (+2 GiB for main, +3 GiB for another service).
- **GPU memory:** the larger of 1.5 × the peak and the peak + 2 GiB. At least 16 GiB for Isaac Sim.
- **CPU:** at least every reading, on hosts that applied the cap and on hosts that did not. A simulator that runs in
  real time keeps the CPU its slowdown was measured with.
- **Processes and threads:** a power of two, at least 2 × the peak thread count and at least 1024. Isaac Sim gets
  4 ×, since its thread count follows the host's cores.
- **Disk:** at least 10 GiB.

The peaks never raise a cap above the rule's earlier cap. A cap with no per-container measurement keeps the earlier
cap.

From the largest call the task allows: a simulator service that builds a response of frames in memory gets at least
its resident size + 1.2 × what building the largest legal response holds, in whole GiB. It gets 2 GiB more where that
leaves no margin over thin data.

A cap may be set above what the peaks give only by (a) this largest-call rule, (b) kernel OOM kills recorded at the
earlier cap, or (c) an owner's decision, which may also set a cap below. `caps_measured` names which one applies.

An honest agent and the oracle must stay inside the caps. Any cap but CPU can get a process killed. A benchmark that
cannot meet this states the exception in its README.

## Who enforces a cap

**The container runtime first.** Docker and Harbor apply what the host lets them.

**The resource monitor second.** The `rcb_monitor` sidecar reads each container's own cgroup limits (`cpu.max`,
`memory.max`, `pids.max`, or their cgroup v1 equivalents) at every sample. It samples every 5 s, disk once a minute.

- A cap the runtime holds, at the cap or below, is the runtime's. The monitor only records it.
- A cap whose limit is missing or higher than the cap is enforced by the monitor when the run-time switch
  `RCB_LIMITS_ENFORCE` is `1` (the backstop). With `0` (the default) it is only recorded. Disk and GPU memory are
  always in this group.
- The monitor acts on main and, in privileged mode, on the services the agent drives, the way Docker would. The
  benchmark's own services (a standard mode's sim sidecar, RoboPaint's `scorer`) are recorded only, in both settings.
- A measurement is over a cap above cap × (1 + `RCB_LIMITS_TOLERANCE`), default 0.05, for sampling noise. A count of
  processes and threads is over above the cap itself, in two samples in a row: one alone can be a burst.
- Who enforced each cap of each container is in the record (`enforced_by`).

| Resource | Docker / Harbor on a cgroup v2 Docker host | Hosts where they do not | Monitor backstop (`RCB_LIMITS_ENFORCE=1`) |
|---|---|---|---|
| CPU (`cpus`) | a throttle (CFS quota) | rootless podman without a delegated cgroup: none | Writes the cap as the container's own CPU quota where its cgroup can be written, and puts the old value back after. Otherwise duty-cycles the container's processes with `SIGSTOP` / `SIGCONT` (100 ms periods) while their demand is above the cap. Never a kill. |
| Memory (`memory_gb`) | the kernel's OOM killer, at the container's cap | rootless podman without a delegated cgroup: none | Kills the process with the largest PSS, one per sample, and only when the processes it may kill hold enough to cover the excess (none holding under 10 MiB). |
| Processes and threads (`pids`) | a fork or a new thread fails at the cap | rootless podman without a delegated cgroup: none | Kills the newest processes until the count is back at the cap, only when they hold enough of the count (not when the excess is PID 1's or unreaped zombies). |
| Disk (`disk_gb`, `storage_mb`) | a cloud backend may apply `storage_mb` | local Docker (overlay2 on ext4): none | Kills the process holding the most bytes open for writing under the measured paths, when those bytes cover the excess and are at least 10 MiB. No second kill until the disk has grown again or has been under the cap. |
| GPU memory (`x-gpu-memory-gb`) | none | every card without MIG: none (a card may be shared) | Kills the process holding the most GPU memory in that container, one per sample, when the processes it may kill can cover the excess. |

**What the monitor never does.**
- It never kills PID 1 of a container or what started with it.
- It kills a process only while that process still has the start time it was measured with and is still in the
  trial's container. It uses a pidfd where the kernel has them, and checks again right before each signal elsewhere.
- What it cannot observe it records and never acts on: GPU memory NVML does not report, NVML's process IDs when the
  monitor is outside the host's PID namespace, open files it cannot read.
- Neither setting changes the grade. A killed process ends like any process that dies. The trial may fail for it,
  and the grader judges what the agent left. Going over a cap is recorded (`limits_violation_observed`).

**The `SIGSTOP` fallback.**
- It is used only where the runtime does not hold the container's CPU and its cgroup cannot take a quota (rootless
  runtimes; `cgroup: host` is read-only on most hosts).
- It is visible to the agent. An interactive shell with job control reports a throttled child as a stopped job
  (`Stopped`) and may stop waiting for it.
- It resumes only the processes it stopped. A stop the agent sends to a process the monitor holds stopped cannot be
  told apart, and is undone with it. A restarted monitor resumes every stopped process of a throttled container that
  is not known to have been stopped by the agent.
- It looks for new processes twice per period, so a short process can run free for up to one period. The share never
  drops below the cap divided by the container's CPUs, or 0.5 %, so no process is held for more than 0.4 s. When short
  processes alone use more than the cap, the monitor records `throttle_insufficient`.
- Without a cgroup of its own (apptainer, rootless podman without delegation), a container's CPU is counted from its
  processes and the children they reaped. A process that ends between two samples counts only through its parent.

**cgroup v1.** Docker applies CPU, memory and processes through the v1 controllers. The monitor then measures memory
by PSS and reads no kernel OOM counters. It reads the runtime's limits from the container's directories where the v1
hierarchy is visible to it. Where it is not, every cap is recorded as the monitor's, and the kernel still applies the
runtime's limits first.

**Without `pid: host`.** A runtime that refuses `pid: host` runs the monitor as a beacon: `usage.json` has the caps and
the clock, nothing is measured or enforced.

**GPU memory of a recorded service and of the verifier.** Their `x-gpu-memory-gb` is a cap stated for the reader.
Nothing measures it.

## What the agent sees

- The Resources line of its instruction's `## Limits`: the caps of its own container.
- `/run/rcb-limits/usage.json`: its container's use (`own`) and caps (`caps`), the scope's sums, `limits`
  (`gpu_memory_gb`, `disk_gb`, `tolerance`), `over`, `kills`, `cpu_throttled`, `enforced_by`, and its clock
  (`elapsed_s`, `time_left_s`, `deadline_utc`). Under a beacon it also says `"measured": false`.
- Its own cgroup files: `/sys/fs/cgroup/memory.max`, `cpu.max`, `pids.max`.

## Running with caps

- **The switches** are run-time environment variables with compose defaults, so they do not change the digest.
  - `RCB_LIMITS_ENFORCE`: `0` (default) Docker and Harbor enforce what the host lets them, the monitor records; `1`
    the monitor is also the backstop. Any other value enforces nothing and gives `infra_error = 1`,
    `resource_switch_error = 1`.
  - `RCB_LIMITS_TOLERANCE`: a number in [0, 1], default `0.05`. Anything else is treated like a bad switch.
- **CPU caps above the host's count** mean the host's count. The runner clamps them in its copy
  (`scripts/clamp_cpus.py`). Memory and process caps are never clamped.
- **Placing trials.** Harbor caps each container and does not check whether a machine has room (concurrency is `-n`).
  A machine that holds the sum of a phase's caps never runs short. Packing more is the runner's call.
- **Out-of-memory kills.** A host OOM kill of a process in the scope is never the agent's: with enforcement on it is
  `infra_error = 1` (`resource_host_oom`). A benchmark-owned service killed for memory in an episode that did not
  succeed is `infra_error = 1` (`resource_service_oom`) in both settings. A trial a pool kills to protect its host is
  an operations abort (`killed_by_pool`), not a graded result.

## The record

The monitor writes its own record (`rcb-monitor/1`) and seals it in the first collect hook.

- Per container (`containers`): `service`, `cpu`, `memory_gb`, `processes`, `threads`, `pids`, `gpu_memory_gb`.
  Summed over the scope (`scope`), with `disk_gb`.
- Each container's `runtime`: the limits its own cgroup set (`cpus`, `memory_gb`, `pids`; null for none).
- Events:
  - `enforcement`: who holds each cap (`by`: `runtime`, `monitor` or `none`), written when it changes;
  - `over`: the first time a container is over a cap, per resource, with `by`;
  - `kill`: `resource` (`memory`, `pids`, `disk`, `gpu_memory`), `pid`, `value`, `cap`;
  - `throttle_start` / `throttle_end`: CPU, with `method` (`cgroup` or `signal`), `sec` and `engaged_sec`;
  - `throttle_insufficient`, `unobservable`, `no_victim`, `backstop_error`;
  - `oom`: a kernel OOM kill, with `cause` `cap` or `host`.
- The summary counts failed record writes (`write_errors`) and reads that failed for want of a file descriptor
  (`fd_exhausted`).
- The verifier recomputes what was over a cap from the raw samples, with its own copy of the caps
  (`tests/rcb_limits.json`, format `rcb-limits/2`).
- A missing, unsealed or mostly empty record (more than 10 % of the agent phase unobserved) is
  `resource_monitor_missing = 1`. With `RCB_LIMITS_ENFORCE=1` that is `infra_error = 1`: the backstop that was asked
  for did not run.
- **Session log.** The monitor copies the agent's `/app/output/rcb_session_log.jsonl` append-only into its record
  (`session_log/`). When the agent's file was removed or rewritten, the verifier gives the grader that copy
  (`session_log_tampered`, `session_log_from_monitor`). The log feeds cost fields only.

**`reward.json` fields** (always written): `resource_enforced`, `limits_violation_observed`,
`resource_monitor_missing`; the peaks `peak_gpu_memory_gb`, `peak_memory_gb`, `peak_processes`, `peak_pids`,
`peak_cpus`, `peak_disk_gb` (the scope's sums); `over_<metric> = 1` per metric over its cap (`memory_gb`, `pids`,
`cpus`, `gpu_memory_gb`, `disk_gb`, `oom`); the backstop's `resource_memory_kills`, `resource_pids_kills`,
`resource_disk_kills`, `resource_gpu_memory_kills`, `resource_monitor_kills` (their sum), `resource_cpu_throttles`,
`resource_cpu_throttled_sec`; the kernel's `resource_oom_kills`, `resource_host_oom_kills`,
`resource_service_oom_kills`. Details are in `/logs/verifier/resource_limits.json`.
