# RoboDojo

## Overview

The simulation part of RoboDojo's sim-and-real benchmark for generalist manipulation policies: two ARX X5 arms at a
table, in Isaac Sim. Every task of RoboDojo's simulation benchmark is here: its 42 tasks over five capability
dimensions and the 12 `_random` variants of the Generalization tasks, 54 families. Each family has one frozen instance
in two modes: 108 task directories, `tasks/robodojo/robodojo-<family>-i00-privileged` and `-standard`.

| | |
|---|---|
| upstream | [RoboDojo](https://github.com/RoboDojo-Benchmark/RoboDojo) (Chen et al., 2026) at `cb2a37d`, on its Isaac Lab 2.3 fork (`afca7b0`) and Isaac Sim 5.1.0, with its cuRobo fork (`d17b54c`) for IK |
| simulator | Isaac Sim 5.1, GPU PhysX (RoboDojo forces GPU dynamics for its cloth and liquids), RTX rendering |
| robot | two ARX X5 arms, 6 joints each, parallel two-finger grippers; RoboDojo's 14-D joint action at 25 Hz |
| score | RoboDojo's own reward manager for the task: its check stages, run after every action |
| instance | RoboDojo's own evaluation layout `Assets/Eval_Layout/RoboDojo/arx_x5/0/<task>_0.json` (seed 0) |
| image | built from public sources by every task (`images/robodojo/`, about 75 GB with RoboDojo's 41 GB of assets) |

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/robodojo -a codex -m openai/gpt-6-astra
```
The first task builds the simulator image (below); later tasks reuse it from Docker's build cache.

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | RoboDojo's evaluator environment through `rcb_robodojo.py`: object poses, the checks, IK, replay | unlimited | its `trajectory.npz`, replayed in up to 3 fresh processes, any success counting |
| standard | the three cameras and both arms' proprioception, through `rcb_client.py`; no object poses, no success signal | 0 | the episode as it ran (live; nothing replayed) |

### Before you run

- **Licence.** The image contains NVIDIA Isaac Sim 5.1 / Omniverse Kit, the Isaac stack's wheels from
  pypi.nvidia.com, and cuRobo. Building and running it accepts the
  [NVIDIA Isaac Sim / Omniverse licence](https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html),
  NVIDIA's terms for those wheels and NVIDIA's cuRobo licence (the recipe sets `OMNI_KIT_ACCEPT_EULA=YES`). Read them
  before your first run. No account, login or token is needed.
- **GPU and driver.** Linux x86_64, Docker with BuildKit and the NVIDIA Container Toolkit, an RTX-class NVIDIA GPU
  (Isaac renders with RTX even headless; RoboDojo runs PhysX on the GPU) with a driver Isaac Sim 5.1 supports (checked
  on an RTX 4090, driver 580.x), about 5-10 GB of GPU memory per Isaac process. Isaac hangs instead of exiting when
  the GPU runs out of memory, so a shared GPU runs few tasks at once.
- **Disk.** About 150 GB free for the first build.
- **Data.** RoboDojo's assets (Hugging Face dataset `RoboDojo-Benchmark/RoboDojo`, `Assets/` at a pinned revision,
  15365 files, about 41 GB) are downloaded by the image build itself, anonymously through the dataset's git LFS.
  Nothing to download by hand or mount.
- **First build.** NVIDIA does not allow Isaac Sim to be redistributed, so the image is not on a public registry. The
  first task builds it with Docker from public sources: about 30-90 min, most of it the 41 GB download, with network
  access to github.com, snapshot.ubuntu.com, pypi.org, download.pytorch.org, pypi.nvidia.com, huggingface.co (and its
  LFS storage), NVIDIA's extension registry and its asset bucket. Every task's Dockerfile starts with that recipe, so
  the build runs once per Docker host. Maintainers who can pull `ghcr.io/mll-lab-nu/efe-private:robodojo-0.2.1` get
  its layers instead (compose `build.cache_from`). To build the image ahead of a run, run one task with `-a nop`
  (reward 0).

## Upstream and license

- Upstream: RoboDojo, [RoboDojo-Benchmark/RoboDojo](https://github.com/RoboDojo-Benchmark/RoboDojo) at `cb2a37d`, MIT
  License.
- Assets: Hugging Face `RoboDojo-Benchmark/RoboDojo`, Apache License 2.0.
- RoboDojo's Isaac Lab fork: BSD 3-Clause License. RoboDojo's cuRobo fork: NVIDIA's cuRobo licence.
- Isaac Sim 5.1 and its wheels: NVIDIA proprietary, no redistribution. The image is therefore build-only
  (`images/robodojo/BUILD_ONLY` has the licences, the pinned inputs and the check of a build). No non-commercial terms
  apply to RoboDojo's own code and assets.

## Changes from upstream

- RoboDojo's reward manager for each task is unchanged (one exception, `hang_mugs(_random)`, below): its
  `run_reward()` check list, registered at the start of every episode as RoboDojo's evaluator does it, and evaluated
  after every action. Stages count in order, at most one
  per action; a passed stage is popped and not checked again; a failed check ends the episode as a failure.
- `Session` builds RoboDojo's own evaluator environment (`src/eval_client/eval_env.py`: one env, the policy-server
  client replaced by a stub) and resets it onto the frozen layout exactly as RoboDojo's evaluator starts an episode.
- Each instance's `instance.json` (`environment/sim/instance.json`) holds the evaluation layout verbatim (with its
  sha256), the state hash after RoboDojo's reset, RoboDojo's language instruction for the layout, and the fields
  `physics` and `determinism`.
- `make_toast` runs with PhysX enhanced determinism (RoboDojo's own sim setting, off by default upstream): one of
  three fresh resets differed without it. Its instance records `"physics": {"enable_enhanced_determinism": true}`, and
  every session, the service and the verifier use it.
- Standard episodes are agent-ended. RoboDojo's evaluator ends an episode at the first action where the reward
  reaches 1, or after the task's `step_lim` actions. Here the agent sees no success signal, passing the checks does not
  end the episode, and the episode ends at `/finish`, after `step_lim` actions, at the end of the agent's time, or at a
  failed check (0). It is judged when it ends, by the task's class in `rcb_robodojo.py` `END_JUDGEMENT`:
  - **end** (47 tasks): the staged reward is 1, and the last check stage, checked again with RoboDojo's own function
    after every action once it has passed, still holds after the last action. The earlier stages of an ordered task
    count as they happened.
  - **history** (7 tasks: `play_Xylophone`, `press_by_number`, the three pouring tasks, the two folding tasks): the
    goal is a sequence of moments or is judged at a trigger, so RoboDojo's verdict stands as the episode ran.
- `hang_mugs(_random)`: RoboDojo's `is_axis_aligned` compares the mug's handle frame with the rack's first hanging
  point (arm 0), while its distance check accepts the handle at any of the six arms, so a mug hung on another arm
  failed. `rcb_robodojo.py` patches `Func_Parser.is_axis_aligned` when it builds the env: when both objects have
  functional points and the rack's has several frames, the frame nearest to the mug's point is compared. Every other
  call is RoboDojo's own.
- Privileged mode applies no step limit. A technical cap ends an episode after 15,000 actions (10 min of simulated
  time; reason `step_guard`), the most a trajectory may hold.
- The instructions state RoboDojo's checks in plain physical terms, without changing them. Where RoboDojo's own text
  misleads, the instruction follows the check:
  - `sort_nesting_dolls_by_size(_random)`: the config's comments call index mod 5 = 4 the largest doll; the dolls'
    measured sizes say it is the smallest.
  - `swap_blocks`: the button rests at about 0.79 of its travel, below the 0.9 / 0.95 its stages and press counter
    need.
  - `pack_objects_into_box(_random)`: the check reads the car, toothbrush and hammer through an asset frame (the
    'checkpoint' point) and the shoe through its body frame, with opposite signs in code. Physically all four want their
    front end to the left (car: the end that points right at the start in the non-random layout; brush head, hammer
    head, shoe toe).

## Interface

**Privileged.** `rcb_robodojo.py`: `Session(task, instance=...)`. Action: RoboDojo's 14-D joint action
`[left joint1..6, left gripper, right joint1..6, right gripper]` at 25 Hz (physics dt 4 ms, 10 physics steps per
action, RoboDojo's controller interpolating to the targets). Grippers are RoboDojo's normalised command (1 open, 0
closed). Helpers: hold, joint moves, gripper ramps, RoboDojo's cuRobo IK (`ik`, `move_ee`); object poses and bounding
boxes; the three cameras (`cam_head` static, `cam_left_wrist`, `cam_right_wrist`, 640×480, optional z-depth);
proprioception; numpy FK/IK of both arms from the X5 URDF; recording, a fresh-process `replay` CLI, video. A reset
right after a reset changes nothing, so the first episode in a process is exactly the grader's. After actions,
RoboDojo's reset settles the scene again from where it is: same layout and start, not bit for bit the same state.
A `s.reset()` in a long-lived process is not always reliable after an articulated object moved ("articulation not
found", or "All scene Unstable Error"); a fresh process, as the verifier uses, always builds the frozen start.

**Standard.** The `sim` sidecar serves the robot through `rcb_client.py` and the `efe-robot` MCP tools (wire
protocol `eai-standard/3.0`).
- Actions: `joint_position` (14 values: RoboDojo's action, rows `dt` apart, a multiple of 1/25 s) and `ee_pose` (16
  values: both arms' link6 targets and gripper commands, solved by the arms' kinematic model and executed as a joint
  move of at most 0.25 m/s).
- Observations: cameras `cam_head`, `cam_left_wrist`, `cam_right_wrist` (640×480, z-depth); 58 proprioception
  columns; `/kinematics` (FK/IK of both arms from the X5 URDF, matching the simulator's link6 poses).
- Request checks: every field of a `/submit` or `/observe` is read and checked before the first action. A malformed
  request (a wrong type, a value out of range, an `ee_pose` position more than 3 m from the world origin on any axis, a
  zero quaternion) is a 400 and executes nothing. Cameras are taken once each; one call returns at most 3000 images.
- Not given: object poses, the scene layout, the checks or their parts, any success signal.
- The joint limits in `/spec` and `robot_spec()` are the articulation's soft limits as Isaac Lab reports them (about
  ±10 rad for several joints). The arm's joint4 may stop at about ±1.78 rad.

World-frame information: the instructions give the world frame (axes, the arm bases, the table, the head camera) and
state RoboDojo's check in physical terms, with absolute coordinates where the check uses them. Standard tasks never
give object poses; privileged tasks give them through the tooling. The instructions do not say what the task asks
the agent to work out (for example which tile completes an equation, or which object the language names), nor which
step of RoboDojo's task sentence the check does not read.

Tooling holds thin wrappers only: joint moves, gripper commands, hold, RoboDojo's IK, and the frozen instance, state,
recording, replay and rendering. No task-level skill.

## Grading

- **Privileged.** `tests/grade.py` replays `/app/output/trajectory.npz` open-loop from the frozen start, each time in
  a fresh process of a verifier container without network, up to 3 times (`[metadata] replays`), stopping at the first
  success. Reward 1 if any replay succeeds. Only the file's `task` and `actions` entries are read, their sizes checked
  in the archive before anything is decompressed. A file that is not an npz, holds pickled or object arrays, has
  another shape, NaN or inf, more than 15,000 rows, or another task's name is the agent's 0 (`bad_trajectory`,
  `wrong_task`). A replay process that ends without a result or runs out of its time is the verifier's
  (`grader_error`, an infrastructure failure). A replay whose process rebuilt the frozen layout to another state than
  `instance.json` records did not start from the frozen state and gives no verdict (`instance_mismatch`,
  infrastructure), except where `instance.json` sets `"determinism": "verdict"`: there the hash is recorded, not
  compared.
- **Standard.** The sidecar judges the live episode with RoboDojo's checks after every action and the end rule above;
  `final.json` records the verdict (`graded_by` "live", `replays` 0). No reset. A crash inside the agent's calls and a
  simulator error raised by them are the agent's (the episode is judged on the state it left). A missing or
  unfinalized `final.json`, no `episode.json`, a give-up after crashes between calls, and an episode the collect hook
  never sees end are infrastructure failures. Before it serves, the service compares the rebuilt layout's state hash
  with `instance.json`'s (`instance_exact`); a mismatch is an infrastructure give-up (`instance_mismatch`), except for
  the instances graded by verdict, whose layout is still checked to be `instance.json`'s own.
- **Crash recovery (standard).** A crashed service is restarted inside the trial and replays its journal from the last
  checkpoint. Resume class `exact` (a fresh process whose first run is bit-exact) for 48 tasks, `approx` for the six
  tasks below; for those, the verdict after a resume is the live state the resumed service continued from, and
  `reward.json` reports `resumes` and `resume_state_mismatch`. At most two resumes.
- **Determinism.** Measured with two fresh-process replays of a 120-action trajectory moving both arms and grippers:
  48 of the 54 tasks replay bit for bit, `make_toast` with enhanced determinism. Six do not (`"determinism":
  "verdict"` in their `instance.json`): `fold_clothes` and `fold_clothes_random` (GPU PhysX cloth, once the garment is
  handled), `make_toast_random` (resets differ even with enhanced determinism), and the three liquid tasks
  `pour_liquid_into_cup`, `pour_liquid_into_cup_random` and `pour_by_language` (GPU PhysX particles). The same
  trajectory can succeed in one fresh replay and fail in the next, so a success may include some luck of the physics,
  in either mode. Frozen on an RTX 4090; on L40S, L40 and L4 the frozen layouts rebuild to the recorded hashes and the
  120-action trajectory ends in the same state. Every graded trial reports `instance_exact`.
- **Videos.** Standard: `live.mp4` from the frames of `cam_head` that the agent's own calls already rendered (at most
  one per 5 actions) plus the end state, encoded by the collect hook after the verdict. Privileged: every replay is
  filmed and the last one run is kept (`replay.mp4`). A video never changes the verdict.
- **Time limits.** The agent has 3600 s in both modes. Every Python process pays about 2.5-4 min of Isaac Sim launch,
  scene build and RoboDojo's settling, so an hour holds about a dozen simulator starts at most. A replay takes up to
  about 7 min until the layout is ready and then runs at about 5-11 actions per second, filmed; its allowance is
  max(1800 s, 1200 s + rows / 2.5). The privileged verifier has 22200 s (three replays of 15,000 rows, plus 600 s).
  The standard collect hook has 3600 s (the episode end, up to 2700 s through a resume, plus the video encode); the
  standard verifier keeps 1200 s.

## Tasks

One frozen instance per family: RoboDojo's evaluation layout 0 of seed 0. Every task also allows seeds 1 and 2
(`[metadata.seeds]`): layout 0 of RoboDojo's evaluation seeds 1 and 2, which RoboDojo's own evaluation runs. A seed
moves the objects, can swap object models and the clutter, and in the language and number tasks changes RoboDojo's
instruction (target, colours, numbers, order); the robot's start stays. Upstream's files for `cover_blocks` seed 1 and
`play_tic_tac_toe` seeds 1 and 2 repeat seed 0's layout. Each seed's instance and its instruction changes
(`seed.toml`) are in `tests/seeds/<k>/` of the privileged task; `scripts/task_seed.py materialize` puts them in place.
Each seed passed the same determinism test, except `store_laptop_and_headphones_random` seed 1, whose laptop settles
in one of two states about 2 µm apart; that seed's instance is graded by verdict.

| dimension | families |
|---|---|
| Generalization (12, each with its `_random` variant) | `stack_bowls`, `push_T`, `pack_objects_into_box`, `fold_clothes`, `hang_mugs`, `sweep_blocks`, `pour_liquid_into_cup`, `make_toast`, `arrange_largest_number`, `sort_nesting_dolls_by_size`, `store_laptop_and_headphones`, `stack_blocks` |
| Memory (6) | `cover_blocks`, `match_and_pick_from_conveyor`, `swap_blocks`, `swap_T`, `press_by_number`, `imitate_sorting_sequence` |
| Precision (8) | `fasten_screws`, `plug_in_charger`, `insert_tubes`, `pour_balls_into_vase`, `play_Xylophone`, `deposit_coin`, `insert_key`, `build_tower` |
| Long-Horizon (8) | `fill_pen_holder`, `classify_objects`, `put_bottles_into_dustbin`, `play_tic_tac_toe`, `fill_egg_holder`, `organize_table`, `make_kong`, `play_stacking_toy` |
| Open (8) | `align_blocks`, `general_pickup`, `solve_equation`, `stack_blocks_by_language`, `classify_objects_by_language`, `pick_from_conveyor_by_image`, `store_tools_in_toolbox`, `pour_by_language` |

The `_random` variants use other object models, lighting and backgrounds, with about 15-20 clutter objects. Each
task's README states its exact checks, its step limit and its end rule.

## Others

- **No reference solution.** RoboDojo releases no expert or planner script, and its training demonstrations (Hugging
  Face, `data/`) record no initial state or layout, so none replays on a frozen layout. Every task is
  `oracle = "none"`.
- **Resources.** Measured on the heaviest scene (`pour_liquid_into_cup_random`: GPU PhysX liquid and 15-20 clutter
  objects) on an RTX 4090: one Isaac session (the privileged main container, or the standard sidecar) peaks at about
  16 GiB of memory and 9.0-9.5 GiB of GPU memory and uses every core it is given while Isaac starts; a filmed verifier
  replay 15.7 GiB and 9.6 GiB. The privileged GPU-memory cap holds one session; a second one at once can go over it.
  The caps are in `scripts/task_resources.toml`.
- **Image.** `images/robodojo/` is a recipe that needs no build context, copied verbatim into every task's Dockerfile
  (privileged: `environment/` and `tests/`; standard: the sidecar's `environment/sim/Dockerfile`) as the stage
  `robodojo-base`. Isaac keeps generated Python in its Kit cache: the verifier and the standard sidecar mount their own
  `*_trusted` cache volumes, scoped to the trial's compose project.
