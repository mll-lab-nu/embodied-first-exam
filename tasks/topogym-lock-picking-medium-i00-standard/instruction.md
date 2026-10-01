# TopoGym · lock_picking — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a robot (**a 7-DoF Franka Panda arm with a Robotiq 2F-85 parallel gripper on a fixed base**) **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode. **Task:** Insert the tabbed key through all three rotor plates and the final END plate, while respecting their slots and stops.

## Success requirements

- Keep the finite-length shaft passing through the full thickness of all four plates at once, facing the insertion direction. Reaching END with only the shaft tip is insufficient.
- The rear edge of the leading tab must clear the outer face of END by at least 1 mm.
- Normal contact with the bore wall and a small tilt are allowed when the shaft still fits through all four bores. The radial numerical contact tolerance is 0.01 mm; do not push the shaft through solid plate material.
- Keep every tab clear of solid plate material whenever it overlaps a plate; account for the key's offset and tilt, not just its rotation about the shaft.
- Keep limited-travel rotor pins within their physical slot bounds (angular tolerance 0.5 degrees).
- You may keep holding the key. Release and zero velocity are not required; all insertion and clearance conditions must remain satisfied throughout confirmation.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- A limited-travel rotor exceeding its allowed bounds ends the episode in failure.
- The key falling more than 100 mm below the tabletop ends the episode in failure.

## Grader details (in addition to the requirements above)

- Sizes: bore radius 7.5 mm, shaft radius 6.5 mm. At each of the 8 plate faces (three 10 mm rotor plates and END, 150 mm apart), the shaft axis' distance from the bore axis plus 6.5 mm / cos(tilt) may exceed 7.5 mm by at most 0.01 mm: about 1.01 mm of offset when the key is straight, which over the stack allows only about 0.25 degrees of tilt.
- The shaft reaches from 515 mm behind the leading tab to 15 mm in front of it; all 8 plate faces must lie within that length.
- Tabs: radius 36 mm, half-width 4 degrees; slots: half-width 8 degrees. A tab that overlaps a plate must sit inside one of that plate's slots with an angular margin of at least asin(axis offset / 36 mm) + the tilt.
- Rotor stops (from each rotor's start angle; "the other way" is the sense that turns rotor 2's slot toward the tabs' starting angle): rotor 1 15 degrees either way; rotor 2 10 degrees one way and 75 degrees the other; rotor 3 turns freely. Going more than 0.5 degrees beyond a stop ends the episode.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): lock_key: radius 32 mm, on the key's handle. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success (all final conditions satisfied for
  0.5 s), when your time is up, on a simulator error, or when the task's own failure predicate fires (then `meta["reason"]` is `task_failed`). Knocked-over objects stay
  knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth when you ask for it) plus the robot's own state:
  joint positions, velocities and drive efforts, gripper openings, end-effector poses. Nothing tells you where the
  objects are (no object poses or positions). The success implementation and internal measurements are not exposed;
  the task requirements above still apply in full.
- **Your wall-clock budget is 360 min (21600 s)** (`meta["time_left_s"]` counts it down); steps are unlimited. Actions and
  simulated time are reported as cost. One control step takes about 0.8 s of wall clock on an unloaded GPU, and up to about 2.9 s when other simulations share the GPU; the call metadata reports the time.
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
- One control step takes about 0.8 s of wall clock on an unloaded GPU and up to about 2.9 s when other simulations share it; the advice below assumes the slower figure. A request returns only when all of its steps have run, and the client gives up waiting after 1800 s for `submit` and 600 s for `get_obs`: keep each `submit` to at most 310 control steps (7.75 s of simulated time: rows x dt); keep each `get_obs(seconds=...)` watch to at most 103 control steps (2.58 s) (both with a 2x margin).
- If a request times out in the client anyway, the service still runs it to the end: do NOT send it again (it would run twice). Call `r.get_obs()` (repeat it if it also times out): it answers once the earlier request has finished and shows the state after it.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects to the existing service; retries until ready (default timeout 600 s)
spec = r.spec()                               # actions, cameras (intrinsics, mounting), robot_spec, world, kinematics, budget

obs = r.get_obs()                             # current frames from 3 cameras: obs.last[cam] -> uint8 (480,848,3)
obs.meta["proprio"]                           # {"layout": [40 names], "now": [...]}: groups in spec["proprio_groups"]
obs.meta["cameras"]                           # per camera: intrinsic_cv, extrinsic_cv, cam2world_gl of the LAST frame
obs = r.get_obs(depth=True)                   # + obs.last_depth[cam]: float32 (480,848) z-depth in metres, 0 = no reading
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 8) rows dt seconds apart; streamed at 40 Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 8) tool-frame targets; inverse kinematics per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["agentview"]                          # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["agentview"]                         # uint8 (N,480,848,3) at video_fps if requested
res.last["wrist"]; res.proprio              # last frame per camera; float32 (N, 40) proprio, one row per frame
res.frame_step, res.frame_time_s              # per frame: control steps since the episode start, simulated time (s)
res.extrinsic_cv["wrist"]                    # (N,3,4) world -> camera at every frame
res = r.submit("joint_position", A, dt=0.1, depth="frames")   # + res.depth[cam]: (N,480,848) z-depth per frame (1 mm steps)
res.group("tcp_pose"); res.group("joint_effort", now=True)   # proprio columns by group name
r.fk(q)["poses"]["arm_tcp"]                   # forward kinematics of the 7 arm joints (spec["kinematics"]); moves nothing
r.ik({"arm_tcp": pose}, seed=q)             # inverse kinematics -> {"ok", "q", "error"}; moves nothing
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, last/, frames/, proprio.npy, depth, frame_meta.npz
```
Cameras: `agentview` (static); `front_oblique` (static); `wrist` (on the robot link `hand`; it moves, so use the pose that comes with each frame). Resolution 848×480. `spec["cameras"][cam]` gives the
intrinsics and the mounting: a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) · `link_T_cam_cv`).
A point (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z + cx, v = fy·Y/Z + cy;
depth is that Z. `spec["robot_spec"]` lists the joints with their position, velocity and effort limits, the grippers,
the PD gains and the tool frames; `spec["world"]` the frame conventions.

### Action types
- `joint_position` (8): `joint1`, `joint2`, `joint3`, `joint4`, `joint5`, `joint6`, `joint7`, `arm_gripper`; radians, gripper = opening width in metres
  (arm: 0 = closed .. 0.0854 = open). Absolute targets tracked by PD controllers.
  Rows are `dt` apart (`1/40 ≤ dt ≤ 0.5` s, a multiple of the control period); a chunk may cover at most 10 s;
  out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the spec). The gripper switches at the
  row. Use `obs.meta["proprio"]["now"][:8]` as the starting row to move smoothly.
- `ee_pose` (8): per arm (in the order ['arm']) `x y z qw qx qy qz gripper`; world frame (robot base at (-0.570, 0.000, 0.920),
  +z up); quaternions wxyz. Each row is solved by inverse kinematics (no collision checking) and driven to in joint
  space; an arm whose IK fails holds and is reported in `meta["plan"]`. The pose is each gripper's **tool frame** (TCP;
  its approach and finger-closing axes are in `spec["robot_spec"]["tcp"]`), the same convention as the proprio TCP
  poses, so an observed pose is a valid target. At most 50 rows per submit.

Grasping: assisted grasping (contact_weld_v1): a gripper whose command moves towards closed takes hold of a graspable part (lock_key) once both fingers touch the same part inside its grasp region, the tool frame within 6 cm of it and the penetration at most 2 mm, for 0.05 s; the part then follows the gripper rigidly. Any command that opens the gripper (by more than 0.2 % of its travel) lets it go. A hold that breaks (the fingers open more than 15 %, or the part drifts 1 cm / 0.15 rad from its held pose) is lost, and the gripper must open before it can take hold again. Two grippers never hold the same part; other objects are grasped physically (friction).

Objects here: `lock_base`, `lock_disc_0`, `lock_frame_0`, `lock_disc_1`, `lock_frame_1`, `lock_disc_2`, `lock_frame_2`, `key_tray`, `key_tray_post_0`, `key_cradle_0_0`, `key_cradle_0_1`, `key_tray_post_1`, `key_cradle_1_0`, `key_cradle_1_1`, `lock_goal_post`, `lock_goal`, `lock_key`.
