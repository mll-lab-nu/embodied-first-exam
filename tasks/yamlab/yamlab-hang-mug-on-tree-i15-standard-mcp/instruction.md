# YAMLab · HangMugOnTree-v0 — STANDARD MODE, MCP TOOLS ONLY (robot as a service, eai-standard/2.2)

You control two **I2RT YAM arms with parallel two-finger grippers** on a workstation table (YAMLab's bimanual setup)
**as if they were real hardware**: the simulator runs in a service you cannot open. You get the `efe-robot` tools and one episode.
**Task:** Pick up the mug with the **left** arm, hand it over to the **right** arm (the right gripper takes it, then the left one lets go, with the mug kept lifted), and hang the mug on the mug tree, released by both grippers. The scene has the mug and the mug tree on the table.

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

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the robot base frame: midway between the two arm bases at their mounting height, +X
forward towards the far side of the table, +Y towards the left arm, +Z up; the left arm's base is at (0, +0.305, 0) and
the right arm's at (0, -0.305, 0). Space `native` sends rows in the robot's own action types exactly as the sections
below describe them (their frame, units and gripper values).

**This robot** (two I2RT YAM 6-joint arms with parallel two-finger grippers on a workstation table (YAMLab's bimanual
setup)): left (arm: 6 joints, end-effector pose, gripper); right (arm: 6 joints, end-effector pose, gripper). Cameras:
`top`, `left_wrist`, `right_wrist`.

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
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time. A call still executing after 45 s returns `{"pending": true, "operation": id}` while the
  robot goes on executing it: call `wait(operation=id)` (it waits up to 45 s more each time) for its result. A result
  with `"episode_over": true` means the episode has ended.
- Nothing needs to be saved: the server records every tool call, and the service records the episode.

**Notes on this robot.** At the start both arms are at their home pose (all joints 0, grippers open) with the tool
frames pointing forward (+X). The gripper value in the state is the finger target in force; gripper_opening_m is the
measured opening (0.095 m fully open; a gripper closed on an object stops above 0). Joint efforts (left_joint1_effort
...) in proprio_now grow when an arm pushes on something. A joint goal for one arm also re-sends the other arm's
measured joints. The episode ends by itself at the first control step where the task's check holds.

## Success
1. **pick**: the **left** gripper grasps the mug (YAMLab's grasp detection: both fingers of that gripper touch the mug with at least 0.1 N, on their pads) and the mug's centre is more than 5 cm above its resting height, for 8 consecutive control steps;
2. **handover**: the **right** gripper grasps the mug, the left gripper does not, and the mug's centre stays more than 5 cm above its resting height, for 30 consecutive control steps (as in YAMLab, the left fingers' friction is raised when the left gripper first grasps the mug and lowered again when both grippers hold it: YAMLab's own handover aid);
3. **hang**: the mug's centre within 0.11462 m (horizontally) of the mug tree's centre and more than 5 cm above the height it would rest at on the table, **neither** gripper grasping it, and its height steady (within 3.0 cm of where this stage started), for 30 consecutive control steps.

Each condition must hold for the stated number of consecutive control steps (1/30 s each); the stages count in order and
stay counted once reached. The episode **ends by itself** at the first control step where every stage has been reached
(success), or when a task object falls off the table (failure).

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, when an object falls off the table, when
  your time is up, or on a simulator error. A dropped or knocked-over object stays that way.
- **No privileged state.** You see what the cameras see (RGB, and depth if you ask) plus the robot's own proprioception
  (joints, grippers, tool-frame poses, velocities, drive efforts). No object poses, no success signal.
- There is no step budget: the time limit (`## Time limit`) is your only budget (`meta["time_left_s"]`). Actions and simulated time
  are reported as cost. One technical cap: the episode ends after **100,000 control steps** (55.6 min of simulated time;
  `spec["max_control_steps"]`, reason `step_guard`) and is graded as it stands. The service steps faster than real time
  (60-120 control steps/s), so long watches and far-away `ee_pose` targets can reach it: `meta["control_steps"]` counts.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. The episode is graded as it stands when your time is up: keep working until it has
  succeeded.
- **If the service crashes**, a call fails with a connection error: the simulator restarts and resumes the SAME episode
  (never a reset) in the state after the last call it completed, which you may not have received. `r.wait_ready()` waits
  until it answers again (resuming replays the episode so far, which can take minutes; the wall clock keeps running), then
  check `r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).
- **Images are files.** The tools write camera images, depth and video under `/app/obs/` and return their paths with small JSON; open an image with your file-reading tool, or ask for small images in the result with `inline_cameras`.

## The robot service through its Python client (reference; your code cannot reach it: act through the `efe-robot` tools above)
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and builds the scene (see below)
spec = r.spec()                               # action types, dims, joint limits, cameras, budget, robot spec

obs = r.get_obs()                             # current frames from 3 cameras: obs.last[cam] -> uint8 (480, 640, 3)
obs.meta["proprio"]                           # {"layout": [...58 names], "now": [...]}: joints, grippers, tool poses, ...
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl at the LAST frame
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 14) rows dt seconds apart; streamed at 30 Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 16) tool-frame targets of both arms; differential IK per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["top"]                              # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["left_wrist"]                      # uint8 (N,H,W,3) at video_fps if requested
res.last["right_wrist"]; res.proprio          # last frame per camera; float32 (N, 58) proprio at each video frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy
```
The service's first start in a trial compiles Isaac's shaders: `Robot()` can wait ~2-12 min (it prints its progress to
stderr once a minute). It gives up after 3600 s (`Robot(timeout=...)`) with `RuntimeError("sim service unavailable ...")`:
then call it again (nothing has happened in the episode yet; your wall clock runs from the start of the trial).

Cameras (640×480 each): `top` (static, above the table looking down at the workspace), `left_wrist` and `right_wrist` (on
each arm's wrist; they move: `res.extrinsic_cv[cam]` has their pose at every frame).

### Optional inputs (eai-standard/2.2; ask only for what you need)
- Depth: `r.get_obs(depth=True)` -> `obs.last_depth[cam]` float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned
  with `obs.last[cam]`; `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N,H,W), one map per frame (1 mm steps).
- Per frame: `res.frame_step` (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N,3,4 world -> camera, OpenCV
  axes). `spec["cameras"][cam]`: `intrinsic_cv` and `mount` (static pose, or a wrist camera on link `<arm>_link_6` with a
  fixed `link_T_cam_cv`).
- `spec["robot_spec"]` (joints and their limits, grippers, controller gains, tool frames, the arm bases), `spec["world"]`
  (frame, units, wxyz), `spec["proprio_groups"]` + `res.group("joint_vel")` (joint_pos, tcp_pose, gripper_cmd, joint_vel,
  gripper_opening, joint_effort).
- `r.fk(q12)` -> poses of `spec["kinematics"]["links"]`; `r.ik({"left_tcp": pose7}, seed=q12)` -> `{"ok", "q", "error"}`:
  stateless models of both arms (no physics, no simulated time); `q12` = left joint1..6 then right joint1..6.

### Action types
- `joint_position` (14): `left_joint1..6, left_gripper, right_joint1..6, right_gripper`, YAMLab's own action. Joints:
  absolute targets (rad) tracked by PD controllers. Gripper: the position target of that arm's finger in metres,
  **-0.0475 = fully open .. 0.0 = closed** (continuous; a closing gripper stops at whatever is between its fingers). Rows
  are `dt` apart (`1/30 ≤ dt ≤ 0.5` s, a multiple of the 30 Hz control period: 1/30, 2/30, ...; any other `dt` is
  rejected, never rounded); `interpolate="linear"` (default) or `"hold"`; a chunk may cover at most 10 s; out-of-limit
  values are clipped and listed in `meta["clipped"]` (limits in the spec). Start from `obs.meta["proprio"]["now"]` (the
  first 14 columns are the measured joints and fingers) to move smoothly.
- `ee_pose` (16): per arm, left then right, `x y z qw qx qy qz gripper` in the world frame (metres; x forward from the
  arm bases towards the far side of the table, y to the left, z up; quaternions wxyz). Each row drives both tool frames to
  their targets together by differential IK in closed loop (at most 0.25 m/s); an arm that does not converge within 6 mm is
  reported in `meta["plan"]`. The tool frame `<arm>_tcp` is the midpoint of that gripper's two fingertips, 0.1426 m from
  `link_6` along `link_6`'s +z (approach) axis, with `link_6`'s orientation. At the start both arms are at their home pose
  (all joints 0, grippers open), tool frames pointing forward. At most 50 rows per submit; a position more than 3 m from
  the world origin on any axis, or a zero quaternion, is rejected (400), nothing moves.
  One call returns at most 5412 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").
- A malformed request (a wrong type, a value out of range) is answered 400 with the reason and executes nothing.
- Control runs at 30 Hz (simulated time; sim dt 1/120 s, decimation 4).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the files the robot tools write included. You may write and run code to compute; every robot command and observation must go through the `efe-robot` MCP tools; code must not contact the simulator. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **5 CPUs**, **4 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
