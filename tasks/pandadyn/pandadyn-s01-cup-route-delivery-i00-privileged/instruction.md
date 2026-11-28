# Panda Dynamic Scenes · Cup catch, route pour, rebound recatch and cart delivery (S01) (privileged)

## Task
Catch the falling ball in the cup and pour it into the channel farther from you. Let it roll down by itself and bounce
off the plate below its end, catch it again in flight, and put it into the sliding cart while the cart is moving.

## Goal
Success: the cup catches the falling ball and pours it into the channel farther from the robot; the ball rolls down by
itself, drops off the end and bounces off that channel's rebound plate; the cup catches it again in flight; finally the
ball rests in the cart, clear of the cup, while the cart moves. A catch means the ball drops into the cup from above
after flying free and stays there.

The steps count only in this order. Once a step is done, it stays done. The replay ends as soon as the task is done or
has failed; the task also fails at once when:
- the ball touches the other channel while it is being poured;
- the ball touches the table or the cup between the pour and the rebound;
- the task's horizon is reached before the task is done (Robot Interface);
- an object leaves the workspace (falls well below the table top or flies far away);
- a robot part touches what it may not: only the cup may touch anything, and only the ball;
- an arm touches itself, a robot part touches the table or the floor, or a contact presses deep into anything;
- an arm goes beyond the Franka Panda's own safety limits (Robot Interface, Safety).

Deliverable: `/app/output/trajectory.npz`, written with `Session.save_trajectory(...)`. It holds `task` and `actions`;
`actions` is a (T, 8) float array of at most 4,500 rows, one per control step. Anything else (another shape, NaN, more
rows, a file that is not such an npz) scores 0. It is replayed open-loop from the fixed start and scores 1 if the task
succeeds in the replay, else 0. Keep the script that produced it at `/app/output/gen.py`. Save a valid one early and
overwrite it when you have a better one.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed.

## Robot Interface
One simulated Franka Panda arm (7 joints, its standard hand, and the task's tool where it has one) on a table (ManiSkill
3 / SAPIEN, rigid-body physics at 1000 Hz). The scene is one fixed instance: everything starts the same way after every
reset. Things move by themselves from the first control step on: the scene does not wait for the robot. You have the
full simulator to develop with; you hand in a trajectory of robot actions.

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
- Action row (8 values per control step): `[joint1..7, aperture]`. Each arm has 8 values: its 7 absolute joint-position
  targets (rad, `panda_joint1..7`) and its total gripper aperture target (m, 0 = closed .. 0.08 = open). Each finger
  moves at most 0.025 m/s. Values outside the joint limits (`s.robot_spec()`) are clipped to them before they are
  executed, and the trajectory records the clipped row.
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
One Panda, base at (-0.55, 0, 0), yaw 0 (facing +x). Its hand carries a blue square cup closed on all four sides: inner
0.14 m x 0.14 m, walls 0.028 m high and 5 mm thick, floor 5 mm thick. The tool frame is the centre of the cup's inner
floor (top surface of the bottom plate), z up out of the opening, x and y along the walls. A rigid dark-grey adapter on
the cup's -x side joins it to the hand: a horizontal bar 0.035 m above the floor (tool-frame x from -0.152 to -0.058)
and a short vertical post at the middle of the -x wall (rising 7 mm above the rim and protruding 6 mm into the cup);
both are part of the tool. The Panda TCP is at (-0.12, 0, 0.04) in the tool frame, so with the cup level the gripper
points straight down just behind the cup's -x wall. At the start the cup is level (tool axes aligned with the world
axes), its frame origin at (-0.16, -0.32, 0.23). The tool's adapter runs between the gripper's fingertips. If you close
the gripper to less than about 12 mm of aperture, the fingers touch the adapter, and the episode ends as a collision
with its own tool. The gripper starts fully open, at 0.08 m.

### Safety
The task fails when an arm goes beyond the Franka Panda's own safety limits. These limits cover joint positions, joint
and finger speeds, the hand's speed and acceleration, joint accelerations and jerks, motor torques, and how fast the
torques change. The numbers are in the robot spec's `safety_limits`. The limits apply to the motion as measured,
whatever was commanded (a catch or a strike moves the arm too). The servo's own reference motion must also stay within
the same speed, acceleration and jerk limits.

## Others
- State labels (`s.objects()`, `s.fixtures()`): `ball` is the ball; `cart` (in `s.fixtures()`) the cart.
- The ball is already in flight when the episode starts and comes down within about a second.

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
