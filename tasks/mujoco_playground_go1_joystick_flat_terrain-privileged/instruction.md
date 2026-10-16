# MuJoCo Playground · Go1JoystickFlatTerrain — frozen episode

**Task:** Make the Unitree Go1 follow the joystick command schedule on flat ground for the whole 20 s episode without falling over.

You control the Unitree Go1 quadruped in one episode of MuJoCo Playground's `Go1JoystickFlatTerrain` environment, rebuilt in plain
MuJoCo 3.3.7 from Playground's own scene files (Apache-2.0, commit 4057c14) and the robot from MuJoCo Menagerie. The
episode is frozen: it starts the same way after every reset (Playground's `reset` with seed 0), and you may reset
as often as you like. Your deliverable is **one open-loop trajectory**, not a general policy.

## The episode
The robot starts at Playground's `home` pose, its base moved to (-0.493, -0.479) m and turned to a yaw of -142.4 deg, with a random base velocity (Playground's reset). The ground is flat.
For 20 s (1000 control steps) it is given this command schedule, drawn by Playground's command process (a new draw after Exp(1) x 5 s; a draw may keep a component). A command is a velocity in the robot's own frame: vx forward, vy to the left (the trunk's planar velocity), and the yaw rate:

| from (s) | vx (m/s) | vy (m/s) | yaw rate (rad/s) |
|---:|---:|---:|---:|
| 0.00 | +1.413 | -0.611 | +0.712 |
| 0.84 | -0.253 | -0.611 | +0.712 |
| 4.76 | -0.253 | -0.611 | +0.000 |
| 5.96 | -0.552 | -0.611 | +0.000 |

`s.commands` holds the schedule per control step; `s.state()["command"]` is the current one.

## Success
The episode lasts exactly 1000 control steps: the trajectory must have T = 1000 rows. Success iff
1. the robot never meets Playground's termination rule for this environment: the trunk's up axis pointing below the horizon (the z component of the IMU frame's z axis negative); and
2. in every command segment, over its control steps after the first 25 (0.5 s): the mean planar velocity error |v_xy - cmd_xy| is at most 0.2 m/s, with v the IMU's velocimeter (`local_linvel`, trunk frame), and the mean yaw-rate error |w_z - cmd_wz| at most 0.3 rad/s, with w the IMU's gyro.

`s.check()` reports `fell_at`, each segment's errors and `success`.

## Deliverable
`/app/output/trajectory.npz` with `actions`: float64 (T, 12), one row per control step (0.02 s): absolute targets of
the 12 joint position actuators, in `s.joint_names` order (FR, FL, RR, RL legs, each hip (abduction), thigh (hip pitch), calf (knee)), in radians; T = 1000 (the whole schedule). Values
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
s.state()                            # qpos, qvel, IMU (local_linvel, gyro, gravity, accelerometer, pose), feet, contacts, command
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
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **8 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
