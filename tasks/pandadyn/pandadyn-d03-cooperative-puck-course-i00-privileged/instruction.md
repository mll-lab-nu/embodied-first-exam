# Panda Dynamic Scenes · Cooperative puck course (D03) (privileged)

## Task
Hit the sliding puck with the paddles in turn, left, right, left, right: first through the end gap of the row of posts
away from the side rail, then back through the end gap next to the side rail, then through the middle gap, and with the
last hit across the goal line in front of the middle of the backstop.

## Goal
Success: the paddles hit the puck in turn, left, right, left, right; after the first hit it slides toward the right arm
through the end gap away from the side rail, after the second back toward the left arm through the end gap next to the
side rail, after the third toward the right arm through the middle gap, and the right arm's last hit sends it across the
goal line in front of the middle of the backstop. A hit counts only while the paddle itself is moving, and each pass
counts only with the puck sliding free of the paddle that hit it.

The steps count only in this order. Once a step is done, it stays done. The replay ends as soon as the task is done or
has failed; the task also fails at once when:
- the task's horizon is reached before the task is done (Robot Interface);
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not: each paddle may touch only the puck, a paddle must not touch its own arm, no
  other robot part may touch anything, and the two arms must never touch each other;
- an arm touches itself, a robot part touches the table or the floor, or a contact presses deep into anything;
- an arm goes beyond the Franka Panda's own safety limits (Robot Interface, Safety).

Deliverable: `/app/output/trajectory.npz`, written with `Session.save_trajectory(...)`. It holds `task` and `actions`;
`actions` is a (T, 16) float array of at most 4,500 rows, one per control step. Anything else (another shape, NaN, more
rows, a file that is not such an npz) scores 0. It is replayed open-loop from the fixed start and scores 1 if the task
succeeds in the replay, else 0. Keep the script that produced it at `/app/output/gen.py`. Save a valid one early and
overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
Two simulated Franka Panda arms on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). `panda-0` is on the
left and `panda-1` on the right; each has its standard hand and the task's tool where it has one. The scene is one fixed
instance: everything starts the same way after every reset. Things move by themselves from the first control step on:
the scene does not wait for the robot. You have the full simulator to develop with; you hand in a trajectory of robot
actions.

### Session
`rcb_pandadyn`, already installed (run `python` from any directory):
```python
from rcb_pandadyn import Session
s = Session(instance="/app/instance.json")   # ~5-15 s: builds the scene and resets it to the frozen instance
s.reset()                          # back to the frozen initial state (exact; as often as you like)
s.step(row)                        # one control step (10 ms = 10 physics steps): row = 16 values; True once the episode is over
s.hold_action()                    # a row that commands every arm to stay where it is
s.status()                         # {'success', 'done', 'end_reason', 'phase', 'phase_name', 'phases', 'sim_time_s', 'control_steps', 'events', 'state_sha', ...}
s.state()                          # privileged: every object's pose (xyz + quaternion wxyz) and velocities, fixtures, tool poses, phase, announced goals
s.objects(); s.fixtures(); s.params()                # object poses / velocities, fixture joint positions / velocities, the instance's parameters
s.proprio()                        # per arm: joints q (9) and qd (9), hand TCP and tool poses, motor torques, current target row, aperture
s.snapshot(); s.restore(snap)      # exact save / restore of the whole episode (a restore replays its rows: it takes a moment)
s.actions()                        # (T, 16) rows executed since the last reset: the trajectory of this episode
s.replay(actions)                  # reset, run the rows open-loop until the episode ends, return status (+ executed_rows)
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.fk(q7, "panda-0"); s.ik(pose7, "panda-0", frame="tool")   # stateless kinematics: hand TCP / tool world poses <-> 7 joint angles
s.robot_spec()                     # arm bases, tools and mounts, joint limits, servo limits and gains, safety limits
s.render_frame("overview")         # RGB uint8 (480, 640, 3) of "overview" (the whole workspace) or "closeup" (the working area)
s.camera_info()                    # per camera: intrinsic_cv, extrinsic_cv (world -> camera, OpenCV axes), cam2world_gl
s.render_video(actions, "/app/output/check.mp4")   # replays from the frozen state while filming the overview camera
s.u                                # the ManiSkill environment itself (`panda_dynamics` in /opt/pandadyn: read-only reference)
```

The tooling is deliberately thin: joint targets, kinematics and state. Catching, striking, carrying and timing are yours
to build. The environment's source is in `/opt/pandadyn/panda_dynamics`. Check a trajectory as the grader replays it:
`python /opt/tools/rcb_pandadyn.py replay --instance /app/instance.json --traj /app/output/trajectory.npz`. One
`Session` per process. Stepping runs at roughly 40-150 control steps per second; rendering happens only when a frame is
asked for and never moves anything. Do not call `s.close()` before writing every output.

### Actions
- Action row (16 values per control step): `[panda-0 joint1..7, panda-0 aperture, panda-1 joint1..7, panda-1 aperture]`.
  Each arm has 8 values: its 7 absolute joint-position targets (rad, `panda_joint1..7`) and its total gripper aperture
  target (m, 0 = closed .. 0.08 = open). Each finger moves at most 0.025 m/s. Values outside the joint limits
  (`s.robot_spec()`) are clipped to them before they are executed, and the trajectory records the clipped row.
- The servo: every control step, a jerk-limited trajectory generator (Ruckig) turns each arm's latest target into a
  smooth reference motion, with the joints synchronised to arrive together. That motion stays within 65 % of the Panda's
  joint speed limits, 55 % of its acceleration limits and 5 % of its jerk limits. The arm tracks that reference with
  torque control (PD + inverse dynamics, within the Panda's torque and torque-rate limits). A new target replans from
  the current reference motion, so a target far away is reached smoothly, not in one step. `s.robot_spec()["servo"]` has
  the exact limits and gains.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz. A simulated episode ends at the latest at the task's
  horizon (25 s, 2500 rows).

### Observations
- World frame: metres, z up, the table top is the plane z = 0; quaternions are wxyz. Each arm's base pose is in the
  robot spec (`arms`).
- Cameras: `s.render_frame("overview")` (the whole workspace) or `s.render_frame("closeup")` (the working area), RGB 640
  x 480; `s.camera_info()` has their calibration. `s.proprio()` and `s.state()` (above) give the robot's and the scene's
  state.

### Arms and tools
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing
-x). Each carries a flat rigid paddle, 0.10 m long, 0.05 m tall and 12 mm thick, on a rigid adapter on its back (tool
-x) side. The adapter has a horizontal bar 0.035 m above the tool origin (tool x from -0.132 to -0.038), a vertical post
at tool x = -0.05 (z from -0.005 to 0.035) and a 12 mm square bridge from the post to the paddle's back face (x from
-0.044 to -0.006, z from 0.009 to 0.021). Paddle and adapter form one rigid tool link. The tool frame is the paddle
centre, with x normal to its faces, y along its length and z up. The TCP sits 0.12 m behind the paddle centre (tool -x)
and 0.04 m above it. Left paddle start: centre (-0.05, -0.18, 0.048), orientation identity (faces normal to world x,
length along world y). Right paddle start: centre (0.28, 0.12, 0.048), quaternion (0, 0, 0, 1) (yawed 180 deg). At the
start height each paddle's lower edge is 0.023 m above the table. In this task the servo damping on joints 5-7 is raised
to (24, 20, 14) from the default (12, 10, 7). On both arms the tool's adapter runs between the fingertips. If you close
a gripper to less than about 12 mm of aperture, its fingers touch the adapter, and the episode ends as a collision with
its own tool. Both grippers start fully open, at 0.08 m.

### Safety
The task fails when an arm goes beyond the Franka Panda's own safety limits. These limits cover joint positions, joint
and finger speeds, the hand's speed and acceleration, joint accelerations and jerks, motor torques, and how fast the
torques change. The numbers are in the robot spec's `safety_limits`. The limits apply to the motion as measured,
whatever was commanded (a catch or a strike moves the arm too). The servo's own reference motion must also stay within
the same speed, acceleration and jerk limits.

## Others
- State labels (`s.objects()`, `s.fixtures()`): `puck` is the puck.

## Limits
- Time: 3600 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 5 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (3 GiB of its memory). Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
