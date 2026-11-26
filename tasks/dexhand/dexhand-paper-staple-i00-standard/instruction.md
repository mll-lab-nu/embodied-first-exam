# DexHand · Align and staple three paper sheets (standard)

## Task
Square up the 3 loose A5 sheets and staple them together at a corner with the desk stapler, then let go.

## Goal
Success: in this order, the three sheets are squared up and stacked in order; the stack sits in the stapler's throat
with the staple point near one of its corners, inside every sheet; the stapler head is pressed all the way down onto the
top sheet; then the head is back up, no part of the robot touches the sheets or the stapler, and the sheets are still
for a second.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- A sheet drops below the desk top, or leaves the desk or the work area.
- A sheet or the stapler touches the floor or a desk leg, or is dropped.
- The stapler is pushed away or tipped.
- An arm link or the robot's stand touches the desk, the stapler or a sheet.
- The physics becomes unstable.

The steps before the last count as they happen. Success is judged on how things stand when the episode ends. It ends
when you call finish (Limits) or when your session ends. The robot never tells you whether you have succeeded.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded: the episode you end with
  finish (Limits; no reset after it), or else the one running when your session ends.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no score, no success
  signal.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
The right arm and hand of a fixed Tianji Marvin robot (two 7-joint arms, a dexterous hand on each wrist; the left arm
starts parked and may stay there), at a desk (DexHand, MuJoCo). The robot runs as a service you reach through its client
or its MCP tools, as if it were real hardware.

### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"]                   # "sharpa" or "wuji"
obs = r.get_obs(cameras=["overview"], depth=True)
obs.last["overview"]           # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]     # z-depth in metres
obs.meta["proprio"]            # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.02, interpolate="hold", video="none")
r.fk(q)                       # robot-link forward kinematics; no physics is stepped
r.status()
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera
images, counting per-frame depth; reduce cameras, fps or duration for larger chunks. `hold(s)` holds the current targets
and records those steps. `get_obs()` only observes the current state. Forward kinematics uses only the robot's own links
(arms and hands); no IK primitive is supplied. If the service connection fails, call `r.wait_ready()` and inspect
`r.status()` before continuing. Crash recovery resumes the same journaled episode, without a reset, and the wall-clock
budget keeps running.

Resets: `r._post("/reset", ...)` (`POST /reset`) starts a new episode from the same starting state, abandoning the
running one or after one has ended; it takes no simulated time and returns the start's images and proprioception. Once
an episode has ended, `submit` raises `EpisodeOver` until you reset. `meta["episode"]` and `meta["resets_left"]` count
the episodes; `meta["control_steps"]` is the current episode's, `meta["control_steps_total"]` all of them.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `reset`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in
  `fields`) and returns the service's reply `meta` unchanged; images, arrays and video are written as files under
  `/app/obs/` (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file
  (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order: the 14 arm joint targets (left arm
`SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, then the same right-arm joints `..._R_J1` ... `..._R_J7`, radians), then
the left hand's and the right hand's finger targets in radians. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per
hand, `left_thumb_CMC_FE` ... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20
Wuji Hand 2.2 finger joints per hand, `l_wuji_l_THJ0..3`, `l_wuji_l_FFJ0..3`, `l_wuji_l_MFJ0..3`, `l_wuji_l_RFJ0..3`,
`l_wuji_l_LFJ0..3`, then `r_wuji_r_...`). Actuator targets are clipped to the published joint limits and clipping is
reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most 10 s. Hold interpolation
holds each row for `dt`; linear interpolation starts from the previous target. The robot has no scalar gripper opening.

Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's
finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); the left arm is parked and
only the right arm/hand perform the task.

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
wrist pose and current targets. Quaternions in measured poses use WXYZ; world z is up and the desk top is at z = 0.78 m.
Cameras are overview, closeup and throat, at 640 x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
You control a fixed Tianji Marvin robot: a stand with two 7-joint arms and a dexterous hand on each wrist. The right arm
and its hand suffice for the task; the left arm starts parked beside the stand (hanging straight down) and may stay
there (using it is allowed; every robot contact counts as hand contact). Every arm and finger joint is a position servo
inside the physics engine (2 ms physics step). Arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and the arms'
own torque limits (shoulder 108, elbow 66, wrist 18 N m), and no gravity compensation: a held target sags by about 1 cm
at the hand unless your targets account for it. Pushing, pressing and releasing require physical contact. The controller
runs at 50 Hz, with ten 2 ms physics substeps.

Only the right arm and hand are needed; keep the left arm at its start targets.

### Scene
World frame.

World frame: z up, metres and radians. The floor is at z = 0. The robot's stand origin is at (0.58, -0.66, 0.10) with
its base plate on the floor, beside the desk's -y edge, facing the desk diagonally (heading 135 deg: toward -x and +y);
the right shoulder is at about (0.737, -0.503, 1.221) and the left at (0.423, -0.817, 1.221); the right hand's mount
starts at (0.80, -0.22, 1.02) with the fingers pointing down. The desk top is at z = 0.78 m and spans x 0.25-0.99 m, y
-0.36-0.36 m (friction: paper on paper 0.4, paper on desk 0.15, paper on the chrome anvil and stop 0.1). The NOVUS
B2-style desk stapler is a free body (0.173 kg) whose base origin is at (0.575, -0.100, 0.783) with its nose toward +x.
Its anvil top is at z = 0.795 m; the staple point (base frame (0.063, 0, 0.012) m) is at (0.638, -0.100, 0.795) in the
reset pose. A steel paper stop (insertion guide) stands behind the anvil: its front face is at base-frame x = 0.0525 m
(world x = 0.6275 m) for |y - y_base| <= 0.012 m, z 0.790-0.800 m; a stack whose corner is fed against it puts the
staple point about 10.5 mm inside both edges. The handle with its driver blade turns on one passive hinge about the
base-frame y axis at (-0.052, 0, 0.020): return spring 7.0 N m/rad with 0.115 rad preload against the open stop (0 rad),
bottom stop 0.1701 rad (the blade 0.2 mm into a three-sheet stack lying on the anvil). The handle top is about 6.6 cm
above the desk; pressed 8 cm in front of the hinge, the head needs about 10 N to start moving and about 25 N at the
bottom stop. The magazine is rigid with the base.

The three sheets are rigid A5 plates (0.210 x 0.148 m, 0.5 mm thick, 2.5 g each), indexed bottom (0) to top (2). At
reset they rest as a loose, misaligned stack: the bottom sheet's (-x, -y) corner lies on the anvil mouth in front of the
paper stop, its +x edge on the desk; sheets 1 and 2 are shifted 4 mm and 8 mm toward +x. Rest poses (centre; all three
pitched 0.0733 rad about +y, i.e. the -x end raised, yaw 0): sheet 0 (0.7440, -0.0360, 0.7879), sheet 1 (0.7480,
-0.0356, 0.7881), sheet 2 (0.7520, -0.0364, 0.7883).

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 6,000 control steps (120 s of simulated time) per episode; an episode that reaches them ends there and
  is graded as it stands.
- Finish: when you are done, call finish: `POST /finish` with an empty JSON body to the service, at the client's base
  URL (`http://sim:8000` or `http://localhost:8000`; in Python `requests.post(r.base + "/finish", json={})` with your
  client `r`). It ends the episode, and every call after it is refused. Reaching the goal changes no reply and does not
  end the episode; if you never call finish, the end of your session ends it.
