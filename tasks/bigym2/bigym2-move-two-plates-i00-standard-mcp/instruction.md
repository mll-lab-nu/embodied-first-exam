# bigym2 move-two-plates — instance i00 — STANDARD MODE, MCP TOOLS ONLY (robot as a service)

You control a simulated Unitree G1 humanoid robot with two-finger grippers (BiGym 2.0, MuJoCo) **as if it were real
hardware**: the simulator runs in a service you cannot open, and you reach it only through the `efe-robot` tools. NVIDIA's GR00T
whole-body controller, a learned policy that runs inside every control step, drives the legs and waist and keeps the
robot balanced: you command where it walks, how high its pelvis is, how far its torso leans forward, its arm joints and its grippers.
**Task:** Take both plates out of the left dish rack and gently stand them in the right dish rack.

At the start both plates stand in the left dish rack, about 0.7 m away, 29° to your left, 0.82 m above the floor; the right dish rack is about 0.7 m away, 21° to your right, 0.70 m above the floor. Both racks are on the table in front of you. (Distances are from your pelvis along the floor, directions from the way you face,
heights above the floor; measured on this scene.)

## Robot tools (MCP server `efe-robot`)
You act on the robot only through the tools of the MCP server `efe-robot` (in your tool list as `efe-robot` tools, for
example `mcp__efe-robot__move_robot`). You have no shell and cannot run code. The robot service and its rules are as
described in this text; where it names calls of the Python client `rcb_client.py`, which you cannot run here, use the
tool that does the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: on the floor under the pelvis: +X the way the pelvis faces, +Y left, +Z up; it moves
with the robot. Space `native` sends rows in the robot's own action types exactly as the sections below describe them
(their frame, units and gripper values).

**This robot** (Unitree G1 humanoid (29 DoF) with two 7-joint arms and Dex1-1 two-finger grippers; NVIDIA's GR00T
whole-body controller drives the legs and waist and keeps it balanced): left (arm: 7 joints, gripper); right (arm: 7
joints, gripper); torso (torso: 1 joints); lift (lift: 1 joints). Cameras: `head`, `left_wrist`, `right_wrist`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (errors per goal), a `failure` category if a goal was not reached, the state and
  the path of a frame per camera.
- `locomote(vx, vy, wz, duration_s, height?)`: walk with the robot's own controller (body-frame velocities), then stop;
  returns the displacement.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, rows `dt` seconds
  apart; a long one can come from a file under `/app` (`.npy` / `.csv` of native rows, `.json` of rows).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time. A call still executing after 45 s returns `{"pending": true, "operation": id}` while the
  robot goes on executing it: call `wait(operation=id)` (it waits up to 45 s more each time) for its result. A result
  with `"episode_over": true` means the episode has ended.
- Nothing needs to be saved: the server records every tool call, and the service records the episode.

**Notes on this robot.** The arms take joint positions only (no end-effector pose command); each joint's axis and range
and each gripper's point between its finger pads are in describe_robot's spec_file (joints, joint_frame, grippers). The
servos track with a small error: the measured arm joints sit a little below their targets, by up to a few hundredths of
a radian. The torso lean (target torso) and the pelvis height (target lift) are commands to the whole-body controller,
which also moves the waist. Time passes only inside calls; the episode has a fixed number of control steps (50 per
simulated second; control_steps in every result counts those used, spec_file max_control_steps is the total). A fall
(pelvis tilted more than about 53 degrees, or lower than 0.30 m) makes the episode a failure without ending it.

## Rules (real-robot rules)
- **One episode, no reset.** The episode starts when the service comes up, from a fixed starting state; what ends it is under Success below. `spec()["budget"]["reset"]` is authoritative: it is 0 here, so the one episode is the run. Once it has ended, the run is over and `submit` raises `EpisodeOver`.
- **Time moves only inside calls.** `submit` runs your commands and `get_obs(seconds=s)` stands still for s seconds; both use up the episode's control steps. Between calls the robot waits, frozen, while you think; `get_obs()` with no seconds is free.
- **No privileged state, no score.** You see what the robot's three cameras see (RGB, 84×84: `head`, `left_wrist`, `right_wrist`) and its own proprioception (below). Not where any object is now (only the start sentence above), not the success check: the service judges the episode and only tells you that it ended and why (`meta["done"]`, `meta["reason"]`). `spec()` gives the robot's facts: the action slots and their bounds, each camera's field of view and its pose at the start.
- There is nothing to hand in: the service records the episode and grades it as it ran.
- Wall-clock budget: the time limit (`## Time limit`). It ends without warning, and ending your session earlier ends the run the same way, so do not stop early: while the episode runs, the run can still pass.

## Success
The episode succeeds when the following has held for **1 s (50 control steps in a row)**: each plate stands in a slot of the right-hand rack: its centre within 0.05 m of one of that rack's six slot points, standing on edge with its face toward your right (its axis within 20 degrees of the robot's right at the start, as the plates stand now; a plate turned around does not count), touching the right-hand rack, not touching the table, held by neither gripper; both plates at once. *Held* means that a finger of the gripper touches the object (BiGym's `is_gripper_holding_object`): an open gripper still resting against it holds it. A plate touching the floor ends the episode as a failure. The robot must not fall at any time: a fall (the pelvis tilted more than about 53 degrees from upright, or lower than 0.30 m) makes the episode a failure, but does not end it.

The episode ends when the success has held for 1 s (`reason = "success"`), on the failure above, when the pelvis gets more than
10 m from the scene's origin, on a simulator error, after **2300 control steps** (46 s of robot
time), or when your time is up. That live episode is the verdict.

## The robot service through its Python client (reference; act through the `efe-robot` tools above)
Its docstring is the full reference (`/opt/tools/rcb_client.py`, readable with your file-reading tool); here the action type is `"whole_body"` (not the docstring's example name):

| call | endpoint | what it does |
|---|---|---|
| `r = Robot()` | | connects (`http://sim:8000`, then `http://localhost:8000`) and waits until the scene is ready |
| `r.spec()` | `GET /spec` | the robot's facts: `action_types["whole_body"]` (layout, lower, upper, units), `control_dt` (0.02 s), `max_control_steps` (2300), the cameras, `proprio_layout`, `budget` |
| `r.status()` | `GET /status` | `calls`, `rows`, `control_steps`, `done`, `reason`, `elapsed_s` |
| `r.get_obs(cameras=None, seconds=0, video="frames")` | `POST /observe` | the current frames (free), or stand still and watch for `seconds` (at most 30) |
| `r.submit("whole_body", A, dt=0.02, interpolate="linear", cameras=None, video="mp4")` | `POST /submit` | runs `A`, rows of 21 commands `dt` seconds apart (a multiple of 0.02; a chunk covers at most 10 s); stops early when the episode ends |

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

The answers are binary (RCB1) and come back decoded: `res.meta` (the counters, `done`, `reason`, `proprio["now"]`,
`clipped`), `res.last[camera]` (the last frame), `res.frames` or `res.video` (what the cameras saw during the call),
`res.proprio` (proprioception rows). Values outside the bounds are clipped and reported in `meta["clipped"]`, never
refused; a malformed request raises `ValueError` and runs nothing. The response of the call that ends the
episode also carries `meta["outcome"]`, BiGym's own label of how it ended (`success`, `fell`, `timeout`, `terminated`,
`physics_error`). Standing still is the row with the current height,
lean, arm and gripper targets and zero `vx`, `vy`, `wz`; `get_obs(seconds=s)` does that from your last row.
Measured here: a control step costs about 14 ms of service time inside a `submit` (a 1 s chunk returns in about
0.7 s); `get_obs()` without seconds about 10 ms.
```python
from rcb_client import Robot
r = Robot()
res = r.submit("whole_body", A, dt=0.02)   # A: (T, 21) commands, one row per control step
```

## Action rows (21 floats, physical units)
| slot | name | bounds | meaning | at the start |
|---|---|---|---|---|
| 0 | `vx` | [-1, 1] | walking velocity command, forward (m/s, the robot's frame) | 0 |
| 1 | `vy` | [-1, 1] | walking velocity command, to the left (m/s) | 0 |
| 2 | `height` | [0.4, 1] | pelvis height command (m) | 0.74 |
| 3 | `wz` | [-1, 1] | turning rate command, + turns left (rad/s) | 0 |
| 4 | `pitch` | [-0.2, 0.8] | torso lean command, + leans forward (rad) | 0 |
| 5 | `left_shoulder_pitch_joint` | [-3.0892, 2.6704] | absolute joint target (rad) | 0 |
| 6 | `left_shoulder_roll_joint` | [-1.5882, 2.2515] | absolute joint target (rad) | 0 |
| 7 | `left_shoulder_yaw_joint` | [-2.618, 2.618] | absolute joint target (rad) | 0 |
| 8 | `left_elbow_joint` | [-1.0472, 2.0944] | absolute joint target (rad) | 0 |
| 9 | `left_wrist_roll_joint` | [-1.9722, 1.9722] | absolute joint target (rad) | 0 |
| 10 | `left_wrist_pitch_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 11 | `left_wrist_yaw_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 12 | `right_shoulder_pitch_joint` | [-3.0892, 2.6704] | absolute joint target (rad) | 0 |
| 13 | `right_shoulder_roll_joint` | [-1.5882, 2.2515] | absolute joint target (rad) | 0 |
| 14 | `right_shoulder_yaw_joint` | [-2.618, 2.618] | absolute joint target (rad) | 0 |
| 15 | `right_elbow_joint` | [-1.0472, 2.0944] | absolute joint target (rad) | 0 |
| 16 | `right_wrist_roll_joint` | [-1.9722, 1.9722] | absolute joint target (rad) | 0 |
| 17 | `right_wrist_pitch_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 18 | `right_wrist_yaw_joint` | [-1.6144, 1.6144] | absolute joint target (rad) | 0 |
| 19 | `left_gripper` | [0, 1] | 0 open .. 1 closed | 0.6 |
| 20 | `right_gripper` | [0, 1] | 0 open .. 1 closed | 0.6 |

`right_shoulder_roll_joint`'s bounds are BiGym's action bounds, not the joint's own range [-2.2515, 1.5882]: a command outside them is clipped.

The last column is the row that stands still at the start. The whole-body controller, as BiGym's own notes for its coding agents describe it: it follows velocity commands with some lag and wobble, so read the pelvis pose and close the loop rather than dead-reckon; a planar speed command below 0.055 m/s means standing still (use 0 or at least 0.06); standing still, the base drifts a few centimetres, and further while the hands push on furniture or the torso leans far (measured here: 0.27 m and 15 degrees with the hands pressing on a cabinet, 0.11 m and 24 degrees from a 0.8 rad lean); heights above about 0.8 m lock the knees (the pelvis stays near 0.78 m); squatting (a lower height) is how the hands reach low objects, and while squatting the controller does not step: walk first, then squat in place. It keeps the robot balanced but does not stop it from walking into things.

`spec()["joints"]` gives each arm, waist and finger joint's axis, a point on it and its range (the pelvis frame with
every joint at 0: `spec()["joint_frame"]`; the sign convention: `spec()["joint_sign"]`), `spec()["grippers"]` the point between each gripper's finger
pads on its wrist link, and `spec()["cameras"][camera]["mount"]` each camera's pose on its link. Keep your own copy of the last row you sent: a row rebuilt from the measured joint angles sits a little below
the targets the arms were holding (the servos track with a small error), so holding with it lets the arms sag. The
client's docstring explains the protocol with another benchmark's examples (`joint_position`, bounds [-1, 1], `imu`,
`links`, `depth`): for this task `spec()` is authoritative.

## Proprioception
Each row (`meta["proprio"]["now"]`, `res.proprio`) has, in `spec()["proprio_layout"]` order: the positions (`*_pos`) of the 3 waist joints (they show the lean you command), each arm's 7 joints (rad) and its gripper's 2 finger joints (slides, m), and the pelvis (`pelvis_x_pos`, `pelvis_y_pos`, `pelvis_z_pos` in m and `pelvis_rz_pos`, its heading, in rad: the room's frame, z up, heading 0 along the room's +x axis and counter-clockwise positive): 25 values; then their velocities (`*_vel`, per second) in the same order; then `left_gripper_state` and `right_gripper_state` (0 open .. 1 closed); then the pelvis pose again as the base controller tracks it (`pelvis_x`, `pelvis_y`, `pelvis_z`, `pelvis_yaw`). This is BiGym's own low-dimensional observation, the one its learned policies receive.

## External material
In this setting you act on the robot only through the `efe-robot` tools: you have no shell, you cannot run code and you cannot install packages. You may read anything installed in your container with your file-reading tools, the files the robot tools write included. Please solve the task yourself: do not look for a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed.

## Resources
Your container: **4 CPUs**, **4 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it with your file-reading tool before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result.
