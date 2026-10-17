# iSpatialGym

Spatial intelligence on a mobile bimanual robot: the task is a picture. Each instance gives only a goal image, the head
camera's view once the task is done, and the robot has to make the scene look like it (an object's pose, a relation
between two objects, an articulation, its own viewpoint). No sentence names the objects. No benchmark in the set states
its goal this way; BEHAVIOR-1K runs the same robot in the same houses with goals in words.

| | |
|---|---|
| upstream | iSpatialGym's pre-release evaluation pipeline (`kmy17518/iSpatialGym`, MIT, `fddcf756`; [demo gallery](https://minyeongkim.com/ispatialgym/)), on its BEHAVIOR-1K fork (`kmy17518/BEHAVIOR-1K`, branch `ispatialgym-eval`, `6a619460`, its submodule) and its eval data (Hugging Face `kmy17518/ispatialgym-eval-data`, MIT, revision `v1.0`) |
| licence | iSpatialGym's code and eval data: MIT; BEHAVIOR-1K's code MIT, its dataset licensed (no redistribution, mounted at run time) |
| simulator | OmniGibson (the fork: 3.9 + the vector-env merge + iSpatialGym's object states) on Isaac Sim 5.1, CPU PhysX at 120 Hz |
| robot | R1Pro: holonomic base, 4-joint trunk, two 7-joint arms with parallel grippers; iSpatialGym's 23-D JoyLo action at 30 Hz; head and wrist cameras, 1080×1080 RGB |
| score | upstream's geometric success with its settle-eval on: the BDDL goal and every measured target within the `isg-v2` tolerances × 3 (`run_isg --mode policy`) at every one of the last 45 control steps, the measured objects and the robot at rest over them (`pose_settled`); within max(300, 2 × the demo's length) control steps |
| tasks | 12 in both modes: `tasks/ispatialgym-<task>-i00-privileged` and `-standard` (`eai-standard/2.2`), one frozen instance per pair |
| image | `ghcr.io/mll-lab-nu/eai-ispatialgym:0.2.0` (`images/ispatialgym/`, BUILD_ONLY: Isaac Sim inside; both upstream repositories are fetched by commit) |
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

Why these (no model's results enter the choice; `scripts/ispatialgym/subset.toml`):
- **One task per success rule.** A task whose BDDL goal and measured targets are another's keeps one: the obstructed
  camera relocalization (the standard one is it without the obstacle); of an open / close pair the opening twin, as in
  BiGym 2.0; of a relation checked at two scales the small-scale task (tighter tolerances; at scene scale the partner is a
  fixed fixture reached with the base, what BEHAVIOR-1K's tasks cover on the same robot and houses). 23 → 14.
- **Valid here.** Within a task, the first subtask in upstream's index (`metadata/instances.jsonl`) whose instance loads,
  does not succeed when the robot holds still for the whole budget, and replays to the same final state in fresh
  processes (`scripts/ispatialgym/instances/<task>/facts.json`). Every first subtask passed.
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
`goal.json` (LEAKAGE §3): every key taken out of upstream's TRO and template_meta (the targets, the goal camera pose, the
variant), lifted by `mk_tasks.py instances` against the real removal, copied only to the scoring side (`environment/sim/`,
`tests/`), restored there and checked against upstream's TRO by sha256 (a failed restore is a grader error). One success
rule: upstream's BDDL problem from the image (sha256 in `upstream.json`) and the policy tolerances × 3, in both.

| | standard (`eai-standard/2.2`) | privileged |
|---|---|---|
| agent gets | `/app/goal.png`; three RGB cameras with calibration; proprioception in the odometry frame; `robot_spec`; stateless FK / IK | the simulator in its container from the frozen start: every object's state, unlimited resets, the robot's cameras, `robot_spec`, stateless FK / IK; `/app/goal.png` |
| not given | object poses, the world frame, resets, the goal check | the goal, any target, any success check; motion primitives or planners |
| deliverable, grading | the episode the sidecar records; live ∧ two fresh replays ∧ deterministic, in the sidecar | `/app/output/trajectory.npz` (≤ the step budget); two fresh replays in the verifier, both succeed and agree |

The privileged agent's image is eai-ispatialgym with a layer that removes, and the build then asserts gone: every BDDL
problem (goals), the docs (they preview the reference demonstrations; the fork's link the authors' pages), tests,
configs and README, the eval data's repository id and folder names and the project URLs (they locate the
demonstrations) and bytecode; upstream's public release ships no scripted expert, planner, sampler or task spec, and the
build fails if one is there (`scripts/ispatialgym/shared/scrub.sh`; the names it looks for are read from the image, so
no task file names the eval data). It writes this task's start-only BDDL problem (objects and positive initial
atoms, one neutral goal atom) from the image's own copy. Upstream's success-check code stays in the image, as KinDER's and
BEHAVIOR-1K's do; with no goal, target or problem in the container it has nothing to check, and the tooling reports no
success. Measured: the same 300 rows give bit-identical start and final states in the agent's simulator and the
verifier's, for all 12 tasks.

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
harbor run -p tasks/ispatialgym-mental-rotation-i00-standard -a codex -m openai/gpt-6-luna --env-file .env
harbor run -p tasks/ispatialgym-mental-rotation-i00-standard -a nop      # scores 0
harbor run -p tasks/ispatialgym-mental-rotation-i00-privileged -a codex -m openai/gpt-6-luna --env-file .env
```
The dataset is the BEHAVIOR Data Bundle (`omnigibson.utils.asset_utils`: `download_omnigibson_robot_assets()`,
`download_behavior_1k_assets(accept_license=True)`), the same one BEHAVIOR-1K's tasks mount. Build the image as
`images/ispatialgym/BUILD_ONLY` says. Regenerate the tasks: `python3 scripts/ispatialgym/mk_tasks.py render`
(`instances` splits the picked instances of upstream's eval data into `instance.json` and `goal.json`; `measure --task T` writes `facts.json`, on a GPU).

## Positive examples (oracle none, PROTOCOL §4)
Upstream's recorded demonstration of each instance (the eval data's `-demo.hdf5`, `data/demo_0/action`, unchanged), handed
in as the privileged deliverable and graded by the task's own verifier image (two fresh replays, no network) on an L40S,
2026-10-17: 12/12 score 1, deterministic, with a replay video; the replay succeeds at upstream's first settled step + 1
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
  own settle-eval (the same rule held over 45 steps, everything at rest) scores both 0, so both modes use it (2026-10-16).
- **Sim start-up is on the agent's clock**: 3-17 min measured per scene load (a cold Kit cache is the slow one), inside the hour.
- **GPU memory.** One trial's Isaac process takes 4-7 GiB of GPU memory; three trials beside other work on one 24 GB card
  ran out of it at start-up (an infrastructure failure, `infra_error = 1`). The service exits non-zero on a start-up error so
  that compose restarts it (Isaac's Kit otherwise exits 0).
