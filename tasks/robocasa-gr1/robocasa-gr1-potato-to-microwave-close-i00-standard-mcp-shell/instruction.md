# RoboCasa-GR1 · PnPPotatoToMicrowaveClose (standard-mcp-shell)

## Task
A Fourier GR1 humanoid (arms, waist and two dexterous six-command Fourier hands, on a fixed base), at a simulated
kitchen counter (RoboCasa GR1 tabletop, robosuite / MuJoCo). Pick up the potato, place it into the microwave and close
the microwave. The robot runs as a service you reach through the `efe-robot` MCP tools, their Python client `efe_robot`
or the service's own client, as if it were real hardware: one live episode.

## Goal
Success: the potato is inside the microwave and the microwave door is fully closed. What counts is how things stand at
the end of the episode: a success reached earlier and lost by the end does not count, so finish in the state you want
graded and stop sending commands.

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
robot base frame (body robot0_base, fixed in the kitchen): +X the way the robot faces, +Y its left, +Z up; metres,
radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: right_hand (hand: 6 joints, no end-effector pose);
left_hand (hand: 6 joints, no end-effector pose). Cameras: `robot0_agentview_center`, `robot0_agentview_left`,
`robot0_agentview_right`, `egoview`, `robot0_eye_in_right_hand`, `robot0_eye_in_left_hand`.

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

This robot: The arms take absolute grip-site pose targets in the robot base frame, sent with execute_trajectory space
native, action_type ee_pose (24 numbers, one row per 0.05 s control step, each row a target the whole-body inverse
kinematics moves toward): right x, y, z (m), rx, ry, rz (axis-angle, rad), the same for the left, then the six
right-hand and six left-hand finger targets. cmd_* in proprio_now is the command in force (start from it and change what
should move; interpolate long moves over several rows). The grip site is the origin of the hand's mounting frame at the
wrist end of the hand, not a point between the fingertips; the four small pink spheres beside each hand are markers of
the robot model. move_robot and execute_trajectory space joint set the fingers (the hands' joint_positions); the
reported finger values are the commands in force. eef_left_*/eef_right_* in proprio_now are the grip sites' positions in
the world frame. The cameras ride on the robot; each frame comes with its current calibration.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service starts: about a minute)
spec = r.spec()                               # control_dt, action layout + limits + kinds, cameras, proprio layout, budget
cams = list(spec["cameras"])                  # robot0_agentview_center, robot0_agentview_left, robot0_agentview_right, egoview, robot0_eye_in_right_hand, robot0_eye_in_left_hand
obs = r.get_obs(cameras=cams, include_depth=True)   # obs.last[cam] -> uint8 (240, 320, 3); obs.depth[cam] -> metres
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: joints, end effector, last command
obs.meta["cameras"]                           # per camera: intrinsic_cv, cam2world_gl (OpenGL: looks along -z), current
obs = r.get_obs(cameras=cams[:1], seconds=2.0, video="mp4")    # hold still and watch for 2 s (max 30)
res = r.submit("ee_pose", A, cameras=cams[:1], video="mp4")   # A: (T, 24) rows, one per control step
res.meta["done"], res.meta["reason"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
```

`get_obs(seconds=s)` keeps applying the last command (before the first one: both grip sites' current poses and the
current hand commands) while physics runs for `s` seconds; those control steps are part of the episode. Every channel is
an absolute target, so the grip sites stay within about a millimetre, but the IK's posture term can still move the waist
and elbows by a few hundredths of a radian while you watch. One call returns at most 3000 images.

### Actions
- Action `ee_pose`: the robot's native controller command, applied once per control step (`control_dt` = 0.05 s;
  float64). 24 channels, in order: the right then the left hand's grip-site pose target `x, y, z, rx, ry, rz` --
  absolute, in the robot's base frame (metres, axis-angle radians), reached by the whole-body inverse-kinematics
  controller (mink), limits [-10, 10]; then six commands per hand (right, then left) in the finger order
  `little, ring, middle, index, thumb_flexion, thumb_rotation` -- unscaled Fourier hand commands in [-3, 3], not a
  binary grip. The GR1 has no mobile base. Values are clipped to the limits. Rows are `dt` apart (default and minimum:
  `control_dt`; a chunk covers at most 10 s).
- World frame: metres, z up. In the proprio, `eef_left_*` / `eef_right_*` are the grip sites' positions in the world
  frame; the action's pose targets and the `cmd_*` entries (the last command) are in the robot's base frame. The robot's
  base frame (body `robot0_base`, fixed in the world) has its origin at world (2.65000, -2.17500, 0.97000) m and is
  turned +90.0 deg about z (quaternion w x y z (0.70711, 0, 0, 0.70711)): `p_world = R @ p_base + t` with R = [[0, -1,
  0], [1, 0, 0], [0, 0, 1]].

### Observations
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.

### Hands
Each hand command is the position target, in radians, of that finger's joints (`thumb_flexion` drives two thumb joints,
`thumb_rotation` one): 0 is the straight, open finger, larger values bend it toward the palm (the hand closes), and
every finger joint stops at the end of its range (1.22 to 1.74 rad), so values below 0 or above about 1.7 change nothing
more. The grip site that the pose targets place is the origin of the hand's mounting frame (`gripper0_right_grip_site`,
`gripper0_left_grip_site`), at the wrist end of the hand, not a point between the fingertips. The four small pink
spheres beside each hand are part of the robot model (visual markers `robot0_<side>_pinch_spheres_0..3`, about 13.5 cm
from its grip site, with no collision): they are not objects.

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
- Resources: 3 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
