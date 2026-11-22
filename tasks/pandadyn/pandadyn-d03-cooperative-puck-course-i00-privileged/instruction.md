# Panda Dynamic Scenes · Cooperative puck course (D03) (privileged)

## Task
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). A low-friction puck is
already sliding across the table toward the left arm when the episode starts. The two Pandas each hold a paddle and must
hit the same puck in turn: left, right, left, right. After each of the first three hits the puck must pass through a
different gap in a row of posts standing across the table between the arms. First it goes toward the right arm through
the gap at the -y end. Then it goes back toward the left arm through the gap at the +y end, next to a side rail. Then it
goes toward the right arm again through the middle gap. The right arm's final hit must send the puck across a goal line
in front of a backstop wall on the right arm's side. The scene is one fixed instance: everything starts the same way
after every reset. Things move by themselves from the first control step on: the scene does not wait for the robot. You
have the full simulator to develop with; you hand in a trajectory of robot actions.

### Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing
-x). Each carries a flat rigid paddle, 0.10 m long, 0.05 m tall and 12 mm thick, on a rigid adapter on its back (tool
-x) side: a horizontal bar 0.035 m above the tool origin (tool x from -0.132 to -0.038), a vertical post at tool x =
-0.05 (z from -0.005 to 0.035) and a 12 mm square bridge from the post to the paddle's back face (x from -0.044 to
-0.006, z from 0.009 to 0.021); paddle and adapter form one rigid tool link. The tool frame is the paddle centre, with x
normal to its faces, y along its length and z up. The TCP sits 0.12 m behind the paddle centre (tool -x) and 0.04 m
above it. Left paddle start: centre (-0.05, -0.18, 0.048), orientation identity (faces normal to world x, length along
world y). Right paddle start: centre (0.28, 0.12, 0.048), quaternion (0, 0, 0, 1) (yawed 180 deg). At the start height
each paddle's lower edge is 0.023 m above the table. In this task the servo damping on joints 5-7 is raised to (24, 20,
14) from the default (12, 10, 7). On both arms the tool's adapter runs between the fingertips: closing a gripper to less
than about 12 mm of aperture makes its fingers touch the adapter, which ends the episode as a collision with its own
tool (both grippers start fully open, at 0.08 m).

A small orange square puck (44 mm x 44 mm, 24 mm tall) slides on the table with very little friction, so it slows down
only slowly. At t = 0 it is already moving toward the left arm. A row of four short orange posts stands across the table
between the two arms; each post is 32 mm x 50 mm and 70 mm tall. The posts leave three gaps, and they are very bouncy. A
long rail, 70 mm tall and also very bouncy, runs along the +y side of the course. A short backstop wall, 0.13 m wide and
70 mm tall and not bouncy, stands behind the goal line on the right arm's side. All of these are fixed, and only the
puck moves by itself. The table top is the world's z = 0 plane.

Exact sizes, masses, frictions, starting poses and velocities, and the instance's parameters: `s.params()`,
`s.objects()`, `s.fixtures()` and `s.state()` (Robot Interface).

## Goal
Success: the paddles hit the puck in turn, left, right, left, right; after the first hit it slides toward the right arm
through the gap at the -y end of the row of posts (around y = -0.13 on the line x = 0.12); after the second, back toward
the left arm through the gap at the +y end by the side rail (around y = 0.19); after the third, toward the right arm
through the middle gap (around y = 0.025); the right arm's last hit sends it across the goal line in front of the
backstop (x = 0.46, around y = -0.02). A hit counts only while the paddle itself is moving, and each crossing counts
only with the puck sliding free of the paddle that hit it.

The steps count only in this order, and a step once done stays done. The replay ends as soon as the task is done or has
failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. Each paddle may touch only the puck. The paddles must not touch the posts, the
  rail, the backstop, the table or the robot pedestals. No other robot part, the fingers included, may touch anything.
  The two arms and their paddles must never touch each other, and a paddle must not touch its own arm. In every task an
  arm never touches itself, no robot part touches the table or the floor, a robot part other than an allowed one touches
  nothing, a tool touches only what the task allows, and no contact presses deep into anything;
- an arm goes beyond the Franka Panda's own safety limits on joint positions, joint and finger speeds, the hand's speed
  and acceleration, joint accelerations and jerks, and motor torques and how fast they change (the numbers: the robot
  spec's `safety_limits`). They count on the motion as measured, whatever was commanded (a catch or a strike moves the
  arm too), and the servo's own reference motion is held to the same speed, acceleration and jerk limits.

Deliverable: `/app/output/trajectory.npz`, written with `Session.save_trajectory(...)`: it holds `task` and `actions`, a
(T, 16) float array of at most 4,500 rows (one per control step); anything else (another shape, NaN, more rows, a file
that is not such an npz) scores 0. It is replayed open-loop from the fixed start and scores 1 if the task succeeds in
the replay, else 0. Keep the script that produced it at `/app/output/gen.py`. Save a valid one early and overwrite it
when you have a better one.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Only the trajectory counts: changing the simulator's state while you develop changes nothing in the grading.

## Robot Interface
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
  Each arm's 8 values are its 7 absolute joint-position targets (rad, `panda_joint1..7`) and its total gripper aperture
  target (m, 0 = closed .. 0.08 = open; each finger moves at most 0.025 m/s). Values outside the joint limits
  (`s.robot_spec()`) are clipped to them before they are executed, and the trajectory records the clipped row.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and
  5 % (jerk) of the Panda's joint speed, acceleration and jerk limits, and the arm tracks that reference with torque
  control (PD + inverse dynamics, the Panda's torque and torque-rate limits). A new target replans from the current
  reference motion, so a target far away is reached smoothly, not in one step. `s.robot_spec()["servo"]` has the exact
  limits and gains.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz. A simulated episode ends at the latest at the task's
  horizon (25 s, 2500 rows).

### Observations
- World frame: metres, z up, the table top is the plane z = 0; quaternions are wxyz. Each arm's base pose is in the
  robot spec (`arms`).
- Cameras: `s.render_frame("overview")` (the whole workspace) or `s.render_frame("closeup")` (the working area), RGB 640
  x 480; `s.camera_info()` has their calibration. `s.proprio()` and `s.state()` (above) give the robot's and the scene's
  state.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 5 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (3 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
