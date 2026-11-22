# MuJoCo Playground · SpotJoystickGaitTracking (privileged)

## Task
Boston Dynamics Spot (MuJoCo Playground's scene, in MuJoCo), driven by 12 joint position actuators: there is no walking
or balance controller. It starts standing still at its `home` pose. The ground is flat. Make it follow the joystick's
command schedule for the whole 20 s episode with the commanded gait (the feet's swing pattern, frequency and height),
without falling over. The scene is one fixed instance. You have the full simulator to develop with; you hand in a
trajectory of joint targets.

## Goal
Success: for the whole schedule the robot never falls; in every command's stretch, after a short settling time at its
start, its velocity over the ground (in its own frame) and its turning rate follow the command closely on average, and
its feet follow the gait's target heights closely. The trajectory covers the whole schedule (20 s, 1000 control steps);
a fall (the trunk tilting well over) at any step is a failure.

Deliverable: `/app/output/trajectory.npz` with `actions`: float64 (T, 12), one row per control step, T = 1000;
`s.save_trajectory(rows)` writes it. It is replayed from the frozen start. Leave the script that produced it at
`/app/output/gen.py`. Save a valid one early and overwrite it when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the joint targets count: changing `s.data` while you develop changes nothing in the replay.

## Robot Interface
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
12 absolute joint targets per control step, in `s.joint_names` order (FL, FR, HL, HR legs, each hx (abduction), hy (hip
pitch), kn (knee)), in radians; values outside the actuator ranges (`s.lower`, `s.upper`) are clipped. Joint position
actuators (PD): kp = 400 N m/rad, joint damping 10 N m s/rad, plus the actuators' own damping of 20 N m s/rad; the
physics step is 0.004 s, the control step 0.02 s (5 physics steps); a row holds until the next one.

### Observations
`s.state()`: qpos, qvel, the IMU (`local_linvel`, `gyro`, `gravity`, `accelerometer`, pose), the feet and their
contacts, the command; `s.sensor(name)` reads one MuJoCo sensor. The cameras follow the robot.

### Commands
A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw
rate. `s.commands` holds the schedule per control step; `s.state()["command"]` is the current one. The gait: a pace at
3.66 Hz, swing height h = 0.129 m. Foot i's target height at control step t follows its phase phi = phase0[i] + t *
phase_dt, wrapped to [-pi, pi), with phase0 = [0.0, 3.1416, 0.0, 3.1416] (feet FL, FR, HL, HR) and phase_dt = 0.4597
rad: with x = (phi + pi) / (2 pi), it rises as h (s^3 + 3 s^2 (1 - s)) with s = 2x over x in [0, 0.5] and falls as h
minus that with s = 2x - 1 over [0.5, 1].

### World frame
The world frame is z up, in metres; quaternions wxyz. The IMU frame is the trunk's: x forward, y left, z up.

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
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 4 CPUs, 10 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
