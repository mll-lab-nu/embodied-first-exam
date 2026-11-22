# IKEA MuJoCo · EKET cabinet (standard-mcp-shell)

## Task
Two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled), at a table
(RoboARC's IKEA furniture-assembly suite, MuJoCo). Build the EKET cabinet frame: slide the two side panels into the top
panel, then the back panel into its grooves, then the bottom panel onto the sides, and leave the cabinet standing on the
table on its own. The robot runs as a service you reach through the `efe-robot` MCP tools, their Python client
`efe_robot` or the service's own client, as if it were real hardware: one live episode.

## Goal
Success: the cabinet frame is built in the order given above (side A into the top panel, then side B, then the back
panel into its grooves, then the bottom panel onto the sides), every panel in its assembled place, the back included,
and the four frame joints latched; the cabinet stands on the table on its own, nothing touching the floor, and the robot
touches no panel, with everything at rest. Do not force parts into one another: a simulator breakdown (parts pressed
deep into each other) ends the episode at once, without success. When all of this holds, the service checks it once more
after holding your last command for a second more (on a copy: the robot does not move); if it still holds, the episode
ends as a success, and if not, the episode goes on and you can still fix it.

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
robot base frame: the left arm's base link (the origin of the service's frame), +X that arm's forward direction, +Z up;
the right arm's base pose in it is spec robot_spec.base.right; metres, radians, quaternions `wxyz`, gripper 0 open .. 1
closed. Parts: left (arm: 7 joints, end-effector pose, gripper); right (arm: 7 joints, end-effector pose, gripper).
Cameras: `cam_high`, `cam_low`, `cam_left_wrist`, `cam_right_wrist`.

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

This robot: The arms take joint targets only: an end-effector goal is solved with the service's inverse kinematics
(damped least squares on the robot model, no collision checking, within 1 mm and 0.01 rad) and sent as joint rows.
Control runs at 400 Hz (2.5 ms per control step). Arm joint targets move at most at the arm's joint speed limits (spec
robot_spec.controller); a faster request takes the control steps it needs. The gripper command switches at the row.
Grasps are physical: friction from the finger contacts, nothing attaches a part to a gripper. The episode ends by itself
at the first settled success (the task's requirements hold, no robot link touches any part and every part is at rest,
then again after the last row is held 1 s more), on a simulator breakdown (reason sim_breakdown) or when your time is
up; there is no step budget and nothing to signal. The gripper value in the state is the command in force;
gripper_opening_m is the measured opening. Actuator forces (proprio_now, *_effort) rise when an arm pushes on something.

### Client
`/opt/tools/rcb_client.py` (already installed; `python` from any directory):
```python
from rcb_client import Robot
r = Robot()                                    # finds the service (sim:8000 / localhost:8000), waits until it is ready
spec = r.spec()                                # action layout and limits, cameras (intrinsics, mounts), proprio layout, world frame, budget
obs = r.get_obs()                              # current frames: obs.last[cam] -> uint8 (480, 848, 3)
obs = r.get_obs(depth=True)                    # + obs.last_depth[cam] -> float32 (480, 848) z-depth in metres (0 = no reading)
obs.meta["cameras"][cam]                       # intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl
obs.group("tcp_pose", now=True)                # proprio groups: joint_pos, joint_vel, gripper_opening, tcp_pose, joint_cmd, joint_effort
res = r.submit("joint_position", rows, dt=0.0025, interpolate="linear", cameras=["cam_high"], video="mp4")
res.meta["executed_rows"], res.meta["clipped"], res.meta["done"], res.meta["reason"], res.meta["time_left_s"]
res.video["cam_high"]                          # mp4 bytes of the chunk; video="frames" gives res.frames[cam] (N, H, W, 3)
obs = r.get_obs(seconds=2.0)                   # hold the last command, simulate 2 s and return the video (<= 30 s)
r.fk(q); r.ik({"left_tcp": [x, y, z, qw, qx, qy, qz]})   # stateless kinematics on the robot's model
r.status()                                     # calls, control steps, done, reason, time left
```

A connection error means the service crashed and is resuming the SAME episode: call `r.wait_ready()` and check
`r.status()` before you continue (`spec()["on_service_error"]`). One call returns at most 1000 images.

One control step takes about 5.0 ms of wall clock here (the simulation runs at about 0.50x real time), so a `submit` of
the maximum 10 s chunk takes about 20 s. The client waits long enough for any call; a client timeout or a connection
error means the connection or the service failed (above), not that the call is still on its way: do not resend it
blindly. `r.operation_status()` (the last call's operation, or `r.operation_status(operation_id)`) asks the service what
became of a call.

### Actions
- **Action** `joint_position`: rows of 16 values, float32 or float64, layout
  `spec()["action_types"]["joint_position"]["layout"]`: per arm (`left_`, then `right_`): `actuator1`..`actuator7` =
  joint position targets (rad; joint 7, the wrist, has no joint limit in these scenes, unlike the real Panda),
  `actuator8` = gripper command (0 = closed, 255 = open; the hand squeezes at its tendon force limit, about 70 N per
  finger, at any width when commanded 0). One control step is 2.5 ms (400 Hz: the row is applied for 4 physics steps of
  0.625 ms). `dt` must be a multiple of 0.0025 s (at most 0.5 s); `hold` keeps each row for its `dt`, `linear`
  interpolates the arm targets. A chunk covers at most 10 s. Out-of-range values are clipped to the actuator's control
  range and reported in `meta["clipped"]`. Speed rule (the robot's real limits; clamp, not fail): arm joint targets move
  at most 0.0054375 rad per control step on joints 1-4 (`actuator1`..`actuator4`: 2.175 rad/s) and 0.006525 rad on
  joints 5-7 (`actuator5`..`actuator7`: 2.61 rad/s), the Franka Panda's joint velocity limits
  (`spec()["robot_spec"]["controller"]`); a row that asks for more takes the control steps it needs, and
  `meta["clipped"]` says so. The gripper command is not limited: it switches at the row. The arms are position servos
  with the scene's gains and force limits; use `obs.group("joint_cmd", now=True)` as the starting row to move smoothly.

### Observations
- **Cameras** (ALOHA-style, 848 x 480, vertical field of view 58 deg): `cam_high` (static, above the front of the work
  area, looking down), `cam_low` (static, low at the front), `cam_left_wrist` and `cam_right_wrist` (on each hand,
  looking at the fingers; they move, so use the pose that comes with each frame). Intrinsics and mounts in
  `spec()["cameras"]`, the per-frame world -> camera pose in every response; depth on request.
- **Proprioception** (`spec()["proprio_layout"]`, groups in `spec()["proprio_groups"]`): per arm the 7 joint positions
  and velocities, the gripper opening (m), the tool-frame pose (`left_tcp` / `right_tcp` (between the fingertips): x y z
  + qw qx qy qz, world frame), the applied commands and the actuator forces.
- **World frame**: origin at the left arm's base link (`left_link0`) on its mounting, +z up, x along that arm's forward
  direction; metres, quaternions **WXYZ**. The proprio tool-frame poses, the camera extrinsics and mounts and
  `/kinematics` are all in it; no positions of the scene are given. `spec()["robot_spec"]["base"]` gives the right arm's
  base pose in it (the rig's fixed geometry).
- Not available (simulator privilege): part poses, positions of anything in the scene, the scene files, contact forces
  on parts, the success check itself.

## Others
- Mitres, keyholes, dowels and the back grooves hold by contact only; each of the four frame joints latches where it is
  once its slide is complete (side A, side B, the bottom).
- Parts move only through contact with the robot, gravity and the scene's own mechanism.
- Grasps are physical: only the friction of the finger contacts holds a part; nothing attaches it to a gripper.

## Limits
- Time: 10800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
