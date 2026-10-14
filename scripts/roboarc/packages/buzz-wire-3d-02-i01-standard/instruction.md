# TopoGym · buzz_wire_3d — STANDARD MODE (robot as a service, eai-standard/2.3)

You control a robot (**a 7-DoF Franka Panda arm with a Robotiq 2F-85 parallel gripper on a fixed base**) **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode. **Task:** Guide the metal loop along the entire wire from start to finish without touching the wire, then release the tool on the finish support.

## Success requirements

- Start within 10 mm along the wire from its starting end and traverse continuously until within 10 mm of its finishing end. Keep one unambiguous wire crossing inside the loop. Skipping branches or taking the loop off the route before completing traversal does not count; restart from the beginning if tracking is lost.
- After completing traversal, lower the tool onto the finish support. The completed traversal remains valid when the loop leaves the wire to rest on the support.
- Match the finish resting pose within 5 mm and 10 degrees. A half-turn about the handle axis is an equivalent orientation. The tool must actually contact the finish support.
- Keep all metal parts of the tool clear of the metal wire throughout the episode. Wooden-handle contact is not a metal-wire failure. Remove all robot contact before final confirmation.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 1 mm/s and its displacement from the start of confirmation at most 1 mm. Each target rigid body's angular speed must be at most 0.02 rad/s and angular drift at most 0.02 rad.
- Keep all final conditions satisfied together for at least 1 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- Any metal-tool touch of the metal wire ends the episode in failure, including brief or zero-force touches.
- The tool falling more than 100 mm below the tabletop ends the episode in failure.

## Grader details (in addition to the requirements above)

- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 6 mm beyond the tool frame (TCP) along its approach axis when open and about 19 mm when closed (the Robotiq fingertips move forward as they close). Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque.
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`meta["safety"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- The release clearance is measured between axis-aligned bounding boxes: one around each collision geometry of the whole robot (every link of both arms) and one around each collision geometry of the tool, so the true gap usually has to be larger than 5 mm.
- The loop's usable opening: the wire's centreline must cross the loop's disk less than 12.67 mm from the loop's centre (loop inner radius 14.14 mm minus the 1.47 mm wire radius).
- Continuous traversal: from one physics tick to the next, the crossing point may move along the wire by at most twice the loop's own motion in that tick (its displacement plus 12.67 mm times its rotation angle) plus 3 mm. A larger jump, no crossing, two crossings or a tangency cancels the traversal; it must then start again within 10 mm of the starting end, the end where the tool rests at the start.
- The finish support is the deck, and the finish resting pose is the start resting pose repeated at the wire's finishing end: the tool lies on the deck with its loop at that end of the wire and its handle pointing inward, the way it lies at the start.
- Metal contact is sampled at all 4 solver substeps of every tick. If any tick since the start had incomplete contact coverage (a simulator-side condition), the episode can no longer succeed.
- Grasp regions (assisted grasping, see Grippers above; one sphere per graspable part): wand: radius 25 mm, on the wand's grip. Both finger contacts must lie inside the part's sphere; a part touched elsewhere is grasped physically.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success (all final conditions satisfied for
  1 s), when your time is up, on a simulator error, or when the task's own failure predicate fires (then `meta["reason"]` is `task_failed`). Knocked-over objects stay
  knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth when you ask for it) plus the robot's own state:
  joint positions, velocities and drive efforts, gripper openings, end-effector poses. Nothing tells you where the
  objects are (no object poses or positions). The success implementation and internal measurements are not exposed;
  the task requirements above still apply in full.
- **Your wall-clock budget is 360 min (21600 s)** (`meta["time_left_s"]` counts it down); steps are unlimited. Actions and
  simulated time are reported as cost. One control step takes about 0.064 s of wall clock here.
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
- One control step takes about 0.064 s of wall clock here. A request returns only when all of its steps have run, and the client gives up waiting after 1800 s for `submit` and 600 s for `get_obs`: a `submit` of the maximum 10 s chunk fits; any watch up to 30 s fits (both with a 2x margin).
- If a request times out in the client anyway, the service still runs it to the end: do NOT send it again (it would run twice). Call `r.get_obs()` (repeat it if it also times out): it answers once the earlier request has finished and shows the state after it.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.3`)
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
- `joint_position` (8): `joint1`, `joint2`, `joint3`, `joint4`, `joint5`, `joint6`, `joint7`, `arm_native_gripper`. arm `arm`: 7 joint targets (rad), then `arm_native_gripper` = native drive target (m, limits 0 .. 0.8; open/closed targets in robot_spec). Absolute targets tracked by PD controllers.
  Rows are `dt` apart (`1/40 ≤ dt ≤ 0.5` s, a multiple of the control period); a chunk may cover at most 10 s;
  out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the spec). The gripper switches at the
  row. Use `obs.meta["proprio"]["now"][:8]` as the starting row to move smoothly. An arm joint target moves at most
  0.04 rad per control step (1.6 rad/s, the same speed as `ee_pose` rows): a row that asks for more takes
  the control steps it needs, and `meta["clipped"]` says so.
- `ee_pose` (8): per arm (in the order ['arm']) `x y z qw qx qy qz gripper`; world frame (robot base at (-0.570, 0.000, 0.920),
  +z up); quaternions wxyz. Each row is solved by inverse kinematics (no collision checking) and driven to in joint
  space; an arm whose IK fails holds and is reported in `meta["plan"]`. The pose is each gripper's **tool frame** (TCP;
  its approach and finger-closing axes are in `spec["robot_spec"]["tcp"]`), the same convention as the proprio TCP
  poses, so an observed pose is a valid target. At most 50 rows per submit. A row whose IK solution lies more than
  0.5 rad from the current joints on any joint is refused the same way as a failed IK (for a small pose change that is
  another IK branch, which would swing the arm): split long moves into rows a few cm and degrees apart.
- Both action types: no gripper target goes lower than 15 mm below the tabletop; a target that would bring any part of
  a gripper lower is stopped there and listed in `meta["clipped"]`. Every response's `meta["safety"]` reports, since the
  previous call, forcing (the arms' pressing loads and forcing events), the deepest task contact, the longest time above
  its sustained limit and the review events (rigid families), the lowest rope / cord volume ratio (soft families) and the
  table-guard stops, against the limits above.

Grasping: assisted grasping (contact_weld_v1): a gripper whose command moves towards closed takes hold of a graspable part (wand) once both fingers touch the same part inside its grasp region, the tool frame within 6 cm of it and the penetration at most 2 mm, for 0.02 s; the part then follows the gripper rigidly. Any command that opens the gripper (by more than 0.2 % of its travel) lets it go. A hold that breaks (the fingers open more than 15 %, or the part drifts 1 cm / 0.15 rad from its held pose) is lost, and the gripper must open before it can take hold again. Two grippers never hold the same part; other objects are grasped physically (friction).

Objects here: `wire_base`, `wire`, `wand`.
