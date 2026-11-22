# AM-Bench · ambench-cabinet-pick-place-fahexa-i00 (standard-mcp-shell)

## Task
A simulated aerial manipulator: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude while
hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in AM-Bench
(Isaac Lab). A tall wooden cabinet stands ahead of the hovering aerial manipulator, and a small soda can stands inside
one of its shelf compartments, behind a closed sliding door. Get the can onto the top of the cabinet. The robot runs as
a service you reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the service's own client, as
if it were real hardware: one live episode.

### Scene
The ground is the world's z = 0 plane; there is no wall. Ahead of the robot stands an immovable cabinet with light-wood
panels and metal handles, about 1.2 m wide, 0.6 m deep and 1.68 m tall, its front facing the robot and its top a flat
board. From the bottom up: a solid base; a drawer with a horizontal bar handle; a compartment closed by two hinged doors
with vertical handles, which are locked; the can's compartment, about 27 cm tall, whose right half (as seen from the
robot) is closed by a fixed panel and whose left half is closed by a sliding door with a vertical bar handle; and a top
compartment closed by a front panel with a horizontal bar handle. The sliding door slides sideways to the robot's right,
in front of the fixed panel, over 0.6 m of travel; it has no spring (it stays where it is left) and its motion is
resisted by damping and friction. The bottom drawer and the top front panel are not jointed: they are loose parts held
in place only by gravity and contact. The can (4 cm in diameter, 6.4 cm tall, 5 g, with a soda label) stands upright on
the floor of the sliding-door compartment, a little in from the front and hidden behind the closed sliding door; its
exact spot varies by a few centimetres between instances, and nothing else varies. Nothing moves by itself. The robot
starts hovering level and motionless, facing the cabinet, with its arm at its zero joint configuration (end effector a
little ahead of and above the airframe) and the gripper closed.

## Goal
Success: the can stands at rest on the top of the cabinet; where on the top, which way up and whether the gripper still
holds it do not matter. The episode ends by itself as soon as the task is done (reason `success`), or as a failure when
its 60 s of simulated time run out (reason `episode_timeout`).

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Simulated time moves only while the robot runs your commands or you watch it hold still: between your calls the world
  is frozen.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame: at the airframe's centre (measured at the start of each call), +X the airframe's heading, +Y to its
left, +Z straight up (level: the heading only, the airframe's tilt is ignored); it moves with the airframe; metres,
radians, quaternions `wxyz`, gripper 0 open .. 1 closed. Parts: arm (arm: end-effector pose, gripper). Cameras:
`ee_camera`, `base_camera`.

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

This robot: The robot flies: there is no separate base command, the airframe moves wherever the end-effector target
needs it (base_odometry in each result is the airframe's world position and heading). At the start the airframe hovers
level facing +X with the arm at its zero joints and the gripper closed. Move in small steps and watch the cameras: the
airframe, not only the arm, approaches nearby surfaces. The state's gripper value is the command in force;
gripper_opening_m is the measured finger opening (0.002 m = closed on nothing). The episode ends by itself at the first
control step where the task is done, or at the task's episode length of simulated time (spec_file max_control_steps at
120 Hz).

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.2`):
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and builds the scene (see below)
spec = r.spec()                               # the action, cameras, proprio layout, budget, robot spec, kinematics

obs = r.get_obs()                             # current frames: obs.last[cam] -> uint8 (384, 384, 3), cam in ee_camera, base_camera
obs.meta["proprio"]                           # {"layout": [...45 names], "now": [...]}: joints, gripper, tool and airframe poses, ...
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl at the LAST frame
obs = r.get_obs(seconds=1.0, video="mp4")     # hold the current target and watch for 1 s (max 30; simulated time advances)

res = r.submit("ee_pose", A, dt=1/120, interpolate="hold")   # A: (T, 8) rows dt apart (see Action)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["ee_camera"]                        # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["base_camera"]                     # uint8 (N,H,W,3) at video_fps if requested
res.last["ee_camera"]; res.proprio            # last frame per camera; float32 (N, 45) proprio at each video frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy
```

The service's first start in a trial compiles Isaac's shaders: `Robot()` can wait ~2-12 min (it prints its progress to
stderr once a minute). It gives up after 3600 s (`Robot(timeout=...)`) with
`RuntimeError("sim service unavailable ...")`: then call it again (nothing has happened in the episode yet; your wall
clock runs from the start of the trial).

If the service crashes, a call fails with a connection error: the simulator restarts and resumes the SAME episode (never
a reset) in the state after the last call it completed, which you may not have received. `r.wait_ready()` waits until it
answers again (resuming replays the episode so far, which can take minutes; the wall clock keeps running), then check
`r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).

Simulated time moves only in `submit` and in `get_obs(seconds=s)` (the robot holds its current target while you watch,
at most 30 s). One call returns at most 3000 images.

Optional inputs (ask only for what you need):
- Depth: `r.get_obs(depth=True)` -> `obs.last_depth[cam]` float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned
  with `obs.last[cam]`; `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N,H,W), one map per frame (1 mm
  steps).
- Per frame: `res.frame_step` (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N,3,4 world -> camera, OpenCV
  axes). `spec["cameras"][cam]`: `intrinsic_cv` and `mount` (the parent link and a fixed `link_T_cam_cv`).
- `spec["robot_spec"]` (the arm's joints and limits, the gripper and its command, the controller, the tool frame),
  `spec["world"]` (frame, units, wxyz), `spec["proprio_groups"]` + `res.group("base_pose")` (joint_pos, joint_vel,
  tcp_pose, gripper_opening, gripper_cmd, joint_effort, base_pose, base_vel, ee_cmd).
- `r.fk(q4, base_pose=base7)` -> poses of `spec["kinematics"]["links"]` (in the airframe frame without `base_pose`,
  world with it); `r.ik({"tcp": pose7}, seed=q4, base_pose=base7)` -> `{"ok", "q", "error"}`: a stateless model of the
  arm on its airframe (no physics, no simulated time); `q4` = the arm's four joints. AM-Bench's own controller moves the
  airframe too (below): this model is the arm alone, for reasoning about reach and camera poses.

### Actions
- World frame: metres, z up, the ground is the plane z = 0; positions relative to the environment's origin (the same
  frame for the action, the proprio poses, the camera extrinsics and `r.fk` with `base_pose`); quaternions are wxyz.
- At the start the airframe hovers level, facing +x, with the arm at its zero joint configuration and the gripper
  closed.
- `ee_pose` (8 per row): `x y z qw qx qy qz gripper` — AM-Bench's own action. The target pose of the tool frame `tcp`
  (the end-effector link, the frame of proprio `tcp_pose`; position in metres, world frame; orientation wxyz) and the
  gripper command (-1 = closed .. +1 = open). Every control step, AM-Bench's whole-body controller turns the target into
  an airframe pose (its floating-base inverse kinematics), the airframe pose into the six rotor thrusts (a PID) and the
  arm joints into targets for their drives: you command where the end effector should be, the airframe follows.
- Rows are `dt` apart (`1/120 ≤ dt ≤ 0.5` s, a multiple of the 120 Hz control period: 1/120, 2/120, ...; any other `dt`
  is rejected, never rounded); `interpolate="hold"` (each row exactly as given, for its dt) or `"linear"` (default: from
  the previous target, positions linear, orientation slerp, gripper linear); a chunk may cover at most 10 s; a gripper
  value outside [-1, 1] is clipped and listed in `meta["clipped"]`. Start from the target in force
  (`res.group("ee_cmd")`, or the proprio `tcp_pose`) to move smoothly: at the start the target is the end effector's own
  pose and the gripper is closed.
- A malformed request (a wrong type, a value out of range, a position more than 30 m from the origin, a zero quaternion)
  is answered 400 with the reason and executes nothing.
- Control and physics run at 120 Hz (simulated time; one physics step of 1/120 s per control step).

### Observations
- Cameras (384×384 each, both moving with the robot): `ee_camera` (on the end effector, looking along the gripper) and
  `base_camera` (on the airframe, looking forward); their intrinsics and mounts are in the spec's `cameras`, their pose
  at every frame comes with each reply.
- Depth (`depth=True`): z-depth in metres, 0 = no reading, pixel-aligned with the colour image, in 1 mm steps.
- Proprioception: 45 values a row (their `layout` comes with them): the arm's joint positions, velocities and efforts,
  the gripper's opening and command, the tool frame's pose (`tcp_pose`), the airframe's pose and velocity (`base_pose`,
  `base_vel`) and the end-effector target in force (`ee_cmd`); the groups are in the spec's `proprio_groups`.

## Others
- Neither the cabinet's pose, the sliding door's position nor the can's pose is given: the cabinet, the door and its
  handle have to be found with the forward-looking onboard cameras, the can is hidden behind the closed door at the
  start, and whether the can ended at the right height and at rest can only be judged from the images together with
  proprioception.

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
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
