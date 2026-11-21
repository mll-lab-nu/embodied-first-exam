# ispatialgym-inter-object-relation-satisfaction-ontop-small-scale-i00-standard

| | |
|---|---|
| Benchmark | iSpatialGym |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `ispatialgym-inter-object-relation-satisfaction-ontop-small-scale-i00-privileged` |
| Simulator / robot | `ispatialgym` / `r1pro` |
| Family / instance | `inter_object_relation_satisfaction_ontop_small_scale` / seed 0 |
| Oracle | `none` — upstream's goal image of this instance is the last frame of a successful replay of upstream's own demonstration of it (kmy17518/ispatialgym-eval-data@15cb9a7, ispatialgym-eval-instances/README.md, Goal images) |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:ispatialgym-0.2.1` |

## Task
iSpatialGym `inter_object_relation_satisfaction_ontop_small_scale` (family `inter_object_relation_satisfaction`), upstream subtask `inter_object_relation_satisfaction_ontop_small_scale_pack_of_kielbasa_platter`, instance 0 (house_single_floor): Place the target centred on top of the partner; both start on the same surface. The task is given
only as the goal image (`/app/goal.png`, the head camera's view once it is done), as in iSpatialGym's own
evaluation; the instruction names no object.

## Difficulty
The agent has to work out from one picture what differs between the scene and the goal (which object, which relation,
which pose) and then do it with a mobile bimanual robot it only sees through its own cameras and proprioception, within
1900 control steps (63.3 s of simulated time, iSpatialGym's policy budget: twice the length of upstream's own
demonstration of this instance, at least 300). Holding still does not succeed (`hold` in
`scripts/ispatialgym/instances/inter_object_relation_satisfaction_ontop_small_scale/facts.json`).

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

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 5 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 12 | 21 GiB | 2048 | 9 GiB | — |
| verifier (as `main`) | 8 | 5 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2`: RGB + proprioception through the client; no reset, no object poses, no success predicate |
| Action space | `submit` chunks of `joint_position` (23: base velocity command, trunk, both arms, one command per gripper; iSpatialGym's JoyLo action) streamed at the 30 Hz control rate; `observe` frames or a watch window; stateless `/kinematics` |
| Goal | `/app/goal.png` (from the files-only image `ispatialgym-goals-files`): upstream's goal image of this instance, the head camera at 1080×1080 |
| Instance | `environment/sim/instance.json`, byte-identical to the privileged twin's: the start only (scene, template keys the loader reads, start-only TRO, objects without upstream's role names); `environment/sim/goal.json` (sidecar only) restores upstream's targets onto it, checked by sha256; start-state hash d1d22a94d97adcfa |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only into the sidecar from `$RCB_BEHAVIOR_DATA` (a precondition) |
| Crash recovery | `restart: on-failure:6`; the service journals every control step and resumes the same episode after a crash (resume class `approx`) |
