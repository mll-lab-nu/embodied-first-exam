# RoboWits · stand_pages — STANDARD MODE, MCP TOOLS AND SHELL (robot as a service, eai-standard/2.2)

You control a bimanual **Marvin** robot (two 7-DoF arms with Pika parallel grippers) **as if it were real hardware**:
the simulator runs in a service you cannot open. You get one client and one episode. **Task:** Stand the two pages up
on the table so that they brace each other. They start joined like an open book: the stabilizing bar already runs
through the eyelets of both pages as a hinge pin, so nothing has to be inserted.

## Robot tools (MCP server `efe-robot`) and their Python client `efe_robot`
Besides the robot service's own client (below), you get the robot through the tools of the MCP server `efe-robot` (in
your tool list as `efe-robot` tools, for example `mcp__efe-robot__move_robot`) and through the same tools as Python
functions: `import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments
and result, and its docstring is the tool's description), or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'`
from the shell. They all drive the one robot: use one route at a time. The calls of the service's client and the tools
that do the same:

| Client | Tool |
|---|---|
| `Robot()`, `r.spec()` | `describe_robot()`: the robot's parts, joints and limits, cameras, control period, action types and conventions, and the time left; the full spec is saved as a JSON file (`spec_file`) you can read |
| `r.get_obs(cameras, seconds, depth)` | `observe(cameras, seconds, depth)` |
| `r.submit(type, A, dt, interpolate)` | `execute_trajectory(space="native", action_type=type, native_rows=A, dt=dt, interpolate=...)`, or `move_robot` / `execute_trajectory` in the conventions below |
| `r.status()`, `meta[...]` | every tool result: `time_left_s`, `sim_time_s`, `done`, `reason` and the service's messages |

**Conventions** of `move_robot`, `locomote` and `execute_trajectory` (spaces other than `native`): the robot base frame
at the start of each call (+X forward, +Y left, +Z up), metres and radians, quaternions `wxyz`, gripper 0 = open to 1 =
closed. Base frame of this robot: the robot base frame: the robot's base point (1.08 m above the world origin), +X away
from the robot towards the table, +Y to the robot's left, +Z up. Space `native` sends rows in the robot's own action
types exactly as the sections below describe them (their frame, units and gripper values).

**This robot** (Marvin bimanual robot: two 7-joint arms with parallel two-finger grippers at a table (RoboWits on
Genesis)): right (arm: 7 joints, end-effector pose, gripper); left (arm: 7 joints, end-effector pose, gripper). Cameras:
`ego`, `wrist_right`, `wrist_left`.

- `describe_robot()`: call it first.
- `observe(cameras?, depth?, seconds?, save_to?, inline_cameras?)`: images are written as JPEG files under `/app/obs/`
  (depth as `.npy`, float32 metres; with `seconds` > 0 a video `.mp4` too); the result has their paths, each camera's
  intrinsics `K` and pose in the robot base frame, each part's joints, gripper and end-effector pose, and `proprio_now`
  (the robot's own proprioception row; its layout is in the spec file). Open an image with your file-reading tool;
  `inline_cameras` also returns small images in the result.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (errors per goal), a `failure` category if a goal was not reached, the state and
  the path of a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: a dense trajectory, rows `dt` seconds
  apart; a long one can come from a file under `/app` (`.npy` / `.csv` of native rows, `.json` of rows).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending operation.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as described above).
- One tool call runs at a time (the Python functions wait for a pending call themselves). A call still executing after
  45 s returns `{"pending": true, "operation": id}` while the robot goes on executing it: call `wait(operation=id)` (it
  waits up to 45 s more each time) for its result. A result with `"episode_over": true` means the episode has ended.

**Notes on this robot.** The gripper value in the state is the commanded opening width (0.1 m = open, 0 = closed);
gripper_opening_m is the measured opening (a gripper closed on an object stops above 0). The wrist joints are limited to
about +-60 deg, so a vertical approach works only for finger-closing directions within about 60 deg of the +Y axis.
Joint efforts (Joint1_R_effort ...) in proprio_now rise when an arm pushes on something. The episode ends by itself once
the goal holds with the graded objects released and at rest through a short settle window.

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

- For each of the two pages:
  - it stands upright: within 15 degrees of vertical about both horizontal axes (either face forward, any heading);
  - its footprint lies inside the table bounds (no tolerance);
  - the bottom of its bounding box is within 3 cm of the table top;
  - it is not held.
- Released and at rest: no part of the robot touches either page or the stabilizing bar (holding the bar holds the
  pages up), and each page moves at most 2 mm during the check window.

Not checked: any connection between the pages (the hinge) and where the bar ends up.

Task text vs grader ("Stand the two pages up on the table so that they brace each other."): The hinge is not checked:
two pages standing upright on the table, released and at rest, pass with or without the bar through their eyelets. In
this scene the bar already runs through the eyelets of both pages at the start (they lie open like a book): nothing
has to be inserted.

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
- One call returns at most 1500 images (`max_frames_per_call`, PROTOCOL §3 "Images per call").

Objects here: two thin grey pages with a row of eyelets along one edge and a grey bar (20 cm long, 1.5 cm square
section) that already runs through the eyelets of both pages, all lying flat on the table in front of the robot.

The wrist joints are limited to ±60°, so a vertical approach only works for finger-closing directions within about ±60°
of the world y axis.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **4 CPUs**, **5 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
