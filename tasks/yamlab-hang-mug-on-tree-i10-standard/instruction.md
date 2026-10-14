# YAMLab · HangMugOnTree-v0 — STANDARD MODE (robot as a service, eai-standard/2.2)

You control two **I2RT YAM arms with parallel two-finger grippers** on a workstation table (YAMLab's bimanual setup)
**as if they were real hardware**: the simulator runs in a service you cannot open. You get one client and one episode.
**Task:** Pick up the mug with the **left** arm, hand it over to the **right** arm (the right gripper takes it, then the left one lets go, with the mug kept lifted), and hang the mug on the mug tree, released by both grippers. The scene has the mug and the mug tree on the table.

## Success
1. **pick**: the **left** gripper grasps the mug (YAMLab's grasp detection: both fingers of that gripper touch the mug with at least 0.1 N, on their pads) and the mug's centre is more than 5 cm above its resting height, for 8 consecutive control steps;
2. **handover**: the **right** gripper grasps the mug, the left gripper does not, and the mug's centre stays more than 5 cm above its resting height, for 30 consecutive control steps (as in YAMLab, the left fingers' friction is raised when the left gripper first grasps the mug and lowered again when both grippers hold it: YAMLab's own handover aid);
3. **hang**: the mug's centre within 0.114 m (horizontally) of the mug tree's centre and more than 5 cm above the height it would rest at on the table, **neither** gripper grasping it, and its height steady (within 3.0 cm of where this stage started), for 30 consecutive control steps.

Each condition must hold for the stated number of consecutive control steps (1/30 s each); the stages count in order and
stay counted once reached. The episode **ends by itself** at the first control step where every stage has been reached
(success), or when a task object falls off the table (failure).

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, when an object falls off the table, when
  your time is up, or on a simulator error. A dropped or knocked-over object stays that way.
- **No privileged state.** You see what the cameras see (RGB, and depth if you ask) plus the robot's own proprioception
  (joints, grippers, tool-frame poses, velocities, drive efforts). No object poses, no success signal.
- There is no step budget: the time limit (`## Time limit`) is your only budget (`meta["time_left_s"]`). Actions and simulated time
  are reported as cost. One technical cap: the episode ends after **100,000 control steps** (55.6 min of simulated time;
  `spec["max_control_steps"]`, reason `step_guard`) and is graded as it stands. The service steps faster than real time
  (60-120 control steps/s), so long watches and far-away `ee_pose` targets can reach it: `meta["control_steps"]` counts.
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record. The episode is graded as it stands when your time is up: keep working until it has
  succeeded.
- **If the service crashes**, a call fails with a connection error: the simulator restarts and resumes the SAME episode
  (never a reset) in the state after the last call it completed, which you may not have received. `r.wait_ready()` waits
  until it answers again (resuming replays the episode so far, which can take minutes; the wall clock keeps running), then
  check `r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and builds the scene (see below)
spec = r.spec()                               # action types, dims, joint limits, cameras, budget, robot spec

obs = r.get_obs()                             # current frames from 3 cameras: obs.last[cam] -> uint8 (480, 640, 3)
obs.meta["proprio"]                           # {"layout": [...58 names], "now": [...]}: joints, grippers, tool poses, ...
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl at the LAST frame
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 14) rows dt seconds apart; streamed at 30 Hz with linear interpolation
res = r.submit("ee_pose", P)                  # P: (T, 16) tool-frame targets of both arms; differential IK per row
res.meta["done"], res.meta["reason"], res.meta["plan"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["top"]                              # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["left_wrist"]                      # uint8 (N,H,W,3) at video_fps if requested
res.last["right_wrist"]; res.proprio          # last frame per camera; float32 (N, 58) proprio at each video frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy
```
The service's first start in a trial compiles Isaac's shaders: `Robot()` can wait ~2-12 min (it prints its progress to
stderr once a minute). It gives up after 3600 s (`Robot(timeout=...)`) with `RuntimeError("sim service unavailable ...")`:
then call it again (nothing has happened in the episode yet; your wall clock runs from the start of the trial).

Cameras (640×480 each): `top` (static, above the table looking down at the workspace), `left_wrist` and `right_wrist` (on
each arm's wrist; they move: `res.extrinsic_cv[cam]` has their pose at every frame).

### Optional inputs (eai-standard/2.2; ask only for what you need)
- Depth: `r.get_obs(depth=True)` -> `obs.last_depth[cam]` float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned
  with `obs.last[cam]`; `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N,H,W), one map per frame (1 mm steps).
- Per frame: `res.frame_step` (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N,3,4 world -> camera, OpenCV
  axes). `spec["cameras"][cam]`: `intrinsic_cv` and `mount` (static pose, or a wrist camera on link `<arm>_link_6` with a
  fixed `link_T_cam_cv`).
- `spec["robot_spec"]` (joints and their limits, grippers, controller gains, tool frames, the arm bases), `spec["world"]`
  (frame, units, wxyz), `spec["proprio_groups"]` + `res.group("joint_vel")` (joint_pos, tcp_pose, gripper_cmd, joint_vel,
  gripper_opening, joint_effort).
- `r.fk(q12)` -> poses of `spec["kinematics"]["links"]`; `r.ik({"left_tcp": pose7}, seed=q12)` -> `{"ok", "q", "error"}`:
  stateless models of both arms (no physics, no simulated time); `q12` = left joint1..6 then right joint1..6.

### Action types
- `joint_position` (14): `left_joint1..6, left_gripper, right_joint1..6, right_gripper`, YAMLab's own action. Joints:
  absolute targets (rad) tracked by PD controllers. Gripper: the position target of that arm's finger in metres,
  **-0.0475 = fully open .. 0.0 = closed** (continuous; a closing gripper stops at whatever is between its fingers). Rows
  are `dt` apart (`1/30 ≤ dt ≤ 0.5` s, a multiple of the 30 Hz control period: 1/30, 2/30, ...; any other `dt` is
  rejected, never rounded); `interpolate="linear"` (default) or `"hold"`; a chunk may cover at most 10 s; out-of-limit
  values are clipped and listed in `meta["clipped"]` (limits in the spec). Start from `obs.meta["proprio"]["now"]` (the
  first 14 columns are the measured joints and fingers) to move smoothly.
- `ee_pose` (16): per arm, left then right, `x y z qw qx qy qz gripper` in the world frame (metres; x forward from the
  arm bases towards the far side of the table, y to the left, z up; quaternions wxyz). Each row drives both tool frames to
  their targets together by differential IK in closed loop (at most 0.25 m/s); an arm that does not converge within 6 mm is
  reported in `meta["plan"]`. The tool frame `<arm>_tcp` is the midpoint of that gripper's two fingertips, 0.1426 m from
  `link_6` along `link_6`'s +z (approach) axis, with `link_6`'s orientation. At the start both arms are at their home pose
  (all joints 0, grippers open), tool frames pointing forward. At most 50 rows per submit; a position more than 3 m from
  the world origin on any axis, or a zero quaternion, is rejected (400), nothing moves.
- A malformed request (a wrong type, a value out of range) is answered 400 with the reason and executes nothing.
- Control runs at 30 Hz (simulated time; sim dt 1/120 s, decimation 4).

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 8 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
