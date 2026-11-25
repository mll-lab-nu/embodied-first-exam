# RoboWits · retrieve_cube (standard)

## Task
Take the small cube out of the container and put it on the green target area.

## Goal
Success: the cube is out of the container and lies on the table on the green target area, clear of the table's edges;
the robot has let go of the cube, no longer touches it, and it is at rest. When all of this holds after a call, the
service holds your last command within that call for about three seconds (a second, then two seconds in which all of
this must keep holding, with nothing moving); if it all holds through, the episode ends as a success, and if not, it
goes on. When your session ends, the same check runs once more after your last command.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout; the episode ends when
  the task is done.

## Robot Interface
A bimanual Marvin robot (two 7-DoF arms with Pika parallel grippers), in RoboWits' simulation (Genesis). The robot runs
as a service you reach only through its client, as if it were real hardware: one live episode.

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
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; a technical cap ends the episode after 200,000 control steps (1/30 s each, watches included),
  as a failure: no settle check runs after it.
