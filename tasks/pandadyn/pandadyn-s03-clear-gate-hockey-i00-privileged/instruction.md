# Panda Dynamic Scenes · Clear the blocker, recover and bank into the goal (S03) (privileged)

## Task
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). A square puck slides toward the robot over an almost frictionless table at
the start. First touch it with the paddle; then strike it so that, sliding free of the paddle, it hits a sliding blocker
bar that obstructs the way to the goal fast enough to push it aside along its rail. Let the puck slide back across a
recovery line by itself, strike it a second time, and make it bank off the rail designated for this episode (one of two
rails, coloured green; the other is grey) without touching the other rail, and then cross the goal line while the
blocker is still pushed aside. The scene is one fixed instance: everything starts the same way after every reset. Things
move by themselves from the first control step on: the scene does not wait for the robot. You have the full simulator to
develop with; you hand in a trajectory of robot actions.

### Scene
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x). Its hand carries a blue upright paddle: a box 12 mm thick (tool x)
x 0.10 m wide (tool y) x 50 mm tall (tool z), centred at the tool frame origin; its striking faces are normal to the
tool x axis. A rigid dark-grey adapter behind the paddle (on its -x side) joins it to the hand: a horizontal bar 0.035 m
above the tool origin (tool-frame x from -0.132 to -0.038), a short vertical post at x = -0.05 reaching down to z =
-0.005, and a 12 mm square bridge from the post to the paddle's back face (x from -0.044 to -0.006, z from 0.009 to
0.021); all of it is part of the tool, and paddle and adapter form one rigid piece. The Panda TCP is at (-0.12, 0, 0.04)
in the tool frame, so with the paddle upright the gripper points straight down. At the start the paddle is upright with
tool axes aligned with the world axes (faces normal to world x), its centre at (0.03, -0.20, 0.045), so its lower edge
is 0.02 m above the table. The tool's adapter runs between the gripper's fingertips: closing the gripper to less than
about 12 mm of aperture makes the fingers touch the adapter, which ends the episode as a collision with its own tool
(the gripper starts fully open, at 0.08 m).

An orange square puck (44 mm x 44 mm, 24 mm tall) slides over the table toward the robot (-x) at t = 0. The table
surface and the puck are nearly frictionless and the puck is bouncy, so it keeps sliding and rebounds off walls. A blue
blocker bar (140 mm long, 30 mm thick, 64 mm tall), set at an angle to the axes, stands on the table on a passive,
unpowered sliding joint along the world y axis; it starts at one end of its travel, so it can only be pushed toward +y,
and it obstructs the route to the goal. Three fixed walls, 70 mm tall, stand on the table: a long side rail (0.34 m)
running along x on the robot's right (-y side) of the play area, a short end rail (0.20 m) running along y on the
robot's side of the play area, and an orange backstop (0.20 m) running along y behind the goal line. One of the two
rails is designated for this episode's final bank shot and is coloured green; the other is grey. The goal itself is not
a physical object but a line segment on the table (see world goals). Nothing else moves by itself. The table top is the
world's z = 0 plane.

Exact sizes, masses, frictions, starting poses and velocities, and the instance's parameters: `s.params()`,
`s.objects()`, `s.fixtures()` and `s.state()` (Robot Interface).

## Goal
Success: the paddle touches the puck; then it strikes it so that the puck, sliding free of the paddle for a moment, hits
the blocker bar fast enough to push it well aside along its rail; the puck slides back across the recovery line (x =
0.16) by itself; the paddle strikes it a second time, and after that last touch it banks off the designated rail, at
this instance the short end rail on the robot's side of the play area (coloured green), touches no other rail, and
crosses the goal line (x = 0.46, around y = 0.06) moving away from the robot, not touching the paddle, with the blocker
still pushed aside. The task fails at once if the paddle touches the blocker, if the puck meets the blocker too soon
after leaving the paddle (pushed rather than struck), or if it crosses the goal line after touching the other rail,
without the bank, touching the paddle or with the blocker back in the way.

The steps count only in this order, and a step once done stays done. The replay ends as soon as the task is done or has
failed; the task also fails at once when:
- the task's horizon, 35 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. Only the paddle (including its adapter) may touch anything, and it may touch
  only the puck: touching the blocker, either rail, the backstop or the table is forbidden. No other part of the robot,
  the fingers included, may touch anything, the puck included. In every task the arm never touches itself, no robot part
  touches the table or the floor, a robot part other than an allowed one touches nothing, a tool touches only what the
  task allows, and no contact presses deep into anything;
- an arm goes beyond the Franka Panda's own safety limits on joint positions, joint and finger speeds, the hand's speed
  and acceleration, joint accelerations and jerks, and motor torques and how fast they change (the numbers: the robot
  spec's `safety_limits`). They count on the motion as measured, whatever was commanded (a catch or a strike moves the
  arm too), and the servo's own reference motion is held to the same speed, acceleration and jerk limits.

Deliverable: `/app/output/trajectory.npz`, written with `Session.save_trajectory(...)`: it holds `task` and `actions`, a
(T, 8) float array of at most 4,500 rows (one per control step); anything else (another shape, NaN, more rows, a file
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
s.step(row)                        # one control step (10 ms = 10 physics steps): row = 8 values; True once the episode is over
s.hold_action()                    # a row that commands every arm to stay where it is
s.status()                         # {'success', 'done', 'end_reason', 'phase', 'phase_name', 'phases', 'sim_time_s', 'control_steps', 'events', 'state_sha', ...}
s.state()                          # privileged: every object's pose (xyz + quaternion wxyz) and velocities, fixtures, tool poses, phase, announced goals
s.objects(); s.fixtures(); s.params()                # object poses / velocities, fixture joint positions / velocities, the instance's parameters
s.proprio()                        # per arm: joints q (9) and qd (9), hand TCP and tool poses, motor torques, current target row, aperture
s.snapshot(); s.restore(snap)      # exact save / restore of the whole episode (a restore replays its rows: it takes a moment)
s.actions()                        # (T, 8) rows executed since the last reset: the trajectory of this episode
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
- Action row (8 values per control step): `[joint1..7, aperture]`. Each arm's 8 values are its 7 absolute joint-position
  targets (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open; each finger
  moves at most 0.025 m/s). Values outside the joint limits (`s.robot_spec()`) are clipped to them before they are
  executed, and the trajectory records the clipped row.
- The servo: every control step, each arm's latest target is turned into a smooth reference motion by a jerk-limited
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 55 % (acceleration) and
  5 % (jerk) of the Panda's joint speed, acceleration and jerk limits, and the arm tracks that reference with torque
  control (PD + inverse dynamics, the Panda's torque and torque-rate limits). A new target replans from the current
  reference motion, so a target far away is reached smoothly, not in one step. `s.robot_spec()["servo"]` has the exact
  limits and gains.
- Control runs at 100 Hz (10 ms per row), physics at 1000 Hz. A simulated episode ends at the latest at the task's
  horizon (35 s, 3500 rows).

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
