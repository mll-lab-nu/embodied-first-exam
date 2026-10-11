# MuJoCo Playground

GPU-scale RL environments from Google DeepMind, here in plain MuJoCo on the CPU. This page covers the quadruped
locomotion tasks (`scripts/mujoco-playground/`); the four manipulation tasks (`mujoco_playground_{aloha,panda}_*`,
ALOHA and Franka Panda, scripted IK references, `eai-standard/2.1`) predate it and are made by hand.

| | |
|---|---|
| upstream | [MuJoCo Playground](https://playground.mujoco.org/) (Apache-2.0) @ `4057c14`, with MuJoCo Menagerie @ `1b86ece` (the commit Playground pins) |
| simulator | MuJoCo 3.3.7, CPU physics (bit-exact replay); EGL rendering on a GPU, else OSMesa |
| robots | `unitree-go1` (Unitree Go1), `boston-dynamics-spot` (Boston Dynamics Spot), `google-barkour-vb` (Google Barkour vB); 12 joint position actuators each |
| score | binary, defined here from Playground's termination rules and reward targets (Playground has shaped RL rewards only) |
| tasks | Playground's 9 quadruped environments × 2 modes: `tasks/mujoco_playground_<env>-privileged` and `-standard` (`eai-standard/2.2`) |
| image | `ghcr.io/mll-lab-nu/eai-mujoco:0.1.3` (`images/mujoco/`: 0.1.2 plus Playground's `locomotion/{go1,spot}` scenes and Menagerie's Go1, Spot and Barkour; every 0.1.2 file is unchanged) |
| oracle | full, both modes |

## Tasks

| robot | environment | what it asks | horizon | instance | reference |
|---|---|---|---|---|---|
| Go1 | Go1JoystickFlatTerrain | track a joystick schedule (4 segments) on flat ground | 1000 steps, 20 s | seed 0 | Playground's Go1 policy |
| | Go1JoystickRoughTerrain | the same (7 segments) on a 20 x 20 m heightfield, bumps up to 5 cm | 1000, 20 s | seed 1 | Playground's Go1 policy |
| | Go1Getup | get up from a drop (lying tilted 110 deg) and stand | 300, 6 s | seed 5 | trained policy + scripted stand |
| | Go1Handstand | balance on the front legs, nose down, for 2 s | 500, 10 s | seed 0 | trained policy |
| | Go1Footstand | stand on the hind legs, nose up, for 2 s | 500, 10 s | seed 0 | trained policy (training-only changes) |
| Spot | SpotFlatTerrainJoystick | track a joystick schedule (5 segments) | 1000, 20 s | seed 0 | trained policy |
| | SpotGetup | get up from a 1 m drop (lying tilted 128 deg) and stand | 300, 6 s | seed 1 | trained policy |
| | SpotJoystickGaitTracking | joystick tracking with a commanded gait (here pace at 3.66 Hz, 0.129 m swing) | 1000, 20 s | seed 0 | trained policy (command observed) |
| Barkour | BarkourJoystick | joystick tracking (2 segments) through 12 pushes of up to 35 N | 1000, 10 s | seed 2 | trained policy |

## Task definition
- **Scene.** Playground's scene XML and asset set, loaded the way Playground's `get_assets()` does (bare file names from
  its `xmls/` and Menagerie's robot directory; Barkour: Menagerie's scene plus the foot-contact sensors its environment
  adds), with the drive gains Playground's environment sets (`Kp` as the actuator gain, `Kd` as joint damping; an
  actuator's own `kv` stays). One control step = 5 physics steps: 20 ms (Go1, Spot), 10 ms (Barkour, see below).
- **Instance.** One episode as Playground's own `reset` draws it with `jax.random.PRNGKey(seed)` (`make_instances.py`,
  Playground's code): the start state and, for the joystick tasks, the command schedule (and Barkour's pushes, Spot gait
  tracking's gait) that the environment's command process draws over the episode, its per-step key splits replayed
  exactly; the draws do not depend on the physics while the episode does not terminate. Getup: the drop's start state;
  the 0.5 s settle runs in the task's own MuJoCo. `instance.json` holds the start, the schedule, the t = 0 state hash
  and the numbers the texts quote.
- **Selection** (`select_instances.py`, never looking at an agent's result): seeds in order; skip a joystick schedule
  that is mostly standstill (under half the episode commanding |v_xy| >= 0.3 m/s or |w_z| >= 0.3 rad/s), Barkour pushes
  that are null or weak (peak under 20% of the torso's weight), a getup start that is not a fall (no drop, or tilted
  under 90 deg), and any seed whose reference fails. Every task's skipped seeds and why: `scripts/mujoco-playground/selection/`.
- **Actions.** 12 absolute joint position targets per control step, in actuator order; clipped to the actuator ranges.

## Success
- **Joystick.** T = horizon rows; the robot never meets its environment's termination rule (Go1: the trunk's up axis
  below the horizon; Spot: tilted by more than about 32 deg; Barkour: up axis below the horizon, a joint outside its box
  or the torso under 0.18 m); in every command segment, after its first 25 control steps, the mean planar velocity error
  |v_xy - cmd_xy| <= 0.2 m/s (the IMU's velocimeter, trunk frame) and the mean yaw-rate error |w_z - cmd_wz| <= 0.3 rad/s
  (the IMU's gyro). Gait tracking adds: the mean RMS height error of the feet to Playground's gait curve
  (`gait.get_rz`) at most 0.05 m.
- **Getup.** The trajectory ends with 25 control steps in a row with the trunk tilted at most 10 deg and the IMU at least
  0.22 m (Go1; it stands at 0.255-0.26 m with Playground's gains) or 0.40 m (Spot; 0.44 m) above the floor.
- **Hand/footstand.** The trajectory ends with 100 control steps (2 s) in a row with the trunk's forward axis within 30 deg
  of straight down (handstand) or up (footstand), the IMU at least 0.40 m high (Playground aims at 0.55 / 0.53 m) and the
  feet of the lifted pair off the ground; no termination before: the up axis below -0.25, or a front leg's thigh, calf
  or hip on the floor (Playground's rule), and for the footstand the same for a hind leg (see below).
- Standard episodes end on success (getup, hand/footstand), at the horizon, on a termination (a failure), on `done` or
  on timeout. The joystick schedule is in `spec["command_schedule"]` and every response's `meta["command_now"]`; the gait
  in `spec["gait"]`. Pushes are not announced in standard mode.

## Modes

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the simulator (`rcb_quadruped.Session`) and its full state | unlimited | its `trajectory.npz`, replayed in two fresh processes |
| standard (2.2) | cameras (Go1, Spot: four that follow the robot; Barkour: one that follows it and its head camera; RGB, optional depth), joints, IMU (gyro, accelerometer, gravity's direction, velocimeter), foot contacts; the feet's FK/IK in the trunk frame | none | the service's record of the one episode: live check, two fresh-process replays, determinism |

## Reference solutions
- **Go1 joystick:** MuJoCo Playground's own Go1 joystick policy (`experimental/sim2sim/onnx/go1_policy.onnx`, the one its
  `play_go1_joystick.py` runs in native MuJoCo), closed loop on the frozen instance, its targets recorded (`oracle.py`).
- **The rest:** Playground ships no other quadruped policy. Policies are trained here with PPO on the CPU
  (`scripts/mujoco-playground/train/`: rsl_rl with Playground's hyperparameters; each environment re-implemented in numpy
  with Playground's reset, action mapping, observations and rewards), then run closed loop on the frozen instance.
  - Go1 getup: the policy turns the robot belly-down and level but stops in a crouch (a local optimum of the reward); the
    reference then moves the joint targets linearly to `home` in 1 s.
  - Go1 footstand: trained with three training-only changes: the hind-leg termination this task uses, half of the episodes
    starting in Playground's `footstand` keyframe, and a steeper height reward (with Playground's own it squats at 0.2 m).
  - Spot gait tracking: trained with the command added to the observation (see below).
- Every reference row is float32-exact: the standard client sends actions as float32, so the standard oracle (streaming
  the rows through the client) records exactly the privileged reference.
- Policies only make the references: no image contains one, and the agent's egress is the model APIs and the package registries only (Playground's
  policies are public). The four manipulation pairs have scripted references of our own and were left on Harbor's open
  default until 2026-10-10; they are on the same allowlist now (Change log).

## Playground behaviour kept, and where these tasks depart from it
- **Barkour's control step is 10 ms.** Its environment loads Menagerie's scene as is (2 ms timestep) while it takes
  round(ctrl_dt / sim_dt) = 5 substeps with sim_dt = 4 ms, so one step advances 10 ms. Kept: the robot's dynamics are the
  environment's (the push formula still uses ctrl_dt = 20 ms, as upstream).
- **A 1-step Barkour push is zero.** The push is 0.5 sin(pi i / duration) for i = 0 .. duration - 1. Kept; selection skips
  instances whose pushes are null or weak.
- **Footstand's termination reads the front-leg list.** `Footstand._post_init` assigns the hind-leg geoms to
  `_unwanted_contact_geom_ids`, but the termination reads the front-leg sensors it inherits. A policy trained on that
  sits on a hind hip with its feet in the air. The task adds the hind-leg rule.
- **Spot gait tracking does not observe the command.** Its observation (69) has no command, yet its reward tracks one;
  a policy trained on it marches in place. The task keeps the command (the agent sees it); the reference's policy
  observes it.
- **Hand/footstand targets accumulate** (ctrl + 0.3 action, unclipped); the references follow that, the task's actions
  are absolute targets.

## Verification (2026-10-06, eai-mujoco:0.1.3, Harbor)

| | oracle | nop |
|---|---|---|
| all 9 environments, privileged | 1 (both fresh-process replays succeed, deterministic, video) | 0 (no trajectory) |
| all 9 environments, standard | 1 (live check, both replays, deterministic, replays end in the live state, video) | 0 |

The references' own margins (worst joystick segment, end pose):

| environment | reference |
|---|---|
| Go1JoystickFlatTerrain | 0.073 m/s, 0.091 rad/s |
| Go1JoystickRoughTerrain | 0.079 m/s, 0.114 rad/s |
| Go1Getup | upright after 136 steps, IMU 0.257 m |
| Go1Handstand | 115 steps, 13.8 deg from straight down, IMU 0.531 m |
| Go1Footstand | 113 steps, 9.6 deg from straight up, IMU 0.541 m |
| SpotFlatTerrainJoystick | 0.156 m/s, 0.072 rad/s |
| SpotGetup | upright after 63 steps, IMU 0.478 m |
| SpotJoystickGaitTracking | 0.183 m/s, 0.136 rad/s, foot height 0.038 m |
| BarkourJoystick | 0.033 m/s, 0.028 rad/s |

Outside Harbor, the standard service run on each reference (`std_local` check): live verdict success, and a
fresh-process replay of its record ends in the live state hash. Generator: `python3 scripts/mujoco-playground/generate.py --check`.

## Change log
- 2026-10-10 (review 0067, findings M6, M9 and minors), quadruped standard tasks: `tests/grade.py` writes
  `infra_error = 1` (no verdict on the agent) when `final.json` is missing, unreadable or was never finalized by the
  collect hook (before: a missing one was a plain 0, an unfinalized one was graded as it stood); `finalize.sh` writes
  `final.json` atomically; request fields of the wrong type (`dt` or `seconds` null, `cameras` not a list of names, a
  `note` that is not a string, which failed after the physics had run) are a 400 before any physics instead of a 500
  that ended the episode; `meta["time_left_s"]` counts from the agent's first call (kept through a crash by the
  checkpoints), not from the service's start; Barkour's `/spec` gave the control period of `joint_position` as "1/50 s"
  (it is 0.01 s, as `control_hz`, the `dt` check and the instruction say). Both modes: a `trajectory.npz` that cannot be
  read is `bad_trajectory`, not `grader_error`, and every early exit of the graders writes `deterministic`. The
  quadruped calibration (`data.cam_xpos` / `cam_xmat`, per frame) was already the rendered viewpoint and is unchanged.
- 2026-10-10 (review 0067, findings M4, M6, M7, M9), the tasks served by `images/mujoco/limited/server_mj.py`
  (`mujoco_playground_{aloha,panda}_*-standard` and the 21 `dextoolbench_*-standard` tasks). **Observation change:**
  the calibration's `cam2world_gl` held the position of MuJoCo's left-eye camera (`scene.camera[0]`), 3.4 cm to the side
  of the viewpoint the mono image is rendered from; it now gives that viewpoint, and it is recomputed for every
  response instead of once at start-up, so ALOHA's two wrist cameras (which move with the arms; their pose used to stay
  that of the home pose) are right, with one pose per returned frame in the part `cam2world_gl/<cam>`. Tolerances
  here are 5 mm to 3 cm and the cameras are the only source of object positions, so **standard-mode results from before
  this date are not strictly comparable** with later ones. Also: requests validated in full before any physics
  (`dt = Infinity` and the like were a 500 that ended the episode), `final.json` atomic and `finalized` together with
  the verdict (the video comes after it and sets `video_done`), `infra_error` for a missing / unreadable / verdict-less
  `final.json`, the collect hook's loop inside its timeout (it could run 980 s against 900), the agent's clock counted
  from its first request. The success rules, instances and oracles are unchanged. Each task README has the entries.
  Their privileged twins (`tests/grade.py` only): a `trajectory.npz` that cannot be read as an npz with a numeric
  `actions` array is `bad_trajectory`, not `grader_error`, and every early exit writes `deterministic`; the verdicts
  are the same.
- 2026-10-10 (owner decision, board 0072), the four manipulation pairs (`mujoco_playground_{aloha,panda}_*`, both modes):
  the agent's network egress is the allowlist every task has (`[agent] network_mode = "allowlist"`, the hosts of
  `scripts/set_agent_egress.py`; `scripts/mj_mk_limited.py` writes it for every twin, and the four hand-made privileged
  tasks were switched with `scripts/set_agent_egress.py allowlist`). It was open before, for no technical reason: no
  solution of these four was public, so PROTOCOL §2.7's rule did not ask for an allowlist. With open egress agents cloned
  Playground and MuJoCo Menagerie from their own shell and, in standard mode, rebuilt the task's simulator locally
  (board 0072). Nothing in the containers needs the network at run time: `eai-mujoco:0.1.2` holds the Playground and
  Menagerie files the tooling loads (`/opt/rcb_mj`, `images/mujoco/prepare_assets.sh`), and the standard agent image has
  Python with requests, numpy, pillow and scipy (2026-10-11: PyPI and the apt archives are on the list, so more can be
  installed; the PyPI packages `playground` and `envpool` carry Playground's task sources, PROTOCOL §2.11). Scenes, instances, tooling and pass rules
  are unchanged; results from before this date were obtained with open egress. The quadruped pairs were already on the
  allowlist.

## Files
| | |
|---|---|
| `scripts/mujoco-playground/shared/rcb_quadruped.py` | the tooling (privileged), the verifier's replay CLI and the service's simulator |
| `shared/standard/server.py` | the 2.2 adapter on `scripts/eai_standard/rcb_limited.py`; `finalize.sh`, the collect hook |
| `make_instances.py`, `select_instances.py`, `oracle.py` | candidates (Playground's code, JAX), selection and freezing, references |
| `instances/`, `oracles/`, `selection/` | the frozen instances, the reference rows, every candidate tried |
| `train/` | the reference-policy training (CPU PPO), not used by any task |
| `generate.py`, `templates/` | the task directories (`--check` compares) |
