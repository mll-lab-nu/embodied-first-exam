# KinDER

Physical reasoning for robot planning and control, kept apart from perception and language: tool use, non-prehensile
multi-object manipulation, geometric and dynamic constraints.

| | |
|---|---|
| upstream | [KinDER](https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden) (RSS 2026, [arXiv 2604.25788](https://arxiv.org/abs/2604.25788)), MIT, pinned at `5b2dbac` |
| simulator | MuJoCo 3.3 (Dynamic3D) in KinDER's MimicLabs lab, CPU physics |
| robot | TidyBot++: holonomic base, Kinova Gen3 7-DoF arm, Robotiq 2F-85 gripper; delta actions (MuJoCo: 10 Hz) |
| score | pass = KinDER's own goal check within the episode (1000 control steps) |
| tasks | 5 families × 2 modes: `tasks/kinder-<family>-i00-privileged` (scoop-pour, sweep-simple: `-i01-`) and `-standard` (`eai-standard/2.1`) |
| image | `ghcr.io/mll-lab-nu/eai-kinder:0.1.6` (`images/kinder/`, 4.6 GB with the lab scenes) |
| oracle | `dynamo` (the fixture): full, both modes; the other four: none, human review (positive examples below; scoop-pour and sweep-simple: none yet, unvalidated) |

## Tasks (one variant each, seed 0)

| family | challenge | the robot must | positive example |
|---|---|---|---|
| dynamo | nonprehensile | drive into a floor square that three chairs block (fixture) | oracle, both modes; Luna, both |
| sweep-into-drawer | nonprehensile, tool, dynamic | open a drawer, sweep five cubes into it | Luna, privileged (2026-10-04); run `codex-gpt6_1_sol-high`, standard (2026-10-03, no reset) |
| scoop-pour | nonprehensile, tool, dynamic | move 50 cubes between bins with a scoop | none yet (`i01`, 2026-10-16) |
| constrained-cupboard | geometric | six identical rods, each into the compartment it is owed | Luna, privileged only |
| sweep-simple | nonprehensile, tool | fifty cubes into a box marked on the floor, with a wiper | none yet (`i01`, 2026-10-16) |

Why these (no model's results enter the choice):
- **Valid:** KinDER's 3D families whose goal a camera can see or a sentence can name (the 2D ones move an abstract
  planar robot with no real counterpart; LimbRepositioning3D's IKFast module cannot be built in our image).
- **Most task objects (upstream's `oN`):** scoop-pour 50, sweep-simple 50, constrained-cupboard 6, sweep-into-drawer 5;
  every other 3D family has at most 4.
- **Variant:** both cube families use their o50 variant (author, 2026-10-16; before, scoop-pour o30 and sweep-simple
  o10); sweep-simple's o50 has three goals, and the one used is upstream's README example (the right side of the
  kitchen island). Scoop-pour's o100 is not used: it simulates about 5x slower, and known 30-cube solutions already use
  770 and 845 of the 1000 control steps. Cupboard (o1-o6) and drawer (o5 only) are at their largest.
- Per-task reasons: `scripts/kinder/subset.toml`.

Positive examples are runs published on the results
site; each scores 1 under today's privileged verifier, and "both" means it also passes when sent through the
standard client. "privileged only": the trajectory moves the base diagonally by up to 0.14 m a step, which standard
mode clips to a 0.1 m disc (the largest move that stays in upstream's per-axis bound after the odometry rotation).

### Open: tasks without a positive example in their own mode (PROTOCOL §2.7, §4)

Scoop-pour and sweep-simple (`i01`, o50, 2026-10-16) have no positive example yet in either mode: they are unvalidated
(`[metadata] validated = false`) until a human review records one, and are ranked with the validated tasks (PROTOCOL
§2). Every other family has one (human review, §2.7: per family, at least one), so its predicate and instance are known
to be solvable. One standard twin has none of its own yet:

- `kinder-constrained-cupboard-i00-standard`. Its privileged example moves the base by up to 0.14 m a step.

## Modes

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the simulator, its full state (`get_state`/`set_state`) and the goal check | unlimited | its `trajectory.npz`, replayed twice in a fresh process |
| standard | the robot's own sensors, through `rcb_client.py`; no world coordinates, no goal check | 0 (author, 2026-10-16; the protocol's default; 10 from 2026-10-11) | the last episode, replayed in a fresh simulator |

World-frame information (PROTOCOL D7): privileged mode gives KinDER's world state; standard mode gives none -- odometry
starts at the robot's start pose, and the goal is named by what the cameras see. One exception since 2026-10-16: where
the goal is a translucent region marked on the floor (dynamo's green square, sweep-simple's grey box), faint in the
robot's cameras, the standard instruction states its centre, size (and the box's height) in the odometry frame at t = 0,
measured on the frozen instance (`gen_tasks.py measure`, facts.json `goal_region`).

| standard mode: given (a real TidyBot++ has it) | not given |
|---|---|
| the task sentence: goal and success condition; dynamo's and sweep-simple's marked goal region at t = 0 (odometry frame) | any object's position; the other goals' positions |
| `robot_base` RGB, `robot_wrist` RGB-D (the Gen3's RealSense D410), 480×640 | world coordinates; a room camera (`RCB_OBS_ROOM_CAMERA=1`, never overhead) is a knob, off |
| base odometry (pose, velocity), arm joint angles and velocities, finger position | the goal check before the episode ends (`success` / `failed` only) |
| `spec()`: action layout and bounds, arm joint axes, positions, limits and torques, the grasp point, camera fields of view and poses, control rate, episode length, budget | masses, friction, the simulator |

## Run

```bash
harbor run -p tasks/kinder-scoop-pour-i01-standard -a codex -m openai/gpt-6-luna --env-file .env
harbor run -p tasks/kinder-dynamo-i00-privileged -a oracle      # or -a nop: scores 0
```
Agent, provider and effort settings: docs/RUNNING.md. Agent time cutoff: 1800 s in both modes (author, 2026-10-16;
3600 s before). Standard tasks grant no reset by default (author, 2026-10-16; the protocol's default): one episode, whose 1000 control steps the practice and the graded attempt share;
`RCB_RESET_BUDGET=N harbor run ...` runs a configuration with N resets, whose results are reported separately (the shipped instruction describes the default, one episode; for N > 0 regenerate the tasks with `RESET_BUDGET = N`, which renders the reset rules and `r.reset()`). Build the image: `docker build -f images/kinder/Dockerfile -t
ghcr.io/mll-lab-nu/eai-kinder:$(cat images/kinder/VERSION) .` (from the repository root).

## Results

Agent results are not kept in this repository (PROTOCOL D3): per-run READMEs (verdict, cost, what happened),
`reward.json`, the replay's last frame and videos are published on the results site, keyed by run id. Standard-mode
runs with none (the default from 2026-10-16), with 10 (the default 2026-10-11 to 2026-10-16) and with 50 (the
optional capability before it) are reported separately (PROTOCOL D1), as are runs with the 3600 s cutoff (before 2026-10-16), and runs recorded before
protocol v1.0 are marked as such.

## Standard-mode service details (moved from STANDARD_MODE.md, 2026-10-14)

**KinDER and HumanoidBench service (`eai-standard/2.1`).** Same endpoints, RCB1 frames and crash recovery, served by one
shared service (`scripts/{kinder,humanoidbench}/shared/standard/rcb_service.py`, identical in both) with a per-benchmark
simulator adapter (`server.py`). Actions are delta or joint-position rows at the task's control rate (KinDER 10 Hz,
PyBullet tasks kinematic: a refused move comes back `blocked` and stops the chunk; HumanoidBench 50 Hz); the step
counters are `rows` and `control_steps`. No world coordinates are given (odometry and camera poses are in the robot's
starting frame). A request body over 64 MB gets 413 before it is decoded. The service implements the optional reset
capability (`RCB_RESET_BUDGET`).
