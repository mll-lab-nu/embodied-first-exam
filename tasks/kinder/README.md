# KinDER

## Overview

Physical reasoning for robot planning and control, kept apart from perception and language: tool use, non-prehensile
multi-object manipulation, geometric and dynamic constraints. Five KinDER Dynamic3D families, one frozen instance each,
in two modes: 10 task directories, `tasks/kinder/kinder-<family>-i<NN>-privileged` and `-standard`.

| | |
|---|---|
| upstream | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (Huang et al., RSS 2026, [arXiv 2604.25788](https://arxiv.org/abs/2604.25788)), pinned at `5b2dbac` |
| simulator | MuJoCo 3.3 (KinDER Dynamic3D) in the MimicLabs lab scenes, CPU physics |
| robot | TidyBot++: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper; delta actions at 10 Hz |
| score | pass = KinDER's own goal check (the environment's `terminated`) within an episode of 1,000 control steps |
| image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` (`images/kinder/`, 4.6 GB with the lab scenes) |

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/kinder -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the simulator, its full state (`get_state` / `set_state`) and the goal check | unlimited | its `trajectory.npz`, replayed once in a fresh process |
| standard | the robot's own sensors, through `rcb_client.py`; no world coordinates, no goal check | 0 | the episode as it ran (live; nothing replayed) |

## Upstream and license

- Upstream: KinDER, [Princeton-Robot-Planning-and-Learning/kindergarden](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden)
  at `5b2dbac482142b879b48449b3fa2af63f641aed3`, installed with pip in `images/kinder/Dockerfile` (every dependency
  pinned in `images/kinder/requirements.txt`). MIT License (copyright (c) 2025 Tom Silver).
- Scenes: MimicLabs ([Gatech-RL2/mimiclabs](https://github.com/Gatech-RL2/mimiclabs), MIT License), about 2 GB,
  downloaded once at image build time by upstream's `download_mimiclabs_assets`; a task container needs no network
  for them.
- Simulator: MuJoCo (Apache License 2.0). No non-commercial terms apply.

## Changes from upstream

- No change to KinDER's physics, scenes or goal checks.
- Dynamo's `task_view` camera (used for videos and the optional room camera) is moved by `instance.json`; upstream's
  looks down from overhead. The tooling checks that KinDER builds the camera from the task config.
- Each instance records the state hash right after reset (`scene_sha`); a KinDER that no longer builds the same scene
  from the seed is refused (`instance_mismatch`, infrastructure).
- Upstream ends an episode at the first goal check that holds. The privileged replay keeps that rule. In standard mode
  the goal check never ends the episode: the agent ends it, and the state it ends in is judged.
- Standard mode bounds a base move to a 0.1 m disc in the odometry frame (the largest move that stays inside upstream's
  per-axis bound of 0.1 m after the rotation into the world frame).

## Interface

**Privileged.** `/opt/tools/rcb_kinder.py` (`from rcb_kinder import Session`): `Session()` rebuilds the frozen instance
from `/app/instance.json`; `reset()`, `step(action)` (one 10 Hz control step: `(obs, success, done)`), `state()`,
`env` (the KinDER environment), `images(cameras)`, `recording()`, `replay(actions)`, `save_trajectory(actions, path)`.
An action is KinDER's own 11 values: base x, y, yaw deltas in the world frame (each at most 0.1), seven arm joint
deltas (each at most 0.1 rad), and the gripper command (0 open, 1 closed). Actions outside the action space's bounds
are refused, not clipped. KinDER on the CPU repeats exactly when replayed from `reset()`.

**Standard.** The `sim` sidecar serves the robot through `/opt/tools/rcb_client.py` and the `efe-robot` MCP tools
(wire protocol `eai-standard/3.0`).
- Actions: one type, `delta`, 11 values per 10 Hz control step: base x, y (together at most 0.1 m) and yaw (at most
  0.1 rad) in the odometry frame, the seven arm joint deltas (each at most 0.1 rad), the gripper command; at most 100
  rows a call. Values outside the bounds are clipped and reported in `meta["clipped"]`.
- Observations: `robot_base` RGB and `robot_wrist` RGB-D (the Gen3's RealSense D410), 480 × 640, with calibration;
  base odometry (pose and velocity in the frame the base starts in), arm joint angles and velocities, finger position.
  `spec()` gives the action layout and bounds, the arm's joint axes, limits and torques, the grasp point, the cameras'
  fields of view and poses, the control rate and the episode length.
- Not given: world coordinates, any object's position, masses, friction, the goal check before the episode ends.
  A room camera (`RCB_OBS_ROOM_CAMERA=1`, never overhead) exists as a setting and is off.

World-frame information: privileged mode gives KinDER's world state. Standard mode gives none: odometry starts at the
robot's start pose, and goals are named by what the cameras see.

## Grading

- **Privileged.** `tests/grade.py` replays `/app/output/trajectory.npz` once, open-loop, from `tests/instance.json`
  in a fresh process, in a verifier container without network. Pass if KinDER's goal check holds at any step within
  the first 1,000 rows; the replay stops at that step. A missing file, a file for another instance, a wrong shape, a
  non-finite value or a value outside the bounds scores 0.
- **Standard.** The sidecar judges the episode it runs: it ends at the agent's `/finish`, after 1,000 control steps, or
  when the agent's time runs out, and is judged by KinDER's goal check on the state it ends in (`end_judgement =
  "state"`, no settle window). A simulator error from the agent's call is 0. KinDER has no failure terminations.
  `tests/grade.py` transcribes the sidecar's verdict. Standard tasks grant no reset by default (`RCB_RESET_BUDGET=0`);
  a run with `RCB_RESET_BUDGET=N` is a separate configuration.
- The video is one render pass over the trajectory after the verdict (the `task_view` camera) and never changes it.

## Tasks

| family | KinDER environment | challenge | the robot must |
|---|---|---|---|
| dynamo | `Dynamo3D-o3` | nonprehensile | drive into a floor square that three chairs block |
| sweep-into-drawer | `SweepIntoDrawer3D-o5` | nonprehensile, tool, dynamic | sweep five cubes into a drawer of the kitchen island |
| scoop-pour | `ScoopPour3D-o50` | nonprehensile, tool, dynamic | move 50 cubes from one bin to another with a scoop |
| constrained-cupboard | `ConstrainedCupboard3D-o6` | geometric | put six identical rods, each into the compartment it is assigned |
| sweep-simple | `SweepSimple3D-o50` (right side of the kitchen island) | nonprehensile, tool | sweep 50 cubes into a box marked on the floor, with a wiper |

All instances use seed 0 (`i00`; scoop-pour and sweep-simple: `i01`, the o50 variants). Each task's README states its
goal check.

Why these: KinDER's 3D families whose goal a camera can see or a sentence can name (the 2D families move an abstract
planar robot with no real counterpart; LimbRepositioning3D's IKFast module cannot be built in the image), with the
most task objects (upstream's `oN`): scoop-pour 50, sweep-simple 50, constrained-cupboard 6, sweep-into-drawer 5;
every other 3D family has at most 4. Scoop-pour's o100 is not used: it simulates about 5 times slower. Sweep-simple's
o50 has three goals; the one used is upstream's README example (the right side of the kitchen island).
