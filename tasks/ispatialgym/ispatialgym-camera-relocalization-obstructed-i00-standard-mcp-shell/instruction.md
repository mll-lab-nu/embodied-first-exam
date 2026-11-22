# iSpatialGym · make the scene look like a picture (standard-mcp-shell)

## Task
An R1Pro mobile robot with two arms, in a simulated house (iSpatialGym on BEHAVIOR-1K's OmniGibson). `/app/goal.png` is
what the robot's head camera (`robot_r1:zed_link:Camera:0`) sees once the task is done. It is the same camera,
resolution and intrinsics as the robot's own head camera. Change the scene so that it looks like the picture. No
sentence here names the objects that matter or what to do with them: the picture is the whole task. The robot runs as a
service you reach through the `efe-robot` MCP tools, their Python client `efe_robot` or the service's own client, as if
it were real hardware: one live episode.

## Goal
Success: the head camera sees the scene from where the picture was taken: it stands at roughly the picture's viewpoint
and looks roughly the same way, and the objects the task is about stand in the relations the picture shows (what is on,
in, under, next to or touching what, what is open, which objects the robot holds or has let go of). The robot does not
have to match the picture (its arms, grippers and base may be anywhere), and nothing the picture does not show is
judged.

Once the scene looks right, stop the robot and keep it and the objects still for at least 45 control steps (1.5 s of
simulated time): that is part of success, and the episode ends as soon as it holds.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no map, no world frame; the episode ends when the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is under the robot's base_link at the height of its starting pose (about floor level): +X the way the
base faces, +Y to the robot's left, +Z up; it moves with the base; metres, radians, quaternions `wxyz`, gripper 0 open
.. 1 closed. Parts: left (arm: 7 joints, end-effector pose, gripper); right (arm: 7 joints, end-effector pose, gripper);
torso (torso: 4 joints, no end-effector pose); base (mobile: dx, dy, dyaw). Cameras: `robot_r1:zed_link:Camera:0`,
`robot_r1:left_realsense_link:Camera:0`, `robot_r1:right_realsense_link:Camera:0`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}` (the base: `{target: "base", dx, dy, dyaw}`); the
  parts move together and the call returns when the motion is done, with `reached` (the error per goal), a `failure`
  category if a goal was not reached, the state and a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: The goal picture is /app/goal.png: the head camera's view (robot_r1:zed_link:Camera:0, same resolution and
intrinsics) once the task is done. Simulated time passes only while the robot moves or you wait, and the episode has a
fixed number of control steps (30 per simulated second; control_steps_left in every result): give short motions a short
duration_s. Success needs the scene and the robot still for 45 control steps: after the last motion, wait at least 1.5
s. End-effector poses (goals and state) are the fingertip centre (TCP), midway between the two fingertips, about 2 cm
further along the fingers than the end-effector frame between the finger pads, where a grasped object is held (the
proprio eef_pose group). An end-effector goal is solved by the robot's inverse kinematics from the current joints and
moves only that arm, in joint space, without collision checking. Grasping is assisted: closing on an object holds what
the finger pads touch, and the hand lets go only when fully open (gripper 0). The reported gripper value is 1 while the
measured opening is below 9 cm (closed, or holding an object) and 0 when fully open; gripper_opening_m is the measured
opening. The cameras give RGB only (no depth). The simulator runs at about 8 control steps per second of wall time.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                   # connects: waits while Isaac Sim starts and loads the scene
                                              # (5-6 min; the first start in a container is the slowest)
spec = r.spec()                               # actions, cameras, robot_spec, world, kinematics, budget

obs = r.get_obs()                             # the current head-camera frame: obs.last[cam] -> uint8 (1080, 1080, 3)
obs = r.get_obs(cameras=[...])                # any of the three cameras (spec["cameras"])
obs.meta["proprio"]                           # {"layout": [...], "now": [...]}: named columns (spec["proprio_groups"])
obs.meta["cameras"]                           # per camera: intrinsic_cv / extrinsic_cv (odometry -> camera) of the LAST frame
obs = r.get_obs(seconds=2.0, video="mp4")     # hold the last command and watch for 2 s (max 30): obs.video[cam] = mp4 bytes

res = r.submit("joint_position", A, dt=0.1)   # A: (T, 23) rows dt seconds apart; streamed at 30 Hz
res.meta["done"], res.meta["reason"], res.meta["clipped"], res.meta["control_steps_left"]
res.video[cam]; res.frames[cam]; res.last[cam]; res.proprio   # execution video / frames / last frame per camera, proprio per frame
```
One call returns at most 300 images. A malformed request is refused with a 400 and nothing is executed (a wrong type or
shape, a value out of range, a `dt` that is not a whole number of control periods, `video_fps` outside 1-30, a call over
the image limit): fix it and send it again. If the service crashes (a connection error or a 5xx answer), it restarts and
resumes the SAME episode (never a reset) in the state after the last call it completed, which you may not have received:
call `r.wait_ready()`, then check `r.status()` (`calls`, `control_steps`) before you continue. The simulator runs at
about 13 control steps per second of wall time.

- Per frame: `res.frame_step`, `res.frame_time_s` and `res.extrinsic_cv[cam]` (N, 3, 4; odometry -> camera, OpenCV
  axes). Intrinsics `spec["cameras"][cam]["intrinsic_cv"]` (the goal image's are the head camera's), mounting
  `spec["cameras"][cam]["mount"]` (parent link + fixed `link_T_cam_cv`).
- Proprioception: named columns `spec["proprio_layout"]`, groups `spec["proprio_groups"]` (joint_pos, joint_vel,
  joint_effort, gripper_opening, tcp_pose, eef_pose, base_pose, base_twist): `res.group("tcp_pose")` per frame,
  `res.group("tcp_pose", now=True)` now.
- Robot: `spec["robot_spec"]`: joint names and limits, the gripper rule, the end-effector frame and the fingertip centre
  (TCP), the base command.
- Kinematics (stateless: no physics, no time): `r.fk(q)`, `r.ik({"left_tcp": pose}, seed=q)`; q =
  `spec["kinematics"]["joint_names"]` (trunk + both arms); poses in the robot's base frame, or in the odometry frame
  with `base_pose=` the 7 base_pose proprio columns.

### Actions
Blocks (`spec["action_types"]["joint_position"]["blocks"]`): base (3), trunk (4), left arm (7), left gripper (1), right
arm (7), right gripper (1). Rows are `dt` apart (`1/30 ≤ dt ≤ 0.5` s, a multiple of the 30 Hz control period: `k/30` s;
any other `dt` is a 400); a chunk covers at most 10 s; out-of-limit values are clipped and listed in `meta["clipped"]`.
- Base: a velocity command in [-1, 1] in the robot's own frame (forward, left, yaw rate), scaled to 0.75 m/s, 0.75 m/s
  and 1 rad/s; it switches at the row and holds until the next one; zeros stop.
- Trunk and arms: absolute joint targets (rad), linearly interpolated between rows (or held, `interpolate="hold"`).
- Grippers: one command each in [-1, 1]: -1 closed, 1 fully open, in between the fingers' target as a fraction of their
  travel; it switches at the row. Grasping is assisted: closing on an object holds what the finger pads touch, and the
  hand lets go only at 1.

### Observations
- Cameras: `robot_r1:zed_link:Camera:0` (head: the goal image's camera; it moves with the base and the trunk),
  `robot_r1:left_realsense_link:Camera:0` and `robot_r1:right_realsense_link:Camera:0` (wrists), 1080×1080 RGB each, no
  depth. They all move, so always use the calibration that arrived with the image. While the robot moves, a frame shows
  the scene 2 control steps (67 ms) before the step it is reported at; the camera pose that comes with it is the one it
  was rendered with.
- Proprioception: the robot's joints, base pose and velocity, end-effector and fingertip poses and gripper openings.
  Every pose is in the odometry frame: the robot's `base_link` at the start of the episode (x forward, y left, z up).
  Mind the joint order: the joint columns follow the robot spec's joint list (the trunk, then the two arms interleaved:
  left joint 1, right joint 1, left joint 2, ...), while the action's arm blocks (and the kinematics' `q`) are grouped
  (left arm joints 1-7, then right arm joints 1-7); map by name.

## Others
- Simulated time passes only while you submit rows or watch. To hold still, first send a row with the base command at 0
  (the base keeps its last command until the next row), then submit rows that hold still, or watch with
  `r.get_obs(seconds=...)`, which holds the last command.

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
- Resources: 8 CPUs, 5 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 1324 control steps (44.1 s of simulated time): they are the whole episode, which ends when they run out
  ("failed: the episode's control steps ran out") or on a simulator error; look and plan before you spend them.
