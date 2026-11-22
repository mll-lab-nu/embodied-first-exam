# RoboLab · food_packing3_cans (standard-mcp-shell)

## Task
A Franka Panda arm with a Robotiq 2F-85 gripper at a table (NVIDIA RoboLab's DROID setup, Isaac Sim / PhysX). Pack
canned foods into the bin. The robot runs as a service you reach through the `efe-robot` MCP tools, their Python client
`efe_robot` or the service's own client, as if it were real hardware: one live episode.

## Goal
Success: the three cans (the Spam can, the tomato soup can and the tuna can) are all in the dark grey bin, and the
gripper has let go of them. "The gripper" means both fingers: an object that still touches either finger counts as held.
The episode ends as soon as the task is done, when your time is up, or on a simulator error. When your session ends with
the episode still running, your last command is held for 2 s more (30 control steps) while the task is still judged, so
a release you sent last completes.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is the Franka base (panda_link0): +X forward towards the table, +Y to the robot's left, +Z up; metres,
radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 7 joints, end-effector pose, gripper).
Cameras: `egocentric_mirrored_camera`, `over_shoulder_left_camera`, `wrist_cam`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (the error per goal), a `failure` category if a goal was not reached, the state and
  a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: The end-effector pose (goals and state) is the fingertip-centre tool frame; at the starting pose the gripper
points straight down. The gripper is binary (a value of 0.5 or more closes it) and switches at once; the reported
gripper value is the command, gripper_opening_m is the measured distance between the finger pads (about 0.085 m open,
about 0.002 m closed on nothing, more when closed on an object). An end-effector goal that also sets the gripper
switches the gripper at the start of the arm's motion: to grasp, reach first, then close the gripper in a separate
move_robot call. End-effector goals move in a straight line and do not avoid objects; each takes as long as the
controller needs (duration_s does not apply). The simulator runs at 15 control steps per simulated second and is slower
than real time. The episode ends by itself the moment the success condition holds.

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
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

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
- A busy service has not crashed. The service answers one request at a time: while a call runs (a long `submit` or a
  watching `get_obs` can take minutes; one call stops at `spec["max_call_wall_s"]`), every other request waits for it,
  `r.status()` from another process included. A client-side timeout while a call is in flight (for example a `requests`
  ReadTimeout on `r.status()`) means "busy": nothing restarts, the call runs to its end and the episode goes on from
  there. Keep one client process and wait for your call's answer.
- If the service crashes, the connection is refused or reset and the call is lost: the simulator restarts and resumes
  the same episode (never a reset) in the state after the last call it completed, which you may not have received.
  `r.wait_ready()` waits until it answers again (resuming replays the episode so far, which can take minutes; the wall
  clock keeps running); then check `r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).

### Actions
- `joint_position` (8): `panda_joint1..7, gripper`; radians, and the gripper command is binary (0 = open, 1 = closed; it
  switches at the row, never interpolated). Absolute targets tracked by PD controllers. Rows are `dt` apart
  (`1/15 ≤ dt ≤ 0.5` s, a multiple of the 15 Hz control period: 1/15, 2/15, ...; any other `dt` is rejected, never
  rounded); a chunk covers at most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the
  spec). Use `obs.meta["proprio"]["now"][:7]` for the current joints to move smoothly.
- `ee_pose` (8): `x y z qw qx qy qz gripper` in the env-local frame (the robot's root frame: the Franka base at the
  origin, x forward towards the table, y to its left, z up); quaternions wxyz. Each row is driven to by differential IK
  in closed loop (at most 0.25 m/s); a row that does not converge within 6 mm is reported in `meta["plan"]`. The pose is
  the fingertip-centre tool frame: the gripper flange moved 0.162 m along the approach axis to the ends of the closed
  fingertips (the pads extend ~5.7 cm back from there). At the reset pose the gripper points straight down. At most 50
  rows per submit; a position more than 2 m from the robot's base on any axis, or a zero quaternion, is rejected (400)
  and nothing moves.
- The Robotiq opens to 8.5 cm.

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

## Others
- Objects here: a dark grey bin, a Cheez-It box, a chocolate pudding box, a mustard bottle, a Spam can, a sugar box, a
  tomato soup can and a tuna can.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 8 CPUs, 24 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget (actions and simulated time are reported as cost); a technical cap ends the episode after
  100,000 control steps (1.9 h of simulated time), graded as it stands; at this service's speed (3-15 control steps/s)
  your time runs out long before.
