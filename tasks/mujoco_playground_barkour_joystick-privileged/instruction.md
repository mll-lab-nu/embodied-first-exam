# MuJoCo Playground · BarkourJoystick — frozen episode

**Task:** Make Google's Barkour quadruped follow the joystick command schedule for the whole 10 s episode, through random pushes, without falling over.

You control the Google Barkour vB quadruped in one episode of MuJoCo Playground's `BarkourJoystick` environment, rebuilt in plain
MuJoCo 3.3.7 from Playground's own scene files (Apache-2.0, commit 4057c14) and the robot from MuJoCo Menagerie. The
episode is frozen: it starts the same way after every reset (Playground's `reset` with seed 2), and you may reset
as often as you like. Your deliverable is **one open-loop trajectory**, not a general policy.

## The episode
The robot starts standing still at Playground's `home` pose (this environment's reset does not move it). The ground is flat. One control step is 10 ms of simulated time: Playground's Barkour environment keeps Menagerie's 2 ms timestep and takes 5 substeps.
For 10 s (1000 control steps) it is given this command schedule, drawn by Playground's command process (a new draw after 501 control steps). A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw rate:

| from (s) | vx (m/s) | vy (m/s) | yaw rate (rad/s) |
|---:|---:|---:|---:|
| 0.00 | +0.459 | +0.221 | +0.016 |
| 5.01 | +0.090 | -0.389 | +0.643 |

The torso is pushed 12 times (Playground's kicks): each push lasts 5 control steps, a half-sine of horizontal force up to 35 N in a random direction; `instance.json` (`kicks`) lists when and where, and `s.push_force(t)` gives the force of control step t.

`s.commands` holds the schedule per control step; `s.state()["command"]` is the current one.

## Success
The episode lasts exactly 1000 control steps: the trajectory must have T = 1000 rows. Success iff
1. the robot never meets Playground's termination rule for this environment: the trunk's up axis pointing below the horizon, a joint outside its box (abduction [-0.7, 0.52], hip [-1.0, 2.1], knee [0.05, 2.1] rad) or the torso lower than 0.18 m; and
2. in every command segment, over its control steps after the first 25 (0.25 s): the mean planar velocity error |v_xy - cmd_xy| is at most 0.2 m/s, with v the IMU's velocimeter (`local_linvel`, trunk frame), and the mean yaw-rate error |w_z - cmd_wz| at most 0.3 rad/s, with w the IMU's gyro.

`s.check()` reports `fell_at`, each segment's errors and `success`.

## Deliverable
`/app/output/trajectory.npz` with `actions`: float64 (T, 12), one row per control step (0.01 s): absolute targets of
the 12 joint position actuators, in `s.joint_names` order (front-left, hind-left, front-right, hind-right legs, each abduction, hip, knee), in radians; T = 1000 (the whole schedule). Values
outside the actuator ranges (`s.lower`, `s.upper`) are clipped. `s.save_trajectory(rows)` writes it. Also leave the
script that produced it at `/app/output/gen.py`. Save a working trajectory as soon as you have one and overwrite it as
you improve it: whatever is in `/app/output/` when your 3600 s are up is graded. The tooling logs your sessions and
resets (cost accounting, not graded).

## Tooling (installed; `python` from any directory)
```python
from rcb_quadruped import Session
s = Session("/app/instance.json")    # the frozen episode at t = 0 (checked against the instance's state hash)
s.joint_names; s.lower; s.upper      # the actuator order and ranges (rad)
s.home                               # Playground's standing pose (its `home` keyframe), in that order
s.step(row)                          # one control step: 12 joint targets, 5 physics steps of 0.002 s; returns s.check()
s.check()                            # the task's check on the steps so far (see Success)
s.state()                            # qpos, qvel, IMU (local_linvel, gyro, gravity, accelerometer, pose), feet, contacts, command
s.sensor(name); s.gravity()          # one MuJoCo sensor; gravity's direction in the IMU frame
s.model, s.data                      # the live MuJoCo model and data (read them; changing them is not part of the replay)
s.render(cam); s.cameras             # uint8 (240, 320, 3) from cameras that follow the robot: `track` (follows the robot) and `realsense/rgb` (on its head)
s.reset()                            # back to t = 0
s.replay(rows)                       # reset, run the rows, return the check and the final state's hash
s.render_video(rows, "/app/output/try.mp4")
s.save_trajectory(rows, "/app/output/trajectory.npz")
```
The grader runs exactly this CLI in two fresh processes, so run it to check yourself:
`python /opt/tools/rcb_quadruped.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- Joint position actuators (PD): kp = 35 N m/rad, joint damping 0.5239 N m s/rad, plus the actuators' own damping of 0.5 N m s/rad, as Playground's environment sets them; the physics step is 0.002 s,
  the control step 0.01 s (5 physics steps); a row holds until the next one.
- World frame z up, metres; quaternions **wxyz**. The IMU frame is the trunk's: x forward, y left, z up.
- Physics is MuJoCo on the CPU: the same rows from the same start give the same result in every fresh process.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
