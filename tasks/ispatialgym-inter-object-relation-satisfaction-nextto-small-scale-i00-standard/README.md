# ispatialgym-inter-object-relation-satisfaction-nextto-small-scale-i00-standard

| | |
|---|---|
| Benchmark | iSpatialGym |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `ispatialgym-inter-object-relation-satisfaction-nextto-small-scale-i00-privileged` |
| Simulator / robot | `ispatialgym` / `r1pro` |
| Family / instance | `inter_object_relation_satisfaction_nextto_small_scale` / seed 0 |
| Oracle | `none` — upstream's goal image of this instance is the last frame of a successful replay of upstream's own demonstration of it (kmy17518/ispatialgym-eval-data@15cb9a7, ispatialgym-eval-instances/README.md, Goal images) |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-ispatialgym:0.2.0` |

## Task
iSpatialGym `inter_object_relation_satisfaction_nextto_small_scale` (family `inter_object_relation_satisfaction`), upstream subtask `inter_object_relation_satisfaction_nextto_small_scale_marker_colored_pencil`, instance 0 (house_single_floor): Move the target until it is next to the partner, keeping its orientation. The task is given
only as the goal image (`environment/goal.png`, the head camera's view once it is done), as in iSpatialGym's own
evaluation; the instruction names no object.

## Difficulty
The agent has to work out from one picture what differs between the scene and the goal (which object, which relation,
which pose) and then do it with a mobile bimanual robot it only sees through its own cameras and proprioception, within
2076 control steps (69.2 s of simulated time, iSpatialGym's policy budget: twice the length of upstream's own
demonstration of this instance, at least 300). Holding still does not succeed (`hold` in
`scripts/ispatialgym/instances/inter_object_relation_satisfaction_nextto_small_scale/facts.json`).

## Reference solution
None.

## Verification
`success` = the live episode's success, judged by the sim sidecar at every control step the episode runs; nothing
replays it (2026-10-17). Success is iSpatialGym's own geometric success as `run_isg --mode policy` judges it (the BDDL goal
and every measured target within the isg-v2 tolerances x 3, held over the last 45 control steps with the task's objects and the robot at rest: upstream's settle-eval).
Upstream's symbolic success and the success step are reported apart, and so are the crash-recovery fields; the video
(`/logs/verifier/live.mp4`, the head camera) is recorded during the episode (a video-only render, `replay.mp4`, only
when it is missing) and never decides anything. The frozen start
is checked when the sidecar builds the scene, before the agent is served. `infra_error` = 1 (no verdict on the agent) when
`final.json` is missing, unreadable or not finalized, the service never ended the episode, it gave up after crashes not
all inside the agent's calls, or the frozen start did not rebuild (`instance_mismatch`).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 6 | 6 |
| Memory | 16 GB | 16 GB |
| GPU memory | 6 GB | 6 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: freezing the 14 instances (RTX 4090, 2026-10-14, docker stats and nvidia-smi every 20 s, four Isaac processes at once): one Isaac process with the robot's three 1080x1080 cameras holds 12-13 GiB of memory and 3.5-4.6 GiB of GPU memory, 4-7 cores while Isaac starts and the scene loads, about 1 core after; the sim service is one such process (plus the live video's encoder, 540 px at 10 fps, not measured), the collect hook replays nothing (graded live, 2026-10-17); the agent's container runs the client only
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 9 GiB GPU memory, 21 GiB memory. Limits measured: freezing the 14 instances (RTX 4090, 2026-10-14, docker stats and nvidia-smi every 20 s, four Isaac processes at once): one Isaac process with the robot's three 1080x1080 cameras holds 12-13 GiB of memory and 3.5-4.6 GiB of GPU memory, 4-7 cores while Isaac starts and the scene loads, about 1 core after; the sim service is one such process (plus the live video's encoder, 540 px at 10 fps, not measured), the collect hook replays nothing (graded live, 2026-10-17); the agent's container runs the client only -> max(1.5 x peak, peak + 4) for the trial (GPU 4.6 GiB, memory 13.5 GiB with the agent's client); the agent's own memory, processes and disk: the standard modes' defaults.

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2`: RGB + proprioception through the client; no reset, no object poses, no success predicate |
| Action space | `submit` chunks of `joint_position` (23: base velocity command, trunk, both arms, one command per gripper; iSpatialGym's JoyLo action) streamed at the 30 Hz control rate; `observe` frames or a watch window; stateless `/kinematics` |
| Goal | `environment/goal.png` (copied to `/app/goal.png`): upstream's goal image of this instance, the head camera at 1080×1080 |
| Instance | `environment/sim/instance.json`, byte-identical to the privileged twin's: the start only (scene, template keys the loader reads, start-only TRO, objects without upstream's role names); `environment/sim/goal.json` (sidecar only) restores upstream's targets onto it, checked by sha256; start-state hash d031dc8f7893a9de |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only into the sidecar from `$RCB_BEHAVIOR_DATA` (a precondition) |
| Crash recovery | `restart: on-failure:6`; the service journals every control step and resumes the same episode after a crash (resume class `approx`) |
