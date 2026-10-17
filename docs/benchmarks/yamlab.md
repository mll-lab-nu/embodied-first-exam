# YAMLab

[YAMLab](https://github.com/ARISE-Initiative/yamlab) @ ec0455d (MIT) on Isaac Lab @ f4aa17f / Isaac Sim 5.1.0: bimanual
manipulation with two I2RT YAM arms (6 joints each, parallel two-finger grippers) on a workstation table.
`simulator = "yamlab"`, `robot = "i2rt-yam-bimanual"`. Two families, YAMLab's two tasks:
- `put_pot_on_cooktop` (PutPotOnCooktop-v0): lift a pot with both grippers and set it upright on a cooktop;
- `hang_mug_on_tree` (HangMugOnTree-v0): lift a mug with the left gripper, hand it to the right one in the air, hang it on
  a mug tree.

5 frozen instances per family (10), each a privileged task `yamlab-<family>-iNN-privileged` and its standard twin
`yamlab-<family>-iNN-standard` (`eai-standard/2.2`): 20 task directories. Each instance is a different pair of YAMLab's
object assets (pot_k + cooktop_k, mug_k + mug_tree_k) placed as in one of YAMLab's human teleoperation demonstrations.
The instances keep the ids they were frozen with (Instances): `put_pot_on_cooktop` i00, i03, i04, i07, i08;
`hang_mug_on_tree` i10, i13, i15, i20, i21.

## Instances
25 instances per family were frozen (Tasks and generator); on 2026-10-10 (owner) the set was cut to 5 per family, because
the 25 differ only in the object pair and one of 9 (pot) or 3 (mug) placements and so repeat each other. The kept five are
chosen among the instances whose standard task GPT-6 Luna's run (`codex-gpt6_luna-xhigh`) had graded at that time, mixing
its successes and failures and spreading over the placement schedule:

| Instance | Placement (schedule entry) | Luna, standard | Luna, privileged |
|---|---|---|---|
| `put_pot_on_cooktop` i00 | 0 | fail | fail |
| `put_pot_on_cooktop` i03 | 3 | fail | success |
| `put_pot_on_cooktop` i04 | 4 | fail | success |
| `put_pot_on_cooktop` i07 | 7 | fail | fail |
| `put_pot_on_cooktop` i08 | 8 | fail | fail |
| `hang_mug_on_tree` i10 | 1 | fail | success |
| `hang_mug_on_tree` i13 | 1 | success | fail |
| `hang_mug_on_tree` i15 | 0 | fail | fail |
| `hang_mug_on_tree` i20 | 2 | success | success |
| `hang_mug_on_tree` i21 | 0 | success | fail (time-out) |

`put_pot_on_cooktop` had no graded Luna success in standard mode (0 of the 10 graded: i00-i05, i07, i08, i10, i11), so its
five are failures; the three that ended in an agent time-out (i01, i02, i05) were not taken. `hang_mug_on_tree`: 4 of 25
succeeded (i13, i20, i21, i23); three are kept, one per placement, with two failures that ended without a time-out.
The kept tasks are byte-identical to before (their results stand); the other 20 instances per family (40 pairs, 80 task
directories) are removed with their frozen files. `scripts/yamlab/instances.json` lists the kept instances with their ids
and, under `pruned`, the removed ids; `freeze.py`'s `KEEP` applies the same cut.

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
  The first accepted demo of a file is that pair's instance; the first 25 accepted pairs per family became i00..i24, of
  which five per family are kept (Instances). `instances.json` lists the rejected candidates with their reason.
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
`oracle = "full"`, 50/50 in both modes (measured on the 25 + 25 instances before the prune; the 10 kept are among them). The reference solution is YAMLab's own human demonstration of that instance: a
30-step (1 s) linear move from the home pose to the demonstration's first action, then its recorded 14-D actions, replayed
open-loop. YAMLab's own replay tool restores the recorded *states* frame by frame; here only the actions are replayed, and
with PhysX on the CPU they reproduce the demonstrations: object paths stay within millimetres to ~3 cm of the recorded ones
and every selected demonstration succeeds under the evaluation thresholds. The privileged oracle (`solution/oracle.py`)
runs `solution/oracle_actions.npy` through the agent's own tooling; the standard oracle (`solution/oracle_replay.py`, the
RoboLab script) streams the same rows as one-second `joint_position` chunks (`dt` = 1/30 s, `hold`) through the client,
riding through a service crash. The demonstrations are public (the dataset), so the agent's egress is closed to the model
APIs and the package registries in both modes (`network_mode = "allowlist"`), and the image contains no demonstration.

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
- Standard (since 2026-10-17, owner, boards 0150/0151): graded by the **live episode**, with no grading replay. The
  service judges the episode it runs (YAMLab's check after every control step, every stage latched; a task object off the
  table ends it, `object_fell`), dumps it on the collect hook's signal and exits; the hook (`environment/sim/finalize.sh`,
  RoboLab's) writes `final.json` from `episode.json` (`graded_by` "live", `replays` 0) before anything else. success =
  the live success, no infrastructure failure. The standard verifier reads only `final.json` with
  `network_mode = "no-network"`. YAMLab has no end-of-episode hold, and its replay applied none either, so the live rule is
  the replay's. Until 2026-10-17 the hook replayed the trajectory in two fresh processes (success = live ∧ replay ∧
  deterministic); a trial of that version is re-scored by its live episode as RoboLab's (docs/benchmarks/robolab.md,
  Grading).
- The start state (standard): before serving, the service compares the rebuilt scene with the instance's recorded state
  (`state_sha`, or every object pose and joint within tolerance, `Session.instance_matches`); a mismatch is a give-up as an
  infrastructure failure (`instance_mismatch`, 409 to every request). Before, the strict check crashed the service.
- Whose failure a 0 is, as RoboLab's (docs/benchmarks/robolab.md, Grading): the standard grader books a missing,
  unreadable or unfinalized `final.json`, no record of the live episode, a give-up after crashes between calls and an
  instance mismatch at the start as `infra_error = 1`; a crash inside the agent's calls and a simulator error raised by
  them stay the agent's 0. `finalize.sh` writes `final.json` atomically. The privileged
  grader books an unreadable deliverable as `bad_trajectory` (the agent's 0) and a replay without a result, a replay
  time-out or `instance_ok = 0` as `grader_error = infra_error = 1`.
- The video (standard, since 2026-10-17) comes from the live episode (`live_video.py`, `live.mp4`): the cameras render
  only when a frame is asked for, and a filmed replay took 2.4x as long as an unfilmed one (median over the 21 archived
  standard trials longer than 2000 control steps), so the service never renders for the video. It keeps the tooling's
  video frame (top + both wrist cameras) at the control steps the agent's own calls already rendered (the call's frames at
  its `video_fps`, 5 per simulated second by default, and the frame at each call's end), at most one per 6 control steps,
  as JPEG files (`/data/live_video/`; a resume deletes the frames of the call lost in the crash); only the end state is rendered once more, at the dump. The video's rate is therefore
  the agent's (at least one frame per call), not a fixed one. The collect hook encodes it after the verdict; a failure
  costs the video only. Privileged: the replay video never decides a replay: the tooling catches every video failure
  (`video_ok` false in the replay's result) and the frames go straight to the encoder; a trajectory longer than 18,000
  control steps is filmed as a time lapse (at most 9,000 frames).
- Both verifiers run with `network_mode = "no-network"`. Isaac Sim starts and renders offline: the two web assets the
  scene would otherwise fetch from NVIDIA's asset bucket at run time (Isaac Lab's default ground; the three MDL materials
  of YAMLab's workstation USDs) are baked into the image (`images/yamlab/web_assets.txt`, sha256-checked; the workstation
  USDs' URLs rewritten to the copies by `images/yamlab/localize_assets.py`). Measured offline with a cold Kit cache: no
  asset error, the same scene and final-state hashes as online, frames within renderer noise of the online ones.

## Crash recovery (standard mode, docs/STANDARD_MODE.md §13)
Resume class `exact`: the resumed service is a fresh process whose journal replay is that process's first run, so the
state hash at the last checkpoint must match exactly (else `resume_failed`, `infra_error`). `RCB_STARTUP_TIMEOUT_S = 1800`
(the compose file's value; see Time budget).
Acceptance test `scripts/yamlab/kill_test.sh` (Harbor oracle on `yamlab-put-pot-on-cooktop-i01-standard`, since removed, the service
killed with SIGKILL in the middle of its 7th call, after 6 checkpointed calls / 180 control steps): the container restarted,
the fresh service replayed the 180 journaled steps in 1.9 s, matched the checkpoint's state hash exactly (`68076b87…`),
resumed the same episode after 49 s of downtime, the oracle continued from the reported step, and the episode was graded
as usual: success 1, live = replay 1 = replay 2, `resumes = 1`, `sim_startups = 2`, no infra error.

## Time budget (D8)
**Since 2026-10-12: 3600 s** for every task of both modes (owner: stricter cutoffs in 30-minute steps, one number for both modes; history in [`../CUTOFFS.md`](../CUTOFFS.md)). The text below describes the budget before that, 5400 s, and why it was chosen; results are grouped by budget.

The number is each task's own `[agent] timeout_sec`, written by the generator (PROTOCOL §2.12; history in [`../CUTOFFS.md`](../CUTOFFS.md)), and
every instruction states it in its closing `## Time limit` section; the benchmark's own text names no number. On
2026-10-11: 5400 s for every task of both modes, as RoboLab: every Python process pays ~1.5-2.5 min of Isaac Sim launch and scene build
(more on a loaded host), and these are long two-arm episodes (the reference demonstrations run 10-28 s of robot time).
A trial's first Isaac start in a container compiles the shaders into the trial's fresh Kit cache: 629 s measured on a
heavily loaded host; the standard sidecar's startup watchdog is therefore 1800 s (as BEHAVIOR-1K), and the standard
oracle waits up to an hour for the service.

Verifier-side limits (2026-10-10; not measured on a GPU host for this change). Privileged: each fresh-process replay has
max(1800 s, 1200 s + rows / 20) (the verifier's first Isaac start is the cold one; 20 control steps/s is a third of the slow
nominal rate) and `[verifier] timeout_sec = 13000` fits two replays of the longest accepted trajectory (100,000 rows:
6200 s each) plus 600 s; before, 2400 s was shorter than two 1800 s replays and than one cold start plus a long filmed
replay. Standard: `[[verifier.collect]] timeout_sec = 15000` (was 5400) = the episode end (up to 2700 s through a resume)
+ two replays of up to 5700 s + 900 s, until 2026-10-17; now 3600 s (the episode end + the video encode, at most 600 s on
the CPU, + a margin). The saving: two fresh-process replays per trial (74-149 s each at the median, 400-1000 s at the p90
over the 31 archived standard trials, on the trial's GPU).
The tests of these rules run without a simulator and cover YAMLab with RoboLab: `scripts/robolab/tests/test_*.py`.

The tooling's runaway guard ends an episode after 100,000 control steps (`step_guard`, 55.6 min of simulated time). At
60-120 control steps/s a standard episode can reach it within the 5400 s budget, so it is stated in `/spec`
(`max_control_steps`, `episode`), in both instructions and in the README (PROTOCOL §4.5: a technical cap, not a step
budget); a privileged trajectory may hold at most that many rows.

## Standard mode (eai-standard/2.2)
`joint_position` (14: YAMLab's action, rows `dt` apart, a multiple of 1/30 s; `linear` interpolates the gripper targets too)
and `ee_pose` (16: both tool frames + both gripper targets per row, closed-loop differential IK, at most 0.25 m/s); cameras
`top`, `left_wrist`, `right_wrist` (640×480, z-depth); `/kinematics` from numpy models of both arms (`q` = left joint1..6,
right joint1..6); 58 proprio columns (joints and fingers, both tool poses, gripper targets, velocities, gripper openings,
arm efforts). STANDARD_MODE.md §16. Requests are checked completely before the first control step, as RoboLab's
(docs/benchmarks/robolab.md, Standard mode): wrong types, out-of-range values, an `ee_pose` position more than 3 m from
the world origin on any axis or a zero quaternion are 400s that execute nothing.

## Declarations
- **Tooling: thin wrappers only.** IK moves, joint moves, gripper commands, hold, plus the frozen instance, state, stage
  flags, recording, replay and rendering. Task-level skills (grasp, lift, handover, place, hang) are never added to the
  agent's tooling.
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE.md §10,
  `scripts/yamlab/ci/advisory-world-frame.sh`); the robot (both arm bases) and the world conventions are given. Privileged tasks give the
  privileged state through the tooling and the world heights of the success check in the instruction.

- **Pointers to the reference solution.** The reference solution of an instance is the YAMLab teleoperation
  demonstration it was frozen from, replayed (Evidence), and that dataset is public. The agent's egress is the model
  APIs only, so it cannot be fetched. Since 2026-10-10 the instance file an agent reads names no recording (it had a
  `source` entry with the dataset, the file and the demonstration index; `mk_tasks.py` now refuses such a file, and the
  provenance is in `scripts/yamlab/instances.json` only). What still locates it for someone outside the trial: the
  instance id `iNN` in the task name is the index of the dataset's recording file, the privileged instruction names the
  object asset with the same number, and the image's `/opt/yamlab` (its README and `scripts/download_data.py`) names the
  dataset. Renaming the instances would change every task's identity; it is left as it is.

## Image and host
`images/yamlab/` → `ghcr.io/mll-lab-nu/eai-yamlab:0.1.0` (~26.5 GB): YAMLab, Isaac Lab, Isaac Sim 5.1, the LeRobot fork
YAMLab's recorder imports, and the two tasks' object assets (~3 GB). It contains Isaac Sim: **BUILD_ONLY**
(`images/yamlab/BUILD_ONLY` has the licences, the build command and the check of a build). Needs an RTX-class GPU (PhysX on
the CPU); one simulator per ~16 GB of RAM. Isaac keeps generated Python in its Kit cache: the verifier and the standard
sidecar mount their own `*_trusted` cache volumes; every cache volume is scoped to the trial's compose project.

## Change log
- 2026-10-17 (owner, boards 0150/0151): standard modes graded by the live episode; no grading replay; video by the sim
  service during the live episode (`live.mp4`, from the renders of the agent's own calls). The start-state check moved to
  the episode's start (`instance_mismatch` = a give-up as infra before serving). Collect hook 15000 s -> 3600 s. The
  `main` kill hook (`kill -9 -1`) runs before the sim's (PROTOCOL H.4). Privileged tasks unchanged. The 10 standard task
  dirs regenerated in place (new DIGESTs; the instructions do not change).

## Licences
YAMLab, its USDs and its dataset (objects, demonstrations): MIT. Isaac Lab: BSD-3-Clause. LeRobot fork: Apache-2.0. Isaac Sim
5.1 and its wheels: NVIDIA proprietary (no redistribution), hence BUILD_ONLY.

## Standard-mode service details (moved from STANDARD_MODE.md, 2026-10-14)

Serves `eai-standard/2.2`. Resume class `exact` (Isaac Lab, CPU PhysX, a fixed env seed: the resumed service is a fresh process, whose first run is bit-exact). Its service states no `max_frames_per_call` yet (calls are bounded by `max_watch_s`, `max_chunk_s` and the frame rate).

## Easy set

The benchmark owner's screening of 2026-10-17 (results dashboard snapshot 2026-10-17T05:59:33Z; ten runs, one trial per
run and task directory). A directory is **easy** when a run solved it: a graded success within the task's time limit.
Where only one or two of the later runs solved a directory Luna had failed, their logs were checked for shortcuts and
for any access to tests, solutions or graders (for this benchmark from the grading records only: the log review was
partial). It is **hard** when GPT-6 Luna and every later run that attempted it failed, GPT-6 Astra and Claude Opus 5.5
among them; a standard directory that only Astra solved is hard as well. It is **unverified** when only Luna attempted
it and failed (the later runs only take bases Luna solved in no mode), and **pending** without a Luna verdict. A base
whose every mode is easy is in the easy set (`docs/easy_set.toml`, reason `solved`): kept under its name and reported
apart from the main table.

Runs: Luna `codex-gpt6_luna-xhigh`; Astra `codex-gpt6_astra-high`; Opus `claude_code-opus_5_5-high`; Sol 6.1
`codex-gpt6_1_sol-high`; Sol `codex-gpt6_sol-high`; Gemini 3.8 Flash `antigravity_cli-gemini_3_8_flash-high`; Gemini 4
Argon `antigravity_cli-gemini_4_argon-high`; DeepSeek V4.1 Flash `dsh-deepseek_v4_1_flash-high`; GLM 5.3 Flash
`claude_code-glm_5_3_flash-high`; Qwen3.8 27B `claude_code-qwen3_8_27b-high`.

5 of 10 bases are in the easy set; by directory: 15 easy, 0 hard, 5 unverified, 0 pending.

| base | easy set | privileged | standard |
|---|---|---|---|
| `yamlab-hang-mug-on-tree-i10` |  | easy: Luna | unverified |
| `yamlab-hang-mug-on-tree-i13` |  | unverified | easy: Luna |
| `yamlab-hang-mug-on-tree-i15` | yes | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon | easy: Opus |
| `yamlab-hang-mug-on-tree-i20` | yes | easy: Luna | easy: Luna |
| `yamlab-hang-mug-on-tree-i21` |  | unverified | easy: Luna |
| `yamlab-put-pot-on-cooktop-i00` | yes | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon |
| `yamlab-put-pot-on-cooktop-i03` |  | easy: Luna | unverified |
| `yamlab-put-pot-on-cooktop-i04` |  | easy: Luna | unverified |
| `yamlab-put-pot-on-cooktop-i07` | yes | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus |
| `yamlab-put-pot-on-cooktop-i08` | yes | easy: Astra, Opus, DeepSeek V4.1 Flash | easy: Astra, Opus, Gemini 4 Argon |
