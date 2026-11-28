# AM-Bench · ambench-open-door-fahexa-i00 (standard)

## Task
Push the door open, away from you, about a quarter of the way or more.

## Goal
Success: the door is pushed open, away from the robot, about a quarter of the way or more.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout, no success signal.
- Simulated time moves only while the robot runs your commands or holds still (`hold(s)`): between your calls the world
  is frozen.

## Robot Interface
A simulated aerial manipulator in AM-Bench (Isaac Lab). It is a fully actuated hexarotor: six tilted rotors let it hold
any attitude while hovering. It carries a small arm with four joints (three pitch joints and a roll joint) and a
two-finger gripper. The robot runs as a service you reach through its client or its MCP tools, as if it were real
hardware: one live episode.

`POST /finish` (client `r.finish()`, MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py` (protocol `eai-standard/3.0`):
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and builds the scene (see below)
spec = r.spec()                               # the action, cameras, proprio layout, budget, robot spec, kinematics

obs = r.get_obs()                             # current frames: obs.last[cam] -> uint8 (384, 384, 3), cam in ee_camera, base_camera
obs.meta["proprio"]                           # {"layout": [...45 names], "now": [...]}: joints, gripper, tool and airframe poses, ...
obs.meta["cameras"]                           # per-camera intrinsic_cv / extrinsic_cv / cam2world_gl at the LAST frame
obs = r.hold(1.0)                             # hold the current target for 1 s of robot time (simulated time advances)
obs = r.get_obs(last_s=1.0)                   # the frames recorded over the last 1 s (reading moves no time)

res = r.submit("ee_pose", A, dt=1/120, interpolate="hold")   # A: (T, 8) rows dt apart (see Action)
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_chunk"]
res.video["ee_camera"]                        # mp4 bytes of the execution (video="mp4" | "frames" | "both" | "none")
res.frames["base_camera"]                     # uint8 (N,H,W,3) at video_fps if requested
res.last["ee_camera"]; res.proprio            # last frame per camera; float32 (N, 45) proprio at each video frame
res.save("/app/runs/003")                     # meta.json, <cam>.mp4, frames/<cam>/NNN.jpg, last/<cam>.jpg, proprio.npy
```

The service's first start in a trial compiles Isaac's shaders: `Robot()` can wait ~2-12 min (it prints its progress to
stderr once a minute). After 3600 s (`Robot(timeout=...)`) it gives up with
`RuntimeError("sim service unavailable ...")`. Then call it again: nothing has happened in the episode yet. Your wall
clock runs from the start of the trial.

If the service crashes, a call fails with a connection error. The simulator restarts and resumes the SAME episode (never
a reset), in the state after the last call it completed. You may not have received that call's reply. `r.wait_ready()`
waits until it answers again. Resuming replays the episode so far and can take minutes; the wall clock keeps running.
Then check `r.status()["control_steps"]` before you continue (`spec["on_service_error"]`).

Simulated time moves only in `submit` and in `hold(s)` (the robot holds its current target for s seconds). One call
returns at most 3000 images.

Optional inputs (ask only for what you need):
- Depth: `r.get_obs(depth=True)` -> `obs.last_depth[cam]` float32 (H,W) z-depth in metres, 0 = no reading, pixel-aligned
  with `obs.last[cam]`; `r.submit(..., depth="frames")` -> also `res.depth[cam]` (N,H,W), one map per frame (1 mm
  steps).
- Per frame: `res.frame_step` (control step), `res.frame_time_s`, `res.extrinsic_cv[cam]` (N,3,4 world -> camera, OpenCV
  axes). `spec["cameras"][cam]`: `intrinsic_cv` and `mount` (the parent link and a fixed `link_T_cam_cv`).
- `spec["robot_spec"]` (the arm's joints and limits, the gripper and its command, the controller, the tool frame),
  `spec["world"]` (frame, units, wxyz), `spec["proprio_groups"]` + `res.group("base_pose")` (joint_pos, joint_vel,
  tcp_pose, gripper_opening, gripper_cmd, joint_effort, base_pose, base_vel, ee_cmd).
- `r.fk(q4, base_pose=base7)` -> poses of `spec["kinematics"]["links"]`, in the airframe frame without `base_pose` and
  in the world frame with it. `r.ik({"tcp": pose7}, seed=q4, base_pose=base7)` -> `{"ok", "q", "error"}`. Both use a
  stateless model of the arm on its airframe (no physics, no simulated time); `q4` = the arm's four joints. AM-Bench's
  own controller moves the airframe too (below): this model is the arm alone, for reasoning about reach and camera
  poses.

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `kinematics`, `finish`. A tool takes its endpoint's request fields (any other field in `fields`)
  and returns the service's reply `meta` unchanged; images, arrays and video are written as files under `/app/obs/`
  (`.png`, `.npy`, `.mp4`) and the result lists them. Long action chunks can be passed as a file (`actions_file`).
- `observe` returns at once with what is already recorded: the current frame, or the last `last_s` seconds. Time passes
  only through `submit`, which answers when its rows have run; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets time pass with the robot holding still.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client and the tools drive the same robot in the same episode; use either, or both.

### Actions
- World frame: metres, z up, the ground is the plane z = 0. Positions are relative to the environment's origin; the
  action, the proprio poses, the camera extrinsics and `r.fk` with `base_pose` all use this frame. Quaternions are wxyz.
- At the start the airframe hovers level, facing +x, with the arm at its zero joint configuration and the gripper
  closed.
- `ee_pose` (8 per row): `x y z qw qx qy qz gripper` — AM-Bench's own action. The target pose of the tool frame `tcp`,
  and the gripper command (-1 = closed .. +1 = open). `tcp` is the end-effector link, the frame of proprio `tcp_pose`;
  its position is in metres in the world frame, its orientation wxyz. Every control step, AM-Bench's whole-body
  controller turns the target into an airframe pose (its floating-base inverse kinematics). A PID turns the airframe
  pose into the six rotor thrusts, and the arm joints become targets for their drives. You command where the end
  effector should be; the airframe follows.
- Rows are `dt` apart. `dt` must be a multiple of the 120 Hz control period (1/120, 2/120, ...) with `1/120 ≤ dt ≤ 0.5`
  s; any other `dt` is rejected, never rounded. With `interpolate="hold"` each row is used exactly as given, for its dt;
  with `"linear"` (default) the target moves from the previous one: positions linear, orientation slerp, gripper linear.
  A chunk may cover at most 10 s. A gripper value outside [-1, 1] is clipped and listed in `meta["clipped"]`. To move
  smoothly, start from the current target (`res.group("ee_cmd")`, or the proprio `tcp_pose`). At the start, the target
  is the end effector's own pose and the gripper is closed.
- A malformed request (a wrong type, a value out of range, a position more than 30 m from the origin, a zero quaternion)
  is answered 400 with the reason and executes nothing.
- Control and physics run at 120 Hz (simulated time; one physics step of 1/120 s per control step).

### Observations
- Cameras (384×384 each, both moving with the robot): `ee_camera` (on the end effector, looking along the gripper) and
  `base_camera` (on the airframe, looking forward); their intrinsics and mounts are in the spec's `cameras`, their pose
  at every frame comes with each reply.
- Depth (`depth=True`): z-depth in metres, 0 = no reading, pixel-aligned with the colour image, in 1 mm steps.
- Proprioception: 45 values a row (their `layout` comes with them). They are the arm's joint positions, velocities and
  efforts, the gripper's opening and command, the tool frame's pose (`tcp_pose`), the airframe's pose and velocity
  (`base_pose`, `base_vel`) and the current end-effector target (`ee_cmd`). The groups are in the spec's
  `proprio_groups`.

### Episode
One episode lasts 15 s of simulated time.

## Others
- The door's handle and lock plate are for show: the robot's fingers pass through them.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`).
  Trust this file: the `time_left_s` in the service's replies starts only at your first request. A call into a
  long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none. You get one episode.
- Steps: at most 15 s of simulated time, then the episode ends.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
