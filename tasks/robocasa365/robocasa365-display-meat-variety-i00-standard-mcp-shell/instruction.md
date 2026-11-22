# RoboCasa365 · DisplayMeatVariety (standard-mcp-shell)

## Task
A Franka Panda arm on an Omron mobile base with a torso lift, in a simulated kitchen (RoboCasa365, robosuite / MuJoCo).
Retrieve the chicken drumstick, shrimp, and steak from the fridge and place them on the serving tray on the dining
counter. The robot runs as a service you reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the
service's own client, as if it were real hardware: one live episode.

## Goal
Success: the drumstick, the shrimp and the steak all lie on the serving tray, the tray on the dining counter, and the
hand has let go and moved away from all three. What counts is how things stand at the end of the episode: a success
reached earlier and lost by the end does not count, so finish in the state you want graded and stop sending commands.

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
robot base frame is the mobile base's starting placement: on the floor at the base's origin, +X the way the arm faces,
+Y the robot's left, +Z up; it stays where the base started (driving the base does not move this frame); metres,
radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: 7 joints, end-effector pose (inverse
kinematics in these tools), gripper). Cameras: `robot0_agentview_center`, `robot0_agentview_left`,
`robot0_agentview_right`, `robot0_eye_in_hand`.

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

This robot: The arm takes absolute joint position targets (describe_robot gives the joint limits); a move_robot pose
goal or an execute_trajectory ee row is turned into them here, by inverse kinematics on the robot's model from the
measured joints, base and lift, without path planning or collision checking. The base and the torso lift are driven with
execute_trajectory space native, action_type joint_position (13 numbers, one row per 0.05 s control step): arm_joint1..7
(keep the current targets, cmd_* in proprio_now), grip (+1 closes, -1 opens), base_x, base_y, base_yaw (the mobile
base's velocities in its own frame, normalised to [-1, 1]), torso (the lift's velocity, normalised), hybrid_mode (-1,
the default). proprio_now has eef_right_x/y/z (the grip site's position in the world frame), the joints
(robot0_joint1..7, mobilebase0_joint_mobile_forward/side/yaw, mobilebase0_joint_torso_height) and cmd_* (the last
command). The poses the tools report are in the base's starting placement. The cameras ride on the robot; each frame
comes with its current calibration.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.1`:
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
res.meta["done"], res.meta["reason"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio
```

`get_obs(seconds=s)` holds the robot still (delta channels zero, targets, grip and mode kept) while physics runs for `s`
seconds; those control steps are part of the episode. One call returns at most 3000 images.

### Actions
- Action `joint_position`: the robot's native controller command, applied once per control step (`control_dt` = 0.05 s;
  float64). 13 channels, in order: `arm_joint1 .. arm_joint7` -- absolute joint position targets (rad, within the joint
  limits in `spec["action_types"]["joint_position"]` (`lower` / `upper`, from `r.spec()`)); `grip` (+1 closes, -1
  opens); `base_x, base_y, base_yaw` -- the mobile base's velocities in its own frame (normalised, [-1, 1]); `torso` --
  the torso lift's velocity; `hybrid_mode` (> 0: base mode; <= 0: arm mode, the default -1). Values are clipped to the
  limits. Rows are `dt` apart (default and minimum: `control_dt`; a chunk covers at most 10 s).
- World frame: metres, z up.

### Observations
- The cameras are mounted on the robot and move with it: use the calibration that comes with each response.

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
- Resources: 4 CPUs, 6 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
