# MuJoCo Playground · Go1JoystickFlatTerrain (privileged)

## Task
Make the robot follow the joystick's commands for the whole schedule without falling over.

## Goal
Success: the robot never falls, and through every command of the schedule its speed and turning follow that command
closely on average. A fall (the trunk tipping over) at any step is a failure.

Deliverable: `/app/output/trajectory.npz` with `actions`: float64 (T, 12), one row per control step, T = 1000;
`s.save_trajectory(rows)` writes it. It is replayed from the frozen start. Leave the script that produced it at
`/app/output/gen.py`. Save a valid one early and overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
The Unitree Go1 quadruped (MuJoCo Playground's scene, in MuJoCo), driven by 12 joint position actuators: there is no
walking or balance controller. The scene is one fixed instance. You have the full simulator to develop with; you hand in
a trajectory of joint targets.

### Session
`rcb_quadruped` (installed; run `python` from any directory):
```python
from rcb_quadruped import Session
s = Session("/app/instance.json")    # the frozen episode at t = 0 (checked against the instance's state hash)
s.joint_names; s.lower; s.upper      # the actuator order and ranges (rad)
s.home                               # the standing pose (its `home` keyframe), in that order
s.step(row)                          # one control step: 12 joint targets, 5 physics steps of 0.004 s; returns s.check()
s.check()                            # the task's check on the steps so far
s.state()                            # qpos, qvel, IMU (local_linvel, gyro, gravity, accelerometer, pose), feet, contacts, command
s.sensor(name); s.gravity()          # one MuJoCo sensor; gravity's direction in the IMU frame
s.model, s.data                      # the live MuJoCo model and data (read them; changing them is not part of the replay)
s.render(cam); s.cameras             # uint8 (240, 320, 3) from cameras that follow the robot: `track`, `side`, `back`, `top` (they follow the robot)
s.reset()                            # back to t = 0
s.replay(rows)                       # reset, run the rows, return the check and the final state's hash
s.render_video(rows, "/app/output/try.mp4")
s.save_trajectory(rows, "/app/output/trajectory.npz")
```

`s.check()` reports `fell_at`, each segment's errors and `success`.

### Actions
12 absolute joint targets per control step, in radians, in `s.joint_names` order: the FR, FL, RR, RL legs, each with hip
(abduction), thigh (hip pitch) and calf (knee). Values outside the actuator ranges (`s.lower`, `s.upper`) are clipped.
Joint position actuators (PD): kp = 35 N m/rad, joint damping 0.5 N m s/rad. The physics step is 0.004 s and the control
step 0.02 s (5 physics steps). A row holds until the next one.

### Observations
`s.state()`: qpos, qvel, the IMU (`local_linvel`, `gyro`, `gravity`, `accelerometer`, pose), the feet and their
contacts, the command; `s.sensor(name)` reads one MuJoCo sensor. The cameras follow the robot.

### Commands
A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw
rate. `s.commands` holds the schedule per control step; `s.state()["command"]` is the current one.

### World frame
The world frame is z up, in metres; quaternions wxyz. The IMU frame is the trunk's: x forward, y left, z up.

### Episode
The robot starts at its `home` pose, its base moved to (-0.493, -0.479) m and turned to a yaw of -142.4 deg, with a
random base velocity. The ground is flat.

## Others
- To check a trajectory the way it is graded, replay it from the command line:
  `python /opt/tools/rcb_quadruped.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`.

## Limits
- Time: 1800 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 4 CPUs, 10 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
