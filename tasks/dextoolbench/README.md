# DexToolBench

## Overview

Twenty-one tasks of DexToolBench, the dexterous tool-use benchmark of SimToolReal, in plain MuJoCo, each in two modes:
42 task directories, `dextoolbench_<category>_<object>_<task>-privileged` and `-standard`. A KUKA iiwa 14 arm with a
left Sharpa HA4 hand (29 position-controlled joints, control at 60 Hz) stands next to a table with a tool on it. A
task is one human demonstration from DexToolBench: the tool's start pose and a sequence of goal poses of the tool. The
robot must pick the tool up and carry it through every goal pose, in order. Each task has one fixed instance (seed 0):
the start and the goals come from the demonstration, with no randomization. Both modes of a task share the scene, the
instance and the rule for reaching a pose.

- **privileged**: the agent has the full simulator (`rcb_dtb.Session`), its state and free resets, and hands in one
  trajectory of joint targets, which the verifier replays open-loop.
- **standard**: the simulator runs in a `sim` sidecar the agent cannot open. The agent gets the robot's four cameras
  (RGB-D, calibrated), its proprioception and the current goal pose, through `rcb_client.py` or the same service as
  MCP tools. It has 20 resets; the last episode is graded live.

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/dextoolbench -a <agent> -m <model>
```
Every image is public: Harbor pulls it.

Images: the privileged task (agent and verifier) and the standard `sim` sidecar run on `ghcr.io/mll-lab-nu/efe:mujoco-0.1.2`
(MuJoCo 3.3.7 and the assets, `images/mujoco/`), with the tooling copied from the pinned files image
`efe:dextoolbench-files-0.8.0`. The standard agent container is `python:3.12-slim` with the client only. Physics runs on
the CPU; one NVIDIA GPU (5 GiB of its memory, any 8 GB+ card) is used for EGL rendering of camera images and videos, by
`main` in privileged mode and by `sim` in standard mode. The tooling falls back to OSMesa (CPU) rendering when EGL is
not available.

## Upstream and license

- Upstream: SimToolReal / DexToolBench, [tylerlum/simtoolreal](https://github.com/tylerlum/simtoolreal) pinned at
  `313d5ae`. MIT License (Copyright (c) 2026 Tyler Lum). Citation: Kedia, Lum, Bohg and Liu, 2026, "SimToolReal: An
  Object-Centric Policy for Zero-Shot Dexterous Tool Manipulation", arXiv:2602.16863. Used here: the tool meshes
  (convex-decomposed collision meshes), the goal trajectories (`dextoolbench/trajectories/`) and the left Sharpa HA4
  hand model (`images/mujoco/prepare_assets.sh`). SimToolReal's training code and pretrained policy are not in the
  image.
- Robot arm: KUKA iiwa 14 from MuJoCo Menagerie @ `1b86ece` (BSD 3-Clause License).
- Simulator: MuJoCo 3.3.7 (Apache License 2.0).
- No non-commercial terms apply.

## Changes from upstream

- **Simulator.** Upstream evaluates DexToolBench in Isaac Sim / Isaac Gym. Here the scene is rebuilt in plain MuJoCo
  from SimToolReal's own sim-to-sim scene (`deployment/mujoco/mujoco_sim.py`), without its training stack
  (`rcb_dtb.build_model`): the iiwa 14 with the Sharpa HA4 hand at its flange, base at (0, 0.8, 0); a 0.475 × 0.4 ×
  0.3 m table, top at z = 0.53 m; the tool with its convex-decomposed meshes; a green goal marker without contacts.
  Physics at 600 Hz (implicitfast, elliptic cones, multi-CCD, gravity-compensated robot), control at 60 Hz (10 physics
  steps per control step). For the claw hammer's swing_down, the pretrained policy's final state hash in this scene,
  before the table props were added, equals the one in SimToolReal's own MuJoCo scene (`b8acca987fcd`).
- **Table props.** SimToolReal's own sim-to-sim scene has none. Here each tool category gets the props of its
  SimToolReal table URDF: one 3 × 3 × 6 cm nail for the hammers (`table_narrow_nail`), a 2 × 40 × 40 cm whiteboard at
  the table's +x edge for the erasers and markers (`table_narrow_whiteboard`), a bowl and a plate for the spatulas
  (`table_narrow_bowl_plate`), and a plain table for the brushes and screwdrivers. The YCB bowl and plate meshes are not
  in the SimToolReal repository, so primitive shapes of YCB's size stand in for them.
- **Start pose.** One task, the flat spatula's flip_over, starts from a raised pose resting on the plate and the bowl's
  rim: the demonstration's start, flat on a bare table, would put the spatula inside the stand-ins. Every other start
  pose and every goal pose is upstream's.
- **Reaching a pose.** Upstream's evaluation rule is kept: the fixed-size keypoint box (1.5 × 0.141 × 0.03025 × 0.0271
  m, the same for every tool), a tolerance of 1.5 cm (evaluation tolerance 0.01 m × keypoint scale 1.5) on the largest
  of the 8 corner distances, and one control step near the goal (`success_steps = 1`). Upstream compares with "at
  most"; here the distance must be less than 1.5 cm.
- **Time per goal.** Upstream gives each goal 10 s (600 control steps) and ends the episode when one is missed. The
  privileged tasks give each goal 30 s (1,800 control steps); the standard tasks have no per-goal limit, a cap of
  360,000 control steps per episode (100 min of robot time) and 20 resets. The two modes share the rule for reaching a
  pose but not this time rule.
- **Episode end.** Upstream's episode ends when the last goal is reached. The privileged replay stops there too. In
  the standard tasks reaching the last goal ends nothing and is not shown; the agent ends the episode.
- **Task selection.** 21 of DexToolBench's 24 demonstrations are ported. The other three (`blue_brush/sweep_right`,
  `flat_eraser/wipe_c`, `flat_eraser/wipe_smile`) are not: SimToolReal's pretrained policy reaches none of their goals
  in this scene, so they would have no reference trajectory.

## Interface

Both modes: world frame in metres, z up; poses are x y z qx qy qz qw. An action is 29 joint position targets in the
order of `rcb_dtb.JOINT_NAMES`: `joint1..joint7` (iiwa), then the 22 hand joints (thumb `CMC_FE, CMC_AA, MCP_FE,
MCP_AA, IP`; index, middle and ring `MCP_FE, MCP_AA, PIP, DIP`; pinky `CMC, MCP_FE, MCP_AA, PIP, DIP`, all prefixed
`palmleft_`), clipped to the actuator ranges. Cameras: `front`, `side`, `top`, `oblique`, all fixed, RGB 240 × 320.

**Privileged.** `/opt/tools/rcb_dtb.py`: `Session("/app/instance.json")` builds the scene at the frozen start;
`s.model` / `s.data` are the MuJoCo objects, `s.state()` the robot, tool and goal state, `s.goals` every goal pose.
`s.step(targets)` runs one control step and returns the goal progress; `s.reset()` returns to the start (no limit);
`s.record_start()`, `s.record_stop()`, `s.save_trajectory(A)` write `/app/output/trajectory.npz`; `s.replay(A)` replays
as the verifier does; `s.render(camera)` and `s.render_video(A, path)` render. The deliverable is `(T, 29)` float64
targets, one row per control step, at most 360,000 rows; MuJoCo on the CPU replays it bit-exactly from the frozen start.
Every Session writes a self-reported session log and rollout traces under `/logs/agent/rcb/`; the verifier turns
them into cost counts and videos, which never change the verdict.

**Standard.** The service is `embodied_first_exam/benchmarks/dextoolbench/sim/server_mj.py`, the same file as the
MuJoCo Playground tasks' service (`ci_checks/check-tooling-identity.sh` keeps the copies identical). It serves the
standard protocol (`eai-standard/3.0` rules: agent-ended episodes, hold chunks) through the shared client and MCP
tools. Differences from the other services:
- one action type, `joint_position` (29 values), rows `dt` apart (a multiple of 1/60 s), held or linearly interpolated
  per control step; at most 10 s per chunk; actions are sent as float64, since float32 rounding changes a fast tool
  swing;
- `meta["task"]`: the current goal pose, `goal_index`, `n_goals`, `goals_reached`, `steps_left_on_goal` (null: no
  per-goal limit). After the last goal is reached it stays the current goal and `goals_reached` stops one short;
- `meta["cameras"]`: each camera's `intrinsic_cv` and `cam2world_gl`; depth in metres on request. Never the tool's pose;
- resets (`POST /reset`, `RCB_RESET_BUDGET`, default 20): each starts a new episode from the frozen start (robot at
  home, tool at its start, first goal current); after `/finish` or the end of the agent's time no reset is accepted;
- episode cap `RCB_MAX_CONTROL_STEPS` = 360,000 control steps per episode, then `submit` is refused until a reset.

## Grading

**Privileged.** `tests/grade.py` loads `/app/output/trajectory.npz` and replays it once from `tests/instance.json` with
the verifier's own copy of `rcb_dtb.py`, in a separate container without network. The goal tracker
(`rcb_dtb.Session._track`) runs after every control step: the current goal counts when the largest keypoint-corner
distance is below 1.5 cm, then the next goal is current; a goal not reached within 1,800 control steps ends the replay
as a failure. `reward.txt` = 1 when every goal is reached; `reward.json` also records `progress` (goals reached /
goals). A missing file (`missing_trajectory`) or an unreadable or malformed one (`bad_trajectory`) scores 0; an
exception in the grader scores 0 with `grader_error`. Videos of the replay and of the agent's last rollouts are
rendered after the verdict and never change it.

**Standard.** The verdict is the live episode's (`graded_by = "live"`, nothing replayed). The service runs the same
goal tracker on every control step it executes, with no per-goal limit. The episode ends at `POST /finish`
(`finished`), at the cap (`step_limit`) or when the agent's session ends (`timeout`); it passes when every goal was
reached, in order, during the last episode. A simulator error (`error`) or repeated crashes inside the agent's calls
(`sim_crashed_on_call`) score 0. The frozen start is checked by its state hash (`RCB_START_SHA` in the compose file,
`Session.state_sha()` over qpos and qvel) before the agent is served; a mismatch (`instance_mismatch`), crashes between
calls, a failed resume or a missing verdict are infrastructure failures (`infra_error`). `tests/grade.py` transcribes
`/data/final.json`. Re-measure `RCB_START_SHA` when the tooling, an instance or the image changes.

## Tasks

Each row is one task in both modes (`-privileged`, `-standard`). Goals: the number of goal poses. Reference: the goals
reached by SimToolReal's pretrained policy, replayed in this scene (`solution/`, also in each task.toml's
`oracle_evidence`); a task whose reference reaches every goal has `oracle = "full"`, the others `oracle = "partial"`.

| task | category | object | demonstration | goals | reference |
|---|---|---|---|---|---|
| `dextoolbench_brush_blue_brush_sweep_forward` | brush | blue_brush | sweep_forward | 34 | 8/34 |
| `dextoolbench_brush_red_brush_sweep_forward` | brush | red_brush | sweep_forward | 38 | 20/38 |
| `dextoolbench_brush_red_brush_sweep_right` | brush | red_brush | sweep_right | 38 | 19/38 |
| `dextoolbench_eraser_handle_eraser_wipe_c` | eraser | handle_eraser | wipe_c | 31 | 12/31 |
| `dextoolbench_eraser_handle_eraser_wipe_smile` | eraser | handle_eraser | wipe_smile | 29 | 29/29 |
| `dextoolbench_hammer_claw_hammer_swing_down` | hammer | claw_hammer | swing_down | 37 | 37/37 |
| `dextoolbench_hammer_claw_hammer_swing_side` | hammer | claw_hammer | swing_side | 40 | 13/40 |
| `dextoolbench_hammer_mallet_hammer_swing_down` | hammer | mallet_hammer | swing_down | 36 | 12/36 |
| `dextoolbench_hammer_mallet_hammer_swing_side` | hammer | mallet_hammer | swing_side | 32 | 5/32 |
| `dextoolbench_marker_sharpie_marker_draw_smile` | marker | sharpie_marker | draw_smile | 36 | 36/36 |
| `dextoolbench_marker_sharpie_marker_write_c` | marker | sharpie_marker | write_c | 25 | 25/25 |
| `dextoolbench_marker_staples_marker_draw_smile` | marker | staples_marker | draw_smile | 49 | 49/49 |
| `dextoolbench_marker_staples_marker_write_c` | marker | staples_marker | write_c | 29 | 19/29 |
| `dextoolbench_screwdriver_long_screwdriver_spin_horizontal` | screwdriver | long_screwdriver | spin_horizontal | 31 | 31/31 |
| `dextoolbench_screwdriver_long_screwdriver_spin_vertical` | screwdriver | long_screwdriver | spin_vertical | 100 | 27/100 |
| `dextoolbench_screwdriver_short_screwdriver_spin_horizontal` | screwdriver | short_screwdriver | spin_horizontal | 38 | 15/38 |
| `dextoolbench_screwdriver_short_screwdriver_spin_vertical` | screwdriver | short_screwdriver | spin_vertical | 76 | 36/76 |
| `dextoolbench_spatula_flat_spatula_flip_over` | spatula | flat_spatula | flip_over | 45 | 22/45 |
| `dextoolbench_spatula_flat_spatula_serve_plate` | spatula | flat_spatula | serve_plate | 33 | 9/33 |
| `dextoolbench_spatula_spoon_spatula_flip_over` | spatula | spoon_spatula | flip_over | 40 | 6/40 |
| `dextoolbench_spatula_spoon_spatula_serve_plate` | spatula | spoon_spatula | serve_plate | 48 | 13/48 |

## Others

- Agent egress is closed to everything but the model APIs and the package registries, because SimToolReal's pretrained
  policy is publicly downloadable.
