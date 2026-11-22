# YAMLab · HangMugOnTree-v0 (standard-mcp-shell)

## Task
Two I2RT YAM arms with parallel two-finger grippers on a workstation table (YAMLab's bimanual setup, Isaac Sim). Pick up
the mug with the **left** arm, hand it over to the **right** arm (the right gripper takes it, then the left one lets go,
with the mug kept lifted), and hang the mug on the mug tree, released by both grippers. The scene has the mug and the
mug tree on the table. The robot runs as a service you reach through the `efe-robot` MCP tools, their Python client
`efe_robot` or the service's own client, as if it were real hardware: one live episode.

## Goal
Success: the left gripper picks the mug up between its finger pads and lifts it clear of the table for a moment; the
right gripper then takes it while the left one lets go, holding the mug up on its own for about a second; then the mug
hangs on the mug tree, released by both grippers, steady for about a second. The steps count in this order, each for
good once done. An object falling off the table ends the episode as a failure. The episode ends as soon as the task is
done.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame: midway between the two arm bases at their mounting height, +X forward towards the far side of the
table, +Y towards the left arm, +Z up; the left arm's base is at (0, +0.305, 0) and the right arm's at (0, -0.305, 0);
metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: left (arm: 6 joints, end-effector pose,
gripper); right (arm: 6 joints, end-effector pose, gripper). Cameras: `top`, `left_wrist`, `right_wrist`.

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

This robot: At the start both arms are at their home pose (all joints 0, grippers open) with the tool frames pointing
forward (+X). The gripper value in the state is the finger target in force; gripper_opening_m is the measured opening
(0.095 m fully open; a gripper closed on an object stops above 0). Joint efforts (left_joint1_effort ...) in proprio_now
grow when an arm pushes on something. A joint goal for one arm also re-sends the other arm's measured joints. The
episode ends by itself at the first control step where the task's check holds.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
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
```

The service's first start in a trial compiles Isaac's shaders: `Robot()` can wait ~2-12 min (it prints its progress to
stderr once a minute). It gives up after 3600 s (`Robot(timeout=...)`) with
`RuntimeError("sim service unavailable ...")`: then call it again (nothing has happened in the episode yet; your wall
clock runs from the start of the trial).

Optional inputs (ask only for what you need):
- Depth: `r.get_obs(depth=True)` -> `obs.last_depth[cam]` float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned
  with `obs.last[cam]`; `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N,H,W), one map per frame (1 mm
  steps).
- Per frame: `res.frame_step` (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N,3,4 world -> camera, OpenCV
  axes). `spec["cameras"][cam]`: `intrinsic_cv` and `mount` (static pose, or a wrist camera on link `<arm>_link_6` with
  a fixed `link_T_cam_cv`).
- `r.fk(q12)` -> poses of `spec["kinematics"]["links"]`; `r.ik({"left_tcp": pose7}, seed=q12)` ->
  `{"ok", "q", "error"}`: stateless models of both arms (no physics, no simulated time); `q12` = left joint1..6 then
  right joint1..6.
- `res.group("joint_vel")`: proprio columns by group name (`spec["proprio_groups"]`).

If the service crashes, a call fails with a connection error: the simulator restarts and resumes the SAME episode (never
a reset) in the state after the last call it completed, which you may not have received. `r.wait_ready()` waits until it
answers again (resuming replays the episode so far, which can take minutes; the wall clock keeps running), then check
`r.status()["control_steps"]` before you continue (`spec["on_service_error"]`). One call returns at most 5412 images.

### Actions
- `joint_position` (14): `left_joint1..6, left_gripper, right_joint1..6, right_gripper`, YAMLab's own action. Joints:
  absolute targets (rad) tracked by PD controllers. Gripper: the position target of that arm's finger in metres,
  **-0.0475 = fully open .. 0.0 = closed** (continuous; a closing gripper stops at whatever is between its fingers).
  Rows are `dt` apart (`1/30 ≤ dt ≤ 0.5` s, a multiple of the 30 Hz control period: 1/30, 2/30, ...; any other `dt` is
  rejected, never rounded); `interpolate="linear"` (default) or `"hold"`; a chunk may cover at most 10 s; out-of-limit
  values are clipped and listed in `meta["clipped"]` (limits in the spec). Start from `obs.meta["proprio"]["now"]` (the
  first 14 columns are the measured joints and fingers) to move smoothly.
- `ee_pose` (16): per arm, left then right, `x y z qw qx qy qz gripper` in the world frame (metres; x forward from the
  arm bases towards the far side of the table, y to the left, z up; quaternions wxyz). Each row drives both tool frames
  to their targets together by differential IK in closed loop (at most 0.25 m/s); an arm that does not converge within 6
  mm is reported in `meta["plan"]`. The tool frame `<arm>_tcp` is the midpoint of that gripper's two fingertips, 0.1426
  m from `link_6` along `link_6`'s +z (approach) axis, with `link_6`'s orientation. At the start both arms are at their
  home pose (all joints 0, grippers open), tool frames pointing forward. At most 50 rows per submit; a position more
  than 3 m from the world origin on any axis, or a zero quaternion, is rejected (400), nothing moves.
- A malformed request (a wrong type, a value out of range) is answered 400 with the reason and executes nothing.
- Control runs at 30 Hz (simulated time; sim dt 1/120 s, decimation 4).

### Observations
- Cameras (640×480 each): `top` (static, above the table looking down at the workspace), `left_wrist` and `right_wrist`
  (on each arm's wrist; they move: every frame comes with its pose).
- In the spec: `robot_spec` (joints and their limits, grippers, controller gains, tool frames, the arm bases), `world`
  (frame, units, wxyz), `proprio_groups` (joint_pos, tcp_pose, gripper_cmd, joint_vel, gripper_opening, joint_effort).

## Others
- The left gripper's fingers grip the mug harder from its first grasp of the mug until both grippers hold it (YAMLab's
  own handover aid), so the left hand can hold the mug firmly while the right one takes it.

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
- Resources: 5 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; a technical cap ends the episode after 100,000 control steps (1/30 s each, about 56 min of
  simulated time), graded as it stands. The service runs 60-120 control steps per second, so long watches can reach it.
