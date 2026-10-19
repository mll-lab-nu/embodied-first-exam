# iSpatialGym

Spatial intelligence on a mobile bimanual robot: the task is a picture. Each instance gives only a goal image, the head
camera's view once the task is done, and the robot has to make the scene look like it (an object's pose, a relation
between two objects, an articulation, its own viewpoint). No sentence names the objects. No benchmark in the set states
its goal this way; BEHAVIOR-1K runs the same robot in the same houses with goals in words.

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/ispatialgym -a codex -m openai/gpt-6-astra
```
Some images are not on a public registry: build them first ([Getting the images](#getting-the-images)).

## Getting the images

All iSpatialGym tasks (privileged and standard) need images that are not on a public registry: the iSpatialGym simulator
image, built on the BEHAVIOR-1K image (NVIDIA Isaac Sim 5.1 inside, which NVIDIA does not allow anyone to redistribute), and the licensed BEHAVIOR dataset on the host. Run every command from the repository root on a Linux x86_64 host with Docker (BuildKit), the NVIDIA Container Toolkit and an RTX-class NVIDIA GPU.

1. Licences: building accepts the NVIDIA Isaac Sim / Omniverse terms of the official `stanfordvl/behavior` image; the
   dataset step asks you to accept the BEHAVIOR Data Bundle licence (no redistribution). No account, login or token is
   needed: Docker Hub, github.com (iSpatialGym and its BEHAVIOR-1K fork, fetched by commit), pypi.org and the public
   Hugging Face dataset `behavior-1k/zipped-datasets` are all anonymous.
2. Build the BEHAVIOR-1K image first (iSpatialGym's Dockerfile starts `FROM` it), then iSpatialGym's (the files image is public: the task builds pull it):
   ```bash
   docker build -f images/behavior/Dockerfile -t ghcr.io/mll-lab-nu/efe-private:behavior-$(cat images/behavior/VERSION) .
   docker build -f images/ispatialgym/Dockerfile -t ghcr.io/mll-lab-nu/efe-private:ispatialgym-$(cat images/ispatialgym/VERSION) .
   ```
3. The dataset, `RCB_BEHAVIOR_DATA` (the same directory BEHAVIOR-1K's tasks use; skip if you have it): BEHAVIOR-1K's own
   downloader, in the behavior image, no GPU needed; it prints the licence and asks you to accept it:
   ```bash
   export RCB_BEHAVIOR_DATA=/path/to/behavior-data && mkdir -p "$RCB_BEHAVIOR_DATA"
   docker run --rm -it -e OMNIGIBSON_DATA_PATH=/data -v "$RCB_BEHAVIOR_DATA":/data \
     ghcr.io/mll-lab-nu/efe-private:behavior-$(cat images/behavior/VERSION) python -m omnigibson.utils.asset_utils \
     --download_omnigibson_robot_assets --download_behavior_1k_assets
   ```
4. Run (the tasks mount `$RCB_BEHAVIOR_DATA` read-only and refuse to start without it):
   ```bash
   harbor run -d embodied-first-exam@all -p tasks/ispatialgym -a codex -m openai/gpt-6-astra
   ```

| | |
|---|---|
| upstream | iSpatialGym's pre-release evaluation pipeline (`kmy17518/iSpatialGym`, MIT, `fddcf756`; [demo gallery](https://minyeongkim.com/ispatialgym/)), on its BEHAVIOR-1K fork (`kmy17518/BEHAVIOR-1K`, branch `ispatialgym-eval`, `6a619460`, its submodule) and its eval data (Hugging Face `kmy17518/ispatialgym-eval-data`, MIT, revision `v1.0`) |
| licence | iSpatialGym's code and eval data: MIT; BEHAVIOR-1K's code MIT, its dataset licensed (no redistribution, mounted at run time) |
| simulator | OmniGibson (the fork: 3.9 + the vector-env merge + iSpatialGym's object states) on Isaac Sim 5.1, CPU PhysX at 120 Hz |
| robot | R1Pro: holonomic base, 4-joint trunk, two 7-joint arms with parallel grippers; iSpatialGym's 23-D JoyLo action at 30 Hz; head and wrist cameras, 1080×1080 RGB |
| score | upstream's geometric success with its settle-eval on: the BDDL goal and every measured target within the `isg-v2` tolerances × 3 (`run_isg --mode policy`) at every one of the last 45 control steps, the measured objects and the robot at rest over them (`pose_settled`); within max(300, 2 × the demo's length) control steps |
| tasks | 12 in both modes: `tasks/ispatialgym/ispatialgym-<task>-i00-privileged` and `-standard` (`eai-standard/2.2`), one frozen instance per pair |
| image | `ghcr.io/mll-lab-nu/efe-private:ispatialgym-0.2.0` (`images/ispatialgym/`, BUILD_ONLY: Isaac Sim inside; both upstream repositories are fetched by commit) |
| oracle | none |

## Tasks: upstream's 23, ours ✅ (12)

| family | task | the robot must | ours | why not |
|---|---|---|---|---|
| alignment | axial | push an object on a table until its long axis lines up with the table edges | ✅ | |
| | vertical | push a tilted object hanging on a wall upright | ✅ | |
| camera relocalization | obstructed | drive and set the trunk so that the head camera sees the goal image, around an obstacle | ✅ | |
| | standard | the same without the obstacle | ⬜ | obstructed's goal |
| configuration matching | articulation open, small scale | open a small object (blender, carton) to the pictured angle, the other arm bracing it | ✅ | |
| | articulation close, small scale | close it | ⬜ | the closing twin |
| | articulation open / close, large scale | open or close a door or dishwasher, mostly with the base and trunk | ⬜ | the small-scale rule at scene scale |
| | attachment | put a lid, cap or cork on its partner as pictured | ⬜ | its attach rule needs the joining pair (the answer) in the agent's simulator |
| | block design | arrange four Kohs blocks so that their tops show the pictured 2×2 pattern | ✅ | |
| disembedding | (one) | find the pictured object among distractors and move it alone to the other tray | ⬜ | the start instance tells the target from the distractors |
| object relations | inside / next to / on top / touching / under, small scale | place an object so that it stands in the pictured relation to a partner on the same surface | ✅ (5) | |
| | the same five, large scale | the same relation to a scene fixture (sink, bed, bookcase), with the base | ⬜ (5) | the small-scale rule at scene scale |
| mental rotation | (one) | turn a held object in the hand to the pictured orientation | ✅ | |
| object scaling | (one) | move a held object along the camera's axis until it looks as large as pictured | ✅ | |

Why these (no model's results enter the choice):
- **One task per success rule.** A task whose BDDL goal and measured targets are another's keeps one: the obstructed
  camera relocalization (the standard one is it without the obstacle); of an open / close pair the opening twin, as in
  BiGym 2.0; of a relation checked at two scales the small-scale task (tighter tolerances; at scene scale the partner is a
  fixed fixture reached with the base, what BEHAVIOR-1K's tasks cover on the same robot and houses). 23 → 14.
- **Valid here.** Within a task, the first subtask in upstream's index (`metadata/instances.jsonl`) whose instance loads,
  does not succeed when the robot holds still for the whole budget, and replays to the same final state in fresh
  processes (`facts.json` of the task's instance). Every first subtask passed.
- **Instance 0** of that subtask (the release has one per subtask); 11 of the 12 are in `house_single_floor`.
- **Both modes without the answer in reach.** The privileged agent's simulator must load the start and nothing that
  scores it, and the same rows must give it the scoring side's states. Two tasks cannot: attachment (upstream's attach
  rule reads the pair of parts that join, which is the answer, to simulate at all) and disembedding (upstream declares the
  target alone and spawns it first, so the start tells it from the distractors). 14 → 12.

## Modes (PROTOCOL §3)
Both twins share one frozen instance, `instance.json`, byte-identical in the privileged `environment/` and `tests/` and
the standard `environment/sim/` (H.7): the scene template, the template keys the loader reads, and upstream's TRO with
only what rebuilds the start (object states, robot state, bindings, hinges, grasps), the scene's objects named without
upstream's role prefix (`target_*`, `partner_*`, …). Renaming moves the settled start of 3 of the 12 instances by at
most 5e-5 (m or rad; alignment_axial, block_design, touching) and none of the others, measured; both twins and the agent
run the renamed one. What scores it is
`goal.json` (docs/protocol/leakage.md §3): every key taken out of upstream's TRO and template_meta (the targets, the goal camera pose, the
variant), lifted against the real removal, copied only to the scoring side (`environment/sim/`,
`tests/`), restored there and checked against upstream's TRO by sha256 (a failed restore is a grader error). One success
rule: upstream's BDDL problem from the image (sha256 in `upstream.json`) and the policy tolerances × 3, in both.

| | standard (`eai-standard/2.2`) | privileged |
|---|---|---|
| agent gets | `/app/goal.png`; three RGB cameras with calibration; proprioception in the odometry frame; `robot_spec`; stateless FK / IK | the simulator in its container from the frozen start: every object's state, unlimited resets, the robot's cameras, `robot_spec`, stateless FK / IK; `/app/goal.png` |
| not given | object poses, the world frame, resets, the goal check | the goal, any target, any success check; motion primitives or planners |
| deliverable, grading | the episode the sidecar records, graded live: the sidecar's success at the episode's end, nothing replayed (Grading) | `/app/output/trajectory.npz` (≤ the step budget); two fresh replays in the verifier, both succeed and agree |

The privileged agent's image is `ghcr.io/mll-lab-nu/efe-private:ispatialgym-0.2.0` with a layer that removes, and the build then asserts gone: every BDDL
problem (goals), the docs (they preview the reference demonstrations; the fork's link the authors' pages), tests,
configs and README, the eval data's repository id and folder names and the project URLs (they locate the
demonstrations) and bytecode; upstream's public release ships no scripted expert, planner, sampler or task spec, and the
build fails if one is there (each privileged task's `environment/scrub/scrub.sh`; the names it looks for are read from the image, so
no task file names the eval data). It writes this task's start-only BDDL problem (objects and positive initial
atoms, one neutral goal atom) from the image's own copy. Upstream's success-check code stays in the image, as KinDER's and
BEHAVIOR-1K's do; with no goal, target or problem in the container it has nothing to check, and the tooling reports no
success. Measured: the same 300 rows give bit-identical start and final states in the agent's simulator and the
verifier's, for all 12 tasks.

## Grading (standard)
- **The live episode is the verdict.** The sidecar judges upstream's success under settle-eval at every control step the
  episode runs (`rcb_ispatialgym.Session.step`); the episode ends at the first step it holds, and `success` in
  `final.json` is that result (`episode.json`, merged by `finalize.sh`). The at-rest window is part of that predicate
  (the last 45 control steps of the live episode), so no hold is added after the agent's container stops; the rule is the
  privileged twin's, which its verifier judges on two fresh replays.
- **The frozen start** is checked when the sidecar builds the scene, before the agent is served (the start-state hash
  of `facts.json`, else every object pose and robot joint within 2 mm / 0.02 rad); a mismatch gives up as
  `instance_mismatch` (`infra_error = 1`). On a resume the rebuilt start is checked again.
- **Video**: recorded live (`/out/live.mp4`): the head camera's frame that every control step renders anyway for the
  agent's observations, every third step (10 fps, 540 px), copied in the control loop and encoded by a thread
  (`rcb_ispatialgym.LiveVideo`; a full queue or an unreadable frame drops that frame, counted, rather than wait or stop;
  closing is bounded to 4 min). A resume records it anew from the start, as
  it replays the journal. The service closes it when the collect hook ends the episode; a failed recording loses only
  the video. Only when `live.mp4` is missing or does not play, `finalize.sh` runs ONE video-only render
  (`rcb_ispatialgym.py replay --video`, `replay.mp4`) after the verdict, whose success and hash are not read; the
  collect hook's bound covers it (the end, up to 1 h, + a scene load and the whole step budget + 10 min).
- **Infrastructure** (`infra_error = 1`): no or unfinalized `final.json`, the service never ended the episode (no
  `episode.json`; one the newest service start dumped before failing to exit in time is still the verdict,
  `end_timed_out`; a resume whose episode goes on deletes one left by a call the crash lost), a give-up
  after crashes not all inside the agent's calls (`sim_crashed`, `resume_failed`), `instance_mismatch`. A crash inside the
  agent's calls (`sim_crashed_on_call`) and a simulator error raised by its actions (`error`) score 0.

## Where upstream keeps the answers

| what | where upstream has it | here |
|---|---|---|
| measured targets and tolerances, the goal camera's world pose | the instance file (`*-tro_state.json`: `pose_targets`, `goal_observation`) | `goal.json`, scoring side only; the agent sees the tolerances |
| the goal relation and roles | the BDDL problem (`:goal`, `:variant`, comments, negative `:init` atoms), the objects' names | the problem only in the standard sidecar and the verifier; names without roles in `instance.json` |
| demonstrations | the eval data's demos folder (Hugging Face: actions per step) | in no image and no task; its repository id and folder names are removed from the privileged agent's image (`scrub.sh`); the agent's egress is the model APIs and package registries |
| the scripted demonstrator and its per-instance plans | upstream's internal release only (`ispatialgym/oracle/`, `*.oracle.json`); the public release (`fddcf756`) ships neither | in no image: `scrub.sh` fails the privileged build if any is there; the standard agent's container is the eai-standard client |
| the instance generator, its specs and seeds | upstream's internal release only (`ispatialgym/sampling/`, `assets/task_specs/`); not in the public release | in no image: `scrub.sh` fails the privileged build if any is there |

## Run
```bash
export RCB_BEHAVIOR_DATA=/path/to/behavior-data   # omnigibson-robot-assets/, behavior-1k-assets/ (3.9.0), omnigibson.key; mounted at /bdata
harbor run -p tasks/ispatialgym/ispatialgym-mental-rotation-i00-standard -a codex -m openai/gpt-6-astra --env-file .env
harbor run -p tasks/ispatialgym/ispatialgym-mental-rotation-i00-standard -a nop      # scores 0
harbor run -p tasks/ispatialgym/ispatialgym-mental-rotation-i00-privileged -a codex -m openai/gpt-6-astra --env-file .env
```
The dataset is the BEHAVIOR Data Bundle (`omnigibson.utils.asset_utils`: `download_omnigibson_robot_assets()`,
`download_behavior_1k_assets(accept_license=True)`), the same one BEHAVIOR-1K's tasks mount. Build the image as
`images/ispatialgym/BUILD_ONLY` says. The task directories are the deliverable; the tooling that built them is kept
outside this repository. The frozen instances are kept in the task directories only: the standard twin's
`environment/sim/` (`instance.json`, `goal.json`, `facts.json`, `upstream.json`). The goal images (upstream's, unchanged,
MIT) are in the public Hugging Face dataset `MLL-Lab/embodied-first-exam-public` (`ispatialgym/`), pinned in
`images/ispatialgym-goals-files/FILES.json`; the tasks copy each to `/app/goal.png` from that files-only image.

## Positive examples (oracle none, PROTOCOL §4)
Upstream's recorded demonstration of each instance (the eval data's `-demo.hdf5`, `data/demo_0/action`, unchanged), handed
in as the privileged deliverable and graded by the task's own verifier image (two fresh replays, no network) on an L40S:
12/12 score 1, deterministic, with a replay video; the replay succeeds at upstream's first settled step + 1
or earlier (the × 3 tolerances), e.g. mental_rotation 130 of 136 rows, block_design 3501 of 4149. One Isaac process of
the verifier held up to 17 GiB of GPU memory on that card (texture streaming takes what the card has; 3.5-4.6 GiB on an
RTX 4090 with four processes at once).

## Known issues
- **The privileged start names the task's objects.** The start-only BDDL problem the loader needs lists the objects the
  task is about (as BEHAVIOR-1K's do), and `instance.json` keeps upstream's load order, in which they come last before the
  robot; reordering it changes the settled start. What is to be done with them (the relation, the pose, the angle) is
  only in the picture; the instruction claims no more than that. In next to and touching the moved object starts close to
  its measured pose (inside the × 3 position tolerance), so the relation is most of those two tasks.
- **No fall rule.** Upstream ends an episode only on success or at its step budget. The R1Pro can tip over against an
  obstacle (seen in camera relocalization), and in one run a toppled robot driven on fell through the floor; the episode
  then runs on to its budget. Kept as upstream has it.
- **Settle-eval on, not upstream's policy default.** With settle-eval off (`run_isg --mode policy`: the first step the
  goal holds), the privileged adversarial trial scored 1 on mental_rotation without a leak, by a blind sweep of the held
  knife's poses (8 steps each), and a generic 300-row determinism probe succeeded on alignment_vertical at step 61. Upstream's
  own settle-eval (the same rule held over 45 steps, everything at rest) scores both 0, so both modes use it.
- **Sim start-up is on the agent's clock**: 3-17 min measured per scene load (a cold Kit cache is the slow one), inside the hour.
- **GPU memory.** One trial's Isaac process takes 4-7 GiB of GPU memory; three trials beside other work on one 24 GB card
  ran out of it at start-up (an infrastructure failure, `infra_error = 1`). The service exits non-zero on a start-up error so
  that compose restarts it (Isaac's Kit otherwise exits 0).
