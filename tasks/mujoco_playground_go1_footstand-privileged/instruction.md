# MuJoCo Playground · Go1Footstand — frozen episode

**Task:** Make the Unitree Go1 stand up on its hind legs, nose up, front legs in the air, and balance there for 2 s.

You control the Unitree Go1 quadruped in one episode of MuJoCo Playground's `Go1Footstand` environment, rebuilt in plain
MuJoCo 3.3.7 from Playground's own scene files (Apache-2.0, commit 4057c14) and the robot from MuJoCo Menagerie. The
episode is frozen: it starts the same way after every reset (Playground's `reset` with seed 0), and you may reset
as often as you like. Your deliverable is **one open-loop trajectory**, not a general policy.

## The episode
The robot starts at Playground's `home` pose, its base moved to (-0.396, -0.156) m, turned to a yaw of -150.2 deg, with a random base velocity (Playground's reset). You have 500 control steps (10 s).

## Success
Success iff the trajectory (at most 500 rows) ends with 100 control steps in a row (2 s) after each of which the trunk's forward axis (the IMU frame's x axis) is within 30 deg of straight up, the IMU is at least 0.4 m above the floor and the front (FR, FL) feet are off the ground; and no control step before its end meets Playground's termination rule: the trunk's up axis below -0.25 (z component of the IMU frame's z axis), or any part of a front leg other than its foot (thigh, calf, hip) touching the floor (Playground's rule as its code reads it), or the same for a hind leg (the list its Footstand sets up but never reads; without it, sitting on a hind hip would count). End the trajectory once the hold is complete. `s.check()` reports `fell_at`, the last pose angle and height, and `success`.

## Deliverable
`/app/output/trajectory.npz` with `actions`: float64 (T, 12), one row per control step (0.02 s): absolute targets of
the 12 joint position actuators, in `s.joint_names` order (FR, FL, RR, RL legs, each hip (abduction), thigh (hip pitch), calf (knee)), in radians; 1 <= T <= 500. Values
outside the actuator ranges (`s.lower`, `s.upper`) are clipped. `s.save_trajectory(rows)` writes it. Also leave the
script that produced it at `/app/output/gen.py`. Save a working trajectory as soon as you have one and overwrite it as
you improve it: whatever is in `/app/output/` when your time is up is graded. The tooling logs your sessions and
resets (cost accounting, not graded).

## Tooling (installed; `python` from any directory)
```python
from rcb_quadruped import Session
s = Session("/app/instance.json")    # the frozen episode at t = 0 (checked against the instance's state hash)
s.joint_names; s.lower; s.upper      # the actuator order and ranges (rad)
s.home                               # Playground's standing pose (its `home` keyframe), in that order
s.step(row)                          # one control step: 12 joint targets, 5 physics steps of 0.004 s; returns s.check()
s.check()                            # the task's check on the steps so far (see Success)
s.state()                            # qpos, qvel, IMU (local_linvel, gyro, gravity, accelerometer, pose), feet, contacts
s.sensor(name); s.gravity()          # one MuJoCo sensor; gravity's direction in the IMU frame
s.model, s.data                      # the live MuJoCo model and data (read them; changing them is not part of the replay)
s.render(cam); s.cameras             # uint8 (240, 320, 3) from cameras that follow the robot: `track`, `side`, `back`, `top` (they follow the robot)
s.reset()                            # back to t = 0
s.replay(rows)                       # reset, run the rows, return the check and the final state's hash
s.render_video(rows, "/app/output/try.mp4")
s.save_trajectory(rows, "/app/output/trajectory.npz")
```
The grader runs exactly this CLI in two fresh processes, so run it to check yourself:
`python /opt/tools/rcb_quadruped.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`

## Conventions
- Joint position actuators (PD): kp = 35 N m/rad, joint damping 0.5 N m s/rad, as Playground's environment sets them; the physics step is 0.004 s,
  the control step 0.02 s (5 physics steps); a row holds until the next one.
- World frame z up, metres; quaternions **wxyz**. The IMU frame is the trunk's: x forward, y left, z up.
- Physics is MuJoCo on the CPU: the same rows from the same start give the same result in every fresh process.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
