# RoboLab · banana_in_bowl — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a **Franka Panda arm with a Robotiq 2F-85 gripper** (NVIDIA RoboLab's DROID setup) **as if it were real
hardware**: the simulator runs in a service you cannot open. You get one client and one episode. **Task:** Pick up the
banana and place it in the bowl: the banana must end up inside the bowl, in contact with it, and the gripper must have
let go of it.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success (at the first control step where the
  success condition holds), when your time is up, or on a simulator error. Knocked-over objects stay knocked over. When
  your session ends the service holds your last command for 30 more control steps (2 s) while it checks the condition,
  so a release you sent last completes. "The gripper" in the success condition is both Robotiq fingers: an object that
  touches either finger is still held.
- **No privileged state.** You see what the cameras see (RGB, and depth if you ask) plus the robot's own
  proprioception (joints, gripper, end-effector pose, velocities, drive efforts). No object poses, no success predicate.
- There is no step budget: the time limit (`## Time limit`) is your only budget (`meta["time_left_s"]`). Actions and simulated time
  are reported as cost. One technical cap: the episode ends after 100,000 control steps (1.9 h of simulated time;
  `spec["max_control_steps"]`, reason `step_guard`) and is graded as it stands; at this service's speed (3-15 control
  steps/s) your time runs out long before.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script
  at `/app/output/gen.py` for the record. The episode is graded as it stands when your time is up: keep working until it
  has succeeded.
- **A busy service has not crashed.** The service answers one request at a time: while a call runs (a long `submit` or
  a watching `get_obs` can take minutes; one call stops at `spec["max_call_wall_s"]`), every other request waits for
  it, `r.status()` from another process included. A client-side timeout while a call is in flight (for example
  `requests` ReadTimeout on `r.status()`) means "busy": nothing restarts, the call runs to its end and the episode goes
  on from there. Keep one client process and wait for your call's answer.
- **If the service crashes**, the connection is refused or reset and the call is lost: the
  simulator restarts and resumes the SAME episode (never a reset) in the state after the last call it completed, which
  you may not have received. `r.wait_ready()` waits until it answers again (resuming replays the episode so far, which
  can take minutes; the wall clock keeps running), then check `r.status()["control_steps"]` before you continue
  (`spec["on_service_error"]`).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects (waits while Isaac Sim starts and builds the scene, ~2 min; longer on a
                                              # busy host: it reports its progress on stderr and gives up after 3600 s)
spec = r.spec()                               # action types, dims, joint limits, cameras, budget, robot spec

obs = r.get_obs()                             # current frames from 3 cameras: obs.last[cam] -> uint8 (H,W,3)
obs.meta["proprio"]                           # {"layout": [...32 names], "now": [...]}: joints, gripper, end-effector pose, ...
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl at the LAST frame
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.2)   # A: (T, 8) rows dt seconds apart; streamed at 15 Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 8) fingertip-centre targets; differential IK per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["wrist_cam"]                        # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["wrist_cam"]                       # uint8 (N,H,W,3) at video_fps if requested
res.last["egocentric_mirrored_camera"]; res.proprio   # last frame per camera; float32 (N, 32) proprio at each video frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy
```
Cameras: `egocentric_mirrored_camera` (static, facing the robot across the table, 864×480), `over_shoulder_left_camera`
(static, over the robot's left shoulder, 1280×720) and `wrist_cam` (on the gripper, 1280×720; it moves:
`res.extrinsic_cv["wrist_cam"]` has its pose at every frame).

### Optional inputs (eai-standard/2.2; ask only for what you need)
- Depth: `r.get_obs(depth=True)` -> `obs.last_depth[cam]` float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned
  with `obs.last[cam]`; `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N,H,W), one map per frame (1 mm steps).
- Per frame: `res.frame_step` (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N,3,4 world -> camera, OpenCV
  axes). `spec["cameras"][cam]`: `intrinsic_cv` and `mount` (static pose, or `wrist_cam` on link `base_link` with a fixed
  `link_T_cam_cv`).
- `spec["robot_spec"]` (joints and their limits, gripper, controller gains, tool frames), `spec["world"]` (frame, units,
  wxyz), `spec["proprio_groups"]` + `res.group("joint_vel")` (joint_pos, joint_vel, tcp_pose, gripper_opening, joint_effort).
- `r.fk(q7)` -> poses of `spec["kinematics"]["links"]`; `r.ik({"tcp": pose7}, seed=q7)` -> `{"ok", "q", "error"}`: a
  stateless model of the arm (no physics, no simulated time).

### Action types
- `joint_position` (8): `panda_joint1..7, gripper`; radians, and the gripper command is binary (0 = open, 1 = closed; it
  switches at the row, never interpolated). Absolute targets tracked by PD controllers. Rows are `dt` apart
  (`1/15 ≤ dt ≤ 0.5` s, a multiple of the 15 Hz control period: 1/15, 2/15, ...; any other `dt` is rejected, never
  rounded); a chunk may cover at most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]` (limits in the
  spec). Use `obs.meta["proprio"]["now"][:7]` for the current joints to move smoothly.
- `ee_pose` (8): `x y z qw qx qy qz gripper` in the env-local frame (the robot's root frame: Franka base at the origin, x
  forward towards the table, z up); quaternions wxyz. Each row is driven to by differential IK in closed loop (at most
  0.25 m/s); a row that does not converge within 6 mm is reported in `meta["plan"]`. The pose is the **fingertip-centre
  tool frame**: the gripper flange moved 0.162 m along the approach axis to the ends of the closed fingertips (the pads
  extend ~5.7 cm back from there). At the reset pose the gripper points straight down. At most 50 rows per submit; a
  position more than 2 m from the robot's base on any axis, or a zero quaternion, is rejected (400), nothing moves.
- A malformed request (a wrong type, a value out of range) is answered 400 with the reason and executes nothing.

Objects here: a yellow banana and a red bowl on the table.
The Robotiq opens to 8.5 cm. The episode ends by itself the moment the banana rests in the bowl with the gripper open.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
