# IKEA MuJoCo · IKEA 365+ serving stand (standard)

## Task
Rebuild the IKEA 365+ serving stand: take the screw out of member A and set it down by itself, away from both members,
lay member B across member A, and screw the screw back in through both members until it seats. After that, lift the
stand about a hand's width off the bench, turn it upside down in the air, set it down and put the bowl on it. Then let
go of everything and move both arms clear.

## Goal
Success: these steps were done in that order, and at the end the screw is seated through both members, member B lies
across member A, and the stand is upside down on the bench with the bowl on it, standing firmly on its own; no arm
touches any part and everything is still. Forcing parts deep into each other breaks the simulation and ends the episode
at once, without success. When all of this holds, the service checks it once more after holding your last command for a
second more (on a copy: the robot does not move); if it still holds, the episode ends as a success, and if not, the
episode goes on and you can still fix it.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One episode, no reset: what you knock over stays knocked over.
- You get only the cameras and the robot's own sensor readings: no object poses, no scene layout; the episode ends when
  the task is done.

## Robot Interface
Two 7-DoF Franka Panda arms, each with the MuJoCo Menagerie Panda hand (two-finger, tendon-coupled), at a table
(RoboARC's IKEA furniture-assembly suite, MuJoCo). The robot runs as a service you reach only through its client, as if
it were real hardware: one live episode.

### Client
`/opt/tools/rcb_client.py` (already installed; `python` from any directory):
```python
from rcb_client import Robot
r = Robot()                                    # finds the service (sim:8000 / localhost:8000), waits until it is ready
spec = r.spec()                                # action layout and limits, cameras (intrinsics, mounts), proprio layout, world frame, budget
obs = r.get_obs()                              # current frames: obs.last[cam] -> uint8 (480, 848, 3)
obs = r.get_obs(depth=True)                    # + obs.last_depth[cam] -> float32 (480, 848) z-depth in metres (0 = no reading)
obs.meta["cameras"][cam]                       # intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl
obs.group("tcp_pose", now=True)                # proprio groups: joint_pos, joint_vel, gripper_opening, tcp_pose, joint_cmd, joint_effort
res = r.submit("joint_position", rows, dt=0.0025, interpolate="linear", cameras=["cam_high"], video="mp4")
res.meta["executed_rows"], res.meta["clipped"], res.meta["done"], res.meta["reason"], res.meta["time_left_s"]
res.video["cam_high"]                          # mp4 bytes of the chunk; video="frames" gives res.frames[cam] (N, H, W, 3)
obs = r.get_obs(seconds=2.0)                   # hold the last command, simulate 2 s and return the video (<= 30 s)
r.fk(q); r.ik({"left_tcp": [x, y, z, qw, qx, qy, qz]})   # stateless kinematics on the robot's model
r.status()                                     # calls, control steps, done, reason, time left
```

A connection error means the service crashed and is resuming the SAME episode: call `r.wait_ready()` and check
`r.status()` before you continue (`spec()["on_service_error"]`). One call returns at most 1000 images.

One control step takes about 5.5 ms of wall clock here (the simulation runs at about 0.46x real time), so a `submit` of
the maximum 10 s chunk takes about 22 s. The client waits long enough for any call; a client timeout or a connection
error means the connection or the service failed (above), not that the call is still on its way: do not resend it
blindly. `r.operation_status()` (the last call's operation, or `r.operation_status(operation_id)`) asks the service what
became of a call.

### Actions
- **Action** `joint_position`: rows of 16 values, float32 or float64, layout
  `spec()["action_types"]["joint_position"]["layout"]`: per arm (`left_`, then `right_`): `actuator1`..`actuator7` =
  joint position targets (rad; joint 7, the wrist, has no joint limit in these scenes, unlike the real Panda),
  `actuator8` = gripper command (0 = closed, 255 = open; the hand squeezes at its tendon force limit, about 70 N per
  finger, at any width when commanded 0). One control step is 2.5 ms (400 Hz: the row is applied for 4 physics steps of
  0.625 ms). `dt` must be a multiple of 0.0025 s (at most 0.5 s); `hold` keeps each row for its `dt`, `linear`
  interpolates the arm targets. A chunk covers at most 10 s. Out-of-range values are clipped to the actuator's control
  range and reported in `meta["clipped"]`. Speed rule (the robot's real limits; clamp, not fail): arm joint targets move
  at most 0.0054375 rad per control step on joints 1-4 (`actuator1`..`actuator4`: 2.175 rad/s) and 0.006525 rad on
  joints 5-7 (`actuator5`..`actuator7`: 2.61 rad/s), the Franka Panda's joint velocity limits
  (`spec()["robot_spec"]["controller"]`); a row that asks for more takes the control steps it needs, and
  `meta["clipped"]` says so. The gripper command is not limited: it switches at the row. The arms are position servos
  with the scene's gains and force limits; use `obs.group("joint_cmd", now=True)` as the starting row to move smoothly.

### Observations
- **Cameras** (ALOHA-style, 848 x 480, vertical field of view 58 deg): `cam_high` (static, above the front of the work
  area, looking down), `cam_low` (static, low at the front), `cam_left_wrist` and `cam_right_wrist` (on each hand,
  looking at the fingers; they move, so use the pose that comes with each frame). Intrinsics and mounts in
  `spec()["cameras"]`, the per-frame world -> camera pose in every response; depth on request.
- **Proprioception** (`spec()["proprio_layout"]`, groups in `spec()["proprio_groups"]`): per arm the 7 joint positions
  and velocities, the gripper opening (m), the tool-frame pose (`left_tcp` / `right_tcp` (between the fingertips): x y z
  + qw qx qy qz, world frame), the applied commands and the actuator forces.
- **World frame**: origin at the left arm's base link (`left_link0`) on its mounting, +z up, x along that arm's forward
  direction; metres, quaternions **WXYZ**. The proprio tool-frame poses, the camera extrinsics and mounts and
  `/kinematics` are all in it; no positions of the scene are given. `spec()["robot_spec"]["base"]` gives the right arm's
  base pose in it (the rig's fixed geometry).
- Not available (simulator privilege): part poses, positions of anything in the scene, the scene files, contact forces
  on parts, the success check itself.

### Grasping
- Grasps are physical: only the friction of the finger contacts holds a part; nothing attaches it to a gripper.

## Others
- The screw goes in only by being turned. Once it is seated, the screw and member B lock to member A where they are.

## Limits
- Time: 10800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
