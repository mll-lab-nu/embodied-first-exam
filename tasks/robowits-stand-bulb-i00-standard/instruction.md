# RoboWits · stand_bulb — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a bimanual **Marvin** robot (two 7-DoF arms with Pika parallel grippers) **as if it were real hardware**:
the simulator runs in a service you cannot open. You get one client and one episode. **Task:** Stand the tall object
with curved bottom stably within the green target area.

## Success criterion (as graded)
This is exactly what the grader checks (RoboWits' success predicate, stated in words). Where the task text says
something else, this section is what counts. The service evaluates it after every `submit` and after every `get_obs`
that watches (`seconds` > 0), and once more when the episode ends; the first time it holds, the episode ends as a
success. The service then replays your recorded episode, which must end in the same state and satisfy it again.

- The footprints of the tall object and of the target patch lie inside the table bounds (1 mm tolerance).
- The tall object is "upright": its bounding box is taller than it is wide.
- The tall object is still: its speed is at most 5 cm/s.
- At least 80 % of the tall object's footprint area lies over the target patch.
- The tall object is not held.

Not checked: the stabilizing ring, any tilt the bounding-box test lets through (for this 21.6 x 12 cm object, tilts up
to roughly 45 degrees can pass), and how long it stands.

Task text vs grader ("Stand the tall object with curved bottom stably within the green target area."): "Stand ...
stably" means the bounding-box test above and one speed sample at the end (at most 5 cm/s).

Terms: a *footprint* is an object's outline seen from above; *not held* means that neither gripper tip (the `tcp_pose`
points of your proprioception) is inside the object's bounding box grown by 3 cm on every side; the *table bounds* are
a fixed rectangle slightly inside the edges of the table top (its corners are world positions, which this mode does
not give: keeping clear of the table's edges satisfies it).

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, when your time is up, or on a
  simulator error. Knocked-over objects stay knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth when you ask for it) plus the robot's own state:
  joint positions, velocities and drive efforts, gripper openings, end-effector poses. Nothing tells you where the
  objects are (no object poses or positions), and no endpoint tests the success criterion: the episode simply ends
  (`meta["done"]`, `reason` "success") the first time it holds.
- **Your wall-clock budget is 90 min (5400 s)** (`meta["time_left_s"]` counts it down); steps are unlimited. Actions and
  simulated time are reported as cost. Use the time: ending your session before the task is done ends the episode as
  a failure.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script
  at `/app/output/gen.py` for the record.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.
- **If the service crashes** (a connection error or a 5xx instead of an answer), it restarts and resumes the SAME
  episode, never a reset, in the state after the last call it completed. `r.wait_ready()` waits until it answers again
  (resuming replays the episode so far: about a second per 700 control steps); then check `r.status()` (`calls`,
  `control_steps`) before you continue. A call that runs longer than `spec["max_call_wall_s"]` stops at the next control
  step and returns what it executed (`res.stopped`, `meta["executed_rows"]`).

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
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
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, last/, frames/, proprio.npy, depth, frame_meta.npz
```
Cameras: `ego` (static, above and behind the robot, looking at the table), `wrist_right` / `wrist_left` (on the wrists;
they move, so use the pose that comes with each frame). Resolution 848×480. `spec["cameras"][cam]` gives the intrinsics
and the mounting: a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) · `link_T_cam_cv`). A
point (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z + cx, v = fy·Y/Z + cy; depth
is that Z. `spec["robot_spec"]` lists the joints with their position, velocity and effort limits, the grippers, the PD
gains and the tool frames; `spec["world"]` the frame conventions.

### Action types
- `joint_position` (16): `Joint1_R..Joint7_R, right_gripper, Joint1_L..Joint7_L, left_gripper`; radians, gripper =
  opening width in metres, 0 = closed .. 0.1 = open. Absolute targets tracked by PD controllers. Rows are `dt` apart
  (`1/30 ≤ dt ≤ 0.5` s, a multiple of the 30 Hz control period); a chunk may cover at most 10 s; out-of-limit values are
  clipped and listed in `meta["clipped"]` (limits in the spec). Use `obs.meta["proprio"]["now"][:16]` as the starting
  row to move smoothly.
- `ee_pose` (16): right `x y z qw qx qy qz gripper`, left same; world frame (robot base at (0, 0, 1.08), x away from the
  robot, y to its left, +z up); quaternions wxyz. Each row is solved by inverse kinematics (no collision checking) and
  driven to in joint space; an arm whose IK fails holds and is reported in `meta["plan"]`. The pose is the **gripper tip**
  frame: +z is the approach direction, +x the direction the fingers close along (same convention as the `proprio`
  end-effector poses, so an observed pose is a valid target). At most 50 rows per submit.

Objects here: target patch, stabilizing ring, tall object with curved bottom.

The wrist joints are limited to ±60°, so a vertical approach only works for finger-closing directions within about ±60°
of the world y axis.
