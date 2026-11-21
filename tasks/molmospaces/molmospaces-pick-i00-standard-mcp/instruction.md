# MolmoSpaces · pick — STANDARD MODE, MCP TOOLS ONLY (robot as a service, eai-standard/2.2)

**Task:** Pick up the pie.

You control a Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup) — **as if it were real hardware** — in one episode of Ai2's MolmoSpaces benchmark (an Objaverse object).
The simulator (upstream's own code: molmo-spaces 0.2.9, MuJoCo 3.5.0) runs in a service you cannot open. You get the `efe-robot` tools and one episode.

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
closed. Base frame of this robot: the robot base frame: the arm's fixed base (robot_spec.base.pose in describe_robot's
spec_file), +X the way the arm faces, +Y to its left, +Z up. Space `native` sends rows in the robot's own action types
exactly as the sections below describe them (their frame, units and gripper values).

**This robot** (Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup)): arm (arm: 7 joints,
end-effector pose, gripper). Cameras: `wrist_camera_zed_mini`, `droid_shoulder_light_randomization`,
`randomized_zed2_analogue_1`, `randomized_zed2_analogue_2`, `randomized_gopro_analogue_1`.

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

**Notes on this robot.** One control step is 1/15.152 s; the episode ends after spec_file max_control_steps steps (303,
the task's 20 s horizon), so keep moves short and direct. The arm takes joint positions; end-effector goals are solved
by the service's IK and sent as joint positions. gripper_opening_m is the measured distance between the fingertips.

## Rules (real-robot rules)
- **No reset.** One episode. You see the robot's cameras (RGB, depth if you ask) and its proprioception (joints,
  grippers, tool poses, velocities, efforts). No object poses, no success check.
- **The episode ends** after **303 control steps** (the benchmark's 20 s horizon at
  15.152 Hz; `spec["max_control_steps"]`, counted by `meta["control_steps"]`), when you submit `done`
  (`r.submit("done", [])`), or when your time is up.
- **Success** is upstream's `judge_success()` on the state at that moment: the object touches the robot and nothing else, and it is at least 1 cm higher than where it started. The task has to hold at the
  end: met earlier and undone by then does not count, so end the episode with `done` once it holds. The service
  judges your episode itself, on the state it ends in; it scores 1 if that state succeeds.
- Your only budget is the time limit (`## Time limit`), from your start (the service's `time_s` and `time_left_s`
  count from your first request to it, so `time_left_s` never reaches 0 before your time is up: plan by it).
  Simulated time only advances with your commands (and `get_obs(seconds=...)`).
- Nothing to hand in: the service records the episode and grades it.
- **If the service crashes**, a call fails with a connection error: it restarts and resumes the SAME episode (never a
  reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check `r.status()`.
- **Images are files.** The tools write camera images, depth and video under `/app/obs/` and return their paths with small JSON; open an image with your file-reading tool, or ask for small images in the result with `inline_cameras`.

## The robot service through its Python client (reference; act through the `efe-robot` tools above)
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service builds the episode)
spec = r.spec()                                # action types, limits, cameras (+ calibration), robot_spec, kinematics, budget
obs = r.get_obs()                              # obs.last[cam] -> uint8 (H, W, 3); obs.meta["proprio"] {"layout", "now"}
obs = r.get_obs(depth=True)                    # + obs.last_depth[cam] -> float32 (H, W) z-depth in m (0 = no reading)
res = r.submit("joint_position", A, dt=0.066)   # A: (T, 8) rows dt apart; res.video[cam], res.proprio, res.meta
obs = r.get_obs(seconds=2.0, video="mp4")      # hold the current targets and watch for 2 s (max 30; whole control
                                               # steps: obs.meta["seconds"] is what ran)
r.fk(q); r.ik({"gripper": pose7}, seed=q)        # upstream's kinematic model, no physics: tcp poses <-> joint positions
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time
```
Cameras: `wrist_camera_zed_mini`, `droid_shoulder_light_randomization`, `randomized_zed2_analogue_1`, `randomized_zed2_analogue_2`, `randomized_gopro_analogue_1` (`spec["cameras"][cam]`: intrinsics and mount; every response carries each camera's pose).
One call returns at most 1812 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

### `joint_position` (8)
`fr3_joint1`, `fr3_joint2`, `fr3_joint3`, `fr3_joint4`, `fr3_joint5`, `fr3_joint6`, `fr3_joint7`, `gripper`: the targets of upstream's joint-position controllers (fr3_joint1..7 in rad; gripper: the Robotiq command, 0 = open .. 255 = closed). At t = 0 the gripper is open and its target is 0. Rows are `dt` apart (a
whole multiple of the 0.066 s control period, at most 0.5 s: up to 0.462 s), `interpolate="linear"` (default) or
`"hold"` between rows; a chunk covers at
most 10 s; values outside the limits (`spec["action_types"]["joint_position"]["limits"]`) are clipped and listed in
`res.meta["clipped"]`. `obs.meta["proprio"]["now"]` starts with the measured positions of the row's joints, in row
order (`["layout"]` names every entry); the gripper entries of a row are commands in the units above, not the measured
openings. `q` for `r.fk` / `r.ik` follows `spec["kinematics"]["joint_names"]`; poses are x y z qw qx qy qz in the house's
world frame (z up, metres).

## External material
In this setting you act on the robot only through the `efe-robot` tools: you have no shell, you cannot run code and you cannot install packages. You may read anything installed in your container with your file-reading tools, the files the robot tools write included. Please solve the task yourself: do not look for a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed.

## Resources
Your container: **3 CPUs**, **4 GiB of memory**, **1024 processes and threads** and **12 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time the robot tools take counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. Every robot tool result reports `time_left_s`, the service's count of the same limit from your first tool call, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that call. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it with your file-reading tool before you decide that time is short, never guess. A robot tool that is still executing when its call has to return answers `pending` with an operation id: call `wait` with that `operation` to collect the result.
