# AM-Bench · ambench-lemon-harvesting-fahexa-i00 (standard)

## Task
A simulated aerial manipulator: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude while
hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in AM-Bench
(Isaac Lab). One lemon and six limes are fixed to the front face of a wall in front of the hovering aerial manipulator,
and a grey storage tote sits on a small table against the wall to the robot's left. Harvest the lemon: free it from the
wall and get it into the tote. The robot runs as a service you reach only through its client, as if it were real
hardware: one live episode.

### Scene
The ground is the world's z = 0 plane. In front of the robot stands an immovable (kinematic) wall: a slab 0.1 m thick,
2.0 m wide and 2.0 m tall with a concrete-block surface, its front face turned toward the robot. The wall is the same in
every instance. Seven fruits sit on its front face, each with its long axis pointing at the robot: one yellow lemon
(about 7.6 x 5 x 5 cm, 50 g) and six green limes (about 7.6 x 6 x 6 cm). The limes are fixed in place and cannot be
moved. The lemon is a free rigid body held to the wall by a breakable fixed joint: it stays put until the joint has to
carry more than 10 N of force or 10 N m of torque, after which it is loose and falls under gravity. Where the fruits sit
varies between instances: anywhere in a band 1 m wide and 0.4 m tall, centred sideways on the wall in its upper half, at
least 15 cm apart. To the robot's left, against the wall, stands a small table (white top, about 0.45 x 0.48 m and 0.66
m tall) carrying an open-top grey plastic tote, 40 x 30 x 17 cm; table and tote are immovable and the same in every
instance. Nothing moves by itself. The robot starts hovering level and motionless, facing the wall, with its arm at its
zero joint configuration (end effector a little ahead of and above the airframe) and the gripper closed.

## Goal
Success: the lemon, pulled free of the wall, is in the tote and the gripper is fully open (it has let go of the lemon).
The episode ends by itself as soon as the task is done (reason `success`), or as a failure when its 30 s of simulated
time run out (reason `episode_timeout`).

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Simulated time moves only while the robot runs your commands or you watch it hold still: between your calls the world
  is frozen.

## Robot Interface
### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/2.2`):
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
stderr once a minute). It gives up after 3600 s (`Robot(timeout=...)`) with
`RuntimeError("sim service unavailable ...")`: then call it again (nothing has happened in the episode yet; your wall
clock runs from the start of the trial).

If the service crashes, a call fails with a connection error: the simulator restarts and resumes the SAME episode (never
a reset) in the state after the last call it completed, which you may not have received. `r.wait_ready()` waits until it
answers again (resuming replays the episode so far, which can take minutes; the wall clock keeps running), then check
`r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).

Simulated time moves only in `submit` and in `get_obs(seconds=s)` (the robot holds its current target while you watch,
at most 30 s). One call returns at most 3000 images.

Optional inputs (ask only for what you need):
- Depth: `r.get_obs(depth=True)` -> `obs.last_depth[cam]` float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned
  with `obs.last[cam]`; `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N,H,W), one map per frame (1 mm
  steps).
- Per frame: `res.frame_step` (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N,3,4 world -> camera, OpenCV
  axes). `spec["cameras"][cam]`: `intrinsic_cv` and `mount` (the parent link and a fixed `link_T_cam_cv`).
- `spec["robot_spec"]` (the arm's joints and limits, the gripper and its command, the controller, the tool frame),
  `spec["world"]` (frame, units, wxyz), `spec["proprio_groups"]` + `res.group("base_pose")` (joint_pos, joint_vel,
  tcp_pose, gripper_opening, gripper_cmd, joint_effort, base_pose, base_vel, ee_cmd).
- `r.fk(q4, base_pose=base7)` -> poses of `spec["kinematics"]["links"]` (in the airframe frame without `base_pose`,
  world with it); `r.ik({"tcp": pose7}, seed=q4, base_pose=base7)` -> `{"ok", "q", "error"}`: a stateless model of the
  arm on its airframe (no physics, no simulated time); `q4` = the arm's four joints. AM-Bench's own controller moves the
  airframe too (below): this model is the arm alone, for reasoning about reach and camera poses.

### Actions
- World frame: metres, z up, the ground is the plane z = 0; positions relative to the environment's origin (the same
  frame for the action, the proprio poses, the camera extrinsics and `r.fk` with `base_pose`); quaternions are wxyz.
- At the start the airframe hovers level, facing +x, with the arm at its zero joint configuration and the gripper
  closed.
- `ee_pose` (8 per row): `x y z qw qx qy qz gripper` — AM-Bench's own action. The target pose of the tool frame `tcp`
  (the end-effector link, the frame of proprio `tcp_pose`; position in metres, world frame; orientation wxyz) and the
  gripper command (-1 = closed .. +1 = open). Every control step, AM-Bench's whole-body controller turns the target into
  an airframe pose (its floating-base inverse kinematics), the airframe pose into the six rotor thrusts (a PID) and the
  arm joints into targets for their drives: you command where the end effector should be, the airframe follows.
- Rows are `dt` apart (`1/120 ≤ dt ≤ 0.5` s, a multiple of the 120 Hz control period: 1/120, 2/120, ...; any other `dt`
  is rejected, never rounded); `interpolate="hold"` (each row exactly as given, for its dt) or `"linear"` (default: from
  the previous target, positions linear, orientation slerp, gripper linear); a chunk may cover at most 10 s; a gripper
  value outside [-1, 1] is clipped and listed in `meta["clipped"]`. Start from the target in force
  (`res.group("ee_cmd")`, or the proprio `tcp_pose`) to move smoothly: at the start the target is the end effector's own
  pose and the gripper is closed.
- A malformed request (a wrong type, a value out of range, a position more than 30 m from the origin, a zero quaternion)
  is answered 400 with the reason and executes nothing.
- Control and physics run at 120 Hz (simulated time; one physics step of 1/120 s per control step).

### Observations
- Cameras (384×384 each, both moving with the robot): `ee_camera` (on the end effector, looking along the gripper) and
  `base_camera` (on the airframe, looking forward); their intrinsics and mounts are in the spec's `cameras`, their pose
  at every frame comes with each reply.
- Depth (`depth=True`): z-depth in metres, 0 = no reading, pixel-aligned with the colour image, in 1 mm steps.
- Proprioception: 45 values a row (their `layout` comes with them): the arm's joint positions, velocities and efforts,
  the gripper's opening and command, the tool frame's pose (`tcp_pose`), the airframe's pose and velocity (`base_pose`,
  `base_vel`) and the end-effector target in force (`ee_cmd`); the groups are in the spec's `proprio_groups`.

## Others
- The fruits' positions, which fruit is the lemon, the tote's and table's poses and whether the lemon is still attached
  are not given: the yellow lemon has to be told from the green limes and located on the concrete wall with the onboard
  cameras, and the tote found on the table. The gripper width comes from proprioception; whether the lemon is in the
  tote can only be judged visually.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
