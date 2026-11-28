# RoboARC · rope_threading (standard)

## Task
Thread the rope, from its end that started farther from the rings, through the cyan grommet in the wall (G1), then the
green ring (A), then the purple grommet in the wall (G2), then the amber ring (T), then the red grommet in the wall
(G3), then the cyan ring (C), in that order, each the way given below.

## Goal
Success: counted from that end, the rope goes through G1, then A, then G2, then T, then G3, then C in that order,
through each hole exactly once and the right way: G1 toward C's side, A away from C's side, G2 toward T's side, T away
from G2's side, G3 toward A's side, C away from A's side; the rope is intact and still.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts. Make sure
everything is at rest when you send `/finish`.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras, the robot's own sensor readings and the safety readings (Robot Interface): no object poses,
  no scene layout, no success signal.

## Robot Interface
Two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base, at a table (RoboARC, MuJoCo). The robot runs
as a service you reach through its client or its MCP tools, as if it were real hardware: one live episode.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/3.0`:
```python
from rcb_client import Robot
r = Robot()                                   # connects to the existing service; retries until ready (default timeout 3600 s)
spec = r.spec()                               # actions, cameras (intrinsics, mounting), robot_spec, world, kinematics, budget

obs = r.get_obs()                             # current frames from 4 cameras: obs.last[cam] -> uint8 (480,848,3)
obs.meta["proprio"]                           # {"layout": [72 names], "now": [...]}: groups in spec["proprio_groups"]
obs.meta["cameras"]                           # per camera: intrinsic_cv, extrinsic_cv, cam2world_gl of the LAST frame
obs = r.get_obs(depth=True)                   # + obs.last_depth[cam]: float32 (480,848) z-depth in metres, 0 = no reading
obs = r.hold(2.0)                             # hold the last command for 2 s of robot time: obs.video[cam] = mp4 bytes
obs = r.get_obs(last_s=1.0)                   # the frames recorded over the last 1 s (reading moves no time)

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 14) rows dt seconds apart; streamed at 25 Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 16) tool-frame targets; inverse kinematics per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["cam_high"]                          # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["cam_high"]                         # uint8 (N,480,848,3) at video_fps if requested
res.last["cam_right_wrist"]; res.proprio              # last frame per camera; float32 (N, 72) proprio, one row per frame
res.frame_step, res.frame_time_s              # per frame: control steps since the episode start, simulated time (s)
res.extrinsic_cv["cam_right_wrist"]                    # (N,3,4) world frame -> camera at every frame
res = r.submit("joint_position", A, dt=0.1, depth="frames")   # + res.depth[cam]: (N,480,848) z-depth per frame (1 mm steps)
res.group("tcp_pose"); res.group("joint_effort", now=True)   # proprio columns by group name
r.fk(q)["poses"]["left_tcp"]                   # forward kinematics of the 12 arm joints (spec["kinematics"]); moves nothing
r.ik({"left_tcp": pose}, seed=q)             # inverse kinematics -> {"ok", "q", "error"}; moves nothing
```

- One control step takes about 0.36 s of wall clock here. A request returns when all of its steps have run, or earlier.
  If a call has run for 900 s (`spec["max_call_wall_s"]`), the service stops it at the next control step and returns
  what it executed. Then `res.stopped` is `"max_call_wall_s"`, `res.meta["executed_rows"]` (for a hold,
  `res.meta["duration_s"]`) says how far it got, and the robot holds its last target. Check `res.stopped` before you
  send the next rows. A `submit` of the maximum 10 s chunk, or a 10 s `hold(s)`, takes about 90 s here and fits (with a
  2x margin).
- The client waits longer than that (1800 s for `submit`, 1020 s for `get_obs`), so a client timeout or a connection
  error means the connection or the service failed, not that the call is still on its way. Do NOT send the request again
  blindly, because it could run twice. Use `r.operation_status()` to find out what became of the last one. Its `status`
  is one of these: `completed` or `error`, with `rows_before` and `committed_rows` (the episode's control steps before
  and after the call) and `stopped`; `interrupted`, if the service restarted during the call (it resumes the same
  episode in the state after the last completed call: `spec["on_service_error"]`, `r.wait_ready()`); or `admitted`, if
  the call has not finished. An HTTP 404 error from this query means the service never admitted the request, so nothing
  ran. The service answers one request at a time, so this query waits while a call is running: repeat it if it times
  out. If your client hangs up, the service stops the call at the next control step. A request that arrives after its
  deadline is refused (408), and one whose operation id was already admitted is refused (409); neither moves the robot.
  A control step that hangs for more than 60 s past the call's limit ends the episode as an infrastructure error, not as
  your failure.
- `meta["reason"]` says why the episode ended: `finished` (you called finish), `task_failed` (the task's failure rule),
  `step_limit` (the step cap), `timeout`, or an error.
- One call returns at most 2000 images.

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
- `joint_position` (14): `left/waist`, `left/shoulder`, `left/elbow`, `left/forearm_roll`, `left/wrist_angle`,
  `left/wrist_rotate`, `left_native_gripper`, `right/waist`, `right/shoulder`, `right/elbow`, `right/forearm_roll`,
  `right/wrist_angle`, `right/wrist_rotate`, `right_native_gripper`. arm `left`: 6 joint targets (rad), then
  `left_native_gripper` = native drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); arm
  `right`: 6 joint targets (rad), then `right_native_gripper` = native drive target (m, limits 0.002 .. 0.037;
  open/closed targets in robot_spec). Absolute targets tracked by PD controllers. Rows are `dt` apart (`1/25 ≤ dt ≤ 0.5`
  s, a multiple of the control period). A chunk may cover at most 10 s. Out-of-limit values are clipped and listed in
  `meta["clipped"]`; the limits are in the spec. The gripper command is not interpolated: it switches to its new value
  at the start of its row. Use `obs.meta["proprio"]["now"][:14]` as the starting row to move smoothly. An arm joint
  target moves at most 0.04 rad per control step (1 rad/s, the same speed as `ee_pose` rows): a row that asks for more
  takes the control steps it needs, and `meta["clipped"]` says so. The proprio group `gripper_opening`
  (`res.group("gripper_opening")`) is the measured gap between each gripper's finger pads in metres (0 = the pads
  touch); the gripper entries of `joint_pos` are in the unit of the gripper command above.
- `ee_pose` (16): per arm, in the order ['left', 'right'], `x y z qw qx qy qz gripper`. Poses are in the world frame
  (origin at the robot's root link on its mounting, +z up), which is also the frame of the proprio TCP pose and the
  camera extrinsics. Quaternions are wxyz. The service solves each row by inverse kinematics (with no collision
  checking) and drives the arm there in joint space. If the IK fails for an arm, that arm holds and the failure is
  reported in `meta["plan"]`. The pose is each gripper's **tool frame** (TCP). Its approach and finger-closing axes are
  in `spec["robot_spec"]["tcp"]`. This is the same convention as the proprio TCP poses, so an observed pose is a valid
  target. At most 50 rows per submit. If a row's IK solution lies more than 0.5 rad from the current joints on any
  joint, the row is refused, the same way as a failed IK. For a small pose change, such a jump means another IK branch,
  which would swing the arm. Split long moves into rows a few cm and degrees apart.
- Both action types: no gripper target goes lower than 15 mm below the tabletop. A target that would bring any part of a
  gripper lower is stopped at that height and listed in `meta["clipped"]`.

### Observations
- Cameras: `cam_high` (static); `cam_low` (static); `cam_left_wrist` (on the robot link `left/gripper_base`; it moves,
  so use the pose that comes with each frame); `cam_right_wrist` (on the robot link `right/gripper_base`; it moves, so
  use the pose that comes with each frame). Resolution 848×480. `spec["cameras"][cam]` gives the intrinsics and the
  mounting. The mounting is either a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) ·
  `link_T_cam_cv`). A point (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z +
  cx, v = fy·Y/Z + cy; depth is that Z. `spec["robot_spec"]` lists the joints with their position, velocity and effort
  limits, the grippers, the PD gains and the tool frames. `spec["world"]` gives the frame conventions: the world frame
  has its origin at the robot's root link on its mounting, with +z up.
- The safety readings (`meta["safety"]`, in every response) cover the time since the previous call and show each value
  next to its limit. They report forcing (the arms' pressing loads and forcing events); for rigid families, the deepest
  task contact, the longest time above its sustained limit and the review events; for soft families, the lowest rope /
  cord volume ratio; and the table-guard stops.

### Grasping
- Assisted grasping: a gripper whose command moves towards closed takes hold of a graspable part (rope) once all of this
  has held for 0.02 s: both fingers touch the same part inside its grasp region, the tool frame is within 6 cm of it,
  and the penetration is at most 6 mm. The part then follows the gripper rigidly. Any command that opens the gripper by
  more than 0.2 % of its travel releases the part. A hold is lost if the fingers open more than 15 %, the part drifts
  2.5 cm / 0.15 rad from its held pose, or the hold has to push or pull its part with more than 60 N averaged over 20
  ms. The gripper must then open before it can take hold again. That force is reached when, for example, two held parts
  that hook into each other are pulled apart, or a held part is pressed into another object. Two grippers never hold the
  same part. Objects that are not graspable parts are grasped physically (by friction).
- Grasp regions (one or more spheres per graspable part): rope: 544 spheres of radius 8 mm. Both finger contacts must
  lie inside one of the part's spheres; a part touched elsewhere is grasped physically.
- Only the grippers' fingers collide with the rope and the rings: every other robot part (palms, wrists, arm links,
  bases) passes through them without contact, so only the fingers can push, pinch or hold the rope.

### Safety
- The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive
  torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. If
  any part of an arm is more than 5 mm deep in a fixed object (a fixture, the table), the arm is stopped where it is.
  For that control step its joint targets are set to its measured joints, so it stops pushing. These stops are reported
  in clipped[].
- Forcing means an arm drive is near its torque cap while its gripper, or a part it holds, presses hard on something.
  Forcing is recorded as evidence (`meta["safety"]`) and shown to the reviewer when a success is reviewed. By itself, it
  does not end the episode or change the grade. If the simulator breaks down, the episode ends. This counts as your
  failure if an arm was forcing just before the breakdown, and as an infrastructure error otherwise.

## Others
- Objects here (the names the safety readings use): `A`, `A_pedestal`, `C`, `C_base`, `C_stand`, `G1`, `G2`, `G3`, `P1`,
  `P2`, `T`, `T_pedestal`, `bulkhead_corner00`, `bulkhead_corner01`, `bulkhead_corner02`, `bulkhead_corner03`,
  `bulkhead_corner10`, `bulkhead_corner11`, `bulkhead_corner12`, `bulkhead_corner13`, `bulkhead_corner20`,
  `bulkhead_corner21`, `bulkhead_corner22`, `bulkhead_corner23`, `bulkhead_lintel0`, `bulkhead_lintel1`,
  `bulkhead_lintel2`, `bulkhead_sill0`, `bulkhead_sill1`, `bulkhead_sill2`, `bulkhead_strip0`, `bulkhead_strip1`,
  `bulkhead_strip2`, `bulkhead_strip3`, `left_base_riser`, `right_base_riser`, `rope`.

## Limits
- Time: 10800 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 4 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Steps: at most 200,000 control steps, then the episode ends. Holds count as control steps too.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
