# MuJoCo Playground

GPU-scale RL environments from Google DeepMind, here in plain MuJoCo on the CPU. This page covers the quadruped
locomotion tasks; the four manipulation tasks (`mujoco_playground_{aloha,panda}_*`,
ALOHA and Franka Panda, scripted IK references, `eai-standard/2.1`) predate it and are made by hand.

| | |
|---|---|
| upstream | [MuJoCo Playground](https://playground.mujoco.org/) (Apache-2.0) @ `4057c14`, with MuJoCo Menagerie @ `1b86ece` (the commit Playground pins) |
| simulator | MuJoCo 3.3.7, CPU physics (bit-exact replay); EGL rendering on a GPU, else OSMesa |
| robots | `unitree-go1` (Unitree Go1), `boston-dynamics-spot` (Boston Dynamics Spot), `google-barkour-vb` (Google Barkour vB); 12 joint position actuators each |
| score | binary, defined here from Playground's termination rules and reward targets (Playground has shaped RL rewards only) |
| tasks | Playground's 9 quadruped environments × 2 modes: `tasks/mujoco-playground/mujoco_playground_<env>-privileged` and `-standard` (`eai-standard/2.2`); BarkourJoystick, the one dynamic environment, also `-standard-realtime` (`eai-standard/2.3`) |
| image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.3` (`images/mujoco/`: 0.1.2 plus Playground's `locomotion/{go1,spot}` scenes and Menagerie's Go1, Spot and Barkour; every 0.1.2 file is unchanged) |
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
- **Instance.** One episode as Playground's own `reset` draws it with `jax.random.PRNGKey(seed)` (Playground's
  code): the start state and, for the joystick tasks, the command schedule (and Barkour's pushes, Spot gait
  tracking's gait) that the environment's command process draws over the episode, its per-step key splits replayed
  exactly; the draws do not depend on the physics while the episode does not terminate. Getup: the drop's start state;
  the 0.5 s settle runs in the task's own MuJoCo. `instance.json` holds the start, the schedule, the t = 0 state hash
  and the numbers the texts quote.
- **Selection** (never looking at an agent's result): seeds in order; skip a joystick schedule
  that is mostly standstill (under half the episode commanding |v_xy| >= 0.3 m/s or |w_z| >= 0.3 rad/s), Barkour pushes
  that are null or weak (peak under 20% of the torso's weight), a getup start that is not a fall (no drop, or tilted
  under 90 deg), and any seed whose reference fails.
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
| standard (2.2) | cameras (Go1, Spot: four that follow the robot; Barkour: one that follows it and its head camera; RGB, optional depth), joints, IMU (gyro, accelerometer, gravity's direction, velocimeter), foot contacts; the feet's FK/IK in the trunk frame | 10 (`RCB_RESET_BUDGET`) | the live episode's verdict: the task's check on the last episode as the service ran it |
| standard-realtime (2.3; BarkourJoystick only) | as standard, minus FK/IK, plus the joystick command in force in the proprioception; time does not stop (S = 1) | 10 (`RCB_RESET_BUDGET`) | the live episode's verdict, as standard |

## Reference solutions
- **Go1 joystick:** MuJoCo Playground's own Go1 joystick policy (`experimental/sim2sim/onnx/go1_policy.onnx`, the one its
  `play_go1_joystick.py` runs in native MuJoCo), closed loop on the frozen instance, its targets recorded.
- **The rest:** Playground ships no other quadruped policy. Policies are trained here with PPO on the CPU
  (rsl_rl with Playground's hyperparameters; each environment re-implemented in numpy
  with Playground's reset, action mapping, observations and rewards), then run closed loop on the frozen instance.
  - Go1 getup: the policy turns the robot belly-down and level but stops in a crouch (a local optimum of the reward); the
    reference then moves the joint targets linearly to `home` in 1 s.
  - Go1 footstand: trained with three training-only changes: the hind-leg termination this task uses, half of the episodes
    starting in Playground's `footstand` keyframe, and a steeper height reward (with Playground's own it squats at 0.2 m).
  - Spot gait tracking: trained with the command added to the observation (see below).
- Every reference row is float32-exact: the standard client sends actions as float32, so the standard oracle (streaming
  the rows through the client) records exactly the privileged reference.
- Policies only make the references: no image contains one, and the agent's egress is the model APIs and the package
  registries only (Playground's policies are public). The four manipulation pairs (scripted references of our own) are
  on the same allowlist; nothing in their containers needs the network at run time (`eai-mujoco` holds the Playground
  and Menagerie files the tooling loads, `/opt/rcb_mj`). The PyPI packages `playground` and `envpool` carry
  Playground's task sources (the honour rule, PROTOCOL §5).

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

## Verification (Harbor)

| | oracle | nop |
|---|---|---|
| all 9 environments, privileged | 1 (both fresh-process replays succeed, deterministic, video) | 0 (no trajectory) |
| all 9 environments, standard | 1 (live check, video) | 0 |

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

Outside Harbor, the standard service run on each reference (`std_local` check): live verdict success.

## Task-specific rules
- **ALOHA single peg insertion** (both modes): the peg tip's axial parameter `t_min <= t <= 0.75`, within 5 mm of the
  axis. Site `socket_rear` is at the tube's centre (t = 0 mid-tube, 0.048 m per unit of t); `t_min` is read from the
  model (the inner face of the rear wall, −0.833) minus `REAR_MARGIN_M` = 2 mm for the contact's give: −0.875. A tip
  behind the wall is a failure. Upstream has no success predicate; its shaped reward peaks at the tube's centre.
- **Privileged graders** (`tests/grade.py`): a `trajectory.npz` that cannot be read as an npz with a numeric `actions`
  array is `bad_trajectory`; quadrupeds: a replay process that died or timed out (`replay_failed`), a rebuilt start that
  does not match the instance's hash (`instance_mismatch`) and an exception of the verifier write `infra_error = 1`
  beside `grader_error = 1`.
- **Resets.** The quadruped standard tasks allow 10 resets: `RCB_RESET_BUDGET` (the compose files' default 10; 0 = a
  single episode), `POST /reset` (JSON or RCB1 `{cameras, video_fps, depth}`, no physics) abandons the running or ended
  episode and restarts from the frozen start; 409 after a success, once the agent's time is up and once the budget is
  spent; only the last episode is graded (`trajectory.npz` holds its rows); `meta` / `/status` add `episode`,
  `resets_left`, `control_steps_total`; `final.json` and `reward.json` add `resets`, `reset_budget`, `episodes`. Crash
  recovery replays the journal with the committed resets. `server_mj.py` has the same optional capability (default 0):
  the two ALOHA and two Panda standard tasks set none (`/reset` is a 404, `budget.reset` 0).

## Grading (standard modes)
- **2.2 quadrupeds** (each standard task's `environment/sim/`): the service runs `rcb_quadruped.Session.check()` on the live simulator when
  the episode ends (`finish()`; a getup / stand episode ends the moment its hold is met, a joystick episode passes only
  at the horizon) and writes it to `episode.json`; `finalize.sh` makes it `final.json`'s `success` (`graded_by =
  "live"`), then `video.py` renders `replay.mp4` in one fresh process (at most the horizon, ~150 frames: well under a
  minute on the CPU). `server.py` builds the scene with `check_hash=False` and gives up before serving the agent when the
  start's hash is not the instance's `state_sha` (`instance_mismatch`, infrastructure).
- **Standard-realtime** (BarkourJoystick): the shared layer's live verdict (`rcb_service._finalize`); `server.py`'s
  `step()` reports `check()` after every control step (joystick: success only at the horizon), its `start_sha` is the
  instance's `state_sha`, and it has no `live_verdict()`. The video is
  the layer's render pass on the service's own simulator after the verdict.
- **`server_mj.py`** (ALOHA, Panda; DexToolBench, [`dextoolbench.md`](dextoolbench.md)): `finalize()` reads the
  tooling's `check()` of the live final state (ALOHA, Panda) or the goal tracker's progress (DexToolBench), writes the
  verdict, then renders `replay.mp4` in one pass over the trajectory on its own simulator (EGL on the sidecar's GPU).
- **Collect hooks** wait for the verdict 900 s (2.2 quadrupeds, `RCB_COLLECT_END_TIMEOUT_S`), 300 s (realtime), 840 s (`server_mj.py`, since a service that crashed late in
  a long episode resumes it from the journal first), then for the video. `final.json` / `reward.json` have `graded_by`
  (`graded_by_live = 1`), `replays = 0`, `live_success`.
- **Infrastructure** (`infra_error = 1`, no verdict on the agent): a missing, unreadable or unfinalized `final.json`, a
  give-up after crashes between calls or a failed resume, a frozen start that did not build, a service that did not end
  its episode for the collect hook, a service-side failure writing the verdict (`finalize_error`). Crashes all inside
  the agent's calls (`sim_crashed_on_call`), a simulator error from a call (2.2 / 2.1: `sim_error`, the agent's 0; 2.3:
  the layer's own rule, PROTOCOL §4b), a fall, a timeout are the agent's result. A video that fails is only a missing
  video.

## Standard-realtime (`eai-standard/2.3`)
The dynamic families (PROTOCOL §2: each task's `[metadata] dynamics`) get a `-standard-realtime` twin. Among the quadrupeds that is **BarkourJoystick** (its torso is pushed 12 times at
frozen moments: an external force that is neither the robot's nor gravity).
- **Service.** The shared realtime layer, unchanged (`rcb_realtime.py` and `rcb_client.py` from
  `embodied_first_exam/standard/realtime/`; `rcb_service.py` and `grade.py`, byte-identical to HumanoidBench's realtime
  tasks' copies; `check-tooling-identity.sh`), with the twin's `environment/sim/server.py`, which implements `rcb_service.Sim` on `rcb_quadruped.Session`: the standard twin's
  instance, schedule, pushes, termination rule, check and replay; the proprioception adds `cmd_vx`, `cmd_vy`, `cmd_wz`
  (the command in force; standard mode has it in `meta["command_now"]`). Not served: the 2.2 additions (`/kinematics`,
  per-frame camera poses, depth modes) and the `done` action. Graded on the live episode; the clock's record is
  evidence only. The `sim` service reserves a GPU for EGL
  rendering (`server.py` writes the NVIDIA EGL ICD manifest when the image has none and `rcb_quadruped` probes EGL).
- **Slowdown S = 1, resets 10, cutoff 1800 s** (the standard twin's). RTF of the service (4 CPUs): 31.6 with the clock
  flat out.
- **Checked at S = 1**: the reference (`solution/oracle_plan.py`, the privileged rows planned from step 0 in one
  `submit(at=0)`) succeeds live, no stall, graded 1 by `tests/grade.py`;
  the same rows streamed one per call with a camera image every 0.25 s (7.7 ms each over EGL) succeed with no stall;
  nop (no request) ends `timeout`, not a success.

## Files
| | |
|---|---|
| each task's `rcb_quadruped.py` (`environment/`, `tests/`, the standard twin's `environment/sim/`) | the tooling (privileged), the verifier's replay CLI and the service's simulator |
| the standard twin's `environment/sim/server.py` | the 2.2 adapter on `embodied_first_exam/standard/rcb_limited.py`; `finalize.sh`, the collect hook |
| `environment/instance.json` | the frozen instance |
| `solution/oracle.npy` | the reference rows |
| the standard-realtime twin's `environment/sim/server.py`, `solution/` | its service (the 2.3 adapter) and its reference (`oracle_plan.py`, `solve.sh`) |

The task directories are the deliverable; the tooling that built them is kept outside this repository.

## Standard-mode service details

**MuJoCo service (DexToolBench, MuJoCo Playground manipulation; `eai-standard/2.1`).** Same endpoints and RCB1 frames,
served by `images/mujoco/limited/server_mj.py`. Differences: one action type, `joint_position` with the task's own
actuator layout (DexToolBench 29, ALOHA 14, Panda 8), rows `dt` apart where `dt` is a multiple of `control_dt` (1/60 s
DexToolBench, 1/50 s Playground), hold or linear interpolation per control step. Actions are sent as **float64** (MuJoCo
on CPU replays bit-exactly, and float32 rounding changes a chaotic tool swing). `meta.task` carries the task definition
(DexToolBench: current goal pose and index; Playground: the target) and `meta.cameras` each camera's intrinsics
(`intrinsic_cv` for the returned image; fx = fy for a camera defined by its field of view, fx ≠ fy for one defined by its
sensor size, `cam_sensorsize` > 0: fx = W × focal_x / sensor_x, fy = H × focal_y / sensor_y, cx = W / 2 − W ×
principal_x / sensor_x, cy = H / 2 + H × principal_y / sensor_y; ALOHA's overhead and wrist cameras, 158.52 and
216.45 px) and camera-to-world pose: the viewpoint the image is rendered from (not MuJoCo's left-eye camera), in the
state the response ends in, one pose per returned frame (`cam2world_gl/<cam>`). Cameras carry `moving` (true for ALOHA's wrist cameras). `final.json` is `finalized` as soon as the
live episode's verdict is in it; the video is rendered afterwards and sets `video_done`, which is what the collect hook waits
for (the MetaWorld+ service, `images/metaworld/standard/server_mw.py`, follows the same rules). DexToolBench's own eval
gives each goal 10 s; here the standard twins have **no per-goal limit** and **20 resets** (the optional reset
capability) and an episode cap of 360,000 control steps (100 min of
robot time, `spec.max_control_steps`), while the privileged tasks give each goal 30 s (replayed offline, free resets).
DexToolBench episodes end when all goals are reached, at the cap, or when the agent's time is up; Playground episodes
run to the end of the agent phase and the final state is graded. The service journals and resumes like the shared
layer (journal `record.f64`; startup watchdog `RCB_STARTUP_TIMEOUT_S`, default 300 s) and grades the live episode
(Grading, above). It implements the optional reset capability.

**Quadrupeds (`eai-standard/2.2`).** MuJoCo Playground's quadruped tasks serve the shared 2.2 layer. Their service implements the optional reset capability; the 2.2 client has no `reset()`, so the instructions call `POST /reset` through `Robot._post`. The service states no `max_frames_per_call` yet.
