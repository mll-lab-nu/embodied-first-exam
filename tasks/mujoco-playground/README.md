# MuJoCo Playground

## Overview

Environments from MuJoCo Playground (Zakka et al., 2025), Google DeepMind's GPU-scale RL suite, rebuilt in plain MuJoCo
on the CPU: nine quadruped locomotion environments and four manipulation environments. Each one is a task family with
one frozen instance and a binary pass condition that this benchmark defines (Playground has shaped rewards only).

| | |
|---|---|
| upstream | [MuJoCo Playground](https://playground.mujoco.org/) (`google-deepmind/mujoco_playground` @ `4057c14`, Apache-2.0), with MuJoCo Menagerie @ `1b86ece` (the commit Playground pins) |
| simulator | MuJoCo 3.3.7, CPU physics (bit-exact replay); EGL rendering on a GPU, else OSMesa |
| robots | `unitree-go1` (Unitree Go1), `boston-dynamics-spot` (Boston Dynamics Spot), `google-barkour-vb` (Google Barkour vB): 12 joint position actuators each; `aloha-2` (ALOHA 2, two arms, 14 actuators); `franka-panda` (Franka Emika Panda, 8 actuators) |
| score | binary: the pass condition of each environment, defined here (Changes from upstream) |
| tasks | 13 families, 27 task directories: `tasks/mujoco-playground/mujoco_playground_<env>-privileged` and `-standard` for every family; BarkourJoystick, the one dynamic environment, also `-realtime` |
| images | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.3` (quadrupeds; `images/mujoco/`: 0.1.2 plus Playground's `locomotion/{go1,spot}` scenes and Menagerie's Go1, Spot and Barkour, every 0.1.2 file unchanged); `ghcr.io/mll-lab-nu/efe:mujoco-0.1.2` (manipulation) |
| oracle | full, every task |

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/mujoco-playground -a <agent> -m <model>
```
Every image is public: Harbor pulls it.

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the simulator (`rcb_quadruped`, `rcb_aloha` or `rcb_panda` `Session`) and its full state | unlimited | its `trajectory.npz`, replayed once in the verifier |
| standard | cameras and the robot's own sensors through a client; quadrupeds also the feet's kinematics | quadrupeds 10 (`RCB_RESET_BUDGET`); manipulation none | the last episode, as the service ran it (live; nothing replayed) |
| realtime (BarkourJoystick only) | as standard, minus the kinematics, plus the joystick command in the proprioception; time does not stop (S = 1) | 10 (`RCB_RESET_BUDGET`) | the last episode, as the service ran it (live) |

## Upstream and license

- MuJoCo Playground, [google-deepmind/mujoco_playground](https://github.com/google-deepmind/mujoco_playground), pinned at
  `4057c14`: Apache License 2.0. Citation: Zakka et al., 2025, "MuJoCo Playground: An open-source framework for
  GPU-accelerated robot learning and sim-to-real transfer".
- Robot models from MuJoCo Menagerie, [google-deepmind/mujoco_menagerie](https://github.com/google-deepmind/mujoco_menagerie)
  @ `1b86ece`, each under its own license: Unitree Go1 (BSD 3-Clause, Unitree Robotics), Boston Dynamics Spot
  (BSD 3-Clause, Clearpath Robotics), Google Barkour vB (Apache License 2.0, DeepMind), ALOHA 2 (BSD 3-Clause, Trossen
  Robotics), Franka Emika Panda (Apache License 2.0).
- The rough-terrain texture is Poly Haven's (CC0). No non-commercial terms apply anywhere.
- `images/mujoco/prepare_assets.sh` clones both repositories at those commits and copies only the scene XMLs, the robot
  models and their licenses into the image (`/opt/rcb_mj`); Playground's training code and policies are not in it.

## Changes from upstream

### Success: defined by this benchmark

Upstream MuJoCo Playground defines, for every one of these 13 environments, only a shaped training reward and a
termination rule: there is no success test. The binary pass condition of each family is this benchmark's own,
built from Playground's termination rules, reward targets and scene geometry. It is defined in the tooling's
`Session.check()` and applied by the graders:

| families | condition defined in | privileged grader | standard / realtime verdict |
|---|---|---|---|
| quadrupeds | `privileged/environment/rcb_quadruped.py` (`check`, `terminated`) | `privileged/tests/grade.py` | `sim/server.py` + `standard/tests/grade.py`; realtime: the task's `environment/sim/server.py` on the sidecar service `rcb_service.py` (`standard-files`) |
| ALOHA | `privileged/environment/rcb_aloha.py` (`check`, `_check_handover`) | `privileged/tests/variants/72df271117/grade.py` | `sim/server_mj.py` + DexToolBench's `standard/tests/grade.py` (shared MuJoCo verifier) |
| Panda | `privileged/environment/rcb_panda.py` (`check`) | `privileged/tests/variants/c5bde2d42e/grade.py` | as ALOHA |

Paths are under `embodied_first_exam/benchmarks/mujoco-playground/` (DexToolBench's under
`embodied_first_exam/benchmarks/dextoolbench/`). The conditions in short (each task README has the full text):

| family | pass condition |
|---|---|
| joystick (Go1 flat and rough, Spot flat, Spot gait tracking, Barkour) | all 1000 control steps with no termination; in every command segment, after its first 25 control steps, mean planar velocity error ≤ 0.2 m/s and mean yaw-rate error ≤ 0.3 rad/s (IMU velocimeter and gyro); gait tracking also mean RMS foot-height error to Playground's gait curve (`gait.get_rz`) ≤ 0.05 m |
| getup (Go1, Spot) | the last 25 control steps all with the trunk tilted ≤ 10° and the IMU ≥ 0.22 m (Go1; it stands at 0.255-0.26 m with Playground's gains) or ≥ 0.40 m (Spot; 0.44 m) above the floor |
| handstand / footstand (Go1) | no termination; the last 100 control steps (2 s) all with the trunk's forward axis within 30° of straight down / up, the IMU ≥ 0.40 m (Playground aims at 0.55 / 0.53 m) and the feet of the lifted pair off the floor |
| AlohaHandOver | at the end: the box < 3 cm from the target, touching a right-gripper finger and nothing of the left arm, its centre ≥ 0.05 m high |
| AlohaSinglePegInsertion | at the end: the peg tip < 5 mm from the socket axis, axial parameter −0.875 ≤ t ≤ 0.75 (inside the cavity, at least 12 mm in from the open end) |
| PandaPickCubeOrientation | at the end: the box < 2 cm and < 15° from the target |
| PandaOpenCabinet | at the end: the handle < 1.5 cm from the target along the slide (x) |

Terminations: Playground's own fall rules are kept (Go1 joystick: the trunk's up axis below the horizon; Spot: up
axis z below 0.85, about 32°; Barkour: up axis below the horizon, a joint outside its box, the torso under 0.18 m;
Go1 handstand / footstand: up axis z below −0.25 or a front-leg thigh, calf or hip on the floor). Playground's
energy terminations (getup, handstand, footstand) and the manipulation environments' out-of-bounds termination are not
applied. A termination is a failure at any step; the getup families have none.

ALOHA peg insertion: site `socket_rear` is at the tube's centre (t = 0; 0.048 m per unit of t, t = 1 at
`socket_entrance`); the lower bound is the inner face of the rear wall read from the model (t = −0.833) minus
`REAR_MARGIN_M` = 2 mm for the contact's give: −0.875. Playground's shaped reward for it peaks at the tube's centre.

### Scenes, instances and actions

- **Scene.** Playground's scene XML and asset set, loaded the way Playground's `get_assets()` does (bare file names from
  its `xmls/` and Menagerie's robot directory; Barkour: Menagerie's scene plus the foot-contact sensors its environment
  adds), with the drive gains Playground's environment sets (`Kp` as the actuator gain, `Kd` as joint damping; an
  actuator's own `kv` stays). Quadrupeds: one control step = 5 physics steps, 20 ms (Go1, Spot) or 10 ms (Barkour,
  below). ALOHA: 50 Hz control, 8 physics steps (peg insertion, 400 Hz) or 4 (hand-over, 200 Hz); Panda: 50 Hz, 4
  physics steps (200 Hz).
- **Instance.** Quadrupeds: one episode as Playground's own `reset` draws it with `jax.random.PRNGKey(seed)`: the start
  state and, for the joystick tasks, the command schedule (and Barkour's pushes, Spot gait tracking's gait) that the
  environment's command process draws over the episode, its per-step key splits replayed exactly. Getup: the drop's
  start state; the 0.5 s settle runs in the task's own MuJoCo. Manipulation: Playground's reset randomization drawn with
  numpy from the seed (box, peg, socket offsets, targets, the Panda cabinet's arm perturbation). `instance.json` holds
  the start, the schedule, the t = 0 state hash and the numbers the instructions quote.
- **Actions.** Absolute position targets, one row per control step, in actuator order, clipped to the actuator ranges.

### Playground behaviour kept, and where these tasks depart from it

- **Barkour's control step is 10 ms.** Its environment loads Menagerie's scene as is (2 ms timestep) while it takes
  round(ctrl_dt / sim_dt) = 5 substeps with sim_dt = 4 ms, so one step advances 10 ms. Kept: the robot's dynamics are
  the environment's (the push formula still uses ctrl_dt = 20 ms, as upstream).
- **A 1-step Barkour push is zero.** The push is 0.5 sin(pi i / duration) for i = 0 .. duration - 1. Kept; instance
  selection skips instances whose pushes are null or weak.
- **Footstand's termination reads the front-leg list.** `Footstand._post_init` assigns the hind-leg geoms to
  `_unwanted_contact_geom_ids`, but the termination reads the front-leg sensors it inherits. A policy trained on that
  sits on a hind hip with its feet in the air. The task adds the hind-leg rule.
- **Spot gait tracking does not observe the command.** Its observation (69) has no command, yet its reward tracks one.
  The task gives the command (and the gait) to the agent.
- **Hand/footstand targets accumulate** in Playground (ctrl + 0.3 action, unclipped); here actions are absolute targets.

### Added

The standard and realtime modes (a sim sidecar serving the robot), frozen instances, and agent-ended episodes;
upstream has only the RL environments.

## Interface

**Privileged.** The tooling in the agent's container: `rcb_quadruped.Session` (quadrupeds), `rcb_aloha.Session`,
`rcb_panda.Session` (`embodied_first_exam/benchmarks/mujoco-playground/privileged/environment/`): the full simulator on
the frozen instance, its state, unlimited resets, `replay()` and `save_trajectory()`. The deliverable is
`/app/output/trajectory.npz` (`actions`, (T, 12) for a quadruped, (T, 14) ALOHA, (T, 8) Panda), one row per control
step.

**Standard.** The robot is a service in the `sim` sidecar (wire protocol `eai-standard/3.0`), reached through `rcb_client.py` or the `efe-robot` MCP
tools; episodes are agent-ended (`POST /finish`).

- Quadrupeds: `sim/server.py`, the adapter of the shared layer `embodied_first_exam/standard/rcb_limited.py`. Action
  types `joint_position` (12 absolute targets per row) and `done` (ends the episode, as `/finish`). Cameras: Go1 and
  Spot four that follow the robot (`track`, `side`, `back`, `top`); Barkour one that follows it and its head camera;
  RGB 320×240, optional depth. Proprioception: joint positions, velocities and torques, the IMU (gyro, accelerometer,
  gravity's direction, velocimeter), foot contacts; `POST /kinematics`: the feet's FK/IK in the trunk frame. The
  joystick schedule is in `spec["command_schedule"]` and every response's `meta["command_now"]`, the gait in
  `spec["gait"]`; pushes are not announced. 10 resets: `POST /reset` restarts from the frozen start (409 after
  `/finish`, once the agent's time is up and once the budget is spent); the client has no `reset()`, so the
  instructions call `POST /reset` through `Robot._post`. One call returns at most 3000 images (`max_frames_per_call`).
  CPU only: no GPU is reserved.
- Manipulation: `sim/server_mj.py`, shared with DexToolBench. One action type, `joint_position` with the task's own
  actuator layout (ALOHA 14, Panda 8), rows `dt` apart (a multiple of the 1/50 s control step), hold or linear
  interpolation per control step; send actions as float64. `meta.task` carries the target; `meta.cameras` each
  camera's intrinsics (`intrinsic_cv` for the returned image; fx ≠ fy for a camera defined by its sensor size: ALOHA's
  overhead and wrist cameras, 158.52 and 216.45 px) and its camera-to-world pose per returned frame (`cam2world_gl/<cam>`;
  ALOHA's wrist cameras carry `moving`). No reset and no step limit. A GPU on the sidecar renders the cameras (EGL).
- Not given in standard mode: object or target poses, the robot's world pose, the success signal.

**Realtime (BarkourJoystick).** The shared realtime layer (`rcb_realtime.py`, `rcb_client.py` from
`embodied_first_exam/standard/realtime/`; `rcb_service.py` from `embodied_first_exam/standard/sidecar/`, all in `standard-files`) with the task's own `environment/sim/server.py`, which
implements the simulator on `rcb_quadruped.Session`: the same instance, schedule, pushes, termination rule and check.
The proprioception adds `cmd_vx`, `cmd_vy`, `cmd_wz` (the command in force). Not served: `/kinematics`, per-frame
camera poses, depth modes and the `done` action. Slowdown S = 1 (one 10 ms control step every 10 ms of wall time),
10 resets; the service's RTF on 4 CPUs is 31.6 with the clock flat out. The `sim` service reserves a GPU for EGL
rendering.

## Grading

- **Privileged.** `tests/grade.py` in a separate sandbox without network: one open-loop replay of `trajectory.npz`
  from the verifier's own copy of the instance (`tests/instance.json`; the start state is checked against its hash),
  in a fresh process; pass iff the check holds on that replay. A file that cannot be read as an npz with a numeric
  `actions` array of the right width, more rows than allowed (the horizon for a quadruped, 3000 for manipulation) or a
  non-finite value is `bad_trajectory` (0). A replay process that died or timed out (`replay_failed`), a rebuilt start
  that does not match the instance's hash (`instance_mismatch`) and an exception of the verifier set `grader_error = 1`
  (the quadruped grader also `infra_error = 1`). A video is rendered after the verdict and never changes it.
- **Standard.** The verdict is the live episode's: the service runs the task's check on the episode it ran, when the
  episode ends, and writes it to `final.json` (`graded_by = "live"`, `replays = 0`); `tests/grade.py` passes iff that
  check succeeded. Quadrupeds: the episode ends at `/finish` or `done`, at the horizon, on a termination (0) or when the
  agent's time is up; the check is `rcb_quadruped.Session.check()` on the steps executed, so a getup or stand pose
  must be held through the last steps and a joystick episode passes only at the horizon. Manipulation: the episode ends
  at `/finish` or when the agent's time is up; the check is the tooling's `check()` of the final state. A simulator
  error from a call is the agent's 0. A start state that does not hash to the instance's `state_sha` gets no episode
  (`instance_mismatch`, `infra_error = 1`).
- **Realtime.** The shared layer's live verdict (`rcb_service`): `server.py`'s `step()` reports `check()` after every
  control step (joystick: success only at the horizon); its `start_sha` is the instance's `state_sha`.

## Tasks

| robot | environment | what it asks | horizon | instance |
|---|---|---|---|---|
| Go1 | Go1JoystickFlatTerrain | track a joystick schedule (4 segments) on flat ground | 1000 steps, 20 s | seed 0 |
| | Go1JoystickRoughTerrain | the same (7 segments) on a 20 x 20 m heightfield, bumps up to 5 cm | 1000, 20 s | seed 1 |
| | Go1Getup | get up from a drop (lying tilted 110°) and stand | 300, 6 s | seed 5 |
| | Go1Handstand | balance on the front legs, nose down, for 2 s | 500, 10 s | seed 0 |
| | Go1Footstand | stand on the hind legs, nose up, for 2 s | 500, 10 s | seed 0 |
| Spot | SpotFlatTerrainJoystick | track a joystick schedule (5 segments) | 1000, 20 s | seed 0 |
| | SpotGetup | get up from a 1 m drop (lying tilted 128°) and stand | 300, 6 s | seed 1 |
| | SpotJoystickGaitTracking | joystick tracking with a commanded gait (here pace at 3.66 Hz, 0.129 m swing) | 1000, 20 s | seed 0 |
| Barkour | BarkourJoystick | joystick tracking (2 segments) through 12 pushes of up to 35 N | 1000, 10 s | seed 2 |
| ALOHA 2 | AlohaHandOver | pick up the box with the left arm, pass it to the right arm, hold it at the target | at most 3000 rows (privileged) | seed 60417 |
| | AlohaSinglePegInsertion | push the peg into the open end of the socket | at most 3000 rows (privileged) | seed 60417 |
| Panda | PandaPickCubeOrientation | put the box at the target box, in its orientation | at most 3000 rows (privileged) | seed 60417 |
| | PandaOpenCabinet | pull the handle along its slide to the target | at most 3000 rows (privileged) | seed 60417 |

The manipulation tasks also allow seeds 60418 and 60419 (`[metadata.seeds]`; committed under the privileged task's
`tests/seeds/`).

## Others

- **Instance selection** (never looking at an agent's result): seeds in order; skip a joystick schedule that is mostly
  standstill (under half the episode commanding |v_xy| >= 0.3 m/s or |w_z| >= 0.3 rad/s), Barkour pushes that are null
  or weak (peak under 20% of the torso's weight), a getup start that is not a fall (no drop, or tilted under 90°), and
  any seed whose reference fails.
- **Reference solutions.** Go1 joystick: Playground's own Go1 joystick policy (`experimental/sim2sim/onnx/go1_policy.onnx`),
  closed loop on the frozen instance, its targets recorded. The other quadruped references come from policies trained
  here on re-implementations of Playground's environments; the manipulation references are scripted. No image contains
  a policy, and every reference row is float32-exact, so the standard oracle (streaming the rows through the client)
  records exactly the privileged reference. The PyPI packages `playground` and `envpool` carry Playground's task
  sources (the honour rule, docs/protocol/tasks.md#instructionmd).
- **Files.** The privileged task's `environment/instance.json` and `tests/instance.json` and a standard or realtime
  task's `environment/sim/instance.json` are byte-identical copies of the frozen instance. The shared code lives in
  `embodied_first_exam/benchmarks/mujoco-playground/` and reaches the tasks through the files-only image
  `efe:mujoco-playground-files` (`images/mujoco-playground-files/FILES.json`): the tooling (`privileged/environment/`),
  the graders (`privileged/tests/`, `standard/tests/grade.py`), the standard services (`sim/server.py`,
  `sim/server_mj.py`), the collect hook (`sim/finalize.sh`) and the video pass (`sim/video.py`). The realtime service base
  (`rcb_service.py`) comes from `standard-files`.
