# RoboWits · retrieve_cube — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a bimanual **Marvin** robot (two 7-DoF arms with Pika parallel grippers) **as if it were real hardware**:
the simulator runs in a service you cannot open. You get one client and one episode. **Task:** Retrieve the cube from
the container and place it on the green target area.

## Success criterion (as graded)
This is exactly what the grader checks (RoboWits' success predicate, stated in words, and the release and rest
condition the grader adds: the last item). Where the task text says something else, this section is what counts. After
every `submit` and every `get_obs` that watches (`seconds` > 0) the service checks the conditions at that instant;
when they hold, it keeps your last command for a settle window, inside the same call: 1 s with nothing checked, then 2
s in which every condition must hold at every 6th control step and at the last one, with each graded object staying
within 2 mm of where it was when those 2 s began (the *check window*). If the window passes, the episode ends as a
success; if not, the episode goes on and `meta["settle"]` says why. When your session ends, the same window decides
once more, after your last command. The window's steps are part of your recorded episode, and its result on the live
simulator is the verdict: nothing is replayed to grade it.

- The cube is at table height: the bottom of its bounding box between 1 cm below and 3 cm above the table top.
- The footprints of the cube and of the target area lie inside the table bounds grown by 1 cm.
- Less than 50 % of the cube's footprint area lies over the container's footprint.
- At least 50 % of the cube's footprint area lies over the target area (the cube is 1.5 cm, the target area 12 cm
  square).
- Released and at rest: no part of the robot touches the cube, and it moves at most 2 mm during the check window.

Not checked: where the container ends up.

Task text vs grader ("Retrieve the cube from the container and place it on the green target area."): The text and the
grader agree; the grader makes "out of the container" and "on the target" precise (half of the cube's footprint) and
requires the cube at table height.

Terms: a *footprint* is an object's outline seen from above; *not held* means that neither gripper tip (the `tcp_pose`
points of your proprioception) is inside the object's bounding box grown by 3 cm on every side; the *table bounds* are
a fixed rectangle slightly inside the edges of the table top (its corners are world positions, which this mode does
not give: keeping clear of the table's edges satisfies it).

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, when your time is up, on a
  simulator error, or at the technical step cap below. Knocked-over objects stay knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth when you ask for it) plus the robot's own state:
  joint positions, velocities and drive efforts, gripper openings, end-effector poses. Nothing tells you where the
  objects are (no object poses or positions), and no endpoint tests the success criterion: the episode simply ends
  (`meta["done"]`, `reason` "success") the first time it holds through the settle window.
- **Your only budget is the time limit (`## Time limit`)** (`meta["time_left_s"]` is the service's count of it). There is no step budget; actions
  and simulated time are reported as cost. One technical cap: the episode has at most 200000 control steps (about
  1.85 h of simulated time at 30 Hz; `spec["max_control_steps"]`, counted by `meta["control_steps"]`; a `get_obs`
  that watches counts too). The call that reaches it stops there and the episode ends (`reason` "step_guard"); no
  settle window runs after the cap, so such an episode is graded without one, as a failure. Use the time: ending your
  session before the task is done ends the episode as a failure.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script
  at `/app/output/gen.py` for the record.
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.
- **A busy service has not crashed.** The service answers one request at a time: while a call runs, every other
  request waits for it (`r.status()` from another process included), and a client-side timeout during that time means
  "busy", not "crashed": nothing restarts, the call runs to its end and the episode goes on from there.
- **If the service crashes** (the connection is refused or reset instead of an answer), it restarts and resumes the SAME
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
  (`1/30 ≤ dt ≤ 0.5` s, a whole number of 1/30 s control periods: `2/30`, not `0.067`; any other `dt` is refused, never
  rounded); a chunk may cover at most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]` (limits in
  the spec). Use `obs.meta["proprio"]["now"][:16]` as the starting row to move smoothly.
- `ee_pose` (16): right `x y z qw qx qy qz gripper`, left same; world frame (robot base at (0, 0, 1.08), x away from the
  robot, y to its left, +z up); quaternions wxyz. Each row is solved by inverse kinematics (no collision checking) and
  driven to in joint space; an arm whose IK fails holds and is reported in `meta["plan"]`. The pose is the **gripper tip**
  frame: +z is the approach direction, +x the direction the fingers close along (same convention as the `proprio`
  end-effector poses, so an observed pose is a valid target). At most 50 rows per submit; `dt` is ignored; a gripper
  width outside 0 .. 0.1 is clipped and listed in `meta["clipped"]`.
- A request with a field of the wrong type or out of range (`dt`, `seconds` outside 0 .. 30, `video_fps` not a whole
  number in 1 .. 30, `video`, `interpolate`, `cameras` not a list of names, `note` not a string, actions that are not
  finite (T, 16) numbers) is answered 400 before anything is executed: the client raises `ValueError`, nothing has
  moved and the episode goes on.
- One call returns at most 1500 images (`spec["max_frames_per_call"]`: cameras x frames; a frame with
  `depth="frames"` counts 4). A request that would exceed it is answered 400 the same way: ask for fewer cameras,
  a lower `video_fps` or a shorter call. `ee_pose` rows that take longer than planned stop adding frames at that
  number; the motion is executed in full and `meta["frames_skipped"]` counts them.

Objects here: deep narrow container, cube, target area.

The wrist joints are limited to ±60°, so a vertical approach only works for finger-closing directions within about ±60°
of the world y axis.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
