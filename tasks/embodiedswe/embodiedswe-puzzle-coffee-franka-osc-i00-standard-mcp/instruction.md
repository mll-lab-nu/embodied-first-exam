# Make and serve a capsule coffee (Franka, operational-space control) — standard mode — MCP tools only

The task of `embodiedswe-puzzle-coffee-franka-osc-i00-privileged`, on the same frozen scene. You drive a Franka Panda arm with its parallel gripper, under EmbodiedSWE's operational-space (torque) controller, as if it were real hardware: the simulator runs in a service you cannot open, and you get the `efe-robot` tools, one episode and no reset. The client's docstring is its manual (`/opt/tools/rcb_client.py`); `r.spec()` gives the numbers.

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
closed. Base frame of this robot: the arm's base (panda_link0), at world (0, -0.55, 0.55) and turned 90 degrees about z:
+X forward (world +y), +Y left (world -x), +Z up. Space `native` sends rows in the robot's own action types exactly as
the sections below describe them (their frame, units and gripper values).

**This robot** (Franka Emika Panda arm with the Franka Hand parallel gripper on a fixed base, driven by EmbodiedSWE's
operational-space (torque) controller): arm (arm: 2 joints, end-effector pose). Cameras: `overview`, `wrist`.

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

**Notes on this robot.** The arm takes end-effector poses only, tracked by EmbodiedSWE's operational-space (torque)
controller; its seven joints take no direct command. The end-effector pose is the panda_hand frame, not the fingertips:
the point midway between the fingertips is 0.1034 m along the hand's own +Z (approach) axis from it, so for a top-down
grasp put panda_hand 0.1034 m above the grasp point. The arm's two joint_positions are the finger position targets
(finger_1, finger_2, metres each: 0 = closed, 0.04 = open): send both together, e.g. [0.04, 0.04] to open and [0.0, 0.0]
to close; a closed target on an object squeezes it. gripper_opening_m in the state is the measured distance between the
finger pads (about 0.08 fully open). The measured joint angles are in observe's proprio_now (its layout:
describe_robot's spec_file, proprio_layout). One episode, no reset; it ends by itself once the task is complete.

## The task
A capsule coffee machine (0.17 x 0.64 x 0.40 m: a brew tower in front, its water tank behind) stands on a sturdy table with its spout facing -y. On its top: a SLIDING pod-bay cover with a raised grip ridge at its front edge (slide it toward the spout side to open — about 12 cm of travel), and behind the cover a green-capped START key that presses straight DOWN. Under the spout: a built-in cup platform. A green run lamp sits on the top's front rim. On the serving tray to the right: an empty green mug and a coffee capsule (burgundy dome, silver flange).
The machine runs itself by strict rules: it only brews with the cover CLOSED, a capsule seated in the bay, and the mug standing centred under the spout (within 5 cm of its axis) — otherwise START refuses. The brew then runs ~5 s while the run lamp glows and coffee streams into the mug; sliding the cover open mid-brew ABORTS it, and so does removing the mug (a spill) — start over. Pressing START mid-brew stops it. When the brew completes, the mug is filled — its contents turn dark.
Do the full service: open the bay, drop the capsule in, close the bay, stage the mug, press START, WAIT out the brew, then set the filled mug back down upright on the serving tray.
Goal: the mug filled by a completed brew and resting on the tray. The cover ridge, the capsule and the mug rim hold in a firm pinch: close the fingers across them and the grip locks; open wide to release.

Success, exactly: a brew has completed at some point in the run — after START was accepted (cover closed, capsule seated, mug under the spout), 600 physics substeps (5.0 s) elapsed with the cover never more than 10 mm open and the mug never leaving the spout spot (centre within 50 mm horizontally of the spout axis, bottom within 20 mm of the cup platform top, tilt <= 20 deg) and without a second START press — and now the green mug stands on the serving tray: centre within 159 mm horizontally of the tray centre, mug axis within 20 deg of vertical, mug bottom within 15 mm of the tray dish floor (20 mm above the table top), mug moving slower than 0.05 m/s. Not true at the start.

## This robot
- Action: `ee_pose` only, 9 values: the world pose of `panda_hand` (`x y z qw qx qy qz`) and the two finger position targets (m, 0 closed, 0.04 open). Rows are streamed at the 15 Hz control rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates are the simulator's world frame (metres, z up; `spec["world"]`).
- Cameras (RGB 640×480, depth on request): `overview` (static) and `wrist` (on the hand). One call returns at most 240 images (`max_frames_per_call`, PROTOCOL §3 "Images per call": cameras × the frames captured, the first, one every round(15 / `video_fps`) control steps and the last, a per-frame depth one more image; `video="none"` captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no cameras gets `overview`, `wrist` at 4 frames per second, so every call up to `max_chunk_s` / `max_watch_s` fits.
- The episode ends after the first call at whose end the success condition holds (judged on the live simulator), when your time is up, on a simulator error, or after 400,000 control steps (7.4 h of simulated time, reason `step_guard`); it is graded as it stands then. Simulated time advances only inside your calls.
- The service answers one request at a time: while a long call runs, every other request waits, so a client-side timeout means "busy", not "crashed".

## External material
In this setting you act on the robot only through the `efe-robot` tools: you have no shell, you cannot run code and you cannot install packages. You may read anything installed in your container with your file-reading tools, the files the robot tools write included. Please solve the task yourself: do not look for a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed.

## Resources
Your container: **8 CPUs**, **24 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it with your file-reading tool before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result.
