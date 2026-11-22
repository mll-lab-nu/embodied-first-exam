# DexHand: Sweep debris into a held dustpan — MCP tools and shell

Sweep all six pieces of debris on the floor into the dustpan and lift the loaded pan. A fixed two-arm robot starts with a broom held in its right hand and a dustpan held in its left hand; the pan's entrance ramp rests on the floor next to six small rigid debris pieces (packaging pieces, bottle caps, a wood chip and a crumpled-paper ball). Push the debris over the ramp with the broom's bristles, then raise the dustpan. Success requires 2000 consecutive physics steps (1.0 s) in which all of these hold: in the dustpan's own frame every collision shape of all six pieces lies over the pan floor (at least 1 mm inside its 460 mm side-to-side width, inside its 262 mm depth, no lower than 1 mm below the top of the floor plate and no higher than 110 mm above the pan origin); all six pieces touch the pan (contact force at least 1 mN); the pan origin is at least 50 mm above the floor; every piece moves slower than 0.03 m/s and rotates slower than 0.8 rad/s; and every piece has been touched by the bristles at some point. The episode ends with that success, or fails immediately and permanently when: a piece leaves the floor work area (world x outside [0.45, 1.00] m, y outside [-0.50, 0.40] m, or its center more than 0.25 m above or 0.01 m below the floor at z = -0.10 m); any part of the robot touches a piece of debris with at least 1 mN (sweep with the broom only); from 1.2 s on, fewer than two collision parts of a tool's own hand press on its handle with at least 0.01 N each, or the handle's grip point has moved more than 25 mm or turned more than 0.25 rad relative to that palm since 1.2 s (dropped or slipping tool); a tool is pressed (more than 0.01 N) by any robot part other than its own hand; the arms, torso or the two hands collide with each other; or the simulation becomes unstable. Five of six pieces, an unlifted pan or a hold shorter than 1 s is not a success. Only the robot's motor targets act; the tools and the debris are free bodies without welds, scripted motion or applied forces. One control row sets every motor target for one 0.5 ms physics step (2000 Hz); an episode has at most 160000 rows (80 s).

The robot is a fixed Tianji Marvin base with two seven-joint arms. The left arm's hand holds the dustpan by its
handle; the right arm's hand holds the broom by its shaft. Arms and fingers are position servos with native force
bounds; the broom, the dustpan and the debris move only through contact and gravity. At the start the current targets
keep both tools in the hands; the first 1.2 s are a settling period in which the grip is not yet judged. The simulator
integrates at 0.5 ms and every action row is one physics step, so rows are a 2000 Hz control. The service simulates
slower than real time (several seconds of CPU per simulated second).

## Robot tools (MCP server `efe-robot`) and their Python client `efe_robot`
Besides the robot service's own client (below), you get the robot through the tools of the MCP server `efe-robot` (in
your tool list as `efe-robot` tools, for example `mcp__efe-robot__move_robot`) and through the same tools as Python
functions: `import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments
and result, and its docstring is the tool's description), or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'`
from the shell. They all drive the one robot: use one route at a time. The calls of the service's client and the tools
that do the same:

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
joints, no end-effector pose); left_hand (hand: 22 joints, no end-effector pose). Cameras: `overview`, `work`, `pan`,
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
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** Two 7-joint arms (parts left, right) and two hands (left_hand, right_hand), all joint
positions: no end-effector pose command and no inverse kinematics; the measured palm poses come back as ee. The right
hand starts holding the broom and the left hand the dustpan; the start targets keep both grips. The control runs at 2000
Hz (one physics step per control; describe_robot control_dt_s): move_robot and the spaces other than native send rows
0.02 s apart, which the robot interpolates; the simulation runs slower than real time. Every column is a position target
(servo); grasping and carrying work only through contact. The parts follow the Sharpa Wave layout (describe_robot
spec_file: hand "sharpa"). With the Wuji hand (hand "wuji", 20 finger joints per hand) the columns differ: use
execute_trajectory space native with the order in spec action_types.joint_position.layout. Rows are a multiple of 0.0005
s apart; a call covers at most 10 s. Measured poses are in the world frame of the task text, quaternions wxyz.

## Hands
Two genuine manufacturer hand models are available: `sharpa` (Sharpa Wave, 22 finger actuators; the default) and `wuji` (Wuji Hand 2.2, 20 finger actuators). The task, scene, mount, objects and success predicate are the same for both; only one hand is used per episode.
This task uses two hands of one model on the two arms of a fixed robot: Sharpa Wave (default) or Wuji Hand 2.2. Every row holds both arms' joint targets and both hands' finger targets (layout below). With Wuji, both hands start closed on the same broom and dustpan (assets/reset_wuji.npz: the frozen arm, tool, debris and bristle coordinates with Wuji finger joints).
The robot service runs the hand named by `DEXHAND_HAND` on the sim service (default `sharpa`); the agent cannot switch it during an episode. `spec()["hand"]` names it, and `spec()["action_types"]["joint_position"]` gives the row width (`58` for `sharpa`, `54` for `wuji`) and the exact order. The episode record names the hand; the service grades the episode it ran with that hand.

Sharpa rows
(58 targets): the 7 left-arm joints `SHOULDER_PITCH_L_J1_target ... WRIST_ROLL_L_J7_target`, the 7 right-arm joints
`SHOULDER_PITCH_R_J1_target ... WRIST_ROLL_R_J7_target` (radians), then the 22 left-hand and the 22 right-hand
Sharpa Wave finger targets (radians).
Wuji rows (54 targets): the same 14 arm targets, then the 20 left-hand and the 20 right-hand Wuji Hand 2.2
finger targets (`l_wuji_l_THJ0 ... l_wuji_l_LFJ3`, `r_wuji_r_THJ0 ... r_wuji_r_LFJ3`: thumb CMC flexion, CMC
abduction, MCP, IP, then index/middle/ring/pinky MCP flexion, MCP abduction, PIP, DIP; radians). With Wuji the start
differs only in the finger joints and their targets: both Wuji hands start closed on the same broom and dustpan
(the arm, tool, debris and bristle coordinates and the arm targets are those of the Sharpa start), and
the targets at the start keep them. The task, predicate and fail-fast rules are the same for both hands.

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

## Robot service
The simulator runs in a separate service. You receive camera RGB, optional calibrated depth, and the robot's own joint
positions, velocities, actuator efforts, both palm poses (`l_hand_palm`, `r_hand_palm`) and current targets. Object poses, contacts and the predicate
state are not published. A failure ends the episode; a reset starts a new one (see `## Episodes and resets`). The
service records every executed row and judges the graded episode as it ran (that is the verdict; nothing is replayed). Leave your controller at `/app/output/gen.py`; no trajectory
hand-in is needed.

```python
from rcb_client import Robot
r = Robot()
spec = r.spec()
spec["hand"], spec["action_types"]["joint_position"]["layout"]
obs = r.get_obs(cameras=["work"], depth=True)
obs.last["work"]               # RGB uint8 (480, 640, 3)
obs.last_depth["work"]         # z-depth in metres
q = obs.group("joint_pos", now=True)
res = r.submit("joint_position", rows, dt=0.0005, interpolate="hold", video="none")
r.fk(q)                        # robot-link forward kinematics; no physics is stepped
r.status()
```
`rows` is `(T, D)` in `spec["action_types"]["joint_position"]["layout"]` order. `dt` must be a multiple of
`1 / spec["control_hz"]` (0.0005 s), at most 0.5 s; a chunk covers at most `spec["max_chunk_s"]` seconds. `hold`
keeps each row for `dt`; `linear` interpolates from the previous target. The client sends rows as float32. Targets are
clipped to the published joint limits and clipping is reported. Cameras are overview, work (the floor area and the pan),
pan and side, 640 x 480, fixed in the world. Requests return at most 1,000 camera images; ask for fewer cameras or a
lower `video_fps` for long chunks. `get_obs(seconds=...)` holds the current targets for up to 30 s and records those
steps; without seconds it only observes. Measured poses use WXYZ quaternions; world z is up, metres, the robot base at
the origin, the floor the plane z = -0.10 m. Forward kinematics covers the robot's own links; no IK primitive is
supplied. If the service connection fails, call `r.wait_ready()` and inspect `r.status()` before continuing. Crash
recovery resumes the same journaled episode, without a reset, and the wall-clock budget keeps running.

One call returns at most 1000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **2 CPUs**, **4 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
