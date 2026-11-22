# RoboWits · stand_pages (standard-mcp-shell)

## Task
A bimanual Marvin robot (two 7-DoF arms with Pika parallel grippers), in RoboWits' simulation (Genesis). Stand the two
pages up on the table so that they brace each other. They start joined like an open book: the stabilizing bar already
runs through the eyelets of both pages as a hinge pin, so nothing has to be inserted. The robot runs as a service you
reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the service's own client, as if it were real
hardware: one live episode.

## Goal
Success: both pages stand upright on the table, bracing each other, clear of the table's edges; the robot has let go and
moved its grippers away from the pages and touches neither page nor the bar (holding the bar would hold the pages up),
and the pages are at rest. When all of this holds after a call, the service holds your last command within that call for
about three seconds (a second, then two seconds in which all of this must keep holding, with nothing moving); if it all
holds through, the episode ends as a success, and if not, it goes on. When your session ends, the same check runs once
more after your last command.

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
robot base frame: the robot's base point (1.08 m above the world origin), +X away from the robot towards the table, +Y
to the robot's left, +Z up; metres, radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: right (arm: 7
joints, end-effector pose, gripper); left (arm: 7 joints, end-effector pose, gripper). Cameras: `ego`, `wrist_right`,
`wrist_left`.

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

This robot: The gripper value in the state is the commanded opening width (0.1 m = open, 0 = closed); gripper_opening_m
is the measured opening (a gripper closed on an object stops above 0). The wrist joints are limited to about +-60 deg,
so a vertical approach works only for finger-closing directions within about 60 deg of the +Y axis. Joint efforts
(Joint1_R_effort ...) in proprio_now rise when an arm pushes on something. The episode ends by itself once the goal
holds with the graded objects released and at rest through a short settle window.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while the service builds the scene, ~1 min)
spec = r.spec()                               # actions, cameras (intrinsics, mounting), robot_spec, world, kinematics, budget

obs = r.get_obs()                             # current frames from 3 cameras: obs.last[cam] -> uint8 (480,848,3)
obs.meta["proprio"]                           # {"layout": [80 names], "now": [...]}: groups in spec["proprio_groups"]
obs.meta["cameras"]                           # per camera: intrinsic_cv, extrinsic_cv, cam2world_gl of the LAST frame
obs = r.get_obs(depth=True)                   # + obs.last_depth[cam]: float32 (480,848) z-depth in metres, 0 = no reading
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 16) rows dt seconds apart; streamed at 30 Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 16) gripper-tip targets; inverse kinematics per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["ego"]                              # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["ego"]                             # uint8 (N,480,848,3) at video_fps if requested
res.last["wrist_left"]; res.proprio           # last frame per camera; float32 (N, 80) proprio, one row per frame
res.frame_step, res.frame_time_s              # per frame: control steps since the episode start, simulated time (s)
res.extrinsic_cv["wrist_left"]                # (N,3,4) world -> camera at every frame (the wrist cameras move)
res = r.submit("joint_position", A, dt=0.1, depth="frames")   # + res.depth[cam]: (N,480,848) z-depth per frame (1 mm steps)
res.group("tcp_pose"); res.group("joint_effort", now=True)   # proprio columns by group name
r.fk(q14)["poses"]["Gripper_Tip_R"]           # forward kinematics of the 14 arm joints (spec["kinematics"]); moves nothing
r.ik({"Gripper_Tip_R": pose}, seed=q14)       # inverse kinematics -> {"ok", "q", "error"}; moves nothing
r.status(); r.wait_ready()                    # calls, control steps, done, reason; after a connection error: wait, then status
```

A busy service has not crashed. The service answers one request at a time: while a call runs, every other request waits
for it (`r.status()` from another process included), and a client-side timeout during that time means "busy", not
"crashed": nothing restarts, the call runs to its end and the episode goes on from there. If the service crashes (the
connection is refused or reset instead of an answer), it restarts and resumes the SAME episode, never a reset, in the
state after the last call it completed. `r.wait_ready()` waits until it answers again (resuming replays the episode so
far: about a second per 700 control steps); then check `r.status()` (`calls`, `control_steps`) before you continue. A
call that runs longer than `spec["max_call_wall_s"]` stops at the next control step and returns what it executed
(`res.stopped`, `meta["executed_rows"]`). When the settle check after a call fails, `meta["settle"]` says why. One call
returns at most 1500 images.

### Actions
- `joint_position` (16): `Joint1_R..Joint7_R, right_gripper, Joint1_L..Joint7_L, left_gripper`; radians, gripper =
  opening width in metres, 0 = closed .. 0.1 = open. Absolute targets tracked by PD controllers. Rows are `dt` apart
  (`1/30 ≤ dt ≤ 0.5` s, a whole number of 1/30 s control periods: `2/30`, not `0.067`; any other `dt` is refused, never
  rounded); a chunk may cover at most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]` (limits in
  the spec). Use `obs.meta["proprio"]["now"][:16]` as the starting row to move smoothly.
- `ee_pose` (16): right `x y z qw qx qy qz gripper`, left same; world frame (robot base at (0, 0, 1.08), x away from the
  robot, y to its left, +z up); quaternions wxyz. Each row is solved by inverse kinematics (no collision checking) and
  driven to in joint space; an arm whose IK fails holds and is reported in `meta["plan"]`. The pose is the **gripper
  tip** frame: +z is the approach direction, +x the direction the fingers close along (same convention as the `proprio`
  end-effector poses, so an observed pose is a valid target). At most 50 rows per submit; `dt` is ignored; a gripper
  width outside 0 .. 0.1 is clipped and listed in `meta["clipped"]`.
- A request with a field of the wrong type or out of range (`dt`, `seconds` outside 0 .. 30, `video_fps` not a whole
  number in 1 .. 30, `video`, `interpolate`, `cameras` not a list of names, `note` not a string, actions that are not
  finite (T, 16) numbers) is answered 400 before anything is executed: the client raises `ValueError`, nothing has moved
  and the episode goes on.

### Observations
- Cameras: `ego` (static, above and behind the robot, looking at the table), `wrist_right` / `wrist_left` (on the
  wrists; they move, so use the pose that comes with each frame). Resolution 848×480. `spec["cameras"][cam]` gives the
  intrinsics and the mounting: a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) ·
  `link_T_cam_cv`). A point (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z +
  cx, v = fy·Y/Z + cy; depth is that Z.
- `spec["robot_spec"]` lists the joints with their position, velocity and effort limits, the grippers, the PD gains and
  the tool frames; `spec["world"]` the frame conventions.

## Others
- Objects here: two thin grey pages with a row of eyelets along one edge and a grey bar (20 cm long, 1.5 cm square
  section) that already runs through the eyelets of both pages, all lying flat on the table in front of the robot.
- The wrist joints are limited to ±60°, so a vertical approach only works for finger-closing directions within about
  ±60° of the world y axis.

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
- Resources: 4 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; a technical cap ends the episode after 200,000 control steps (1/30 s each, watches included),
  as a failure: no settle check runs after it.
