# AM-Bench · ambench-peg-in-hole-fahexa-i00-resetinf (standard)

## Task
A simulated aerial manipulator: a fully actuated hexarotor (six tilted rotors, so it can hold any attitude while
hovering) carrying a small arm (four joints: three pitch joints and a roll joint) with a two-finger gripper, in AM-Bench
(Isaac Lab). The hovering aerial manipulator starts holding a metal peg (a cylinder 15 cm long and 4 cm in diameter) in
its gripper, pointing straight ahead. A wall stands ahead with a blue square socket mounted on its front face: a square
frame whose square opening faces the robot and is closed at the back by a red plate. Insert the peg into the opening.
The robot runs as a service you reach only through its client, as if it were real hardware.

### Scene
The ground is the world's z = 0 plane. In front of the robot stands an immovable (kinematic) wall: a slab 0.1 m thick,
2.0 m wide and 2.0 m tall with a concrete-block surface, its front face turned toward the robot. Its distance, its
sideways offset and its tilt (the top leaning toward or away from the robot by up to 30 degrees) vary between instances.
On the wall's front face sits an immovable socket: a blue plastic square frame 4 cm thick, mounted flat on the wall,
around a square opening perpendicular to the wall face; a red plate (1 cm thick, flush with the wall) closes the opening
3 cm behind the frame's front face. Nominally the frame's outer side is 10 cm and the opening 6 cm; both are scaled by
one factor between 0.75 and 1.5 (opening 4.5 to 9 cm square), the depth unchanged. Where the socket sits on the central
part of the wall varies between instances. The iron-coloured peg is a free rigid body (it falls if let go); at every
reset it is placed between the gripper's fingers, centred at the gripper's tool point with its axis along the tool's
forward axis, and the gripper is commanded closed, so the robot starts holding it. Nothing else moves by itself. The
robot starts hovering level and motionless, facing the wall, with its arm at its zero joint configuration (end effector
a little ahead of and above the airframe) and the gripper closed on the peg.

## Goal
Success: the peg's front end (the end that pointed ahead at the start) is pushed into the socket's square opening, most
of the way to the red plate at its back; whether the peg is still held does not matter. The episode ends by itself as
soon as the task is done (reason `success`), or as a failure when its 20 s of simulated time run out (reason
`episode_timeout`).

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
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

### This run: unlimited resets, save and load
This run changes the reset budget and adds two calls.

- You have 1000 resets (`spec()["budget"]["reset"]` is 1000): in practice as many as your time allows.
- `POST /reset` on the same base URL as your other calls (`http://sim:8000` or `http://localhost:8000`), with a JSON
  body such as `{"cameras": []}` (in Python, for example `requests.post(base + "/reset", json={"cameras": []})`; the
  client's `_post("/reset", {"cameras": []}, [], 60)` where it has no `reset()`). It abandons the running episode, or
  follows one that has ended (a failure or a fall included), and starts a new episode from the same starting state. The
  answer carries the new episode's first frames; `meta` and `GET /status` add `episode`, `resets_left`, `saves`, `loads`
  and `control_steps_total`.
- Where `/spec` has `state_ops`, two more calls exist (its text is the full rule):
  - `POST /save_state` with `{}` stores the current state in the service and answers JSON
    `{"handle": "s1", "step": ...}`. The handle is all you get, never the state's contents.
  - `POST /load_state` with `{"handle": "s1", "cameras": []}` restores a state saved earlier in this run and starts a
    new episode there; it answers as `/reset` does. At most 32 handles are kept (the least recently used one is
    dropped). Saves and loads do not use up resets. Where `/spec` has no `state_ops`, this task offers resets only.
- Your time keeps running across resets and loads (in standard-realtime the robot's clock pauses after a reset or a load
  until your next command).
- Only the last episode is graded: from the starting state, or for a loaded episode the path that led to the saved state
  followed by what you did after the load. The success rule is checked again from your next command on. A success still
  ends the run: no reset, save or load after it.

## Others
- The socket's pose, the wall's tilt and the opening's size are not given, nor is the peg's pose (it can shift in the
  grip): the blue socket on the concrete wall has to be found with the onboard cameras (the held peg occupies part of
  the end-effector camera's view) and related to the robot through proprioception (base and end-effector poses).
  Insertion depth can only be judged visually.

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
- Resets: at most 1000 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
