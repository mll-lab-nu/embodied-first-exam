# iSpatialGym

Spatial intelligence on a mobile bimanual robot: the task is a picture. Each instance gives only a goal image, the head
camera's view once the task is done, and the robot has to make the scene look like it (an object's pose, a relation
between two objects, an articulation, its own viewpoint). No sentence names the objects. No benchmark in the set states
its goal this way; BEHAVIOR-1K runs the same robot in the same houses with goals in words.

| | |
|---|---|
| upstream | iSpatialGym "eval v1.0" (`kmy17518/iSpatialGym`, branch `ispatialgym-eval-release`, `6c1ed2e7`; [demo gallery](https://minyeongkim.com/ispatialgym/)), on its BEHAVIOR-1K fork (`kmy17518/BEHAVIOR-1K`, branch `ispatialgym-eval`, `6a619460`) and its eval data (`kmy17518/ispatialgym-eval-data`, `15cb9a71`) |
| licence | the iSpatialGym repository is private and has no licence file (Known issues); BEHAVIOR-1K's code is MIT, its dataset licensed (no redistribution) |
| simulator | OmniGibson (the fork: 3.9 + the vector-env merge + iSpatialGym's object states) on Isaac Sim 5.1, CPU PhysX at 120 Hz; cuRobo v0.8.0 |
| robot | R1Pro: holonomic base, 4-joint trunk, two 7-joint arms with parallel grippers; iSpatialGym's 23-D JoyLo action at 30 Hz; head and wrist cameras, 1080×1080 RGB |
| score | upstream's geometric success as `run_isg --mode policy` judges it: the BDDL goal and every measured target within the `isg-v2` tolerances × 3, at the same step; within max(300, 2 × the demo's length) control steps |
| tasks | 14, standard mode only: `tasks/ispatialgym-<task>-i00-standard` (`eai-standard/2.2`) |
| image | `ghcr.io/mll-lab-nu/eai-ispatialgym:0.1.1` (`images/ispatialgym/`, BUILD_ONLY: Isaac Sim inside, and the private source is passed in at build time) |
| oracle | none |

## Tasks: upstream's 23, ours ✅ (14)

| family | task | the robot must | ours | why not |
|---|---|---|---|---|
| alignment | axial | push an object on a table until its long axis lines up with the table edges | ✅ | |
| | vertical | push a tilted object hanging on a wall upright | ✅ | |
| camera relocalization | obstructed | drive and set the trunk so that the head camera sees the goal image, around an obstacle | ✅ | |
| | standard | the same without the obstacle | ⬜ | obstructed's goal |
| configuration matching | articulation open, small scale | open a small object (blender, carton) to the pictured angle, the other arm bracing it | ✅ | |
| | articulation close, small scale | close it | ⬜ | the closing twin |
| | articulation open / close, large scale | open or close a door or dishwasher, mostly with the base and trunk | ⬜ | the small-scale rule at scene scale |
| | attachment | put a lid, cap or cork on its partner as pictured | ✅ | |
| | block design | arrange four Kohs blocks so that their tops show the pictured 2×2 pattern | ✅ | |
| disembedding | (one) | find the pictured object among distractors and move it alone to the other tray | ✅ | |
| object relations | inside / next to / on top / touching / under, small scale | place an object so that it stands in the pictured relation to a partner on the same surface | ✅ (5) | |
| | the same five, large scale | the same relation to a scene fixture (sink, bed, bookcase), with the base | ⬜ (5) | the small-scale rule at scene scale |
| mental rotation | (one) | turn a held object in the hand to the pictured orientation | ✅ | |
| object scaling | (one) | move a held object along the camera's axis until it looks as large as pictured | ✅ | |

Why these (no model's results enter the choice; `scripts/ispatialgym/subset.toml`):
- **One task per success rule.** A task whose BDDL goal and measured targets are another's keeps one: the obstructed
  camera relocalization (the standard one is it without the obstacle); of an open / close pair the opening twin, as in
  BiGym 2.0; of a relation checked at two scales the small-scale task (tighter tolerances; at scene scale the partner is a
  fixed fixture reached with the base, what BEHAVIOR-1K's tasks cover on the same robot and houses). 23 → 14.
- **Valid here.** Within a task, the first subtask in upstream's index (`metadata/instances.jsonl`) whose instance loads,
  does not succeed when the robot holds still for the whole budget, and replays to the same final state in fresh
  processes (`scripts/ispatialgym/instances/<task>/facts.json`). Every first subtask passed.
- **Instance 0** of that subtask (the release has one per subtask); 13 of the 14 are in `house_single_floor`.

## Mode: standard only (PROTOCOL §3)
Upstream evaluates exactly this: a policy that gets the goal image and the robot's observations. A privileged mode would
give the agent the simulator and its full state, which holds the measured target poses, i.e. the answer the picture is
meant to pose.

| given (a real R1Pro has it) | not given |
|---|---|
| `/app/goal.png` (the head camera, the same intrinsics); the success rule with its tolerances, not which objects | any object's or target's pose; which objects the task concerns |
| three RGB cameras, 1080×1080, with intrinsics and extrinsics | depth (upstream's evaluation renders none); the world frame (poses are in the odometry frame: the robot's start) |
| joints, base pose and velocity, end-effector and fingertip poses, gripper openings; `robot_spec`; stateless FK / IK | the goal check before the episode ends; resets (budget 0, the protocol's default) |

## Where upstream keeps the answers

| what | where upstream has it | here |
|---|---|---|
| measured targets and tolerances, the goal camera's world pose | the instance file (`*-tro_state.json`: `pose_targets`, `goal_observation`) | sidecar only (`environment/sim/instance/`); the agent sees the tolerances |
| demonstrations | `ispatialgym-eval-demos` (public GitHub: actions per step) | in no image and no task; the agent's egress is the model APIs and package registries |
| the scripted demonstrator and its per-instance plans | `ispatialgym/oracle/`, `*.oracle.json` | in the sidecar image only (the agent's container is the eai-standard client); no sidecar file is copied |
| the instance generator, its specs and seeds | `ispatialgym/sampling/`, `assets/task_specs/` | sidecar image only |

## Run
```bash
export RCB_BEHAVIOR_DATA=/path/to/behavior-data   # omnigibson-robot-assets/, behavior-1k-assets/ (3.9.0), omnigibson.key; mounted at /bdata
harbor run -p tasks/ispatialgym-mental-rotation-i00-standard -a codex -m openai/gpt-6-luna --env-file .env
harbor run -p tasks/ispatialgym-mental-rotation-i00-standard -a nop      # scores 0
```
The dataset is the BEHAVIOR Data Bundle (`omnigibson.utils.asset_utils`: `download_omnigibson_robot_assets()`,
`download_behavior_1k_assets(accept_license=True)`), the same one BEHAVIOR-1K's tasks mount. Build the image as
`images/ispatialgym/BUILD_ONLY` says. Regenerate the tasks: `python3 scripts/ispatialgym/mk_tasks.py render`
(`instances` copies the picked instances from upstream's eval data; `measure --task T` writes `facts.json`, on a GPU).

## Known issues
- **Licence.** Upstream's repository is private and carries no licence; the image is BUILD_ONLY and its source is passed
  in by the builder. The task directories hold upstream's instance files (scene, start state, goal image): the authors'
  permission is needed before the tasks are published.
- **No fall rule.** Upstream ends an episode only on success or at its step budget. The R1Pro can tip over against an
  obstacle (seen in camera relocalization), and in one run a toppled robot driven on fell through the floor; the episode
  then runs on to its budget. Kept as upstream has it.
- **Sim start-up is on the agent's clock**: 7-15 min measured per trial (a cold Kit cache), inside the hour.
- **GPU memory.** One trial's Isaac process takes 4-7 GiB of GPU memory; three trials beside other work on one 24 GB card
  ran out of it at start-up (an infrastructure failure, `infra_error = 1`). The service exits non-zero on a start-up error so
  that compose restarts it (Isaac's Kit otherwise exits 0).
