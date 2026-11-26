# DexHand · Place a two-handle pot into a shelf (standard)

## Task
Lift the pot by its two handles with both hands, carry it into the shelf on the left and set it down upright on the
shelf board at the target, then open both hands and move them away.

## Goal
Success: the pot is carried with both hands lifting it, off the worktop and the shelf, for a moment; then it stands
upright on the shelf board at the target (Robot Interface), fully inside the compartment except that its front handle
may stick out a little past the board's front edge, resting on the board alone, with both hands opened and moved a
little away from it, and is still for two seconds.

Any of these ends the episode at once as a failure, which later actions cannot undo:
- The pot falls or tips over.
- The pot is dropped.
- The pot leaves the work area.
- The pot touches anything but the two hands, the worktop and the shelf board.
- A robot link touches the furniture or the floor, or two robot parts collide.
- A hand presses into the pot.
- A robot joint is pushed past its range.
- The physics becomes unstable.

The steps before the last count as they happen.

When you are done, send `/finish` to end the episode and get it graded. Everything else counts only as it stands at that
point.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- Episodes: 20 resets (`spec()["budget"]["reset"]`), each a new episode from the same starting state; within an episode
  what you knock over stays knocked over until you reset. Only the last episode is graded. No reset is possible after
  `/finish`.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no score, no success
  signal.

Only the robot's actuator targets act on the scene: no object teleports, grasp welds, scripted object motion or applied
forces.

## Robot Interface
A fixed Tianji Marvin robot with two 7-joint arms and a dexterous hand on each wrist, at a kitchen worktop (DexHand,
MuJoCo). The robot runs as a service you reach through its client or its MCP tools, as if it were real hardware.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`:
```python
from rcb_client import Robot
r = Robot()
spec = r.spec()                    # spec["hand"], spec["action_types"]["joint_position"]["layout"], cameras, limits
obs = r.get_obs(cameras=["overview", "shelf"], depth=True)
obs.last["overview"]               # RGB uint8 (480, 640, 3)
obs.last_depth["overview"]         # z-depth in metres
obs.meta["proprio"]                # named robot measurements
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.002, interpolate="hold", video="none")
r.fk(q)                            # robot-link forward kinematics (both wrists); no physics is stepped
r.status()
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (this client has no reset())
```
Requests can return RGB frames or mp4, with depth `none`, `last` or `frames`; each call returns at most 1,000 camera
images, counting per-frame depth. Frames are rendered in software, about 0.6 s per camera image, and a call records
`video_fps` frames per simulated second (1 to 50, default 10) whatever `video` returns: lower it for long chunks.
`hold(s)` holds the current targets and records those steps; `get_obs()` only observes. No IK primitive is supplied. If
the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes
the same journaled episode, without a reset, and the wall-clock budget keeps running.

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
`rows` is `(T, 58)` for `sharpa` or `(T, 54)` for `wuji`, in `spec["action_types"]["joint_position"]["layout"]` order
(the row layouts below), radians. `dt` must be a multiple of 0.002 s, between 0.002 and 0.5 s; a chunk covers at most 10
s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target.

Each row starts with the 14 arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger
targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`); one row is one 2 ms physics step.
Row layout, `sharpa` (58): 0-6 left arm
`SHOULDER_PITCH_L_J1, SHOULDER_ROLL_L_J2, ELBOW_PITCH_L_J3, ELBOW_YAW_L_J4, WRIST_PITCH_L_J5, WRIST_YAW_L_J6, WRIST_ROLL_L_J7`
(actuators `<joint>_target`); 7-13 the same right-arm joints (`..._R_J1` to `..._R_J7`); 14-35 the left Sharpa Wave
fingers
`l_hand_thumb_CMC_FE, l_hand_thumb_CMC_AA, l_hand_thumb_MCP_FE, l_hand_thumb_MCP_AA, l_hand_thumb_IP, l_hand_index_MCP_FE, l_hand_index_MCP_AA, l_hand_index_PIP, l_hand_index_DIP`,
the same four for middle and ring, then
`l_hand_pinky_CMC, l_hand_pinky_MCP_FE, l_hand_pinky_MCP_AA, l_hand_pinky_PIP, l_hand_pinky_DIP`; 36-57 the right Sharpa
Wave fingers in the same order (`r_hand_...`). Row layout, `wuji` (54): 0-13 the same arm targets; 14-33 the left Wuji
fingers `l_wuji_l_THJ0..THJ3` (thumb), `l_wuji_l_FFJ0..FFJ3` (index), `l_wuji_l_MFJ0..MFJ3` (middle),
`l_wuji_l_RFJ0..RFJ3` (ring), `l_wuji_l_LFJ0..LFJ3` (little); 34-53 the right Wuji fingers in the same order
(`r_wuji_r_...`).

### Observations
You receive camera RGB, optional calibrated depth, and the robot's own joint positions, velocities, actuator efforts,
both wrist poses and current targets. Cameras are overview, front (looking into the shelf compartment) and shelf, at 640
x 480.

### Hands
Two hand models: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger
actuators); the task is the same for both, and one hand is used per episode. The service runs the hand that
`DEXHAND_HAND` names on the sim service (default `sharpa`); you cannot switch it during an episode. The hand in use is
`spec()["hand"]`; `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`)
and the exact order.

### Robot
The robot is a fixed Tianji Marvin stand with two 7-joint arms and a dexterous hand on each wrist. Every arm and finger
joint is a position servo inside the physics engine (2 ms physics step). Arm servos have stiffness 700 N m/rad, damping
48 N m s/rad, the arms' own torque limits and no gravity compensation: a held target sags under the arm's and the pot's
weight unless your targets account for it. Every joint's range and effort limit is in `spec()["robot_spec"]`. The pot
moves only through contact and gravity.

Control rate: one action row is one 2 ms physics step (500 Hz). A row holds a position target for every actuator
(radians), applied for exactly one physics step.

Both hands start open at the same arm pose.

### Scene
World frame: metres, radians, seconds; +z up, +x forward from the robot stand, +y to the robot's left; quaternions are
wxyz. The worktop top is at z = 0.75; the pot is upright on it with its base centre at (0.52, -0.05, 0.75) and its two
loop handles along the world y axis (handle loops 0.13 to 0.22 m from the pot axis, 0.133 to 0.187 m above the base);
the open shelf's board top is at z = 0.79 and spans x from -0.14 to 1.14 and y from 0.12 to 0.84; the compartment is
closed by side walls (inner faces x = -0.14 and x = 1.14), a back wall (inner face y = 0.84) and a top board (underside
z = 1.465), and opens toward -y. The target for the pot's base centre is (0.46, 0.31, 0.79).

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: at most 20 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
- Steps: at most 30,000 rows (one per 2 ms physics step) (60 s of simulated time) per episode; an episode that reaches
  them ends there.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
