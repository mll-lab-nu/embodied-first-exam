# RoboCasa365 · CerealAndBowl — STANDARD MODE, MCP TOOLS ONLY (robot as a service)

A **Franka Panda arm on an Omron mobile base** (with a torso lift) works in a kitchen: RoboCasa365's `CerealAndBowl` kitchen task (robosuite, MuJoCo).
**Task: Open the cabinet. Pick the cereal and bowl from the cabinet and place them on the counter next to the milk. Then close the cabinet.**
The scene is one frozen instance: the initial state of one of the benchmark's official demonstrations.

You control the robot **as if it were real hardware**: the simulator runs in a service you cannot open. You get the `efe-robot` tools and one episode.

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
closed. Base frame of this robot: the mobile base's starting placement: on the floor at the base's origin, +X the way
the arm faces, +Y the robot's left, +Z up; it stays where the base started (driving the base does not move this frame).
Space `native` sends rows in the robot's own action types exactly as the sections below describe them (their frame,
units and gripper values).

**This robot** (Franka Panda on an Omron mobile base with a torso lift (RoboCasa PandaOmron); the arm takes absolute
joint position targets): arm (arm: 7 joints, gripper). Cameras: `robot0_agentview_center`, `robot0_agentview_left`,
`robot0_agentview_right`, `robot0_eye_in_hand`.

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

**Notes on this robot.** The arm takes absolute joint position targets only (no end-effector command): describe_robot
gives the joint limits. The base and the torso lift are driven with execute_trajectory space native, action_type
joint_position (13 numbers, one row per 0.05 s control step): arm_joint1..7 (keep the current targets, cmd_* in
proprio_now), grip (+1 closes, -1 opens), base_x, base_y, base_yaw (the mobile base's velocities in its own frame,
normalised to [-1, 1]), torso (the lift's velocity, normalised), hybrid_mode (-1, the default). proprio_now has
eef_right_x/y/z (the grip site's position in the world frame), the joints (robot0_joint1..7,
mobilebase0_joint_mobile_forward/side/yaw, mobilebase0_joint_torso_height) and cmd_* (the last command). The poses the
tools report are in the base's starting placement. The cameras ride on the robot; each frame comes with its current
calibration.

## Rules (real-robot rules)
- **No reset.** What you knock over stays knocked over.
- **No privileged state.** You see what the robot's cameras see (RGB, optional depth, with each camera's
  calibration) and the robot's own state. No object poses, no scene layout, no success signal.
- Your only budget is the time limit (`## Time limit`; `meta["time_left_s"]` is the service's count of it). There is nothing
  to hand in: the service records the episode as the trajectory and grades it.
- Do not use the benchmark's demonstrations, trained policies or any published solution.
- **Images are files.** The tools write camera images, depth and video under `/app/obs/` and return their paths with small JSON; open an image with your file-reading tool, or ask for small images in the result with `inline_cameras`.

## Scoring
The episode runs until your time is up. The service then applies the environment's own success check for `CerealAndBowl` to
the state of the live episode **after the last executed control step**: the episode as the service ran it, nothing is
replayed. A success reached earlier and then lost does not count: end in the state you want graded and stop submitting.

The check for `CerealAndBowl` requires that the cereal and the bowl both touch the counter nearest the cabinet, and the cabinet is closed (every door at most 0.5% open, normalised).

How RoboCasa365's checks compute these terms (`robocasa/utils/object_utils.py`):
- *the gripper ends more than d m from X*: the distance from the robot's end-effector grip site to X's origin exceeds
  d. Opening the fingers is not enough: release, then move the hand away.
- *X is on / in Y* for an object Y (plate, tray, board, pan, pot, colander, tupperware, glass): X touches Y and their
  centres are within 0.7 × Y's horizontal radius of each other horizontally, unless a distance is given.
- *X touches* a counter, the dining counter or the stove: contact between X and that fixture.
- *X is inside* a fixture (a cabinet, the sink or one of its basins, the microwave): all eight corners of X's bounding
  box are within the fixture's interior region (5 cm tolerance).

## The robot service through its Python client (reference; act through the `efe-robot` tools above)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts: about a minute)
spec = r.spec()                               # control_dt, action layout + limits + kinds, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, robot0_eye_in_hand
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, end effector, last command
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z), current
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("joint_position", A, cameras=cams[:1], video="mp4")   # A: (T, 13) rows, one per control step
res.meta["done"], res.meta["reason"], res.meta["control_steps"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio; res.save("/app/runs/003")
```
- Action `joint_position`: the robot's native controller command, applied once per control step (`control_dt` =
  0.05 s; float64). 13 channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad, within the joint limits in `spec["action_types"]["joint_position"]` (`lower` / `upper`, from `r.spec()`)); `grip` (+1 closes, -1 opens); `base_x, base_y, base_yaw` -- the mobile base's velocities in its own frame (normalised, [-1, 1]); `torso` -- the torso lift's velocity; `hybrid_mode` (> 0: base mode; <= 0: arm mode, the default -1). Values are clipped to the limits. Rows are `dt` apart (default and minimum: `control_dt`; a chunk covers at
  most 10 s).
- `get_obs(seconds=s)` holds the robot still (delta channels zero, targets, grip and mode kept) while physics runs
  for `s` seconds; those control steps are part of the episode.
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.
- World frame: metres, z up.

One call returns at most 3000 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

## External material
In this setting you act on the robot only through the `efe-robot` tools: you have no shell, you cannot run code and you cannot install packages. You may read anything installed in your container with your file-reading tools, the files the robot tools write included. Please solve the task yourself: do not look for a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed.

## Resources
Your container: **4 CPUs**, **6 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it with your file-reading tool before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result.
