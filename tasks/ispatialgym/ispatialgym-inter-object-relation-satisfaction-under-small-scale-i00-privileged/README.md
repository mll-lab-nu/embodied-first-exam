# ispatialgym-inter-object-relation-satisfaction-under-small-scale-i00-privileged

| | |
|---|---|
| Benchmark | iSpatialGym |
| Mode | privileged |
| Twin | `ispatialgym-inter-object-relation-satisfaction-under-small-scale-i00-standard` |
| Simulator / robot | `ispatialgym` / `r1pro` |
| Family / instance | `inter_object_relation_satisfaction_under_small_scale` / seed 0 |
| Oracle | `none` — upstream's goal image of this instance is the last frame of a successful replay of upstream's own demonstration of it (kmy17518/ispatialgym-eval-data@15cb9a7, ispatialgym-eval-instances/README.md, Goal images) |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:ispatialgym-0.2.1` |

## Task
iSpatialGym `inter_object_relation_satisfaction_under_small_scale` (family `inter_object_relation_satisfaction`), upstream subtask `inter_object_relation_satisfaction_under_small_scale_teacup_saucer`, instance 0 (house_single_floor): Set the target down centred on the partner, so that the partner, such as a coaster or saucer, ends under it. The task is given
only as the goal image (`/app/goal.png`, the head camera's view once it is done), as in iSpatialGym's own
evaluation; the instruction names no object.

## Difficulty
The agent has the simulator and every object's state, but nothing says which object, relation or pose the picture asks
for: it has to work that out from one image, then deliver one open-loop trajectory of at most 2214 control steps
(73.8 s of simulated time, iSpatialGym's policy budget) that does it from the frozen start. Holding still does not
succeed (`hold` in `tests/facts.json`).

## Reference solution
None.

## Verification
The verifier restores this task's `goal.json` onto the frozen start (`tests/instance.json`, byte-identical to the
agent's `environment/instance.json` and to the standard twin's), checks the result against upstream's own TRO by
sha256, and replays `/app/output/trajectory.npz` in one fresh process: `success` = that replay reaches iSpatialGym's
geometric success as `run_isg --mode policy` judges it (the BDDL goal and every measured target within the isg-v2
tolerances x 3, held over the last 45 control steps with the task's objects and the robot at rest: upstream's settle-eval). `bad_trajectory` (unreadable, not
`(T, 23)` finite, more than 2214 rows) scores 0; a replay that dies or times out, a failed restore or a start that
does not rebuild is `infra_error` + `grader_error`. `/logs/verifier/replay.mp4`.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 12 | 38 GiB | 4096 | 22 GiB | 10 GiB |
| verifier (as `main`) | 12 | 38 GiB | no cap | 22 GiB | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Agent's container | the ispatialgym image with every BDDL problem, the eval data's repository id and folder names, the project URLs, tests and docs removed at build; the build fails if any is left or if a scripted expert, sampler, task spec or eval-data file is in the image (the public release ships none) (`environment/scrub/scrub.sh`); this task's start-only BDDL problem is written from the image's own copy |
| Action space | `s.step(a)`: 23 floats (base velocity command, trunk, both arms, one command per gripper; iSpatialGym's JoyLo action), one 30 Hz control step |
| Goal | `/app/goal.png` (from the files-only image `ispatialgym-goals-files`): upstream's goal image of this instance, the head camera at 1080×1080 |
| Instance | `environment/instance.json` = `tests/instance.json`: the start only (scene, template keys the loader reads, start-only TRO, objects without upstream's role names); start-state hash 9b28f2ec02007e4d |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only from `$RCB_BEHAVIOR_DATA` (a precondition) |
