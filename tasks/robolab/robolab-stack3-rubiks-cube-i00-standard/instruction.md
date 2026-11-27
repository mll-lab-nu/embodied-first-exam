# RoboLab · stack3_rubiks_cube (standard)

## Task
Stack the 3 Rubik's cubes into one tower.

## Goal
Success: the three Rubik's cubes form one tower, in any order, each cube resting squarely on the one below it.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.

## Robot Interface
A Franka Panda arm with a Robotiq 2F-85 gripper at a table (NVIDIA RoboLab's DROID setup, Isaac Sim / PhysX). The robot
runs as a service you reach through its client or its MCP tools, as if it were real hardware: one live episode.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.2`):
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while Isaac Sim starts and builds the scene, ~2 min; longer on a
                                              # busy host: it reports its progress on stderr and gives up after 3600 s)
spec = r.spec()                               # action types, dims, joint limits, cameras, budget, robot spec

obs = r.get_obs()                             # current frames from 3 cameras: obs.last[cam] -> uint8 (H,W,3)
obs.meta["proprio"]                           # {"layout": [...32 names], "now": [...]}: joints, gripper, end-effector pose, ...
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl at the LAST frame
obs = r.hold(2.0)                             # hold the last command for 2 s of robot time: obs.video[cam] = mp4 bytes
obs = r.get_obs(last_s=1.0)                   # the frames recorded over the last 1 s (reading moves no time)

res = r.submit("joint_position", A, dt=0.2)   # A: (T, 8) rows dt seconds apart; streamed at 15 Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 8) fingertip-centre targets; differential IK per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["wrist_cam"]                        # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["wrist_cam"]                       # uint8 (N,H,W,3) at video_fps if requested
res.last["egocentric_mirrored_camera"]; res.proprio   # last frame per camera; float32 (N, 32) proprio at each video frame
```
- Optional inputs (ask only for what you need): `r.get_obs(depth=True)` -> `obs.last_depth[cam]`, float32 (H, W);
  `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N, H, W), one map per frame. Per frame: `res.frame_step`
  (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N, 3, 4, world -> camera, OpenCV axes). Proprio groups:
  `res.group("joint_vel")`.
- Kinematics: `r.fk(q7)` -> poses of `spec["kinematics"]["links"]`; `r.ik({"tcp": pose7}, seed=q7)` ->
  `{"ok", "q", "error"}`: a stateless model of the arm (no physics, no simulated time).
- A malformed request (a wrong type, a value out of range) is answered 400 with the reason and executes nothing. One
  call returns at most 2712 images.
- A busy service has not crashed. The service answers one request at a time. While a call runs, every other request
  waits for it, including `r.status()` from another process. A long `submit` or a long `hold` can take minutes; one call
  stops at `spec["max_call_wall_s"]`. A client-side timeout while a call is in flight (for example a `requests`
  ReadTimeout on `r.status()`) means "busy". Nothing restarts: the call runs to its end and the episode goes on from
  there. Keep one client process and wait for your call's answer.
- If the service crashes, the connection is refused or reset and the call is lost. The simulator then restarts and
  resumes the same episode (never a reset) from the state after the last call it completed. You may not have received
  that call's answer. `r.wait_ready()` waits until it answers again. Resuming replays the episode so far, which can take
  minutes, and the wall clock keeps running. Then check `r.status()["control_steps"]` before you continue
  (`spec["on_service_error"]`).

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`)
  and returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/`
  (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
- `joint_position` (8): `panda_joint1..7, gripper`; radians, and the gripper command is binary (0 = open, 1 = closed; it
  switches at the row, never interpolated). Absolute targets tracked by PD controllers. Rows are `dt` apart:
  `1/15 ≤ dt ≤ 0.5` s, a multiple of the 15 Hz control period (1/15, 2/15, ...). Any other `dt` is rejected, never
  rounded. A chunk covers at most 10 s. Out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the
  spec). Use `obs.meta["proprio"]["now"][:7]` for the current joints to move smoothly.
- `ee_pose` (8): `x y z qw qx qy qz gripper` in the env-local frame (the robot's root frame: the Franka base at the
  origin, x forward towards the table, y to its left, z up); quaternions wxyz. Closed-loop differential IK drives the
  arm to each row (at most 0.25 m/s). A row that does not converge within 6 mm is reported in `meta["plan"]`. The pose
  is the fingertip-centre tool frame: the gripper flange moved 0.162 m along the approach axis to the ends of the closed
  fingertips (the pads extend ~5.7 cm back from there). At the reset pose the gripper points straight down. At most 50
  rows per submit; a position more than 2 m from the robot's base on any axis, or a zero quaternion, is rejected (400)
  and nothing moves.
- The Robotiq opens to 8.5 cm.

When your session ends with the episode still running, your last command is held for about two seconds more while the
task is still judged, so a release you sent last completes.

### Observations
- Cameras: `egocentric_mirrored_camera` (static, facing the robot across the table, 864×480),
  `over_shoulder_left_camera` (static, over the robot's left shoulder, 1280×720) and `wrist_cam` (on the gripper,
  1280×720; it moves: each frame comes with its pose). Depth on request: z-depth in metres (1 mm steps), 0 = no reading,
  pixel-aligned with the RGB. Calibration: `spec["cameras"][cam]` has `intrinsic_cv` and `mount` (a static pose, or
  `wrist_cam` on link `base_link` with a fixed `link_T_cam_cv`).
- Proprioception (32 columns): joints, gripper, end-effector pose, velocities and drive efforts, in the groups of
  `spec["proprio_groups"]` (joint_pos, joint_vel, tcp_pose, gripper_opening, joint_effort).
- Robot and world facts: `spec["robot_spec"]` has the joints and their limits, the gripper, the controller gains and the
  tool frames; `spec["world"]` has the frame, units and quaternion order (wxyz).

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 8 CPUs, 24 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget (actions and simulated time are reported as cost); a technical cap ends the episode after
  100,000 control steps (1.9 h of simulated time), graded as it stands; at this service's speed (3-15 control steps/s)
  your time runs out long before.
- Finish: if you never send `/finish`, the episode is graded when your session ends.
