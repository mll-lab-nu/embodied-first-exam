# YAMLab

## Overview
[YAMLab](https://github.com/ARISE-Initiative/yamlab) on Isaac Lab / Isaac Sim 5.1.0: bimanual manipulation with two
I2RT YAM arms (6 joints each, parallel two-finger grippers) on a workstation table. Two families, YAMLab's two tasks,
five frozen instances each, in the privileged and standard modes: 20 task directories.

| | |
|---|---|
| upstream | YAMLab @ `ec0455d` (MIT) on Isaac Lab @ `f4aa17f` / Isaac Sim 5.1.0 |
| families | `put_pot_on_cooktop` (PutPotOnCooktop-v0): lift a pot with both grippers and set it upright on a cooktop; `hang_mug_on_tree` (HangMugOnTree-v0): lift a mug with the left gripper, hand it to the right one in the air, hang it on a mug tree |
| tasks | `tasks/yamlab/yamlab-<family>-iNN-privileged` and `-standard` |
| metadata | `simulator = "yamlab"`, `robot = "i2rt-yam-bimanual"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/efe-private:yamlab-0.2.1` (`images/yamlab/`, ~27 GB), BUILD_ONLY: every task builds it as its `yamlab-base` stage when it cannot pull it |
| GPU | one RTX-class NVIDIA GPU (Isaac renders with RTX even headless); PhysX runs on the CPU |

```bash
harbor run -d embodied-first-exam@all -p tasks/yamlab -a codex -m openai/gpt-6-astra
```
The first run builds the simulator image (about 25 min on a fast link, about 60 GB of free disk while it builds). The
tasks allow 90 min for the build (`[environment] build_timeout_sec`); raise it with
`--environment-build-timeout-multiplier` on a slow link. Organization members who can read
`ghcr.io/mll-lab-nu/efe-private` pull the prebuilt layers instead (compose `cache_from`); without that access the build
prints a warning that it cannot read the cache image and goes on building. To build ahead of a batch:
`docker build --target yamlab-base tasks/yamlab/yamlab-put-pot-on-cooktop-i00-privileged/environment`.

## Upstream and license
[YAMLab](https://github.com/ARISE-Initiative/yamlab) at commit `ec0455d2b4ce35f21fc126418ea5e74ac567133d`, MIT License
(Copyright (c) 2026 Tianyuan Dai); its scene and object USDs and its dataset (`yamlab/yamlab_datasets` on Hugging Face,
pinned revision) are MIT too. Isaac Lab @ `f4aa17f` (the commit YAMLab's `install.sh` pins): BSD-3-Clause. YAMLab's
LeRobot fork (`RogerDAI1217/lerobot` @ `67031e9`, imported by its recorder): Apache-2.0. No non-commercial terms.

NVIDIA Isaac Sim 5.1 / Omniverse Kit and its wheels are NVIDIA proprietary: licensed for use, not for redistribution.
The image is therefore not on a public registry (`images/yamlab/BUILD_ONLY`): your first run builds it from public
sources (Docker Hub `nvidia/cuda`, snapshot.ubuntu.com, github.com, pypi.org, download.pytorch.org, pypi.nvidia.com,
the Hugging Face dataset, NVIDIA's public asset bucket), and that build accepts, on your behalf, NVIDIA's Isaac Sim /
Omniverse licence agreement and its terms for the wheels and the asset files it bakes in (`OMNI_KIT_ACCEPT_EULA=YES`,
`ACCEPT_EULA=Y`). Read them before you run these tasks. No account, login or token is needed.

## Changes from upstream
- **Physics, assets, success checks: YAMLab's.** The environments are YAMLab's own (`create_task_environment`, mode
  `replay`: one env on the CPU, no domain randomization) with `is_evaluation_mode=True`, so the success check is
  YAMLab's staged check with its evaluation thresholds, unchanged.
- **Fixed env seed.** YAMLab sets no env seed, so its reset events (random object poses, then 4 warm-up physics steps)
  differ between processes, and PhysX keeps contact data from them that a later state restore does not overwrite:
  identical restored states diverged after one control step in fresh processes. The tooling fixes the Isaac Lab env
  seed (0), so every fresh process makes the same calls before the frozen state is restored; fresh-process runs of the
  same actions are bit-identical (checked for every instance). The tooling also renders once after every restore
  (`sim.render()` runs `forward()`), so every run starts the same way.
- **Episode ends.** YAMLab's `<object>_below_table` terminations would reset the scene; here they end the episode as a
  failure, with the scene as it is. YAMLab's time-out and `task_success` terminations are off; the tooling ends a
  privileged replay at the first step where every stage has latched, as YAMLab's evaluation does.
- **Offline assets.** The two web assets the scene would fetch at run time (Isaac Lab's default ground; the MDL
  materials of YAMLab's workstation USDs) are baked into the image (`images/yamlab/web_assets.txt`, sha256-checked;
  the USDs' URLs rewritten by `images/yamlab/localize_assets.py`). Offline runs give the same scene and final-state
  hashes as online runs.
- **Instances.** Each instance is one pair of YAMLab's object assets (pot_k + cooktop_k, mug_k + mug_tree_k), placed
  as in one of YAMLab's human teleoperation demonstrations of that pair (dataset `yamlab/yamlab_datasets` @ `fc6be97`).
  YAMLab's reset puts both arms at the home pose (joints 0, grippers open). An instance was accepted when its
  demonstration's actions, replayed, succeed live and in two fresh-process replays that end in the live run's state
  hash.
- **Added.** The tooling `rcb_yamlab.py` (session, frozen instance, stage flags, recording, replay, rendering, FK / IK)
  and the standard-mode service (`embodied_first_exam/benchmarks/yamlab/sim/server.py`).

## Interface
- **Actions.** YAMLab's 14-D action `[left joint1..6, left gripper, right joint1..6, right gripper]`: absolute joint
  targets (rad) tracked by PD drives; a gripper entry is its `left_finger` target (m, -0.0475 open .. 0 closed;
  YAMLab mirrors it onto `right_finger`). 30 Hz control (sim dt 1/120 s, decimation 4). At most 100,000 control steps
  per episode (`MAX_STEPS`, about 56 min of simulated time): a technical cap, not a step budget.
- **Privileged.** `rcb_yamlab.py`: `Session` (frozen instance, reset, step, record, replay, save_trajectory, video),
  `objects()` (pose, size from YAMLab's `asset_size.json`, AABB, velocity), the stage flags and `success_params()`,
  three cameras (`top` static; `left_wrist`, `right_wrist` on each arm's `link_6`) with depth and calibration, per-arm
  `ee_pose` / `joint_positions` / `gripper_opening` / efforts, FK / IK on numpy models of both arms, and thin
  primitives (`move_ee`, `move_joints`, `set_gripper`, `hold`). The tool frame `<arm>_tcp` is the midpoint of the two
  fingertips, 0.1426 m along `link_6`'s +z. Task-level skills (grasp, lift, handover, place, hang) are not part of the
  tooling. The deliverable is `/app/output/trajectory.npz`.
- **Standard** (protocol `eai-standard/3.0`). Action types `joint_position` (14, YAMLab's action, rows `dt` apart, a
  multiple of 1/30 s) and `ee_pose` (16: both tool frames and both gripper targets per row, closed-loop differential IK,
  at most 0.25 m/s); cameras `top`, `left_wrist`, `right_wrist` (640×480, z-depth on request); `/kinematics` from the
  numpy arm models; 58 proprio columns (joints and fingers, both tool poses, gripper targets, velocities, gripper
  openings, arm efforts). A request is checked completely before the first control step: wrong types, out-of-range
  values, an `ee_pose` position more than 3 m from the world origin on any axis or a zero quaternion are 400s that
  execute nothing. One episode, no reset.
- **World-frame information.** Standard tasks never say where things are in the world
  (`ci_checks/check-world-frame-texts.sh`); the robot (both arm bases) and the world conventions are
  given. Privileged tasks give the full state through the tooling.

## Grading
- **Success** is YAMLab's staged check in evaluation mode. PutPotOnCooktop: pick (the pot more than 5 cm above its
  resting height with both grippers grasping it, 8 consecutive control steps), then place (the pot on the cooktop:
  centre within the XY tolerance YAMLab computes from the two assets' sizes, height within 2 cm of the stacking height,
  vertical axis within 0.2 rad of vertical, neither gripper grasping it, 30 steps). HangMugOnTree: pick (left gripper
  grasping, the mug more than 5 cm up, 8 steps), handover (right grasping, left not, the mug more than 5 cm up, 30
  steps), hang (the mug within the XY tolerance of the tree, more than 5 cm above its table-resting height, neither
  gripper grasping, height steady within 3 cm, 30 steps). "Grasping" is YAMLab's grasp detection: both fingers touch
  the object with at least 0.1 N, on their pads. Stages latch in order. A task object more than 1 cm below the table top
  ends the episode as a failure. The per-instance tolerances are in each task's README and `instance.json`
  (`success_params`).
- **Privileged: one replay.** `tests/grade.py` replays `/app/output/trajectory.npz` once in a fresh process from the
  verifier's copy of the instance; it passes when every stage latches in that replay (the replay stops there) and the
  rebuilt frozen scene matches the recorded one (exact state hash, or every object pose and joint within tolerance on
  another host). An unreadable or wrong file is the agent's 0; a replay without a result, a replay time-out or a
  scene mismatch is `grader_error = infra_error = 1`.
- **Standard: the live episode.** The service judges the episode it runs; nothing is replayed. The earlier stages
  count as they latch; the last stage must still hold, with its 30-step run complete, when the episode ends (before
  every control step the tooling reopens the last stage's latch with its counter one short, `rcb_yamlab.LAST_STAGE`). At
  `/finish` and at the session's end a run of the last stage that has begun is completed with the last command held.
  A fallen object is 0, also after a success. The 100,000-step cap ends the episode as `step_limit`, judged as it
  stands. Before serving, the service checks that the rebuilt scene matches the instance (`instance_mismatch`, an
  infrastructure failure otherwise).

## Tasks
Five frozen instances per family; the instances keep the ids they were frozen with:

| family | YAMLab env | instances | stages |
|---|---|---|---|
| `put_pot_on_cooktop` | PutPotOnCooktop-v0 | i00, i03, i04, i07, i08 | pick, place |
| `hang_mug_on_tree` | HangMugOnTree-v0 | i10, i13, i15, i20, i21 | pick, handover, hang |

Each instance id `iNN` is the index of the dataset's recording file of that object pair (one file per pair, e.g.
`putpot_007.hdf5` = `Pot/pot_007` + `Cooktop/cooktop_007`). PutPotOnCooktop's demonstrations follow YAMLab's placement schedule of the pot
(3 lateral positions × 3 yaws); HangMugOnTree's the mug's 3 yaws; the cooktop and the tree never move. Every task
carries the tooling, its `instance.json` (in `environment/` and `tests/` for privileged, `environment/sim/` for
standard) and its reference solution: YAMLab's own human demonstration of that instance (a 1 s linear move from the
home pose to the demonstration's first action, then its recorded actions, open-loop), `solution/oracle_actions.npy`
(privileged) or `solution/oracle_qpos.npy` streamed as 1 s `joint_position` chunks (standard).

## Others
- **Reference solution and egress.** The demonstrations are public (the dataset), so the agent's egress is the model
  APIs and the package registries only (`network_mode = "allowlist"`), and the image holds no demonstration. What still
  locates one for someone outside the trial: the instance id is the dataset file's index, the privileged instruction
  names the object asset with the same number, and the image's `/opt/yamlab` names the dataset.
- **Determinism.** A second run of the same actions inside one process can end slightly differently after stepping
  (PhysX keeps contact data across a restore), so a fresh Session's first run is the grader's run. Across hosts the last
  bits can differ; a trial is graded on the host it ran on.
- **Host.** Linux x86_64, Docker with BuildKit and the NVIDIA Container Toolkit, one RTX-class GPU with a driver Isaac
  Sim 5.1 supports; one simulator per ~16 GB of RAM. Every Isaac process pays 1.5-2.5 min of launch and scene build;
  the first start in a trial compiles shaders (up to ~10 min on a loaded host), so the standard sidecar's startup
  watchdog is 1800 s (`RCB_STARTUP_TIMEOUT_S`). The verifier and the sidecar mount their own Kit cache volumes, scoped
  to the trial.
