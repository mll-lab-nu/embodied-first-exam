# AM-Bench · Cabinet Pick and Place — STANDARD MODE (robot as a service, eai-standard/2.2)

You control a simulated **aerial manipulator** **as if it were real hardware**: a fully actuated hexarotor (six tilted
rotors, so it can hold any attitude while hovering) carrying a small arm (four joints: three pitch joints and a roll joint)
with a two-finger gripper, in AM-Bench on Isaac Lab / Isaac Sim 5.1. The simulator runs in a service you cannot open. You
get one client and one episode. **Task:** A tall wooden cabinet stands ahead of the hovering aerial manipulator, and a small soda can stands inside one of its shelf compartments, behind a closed sliding door. Get the can onto the top of the cabinet: AM-Bench counts success when the can's centre is less than 5 cm above a fixed height just below the cabinet's top surface (there is no horizontal condition) while the can moves slower than 0.1 m/s.

## Scene
The ground is the world's z = 0 plane; there is no wall. Ahead of the robot stands an immovable cabinet with light-wood panels and metal handles, about 1.2 m wide, 0.6 m deep and 1.68 m tall, its front facing the robot and its top a flat board. From the bottom up: a solid base; a drawer with a horizontal bar handle; a compartment closed by two hinged doors with vertical handles, which are locked; the can's compartment, about 27 cm tall, whose right half (as seen from the robot) is closed by a fixed panel and whose left half is closed by a sliding door with a vertical bar handle; and a top compartment closed by a front panel with a horizontal bar handle. The sliding door slides sideways to the robot's right, in front of the fixed panel, over 0.6 m of travel; it has no spring (it stays where it is left) and its motion is resisted by damping and friction. The bottom drawer and the top front panel are not jointed: they are loose parts held in place only by gravity and contact. The can (4 cm in diameter, 6.4 cm tall, 5 g, with a soda label) stands upright on the floor of the sliding-door compartment, a little in from the front and hidden behind the closed sliding door; its exact spot varies by a few centimetres between instances, and nothing else varies. Nothing moves by itself. The robot starts hovering level and motionless, facing the cabinet, with its arm at its zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed.

## Success
Success at a control step when both hold: (1) the can's root position (its body origin, the can's centre) satisfies 0 <= z - 1.67 < 0.05 m (drawer_top_z = 1.67 m above the environment origin, which is the world origin; i.e. 1.67 <= z < 1.72 m); (2) the norm of the can's linear velocity is < 0.1 m/s (can_place_velocity_threshold). Nothing else is tested: no horizontal (x, y) condition, no orientation, the can need not be released, and the door's position does not matter. AM-Bench also reports subtask criteria pulling_door_opened (|pull_door_slide - 0| >= 0.2 m), can_lifted (can z > its z at reset + 0.05 m) and can_placed_on_drawer (the success itself); they are informational only. Evaluated after every control step (decimation 1, so after every 1/120 s physics step) on the simulated state; no hold time is required. The episode terminates at the first step where it holds. Otherwise it is truncated by the time limit: episode_length_s = 60 s, i.e. max_episode_length = 7200 control steps; AM-Bench raises the time-out when episode_length_buf >= max_episode_length - 1, i.e. at the 7199th step.
The episode **ends by itself** at the first control step where the check holds (success), or when the task's episode
length of **60 s** of simulated time runs out (a failure: AM-Bench's time-out ends the episode at control step
7199; reason `episode_timeout`).

Neither the cabinet's pose, the sliding door's position nor the can's pose is given: the cabinet, the door and its handle have to be found with the forward-looking onboard cameras, the can is hidden behind the closed door at the start, and whether the can ended at the right height and at rest can only be judged from the images together with proprioception. Success is not reported during the episode.

## Rules (real-robot rules)
- **No reset.** The episode starts when the service comes up and ends on success, at the time-out above, when your time
  is up, or on a simulator error. Whatever you knock over or push stays that way.
- **No privileged state.** You see what the two onboard cameras see (RGB, and depth if you ask) plus the robot's own
  proprioception (airframe pose and velocity, arm joints, gripper, tool-frame pose, joint efforts, the target in force).
  No object poses, no success signal.
- **Simulated time only moves when you move the robot** (`submit`, or `get_obs(seconds=...)`): between your calls the
  world is frozen, and the episode lasts at most 60 s of simulated time. There is no step budget otherwise:
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

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
