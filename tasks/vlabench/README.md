# VLABench

## Overview
[VLABench](https://github.com/OpenMOSS/VLABench) (Zhang et al., 2024, arXiv 2412.18194) is a language-conditioned
manipulation benchmark for a Franka Panda arm at a table, on MuJoCo and dm_control. Here 36 of its native tasks run,
each on one frozen scene instance, in the privileged and the standard mode: 72 task directories.

| | |
|---|---|
| upstream | VLABench @ `cf588fe60c0c7282174fe979f5913170cfe69017` (MIT); assets `lerobot/vlabench-assets` @ `08d7a44`; MuJoCo 3.2.2, dm_control 1.0.22 |
| tasks | `tasks/vlabench/vlabench-<task>-i00-privileged` and `tasks/vlabench/vlabench-<task>-i00-standard` |
| metadata | `simulator = "vlabench"`, `robot = "franka-panda"`, `family = "vlabench/<task>"`, `oracle = "full"` |
| image | built by each task from `images/vlabench/Dockerfile` (stage `vlabench-base`), build cache `ghcr.io/mll-lab-nu/efe-private:vlabench-0.2.0`; about 15 GB, 12 GB of it assets |
| GPU | none: CPU physics and CPU (OSMesa) rendering |

```bash
harbor run -d embodied-first-exam@all -p tasks/vlabench -a codex -m <model>
```
The first task to run on a machine builds the image (Others); every later task reuses it.

## Upstream and license
[VLABench](https://github.com/OpenMOSS/VLABench) at commit `cf588fe60c0c7282174fe979f5913170cfe69017`: MIT License.
The scene and object assets are the Hugging Face dataset
[lerobot/vlabench-assets](https://huggingface.co/datasets/lerobot/vlabench-assets) at `08d7a44`, which states no
licence. They are downloaded when the image is built (checked with `git lfs fsck`) and never redistributed: the image is
not published, and each task builds it. The rrt-algorithms library is pinned at `14e4796`. MuJoCo and dm_control:
Apache-2.0. No non-commercial terms apply.

## Changes from upstream
- **Scope.** VLABench @ `cf588fe` has 96 native tasks. A task is in when it has a reference solution that is re-verified
  on its frozen instance and an instruction that identifies the task: 36 tasks. Left out: 41 tasks whose reference does
  not reach the task's success on the frozen instance, 13 whose scene does not build or does not reset bit-exactly, 3
  whose reference ends in failure (complex_seesaw_use, hammer_loose_nail, set_dining_table), and 3 that duplicate
  another task or carry VLABench's unfilled instruction template (select_fruit_semantic, select_book_semantic,
  set_study_table).
- **Frozen instances.** Each task's `instance.json` is VLABench's own episode configuration (scene, objects, conditions,
  instruction) and its seed, plus the hashes of the compiled model and of the initial state. `vlb_tool.Session`
  rebuilds the scene with every random source seeded and refuses to run if either hash differs. The privileged task
  keeps it in `environment/` and `tests/`, the standard task in `environment/sim/`; the three copies are byte-identical
  (`check-instance-copies.sh`).
- **Success predicates unchanged.** Success is VLABench's own termination condition (`task.should_terminate_episode`:
  the instance's conditions, plus the task class's own check where it has one, e.g. the microwave door and start button
  of heat_food). The predicates keep their looseness: containment tests one point of the object (its origin) against a
  box or a disc of the container's annotated sites, and `order` (book_rearrange, play_math_game) sorts no axis, since
  VLABench's loader passes its `axis` list through the entity lookup: it only requires each entity's x, y and z to be
  less than 0.1 m larger than the next one's. Each task README states its predicate exactly.
- **Instructions say what is graded.** Where VLABench's own instruction does not say what its check requires, the task's
  instruction restates it (24 tasks): for example the `*_qa` and `select_painting` answers are button presses,
  `select_billiards*` count only VLABench's target pocket, and `texas_holdem` names the five cards VLABench's ranking
  picks. VLABench's own wording stays in the instance (`s.state()["instruction"]` in privileged mode).
- **No experts.** `images/vlabench/strip_experts.py` removes every `get_expert_skill_sequence`, `configs/task2code.json`,
  the evaluation code and configs, and the source tree's `.git` and `scripts/`. VLABench's general skills and its success
  predicates stay.
- **Episode lengths.** Privileged trajectories have at most 4000 control steps; standard episodes end after 9,000
  control steps, so that the video's re-run of an episode fits the verifier's collect hook.
- **Agent-ended standard episodes.** In standard mode the termination condition no longer ends the episode:
  `vlb_tool.Session` replaces `task.should_terminate_episode` with a never-terminating one after the start-state check
  (so dm_control does not reset the scene) and keeps the original as the success check.
- **Added.** The tooling `vlb_tool.py` and the graders (`embodied_first_exam/benchmarks/vlabench/`), and the standard
  mode's sim service.

## Interface
- **Actions.** VLABench's own: 9 absolute position targets per control step (0.1 s, 100 physics steps), the 7 arm joints
  (rad) and the 2 fingers (m, 0 closed to 0.04 open), clipped into the actuators' bounds. VLABench's model sets no arm
  joint limits; the Panda's documented limits are given as facts.
- **World frame.** Metres; the robot's base at (0, -0.4, 0.78) facing +y (VLABench's default; (0, -0.4, 0.6) for
  `select_billiards*` and (0, -0.7, 0.7) for `find_unseen_object`, from VLABench's per-series robot configuration): x to
  the robot's right, y forward, z up; quaternions w x y z. Stated in both modes' instructions and in `/spec` (`frames`).
- **Privileged.** `/opt/tools/vlb_tool.py` (`Session`): every entity's pose, grasp keypoints and place points, the
  robot's state, VLABench's general skills (pick, place, pull, press, ...) as planning primitives, inverse kinematics,
  cameras, unlimited resets, self-replay. The deliverable is `/app/output/trajectory.npz` (`actions`, (T, 9)).
- **Standard** (protocol `eai-standard/3.0`). `joint_position` (9); four cameras (`forward`, `left`, `right` fixed,
  `wrist` on the hand), RGB 320×320, depth on request, intrinsics and pose in `/spec`; proprioception: joint angles and
  velocities, finger positions, the hand's pose and the last command. No object poses, no task conditions, no success
  signal. One episode, no reset (the reset budget is pinned to 0 in the compose file). `server.py` is VLABench's
  adapter: cameras, proprioception, clipping into the actuators' bounds, holding the last targets during a hold chunk,
  the frozen start's hash, and the video's re-run.
- **Egress.** VLABench's experts are public upstream, so the agent reaches the model APIs and the package registries
  only (`[agent] network_mode = "allowlist"`).

## Grading
- **The predicate.** VLABench checks its termination condition after every control step. A task's condition is the
  conjunction of the instance's conditions (`contain`, `not_contain`, `order`, `above`, `pour`, `is_grasped`, `lift`,
  `joint_in_range`, `press_button`) and the task class's own check where it has one (heat_food, take_out_cool_drink,
  hammer_nail_and_hang_picture, texas_holdem).
- **Privileged: one replay.** `tests/grade.py` replays `/app/output/trajectory.npz` once, in a fresh process without
  network, from the verifier's own copy of the instance. VLABench ends the episode at the first control step at which
  the condition holds, so the trajectory passes when that step is its last row; a row after it makes the trajectory
  invalid. A missing or malformed file is the agent's 0; a replay that fails with an error, runs over 3600 s or finds a
  scene that does not rebuild as recorded is `grader_error = 1`.
- **Standard: the live episode.** Nothing is replayed. The episode ends at `/finish`, after 9,000 control steps
  (`step_limit`), at the end of the session or on a simulator error, and is judged on the state it ends in
  (`end_judgement = "state"`). Five tasks are judged on events instead (`end_judgement = "events"`: friction_qa,
  magnetism_qa, reflection_qa, select_painting, heat_food): their condition holds only while a button is held down, so
  the episode passes once the condition has held after any one control step, as their privileged task counts it. A
  simulator error raised by the agent's call is its 0. The scene is checked against the frozen instance before the agent
  is served (`instance_mismatch`, an infrastructure error).
- The video is one render pass over the graded trajectory after the verdict; it never changes the verdict.

## Tasks
36 tasks, each with one privileged and one standard directory (`i00`, instance seed 0).

| family | condition |
|---|---|
| `add_condiment` | the BBQ sauce bottle over the pan (origin height and pan radius) and tipped, its top below its bottom |
| `book_rearrange` | three books inside the shelf's box, ordered along +x by century, with bounded y / z offsets |
| `find_unseen_object` | the apple outside the cabinet's box |
| `friction_qa` | the button in front of the slowest-sliding object pressed (events) |
| `hammer_nail_and_hang_picture` | the nail's slide joint at 0.05 to 0.08 m, and the painting's grasp point once within 5 cm of the nail |
| `heat_food` | the food inside the microwave's box, the door closed and the start button in contact, together (events) |
| `insert_bloom_flower` | the tulip inside the vase's box |
| `insert_flower` | the rose inside the vase's box |
| `magnetism_qa` | the button in front of the magnetic object pressed (events) |
| `play_math_game` | the cubes `4` and `0` on the placemat, in that order along +x |
| `put_box_on_painting` | the box on the named painting's footprint |
| `reflection_qa` | the button in front of the most reflective mirror pressed (events) |
| `select_billiards` | the striped 14 ball in the target pocket (middle, robot's right) |
| `select_billiards_common_sense` | the black snooker ball in the target pocket (middle, robot's right) |
| `select_billiards_spatial` | the striped 14 ball in the target pocket (corner, robot's right, behind it) |
| `select_book_spatial` | the second book on the top shelf outside the shelf's box |
| `select_chemistry_tube` | the CuCl2 tube outside the stand's box |
| `select_chemistry_tube_common_sense` | the KMnO4 tube outside the stand's box |
| `select_chemistry_tube_semantic` | the KMnO4 tube outside the stand's box |
| `select_chemistry_tube_spatial` | the fifth tube of the near row (KMnO4) outside the stand's box |
| `select_drink` | the juice outside the fridge's box |
| `select_fruit` | the banana on the plate (radius, 0 to 10 cm above it) |
| `select_fruit_common_sense` | the pear on the plate (radius, 0 to 10 cm above it) |
| `select_mahjong` | the 6 sou tile on the placemat |
| `select_mahjong_semantic` | the 9 man tile on the placemat |
| `select_mahjong_spatial` | the seventh tile from the left (2 sou) on the placemat |
| `select_nth_largest_poker` | the lowest card touched by a finger and at least 0.9 m high |
| `select_painting` | the button in front of the ukiyo-e painting pressed (events) |
| `select_poker` | the ace of hearts touched by a finger and at least 0.9 m high |
| `select_poker_semantic` | the six of spades touched by a finger and at least 0.9 m high |
| `select_poker_spatial` | the fourth card from the left (six of spades) touched by a finger and at least 0.9 m high |
| `select_specific_type_book` | the history book outside the shelf's box |
| `select_toy` | the Mickey Mouse toy inside the gift box's box |
| `select_unique_type_mahjong` | the only sou tile (8 sou) on the placemat |
| `take_out_cool_drink` | the juice from the small fridge outside its box, and the fridge door closed |
| `texas_holdem` | the five cards of VLABench's first straight (6 to 10) on the placemat |

- **Reference solutions.** Every task has `oracle = "full"`: a recorded trajectory of control steps on its instance
  (`solution/oracle.npy`, the same file in both modes), re-verified to end with the task's success at its last step;
  the standard task's `solution/` submits it through the client.

## Others
- **Before running.** Docker with BuildKit and Compose v2 (Docker Engine 29 refuses a buildx plugin older than 0.13).
  About 40 GB free in Docker's data root for the first build (about 22 GB when the prebuilt layers are pulled). The
  first build fetches Debian packages (snapshot.debian.org), PyPI wheels, two GitHub repositories and the Hugging Face
  dataset (about 12 GB, anonymous): 5 to 20 minutes on a fast connection; the task allows 3600 s.
- **The image.** Every task's Dockerfiles (privileged: `environment/` and `tests/`; standard: `environment/sim/`) start
  with the recipe `images/vlabench/Dockerfile` as the stage `vlabench-base`, and compose `build.cache_from` names
  `ghcr.io/mll-lab-nu/efe-private:vlabench-0.2.0`, the same recipe prebuilt with BuildKit's inline cache. A runner that
  can pull it (members of the mll-lab-nu organization) takes its layers; any other runner gets a warning that the cache
  cannot be read and builds the layers from public sources. Both give the same image. The recipe pins Python 3.10.18 by
  digest, Debian packages from snapshot.debian.org at 2026-10-02 00:00 UTC, pip (`requirements.txt`, from the public
  files image `efe:vlabench-build-files`), VLABench, rrt-algorithms and the assets at fixed commits.
  `images/vlabench/build_local.sh` builds the same recipe from an assets checkout already on disk.
- **Rebuilding the cache** (maintainers; `images/vlabench/BUILD_ONLY`):
  ```bash
  docker build --build-arg BUILDKIT_INLINE_CACHE=1 \
      -t ghcr.io/mll-lab-nu/efe-private:vlabench-$(cat images/vlabench/VERSION) images/vlabench
  docker push ghcr.io/mll-lab-nu/efe-private:vlabench-$(cat images/vlabench/VERSION)
  ```
  A change to the recipe is a new `VERSION` and a new tag in every task's `build.cache_from`; `normalize` copies the
  recipe into the tasks' Dockerfiles.
- **Physics changes show.** The instance hashes are checked on every load, so a build whose physics differs shows up
  as a grader or infrastructure error, never as a silent change.
