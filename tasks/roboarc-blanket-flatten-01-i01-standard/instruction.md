# RoboARC (simulator package `topogym`) · blanket_flatten — STANDARD MODE (robot as a service, eai-standard/2.4)

You control a robot (**two 6-DoF ALOHA (ViperX) arms with parallel-jaw grippers on a fixed base**) **as if it were real hardware**: the simulator runs in a service you cannot open. You get one
client and one episode. **Task:** Unfold and spread the blanket flat on the table without overlaps or excessive stretching, then release it and withdraw.

## Success requirements

- Cover at least 95% of the blanket's unfolded material area in top-down projection. Overlapping layers count only once, holes do not count, and a large outer bounding box is insufficient.
- The sheet must lie flat on the tabletop, fully in contact with the table surface: keep every cloth point at most 30 mm above the tabletop and no more than 8 mm below it.
- No material edge may stretch beyond 1.15 times its original length. Raised corners or pulling the blanket taut in the air do not count.
- Release all target parts and disengage any assisted grasp. Withdraw the robot until there is at least 5 mm of verified clearance from every target part; opening the fingers while still touching or surrounding the target is insufficient.
- During confirmation, every target point or rigid body's linear speed must be at most 30 mm/s and its displacement from the start of confirmation at most 3 mm.
- Keep all final conditions satisfied together for at least 0.5 s of simulation time. If any final condition stops holding, the confirmation interval starts again. A brief qualifying pose is not enough; let the simulation advance through the full interval.

## Task failure conditions

- Any cloth point falling more than 100 mm below the tabletop ends the episode in failure.

## Grader details (in addition to the requirements above)

- Robot safety (this benchmark's tooling): no gripper target goes lower than 15 mm below the tabletop; a commanded target that would bring any part of a gripper lower is stopped there, on the commanded path. The fingertips reach about 16 mm beyond the tool frame (TCP) along its approach axis, open or closed. Arm drive torques are capped (the effort limits in robot_spec), so an arm pushing against an obstacle stalls at that torque. An arm with any part more than 5 mm deep in a fixed object (a fixture, the table) is stopped where it is: its joint targets become its measured joints for that control step, so it stops pushing (the response does not report these stops).
- Forcing is recorded, not judged: an arm drive (not a gripper drive) at 95% of its torque cap or more while that arm's gripper, or a part it holds, presses on anything else with 20 N or more in total is forcing; 0.5 s of it on every physics tick is a forcing event in the evidence (`meta["safety"]`), shown to the reviewer when a success is reviewed. Forcing does not end the episode and does not change the grade by itself.
- Simulator breakdown (a cloth particle faster than 20 m/s): the episode ends as an infrastructure error, not your failure, unless an arm was forcing (even for one tick) within the 0.25 s before it: then it is your failure (forced_breakdown: what broke and what forced it).
- The blanket is 0.6 m x 0.48 m (0.288 m^2), so the coverage needs at least 0.2736 m^2 of its area in the top view. Heights are measured at the cloth particles' centres.
- The release clearance is measured from one box around all cloth particles, grown by 8 mm: every robot collision box must stay at least 5 mm from it, i.e. at least 13 mm outside the cloth's bounding box, above its highest point too.
- Soft grasp patches: blanket: spatial radius 18 mm, material radius 18 mm, finger proximity 6 mm, maximum material strain ratio 1.3, exposed patch required. Both fingers must be near the same material patch; penetration and native constraint health checks still apply. Two hands may hold disjoint patches of one object. Material bounds, when present, restrict the admissible region.
- Grading: success needs the live episode to succeed (with the thresholds above) AND one fresh-process replay of its rows to succeed; a live failure is final whatever the replay shows. Its cloth step runs on the GPU on a deterministic solver and the rest on the CPU (MuJoCo, float64), so that replay reproduces the live episode on the same host; the rule is kept as a margin: it runs the rows with the thresholds above and, if the episode has not ended after the last row, holds the final targets for up to 2 s (80 control steps), stopping at the first success or failure, so a confirmation that starts a few physics ticks later than in the live episode can still complete; during that hold it accepts a blanket coverage of 92% instead of 95% and cloth speeds up to 80 mm/s instead of 30 mm/s (the displacement limit during the confirmation stays). Nothing else is relaxed: every other condition, the failure conditions and the confirmation time are the same.

## Rules (real-robot rules)
- **No reset.** The episode ends on success (all final conditions satisfied for
  0.5 s), when your time is up, on a simulator error, or when the task's own failure predicate fires (then `meta["reason"]` is `task_failed`). Knocked-over objects stay
  knocked over.
- **No privileged state.** You see what the cameras see (RGB, and depth when you ask for it) plus the robot's own state:
  joint positions, velocities and drive efforts, gripper openings, end-effector poses. Nothing tells you where the
  objects are (no object poses or positions). The success implementation is not exposed, and of the simulator's internal
  measurements only the safety readings of `meta["safety"]` are (listed under Action types, below); the task
  requirements above still apply in full.
- **Your only budget is the time limit (`## Time limit`)**; there is no step budget, but the
  episode ends after 200000 control steps, watches included (83 min of simulated time; a technical cap,
  `spec["max_control_steps"]`: `meta["reason"]` is `step_guard`, and the episode is graded as it stands). Actions and simulated time are reported as cost.
  This service also ends the episode itself (`meta["reason"]` is `timeout`; it is graded as it stands) when its own
  count of that limit, `meta["time_left_s"]`, reaches 0. That count starts at your first request to the service, so it
  never reaches 0 before your time is up.
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
- Connect with `Robot()` and let its retry loop wait for the existing service (default connection budget: 3600 seconds,
  still subject to the actual agent deadline). Do not try to start or rebuild a simulator yourself.
- Reconnecting a client accesses the same episode; it does not reset the world. While an action request is still
  running, wait for its original command rather than resubmitting the same actions, which could execute them twice.

## Time per call
- One control step takes about 0.38 s of wall clock here. A request returns when all of its steps have run, or
  earlier: a call that has run for 900 s (`spec["max_call_wall_s"]`) is stopped by the service at the next control
  step and returns what it executed (`res.stopped` is `"max_call_wall_s"`; `res.meta["executed_rows"]`, or
  `res.meta["control_steps_watch"]` for a watch, says how far it got; the robot holds its last target). Check
  `res.stopped` before you send the next rows. A `submit` of the maximum 10 s chunk takes about 152 s here; a `get_obs(seconds=...)` watch fits up to about 1184 control steps (29.60 s, a 2x margin), and a longer one is cut short the same way.
- The client waits longer than that (1800 s for `submit`, 1020 s for `get_obs`), so a client timeout or a connection
  error means the connection or the service failed, not that the call is still on its way. Do NOT send the request
  again blindly (it could run twice): `r.operation_status()` tells what became of the last one. Its `status` is
  `completed` or `error` (with `rows_before` and `committed_rows`, the episode's control steps before and after it,
  and `stopped`), `interrupted` (the service restarted during it and resumes the same episode in the state after the
  last completed call: `spec["on_service_error"]`, `r.wait_ready()`), or `admitted` (not finished); an HTTP 404 error
  there means the service never admitted the request, so nothing ran. The service answers one request at a time, so
  this query waits while a call is running: repeat it if it times out. If your client hangs up, the service stops
  the call at the next control step. A request that arrives after its deadline is refused (408), and one whose
  operation id was already admitted is refused (409); neither moves the robot. A control step that hangs for more
  than 60 s past the call's limit ends the episode as an infrastructure error, not as your failure.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.4`)
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
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, last/, frames/, proprio.npy, depth, frame_meta.npz
```
Cameras: `cam_high` (static); `cam_low` (static); `cam_left_wrist` (on the robot link `left/gripper_base`; it moves, so use the pose that comes with each frame); `cam_right_wrist` (on the robot link `right/gripper_base`; it moves, so use the pose that comes with each frame). Resolution 848×480. `spec["cameras"][cam]` gives the
intrinsics and the mounting: a static pose, or the parent link and the fixed offset (world_T_cam = FK(link) · `link_T_cam_cv`).
A point (X, Y, Z) in a camera's OpenCV frame (x right, y down, z forward) appears at u = fx·X/Z + cx, v = fy·Y/Z + cy;
depth is that Z. `spec["robot_spec"]` lists the joints with their position, velocity and effort limits, the grippers,
the PD gains and the tool frames; `spec["world"]` the frame conventions (the world frame: origin at the robot's root link on its mounting, +z up; no positions of the scene are given).

### Action types
- `joint_position` (14): `left/waist`, `left/shoulder`, `left/elbow`, `left/forearm_roll`, `left/wrist_angle`, `left/wrist_rotate`, `left_native_gripper`, `right/waist`, `right/shoulder`, `right/elbow`, `right/forearm_roll`, `right/wrist_angle`, `right/wrist_rotate`, `right_native_gripper`. arm `left`: 6 joint targets (rad), then `left_native_gripper` = native drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec); arm `right`: 6 joint targets (rad), then `right_native_gripper` = native drive target (m, limits 0.002 .. 0.037; open/closed targets in robot_spec). Absolute targets tracked by PD controllers.
  Rows are `dt` apart (`1/40 ≤ dt ≤ 0.5` s, a multiple of the control period); a chunk may cover at most 10 s;
  out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the spec). The gripper switches at the
  row. Use `obs.meta["proprio"]["now"][:14]` as the starting row to move smoothly. An arm joint target moves at most
  0.04 rad per control step (1.6 rad/s, the same speed as `ee_pose` rows): a row that asks for more takes
  the control steps it needs, and `meta["clipped"]` says so.
  The proprio group `gripper_opening` (`res.group("gripper_opening")`) is the measured gap between each gripper's finger
  pads in metres (0 = the pads touch); the gripper entries of `joint_pos` are in the unit of the gripper command above.
- `ee_pose` (16): per arm (in the order ['left', 'right']) `x y z qw qx qy qz gripper`; world frame (origin at the robot's root link on its mounting, +z up; the frame of the proprio TCP pose and the camera extrinsics); quaternions wxyz. Each row is solved by inverse kinematics (no collision checking) and driven to in joint
  space; an arm whose IK fails holds and is reported in `meta["plan"]`. The pose is each gripper's **tool frame** (TCP;
  its approach and finger-closing axes are in `spec["robot_spec"]["tcp"]`), the same convention as the proprio TCP
  poses, so an observed pose is a valid target. At most 50 rows per submit. A row whose IK solution lies more than
  0.5 rad from the current joints on any joint is refused the same way as a failed IK (for a small pose change that is
  another IK branch, which would swing the arm): split long moves into rows a few cm and degrees apart.
- One call returns at most 2000 images (`spec["max_frames_per_call"]`: cameras x frames; a frame with
  `depth="frames"` counts 4). A request that would exceed it is answered 400 before anything moves: ask for
  fewer cameras, a lower `video_fps` or a shorter call. Rows that take longer than planned (the speed limit, `ee_pose`)
  stop adding frames at that number; the motion is executed in full and `meta["frames_skipped"]` counts them.
- Both action types: no gripper target goes lower than 15 mm below the tabletop; a target that would bring any part of
  a gripper lower is stopped there and listed in `meta["clipped"]`. Every response's `meta["safety"]` reports, since the
  previous call, forcing (the arms' pressing loads and forcing events), the deepest task contact, the longest time above
  its sustained limit and the review events (rigid families), the lowest rope / cord volume ratio (soft families) and the
  table-guard stops, against the limits above.

Grasping: assisted grasping (pbd_local_patch_v1): closing intent and bilateral finger proximity to a material patch of blanket must persist for 0.03 s, with penetration at most 2 mm and the TCP within 6 cm. The admitted patch follows through a local kinematic PBD attachment; the rest remains deformable. Opening by more than 0.2 % of gripper travel releases it. A hold is lost on excessive opening, material strain, invalid volume or follow error above 10 mm; a lost hand must open before reacquiring. Two hands may hold disjoint material patches of the same object; overlapping patches are rejected. Patch radii, strain limits and the exposed-patch requirement are declared in grasp_assist.targets.

Objects here: `blanket`.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 10800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
