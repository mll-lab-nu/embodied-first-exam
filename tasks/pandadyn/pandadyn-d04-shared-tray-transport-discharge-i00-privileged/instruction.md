# Panda Dynamic Scenes · Shared tray transport and discharge (D04) (privileged)

## Task
Two simulated Franka Panda arms (`panda-0` on the left, `panda-1` on the right; each with its standard hand and the
task's tool where it has one) on a table (ManiSkill 3 / SAPIEN, rigid-body physics at 1000 Hz). The two Pandas hold one
tray between them. Each arm's small open fork cradles a tab on one end of the tray, and an orange ball lies loose in the
tray. Working together, the arms must first hold the tray steadily. They then carry it through two waypoints that make a
turn. When the environment pushes the ball, they must bring it back to rest near the tray centre. Next they bring the
tray to an exit position beside a fixed basin, and finally they tip the ball out so that it settles in the basin. Both
forks must support the tray during the transport phases, the ball must not leave the tray before the discharge, and the
tray must never drop low. The scene is one fixed instance: everything starts the same way after every reset. Things move
by themselves from the first control step on: the scene does not wait for the robot. You have the full simulator to
develop with; you hand in a trajectory of robot actions.

### Scene
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing
-x). Each carries a support fork: a small, shallow square cradle 0.07 m x 0.07 m inside. It has a 5 mm floor and 18 mm
high walls on three sides, is open on the tool +x side, and is held by an adapter on its closed tool -x wall. The tool
frame is the centre of the cradle floor's top surface, z up. The TCP sits 0.12 m along tool -x and 0.04 m above the tool
frame. Left fork start: (-0.075, 0, 0.22), orientation identity (open side toward world +x). Right fork start: (0.215,
0, 0.22), quaternion (0, 0, 0, 1) (yawed 180 deg, open side toward world -x). The two open sides face each other. In
this task both arms' servos plan their reference motion with lower acceleration and jerk fractions than usual (0.30 and
0.025, default 0.55 and 0.05). On both arms the tool's adapter runs between the fingertips: closing a gripper to less
than about 12 mm of aperture makes its fingers touch the adapter, which ends the episode as a collision with its own
tool (both grippers start fully open, at 0.08 m).

A blue rigid tray, 0.20 m x 0.24 m inside, has a 9 mm rim and a 5 mm floor. A flat tab (48 mm x 60 mm, 8 mm thick)
sticks out at floor level from the middle of each of its two longer sides. At the start each tab rests in one arm's
fork, so the tray hangs between the two arms. An orange ball (radius 18 mm) lies loose near the middle of the tray. A
fixed blue open-top basin, 0.21 m x 0.20 m inside and 0.08 m deep, stands on posts above the table. Nothing moves by
itself, except that the environment gives the ball a brief push along world +x the moment the third phase begins. The
table top is the world's z = 0 plane.

Exact sizes, masses, frictions, starting poses and velocities, and the instance's parameters: `s.params()`,
`s.objects()`, `s.fixtures()` and `s.state()` (Robot Interface).

## Goal
Success: the two forks hold the tray steadily together, the ball in it; carried on both forks, the tray's centre passes
waypoint A (0.12, -0.04, 0.27) and then waypoint B (0.02, 0.08, 0.27); when the ball is pushed (the moment the turn is
done), the arms bring it back to rest near the tray's centre, both forks still supporting the tray; then the tray is
brought, on both forks, to the exit position beside the basin, around (0.12, 0.18); finally the ball is tipped out and
settles in the basin, away from the tray, for about 0.7 s. The task fails at once if the ball leaves the tray before the
discharge, or if the tray drops low at any time.

The steps count only in this order, and a step once done stays done. The replay ends as soon as the task is done or has
failed; the task also fails at once when:
- the task's horizon, 25 s of robot time, is reached before the task is done;
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not. The forks may touch the tray and the ball, which are free objects, and nothing
  else: not the basin or its posts, not the table, not the robot pedestals. No other robot part, the fingers included,
  may touch anything. The two arms and their forks must never touch each other, and a fork must not touch its own arm.
  The tray and the ball may touch the basin. In every task an arm never touches itself, no robot part touches the table
  or the floor, a robot part other than an allowed one touches nothing, a tool touches only what the task allows, and no
  contact presses deep into anything;
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
  trajectory generator (Ruckig, the joints synchronised to arrive together) within 65 % (speed), 30 % (acceleration) and
  2 % (jerk) of the Panda's joint speed, acceleration and jerk limits, and the arm tracks that reference with torque
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
