# MuJoCo Playground · Go1JoystickFlatTerrain (standard-mcp-shell)

## Task
The Unitree Go1 quadruped (MuJoCo Playground's scene, in MuJoCo), driven by 12 joint position actuators: there is no
walking or balance controller. It starts at its `home` pose, its base moved to (-0.493, -0.479) m and turned to a yaw of
-142.4 deg, with a random base velocity. The ground is flat. Make it follow the joystick's command schedule for the
whole 20 s episode without falling over. The robot runs as a service you reach through the `efe-robot` MCP tools, their
Python client `efe_robot` or the service's own client, as if it were real hardware.

## Goal
Success: for the whole schedule the robot never falls, and in every command's stretch, after a short settling time at
its start, its velocity over the ground (in its own frame) and its turning rate follow the command closely on average.
The episode lasts the whole schedule (20 s, 1000 control steps); a fall (the trunk tipping over) ends it at once, as a
failure, and so does ending it yourself (`done`) or running out of time before the schedule's end.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- Episodes: 10 resets, each a new episode from the same starting state (Robot Interface). Only the last episode is
  graded: a success ends the run at once (no reset after it), and when your time is up the episode then running is
  graded.
- No privileged state: you get the camera images (with their calibration) and the robot's own sensors (joint positions,
  velocities and torques, the IMU, foot contacts); no world positions; when the episode ends, the service tells you that
  it ended and why.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__move_robot`), also as Python functions:
`import efe_robot` (`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result,
its docstring the tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell.
They and the service's client (`### Client`) all drive the one robot. Their conventions (all but space `native`): the
robot base frame is the simulator's world frame (z up), not the trunk: the service reports no trunk pose, so camera
poses are given in this frame; no part here takes an end-effector pose; metres, radians, quaternions `wxyz`, gripper 0
open .. 1 closed. Parts: legs (legs: 12 joints, no end-effector pose). Cameras: `track`, `side`, `back`, `top`.

- `describe_robot()`: call it first: parts and limits, cameras, control period, action types, the time left; the full
  spec as a JSON file (`spec_file`).
- `observe(cameras?, depth?, seconds?, inline_cameras?)`: JPEG images under `/app/obs/` (depth `.npy`, float32 metres;
  with `seconds` > 0 an `.mp4` too, the robot held still meanwhile); the result has their paths, each camera's `K` and
  pose in the base frame, each part's joints, gripper and end-effector pose, and `proprio_now` (the robot's own
  proprioception row; its layout is in the spec file).
- `locate(camera, u, v | pixels, window_px?)`: the 3-D point in the base frame a depth camera sees at pixel (u, v) of
  its full-size image (u the column, v the row); no time passes.
- `move_robot(goals, duration_s?)`: one goal per part,
  `{target, position?, quaternion_wxyz?, joint_positions?, gripper?}`; the parts move together and the call returns when
  the motion is done, with `reached` (the error per goal), a `failure` category if a goal was not reached, the state and
  a frame per camera.
- `execute_trajectory(space, rows | native_rows | rows_file, dt?, interpolate?)`: dense rows `dt` seconds apart; long
  arrays as `rows_file`, a file under `/app` (`.npy` or `.csv` of native rows for space `native` with `action_type`, or
  a `.json` list).
- `wait(seconds?, operation?)`: let time pass holding the current command, or collect a pending call.
- `reset_episode()`: a new episode from the same starting state (one reset of the budget).
- `signal(kind, note)`: `done` records that you are finished (the episode itself ends as Goal says).
- One call at a time (the Python functions wait for a pending call themselves). A call still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`. `"episode_over": true` means the episode
  has ended.

This robot: There is no walking or balance controller: every gait, turn and pose comes from the 12 joint targets you
send, one row per control step (0.02 s). The joint targets are absolute angles in radians, in the same order as proprio
group joint_pos; the state also has joint velocities and torques, the IMU (gyro, accelerometer, gravity direction, the
trunk's velocity) and foot contacts (proprio_now, layout in describe_robot's spec_file: proprio_layout, proprio_groups).
spec_file also has the home pose, the joint limits, the command schedule where the task has one (every result's
command_now is the current command), and forward/inverse kinematics of the feet in the trunk frame for reference. Time
passes only inside calls. The robot's own action type done (native, no columns) ends the episode at once.

### Client
`/opt/tools/rcb_client.py`, protocol `eai-standard/2.2`:
```python
from rcb_client import Robot
r = Robot()                                    # connects (waits while the service starts)
spec = r.spec()                                # action types, limits, cameras, robot_spec (home pose, gains), kinematics, command_schedule
obs = r.get_obs()                              # obs.last[cam] -> uint8 (240, 320, 3); obs.meta["proprio"] {"layout", "now"}
res = r.submit("joint_position", A, dt=0.02)   # A: (T, 12) rows dt apart; res.proprio (one row per frame), res.meta
obs = r.get_obs(seconds=1.0, video="mp4")      # hold the targets and watch for 1 s (max 30)
r.fk(q); r.ik({"FR": [x, y, z, 1, 0, 0, 0]}, seed=q)   # feet in the trunk frame <-> joints (no physics)
r.submit("done", [])                           # end the episode now
r.status()                                     # calls, control steps, done, reason, elapsed time, episode, resets_left
obs = r._post("/reset", {"cameras": ["track"]}, [], 900)   # POST /reset: a new episode (the 2.2 client has no reset())
```

Simulated time only advances with your commands (and `get_obs(seconds=...)`, which holds the current targets). A reset
(`POST /reset`, the `_post` line above) puts the robot back on the same frozen starting state and starts a new episode,
either abandoning the running one or after one has ended; it takes no simulated time and returns the start's images and
proprioception. Once an episode has ended, `submit` raises `EpisodeOver` until you reset. The wall clock is the run's
and never restarts; `meta["episode"]` and `meta["resets_left"]` count the episodes (`meta["control_steps"]` is the
current episode's). If the service crashes, a call fails with a connection error: it restarts and resumes the same
episode (never a reset) in the state after the last call it completed. `r.wait_ready()` waits for it; then check
`r.status()`. One call returns at most 3000 images.

### Actions
Action type `joint_position` (12): FR, FL, RR, RL legs, each hip (abduction), thigh (hip pitch), calf (knee): absolute
targets of the joint position actuators (rad; kp = 35 N m/rad, joint damping 0.5 N m s/rad). Rows are `dt` apart (a
whole multiple of the 0.02 s control period, at most 0.5 s), `interpolate="linear"` (default) or `"hold"` between rows;
a chunk covers at most 10 s; values outside the limits (`spec["action_types"]["joint_position"]["limits"]`) are clipped
and listed in `res.meta["clipped"]`. Feedback control means short chunks: each response tells you where the robot is
now.

### Observations
Cameras: `track`, `side`, `back`, `top` (they follow the robot); `spec["cameras"]` gives each one's mounting and
intrinsics, and every response carries its pose. Proprioception (`spec["proprio_groups"]`): `joint_pos`, `joint_vel`,
`joint_effort` (12 each, action order), `imu_gyro`, `imu_accelerometer`, `imu_gravity`, `imu_linvel` (3 each, IMU frame:
x forward, y left, z up), `foot_contact` (FR, FL, RR, RL).

### Commands
A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw
rate. The schedule is `spec["command_schedule"]` (each segment's start and command); every response's
`meta["command_now"]` is the current command.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
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
- Resets: at most 10 (`spec()["budget"]["reset"]`), each a new episode from the same starting state.
