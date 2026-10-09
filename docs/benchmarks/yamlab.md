# YAMLab

[YAMLab](https://github.com/ARISE-Initiative/yamlab) @ ec0455d (MIT) on Isaac Lab @ f4aa17f / Isaac Sim 5.1.0: bimanual
manipulation with two I2RT YAM arms (6 joints each, parallel two-finger grippers) on a workstation table.
`simulator = "yamlab"`, `robot = "i2rt-yam-bimanual"`. Two families, YAMLab's two tasks:
- `put_pot_on_cooktop` (PutPotOnCooktop-v0): lift a pot with both grippers and set it upright on a cooktop;
- `hang_mug_on_tree` (HangMugOnTree-v0): lift a mug with the left gripper, hand it to the right one in the air, hang it on
  a mug tree.

25 frozen instances per family (50), each a privileged task `yamlab-<family>-iNN-privileged` and its standard twin
`yamlab-<family>-iNN-standard` (`eai-standard/2.2`): 100 task directories. Each instance is a different pair of YAMLab's
object assets (pot_k + cooktop_k, mug_k + mug_tree_k) placed as in one of YAMLab's human teleoperation demonstrations.

## Tasks and generator
- `python3 scripts/yamlab/mk_tasks.py` writes every YAMLab task dir (both modes) from `scripts/yamlab/` alone:
  `instances.json` (per family, the frozen instances in order with their source demonstration, assets and oracle hashes),
  `frozen/<family>-iNN/` (`instance.json`, `oracle_actions.npy`), `shared/rcb_yamlab.py` (the tooling), `template/<mode>/`
  and `scripts/eai_standard/` (the 2.2 layer and the standard client). Re-running it leaves `git diff tasks/` empty;
  `--check` only compares.
- Selection (`scripts/yamlab/select_instances.py`, in the image, on a GPU host) and freezing (`scripts/yamlab/freeze.py`):
  YAMLab's dataset `yamlab/yamlab_datasets` @ fc6be97 has 40 teleoperation files per task, one object pair each
  (`putpot_007.hdf5` = `Pot/pot_007` + `Cooktop/cooktop_007`), with 9 (PutPotOnCooktop) or 3 (HangMugOnTree) human
  demonstrations recorded on YAMLab's fixed placement schedule: demo j is schedule entry j (PutPotOnCooktop: the pot at
  3 lateral positions × 3 yaws, -118° / -90° / -62°; HangMugOnTree: the mug at 3 yaws, 105° / 135° / 165°; the cooktop and
  the tree never move). Files are walked in order; inside the k-th file the demos are tried from demo k mod n on,
  wrapping around, so the instances spread evenly over the schedule (the first selection took every file's demo 0, which
  gave all 25 instances of a family the same placement). A candidate is accepted when
  1. `rcb_yamlab.py make-instance` rebuilds the demo's recorded initial state (YAMLab's reset: both arms at the home pose,
     joints 0, grippers open; both objects where the demo found them) and writes it with its hash and YAMLab's success
     thresholds for that pair;
  2. the oracle (below) succeeds live in a fresh process;
  3. two `replay` runs, each in its own fresh process (the second one also films the replay), succeed and end in the
     live run's state hash.
  The first accepted demo of a file is that pair's instance; the first 25 accepted pairs per family become i00..i24.
  `instances.json` lists the rejected candidates with their reason.
- The tasks carry the frozen instance in `environment/` and `tests/` (privileged) and `environment/sim/` (standard).

## Success (YAMLab's own, evaluation thresholds)
The stage flags of YAMLab's task managers (`yamlab/envs/tasks/*_manager.py`) with `is_evaluation_mode`, unchanged:
- PutPotOnCooktop: pick = the pot's centre > 5 cm above its resting height with both grippers grasping it, 8 consecutive
  control steps; place = the pot on the cooktop (centre within the XY tolerance YAMLab computes from the two assets' sizes,
  height within 2 cm of the stacking height, upright within 0.2 rad) with neither gripper grasping it, 30 steps.
- HangMugOnTree: pick = left gripper grasping and the mug > 5 cm up, 8 steps; handover = right grasping, left not, mug
  > 5 cm up, 30 steps; hang = the mug within the XY tolerance of the tree, > 5 cm above its table-resting height, neither
  gripper grasping, height steady within 3 cm, 30 steps. YAMLab's own left-finger friction switching (raised at the left
  grasp, lowered when both grippers hold the mug) is part of the environment, in both modes and in every replay.
- "Grasping" is YAMLab's grasp detection (both fingers of a gripper touch the object with ≥ 0.1 N on their pads).
- Stages latch in order. As in YAMLab's evaluation (its `task_success` termination), the episode ends at the first control
  step where every stage has latched; it also ends, as a failure, when a task object falls more than 1 cm below the table
  top (YAMLab's `<object>_below_table` termination). Stages require held conditions (8 or 30 control steps), so a
  momentary pose does not count. The instructions give every number (privileged: also the world heights).

## Oracle (PROTOCOL §2.7)
`oracle = "full"`, 50/50 in both modes. The reference solution is YAMLab's own human demonstration of that instance: a
30-step (1 s) linear move from the home pose to the demonstration's first action, then its recorded 14-D actions, replayed
open-loop. YAMLab's own replay tool restores the recorded *states* frame by frame; here only the actions are replayed, and
with PhysX on the CPU they reproduce the demonstrations: object paths stay within millimetres to ~3 cm of the recorded ones
and every selected demonstration succeeds under the evaluation thresholds. The privileged oracle (`solution/oracle.py`)
runs `solution/oracle_actions.npy` through the agent's own tooling; the standard oracle (`solution/oracle_replay.py`, the
RoboLab script) streams the same rows as one-second `joint_position` chunks (`dt` = 1/30 s, `hold`) through the client,
riding through a service crash. The demonstrations are public (the dataset), so the agent's egress is closed to the model
APIs in both modes (`network_mode = "allowlist"`), and the image contains no demonstration.

## Tooling (`rcb_yamlab.py`)
Same shape as RoboLab's `rcb_robolab.py`: `Session` (frozen instance, reset, step, record, replay, save_trajectory, video),
`objects()` (pose, size from YAMLab's `asset_size.json`, AABB, velocity), the stage flags and `success_params()`, three
cameras (`top` static; `left_wrist`, `right_wrist` on each arm's `link_6`) with depth and calibration, per-arm
`ee_pose` / `joint_positions` / `gripper_opening` / efforts, stateless FK / IK on numpy models of both arms (checked against
the simulator to 2e-7 m), and thin primitives: `move_ee` (both arms together, Isaac Lab's differential IK), `move_joints`,
`set_gripper` / `open_gripper` / `close_gripper`, `hold`. The tool frame `<arm>_tcp` is the midpoint of the two fingertips
(YAMLab's finger keypoints), 0.1426 m along `link_6`'s +z.
- The env is YAMLab's own (`create_task_environment`, mode `replay`: one env on the CPU, no time-out / success termination,
  no domain randomization) with `is_evaluation_mode=True`; no image observation terms; the below-table terminations are
  evaluated by the tooling (YAMLab's env would reset the scene there).
- **Actions**: YAMLab's 14-D action `[left joint1..6, left gripper, right joint1..6, right gripper]`, absolute joint
  targets (rad); a gripper entry is its `left_finger` target (m, -0.0475 open .. 0 closed; YAMLab mirrors it onto
  `right_finger`). 30 Hz control (sim dt 1/120 s, decimation 4).

## Determinism (measured on Isaac Sim 5.1, CPU PhysX)
- YAMLab sets no env seed, so its reset events (random object poses, then 4 warm-up physics steps) differ between processes,
  and PhysX keeps contact data from them that a later `reset_to` does not overwrite: with identical restored states (hash and
  every link pose, velocity and joint target equal) three fresh processes differed after the first control step (the
  cooktop's angular velocity by up to 0.08 rad/s), ending in different states. The tooling therefore fixes the Isaac Lab env
  seed (0): every fresh process makes the same calls before the frozen state is restored, and fresh-process runs are
  bit-identical (verified for every instance: live == replay 1 == replay 2, run concurrently).
- `sim.render()` runs `forward()`, which recomputes articulation link poses from joint positions; after a `reset_to` that
  changes the next step. The tooling renders once right after every restore, so every run starts the same way. Rendering
  between steps does not change physics (a replay filmed every 2 control steps ends in the unfilmed replay's hash), and the
  cameras render only when a frame is asked for (no per-step rendering: ~3x faster stepping).
- After stepping, a restore inside the same process does not reset PhysX's contact data, so a second run of the same actions
  in one process can end slightly differently. A fresh Session's first run (and `replay()` before any step) is the grader's
  run; the instructions point to the `replay` CLI as the reference.
- Across hosts the last bits can differ (as RoboLab's); a trial is graded on the host it ran on.

## Grading
- Privileged: `tests/grade.py` replays `/app/output/trajectory.npz` twice, each in a fresh process; success = YAMLab's check
  held in both, the final hashes agree, and the rebuilt frozen scene matches the recorded one.
- Standard: the service dumps the episode and exits on the collect hook's signal; the hook (`environment/sim/finalize.sh`,
  RoboLab's) replays it in two fresh processes; success = live ∧ replay ∧ deterministic, `live_matches_replay` reported
  separately. The standard verifier reads only `final.json` with `network_mode = "no-network"`.
- Both verifiers run with `network_mode = "no-network"`. Isaac Sim starts and renders offline: the two web assets the
  scene would otherwise fetch from NVIDIA's asset bucket at run time (Isaac Lab's default ground; the three MDL materials
  of YAMLab's workstation USDs) are baked into the image (`images/yamlab/web_assets.txt`, sha256-checked; the workstation
  USDs' URLs rewritten to the copies by `images/yamlab/localize_assets.py`). Measured offline with a cold Kit cache: no
  asset error, the same scene and final-state hashes as online, frames within renderer noise of the online ones.

## Crash recovery (standard mode, docs/STANDARD_MODE_2_2.md §13)
Resume class `exact`: the resumed service is a fresh process whose journal replay is that process's first run, so the
state hash at the last checkpoint must match exactly (else `resume_failed`, `infra_error`). `RCB_STARTUP_TIMEOUT_S = 900`.
Acceptance test `scripts/yamlab/kill_test.sh` (Harbor oracle on `yamlab-put-pot-on-cooktop-i01-standard`, the service
killed with SIGKILL in the middle of its 7th call, after 6 checkpointed calls / 180 control steps): the container restarted,
the fresh service replayed the 180 journaled steps in 1.9 s, matched the checkpoint's state hash exactly (`68076b87…`),
resumed the same episode after 49 s of downtime, the oracle continued from the reported step, and the episode was graded
as usual: success 1, live = replay 1 = replay 2, `resumes = 1`, `sim_startups = 2`, no infra error.

## Time budget (D8)
5400 s for every task of both modes, as RoboLab: every Python process pays ~1.5-2.5 min of Isaac Sim launch and scene build
(more on a loaded host), and these are long two-arm episodes (the reference demonstrations run 10-28 s of robot time).
A trial's first Isaac start in a container compiles the shaders into the trial's fresh Kit cache: 629 s measured on a
heavily loaded host; the standard sidecar's startup watchdog is therefore 1800 s (as BEHAVIOR-1K), and the standard
oracle waits up to an hour for the service.

## Standard mode (eai-standard/2.2)
`joint_position` (14: YAMLab's action, rows `dt` apart, a multiple of 1/30 s; `linear` interpolates the gripper targets too)
and `ee_pose` (16: both tool frames + both gripper targets per row, closed-loop differential IK, at most 0.25 m/s); cameras
`top`, `left_wrist`, `right_wrist` (640×480, z-depth); `/kinematics` from numpy models of both arms (`q` = left joint1..6,
right joint1..6); 58 proprio columns (joints and fingers, both tool poses, gripper targets, velocities, gripper openings,
arm efforts). STANDARD_MODE_2_2.md §16.

## Declarations
- **Tooling: thin wrappers only.** IK moves, joint moves, gripper commands, hold, plus the frozen instance, state, stage
  flags, recording, replay and rendering. Task-level skills (grasp, lift, handover, place, hang) are never added to the
  agent's tooling.
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE_2_2.md §10,
  `check-limited-texts.sh`); the robot (both arm bases) and the world conventions are given. Privileged tasks give the
  privileged state through the tooling and the world heights of the success check in the instruction.

## Image and host
`images/yamlab/` → `ghcr.io/mll-lab-nu/eai-yamlab:0.1.0` (~26.5 GB): YAMLab, Isaac Lab, Isaac Sim 5.1, the LeRobot fork
YAMLab's recorder imports, and the two tasks' object assets (~3 GB). It contains Isaac Sim: **BUILD_ONLY**
(`images/yamlab/BUILD_ONLY` has the licences, the build command and the check of a build). Needs an RTX-class GPU (PhysX on
the CPU); one simulator per ~16 GB of RAM. Isaac keeps generated Python in its Kit cache: the verifier and the standard
sidecar mount their own `*_trusted` cache volumes; every cache volume is scoped to the trial's compose project.

## Licences
YAMLab, its USDs and its dataset (objects, demonstrations): MIT. Isaac Lab: BSD-3-Clause. LeRobot fork: Apache-2.0. Isaac Sim
5.1 and its wheels: NVIDIA proprietary (no redistribution), hence BUILD_ONLY.
