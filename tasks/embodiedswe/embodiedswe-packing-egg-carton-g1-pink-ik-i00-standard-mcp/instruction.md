# Put three eggs in the carton and close the lid (Unitree G1, fixed pelvis, Pink IK) — standard mode — MCP tools only

The task of `embodiedswe-packing-egg-carton-g1-pink-ik-i00-privileged`, on the same frozen scene. You drive a Unitree G1 humanoid with three-finger hands, its pelvis fixed, its arms and waist under EmbodiedSWE's Pink IK, as if it were real hardware: the simulator runs in a service you cannot open, and you get the `efe-robot` tools, one episode and no reset. The client's docstring is its manual (`/opt/tools/rcb_client.py`); `r.spec()` gives the numbers.

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
closed. Base frame of this robot: the pelvis: origin at the pelvis, +X the way the pelvis faces, +Y to the robot's left,
+Z up (levelled). Space `native` sends rows in the robot's own action types exactly as the sections below describe them
(their frame, units and gripper values).

**This robot** (Unitree G1 humanoid with two Dex3 three-finger hands, pelvis fixed to the world, upper body driven by
EmbodiedSWE's Pink IK): left (arm: end-effector pose); right (arm: end-effector pose); hands (hand: 14 joints). Cameras:
`overview`, `head`.

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
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, rows `dt` seconds
  apart; a long one can come from a file under `/app` (`.npy` / `.csv` of native rows, `.json` of rows).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time. A call still executing after 45 s returns `{"pending": true, "operation": id}` while the
  robot goes on executing it: call `wait(operation=id)` (it waits up to 45 s more each time) for its result. A result
  with `"episode_over": true` means the episode has ended.
- Nothing needs to be saved: the server records every tool call, and the service records the episode.

**Notes on this robot.** Each arm takes its wrist pose (the left_wrist_yaw_link / right_wrist_yaw_link frame; the palm
and fingers extend beyond it). EmbodiedSWE's Pink IK solves the waist and both arms (17 joints) for the two wrist
targets together, so moving one wrist can shift the waist and the other arm a little. The pelvis is fixed to the world
(the legs are locked). The part hands takes the 14 Dex3 hand joint targets (rad) of both hands in the order
describe_robot lists them (each joint's name says its hand and finger): send all 14, copying the current targets
(observe: parts.hands.joint_positions) for the joints you leave alone. There is no single gripper value: close and open
a hand through its joint targets (their limits: describe_robot's spec_file, action_types.ee_pose.joint_limits); a target
past a joint's limit presses the joint against it. Each arm's gripper_opening_m is the distance from that hand's thumb
tip to the midpoint of its index and middle fingertips. The measured joint angles are in observe's proprio_now (its
layout: describe_robot's spec_file, proprio_layout). One episode, no reset; it ends by itself once the task is complete.

## The task
Four loose eggs lie on their sides on the left half of the table. On the right is a small four-cell egg carton fixed to the table, with its hinged lid standing fully open. The carton has four distinct pockets in a 2 by 2 layout.
Goal (three stages): pick eggs from the table one at a time, turn each upright, and place three eggs securely in three DISTINCT carton pockets; then push the hinged lid closed over them. Every seated egg must remain upright and settled, and the lid must rest closed at the end. The fourth egg is a distractor and can stay on the table.

Success, exactly: at the end of the run three different pockets of the 2 x 2 carton each hold a seated egg (at least three eggs seated, at least three distinct pockets occupied). Pocket centres are 30 mm from the carton's centre along each of its two base axes. An egg counts as seated when, in the carton's base frame (origin at the carton's bottom centre, z along the carton's up), its centre is within 21 mm horizontally of a pocket centre and 15-42 mm above the carton base, its long axis is within 50° of the carton's vertical (either end up), and it moves slower than 0.05 m/s. The hinged lid is within 7° of fully shut; it starts 110° open. All four eggs, the spare included, move slower than 0.05 m/s, and the lid swings slower than 0.10 rad/s. Not true at the start.

## This robot
- Action: `ee_pose` only, 28 values: the world poses of the left and right `wrist_yaw_link` (`x y z qw qx qy qz` each), then 14 hand joint targets (rad). Rows are streamed at the 60 Hz control rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates are the simulator's world frame (metres, z up; `spec["world"]`).
- Cameras (RGB 640×480, depth on request): `overview` (static) and `head` (on the torso, where the real G1 carries its depth camera). One call returns at most 240 images (`max_frames_per_call`, PROTOCOL §3 "Images per call": cameras × the frames captured, the first, one every round(60 / `video_fps`) control steps and the last, a per-frame depth one more image; `video="none"` captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no cameras gets `overview`, `head` at 3 frames per second, so every call up to `max_chunk_s` / `max_watch_s` fits.
- The episode ends after the first call at whose end the success condition holds (judged on the live simulator), when your time is up, on a simulator error, or after 400,000 control steps (1.9 h of simulated time, reason `step_guard`); it is graded as it stands then. Simulated time advances only inside your calls.
- The service answers one request at a time: while a long call runs, every other request waits, so a client-side timeout means "busy", not "crashed".

## External material
In this setting you act on the robot only through the `efe-robot` tools: you have no shell, you cannot run code and you cannot install packages. You may read anything installed in your container with your file-reading tools, the files the robot tools write included. Please solve the task yourself: do not look for a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed.

## Resources
Your container: **8 CPUs**, **24 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it with your file-reading tool before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result.
