# TopoGym · rope_threading — STANDARD MODE (robot as a service, eai-standard/2.3)

You control a robot (**two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base**) **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode. **Task:** Thread the rope through the cyan ring (R1) then green ring (R2) then purple ring (R3), in that order along the rope from material start to material end.

## Success requirements

- Required directions along that material order: cyan ring (R1): cross toward the side containing the green ring (R2); green ring (R2): cross toward the side containing the purple ring (R3); purple ring (R3): cross away from the side containing the green ring (R2). Do not reverse the crossing directions.
- Pass fully through each required hole exactly once, with no extra crossings or ambiguous tangencies. Keep the full rope thickness clear of the rim, with an additional 0.1 mm radial margin; the passage must clear both sides of each ring's thickness, not just its middle plane.
- Keep every rope point at or below 1 mm/s. Holding is allowed; release is not required.
- Keep the rope intact; collapsed or inverted rope volume is not accepted.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- Invalid rope volume ends the episode in failure.

## Grader details (in addition to the requirements above)

- The rope is very soft (Young's modulus 50 kPa): a full close of a gripper on it, or landing on it, crushes it. A crushed rope volume (an inverted volume element) ends the episode only once it has lasted 0.25 s (while it lasts, the goal cannot be confirmed); an invalid soft-body solver state ends it at once. Close to about half the rope's diameter and slow down in the last centimetre.
- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque.
- Sizes: each ring's inner radius is 69 mm and its tube 12 mm thick (radius 6 mm); the rope's radius is 4 mm. So the rope's centreline must pass less than 64.9 mm from a ring's centre, and the passage is checked on the ring's middle plane and on the planes 6 mm to either side of it.
- The material start is the rope end that is farther from the rings at the start.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success (all final conditions satisfied for
  0.5 s), when your time is up, on a simulator error, or when the task's own failure predicate fires (then `meta["reason"]` is `task_failed`). Knocked-over objects stay
  knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth when you ask for it) plus the robot's own state:
  joint positions, velocities and drive efforts, gripper openings, end-effector poses. Nothing tells you where the
  objects are (no object poses or positions). The success implementation and internal measurements are not exposed;
  the task requirements above still apply in full.
- **Your wall-clock budget is 360 min (21600 s)** (`meta["time_left_s"]` counts it down); steps are unlimited. Actions and
  simulated time are reported as cost. One control step takes about 2.2 s of wall clock on an unloaded GPU, and up to about 4.4 s when other simulations share the GPU; the call metadata reports the time.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script
  at `/app/output/gen.py` for the record.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Startup and long-running commands

- Scene initialization and kernel compilation can take minutes. Actual time depends on the task, hardware, and load.
  Quiet logs during initialization do not by themselves mean failure. Use `python -u` for unbuffered script output.
- A command tool's wait/yield interval (for example, `yield_time_ms=30000`) is not the command's lifetime.
  When a command is still running, retain its process/session identifier and continue waiting for that same command.
  With Codex's `exec_command`, expose the complete result, including `session_id` and `exit_code`, rather than only
  `output` (for example, `text(r)` instead of only `text(r.output)`). Continue it with `write_stdin` using the returned
  `session_id` and no input. An outer JavaScript wrapper saying `Script completed` does not prove Python has exited.
  Use the corresponding wait/status operation if another command tool is provided.
- Do not rerun a command just because its first wait returned partial logs. Confirm the original process has exited
  before starting a replacement; if cancellation is necessary, stop only your own identified process and confirm exit.
- Keep the task's simulator and sensor configuration. Waiting does not extend the actual agent wall-clock budget.
- Connect with `Robot()` and let its retry loop wait for the existing service (default connection budget: 600 seconds,
  still subject to the actual agent deadline). Do not try to start or rebuild a simulator yourself.
- Reconnecting a client accesses the same episode; it does not reset the world. While an action request is still
  running, wait for its original command rather than resubmitting the same actions, which could execute them twice.

## Time per call
- One control step takes about 2.2 s of wall clock on an unloaded GPU and up to about 4.4 s when other simulations share it; the advice below assumes the slower figure. A request returns only when all of its steps have run, and the client gives up waiting after 1800 s for `submit` and 600 s for `get_obs`: keep each `submit` to at most 206 control steps (5.15 s of simulated time: rows x dt); keep each `get_obs(seconds=...)` watch to at most 68 control steps (1.70 s) (both with a 2x margin).
- If a request times out in the client anyway, the service still runs it to the end: do NOT send it again (it would run twice). Call `r.get_obs()` (repeat it if it also times out): it answers once the earlier request has finished and shows the state after it.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`)
```python
from rcb_client import Robot
r = Robot()                                   # connects to the existing service; retries until ready (default timeout 600 s)
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
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, last/, frames/, proprio.npy, depth, frame_meta.npz
```
Cameras: `cam_high` (static); `cam_low` (static); `cam_left_wrist` (on the robot link `left/gripper_base`; it moves, so use the pose that comes with each frame); `cam_right_wrist` (on the robot link `right/gripper_base`; it moves, so use the pose that comes with each frame). Resolution 848×480. `spec["cameras"][cam]` gives the
intrinsics and the mounting: a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) · `link_T_cam_cv`).
A point (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z + cx, v = fy·Y/Z + cy;
depth is that Z. `spec["robot_spec"]` lists the joints with their position, velocity and effort limits, the grippers,
the PD gains and the tool frames; `spec["world"]` the frame conventions.

### Action types
- `joint_position` (14): `left/waist`, `left/shoulder`, `left/elbow`, `left/forearm_roll`, `left/wrist_angle`, `left/wrist_rotate`, `left_gripper`, `right/waist`, `right/shoulder`, `right/elbow`, `right/forearm_roll`, `right/wrist_angle`, `right/wrist_rotate`, `right_gripper`; radians, gripper = opening width in metres
  (left: 0 = closed .. 0.057385 = open; right: 0 = closed .. 0.057385 = open). Absolute targets tracked by PD controllers.
  Rows are `dt` apart (`1/40 ≤ dt ≤ 0.5` s, a multiple of the control period); a chunk may cover at most 10 s;
  out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the spec). The gripper switches at the
  row. Use `obs.meta["proprio"]["now"][:14]` as the starting row to move smoothly. An arm joint target moves at most
  0.04 rad per control step (1.6 rad/s, the same speed as `ee_pose` rows): a row that asks for more takes
  the control steps it needs, and `meta["clipped"]` says so.
- `ee_pose` (16): per arm (in the order ['left', 'right']) `x y z qw qx qy qz gripper`; world frame (robot base at (-0.136, 0.000, 0.920),
  +z up); quaternions wxyz. Each row is solved by inverse kinematics (no collision checking) and driven to in joint
  space; an arm whose IK fails holds and is reported in `meta["plan"]`. The pose is each gripper's **tool frame** (TCP;
  its approach and finger-closing axes are in `spec["robot_spec"]["tcp"]`), the same convention as the proprio TCP
  poses, so an observed pose is a valid target. At most 50 rows per submit. A row whose IK solution lies more than
  0.5 rad from the current joints on any joint is refused the same way as a failed IK (for a small pose change that is
  another IK branch, which would swing the arm): split long moves into rows a few cm and degrees apart.
- Both action types: no gripper target goes lower than 15 mm below the tabletop; a target that would bring any part of
  a gripper lower is stopped there and listed in `meta["clipped"]`. Every response's `meta["safety"]` reports, since the
  previous call, the deepest task contact and the longest time above its sustained limit (rigid families), the lowest
  rope / cord volume ratio (soft families) and the table-guard stops, against the limits above.

Grasping: physical grasping only (no assisted grasping): closing on an object squeezes it with the gripper's PD force; friction holds it.

Objects here: `rope`, `R1`, `R1_stand`, `R1_base`, `R2`, `R2_stand`, `R2_base`, `R3`, `R3_stand`, `R3_base`, `left_base_riser`, `right_base_riser`.
