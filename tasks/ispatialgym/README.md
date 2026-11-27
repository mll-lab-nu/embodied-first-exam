# iSpatialGym

## Overview
Spatial intelligence on a mobile bimanual robot: the task is a picture. Each instance gives only a goal image, the head
camera's view once the task is done, and the robot has to make the scene look like it (an object's pose, a relation
between two objects, an articulation, its own viewpoint). No sentence names the objects. 12 of upstream's tasks, one
frozen instance each, in the privileged and standard modes: 24 task directories,
`tasks/ispatialgym/ispatialgym-<task>-i00-privileged` and `-standard`.

| | |
|---|---|
| upstream | iSpatialGym's pre-release evaluation pipeline (`kmy17518/iSpatialGym` @ `fddcf756`, MIT; [demo gallery](https://minyeongkim.com/ispatialgym/)), on its BEHAVIOR-1K fork (`kmy17518/BEHAVIOR-1K`, branch `ispatialgym-eval`, `6a619460`, its submodule) and its eval data (Hugging Face `kmy17518/ispatialgym-eval-data`, revision `v1.0`) |
| simulator | OmniGibson (the fork: 3.9 + the vector-env merge + iSpatialGym's object states) on Isaac Sim 5.1, CPU PhysX at 120 Hz |
| robot | R1Pro: holonomic base, 4-joint trunk, two 7-joint arms with parallel grippers; iSpatialGym's 23-D JoyLo action at 30 Hz; head and wrist cameras, 1080×1080 RGB |
| metadata | `simulator = "ispatialgym"`, `robot = "r1pro"`, `oracle = "none"` |
| image | `ghcr.io/mll-lab-nu/efe-private:ispatialgym-0.2.2` (`images/ispatialgym/`: Isaac Sim inside, so private; the tasks build the same recipe from public sources when they cannot pull it, both upstream repositories fetched by commit) |
| GPU | an RTX-class NVIDIA GPU (Isaac Sim needs one even headless); one Isaac process takes 4-7 GiB of GPU memory |

```bash
export RCB_BEHAVIOR_DATA=/path/to/behavior-data   # the licensed BEHAVIOR dataset: once, see below
harbor run -d embodied-first-exam@all -p tasks/ispatialgym -a codex -m openai/gpt-6-astra
```

### Before you run
One manual step, the dataset (the same directory as BEHAVIOR-1K's: skip it if you have that); the simulator image builds
itself.

1. **Host.** Linux x86_64 with Docker (BuildKit, Docker 23 or later), the NVIDIA Container Toolkit and an RTX-class NVIDIA
   GPU. Disk: about 31 GB for the image in Docker's storage and 40 GB for the dataset.
2. **The dataset (licence: non-commercial academic research only, no redistribution; once per host).** BEHAVIOR-1K's own
   downloader, run in the public BEHAVIOR-1K base image, prints the BEHAVIOR Data Bundle licence and asks you to accept
   it (type `y`), then fetches the data anonymously from the public Hugging Face dataset `behavior-1k/zipped-datasets` and
   installs the decryption key. No account, login, token or GPU is needed:
   ```bash
   export RCB_BEHAVIOR_DATA=/path/to/behavior-data && mkdir -p "$RCB_BEHAVIOR_DATA"
   docker run --rm -it -e OMNIGIBSON_DATA_PATH=/data -v "$RCB_BEHAVIOR_DATA":/data \
     docker.io/stanfordvl/behavior:3.9.2@sha256:2702900192741904e69a573aa7869ea51c592586f9791050796efc37faa893fb \
     python -m omnigibson.utils.asset_utils --download_omnigibson_robot_assets --download_behavior_1k_assets
   ```
   iSpatialGym reads `omnigibson-robot-assets/` (3.8.2), `behavior-1k-assets/` (3.9.0) and `omnigibson.key` from it.
   Export `RCB_BEHAVIOR_DATA` in every shell that runs `harbor run`: the services that run the simulator mount it
   read-only at `/bdata` (`${RCB_BEHAVIOR_DATA:?…}`), so `docker compose` refuses to start a task without it.
3. **The simulator image: nothing to do.** The tasks' Dockerfiles hold its recipe (`images/ispatialgym/Dockerfile`:
   BEHAVIOR-1K's recipe, then iSpatialGym and its BEHAVIOR-1K fork fetched from GitHub by commit, pip versions fixed).
   The first trial on a host builds it: the 14.7 GB base from Docker Hub, ffmpeg from a dated Ubuntu snapshot, the two
   repositories and a few pip packages (about 20 min; about 1 min more on a host that already built BEHAVIOR-1K's image,
   whose layers it shares); later trials reuse it. Building it accepts the NVIDIA Isaac Sim / Omniverse licence terms of
   the official image. With pull access to the prebuilt copy
   (`ghcr.io/mll-lab-nu/efe-private:ispatialgym-<images/ispatialgym/VERSION>`), Docker takes its layers instead (compose
   `build.cache_from`); without access the build logs that it could not fetch the cache and goes on from public sources.

## Upstream and license
- iSpatialGym, [kmy17518/iSpatialGym](https://github.com/kmy17518/iSpatialGym) @ `fddcf756` (pre-release), MIT License
  (Copyright (c) 2026 iSpatialGym Authors). Its eval data (Hugging Face `kmy17518/ispatialgym-eval-data`, revision `v1.0`:
  the instances, the goal images, the demonstrations): MIT.
- Its BEHAVIOR-1K fork (`kmy17518/BEHAVIOR-1K` @ `6a619460`: OmniGibson and bddl): MIT.
- The BEHAVIOR Data Bundle (scenes, objects, robot assets), under the BEHAVIOR Data Bundle End User License Agreement:
  **non-commercial academic research use only (NC)**, no redistribution, use only within OmniGibson. It is mounted at
  run time and never copied into an image or this repository.
- NVIDIA Isaac Sim 5.1 and Omniverse Kit: NVIDIA proprietary licence terms (no public copy), accepted when the image is
  built.
- The goal images (upstream's, unchanged, MIT) are in the public Hugging Face dataset
  `MLL-Lab/embodied-first-exam-public` (`ispatialgym/`), pinned in `images/ispatialgym-goals-files/FILES.json`; each task
  copies its image to `/app/goal.png` from that files-only image.

## Changes from upstream
- **Settle-eval on.** Upstream's policy evaluation (`run_isg --mode policy`) counts the first control step on which the
  BDDL goal and every measured target hold. Here upstream's own settle-eval is on in both modes: the same conditions held
  over 45 consecutive control steps, with the named objects and the robot at rest over them (`pose_settled`: drift
  within 2 mm / 5 mrad). Without it a blind sweep of poses, or a generic probe trajectory, can pass a step by chance.
- **Tolerances.** Upstream's `isg-v2` tolerance profile, computed at load from the start state, times 3 (the policy
  scale, `run_isg --tolerance-scale 3`). Each task's applied values are in `environment/sim/facts.json`.
- **Step budget.** Upstream's policy budget, max(300, 2 × the length of upstream's demonstration of the instance)
  control steps: the privileged trajectory's row limit and the standard episode's step limit.
- **Agent-ended standard episodes.** Upstream ends an episode at the first success. In standard mode the success never
  ends the episode or shows; the agent ends it with `/finish`, or its session's end or the step limit does. At
  `/finish` and the session's end the last command is held (base at 0) for up to 45 control steps while the success has
  not been reached.
- **Frozen instances.** Both modes of a task share one frozen instance, `instance.json`, byte-identical in the privileged
  `environment/` and `tests/` and the standard `environment/sim/`: the scene template, the template keys the loader
  reads, and upstream's TRO with only what rebuilds the start (object states, robot state, bindings, hinges, grasps),
  the scene's objects named without upstream's role prefix (`target_*`, `partner_*`, …). Renaming moves the settled
  start of 3 of the 12 instances by at most 5e-5 (m or rad; alignment_axial, block_design, touching) and none of the
  others. Every key taken out of upstream's TRO and template_meta (the targets, the goal camera pose, the variant) is in
  `goal.json`, copied only to the scoring side (`environment/sim/`, `tests/`), restored there and checked against
  upstream's TRO by sha256 (a failed restore is a grader error). The success rule is upstream's BDDL problem from the
  image (sha256 in `upstream.json`) in both modes.
- **The privileged agent's image** is the ispatialgym image with a layer that removes, and the build then asserts gone:
  every BDDL problem (goals), the docs, tests, configs and README, the eval data's repository id and folder names, the
  project URLs, and bytecode; the build fails if a scripted expert, planner, sampler or task spec is there (each
  privileged task's `environment/scrub/scrub.sh`). It writes this task's start-only BDDL problem (objects and positive
  initial atoms, one neutral goal atom) from the image's own copy. Upstream's success-check code stays in the image;
  with no goal, target or problem in the container it has nothing to check, and the tooling reports no success. The
  same 300 rows give bit-identical start and final states in the agent's simulator and the verifier's, for all 12 tasks.
- **Added.** The tooling `rcb_ispatialgym.py` (session, frozen instance, recording, replay, video, FK / IK) and the
  standard-mode service (`embodied_first_exam/benchmarks/ispatialgym/sim/server.py`).

## Interface
- **Actions.** iSpatialGym's 23-D JoyLo action at 30 Hz: base (3, a velocity command in the robot's frame), trunk (4),
  left arm (7), left gripper (1), right arm (7), right gripper (1). Trunk and arm entries are absolute joint targets; a
  gripper entry is a command in [-1, 1] (-1 closed, 1 fully open). Grasping is assisted: a closing gripper holds what the
  finger pads touch.
- **Privileged.** `/opt/tools/rcb_ispatialgym.py` (`Session`): the simulator from the frozen start, every object's state,
  unlimited resets, the robot's cameras, `robot_spec`, stateless FK / IK, and `/app/goal.png`. Not given: the goal, any
  target, any success check, motion primitives or planners. The deliverable is `/app/output/trajectory.npz`.
- **Standard** (protocol `eai-standard/3.0`). `/app/goal.png`; action type `joint_position` (23, rows `dt` apart, a
  multiple of 1/30 s up to 0.5 s, at most 10 s per chunk); three RGB cameras (head `robot_r1:zed_link:Camera:0`, the goal
  image's camera, and two wrist cameras) with their calibration per frame; proprioception in the odometry frame (the
  robot's `base_link` at the start of the episode); `robot_spec`; stateless FK / IK. Not given: object poses, the world
  frame, resets, the success signal. The simulator runs at about 8 control steps per second of wall time.
- **Start-up.** A scene load takes 3-17 min (a cold Kit cache is the slow one); in standard mode it is on the agent's
  clock.

## Grading
Success is upstream's geometric success under settle-eval: on some control step, the task's BDDL goal (its relations,
what is open, what is held and what is not) and every measured target (`:measure`: an object's position and / or
orientation, a joint angle, a group's layout or the head camera's pose, within the scaled tolerances) have held on that
step and the 44 before it, and the named objects and the robot are at rest over those steps. The reward is 1 or 0. Each
task's README states its conditions and tolerances.

- **Privileged.** `tests/grade.py` checks the trajectory's shape and row count, then replays it once, open-loop, in a
  fresh process from the frozen start; the replay stops at the first success. A missing or malformed file scores 0; a
  replay that gives no result, times out or starts from a start that did not rebuild is an infrastructure error.
- **Standard.** The live episode is the verdict, judged by the service at every control step; nothing replays it. A
  success, once reached, stands. The frozen start is checked when the sidecar builds the scene, before the agent is
  served (the start-state hash of `facts.json`, else every object pose and robot joint within 2 mm / 0.02 rad); a
  mismatch is an infrastructure error (`instance_mismatch`). A simulator error raised by the agent's actions, or
  crashes all inside the agent's calls, score 0.

## Tasks
Upstream has 23 tasks; 12 are here (✅).

| family | task | the robot must | here |
|---|---|---|---|
| alignment | axial | push an object on a table until its long axis lines up with the table edges | ✅ |
| | vertical | push a tilted object hanging on a wall upright | ✅ |
| camera relocalization | obstructed | drive and set the trunk so that the head camera sees the goal image, around an obstacle | ✅ |
| | standard | the same without the obstacle | ⬜ |
| configuration matching | articulation open, small scale | open a small object (blender, carton) to the pictured angle | ✅ |
| | articulation close, small scale | close it | ⬜ |
| | articulation open / close, large scale | open or close a door or dishwasher, mostly with the base and trunk | ⬜ |
| | attachment | put a lid, cap or cork on its partner as pictured | ⬜ |
| | block design | arrange four blocks on a tray as pictured | ✅ |
| disembedding | (one) | find the pictured object among distractors and move it alone to the other tray | ⬜ |
| object relations | inside / next to / on top / touching / under, small scale | place an object so that it stands in the pictured relation to a partner on the same surface | ✅ (5) |
| | the same five, large scale | the same relation to a scene fixture (sink, bed, bookcase), with the base | ⬜ (5) |
| mental rotation | (one) | turn a held object in the hand to the pictured orientation | ✅ |
| object scaling | (one) | move a held object along the camera's axis until it looks as large as pictured | ✅ |

The selection:
- **One task per success rule.** Where two tasks share a BDDL goal and measured targets, one is kept: the obstructed
  camera relocalization (the standard one is the same without the obstacle); of an open / close pair the opening one;
  of a relation checked at two scales the small-scale task (tighter tolerances; at scene scale the partner is a fixed
  fixture reached with the base). 23 → 14.
- **Valid here.** Within a task, the first subtask in upstream's index (`metadata/instances.jsonl`) whose instance loads,
  does not succeed when the robot holds still for the whole budget, and replays to the same final state in fresh
  processes. Instance 0 of that subtask (the release has one per subtask); 11 of the 12 are in `house_single_floor`.
- **No answer in the agent's reach.** The privileged agent's simulator must load the start and nothing that scores it.
  Two tasks cannot: attachment (upstream's attach rule needs the pair of parts that join, which is the answer, to
  simulate at all) and disembedding (upstream declares the target alone and spawns it first, so the start tells it from
  the distractors). 14 → 12.

## Others
- **The privileged start names the task's objects.** The start-only BDDL problem the loader needs lists the objects the
  task is about (as BEHAVIOR-1K's do), and `instance.json` keeps upstream's load order. What is to be done with them (the
  relation, the pose, the angle) is only in the picture. In next to and touching the moved object starts close to its
  measured pose (inside the × 3 position tolerance), so the relation is most of those two tasks.
- **No fall rule.** Upstream ends an episode only on success or at its step budget. The R1Pro can tip over against an
  obstacle; the episode then runs on. Kept as upstream has it.
- **Where upstream keeps the answers.** The measured targets, the tolerances and the goal camera's pose are in
  upstream's instance files (`*-tro_state.json`); here they are in `goal.json`, on the scoring side only. The goal
  relation is in the BDDL problem, present only in the standard sidecar and the verifier. The demonstrations (the eval
  data's demos folder) are in no image and no task, and the agent's egress is the model APIs and package registries.
  Upstream's scripted demonstrator and instance generator are not in the public release.
