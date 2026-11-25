# RoboARC · blanket_flatten (standard)

## Task
Unfold the blanket and spread it flat on the table, with no part folded over another and without stretching it. Then let
go of it and move both arms clear of it.

## Goal
Success: the blanket lies fully unfolded and flat on the table, with no part over another, nothing stretched and no
corner raised; both arms have let go of it and moved clear, and the cloth is still. Letting the blanket fall off the
table ends the episode as a failure. The episode ends, as a success, as soon as all of this has held for 0.5 s.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras, the robot's own sensor readings and the safety readings (Robot Interface): no object poses,
  no scene layout; the episode ends when the task is done.

## Robot Interface
Two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base, at a table (RoboARC, MuJoCo). The robot runs
as a service you reach only through its client, as if it were real hardware: one live episode.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.4`:
```python
from rcb_client import Robot
r = Robot()                                   # connects to the existing service; retries until ready (default timeout 3600 s)
spec = r.spec()                               # actions, cameras (intrinsics, mounting), robot_spec, world, kinematics, budget

obs = r.get_obs()                             # current frames from 4 cameras: obs.last[cam] -> uint8 (480,848,3)
obs.meta["proprio"]                           # {"layout": [72 names], "now": [...]}: groups in spec["proprio_groups"]
obs.meta["cameras"]                           # per camera: intrinsic_cv, extrinsic_cv, cam2world_gl of the LAST frame
obs = r.get_obs(depth=True)                   # + obs.last_depth[cam]: float32 (480,848) z-depth in metres, 0 = no reading
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 14) rows dt seconds apart; streamed at 40 Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 16) tool-frame targets; inverse kinematics per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["cam_high"]                          # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["cam_high"]                         # uint8 (N,480,848,3) at video_fps if requested
res.last["cam_right_wrist"]; res.proprio              # last frame per camera; float32 (N, 72) proprio, one row per frame
res.frame_step, res.frame_time_s              # per frame: control steps since the episode start, simulated time (s)
res.extrinsic_cv["cam_right_wrist"]                    # (N,3,4) world -> camera at every frame
res = r.submit("joint_position", A, dt=0.1, depth="frames")   # + res.depth[cam]: (N,480,848) z-depth per frame (1 mm steps)
res.group("tcp_pose"); res.group("joint_effort", now=True)   # proprio columns by group name
r.fk(q)["poses"]["left_tcp"]                   # forward kinematics of the 12 arm joints (spec["kinematics"]); moves nothing
r.ik({"left_tcp": pose}, seed=q)             # inverse kinematics -> {"ok", "q", "error"}; moves nothing
```

- One control step takes about 0.57 s of wall clock here. A request returns when all of its steps have run, or earlier:
  a call that has run for 900 s (`spec["max_call_wall_s"]`) is stopped by the service at the next control step and
  returns what it executed (`res.stopped` is `"max_call_wall_s"`; `res.meta["executed_rows"]`, or
  `res.meta["control_steps_watch"]` for a watch, says how far it got; the robot holds its last target). Check
  `res.stopped` before you send the next rows. A `submit` of the maximum 10 s chunk takes about 228 s here; a
  `get_obs(seconds=...)` watch fits up to about 789 control steps (19.73 s, a 2x margin), and a longer one is cut short
  the same way.
- The client waits longer than that (1800 s for `submit`, 1020 s for `get_obs`), so a client timeout or a connection
  error means the connection or the service failed, not that the call is still on its way. Do NOT send the request again
  blindly (it could run twice): `r.operation_status()` tells what became of the last one. Its `status` is `completed` or
  `error` (with `rows_before` and `committed_rows`, the episode's control steps before and after it, and `stopped`),
  `interrupted` (the service restarted during it and resumes the same episode in the state after the last completed
  call: `spec["on_service_error"]`, `r.wait_ready()`), or `admitted` (not finished); an HTTP 404 error there means the
  service never admitted the request, so nothing ran. The service answers one request at a time, so this query waits
  while a call is running: repeat it if it times out. If your client hangs up, the service stops the call at the next
  control step. A request that arrives after its deadline is refused (408), and one whose operation id was already
  admitted is refused (409); neither moves the robot. A control step that hangs for more than 60 s past the call's limit
  ends the episode as an infrastructure error, not as your failure.
- `meta["reason"]` says why the episode ended: `success`, `task_failed` (the task's failure rule), `step_guard` (the
  step cap), `timeout`, or an error.
- One call returns at most 2000 images.

### Actions
- `joint_position` (14): `left/waist`, `left/shoulder`, `left/elbow`, `left/forearm_roll`, `left/wrist_angle`,
  `left/wrist_rotate`, `left_native_gripper`, `right/waist`, `right/shoulder`, `right/elbow`, `right/forearm_roll`,
  `right/wrist_angle`, `right/wrist_rotate`, `right_native_gripper`. arm `left`: 6 joint targets (rad), then
  `left_native_gripper` = native drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); arm
  `right`: 6 joint targets (rad), then `right_native_gripper` = native drive target (m, limits 0.002 .. 0.037;
  open/closed targets in robot_spec). Absolute targets tracked by PD controllers. Rows are `dt` apart (`1/40 ≤ dt ≤ 0.5`
  s, a multiple of the control period); a chunk may cover at most 10 s; out-of-limit values are clipped and listed in
  `meta["clipped"]` (limits in the spec). The gripper switches at the row. Use `obs.meta["proprio"]["now"][:14]` as the
  starting row to move smoothly. An arm joint target moves at most 0.04 rad per control step (1.6 rad/s, the same speed
  as `ee_pose` rows): a row that asks for more takes the control steps it needs, and `meta["clipped"]` says so. The
  proprio group `gripper_opening` (`res.group("gripper_opening")`) is the measured gap between each gripper's finger
  pads in metres (0 = the pads touch); the gripper entries of `joint_pos` are in the unit of the gripper command above.
- `ee_pose` (16): per arm (in the order ['left', 'right']) `x y z qw qx qy qz gripper`; world frame (origin at the
  robot's root link on its mounting, +z up; the frame of the proprio TCP pose and the camera extrinsics); quaternions
  wxyz. Each row is solved by inverse kinematics (no collision checking) and driven to in joint space; an arm whose IK
  fails holds and is reported in `meta["plan"]`. The pose is each gripper's **tool frame** (TCP; its approach and
  finger-closing axes are in `spec["robot_spec"]["tcp"]`), the same convention as the proprio TCP poses, so an observed
  pose is a valid target. At most 50 rows per submit. A row whose IK solution lies more than 0.5 rad from the current
  joints on any joint is refused the same way as a failed IK (for a small pose change that is another IK branch, which
  would swing the arm): split long moves into rows a few cm and degrees apart.
- Both action types: no gripper target goes lower than 15 mm below the tabletop; a target that would bring any part of a
  gripper lower is stopped there and listed in `meta["clipped"]`.

### Observations
- Cameras: `cam_high` (static); `cam_low` (static); `cam_left_wrist` (on the robot link `left/gripper_base`; it moves,
  so use the pose that comes with each frame); `cam_right_wrist` (on the robot link `right/gripper_base`; it moves, so
  use the pose that comes with each frame). Resolution 848×480. `spec["cameras"][cam]` gives the intrinsics and the
  mounting: a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) · `link_T_cam_cv`). A point
  (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z + cx, v = fy·Y/Z + cy; depth
  is that Z. `spec["robot_spec"]` lists the joints with their position, velocity and effort limits, the grippers, the PD
  gains and the tool frames; `spec["world"]` the frame conventions (the world frame: origin at the robot's root link on
  its mounting, +z up; no positions of the scene are given).
- The safety readings (`meta["safety"]`, in every response) report, since the previous call, forcing (the arms' pressing
  loads and forcing events), the deepest task contact, the longest time above its sustained limit and the review events
  (rigid families), the lowest rope / cord volume ratio (soft families) and the table-guard stops, each next to its
  limit.

### Grasping
- Assisted grasping: closing intent and bilateral finger proximity to a material patch of blanket must persist for 0.03
  s, with penetration at most 2 mm and the TCP within 6 cm. The admitted patch follows through a local kinematic PBD
  attachment; the rest remains deformable. Opening by more than 0.2 % of gripper travel releases it. A hold is lost on
  excessive opening, material strain, invalid volume or follow error above 10 mm; a lost hand must open before
  reacquiring. Two hands may hold disjoint material patches of the same object; overlapping patches are rejected. Patch
  radii, strain limits and the exposed-patch requirement are declared in grasp_assist.targets.
- Soft grasp patches: blanket: spatial radius 18 mm, material radius 18 mm, finger proximity 6 mm, maximum material
  strain ratio 1.5, exposed patch required. Both fingers must be near the same material patch; penetration and native
  constraint health checks still apply. Two hands may hold disjoint patches of one object. Material bounds, when
  present, restrict the admissible region.

### Safety
- The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive
  torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An
  arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint
  targets become its measured joints for that control step, so it stops pushing (the response does not report these
  stops).
- Forcing (an arm drive near its torque cap while its gripper, or a part it holds, presses hard on something) is
  recorded as evidence (`meta["safety"]`) and shown to the reviewer when a success is reviewed; it does not end the
  episode or change the grade by itself. A simulator breakdown ends the episode: as an infrastructure error, or as your
  failure if an arm was forcing just before it.

## Others
- Objects here (the names the safety readings use): `blanket`.

## Limits
- Time: 10800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 3 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: no step budget; a technical cap ends the episode after 200,000 control steps, watches included, graded as it
  stands.
