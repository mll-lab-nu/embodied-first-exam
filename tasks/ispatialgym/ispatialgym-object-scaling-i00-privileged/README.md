# ispatialgym-object-scaling-i00-privileged

| | |
|---|---|
| Benchmark | iSpatialGym |
| Mode | privileged |
| Twin | `ispatialgym-object-scaling-i00-standard` |
| Simulator / robot | `ispatialgym` / `r1pro` |
| Family / instance | `object_scaling` / seed 0 |
| Oracle | `none` — upstream's goal image of this instance is the last frame of a successful replay of upstream's own demonstration of it (kmy17518/ispatialgym-eval-data@15cb9a7, ispatialgym-eval-instances/README.md, Goal images) |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:ispatialgym-0.2.0` |

## Task
iSpatialGym `object_scaling` (family `object_scaling`), upstream subtask `object_scaling_apple`, instance 0 (house_double_floor_lower): The object is held in the right hand; the goal is a change of its depth along the head camera's optical axis. The task is given
only as the goal image (`environment/goal.png`, the head camera's view once it is done), as in iSpatialGym's own
evaluation; the instruction names no object.

## Difficulty
The agent has the simulator and every object's state, but nothing says which object, relation or pose the picture asks
for: it has to work that out from one image, then deliver one open-loop trajectory of at most 300 control steps
(10.0 s of simulated time, iSpatialGym's policy budget) that does it from the frozen start. Holding still does not
succeed (`hold` in `scripts/ispatialgym/instances/object_scaling/facts.json`).

## Reference solution
None.

## Verification
The verifier restores this task's `goal.json` onto the frozen start (`tests/instance.json`, byte-identical to the
agent's `environment/instance.json` and to the standard twin's), checks the result against upstream's own TRO by
sha256, and replays `/app/output/trajectory.npz` in two fresh processes: `success` = both replays reach iSpatialGym's
geometric success as `run_isg --mode policy` judges it (the BDDL goal and every measured target within the isg-v2
tolerances x 3, held over the last 45 control steps with the task's objects and the robot at rest: upstream's settle-eval) and end in the same state. `bad_trajectory` (unreadable, not
`(T, 23)` finite, more than 300 rows) scores 0; a replay that dies or times out, a failed restore or a start that
does not rebuild is `infra_error` + `grader_error`. `/logs/verifier/replay.mp4`.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 6 | 6 |
| Memory | 16 GB | 16 GB |
| GPU memory | 6 GB | 6 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: privileged prototype trials, GPT-6 Luna, RTX 4090, 2026-10-16 (docker stats and nvidia-smi per process every 30 s, 9 trials and their verifiers): the agent container peaked at 14.2 GiB of memory, 14.6 GiB of GPU memory and 12 cores (an agent may run two Isaac processes of about 13 GiB / 4.6 GiB each), the verifier at 14.4 GiB and 12 cores; limits max(1.5 x peak, peak + 4), memory kept at 32 GiB for two processes
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 22 GiB GPU memory, 32 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 22 GiB GPU memory, 32 GiB memory. Limits measured: privileged prototype trials, GPT-6 Luna, RTX 4090, 2026-10-16 (docker stats and nvidia-smi per process every 30 s, 9 trials and their verifiers): the agent container peaked at 14.2 GiB of memory, 14.6 GiB of GPU memory and 12 cores (an agent may run two Isaac processes of about 13 GiB / 4.6 GiB each), the verifier at 14.4 GiB and 12 cores; limits max(1.5 x peak, peak + 4), memory kept at 32 GiB for two processes.

## Details
| | |
|---|---|
| Agent's container | eai-ispatialgym with every BDDL problem, the eval data's repository id and folder names, the project URLs, tests and docs removed at build; the build fails if any is left or if a scripted expert, sampler, task spec or eval-data file is in the image (the public release ships none) (`environment/scrub/scrub.sh`); this task's start-only BDDL problem is written from the image's own copy |
| Action space | `s.step(a)`: 23 floats (base velocity command, trunk, both arms, one command per gripper; iSpatialGym's JoyLo action), one 30 Hz control step |
| Goal | `environment/goal.png` (copied to `/app/goal.png`): upstream's goal image of this instance, the head camera at 1080×1080 |
| Instance | `environment/instance.json` = `tests/instance.json`: the start only (scene, template keys the loader reads, start-only TRO, objects without upstream's role names); start-state hash 572f8d06c14fd44f |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition) |
