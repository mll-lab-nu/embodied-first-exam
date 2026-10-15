# AM-Bench · NDT Inspection — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a simulated **aerial manipulator** **as if it were real hardware**: a fully actuated hexarotor (six tilted
rotors, so it can hold any attitude while hovering) carrying a small arm (four joints: three pitch joints and a roll joint)
with a two-finger gripper, in AM-Bench on Isaac Lab / Isaac Sim 5.1. The simulator runs in a service you cannot open. You
get one client and one episode. **Task:** The hovering aerial manipulator starts outside a large warehouse building, facing one of its long walls, and high up on that wall a small rectangle is marked out with yellow-and-black hazard tape. Carry out a non-destructive-testing style inspection: bring the end effector to the fixed inspection point in front of the marked rectangle (see the goal geometry) and keep it there for 100 consecutive control steps (0.83 s).

## Scene
The ground is the world's z = 0 plane. The scene is NVIDIA's static sample warehouse (shelving racks, pallets, boxes, signs, a forklift and a posed worker figure, none of which moves). The robot hovers a short distance in front of the outer face of one of the building's long walls, which faces it squarely. That wall is a flat, solid panel surface from a few metres above the ground up to the roof; below it the building is open, so at the robot's height the warehouse interior, a pillar on either side and a few signs in the wall's plane are visible. Straight ahead of the robot and well above it, a marked region is taped onto the wall: a rectangle of yellow-and-black hazard-striped reflective tape 3 cm wide, 0.30 m tall and 0.22 m wide outside (0.24 x 0.16 m inside). The tape is visual only (no collision). Far off to the robot's right stands a separate concrete wall slab (0.1 x 2 x 2 m) that plays no part in the task. Nothing moves and nothing varies between instances. The robot starts hovering level and motionless, facing the warehouse wall, with its arm at its zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed.

**Goal geometry.** The inspection point is fixed, the same in every instance, and not itself marked in the scene: g = (1.77, 0.0, 7.0) m in world coordinates (z up; the robot starts with base_link at (0, 0, 1.0) facing +x). The success region for ee_link's origin is |x - 1.77| < 0.03 m and sqrt(y^2 + (z - 7.0)^2) < 0.08 m. It lies on the robot's side of the taped rectangle, opposite its centre, a little less than 20 cm from it.

## Success
With e the position of ee_link's origin (not the tool tip) and g = (1.77, 0.0, 7.0) m (goal_position; environment origin = world origin), a control step is 'in' when |e_x - g_x| < 0.03 m and sqrt((e_y - g_y)^2 + (e_z - g_z)^2) < 0.08 m. A counter increases by 1 at every 'in' step and is reset to 0 at every step that is not; success when it reaches 100 (success_hold_steps), i.e. at the 100th consecutive 'in' step (100/120 s, about 0.83 s). Orientation, velocity and contact are not tested. g is 0.192 m in front of the marker's origin, so with ee_link level and pointing at the wall the tool-tip point is about 2 cm short of the wall surface. AM-Bench reports inspection_target_held (the success itself) as its only criterion. Evaluated after every control step (decimation 1, so after every 1/120 s physics step) on the simulated state; the 100-step hold above is the only hold requirement. The episode terminates at the first step where it holds. Otherwise it is truncated by the time limit: episode_length_s = 20 s, i.e. max_episode_length = 2400 control steps; AM-Bench raises the time-out when episode_length_buf >= max_episode_length - 1, i.e. at the 2399th step.
The episode **ends by itself** at the first control step where the check holds (success), or when the task's episode
length of **20 s** of simulated time runs out (a failure: AM-Bench's time-out ends the episode at control step
2399; reason `episode_timeout`).

The goal is given as a fixed world point (goal geometry) and ee_link's pose is part of proprioception; the wall, the taped marker and anything in the way are seen only through the onboard cameras, and at the start the marker is far above their field of view (about 56 degrees). Success and the hold counter are not reported during the episode.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, at the time-out above, when your time
  is up, or on a simulator error. Whatever you knock over or push stays that way.
- **No privileged state.** You see what the two onboard cameras see (RGB, and depth if you ask) plus the robot's own
  proprioception (airframe pose and velocity, arm joints, gripper, tool-frame pose, joint efforts, the target in force).
  No object poses, no success signal.
- **Simulated time only moves when you move the robot** (`submit`, or `get_obs(seconds=...)`): between your calls the
  world is frozen, and the episode lasts at most 20 s of simulated time. There is no step budget otherwise:
  the time limit (`## Time limit`) is your only budget (`meta["time_left_s"]`).
- There is nothing to hand in: the service records your episode as the trajectory and grades it. Leave your script at
  `/app/output/gen.py` for the record. The episode is graded as it stands when your time is up.
- **If the service crashes**, a call fails with a connection error: the simulator restarts and resumes the SAME episode
  (never a reset) in the state after the last call it completed (to the last bits: a rare GPU race
  can leave those different), which you may not have received. `r.wait_ready()` waits
  until it answers again (resuming replays the episode so far, which can take minutes; the wall clock keeps running), then
  check `r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).
- **Nothing is put into your context automatically.** Images and videos come back as arrays/bytes in a Python object;
  what you look at and where you store it is your code's decision.

## Client (`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`)
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and builds the scene (see below)
spec = r.spec()                               # the action, cameras, proprio layout, budget, robot spec, kinematics

obs = r.get_obs()                             # current frames: obs.last[cam] -> uint8 (384, 384, 3), cam in ee_camera, base_camera
obs.meta["proprio"]                           # {"layout": [...45 names], "now": [...]}: joints, gripper, tool and airframe poses, ...
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl at the LAST frame
obs = r.get_obs(seconds=1.0, video="mp4")     # hold the current target and watch for 1 s (max 30; simulated time advances)

res = r.submit("ee_pose", A, dt=1/120, interpolate="hold")   # A: (T, 8) rows dt apart (see Action)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["ee_camera"]                        # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["base_camera"]                     # uint8 (N,H,W,3) at video_fps if requested
res.last["ee_camera"]; res.proprio            # last frame per camera; float32 (N, 45) proprio at each video frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy
```
The service's first start in a trial compiles Isaac's shaders: `Robot()` can wait ~2-12 min (it prints its progress to
stderr once a minute). It gives up after 3600 s (`Robot(timeout=...)`) with `RuntimeError("sim service unavailable ...")`:
then call it again (nothing has happened in the episode yet; your wall clock runs from the start of the trial).

Cameras (384×384 each, both moving with the robot): `ee_camera` (on the end effector, looking along the gripper) and
`base_camera` (on the airframe, looking forward). `res.extrinsic_cv[cam]` has their pose at every frame.

### Optional inputs (eai-standard/2.2; ask only for what you need)
- Depth: `r.get_obs(depth=True)` -> `obs.last_depth[cam]` float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned
  with `obs.last[cam]`; `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N,H,W), one map per frame (1 mm steps).
- Per frame: `res.frame_step` (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N,3,4 world -> camera, OpenCV
  axes). `spec["cameras"][cam]`: `intrinsic_cv` and `mount` (the parent link and a fixed `link_T_cam_cv`).
- `spec["robot_spec"]` (the arm's joints and limits, the gripper and its command, the controller, the tool frame),
  `spec["world"]` (frame, units, wxyz), `spec["proprio_groups"]` + `res.group("base_pose")` (joint_pos, joint_vel, tcp_pose,
  gripper_opening, gripper_cmd, joint_effort, base_pose, base_vel, ee_cmd).
- `r.fk(q4, base_pose=base7)` -> poses of `spec["kinematics"]["links"]` (in the airframe frame without `base_pose`, world
  with it); `r.ik({"tcp": pose7}, seed=q4, base_pose=base7)` -> `{"ok", "q", "error"}`: a stateless model of the arm on its
  airframe (no physics, no simulated time); `q4` = the arm's four joints. AM-Bench's own controller moves the airframe too
  (below): this model is the arm alone, for reasoning about reach and camera poses.

### Action
- `ee_pose` (8 per row): `x y z qw qx qy qz gripper` — AM-Bench's own action. The target pose of the tool frame `tcp`
  (the end-effector link, the frame of proprio `tcp_pose`; position in metres, world frame; orientation wxyz) and the
  gripper command (**-1 = closed .. +1 = open**). Every control step, AM-Bench's whole-body controller turns the target into
  an airframe pose (its floating-base inverse kinematics), the airframe pose into the six rotor thrusts (a PID) and the arm
  joints into targets for their drives: you command where the end effector should be, the airframe follows.
- Rows are `dt` apart (`1/120 ≤ dt ≤ 0.5` s, a multiple of the 120 Hz control period: 1/120, 2/120, ...; any other `dt` is
  rejected, never rounded); `interpolate="hold"` (each row exactly as given, for its dt) or `"linear"` (default: from the
  previous target, positions linear, orientation slerp, gripper linear); a chunk may cover at most 10 s; a gripper value
  outside [-1, 1] is clipped and listed in `meta["clipped"]`. Start from the target in force (`res.group("ee_cmd")`, or the
  proprio `tcp_pose`) to move smoothly: at the start the target is the end effector's own pose and the gripper is closed.
- A malformed request (a wrong type, a value out of range, a position more than 30 m from the origin, a zero quaternion) is
  answered 400 with the reason and executes nothing.
- Control and physics run at 120 Hz (simulated time; one physics step of 1/120 s per control step).

## Conventions
- World frame: metres, z up, the ground is the plane z = 0; positions relative to the environment's origin (the same frame
  for the action, the proprio poses, the camera extrinsics and `/kinematics` with `base_pose`); quaternions are **wxyz**.
- At the start the airframe hovers level, facing +x, with the arm at its zero joint configuration and the gripper closed.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **8 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
