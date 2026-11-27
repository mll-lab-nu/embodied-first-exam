# Panda Dynamic Scenes · Shared tray transport and discharge (D04) (privileged)

## Task
Hold the tray with the ball in it between the two forks and carry it through the two waypoints. When the ball gets
pushed, bring it back to rest in the middle of the tray; then bring the tray to the exit position beside the basin and
tip the ball into the basin.

## Goal
Success: both forks hold the tray steadily together, the ball in it; carried on both forks, the tray passes waypoint A
and then waypoint B; when the ball is pushed, the arms bring it back to rest near the tray's centre, both forks still
supporting the tray; the tray is brought, on both forks, to the exit position beside the basin; finally the ball is
tipped out and settles in the basin, clear of the tray.

The steps count only in this order. Once a step is done, it stays done. The replay ends as soon as the task is done or
has failed; the task also fails at once when:
- the ball leaves the tray before it is tipped out;
- the tray drops low (well below where it starts) at any time;
- the task's horizon is reached before the task is done (Robot Interface);
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not: the forks may touch only the tray and the ball, a fork must not touch its own
  arm, no other robot part may touch anything, and the two arms must never touch each other;
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

### Arms and tools
panda-0 (left): base at (-0.55, -0.22, 0), yaw 0 (facing +x). panda-1 (right): base at (0.74, 0.22, 0), yaw pi (facing
-x). Each carries a support fork: a small, shallow square cradle 0.07 m x 0.07 m inside. It has a 5 mm floor and 18 mm
high walls on three sides, is open on the tool +x side, and is held by an adapter on its closed tool -x wall. The tool
frame is the centre of the cradle floor's top surface, z up. The TCP sits 0.12 m along tool -x and 0.04 m above the tool
frame. Left fork start: (-0.075, 0, 0.22), orientation identity (open side toward world +x). Right fork start: (0.215,
0, 0.22), quaternion (0, 0, 0, 1) (yawed 180 deg, open side toward world -x). The two open sides face each other. In
this task both arms' servos plan their reference motion with lower acceleration and jerk fractions than usual (0.30 and
0.025, default 0.55 and 0.05). On both arms the tool's adapter runs between the fingertips. If you close a gripper to
less than about 12 mm of aperture, its fingers touch the adapter, and the episode ends as a collision with its own tool.
Both grippers start fully open, at 0.08 m.

### Safety
The task fails when an arm goes beyond the Franka Panda's own safety limits. These limits cover joint positions, joint
and finger speeds, the hand's speed and acceleration, joint accelerations and jerks, motor torques, and how fast the
torques change. The numbers are in the robot spec's `safety_limits`. The limits apply to the motion as measured,
whatever was commanded (a catch or a strike moves the arm too). The servo's own reference motion must also stay within
the same speed, acceleration and jerk limits.

### Goal points
- The waypoints and the exit position are not marked. They are for the centre of the tray's floor, in the world frame:
  waypoint A (0.12, -0.04, 0.27), then waypoint B (0.02, 0.08, 0.27), each within a few centimetres; the exit position
  (0.12, 0.18) across the table, at any height, within a few centimetres.

## Others
- State labels (`s.objects()`, `s.fixtures()`): `tray` is the tray, `ball` the ball.
- The ball gets one push the moment the tray reaches waypoint B.

## Limits
- Time: 3600 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 5 CPUs, 10 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (3 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like (`s.reset()`).
