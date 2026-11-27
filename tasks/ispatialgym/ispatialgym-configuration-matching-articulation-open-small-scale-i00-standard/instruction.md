# iSpatialGym · make the scene look like a picture (standard)

## Task
Make the scene look like the goal image /app/goal.png, the head camera's view once the task is done; the robot itself
does not have to match it.

## Goal
Success: the objects that matter stand as the picture shows them (what is on, in, under, next to or touching what, what
is open, what the robot holds and what it has let go of); one object stands roughly where the picture shows it, turned
roughly as there, with its moving part opened about as far as in the picture; then the robot and those objects stay
still for at least a second and a half.

When you are done, send `/finish` to end the episode and get it graded. Only the state at that point counts.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no map, no world frame, no success
  signal.

## Robot Interface
An R1Pro mobile robot with two arms, in a simulated house (iSpatialGym on BEHAVIOR-1K's OmniGibson). The robot runs as a
service you reach through its client or its MCP tools, as if it were real hardware: one live episode.

`POST /finish` (MCP tool `finish`): ends the episode; it is graded right away.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and loads the scene
                                              # (7 min; the first start in a container is the slowest)
spec = r.spec()                               # actions, cameras, robot_spec, world, kinematics, budget

obs = r.get_obs()                             # the current head-camera frame: obs.last[cam] -> uint8 (1080, 1080, 3)
obs = r.get_obs(cameras=[...])                # any of the three cameras (spec["cameras"])
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: named columns (spec["proprio_groups"])
obs.meta["cameras"]                           # per camera: intrinsic_cv / extrinsic_cv (odometry -> camera) of the LAST frame
obs = r.hold(2.0)                             # hold the last command for 2 s of robot time: obs.video[cam] = mp4 bytes
obs = r.get_obs(last_s=1.0)                   # the frames recorded over the last 1 s (reading moves no time)

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 23) rows dt seconds apart; streamed at 30 Hz
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_left"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio   # execution video / frames / last frame per camera, proprio per frame
```
One call returns at most 300 images. A malformed request is refused with a 400 and nothing is executed (a wrong type or
shape, a value out of range, a `dt` that is not a whole number of control periods, `video_fps` outside 1-30, a call over
the image limit): fix it and send it again. If the service crashes (a connection error or a 5xx answer), it restarts and
resumes the SAME episode; it never resets. It resumes in the state after the last call it completed, and you may not
have received that call's answer. Call `r.wait_ready()`, then check `r.status()` (`calls`, `control_steps`) before you
continue. The simulator runs at about 8 control steps per second of wall time.

- Per frame: `res.frame_step`, `res.frame_time_s` and `res.extrinsic_cv[cam]` (N, 3, 4; odometry -> camera, OpenCV
  axes). Intrinsics `spec["cameras"][cam]["intrinsic_cv"]` (the goal image's are the head camera's), mounting
  `spec["cameras"][cam]["mount"]` (parent link + fixed `link_T_cam_cv`).
- Proprioception: named columns `spec["proprio_layout"]`, groups `spec["proprio_groups"]` (joint_pos, joint_vel,
  joint_effort, gripper_opening, tcp_pose, eef_pose, base_pose, base_twist): `res.group("tcp_pose")` per frame,
  `res.group("tcp_pose", now=True)` now.
- Robot: `spec["robot_spec"]`: joint names and limits, the gripper rule, the end-effector frame and the fingertip centre
  (TCP), the base command.
- Kinematics (stateless: no physics, no time): `r.fk(q)` and `r.ik({"left_tcp": pose}, seed=q)`. q follows
  `spec["kinematics"]["joint_names"]` (trunk + both arms). Poses are in the robot's base frame, or in the odometry frame
  if you pass `base_pose=` the 7 base_pose proprio columns.

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
Blocks (`spec["action_types"]["joint_position"]["blocks"]`): base (3), trunk (4), left arm (7), left gripper (1), right
arm (7), right gripper (1). Rows are `dt` apart. `dt` must be a multiple of the 30 Hz control period (`k/30` s) with
`1/30 ≤ dt ≤ 0.5` s; any other `dt` is a 400. A chunk covers at most 10 s. Out-of-limit values are clipped and listed in
`meta["clipped"]`.
- Base: a velocity command in [-1, 1] in the robot's own frame (forward, left, yaw rate), scaled to 0.75 m/s, 0.75 m/s
  and 1 rad/s. It changes at once at the start of its row and holds until the next row; zeros stop the base.
- Trunk and arms: absolute joint targets (rad), linearly interpolated between rows (or held, `interpolate="hold"`).
- Grippers: one command each in [-1, 1]: -1 closed, 1 fully open, and values in between set the fingers' target as a
  fraction of their travel. It changes at once at the start of its row. Grasping is assisted: closing on an object holds
  what the finger pads touch, and the hand lets go only at 1.

### Observations
- Cameras: `robot_r1:zed_link:Camera:0` (head: the goal image's camera; it moves with the base and the trunk),
  `robot_r1:left_realsense_link:Camera:0` and `robot_r1:right_realsense_link:Camera:0` (wrists), 1080×1080 RGB each, no
  depth. They all move, so always use the calibration that arrived with the image. While the robot moves, a frame shows
  the scene as it was 2 control steps (67 ms) before the step it is reported at. The camera pose that comes with a frame
  is the pose it was rendered with.
- Proprioception: the robot's joints, base pose and velocity, end-effector and fingertip poses and gripper openings.
  Every pose is in the odometry frame: the robot's `base_link` at the start of the episode (x forward, y left, z up).
  Mind the joint order. The joint columns follow the robot spec's joint list: the trunk, then the two arms interleaved
  (left joint 1, right joint 1, left joint 2, ...). The action's arm blocks and the kinematics' `q` are grouped instead:
  left arm joints 1-7, then right arm joints 1-7. Map by name.

### Holding still
Simulated time passes only while you submit rows or hold (`r.hold(s)`). To hold still, first send a row with the base
command at 0, because the base keeps its last command until the next row. Then submit rows that hold still, or call
`r.hold(s)`, which holds the last command.

### Goal image
`/app/goal.png` is what the robot's head camera (`robot_r1:zed_link:Camera:0`) sees once the task is done. It is the
same camera, resolution and intrinsics as the robot's own head camera.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning. Time left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the
  service's `time_left_s` (in every reply) starts at your first request, so the file is the one to trust. Calls into a
  long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 8 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 2382 control steps (79.4 s of simulated time), then the episode ends. Look and plan before you spend
  them.
- Finish: if you never send `/finish`, the episode is graded when the step limit is reached or your session ends.
