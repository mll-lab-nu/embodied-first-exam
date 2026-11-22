# DexHand: Whisk batter in a bowl, drain and set the whisk down — MCP tools only

Pick up the balloon whisk, whisk the batter in the steel bowl, drain the whisk over the bowl and lay it down on the counter. The whisk starts at rest, leaning on the bowl rim with its handle end on the counter (where it settles when released from the source scene's start pose, standing in the bowl); both hands start open. The batter is not simulated: whisking is measured on the whisk-head point, 20 mm above the wire tip on the whisk axis, which is in the batter while it is between 3 mm above the bowl origin and the batter surface (35.7 mm above the bowl origin) and at least 4 mm inside the bowl wall. Complete five stages in order. (1) Picked up: a hand holds the whisk clear of everything else, i.e. the robot touches it, it touches neither the counter nor the bowl and its lowest point is at least 30 mm above the counter top, for 10 consecutive controls. (2) Immersed: the head point enters the batter. (3) Whisked: the head point circles the bowl axis by at least 5 full revolutions of net (signed, unwrapped) angle while it stays in the batter; leaving the batter before 5 revolutions resets the count to zero, and controls with the head point closer than 8 mm to the bowl axis add nothing. (4) Drained: while the robot touches the whisk, the wire tip is at least 10 mm above the bowl rim, the head point is within 55 mm of the bowl axis (over the opening) and the whisk hangs head-down within 30 degrees of vertical, for 25 consecutive controls (0.5 s). (5) Set down: lower the whisk until it touches the counter top while the robot still touches it (it is then placed), then let go; the episode succeeds when, for 50 consecutive controls (1 s), the whisk touches the counter top, touches neither the robot nor the bowl, lies within 30 degrees of horizontal with its centre of mass at least 120 mm from the bowl axis, and its centre of mass moves slower than 0.02 m/s and it turns slower than 0.3 rad/s. The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every control, when: the bowl tilts more than 10 degrees, slides more than 30 mm or rises more than 20 mm from its start; after the pickup, the whisk touches nothing, its lowest point is more than 2 mm above the counter top and its centre of mass moves downward faster than 0.2 m/s (dropped); after the pickup and before it is placed, the whisk touches the counter or is out of robot contact for more than 10 consecutive controls (dropped); after it is placed, the whisk touches neither the robot nor the counter for more than 5 consecutive controls (tossed); the bowl or the whisk touches the floor, has its centre of mass below the counter top (z < 0.68 m) or outside the workspace x in [0.25, 0.99] m, y in [-0.36, 0.36] m, z in [0.60, 1.50] m; or the physics becomes unstable. Before the pickup the whisk may be nudged or slide off the rim; the counter, floor and workspace rules still apply. Later actions cannot undo a failure. "Robot" means any hand, arm link or the stand. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct forces. The episode allows at most 4000 controls at 50 Hz; reaching that limit without success is a failure.

The robot is a fixed Tianji Marvin stand at the world origin facing +x, with two 7-joint arms and a dexterous hand
on each wrist (robot id `marvin-bimanual-sharpa-wave`). Every arm and finger joint is a position servo in the physics
engine under native force bounds; arm servos have stiffness 700 N m/rad, damping 48 N m s/rad and **no gravity
compensation** (a held target sags by about 1 cm at the hand under load unless your targets account for it). The bowl
and the whisk move only through contact with the hands, the arms, each other and the counter. The controller runs at
50 Hz, with ten 2 ms physics substeps. World frame: metres and radians, +z up, +x forward from the robot stand, +y to
the robot's left.

## Robot tools (MCP server `efe-robot`)
You act on the robot only through the tools of the MCP server `efe-robot` (in your tool list as `efe-robot` tools, for
example `mcp__efe-robot__move_robot`). You may write and run code to compute; every robot command and observation must
go through the efe-robot MCP tools; code must not contact the simulator. Each robot command or observation is a tool
call you make yourself: no script starts or calls the `efe-robot` server, and the service's record of its requests is
checked against the server's. To send a trajectory your code computed, save it as a file under `/app` and pass its path
as `rows_file` to `execute_trajectory`. The robot service and its rules are as described in this text; where it names
calls of the Python client `rcb_client.py`, which is not installed for your code here, use the tool that does the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |
| `r.reset()` / `POST /reset` | `reset_episode()` |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the Marvin stand origin (the floor point under its torso): +X the way the robot faces,
+Y to its left, +Z up. Space `native` sends rows in the robot's own action types exactly as the sections below describe
them (their frame, units and gripper values).

**This robot** (Tianji Marvin stand with two 7-joint arms and a Sharpa Wave dexterous hand (22 finger joints) on each
wrist): right_hand (hand: 22 joints, no end-effector pose); left (arm: 7 joints, no end-effector pose); right (arm: 7
joints, no end-effector pose); left_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `closeup`,
`side`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the robot base frame that a camera sees at pixel (u, v)
  of its full-size image (u the column, v the row), or one per pixel of `pixels` [[u, v], ...]: from a new depth image
  of that camera and its calibration (no time passes). For a camera with depth and a known pose; for any other the error
  says so.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (errors per goal), a `failure` category if a goal was not reached, the state and
  the path of a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, rows `dt` seconds
  apart. `rows_file` is the path of a file under `/app` that holds the rows: a `.npy` (2-D float array) or `.csv` (one
  row per line, comma-separated) of native rows for space `native` (with `action_type`), or a `.json` list: of number
  arrays (native rows) or of row objects as in `rows` (the other spaces). Long arrays go this way rather than inline.
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `reset_episode()`: a new episode from the same starting state (it uses one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time. A call still executing after 45 s returns `{"pending": true, "operation": id}` while the
  robot goes on executing it: call `wait(operation=id)` (it waits up to 45 s more each time) for its result. A result
  with `"episode_over": true` means the episode has ended.
- Nothing needs to be saved: the server records every tool call, and the service records the episode.

**Notes on this robot.** Two 7-joint arms (parts left, right) and two hands (left_hand, right_hand), all joint
positions: no end-effector pose command and no inverse kinematics; the measured hand-mount pose comes back as ee. The
arm servos have no gravity compensation (a held target sags about 1 cm at the hand under load). A one-hand task keeps
the other arm parked at its start targets. Every column is a position target (servo); grasping and carrying work only
through contact. The parts follow the Sharpa Wave layout (describe_robot spec_file: hand "sharpa"). With the Wuji hand
(hand "wuji", 20 finger joints per hand) the columns differ: use execute_trajectory space native with the order in spec
action_types.joint_position.layout. Rows are 0.02 s apart or a multiple of it; a call covers at most 10 s. Measured
poses are in the world frame of the task text, quaternions wxyz.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
Each row starts with the 14 Marvin arm joint targets (left arm J1-J7, then right arm J1-J7), followed by the left hand's finger targets and then the right hand's (22 per hand for `sharpa`, 20 per hand for `wuji`). The right arm/hand picks up and uses the whisk; the left arm/hand may steady the bowl.
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`) and the exact order. The episode record names the hand; the service grades the episode it ran with that hand.

## Episodes and resets
You have **20 resets** (`spec["budget"]["reset"]`, which is authoritative: if it says 0, there is no reset
and the one episode is the run). A reset puts the robot and every object back in the same frozen starting state and
starts a new episode, either abandoning the running one or after one has ended; it takes no simulated time and
returns the start's images and proprioception:
```python
res = r._post("/reset", {"cameras": ["overview"]}, [], 900)   # POST /reset (the 2.2 client has no reset())
res.meta["episode"], res.meta["resets_left"]
```
Once an episode has ended, `submit` raises `EpisodeOver` until you reset. **Only the last episode is graded**: an
episode you reset away is never graded, a success ends the run at once (no reset after it), and when your time is up
the episode then running is the one graded. The wall clock is the run's and never restarts; `meta["episode"]` and
`meta["resets_left"]` count the episodes (`meta["control_steps"]` is the current episode's,
`meta["control_steps_total"]` all of them).

## The robot service through its Python client (reference; your code cannot reach it: act through the `efe-robot` tools above)
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own
joint positions, velocities, actuator efforts, wrist pose and current targets. An episode ends at the first success
or the first failure (see the task text); after that the service accepts no more actions until a reset (see
`## Episodes and resets`). The service records every action and watch step, then judges the graded episode as it ran
(that is the verdict; nothing is replayed).

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
res.save("/app/runs/001")
```
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order, radians: columns 0-6 the left arm
`SHOULDER_PITCH_L_J1` ... `WRIST_ROLL_L_J7`, 7-13 the right arm `..._R_J1` ... `..._R_J7`, then the left hand's and
the right hand's finger targets. `D` is 58 for `sharpa` (22 Sharpa Wave finger joints per hand, `left_thumb_CMC_FE`
... `left_pinky_DIP`, then `right_thumb_CMC_FE` ... `right_pinky_DIP`) and 54 for `wuji` (20 Wuji Hand 2.2 finger joints
per hand, `l_wuji_*` then `r_wuji_*`). The episode starts with both hands open above the counter and the arms in a
ready pose; holding the current targets keeps it. The whisk rests against the bowl rim with its handle end on the
counter (where it settles when released from the source scene's start pose, standing in the bowl); the left hand may
steady the bowl, which the success predicate does not require. Actuator targets are clipped to the published joint
limits and clipping is reported. `dt` must be a multiple of 0.02 s, between 0.02 and 0.5 s; a chunk covers at most
10 s. Hold interpolation holds each row for `dt`; linear interpolation starts from the previous target. The robot has
no scalar gripper opening. Quaternions in measured poses use WXYZ; world z is up and the counter top is at z = 0.68 m;
the bowl starts centred at (0.58, 0.0) m. Cameras are overview, closeup and side, at 640 x 480. Requests can return
RGB frames or mp4, with depth `none`, `last` or `frames`. Each call returns at most 1,000 camera images, counting
per-frame depth; reduce cameras, fps or duration for larger chunks. `get_obs(seconds=...)` holds the current targets
for up to 30 s and records those steps. Calling it without seconds only observes the current state. Forward
kinematics uses only the robot's own links; no IK primitive is supplied. If the service connection fails, call
`r.wait_ready()` and inspect `r.status()` before continuing. Crash recovery resumes the same journaled episode, without
a reset, and the wall-clock budget keeps running.

One call returns at most 1000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the files the robot tools write included. You may write and run code to compute; every robot command and observation must go through the `efe-robot` MCP tools; code must not contact the simulator. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **2 CPUs**, **4 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
